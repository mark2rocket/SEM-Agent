"""Slack event handlers and slash commands."""

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import json
import logging
from typing import TYPE_CHECKING

from ...core.security import verify_slack_signature, decrypt_token
from ...api.deps import get_db
from ...config import settings
from ...models.oauth import OAuthToken, OAuthProvider
from ...services.intent_service import IntentService
from ...services.conversation_service import ConversationService
from ...services.action_router import ActionRouter
from ...services.slack_service import SlackService

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
router = APIRouter()

# Global set to keep strong references to background tasks
_background_tasks = set()


def get_google_ads_service(tenant_id: int, db: Session):
    """Get GoogleAdsService with credentials from OAuth tokens and settings.

    Args:
        tenant_id: The tenant ID to fetch credentials for
        db: Database session

    Returns:
        GoogleAdsService instance with credentials

    Raises:
        HTTPException: If Google Ads OAuth token not found
    """
    from ...services.google_ads_service import GoogleAdsService

    # Get OAuth token for tenant
    oauth_token = db.query(OAuthToken).filter(
        OAuthToken.tenant_id == tenant_id,
        OAuthToken.provider == OAuthProvider.GOOGLE
    ).first()

    if not oauth_token or not oauth_token.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google Ads not authorized. Please authorize Google Ads first."
        )

    # Decrypt refresh token
    refresh_token = decrypt_token(oauth_token.refresh_token)

    return GoogleAdsService(
        developer_token=settings.google_developer_token,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        refresh_token=refresh_token,
        login_customer_id=settings.google_login_customer_id
    )


async def handle_message_event(event: dict, db: Session):
    """Process message events for natural language conversations.

    Args:
        event: Slack event payload containing message data
        db: Database session
    """
    try:
        # Ignore bot messages to prevent loops
        if event.get("bot_id"):
            logger.debug("Ignoring bot message")
            return

        # Ignore message_changed and message_deleted events
        if event.get("subtype") in ["message_changed", "message_deleted"]:
            logger.debug(f"Ignoring message subtype: {event.get('subtype')}")
            return

        # Extract event data
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")  # Use message ts if not in thread
        team_id = event.get("team")

        if not all([user_id, channel_id, text, team_id]):
            logger.warning("Missing required fields in message event")
            return

        logger.info(f"Processing message from user {user_id} in channel {channel_id}")

        # Get or create tenant from team_id
        from ...models.tenant import Tenant
        tenant = db.query(Tenant).filter_by(workspace_id=team_id).first()
        if not tenant:
            logger.info(f"Creating new tenant for workspace {team_id}")
            tenant = Tenant(
                workspace_id=team_id,
                workspace_name=team_id,
                slack_channel_id=channel_id,
                is_active=True
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # Initialize services with correct dependencies
        from ...services.gemini_service import GeminiService
        from ...services.report_service import ReportService
        from ...services.keyword_service import KeywordService
        from ...core.redis_client import redis_client

        # Initialize core services
        gemini_service = GeminiService(api_key=settings.gemini_api_key)
        google_ads_service = get_google_ads_service(tenant.id, db)
        slack_service = SlackService(bot_token=tenant.bot_token or settings.slack_bot_token)

        # Initialize business services with correct dependencies
        conversation_service = ConversationService(db, redis_client)
        intent_service = IntentService(gemini_service)
        report_service = ReportService(db, google_ads_service, gemini_service, slack_service)
        keyword_service = KeywordService(db, google_ads_service, slack_service)

        # Initialize action router with all required services
        action_router = ActionRouter(
            db=db,
            report_service=report_service,
            keyword_service=keyword_service,
            google_ads_service=google_ads_service,
            gemini_service=gemini_service
        )

        # Get or create conversation
        conversation = conversation_service.get_or_create_conversation(
            tenant_id=tenant.id,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts
        )

        # Get conversation history for context (last 5 messages)
        history = conversation_service.get_conversation_history(
            conversation_id=conversation.id,
            limit=5
        )

        # Parse intent from message
        intent_result = intent_service.parse_intent(text, history)
        logger.info(f"Parsed intent: {intent_result['intent']}")

        # Add original message text to entities for general chat handler
        intent_result['entities']['original_message'] = text

        # Route action based on intent
        response_text = await action_router.route_action(
            intent=intent_result['intent'],
            entities=intent_result['entities'],
            tenant_id=tenant.id,
            conversation_history=history
        )

        # Save user message and bot response
        conversation_service.save_message(
            conversation_id=conversation.id,
            user_id=user_id,
            message_text=text,
            intent_type=intent_result['intent'],
            entities=intent_result['entities'],
            bot_response=response_text
        )

        # Send response to Slack in thread
        slack_service.client.chat_postMessage(
            channel=channel_id,
            text=response_text,
            thread_ts=thread_ts
        )

        logger.info("Successfully processed message and sent response")

    except Exception as e:
        logger.error(f"Error handling message event: {str(e)}", exc_info=True)
        # Try to send user-friendly error message
        try:
            error_slack_service = SlackService(bot_token=tenant.bot_token or settings.slack_bot_token)
            error_slack_service.client.chat_postMessage(
                channel=channel_id,
                text="죄송합니다. 메시지 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                thread_ts=thread_ts
            )
        except Exception:
            logger.error("Failed to send error message to user")


@router.post("/events")
async def slack_events(request: Request, db: Session = Depends(get_db)):
    """Handle Slack events."""
    body = await request.body()
    body_str = body.decode("utf-8")

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body_str, timestamp, signature, settings.slack_signing_secret):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(body_str)

    # Handle URL verification
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # Handle event callbacks
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        event_type = event.get("type")

        # Add team_id to event for tenant lookup
        event["team"] = payload.get("team_id")

        # Handle message and app_mention events
        if event_type in ["message", "app_mention"]:
            await handle_message_event(event, db)

    return {"ok": True}


