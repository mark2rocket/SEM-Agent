"""Intent recognition service using Gemini AI."""

import json
import logging
from typing import Dict, List, Optional

from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

# Intent type constants
GENERATE_REPORT = "generate_report"
CHANGE_SCHEDULE = "change_schedule"
ANSWER_QUESTION = "answer_question"
KEYWORD_SUGGESTION = "keyword_suggestion"
GENERAL_CHAT = "general_chat"


class IntentService:
    """Service for natural language intent recognition."""

    def __init__(self, gemini_service: GeminiService):
        """Initialize intent service with Gemini AI.

        Args:
            gemini_service: Configured GeminiService instance
        """
        self.gemini_service = gemini_service

    def parse_intent(
        self,
        message: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict:
        """Parse user message to extract intent and entities.

        Args:
            message: User's natural language message
            conversation_history: Optional list of previous messages for context
                Format: [{"role": "user/assistant", "content": "..."}, ...]

        Returns:
            Dict with structure:
            {
                "intent": str,  # One of the intent constants
                "entities": {
                    "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
                    "metrics": ["cost", "conversions", "roas"],
                    "campaign_names": ["캠페인1", "캠페인2"],
                    "schedule_time": "HH:MM",
                    "schedule_frequency": "daily|weekly|monthly"
                },
                "confidence": float  # 0.0 to 1.0
            }
        """
        try:
            # Build context from conversation history
            context = ""
            if conversation_history:
                context = "\n대화 이력:\n"
                for msg in conversation_history[-5:]:  # Last 5 messages
                    role = "사용자" if msg.get("role") == "user" else "어시스턴트"
                    context += f"{role}: {msg.get('content', '')}\n"

            # System prompt explaining SEM-Agent capabilities
            system_prompt = f"""당신은 SEM-Agent의 의도 분류기입니다. 사용자의 메시지를 분석하여 의도를 파악하고 엔티티를 추출하세요.

SEM-Agent 기능:
1. generate_report: 광고 성과 리포트 생성 (비용, 전환, ROAS 등)
2. change_schedule: 리포트 발송 일정 변경
3. answer_question: 광고 캠페인 관련 질문 답변
4. keyword_suggestion: 키워드 추천 및 최적화
5. general_chat: 일반 대화

{context}

현재 메시지: {message}

다음 JSON 형식으로 응답하세요:
{{
  "intent": "의도 타입 (generate_report|change_schedule|answer_question|keyword_suggestion|general_chat)",
  "entities": {{
    "date_range": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}},
    "metrics": ["비용", "전환", "ROAS 등"],
    "campaign_names": ["캠페인 이름"],
    "schedule_time": "HH:MM",
    "schedule_frequency": "daily|weekly|monthly"
  }},
  "confidence": 0.95
}}

규칙:
- intent는 반드시 5가지 중 하나여야 함
- 관련 없는 엔티티는 생략
- confidence는 0.0~1.0 사이
- 날짜는 "어제", "지난주", "이번달" 등을 해석하여 구체적 날짜로 변환
- JSON만 출력, 설명 불필요"""

            # Generate intent classification
            response = self.gemini_service.model.generate_content(system_prompt)
            response_text = response.text.strip()

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            # Parse JSON response
            result = json.loads(response_text)

            # Validate and normalize
            valid_intents = {
                GENERATE_REPORT,
                CHANGE_SCHEDULE,
                ANSWER_QUESTION,
                KEYWORD_SUGGESTION,
                GENERAL_CHAT
            }

            if result.get("intent") not in valid_intents:
                logger.warning(f"Invalid intent: {result.get('intent')}, defaulting to general_chat")
                result["intent"] = GENERAL_CHAT

            # Ensure entities dict exists
            if "entities" not in result:
                result["entities"] = {}

            # Ensure confidence is valid
            if "confidence" not in result or not 0 <= result["confidence"] <= 1:
                result["confidence"] = 0.5

            logger.info(f"Parsed intent: {result['intent']} with confidence {result['confidence']}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return {
                "intent": GENERAL_CHAT,
                "entities": {},
                "confidence": 0.0
            }
        except Exception as e:
            logger.error(f"Intent parsing error: {e}")
            return {
                "intent": GENERAL_CHAT,
                "entities": {},
                "confidence": 0.0
            }
