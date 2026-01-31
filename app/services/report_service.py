"""Report generation service."""

from datetime import date, datetime, timedelta
from typing import Dict, Tuple
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class ReportService:
    """Service for generating performance reports."""

    def __init__(self, db: Session, google_ads_service, gemini_service, slack_service):
        self.db = db
        self.google_ads = google_ads_service
        self.gemini = gemini_service
        self.slack = slack_service

    def generate_weekly_report(self, tenant_id: int) -> Dict:
        """Generate weekly performance report."""
        logger.info(f"Generating weekly report for tenant {tenant_id}")

        try:
            # Import models
            from ..models.google_ads import GoogleAdsAccount
            from ..models.report import ReportHistory
            from ..models.tenant import Tenant

            # Get tenant and verify it exists
            tenant = self.db.query(Tenant).filter_by(id=tenant_id).first()
            if not tenant:
                logger.error(f"Tenant {tenant_id} not found")
                return {"status": "error", "message": "Tenant not found"}

            # Get active Google Ads account
            account = self.db.query(GoogleAdsAccount).filter_by(
                tenant_id=tenant_id, is_active=True
            ).first()
            if not account:
                logger.error(f"No active Google Ads account for tenant {tenant_id}")
                return {"status": "error", "message": "No active Google Ads account"}

            # Get last week's date range
            period_start, period_end = self.get_weekly_period()
            logger.info(f"Report period: {period_start} to {period_end}")

            # Fetch performance metrics from Google Ads
            metrics_data = self.google_ads.get_performance_metrics(
                customer_id=account.customer_id,
                date_from=period_start,
                date_to=period_end
            )

            if not metrics_data or metrics_data.get("status") == "error":
                logger.error(f"Failed to fetch metrics: {metrics_data}")
                return {"status": "error", "message": "Failed to fetch Google Ads metrics"}

            # Generate AI insight using Gemini
            insight_text = self.gemini.generate_report_insight(
                metrics=metrics_data
            )

            # Build Slack message with Block Kit
            period = f"{period_start.strftime('%Y-%m-%d')} ~ {period_end.strftime('%Y-%m-%d')}"
            message_blocks = self.slack.build_weekly_report_message(
                metrics=metrics_data,
                insight=insight_text,
                period=period
            )

            # Send message to Slack
            slack_response = self.slack.client.chat_postMessage(
                channel=tenant.slack_channel_id,
                blocks=message_blocks,
                text=f"Weekly Performance Report ({period_start} ~ {period_end})"
            )

            # Save report to database
            report_history = ReportHistory(
                tenant_id=tenant_id,
                report_type="weekly",
                period_start=datetime.combine(period_start, datetime.min.time()),
                period_end=datetime.combine(period_end, datetime.max.time()),
                slack_message_ts=slack_response.get("ts"),
                gemini_insight=insight_text,
                metrics=metrics_data
            )
            self.db.add(report_history)
            self.db.commit()
            self.db.refresh(report_history)

            logger.info(f"Weekly report generated successfully: report_id={report_history.id}")

            return {
                "status": "success",
                "report_id": report_history.id,
                "period": f"{period_start} ~ {period_end}",
                "metrics": metrics_data
            }

        except Exception as e:
            logger.error(f"Error generating weekly report: {str(e)}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "message": str(e)}

    def get_weekly_period(self) -> Tuple[date, date]:
        """Get last week's date range (Monday to Sunday)."""
        today = date.today()
        days_since_monday = today.weekday()
        last_sunday = today - timedelta(days=days_since_monday + 1)
        last_monday = last_sunday - timedelta(days=6)
        return last_monday, last_sunday