@router.post("/commands")
async def slack_commands(request: Request, db: Session = Depends(get_db)):
    """Handle Slack slash commands."""
    try:
        # Read raw body first for signature verification
        body = await request.body()
        body_str = body.decode("utf-8")

        # Verify signature
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")

        if not verify_slack_signature(body_str, timestamp, signature, settings.slack_signing_secret):
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse form data from body string
        from urllib.parse import parse_qs
        form_dict = parse_qs(body_str)
        command = form_dict.get("command", [""])[0]
        text = form_dict.get("text", [""])[0].strip()
        user_id = form_dict.get("user_id", [""])[0]
        channel_id = form_dict.get("channel_id", [""])[0]
        team_id = form_dict.get("team_id", [""])[0]
        team_domain = form_dict.get("team_domain", [""])[0]

        logger.info(f"Received command: {command} from user {user_id} in channel {channel_id}")

        # Ensure tenant exists (auto-create if needed)
        from ...models.tenant import Tenant
        tenant = db.query(Tenant).filter_by(workspace_id=team_id).first()
        if not tenant:
            logger.info(f"Creating new tenant for workspace {team_id}")
            tenant = Tenant(
                workspace_id=team_id,
                workspace_name=team_domain or team_id,
                slack_channel_id=channel_id,
                is_active=True
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # Handle /sem-help command
        if command == "/sem-help":
            return {
                "response_type": "ephemeral",
                "text": "🤖 *SEM-Agent 도움말*\n\n"
                        "*사용 가능한 명령어:*\n"
                        "• `/sem-help` - 이 도움말 표시\n"
                        "• `/sem-connect` - 계정 연동 (Google Ads, Search Console)\n"
                        "• `/sem-config` - 리포트 설정 변경\n"
                        "• `/sem-report` - 즉시 리포트 생성\n\n"
                        "💡 처음 사용하신다면 `/sem-connect`로 계정을 먼저 연동하세요."
            }

        # Handle /sem-connect command
        elif command == "/sem-connect":
            return handle_connect_command(tenant)

        # Handle /sem-config command
        elif command == "/sem-config":
            return await handle_config_command(db, channel_id, text)

        # Handle /sem-report command
        elif command == "/sem-report":
            return await handle_report_command(db, channel_id)

        # Unknown command
        else:
            return {
                "response_type": "ephemeral",
                "text": "알 수 없는 명령어입니다. `/sem-help`를 입력해서 사용 가능한 명령어를 확인하세요."
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling command: {str(e)}", exc_info=True)
        return {
            "response_type": "ephemeral",
            "text": f"명령어 처리 중 오류가 발생했습니다: {str(e)}"
        }


def handle_connect_command(tenant):
    """Handle /sem-connect command - show account connection menu."""
    google_auth_url = f"https://sem-agent.up.railway.app/oauth/google/authorize?tenant_id={tenant.id}"
    gsc_auth_url = f"https://sem-agent.up.railway.app/oauth/gsc/authorize?tenant_id={tenant.id}"
    return {
        "response_type": "ephemeral",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔗 계정 연동하기", "emoji": True}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "연동할 서비스를 선택하세요:"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📊 Google Ads 연동", "emoji": True},
                        "style": "primary",
                        "url": google_auth_url,
                        "action_id": "connect_google_ads"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔍 Search Console 연동", "emoji": True},
                        "style": "primary",
                        "url": gsc_auth_url,
                        "action_id": "connect_search_console"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 Search Console 연동 시 Google Ads 리포트와 함께 SEO 성과도 자동으로 받아볼 수 있습니다."
                    }
                ]
            }
        ]
    }


