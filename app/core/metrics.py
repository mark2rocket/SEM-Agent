"""Prometheus metrics for monitoring SEM Agent operations."""

from contextlib import contextmanager
from functools import wraps
from time import time
from typing import Callable, Any, Generator

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from sqlalchemy.orm import Session

from ..models.tenant import Tenant
from ..models.keyword import ApprovalRequest


# =============================================================================
# Counters
# =============================================================================

reports_generated = Counter(
    "sem_reports_generated_total",
    "Total reports generated",
    ["tenant_id", "report_type"],
)

keywords_detected = Counter(
    "sem_keywords_detected_total",
    "Total inefficient keywords detected",
    ["tenant_id"],
)

approvals_processed = Counter(
    "sem_approvals_processed_total",
    "Total approval decisions",
    ["tenant_id", "decision"],  # approved, rejected, expired
)


# =============================================================================
# Histograms
# =============================================================================

report_generation_time = Histogram(
    "sem_report_generation_seconds",
    "Report generation duration",
    ["report_type"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

gemini_latency = Histogram(
    "sem_gemini_latency_seconds",
    "Gemini API response time",
    ["model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

google_ads_api_latency = Histogram(
    "sem_google_ads_api_latency_seconds",
    "Google Ads API response time",
    ["operation"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


# =============================================================================
# Gauges
# =============================================================================

active_tenants = Gauge(
    "sem_active_tenants",
    "Number of active tenants",
)

pending_approvals = Gauge(
    "sem_pending_approvals",
    "Number of pending approval requests",
)


# =============================================================================
# Helper Functions and Decorators
# =============================================================================

def track_report_generation(report_type: str, tenant_id: str) -> None:
    """
    Increment the reports generated counter.

    Args:
        report_type: Type of report (e.g., 'weekly', 'monthly')
        tenant_id: Tenant identifier
    """
    reports_generated.labels(tenant_id=tenant_id, report_type=report_type).inc()


def track_keyword_detection(tenant_id: str, count: int = 1) -> None:
    """
    Increment the keywords detected counter.

    Args:
        tenant_id: Tenant identifier
        count: Number of keywords detected (default: 1)
    """
    keywords_detected.labels(tenant_id=tenant_id).inc(count)


def track_approval_decision(tenant_id: str, decision: str) -> None:
    """
    Increment the approvals processed counter.

    Args:
        tenant_id: Tenant identifier
        decision: Decision made ('approved', 'rejected', 'expired')
    """
    approvals_processed.labels(tenant_id=tenant_id, decision=decision).inc()


@contextmanager
def track_report_generation_time(report_type: str) -> Generator[None, None, None]:
    """
    Context manager to track report generation duration.

    Args:
        report_type: Type of report being generated

    Example:
        with track_report_generation_time("weekly"):
            # Generate report
            pass
    """
    start_time = time()
    try:
        yield
    finally:
        duration = time() - start_time
        report_generation_time.labels(report_type=report_type).observe(duration)


@contextmanager
def track_gemini_latency(model: str) -> Generator[None, None, None]:
    """
    Context manager to track Gemini API latency.

    Args:
        model: Gemini model name

    Example:
        with track_gemini_latency("gemini-2.0-flash-exp"):
            # Call Gemini API
            pass
    """
    start_time = time()
    try:
        yield
    finally:
        duration = time() - start_time
        gemini_latency.labels(model=model).observe(duration)


@contextmanager
def track_google_ads_latency(operation: str) -> Generator[None, None, None]:
    """
    Context manager to track Google Ads API latency.

    Args:
        operation: API operation name (e.g., 'search_keywords', 'update_campaign')

    Example:
        with track_google_ads_latency("search_keywords"):
            # Call Google Ads API
            pass
    """
    start_time = time()
    try:
        yield
    finally:
        duration = time() - start_time
        google_ads_api_latency.labels(operation=operation).observe(duration)


def track_latency(metric: Histogram, label: str) -> Callable:
    """
    Decorator to track function execution time.

    Args:
        metric: Histogram metric to update
        label: Label value for the metric

    Returns:
        Decorator function

    Example:
        @track_latency(gemini_latency, "gemini-2.0-flash-exp")
        async def call_gemini():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time() - start_time
                metric.labels(label).observe(duration)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time() - start_time
                metric.labels(label).observe(duration)

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def update_active_tenants_gauge(db: Session) -> None:
    """
    Update the active tenants gauge with current count.

    Args:
        db: Database session
    """
    count = db.query(Tenant).filter(Tenant.is_active == True).count()
    active_tenants.set(count)


def update_pending_approvals_gauge(db: Session) -> None:
    """
    Update the pending approvals gauge with current count.

    Args:
        db: Database session
    """
    from datetime import datetime
    count = db.query(ApprovalRequest).filter(
        ApprovalRequest.responded_at.is_(None),
        ApprovalRequest.expires_at > datetime.utcnow()
    ).count()
    pending_approvals.set(count)


def update_all_gauges(db: Session) -> None:
    """
    Update all gauge metrics with current values.

    Args:
        db: Database session
    """
    update_active_tenants_gauge(db)
    update_pending_approvals_gauge(db)


# =============================================================================
# FastAPI Endpoint
# =============================================================================

from fastapi import APIRouter

metrics_router = APIRouter()


@metrics_router.get("/metrics")
def get_metrics() -> Response:
    """
    FastAPI endpoint to expose Prometheus metrics.

    Returns:
        Response with Prometheus metrics in text format

    Example:
        from fastapi import APIRouter
        router = APIRouter()
        router.add_api_route("/metrics", get_metrics, methods=["GET"])
    """
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
