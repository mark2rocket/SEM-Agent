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

    def generate_weekly_report(self, tenant_id: int, notify_channel: str = None, response_url: str = None, override_campaign_ids: list = None) -> Dict:
        """Generate weekly performance report.

        Args:
            override_campaign_ids: 단일 캠페인 ID 리스트. 지정하면 schedule 설정 무시.
        """
        logger.info(f"Generating weekly report for tenant {tenant_id}, override_campaigns={override_campaign_ids}")

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

            # 캠페인 필터 결정: override > schedule > 전체
            if override_campaign_ids is not None:
                selected_campaign_ids = override_campaign_ids if override_campaign_ids else None
                logger.info(f"Using override campaign filter: {selected_campaign_ids}")
            else:
                schedule = self.db.query(ReportSchedule).filter_by(tenant_id=tenant_id).first()
                selected_campaign_ids = None
                if schedule and schedule.campaign_ids:
                    selected_campaign_ids = schedule.campaign_ids.split(',')
                    logger.info(f"Filtering report by {len(selected_campaign_ids)} selected campaigns")

            # 단일 캠페인인 경우 이름 조회
            campaign_name = None
            if selected_campaign_ids and len(selected_campaign_ids) == 1:
                try:
                    campaigns = self.google_ads.list_campaigns(account.customer_id)
                    for c in campaigns:
                        if c['id'] == selected_campaign_ids[0]:
                            campaign_name = c['name']
                            break
                except Exception as e:
                    logger.warning(f"Could not fetch campaign name: {e}")

            # Fetch 4 weeks of metrics for trend analysis (oldest first)
            week_periods = self.get_n_week_periods(4)
            trend_data = []
            for w_start, w_end in week_periods:
                w_metrics = self.google_ads.get_performance_metrics(
                    customer_id=account.customer_id,
                    date_from=w_start,
                    date_to=w_end,
                    campaign_ids=selected_campaign_ids
                )
                if w_metrics and w_metrics.get("status") != "error":
                    trend_data.append({
                        "period": f"{w_start.strftime('%m/%d')}~{w_end.strftime('%m/%d')}",
                        "metrics": w_metrics
                    })

            if not trend_data:
                logger.error("Failed to fetch metrics for any week")
                return {"status": "error", "message": "Failed to fetch Google Ads metrics"}

            # Use most recent week as current, second-most-recent as previous
            metrics_data = trend_data[-1]["metrics"]
            period_start, period_end = week_periods[-1]
            logger.info(f"Report period: {period_start} to {period_end}, trend weeks: {len(trend_data)}")

            # Calculate week-over-week changes (current vs previous week)
            if len(trend_data) >= 2:
                self._add_change_indicators(metrics_data, trend_data[-2]["metrics"])
            else:
                logger.warning("Could not fetch previous period metrics for comparison")

            # Generate AI insight using Gemini (with 4-week trend)
            insight_text = self.gemini.generate_report_insight(
                metrics=metrics_data,
                trend_data=trend_data
            )

            # Build Slack message with Block Kit
            period = f"{period_start.strftime('%Y-%m-%d')} ~ {period_end.strftime('%Y-%m-%d')}"
            message_blocks = self.slack.build_weekly_report_message(
                metrics=metrics_data,
                insight=insight_text,
                period=period,
                trend_data=trend_data,
                campaign_name=campaign_name
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

    def generate_gsc_report(
        self, tenant_id: int, notify_channel: str = None, response_url: str = None
    ) -> dict:
        """Generate Google Search Console weekly report."""
        logger.info(f"Generating GSC report for tenant {tenant_id}")
        try:
            from ..models.google_ads import SearchConsoleAccount
            from ..models.tenant import Tenant
            from ..core.security import decrypt_token
            from ..config import settings
            from ..services.search_console_service import SearchConsoleService

            tenant = self.db.query(Tenant).filter_by(id=tenant_id).first()
            if not tenant:
                return {"status": "error", "message": "Tenant not found"}

            gsc_account = self.db.query(SearchConsoleAccount).filter_by(
                tenant_id=tenant_id, is_active=True
            ).first()
            if not gsc_account or not gsc_account.refresh_token:
                return {"status": "skipped", "message": "No Search Console account connected"}

            refresh_token = decrypt_token(gsc_account.refresh_token)
            gsc_service = SearchConsoleService(
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                refresh_token=refresh_token
            )

            # Fetch 4 weeks of trend data
            week_periods = self.get_n_week_periods(4)
            trend_data = []
            for w_start, w_end in week_periods:
                try:
                    w_metrics = gsc_service.get_search_analytics(gsc_account.site_url, w_start, w_end)
                    trend_data.append({
                        "period": f"{w_start.strftime('%m/%d')}~{w_end.strftime('%m/%d')}",
                        "metrics": w_metrics
                    })
                except Exception as e:
                    logger.warning(f"GSC week fetch failed for {w_start}: {e}")

            if not trend_data:
                return {"status": "error", "message": "Failed to fetch Search Console data"}

            metrics_data = trend_data[-1]["metrics"]
            period_start, period_end = week_periods[-1]

            try:
                top_queries = gsc_service.get_top_queries(gsc_account.site_url, period_start, period_end)
            except Exception as e:
                logger.warning(f"Failed to fetch top queries: {e}")
                top_queries = []

            try:
                top_pages = gsc_service.get_top_pages(gsc_account.site_url, period_start, period_end)
            except Exception as e:
                logger.warning(f"Failed to fetch top pages: {e}")
                top_pages = []

            insight_text = self.gemini.generate_gsc_insight(
                metrics=metrics_data,
                top_queries=top_queries,
                trend_data=trend_data
            )

            period = f"{period_start.strftime('%Y-%m-%d')} ~ {period_end.strftime('%Y-%m-%d')}"
            message_blocks = self.slack.build_gsc_report_message(
                metrics=metrics_data,
                top_queries=top_queries,
                top_pages=top_pages,
                insight=insight_text,
                period=period,
                site_url=gsc_account.site_url,
                trend_data=trend_data
            )

            blocks_list = message_blocks.get("blocks", message_blocks)
            target_channel = notify_channel or tenant.slack_channel_id
            report_text = f"Search Console Report ({period_start} ~ {period_end})"
            slack_ts = None

            if target_channel:
                try:
                    slack_response = self.slack.client.chat_postMessage(
                        channel=target_channel,
                        blocks=blocks_list,
                        text=report_text
                    )
                    slack_ts = slack_response.get("ts")
                    logger.info(f"GSC report posted via chat_postMessage to {target_channel}")
                except Exception as post_error:
                    logger.warning(f"GSC chat_postMessage failed: {post_error}")

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
                        logger.info("GSC report posted via response_url fallback")
                    else:
                        logger.error(f"GSC response_url fallback failed: {r.status_code} {r.text}")
                except Exception as e:
                    logger.error(f"GSC response_url fallback exception: {e}")

            if slack_ts is None:
                return {"status": "error", "message": "GSC 리포트를 채널에 게시할 수 없습니다."}

            return {
                "status": "success",
                "period": f"{period_start} ~ {period_end}",
                "metrics": metrics_data
            }

        except Exception as e:
            logger.error(f"Error generating GSC report: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def get_n_week_periods(self, n: int = 4):
        """Get last n complete weeks' date ranges, oldest first."""
        today = date.today()
        days_since_monday = today.weekday()
        last_sunday = today - timedelta(days=days_since_monday + 1)
        periods = []
        for i in range(n - 1, -1, -1):
            week_end = last_sunday - timedelta(weeks=i)
            week_start = week_end - timedelta(days=6)
            periods.append((week_start, week_end))
        return periods

    def get_weekly_period(self) -> Tuple[date, date]:
        """Get last week's date range (Monday to Sunday)."""
        return self.get_n_week_periods(1)[0]

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
            ("impressions", "impressions"),
            ("clicks", "clicks"),
            ("conversions", "conversions"),
            ("cpc", "cpc"),
            ("cpa", "cpa"),
        ]

        for metric_key, display_key in metrics_to_track:
            current_val = current_metrics.get(metric_key, 0)
            previous_val = previous_metrics.get(metric_key, 0)

            change_pct, emoji = calculate_change(current_val, previous_val)

            # Add change indicator to metrics dict
            current_metrics[f"{display_key}_change"] = f"{emoji} {change_pct}" if emoji else change_pct