async def handle_config_command(db: Session, channel_id: str, text: str):
    """Handle /sem-config command for report scheduling."""
    from ...models.tenant import Tenant
    from ...models.report import ReportSchedule, ReportFrequency
    from ...models.google_ads import GoogleAdsAccount
    from datetime import time

    # Find tenant by channel
    tenant = db.query(Tenant).filter_by(slack_channel_id=channel_id).first()
    if not tenant:
        return {
            "response_type": "ephemeral",
            "text": "채널을 찾을 수 없습니다. 먼저 봇을 설치해주세요."
        }

    # Get or create report schedule
    schedule = db.query(ReportSchedule).filter_by(tenant_id=tenant.id).first()
    if not schedule:
        schedule = ReportSchedule(
            tenant_id=tenant.id,
            frequency=ReportFrequency.WEEKLY,
            day_of_week=0,  # Monday
            time_of_day=time(9, 0)
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)

    # Parse configuration from text
    if text:
        parts = text.lower().split()

        # Parse frequency
        if "daily" in parts or "매일" in parts:
            schedule.frequency = ReportFrequency.DAILY
        elif "weekly" in parts or "매주" in parts:
            schedule.frequency = ReportFrequency.WEEKLY
        elif "monthly" in parts or "매월" in parts:
            schedule.frequency = ReportFrequency.MONTHLY
        elif "disabled" in parts or "끄기" in parts or "off" in parts:
            schedule.frequency = ReportFrequency.DISABLED

        # Parse time (look for HH:MM pattern)
        for part in parts:
            if ":" in part:
                try:
                    hour, minute = map(int, part.split(":"))
                    if 0 <= hour < 24 and 0 <= minute < 60:
                        schedule.time_of_day = time(hour, minute)
                except ValueError:
                    pass

        db.commit()
        db.refresh(schedule)

    # Build frequency text for response
    frequency_text = {
        ReportFrequency.DAILY: "매일",
        ReportFrequency.WEEKLY: "매주 월요일",
        ReportFrequency.MONTHLY: "매월 1일",
        ReportFrequency.DISABLED: "비활성화"
    }.get(schedule.frequency, "알 수 없음")

    time_text = schedule.time_of_day.strftime("%H:%M")

    # After schedule update, show campaign selection UI
    try:
        # Get Google Ads account for customer_id
        account = db.query(GoogleAdsAccount).filter_by(
            tenant_id=tenant.id, is_active=True
        ).first()

        if account:
            # Fetch campaigns
            google_ads_service = get_google_ads_service(tenant.id, db)
            campaigns = google_ads_service.list_campaigns(account.customer_id)

            if campaigns:
                # Build checkbox options for campaigns
                checkbox_options = []
                for campaign in campaigns:
                    checkbox_options.append({
                        "text": {
                            "type": "plain_text",
                            "text": f"{campaign['name']} ({campaign['status']})"
                        },
                        "value": campaign['id']
                    })

                # Get currently selected campaign IDs
                selected_values = []
                if schedule.campaign_ids:
                    selected_values = schedule.campaign_ids.split(',')

                # Build Block Kit message with checkboxes
                blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"📅 *리포트 설정 완료*\n\n"
                                    f"• 주기: {frequency_text}\n"
                                    f"• 시간: {time_text} (KST)\n"
                                    f"• 상태: {'활성화' if schedule.is_active else '비활성화'}"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*리포트에 포함할 캠페인을 선택하세요:*\n선택하지 않으면 모든 캠페인이 포함됩니다."
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "checkboxes",
                                "action_id": "select_campaigns_config",
                                "options": checkbox_options,
                                "initial_options": [
                                    {"text": {"type": "plain_text", "text": next((c['name'] for c in campaigns if c['id'] == val), val)}, "value": val}
                                    for val in selected_values
                                    if any(c['id'] == val for c in campaigns)
                                ] if selected_values else []
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"💡 총 {len(campaigns)}개의 캠페인이 있습니다."
                            }
                        ]
                    }
                ]

                return {
                    "response_type": "ephemeral",
                    "blocks": blocks
                }

    except Exception as e:
        logger.error(f"Error fetching campaigns for config: {str(e)}", exc_info=True)
        # Fall back to simple text response

    # Fallback response (no campaigns or error)
    return {
        "response_type": "ephemeral",
        "text": f"📅 *리포트 설정*\n\n"
                f"• 주기: {frequency_text}\n"
                f"• 시간: {time_text} (KST)\n"
                f"• 상태: {'활성화' if schedule.is_active else '비활성화'}\n\n"
                f"*사용법:*\n"
                f"`/sem-config daily 09:00` - 매일 오전 9시\n"
                f"`/sem-config weekly 14:00` - 매주 월요일 오후 2시\n"
                f"`/sem-config monthly 09:00` - 매월 1일 오전 9시\n"
                f"`/sem-config off` - 자동 리포트 끄기"
    }


