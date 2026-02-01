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
from app.models.report import ReportSchedule, ReportFrequency
from app.models.google_ads import GoogleAdsAccount

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
            logger.info(f"Generating report for tenant {tenant_id}")

            # Generate report (service method only takes tenant_id)
            report = await self.report_service.generate_weekly_report(tenant_id=tenant_id)

            # Check report status
            if report.get('status') == 'error':
                return f"Sorry, I couldn't generate the report: {report.get('message', 'Unknown error')}"

            # Format report summary for Slack
            metrics = report.get('metrics', {})
            period = report.get('period', 'Last week')

            response = f"*Weekly Report Summary* ({period})\n\n"
            response += f"*Total Spend:* ${metrics.get('cost', 0):,.2f}\n"
            response += f"*Impressions:* {metrics.get('impressions', 0):,}\n"
            response += f"*Clicks:* {metrics.get('clicks', 0):,}\n"
            response += f"*Conversions:* {metrics.get('conversions', 0)}\n"
            response += f"*ROAS:* {metrics.get('roas', 0):.2f}\n\n"

            response += "_Report has been sent to your Slack channel!_"

            return response

        except Exception as e:
            logger.error(f"Error generating report: {e}", exc_info=True)
            return f"Sorry, I couldn't generate the report: {str(e)}"

    async def _handle_change_schedule(self, entities: Dict[str, Any], tenant_id: int) -> str:
        """Handle report schedule change request."""
        try:
            frequency = entities.get('frequency', 'weekly')
            day = entities.get('day', 'Monday')
            time_str = entities.get('time', '09:00')

            logger.info(f"Changing schedule for tenant {tenant_id}: {frequency}, {day}, {time_str}")

            # Map day name to day_of_week integer (0=Monday, 6=Sunday)
            day_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            day_of_week = day_map.get(day.lower(), 0)

            # Parse time string to time object
            from datetime import time as time_obj
            hour, minute = map(int, time_str.split(':'))
            time_of_day = time_obj(hour, minute)

            # Map frequency string to ReportFrequency enum
            frequency_map = {
                'daily': ReportFrequency.DAILY,
                'weekly': ReportFrequency.WEEKLY,
                'monthly': ReportFrequency.MONTHLY,
                'disabled': ReportFrequency.DISABLED
            }
            report_frequency = frequency_map.get(frequency.lower(), ReportFrequency.WEEKLY)

            # Update ReportSchedule directly in database
            schedule = self.db.query(ReportSchedule).filter_by(tenant_id=tenant_id).first()

            if schedule:
                schedule.frequency = report_frequency
                schedule.day_of_week = day_of_week
                schedule.time_of_day = time_of_day
                schedule.updated_at = datetime.utcnow()
            else:
                # Create new schedule if it doesn't exist
                schedule = ReportSchedule(
                    tenant_id=tenant_id,
                    frequency=report_frequency,
                    day_of_week=day_of_week,
                    time_of_day=time_of_day
                )
                self.db.add(schedule)

            self.db.commit()

            return f"✅ Report schedule updated!\n" \
                   f"You'll now receive {frequency} reports on *{day}* at *{time_str}*."

        except Exception as e:
            logger.error(f"Error changing schedule: {e}", exc_info=True)
            self.db.rollback()
            return f"Sorry, I couldn't update the schedule: {str(e)}"

    async def _handle_answer_question(
        self,
        entities: Dict[str, Any],
        tenant_id: int,
        conversation_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """Handle data question by querying Google Ads."""
        try:
            # Get customer_id from tenant_id
            account = self.db.query(GoogleAdsAccount).filter_by(
                tenant_id=tenant_id, is_active=True
            ).first()
            if not account:
                logger.error(f"No active Google Ads account for tenant {tenant_id}")
                return "Sorry, I couldn't find an active Google Ads account for your organization. Please set up your Google Ads account first."

            # Parse date range
            start_date, end_date = self._parse_date_range(entities)

            # Extract metrics of interest
            metrics = entities.get('metrics', ['clicks', 'impressions', 'cost', 'conversions'])

            logger.info(f"Answering question for tenant {tenant_id}: metrics={metrics}")

            # Query Google Ads data
            data = await self.google_ads_service.get_campaign_metrics(
                customer_id=account.customer_id,
                date_from=start_date,
                date_to=end_date,
                metrics=metrics
            )

            # Use Gemini to format natural language response
            prompt = f"""Based on this Google Ads data, answer the user's question naturally:

Data: {data}
Date Range: {start_date} to {end_date}
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

            # Use Gemini to generate keyword suggestions
            prompt = f"""You are a Google Ads keyword expert. Generate {max_suggestions} keyword suggestions based on these seed keywords: {', '.join(seed_keywords)}.

For each keyword suggestion, provide:
1. The keyword phrase
2. Estimated search volume category (High/Medium/Low)
3. Competition level (High/Medium/Low)
4. Suggested bid range

Format your response as a numbered list with clear sections for each metric.
Focus on keywords that are relevant for search advertising campaigns."""

            suggestions_text = await self.gemini_service.generate_text(prompt)

            # Format response
            response = "*Keyword Suggestions:*\n\n"
            response += suggestions_text
            response += "\n\n_Would you like me to help you add any of these keywords to your campaign?_"

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
