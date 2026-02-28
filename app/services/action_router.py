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
from app.models.google_ads import GoogleAdsAccount, SearchConsoleAccount

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

            elif intent == "query_gsc_data":
                return await self._handle_query_gsc_data(entities, tenant_id)

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
            report = self.report_service.generate_weekly_report(tenant_id=tenant_id)

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
        """Handle keyword suggestion request using Google Ads Keyword Planner."""
        try:
            seed_keywords = entities.get('keywords', [])
            if not seed_keywords:
                # 원본 메시지에서 키워드 추출 시도
                original = entities.get('original_message', '')
                seed_keywords = [w for w in original.split() if len(w) > 1 and w not in
                                 ['키워드', '추천', '알려줘', '보여줘', '뭐야', '관련', '해줘']][:3]

            if not seed_keywords:
                return "키워드 추천을 위해 시드 키워드를 알려주세요.\n예: `@봇 \"러닝화\" 키워드 추천해줘`"

            account = self.db.query(GoogleAdsAccount).filter_by(
                tenant_id=tenant_id, is_active=True
            ).first()
            if not account:
                return "❌ Google Ads 계정이 연동되어 있지 않습니다."

            logger.info(f"Keyword Planner request: seeds={seed_keywords}, tenant={tenant_id}")

            import asyncio
            ideas = await asyncio.to_thread(
                self.google_ads_service.generate_keyword_ideas,
                account.customer_id,
                seed_keywords,
                limit=10
            )

            if not ideas:
                # Keyword Planner 실패 시 Gemini 폴백
                logger.warning("Keyword Planner returned no results, falling back to Gemini")
                prompt = f"""한국 Google Ads 전문가로서 다음 시드 키워드 기반으로 10개 키워드를 추천해줘: {', '.join(seed_keywords)}
각 키워드별로 예상 검색량(높음/중간/낮음), 경쟁도, 추천 입찰가를 포함해서 한국어로 답변해줘."""
                return await self.gemini_service.generate_text(prompt)

            comp_map = {"HIGH": "높음", "MEDIUM": "보통", "LOW": "낮음", "UNKNOWN": "-"}
            lines = [f"🔑 *키워드 아이디어* (시드: {', '.join(seed_keywords)})"]
            lines.append("")
            for i, idea in enumerate(ideas, 1):
                comp = comp_map.get(idea['competition'], idea['competition'])
                searches = idea['avg_monthly_searches']
                bid = f"₩{idea['low_bid_krw']:,}~{idea['high_bid_krw']:,}" if idea['high_bid_krw'] > 0 else "N/A"
                lines.append(
                    f"{i}. `{idea['keyword']}` — 월 검색 {searches} · 경쟁도 {comp} · 입찰가 {bid}"
                )
            lines.append("")
            lines.append("_캠페인에 추가하고 싶은 키워드가 있으면 알려주세요!_")
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error suggesting keywords: {e}", exc_info=True)
            return f"키워드 추천 중 오류가 발생했습니다: {str(e)}"

    async def _handle_query_gsc_data(self, entities: Dict[str, Any], tenant_id: int) -> str:
        """Handle Google Search Console data query."""
        try:
            from app.services.search_console_service import SearchConsoleService
            from app.core.security import decrypt_token
            from app.config import settings

            gsc_account = self.db.query(SearchConsoleAccount).filter_by(
                tenant_id=tenant_id, is_active=True
            ).first()
            if not gsc_account or not gsc_account.refresh_token:
                return "❌ Search Console이 연동되어 있지 않습니다. `/sem-connect` 에서 연동해주세요."

            refresh_token = decrypt_token(gsc_account.refresh_token)
            gsc_service = SearchConsoleService(
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                refresh_token=refresh_token
            )

            start_date, end_date = self._parse_date_range(entities)
            data_type = entities.get("gsc_data_type", "overview")
            limit = int(entities.get("limit", 5))
            target_url = entities.get("target_url")

            from datetime import date as date_type
            start = start_date.date() if hasattr(start_date, "date") else start_date
            end = end_date.date() if hasattr(end_date, "date") else end_date

            period_str = f"{start} ~ {end}"
            data_summary = f"사이트: {gsc_account.site_url}\n기간: {period_str}\n"

            if data_type == "queries":
                rows = gsc_service.get_top_queries(gsc_account.site_url, start, end, limit)
                if not rows:
                    return f"📊 해당 기간({period_str}) 검색어 데이터가 없습니다."
                lines = [f"🔎 *인기 검색어 Top {len(rows)}* ({period_str})"]
                for i, r in enumerate(rows, 1):
                    lines.append(f"{i}. `{r['query']}` — {r['clicks']}클릭 · {r['impressions']}노출 · CTR {r['ctr']:.1f}% · {r['position']:.1f}위")
                return "\n".join(lines)

            elif data_type == "pages":
                rows = gsc_service.get_top_pages(gsc_account.site_url, start, end, limit)
                if not rows:
                    return f"📄 해당 기간({period_str}) 페이지 데이터가 없습니다."
                lines = [f"📄 *인기 콘텐츠 Top {len(rows)}* ({period_str})"]
                for i, r in enumerate(rows, 1):
                    path = r.get("path", r.get("url", "-"))
                    lines.append(f"{i}. `{path}` — {r['clicks']}클릭 · {r['impressions']}노출 · CTR {r['ctr']:.1f}% · {r['position']:.1f}위")
                return "\n".join(lines)

            else:  # overview
                metrics = gsc_service.get_search_analytics(gsc_account.site_url, start, end)
                data_summary += (
                    f"클릭: {metrics.get('clicks', 0):,}회\n"
                    f"노출: {metrics.get('impressions', 0):,}회\n"
                    f"CTR: {metrics.get('ctr', 0):.1f}%\n"
                    f"평균 순위: {metrics.get('position', 0):.1f}위"
                )

                prompt = f"""다음 Google Search Console 데이터를 보고 자연스럽게 한국어로 요약해줘:

{data_summary}

사용자 질문 맥락: {entities.get('original_message', '')}

2~3문장으로 핵심만 간결하게 답변해줘."""
                return await self.gemini_service.generate_text(prompt)

        except Exception as e:
            logger.error(f"Error querying GSC data: {e}", exc_info=True)
            return f"Search Console 데이터 조회 중 오류가 발생했습니다: {str(e)}"

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
