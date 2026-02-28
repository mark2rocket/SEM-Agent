"""Unit tests for new features: GSC, Keyword Planner, Intent, ActionRouter."""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import date


# ─────────────────────────────────────────
# SearchConsoleService
# ─────────────────────────────────────────

class TestSearchConsoleService:
    """get_top_pages, get_top_queries, get_search_analytics 테스트."""

    def _make_service(self):
        from app.services.search_console_service import SearchConsoleService
        svc = SearchConsoleService(
            client_id="cid", client_secret="csec", refresh_token="rt"
        )
        mock_gapi = MagicMock()
        svc._service = mock_gapi
        return svc, mock_gapi

    def test_get_top_pages_returns_list(self):
        """get_top_pages: 정상 응답에서 pages 리스트 반환."""
        svc, mock_gapi = self._make_service()
        mock_gapi.searchanalytics().query().execute.return_value = {
            "rows": [
                {"keys": ["https://example.com/blog/post-1"], "clicks": 120,
                 "impressions": 2000, "ctr": 0.06, "position": 4.2},
                {"keys": ["https://example.com/blog/post-2"], "clicks": 85,
                 "impressions": 1500, "ctr": 0.057, "position": 5.1},
            ]
        }
        result = svc.get_top_pages("https://example.com", date(2024, 1, 1), date(2024, 1, 7))
        assert len(result) == 2
        assert result[0]["clicks"] == 120
        assert result[0]["path"] == "/blog/post-1"
        assert result[0]["ctr"] == 6.0

    def test_get_top_pages_empty_response(self):
        """get_top_pages: 데이터 없으면 빈 리스트."""
        svc, mock_gapi = self._make_service()
        mock_gapi.searchanalytics().query().execute.return_value = {"rows": []}
        result = svc.get_top_pages("https://example.com", date(2024, 1, 1), date(2024, 1, 7))
        assert result == []

    def test_get_top_queries_returns_list(self):
        """get_top_queries: 정상 응답에서 queries 리스트 반환."""
        svc, mock_gapi = self._make_service()
        mock_gapi.searchanalytics().query().execute.return_value = {
            "rows": [
                {"keys": ["파이썬 강의"], "clicks": 200, "impressions": 3000,
                 "ctr": 0.067, "position": 3.5},
            ]
        }
        result = svc.get_top_queries("https://example.com", date(2024, 1, 1), date(2024, 1, 7))
        assert len(result) == 1
        assert result[0]["query"] == "파이썬 강의"
        assert result[0]["position"] == 3.5

    def test_get_search_analytics_overview(self):
        """get_search_analytics: 전체 지표 반환."""
        svc, mock_gapi = self._make_service()
        mock_gapi.searchanalytics().query().execute.return_value = {
            "rows": [{"clicks": 500, "impressions": 8000, "ctr": 0.0625, "position": 4.8}]
        }
        result = svc.get_search_analytics("https://example.com", date(2024, 1, 1), date(2024, 1, 7))
        assert result["clicks"] == 500
        assert result["impressions"] == 8000
        assert result["ctr"] == 6.25
        assert result["position"] == 4.8

    def test_get_search_analytics_no_data(self):
        """get_search_analytics: 데이터 없으면 기본값 반환."""
        svc, mock_gapi = self._make_service()
        mock_gapi.searchanalytics().query().execute.return_value = {"rows": []}
        result = svc.get_search_analytics("https://example.com", date(2024, 1, 1), date(2024, 1, 7))
        assert result == {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}


# ─────────────────────────────────────────
# SlackService - build_gsc_report_message
# ─────────────────────────────────────────

