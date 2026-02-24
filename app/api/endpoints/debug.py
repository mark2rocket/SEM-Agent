"""Debug endpoints for troubleshooting."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from ...api.deps import get_db
from ...models.tenant import Tenant
from ...models.oauth import OAuthToken
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


@router.post("/create-google-ads-account/{tenant_id}")
async def create_google_ads_account(
    tenant_id: int,
    customer_id: str,
    account_name: str = "Main Account",
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Manually create a GoogleAdsAccount record (for debugging/fixing).

    Example: POST /debug/create-google-ads-account/1?customer_id=4565370415&account_name=My%20Account
    """

    # Check if tenant exists
    tenant = db.query(Tenant).filter_by(id=tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

    # Check if account already exists
    existing = db.query(GoogleAdsAccount).filter_by(
        tenant_id=tenant_id,
        customer_id=customer_id
    ).first()

    if existing:
        return {
            "status": "already_exists",
            "account": {
                "id": existing.id,
                "customer_id": existing.customer_id,
                "account_name": existing.account_name,
                "is_active": existing.is_active,
            }
        }

    # Create new account
    new_account = GoogleAdsAccount(
        tenant_id=tenant_id,
        customer_id=customer_id,
        account_name=account_name,
        is_active=True
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)

    return {
        "status": "created",
        "account": {
            "id": new_account.id,
            "customer_id": new_account.customer_id,
            "account_name": new_account.account_name,
            "is_active": new_account.is_active,
            "created_at": new_account.created_at.isoformat(),
        }
    }
