from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class SlackEvent(BaseModel):
    type: str
    event_ts: str
    user: Optional[str] = None
    channel: Optional[str] = None
    text: Optional[str] = None


class SlackCommand(BaseModel):
    command: str
    text: str
    user_id: str
    channel_id: str
    response_url: str
    trigger_id: str


class SlackInteraction(BaseModel):
    type: str
    user: Dict[str, Any]
    actions: List[Dict[str, Any]]
    response_url: str
    message: Optional[Dict[str, Any]] = None
