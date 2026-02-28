"""OAuth endpoints for Google and Slack."""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
import logging
import secrets
from datetime import datetime
from typing import Optional
import httpx

from ...api.deps import get_db
from ...config import settings
from ...core.redis_client import redis_client
from ...core.security import encrypt_token, decrypt_token
from ...models.oauth import OAuthToken, OAuthProvider
from ...models.tenant import Tenant, User
from ...models.google_ads import GoogleAdsAccount, SearchConsoleAccount
from ...services.slack_service import SlackService
from ...services.google_ads_service import GoogleAdsService

logger = logging.getLogger(__name__)
router = APIRouter()

# Google OAuth scopes for Google Ads
GOOGLE_ADS_SCOPES = ["https://www.googleapis.com/auth/adwords"]

# Google Search Console scopes
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# Slack OAuth scopes
SLACK_SCOPES = ["chat:write", "commands", "im:history"]


def _create_flow() -> Flow:
    """Create Google OAuth flow with client configuration."""
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=GOOGLE_ADS_SCOPES
    )
    flow.redirect_uri = settings.google_redirect_uri
    return flow


@router.get("/google/authorize")
async def google_oauth_authorize(tenant_id: int, db: Session = Depends(get_db)):
    """
    Initiate Google OAuth flow.

    Args:
        tenant_id: ID of the tenant to authorize
        db: Database session

    Returns:
        Redirect to Google OAuth consent page
    """
    logger.info(f"Starting Google OAuth for tenant {tenant_id}")

    try:
        # Generate CSRF state token
        state_token = secrets.token_urlsafe(32)
        state = f"{tenant_id}:{state_token}"

        # Store state in Redis with 10-minute expiration
        await redis_client.setex(
            f"google_oauth_state:{state}",
            600,  # 10 minutes
            str(tenant_id)
        )

        # Create OAuth flow
        flow = _create_flow()

        # Generate authorization URL
        authorization_url, _ = flow.authorization_url(
            access_type="offline",  # Request refresh token
            include_granted_scopes="true",
            state=state,
            prompt="consent"  # Force consent to get refresh token
        )

        logger.info(f"Redirecting tenant {tenant_id} to Google OAuth")
        return RedirectResponse(url=authorization_url)

    except Exception as e:
        logger.error(f"Error initiating Google OAuth: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate Google OAuth flow"
        )


