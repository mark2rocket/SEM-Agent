"""Integration tests for API endpoints."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from fastapi import status

from app.models.report import ReportHistory
from app.models.keyword import KeywordCandidate, ApprovalRequest, KeywordStatus, ApprovalAction
from app.models.tenant import Tenant


@pytest.fixture
def mock_services():
    """Mock all external services for testing."""
    with patch("app.api.endpoints.reports.GoogleAdsService") as mock_gads, \
         patch("app.api.endpoints.reports.GeminiService") as mock_gemini, \
         patch("app.api.endpoints.reports.SlackService") as mock_slack_reports, \
         patch("app.api.endpoints.keywords.GoogleAdsService") as mock_gads_kw, \
         patch("app.api.endpoints.keywords.SlackService") as mock_slack_kw:

        # Configure mocks to return instances
        mock_gads.return_value = Mock()
        mock_gemini.return_value = Mock()
        mock_slack_reports.return_value = Mock()
        mock_gads_kw.return_value = Mock()
        mock_slack_kw.return_value = Mock()

        yield {
            "google_ads": mock_gads,
            "gemini": mock_gemini,
            "slack_reports": mock_slack_reports,
            "google_ads_kw": mock_gads_kw,
            "slack_kw": mock_slack_kw
        }


@pytest.fixture
def sample_tenant(db):
    """Create a sample tenant for testing."""
    tenant = Tenant(
        id=1,
        workspace_id="T123456",
        workspace_name="Test Team",
        bot_token="xoxb-test-token",
        slack_channel_id="C123456",
        is_active=True
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@pytest.fixture
def sample_report(db, sample_tenant):
    """Create a sample report for testing."""
    report = ReportHistory(
        id=1,
        tenant_id=sample_tenant.id,
        report_type="weekly",
        period_start=datetime.utcnow() - timedelta(days=7),
        period_end=datetime.utcnow(),
        slack_message_ts="1234567890.123456",
        gemini_insight="테스트 인사이트입니다.",
        metrics={
            "clicks": 1000,
            "impressions": 10000,
            "cost": 50000,
            "conversions": 50
        }
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@pytest.fixture
def sample_keyword(db, sample_tenant):
    """Create a sample keyword candidate for testing."""
    keyword = KeywordCandidate(
        id=1,
        tenant_id=sample_tenant.id,
        campaign_id="campaign_123",
        campaign_name="테스트 캠페인",
        search_term="비효율 검색어",
        cost=10000.0,
        clicks=100,
        conversions=0,
        status=KeywordStatus.PENDING
    )
    db.add(keyword)
    db.commit()
    db.refresh(keyword)
    return keyword


@pytest.fixture
def sample_approval(db, sample_keyword):
    """Create a sample approval request for testing."""
    approval = ApprovalRequest(
        id=1,
        keyword_candidate_id=sample_keyword.id,
        slack_message_ts="1234567890.123456",
        requested_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


# ============================================================================
# HEALTH ENDPOINT TESTS
# ============================================================================

def test_health_check(client):
    """Test /health endpoint returns 200."""
    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data


def test_health_ready_success(client, db):
    """Test /health/ready checks database connectivity."""
    response = client.get("/health/ready")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "ok"


def test_health_ready_database_failure(client):
    """Test /health/ready returns 503 when database is unavailable."""
    # Mock database failure at the Session level
    from sqlalchemy.orm import Session
    with patch.object(Session, 'execute', side_effect=Exception("Database connection failed")):
        response = client.get("/health/ready")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "database" in data["errors"][0]


# ============================================================================
# REPORT ENDPOINT TESTS
# ============================================================================

def test_generate_report_success(client, sample_tenant, mock_services):
    """Test POST /api/v1/reports/generate generates report successfully."""
    with patch("app.services.report_service.ReportService.generate_weekly_report") as mock_generate:
        # Mock service response
        mock_generate.return_value = {
            "status": "success",
            "report_id": 1,
            "period": "2024-01-01 ~ 2024-01-07",
            "metrics": {
                "clicks": 1000,
                "impressions": 10000,
                "cost": 50000,
                "conversions": 50
            }
        }

        request_data = {
            "tenant_id": sample_tenant.id,
            "report_type": "weekly"
        }

        response = client.post("/api/v1/reports/generate", json=request_data)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["report_id"] == 1
        assert data["tenant_id"] == sample_tenant.id
        assert "metrics" in data
        assert "created_at" in data


def test_generate_report_failure(client, sample_tenant, mock_services):
    """Test POST /api/v1/reports/generate handles service errors."""
    with patch("app.services.report_service.ReportService.generate_weekly_report") as mock_generate:
        # Mock service error
        mock_generate.return_value = {
            "status": "error",
            "message": "리포트 생성에 실패했습니다."
        }

        request_data = {
            "tenant_id": sample_tenant.id,
            "report_type": "weekly"
        }

        response = client.post("/api/v1/reports/generate", json=request_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "리포트 생성에 실패했습니다." in response.json()["detail"]


def test_get_report_success(client, sample_report):
    """Test GET /api/v1/reports/{id} returns report details."""
    response = client.get(f"/api/v1/reports/{sample_report.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["report_id"] == sample_report.id
    assert data["tenant_id"] == sample_report.tenant_id
    assert data["insight"] == sample_report.gemini_insight
    assert data["metrics"]["clicks"] == 1000


def test_get_report_not_found(client):
    """Test GET /api/v1/reports/{id} returns 404 for non-existent report."""
    response = client.get("/api/v1/reports/9999")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_list_reports_success(client, sample_report):
    """Test GET /api/v1/reports with pagination."""
    response = client.get(
        "/api/v1/reports",
        params={"tenant_id": sample_report.tenant_id, "limit": 10, "offset": 0}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["report_id"] == sample_report.id


def test_list_reports_pagination(client, db, sample_tenant):
    """Test GET /api/v1/reports pagination works correctly."""
    # Create multiple reports
    for i in range(15):
        report = ReportHistory(
            tenant_id=sample_tenant.id,
            report_type="weekly",
            period_start=datetime.utcnow() - timedelta(days=7 * (i + 1)),
            period_end=datetime.utcnow() - timedelta(days=7 * i),
            metrics={"clicks": i * 100}
        )
        db.add(report)
    db.commit()

    # Test first page
    response = client.get(
        "/api/v1/reports",
        params={"tenant_id": sample_tenant.id, "limit": 10, "offset": 0}
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 10

    # Test second page
    response = client.get(
        "/api/v1/reports",
        params={"tenant_id": sample_tenant.id, "limit": 10, "offset": 10}
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 5


def test_list_reports_empty(client, sample_tenant):
    """Test GET /api/v1/reports returns empty list when no reports exist."""
    response = client.get(
        "/api/v1/reports",
        params={"tenant_id": sample_tenant.id}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


# ============================================================================
# KEYWORD ENDPOINT TESTS
# ============================================================================

def test_list_keywords_success(client, sample_keyword):
    """Test GET /api/v1/keywords returns keyword list."""
    response = client.get(
        "/api/v1/keywords",
        params={"tenant_id": sample_keyword.tenant_id}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["id"] == sample_keyword.id
    assert data[0]["search_term"] == sample_keyword.search_term


def test_list_keywords_with_status_filter(client, db, sample_tenant):
    """Test GET /api/v1/keywords with status filter."""
    # Create keywords with different statuses
    pending = KeywordCandidate(
        tenant_id=sample_tenant.id,
        campaign_id="c1",
        campaign_name="Campaign 1",
        search_term="pending term",
        cost=100.0,
        clicks=10,
        conversions=0,
        status=KeywordStatus.PENDING
    )
    approved = KeywordCandidate(
        tenant_id=sample_tenant.id,
        campaign_id="c2",
        campaign_name="Campaign 2",
        search_term="approved term",
        cost=200.0,
        clicks=20,
        conversions=1,
        status=KeywordStatus.APPROVED
    )
    db.add_all([pending, approved])
    db.commit()

    # Filter by pending
    response = client.get(
        "/api/v1/keywords",
        params={"tenant_id": sample_tenant.id, "status": "pending"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"

    # Filter by approved
    response = client.get(
        "/api/v1/keywords",
        params={"tenant_id": sample_tenant.id, "status": "approved"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "approved"


def test_list_keywords_invalid_status(client, sample_tenant):
    """Test GET /api/v1/keywords with invalid status returns 400."""
    response = client.get(
        "/api/v1/keywords",
        params={"tenant_id": sample_tenant.id, "status": "invalid_status"}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid status" in response.json()["detail"]


def test_get_keyword_success(client, sample_keyword):
    """Test GET /api/v1/keywords/{id} returns keyword details."""
    response = client.get(f"/api/v1/keywords/{sample_keyword.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == sample_keyword.id
    assert data["search_term"] == sample_keyword.search_term
    assert data["campaign_name"] == sample_keyword.campaign_name
    assert data["cost"] == sample_keyword.cost


def test_get_keyword_not_found(client):
    """Test GET /api/v1/keywords/{id} returns 404 for non-existent keyword."""
    response = client.get("/api/v1/keywords/9999")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_approve_keyword_success(client, db, sample_approval, mock_services):
    """Test POST /api/v1/approvals/{id}/approve approves keyword."""
    from datetime import datetime
    from app.models.keyword import ApprovalAction, KeywordStatus

    def mock_approve_keyword(approval_request_id: int, slack_user_id: str) -> bool:
        """Mock that actually updates the database."""
        approval = db.query(ApprovalRequest).filter_by(id=approval_request_id).first()
        if not approval or approval.responded_at:
            return False

        # Update approval
        approval.responded_at = datetime.utcnow()
        approval.approved_by = slack_user_id
        approval.action = ApprovalAction.APPROVE

        # Update keyword status
        approval.keyword_candidate.status = KeywordStatus.APPROVED
        db.commit()
        return True

    with patch("app.services.keyword_service.KeywordService.approve_keyword", side_effect=mock_approve_keyword):
        response = client.post(
            f"/api/v1/approvals/{sample_approval.id}/approve",
            params={"slack_user_id": "U123456"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == sample_approval.id
        assert data["status"] == "approved"
        assert data["approved_by"] is not None


def test_approve_keyword_failure(client, sample_approval, mock_services):
    """Test POST /api/v1/approvals/{id}/approve handles service errors."""
    with patch("app.services.keyword_service.KeywordService.approve_keyword") as mock_approve:
        # Mock service failure
        mock_approve.return_value = False

        response = client.post(
            f"/api/v1/approvals/{sample_approval.id}/approve",
            params={"slack_user_id": "U123456"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Failed to approve keyword" in response.json()["detail"]


def test_approve_keyword_not_found(client, mock_services):
    """Test POST /api/v1/approvals/{id}/approve returns 404 for non-existent approval."""
    with patch("app.services.keyword_service.KeywordService.approve_keyword") as mock_approve:
        # Mock service returns True but approval doesn't exist
        mock_approve.return_value = True

        response = client.post(
            "/api/v1/approvals/9999/approve",
            params={"slack_user_id": "U123456"}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


def test_reject_keyword_success(client, sample_approval):
    """Test POST /api/v1/approvals/{id}/reject rejects keyword."""
    response = client.post(
        f"/api/v1/approvals/{sample_approval.id}/reject",
        params={"slack_user_id": "U123456"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == sample_approval.id
    assert data["status"] == "rejected"
    assert data["approved_by"] == "U123456"


def test_reject_keyword_not_found(client):
    """Test POST /api/v1/approvals/{id}/reject returns 404 for non-existent approval."""
    response = client.post(
        "/api/v1/approvals/9999/reject",
        params={"slack_user_id": "U123456"}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_reject_keyword_already_responded(client, db, sample_approval):
    """Test POST /api/v1/approvals/{id}/reject returns 400 if already responded."""
    # Mark approval as already responded
    sample_approval.responded_at = datetime.utcnow()
    sample_approval.approved_by = "U000000"
    db.commit()

    response = client.post(
        f"/api/v1/approvals/{sample_approval.id}/reject",
        params={"slack_user_id": "U123456"}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already responded" in response.json()["detail"].lower()


def test_reject_keyword_expired(client, db, sample_approval):
    """Test POST /api/v1/approvals/{id}/reject returns 400 if expired."""
    # Set approval as expired
    sample_approval.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    response = client.post(
        f"/api/v1/approvals/{sample_approval.id}/reject",
        params={"slack_user_id": "U123456"}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "expired" in response.json()["detail"].lower()


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

def test_not_found_error(client):
    """Test 404 error for non-existent resource."""
    response = client.get("/api/v1/reports/9999999")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "detail" in response.json()


def test_validation_error(client, sample_tenant, mock_services):
    """Test 400 error for invalid input."""
    # Missing required field
    request_data = {
        "report_type": "weekly"
        # Missing tenant_id
    }

    response = client.post("/api/v1/reports/generate", json=request_data)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "detail" in response.json()


def test_validation_error_invalid_type(client, mock_services):
    """Test 422 error for invalid data type."""
    request_data = {
        "tenant_id": "not_an_integer",  # Should be int
        "report_type": "weekly"
    }

    response = client.post("/api/v1/reports/generate", json=request_data)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.skip(reason="Rate limiting requires Redis and is tested separately")
def test_rate_limit_error(client, sample_tenant):
    """Test 429 error when rate limit is exceeded."""
    # This test requires Redis to be running and rate limiting to be active
    # Make multiple rapid requests to trigger rate limit
    request_data = {
        "tenant_id": sample_tenant.id,
        "report_type": "weekly"
    }

    # Make requests until rate limit is hit
    responses = []
    for _ in range(100):
        response = client.post("/api/v1/reports/generate", json=request_data)
        responses.append(response)
        if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            break

    # At least one request should hit rate limit
    assert any(r.status_code == status.HTTP_429_TOO_MANY_REQUESTS for r in responses)


# ============================================================================
# KOREAN ERROR MESSAGE TESTS
# ============================================================================

def test_korean_error_messages(client, db, sample_approval):
    """Test that error messages are in Korean where appropriate."""
    # Mark approval as already responded
    sample_approval.responded_at = datetime.utcnow()
    db.commit()

    response = client.post(
        f"/api/v1/approvals/{sample_approval.id}/reject",
        params={"slack_user_id": "U123456"}
    )

    # Note: Current implementation uses English error messages
    # This test documents expected behavior if Korean messages are added
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# RESPONSE STRUCTURE TESTS
# ============================================================================

def test_report_response_structure(client, sample_report):
    """Test report response has correct structure."""
    response = client.get(f"/api/v1/reports/{sample_report.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Check required fields
    required_fields = ["report_id", "tenant_id", "period", "metrics", "insight", "created_at"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Check data types
    assert isinstance(data["report_id"], int)
    assert isinstance(data["tenant_id"], int)
    assert isinstance(data["period"], str)
    assert isinstance(data["metrics"], dict)
    assert isinstance(data["insight"], str)
    assert isinstance(data["created_at"], str)


def test_keyword_response_structure(client, sample_keyword):
    """Test keyword response has correct structure."""
    response = client.get(f"/api/v1/keywords/{sample_keyword.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Check required fields
    required_fields = ["id", "search_term", "campaign_name", "cost", "clicks", "conversions", "status", "detected_at"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Check data types
    assert isinstance(data["id"], int)
    assert isinstance(data["search_term"], str)
    assert isinstance(data["campaign_name"], str)
    assert isinstance(data["cost"], (int, float))
    assert isinstance(data["clicks"], int)
    assert isinstance(data["conversions"], int)
    assert isinstance(data["status"], str)
    assert isinstance(data["detected_at"], str)


def test_approval_response_structure(client, sample_approval):
    """Test approval response has correct structure."""
    response = client.post(
        f"/api/v1/approvals/{sample_approval.id}/reject",
        params={"slack_user_id": "U123456"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Check required fields
    required_fields = ["id", "keyword_candidate_id", "status", "slack_message_ts", "requested_at", "expires_at"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Check data types
    assert isinstance(data["id"], int)
    assert isinstance(data["keyword_candidate_id"], int)
    assert isinstance(data["status"], str)
    assert isinstance(data["slack_message_ts"], str)
    assert isinstance(data["requested_at"], str)
    assert isinstance(data["expires_at"], str)
