"""FastAPI application entry point."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from .config import settings
from .core.security import init_token_encryption
from .models import Base
from .core.database import engine
from .core.middleware import RateLimitMiddleware, TenantContextMiddleware, RequestLoggingMiddleware
from .core.exceptions import register_exception_handlers

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SEM-Agent API",
    description="Slack bot for Google Ads management with AI-powered insights",
    version="1.0.0",
    debug=settings.debug
)

# Register exception handlers
register_exception_handlers(app)

# Initialize Redis client for rate limiting
redis_client = None

# Add middleware (order matters: logging → tenant → rate limit → CORS)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TenantContextMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    global redis_client
    logger.info("Starting SEM-Agent API...")

    # Initialize Redis client for rate limiting
    redis_client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True
    )
    logger.info("Redis client initialized")

    # Add rate limit middleware with Redis client
    app.add_middleware(RateLimitMiddleware, redis_client=redis_client)
    logger.info("Rate limit middleware registered")

    # Initialize token encryption
    init_token_encryption(settings.token_encryption_key)
    logger.info("Token encryption initialized")

    # Create database tables (in production, use Alembic migrations)
    if settings.is_development:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created")

    logger.info("SEM-Agent API started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global redis_client
    logger.info("Shutting down SEM-Agent API...")

    # Close Redis connection
    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "SEM-Agent API",
        "version": "1.0.0",
        "docs": "/docs"
    }


# Register API routers
from .api.endpoints import slack, oauth
from .api.endpoints.health import router as health_router
from .api.endpoints.reports import router as reports_router
from .api.endpoints.keywords import router as keywords_router
from .core.metrics import metrics_router

app.include_router(health_router, tags=["health"])
app.include_router(slack.router, prefix="/slack", tags=["slack"])
app.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
app.include_router(reports_router, prefix="/api/v1", tags=["reports"])
app.include_router(keywords_router, prefix="/api/v1", tags=["keywords"])
app.include_router(metrics_router, tags=["monitoring"])