async def handle_report_command(db: Session, channel_id: str):
    """Handle /sem-report command for immediate report generation."""
    from ...models.tenant import Tenant
    from ...models.google_ads import GoogleAdsAccount
    from ...models.report import ReportSchedule

    # Find tenant by channel
    tenant = db.query(Tenant).filter_by(slack_channel_id=channel_id).first()
    if not tenant:
        return {
            "response_type": "ephemeral",
            "text": "채널을 찾을 수 없습니다. 먼저 봇을 설치해주세요."
        }

    # Initialize services
    try:
        google_ads_service = get_google_ads_service(tenant.id, db)
    except HTTPException:
        # Google Ads not connected
        google_auth_url = f"https://sem-agent.up.railway.app/oauth/google/authorize?tenant_id={tenant.id}"
        return {
            "response_type": "ephemeral",
            "text": f"❌ Google Ads 계정이 연동되지 않았습니다.\n\n"
                    f"📊 *리포트를 생성하려면 먼저 Google Ads 계정을 연동하세요:*\n"
                    f"<{google_auth_url}|여기를 클릭하여 계정 연동>\n\n"
                    f"연동 후 다시 `/sem-report` 명령어를 입력해주세요."
        }

    # Fetch campaigns and show selection UI
    try:
        # Get Google Ads account for customer_id
        account = db.query(GoogleAdsAccount).filter_by(
            tenant_id=tenant.id, is_active=True
        ).first()

        if not account:
            return {
                "response_type": "ephemeral",
                "text": "❌ Google Ads 계정을 찾을 수 없습니다."
            }

        # Fetch campaigns
        campaigns = google_ads_service.list_campaigns(account.customer_id)

        if not campaigns:
            return {
                "response_type": "ephemeral",
                "text": "❌ 사용 가능한 캠페인이 없습니다."
            }

        # Build checkbox options for campaigns
        checkbox_options = []
        for campaign in campaigns:
            checkbox_options.append({
                "text": {
                    "type": "plain_text",
                    "text": f"{campaign['name']} ({campaign['status']})"
                },
                "value": campaign['id']
            })

        # Get currently saved campaign selections (if any)
        schedule = db.query(ReportSchedule).filter_by(tenant_id=tenant.id).first()
        selected_values = []
        if schedule and schedule.campaign_ids:
            selected_values = schedule.campaign_ids.split(',')

        # Build initial_options (must match options text exactly, omit if empty)
        matched_initial = [
            {
                "text": {"type": "plain_text", "text": f"{c['name']} ({c['status']})"},
                "value": c['id']
            }
            for val in selected_values
            for c in campaigns
            if c['id'] == val
        ] if selected_values else []

        checkbox_element = {
            "type": "checkboxes",
            "action_id": "select_campaigns_report",
            "options": checkbox_options,
        }
        if matched_initial:
            checkbox_element["initial_options"] = matched_initial

        # Build Block Kit message with checkboxes
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "📊 *리포트 생성*\n\n리포트에 포함할 캠페인을 선택하세요:"
                }
            },
            {
                "type": "actions",
                "elements": [checkbox_element]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"💡 총 {len(campaigns)}개의 캠페인이 있습니다. 선택하지 않으면 모든 캠페인이 포함됩니다."
                    }
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📊 리포트 생성"},
                        "style": "primary",
                        "action_id": "generate_report_button"
                    }
                ]
            }
        ]

        return {
            "response_type": "ephemeral",
            "blocks": blocks
        }

    except Exception as e:
        logger.error(f"Error fetching campaigns for report: {str(e)}", exc_info=True)
        return {
            "response_type": "ephemeral",
            "text": f"캠페인 조회 중 오류가 발생했습니다: {str(e)}"
        }


