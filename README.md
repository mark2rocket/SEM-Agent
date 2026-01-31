# SEM-Agent (Search Advertising AI Agent)

**Slack bot for Google Ads management with AI-powered insights**

## Overview

SEM-Agent is a Slack bot that integrates with Google Ads to provide:
1. **Automated Performance Reports** - Weekly reports with Gemini AI insights (한국어)
2. **Negative Keyword Automation** - AI detection with human-in-the-loop approval

## Features

- 📊 **주간 리포트** - 매주 월요일 오전 9시 자동 발송 (설정 변경 가능)
- 🧠 **Gemini AI 인사이트** - 성과 데이터를 분석하여 한국어로 요약
- 🚨 **비효율 키워드 감지** - 자동 감지 후 승인 버튼으로 즉시 제외
- ⚙️ **슬랙 명령어** - `/sem-config`, `/sem-report`, `/sem-status`

## Tech Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Backend | Python + FastAPI | 3.11+ / 0.109+ |
| Database | PostgreSQL | 15+ |
| Cache/Broker | Redis | 7+ |
| Scheduler | Celery Beat | 5.3+ |
| AI | Google Gemini | 1.5 Flash/Pro |
| Google Ads | Google Ads API | v16 |
| Slack | Slack Bolt SDK | 1.18+ |

## Documentation

- **[PRD](docs/PRD.md)** - Product Requirements Document (v1.1.0)
- **[Implementation Plan](docs/IMPLEMENTATION_PLAN.md)** - 60-day development plan

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Google Ads Developer Token
- Slack App (bot token + signing secret)
- Gemini API Key

### Installation

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/SEM-Agent.git
cd SEM-Agent

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# Run database migrations
alembic upgrade head

# Start services
docker-compose up -d

# Start Celery worker and beat
celery -A app.tasks.celery_app worker --loglevel=info &
celery -A app.tasks.celery_app beat --loglevel=info &

# Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Project Structure

```
SEM-Agent/
├── app/
│   ├── api/endpoints/    # FastAPI endpoints
│   ├── core/             # Security, middleware
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic
│   └── tasks/            # Celery tasks
├── migrations/           # Alembic migrations
├── tests/                # Unit & integration tests
├── docs/                 # Documentation
├── docker-compose.yml
└── requirements.txt
```

## Development Status

- [x] PRD Completed (v1.1.0)
- [x] Implementation Plan Approved
- [ ] Phase 0: Project Bootstrap (Days 1-3)
- [ ] Phase 1: Security Foundation (Days 4-10)
- [ ] Phase 2: OAuth Flows (Days 11-20)
- [ ] Phase 3: Infrastructure (Days 21-30)
- [ ] Phase 4A: Reporting (Days 31-45)
- [ ] Phase 4B: Keyword Automation (Days 31-50)
- [ ] Phase 5: Hardening (Days 51-60)

## Slack Commands

| Command | Description |
|---------|-------------|
| `/sem-config` | 리포트 설정 변경 (주기, 시간) |
| `/sem-report` | 즉시 리포트 생성 (어제/지난주/지난달) |
| `/sem-status` | 연결 상태 및 다음 리포트 일정 확인 |

## Environment Variables

See `.env.example` for all required environment variables.

Key variables:
- `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_DEVELOPER_TOKEN`
- `GEMINI_API_KEY`
- `TOKEN_ENCRYPTION_KEY` (Base64-encoded Fernet key)

## License

MIT

## Support

For issues or questions, please open an issue on GitHub.
