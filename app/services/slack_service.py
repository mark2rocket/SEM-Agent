"""Slack messaging service with Block Kit."""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from typing import Dict, List
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

    def build_weekly_report_message(
        self,
        metrics: Dict,
        insight: str,
        period: str
    ) -> Dict:
        """Build Block Kit message for weekly report."""
        # Format metric values with week-over-week changes
        cost_text = f"*총 비용:*\n₩{metrics['cost']:,.0f}"
        if "cost_change" in metrics:
            cost_text += f" {metrics['cost_change']}"

        conversions_text = f"*전환수:*\n{metrics['conversions']:.0f}"
        if "conversions_change" in metrics:
            conversions_text += f" {metrics['conversions_change']}"

        roas_text = f"*ROAS:*\n{metrics['roas']:.0f}%"
        if "roas_change" in metrics:
            roas_text += f" {metrics['roas_change']}"

        clicks_text = f"*클릭수:*\n{metrics.get('clicks', 0):,}"
        if "clicks_change" in metrics:
            clicks_text += f" {metrics['clicks_change']}"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📊 주간 광고 리포트 ({period})"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": cost_text},
                    {"type": "mrkdwn", "text": conversions_text},
                    {"type": "mrkdwn", "text": roas_text},
                    {"type": "mrkdwn", "text": clicks_text}
                ]
            },
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
