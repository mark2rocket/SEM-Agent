# SEM Slack Bot Implementation Plan

**Version:** 2.0.0
**Status:** APPROVED (Consensus Achieved)
**Created:** 2026-01-31

## PRD Reference

**Full PRD:** See `.omc/plans/sem-slack-bot-prd.md`

Based on PRD v1.1.0: SEM (Search Advertising AI Agent) for Slack
- Option B: Human-in-the-Loop + Weekly Default + Gemini Powered

**Key PRD Decisions (Resolved):**
| Question | Decision |
|----------|----------|
| Multi-account support? | V1은 단일 계정, V2에서 지원 |
| Timezone handling? | 사용자 설정 타임존 (기본 KST) |
| Approval expiration? | 24시간 후 자동 만료 (무시 처리) |
| Gemini budget? | 월 $100 (Flash 기본, Pro는 월간 리포트만) |
| GDPR? | V1은 한국 대상, GDPR은 V2에서 고려 |

---

## 1. Project Overview

### 1.1 Goal
Build a Slack bot that integrates with Google Ads to provide:
1. Automated performance reports with AI-powered insights
2. Negative keyword automation with human approval workflow

### 1.2 Tech Stack
| Component | Technology | Version |
|-----------|------------|---------|
| Backend | Python + FastAPI | 3.11+ / 0.109+ |
| Database | PostgreSQL | 15+ |
| Cache/Broker | Redis | 7+ |
| Scheduler | Celery Beat | 5.3+ |
| AI | Google Gemini | 1.5 Flash (default) / Pro |
| Google Ads | Google Ads API | v16 |
| Slack | Slack Bolt SDK | 1.18+ |

### 1.3 Directory Structure
```
sem-slack-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry
│   ├── config.py                  # Settings via pydantic-settings
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                # Dependency injection
│   │   └── endpoints/
│   │       ├── __init__.py
│   │       ├── slack.py           # /slack/events, /slack/commands
│   │       ├── oauth.py           # /oauth/google/*, /slack/oauth/*
│   │       ├── reports.py         # /api/v1/reports
│   │       ├── keywords.py        # /api/v1/keywords, /api/v1/approvals
│   │       └── health.py          # /health, /health/ready
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py            # Token encryption, signature verification
│   │   ├── middleware.py          # Rate limiting, tenant resolution
│   │   └── exceptions.py          # Custom exception handlers
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py              # Tenant, User models
│   │   ├── oauth.py               # OAuthToken model
│   │   ├── google_ads.py          # GoogleAdsAccount, Threshold models
│   │   ├── report.py              # ReportSchedule, ReportHistory models
│   │   └── keyword.py             # KeywordCandidate, ApprovalRequest models
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── slack.py               # Slack event/command schemas
│   │   ├── report.py              # Report request/response schemas
│   │   └── keyword.py             # Keyword/approval schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── token_service.py       # Token encryption/decryption
│   │   ├── slack_service.py       # Slack messaging, Block Kit
│   │   ├── google_ads_service.py  # Google Ads API client
│   │   ├── gemini_service.py      # Gemini API with rate limiting
│   │   ├── report_service.py      # Report generation logic
│   │   └── keyword_service.py     # Keyword detection & approval
│   └── tasks/
│       ├── __init__.py
│       ├── celery_app.py          # Celery configuration
│       ├── report_tasks.py        # Scheduled report tasks
│       ├── keyword_tasks.py       # Keyword detection tasks
│       └── maintenance_tasks.py   # Token refresh, cleanup
├── migrations/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## 2. Implementation Phases

### Phase 0: Project Bootstrap (Days 1-3)

#### Task 0.1: Repository Setup
**File:** `pyproject.toml`, `requirements.txt`
**Action:** CREATE

```toml
# pyproject.toml
[project]
name = "sem-slack-bot"
version = "0.1.0"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]

[tool.mypy]
python_version = "3.11"
strict = true
```

```txt
# requirements.txt
fastapi==0.109.2
uvicorn[standard]==0.27.1
pydantic-settings==2.2.1
sqlalchemy[asyncio]==2.0.27
asyncpg==0.29.0
alembic==1.13.1
redis==5.0.1
celery[redis]==5.3.6
slack-bolt==1.18.1
google-ads==23.1.0
google-generativeai==0.4.0
cryptography==42.0.2
httpx==0.26.0
python-jose[cryptography]==3.3.0
pytest==8.0.0
pytest-asyncio==0.23.4
```

**Acceptance Criteria:**
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] `ruff check .` passes
- [ ] `mypy app/` passes

#### Task 0.2: Docker Compose Setup
**File:** `docker-compose.yml`
**Action:** CREATE

```yaml
version: '3.9'
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: sem
      POSTGRES_PASSWORD: sem_dev_password
      POSTGRES_DB: sem_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sem"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://sem:sem_dev_password@db:5432/sem_db
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  postgres_data:
```

**Acceptance Criteria:**
- [ ] `docker-compose up -d` starts all services
- [ ] `curl http://localhost:8000/health` returns `{"status": "ok"}`
- [ ] PostgreSQL accepts connections on port 5432
- [ ] Redis accepts connections on port 6379

#### Task 0.3: Configuration Setup
**File:** `app/config.py`
**Action:** CREATE

```python
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import json

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    debug: bool = Field(default=False, description="Enable debug mode")
    base_url: str = Field(default="http://localhost:8000", description="Base URL for callbacks")
    allowed_origins: list[str] = Field(default=["http://localhost:3000"])

    # Database
    database_url: str = Field(..., description="PostgreSQL connection URL")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Encryption
    token_encryption_key: str = Field(..., description="Base64-encoded 32-byte Fernet key for KEK")

    # Slack
    slack_client_id: str = Field(..., description="Slack app client ID")
    slack_client_secret: str = Field(..., description="Slack app client secret")
    slack_signing_secret: str = Field(..., description="Slack request signing secret")
    slack_bot_token: Optional[str] = Field(default=None, description="Default bot token (overridden per tenant)")

    # Google
    google_client_id: str = Field(..., description="Google OAuth client ID")
    google_client_secret: str = Field(..., description="Google OAuth client secret")
    google_redirect_uri: str = Field(default="http://localhost:8000/oauth/google/callback")
    google_developer_token: str = Field(..., description="Google Ads API developer token")

    # Gemini
    gemini_api_key: str = Field(..., description="Google Gemini API key")
    gemini_monthly_budget_usd: float = Field(default=100.0)

    @property
    def google_client_config(self) -> dict:
        """Google OAuth client config for flow initialization."""
        return {
            "web": {
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret,
                "redirect_uris": [self.google_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**File:** `.env.example`
**Action:** CREATE

```bash
# App
DEBUG=false
BASE_URL=http://localhost:8000

# Database
DATABASE_URL=postgresql+asyncpg://sem:sem_dev_password@localhost:5432/sem_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Encryption (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
TOKEN_ENCRYPTION_KEY=your-base64-fernet-key-here

# Slack (from https://api.slack.com/apps)
SLACK_CLIENT_ID=your-slack-client-id
SLACK_CLIENT_SECRET=your-slack-client-secret
SLACK_SIGNING_SECRET=your-slack-signing-secret

# Google (from https://console.cloud.google.com)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/google/callback
GOOGLE_DEVELOPER_TOKEN=your-google-ads-developer-token

# Gemini
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MONTHLY_BUDGET_USD=100.0
```

**Acceptance Criteria:**
- [ ] `Settings()` loads all required env vars or raises validation error
- [ ] Missing required fields raise clear error with field name
- [ ] `settings.google_client_config` returns valid OAuth config dict
- [ ] `.env.example` documents all required variables

#### Task 0.4: FastAPI Skeleton
**File:** `app/main.py`
**Action:** CREATE

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.config import settings

# Database setup
engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Redis setup
redis_client: Redis | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    global redis_client
    # Startup
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    yield
    # Shutdown
    if redis_client:
        await redis_client.close()

app = FastAPI(
    title="SEM Slack Bot",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db() -> AsyncSession:
    """Dependency for database session."""
    async with async_session() as session:
        yield session

async def get_redis() -> Redis:
    """Dependency for Redis client."""
    return redis_client

@app.get("/health")
async def health_check():
    """Liveness probe - always returns ok if app is running."""
    return {"status": "ok"}

@app.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Readiness probe - checks all dependencies."""
    errors = []

    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        errors.append(f"database: {str(e)}")

    # Check Redis
    try:
        await redis.ping()
    except Exception as e:
        errors.append(f"redis: {str(e)}")

    if errors:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "errors": errors}
        )

    return {"status": "ready", "database": "ok", "redis": "ok"}
```

**Acceptance Criteria:**
- [ ] `GET /health` returns 200 with `{"status": "ok"}`
- [ ] `GET /health/ready` returns 200 when DB and Redis are connected
- [ ] `GET /health/ready` returns 503 with error details when dependencies unavailable
- [ ] Database session is properly closed after each request
- [ ] Redis connection is established on startup and closed on shutdown

---

### Phase 1: Security Foundation (Days 4-10)

#### Task 1.1: Token Encryption Service
**File:** `app/services/token_service.py`
**Action:** CREATE