class TestGSCReportMessage:
    """build_gsc_report_message 구조 검증."""

    def _make_service(self):
        from app.services.slack_service import SlackService
        with patch("slack_sdk.WebClient"):
            return SlackService(bot_token="xoxb-test")

    def test_gsc_report_has_required_sections(self):
        """GSC 리포트 블록에 검색어·콘텐츠·AI인사이트 섹션 포함."""
        svc = self._make_service()
        metrics = {"clicks": 300, "impressions": 5000, "ctr": 6.0, "position": 4.5}
        top_queries = [
            {"query": "파이썬 튜토리얼", "clicks": 80, "impressions": 1200, "ctr": 6.7, "position": 3.2},
        ]
        top_pages = [
            {"path": "/blog/python-intro", "url": "https://ex.com/blog/python-intro",
             "clicks": 120, "impressions": 2000, "ctr": 6.0, "position": 4.1},
        ]
        result = svc.build_gsc_report_message(
            metrics=metrics,
            top_queries=top_queries,
            top_pages=top_pages,
            insight="이번 주 오가닉 트래픽이 전주 대비 15% 증가했습니다.",
            period="2024-01-08 ~ 2024-01-14",
            site_url="https://example.com"
        )
        blocks = result["blocks"]
        all_text = str(blocks)

        assert "인기 검색어" in all_text
        assert "인기 콘텐츠" in all_text
        assert "AI 인사이트" in all_text or "인사이트" in all_text
        assert "파이썬 튜토리얼" in all_text
        assert "/blog/python-intro" in all_text

    def test_gsc_report_no_pages_shows_no_data(self):
        """top_pages 없으면 '데이터 없음' 표시."""
        svc = self._make_service()
        metrics = {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        result = svc.build_gsc_report_message(
            metrics=metrics, top_queries=[], top_pages=[],
            insight="데이터 없음", period="2024-01-08 ~ 2024-01-14",
            site_url="https://example.com"
        )
        assert "데이터 없음" in str(result["blocks"])

    def test_gsc_report_domain_extracted_from_site_url(self):
        """헤더에 도메인이 올바르게 추출되어 표시."""
        svc = self._make_service()
        metrics = {"clicks": 10, "impressions": 100, "ctr": 10.0, "position": 5.0}
        result = svc.build_gsc_report_message(
            metrics=metrics, top_queries=[], top_pages=None,
            insight="OK", period="2024-01-08 ~ 2024-01-14",
            site_url="https://myblog.com/"
        )
        header = result["blocks"][0]["text"]["text"]
        assert "myblog.com" in header


# ─────────────────────────────────────────
# IntentService - query_gsc_data intent
# ─────────────────────────────────────────

class TestIntentServiceGSC:
    """query_gsc_data intent 분류 테스트."""

    def _make_service(self):
        from app.services.intent_service import IntentService
        mock_gemini = Mock()
        return IntentService(gemini_service=mock_gemini), mock_gemini

    def _mock_response(self, mock_gemini, intent: str, entities: dict = None):
        import json
        payload = {"intent": intent, "entities": entities or {}, "confidence": 0.95}
        mock_resp = Mock()
        mock_resp.text = json.dumps(payload)
        mock_gemini.model.generate_content.return_value = mock_resp

    def test_gsc_query_intent_recognized(self):
        """'인기 검색어 알려줘' → query_gsc_data intent."""
        svc, mock_gemini = self._make_service()
        self._mock_response(mock_gemini, "query_gsc_data",
                            {"gsc_data_type": "queries", "limit": 5})
        result = svc.parse_intent("이번 주 인기 검색어 알려줘")
        assert result["intent"] == "query_gsc_data"
        assert result["confidence"] > 0.5

    def test_gsc_pages_intent_recognized(self):
        """'인기 페이지 보여줘' → query_gsc_data, pages 타입."""
        svc, mock_gemini = self._make_service()
        self._mock_response(mock_gemini, "query_gsc_data",
                            {"gsc_data_type": "pages", "limit": 5})
        result = svc.parse_intent("클릭 많은 페이지 Top 5 보여줘")
        assert result["intent"] == "query_gsc_data"
        assert result["entities"].get("gsc_data_type") == "pages"

    def test_keyword_suggestion_intent_recognized(self):
        """'키워드 추천해줘' → keyword_suggestion intent."""
        svc, mock_gemini = self._make_service()
        self._mock_response(mock_gemini, "keyword_suggestion",
                            {"keywords": ["러닝화"]})
        result = svc.parse_intent("러닝화 관련 키워드 추천해줘")
        assert result["intent"] == "keyword_suggestion"

    def test_invalid_intent_falls_back_to_general_chat(self):
        """알 수 없는 intent → general_chat으로 폴백."""
        svc, mock_gemini = self._make_service()
        self._mock_response(mock_gemini, "unknown_intent")
        result = svc.parse_intent("안녕하세요")
        assert result["intent"] == "general_chat"

    def test_json_parse_error_falls_back(self):
        """Gemini가 JSON이 아닌 응답 → general_chat 폴백."""
        svc, mock_gemini = self._make_service()
        mock_resp = Mock()
        mock_resp.text = "이건 JSON이 아닙니다"
        mock_gemini.model.generate_content.return_value = mock_resp
        result = svc.parse_intent("뭔가 질문")
        assert result["intent"] == "general_chat"
        assert result["confidence"] == 0.0


# ─────────────────────────────────────────
# GoogleAdsService - generate_keyword_ideas
# ─────────────────────────────────────────

class TestKeywordPlannerAPI:
    """generate_keyword_ideas REST API 테스트."""

    def _make_service(self):
        from app.services.google_ads_service import GoogleAdsService
        return GoogleAdsService(
            developer_token="dev-token",
            client_id="cid",
            client_secret="csec",
            refresh_token="rt",
            login_customer_id="1234567890"
        )

    def _mock_token(self, svc):
        svc._access_token = "mock-access-token"
        import time
        svc._token_expiry = time.time() + 3600

    def test_generate_keyword_ideas_returns_list(self):
        """정상 응답에서 keyword idea 리스트 반환."""
        svc = self._make_service()
        self._mock_token(svc)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"text": "러닝화 추천", "keywordIdeaMetrics": {
                    "avgMonthlySearches": "10000",
                    "competition": "HIGH",
                    "competitionIndex": 85,
                    "lowTopOfPageBidMicros": "800000000",
                    "highTopOfPageBidMicros": "1200000000"
                }},
                {"text": "남자 러닝화", "keywordIdeaMetrics": {
                    "avgMonthlySearches": "5400",
                    "competition": "MEDIUM",
                    "competitionIndex": 55,
                    "lowTopOfPageBidMicros": "600000000",
                    "highTopOfPageBidMicros": "900000000"
                }},
            ]
        }
        with patch("requests.post", return_value=mock_resp):
            ideas = svc.generate_keyword_ideas("1234567890", ["러닝화"])
        assert len(ideas) == 2
        assert ideas[0]["keyword"] == "러닝화 추천"
        assert ideas[0]["competition"] == "HIGH"
        assert ideas[0]["low_bid_krw"] == 800
        assert ideas[0]["high_bid_krw"] == 1200

    def test_generate_keyword_ideas_api_error_returns_empty(self):
        """API 오류 시 빈 리스트 반환."""
        svc = self._make_service()
        self._mock_token(svc)
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Permission denied"
        with patch("requests.post", return_value=mock_resp):
            ideas = svc.generate_keyword_ideas("1234567890", ["테스트"])
        assert ideas == []

    def test_generate_keyword_ideas_network_error_returns_empty(self):
        """네트워크 오류 시 빈 리스트 반환."""
        svc = self._make_service()
        self._mock_token(svc)
        with patch("requests.post", side_effect=Exception("timeout")):
            ideas = svc.generate_keyword_ideas("1234567890", ["테스트"])
        assert ideas == []

    def test_generate_keyword_ideas_micros_conversion(self):
        """micros → 원 변환이 올바른지 확인."""
        svc = self._make_service()
        self._mock_token(svc)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"text": "테스트 키워드", "keywordIdeaMetrics": {
                    "avgMonthlySearches": "1000",
                    "competition": "LOW",
                    "competitionIndex": 20,
                    "lowTopOfPageBidMicros": "500000000",   # 500원
                    "highTopOfPageBidMicros": "1000000000"  # 1000원
                }}
            ]
        }
        with patch("requests.post", return_value=mock_resp):
            ideas = svc.generate_keyword_ideas("1234567890", ["테스트"])
        assert ideas[0]["low_bid_krw"] == 500
        assert ideas[0]["high_bid_krw"] == 1000


