# SEM-Agent Setup Guide

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Google Ads Developer Token
- Slack App credentials
- Google Gemini API key

## Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd SEM-Agent
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and configure:

**Slack Configuration:**
1. Create a Slack App at https://api.slack.com/apps
2. Add bot scopes: `chat:write`, `commands`, `im:write`
3. Copy Client ID, Client Secret, and Signing Secret

**Google Ads Configuration:**
1. Apply for Google Ads API access
2. Create OAuth 2.0 credentials
3. Get Developer Token

**Gemini AI Configuration:**
1. Get API key from https://makersuite.google.com/app/apikey

**Security Keys:**
Generate encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 5. Database Setup

```bash
# Create database
createdb sem_agent

# Run migrations
alembic upgrade head
```

### 6. Start Services with Docker

```bash
docker-compose up -d
```

Or start services manually:

```bash
# Terminal 1: FastAPI
uvicorn app.main:app --reload

# Terminal 2: Celery Worker
celery -A app.tasks.celery_app worker --loglevel=info

# Terminal 3: Celery Beat
celery -A app.tasks.celery_app beat --loglevel=info
```

## Slack App Configuration

1. **OAuth & Permissions:**
   - Add Redirect URL: `http://localhost:8000/oauth/slack/callback`
   - Bot Token Scopes: `chat:write`, `commands`, `im:write`

2. **Slash Commands:**
   - `/sem-config` → `http://localhost:8000/slack/commands`
   - `/sem-report` → `http://localhost:8000/slack/commands`
   - `/sem-status` → `http://localhost:8000/slack/commands`

3. **Interactivity:**
   - Request URL: `http://localhost:8000/slack/interactions`

4. **Event Subscriptions:**
   - Request URL: `http://localhost:8000/slack/events`

## Testing

```bash
pytest tests/
```

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment guide.