```python
from cryptography.fernet import Fernet
from typing import Optional
import base64
import os

class TokenService:
    """
    Envelope encryption for OAuth tokens.
    - DEK (Data Encryption Key): Fernet key, unique per token
    - KEK (Key Encryption Key): From environment/KMS
    """

    def __init__(self, kek: str):
        """
        Args:
            kek: Base64-encoded 32-byte key (from env or KMS)
        """
        self._kek = Fernet(kek.encode() if isinstance(kek, str) else kek)

    def encrypt_token(self, plaintext: str) -> tuple[bytes, bytes]:
        """
        Encrypt a token using envelope encryption.

        Returns:
            (encrypted_token, encrypted_dek)
        """
        # Generate random DEK
        dek = Fernet.generate_key()
        dek_cipher = Fernet(dek)

        # Encrypt token with DEK
        encrypted_token = dek_cipher.encrypt(plaintext.encode())

        # Encrypt DEK with KEK
        encrypted_dek = self._kek.encrypt(dek)

        return encrypted_token, encrypted_dek

    def decrypt_token(self, encrypted_token: bytes, encrypted_dek: bytes) -> str:
        """Decrypt a token using envelope encryption."""
        # Decrypt DEK with KEK
        dek = self._kek.decrypt(encrypted_dek)
        dek_cipher = Fernet(dek)

        # Decrypt token with DEK
        return dek_cipher.decrypt(encrypted_token).decode()
```

**Acceptance Criteria:**
- [ ] `encrypt_token("test")` returns non-plaintext bytes
- [ ] `decrypt_token(enc, dek)` returns original plaintext
- [ ] Different calls to `encrypt_token` produce different ciphertexts (random DEK)
- [ ] Decryption with wrong KEK raises `InvalidToken`
- [ ] Unit test: `tests/unit/test_token_service.py` passes

#### Task 1.2: Database Schema with RLS (Complete)
**File:** `migrations/versions/001_initial_schema.py`
**Action:** CREATE

```python
"""Initial schema with RLS - Complete

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ============================================
    # TENANT & AUTHENTICATION
    # ============================================

    # Tenants table
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('slack_team_id', sa.String(32), unique=True, nullable=False),
        sa.Column('slack_team_name', sa.String(255), nullable=False),
        sa.Column('default_channel_id', sa.String(32)),  # Channel for notifications
        sa.Column('timezone', sa.String(64), server_default="'Asia/Seoul'"),
        sa.Column('settings', postgresql.JSONB, server_default='{}'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('slack_user_id', sa.String(32), nullable=False),
        sa.Column('slack_username', sa.String(255)),
        sa.Column('email', sa.String(255)),
        sa.Column('role', sa.String(32), server_default="'member'"),  # 'admin', 'member'
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('tenant_id', 'slack_user_id', name='uq_users_tenant_slack'),
    )

    # OAuth tokens table (encrypted)
    op.create_table(
        'oauth_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),  # 'slack', 'google_ads'
        sa.Column('encrypted_access_token', postgresql.BYTEA, nullable=False),
        sa.Column('encrypted_refresh_token', postgresql.BYTEA),
        sa.Column('encrypted_dek', postgresql.BYTEA, nullable=False),
        sa.Column('token_expires_at', sa.DateTime(timezone=True)),
        sa.Column('scopes', postgresql.ARRAY(sa.Text)),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('tenant_id', 'provider', name='uq_oauth_tokens_tenant_provider'),
    )

    # ============================================
    # GOOGLE ADS CONFIGURATION
    # ============================================

    # Google Ads accounts
    op.create_table(
        'google_ads_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', sa.String(32), nullable=False),  # Google Ads customer ID (no dashes)
        sa.Column('customer_name', sa.String(255)),
        sa.Column('is_manager_account', sa.Boolean, server_default='false'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('linked_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('tenant_id', 'customer_id', name='uq_google_ads_tenant_customer'),
    )

    # Inefficiency thresholds (per tenant, optionally per account)
    op.create_table(
        'inefficiency_thresholds',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('google_ads_accounts.id', ondelete='CASCADE')),
        # NULL account_id = tenant-wide default
        sa.Column('min_impressions', sa.Integer, server_default='1000'),
        sa.Column('max_ctr_percent', sa.Numeric(5, 2), server_default='0.50'),
        sa.Column('min_cost_usd', sa.Numeric(10, 2), server_default='50.00'),
        sa.Column('max_conversion_rate_percent', sa.Numeric(5, 2), server_default='0.10'),
        sa.Column('lookback_days', sa.Integer, server_default='30'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('tenant_id', 'account_id', name='uq_thresholds_tenant_account'),
    )

    # ============================================
    # REPORTING
    # ============================================

    # Report schedules
    op.create_table(
        'report_schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('google_ads_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('report_type', sa.String(32), nullable=False),  # 'daily', 'weekly', 'monthly'
        sa.Column('slack_channel_id', sa.String(32), nullable=False),
        sa.Column('schedule_hour', sa.Integer, nullable=False),  # 0-23
        sa.Column('schedule_minute', sa.Integer, server_default='0'),  # 0-59
        sa.Column('schedule_day_of_week', sa.Integer),  # 0=Mon for weekly (NULL for daily)
        sa.Column('schedule_day_of_month', sa.Integer),  # 1-31 for monthly (NULL for others)
        sa.Column('timezone', sa.String(64), server_default="'Asia/Seoul'"),
        sa.Column('include_gemini_insights', sa.Boolean, server_default='true'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Report history
    op.create_table(
        'report_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('report_schedules.id', ondelete='SET NULL')),
        sa.Column('account_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('google_ads_accounts.id', ondelete='SET NULL')),
        sa.Column('report_type', sa.String(32), nullable=False),
        sa.Column('period_start', sa.Date, nullable=False),
        sa.Column('period_end', sa.Date, nullable=False),
        sa.Column('metrics_snapshot', postgresql.JSONB, nullable=False),
        sa.Column('gemini_insights', sa.Text),
        sa.Column('slack_channel_id', sa.String(32)),
        sa.Column('slack_message_ts', sa.String(32)),
        sa.Column('status', sa.String(32), server_default="'success'"),  # 'success', 'partial', 'failed'
        sa.Column('error_message', sa.Text),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # ============================================
    # KEYWORD AUTOMATION & APPROVALS
    # ============================================

    # Keyword candidates (detected inefficient keywords)
    op.create_table(
        'keyword_candidates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('google_ads_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('keyword_text', sa.String(255), nullable=False),
        sa.Column('match_type', sa.String(32), nullable=False),  # 'BROAD', 'PHRASE', 'EXACT'
        sa.Column('campaign_id', sa.String(64), nullable=False),
        sa.Column('campaign_name', sa.String(255)),
        sa.Column('ad_group_id', sa.String(64), nullable=False),
        sa.Column('impressions', sa.Integer, nullable=False),
        sa.Column('clicks', sa.Integer, nullable=False),
        sa.Column('cost_micros', sa.BigInteger, nullable=False),
        sa.Column('conversions', sa.Numeric(10, 2), nullable=False),
        sa.Column('ctr_percent', sa.Numeric(5, 2), nullable=False),
        sa.Column('conversion_rate_percent', sa.Numeric(5, 2), nullable=False),
        sa.Column('detection_reason', sa.Text, nullable=False),
        sa.Column('gemini_analysis', sa.Text),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Approval requests
    op.create_table(
        'approval_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('keyword_candidates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action_type', sa.String(32), nullable=False),  # 'add_negative'
        sa.Column('action_payload', postgresql.JSONB, nullable=False),
        sa.Column('status', sa.String(32), server_default="'pending'"),
        # 'pending', 'approved', 'rejected', 'expired', 'executed'
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('slack_channel_id', sa.String(32), nullable=False),
        sa.Column('slack_message_ts', sa.String(32)),
        sa.Column('decided_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('decided_at', sa.DateTime(timezone=True)),
        sa.Column('decision_comment', sa.Text),
        sa.Column('executed_at', sa.DateTime(timezone=True)),
        sa.Column('execution_result', postgresql.JSONB),
    )

    # ============================================
    # AUDIT & OBSERVABILITY
    # ============================================

    # Audit logs
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('action', sa.String(64), nullable=False),
        # e.g., 'oauth.connected', 'report.generated', 'keyword.approved'
        sa.Column('resource_type', sa.String(64)),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True)),
        sa.Column('details', postgresql.JSONB, server_default='{}'),
        sa.Column('ip_address', postgresql.INET),
        sa.Column('user_agent', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # ============================================
    # INDEXES
    # ============================================

    op.create_index('idx_oauth_tokens_tenant_provider', 'oauth_tokens', ['tenant_id', 'provider'])
    op.create_index('idx_report_schedules_active', 'report_schedules', ['is_active', 'report_type'])
    op.create_index('idx_approval_requests_pending', 'approval_requests',
                    ['tenant_id', 'status', 'expires_at'])
    op.create_index('idx_keyword_candidates_detected', 'keyword_candidates',
                    ['tenant_id', 'detected_at'])
    op.create_index('idx_audit_logs_tenant_time', 'audit_logs', ['tenant_id', 'created_at'])

    # ============================================
    # ROW-LEVEL SECURITY
    # ============================================

    tables_with_rls = [
        'tenants', 'users', 'oauth_tokens', 'google_ads_accounts',
        'inefficiency_thresholds', 'report_schedules', 'report_history',
        'keyword_candidates', 'approval_requests', 'audit_logs'
    ]

    for table in tables_with_rls:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')

    # RLS policies (tenant isolation)
    op.execute('''
        CREATE POLICY tenant_isolation_users ON users
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_oauth ON oauth_tokens
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_accounts ON google_ads_accounts
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_thresholds ON inefficiency_thresholds
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_schedules ON report_schedules
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_history ON report_history
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_candidates ON keyword_candidates
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_approvals ON approval_requests
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')
    op.execute('''
        CREATE POLICY tenant_isolation_audit ON audit_logs
        FOR ALL USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    ''')

def downgrade():
    # Drop policies
    policies = [
        ('tenant_isolation_users', 'users'),
        ('tenant_isolation_oauth', 'oauth_tokens'),
        ('tenant_isolation_accounts', 'google_ads_accounts'),
        ('tenant_isolation_thresholds', 'inefficiency_thresholds'),
        ('tenant_isolation_schedules', 'report_schedules'),
        ('tenant_isolation_history', 'report_history'),
        ('tenant_isolation_candidates', 'keyword_candidates'),
        ('tenant_isolation_approvals', 'approval_requests'),
        ('tenant_isolation_audit', 'audit_logs'),
    ]
    for policy, table in policies:
        op.execute(f'DROP POLICY IF EXISTS {policy} ON {table}')

    # Drop tables in reverse order
    tables = [
        'audit_logs', 'approval_requests', 'keyword_candidates',
        'report_history', 'report_schedules', 'inefficiency_thresholds',
        'google_ads_accounts', 'oauth_tokens', 'users', 'tenants'
    ]
    for table in tables:
        op.drop_table(table)
```

