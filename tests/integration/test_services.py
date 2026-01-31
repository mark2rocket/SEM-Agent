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


@patch('app.services.google_ads_service.GoogleAdsClient')
class TestGoogleAdsService:
    """Test GoogleAdsService integration."""

    def test_google_ads_service_initialization(self, mock_google_ads_client):
        """Test GoogleAdsService can be initialized."""
        # Mock the GoogleAdsClient.load_from_dict to return a mock client
        mock_client = Mock()
        mock_google_ads_client.load_from_dict.return_value = mock_client

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )
        assert service.client is not None

    def test_get_performance_metrics_stub(self, mock_google_ads_client):
        """Test get_performance_metrics returns expected structure."""
        # Mock the GoogleAdsClient.load_from_dict to return a mock client
        mock_client = Mock()
        mock_google_ads_client.load_from_dict.return_value = mock_client

        # Mock the Google Ads API service and query response
        mock_ga_service = Mock()
        mock_client.get_service.return_value = mock_ga_service

        # Mock query response with empty results
        mock_ga_service.search.return_value = []

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        # Should return metrics with zero values when no data
        metrics = service.get_performance_metrics(
            customer_id="1234567890",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 7)
        )

        assert isinstance(metrics, dict)
        assert "cost" in metrics
        assert "conversions" in metrics
        assert "roas" in metrics

    def test_get_search_terms_stub(self, mock_google_ads_client):
        """Test get_search_terms returns expected structure."""
        # Mock the GoogleAdsClient.load_from_dict to return a mock client
        mock_client = Mock()
        mock_google_ads_client.load_from_dict.return_value = mock_client

        # Mock the GoogleAdsService to return empty iterator
        mock_ga_service = Mock()
        mock_ga_service.search.return_value = []  # Empty list is iterable
        mock_client.get_service.return_value = mock_ga_service

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        # Should return empty list with mocked response
        terms = service.get_search_terms(
            customer_id="1234567890",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 7)
        )

        assert isinstance(terms, list)
        assert len(terms) == 0

    def test_add_negative_keyword_stub(self, mock_google_ads_client):
        """Test add_negative_keyword returns success."""
        # Mock the GoogleAdsClient.load_from_dict to return a mock client
        mock_client = Mock()
        mock_google_ads_client.load_from_dict.return_value = mock_client

        # Mock the services needed for adding negative keywords
        mock_campaign_criterion_service = Mock()
        mock_campaign_service = Mock()
        mock_campaign_service.campaign_path.return_value = "customers/1234567890/campaigns/C12345"

        # Mock the response from mutate_campaign_criteria
        mock_result = Mock()
        mock_result.resource_name = "customers/1234567890/campaignCriteria/12345~67890"
        mock_response = Mock()
        mock_response.results = [mock_result]
        mock_campaign_criterion_service.mutate_campaign_criteria.return_value = mock_response

        # Mock get_service to return appropriate services
        def get_service_side_effect(service_name):
            if service_name == "CampaignCriterionService":
                return mock_campaign_criterion_service
            elif service_name == "CampaignService":
                return mock_campaign_service
            return Mock()

        mock_client.get_service.side_effect = get_service_side_effect

        # Mock get_type for operation
        mock_operation = Mock()
        mock_operation.create = Mock()
        mock_operation.create.campaign = None
        mock_operation.create.negative = False
        mock_operation.create.keyword = Mock()
        mock_operation.create.keyword.text = ""
        mock_operation.create.keyword.match_type = None
        mock_client.get_type.return_value = mock_operation

        # Mock enums
        mock_keyword_match_type_enum = Mock()
        mock_keyword_match_type_enum.EXACT = 2
        mock_client.enums.KeywordMatchTypeEnum = mock_keyword_match_type_enum

        service = GoogleAdsService(
            developer_token="test_dev_token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )

        # Should return True with mocked successful response
        result = service.add_negative_keyword(
            customer_id="1234567890",
            campaign_id="C12345",
            keyword_text="free download"
        )

        assert result is True
        mock_campaign_criterion_service.mutate_campaign_criteria.assert_called_once()


class TestReportService:
    """Test ReportService integration."""

    @patch('app.services.slack_service.SlackService')
    @patch('app.services.gemini_service.GeminiService')
    @patch('app.services.google_ads_service.GoogleAdsService')
    def test_generate_weekly_report_full_workflow(self, mock_google_ads, mock_gemini, mock_slack, db):
        """Test complete weekly report generation workflow."""
        from app.services.report_service import ReportService
        from app.models.tenant import Tenant
        from app.models.google_ads import GoogleAdsAccount
        from app.models.report import ReportHistory
        from datetime import date

        # 1. Setup test data in database
        tenant = Tenant(
            workspace_id="T12345",
            workspace_name="Test Workspace",
            bot_token="xoxb-test-token",
            slack_channel_id="C12345"
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        google_ads_account = GoogleAdsAccount(
            tenant_id=tenant.id,
            customer_id="1234567890",
            account_name="Test Account",
            is_active=True
        )
        db.add(google_ads_account)
        db.commit()

        # 2. Mock Google Ads API response
        mock_ads_instance = mock_google_ads.return_value
        mock_ads_instance.get_performance_metrics.return_value = {
            "cost": 1500000,
            "conversions": 75,
            "roas": 420,
            "impressions": 50000,
            "clicks": 2500
        }

        # 3. Mock Gemini AI response
        mock_gemini_instance = mock_gemini.return_value
        mock_gemini_instance.generate_report_insight.return_value = "지난주 대비 전환율이 15% 상승했습니다."

        # 4. Mock Slack API response
        mock_slack_instance = mock_slack.return_value
        mock_slack_instance.build_weekly_report_message.return_value = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "Weekly Report"}}
            ]
        }
        mock_slack_instance.client.chat_postMessage.return_value = {"ts": "1234567890.123456"}

        # 5. Create service and execute
        service = ReportService(
            db=db,
            google_ads_service=mock_ads_instance,
            gemini_service=mock_gemini_instance,
            slack_service=mock_slack_instance
        )

        result = service.generate_weekly_report(tenant_id=tenant.id)

        # 6. Verify result
        assert result["status"] == "success"
        assert "report_id" in result
        assert "period" in result
        assert "metrics" in result
        assert result["metrics"]["cost"] == 1500000

        # 7. Verify Google Ads was called correctly
        mock_ads_instance.get_performance_metrics.assert_called_once()
        call_args = mock_ads_instance.get_performance_metrics.call_args
        assert call_args.kwargs["customer_id"] == "1234567890"

        # 8. Verify Gemini was called
        mock_gemini_instance.generate_report_insight.assert_called_once()

        # 9. Verify Slack message was sent
        mock_slack_instance.client.chat_postMessage.assert_called_once()
        slack_call = mock_slack_instance.client.chat_postMessage.call_args
        assert slack_call.kwargs["channel"] == "C12345"

        # 10. Verify database record was created
        report = db.query(ReportHistory).filter_by(id=result["report_id"]).first()
        assert report is not None
        assert report.tenant_id == tenant.id
        assert report.report_type == "weekly"
        assert report.slack_message_ts == "1234567890.123456"
        assert report.gemini_insight == "지난주 대비 전환율이 15% 상승했습니다."
        assert report.metrics["cost"] == 1500000


