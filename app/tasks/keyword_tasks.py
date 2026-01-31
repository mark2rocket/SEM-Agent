"""Celery tasks for keyword monitoring."""

from celery import shared_task
from datetime import datetime
import logging

from sqlalchemy.orm import Session
from ..core.database import SessionLocal
from ..models.tenant import Tenant
from ..models.keyword import ApprovalRequest, KeywordCandidate, KeywordStatus, ApprovalAction
from ..services.google_ads_service import GoogleAdsService
from ..services.slack_service import SlackService
from ..services.keyword_service import KeywordService
from ..config import settings

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.keyword_tasks.detect_inefficient_keywords")
def detect_inefficient_keywords():
    """Detect inefficient keywords for all active tenants."""
    db = SessionLocal()
    try:
        logger.info("Starting inefficient keyword detection for all tenants...")

        # Query all active tenants
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        logger.info(f"Found {len(tenants)} active tenants")

        total_detected = 0
        total_alerts_sent = 0

        for tenant in tenants:
            try:
                logger.info(f"Processing tenant: {tenant.workspace_name} (ID: {tenant.id})")

                # Get OAuth tokens
                oauth_token = tenant.oauth_tokens[0] if tenant.oauth_tokens else None
                if not oauth_token:
                    logger.warning(f"No OAuth token found for tenant {tenant.workspace_name}")
                    continue

                # Get customer ID from GoogleAdsAccount relationship
                google_account = tenant.google_ads_accounts[0] if tenant.google_ads_accounts else None
                if not google_account:
                    logger.warning(f"No Google Ads account found for tenant {tenant.workspace_name}")
                    continue

                # Initialize services
                google_ads = GoogleAdsService(
                    developer_token=settings.google_developer_token,
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    refresh_token=oauth_token.refresh_token
                )

                slack = SlackService(bot_token=oauth_token.bot_token)

                keyword_service = KeywordService(
                    db=db,
                    google_ads_service=google_ads,
                    slack_service=slack
                )

                # Detect inefficient keywords
                detected_keywords = keyword_service.detect_inefficient_keywords(
                    tenant_id=tenant.id
                )

                logger.info(f"Detected {len(detected_keywords)} inefficient keywords for tenant {tenant.workspace_name}")
                total_detected += len(detected_keywords)

                # Create approval requests and send alerts
                for keyword_data in detected_keywords:
                    try:
                        # Create approval request
                        approval_request_id = keyword_service.create_approval_request(
                            tenant_id=tenant.id,
                            keyword_data=keyword_data
                        )

                        total_alerts_sent += 1
                        logger.info(f"Created approval request and sent alert for keyword: {keyword_data['search_term']}")

                    except Exception as e:
                        logger.error(f"Error processing keyword {keyword_data.get('search_term', 'unknown')}: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error processing tenant {tenant.workspace_name}: {e}")
                continue

        logger.info(f"Keyword detection completed. Detected: {total_detected}, Alerts sent: {total_alerts_sent}")

    except Exception as e:
        logger.error(f"Error in detect_inefficient_keywords: {e}")
    finally:
        db.close()


@shared_task(name="app.tasks.keyword_tasks.check_approval_expirations")
def check_approval_expirations():
    """Expire old approval requests that have not been responded to."""
    db = SessionLocal()
    try:
        logger.info("Checking for expired approval requests...")

        # Query approval requests where expires_at < now and action is None
        now = datetime.utcnow()
        expired_requests = db.query(ApprovalRequest).filter(
            ApprovalRequest.expires_at < now,
            ApprovalRequest.action == None
        ).all()

        expired_count = 0
        for request in expired_requests:
            try:
                # Update approval request
                request.action = ApprovalAction.EXPIRED
                request.responded_at = now

                # Update associated keyword candidate status
                if request.keyword_candidate:
                    request.keyword_candidate.status = KeywordStatus.EXPIRED

                expired_count += 1
                logger.info(f"Expired approval request ID: {request.id}")

            except Exception as e:
                logger.error(f"Error expiring approval request {request.id}: {e}")
                continue

        db.commit()
        logger.info(f"Expired {expired_count} approval requests")

    except Exception as e:
        logger.error(f"Error in check_approval_expirations: {e}")
        db.rollback()
    finally:
        db.close()