**Acceptance Criteria:**
- [ ] `alembic upgrade head` executes without errors
- [ ] All 10 tables created: tenants, users, oauth_tokens, google_ads_accounts, inefficiency_thresholds, report_schedules, report_history, keyword_candidates, approval_requests, audit_logs
- [ ] All tables have RLS enabled (`SELECT relrowsecurity FROM pg_class WHERE relname='oauth_tokens'` returns `t`)
- [ ] Query without `SET app.tenant_id` returns no rows
- [ ] Query with correct `tenant_id` returns matching rows only
- [ ] Cross-tenant data access impossible (verified via integration test)
- [ ] Integration test: `tests/integration/test_rls.py` passes

#### Task 1.3: Tenant Context Middleware
**File:** `app/core/middleware.py`
**Action:** CREATE

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import json
import hashlib
import hmac
import time

class TenantMiddleware(BaseHTTPMiddleware):
    """
    Resolves tenant from Slack team_id and sets app.tenant_id for RLS.
    """

    # Paths that don't require tenant context
    PUBLIC_PATHS = {"/health", "/health/ready", "/docs", "/openapi.json"}
    # Paths that handle their own tenant resolution
    OAUTH_PATHS = {"/slack/oauth/install", "/slack/oauth/callback",
                   "/oauth/google/connect", "/oauth/google/callback"}

    def __init__(self, app, db_session_factory, redis_client):
        super().__init__(app)
        self.db_session_factory = db_session_factory
        self.redis = redis_client

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip tenant resolution for public paths
        if path in self.PUBLIC_PATHS or path in self.OAUTH_PATHS:
            return await call_next(request)

        # Extract Slack team_id from various sources
        tenant_id = await self._resolve_tenant(request)

        if tenant_id:
            # Store tenant_id in request state for use in dependencies
            request.state.tenant_id = tenant_id

        response = await call_next(request)
        return response

    async def _resolve_tenant(self, request: Request) -> str | None:
        """
        Resolve tenant from request in priority order:
        1. Slack event/command payload (team_id)
        2. X-Tenant-ID header (internal API)
        3. JWT token claim (future use)
        """

        # 1. From Slack event payload (POST /slack/events or /slack/commands)
        if request.url.path.startswith("/slack/"):
            try:
                body = await request.body()
                if body:
                    payload = json.loads(body)

                    # Slack Events API
                    if "team_id" in payload:
                        team_id = payload["team_id"]
                    # Slack event wrapper
                    elif "event" in payload and "team" in payload:
                        team_id = payload["team"]
                    # Slash commands (form-encoded, parsed differently)
                    else:
                        team_id = None

                    if team_id:
                        # Look up tenant_id from slack_team_id
                        return await self._get_tenant_by_slack_team(team_id)
            except (json.JSONDecodeError, KeyError):
                pass

        # 2. From X-Tenant-ID header (internal/admin API)
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header:
            # Validate UUID format
            try:
                from uuid import UUID
                UUID(tenant_header)
                return tenant_header
            except ValueError:
                pass

        return None

    async def _get_tenant_by_slack_team(self, slack_team_id: str) -> str | None:
        """Look up tenant UUID from Slack team ID with caching."""
        cache_key = f"tenant:slack:{slack_team_id}"

        # Check cache first
        cached = await self.redis.get(cache_key)
        if cached:
            return cached

        # Query database
        async with self.db_session_factory() as db:
            result = await db.execute(
                text("SELECT id FROM tenants WHERE slack_team_id = :team_id AND is_active = true"),
                {"team_id": slack_team_id}
            )
            row = result.fetchone()
            if row:
                tenant_id = str(row[0])
                # Cache for 5 minutes
                await self.redis.setex(cache_key, 300, tenant_id)
                return tenant_id

        return None


class SlackSignatureMiddleware(BaseHTTPMiddleware):
    """Verify Slack request signatures for security."""

    def __init__(self, app, signing_secret: str):
        super().__init__(app)
        self.signing_secret = signing_secret

    async def dispatch(self, request: Request, call_next):
        # Only verify Slack endpoints
        if not request.url.path.startswith("/slack/"):
            return await call_next(request)

        # Skip signature check for OAuth callbacks (they don't have signatures)
        if "oauth" in request.url.path:
            return await call_next(request)

        # Get signature headers
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")

        if not timestamp or not signature:
            raise HTTPException(401, "Missing Slack signature headers")

        # Verify timestamp is recent (within 5 minutes)
        try:
            request_time = int(timestamp)
            if abs(time.time() - request_time) > 300:
                raise HTTPException(401, "Request timestamp too old")
        except ValueError:
            raise HTTPException(401, "Invalid timestamp")

        # Verify signature
        body = await request.body()
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_sig = "v0=" + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, signature):
            raise HTTPException(401, "Invalid Slack signature")

        return await call_next(request)
```

**File:** `app/api/deps.py`
**Action:** CREATE

```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import AsyncGenerator

from app.main import async_session, redis_client

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database session."""
    async with async_session() as session:
        yield session

async def get_redis():
    """Dependency for Redis client."""
    return redis_client

async def get_tenant_id(request: Request) -> UUID:
    """
    Dependency to get and validate tenant ID from request.
    Sets RLS context for database queries.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(401, "Tenant context required")
    return UUID(tenant_id)

