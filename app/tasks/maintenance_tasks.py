"""Celery tasks for maintenance operations."""

from celery import shared_task
from datetime import datetime, timedelta
import logging

from ..core.database import SessionLocal
from ..models.oauth import OAuthToken, OAuthProvider
from ..core.security import TokenEncryption
from ..config import settings
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.maintenance_tasks.refresh_expired_tokens")
def refresh_expired_tokens():
    """Refresh OAuth tokens that are about to expire."""
    db = SessionLocal()
    try:
        # Find tokens expiring within 24 hours
        cutoff_time = datetime.utcnow() + timedelta(days=1)
        expiring_tokens = db.query(OAuthToken).filter(
            OAuthToken.provider == OAuthProvider.GOOGLE,
            OAuthToken.expires_at < cutoff_time,
            OAuthToken.expires_at.isnot(None)
        ).all()

        encryptor = TokenEncryption(settings.TOKEN_ENCRYPTION_KEY)
        refreshed_count = 0
        failed_count = 0

        for token in expiring_tokens:
            try:
                # Decrypt refresh token
                refresh_token = encryptor.decrypt(token.refresh_token)

                # Create credentials and refresh
                credentials = Credentials(
                    token=None,
                    refresh_token=refresh_token,
                    token_uri='https://oauth2.googleapis.com/token',
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET
                )

                # Refresh the token
                request = Request()
                credentials.refresh(request)

                # Encrypt and save new access token
                new_access_token = encryptor.encrypt(credentials.token)
                token.access_token = new_access_token
                token.expires_at = credentials.expiry
                token.updated_at = datetime.utcnow()

                refreshed_count += 1
                logger.info(f"Successfully refreshed token for tenant {token.tenant_id}")

            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to refresh token for tenant {token.tenant_id}: {e}")

        # Commit all changes
        db.commit()
        logger.info(f"Token refresh complete: {refreshed_count} refreshed, {failed_count} failed, {len(expiring_tokens)} total")

    except Exception as e:
        logger.error(f"Error in refresh_expired_tokens: {e}")
        db.rollback()
    finally:
        db.close()
