"""Gemini AI service for generating insights."""

import google.generativeai as genai
from typing import Dict, Optional
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, max_requests: int, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()

    def can_proceed(self) -> bool:
        now = time.time()
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        return len(self.requests) < self.max_requests

    def add_request(self):
        self.requests.append(time.time())


class GeminiService:
    """Service for Gemini AI integration."""

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        rpm = 60 if "flash" in model_name else 10
        self.rate_limiter = RateLimiter(max_requests=rpm)

    def generate_report_insight(
        self,
        metrics: Dict,
        previous_metrics: Optional[Dict] = None
    ) -> str:
        """Generate Korean insights for performance report."""
        prompt = f"""다음 광고 성과 데이터를 분석하여 3문장 이내의 한국어 인사이트를 작성해주세요:

현재 기간:
- 비용: ₩{metrics.get('cost', 0):,.0f}
- 전환: {metrics.get('conversions', 0)}건
- ROAS: {metrics.get('roas', 0)}%
"""
        # TODO: Implement rate limiting and actual API call
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return "성과 데이터를 분석했습니다."

    def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate general text response using Gemini."""
        if not self.rate_limiter.can_proceed():
            logger.warning("Rate limit exceeded for Gemini API")
            return "죄송합니다. 잠시 후 다시 시도해주세요."

        try:
            self.rate_limiter.add_request()
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return "응답을 생성하는 중 오류가 발생했습니다."