async def get_db_with_tenant(
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for database session with RLS tenant context set.
    Use this for all tenant-scoped queries.
    """
    # Set RLS context
    await db.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
    yield db
```

**Acceptance Criteria:**
- [ ] Slack events automatically resolve tenant from `team_id` in payload
- [ ] Slack request signatures are verified (401 on invalid signature)
- [ ] X-Tenant-ID header works for internal API calls
- [ ] `get_db_with_tenant` dependency sets RLS context correctly
- [ ] RLS is enforced for all database queries using the dependency
- [ ] Unauthenticated requests to tenant-scoped endpoints return 401
- [ ] Cross-tenant data access is impossible (security test)
- [ ] Tenant lookup is cached in Redis (5 min TTL)

---

### Phase 2: OAuth Flows (Days 11-20)

#### Task 2.1: Slack OAuth Implementation
**File:** `app/api/endpoints/oauth.py`
**Action:** CREATE

**Required Slack Scopes:**
```
bot:
  - chat:write
  - commands
  - im:write
  - users:read
user:
  - (none required for bot-only flow)
```

```python
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

slack_app = AsyncApp(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET,
)

@router.get("/slack/oauth/install")
async def slack_oauth_install():
    """Redirect to Slack OAuth authorization URL."""
    state = generate_state_token()
    await redis.setex(f"slack_oauth_state:{state}", 600, "pending")

    return RedirectResponse(
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        f"&scope=chat:write,commands,im:write,users:read"
        f"&state={state}"
    )

@router.get("/slack/oauth/callback")
async def slack_oauth_callback(code: str, state: str):
    """Handle Slack OAuth callback."""
    # Verify state
    stored_state = await redis.get(f"slack_oauth_state:{state}")
    if not stored_state:
        raise HTTPException(400, "Invalid or expired state")

    # Exchange code for tokens
    response = await slack_client.oauth_v2_access(
        client_id=settings.SLACK_CLIENT_ID,
        client_secret=settings.SLACK_CLIENT_SECRET,
        code=code,
    )

    # Create or update tenant
    tenant = await create_or_update_tenant(
        slack_team_id=response["team"]["id"],
        slack_team_name=response["team"]["name"],
    )

    # Store encrypted bot token
    await token_service.store_token(
        tenant_id=tenant.id,
        provider="slack",
        access_token=response["access_token"],
    )

    # Send welcome message with Block Kit
    welcome_blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🎉 SEM Bot 연동 완료!",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "세팅 완료! 📅 *매주 월요일 오전 9시*에 주간 리포트가 발송됩니다.\n\n다음 단계로 Google Ads 계정을 연동해주세요."
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔗 Google Ads 연결"},
                    "style": "primary",
                    "action_id": "connect_google_ads",
                    "url": f"{settings.base_url}/oauth/google/connect?tenant_id={tenant.id}"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "⚙️ 리포트 주기 변경하기"},
                    "action_id": "open_report_settings"
                }
            ]
        }
    ]

    await slack_app.client.chat_postMessage(
        channel=response["authed_user"]["id"],
        text="세팅 완료! 매주 월요일 오전 9시에 주간 리포트가 발송됩니다.",
        blocks=welcome_blocks,
    )

    return RedirectResponse("/oauth/success")
```

**Acceptance Criteria:**
- [ ] User clicks "Add to Slack" → redirected to Slack OAuth
- [ ] OAuth completion creates tenant in database
- [ ] Bot token is stored encrypted (verify ciphertext in DB)
- [ ] Welcome message appears in Slack with Korean text
- [ ] `[리포트 주기 변경하기]` button is visible
- [ ] Re-installing updates existing tenant (no duplicates)

#### Task 2.2: Google Ads OAuth Implementation
**File:** `app/api/endpoints/oauth.py`
**Action:** MODIFY

**Required Google Ads Scopes:**
```
https://www.googleapis.com/auth/adwords
```

```python
from google.oauth2.credentials import Credentials
from google.ads.googleads.client import GoogleAdsClient

@router.get("/oauth/google/connect")
async def google_oauth_connect(tenant_id: UUID = Depends(get_current_tenant)):
    """Initiate Google Ads OAuth flow."""
    state = f"{tenant_id}:{generate_state_token()}"
    await redis.setex(f"google_oauth_state:{state}", 600, str(tenant_id))

    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        client_config=settings.GOOGLE_CLIENT_CONFIG,
        scopes=["https://www.googleapis.com/auth/adwords"],
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",  # Force refresh token
    )

    return RedirectResponse(auth_url)

@router.get("/oauth/google/callback")
async def google_oauth_callback(code: str, state: str):
    """Handle Google OAuth callback."""
    # Verify state and get tenant
    tenant_id = await redis.get(f"google_oauth_state:{state}")
    if not tenant_id:
        raise HTTPException(400, "Invalid or expired state")

    # Exchange code for tokens
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        client_config=settings.google_client_config,
        scopes=["https://www.googleapis.com/auth/adwords"],
    )
    flow.redirect_uri = settings.google_redirect_uri
    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Store encrypted tokens
    await token_service.store_token(
        tenant_id=UUID(tenant_id),
        provider="google_ads",
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        expires_at=credentials.expiry,
    )

    # List accessible Google Ads accounts
    accounts = await google_ads_service.list_accessible_accounts(credentials)

    # Return account selection UI
    return templates.TemplateResponse("select_account.html", {
        "accounts": accounts,
        "tenant_id": tenant_id,
    })
```

**Acceptance Criteria:**
- [ ] User clicks "Connect Google Ads" → redirected to Google OAuth
- [ ] OAuth completion stores encrypted refresh token
- [ ] Account selection shows all accessible Google Ads accounts
- [ ] Selected account is stored in `google_ads_accounts` table
- [ ] Token refresh works after 1 hour (access token expiry)
- [ ] Refresh token is preserved across refreshes

#### Task 2.3: Slack Event Handlers
**File:** `app/api/endpoints/slack.py`
**Action:** CREATE

```python
from fastapi import APIRouter, Request, Depends
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from uuid import UUID

from app.config import settings
from app.api.deps import get_db_with_tenant, get_redis
from app.services.report_service import ReportService
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/slack", tags=["slack"])

# Initialize Slack Bolt app
slack_app = AsyncApp(
    token=settings.slack_bot_token,
    signing_secret=settings.slack_signing_secret,
)
slack_handler = AsyncSlackRequestHandler(slack_app)


# ============================================
# SLASH COMMANDS
# ============================================

@slack_app.command("/sem-config")
async def handle_config_command(ack, body, client):
    """Handle /sem-config command - open settings modal."""
    await ack()

    tenant_id = body["team_id"]

    await client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "report_settings_modal",
            "title": {"type": "plain_text", "text": "리포트 설정"},
            "submit": {"type": "plain_text", "text": "저장"},
            "close": {"type": "plain_text", "text": "취소"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "report_frequency",
                    "label": {"type": "plain_text", "text": "리포트 주기"},
                    "element": {
                        "type": "static_select",
                        "action_id": "frequency_select",
                        "placeholder": {"type": "plain_text", "text": "주기 선택"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "매일"}, "value": "daily"},
                            {"text": {"type": "plain_text", "text": "매주 (기본)"}, "value": "weekly"},
                            {"text": {"type": "plain_text", "text": "매월"}, "value": "monthly"},
                            {"text": {"type": "plain_text", "text": "끄기"}, "value": "off"},
                        ],
                        "initial_option": {"text": {"type": "plain_text", "text": "매주 (기본)"}, "value": "weekly"}
                    }
                },
                {
                    "type": "input",
                    "block_id": "report_time",
                    "label": {"type": "plain_text", "text": "발송 시간"},
                    "element": {
                        "type": "static_select",
                        "action_id": "time_select",
                        "options": [
                            {"text": {"type": "plain_text", "text": "09:00"}, "value": "9"},
                            {"text": {"type": "plain_text", "text": "14:00"}, "value": "14"},
                            {"text": {"type": "plain_text", "text": "18:00"}, "value": "18"},
                        ],
                        "initial_option": {"text": {"type": "plain_text", "text": "09:00"}, "value": "9"}
                    }
                }
            ]
        }
    )


@slack_app.command("/sem-report")
async def handle_report_command(ack, body, client, say):
    """Handle /sem-report command - generate on-demand report."""
    await ack()

    # Show period selection
    await client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "report_period_modal",
            "title": {"type": "plain_text", "text": "리포트 기간 선택"},
            "submit": {"type": "plain_text", "text": "생성"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "period",
                    "label": {"type": "plain_text", "text": "기간"},
                    "element": {
                        "type": "static_select",
                        "action_id": "period_select",
                        "options": [
                            {"text": {"type": "plain_text", "text": "어제"}, "value": "yesterday"},
                            {"text": {"type": "plain_text", "text": "지난주"}, "value": "last_week"},
                            {"text": {"type": "plain_text", "text": "지난달"}, "value": "last_month"},
                        ]
                    }
                }
            ]
        }
    )


@slack_app.command("/sem-status")
async def handle_status_command(ack, body, say):
    """Handle /sem-status command - show connection status."""
    await ack()

    # This would query the database for actual status
    await say({
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🔗 연결 상태*\n• Slack: ✅ 연결됨\n• Google Ads: ✅ 연결됨\n\n*📅 다음 리포트*\n• 월요일 09:00 KST (주간 리포트)"
                }
            }
        ]
    })


# ============================================
# BUTTON ACTIONS
# ============================================

@slack_app.action("connect_google_ads")
async def handle_connect_google_ads(ack, body, client):
    """Handle Google Ads connect button click."""
    await ack()
    # Button has URL, so this is just for logging/analytics


@slack_app.action("open_report_settings")
async def handle_open_settings(ack, body, client):
    """Handle settings button click - open settings modal."""
    await ack()

    await client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "report_settings_modal",
            "title": {"type": "plain_text", "text": "리포트 설정"},
            "submit": {"type": "plain_text", "text": "저장"},
            "close": {"type": "plain_text", "text": "취소"},
            "blocks": [
                # Same blocks as /sem-config command
                {
                    "type": "input",
                    "block_id": "report_frequency",
                    "label": {"type": "plain_text", "text": "리포트 주기"},
                    "element": {
                        "type": "static_select",
                        "action_id": "frequency_select",
                        "options": [
                            {"text": {"type": "plain_text", "text": "매일"}, "value": "daily"},
                            {"text": {"type": "plain_text", "text": "매주 (기본)"}, "value": "weekly"},
                            {"text": {"type": "plain_text", "text": "매월"}, "value": "monthly"},
                            {"text": {"type": "plain_text", "text": "끄기"}, "value": "off"},
                        ]
                    }
                }
            ]
        }
    )


@slack_app.action("view_report_details")
async def handle_view_details(ack, body, client, say):
    """Handle view report details button."""
    await ack()
    report_id = body["actions"][0]["value"]
    # Fetch and display detailed report
    await say(f"상세 리포트를 불러오는 중... (ID: {report_id})")


@slack_app.action("approve_keyword_exclusion")
async def handle_approve_exclusion(ack, body, client):
    """Handle keyword exclusion approval button."""
    await ack()

    request_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]

    # Process approval (this would use ApprovalService)
    # await approval_service.handle_approval(request_id, user_id, approved=True)

    # Update the message to show approved status
    await client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text="✅ 키워드가 제외 처리되었습니다.",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"✅ *제외 키워드 등록 완료*\n\n승인자: <@{user_id}>"
                }
            }
        ]
    )


@slack_app.action("reject_keyword_exclusion")
async def handle_reject_exclusion(ack, body, client):
    """Handle keyword exclusion rejection button."""
    await ack()

    request_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]

    # Process rejection
    # await approval_service.handle_approval(request_id, user_id, approved=False)

    # Update the message
    await client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text="👀 키워드 제외가 무시되었습니다.",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"👀 *무시됨*\n\n처리자: <@{user_id}>"
                }
            }
        ]
    )


# ============================================
# MODAL SUBMISSIONS
# ============================================

@slack_app.view("report_settings_modal")
async def handle_settings_submission(ack, body, client, view):
    """Handle report settings modal submission."""
    await ack()

    user_id = body["user"]["id"]
    values = view["state"]["values"]

    frequency = values["report_frequency"]["frequency_select"]["selected_option"]["value"]
    time_hour = values["report_time"]["time_select"]["selected_option"]["value"]

    # Update schedule in database
    # await report_service.update_schedule(tenant_id, frequency, time_hour)

    # Confirm to user
    await client.chat_postMessage(
        channel=user_id,
        text=f"✅ 리포트 설정이 저장되었습니다.\n• 주기: {frequency}\n• 시간: {time_hour}:00"
    )


@slack_app.view("report_period_modal")
async def handle_report_period_submission(ack, body, client, view):
    """Handle on-demand report period selection."""
    await ack()

    user_id = body["user"]["id"]
    period = view["state"]["values"]["period"]["period_select"]["selected_option"]["value"]

    # Generate report asynchronously
    await client.chat_postMessage(
        channel=user_id,
        text=f"📊 {period} 리포트를 생성 중입니다. 잠시만 기다려주세요..."
    )

    # Trigger async report generation
    # await report_service.generate_on_demand_report(tenant_id, period)


# ============================================
# FASTAPI ENDPOINTS
# ============================================

@router.post("/events")
async def slack_events(request: Request):
    """Handle Slack Events API."""
    return await slack_handler.handle(request)


@router.post("/commands")
async def slack_commands(request: Request):
    """Handle Slack slash commands."""
    return await slack_handler.handle(request)


@router.post("/interactions")
async def slack_interactions(request: Request):
    """Handle Slack interactive components (buttons, modals)."""
    return await slack_handler.handle(request)
```

**Acceptance Criteria:**
- [ ] `/sem-config` opens report settings modal
- [ ] `/sem-report` opens period selection modal and generates report
- [ ] `/sem-status` shows connection and schedule status
- [ ] `open_report_settings` button opens settings modal
- [ ] `approve_keyword_exclusion` button processes approval and updates message
- [ ] `reject_keyword_exclusion` button processes rejection and updates message
- [ ] `report_settings_modal` submission saves settings to database
- [ ] All Slack requests have signature verification
- [ ] Korean text renders correctly in all messages and modals

---

### Phase 3: Infrastructure (Days 21-30)

#### Task 3.1: Celery Configuration
**File:** `app/tasks/celery_app.py`
**Action:** CREATE

```python
from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "sem_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# Dynamic schedules loaded from database
celery_app.conf.beat_schedule = {
    "process-scheduled-reports": {
        "task": "app.tasks.report_tasks.process_scheduled_reports",
        "schedule": crontab(minute="*/5"),  # Check every 5 minutes
    },
    "check-approval-expirations": {
        "task": "app.tasks.keyword_tasks.check_approval_expirations",
        "schedule": crontab(minute="*/15"),  # Check every 15 minutes
    },
    "refresh-expiring-tokens": {
        "task": "app.tasks.maintenance_tasks.refresh_expiring_tokens",
        "schedule": crontab(minute=0, hour="*/1"),  # Every hour
    },
}
```

**Acceptance Criteria:**
- [ ] `celery -A app.tasks.celery_app worker` starts without errors
- [ ] `celery -A app.tasks.celery_app beat` schedules tasks correctly
- [ ] Tasks survive worker restart (Redis persistence)
- [ ] Task failures are logged with full traceback
- [ ] `flower` shows task history and worker status

#### Task 3.1b: Celery Task Implementations
**File:** `app/tasks/report_tasks.py`
**Action:** CREATE

```python
from celery import shared_task
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncio
import pytz

from app.config import settings
from app.tasks.celery_app import celery_app
from app.models.report import ReportSchedule
from app.services.report_service import ReportService
from app.services.slack_service import SlackService

# Create async engine for tasks
engine = create_async_engine(settings.database_url)


def run_async(coro):
    """Helper to run async code in Celery tasks."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


@celery_app.task(name="app.tasks.report_tasks.process_scheduled_reports")
def process_scheduled_reports():
    """
    Check for reports due to be sent and trigger generation.
    Runs every 5 minutes via Celery Beat.
    """
    run_async(_process_scheduled_reports_async())


async def _process_scheduled_reports_async():
    """Async implementation of scheduled report processing."""
    async with AsyncSession(engine) as db:
        now = datetime.utcnow()

        # Find schedules that should run now
        # Check based on schedule_hour, schedule_day_of_week, etc.
        schedules = await db.execute(
            select(ReportSchedule).where(
                and_(
                    ReportSchedule.is_active == True,
                    # Additional filtering based on current time
                )
            )
        )

        for schedule in schedules.scalars():
            if _should_run_now(schedule, now):
                # Trigger individual report generation
                generate_report_for_schedule.delay(str(schedule.id))


def _should_run_now(schedule: ReportSchedule, now: datetime) -> bool:
    """Check if schedule should run at current time."""
    # Convert to schedule's timezone
    tz = pytz.timezone(schedule.timezone)
    local_now = now.astimezone(tz)

    # Check hour and minute (within 5 minute window)
    if local_now.hour != schedule.schedule_hour:
        return False
    if local_now.minute > 5:  # Only trigger in first 5 mins of the hour
        return False

    # Check day based on report type
    if schedule.report_type == "weekly":
        if local_now.weekday() != (schedule.schedule_day_of_week or 0):
            return False
    elif schedule.report_type == "monthly":
        if local_now.day != (schedule.schedule_day_of_month or 1):
            return False

    return True


@celery_app.task(name="app.tasks.report_tasks.generate_report_for_schedule")
def generate_report_for_schedule(schedule_id: str):
    """Generate and send a report for a specific schedule."""
    run_async(_generate_report_async(schedule_id))


async def _generate_report_async(schedule_id: str):
    """Async implementation of report generation."""
    async with AsyncSession(engine) as db:
        # Fetch schedule
        schedule = await db.get(ReportSchedule, schedule_id)
        if not schedule or not schedule.is_active:
            return

        # Initialize services
        report_service = ReportService(db)
        slack_service = SlackService()

        try:
            # Generate report based on type
            if schedule.report_type == "daily":
                report = await report_service.generate_daily_report(
                    tenant_id=schedule.tenant_id,
                    account_id=str(schedule.account_id),
                )
            elif schedule.report_type == "weekly":
                report = await report_service.generate_weekly_report(
                    tenant_id=schedule.tenant_id,
                    account_id=str(schedule.account_id),
                )
            elif schedule.report_type == "monthly":
                report = await report_service.generate_monthly_report(
                    tenant_id=schedule.tenant_id,
                    account_id=str(schedule.account_id),
                )

            # Send to Slack
            await slack_service.send_report(
                channel_id=schedule.slack_channel_id,
                report=report,
            )

        except Exception as e:
            # Log error and notify
            import logging
            logging.error(f"Report generation failed for schedule {schedule_id}: {e}")
            # Could send error notification to admin channel
```

**File:** `app/tasks/keyword_tasks.py`
**Action:** CREATE

```python
from celery import shared_task
from datetime import datetime, timedelta
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncio

from app.config import settings
from app.tasks.celery_app import celery_app
from app.models.keyword import ApprovalRequest, ApprovalStatus

engine = create_async_engine(settings.database_url)


def run_async(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


@celery_app.task(name="app.tasks.keyword_tasks.check_approval_expirations")
def check_approval_expirations():
    """
    Check for expired approval requests and mark them as expired.
    Runs every 15 minutes via Celery Beat.
    """
    run_async(_check_expirations_async())


async def _check_expirations_async():
    """Async implementation of expiration checking."""
    async with AsyncSession(engine) as db:
        now = datetime.utcnow()

        # Find and update expired pending requests
        result = await db.execute(
            update(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.expires_at < now,
                )
            )
            .values(status=ApprovalStatus.EXPIRED)
            .returning(ApprovalRequest.id, ApprovalRequest.slack_channel_id, ApprovalRequest.slack_message_ts)
        )

        expired_requests = result.fetchall()
        await db.commit()

        # Update Slack messages for expired requests
        if expired_requests:
            from app.services.slack_service import SlackService
            slack_service = SlackService()

            for req_id, channel_id, message_ts in expired_requests:
                if channel_id and message_ts:
                    try:
                        await slack_service.update_message(
                            channel_id=channel_id,
                            message_ts=message_ts,
                            text="⏰ 승인 요청이 만료되었습니다.",
                            blocks=[
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": "⏰ *승인 요청 만료*\n24시간 내 응답이 없어 자동으로 만료되었습니다."
                                    }
                                }
                            ]
                        )
                    except Exception:
                        pass  # Slack message update is best-effort


