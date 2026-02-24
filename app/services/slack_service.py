"""Slack messaging service with Block Kit."""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class SlackService:
    """Service for Slack messaging and Block Kit."""

    def __init__(self, bot_token: str):
        self.client = WebClient(token=bot_token)

    def send_message(self, message: Dict, channel: str = None) -> Dict:
        """Send a message to Slack channel."""
        try:
            # Support both direct blocks and message dict format
            if "blocks" in message:
                blocks = message["blocks"]
            else:
                blocks = message

            # Use provided channel or default from settings
            if not channel:
                from ..config import settings
                channel = settings.slack_alert_channel

            response = self.client.chat_postMessage(
                channel=channel,
                blocks=blocks
            )
            return response.data
        except SlackApiError as e:
            logger.error(f"Slack API error: {e}")
            raise

    def _build_trend_chart_url(self, trend_data: list) -> str:
        """Build QuickChart.io short URL for 4-week trend chart (CPA, CPC, 전환수).

        Uses QuickChart create API to generate a short URL that Slack can render.
        """
        import json
        import requests as http_requests

        labels = [d["period"] for d in trend_data]
        cpa_data = [round(d["metrics"].get("cpa", 0)) for d in trend_data]
        cpc_data = [round(d["metrics"].get("cpc", 0)) for d in trend_data]
        conversions_data = [int(d["metrics"].get("conversions", 0)) for d in trend_data]

        chart_config = {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "type": "line",
                        "label": "CPA",
                        "data": cpa_data,
                        "borderColor": "#E53E3E",
                        "backgroundColor": "rgba(0,0,0,0)",
                        "yAxisID": "y",
                        "tension": 0.3,
                        "pointRadius": 5,
                        "borderWidth": 2
                    },
                    {
                        "type": "line",
                        "label": "CPC",
                        "data": cpc_data,
                        "borderColor": "#3182CE",
                        "backgroundColor": "rgba(0,0,0,0)",
                        "yAxisID": "y",
                        "tension": 0.3,
                        "pointRadius": 5,
                        "borderWidth": 2
                    },
                    {
                        "type": "bar",
                        "label": "Conv",
                        "data": conversions_data,
                        "backgroundColor": "rgba(56,161,105,0.6)",
                        "yAxisID": "y1"
                    }
                ]
            },
            "options": {
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "4-Week Trend: CPA / CPC / Conversions",
                        "font": {"size": 14}
                    },
                    "legend": {"position": "bottom"}
                },
                "scales": {
                    "y": {
                        "type": "linear",
                        "position": "left",
                        "title": {"display": True, "text": "Cost (KRW)"},
                        "grid": {"color": "rgba(0,0,0,0.05)"}
                    },
                    "y1": {
                        "type": "linear",
                        "position": "right",
                        "title": {"display": True, "text": "Conversions"},
                        "grid": {"drawOnChartArea": False},
                        "ticks": {"stepSize": 1}
                    }
                }
            }
        }

        # QuickChart create API → 단축 URL 반환 (Slack image block 렌더링 호환)
        try:
            resp = http_requests.post(
                "https://quickchart.io/chart/create",
                json={"chart": json.dumps(chart_config), "width": 600, "height": 280, "backgroundColor": "white"},
                timeout=10
            )
            if resp.status_code == 200:
                result = resp.json()
                if result.get("success"):
                    return result["url"]
                logger.warning(f"QuickChart create API returned: {result}")
            else:
                logger.warning(f"QuickChart create API HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"QuickChart create API error: {e}", exc_info=True)

        return ""

    def build_weekly_report_message(
        self,
        metrics: Dict,
        insight: str,
        period: str,
        trend_data: list = None
    ) -> Dict:
        """Build Block Kit message for weekly report."""
        def fmt_change(key: str) -> str:
            return f" {metrics[key]}" if key in metrics else ""

        cpa_val = metrics.get("cpa", 0)
        cpa_display = f"₩{cpa_val:,.0f}" if cpa_val > 0 else "N/A"

        cost_text = f"*비용:*\n₩{metrics['cost']:,.0f}{fmt_change('cost_change')}"
        impressions_text = f"*노출:*\n{metrics.get('impressions', 0):,}{fmt_change('impressions_change')}"
        clicks_text = f"*클릭:*\n{metrics.get('clicks', 0):,}{fmt_change('clicks_change')}"
        conversions_text = f"*전환:*\n{metrics.get('conversions', 0):.0f}{fmt_change('conversions_change')}"
        cpc_text = f"*CPC:*\n₩{metrics.get('cpc', 0):,.0f}{fmt_change('cpc_change')}"
        cpa_text = f"*CPA:*\n{cpa_display}{fmt_change('cpa_change')}"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📊 주간 광고 리포트 ({period})"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": cost_text},
                    {"type": "mrkdwn", "text": impressions_text}
                ]
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": clicks_text},
                    {"type": "mrkdwn", "text": conversions_text}
                ]
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": cpc_text},
                    {"type": "mrkdwn", "text": cpa_text}
                ]
            }
        ]

        # 4주 트렌드 차트 (데이터가 2주 이상일 때만)
        if trend_data and len(trend_data) >= 2:
            chart_url = self._build_trend_chart_url(trend_data)
            if chart_url:
                blocks += [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "*📈 4주 트렌드*"}
                    },
                    {
                        "type": "image",
                        "image_url": chart_url,
                        "alt_text": "4주 트렌드 차트 (CPA, CPC, 전환수)"
                    }
                ]

        blocks += [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"💡 *AI 인사이트*\n{insight}"}
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "Powered by Gemini AI"}]
            }
        ]
        return {"blocks": blocks}

    def build_keyword_alert_message(self, keyword_data: Dict, approval_request_id: int = None) -> Dict:
        """Build Block Kit message for keyword alert."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "⚠️ 비효율 검색어 발견"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*검색어:*\n{keyword_data['search_term']}"},
                    {"type": "mrkdwn", "text": f"*캠페인:*\n{keyword_data['campaign_name']}"},
                    {"type": "mrkdwn", "text": f"*비용:*\n₩{keyword_data['cost']:,.0f}"},
                    {"type": "mrkdwn", "text": f"*클릭:*\n{keyword_data['clicks']}"},
                    {"type": "mrkdwn", "text": f"*전환:*\n{keyword_data['conversions']}"}
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "제외 승인"},
                        "style": "primary",
                        "action_id": "approve_keyword",
                        "value": str(approval_request_id) if approval_request_id else "0"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "무시"},
                        "action_id": "ignore_keyword",
                        "value": str(approval_request_id) if approval_request_id else "0"
                    }
                ]
            }
        ]
        return {"blocks": blocks}
