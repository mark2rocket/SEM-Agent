from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class KeywordCandidateResponse(BaseModel):
    id: int
    search_term: str
    campaign_name: str
    cost: float
    clicks: int
    conversions: int
    status: str
    detected_at: datetime


class ApprovalRequest(BaseModel):
    keyword_candidate_id: int


class ApprovalResponse(BaseModel):
    id: int
    keyword_candidate_id: int
    status: str
    slack_message_ts: str
    requested_at: datetime
    expires_at: datetime
    responded_at: Optional[datetime] = None
    approved_by: Optional[str] = None
