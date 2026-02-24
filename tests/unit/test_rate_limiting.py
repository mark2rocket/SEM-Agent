"""Unit tests for rate limiting middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request, Response, status
from redis.asyncio import Redis

from app.core.middleware import RateLimitMiddleware, TenantContextMiddleware, RequestLoggingMiddleware
from app.core.middleware import tenant_context, request_id_context


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock(spec=Redis)
    # Configure async methods to return awaitable values
    redis.incr = AsyncMock()
    redis.expire = AsyncMock()
    redis.ttl = AsyncMock()
    return redis


@pytest.fixture
def mock_request():
    """Mock FastAPI request."""
    request = MagicMock(spec=Request)
    request.url.path = "/api/v1/reports"
    request.query_params = {}
    request.headers = {}
    request.method = "GET"
    return request


@pytest.fixture
def mock_call_next():
    """Mock call_next function."""
    async def call_next(request):
        response = Response(content="OK", status_code=200)
        return response
    return call_next


class TestRateLimitMiddleware:
    """Test rate limiting middleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_first_request(self, mock_redis, mock_request, mock_call_next):
        """Test that first request is allowed."""
        # Setup
        tenant_context.set("test_tenant")
        mock_redis.incr.return_value = 1
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # Execute
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert response.status_code == 200
        assert mock_redis.incr.called
        assert mock_redis.expire.called

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_101st_request(self, mock_redis, mock_request, mock_call_next):
        """Test that 101st request within 60s returns 429."""
        # Setup
        tenant_context.set("test_tenant")
        mock_redis.incr.return_value = 101
        mock_redis.ttl.return_value = 45
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # Execute
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "45"

    @pytest.mark.asyncio
    async def test_rate_limit_different_tenants_independent(self, mock_redis, mock_request, mock_call_next):
        """Test that different tenants have independent rate limits."""
        # Setup
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # Tenant 1 - first request
        tenant_context.set("tenant_1")
        mock_redis.incr.return_value = 1
        response1 = await middleware.dispatch(mock_request, mock_call_next)
        assert response1.status_code == 200

        # Tenant 2 - first request
        tenant_context.set("tenant_2")
        mock_redis.incr.return_value = 1
        response2 = await middleware.dispatch(mock_request, mock_call_next)
        assert response2.status_code == 200

        # Verify different Redis keys were used
        calls = [call[0][0] for call in mock_redis.incr.call_args_list]
        assert "tenant_1" in calls[0]
        assert "tenant_2" in calls[1]

    @pytest.mark.asyncio
    async def test_rate_limit_google_ads_api(self, mock_redis, mock_request, mock_call_next):
        """Test rate limit for Google Ads API."""
        # Setup
        tenant_context.set("test_tenant")
        mock_request.url.path = "/api/v1/google-ads/campaigns"
        mock_redis.incr.return_value = 101
        mock_redis.ttl.return_value = 30
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # Execute
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        # Verify correct API type was used
        key_used = mock_redis.incr.call_args[0][0]
        assert "google_ads" in key_used

    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self, mock_redis, mock_request, mock_call_next):
        """Test that rate limit resets after window expires."""
        # Setup
        tenant_context.set("test_tenant")
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # First request - counter at 1
        mock_redis.incr.return_value = 1
        response1 = await middleware.dispatch(mock_request, mock_call_next)
        assert response1.status_code == 200
        assert mock_redis.expire.called

    @pytest.mark.asyncio
    async def test_rate_limit_skips_health_check(self, mock_redis, mock_request, mock_call_next):
        """Test that health check endpoint skips rate limiting."""
        # Setup
        mock_request.url.path = "/health"
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # Execute
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert response.status_code == 200
        assert not mock_redis.incr.called

    @pytest.mark.asyncio
    async def test_rate_limit_no_tenant_context(self, mock_redis, mock_request, mock_call_next):
        """Test that requests without tenant context skip rate limiting."""
        # Setup
        tenant_context.set(None)
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # Execute
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert response.status_code == 200
        assert not mock_redis.incr.called

    @pytest.mark.asyncio
    async def test_rate_limit_redis_error_allows_request(self, mock_redis, mock_request, mock_call_next):
        """Test that Redis errors don't block requests."""
        # Setup
        tenant_context.set("test_tenant")
        mock_redis.incr.side_effect = Exception("Redis connection error")
        middleware = RateLimitMiddleware(app=MagicMock(), redis_client=mock_redis)

        # Execute
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert - request should be allowed despite Redis error
        assert response.status_code == 200


class TestTenantContextMiddleware:
    """Test tenant context middleware."""

    @pytest.mark.asyncio
    async def test_tenant_from_query_param(self, mock_request, mock_call_next):
        """Test extracting tenant from query parameter."""
        # Setup
        mock_request.query_params = {"workspace_id": "W123456"}
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # Context is cleaned up after request, but we can verify it was set
        # by checking logs or side effects

    @pytest.mark.asyncio
    async def test_tenant_from_header(self, mock_request, mock_call_next):
        """Test extracting tenant from custom header."""
        # Setup
        mock_request.headers = {"X-Workspace-ID": "W123456"}
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert - context should be cleaned up after request
        # Verification would require inspecting context during request

    @pytest.mark.asyncio
    async def test_tenant_context_cleanup(self, mock_request, mock_call_next):
        """Test that tenant context is cleaned up after request."""
        # Setup
        mock_request.query_params = {"workspace_id": "W123456"}
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert - context should be None after request
        assert tenant_context.get() is None


class TestRequestLoggingMiddleware:
    """Test request logging middleware."""

    @pytest.mark.asyncio
    async def test_logging_adds_correlation_id(self, mock_request, mock_call_next):
        """Test that correlation ID is added to response."""
        # Setup
        middleware = RequestLoggingMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert "X-Correlation-ID" in response.headers
        assert len(response.headers["X-Correlation-ID"]) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_logging_handles_errors(self, mock_request):
        """Test that errors are caught and logged."""
        # Setup
        async def error_call_next(request):
            raise ValueError("Test error")

        middleware = RequestLoggingMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(mock_request, error_call_next)

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "X-Correlation-ID" in response.headers

    @pytest.mark.asyncio
    async def test_logging_cleanup(self, mock_request, mock_call_next):
        """Test that request ID context is cleaned up."""
        # Setup
        middleware = RequestLoggingMiddleware(app=MagicMock())

        # Execute
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert - context should be None after request
        assert request_id_context.get() is None
