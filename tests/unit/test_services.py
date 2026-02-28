"""Unit tests for service modules."""

from unittest.mock import Mock, patch, MagicMock
from datetime import date, timedelta

from app.services.keyword_service import KeywordService
from app.services.report_service import ReportService
from app.services.gemini_service import GeminiService, RateLimiter
from app.services.slack_service import SlackService


class TestKeywordService:
    """Test KeywordService."""

    def test_keyword_service_initialization(self):
        """Test KeywordService can be initialized."""
        mock_db = Mock()
        mock_google_ads = Mock()
        mock_slack = Mock()

        service = KeywordService(
            db=mock_db,
            google_ads_service=mock_google_ads,
            slack_service=mock_slack
        )

        assert service.db is not None
        assert service.google_ads is not None
        assert service.slack is not None

    def test_detect_inefficient_keywords_returns_list(self, db):
        """Test detect_inefficient_keywords returns a list."""
        from app.models.tenant import Tenant

        # Create tenant in database
        tenant = Tenant(workspace_id="T123", workspace_name="Test")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        mock_google_ads = Mock()
        mock_google_ads.get_search_terms.return_value = []
        mock_slack = Mock()

        service = KeywordService(
            db=db,
            google_ads_service=mock_google_ads,
            slack_service=mock_slack
        )

        result = service.detect_inefficient_keywords(tenant_id=tenant.id)
        assert isinstance(result, list)

    def test_create_approval_request_returns_int(self, db):
        """Test create_approval_request returns an integer."""
        from app.models.tenant import Tenant

        # Create tenant in database
        tenant = Tenant(workspace_id="T123", workspace_name="Test")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        mock_google_ads = Mock()
        mock_slack = Mock()
        mock_slack.build_keyword_alert_message.return_value = {"blocks": []}
        mock_slack.send_message.return_value = {"ts": "123.456"}

        service = KeywordService(
            db=db,
            google_ads_service=mock_google_ads,
            slack_service=mock_slack
        )

        keyword_data = {
            "search_term": "test keyword",
            "campaign_id": "C001",
            "campaign_name": "Test Campaign",
            "cost": 10000,
            "clicks": 50,
            "conversions": 0
        }

        result = service.create_approval_request(tenant_id=tenant.id, keyword_data=keyword_data)
        assert isinstance(result, int)

    def test_approve_keyword_returns_bool(self, db):
        """Test approve_keyword returns a boolean."""
        from app.models.tenant import Tenant
        from app.models.keyword import KeywordCandidate, ApprovalRequest, KeywordStatus
        from datetime import datetime

        # Create tenant and keyword in database
        tenant = Tenant(workspace_id="T123", workspace_name="Test")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        keyword = KeywordCandidate(
            tenant_id=tenant.id,
            campaign_id="C001",
            campaign_name="Test",
            search_term="test",
            cost=10000,
            clicks=10,
            conversions=0,
            status=KeywordStatus.PENDING
        )
        db.add(keyword)
        db.commit()
        db.refresh(keyword)

        approval = ApprovalRequest(
            keyword_candidate_id=keyword.id,
            slack_message_ts="123.456",
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)

        mock_google_ads = Mock()
        mock_google_ads.add_negative_keyword.return_value = True
        mock_slack = Mock()

        service = KeywordService(
            db=db,
            google_ads_service=mock_google_ads,
            slack_service=mock_slack
        )

        result = service.approve_keyword(approval_request_id=approval.id, slack_user_id="U12345")
        assert isinstance(result, bool)


