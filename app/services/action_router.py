"""
Action Router Service

Routes parsed intents to appropriate service actions and formats responses.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from app.services.report_service import ReportService
from app.services.keyword_service import KeywordService
from app.services.google_ads_service import GoogleAdsService
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)


class ActionRouter:
    """Routes user intents to appropriate service actions."""

    def __init__(
        self,
        db: Session,
        report_service: ReportService,
        keyword_service: KeywordService,
        google_ads_service: GoogleAdsService,
        gemini_service: GeminiService
    ):
        """
        Initialize ActionRouter with required services.

        Args:
            db: Database session
            report_service: Service for report generation
            keyword_service: Service for keyword operations
            google_ads_service: Service for Google Ads API
            gemini_service: Service for Gemini AI
        """
        self.db = db
        self.report_service = report_service
        self.keyword_service = keyword_service
        self.google_ads_service = google_ads_service
        self.gemini_service = gemini_service

    async def route_action(
        self,
        intent: str,
        entities: Dict[str, Any],
        tenant_id: int,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Route intent to appropriate action and return formatted response.

        Args:
            intent: Parsed intent type
            entities: Extracted entities from user message
            tenant_id: Tenant ID for multi-tenancy
            conversation_history: Previous conversation messages

        Returns:
            Formatted response string ready for Slack
        """
        try:
            logger.info(f"Routing action: intent={intent}, entities={entities}, tenant_id={tenant_id}")

            if intent == "generate_report":
                return await self._handle_generate_report(entities, tenant_id)

            elif intent == "change_schedule":
                return await self._handle_change_schedule(entities, tenant_id)

            elif intent == "answer_question":
                return await self._handle_answer_question(entities, tenant_id, conversation_history)

            elif intent == "keyword_suggestion":
                return await self._handle_keyword_suggestion(entities, tenant_id)

            elif intent == "general_chat":
                return await self._handle_general_chat(entities, tenant_id, conversation_history)

            else:
                logger.warning(f"Unknown intent: {intent}")
                return "I'm not sure how to help with that. Try asking me to:\n" \
                       "• Generate a report\n" \
                       "• Change your report schedule\n" \
                       "• Answer questions about your campaigns\n" \
                       "• Suggest keywords"

        except Exception as e:
            logger.error(f"Error routing action: {e}", exc_info=True)
            return f"Sorry, I encountered an error: {str(e)}. Please try again or contact support."

    async def _handle_generate_report(self, entities: Dict[str, Any], tenant_id: int) -> str:
        """Handle report generation request."""
        try:
            # Parse date range from entities
            start_date, end_date = self._parse_date_range(entities)

            logger.info(f"Generating report for tenant {tenant_id}: {start_date} to {end_date}")

            # Generate report
            report = await self.report_service.generate_weekly_report(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date
            )

            # Format report summary for Slack
            response = f"*Weekly Report Summary* ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})\n\n"
            response += f"*Total Spend:* ${report['total_spend']:,.2f}\n"
            response += f"*Impressions:* {report['total_impressions']:,}\n"
            response += f"*Clicks:* {report['total_clicks']:,}\n"
            response += f"*CTR:* {report['average_ctr']:.2f}%\n"
            response += f"*Conversions:* {report['total_conversions']}\n\n"

            # Top campaigns
            if report.get('top_campaigns'):
                response += "*Top Campaigns:*\n"
                for campaign in report['top_campaigns'][:3]:
                    response += f"• {campaign['name']}: {campaign['clicks']} clicks, ${campaign['spend']:.2f}\n"

            # Recommendations
            if report.get('recommendations'):
                response += f"\n*AI Recommendations:*\n{report['recommendations']}"

            return response

        except Exception as e:
            logger.error(f"Error generating report: {e}", exc_info=True)
            return f"Sorry, I couldn't generate the report: {str(e)}"

    async def _handle_change_schedule(self, entities: Dict[str, Any], tenant_id: int) -> str:
        """Handle report schedule change request."""
        try:
            frequency = entities.get('frequency', 'weekly')
            day = entities.get('day', 'Monday')
            time = entities.get('time', '09:00')

            logger.info(f"Changing schedule for tenant {tenant_id}: {frequency}, {day}, {time}")

            # Update schedule in database
            success = await self.report_service.update_schedule(
                tenant_id=tenant_id,
                frequency=frequency,
                day=day,
                time=time
            )

            if success:
                return f"✅ Report schedule updated!\n" \
                       f"You'll now receive {frequency} reports on *{day}* at *{time}*."
            else:
                return "I couldn't update the schedule. Please check the settings and try again."

        except Exception as e:
            logger.error(f"Error changing schedule: {e}", exc_info=True)
            return f"Sorry, I couldn't update the schedule: {str(e)}"

    async def _handle_answer_question(
        self,
        entities: Dict[str, Any],
        tenant_id: int,
        conversation_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """Handle data question by querying Google Ads."""
        try:
            # Parse date range
            start_date, end_date = self._parse_date_range(entities)

            # Extract metrics of interest
            metrics = entities.get('metrics', ['clicks', 'impressions', 'cost', 'conversions'])
            campaign_name = entities.get('campaign_name')

            logger.info(f"Answering question for tenant {tenant_id}: metrics={metrics}, campaign={campaign_name}")

            # Query Google Ads data
            data = await self.google_ads_service.get_campaign_metrics(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date,
                campaign_name=campaign_name,
                metrics=metrics
            )

            # Use Gemini to format natural language response
            prompt = f"""Based on this Google Ads data, answer the user's question naturally:

Data: {data}
Date Range: {start_date} to {end_date}
Campaign: {campaign_name or 'All campaigns'}
Conversation History: {conversation_history or 'None'}

Format the response in a friendly, conversational way with key metrics highlighted."""

            response = await self.gemini_service.generate_text(prompt)

            return response

        except Exception as e:
            logger.error(f"Error answering question: {e}", exc_info=True)
            return f"Sorry, I couldn't fetch that data: {str(e)}"

    async def _handle_keyword_suggestion(self, entities: Dict[str, Any], tenant_id: int) -> str:
        """Handle keyword suggestion request."""
        try:
            seed_keywords = entities.get('keywords', [])
            campaign_id = entities.get('campaign_id')
            max_suggestions = entities.get('max_suggestions', 10)

            logger.info(f"Suggesting keywords for tenant {tenant_id}: seeds={seed_keywords}")

            # Get keyword suggestions
            suggestions = await self.keyword_service.suggest_keywords(
                tenant_id=tenant_id,
                seed_keywords=seed_keywords,
                campaign_id=campaign_id,
                max_suggestions=max_suggestions
            )

            # Format response
            response = "*Keyword Suggestions:*\n\n"

            for idx, keyword in enumerate(suggestions, 1):
                response += f"{idx}. *{keyword['keyword']}*\n"
                response += f"   • Search Volume: {keyword.get('search_volume', 'N/A')}\n"
                response += f"   • Competition: {keyword.get('competition', 'N/A')}\n"
                response += f"   • Suggested Bid: ${keyword.get('suggested_bid', 0):.2f}\n\n"

            response += "\n_Would you like me to add any of these keywords to your campaign?_"

            return response

        except Exception as e:
            logger.error(f"Error suggesting keywords: {e}", exc_info=True)
            return f"Sorry, I couldn't generate keyword suggestions: {str(e)}"

    async def _handle_general_chat(
        self,
        entities: Dict[str, Any],
        tenant_id: int,
        conversation_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """Handle general chat using Gemini."""
        try:
            # Build context from conversation history
            context = "You are a helpful Google Ads assistant. Be friendly and conversational.\n\n"

            if conversation_history:
                context += "Previous conversation:\n"
                for msg in conversation_history[-5:]:  # Last 5 messages for context
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    context += f"{role}: {content}\n"

            context += f"\nUser message: {entities.get('original_message', '')}"

            # Generate response with Gemini
            response = await self.gemini_service.generate_text(context)

            return response

        except Exception as e:
            logger.error(f"Error in general chat: {e}", exc_info=True)
            return "Sorry, I didn't catch that. Could you rephrase?"

    def _parse_date_range(self, entities: Dict[str, Any]) -> tuple[datetime, datetime]:
        """
        Parse date range from entities.

        Handles natural language like "last week", "this month", "yesterday".

        Args:
            entities: Extracted entities containing date information

        Returns:
            Tuple of (start_date, end_date)
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Check for explicit dates
        if 'start_date' in entities and 'end_date' in entities:
            return entities['start_date'], entities['end_date']

        # Parse natural language date ranges
        time_period = entities.get('time_period', 'last_week').lower()

        if time_period in ['yesterday', 'last_day']:
            start_date = today - timedelta(days=1)
            end_date = today - timedelta(days=1)

        elif time_period in ['last_week', 'past_week']:
            start_date = today - timedelta(days=7)
            end_date = today - timedelta(days=1)

        elif time_period in ['this_week', 'current_week']:
            # Start from Monday
            days_since_monday = today.weekday()
            start_date = today - timedelta(days=days_since_monday)
            end_date = today

        elif time_period in ['last_month', 'past_month']:
            start_date = today - timedelta(days=30)
            end_date = today - timedelta(days=1)

        elif time_period in ['this_month', 'current_month']:
            start_date = today.replace(day=1)
            end_date = today

        elif time_period in ['last_7_days', 'past_7_days']:
            start_date = today - timedelta(days=7)
            end_date = today

        elif time_period in ['last_30_days', 'past_30_days']:
            start_date = today - timedelta(days=30)
            end_date = today

        else:
            # Default to last week
            logger.warning(f"Unknown time period: {time_period}, defaulting to last week")
            start_date = today - timedelta(days=7)
            end_date = today - timedelta(days=1)

        return start_date, end_date
