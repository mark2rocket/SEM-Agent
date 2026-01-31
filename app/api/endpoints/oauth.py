"""OAuth endpoints for Google and Slack."""

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
import logging
import secrets
from datetime import datetime
from typing import Optional
import httpx

from ...api.deps import get_db
from ...config import settings
from ...core.redis_client import redis_client
from ...core.security import encrypt_token
from ...models.oauth import OAuthToken, OAuthProvider

logger = logging.getLogger(__name__)
router = APIRouter()

# Google OAuth scopes for Google Ads
GOOGLE_ADS_SCOPES = ["https://www.googleapis.com/auth/adwords"]

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

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Google Ads authorization successful",
                "tenant_id": tenant_id,
                "has_refresh_token": encrypted_refresh_token is not None,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling OAuth callback: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete OAuth flow: {str(e)}"
        )


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
