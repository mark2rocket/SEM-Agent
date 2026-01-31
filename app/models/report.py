"""Report scheduling and history models."""

from sqlalchemy import String, Integer, DateTime, Boolean, JSON, Enum as SQLEnum, Time, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, time
from typing import Optional
import enum

from .base import Base


class ReportFrequency(str, enum.Enum):
    """Report frequency options."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    DISABLED = "disabled"


class ReportSchedule(Base):
    """Report scheduling configuration."""

    __tablename__ = "report_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True, index=True)
    frequency: Mapped[str] = mapped_column(SQLEnum(ReportFrequency), default=ReportFrequency.WEEKLY)
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0=Monday, 6=Sunday
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-31
    time_of_day: Mapped[time] = mapped_column(Time, default=time(9, 0))  # Default 09:00
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Seoul")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<ReportSchedule(tenant_id={self.tenant_id}, frequency={self.frequency})>"


class ReportHistory(Base):
    """History of generated reports."""

    __tablename__ = "report_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(50))  # daily, weekly, monthly
    period_start: Mapped[datetime] = mapped_column(DateTime)
    period_end: Mapped[datetime] = mapped_column(DateTime)
    slack_message_ts: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    gemini_insight: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<ReportHistory(id={self.id}, type={self.report_type})>"