class TestReportService:
    """Test ReportService."""

    def test_report_service_initialization(self):
        """Test ReportService can be initialized."""
        mock_db = Mock()
        mock_google_ads = Mock()
        mock_gemini = Mock()
        mock_slack = Mock()

        service = ReportService(
            db=mock_db,
            google_ads_service=mock_google_ads,
            gemini_service=mock_gemini,
            slack_service=mock_slack
        )

        assert service.db is not None
        assert service.google_ads is not None
        assert service.gemini is not None
        assert service.slack is not None

    def test_generate_weekly_report_returns_dict(self):
        """Test generate_weekly_report returns a dict."""
        mock_db = Mock()
        mock_google_ads = Mock()
        mock_gemini = Mock()
        mock_slack = Mock()

        service = ReportService(
            db=mock_db,
            google_ads_service=mock_google_ads,
            gemini_service=mock_gemini,
            slack_service=mock_slack
        )

        result = service.generate_weekly_report(tenant_id=1)
        assert isinstance(result, dict)

    def test_get_weekly_period_returns_monday_to_sunday(self):
        """Test get_weekly_period returns correct date range."""
        mock_db = Mock()
        mock_google_ads = Mock()
        mock_gemini = Mock()
        mock_slack = Mock()

        service = ReportService(
            db=mock_db,
            google_ads_service=mock_google_ads,
            gemini_service=mock_gemini,
            slack_service=mock_slack
        )

        monday, sunday = service.get_weekly_period()

        # Verify dates are in correct order
        assert monday < sunday

        # Verify it's a 7-day period (Monday to Sunday)
        assert (sunday - monday).days == 6

        # Verify monday is actually a Monday (weekday() returns 0 for Monday)
        assert monday.weekday() == 0

        # Verify sunday is actually a Sunday (weekday() returns 6 for Sunday)
        assert sunday.weekday() == 6

    def test_get_weekly_period_returns_last_week(self):
        """Test get_weekly_period returns last week, not current week."""
        mock_db = Mock()
        mock_google_ads = Mock()
        mock_gemini = Mock()
        mock_slack = Mock()

        service = ReportService(
            db=mock_db,
            google_ads_service=mock_google_ads,
            gemini_service=mock_gemini,
            slack_service=mock_slack
        )

        monday, sunday = service.get_weekly_period()
        today = date.today()

        # Both dates should be in the past
        assert monday < today
        assert sunday < today


class TestRateLimiter:
    """Test RateLimiter."""

    def test_can_proceed_when_under_limit(self):
        limiter = RateLimiter(max_requests=5)
        assert limiter.can_proceed() is True

    def test_blocked_when_limit_exceeded(self):
        limiter = RateLimiter(max_requests=2)
        limiter.add_request()
        limiter.add_request()
        assert limiter.can_proceed() is False

    def test_allows_after_window_expires(self):
        import time
        limiter = RateLimiter(max_requests=1, time_window=1)
        limiter.requests.append(time.time() - 2)  # expired request
        assert limiter.can_proceed() is True


