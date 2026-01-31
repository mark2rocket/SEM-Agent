# Database Migration Quick Start

## First Time Setup

### 1. Start PostgreSQL

**Using Docker:**
```bash
docker-compose up -d postgres
```

**Using local PostgreSQL:**
```bash
# macOS
brew services start postgresql@14

# Linux
sudo systemctl start postgresql
```

### 2. Create Database

```bash
# Connect to PostgreSQL
psql -h localhost -U postgres

# Create database and user
CREATE DATABASE semdb;
CREATE USER semuser WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE semdb TO semuser;
\q
```

### 3. Configure Environment

```bash
# Copy example .env
cp .env.example .env

# Edit .env and set DATABASE_URL
DATABASE_URL=postgresql://semuser:your_password@localhost:5432/semdb
```

### 4. Run Initial Migration

```bash
# Apply all migrations
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade  -> 5785681901d3, Initial schema
```

### 5. Verify Migration

```bash
# Run verification script
python scripts/verify_migration.py

# Expected output:
# ✅ All checks passed!
```

## Common Commands

### Check Migration Status

```bash
# Show current version
alembic current

# Show migration history
alembic history --verbose

# Show pending migrations
alembic upgrade head --sql
```

### Apply Migrations

```bash
# Apply all pending
alembic upgrade head

# Apply one step
alembic upgrade +1

# Apply to specific revision
alembic upgrade 5785681901d3
```

### Rollback Migrations

```bash
# Rollback one step
alembic downgrade -1

# Rollback all
alembic downgrade base

# Rollback to specific revision
alembic downgrade 5785681901d3
```

### Create New Migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "Add new column"

# Create empty migration
alembic revision -m "Custom migration"
```

## Troubleshooting

### Connection Refused

```bash
# Check if PostgreSQL is running
pg_isready -h localhost -p 5432

# If not, start it (see step 1)
```

### Permission Denied

```sql
-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE semdb TO semuser;
GRANT ALL PRIVILEGES ON SCHEMA public TO semuser;
```

### Wrong Current Version

```bash
# Check current version
alembic current

# Force stamp to head (use carefully!)
alembic stamp head
```

## Quick Verification

```bash
# Connect to database
psql -h localhost -U semuser -d semdb

# List all tables (should show 9 tables)
\dt

# Exit
\q
```

## Production Deployment

```bash
# 1. ALWAYS backup first
pg_dump -Fc -h localhost -U semuser -d semdb > backup_$(date +%Y%m%d).dump

# 2. Apply migrations
alembic upgrade head

# 3. Verify
python scripts/verify_migration.py

# 4. If issues, restore backup
pg_restore -h localhost -U semuser -d semdb backup_20260201.dump
```

## Docker Quick Start

```bash
# Start all services (includes migration)
docker-compose up -d

# Or run migration manually
docker-compose run --rm app alembic upgrade head

# Verify
docker-compose run --rm app python scripts/verify_migration.py
```

## Next Steps

After migration is complete:
1. Review [DEPLOYMENT.md](docs/DEPLOYMENT.md) for full deployment guide
2. Configure OAuth credentials in `.env`
3. Start the application: `uvicorn app.main:app --reload`

## Schema Overview

The initial migration creates:

- **tenants** - Slack workspaces
- **users** - Tenant users
- **oauth_tokens** - OAuth credentials
- **google_ads_accounts** - Linked Google Ads accounts
- **performance_thresholds** - Detection settings
- **report_schedules** - Report scheduling
- **report_history** - Generated reports
- **keyword_candidates** - Detected search terms
- **approval_requests** - Keyword approval workflow

For detailed schema documentation, see [DATABASE_MIGRATION.md](docs/DATABASE_MIGRATION.md).
