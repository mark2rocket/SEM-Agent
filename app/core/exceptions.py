"""
Custom exception handling for SEM Agent.

This module defines custom exceptions and their handlers for the application,
ensuring all error messages are in Korean and include proper logging/notification.
"""

import uuid
from typing import Optional, Dict, Any
from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Base Exception Classes
# ============================================================================

class SEMAgentException(Exception):
    """Base exception class for all SEM Agent errors."""

    def __init__(
        self,
        message: str,
        message_ko: str,
        status_code: int = 500,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.message_ko = message_ko
        self.status_code = status_code
        self.tenant_id = tenant_id
        self.details = details or {}
        self.correlation_id = str(uuid.uuid4())
        super().__init__(message)


# ============================================================================
# Authentication & Authorization Exceptions
# ============================================================================

class TenantNotFoundError(SEMAgentException):
    """Raised when tenant cannot be found in the system."""

    def __init__(self, tenant_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Tenant not found: {tenant_id}",
            message_ko=f"테넌트를 찾을 수 없습니다: {tenant_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            tenant_id=tenant_id,
            details=details,
        )


class InvalidTokenError(SEMAgentException):
    """Raised when authentication token is invalid or expired."""

    def __init__(self, reason: str = "Invalid or expired token", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=reason,
            message_ko="인증 토큰이 유효하지 않거나 만료되었습니다.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class OAuthError(SEMAgentException):
    """Raised when OAuth authentication fails or expires."""

    def __init__(self, tenant_id: str, provider: str = "Google Ads", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"OAuth error for {provider}",
            message_ko=f"{provider} 연결이 만료되었습니다. [다시 연결]",
            status_code=status.HTTP_401_UNAUTHORIZED,
            tenant_id=tenant_id,
            details=details,
        )


# ============================================================================
# Rate Limiting Exceptions
# ============================================================================

class RateLimitExceededError(SEMAgentException):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        retry_after: int,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"Rate limit exceeded. Retry after {retry_after} seconds",
            message_ko=f"요청이 많습니다. {retry_after}초 후 다시 시도해주세요.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            tenant_id=tenant_id,
            details={**(details or {}), "retry_after": retry_after},
        )
        self.retry_after = retry_after


# ============================================================================
# External API Exceptions
# ============================================================================

class GoogleAdsAPIError(SEMAgentException):
    """Raised when Google Ads API returns an error."""

    def __init__(
        self,
        error_message: str,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"Google Ads API error: {error_message}",
            message_ko="Google Ads에서 응답이 없습니다. 잠시 후 다시 시도해주세요.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            tenant_id=tenant_id,
            details=details,
        )


class SlackAPIError(SEMAgentException):
    """Raised when Slack API returns an error."""

    def __init__(
        self,
        error_message: str,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"Slack API error: {error_message}",
            message_ko="Slack 연동에 문제가 발생했습니다. 잠시 후 다시 시도해주세요.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            tenant_id=tenant_id,
            details=details,
        )


class GeminiError(SEMAgentException):
    """Raised when Gemini AI analysis fails."""

    def __init__(
        self,
        error_message: str,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"Gemini API error: {error_message}",
            message_ko="AI 분석을 수행할 수 없습니다. 다시 시도해주세요.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            tenant_id=tenant_id,
            details=details,
        )


# ============================================================================
# Approval Workflow Exceptions
# ============================================================================

class ApprovalExpiredError(SEMAgentException):
    """Raised when approval request has expired."""

    def __init__(
        self,
        approval_id: str,
        expired_at: str,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"Approval request {approval_id} expired at {expired_at}",
            message_ko="승인 요청이 만료되었습니다. 새로운 요청을 생성해주세요.",
            status_code=status.HTTP_410_GONE,
            tenant_id=tenant_id,
            details={**(details or {}), "approval_id": approval_id, "expired_at": expired_at},
        )


# ============================================================================
# Validation Exceptions
# ============================================================================

class ValidationError(SEMAgentException):
    """Raised when input validation fails."""

    def __init__(self, field: str, reason: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Validation error: {field} - {reason}",
            message_ko=f"입력 값을 확인해주세요: {reason}",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={**(details or {}), "field": field},
        )


class NotFoundError(SEMAgentException):
    """Raised when requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            message_ko="요청한 리소스를 찾을 수 없습니다.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={**(details or {}), "resource_type": resource_type, "resource_id": resource_id},
        )


# ============================================================================
# Exception Handlers
# ============================================================================

async def sem_agent_exception_handler(request: Request, exc: SEMAgentException) -> JSONResponse:
    """
    Generic handler for all SEMAgentException instances.

    Logs the error with correlation ID and returns a JSON response with Korean message.
    """
    logger.error(
        f"[{exc.correlation_id}] {exc.__class__.__name__}: {exc.message}",
        extra={
            "correlation_id": exc.correlation_id,
            "tenant_id": exc.tenant_id,
            "status_code": exc.status_code,
            "details": exc.details,
            "path": request.url.path,
            "method": request.method,
        }
    )

    # For critical errors (5xx), send Slack notification
    if exc.status_code >= 500 and exc.tenant_id:
        try:
            # Import here to avoid circular dependency
            from app.services.slack import slack_service

            await slack_service.send_error_notification(
                tenant_id=exc.tenant_id,
                message=exc.message_ko,
                correlation_id=exc.correlation_id,
                error_details=exc.details,
            )
        except Exception as notification_error:
            logger.error(
                f"Failed to send error notification: {notification_error}",
                extra={"correlation_id": exc.correlation_id}
            )

    response_content = {
        "error": exc.__class__.__name__,
        "message": exc.message_ko,
        "correlation_id": exc.correlation_id,
    }

    # Include details in non-production environments
    if exc.details:
        response_content["details"] = exc.details

    return JSONResponse(
        status_code=exc.status_code,
        content=response_content,
        headers={"X-Correlation-ID": exc.correlation_id}
    )


async def oauth_error_handler(request: Request, exc: OAuthError) -> JSONResponse:
    """
    Specialized handler for OAuth errors.

    Sends Slack notification with reconnection link.
    """
    logger.warning(
        f"[{exc.correlation_id}] OAuth connection expired for tenant {exc.tenant_id}",
        extra={
            "correlation_id": exc.correlation_id,
            "tenant_id": exc.tenant_id,
            "path": request.url.path,
        }
    )

    if exc.tenant_id:
        try:
            from app.services.slack import slack_service
            from app.core.config import settings

            await slack_service.send_error_notification(
                tenant_id=exc.tenant_id,
                message=exc.message_ko,
                action_url=f"{settings.BASE_URL}/oauth/google/connect",
                correlation_id=exc.correlation_id,
            )
        except Exception as notification_error:
            logger.error(
                f"Failed to send OAuth error notification: {notification_error}",
                extra={"correlation_id": exc.correlation_id}
            )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "oauth_expired",
            "message": exc.message_ko,
            "correlation_id": exc.correlation_id,
            "action_required": "reconnect",
        },
        headers={"X-Correlation-ID": exc.correlation_id}
    )


async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
    """
    Specialized handler for rate limit errors.

    Includes Retry-After header.
    """
    logger.warning(
        f"[{exc.correlation_id}] Rate limit exceeded for tenant {exc.tenant_id}",
        extra={
            "correlation_id": exc.correlation_id,
            "tenant_id": exc.tenant_id,
            "retry_after": exc.retry_after,
            "path": request.url.path,
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "rate_limit_exceeded",
            "message": exc.message_ko,
            "correlation_id": exc.correlation_id,
            "retry_after": exc.retry_after,
        },
        headers={
            "X-Correlation-ID": exc.correlation_id,
            "Retry-After": str(exc.retry_after),
        }
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Fallback handler for unhandled exceptions.

    Logs the error and returns a generic error message in Korean.
    """
    correlation_id = str(uuid.uuid4())

    logger.exception(
        f"[{correlation_id}] Unhandled exception: {str(exc)}",
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "method": request.method,
        }
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            "correlation_id": correlation_id,
        },
        headers={"X-Correlation-ID": correlation_id}
    )


# ============================================================================
# Exception Handler Registration
# ============================================================================

def register_exception_handlers(app):
    """
    Register all exception handlers with the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    # Register specific handlers first
    app.add_exception_handler(OAuthError, oauth_error_handler)
    app.add_exception_handler(RateLimitExceededError, rate_limit_error_handler)

    # Register generic handler for all SEMAgentException instances
    app.add_exception_handler(SEMAgentException, sem_agent_exception_handler)

    # Register fallback handler for unhandled exceptions
    app.add_exception_handler(Exception, unhandled_exception_handler)

    logger.info("Exception handlers registered successfully")
