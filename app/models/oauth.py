"""OAuth token models."""

from sqlalchemy import String, Integer, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
import enum

from .base import Base


class OAuthProvider(str, enum.Enum):
    """OAuth provider types."""
    GOOGLE = "google"
    SLACK = "slack"


class OAuthToken(Base):
    """OAuth tokens for external services."""

    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    provider: Mapped[str] = mapped_column(SQLEnum(OAuthProvider))
    access_token: Mapped[str] = mapped_column(String)  # Encrypted
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Encrypted
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="oauth_tokens")

    def __repr__(self) -> str:
        return f"<OAuthToken(id={self.id}, provider={self.provider})>"
