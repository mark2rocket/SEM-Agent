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

# Initialize Redis client for rate limiting (synchronous initialization for middleware)
try:
    redis_client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,  # 5 second connection timeout
        socket_timeout=5,  # 5 second operation timeout
        retry_on_timeout=True,
        health_check_interval=30
    )
    logger.info("Redis client created successfully")
except Exception as e:
    logger.error(f"Failed to create Redis client: {e}")
    raise

# Add middleware (order matters: logging → tenant → rate limit → CORS)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(RateLimitMiddleware, redis_client=redis_client)

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
    try:
        logger.info("Starting SEM-Agent API...")
        logger.info(f"Environment: {settings.environment}")

        # Test Redis connection
        try:
            await redis_client.ping()
            logger.info("Redis connection verified - ready for rate limiting")
        except Exception as e:
            logger.error(f"Redis connection test failed: {e}")
            logger.warning("Continuing without Redis rate limiting")

        # Initialize token encryption
        logger.info("Initializing token encryption...")
        init_token_encryption(settings.token_encryption_key)
        logger.info("Token encryption initialized successfully")

        # Run Alembic migrations
        logger.info("Running database migrations...")
        try:
            from alembic.config import Config
            from alembic import command
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")
            logger.info("Database migrations completed successfully")
        except Exception as e:
            logger.error(f"Failed to run migrations: {e}")
            logger.info("Falling back to create_all...")
            Base.metadata.create_all(bind=engine)

        logger.info("Database tables ready")

        logger.info("✅ SEM-Agent API started successfully")
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise


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
from .api.endpoints import slack, oauth  # noqa: E402
from .api.endpoints.health import router as health_router  # noqa: E402
from .api.endpoints.reports import router as reports_router  # noqa: E402
from .api.endpoints.keywords import router as keywords_router  # noqa: E402
from .api.endpoints.debug import router as debug_router  # noqa: E402
from .core.metrics import metrics_router  # noqa: E402

app.include_router(health_router, tags=["health"])
app.include_router(slack.router, prefix="/slack", tags=["slack"])
app.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
app.include_router(reports_router, prefix="/api/v1", tags=["reports"])
app.include_router(keywords_router, prefix="/api/v1", tags=["keywords"])
app.include_router(debug_router, prefix="/debug", tags=["debug"])
app.include_router(metrics_router, tags=["monitoring"])
