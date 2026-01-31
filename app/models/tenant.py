"""Tenant and User models."""

from sqlalchemy import String, Integer, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional

from .base import Base


class Tenant(Base):
    """Slack workspace tenant."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    workspace_name: Mapped[str] = mapped_column(String(255))
    bot_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    slack_channel_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    oauth_tokens = relationship("OAuthToken", back_populates="tenant", cascade="all, delete-orphan")
    google_ads_accounts = relationship("GoogleAdsAccount", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, workspace={self.workspace_name})>"


class User(Base):
    """User within a tenant."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    slack_user_id: Mapped[str] = mapped_column(String(50), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, slack_user={self.slack_user_id})>"
