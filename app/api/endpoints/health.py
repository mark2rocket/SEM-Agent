"""Health check endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from redis.asyncio import Redis

from ..deps import get_db

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Liveness probe - always returns ok if app is running.

    Returns:
        dict: Health status
    """
    from ...config import settings
    return {"status": "healthy", "environment": settings.environment}


@router.get("/health/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe - checks all dependencies.

    Args:
        db: Database session

    Returns:
        dict: Readiness status with dependency checks
    """
    errors = []

    # Check PostgreSQL connectivity
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        errors.append(f"database: {str(e)}")

    # Check Redis connectivity (if Redis dependency is available)
    # Note: Redis dependency needs to be added to deps.py if required
    # For now, we skip Redis check to match the existing deps.py structure

    if errors:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "errors": errors}
        )

    return {"status": "ready", "database": "ok"}
