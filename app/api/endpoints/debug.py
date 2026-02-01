"""Debug endpoints for troubleshooting."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any

from ...api.deps import get_db
from ...models.tenant import Tenant
from ...models.oauth import OAuthToken, OAuthProvider
from ...models.google_ads import GoogleAdsAccount

router = APIRouter()


@router.get("/check-state/{tenant_id}")
async def check_state(tenant_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Check database state for a tenant (for debugging)."""

    # Get tenant
    tenant = db.query(Tenant).filter_by(id=tenant_id).first()

    # Get OAuth tokens
    oauth_tokens = db.query(OAuthToken).filter_by(tenant_id=tenant_id).all()

    # Get Google Ads accounts
    google_ads_accounts = db.query(GoogleAdsAccount).filter_by(tenant_id=tenant_id).all()

    return {
        "tenant": {
            "id": tenant.id if tenant else None,
            "workspace_id": tenant.workspace_id if tenant else None,
            "channel_id": tenant.slack_channel_id if tenant else None,
        } if tenant else None,
        "oauth_tokens": [
            {
                "id": token.id,
                "provider": token.provider.value,
                "has_refresh_token": bool(token.refresh_token),
                "created_at": token.created_at.isoformat() if token.created_at else None,
            }
            for token in oauth_tokens
        ],
        "google_ads_accounts": [
            {
                "id": acc.id,
                "customer_id": acc.customer_id,
                "account_name": acc.account_name,
                "is_active": acc.is_active,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
            }
            for acc in google_ads_accounts
        ],
    }
