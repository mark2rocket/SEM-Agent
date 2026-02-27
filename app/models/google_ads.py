"""Google Ads account models."""

from sqlalchemy import String, Integer, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional

from .base import Base


class GoogleAdsAccount(Base):
    """Google Ads account linked to tenant."""

    __tablename__ = "google_ads_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[str] = mapped_column(String(50), index=True)
    account_name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="google_ads_accounts")

    def __repr__(self) -> str:
        return f"<GoogleAdsAccount(id={self.id}, customer_id={self.customer_id})>"


class PerformanceThreshold(Base):
    """Performance thresholds for keyword detection."""

    __tablename__ = "performance_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True, index=True)
    min_cost_for_detection: Mapped[float] = mapped_column(Float, default=10000.0)
    min_clicks_for_detection: Mapped[int] = mapped_column(Integer, default=5)
    lookback_days: Mapped[int] = mapped_column(Integer, default=7)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PerformanceThreshold(tenant_id={self.tenant_id})>"


class SearchConsoleAccount(Base):
    """Google Search Console site linked to tenant."""

    __tablename__ = "search_console_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    site_url: Mapped[str] = mapped_column(String(500))
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Encrypted
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="search_console_accounts")

    def __repr__(self) -> str:
        return f"<SearchConsoleAccount(id={self.id}, site_url={self.site_url})>"