@celery_app.task(name="app.tasks.keyword_tasks.detect_inefficient_keywords")
def detect_inefficient_keywords(tenant_id: str, account_id: str):
    """Detect inefficient keywords for a specific account."""
    run_async(_detect_keywords_async(tenant_id, account_id))


async def _detect_keywords_async(tenant_id: str, account_id: str):
    """Async implementation of keyword detection."""
    async with AsyncSession(engine) as db:
        from app.services.keyword_service import KeywordService
        from app.services.approval_service import ApprovalService

        keyword_service = KeywordService(db)
        approval_service = ApprovalService(db)

        # Detect inefficient keywords
        candidates = await keyword_service.detect_inefficient_keywords(
            tenant_id=tenant_id,
            account_id=account_id,
        )

        # Create approval requests for each candidate
        for candidate in candidates:
            await approval_service.create_approval_request(
                candidate=candidate,
                channel_id=candidate.notification_channel,  # From tenant settings
            )
```

**File:** `app/tasks/maintenance_tasks.py`
**Action:** CREATE

```python
from celery import shared_task
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncio

from app.config import settings
from app.tasks.celery_app import celery_app
from app.models.oauth import OAuthToken

engine = create_async_engine(settings.database_url)


def run_async(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


@celery_app.task(name="app.tasks.maintenance_tasks.refresh_expiring_tokens")
def refresh_expiring_tokens():
    """
    Refresh OAuth tokens that are expiring soon.
    Runs every hour via Celery Beat.
    """
    run_async(_refresh_tokens_async())


async def _refresh_tokens_async():
    """Async implementation of token refresh."""
    async with AsyncSession(engine) as db:
        from app.services.token_service import TokenService

        token_service = TokenService(settings.token_encryption_key)

        # Find tokens expiring in the next 30 minutes
        expiry_threshold = datetime.utcnow() + timedelta(minutes=30)

        result = await db.execute(
            select(OAuthToken).where(
                and_(
                    OAuthToken.provider == "google_ads",
                    OAuthToken.token_expires_at < expiry_threshold,
                    OAuthToken.token_expires_at > datetime.utcnow(),
                )
            )
        )

        for token in result.scalars():
            try:
                # Decrypt refresh token
                refresh_token = token_service.decrypt_token(
                    token.encrypted_refresh_token,
                    token.encrypted_dek,
                )

                # Refresh with Google
                new_credentials = await _refresh_google_token(refresh_token)

                # Encrypt and store new access token
                enc_access, enc_dek = token_service.encrypt_token(new_credentials.token)
                token.encrypted_access_token = enc_access
                token.encrypted_dek = enc_dek
                token.token_expires_at = new_credentials.expiry
                token.updated_at = datetime.utcnow()

            except Exception as e:
                import logging
                logging.error(f"Token refresh failed for token {token.id}: {e}")
                # Could notify user that re-authentication is needed

        await db.commit()


async def _refresh_google_token(refresh_token: str):
    """Refresh Google OAuth token."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )

    # This is sync but we run it in executor for async compatibility
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, credentials.refresh, Request())

    return credentials
```

**Acceptance Criteria:**
- [ ] `process_scheduled_reports` correctly identifies due schedules
- [ ] `generate_report_for_schedule` generates and sends reports
- [ ] `check_approval_expirations` marks expired requests and updates Slack
- [ ] `refresh_expiring_tokens` refreshes tokens before expiry
- [ ] All tasks handle errors gracefully without crashing worker
- [ ] Tasks log errors with sufficient context for debugging

#### Task 3.2: Rate Limiting Middleware
**File:** `app/core/middleware.py`
**Action:** MODIFY

```python
from redis.asyncio import Redis
import time

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting per tenant per API."""

    LIMITS = {
        "google_ads": {"requests": 100, "window": 60},  # 100/min
        "slack": {"requests": 50, "window": 60},        # 50/min
        "gemini_flash": {"requests": 60, "window": 60}, # 60/min
        "gemini_pro": {"requests": 10, "window": 60},   # 10/min
    }

    async def check_rate_limit(
        self,
        redis: Redis,
        tenant_id: str,
        api: str
    ) -> tuple[bool, int]:
        """
        Returns:
            (allowed, retry_after_seconds)
        """
        key = f"ratelimit:{tenant_id}:{api}"
        limit = self.LIMITS.get(api, {"requests": 100, "window": 60})

        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, limit["window"])

        if current > limit["requests"]:
            ttl = await redis.ttl(key)
            return False, ttl

        return True, 0
