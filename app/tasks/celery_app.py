"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from ..config import settings

# Create Celery application
celery_app = Celery(
    "sem_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Configure Celery
celery_app.conf.update(
    timezone=settings.celery_timezone,
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "generate-scheduled-reports": {
        "task": "app.tasks.report_tasks.generate_scheduled_reports",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "detect-inefficient-keywords": {
        "task": "app.tasks.keyword_tasks.detect_inefficient_keywords",
        "schedule": crontab(minute="0"),  # Every hour
    },
    "expire-approval-requests": {
        "task": "app.tasks.keyword_tasks.check_approval_expirations",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
    },
    "refresh-expired-tokens": {
        "task": "app.tasks.maintenance_tasks.refresh_expired_tokens",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
}
