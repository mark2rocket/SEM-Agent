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

    def generate_weekly_report(self, tenant_id: int, notify_channel: str = None, response_url: str = None) -> Dict:
        """Generate weekly performance report."""
        logger.info(f"Generating weekly report for tenant {tenant_id}")

        try:
            # Import models
            from ..models.google_ads import GoogleAdsAccount
            from ..models.report import ReportHistory, ReportSchedule
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

            # Get report schedule to check for campaign filters
            schedule = self.db.query(ReportSchedule).filter_by(tenant_id=tenant_id).first()
            selected_campaign_ids = None
            if schedule and schedule.campaign_ids:
                selected_campaign_ids = schedule.campaign_ids.split(',')
                logger.info(f"Filtering report by {len(selected_campaign_ids)} selected campaigns")

            # Get last week's date range
            period_start, period_end = self.get_weekly_period()
            logger.info(f"Report period: {period_start} to {period_end}")

            # Fetch performance metrics from Google Ads
            metrics_data = self.google_ads.get_performance_metrics(
                customer_id=account.customer_id,
                date_from=period_start,
                date_to=period_end,
                campaign_ids=selected_campaign_ids
            )

            if not metrics_data or metrics_data.get("status") == "error":
                logger.error(f"Failed to fetch metrics: {metrics_data}")
                return {"status": "error", "message": "Failed to fetch Google Ads metrics"}

            # Calculate previous period dates
            period_days = (period_end - period_start).days + 1
            prev_start = period_start - timedelta(days=period_days)
            prev_end = period_start - timedelta(days=1)
            logger.info(f"Previous period: {prev_start} to {prev_end}")

            # Fetch previous period metrics for week-over-week comparison
            prev_metrics_data = self.google_ads.get_performance_metrics(
                customer_id=account.customer_id,
                date_from=prev_start,
                date_to=prev_end,
                campaign_ids=selected_campaign_ids
            )

            # Calculate week-over-week changes
            if prev_metrics_data and prev_metrics_data.get("status") != "error":
                self._add_change_indicators(metrics_data, prev_metrics_data)
            else:
                logger.warning("Could not fetch previous period metrics for comparison")

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
            # build_weekly_report_message returns {"blocks": [...]}, extract the list
            blocks_list = message_blocks.get("blocks", message_blocks) if isinstance(message_blocks, dict) else message_blocks
            target_channel = notify_channel or tenant.slack_channel_id
            report_text = f"Weekly Performance Report ({period_start} ~ {period_end})"
            slack_ts = None

            # 방법 1: chat_postMessage (봇 토큰 필요)
            if target_channel:
                try:
                    slack_response = self.slack.client.chat_postMessage(
                        channel=target_channel,
                        blocks=blocks_list,
                        text=report_text
                    )
                    slack_ts = slack_response.get("ts")
                    logger.info(f"Report posted via chat_postMessage to {target_channel}")
                except Exception as post_error:
                    logger.warning(f"chat_postMessage failed: {post_error} — trying response_url fallback")

            # 방법 2: response_url (봇 토큰 불필요, 채널에 공개 게시 가능)
            if slack_ts is None and response_url:
                import requests as http_requests
                try:
                    r = http_requests.post(
                        response_url,
                        json={
                            "response_type": "in_channel",
                            "replace_original": False,
                            "blocks": blocks_list,
                            "text": report_text
                        },
                        timeout=10
                    )
                    if r.status_code == 200:
                        slack_ts = "response_url"
                        logger.info("Report posted via response_url fallback")
                    else:
                        logger.error(f"response_url fallback failed: {r.status_code} {r.text}")
                except Exception as e:
                    logger.error(f"response_url fallback exception: {e}")

            if slack_ts is None:
                return {"status": "error", "message": "리포트를 채널에 게시할 수 없습니다. 봇 권한 또는 채널 설정을 확인하세요."}

            # slack_response 호환을 위한 변수 설정 (ts 저장에 사용)
            slack_response = {"ts": slack_ts if slack_ts != "response_url" else None}

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

    def _add_change_indicators(self, current_metrics: Dict, previous_metrics: Dict) -> None:
        """Add week-over-week change indicators to metrics."""
        def calculate_change(current_value: float, previous_value: float) -> tuple[str, str]:
            """Calculate percentage change with emoji indicator."""
            if previous_value == 0:
                return "N/A", ""

            pct_change = ((current_value - previous_value) / previous_value) * 100

            if pct_change > 0:
                emoji = "🔺"
            elif pct_change < 0:
                emoji = "🔻"
            else:
                emoji = "➡️"

            return f"{abs(pct_change):.1f}%", emoji

        # Calculate changes for key metrics
        metrics_to_track = [
            ("cost", "cost"),
            ("conversions", "conversions"),
            ("roas", "roas"),
            ("clicks", "clicks")
        ]

        for metric_key, display_key in metrics_to_track:
            current_val = current_metrics.get(metric_key, 0)
            previous_val = previous_metrics.get(metric_key, 0)

            change_pct, emoji = calculate_change(current_val, previous_val)

            # Add change indicator to metrics dict
            current_metrics[f"{display_key}_change"] = f"{emoji} {change_pct}" if emoji else change_pct
