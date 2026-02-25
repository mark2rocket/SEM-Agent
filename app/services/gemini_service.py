"""Gemini AI service for generating insights."""

from google import genai
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

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        """Initialize GeminiService with google-genai SDK.

        Args:
            api_key: Google API key for Gemini
            model_name: Model to use (default: gemini-2.0-flash)
        """
        try:
            self.client = genai.Client(api_key=api_key)
            self.model_name = model_name
            logger.info(f"GeminiService initialized with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client {model_name}: {e}")
            raise

        rpm = 60 if "flash" in model_name else 10
        self.rate_limiter = RateLimiter(max_requests=rpm)

    def generate_report_insight(
        self,
        metrics: Dict,
        previous_metrics: Optional[Dict] = None,
        trend_data: Optional[list] = None
    ) -> str:
        """Generate Korean insights for performance report."""
        cpa = metrics.get('cpa', 0)
        cpa_display = f"₩{cpa:,.0f}" if cpa > 0 else "전환 없음"

        changes = []
        for key, label in [("cost_change", "비용"), ("clicks_change", "클릭"), ("conversions_change", "전환"), ("cpc_change", "CPC"), ("cpa_change", "CPA")]:
            if key in metrics:
                changes.append(f"{label}: {metrics[key]}")
        change_summary = ", ".join(changes) if changes else "전주 대비 데이터 없음"

        # 4주 트렌드 테이블 생성
        trend_section = ""
        if trend_data and len(trend_data) >= 2:
            rows = []
            for d in trend_data:
                m = d["metrics"]
                cpa_v = m.get("cpa", 0)
                cpa_str = f"₩{cpa_v:,.0f}" if cpa_v > 0 else "N/A"
                rows.append(
                    f"| {d['period']} | ₩{m.get('cpc', 0):,.0f} | {int(m.get('conversions', 0))}건 | {cpa_str} |"
                )
            rows_text = "\n".join(rows)
            trend_section = (
                "\n[4주 트렌드]\n"
                "| 기간 | CPC | 전환수 | CPA |\n"
                "|------|-----|--------|-----|\n"
                f"{rows_text}\n"
            )

        prompt = f"""당신은 10년 경력의 B2B 검색광고(SEM) 전문가입니다.
아래 주간 Google Ads 성과를 분석하여 담당자가 바로 실무에 활용할 수 있는 한국어 코멘트를 작성하세요.

[이번 주 성과]
- 비용: ₩{metrics.get('cost', 0):,.0f}
- 노출: {metrics.get('impressions', 0):,}회
- 클릭: {metrics.get('clicks', 0):,}회
- 전환: {metrics.get('conversions', 0):.0f}건
- CPC: ₩{metrics.get('cpc', 0):,.0f}
- CPA: {cpa_display}

[전주 대비 증감]
{change_summary}
{trend_section}
[지표 해석 기준]
- CPC 감소 = 클릭 효율 개선 (긍정)
- CPA 감소 = 리드 획득 비용 절감 (긍정)
- 비용 증가 + 전환 증가 = 정상 확장 (긍정)
- 비용 증가 + 전환 감소/정체 = 효율 저하 (주의)
- 전환 0건 = 키워드·랜딩페이지 즉시 점검 필요

[작성 규칙]
- 정확히 3문장으로 작성
- 첫 문장: 이번 주 전체 성과를 수치와 함께 한 줄로 평가 (긍정/부정 방향 명확히)
- 둘째 문장: 가장 주목할 지표 변화와 그 의미를 수치 포함하여 설명
- 셋째 문장: 4주 트렌드 흐름을 바탕으로 다음 주 집중해야 할 구체적인 액션 1가지 제안
- ROAS는 절대 언급하지 말 것 (B2B 계정 특성상 해당 없음)
- "분석했습니다" 같은 무의미한 마무리 금지
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            text = response.text
            if not text or not text.strip():
                logger.warning("Gemini returned empty response")
                return "성과 데이터를 분석했습니다."
            return text.strip()
        except Exception as e:
            logger.error(f"Gemini API error [{type(e).__name__}]: {e}", exc_info=True)
            return "성과 데이터를 분석했습니다."

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate general text response using Gemini."""
        if not self.rate_limiter.can_proceed():
            logger.warning("Rate limit exceeded for Gemini API")
            return "죄송합니다. 잠시 후 다시 시도해주세요."

        try:
            self.rate_limiter.add_request()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return "응답을 생성하는 중 오류가 발생했습니다."
