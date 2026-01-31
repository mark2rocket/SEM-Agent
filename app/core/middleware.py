"""Middleware for rate limiting, tenant resolution, and request logging."""

import logging
import time
import uuid
from typing import Optional, Callable
from contextvars import ContextVar

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..config import settings

logger = logging.getLogger(__name__)

# Context variable for tenant ID
tenant_context: ContextVar[Optional[str]] = ContextVar("tenant_context", default=None)
request_id_context: ContextVar[Optional[str]] = ContextVar("request_id_context", default=None)


def get_current_tenant() -> Optional[str]:
    """Get current tenant ID from context."""
    return tenant_context.get()


def get_current_request_id() -> Optional[str]:
    """Get current request correlation ID from context."""
    return request_id_context.get()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting per tenant per API.

    Implements distributed rate limiting using Redis with the following limits:
    - Google Ads API: 100 requests per minute
    - Slack API: 50 requests per minute
    - Gemini Flash: 60 requests per minute
    - Gemini Pro: 10 requests per minute
    - Default: 100 requests per minute
    """

    LIMITS = {
        "google_ads": {"requests": 100, "window": 60},  # 100/min
        "slack": {"requests": 50, "window": 60},        # 50/min
        "gemini_flash": {"requests": 60, "window": 60}, # 60/min
        "gemini_pro": {"requests": 10, "window": 60},   # 10/min
        "default": {"requests": 100, "window": 60},     # Default 100/min
    }

    def __init__(self, app: ASGIApp, redis_client: Redis):
        super().__init__(app)
        self.redis = redis_client

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limits before processing request."""
        # Skip rate limiting for health check and root
        if request.url.path in ["/health", "/"]:
            return await call_next(request)

        # Extract tenant ID from context (set by TenantContextMiddleware)
        tenant_id = tenant_context.get()
        if not tenant_id:
            # No tenant context, skip rate limiting (will be handled by auth)
            return await call_next(request)

        # Determine API from path
        api = self._get_api_from_path(request.url.path)

        # Check rate limit
        allowed, retry_after = await self.check_rate_limit(tenant_id, api)

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for tenant={tenant_id}, api={api}, "
                f"retry_after={retry_after}s"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "요청 한도를 초과했습니다",
                    "message": f"{retry_after}초 후 다시 시도해주세요",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )

        return await call_next(request)

    def _get_api_from_path(self, path: str) -> str:
        """Determine API type from request path."""
        if "/google-ads" in path or "/ads" in path:
            return "google_ads"
        elif "/slack" in path:
            return "slack"
        elif "/gemini" in path or "/ai" in path:
            # Check if it's a pro model request (could be determined from request body)
            # For now, default to flash
            return "gemini_flash"
        return "default"

    async def check_rate_limit(
        self,
        tenant_id: str,
        api: str
    ) -> tuple[bool, int]:
        """Check if request is within rate limit.

        Uses Redis INCR with expiration for efficient distributed rate limiting.

        Args:
            tenant_id: Tenant identifier
            api: API type (google_ads, slack, etc.)

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        key = f"ratelimit:{tenant_id}:{api}"
        limit = self.LIMITS.get(api, self.LIMITS["default"])

        try:
            # Increment counter
            current = await self.redis.incr(key)

            # Set expiration on first request
            if current == 1:
                await self.redis.expire(key, limit["window"])

            # Check if over limit
            if current > limit["requests"]:
                ttl = await self.redis.ttl(key)
                # TTL returns -1 if key has no expiry, -2 if key doesn't exist
                return False, max(0, ttl) if ttl > 0 else limit["window"]

            return True, 0
        except Exception as e:
            # On Redis error, allow request but log error
            logger.error(f"Rate limit check failed: {e}")
            return True, 0


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extract tenant context from request and set for request lifecycle.

    Tenant can be identified from:
    1. workspace_id query parameter (for Slack callbacks)
    2. X-Workspace-ID header
    3. JWT token (future implementation)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Extract and set tenant context."""
        tenant_id = None

        # Try to extract tenant from query params (Slack OAuth)
        if "workspace_id" in request.query_params:
            tenant_id = request.query_params["workspace_id"]
        # Try to extract from custom header
        elif "X-Workspace-ID" in request.headers:
            tenant_id = request.headers["X-Workspace-ID"]
        # Try to extract from Slack team_id in body (for Slack events)
        elif request.url.path.startswith("/slack"):
            # Will be set by Slack event handler
            pass

        # Set tenant context
        if tenant_id:
            tenant_context.set(tenant_id)
            logger.debug(f"Tenant context set: {tenant_id}")

        try:
            response = await call_next(request)
            return response
        finally:
            # Clean up context
            tenant_context.set(None)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request and response details with correlation ID.

    Logs:
    - Request method, path, tenant_id, correlation_id
    - Response status code and duration
    - Errors with stack traces
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response."""
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        request_id_context.set(correlation_id)

        # Start timer
        start_time = time.time()

        # Get tenant from context (set by TenantContextMiddleware)
        tenant_id = tenant_context.get()

        # Log request
        logger.info(
            f"Request started: method={request.method} path={request.url.path} "
            f"tenant={tenant_id or 'anonymous'} correlation_id={correlation_id}"
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            logger.info(
                f"Request completed: method={request.method} path={request.url.path} "
                f"status={response.status_code} duration_ms={duration_ms:.2f} "
                f"tenant={tenant_id or 'anonymous'} correlation_id={correlation_id}"
            )

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                f"Request failed: method={request.method} path={request.url.path} "
                f"duration_ms={duration_ms:.2f} tenant={tenant_id or 'anonymous'} "
                f"correlation_id={correlation_id} error={str(e)}",
                exc_info=True
            )

            # Return error response
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "내부 서버 오류가 발생했습니다",
                    "correlation_id": correlation_id
                },
                headers={"X-Correlation-ID": correlation_id}
            )
        finally:
            # Clean up context
            request_id_context.set(None)


async def get_redis_client() -> Redis:
    """Create Redis client for middleware."""
    return Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True
    )