```

**Acceptance Criteria:**
- [ ] 101st request within 60s to Google Ads returns 429
- [ ] `Retry-After` header contains correct seconds
- [ ] Different tenants have independent limits
- [ ] Rate limits reset after window expires
- [ ] Unit test: `tests/unit/test_rate_limiting.py` passes

#### Task 3.3: Google Ads API Client
**File:** `app/services/google_ads_service.py`
**Action:** CREATE

**Google Ads API Version:** v16

```python
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import tenacity

class GoogleAdsService:
    """Google Ads API v16 client with retry and caching."""

    API_VERSION = "v16"

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        retry=tenacity.retry_if_exception_type(GoogleAdsException),
    )
    async def get_campaign_performance(
        self,
        customer_id: str,
        date_range: tuple[date, date],
    ) -> list[dict]:
        """
        Fetch campaign performance metrics.

        GAQL Query:
        SELECT
            campaign.id,
            campaign.name,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        """
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
            FROM campaign
            WHERE segments.date BETWEEN '{date_range[0]}' AND '{date_range[1]}'
        """

        response = self.client.get_service("GoogleAdsService").search_stream(
            customer_id=customer_id,
            query=query,
        )

        results = []
        for batch in response:
            for row in batch.results:
                results.append({
                    "campaign_id": row.campaign.id,
                    "campaign_name": row.campaign.name,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": row.metrics.cost_micros / 1_000_000,
                    "conversions": row.metrics.conversions,
                    "conversion_value": row.metrics.conversions_value,
                })

        return results

    async def add_negative_keyword(
        self,
        customer_id: str,
        campaign_id: str,
        keyword_text: str,
        match_type: str = "BROAD",
    ) -> dict:
        """Add negative keyword to campaign."""
        campaign_criterion_service = self.client.get_service("CampaignCriterionService")

        operation = self.client.get_type("CampaignCriterionOperation")
        criterion = operation.create
        criterion.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion.negative = True
        criterion.keyword.text = keyword_text
        criterion.keyword.match_type = self.client.enums.KeywordMatchTypeEnum[match_type]

        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[operation],
        )

        return {"resource_name": response.results[0].resource_name}
```

**Acceptance Criteria:**
- [ ] `get_campaign_performance` returns correct metrics for date range
- [ ] Retry logic works on transient Google Ads errors
- [ ] `add_negative_keyword` successfully adds keyword to campaign
- [ ] API quota errors are handled gracefully with user notification
- [ ] Integration test with sandbox account passes

---

### Phase 4A: Reporting (Days 31-45)

#### Task 4A.1: Gemini Service with Rate Limiting
**File:** `app/services/gemini_service.py`
**Action:** CREATE

**Model Configuration:**
- Default: `gemini-1.5-flash` (cost-efficient)
- Complex analysis: `gemini-1.5-pro`
- Max tokens: 1000 (response), 4000 (input)

```python
import google.generativeai as genai
from typing import Literal
from datetime import datetime
from redis.asyncio import Redis
import json

from app.config import settings
from app.core.exceptions import RateLimitExceeded, GeminiError

class GeminiService:
    """Gemini API with rate limiting and cost tracking."""

    MODELS = {
        "flash": "gemini-1.5-flash",
        "pro": "gemini-1.5-pro",
    }

    # Cost per 1M tokens (as of 2024)
    COSTS = {
        "flash": {"input": 0.075, "output": 0.30},
        "pro": {"input": 1.25, "output": 5.00},
    }

    INSIGHT_PROMPT_TEMPLATE = """
당신은 Google Ads 전문 분석가입니다. 아래 성과 데이터를 분석하고 한국어로 3줄 요약을 작성하세요.

데이터:
{metrics_json}

요구사항:
1. 전주 대비 주요 변화 설명
2. 변화의 원인 추정
3. 개선 포인트 제안

형식:
- 간결하게 3문장으로 작성
- 수치는 정확히 인용
- 비즈니스 인사이트 중심
"""

    INEFFICIENCY_PROMPT_TEMPLATE = """
다음 검색어가 비효율적으로 판단된 이유를 한국어로 간단히 설명해주세요:

검색어: {keyword}
노출수: {impressions}
클릭수: {clicks}
비용: ₩{cost:,.0f}
전환수: {conversions}
CTR: {ctr:.2f}%
전환율: {conv_rate:.2f}%

