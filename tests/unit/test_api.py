"""Unit tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import json

from app.main import app


# Note: client fixture is provided by conftest.py
# No need to redefine it here


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check(self, client):
        """Test /health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "environment" in data

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert data["version"] == "1.0.0"


class TestSlackEndpoints:
    """Test Slack API endpoints."""

    def test_slack_url_verification(self, client):
        """Test Slack URL verification challenge."""
        payload = {
            "type": "url_verification",
            "challenge": "test_challenge_123"
        }

        # Mock signature verification
        with patch('app.api.endpoints.slack.verify_slack_signature', return_value=True):
            response = client.post(
                "/slack/events",
                json=payload,
                headers={
                    "X-Slack-Request-Timestamp": "1234567890",
                    "X-Slack-Signature": "v0=test_signature"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["challenge"] == "test_challenge_123"

    def test_slack_events_invalid_signature(self, client):
        """Test that invalid signature is rejected."""
        payload = {"type": "event_callback"}

        # Mock signature verification to return False
        with patch('app.api.endpoints.slack.verify_slack_signature', return_value=False):
            response = client.post(
                "/slack/events",
                json=payload,
                headers={
                    "X-Slack-Request-Timestamp": "1234567890",
                    "X-Slack-Signature": "v0=invalid"
                }
            )

        assert response.status_code == 403


class TestOAuthEndpoints:
    """Test OAuth endpoints."""

    def test_google_oauth_authorize(self, client, db):
        """Test Google OAuth authorize endpoint initialization."""
        # Test that endpoint is registered and requires tenant_id
        response = client.get("/oauth/google/authorize")

        # Should return 422 for missing tenant_id parameter
        assert response.status_code == 422
        assert "tenant_id" in response.text

    @patch('app.api.endpoints.oauth._create_flow')
    @patch('app.api.endpoints.oauth.redis_client')
    @patch('app.api.endpoints.oauth.encrypt_token')
    def test_google_oauth_callback(self, mock_encrypt_token, mock_redis_client, mock_create_flow, client, db):
        """Test Google OAuth callback endpoint."""
        # Mock redis_client async methods
        mock_redis_client.get = AsyncMock(return_value="1")
        mock_redis_client.delete = AsyncMock(return_value=1)

        # Mock encrypt_token
        mock_encrypt_token.side_effect = lambda x: f"encrypted_{x}"

        # Mock the Flow object
        mock_flow = Mock()
        mock_credentials = Mock()
        mock_credentials.refresh_token = "test_refresh_token"
        mock_credentials.token = "test_access_token"
        mock_credentials.expiry = None
        mock_flow.fetch_token.return_value = None
        mock_flow.credentials = mock_credentials
        mock_create_flow.return_value = mock_flow

        response = client.get("/oauth/google/callback?code=test_code&state=1:test_state_token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


class TestAPIDocumentation:
    """Test API documentation endpoints."""

    def test_openapi_schema(self, client):
        """Test OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == "SEM-Agent API"

    def test_docs_endpoint(self, client):
        """Test /docs endpoint is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
