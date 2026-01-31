"""Report management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from ...schemas.report import ReportRequest, ReportResponse
from ...models.report import ReportHistory
from ...services.report_service import ReportService
from ...services.google_ads_service import GoogleAdsService
from ...services.gemini_service import GeminiService
from ...services.slack_service import SlackService
from ..deps import get_db

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def get_report_service(db: Session = Depends(get_db)) -> ReportService:
    """
    Dependency for ReportService with injected dependencies.

    Args:
        db: Database session

    Returns:
        ReportService instance
    """
    google_ads_service = GoogleAdsService(db)
    gemini_service = GeminiService()
    slack_service = SlackService()

    return ReportService(
        db=db,
        google_ads_service=google_ads_service,
        gemini_service=gemini_service,
        slack_service=slack_service
    )


@router.post("/generate", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    request: ReportRequest,
    report_service: ReportService = Depends(get_report_service)
):
    """
    Generate ad-hoc performance report.

    Args:
        request: Report generation request
        report_service: ReportService instance

    Returns:
        ReportResponse with generated report details

    Raises:
        HTTPException: If report generation fails
    """
    try:
        result = report_service.generate_weekly_report(tenant_id=request.tenant_id)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to generate report")
            )

        return ReportResponse(
            report_id=result["report_id"],
            tenant_id=request.tenant_id,
            period=result["period"],
            metrics=result["metrics"],
            insight="",  # Insight is stored in DB, not returned in this response
            created_at=datetime.utcnow().isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """
    Get report by ID.

    Args:
        report_id: Report ID
        db: Database session

    Returns:
        ReportResponse with report details

    Raises:
        HTTPException: If report not found
    """
    report = db.query(ReportHistory).filter(ReportHistory.id == report_id).first()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )

    return ReportResponse(
        report_id=report.id,
        tenant_id=report.tenant_id,
        period=f"{report.period_start.date()} ~ {report.period_end.date()}",
        metrics=report.metrics or {},
        insight=report.gemini_insight or "",
        created_at=report.created_at.isoformat()
    )


@router.get("", response_model=List[ReportResponse])
async def list_reports(
    tenant_id: int,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List reports for tenant.

    Args:
        tenant_id: Tenant ID
        limit: Maximum number of reports to return
        offset: Number of reports to skip
        db: Database session

    Returns:
        List of ReportResponse
    """
    reports = (
        db.query(ReportHistory)
        .filter(ReportHistory.tenant_id == tenant_id)
        .order_by(ReportHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [
        ReportResponse(
            report_id=report.id,
            tenant_id=report.tenant_id,
            period=f"{report.period_start.date()} ~ {report.period_end.date()}",
            metrics=report.metrics or {},
            insight=report.gemini_insight or "",
            created_at=report.created_at.isoformat()
        )
        for report in reports
    ]