1-2문장으로 왜 이 키워드를 제외해야 하는지 설명해주세요.
"""

    def __init__(self, redis: Redis, tenant_id: str):
        """
        Initialize Gemini service.

        Args:
            redis: Redis client for rate limiting and usage tracking
            tenant_id: Current tenant ID for rate limiting
        """
        self.redis = redis
        self.tenant_id = tenant_id

        # Configure Gemini API
        genai.configure(api_key=settings.gemini_api_key)

        # Initialize models
        self._models = {
            "flash": genai.GenerativeModel(self.MODELS["flash"]),
            "pro": genai.GenerativeModel(self.MODELS["pro"]),
        }

    async def generate_insight(
        self,
        metrics: dict,
        model: Literal["flash", "pro"] = "flash",
    ) -> str:
        """Generate Korean insight from metrics."""
        # Check rate limit
        allowed, retry_after = await self._check_rate_limit(model)
        if not allowed:
            raise RateLimitExceeded(retry_after)

        prompt = self.INSIGHT_PROMPT_TEMPLATE.format(
            metrics_json=json.dumps(metrics, ensure_ascii=False, indent=2)
        )

        try:
            response = await self._models[model].generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=1000,
                    temperature=0.3,  # Lower for consistency
                ),
            )

            # Track token usage for cost monitoring
            await self._track_usage(
                model=model,
                input_tokens=response.usage_metadata.prompt_token_count,
                output_tokens=response.usage_metadata.candidates_token_count,
            )

            return response.text

        except Exception as e:
            raise GeminiError(f"Gemini API error: {str(e)}")

    async def explain_inefficiency(self, keyword_data: dict) -> str:
        """Generate explanation for why a keyword is inefficient."""
        allowed, retry_after = await self._check_rate_limit("flash")
        if not allowed:
            # Return default message if rate limited
            return "비용 대비 전환이 낮아 비효율적인 키워드로 판단됩니다."

        prompt = self.INEFFICIENCY_PROMPT_TEMPLATE.format(
            keyword=keyword_data["keyword_text"],
            impressions=keyword_data["impressions"],
            clicks=keyword_data["clicks"],
            cost=keyword_data["cost_micros"] / 1_000_000,
            conversions=keyword_data["conversions"],
            ctr=keyword_data.get("ctr_percent", 0),
            conv_rate=keyword_data.get("conversion_rate_percent", 0),
        )

        try:
            response = await self._models["flash"].generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=200,
                    temperature=0.3,
                ),
            )
            return response.text
        except Exception:
            return "비용 대비 전환이 낮아 비효율적인 키워드로 판단됩니다."

    async def _check_rate_limit(self, model: str) -> tuple[bool, int]:
        """
        Check rate limit for Gemini API calls.

        Returns:
            (allowed, retry_after_seconds)
        """
        limits = {
            "flash": 60,  # 60 requests per minute
            "pro": 10,    # 10 requests per minute
        }

        key = f"ratelimit:{self.tenant_id}:gemini_{model}"
        limit = limits.get(model, 60)

        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, 60)  # 1 minute window

        if current > limit:
            ttl = await self.redis.ttl(key)
            return False, ttl

        return True, 0

    async def _track_usage(self, model: str, input_tokens: int, output_tokens: int):
        """Track token usage for cost monitoring."""
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Calculate cost
        costs = self.COSTS[model]
        cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

        # Increment daily counters
        usage_key = f"gemini_usage:{self.tenant_id}:{today}"
        await self.redis.hincrby(usage_key, f"{model}_input_tokens", input_tokens)
        await self.redis.hincrby(usage_key, f"{model}_output_tokens", output_tokens)
        await self.redis.hincrbyfloat(usage_key, f"{model}_cost_usd", cost)
        await self.redis.expire(usage_key, 86400 * 30)  # Keep for 30 days

    async def get_monthly_usage(self) -> dict:
        """Get current month's usage statistics."""
        # This would aggregate daily usage for the current month
        # Implementation depends on reporting needs
        pass
```

**Acceptance Criteria:**
- [ ] Korean insights are grammatically correct
- [ ] Insights reference specific metrics from input
- [ ] Rate limiting prevents > 60 Flash requests/minute
- [ ] Token usage is logged for cost tracking
- [ ] Fallback message shown when Gemini unavailable

#### Task 4A.2: Report Generation
**File:** `app/services/report_service.py`
**Action:** CREATE

```python
class ReportService:
    """Generate and format performance reports."""

    async def generate_weekly_report(
        self,
        tenant_id: UUID,
        account_id: str,
    ) -> dict:
        """Generate weekly performance report with Gemini insights."""
        # Get date range (last Monday to Sunday)
        today = date.today()
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_sunday = last_monday + timedelta(days=6)

        # Fetch metrics
        metrics = await self.google_ads_service.get_campaign_performance(
            customer_id=account_id,
            date_range=(last_monday, last_sunday),
        )

        # Calculate aggregates
        summary = self._aggregate_metrics(metrics)

        # Get previous week for comparison
        prev_metrics = await self.google_ads_service.get_campaign_performance(
            customer_id=account_id,
            date_range=(last_monday - timedelta(days=7), last_sunday - timedelta(days=7)),
        )
        prev_summary = self._aggregate_metrics(prev_metrics)

        # Calculate changes
        changes = self._calculate_changes(summary, prev_summary)

        # Generate Gemini insight
        insight = await self.gemini_service.generate_insight({
            "current": summary,
            "previous": prev_summary,
            "changes": changes,
        })

        return {
            "period": f"{last_monday} ~ {last_sunday}",
            "metrics": summary,
            "changes": changes,
            "insight": insight,
        }
```

**Acceptance Criteria:**
- [ ] Report contains all required metrics (비용, 전환, ROAS)
- [ ] Week-over-week changes are calculated correctly
- [ ] Gemini insight is included in report
- [ ] Report generation completes in < 30 seconds
- [ ] Korean formatting is correct (₩ symbol, % formatting)

#### Task 4A.3: Slack Block Kit Formatting
**File:** `app/services/slack_service.py`
**Action:** CREATE

```python
class SlackService:
    """Slack messaging with Block Kit."""

    def format_weekly_report(self, report: dict) -> list[dict]:
        """Format report as Slack Block Kit blocks."""
        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📅 주간 성과 리포트 ({report['period']})",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"• 비용: ₩{report['metrics']['cost']:,.0f} "
                        f"({self._format_change(report['changes']['cost'])})\n"
                        f"• 전환: {report['metrics']['conversions']:.0f}건 "
                        f"({self._format_change(report['changes']['conversions'])})\n"
                        f"• ROAS: {report['metrics']['roas']:.0f}% "
                        f"({self._format_change(report['changes']['roas'])})"
                    ),
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🧠 Gemini Insight*\n{report['insight']}",
                }
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "상세 보기"},
                        "action_id": "view_report_details",
                        "value": report["id"],
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "설정 변경"},
                        "action_id": "open_settings",
                    },
                ],
            },
        ]

    def _format_change(self, change: float) -> str:
        """Format percentage change with emoji."""
        if change > 0:
            return f"🔺{change:.1f}%"
        elif change < 0:
            return f"🔻{abs(change):.1f}%"
        return "→ 0%"
```

**Acceptance Criteria:**
- [ ] Report renders correctly in Slack (all blocks visible)
- [ ] Korean text displays correctly
- [ ] Emoji indicators show correct direction (🔺/🔻)
- [ ] Buttons are clickable and trigger correct actions
- [ ] Currency formatting uses ₩ with thousands separators

---

### Phase 4B: Keyword Automation (Days 31-50)

#### Task 4B.1: Inefficiency Detection
**File:** `app/services/keyword_service.py`
**Action:** CREATE

**Default Thresholds:**
| Metric | Default | Description |
|--------|---------|-------------|
| `min_impressions` | 1000 | Minimum data for significance |
| `max_ctr_percent` | 0.5 | CTR below this = potential issue |
| `min_cost_usd` | 50 | Minimum spend to consider |
| `max_conversion_rate` | 0.1 | Conv rate below this = inefficient |
| `lookback_days` | 30 | Analysis window |

```python
class KeywordService:
    """Detect and manage inefficient keywords."""

    async def detect_inefficient_keywords(
        self,
        tenant_id: UUID,
        account_id: str,
    ) -> list[KeywordCandidate]:
        """
        Detect keywords meeting inefficiency criteria.

        SQL equivalent:
        WHERE impressions >= :min_impressions
          AND ctr < :max_ctr
          AND cost >= :min_cost
          AND conversion_rate < :max_conversion_rate
        """
        thresholds = await self._get_thresholds(tenant_id, account_id)

        # Fetch search term performance
        search_terms = await self.google_ads_service.get_search_term_performance(
            customer_id=account_id,
            date_range=self._get_lookback_range(thresholds.lookback_days),
        )

        candidates = []
        for term in search_terms:
            if self._is_inefficient(term, thresholds):
                # Generate explanation with Gemini
                explanation = await self.gemini_service.explain_inefficiency(term)

                candidate = KeywordCandidate(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    keyword_text=term["search_term"],
                    match_type=term["match_type"],
                    campaign_id=term["campaign_id"],
                    ad_group_id=term["ad_group_id"],
                    impressions=term["impressions"],
                    clicks=term["clicks"],
                    cost_micros=term["cost_micros"],
                    conversions=term["conversions"],
                    detection_reason=self._format_reason(term, thresholds),
                    gemini_analysis=explanation,
                )
                candidates.append(candidate)

        return candidates

    def _is_inefficient(self, term: dict, thresholds: Thresholds) -> bool:
        """Check if keyword meets inefficiency criteria."""
        if term["impressions"] < thresholds.min_impressions:
            return False  # Not enough data

        ctr = (term["clicks"] / term["impressions"]) * 100
        cost = term["cost_micros"] / 1_000_000
        conv_rate = (term["conversions"] / term["clicks"]) * 100 if term["clicks"] > 0 else 0

        return (
            ctr < thresholds.max_ctr_percent
            and cost >= thresholds.min_cost_usd
            and conv_rate < thresholds.max_conversion_rate
        )
