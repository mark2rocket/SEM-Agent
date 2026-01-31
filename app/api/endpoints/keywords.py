"""Keyword management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

from ...schemas.keyword import (
    KeywordCandidateResponse,
    ApprovalRequest as ApprovalRequestSchema,
    ApprovalResponse
)
from ...models.keyword import KeywordCandidate, ApprovalRequest, KeywordStatus
from ...services.keyword_service import KeywordService
from ...services.google_ads_service import GoogleAdsService
from ...services.slack_service import SlackService
from ..deps import get_db

router = APIRouter(prefix="/api/v1", tags=["keywords"])


def get_keyword_service(db: Session = Depends(get_db)) -> KeywordService:
    """
    Dependency for KeywordService with injected dependencies.

    Args:
        db: Database session

    Returns:
        KeywordService instance
    """
    google_ads_service = GoogleAdsService(db)
    slack_service = SlackService()

    return KeywordService(
        db=db,
        google_ads_service=google_ads_service,
        slack_service=slack_service
    )


@router.get("/keywords", response_model=List[KeywordCandidateResponse])
async def list_keywords(
    tenant_id: int,
    status_filter: str = Query(None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List keyword candidates for tenant.

    Args:
        tenant_id: Tenant ID
        status_filter: Filter by status (pending, approved, rejected, expired)
        limit: Maximum number of keywords to return
        offset: Number of keywords to skip
        db: Database session

    Returns:
        List of KeywordCandidateResponse
    """
    query = db.query(KeywordCandidate).filter(KeywordCandidate.tenant_id == tenant_id)

    # Apply status filter if provided
    if status_filter:
        try:
            status_enum = KeywordStatus(status_filter)
            query = query.filter(KeywordCandidate.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: pending, approved, rejected, expired"
            )

    keywords = (
        query
        .order_by(KeywordCandidate.detected_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [
        KeywordCandidateResponse(
            id=kw.id,
            search_term=kw.search_term,
            campaign_name=kw.campaign_name,
            cost=kw.cost,
            clicks=kw.clicks,
            conversions=kw.conversions,
            status=kw.status,
            detected_at=kw.detected_at
        )
        for kw in keywords
    ]


@router.get("/keywords/{keyword_id}", response_model=KeywordCandidateResponse)
async def get_keyword(
    keyword_id: int,
    db: Session = Depends(get_db)
):
    """
    Get keyword details by ID.

    Args:
        keyword_id: Keyword candidate ID
        db: Database session

    Returns:
        KeywordCandidateResponse

    Raises:
        HTTPException: If keyword not found
    """
    keyword = db.query(KeywordCandidate).filter(KeywordCandidate.id == keyword_id).first()

    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Keyword {keyword_id} not found"
        )

    return KeywordCandidateResponse(
        id=keyword.id,
        search_term=keyword.search_term,
        campaign_name=keyword.campaign_name,
        cost=keyword.cost,
        clicks=keyword.clicks,
        conversions=keyword.conversions,
        status=keyword.status,
        detected_at=keyword.detected_at
    )


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_keyword(
    approval_id: int,
    slack_user_id: str = Query(..., description="Slack user ID who approved"),
    keyword_service: KeywordService = Depends(get_keyword_service),
    db: Session = Depends(get_db)
):
    """
    Approve keyword exclusion and add as negative keyword.

    Args:
        approval_id: Approval request ID
        slack_user_id: Slack user ID performing the approval
        keyword_service: KeywordService instance
        db: Database session

    Returns:
        ApprovalResponse with updated approval details

    Raises:
        HTTPException: If approval fails
    """
    success = keyword_service.approve_keyword(
        approval_request_id=approval_id,
        slack_user_id=slack_user_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to approve keyword. Request may be expired, already responded, or not found."
        )

    # Fetch updated approval request
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()

    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request {approval_id} not found"
        )

    return ApprovalResponse(
        id=approval.id,
        keyword_candidate_id=approval.keyword_candidate_id,
        status="approved",
        slack_message_ts=approval.slack_message_ts,
        requested_at=approval.requested_at,
        expires_at=approval.expires_at,
        responded_at=approval.responded_at,
        approved_by=approval.approved_by
    )


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_keyword(
    approval_id: int,
    slack_user_id: str = Query(..., description="Slack user ID who rejected"),
    db: Session = Depends(get_db)
):
    """
    Reject keyword exclusion request.

    Args:
        approval_id: Approval request ID
        slack_user_id: Slack user ID performing the rejection
        db: Database session

    Returns:
        ApprovalResponse with updated approval details

    Raises:
        HTTPException: If approval request not found or already responded
    """
    from datetime import datetime
    from ...models.keyword import ApprovalAction

    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()

    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request {approval_id} not found"
        )

    # Check if already responded
    if approval.responded_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval request already responded to"
        )

    # Check if expired
    if approval.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval request has expired"
        )

    # Update approval request
    approval.responded_at = datetime.utcnow()
    approval.approved_by = slack_user_id
    approval.action = ApprovalAction.IGNORE

    # Update keyword candidate status
    keyword = approval.keyword_candidate
    keyword.status = KeywordStatus.REJECTED

    db.commit()
    db.refresh(approval)

    return ApprovalResponse(
        id=approval.id,
        keyword_candidate_id=approval.keyword_candidate_id,
        status="rejected",
        slack_message_ts=approval.slack_message_ts,
        requested_at=approval.requested_at,
        expires_at=approval.expires_at,
        responded_at=approval.responded_at,
        approved_by=approval.approved_by
    )