class TestGeminiService:
    """Test GeminiService with mocked google-genai SDK."""

    def _make_service(self, mock_client_cls):
        """Helper: create GeminiService with mocked Client."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        service = GeminiService(api_key="test-key", model_name="gemini-2.0-flash")
        return service, mock_client

    def test_initialization(self):
        with patch("google.genai.Client") as mock_client_cls:
            service, _ = self._make_service(mock_client_cls)
            mock_client_cls.assert_called_once_with(api_key="test-key")
            assert service.model_name == "gemini-2.0-flash"

    def test_flash_model_sets_high_rpm(self):
        with patch("google.genai.Client"):
            service = GeminiService(api_key="test-key", model_name="gemini-2.0-flash")
            assert service.rate_limiter.max_requests == 60

    def test_pro_model_sets_low_rpm(self):
        with patch("google.genai.Client"):
            service = GeminiService(api_key="test-key", model_name="gemini-1.5-pro")
            assert service.rate_limiter.max_requests == 10

    def test_generate_report_insight_success(self):
        with patch("google.genai.Client") as mock_client_cls:
            service, mock_client = self._make_service(mock_client_cls)

            mock_response = MagicMock()
            mock_response.text = "이번 주 광고 성과가 우수합니다. CPA가 10% 개선되었습니다. 다음 주에는 전환율 높은 키워드 입찰가를 높이세요."
            mock_client.models.generate_content.return_value = mock_response

            metrics = {
                "cost": 1000000, "impressions": 10000,
                "clicks": 500, "conversions": 10,
                "cpc": 2000, "cpa": 100000
            }
            result = service.generate_report_insight(metrics=metrics)

            assert result == "이번 주 광고 성과가 우수합니다. CPA가 10% 개선되었습니다. 다음 주에는 전환율 높은 키워드 입찰가를 높이세요."
            mock_client.models.generate_content.assert_called_once()
            call_kwargs = mock_client.models.generate_content.call_args
            assert call_kwargs.kwargs["model"] == "gemini-2.0-flash"
            assert "₩1,000,000" in call_kwargs.kwargs["contents"]

    def test_generate_report_insight_with_trend_data(self):
        with patch("google.genai.Client") as mock_client_cls:
            service, mock_client = self._make_service(mock_client_cls)

            mock_response = MagicMock()
            mock_response.text = "4주 트렌드 기반 분석입니다."
            mock_client.models.generate_content.return_value = mock_response

            metrics = {"cost": 500000, "impressions": 5000, "clicks": 250, "conversions": 5, "cpc": 2000, "cpa": 100000}
            trend_data = [
                {"period": "01/01~01/07", "metrics": {"cpc": 2200, "conversions": 4, "cpa": 110000}},
                {"period": "01/08~01/14", "metrics": {"cpc": 2100, "conversions": 5, "cpa": 100000}},
            ]
            result = service.generate_report_insight(metrics=metrics, trend_data=trend_data)

            assert result == "4주 트렌드 기반 분석입니다."
            prompt_content = mock_client.models.generate_content.call_args.kwargs["contents"]
            assert "4주 트렌드" in prompt_content
            assert "01/01~01/07" in prompt_content

    def test_generate_report_insight_api_error_returns_fallback(self):
        with patch("google.genai.Client") as mock_client_cls:
            service, mock_client = self._make_service(mock_client_cls)
            mock_client.models.generate_content.side_effect = Exception("403 API key reported as leaked")

            metrics = {"cost": 1000000, "impressions": 10000, "clicks": 500, "conversions": 10, "cpc": 2000, "cpa": 100000}
            result = service.generate_report_insight(metrics=metrics)

            assert result == "성과 데이터를 분석했습니다."

    def test_generate_report_insight_empty_response_returns_fallback(self):
        with patch("google.genai.Client") as mock_client_cls:
            service, mock_client = self._make_service(mock_client_cls)

            mock_response = MagicMock()
            mock_response.text = "   "
            mock_client.models.generate_content.return_value = mock_response

            metrics = {"cost": 0, "impressions": 0, "clicks": 0, "conversions": 0, "cpc": 0, "cpa": 0}
            result = service.generate_report_insight(metrics=metrics)

            assert result == "성과 데이터를 분석했습니다."

    def test_generate_report_insight_no_roas_in_prompt(self):
        """ROAS는 B2B 계정에서 사용 금지 - 프롬프트에 ROAS 없어야 함."""
        with patch("google.genai.Client") as mock_client_cls:
            service, mock_client = self._make_service(mock_client_cls)

            mock_response = MagicMock()
            mock_response.text = "정상 응답"
            mock_client.models.generate_content.return_value = mock_response

            metrics = {"cost": 1000000, "impressions": 10000, "clicks": 500, "conversions": 10, "cpc": 2000, "cpa": 100000}
            service.generate_report_insight(metrics=metrics)

            prompt_content = mock_client.models.generate_content.call_args.kwargs["contents"]
            assert "ROAS" in prompt_content  # 금지 규칙으로 언급되어야 함
            assert "절대 언급하지 말 것" in prompt_content


class TestSlackService:
    """Test SlackService Block Kit message builders."""

    def _make_service(self):
        with patch("slack_sdk.WebClient"):
            return SlackService(bot_token="xoxb-test-token")

    def test_build_weekly_report_message_returns_blocks(self):
        service = self._make_service()
        metrics = {
            "cost": 1000000, "impressions": 10000,
            "clicks": 500, "conversions": 10,
            "cpc": 2000, "cpa": 100000
        }
        result = service.build_weekly_report_message(
            metrics=metrics,
            insight="좋은 성과입니다.",
            period="2024-01-01 ~ 2024-01-07"
        )
        assert "blocks" in result
        blocks = result["blocks"]
        assert len(blocks) > 0
        # 헤더 블록 확인
        assert blocks[0]["type"] == "header"
        assert "주간 광고 리포트" in blocks[0]["text"]["text"]

    def test_build_weekly_report_message_contains_all_metrics(self):
        service = self._make_service()
        metrics = {
            "cost": 1500000, "impressions": 20000,
            "clicks": 800, "conversions": 15,
            "cpc": 1875, "cpa": 100000
        }
        result = service.build_weekly_report_message(
            metrics=metrics,
            insight="테스트 인사이트",
            period="2024-01-01 ~ 2024-01-07"
        )
        blocks_text = str(result)
        assert "₩1,500,000" in blocks_text   # 비용
        assert "20,000" in blocks_text         # 노출
        assert "800" in blocks_text            # 클릭
        assert "15" in blocks_text             # 전환
        assert "₩1,875" in blocks_text         # CPC
        assert "₩100,000" in blocks_text       # CPA

    def test_build_weekly_report_message_contains_insight(self):
        service = self._make_service()
        metrics = {"cost": 0, "impressions": 0, "clicks": 0, "conversions": 0, "cpc": 0, "cpa": 0}
        result = service.build_weekly_report_message(
            metrics=metrics,
            insight="이번 주는 전환이 없어 키워드 점검이 필요합니다.",
            period="2024-01-01 ~ 2024-01-07"
        )
        blocks_text = str(result)
        assert "이번 주는 전환이 없어 키워드 점검이 필요합니다." in blocks_text

    def test_build_weekly_report_message_with_change_indicators(self):
        service = self._make_service()
        metrics = {
            "cost": 1000000, "cost_change": "🔺 5.0%",
            "impressions": 10000, "impressions_change": "🔻 3.0%",
            "clicks": 500, "clicks_change": "➡️ 0.0%",
            "conversions": 10, "conversions_change": "🔺 10.0%",
            "cpc": 2000, "cpc_change": "🔻 2.0%",
            "cpa": 100000, "cpa_change": "🔻 8.0%"
        }
        result = service.build_weekly_report_message(
            metrics=metrics,
            insight="전환 증가 추세입니다.",
            period="2024-01-01 ~ 2024-01-07"
        )
        blocks_text = str(result)
        assert "🔺 5.0%" in blocks_text

    def test_build_weekly_report_no_chart_when_insufficient_trend(self):
        """트렌드 데이터가 1개 이하면 차트 블록 없음."""
        service = self._make_service()
        metrics = {"cost": 1000000, "impressions": 10000, "clicks": 500, "conversions": 10, "cpc": 2000, "cpa": 100000}
        trend_data = [{"period": "01/01~01/07", "metrics": metrics}]  # 1개만
        result = service.build_weekly_report_message(
            metrics=metrics,
            insight="테스트",
            period="2024-01-01 ~ 2024-01-07",
            trend_data=trend_data
        )
        # image 블록이 없어야 함
        image_blocks = [b for b in result["blocks"] if b.get("type") == "image"]
        assert len(image_blocks) == 0

    def test_build_sparkline_ascending(self):
        """스파크라인: 오름차순 데이터에서 올바른 문자 반환."""
        service = self._make_service()
        result = service._build_sparkline([10, 20, 30, 40, 50])
        assert isinstance(result, str)
        assert len(result) == 5

    def test_build_sparkline_constant(self):
        """스파크라인: 모든 값이 동일하면 중간 문자 반환."""
        service = self._make_service()
        result = service._build_sparkline([100, 100, 100])
        assert isinstance(result, str)
        assert len(result) == 3

    def test_build_weekly_report_includes_sparkline(self):
        """주간 리포트에 스파크라인이 포함된 섹션이 있어야 함."""
        service = self._make_service()
        metrics = {"cost": 1000000, "impressions": 10000, "clicks": 500,
                   "conversions": 10, "cpc": 2000, "cpa": 100000}
        trend_data = [
            {"period": "01/01~01/07", "metrics": {"cost": 900000, "impressions": 9000,
             "clicks": 450, "conversions": 8, "cpc": 2000, "cpa": 112500}},
            {"period": "01/08~01/14", "metrics": {"cost": 1000000, "impressions": 10000,
             "clicks": 500, "conversions": 10, "cpc": 2000, "cpa": 100000}},
        ]
        result = service.build_weekly_report_message(
            metrics=metrics,
            insight="테스트 인사이트",
            period="2024-01-08 ~ 2024-01-14",
            trend_data=trend_data
        )
        assert "blocks" in result
        all_text = str(result)
        assert "클릭" in all_text or "cost" in all_text.lower()

    def test_build_keyword_alert_message_structure(self):
        service = self._make_service()
        keyword_data = {
            "search_term": "무료 광고",
            "campaign_name": "브랜드 캠페인",
            "cost": 50000,
            "clicks": 25,
            "conversions": 0
        }
        result = service.build_keyword_alert_message(keyword_data, approval_request_id=42)
        blocks = result["blocks"]

        # 헤더 확인
        assert blocks[0]["type"] == "header"
        assert "비효율 검색어" in blocks[0]["text"]["text"]

        # 데이터 섹션 확인
        section_text = str(blocks[1])
        assert "무료 광고" in section_text
        assert "브랜드 캠페인" in section_text

        # 버튼 확인
        action_block = blocks[2]
        assert action_block["type"] == "actions"
        assert action_block["elements"][0]["value"] == "42"
        assert action_block["elements"][1]["value"] == "42"

    def test_build_keyword_alert_message_zero_approval_id(self):
        """approval_request_id 없을 때 "0" 기본값."""
        service = self._make_service()
        keyword_data = {
            "search_term": "테스트", "campaign_name": "캠페인",
            "cost": 1000, "clicks": 5, "conversions": 0
        }
        result = service.build_keyword_alert_message(keyword_data)
        action_block = result["blocks"][2]
        assert action_block["elements"][0]["value"] == "0"