```

**Acceptance Criteria:**
- [ ] Keywords below threshold CTR are detected
- [ ] Keywords with insufficient impressions are ignored
- [ ] Detection reason explains which threshold was violated
- [ ] Gemini analysis provides actionable context
- [ ] Unit test with mock data passes

#### Task 4B.2: Approval Workflow
**File:** `app/services/approval_service.py`
**Action:** CREATE

**Approval States:**
```
PENDING → APPROVED → EXECUTED
       ↘ REJECTED
       ↘ EXPIRED (after 24 hours)
```

```python
from datetime import datetime, timedelta
from enum import Enum

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"

class ApprovalService:
    """Manage keyword approval workflow."""

    DEFAULT_EXPIRY_HOURS = 24

    async def create_approval_request(
        self,
        candidate: KeywordCandidate,
        channel_id: str,
    ) -> ApprovalRequest:
        """Create approval request and notify via Slack."""
        request = ApprovalRequest(
            tenant_id=candidate.tenant_id,
            candidate_id=candidate.id,
            action_type="add_negative",
            action_payload={
                "customer_id": candidate.account_id,
                "campaign_id": candidate.campaign_id,
                "keyword_text": candidate.keyword_text,
                "match_type": candidate.match_type,
            },
            status=ApprovalStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(hours=self.DEFAULT_EXPIRY_HOURS),
            slack_channel_id=channel_id,
        )

        await self.db.add(request)
        await self.db.commit()

        # Send Slack notification
        message = await self.slack_service.send_approval_request(
            channel_id=channel_id,
            candidate=candidate,
            request_id=request.id,
        )

        # Store message timestamp for updates
        request.slack_message_ts = message["ts"]
        await self.db.commit()

        return request

    async def handle_approval(
        self,
        request_id: UUID,
        user_id: UUID,
        approved: bool,
        comment: str | None = None,
    ) -> ApprovalRequest:
        """Process user approval or rejection."""
        request = await self.db.get(ApprovalRequest, request_id)

        if request.status != ApprovalStatus.PENDING:
            raise InvalidStateError(f"Request is already {request.status}")

        if datetime.utcnow() > request.expires_at:
            request.status = ApprovalStatus.EXPIRED
            await self.db.commit()
            raise ExpiredError("Approval request has expired")

        request.decided_by = user_id
        request.decided_at = datetime.utcnow()
        request.decision_comment = comment

        if approved:
            request.status = ApprovalStatus.APPROVED
            # Execute the action
            result = await self._execute_action(request)
            request.status = ApprovalStatus.EXECUTED
            request.executed_at = datetime.utcnow()
            request.execution_result = result
        else:
            request.status = ApprovalStatus.REJECTED

        await self.db.commit()

        # Update Slack message
        await self.slack_service.update_approval_message(
            channel_id=request.slack_channel_id,
            message_ts=request.slack_message_ts,
            status=request.status,
            decided_by=user_id,
        )

        # Audit log
        await self.audit_service.log(
            action="keyword.approval_decision",
            resource_type="approval_request",
            resource_id=request.id,
            details={
                "approved": approved,
                "comment": comment,
            },
        )

        return request
```

**Acceptance Criteria:**
- [ ] Approval request creates Slack message with buttons
- [ ] `[제외 키워드 등록]` click triggers approval flow
- [ ] `[무시하기]` click triggers rejection flow
- [ ] Expired requests cannot be approved (24h default)
- [ ] Approved actions execute against Google Ads API
- [ ] All decisions are audit logged
- [ ] Slack message updates to show decision status

---

### Phase 5: Hardening (Days 51-60)

#### Task 5.1: Error Handling
**File:** `app/core/exceptions.py`
**Action:** CREATE

**Error Taxonomy:**
| Error Type | HTTP Code | User Message (Korean) |
|------------|-----------|----------------------|
| `OAuthError` | 401 | "Google Ads 연결이 만료되었습니다. [다시 연결]" |
| `RateLimitError` | 429 | "요청이 많습니다. {n}초 후 다시 시도해주세요." |
| `GoogleAdsError` | 502 | "Google Ads에서 응답이 없습니다. 잠시 후 다시 시도해주세요." |
| `GeminiError` | 503 | "AI 분석을 수행할 수 없습니다. 다시 시도해주세요." |
| `ValidationError` | 400 | "입력 값을 확인해주세요: {details}" |
| `NotFoundError` | 404 | "요청한 리소스를 찾을 수 없습니다." |

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(OAuthError)
async def oauth_error_handler(request: Request, exc: OAuthError):
    # Notify user via Slack
    await slack_service.send_error_notification(
        tenant_id=exc.tenant_id,
        message="Google Ads 연결이 만료되었습니다.",
        action_url=f"{settings.BASE_URL}/oauth/google/connect",
    )

    return JSONResponse(
        status_code=401,
        content={"error": "oauth_expired", "message": exc.message_ko},
    )
```

**Acceptance Criteria:**
- [ ] All errors return Korean messages
- [ ] Errors include correlation ID for debugging
- [ ] Critical errors send Slack notification to user
- [ ] Error rates are tracked in metrics
- [ ] Unhandled exceptions are caught and logged

#### Task 5.2: Monitoring
**File:** `app/core/metrics.py`
**Action:** CREATE

```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
reports_generated = Counter(
    "sem_reports_generated_total",
    "Total reports generated",
    ["tenant_id", "report_type"],
)

keywords_detected = Counter(
    "sem_keywords_detected_total",
    "Total inefficient keywords detected",
    ["tenant_id"],
)

approvals_processed = Counter(
    "sem_approvals_processed_total",
    "Total approval decisions",
    ["tenant_id", "decision"],  # approved, rejected, expired
)

# Histograms
report_generation_time = Histogram(
    "sem_report_generation_seconds",
    "Report generation duration",
    ["report_type"],
)

gemini_latency = Histogram(
    "sem_gemini_latency_seconds",
    "Gemini API response time",
    ["model"],
)

# Gauges
active_tenants = Gauge(
    "sem_active_tenants",
    "Number of active tenants",
)

pending_approvals = Gauge(
    "sem_pending_approvals",
    "Number of pending approval requests",
)
```

**Acceptance Criteria:**
- [ ] `/metrics` endpoint returns Prometheus format
- [ ] All key operations are instrumented
- [ ] Grafana dashboard shows key metrics
- [ ] Alerts fire when error rate > 5%
- [ ] Alerts fire when pending approvals > 100

---

## 3. Verification Plan

### Unit Tests
| Module | Test File | Coverage Target |
|--------|-----------|-----------------|
| Token encryption | `tests/unit/test_token_service.py` | 100% |
| Rate limiting | `tests/unit/test_rate_limiting.py` | 100% |
| Keyword detection | `tests/unit/test_keyword_service.py` | 90% |
| Report formatting | `tests/unit/test_slack_service.py` | 90% |

### Integration Tests
| Flow | Test File | Requirements |
|------|-----------|--------------|
| Slack OAuth | `tests/integration/test_slack_oauth.py` | Slack sandbox app |
| Google OAuth | `tests/integration/test_google_oauth.py` | Google test account |
| Report generation | `tests/integration/test_reports.py` | Sandbox Google Ads |
| Keyword exclusion | `tests/integration/test_keywords.py` | Sandbox Google Ads |

### Security Tests
| Test | Method | Pass Criteria |
|------|--------|---------------|
| Token encryption | Verify DB ciphertext | No plaintext tokens |
| RLS isolation | Cross-tenant query | Zero rows returned |
| Rate limiting | Burst 200 requests | 429 after limit |
| Signature verification | Invalid Slack sig | 401 returned |

---

## 4. Open Questions (RESOLVED - See PRD Section 10)

| Question | Decision |
|----------|----------|
| Multi-account support? | V1은 단일 계정, V2에서 지원 |
| Timezone handling? | 사용자 설정 타임존 (기본 KST) |
| Approval expiration? | 24시간 후 자동 만료 (무시 처리) |
| Gemini budget? | 월 $100 (Flash 기본, Pro는 월간 리포트만) |
| GDPR? | V1은 한국 대상, GDPR은 V2에서 고려 |

---

## 5. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-31 | Initial plan creation |
| 2.0.0 | 2026-01-31 | Iteration 3 - Addressed Critic feedback: Added PRD document, complete DB schema (10 tables), config.py with all env vars, Slack event handlers, Celery task implementations, complete Gemini service initialization, removed all `...` placeholders |
| 2.1.0 | 2026-01-31 | **APPROVED** - Consensus achieved after Critic review. Minor fixes: added JSONResponse import, marked open questions as resolved |
