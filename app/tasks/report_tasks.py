"""Celery tasks for report generation."""

from celery import shared_task
from datetime import datetime, time
import logging
import pytz
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.report import ReportSchedule, ReportFrequency
from ..models.tenant import Tenant
from ..services.google_ads_service import GoogleAdsService
from ..services.gemini_service import GeminiService
from ..services.slack_service import SlackService
from ..services.report_service import ReportService
from ..config import settings

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.report_tasks.generate_scheduled_reports")
def generate_scheduled_reports():
    """Check for due reports and generate them."""
    db = SessionLocal()
    try:
        logger.info("Checking for scheduled reports...")

        # Get current UTC time
        now_utc = datetime.now(pytz.UTC)

        # Query all active schedules
        schedules = db.query(ReportSchedule).filter(
            ReportSchedule.is_active == True
        ).all()

        logger.info(f"Found {len(schedules)} active schedules")

        for schedule in schedules:
            try:
                # Convert current time to schedule's timezone
                tz = pytz.timezone(schedule.timezone)
                now_local = now_utc.astimezone(tz)

                # Check if this schedule is due now
                is_due = False

                if schedule.frequency == ReportFrequency.DAILY:
                    # Daily: check if time_of_day matches current hour
                    if schedule.time_of_day and now_local.hour == schedule.time_of_day.hour:
                        is_due = True

                elif schedule.frequency == ReportFrequency.WEEKLY:
                    # Weekly: check day_of_week (0=Monday, 6=Sunday) and time
                    if (schedule.day_of_week is not None and
                        now_local.weekday() == schedule.day_of_week and
                        schedule.time_of_day and
                        now_local.hour == schedule.time_of_day.hour):
                        is_due = True

                elif schedule.frequency == ReportFrequency.MONTHLY:
                    # Monthly: check day_of_month and time
                    if (schedule.day_of_month is not None and
                        now_local.day == schedule.day_of_month and
                        schedule.time_of_day and
                        now_local.hour == schedule.time_of_day.hour):
                        is_due = True

                if not is_due:
                    continue

                logger.info(f"Schedule {schedule.id} is due - generating report for tenant {schedule.tenant_id}")

                # Get tenant with Slack channel
                tenant = db.query(Tenant).filter(Tenant.id == schedule.tenant_id).first()
                if not tenant:
                    logger.error(f"Tenant {schedule.tenant_id} not found for schedule {schedule.id}")
                    continue

                if not tenant.slack_channel_id:
                    logger.warning(f"Tenant {tenant.id} has no Slack channel configured")
                    continue

                # Get OAuth token for Google Ads
                oauth_token = tenant.oauth_tokens[0] if tenant.oauth_tokens else None
                if not oauth_token or not oauth_token.refresh_token:
                    logger.error(f"No valid OAuth token found for tenant {tenant.id}")
                    continue

                # Initialize services
                google_ads = GoogleAdsService(
                    developer_token=settings.google_developer_token,
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    refresh_token=oauth_token.refresh_token
                )

                gemini_service = GeminiService(api_key=settings.gemini_api_key)
                slack_service = SlackService(bot_token=oauth_token.bot_token)

                report_service = ReportService(
                    db=db,
                    google_ads_service=google_ads,
                    gemini_service=gemini_service,
                    slack_service=slack_service
                )

                # Generate report
                report = report_service.generate_weekly_report(tenant_id=tenant.id)
                logger.info(f"Successfully generated report {report.id} for tenant {tenant.id}")

            except Exception as e:
                logger.error(f"Error processing schedule {schedule.id}: {e}", exc_info=True)
                # Continue with next schedule
                continue

    except Exception as e:
        logger.error(f"Error in generate_scheduled_reports: {e}", exc_info=True)
    finally:
        db.close()


@shared_task(name="app.tasks.report_tasks.generate_report_for_tenant")
def generate_report_for_tenant(tenant_id: int, report_type: str = "weekly"):
    """Generate report for specific tenant."""
    db = SessionLocal()
    try:
        logger.info(f"Generating {report_type} report for tenant {tenant_id}")

        # Get tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logger.error(f"Tenant {tenant_id} not found")
            return

        if not tenant.slack_channel_id:
            logger.warning(f"Tenant {tenant_id} has no Slack channel configured")
            return

        # Get OAuth token for Google Ads
        oauth_token = tenant.oauth_tokens[0] if tenant.oauth_tokens else None
        if not oauth_token or not oauth_token.refresh_token:
            logger.error(f"No valid OAuth token found for tenant {tenant_id}")
            return

        # Initialize services
        google_ads = GoogleAdsService(
            developer_token=settings.google_developer_token,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            refresh_token=oauth_token.refresh_token
        )

        gemini_service = GeminiService(api_key=settings.gemini_api_key)
        slack_service = SlackService(bot_token=oauth_token.bot_token)

        report_service = ReportService(
            db=db,
            google_ads_service=google_ads,
            gemini_service=gemini_service,
            slack_service=slack_service
        )

        # Generate report based on type
        if report_type == "weekly":
            report = report_service.generate_weekly_report(tenant_id=tenant_id)
            logger.info(f"Successfully generated weekly report {report.id} for tenant {tenant_id}")
        else:
            logger.warning(f"Unknown report type: {report_type}")

    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
    finally:
        db.close()
