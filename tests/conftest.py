"""Pytest configuration and fixtures."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Set test environment variables BEFORE importing app
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SLACK_CLIENT_ID", "test_slack_client_id")
os.environ.setdefault("SLACK_CLIENT_SECRET", "test_slack_client_secret")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test_slack_signing_secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test_google_client_id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test_google_client_secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/google/callback")
os.environ.setdefault("GOOGLE_DEVELOPER_TOKEN", "test_developer_token")
os.environ.setdefault("GOOGLE_LOGIN_CUSTOMER_ID", "1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_api_key")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "test_encryption_key_32_bytes_long!")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_jwt_signing")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from app.models import Base
from app.core.database import get_db


# Test database URL (use in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Create test client with mocked middleware."""
    # Import app after setting up environment
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.core.middleware import TenantContextMiddleware, RequestLoggingMiddleware
    from app.core.exceptions import register_exception_handlers

    # Create a clean test app without RateLimitMiddleware
    test_app = FastAPI(
        title="SEM-Agent API",
        description="Slack bot for Google Ads management with AI-powered insights",
        version="1.0.0",
        debug=True
    )

    # Register exception handlers
    register_exception_handlers(test_app)

    # Add middleware (without RateLimitMiddleware)
    test_app.add_middleware(RequestLoggingMiddleware)
    test_app.add_middleware(TenantContextMiddleware)
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    from app.api.endpoints import slack, oauth
    from app.api.endpoints.health import router as health_router
    from app.api.endpoints.reports import router as reports_router
    from app.api.endpoints.keywords import router as keywords_router
    from app.core.metrics import metrics_router

    # Add root endpoint
    @test_app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "SEM-Agent API",
            "version": "1.0.0",
            "docs": "/docs"
        }

    test_app.include_router(health_router, tags=["health"])
    test_app.include_router(slack.router, prefix="/slack", tags=["slack"])
    test_app.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
    test_app.include_router(reports_router, tags=["reports"])
    test_app.include_router(keywords_router, tags=["keywords"])
    test_app.include_router(metrics_router, tags=["monitoring"])

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()
