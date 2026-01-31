from pydantic import BaseModel
from datetime import date
from typing import Optional


class ReportRequest(BaseModel):
    tenant_id: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    report_type: str = "weekly"  # weekly, monthly, custom


class ReportResponse(BaseModel):
    report_id: int
    tenant_id: int
    period: str
    metrics: dict
    insight: str
    created_at: str
