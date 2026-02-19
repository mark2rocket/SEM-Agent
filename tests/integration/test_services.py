"""Integration tests for services."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import date, datetime, timedelta

from app.services.slack_service import SlackService
from app.services.gemini_service import GeminiService, RateLimiter
from app.services.google_ads_service import GoogleAdsService


class TestSlackService:
    """Test SlackService integration."""

    def test_slack_service_initialization(self):
        """Test SlackService can be initialized."""
        service = SlackService(bot_token="xoxb-test-token")
        assert service.client is not None

    def test_build_weekly_report_message(self):
        """Test building weekly report message."""
        service = SlackService(bot_token="xoxb-test-token")

        metrics = {
            "cost": 1000000,
            "conversions": 50,
            "roas": 350
        }
        insight = "성과가 개선되었습니다."
        period = "2024-01-01 ~ 2024-01-07"

        message = service.build_weekly_report_message(metrics, insight, period)

        assert "blocks" in message
        assert len(message["blocks"]) > 0
        # Check header exists
        assert message["blocks"][0]["type"] == "header"

    def test_build_keyword_alert_message(self):
        """Test building keyword alert message."""
        service = SlackService(bot_token="xoxb-test-token")

        keyword_data = {
            "search_term": "무료 다운로드",
            "campaign_name": "브랜드 캠페인",
            "cost": 15000,
            "clicks": 25,
            "conversions": 0
        }

        message = service.build_keyword_alert_message(keyword_data)

        assert "blocks" in message
        assert len(message["blocks"]) > 0


class TestGeminiService:
    """Test GeminiService integration."""

    def test_rate_limiter(self):
        """Test rate limiter functionality."""
        limiter = RateLimiter(max_requests=2, time_window=1)

        # First two requests should pass
        assert limiter.can_proceed()
        limiter.add_request()
        assert limiter.can_proceed()
        limiter.add_request()

        # Third request should be blocked
        assert not limiter.can_proceed()

    def test_gemini_service_initialization(self):
        """Test GeminiService can be initialized."""
        service = GeminiService(
            api_key="test_api_key",
            model_name="gemini-1.5-flash"
        )
        assert service.model is not None
        assert service.rate_limiter is not None

    @patch('app.services.gemini_service.genai.GenerativeModel')
    def test_generate_report_insight(self, mock_model):
        """Test generating report insight."""
        # Mock Gemini API response
        mock_response = Mock()
        mock_response.text = "전반적으로 성과가 개선되었습니다."
        mock_model_instance = Mock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_model.return_value = mock_model_instance

        service = GeminiService(api_key="test_key")
        service.model = mock_model_instance

        metrics = {
            "cost": 1000000,
            "conversions": 50,
            "roas": 350
        }

        insight = service.generate_report_insight(metrics)

        assert isinstance(insight, str)
        assert len(insight) > 0


"""Tests for service layer - Updated for REST API implementation."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date

from app.services.google_ads_service import GoogleAdsService


class TestGoogleAdsService:
    """Test GoogleAdsService with REST API implementation."""

    def test_google_ads_service_initialization(self):
        """Test GoogleAdsService can be initialized."""
        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token",
            login_customer_id="1234567890"
        )

        assert service.developer_token == "test_dev_token"
        assert service.client_id == "test_client_id"
        assert service.login_customer_id == "1234567890"

    @patch('app.services.google_ads_service.requests.post')
    def test_get_access_token(self, mock_post):
        """Test access token refresh."""
        # Mock token response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        token = service._get_access_token()

        assert token == "test_access_token"
        assert mock_post.called

    @patch.object(GoogleAdsService, '_call_search_stream')
    def test_get_performance_metrics(self, mock_search):
        """Test get_performance_metrics returns expected structure."""
        # Mock search response
        mock_search.return_value = [
            {
                "metrics": {
                    "costMicros": "1000000",  # $1
                    "conversions": "5.0",
                    "conversionsValue": "100.0",
                    "clicks": "10",
                    "impressions": "100"
                }
            }
        ]

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        metrics = service.get_performance_metrics(
            customer_id="1234567890",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 7)
        )

        assert isinstance(metrics, dict)
        assert metrics["cost"] == 1.0
        assert metrics["conversions"] == 5.0
        assert metrics["clicks"] == 10
        assert metrics["impressions"] == 100

    @patch.object(GoogleAdsService, '_call_search_stream')
    def test_get_search_terms(self, mock_search):
        """Test get_search_terms returns expected structure."""
        # Mock search response
        mock_search.return_value = [
            {
                "searchTermView": {"searchTerm": "test keyword"},
                "campaign": {"id": "12345", "name": "Test Campaign"},
                "metrics": {
                    "costMicros": "500000",  # $0.5
                    "clicks": "5",
                    "conversions": "1.0"
                }
            }
        ]

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        terms = service.get_search_terms(
            customer_id="1234567890",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 7)
        )

        assert isinstance(terms, list)
        assert len(terms) == 1
        assert terms[0]["search_term"] == "test keyword"
        assert terms[0]["cost"] == 0.5

    @patch.object(GoogleAdsService, '_call_search_stream')
    def test_list_campaigns(self, mock_search):
        """Test list_campaigns returns expected structure."""
        # Mock search response
        mock_search.return_value = [
            {
                "campaign": {
                    "id": "12345",
                    "name": "Test Campaign",
                    "status": "ENABLED"
                }
            }
        ]

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        campaigns = service.list_campaigns(customer_id="1234567890")

        assert isinstance(campaigns, list)
        assert len(campaigns) == 1
        assert campaigns[0]["id"] == "12345"
        assert campaigns[0]["name"] == "Test Campaign"
        assert campaigns[0]["status"] == "ENABLED"

    @patch('app.services.google_ads_service.requests.post')
    @patch.object(GoogleAdsService, '_get_access_token')
    def test_add_negative_keyword(self, mock_token, mock_post):
        """Test add_negative_keyword returns success."""
        # Mock access token
        mock_token.return_value = "test_access_token"

        # Mock mutate response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{
                "resourceName": "customers/1234567890/campaignCriteria/12345~67890"
            }]
        }
        mock_post.return_value = mock_response

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        result = service.add_negative_keyword(
            customer_id="1234567890",
            campaign_id="12345",
            keyword_text="test keyword",
            match_type="EXACT"
        )

        assert result is True
        assert mock_post.called
