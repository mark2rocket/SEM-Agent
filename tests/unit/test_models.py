"""Unit tests for database models."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base, Tenant, User, OAuthToken, OAuthProvider,
    GoogleAdsAccount, PerformanceThreshold,
    ReportSchedule, ReportHistory, ReportFrequency,
    KeywordCandidate, ApprovalRequest, KeywordStatus
)


@pytest.fixture(scope="function")
def db_session():
    """Create test database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


class TestTenantModel:
    """Test Tenant model."""

    def test_create_tenant(self, db_session):
        """Test creating a tenant."""
        tenant = Tenant(
            workspace_id="T12345",
            workspace_name="Test Workspace",
            is_active=True
        )
        db_session.add(tenant)
        db_session.commit()

        assert tenant.id is not None
        assert tenant.workspace_id == "T12345"
        assert tenant.is_active is True

    def test_tenant_relationships(self, db_session):
        """Test tenant relationships with users and oauth tokens."""
        tenant = Tenant(
            workspace_id="T12345",
            workspace_name="Test Workspace"
        )
        db_session.add(tenant)
        db_session.commit()

        # Add user
        user = User(
            tenant_id=tenant.id,
            slack_user_id="U12345",
            email="test@example.com"
        )
        db_session.add(user)

        # Add OAuth token
        token = OAuthToken(
            tenant_id=tenant.id,
            provider=OAuthProvider.GOOGLE,
            access_token="encrypted_token",
            refresh_token="encrypted_refresh"
        )
        db_session.add(token)
        db_session.commit()

        assert len(tenant.users) == 1
        assert len(tenant.oauth_tokens) == 1


class TestReportSchedule:
    """Test ReportSchedule model."""

    def test_create_weekly_schedule(self, db_session):
        """Test creating weekly report schedule."""
        tenant = Tenant(workspace_id="T12345", workspace_name="Test")
        db_session.add(tenant)
        db_session.commit()

        from datetime import time
        schedule = ReportSchedule(
            tenant_id=tenant.id,
            frequency=ReportFrequency.WEEKLY,
            day_of_week=0,  # Monday
            time_of_day=time(9, 0),
            timezone="Asia/Seoul"
        )
        db_session.add(schedule)
        db_session.commit()

        assert schedule.frequency == ReportFrequency.WEEKLY
        assert schedule.day_of_week == 0
        assert schedule.timezone == "Asia/Seoul"


class TestKeywordCandidate:
    """Test KeywordCandidate model."""

    def test_create_keyword_candidate(self, db_session):
        """Test creating keyword candidate."""
        tenant = Tenant(workspace_id="T12345", workspace_name="Test")
        db_session.add(tenant)
        db_session.commit()

        keyword = KeywordCandidate(
            tenant_id=tenant.id,
            campaign_id="C12345",
            campaign_name="Test Campaign",
            search_term="free download",
            cost=15000.0,
            clicks=25,
            conversions=0,
            status=KeywordStatus.PENDING
        )
        db_session.add(keyword)
        db_session.commit()

        assert keyword.id is not None
        assert keyword.search_term == "free download"
        assert keyword.conversions == 0
        assert keyword.status == KeywordStatus.PENDING

    def test_keyword_with_approval_request(self, db_session):
        """Test keyword with approval request relationship."""
        tenant = Tenant(workspace_id="T12345", workspace_name="Test")
        db_session.add(tenant)
        db_session.commit()

        keyword = KeywordCandidate(
            tenant_id=tenant.id,
            campaign_id="C12345",
            campaign_name="Test Campaign",
            search_term="test keyword",
            cost=10000.0,
            clicks=10,
            conversions=0
        )
        db_session.add(keyword)
        db_session.commit()

        expires_at = datetime.utcnow() + timedelta(hours=24)
        approval = ApprovalRequest(
            keyword_candidate_id=keyword.id,
            slack_message_ts="1234567890.123456",
            expires_at=expires_at
        )
        db_session.add(approval)
        db_session.commit()

        assert keyword.approval_request is not None
        assert keyword.approval_request.slack_message_ts == "1234567890.123456"


class TestGoogleAdsAccount:
    """Test GoogleAdsAccount model."""

    def test_create_google_ads_account(self, db_session):
        """Test creating Google Ads account."""
        tenant = Tenant(workspace_id="T12345", workspace_name="Test")
        db_session.add(tenant)
        db_session.commit()

        account = GoogleAdsAccount(
            tenant_id=tenant.id,
            customer_id="1234567890",
            account_name="Test Account",
            currency="KRW",
            timezone="Asia/Seoul"
        )
        db_session.add(account)
        db_session.commit()

        assert account.customer_id == "1234567890"
        assert account.currency == "KRW"
        assert account.is_active is True
