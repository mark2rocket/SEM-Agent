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

if TYPE_CHECKING:
    from ...services.report_service import ReportService

logger = logging.getLogger(__name__)
router = APIRouter()


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
            google_auth_url = "https://sem-agent.up.railway.app/oauth/google/authorize"
            return {
                "response_type": "ephemeral",
                "text": "🤖 *SEM-Agent 도움말*\n\n"
                        "*사용 가능한 명령어:*\n"
                        "• `/sem-help` - 이 도움말 표시\n"
                        "• `/sem-config` - 리포트 설정 변경\n"
                        "• `/sem-report` - 즉시 리포트 생성\n\n"
                        "*시작하기:*\n"
                        f"1. 📊 *Google Ads 연동*: <{google_auth_url}|여기를 클릭하여 계정 연동>\n"
                        "2. `/sem-config`로 리포트 주기 설정\n"
                        "3. `/sem-report`로 즉시 리포트 확인\n\n"
                        "💡 리포트를 생성하려면 먼저 Google Ads 계정을 연동해야 합니다."
            }

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


async def handle_config_command(db: Session, channel_id: str, text: str):
    """Handle /sem-config command for report scheduling."""
    from ...models.tenant import Tenant
    from ...models.report import ReportSchedule, ReportFrequency
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

    # Build response message
    frequency_text = {
        ReportFrequency.DAILY: "매일",
        ReportFrequency.WEEKLY: "매주 월요일",
        ReportFrequency.MONTHLY: "매월 1일",
        ReportFrequency.DISABLED: "비활성화"
    }.get(schedule.frequency, "알 수 없음")

    time_text = schedule.time_of_day.strftime("%H:%M")

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
    from ...services.report_service import ReportService
    from ...services.google_ads_service import GoogleAdsService
    from ...services.gemini_service import GeminiService
    from ...services.slack_service import SlackService

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
        google_auth_url = "https://sem-agent.up.railway.app/oauth/google/authorize"
        return {
            "response_type": "ephemeral",
            "text": f"❌ Google Ads 계정이 연동되지 않았습니다.\n\n"
                    f"📊 *리포트를 생성하려면 먼저 Google Ads 계정을 연동하세요:*\n"
                    f"<{google_auth_url}|여기를 클릭하여 계정 연동>\n\n"
                    f"연동 후 다시 `/sem-report` 명령어를 입력해주세요."
        }

    gemini_service = GeminiService(api_key=settings.gemini_api_key)
    slack_service = SlackService(bot_token=tenant.bot_token)

    report_service = ReportService(
        db=db,
        google_ads_service=google_ads_service,
        gemini_service=gemini_service,
        slack_service=slack_service
    )

    # Generate report asynchronously (fire and forget)
    try:
        # Send immediate acknowledgment
        response = {
            "response_type": "in_channel",
            "text": "📊 리포트를 생성 중입니다... 잠시만 기다려주세요."
        }

        # Trigger report generation in background
        # Note: In production, this should use Celery task
        import asyncio
        asyncio.create_task(_generate_report_async(report_service, tenant.id))

        return response

    except Exception as e:
        logger.error(f"Error triggering report: {str(e)}", exc_info=True)
        return {
            "response_type": "ephemeral",
            "text": f"리포트 생성 중 오류가 발생했습니다: {str(e)}"
        }


async def _generate_report_async(report_service: "ReportService", tenant_id: int):
    """Generate report asynchronously."""
    try:
        result = report_service.generate_weekly_report(tenant_id)
        logger.info(f"Report generated: {result}")
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)


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
    slack_service = SlackService(bot_token=settings.slack_bot_token)
    keyword_service = KeywordService(db, google_ads_service, slack_service)

    if action_id == "approve_keyword":
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