@router.get("/google/callback")
async def google_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle Google OAuth callback.

    Args:
        code: Authorization code from Google
        state: State parameter for CSRF protection
        error: Error from Google OAuth (if user denied)
        db: Database session

    Returns:
        Success message or error response
    """
    logger.info("Handling Google OAuth callback")

    # Handle user denial
    if error:
        logger.warning(f"User denied Google OAuth: {error}")
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Authorization denied by user",
                "error": error
            }
        )

    # Validate required parameters
    if not code or not state:
        logger.error("Missing code or state in OAuth callback")
        raise HTTPException(
            status_code=400,
            detail="Missing authorization code or state parameter"
        )

    try:
        # Verify state and retrieve tenant_id
        stored_tenant_id = await redis_client.get(f"google_oauth_state:{state}")

        if not stored_tenant_id:
            logger.error(f"Invalid or expired state: {state}")
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired state token"
            )

        tenant_id = int(stored_tenant_id)

        # Delete used state token
        await redis_client.delete(f"google_oauth_state:{state}")

        # Create OAuth flow
        flow = _create_flow()

        # Exchange authorization code for tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Validate that we received the necessary tokens
        if not credentials.token:
            raise HTTPException(
                status_code=500,
                detail="Failed to obtain access token from Google"
            )

        # Encrypt tokens before storing
        encrypted_access_token = encrypt_token(credentials.token)
        encrypted_refresh_token = None

        if credentials.refresh_token:
            encrypted_refresh_token = encrypt_token(credentials.refresh_token)
        else:
            logger.warning(f"No refresh token received for tenant {tenant_id}")

        # Check if token already exists for this tenant
        existing_token = db.query(OAuthToken).filter(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.provider == OAuthProvider.GOOGLE
        ).first()

        if existing_token:
            # Update existing token
            existing_token.access_token = encrypted_access_token
            if encrypted_refresh_token:
                existing_token.refresh_token = encrypted_refresh_token
            existing_token.expires_at = credentials.expiry
            existing_token.scope = " ".join(GOOGLE_ADS_SCOPES)
            existing_token.updated_at = datetime.utcnow()
            logger.info(f"Updated existing OAuth token for tenant {tenant_id}")
        else:
            # Create new token record
            oauth_token = OAuthToken(
                tenant_id=tenant_id,
                provider=OAuthProvider.GOOGLE,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expires_at=credentials.expiry,
                scope=" ".join(GOOGLE_ADS_SCOPES)
            )
            db.add(oauth_token)
            logger.info(f"Created new OAuth token for tenant {tenant_id}")

        # Commit to database
        db.commit()

        logger.info(f"Successfully stored OAuth tokens for tenant {tenant_id}")

        # Track account creation status for user feedback
        accounts_created = 0
        account_creation_error = None

        # Create GoogleAdsAccount records for accessible accounts
        try:
            # Get the refresh token to use (either new or existing)
            refresh_token_to_use = credentials.refresh_token if credentials.refresh_token else None
            if not refresh_token_to_use and existing_token and existing_token.refresh_token:
                # Use existing refresh token if no new one was provided
                refresh_token_to_use = decrypt_token(existing_token.refresh_token)

            if refresh_token_to_use:
                # Initialize Google Ads service with the credentials
                google_ads_service = GoogleAdsService(
                    developer_token=settings.google_developer_token,
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    refresh_token=refresh_token_to_use,
                    login_customer_id=settings.google_login_customer_id
                )

                # List accessible accounts
                accessible_accounts = google_ads_service.list_accessible_accounts()

                if accessible_accounts:
                    logger.info(f"Found {len(accessible_accounts)} accessible Google Ads accounts for tenant {tenant_id}")

                    # Set first account as active, others as inactive
                    for idx, account_info in enumerate(accessible_accounts):
                        customer_id = account_info["customer_id"]

                        # Check if account already exists
                        existing_account = db.query(GoogleAdsAccount).filter(
                            GoogleAdsAccount.tenant_id == tenant_id,
                            GoogleAdsAccount.customer_id == customer_id
                        ).first()

                        if existing_account:
                            # Update existing account
                            existing_account.account_name = account_info["account_name"]
                            existing_account.currency = account_info.get("currency")
                            existing_account.timezone = account_info.get("timezone")
                            # Keep existing is_active status
                            logger.info(f"Updated existing GoogleAdsAccount: {customer_id} for tenant {tenant_id}")
                        else:
                            # Create new account (first one is active, others inactive)
                            new_account = GoogleAdsAccount(
                                tenant_id=tenant_id,
                                customer_id=customer_id,
                                account_name=account_info["account_name"],
                                currency=account_info.get("currency"),
                                timezone=account_info.get("timezone"),
                                is_active=(idx == 0)  # First account is active
                            )
                            db.add(new_account)
                            logger.info(f"Created new GoogleAdsAccount: {customer_id} (active={idx == 0}) for tenant {tenant_id}")

                    # Commit account records
                    db.commit()
                    accounts_created = len(accessible_accounts)
                    logger.info(f"Successfully created/updated {accounts_created} GoogleAdsAccount records for tenant {tenant_id}")
                else:
                    logger.warning(f"No accessible Google Ads accounts found for tenant {tenant_id}")
            else:
                logger.warning(f"No refresh token available to fetch Google Ads accounts for tenant {tenant_id}")

        except Exception as e:
            # Don't fail the OAuth flow if account listing fails
            account_creation_error = str(e)
            logger.error(f"Failed to create GoogleAdsAccount records for tenant {tenant_id}: {e}", exc_info=True)
            # Rollback any partial account changes
            db.rollback()

        # Send welcome message to Slack if Slack token exists
        try:
            # Get tenant with Slack OAuth token
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                # Get Slack bot token
                slack_token = db.query(OAuthToken).filter(
                    OAuthToken.tenant_id == tenant_id,
                    OAuthToken.provider == OAuthProvider.SLACK
                ).first()

                if slack_token:
                    # Decrypt the Slack bot token
                    decrypted_bot_token = decrypt_token(slack_token.access_token)
                    slack_service = SlackService(bot_token=decrypted_bot_token)

                    # Get user's Slack user ID (use first user or workspace channel as fallback)
                    user = db.query(User).filter(User.tenant_id == tenant_id).first()

                    welcome_message = (
                        "세팅 완료! 📅 **매주 월요일 오전 9시**에 주간 리포트가 발송됩니다.\n\n"
                        "아래 버튼으로 리포트 주기를 변경할 수 있습니다."
                    )

                    # Determine target channel (user DM or workspace channel)
                    target_channel = None
                    if user and user.slack_user_id:
                        target_channel = user.slack_user_id  # Send DM to user
                    elif tenant.slack_channel_id:
                        target_channel = tenant.slack_channel_id  # Fallback to workspace channel

                    if target_channel:
                        message_blocks = {
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {"type": "mrkdwn", "text": welcome_message}
                                },
                                {
                                    "type": "actions",
                                    "elements": [
                                        {
                                            "type": "button",
                                            "text": {"type": "plain_text", "text": "리포트 주기 변경하기"},
                                            "action_id": "configure_schedule",
                                            "value": "open_config"
                                        }
                                    ]
                                }
                            ]
                        }

                        slack_service.send_message(message=message_blocks, channel=target_channel)
                        logger.info(f"Sent welcome message to Slack for tenant {tenant_id}")
                    else:
                        logger.warning(f"No Slack channel found for tenant {tenant_id}, skipping welcome message")
                else:
                    logger.info(f"No Slack token found for tenant {tenant_id}, skipping welcome message")
        except Exception as e:
            # Don't fail the OAuth flow if Slack message fails
            logger.error(f"Failed to send Slack welcome message: {e}", exc_info=True)

        # Return a nice HTML success page
        html_content = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Google Ads 연동 완료</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                .container {{
                    background: white;
                    border-radius: 16px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    padding: 48px;
                    max-width: 500px;
                    width: 100%;
                    text-align: center;
                }}
                .icon {{
                    font-size: 64px;
                    margin-bottom: 24px;
                }}
                h1 {{
                    color: #1a202c;
                    font-size: 28px;
                    font-weight: 700;
                    margin-bottom: 16px;
                }}
                p {{
                    color: #4a5568;
                    font-size: 16px;
                    line-height: 1.6;
                    margin-bottom: 32px;
                }}
                .success-badge {{
                    display: inline-block;
                    background: #48bb78;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 14px;
                    font-weight: 600;
                    margin-bottom: 24px;
                }}
                .info-box {{
                    background: #f7fafc;
                    border-radius: 8px;
                    padding: 20px;
                    margin-bottom: 32px;
                    text-align: left;
                }}
                .info-item {{
                    display: flex;
                    justify-content: space-between;
                    padding: 8px 0;
                    border-bottom: 1px solid #e2e8f0;
                }}
                .info-item:last-child {{
                    border-bottom: none;
                }}
                .info-label {{
                    color: #718096;
                    font-size: 14px;
                }}
                .info-value {{
                    color: #2d3748;
                    font-weight: 600;
                    font-size: 14px;
                }}
                .next-steps {{
                    background: #edf2f7;
                    border-left: 4px solid #667eea;
                    padding: 16px;
                    margin-bottom: 32px;
                    text-align: left;
                }}
                .next-steps h3 {{
                    color: #2d3748;
                    font-size: 16px;
                    font-weight: 600;
                    margin-bottom: 12px;
                }}
                .next-steps ol {{
                    margin-left: 20px;
                    color: #4a5568;
                    font-size: 14px;
                    line-height: 1.8;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 14px 32px;
                    border-radius: 8px;
                    text-decoration: none;
                    font-weight: 600;
                    font-size: 16px;
                    transition: transform 0.2s, box-shadow 0.2s;
                }}
                .button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">✅</div>
                <div class="success-badge">연동 완료</div>
                <h1>Google Ads 연동 성공!</h1>
                <p>SEM-Agent가 이제 Google Ads 데이터에 접근할 수 있습니다.</p>

                <div class="info-box">
                    <div class="info-item">
                        <span class="info-label">상태</span>
                        <span class="info-value">✓ 활성화</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Refresh Token</span>
                        <span class="info-value">{'✓ 있음' if encrypted_refresh_token else '✗ 없음'}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Google Ads 계정</span>
                        <span class="info-value">{"✓ " + str(accounts_created) + "개 연동됨" if accounts_created > 0 else "✗ 연동 실패" if account_creation_error else "⚠️ 없음"}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">만료 시간</span>
                        <span class="info-value">{credentials.expiry.strftime('%Y-%m-%d %H:%M') if credentials.expiry else 'N/A'}</span>
                    </div>
                    {f'''<div style="background: #fee2e2; padding: 12px; border-radius: 6px; margin-top: 12px; border-left: 4px solid #dc2626;">
                        <div style="color: #dc2626; font-size: 13px; font-weight: 600;">❌ 계정 연동 오류:</div>
                        <div style="color: #991b1b; font-size: 12px; margin-top: 4px; font-family: monospace;">{account_creation_error}</div>
                    </div>''' if account_creation_error else ''}
                </div>

                <div class="next-steps">
                    <h3>📋 다음 단계</h3>
                    <ol>
                        <li>Slack으로 돌아가세요</li>
                        <li><code>/sem-report</code> 명령어로 첫 리포트 생성</li>
                        <li><code>/sem-config</code>로 자동 리포트 주기 설정</li>
                    </ol>
                </div>

                <a href="slack://open" class="button">Slack으로 돌아가기</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling OAuth callback: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete OAuth flow: {str(e)}"
        )


def _create_gsc_flow() -> Flow:
    """Create Google OAuth flow for Search Console."""
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_gsc_redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config=client_config, scopes=GSC_SCOPES)
    flow.redirect_uri = settings.google_gsc_redirect_uri
    return flow



@router.get("/gsc/authorize")
async def gsc_oauth_authorize(tenant_id: int, db: Session = Depends(get_db)):
    """Initiate Google Search Console OAuth flow."""
    logger.info(f"Starting GSC OAuth for tenant {tenant_id}")
    try:
        state_token = secrets.token_urlsafe(32)
        state = f"{tenant_id}:{state_token}"
        await redis_client.setex(f"gsc_oauth_state:{state}", 600, str(tenant_id))

        flow = _create_gsc_flow()
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            state=state,
            prompt="consent"
        )
        logger.info(f"Redirecting tenant {tenant_id} to GSC OAuth")
        return RedirectResponse(url=authorization_url)
    except Exception as e:
        logger.error(f"Error initiating GSC OAuth: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate GSC OAuth flow")


@router.get("/gsc/callback")
async def gsc_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Handle Google Search Console OAuth callback."""
    logger.info("Handling GSC OAuth callback")

    if error:
        logger.warning(f"User denied GSC OAuth: {error}")
        return JSONResponse(status_code=400, content={"status": "error", "message": "Authorization denied"})

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")

    try:
        stored_tenant_id = await redis_client.get(f"gsc_oauth_state:{state}")
        if not stored_tenant_id:
            raise HTTPException(status_code=400, detail="Invalid or expired state token")

        tenant_id = int(stored_tenant_id)
        await redis_client.delete(f"gsc_oauth_state:{state}")

        flow = _create_gsc_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        if not credentials.refresh_token:
            raise HTTPException(
                status_code=500,
                detail="리프레시 토큰을 받지 못했습니다. 다시 시도해주세요."
            )

        # Fetch available sites
        from googleapiclient.discovery import build as gapi_build
        from google.oauth2.credentials import Credentials as GCredentials
        from google.auth.transport.requests import Request as GRequest

        creds = GCredentials(
            token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=GSC_SCOPES
        )
        gsc_service = gapi_build("searchconsole", "v1", credentials=creds)
        sites_result = gsc_service.sites().list().execute()
        sites = sites_result.get("siteEntry", [])

        if not sites:
            raise HTTPException(
                status_code=400,
                detail="연동된 Search Console 사이트가 없습니다. Google Search Console에서 사이트를 먼저 등록하세요."
            )

        # Use first verified site
        site_url = sites[0]["siteUrl"]
        all_sites = [s["siteUrl"] for s in sites]

        # Store in SearchConsoleAccount
        encrypted_rt = encrypt_token(credentials.refresh_token)
        existing = db.query(SearchConsoleAccount).filter_by(
            tenant_id=tenant_id, site_url=site_url
        ).first()
        if existing:
            existing.refresh_token = encrypted_rt
            existing.is_active = True
            logger.info(f"Updated SearchConsoleAccount for tenant {tenant_id}: {site_url}")
        else:
            sc_account = SearchConsoleAccount(
                tenant_id=tenant_id,
                site_url=site_url,
                refresh_token=encrypted_rt,
                is_active=True
            )
            db.add(sc_account)
            logger.info(f"Created SearchConsoleAccount for tenant {tenant_id}: {site_url}")
        db.commit()

        sites_list_html = "".join(f"<li>{s}</li>" for s in all_sites)
        html_content = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Search Console 연동 완료</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                    background: linear-gradient(135deg, #34a853 0%, #0f9d58 100%);
                    min-height: 100vh; display: flex; align-items: center;
                    justify-content: center; padding: 20px;
                }}
                .container {{
                    background: white; border-radius: 16px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    padding: 48px; max-width: 500px; width: 100%; text-align: center;
                }}
                .icon {{ font-size: 64px; margin-bottom: 24px; }}
                h1 {{ color: #1a202c; font-size: 28px; font-weight: 700; margin-bottom: 16px; }}
                p {{ color: #4a5568; font-size: 16px; line-height: 1.6; margin-bottom: 24px; }}
                .site-box {{
                    background: #f0fdf4; border: 1px solid #86efac;
                    border-radius: 8px; padding: 16px; margin-bottom: 24px; text-align: left;
                }}
                .site-box h3 {{ color: #166534; font-size: 14px; font-weight: 600; margin-bottom: 8px; }}
                .site-box ul {{ margin-left: 16px; color: #15803d; font-size: 14px; line-height: 1.8; }}
                .active-site {{
                    background: #dcfce7; border-radius: 6px; padding: 10px 14px;
                    margin-bottom: 16px; font-size: 14px; font-weight: 600; color: #166534;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #34a853 0%, #0f9d58 100%);
                    color: white; padding: 14px 32px; border-radius: 8px;
                    text-decoration: none; font-weight: 600; font-size: 16px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">✅</div>
                <h1>Search Console 연동 성공!</h1>
                <p>SEM-Agent가 Google Search Console 데이터에 접근할 수 있습니다.</p>
                <div class="active-site">📊 연동된 사이트: {site_url}</div>
                <div class="site-box">
                    <h3>📋 전체 Search Console 사이트 ({len(all_sites)}개)</h3>
                    <ul>{sites_list_html}</ul>
                </div>
                <p style="font-size:14px; color:#6b7280;">
                    이제 <code>/sem-report</code> 명령어로 Google Ads와 함께<br>
                    Search Console 리포트도 받아보세요!
                </p>
                <br>
                <a href="slack://open" class="button">Slack으로 돌아가기</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling GSC OAuth callback: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to complete GSC OAuth flow: {str(e)}")


@router.get("/slack/install")
async def slack_oauth_install(tenant_id: int):
    """
    Initiate Slack app installation.

    Args:
        tenant_id: ID of the tenant to install Slack for

    Returns:
        Redirect to Slack OAuth page
    """
    logger.info(f"Starting Slack OAuth for tenant {tenant_id}")

    try:
        # Generate CSRF state token
        state_token = secrets.token_urlsafe(32)
        state = f"{tenant_id}:{state_token}"

        # Store state in Redis with 10-minute expiration
        await redis_client.setex(
            f"slack_oauth_state:{state}",
            600,  # 10 minutes
            str(tenant_id)
        )

        # Build Slack OAuth URL
        scopes = ",".join(SLACK_SCOPES)
        slack_oauth_url = (
            f"https://slack.com/oauth/v2/authorize"
            f"?client_id={settings.slack_client_id}"
            f"&scope={scopes}"
            f"&state={state}"
            f"&redirect_uri={settings.slack_redirect_uri}"
        )

        logger.info(f"Redirecting tenant {tenant_id} to Slack OAuth")
        return RedirectResponse(url=slack_oauth_url)

    except Exception as e:
        logger.error(f"Error initiating Slack OAuth: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate Slack OAuth flow"
        )


@router.get("/slack/callback")
async def slack_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle Slack OAuth callback.

    Args:
        code: Authorization code from Slack
        state: State parameter for CSRF protection
        error: Error from Slack OAuth (if user denied)
        db: Database session

    Returns:
        Success message or error response
    """
    logger.info("Handling Slack OAuth callback")

    # Handle user denial
    if error:
        logger.warning(f"User denied Slack OAuth: {error}")
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Authorization denied by user",
                "error": error
            }
        )

    # Validate required parameters
    if not code or not state:
        logger.error("Missing code or state in OAuth callback")
        raise HTTPException(
            status_code=400,
            detail="Missing authorization code or state parameter"
        )

    try:
        # Verify state and retrieve tenant_id
        stored_tenant_id = await redis_client.get(f"slack_oauth_state:{state}")

        if not stored_tenant_id:
            logger.error(f"Invalid or expired state: {state}")
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired state token"
            )

        tenant_id = int(stored_tenant_id)

        # Delete used state token
        await redis_client.delete(f"slack_oauth_state:{state}")

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret,
                    "code": code,
                    "redirect_uri": settings.slack_redirect_uri
                }
            )
            response.raise_for_status()
            token_data = response.json()

        # Check if OAuth was successful
        if not token_data.get("ok"):
            error_msg = token_data.get("error", "Unknown error")
            logger.error(f"Slack OAuth error: {error_msg}")
            raise HTTPException(
                status_code=400,
                detail=f"Slack OAuth failed: {error_msg}"
            )

        # Extract bot token
        bot_token = token_data.get("access_token")
        if not bot_token:
            raise HTTPException(
                status_code=500,
                detail="Failed to obtain bot token from Slack"
            )

        # Encrypt token before storing
        encrypted_bot_token = encrypt_token(bot_token)

        # Check if token already exists for this tenant
        existing_token = db.query(OAuthToken).filter(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.provider == OAuthProvider.SLACK
        ).first()

        if existing_token:
            # Update existing token
            existing_token.access_token = encrypted_bot_token
            existing_token.scope = " ".join(SLACK_SCOPES)
            existing_token.updated_at = datetime.utcnow()
            logger.info(f"Updated existing Slack token for tenant {tenant_id}")
        else:
            # Create new token record
            oauth_token = OAuthToken(
                tenant_id=tenant_id,
                provider=OAuthProvider.SLACK,
                access_token=encrypted_bot_token,
                scope=" ".join(SLACK_SCOPES)
            )
            db.add(oauth_token)
            logger.info(f"Created new Slack token for tenant {tenant_id}")

        # Commit to database
        db.commit()

        logger.info(f"Successfully stored Slack token for tenant {tenant_id}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Slack authorization successful",
                "tenant_id": tenant_id,
                "team_id": token_data.get("team", {}).get("id"),
                "team_name": token_data.get("team", {}).get("name")
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Slack OAuth callback: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete Slack OAuth flow: {str(e)}"
        )
