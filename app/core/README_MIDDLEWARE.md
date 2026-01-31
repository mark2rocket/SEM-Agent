# Middleware Integration Guide

## Overview

The middleware module provides three key middleware components for the SEM-Agent API:

1. **RateLimitMiddleware** - Distributed rate limiting using Redis
2. **TenantContextMiddleware** - Tenant resolution and context management
3. **RequestLoggingMiddleware** - Request/response logging with correlation IDs

## Integration with main.py

Add the following to `app/main.py`:

```python
from redis.asyncio import Redis
from app.core.middleware import (
    RateLimitMiddleware,
    TenantContextMiddleware,
    RequestLoggingMiddleware,
    get_redis_client
)

# Create Redis client for rate limiting
redis_client: Redis = None

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    global redis_client

    logger.info("Starting SEM-Agent API...")

    # Initialize Redis client
    redis_client = await get_redis_client()
    logger.info("Redis client initialized")

    # Initialize token encryption
    init_token_encryption(settings.token_encryption_key)
    logger.info("Token encryption initialized")

    # Create database tables
    if settings.is_development:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created")

    logger.info("SEM-Agent API started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global redis_client

    logger.info("Shutting down SEM-Agent API...")

    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed")


# Add middleware in order (last added = first executed)
# Order matters: Logging -> Tenant -> RateLimit

# 1. Rate limiting (checks limits based on tenant context)
app.add_middleware(RateLimitMiddleware, redis_client=redis_client)

# 2. Tenant context (extracts tenant for downstream middleware)
app.add_middleware(TenantContextMiddleware)

# 3. Request logging (logs all requests with correlation ID)
app.add_middleware(RequestLoggingMiddleware)

# 4. CORS (already exists)
app.add_middleware(CORSMiddleware, ...)
```

## Middleware Execution Order

Middleware is executed in **reverse order** of registration:

```
Request → RequestLogging → TenantContext → RateLimit → Your Handler
Response ← RequestLogging ← TenantContext ← RateLimit ← Your Handler
```

## Rate Limiting Configuration

### Default Limits

| API | Requests | Window |
|-----|----------|--------|
| Google Ads | 100 | 60s |
| Slack | 50 | 60s |
| Gemini Flash | 60 | 60s |
| Gemini Pro | 10 | 60s |
| Default | 100 | 60s |

### Path-based API Detection

The middleware automatically detects API type from request path:

- `/google-ads/*` or `/ads/*` → `google_ads`
- `/slack/*` → `slack`
- `/gemini/*` or `/ai/*` → `gemini_flash`
- Others → `default`

### Rate Limit Response

When rate limit is exceeded, returns:

```json
{
  "error": "요청 한도를 초과했습니다",
  "message": "45초 후 다시 시도해주세요",
  "retry_after": 45
}
```

HTTP Status: `429 Too Many Requests`
Header: `Retry-After: 45`

## Tenant Context

### Tenant Extraction Methods

The middleware extracts tenant ID from:

1. **Query parameter**: `?workspace_id=W123456`
2. **Custom header**: `X-Workspace-ID: W123456`
3. **Slack events**: Extracted from event payload (future)

### Using Tenant Context

```python
from app.core.middleware import get_current_tenant

@router.get("/my-endpoint")
async def my_endpoint():
    tenant_id = get_current_tenant()
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant not found")

    # Use tenant_id for queries
    return {"tenant": tenant_id}
```

## Request Logging

### Log Format

**Request:**
```
Request started: method=GET path=/api/v1/reports tenant=W123456 correlation_id=550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```
Request completed: method=GET path=/api/v1/reports status=200 duration_ms=123.45 tenant=W123456 correlation_id=550e8400-e29b-41d4-a716-446655440000
```

**Error:**
```
Request failed: method=POST path=/api/v1/keywords duration_ms=234.56 tenant=W123456 correlation_id=550e8400-e29b-41d4-a716-446655440000 error=Division by zero
```

### Correlation ID

All responses include `X-Correlation-ID` header for request tracking.

```python
from app.core.middleware import get_current_request_id

logger.error(
    f"Processing failed: correlation_id={get_current_request_id()}"
)
```

## Testing

Run unit tests:

```bash
pytest tests/unit/test_rate_limiting.py -v
```

### Test Coverage

- ✓ Rate limit allows first request
- ✓ Rate limit blocks 101st request
- ✓ Different tenants have independent limits
- ✓ Rate limits reset after window
- ✓ Health check endpoint skips rate limiting
- ✓ Requests without tenant context skip rate limiting
- ✓ Redis errors don't block requests
- ✓ Tenant extraction from query params and headers
- ✓ Tenant context cleanup after request
- ✓ Correlation ID added to all responses
- ✓ Error handling with correlation tracking

## Redis Requirements

Ensure Redis is running and accessible via `settings.redis_url`.

```bash
# Local development
redis-server

# Docker
docker run -d -p 6379:6379 redis:7-alpine

# Check connection
redis-cli ping
```

## Monitoring

### Key Metrics to Monitor

1. **Rate limit hits** - Track 429 responses by tenant and API
2. **Request duration** - Monitor `duration_ms` in logs
3. **Error rate** - Track 500 responses by correlation ID
4. **Redis availability** - Monitor Redis connection errors

### Example Monitoring Query (CloudWatch/Datadog)

```
fields @timestamp, correlation_id, method, path, status, duration_ms, tenant
| filter status = 429
| stats count() by tenant, path
```

## Security Considerations

1. **Rate limiting is enforced per tenant** - Prevents abuse by single tenant
2. **Tenant context is required** - Anonymous requests skip rate limiting
3. **Correlation IDs are logged** - Enables security audit trails
4. **Redis failures are non-blocking** - Prevents DoS if Redis is down

## Future Enhancements

- [ ] JWT token-based tenant extraction
- [ ] Configurable rate limits per tenant tier
- [ ] Rate limit metrics export to Prometheus
- [ ] IP-based rate limiting for unauthenticated endpoints
- [ ] Adaptive rate limiting based on system load