async def _generate_report_async(
    tenant_id: int,
    channel_id: str,
    selected_campaign_ids: list[str] = None,
    response_url: str = None
):
    """Generate report asynchronously with proper error handling.

    Args:
        tenant_id: The tenant ID
        channel_id: Slack channel ID to post results/errors to
        selected_campaign_ids: List of campaign IDs to include in report (optional)
    """
    from ...api.deps import get_db
    from ...models.tenant import Tenant
    from ...services.report_service import ReportService
    from ...services.gemini_service import GeminiService
    from ...services.slack_service import SlackService

    # Create new DB session for this background task
    db = next(get_db())
    notify_channel = channel_id  # Slack 알림 채널 (fallback은 tenant 로드 후 결정)

    def _slack_notify(slack_svc, ch, text):
        """안전하게 Slack 알림 전송."""
        if not ch:
            logger.warning(f"No channel to notify: {text}")
            return
        try:
            slack_svc.client.chat_postMessage(channel=ch, text=text)
        except Exception as e:
            logger.error(f"Failed to post to Slack: {e}")

    try:
        # Fetch tenant
        tenant = db.query(Tenant).filter_by(id=tenant_id).first()
        if not tenant:
            logger.error(f"Tenant {tenant_id} not found for async report generation")
            return

        notify_channel = channel_id or tenant.slack_channel_id

        # response_url로 "생성 중" 메시지 전송 (백그라운드에서 처리)
        if response_url:
            import requests as http_requests
            try:
                http_requests.post(
                    response_url,
                    json={"text": "📊 리포트를 생성 중입니다...", "replace_original": True},
                    timeout=5
                )
            except Exception as e:
                logger.warning(f"[Report] Failed to update response_url: {e}")

        # Initialize services with fresh instances
        logger.info(f"[Report] Step 1: Initializing services for tenant {tenant_id}")
        google_ads_service = get_google_ads_service(tenant_id, db)
        gemini_service = GeminiService(api_key=settings.gemini_api_key)

        # Slack bot token은 OAuthToken 테이블에 암호화 저장됨 → 복호화 필요
        slack_oauth = db.query(OAuthToken).filter(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.provider == OAuthProvider.SLACK
        ).first()
        if slack_oauth and slack_oauth.access_token:
            slack_bot_token = decrypt_token(slack_oauth.access_token)
            logger.info("[Report] Using decrypted Slack token from OAuthToken table")
        else:
            slack_bot_token = settings.slack_bot_token
            logger.warning("[Report] No Slack OAuthToken found, using settings token")
        slack_service = SlackService(bot_token=slack_bot_token)

        report_service = ReportService(
            db=db,
            google_ads_service=google_ads_service,
            gemini_service=gemini_service,
            slack_service=slack_service
        )

        logger.info(f"[Report] Step 2: Generating reports for tenant {tenant_id}, campaigns={selected_campaign_ids}, channel={notify_channel}")
        import asyncio

        # 캠페인별 개별 리포트 생성 (선택된 캠페인이 없으면 전체 1개)
        campaigns_to_process = selected_campaign_ids if selected_campaign_ids else [None]
        any_success = False

        for i, campaign_id in enumerate(campaigns_to_process):
            override = [campaign_id] if campaign_id else None
            result = await asyncio.to_thread(
                report_service.generate_weekly_report,
                tenant_id,
                notify_channel=notify_channel,
                response_url=response_url,
                override_campaign_ids=override
            )
            if result.get("status") == "error":
                error_msg = result.get("message", "알 수 없는 오류")
                logger.error(f"[Report] Campaign {campaign_id} failed: {error_msg}")
                _slack_notify(slack_service, notify_channel, f"❌ 리포트 생성 실패 (캠페인 {campaign_id}): {error_msg}")
            else:
                any_success = True
                logger.info(f"[Report] Campaign {campaign_id} success: {result}")

        # GSC 리포트 생성 (Search Console 연동된 경우 자동으로 추가)
        logger.info(f"[Report] Step 3: Generating GSC report for tenant {tenant_id}")
        gsc_result = await asyncio.to_thread(
            report_service.generate_gsc_report,
            tenant_id,
            notify_channel=notify_channel,
            response_url=response_url
        )
        if gsc_result.get("status") == "skipped":
            logger.info("[Report] GSC report skipped (no Search Console account connected)")
        elif gsc_result.get("status") == "error":
            logger.warning(f"[Report] GSC report failed: {gsc_result.get('message')}")
        else:
            logger.info("[Report] GSC report generated successfully")

        if any_success and response_url:
            import requests as http_requests
            try:
                http_requests.post(response_url, json={"delete_original": True}, timeout=5)
            except Exception as ru_err:
                logger.warning(f"[Report] Failed to delete ephemeral message: {ru_err}")
        elif not any_success and response_url:
            import requests as http_requests
            try:
                http_requests.post(response_url, json={"text": "❌ 리포트 생성에 실패했습니다.", "replace_original": True}, timeout=5)
            except Exception as ru_err:
                logger.warning(f"[Report] Failed to update response_url: {ru_err}")

    except HTTPException as e:
        logger.error(f"[Report] HTTP error: {e.detail}", exc_info=True)
        err_text = f"❌ 리포트 생성 중 오류: {e.detail}"
        try:
            slack_service = SlackService(bot_token=settings.slack_bot_token)
            _slack_notify(slack_service, notify_channel, err_text)
        except Exception as slack_error:
            logger.error(f"Failed to post error to Slack: {slack_error}")
        if response_url:
            import requests as http_requests
            try:
                http_requests.post(response_url, json={"text": err_text, "replace_original": True}, timeout=5)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[Report] Unexpected error: {str(e)}", exc_info=True)
        err_text = f"❌ 리포트 생성 중 오류: {str(e)}"
        try:
            tenant = db.query(Tenant).filter_by(id=tenant_id).first()
            bot_token = (tenant.bot_token if tenant else None) or settings.slack_bot_token
            slack_service = SlackService(bot_token=bot_token)
            _slack_notify(slack_service, notify_channel, err_text)
        except Exception as slack_error:
            logger.error(f"Failed to post error to Slack: {slack_error}")
        if response_url:
            import requests as http_requests
            try:
                http_requests.post(response_url, json={"text": err_text, "replace_original": True}, timeout=5)
            except Exception:
                pass
    finally:
        db.close()


