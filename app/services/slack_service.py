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

    def _build_sparkline(self, values: list) -> str:
        """숫자 리스트를 유니코드 스파크라인 문자열로 변환."""
        if not values or len(values) < 2:
            return ""
        blocks = "▁▂▃▄▅▆▇█"
        min_v = min(values)
        max_v = max(values)
        if max_v == min_v:
            return "▄" * len(values)
        result = ""
        for v in values:
            idx = round((v - min_v) / (max_v - min_v) * 7)
            result += blocks[max(0, min(7, idx))]
        return result

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

        # 4주 스파크라인 생성
        spark = {}
        if trend_data and len(trend_data) >= 2:
            for key in ("cost", "impressions", "clicks", "conversions", "cpc", "cpa"):
                vals = [d["metrics"].get(key, 0) for d in trend_data]
                spark[key] = f" `{self._build_sparkline(vals)}`"
        else:
            spark = {k: "" for k in ("cost", "impressions", "clicks", "conversions", "cpc", "cpa")}

        cost_text = f"*비용:*\n₩{metrics['cost']:,.0f}{fmt_change('cost_change')}{spark['cost']}"
        impressions_text = f"*노출:*\n{metrics.get('impressions', 0):,}{fmt_change('impressions_change')}{spark['impressions']}"
        clicks_text = f"*클릭:*\n{metrics.get('clicks', 0):,}{fmt_change('clicks_change')}{spark['clicks']}"
        conversions_text = f"*전환:*\n{metrics.get('conversions', 0):.0f}{fmt_change('conversions_change')}{spark['conversions']}"
        cpc_text = f"*CPC:*\n₩{metrics.get('cpc', 0):,.0f}{fmt_change('cpc_change')}{spark['cpc']}"
        cpa_text = f"*CPA:*\n{cpa_display}{fmt_change('cpa_change')}{spark['cpa']}"

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
