# SEM-Agent Deployment Guide

**Slack bot for Google Ads management with AI-powered insights**

## English Version

### Table of Contents
1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [OAuth App Registration](#oauth-app-registration)
4. [Database Setup](#database-setup)
5. [First Run](#first-run)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)
8. [Production Deployment](#production-deployment)

---

## Prerequisites

Before deploying SEM-Agent, ensure you have the following installed on your system:

### System Requirements

| Component | Version | Description |
|-----------|---------|-------------|
| Python | 3.11+ | Core language |
| Docker | Latest | Container runtime |
| Docker Compose | 2.0+ | Container orchestration |
| PostgreSQL | 15+ | Primary database |
| Redis | 7+ | Cache and message broker |
| Git | Latest | Version control |

### Installation Commands

**macOS (Homebrew):**
```bash
# Install Python 3.11+
brew install python@3.11

# Install Docker Desktop (includes Docker & Docker Compose)
brew install --cask docker

# Install PostgreSQL 15
brew install postgresql@15

# Install Redis 7
brew install redis@7
```

**Ubuntu/Debian:**
```bash
# Update package manager
sudo apt-get update

# Install Python 3.11+
sudo apt-get install python3.11 python3.11-venv python3.11-dev

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install PostgreSQL 15
sudo apt-get install postgresql-15

# Install Redis 7
sudo apt-get install redis-server=7:*
```

**CentOS/RHEL:**
```bash
# Install Python 3.11+
sudo dnf install python3.11 python3.11-devel

# Install Docker
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install docker-ce docker-ce-cli

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install PostgreSQL 15
sudo dnf install postgresql15-server

# Install Redis 7
sudo dnf install redis
```

### Verification

```bash
# Verify Python
python3 --version          # Should be 3.11 or higher

# Verify Docker
docker --version
docker-compose --version

# Verify PostgreSQL
psql --version            # Should be 15 or higher

# Verify Redis
redis-cli --version       # Should be 7 or higher
```

---

## Environment Setup

### Step 1: Clone the Repository

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/SEM-Agent.git
cd SEM-Agent

# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Upgrade pip, setuptools, and wheel
pip install --upgrade pip setuptools wheel
```

### Step 2: Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Verify installation
pip list | grep -E "fastapi|sqlalchemy|celery|redis"
```

### Step 3: Create Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your values (see next sections)
nano .env  # or use your preferred editor
```

### Step 4: Generate Security Keys

You need to generate two encryption keys for security:

```bash
# Generate SECRET_KEY for JWT tokens
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Output: abc123def456... (copy this)

# Generate TOKEN_ENCRYPTION_KEY (Fernet key for API token encryption)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Output: gAAAAABl... (copy this)
```

Add these to your `.env` file:

```bash
SECRET_KEY=<your_generated_secret_key>
TOKEN_ENCRYPTION_KEY=<your_generated_encryption_key>
```

### Step 5: Configure Database Credentials

Edit `.env` to configure PostgreSQL connection:

```bash
# Database configuration
DATABASE_URL=postgresql://sem_user:sem_password@localhost:5432/sem_agent
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

**For production**, use a strong password and secure PostgreSQL connection:

```bash
DATABASE_URL=postgresql://sem_user:STRONG_PASSWORD@db.example.com:5432/sem_agent
```

### Step 6: Configure Redis Connection

```bash
# Redis configuration
REDIS_URL=redis://localhost:6379/0

# For production with authentication:
REDIS_URL=redis://:PASSWORD@redis.example.com:6379/0
```

### Step 7: Configure Application Settings

```bash
# FastAPI settings
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false
ENVIRONMENT=production

# For development:
DEBUG=true
ENVIRONMENT=development

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Celery settings
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TIMEZONE=Asia/Seoul
```

---

## OAuth App Registration

### Google Cloud Console - Google Ads API

#### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** → **New Project**
3. Enter project name: `SEM-Agent` (or your preferred name)
4. Click **Create**
5. Wait for the project to be created (2-3 minutes)

#### Step 2: Enable Required APIs

1. In Cloud Console, go to **APIs & Services** → **Library**
2. Search for and enable:
   - **Google Ads API** (v16)
   - **Google Drive API** (for file management)
   - **Google Sheets API** (for data export)

3. Click each API and select **Enable**

#### Step 3: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth 2.0 Client ID**
3. If prompted to configure consent screen:
   - Click **Configure Consent Screen**
   - Select **Internal** (for testing) or **External**
   - Fill in application information:
     - App name: `SEM-Agent`
     - User support email: your-email@example.com
   - Add scopes:
     - `https://www.googleapis.com/auth/adwords`
     - `https://www.googleapis.com/auth/drive`
   - Click **Save and Continue** → **Save and Continue** → **Back to Dashboard**

4. Back on Credentials page, click **Create Credentials** → **OAuth 2.0 Client ID**
5. Select **Web application**
6. Add authorized redirect URIs:
   - `http://localhost:8000/oauth/google/callback` (development)
   - `https://your-domain.com/oauth/google/callback` (production)
7. Click **Create**

#### Step 4: Get Credentials

1. Click the created credential
2. Copy and save:
   - **Client ID** → `GOOGLE_CLIENT_ID`
   - **Client Secret** → `GOOGLE_CLIENT_SECRET`

3. Add to `.env`:
```bash
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/google/callback
```

#### Step 5: Get Developer Token

1. Go to [Google Ads API Documentation](https://developers.google.com/google-ads/api/docs/first-call/overview)
2. Follow **Get a Developer Token** section
3. Navigate to [Google Ads API Center](https://ads.google.com/aw/apicenter)
4. Click **Tools & Settings** → **Developer Token**
5. Copy your developer token
6. Request access if needed (takes 24-48 hours)

Once approved, add to `.env`:

```bash
GOOGLE_DEVELOPER_TOKEN=your_developer_token
GOOGLE_LOGIN_CUSTOMER_ID=1234567890  # Your Google Ads customer ID
```

### Slack App - Bot & OAuth Setup

#### Step 1: Create a Slack App

1. Go to [Slack API Console](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Enter **App Name**: `SEM-Agent`
4. Select your **Workspace**
5. Click **Create App**

#### Step 2: Configure Slack Permissions

1. In the left menu, go to **OAuth & Permissions**
2. Under **Scopes** → **Bot Token Scopes**, add:
   - `chat:write` - Send messages
   - `commands` - Register slash commands
   - `app_mentions:read` - Listen to mentions
   - `channels:read` - List channels
   - `users:read` - Get user info
   - `team:read` - Get workspace info
   - `incoming-webhook` - Post to channels
   - `interactive_message_input:view` - Interactive buttons

3. Scroll up to **OAuth Tokens for Your Workspace**
4. Click **Install to Workspace**
5. Review permissions and click **Allow**
6. Copy your **Bot User OAuth Token** (starts with `xoxb-`)

#### Step 3: Get Signing Secret & App Token

1. Go to **Basic Information**
2. Under **App Credentials**:
   - Copy **Signing Secret** → `SLACK_SIGNING_SECRET`
   - Copy **Client ID** → `SLACK_CLIENT_ID`
   - Copy **Client Secret** → `SLACK_CLIENT_SECRET`

3. Go to **App-Level Tokens**
4. Click **Generate Token and Scopes**
5. Add scope: `connections:write`
6. Generate and copy token → `SLACK_APP_TOKEN`

#### Step 4: Configure OAuth Redirect

1. Go to **OAuth & Permissions**
2. Under **Redirect URLs**, add:
   - `http://localhost:8000/oauth/slack/callback` (development)
   - `https://your-domain.com/oauth/slack/callback` (production)
3. Click **Save URLs**

#### Step 5: Add Slash Commands

1. Go to **Slash Commands**
2. Click **Create New Command** for each:

**Command 1: /sem-config**
- Command: `/sem-config`
- Request URL: `http://localhost:8000/slack/commands/config`
- Description: Configure report settings
- Usage hint: `[frequency] [time]`

**Command 2: /sem-report**
- Command: `/sem-report`
- Request URL: `http://localhost:8000/slack/commands/report`
- Description: Generate report immediately
- Usage hint: `[period]` (daily, weekly, monthly)

**Command 3: /sem-status**
- Command: `/sem-status`
- Request URL: `http://localhost:8000/slack/commands/status`
- Description: Check connection status
- Usage hint: No parameters

#### Step 6: Add to .env

```bash
SLACK_CLIENT_ID=your_slack_client_id
SLACK_CLIENT_SECRET=your_slack_client_secret
SLACK_SIGNING_SECRET=your_slack_signing_secret
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_REDIRECT_URI=http://localhost:8000/oauth/slack/callback
SLACK_ALERT_CHANNEL=#alerts  # Channel for alerts
```

### Google Gemini AI - API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Click **Create API Key**
3. Copy the API key
4. Add to `.env`:

```bash
GEMINI_API_KEY=your_gemini_api_key
GEMINI_DEFAULT_MODEL=gemini-1.5-flash
GEMINI_PRO_MODEL=gemini-1.5-pro
```

### Complete .env Example

After all registrations, your `.env` should look like:

```bash
# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false
ENVIRONMENT=production

# Database
DATABASE_URL=postgresql://sem_user:password@localhost:5432/sem_agent
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379/0

# Slack
SLACK_CLIENT_ID=1234567890.1234567890
SLACK_CLIENT_SECRET=abcdef123456
SLACK_SIGNING_SECRET=abcdef123456
SLACK_APP_TOKEN=xapp-1-XXXXXX
SLACK_BOT_TOKEN=xoxb-1-XXXXXX
SLACK_REDIRECT_URI=http://localhost:8000/oauth/slack/callback
SLACK_ALERT_CHANNEL=#alerts

# Google OAuth
GOOGLE_CLIENT_ID=1234567890-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-abcdefg
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/google/callback

# Google Ads
GOOGLE_DEVELOPER_TOKEN=1234567890ABCDEFG
GOOGLE_LOGIN_CUSTOMER_ID=1234567890

# Gemini AI
GEMINI_API_KEY=AIzaSyDxxxxxxxxxxxxxxxxx
GEMINI_DEFAULT_MODEL=gemini-1.5-flash
GEMINI_PRO_MODEL=gemini-1.5-pro

# Security
SECRET_KEY=your_secret_key_here
TOKEN_ENCRYPTION_KEY=your_encryption_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TIMEZONE=Asia/Seoul

# Monitoring
SENTRY_DSN=
LOG_LEVEL=INFO
```

---

## Database Setup

### Step 1: Start PostgreSQL

**Using Docker (Recommended):**
```bash
docker-compose up -d postgres
```

**Using Homebrew (macOS):**
```bash
# Start PostgreSQL service
brew services start postgresql@15

# Verify it's running
psql -U postgres -h localhost
```

**Using systemd (Linux):**
```bash
# Start PostgreSQL service
sudo systemctl start postgresql

# Enable on boot
sudo systemctl enable postgresql
```

### Step 2: Create Database and User

```bash
# Connect to PostgreSQL
psql -U postgres -h localhost

# Execute in PostgreSQL shell:
```

```sql
-- Create database user
CREATE USER sem_user WITH PASSWORD 'sem_password';

-- Create database
CREATE DATABASE sem_agent OWNER sem_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE sem_agent TO sem_user;

-- Connect to the new database
\c sem_agent

-- Grant schema privileges
GRANT ALL PRIVILEGES ON SCHEMA public TO sem_user;

-- Exit
\q
```

### Step 3: Verify Database Connection

```bash
# Test connection
psql -U sem_user -h localhost -d sem_agent

# Should connect successfully
# Exit with \q
```

### Step 4: Create Alembic Migrations

```bash
# Navigate to project root
cd /path/to/SEM-Agent

# Initialize Alembic (if not already done)
alembic init migrations

# Create initial migration
alembic revision --autogenerate -m "Initial schema"

# Verify migration was created
ls -la migrations/versions/
```

### Step 5: Run Migrations

```bash
# Apply migrations to database
alembic upgrade head

# Check migration status
alembic current
alembic history
```

### Step 6: Verify Database Schema

```bash
# Connect to database
psql -U sem_user -h localhost -d sem_agent

# List tables
\dt

# Should show tables like:
# - tenants
# - google_ads_integrations
# - slack_integrations
# - keywords
# - reports
# - approval_requests
# etc.

# Exit
\q
```

### Troubleshooting Database Issues

**Connection refused:**
```bash
# Check PostgreSQL is running
psql -U postgres -h localhost

# If failed, restart service:
# macOS: brew services restart postgresql@15
# Linux: sudo systemctl restart postgresql
```

**"Could not connect to server":**
```bash
# Check PostgreSQL port
netstat -an | grep 5432  # macOS/Linux
netstat -ano | grep 5432  # Windows

# Default port is 5432, adjust DATABASE_URL if different
```

**Permission denied:**
```bash
# Verify user password
psql -U sem_user -h localhost -d sem_agent

# Reset password if needed:
psql -U postgres -h localhost
ALTER USER sem_user WITH PASSWORD 'new_password';
```

---

## First Run

### Step 1: Start Supporting Services

```bash
# Option A: Using Docker Compose (Recommended)
docker-compose up -d postgres redis

# Option B: Start services individually
# Terminal 1: PostgreSQL (if using Homebrew)
brew services start postgresql@15

# Terminal 2: Redis (if using Homebrew)
brew services start redis@7

# Verify services are running
docker-compose ps
# or
redis-cli ping      # Should output: PONG
psql -U sem_user -d sem_agent -c "SELECT 1"  # Should output: 1
```

### Step 2: Apply Database Migrations

```bash
# From project root
alembic upgrade head

# Verify migration status
alembic current
```

### Step 3: Start Web Server

```bash
# Terminal 1: Start FastAPI server
source venv/bin/activate  # Activate virtual environment if not already active
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Output should show:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete
```

### Step 4: Start Celery Worker

```bash
# Terminal 2: Start Celery worker
source venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info

# Output should show:
# celery@hostname ready.
# Connected to redis://localhost:6379/0
```

### Step 5: Start Celery Beat (Scheduler)

```bash
# Terminal 3: Start Celery beat scheduler
source venv/bin/activate
celery -A app.tasks.celery_app beat --loglevel=info

# Output should show:
# celery beat v5.3.6 is starting.
# Scheduler: Persistent (/app/celerybeat-schedule)
```

### Running with Docker Compose

Alternatively, run all services with Docker:

```bash
# Build images
docker-compose build

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
docker-compose logs -f celery-worker
docker-compose logs -f celery-beat

# Stop services
docker-compose down
```

---

## Testing

### Step 1: Health Check Endpoint

```bash
# Test API is responding
curl http://localhost:8000/health

# Expected response:
# {"status":"ok"}
```

### Step 2: API Documentation

Open in browser: `http://localhost:8000/docs`

This shows:
- All available endpoints
- Request/response schemas
- Try-it-out functionality

### Step 3: Test Root Endpoint

```bash
curl http://localhost:8000/

# Expected response:
# {
#   "message": "SEM-Agent API",
#   "version": "1.0.0",
#   "docs": "/docs"
# }
```

### Step 4: Test Metrics Endpoint

```bash
curl http://localhost:8000/metrics

# Expected response: Prometheus metrics format
# # HELP python_gc_objects_collected_total Objects collected during gc
# ...
```

### Step 5: Verify Database Connection

```bash
# Check logs for database connection message
docker-compose logs api | grep -i database

# Or run Python test
python3 << 'EOF'
from app.core.database import engine
from app.config import settings

try:
    with engine.connect() as conn:
        result = conn.execute("SELECT 1")
        print("Database connection successful!")
except Exception as e:
    print(f"Database connection failed: {e}")
EOF
```

### Step 6: Verify Redis Connection

```bash
# Test Redis connectivity
redis-cli ping

# Expected response: PONG

# Check Redis keys
redis-cli keys "*"

# Monitor Redis activity
redis-cli monitor
```

### Step 7: Test Celery

```bash
# Check Celery worker is connected
celery -A app.tasks.celery_app inspect active

# Expected response: Shows active workers

# Test a task
python3 << 'EOF'
from app.tasks.celery_app import celery_app

# Send a test task
task = celery_app.send_task('app.tasks.report_tasks.test_task')
print(f"Task ID: {task.id}")

# Check task status
from celery.result import AsyncResult
result = AsyncResult(task.id, app=celery_app)
print(f"Task status: {result.status}")
EOF
```

### Step 8: Run Test Suite

```bash
# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=app --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## Troubleshooting

### Common Issues and Solutions

#### Issue 1: "Connection refused" on startup

**Problem:** API fails to start with connection errors.

**Solutions:**
```bash
# 1. Check if PostgreSQL is running
psql -U sem_user -h localhost -d sem_agent -c "SELECT 1"

# 2. Check if Redis is running
redis-cli ping

# 3. Check environment variables
echo $DATABASE_URL
echo $REDIS_URL

# 4. Verify .env file exists and is readable
cat .env | head -5

# 5. Try with explicit URLs
DATABASE_URL=postgresql://sem_user:password@localhost:5432/sem_agent uvicorn app.main:app
```

#### Issue 2: "Could not connect to database"

**Problem:** Database connection fails despite PostgreSQL running.

**Solutions:**
```bash
# 1. Verify PostgreSQL credentials
psql -U sem_user -h localhost -d sem_agent

# 2. Check DATABASE_URL format
# Correct: postgresql://user:password@host:port/database
# Incorrect: postgres://... (deprecated)

# 3. Check PostgreSQL port
netstat -an | grep 5432
# Default is 5432

# 4. Check firewall (if remote PostgreSQL)
telnet 192.168.x.x 5432

# 5. Create database if missing
psql -U postgres -c "CREATE DATABASE sem_agent OWNER sem_user;"
```

#### Issue 3: "Redis connection failed"

**Problem:** Celery or cache operations fail.

**Solutions:**
```bash
# 1. Verify Redis is running
redis-cli ping

# 2. Check Redis port
netstat -an | grep 6379
# Default is 6379

# 3. Verify REDIS_URL
echo $REDIS_URL
# Should be: redis://localhost:6379/0

# 4. Check Redis credentials (if any)
redis-cli -h localhost ping

# 5. Restart Redis
redis-cli shutdown
redis-server  # or: brew services restart redis@7

# 6. Clear Redis cache (CAUTION: destructive)
redis-cli FLUSHALL
```

#### Issue 4: "Module not found" errors

**Problem:** Python import errors when running application.

**Solutions:**
```bash
# 1. Verify virtual environment is activated
which python
# Should be: /path/to/venv/bin/python

# 2. Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Check for missing __init__.py files
find app -type d -exec touch {}/__init__.py \;

# 4. Verify Python version
python --version
# Should be 3.11 or higher
```

#### Issue 5: "Celery worker won't start"

**Problem:** Worker fails to connect to broker.

**Solutions:**
```bash
# 1. Check Redis is running
redis-cli ping

# 2. Verify CELERY_BROKER_URL
echo $CELERY_BROKER_URL

# 3. Test Celery directly
celery -A app.tasks.celery_app worker --loglevel=debug

# 4. Check for syntax errors in tasks
python -m py_compile app/tasks/*.py

# 5. Restart worker with verbose logging
celery -A app.tasks.celery_app worker -l debug
```

#### Issue 6: "Migrations fail or show errors"

**Problem:** Alembic migration issues.

**Solutions:**
```bash
# 1. Check current migration status
alembic current

# 2. Show migration history
alembic history

# 3. Downgrade to previous version (if needed)
alembic downgrade -1

# 4. Create new migration
alembic revision --autogenerate -m "Description"

# 5. Verify migration file syntax
python app/models/__init__.py

# 6. Manual migration (if auto-generation fails)
alembic revision -m "Manual migration"
# Edit migrations/versions/xxxx_manual_migration.py
alembic upgrade head
```

#### Issue 7: "Port already in use"

**Problem:** Port 8000 (or another) is already in use.

**Solutions:**
```bash
# 1. Find process using port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# 2. Kill the process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows

# 3. Use different port
uvicorn app.main:app --port 8001

# 4. Check for stuck Docker containers
docker-compose ps
docker-compose down -v
```

### Log Locations

**Application Logs:**
```bash
# Docker
docker-compose logs api
docker-compose logs celery-worker
docker-compose logs celery-beat

# Direct output (when running directly)
# Displayed in terminal where command was run
```

**System Logs:**
```bash
# macOS
~/Library/Logs/
tail -f /usr/local/var/log/postgresql@15/postgres.log

# Linux
/var/log/postgresql/
journalctl -u postgresql

# Docker Compose
docker-compose logs -f
```

### Debug Mode Setup

To enable detailed debugging:

1. **Set DEBUG environment variable:**
```bash
DEBUG=true
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

2. **Restart application:**
```bash
docker-compose down
docker-compose up -d
```

3. **View detailed logs:**
```bash
docker-compose logs -f api
```

4. **Debug specific module:**
```python
# In Python code
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug("Debug message")
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] All environment variables configured
- [ ] Database migrations tested
- [ ] HTTPS/SSL certificates obtained
- [ ] Secrets stored securely (AWS Secrets Manager, HashiCorp Vault, etc.)
- [ ] Database backups configured
- [ ] Monitoring and alerting set up
- [ ] Rate limiting configured
- [ ] CORS settings configured for production
- [ ] Error tracking (Sentry) configured
- [ ] All tests passing

### Deployment Options

#### Option 1: AWS Deployment with ECS

```bash
# 1. Push image to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account_id>.dkr.ecr.us-east-1.amazonaws.com

docker build -t sem-agent:latest .
docker tag sem-agent:latest <account_id>.dkr.ecr.us-east-1.amazonaws.com/sem-agent:latest
docker push <account_id>.dkr.ecr.us-east-1.amazonaws.com/sem-agent:latest

# 2. Create ECS task definition
# 3. Create ECS service
# 4. Configure RDS for PostgreSQL
# 5. Configure ElastiCache for Redis
```

#### Option 2: Heroku Deployment

```bash
# 1. Login to Heroku
heroku login

# 2. Create app
heroku create sem-agent

# 3. Add PostgreSQL addon
heroku addons:create heroku-postgresql:standard-0

# 4. Add Redis addon
heroku addons:create heroku-redis:premium-0

# 5. Set environment variables
heroku config:set SECRET_KEY=your_secret_key
heroku config:set TOKEN_ENCRYPTION_KEY=your_encryption_key
# ... set all required variables

# 6. Push code
git push heroku main

# 7. Run migrations
heroku run alembic upgrade head
```

#### Option 3: Docker on VPS

```bash
# 1. SSH into VPS
ssh user@your_server.com

# 2. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. Clone repository
git clone https://github.com/YOUR_USERNAME/SEM-Agent.git
cd SEM-Agent

# 4. Create .env file
nano .env  # Add production values

# 5. Build and run
docker-compose build
docker-compose up -d

# 6. Setup reverse proxy (Nginx)
sudo apt-get install nginx
# Configure nginx to proxy to localhost:8000
```

#### Option 4: Kubernetes Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sem-agent-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: api
        image: your-registry/sem-agent:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: sem-agent-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: sem-agent-secrets
              key: redis-url
```

```bash
# Deploy to Kubernetes
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
```

### Production Configuration

**Environment variables:**
```bash
ENVIRONMENT=production
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000

# Use strong passwords in production
DATABASE_URL=postgresql://sem_user:STRONG_PASSWORD@db-server:5432/sem_agent

# Use production Redis endpoint
REDIS_URL=redis://redis-server:6379/0

# Configure monitoring
SENTRY_DSN=https://your-sentry-url@sentry.io/project-id

LOG_LEVEL=WARNING
```

**Security settings:**
```bash
# Strong encryption keys
SECRET_KEY=<cryptographically_secure_random_string>
TOKEN_ENCRYPTION_KEY=<fernet_key>

# CORS for specific domains
# In code: update allow_origins to specific domains

# Rate limiting
# Enable in production
```

### Monitoring & Maintenance

```bash
# Monitor API performance
curl http://localhost:8000/metrics

# Monitor logs
docker-compose logs -f --tail=100

# Monitor database
psql -U sem_user -d sem_agent -c "SELECT * FROM pg_stat_statements LIMIT 10"

# Monitor Redis
redis-cli info stats
redis-cli --stat

# Backup database
pg_dump -U sem_user sem_agent > backup_$(date +%Y%m%d).sql

# Restore database
psql -U sem_user sem_agent < backup_20250201.sql
```

---

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Redis Documentation](https://redis.io/documentation)
- [Celery Documentation](https://docs.celeryproject.io/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Docker Documentation](https://docs.docker.com/)
- [Google Ads API](https://developers.google.com/google-ads/api/)
- [Slack API Documentation](https://api.slack.com/)
- [Google Gemini API](https://ai.google.dev/)

---

---

# 한국어 배포 가이드

### 목차
1. [필수 요구사항](#필수-요구사항)
2. [환경 설정](#환경-설정)
3. [OAuth 앱 등록](#oauth-앱-등록)
4. [데이터베이스 설정](#데이터베이스-설정)
5. [첫 실행](#첫-실행)
6. [테스트](#테스트)
7. [문제 해결](#문제-해결)
8. [프로덕션 배포](#프로덕션-배포)

---

## 필수 요구사항

SEM-Agent를 배포하기 전에 다음 항목이 설치되어 있는지 확인하세요.

### 시스템 요구사항

| 구성 요소 | 버전 | 설명 |
|---------|------|------|
| Python | 3.11+ | 핵심 언어 |
| Docker | 최신 | 컨테이너 런타임 |
| Docker Compose | 2.0+ | 컨테이너 오케스트레이션 |
| PostgreSQL | 15+ | 주 데이터베이스 |
| Redis | 7+ | 캐시 및 메시지 브로커 |
| Git | 최신 | 버전 관리 |

### 설치 명령어

**macOS (Homebrew):**
```bash
# Python 3.11+ 설치
brew install python@3.11

# Docker Desktop 설치 (Docker & Docker Compose 포함)
brew install --cask docker

# PostgreSQL 15 설치
brew install postgresql@15

# Redis 7 설치
brew install redis@7
```

**Ubuntu/Debian:**
```bash
# 패키지 관리자 업데이트
sudo apt-get update

# Python 3.11+ 설치
sudo apt-get install python3.11 python3.11-venv python3.11-dev

# Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# PostgreSQL 15 설치
sudo apt-get install postgresql-15

# Redis 7 설치
sudo apt-get install redis-server=7:*
```

**CentOS/RHEL:**
```bash
# Python 3.11+ 설치
sudo dnf install python3.11 python3.11-devel

# Docker 설치
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install docker-ce docker-ce-cli

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# PostgreSQL 15 설치
sudo dnf install postgresql15-server

# Redis 7 설치
sudo dnf install redis
```

### 검증

```bash
# Python 버전 확인
python3 --version          # 3.11 이상이어야 함

# Docker 확인
docker --version
docker-compose --version

# PostgreSQL 확인
psql --version            # 15 이상이어야 함

# Redis 확인
redis-cli --version       # 7 이상이어야 함
```

---

## 환경 설정

### 단계 1: 저장소 클론

```bash
# 저장소 클론
git clone https://github.com/YOUR_USERNAME/SEM-Agent.git
cd SEM-Agent

# 가상 환경 생성
python3.11 -m venv venv

# 가상 환경 활성화
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# pip, setuptools, wheel 업그레이드
pip install --upgrade pip setuptools wheel
```

### 단계 2: 의존성 설치

```bash
# Python 패키지 설치
pip install -r requirements.txt

# 설치 확인
pip list | grep -E "fastapi|sqlalchemy|celery|redis"
```

### 단계 3: 환경 설정 파일 생성

```bash
# 예제 환경 파일 복사
cp .env.example .env

# 편집기로 .env 파일 수정
nano .env  # 또는 선호하는 편집기 사용
```

### 단계 4: 보안 키 생성

JWT 토큰과 API 토큰 암호화를 위한 두 개의 암호화 키가 필요합니다.

```bash
# SECRET_KEY 생성 (JWT 토큰용)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# 출력: abc123def456... (복사)

# TOKEN_ENCRYPTION_KEY 생성 (API 토큰 암호화용, Fernet)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 출력: gAAAAABl... (복사)
```

이 값들을 `.env` 파일에 추가하세요:

```bash
SECRET_KEY=<생성한_secret_key>
TOKEN_ENCRYPTION_KEY=<생성한_encryption_key>
```

### 단계 5: 데이터베이스 자격증명 설정

`.env` 파일을 편집하여 PostgreSQL 연결 정보를 설정합니다:

```bash
# 데이터베이스 설정
DATABASE_URL=postgresql://sem_user:sem_password@localhost:5432/sem_agent
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

**프로덕션 환경**에서는 강력한 비밀번호와 보안 PostgreSQL 연결을 사용하세요:

```bash
DATABASE_URL=postgresql://sem_user:강력한_비밀번호@db.example.com:5432/sem_agent
```

### 단계 6: Redis 연결 설정

```bash
# Redis 설정
REDIS_URL=redis://localhost:6379/0

# 프로덕션 환경 (인증 사용):
REDIS_URL=redis://:비밀번호@redis.example.com:6379/0
```

### 단계 7: 애플리케이션 설정

```bash
# FastAPI 설정
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false
ENVIRONMENT=production

# 개발 환경:
DEBUG=true
ENVIRONMENT=development

# 로깅
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Celery 설정
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TIMEZONE=Asia/Seoul
```

---

## OAuth 앱 등록

### Google Cloud Console - Google Ads API

#### 단계 1: Google Cloud 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/) 방문
2. **프로젝트 선택** → **새 프로젝트** 클릭
3. 프로젝트 이름 입력: `SEM-Agent` (또는 선호하는 이름)
4. **만들기** 클릭
5. 프로젝트 생성 대기 (2-3분)

#### 단계 2: 필수 API 활성화

1. Cloud Console에서 **API 및 서비스** → **라이브러리** 이동
2. 다음 API를 검색하여 활성화:
   - **Google Ads API** (v16)
   - **Google Drive API** (파일 관리용)
   - **Google Sheets API** (데이터 내보내기용)

3. 각 API를 클릭하여 **활성화** 선택

#### 단계 3: OAuth 자격증명 생성

1. **API 및 서비스** → **자격증명** 이동
2. **자격증명 만들기** → **OAuth 2.0 클라이언트 ID** 클릭
3. OAuth 동의 화면 설정 요청 시:
   - **내부** (테스트용) 또는 **외부** 선택
   - 애플리케이션 정보 입력:
     - 앱 이름: `SEM-Agent`
     - 사용자 지원 이메일: your-email@example.com
   - 범위 추가:
     - `https://www.googleapis.com/auth/adwords`
     - `https://www.googleapis.com/auth/drive`
   - **저장 후 계속** → **저장 후 계속** → **대시보드로 돌아가기**

4. 자격증명 페이지에서 **자격증명 만들기** → **OAuth 2.0 클라이언트 ID** 클릭
5. **웹 애플리케이션** 선택
6. 승인된 리디렉션 URI 추가:
   - `http://localhost:8000/oauth/google/callback` (개발)
   - `https://your-domain.com/oauth/google/callback` (프로덕션)
7. **만들기** 클릭

#### 단계 4: 자격증명 가져오기

1. 생성된 자격증명 클릭
2. 다음 항목 복사 및 저장:
   - **클라이언트 ID** → `GOOGLE_CLIENT_ID`
   - **클라이언트 보안 정보** → `GOOGLE_CLIENT_SECRET`

3. `.env` 파일에 추가:
```bash
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/google/callback
```

#### 단계 5: 개발자 토큰 받기

1. [Google Ads API 문서](https://developers.google.com/google-ads/api/docs/first-call/overview) 방문
2. **개발자 토큰 받기** 섹션 따르기
3. [Google Ads API 센터](https://ads.google.com/aw/apicenter) 이동
4. **도구 및 설정** → **개발자 토큰** 클릭
5. 개발자 토큰 복사
6. 필요시 액세스 요청 (24-48시간 소요)

승인 후 `.env` 파일에 추가하세요:

```bash
GOOGLE_DEVELOPER_TOKEN=your_developer_token
GOOGLE_LOGIN_CUSTOMER_ID=1234567890  # Google Ads 고객 ID
```

### Slack 앱 - 봇 및 OAuth 설정

#### 단계 1: Slack 앱 생성

1. [Slack API 콘솔](https://api.slack.com/apps) 방문
2. **새 앱 만들기** → **처음부터** 클릭
3. **앱 이름** 입력: `SEM-Agent`
4. **워크스페이스** 선택
5. **앱 만들기** 클릭

#### 단계 2: Slack 권한 설정

1. 왼쪽 메뉴에서 **OAuth 및 권한** 이동
2. **범위** → **봇 토큰 범위** 아래 추가:
   - `chat:write` - 메시지 전송
   - `commands` - 슬래시 명령어 등록
   - `app_mentions:read` - 멘션 수신
   - `channels:read` - 채널 나열
   - `users:read` - 사용자 정보 조회
   - `team:read` - 워크스페이스 정보 조회
   - `incoming-webhook` - 채널에 게시
   - `interactive_message_input:view` - 인터랙티브 버튼

3. 페이지 상단 **워크스페이스에 앱 설치** 클릭
4. 권한 검토 후 **허용** 클릭
5. **봇 사용자 OAuth 토큰** (xoxb-로 시작) 복사

#### 단계 3: 서명 보안 및 앱 토큰 받기

1. **기본 정보** 이동
2. **앱 자격증명** 아래:
   - **서명 보안** 복사 → `SLACK_SIGNING_SECRET`
   - **클라이언트 ID** 복사 → `SLACK_CLIENT_ID`
   - **클라이언트 보안 정보** 복사 → `SLACK_CLIENT_SECRET`

3. **앱 레벨 토큰** 이동
4. **토큰 및 범위 생성** 클릭
5. 범위 추가: `connections:write`
6. 토큰 생성 및 복사 → `SLACK_APP_TOKEN`

#### 단계 4: OAuth 리디렉션 설정

1. **OAuth 및 권한** 이동
2. **리디렉션 URL** 아래 추가:
   - `http://localhost:8000/oauth/slack/callback` (개발)
   - `https://your-domain.com/oauth/slack/callback` (프로덕션)
3. **URL 저장** 클릭

#### 단계 5: 슬래시 명령어 추가

1. **슬래시 명령어** 이동
2. **새 명령어 만들기** 클릭 (각각):

**명령어 1: /sem-config**
- 명령어: `/sem-config`
- 요청 URL: `http://localhost:8000/slack/commands/config`
- 설명: 리포트 설정 변경
- 사용 힌트: `[frequency] [time]`

**명령어 2: /sem-report**
- 명령어: `/sem-report`
- 요청 URL: `http://localhost:8000/slack/commands/report`
- 설명: 즉시 리포트 생성
- 사용 힌트: `[period]` (daily, weekly, monthly)

**명령어 3: /sem-status**
- 명령어: `/sem-status`
- 요청 URL: `http://localhost:8000/slack/commands/status`
- 설명: 연결 상태 확인
- 사용 힌트: 매개변수 없음

#### 단계 6: .env 파일에 추가

```bash
SLACK_CLIENT_ID=your_slack_client_id
SLACK_CLIENT_SECRET=your_slack_client_secret
SLACK_SIGNING_SECRET=your_slack_signing_secret
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_REDIRECT_URI=http://localhost:8000/oauth/slack/callback
SLACK_ALERT_CHANNEL=#alerts  # 알림용 채널
```

### Google Gemini AI - API 키

1. [Google AI Studio](https://makersuite.google.com/app/apikey) 방문
2. **API 키 만들기** 클릭
3. API 키 복사
4. `.env` 파일에 추가:

```bash
GEMINI_API_KEY=your_gemini_api_key
GEMINI_DEFAULT_MODEL=gemini-1.5-flash
GEMINI_PRO_MODEL=gemini-1.5-pro
```

### 완전한 .env 예제

모든 등록 후 `.env` 파일은 다음과 같아야 합니다:

```bash
# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false
ENVIRONMENT=production

# Database
DATABASE_URL=postgresql://sem_user:password@localhost:5432/sem_agent
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379/0

# Slack
SLACK_CLIENT_ID=1234567890.1234567890
SLACK_CLIENT_SECRET=abcdef123456
SLACK_SIGNING_SECRET=abcdef123456
SLACK_APP_TOKEN=xapp-1-XXXXXX
SLACK_BOT_TOKEN=xoxb-1-XXXXXX
SLACK_REDIRECT_URI=http://localhost:8000/oauth/slack/callback
SLACK_ALERT_CHANNEL=#alerts

# Google OAuth
GOOGLE_CLIENT_ID=1234567890-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-abcdefg
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/google/callback

# Google Ads
GOOGLE_DEVELOPER_TOKEN=1234567890ABCDEFG
GOOGLE_LOGIN_CUSTOMER_ID=1234567890

# Gemini AI
GEMINI_API_KEY=AIzaSyDxxxxxxxxxxxxxxxxx
GEMINI_DEFAULT_MODEL=gemini-1.5-flash
GEMINI_PRO_MODEL=gemini-1.5-pro

# Security
SECRET_KEY=your_secret_key_here
TOKEN_ENCRYPTION_KEY=your_encryption_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TIMEZONE=Asia/Seoul

# Monitoring
SENTRY_DSN=
LOG_LEVEL=INFO
```

---

## 데이터베이스 설정

### 단계 1: PostgreSQL 시작

**Docker 사용 (권장):**
```bash
docker-compose up -d postgres
```

**Homebrew 사용 (macOS):**
```bash
# PostgreSQL 서비스 시작
brew services start postgresql@15

# 실행 확인
psql -U postgres -h localhost
```

**systemd 사용 (Linux):**
```bash
# PostgreSQL 서비스 시작
sudo systemctl start postgresql

# 부팅 시 자동 시작 설정
sudo systemctl enable postgresql
```

### 단계 2: 데이터베이스 및 사용자 생성

```bash
# PostgreSQL에 연결
psql -U postgres -h localhost

# PostgreSQL 셸에서 실행:
```

```sql
-- 데이터베이스 사용자 생성
CREATE USER sem_user WITH PASSWORD 'sem_password';

-- 데이터베이스 생성
CREATE DATABASE sem_agent OWNER sem_user;

-- 권한 부여
GRANT ALL PRIVILEGES ON DATABASE sem_agent TO sem_user;

-- 새 데이터베이스로 연결
\c sem_agent

-- 스키마 권한 부여
GRANT ALL PRIVILEGES ON SCHEMA public TO sem_user;

-- 종료
\q
```

### 단계 3: 데이터베이스 연결 확인

```bash
# 연결 테스트
psql -U sem_user -h localhost -d sem_agent

# 성공적으로 연결되어야 함
# \q로 종료
```

### 단계 4: Alembic 마이그레이션 생성

```bash
# 프로젝트 루트로 이동
cd /path/to/SEM-Agent

# Alembic 초기화 (아직 안 되었다면)
alembic init migrations

# 초기 마이그레이션 생성
alembic revision --autogenerate -m "Initial schema"

# 마이그레이션 생성 확인
ls -la migrations/versions/
```

### 단계 5: 마이그레이션 실행

```bash
# 데이터베이스에 마이그레이션 적용
alembic upgrade head

# 마이그레이션 상태 확인
alembic current
alembic history
```

### 단계 6: 데이터베이스 스키마 확인

```bash
# 데이터베이스에 연결
psql -U sem_user -h localhost -d sem_agent

# 테이블 목록
\dt

# 다음과 같은 테이블이 표시되어야 함:
# - tenants
# - google_ads_integrations
# - slack_integrations
# - keywords
# - reports
# - approval_requests
# 등등

# 종료
\q
```

### 데이터베이스 문제 해결

**연결 거부:**
```bash
# PostgreSQL 실행 확인
psql -U postgres -h localhost

# 실패하면 서비스 다시 시작:
# macOS: brew services restart postgresql@15
# Linux: sudo systemctl restart postgresql
```

**"서버에 연결할 수 없음":**
```bash
# PostgreSQL 포트 확인
netstat -an | grep 5432  # macOS/Linux
netstat -ano | findstr 5432  # Windows

# 기본 포트는 5432, 다르면 DATABASE_URL 수정
```

**권한 거부:**
```bash
# 사용자 비밀번호 확인
psql -U sem_user -h localhost -d sem_agent

# 필요시 비밀번호 변경:
psql -U postgres -h localhost
ALTER USER sem_user WITH PASSWORD 'new_password';
```

---

## 첫 실행

### 단계 1: 지원 서비스 시작

```bash
# 옵션 A: Docker Compose 사용 (권장)
docker-compose up -d postgres redis

# 옵션 B: 서비스 개별 시작
# 터미널 1: PostgreSQL (Homebrew 사용시)
brew services start postgresql@15

# 터미널 2: Redis (Homebrew 사용시)
brew services start redis@7

# 서비스 실행 확인
docker-compose ps
# 또는
redis-cli ping      # PONG 출력되어야 함
psql -U sem_user -d sem_agent -c "SELECT 1"  # 1 출력되어야 함
```

### 단계 2: 데이터베이스 마이그레이션 적용

```bash
# 프로젝트 루트에서
alembic upgrade head

# 마이그레이션 상태 확인
alembic current
```

### 단계 3: 웹 서버 시작

```bash
# 터미널 1: FastAPI 서버 시작
source venv/bin/activate  # 가상 환경 활성화 (아직이면)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 다음과 같이 표시되어야 함:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete
```

### 단계 4: Celery 워커 시작

```bash
# 터미널 2: Celery 워커 시작
source venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info

# 다음과 같이 표시되어야 함:
# celery@hostname ready.
# Connected to redis://localhost:6379/0
```

### 단계 5: Celery Beat (스케줄러) 시작

```bash
# 터미널 3: Celery beat 스케줄러 시작
source venv/bin/activate
celery -A app.tasks.celery_app beat --loglevel=info

# 다음과 같이 표시되어야 함:
# celery beat v5.3.6 is starting.
# Scheduler: Persistent (/app/celerybeat-schedule)
```

### Docker Compose를 사용한 실행

또는 Docker로 모든 서비스를 실행하세요:

```bash
# 이미지 빌드
docker-compose build

# 모든 서비스 시작
docker-compose up -d

# 상태 확인
docker-compose ps

# 로그 보기
docker-compose logs -f api
docker-compose logs -f celery-worker
docker-compose logs -f celery-beat

# 서비스 중지
docker-compose down
```

---

## 테스트

### 단계 1: 헬스 체크 엔드포인트

```bash
# API 응답 확인
curl http://localhost:8000/health

# 예상 응답:
# {"status":"ok"}
```

### 단계 2: API 문서

브라우저에서 열기: `http://localhost:8000/docs`

다음이 표시됩니다:
- 모든 사용 가능한 엔드포인트
- 요청/응답 스키마
- 시도(Try-it-out) 기능

### 단계 3: 루트 엔드포인트 테스트

```bash
curl http://localhost:8000/

# 예상 응답:
# {
#   "message": "SEM-Agent API",
#   "version": "1.0.0",
#   "docs": "/docs"
# }
```

### 단계 4: 메트릭 엔드포인트 테스트

```bash
curl http://localhost:8000/metrics

# 예상 응답: Prometheus 메트릭 형식
# # HELP python_gc_objects_collected_total Objects collected during gc
# ...
```

### 단계 5: 데이터베이스 연결 확인

```bash
# 데이터베이스 연결 메시지 확인
docker-compose logs api | grep -i database

# 또는 Python 테스트
python3 << 'EOF'
from app.core.database import engine
from app.config import settings

try:
    with engine.connect() as conn:
        result = conn.execute("SELECT 1")
        print("데이터베이스 연결 성공!")
except Exception as e:
    print(f"데이터베이스 연결 실패: {e}")
EOF
```

### 단계 6: Redis 연결 확인

```bash
# Redis 연결성 테스트
redis-cli ping

# 예상 응답: PONG

# Redis 키 확인
redis-cli keys "*"

# Redis 활동 모니터링
redis-cli monitor
```

### 단계 7: Celery 테스트

```bash
# Celery 워커 연결 확인
celery -A app.tasks.celery_app inspect active

# 예상 응답: 활성 워커 표시

# 작업 테스트
python3 << 'EOF'
from app.tasks.celery_app import celery_app

# 테스트 작업 전송
task = celery_app.send_task('app.tasks.report_tasks.test_task')
print(f"작업 ID: {task.id}")

# 작업 상태 확인
from celery.result import AsyncResult
result = AsyncResult(task.id, app=celery_app)
print(f"작업 상태: {result.status}")
EOF
```

### 단계 8: 테스트 스위트 실행

```bash
# 모든 테스트 실행
pytest tests/ -v

# 커버리지가 포함된 테스트
pytest tests/ --cov=app --cov-report=html

# 커버리지 리포트 보기
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## 문제 해결

### 일반적인 문제 및 해결방법

#### 문제 1: 시작 시 "연결 거부" 오류

**문제:** API가 연결 오류로 시작 실패.

**해결방법:**
```bash
# 1. PostgreSQL 실행 확인
psql -U sem_user -h localhost -d sem_agent -c "SELECT 1"

# 2. Redis 실행 확인
redis-cli ping

# 3. 환경 변수 확인
echo $DATABASE_URL
echo $REDIS_URL

# 4. .env 파일 확인
cat .env | head -5

# 5. 명시적 URL로 시도
DATABASE_URL=postgresql://sem_user:password@localhost:5432/sem_agent uvicorn app.main:app
```

#### 문제 2: "데이터베이스에 연결할 수 없음" 오류

**문제:** PostgreSQL 실행 중에도 연결 실패.

**해결방법:**
```bash
# 1. PostgreSQL 자격증명 확인
psql -U sem_user -h localhost -d sem_agent

# 2. DATABASE_URL 형식 확인
# 올바름: postgresql://user:password@host:port/database
# 오류: postgres://... (deprecated)

# 3. PostgreSQL 포트 확인
netstat -an | grep 5432
# 기본 포트는 5432

# 4. 방화벽 확인 (원격 PostgreSQL인 경우)
telnet 192.168.x.x 5432

# 5. 데이터베이스 없으면 생성
psql -U postgres -c "CREATE DATABASE sem_agent OWNER sem_user;"
```

#### 문제 3: "Redis 연결 실패" 오류

**문제:** Celery 또는 캐시 작업 실패.

**해결방법:**
```bash
# 1. Redis 실행 확인
redis-cli ping

# 2. Redis 포트 확인
netstat -an | grep 6379
# 기본 포트는 6379

# 3. REDIS_URL 확인
echo $REDIS_URL
# 형식: redis://localhost:6379/0

# 4. Redis 자격증명 확인 (있는 경우)
redis-cli -h localhost ping

# 5. Redis 다시 시작
redis-cli shutdown
redis-server  # 또는: brew services restart redis@7

# 6. Redis 캐시 비우기 (주의: 파괴적)
redis-cli FLUSHALL
```

#### 문제 4: "모듈을 찾을 수 없음" 오류

**문제:** 애플리케이션 실행 시 Python import 오류.

**해결방법:**
```bash
# 1. 가상 환경 활성화 확인
which python
# 출력: /path/to/venv/bin/python

# 2. 의존성 재설치
pip install --upgrade pip
pip install -r requirements.txt

# 3. 누락된 __init__.py 파일 확인
find app -type d -exec touch {}/__init__.py \;

# 4. Python 버전 확인
python --version
# 3.11 이상이어야 함
```

#### 문제 5: "Celery 워커 시작 안 됨" 오류

**문제:** 워커가 브로커에 연결 실패.

**해결방법:**
```bash
# 1. Redis 실행 확인
redis-cli ping

# 2. CELERY_BROKER_URL 확인
echo $CELERY_BROKER_URL

# 3. Celery 직접 테스트
celery -A app.tasks.celery_app worker --loglevel=debug

# 4. 작업 구문 오류 확인
python -m py_compile app/tasks/*.py

# 5. 자세한 로깅으로 워커 다시 시작
celery -A app.tasks.celery_app worker -l debug
```

#### 문제 6: "마이그레이션 실패" 오류

**문제:** Alembic 마이그레이션 문제.

**해결방법:**
```bash
# 1. 현재 마이그레이션 상태 확인
alembic current

# 2. 마이그레이션 이력 표시
alembic history

# 3. 이전 버전으로 다운그레이드 (필요시)
alembic downgrade -1

# 4. 새 마이그레이션 생성
alembic revision --autogenerate -m "설명"

# 5. 마이그레이션 파일 구문 확인
python app/models/__init__.py

# 6. 자동 생성 실패 시 수동 마이그레이션
alembic revision -m "수동 마이그레이션"
# migrations/versions/xxxx_manual_migration.py 편집
alembic upgrade head
```

#### 문제 7: "포트 이미 사용 중" 오류

**문제:** 8000 포트 (또는 다른 포트)가 이미 사용 중.

**해결방법:**
```bash
# 1. 포트를 사용 중인 프로세스 찾기
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# 2. 프로세스 종료
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows

# 3. 다른 포트 사용
uvicorn app.main:app --port 8001

# 4. 중단된 Docker 컨테이너 확인
docker-compose ps
docker-compose down -v
```

### 로그 위치

**애플리케이션 로그:**
```bash
# Docker
docker-compose logs api
docker-compose logs celery-worker
docker-compose logs celery-beat

# 직접 실행 (명령어를 실행한 터미널에 표시)
# 터미널 출력에 표시
```

**시스템 로그:**
```bash
# macOS
~/Library/Logs/
tail -f /usr/local/var/log/postgresql@15/postgres.log

# Linux
/var/log/postgresql/
journalctl -u postgresql

# Docker Compose
docker-compose logs -f
```

### 디버그 모드 설정

자세한 디버깅을 활성화하려면:

1. **DEBUG 환경 변수 설정:**
```bash
DEBUG=true
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

2. **애플리케이션 다시 시작:**
```bash
docker-compose down
docker-compose up -d
```

3. **자세한 로그 보기:**
```bash
docker-compose logs -f api
```

4. **특정 모듈 디버그:**
```python
# Python 코드에서
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug("디버그 메시지")
```

---

## 프로덕션 배포

### 배포 전 체크리스트

- [ ] 모든 환경 변수 설정 완료
- [ ] 데이터베이스 마이그레이션 테스트 완료
- [ ] HTTPS/SSL 인증서 획득 완료
- [ ] 보안이 필요한 항목은 보안 저장소에 저장 (AWS Secrets Manager, HashiCorp Vault 등)
- [ ] 데이터베이스 백업 설정 완료
- [ ] 모니터링 및 알림 설정 완료
- [ ] 속도 제한 설정 완료
- [ ] 프로덕션 환경을 위한 CORS 설정 완료
- [ ] 에러 추적 (Sentry) 설정 완료
- [ ] 모든 테스트 통과 확인

### 배포 옵션

#### 옵션 1: AWS ECS를 사용한 배포

```bash
# 1. ECR에 이미지 푸시
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account_id>.dkr.ecr.us-east-1.amazonaws.com

docker build -t sem-agent:latest .
docker tag sem-agent:latest <account_id>.dkr.ecr.us-east-1.amazonaws.com/sem-agent:latest
docker push <account_id>.dkr.ecr.us-east-1.amazonaws.com/sem-agent:latest

# 2. ECS 작업 정의 생성
# 3. ECS 서비스 생성
# 4. RDS에서 PostgreSQL 구성
# 5. ElastiCache에서 Redis 구성
```

#### 옵션 2: Heroku 배포

```bash
# 1. Heroku 로그인
heroku login

# 2. 앱 생성
heroku create sem-agent

# 3. PostgreSQL 애드온 추가
heroku addons:create heroku-postgresql:standard-0

# 4. Redis 애드온 추가
heroku addons:create heroku-redis:premium-0

# 5. 환경 변수 설정
heroku config:set SECRET_KEY=your_secret_key
heroku config:set TOKEN_ENCRYPTION_KEY=your_encryption_key
# ... 모든 필수 변수 설정

# 6. 코드 푸시
git push heroku main

# 7. 마이그레이션 실행
heroku run alembic upgrade head
```

#### 옵션 3: VPS의 Docker 배포

```bash
# 1. VPS에 SSH 접속
ssh user@your_server.com

# 2. Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. 저장소 클론
git clone https://github.com/YOUR_USERNAME/SEM-Agent.git
cd SEM-Agent

# 4. .env 파일 생성
nano .env  # 프로덕션 값 추가

# 5. 빌드 및 실행
docker-compose build
docker-compose up -d

# 6. 리버스 프록시 설정 (Nginx)
sudo apt-get install nginx
# localhost:8000으로 프록시하도록 nginx 구성
```

#### 옵션 4: Kubernetes 배포

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sem-agent-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: api
        image: your-registry/sem-agent:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: sem-agent-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: sem-agent-secrets
              key: redis-url
```

```bash
# Kubernetes에 배포
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
```

### 프로덕션 설정

**환경 변수:**
```bash
ENVIRONMENT=production
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000

# 프로덕션에서는 강력한 비밀번호 사용
DATABASE_URL=postgresql://sem_user:강력한_비밀번호@db-server:5432/sem_agent

# 프로덕션 Redis 엔드포인트 사용
REDIS_URL=redis://redis-server:6379/0

# 모니터링 설정
SENTRY_DSN=https://your-sentry-url@sentry.io/project-id

LOG_LEVEL=WARNING
```

**보안 설정:**
```bash
# 강력한 암호화 키
SECRET_KEY=<암호학적으로_안전한_난수>
TOKEN_ENCRYPTION_KEY=<fernet_key>

# CORS를 특정 도메인으로 제한
# 코드에서: allow_origins를 특정 도메인으로 업데이트

# 속도 제한
# 프로덕션에서 활성화
```

### 모니터링 & 유지보수

```bash
# API 성능 모니터링
curl http://localhost:8000/metrics

# 로그 모니터링
docker-compose logs -f --tail=100

# 데이터베이스 모니터링
psql -U sem_user -d sem_agent -c "SELECT * FROM pg_stat_statements LIMIT 10"

# Redis 모니터링
redis-cli info stats
redis-cli --stat

# 데이터베이스 백업
pg_dump -U sem_user sem_agent > backup_$(date +%Y%m%d).sql

# 데이터베이스 복원
psql -U sem_user sem_agent < backup_20250201.sql
```

---

## 추가 리소스

- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [PostgreSQL 문서](https://www.postgresql.org/docs/)
- [Redis 문서](https://redis.io/documentation)
- [Celery 문서](https://docs.celeryproject.io/)
- [Alembic 문서](https://alembic.sqlalchemy.org/)
- [Docker 문서](https://docs.docker.com/)
- [Google Ads API](https://developers.google.com/google-ads/api/)
- [Slack API 문서](https://api.slack.com/)
- [Google Gemini API](https://ai.google.dev/)