@router.post("/interactions")
async def slack_interactions(request: Request, db: Session = Depends(get_db)):
    """Handle Slack interactive components."""
    body = await request.body()
    body_str = body.decode("utf-8")

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body_str, timestamp, signature, settings.slack_signing_secret):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse Slack interaction payload (JSON in form field)
    form_data = await request.form()
    payload = json.loads(form_data.get("payload"))

    user_id = payload["user"]["id"]
    # channel_id: ephemeral 메시지 인터랙션 시 payload.channel이 없을 수 있음
    channel_id = (
        payload.get("channel", {}).get("id")
        or payload.get("container", {}).get("channel_id")
        or ""
    )
    response_url = payload.get("response_url", "")
    actions = payload.get("actions", [])

    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action["action_id"]

    # Import services here to avoid circular imports
    from ...services.keyword_service import KeywordService
    from ...services.slack_service import SlackService

    # Find tenant by workspace_id from Slack payload
    from ...models.tenant import Tenant
    workspace_id = payload["team"]["id"]
    tenant = db.query(Tenant).filter(
        Tenant.workspace_id == workspace_id
    ).first()

    if not tenant:
        return {
            "text": "❌ 테넌트를 찾을 수 없습니다",
            "replace_original": False,
            "response_type": "ephemeral"
        }

    # Initialize services
    google_ads_service = get_google_ads_service(tenant.id, db)
    slack_service = SlackService(bot_token=tenant.bot_token or settings.slack_bot_token)
    keyword_service = KeywordService(db, google_ads_service, slack_service)

    if action_id == "select_campaigns_config":
        # Handle campaign selection for config flow
        from ...models.report import ReportSchedule

        # Get selected campaign IDs from action
        selected_options = action.get("selected_options", [])
        selected_campaign_ids = [opt["value"] for opt in selected_options]

        # Update ReportSchedule with selected campaigns
        schedule = db.query(ReportSchedule).filter_by(tenant_id=tenant.id).first()
        if schedule:
            # Store as comma-separated string
            schedule.campaign_ids = ','.join(selected_campaign_ids) if selected_campaign_ids else None
            db.commit()

            return {
                "text": f"✅ 캠페인 선택이 저장되었습니다.\n선택된 캠페인: {len(selected_campaign_ids)}개" if selected_campaign_ids else "✅ 모든 캠페인이 리포트에 포함됩니다.",
                "replace_original": True,
                "response_type": "ephemeral"
            }
        else:
            return {
                "text": "❌ 리포트 설정을 찾을 수 없습니다",
                "replace_original": False,
                "response_type": "ephemeral"
            }

    elif action_id == "select_campaigns_report":
        # 체크박스 선택 시 DB에 저장만 하고 리포트는 생성하지 않음
        from ...models.report import ReportSchedule

        selected_options = action.get("selected_options", [])
        selected_campaign_ids = [opt["value"] for opt in selected_options]

        schedule = db.query(ReportSchedule).filter_by(tenant_id=tenant.id).first()
        if not schedule:
            from ...models.report import ReportFrequency
            from datetime import time
            schedule = ReportSchedule(
                tenant_id=tenant.id,
                frequency=ReportFrequency.WEEKLY,
                day_of_week=0,
                time_of_day=time(9, 0)
            )
            db.add(schedule)

        schedule.campaign_ids = ','.join(selected_campaign_ids) if selected_campaign_ids else None
        db.commit()

        # 선택 저장 완료 - 빈 200 응답으로 체크박스 UI 유지
        return {"ok": True}

    elif action_id == "generate_report_button":
        # "리포트 생성" 버튼 클릭 시 DB에 저장된 선택으로 리포트 생성
        from ...models.report import ReportSchedule

        schedule = db.query(ReportSchedule).filter_by(tenant_id=tenant.id).first()
        selected_campaign_ids = (
            schedule.campaign_ids.split(',') if schedule and schedule.campaign_ids else []
        )

        # channel_id가 없으면 tenant의 저장된 채널 사용
        report_channel_id = channel_id or tenant.slack_channel_id or ""

        # response_url과 리포트 생성을 모두 백그라운드에서 처리 → 즉시 {"ok": True} 반환
        import asyncio
        task = asyncio.create_task(
            _generate_report_async(
                tenant_id=tenant.id,
                channel_id=report_channel_id,
                selected_campaign_ids=selected_campaign_ids,
                response_url=response_url
            )
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        return {"ok": True}

    elif action_id == "approve_keyword":
        # Get approval_request_id from action value
        approval_request_id = int(action.get("value"))

        # Approve keyword
        success = keyword_service.approve_keyword(approval_request_id, user_id)

        if success:
            # Get approval details for updated message
            from ...models.keyword import ApprovalRequest
            approval = db.query(ApprovalRequest).filter_by(id=approval_request_id).first()
            keyword = approval.keyword_candidate if approval else None

            response_text = "✅ 제외 키워드로 등록되었습니다"
            if keyword:
                response_text += f"\n승인자: <@{user_id}>\n승인 시각: {approval.responded_at.strftime('%Y-%m-%d %H:%M:%S')}"

            return {
                "text": response_text,
                "replace_original": True
            }
        else:
            return {
                "text": "❌ 처리 중 오류가 발생했습니다",
                "replace_original": False,
                "response_type": "ephemeral"
            }

    elif action_id == "connect_search_console":
        # URL 버튼 클릭 → Slack이 직접 브라우저를 열어줌, 별도 처리 불필요
        return {"ok": True}

    elif action_id == "connect_google_ads":
        # URL 버튼 클릭 시 interaction 수신 - 별도 처리 불필요
        return {"ok": True}

    elif action_id == "ignore_keyword":
        # Get approval_request_id from action value
        approval_request_id = int(action.get("value"))

        # Import models
        from ...models.keyword import ApprovalRequest, ApprovalAction
        from datetime import datetime

        # Update ApprovalRequest
        approval = db.query(ApprovalRequest).filter_by(id=approval_request_id).first()

        if not approval:
            return {
                "text": "❌ 요청을 찾을 수 없습니다",
                "replace_original": False,
                "response_type": "ephemeral"
            }

        if approval.responded_at:
            return {
                "text": "⚠️ 이미 처리된 요청입니다",
                "replace_original": False,
                "response_type": "ephemeral"
            }

        # Update approval request
        approval.responded_at = datetime.utcnow()
        approval.approved_by = user_id
        approval.action = ApprovalAction.IGNORE
        db.commit()

        return {
            "text": f"무시됨\n처리자: <@{user_id}>\n처리 시각: {approval.responded_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "replace_original": True
        }

    return {"ok": True}
