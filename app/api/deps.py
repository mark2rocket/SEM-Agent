"""Dependency injection for FastAPI endpoints."""

from typing import Generator
from sqlalchemy.orm import Session

from ..core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency for FastAPI.

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
