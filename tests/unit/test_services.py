"""Unit tests for service modules."""

import pytest
from unittest.mock import Mock
from datetime import date, timedelta

from app.services.keyword_service import KeywordService
from app.services.report_service import ReportService


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
        from datetime import datetime, timedelta

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