class TestKeywordService:
    """Test KeywordService integration."""

    @patch('app.services.google_ads_service.GoogleAdsService')
    def test_detect_inefficient_keywords_filters_correctly(self, mock_google_ads, db):
        """Test filtering logic with sample data."""
        from app.services.keyword_service import KeywordService
        from app.models.tenant import Tenant
        from app.models.google_ads import PerformanceThreshold
        from app.models.keyword import KeywordCandidate, KeywordStatus

        # 1. Setup test data
        tenant = Tenant(
            workspace_id="T12345",
            workspace_name="Test Workspace"
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        # Setup custom thresholds
        threshold = PerformanceThreshold(
            tenant_id=tenant.id,
            min_cost_for_detection=15000.0,
            min_clicks_for_detection=10,
            lookback_days=7
        )
        db.add(threshold)
        db.commit()

        # 2. Mock Google Ads search terms response
        mock_ads_instance = mock_google_ads.return_value
        mock_ads_instance.get_search_terms.return_value = [
            # Should be detected: high cost, high clicks, no conversions
            {
                "search_term": "free download",
                "campaign_id": "C001",
                "campaign_name": "Brand Campaign",
                "cost": 20000,
                "clicks": 15,
                "conversions": 0
            },
            # Should NOT be detected: low cost
            {
                "search_term": "buy product",
                "campaign_id": "C001",
                "campaign_name": "Brand Campaign",
                "cost": 5000,
                "clicks": 12,
                "conversions": 0
            },
            # Should NOT be detected: low clicks
            {
                "search_term": "expensive keyword",
                "campaign_id": "C001",
                "campaign_name": "Brand Campaign",
                "cost": 25000,
                "clicks": 3,
                "conversions": 0
            },
            # Should NOT be detected: has conversions
            {
                "search_term": "good keyword",
                "campaign_id": "C001",
                "campaign_name": "Brand Campaign",
                "cost": 30000,
                "clicks": 20,
                "conversions": 5
            },
            # Should be detected: meets all criteria
            {
                "search_term": "무료 체험",
                "campaign_id": "C002",
                "campaign_name": "Product Campaign",
                "cost": 18000,
                "clicks": 12,
                "conversions": 0
            }
        ]

        # 3. Create service and execute
        service = KeywordService(
            db=db,
            google_ads_service=mock_ads_instance,
            slack_service=None
        )

        detected = service.detect_inefficient_keywords(tenant_id=tenant.id)

        # 4. Verify filtering logic
        assert len(detected) == 2
        detected_terms = [k["search_term"] for k in detected]
        assert "free download" in detected_terms
        assert "무료 체험" in detected_terms
        assert "buy product" not in detected_terms
        assert "expensive keyword" not in detected_terms
        assert "good keyword" not in detected_terms

        # 5. Verify database records were created
        candidates = db.query(KeywordCandidate).filter_by(tenant_id=tenant.id).all()
        assert len(candidates) == 2
        assert all(c.status == KeywordStatus.PENDING for c in candidates)
        assert all(c.conversions == 0 for c in candidates)

    @patch('app.services.slack_service.SlackService')
    def test_create_approval_request_workflow(self, mock_slack, db):
        """Test approval request creation and Slack alert."""
        from app.services.keyword_service import KeywordService
        from app.models.tenant import Tenant
        from app.models.keyword import KeywordCandidate, ApprovalRequest
        from datetime import datetime, timedelta

        # 1. Setup test data
        tenant = Tenant(
            workspace_id="T12345",
            workspace_name="Test Workspace"
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        # 2. Mock Slack API response
        mock_slack_instance = mock_slack.return_value
        mock_slack_instance.build_keyword_alert_message.return_value = {
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Alert"}}]
        }
        mock_slack_instance.send_message.return_value = {
            "ts": "1234567890.123456",
            "channel": "C12345"
        }

        # 3. Prepare keyword data
        keyword_data = {
            "search_term": "free software",
            "campaign_id": "C001",
            "campaign_name": "Brand Campaign",
            "cost": 25000,
            "clicks": 20,
            "conversions": 0
        }

        # 4. Create service and execute
        service = KeywordService(
            db=db,
            google_ads_service=None,
            slack_service=mock_slack_instance
        )

        approval_id = service.create_approval_request(
            tenant_id=tenant.id,
            keyword_data=keyword_data
        )

        # 5. Verify approval request was created
        assert approval_id is not None
        approval = db.query(ApprovalRequest).filter_by(id=approval_id).first()
        assert approval is not None
        assert approval.slack_message_ts == "1234567890.123456"
        assert approval.responded_at is None

        # 6. Verify expiration is set correctly (24 hours from now)
        now = datetime.utcnow()
        expected_expiry = now + timedelta(hours=24)
        time_diff = abs((approval.expires_at - expected_expiry).total_seconds())
        assert time_diff < 5  # Within 5 seconds tolerance

        # 7. Verify keyword candidate was created
        keyword = approval.keyword_candidate
        assert keyword is not None
        assert keyword.search_term == "free software"
        assert keyword.campaign_id == "C001"
        assert keyword.cost == 25000
        assert keyword.clicks == 20

        # 8. Verify Slack message was sent with approval_request_id
        # The second argument is the approval_request_id (approval.id)
        mock_slack_instance.build_keyword_alert_message.assert_called_once_with(keyword_data, 1)
        mock_slack_instance.send_message.assert_called_once()

    @patch('app.services.google_ads_service.GoogleAdsService')
    def test_approve_keyword_adds_negative(self, mock_google_ads, db):
        """Test approval workflow and Google Ads integration."""
        from app.services.keyword_service import KeywordService
        from app.models.tenant import Tenant
        from app.models.google_ads import GoogleAdsAccount
        from app.models.keyword import KeywordCandidate, ApprovalRequest, KeywordStatus, ApprovalAction
        from datetime import datetime, timedelta

        # 1. Setup test data
        tenant = Tenant(
            workspace_id="T12345",
            workspace_name="Test Workspace"
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        # Create GoogleAdsAccount
        google_account = GoogleAdsAccount(
            tenant_id=tenant.id,
            customer_id="1234567890",
            account_name="Test Account",
            is_active=True
        )
        db.add(google_account)
        db.commit()

        # Create keyword candidate
        keyword = KeywordCandidate(
            tenant_id=tenant.id,
            campaign_id="C001",
            campaign_name="Brand Campaign",
            search_term="spam keyword",
            cost=30000,
            clicks=25,
            conversions=0,
            status=KeywordStatus.PENDING
        )
        db.add(keyword)
        db.commit()
        db.refresh(keyword)

        # Create approval request
        approval = ApprovalRequest(
            keyword_candidate_id=keyword.id,
            slack_message_ts="1234567890.123456",
            expires_at=datetime.utcnow() + timedelta(hours=12)
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)

        # 2. Mock Google Ads API
        mock_ads_instance = mock_google_ads.return_value
        mock_ads_instance.add_negative_keyword.return_value = True

        # 3. Create service and execute approval
        service = KeywordService(
            db=db,
            google_ads_service=mock_ads_instance,
            slack_service=None
        )

        result = service.approve_keyword(
            approval_request_id=approval.id,
            slack_user_id="U12345"
        )

        # 4. Verify approval succeeded
        assert result is True

        # 5. Verify Google Ads was called correctly
        mock_ads_instance.add_negative_keyword.assert_called_once_with(
            customer_id="1234567890",
            campaign_id="C001",
            keyword_text="spam keyword"
        )

        # 6. Verify approval request was updated
        db.refresh(approval)
        assert approval.responded_at is not None
        assert approval.approved_by == "U12345"
        assert approval.action == ApprovalAction.APPROVE

        # 7. Verify keyword status was updated
        db.refresh(keyword)
        assert keyword.status == KeywordStatus.APPROVED

    @patch('app.services.google_ads_service.GoogleAdsService')
    def test_approve_keyword_rejects_expired_request(self, mock_google_ads, db):
        """Test that expired approval requests are rejected."""
        from app.services.keyword_service import KeywordService
        from app.models.tenant import Tenant
        from app.models.keyword import KeywordCandidate, ApprovalRequest, KeywordStatus
        from datetime import datetime, timedelta

        # 1. Setup test data
        tenant = Tenant(
            workspace_id="T12345",
            workspace_name="Test Workspace"
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        # Create keyword candidate
        keyword = KeywordCandidate(
            tenant_id=tenant.id,
            campaign_id="C001",
            campaign_name="Brand Campaign",
            search_term="expired keyword",
            cost=20000,
            clicks=15,
            conversions=0,
            status=KeywordStatus.PENDING
        )
        db.add(keyword)
        db.commit()
        db.refresh(keyword)

        # Create EXPIRED approval request
        approval = ApprovalRequest(
            keyword_candidate_id=keyword.id,
            slack_message_ts="1234567890.123456",
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)

        # 2. Mock Google Ads API (should NOT be called)
        mock_ads_instance = mock_google_ads.return_value

        # 3. Create service and attempt approval
        service = KeywordService(
            db=db,
            google_ads_service=mock_ads_instance,
            slack_service=None
        )

        result = service.approve_keyword(
            approval_request_id=approval.id,
            slack_user_id="U12345"
        )

        # 4. Verify approval was rejected
        assert result is False

        # 5. Verify Google Ads was NOT called
        mock_ads_instance.add_negative_keyword.assert_not_called()

        # 6. Verify keyword status unchanged
        db.refresh(keyword)
        assert keyword.status == KeywordStatus.PENDING
