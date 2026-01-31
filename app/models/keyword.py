"""Keyword candidate and approval models."""

from sqlalchemy import String, Integer, DateTime, Float, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
import enum

from .base import Base


class KeywordStatus(str, enum.Enum):
    """Keyword candidate status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalAction(str, enum.Enum):
    """Approval request action."""
    APPROVE = "approve"
    IGNORE = "ignore"
    EXPIRED = "expired"


class KeywordCandidate(Base):
    """Search terms detected as inefficient."""

    __tablename__ = "keyword_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(String(50))
    campaign_name: Mapped[str] = mapped_column(String(255))
    search_term: Mapped[str] = mapped_column(String(255))
    cost: Mapped[float] = mapped_column(Float)
    clicks: Mapped[int] = mapped_column(Integer)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    status: Mapped[str] = mapped_column(SQLEnum(KeywordStatus), default=KeywordStatus.PENDING)

    # Relationships
    approval_request = relationship("ApprovalRequest", back_populates="keyword_candidate", uselist=False)

    def __repr__(self) -> str:
        return f"<KeywordCandidate(id={self.id}, term='{self.search_term}')>"


class ApprovalRequest(Base):
    """Approval request for keyword exclusion."""

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_candidate_id: Mapped[int] = mapped_column(ForeignKey("keyword_candidates.id"), unique=True, index=True)
    slack_message_ts: Mapped[str] = mapped_column(String(50), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # slack_user_id
    action: Mapped[Optional[str]] = mapped_column(SQLEnum(ApprovalAction), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    # Relationships
    keyword_candidate = relationship("KeywordCandidate", back_populates="approval_request")

    def __repr__(self) -> str:
        return f"<ApprovalRequest(id={self.id}, action={self.action})>"