# ─────────────────────────────────────────
# ActionRouter - _handle_query_gsc_data
# ─────────────────────────────────────────

class TestActionRouterGSC:
    """ActionRouter의 GSC 데이터 조회 handler 테스트."""

    def _make_router(self, db=None, gsc_account=None):
        from app.services.action_router import ActionRouter
        mock_db = db or Mock()
        mock_report = Mock()
        mock_keyword = Mock()
        mock_gads = Mock()
        mock_gemini = Mock()

        router = ActionRouter(
            db=mock_db,
            report_service=mock_report,
            keyword_service=mock_keyword,
            google_ads_service=mock_gads,
            gemini_service=mock_gemini
        )
        return router, mock_db, mock_gemini

    @pytest.mark.asyncio
    async def test_gsc_not_connected_returns_error_message(self):
        """GSC 미연동 시 안내 메시지 반환."""
        router, mock_db, _ = self._make_router()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = await router._handle_query_gsc_data(
            {"gsc_data_type": "queries"}, tenant_id=1
        )
        assert "연동" in result
        assert "/sem-connect" in result

    @pytest.mark.asyncio
    async def test_gsc_queries_returns_formatted_list(self):
        """queries 타입: 검색어 리스트 포맷 반환."""
        from app.models.google_ads import SearchConsoleAccount
        router, mock_db, _ = self._make_router()

        mock_account = Mock(spec=SearchConsoleAccount)
        mock_account.site_url = "https://example.com"
        mock_account.refresh_token = "encrypted_rt"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_account

        mock_queries = [
            {"query": "파이썬 강의", "clicks": 100, "impressions": 1500, "ctr": 6.7, "position": 3.2}
        ]

        with patch("app.core.security.decrypt_token", return_value="raw_rt"), \
             patch("app.services.search_console_service.SearchConsoleService") as mock_svc_cls:
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_top_queries.return_value = mock_queries

            result = await router._handle_query_gsc_data(
                {"gsc_data_type": "queries", "limit": 5,
                 "original_message": "인기 검색어 알려줘"}, tenant_id=1
            )

        assert "파이썬 강의" in result
        assert "100클릭" in result or "100" in result

    @pytest.mark.asyncio
    async def test_gsc_pages_returns_formatted_list(self):
        """pages 타입: 페이지 리스트 포맷 반환."""
        from app.models.google_ads import SearchConsoleAccount
        router, mock_db, _ = self._make_router()

        mock_account = Mock(spec=SearchConsoleAccount)
        mock_account.site_url = "https://example.com"
        mock_account.refresh_token = "encrypted_rt"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_account

        mock_pages = [
            {"path": "/blog/python", "url": "https://example.com/blog/python",
             "clicks": 200, "impressions": 3000, "ctr": 6.7, "position": 4.1}
        ]

        with patch("app.core.security.decrypt_token", return_value="raw_rt"), \
             patch("app.services.search_console_service.SearchConsoleService") as mock_svc_cls:
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_top_pages.return_value = mock_pages

            result = await router._handle_query_gsc_data(
                {"gsc_data_type": "pages", "limit": 5,
                 "original_message": "인기 페이지 보여줘"}, tenant_id=1
            )

        assert "/blog/python" in result
        assert "200클릭" in result or "200" in result
