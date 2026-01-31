# Database Migration Guide

## Overview

This guide covers database migration management using Alembic for the SEM-Agent application.

## Initial Setup

The initial database schema migration has been created and is ready to apply.

**Migration file:** `migrations/versions/5785681901d3_initial_schema.py`

**Includes:**
- 8 database tables (tenants, users, oauth_tokens, google_ads_accounts, performance_thresholds, report_schedules, report_history, keyword_candidates, approval_requests)
- All foreign key constraints
- All required indexes
- 4 enum types (KeywordStatus, OAuthProvider, ReportFrequency, ApprovalAction)

## Running Migrations

### Prerequisites

1. PostgreSQL database running and accessible
2. Environment variables configured in `.env`:
   ```bash
   DATABASE_URL=postgresql://user:password@host:port/database
   ```

### Apply Migrations

**Development:**
```bash
# Apply all pending migrations
alembic upgrade head

# Show current revision
alembic current

# Show migration history
alembic history --verbose
```

**Production:**
```bash
# ALWAYS backup database first
pg_dump -h localhost -U user -d semdb > backup_$(date +%Y%m%d_%H%M%S).sql

# Apply migrations
alembic upgrade head

# Verify
alembic current
```

### Rollback Migrations

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade 5785681901d3

# Rollback all migrations
alembic downgrade base
```

## Creating New Migrations

### Auto-generate from Model Changes

```bash
# After modifying models in app/models/
alembic revision --autogenerate -m "Description of changes"

# Review the generated migration file in migrations/versions/
# Edit if needed to ensure correctness

# Apply the migration
alembic upgrade head
```

### Manual Migration

```bash
# Create empty migration file
alembic revision -m "Description of changes"

# Edit migrations/versions/{revision}_description.py
# Add upgrade() and downgrade() operations

# Apply the migration
alembic upgrade head
```

## Migration in Docker

### Development with Docker Compose

```bash
# Start database
docker-compose up -d postgres

# Run migrations in app container
docker-compose run --rm app alembic upgrade head
```

### Production with Docker

```dockerfile
# Migrations run automatically via entrypoint.sh
# Or manually:
docker exec -it sem-agent-app alembic upgrade head
```

## Database Schema Verification

After applying migrations, verify the schema:

```sql
-- Connect to database
psql -h localhost -U user -d semdb

-- List all tables
\dt

-- Check specific table structure
\d tenants
\d keyword_candidates
\d approval_requests

-- Verify foreign keys
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';

-- Verify indexes
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

## Common Issues

### Issue: Connection Refused

**Error:** `connection to server at "localhost", port 5432 failed: Connection refused`

**Solution:**
```bash
# Check if PostgreSQL is running
pg_isready -h localhost -p 5432

# Start PostgreSQL (macOS)
brew services start postgresql@14

# Start PostgreSQL (Linux)
sudo systemctl start postgresql

# Start PostgreSQL (Docker)
docker-compose up -d postgres
```

### Issue: Permission Denied

**Error:** `permission denied for database`

**Solution:**
```sql
-- Grant necessary privileges
GRANT ALL PRIVILEGES ON DATABASE semdb TO user;
GRANT ALL PRIVILEGES ON SCHEMA public TO user;
```

### Issue: Migration Already Applied

**Error:** `Target database is not up to date`

**Solution:**
```bash
# Check current version
alembic current

# Stamp database to specific revision (use carefully!)
alembic stamp head
```

### Issue: Enum Type Already Exists

**Error:** `type "enumname" already exists`

**Solution:** This happens when migration fails halfway. Options:

1. **Recommended:** Rollback and reapply
   ```bash
   alembic downgrade -1
   alembic upgrade head
   ```

2. **Manual cleanup** (advanced):
   ```sql
   DROP TYPE IF EXISTS keywordstatus CASCADE;
   DROP TYPE IF EXISTS oauthprovider CASCADE;
   DROP TYPE IF EXISTS reportfrequency CASCADE;
   DROP TYPE IF EXISTS approvalaction CASCADE;
   ```

## Migration Best Practices

1. **Always backup before production migrations**
   ```bash
   pg_dump -Fc -h host -U user -d semdb > backup.dump
   ```

2. **Test migrations in development first**
   - Apply migration in dev
   - Run application and test functionality
   - Check for any issues
   - Only then apply to production

3. **Review auto-generated migrations**
   - Alembic's autogenerate is helpful but not perfect
   - Always review generated SQL
   - Test both upgrade and downgrade paths

4. **Keep migrations small and focused**
   - One logical change per migration
   - Easier to debug and rollback

5. **Never edit applied migrations**
   - Create a new migration to fix issues
   - Keep migration history linear

6. **Document complex migrations**
   - Add comments explaining why changes are made
   - Include data migration logic if needed

## Offline/SQL Generation Mode

To generate SQL without applying to database:

```bash
# Generate SQL for all pending migrations
alembic upgrade head --sql > migration.sql

# Generate SQL for specific revision
alembic upgrade 5785681901d3 --sql > initial_schema.sql

# Review and apply manually
psql -h localhost -U user -d semdb -f migration.sql
```

## Initial Schema Tables

### Core Tables

1. **tenants** - Slack workspace tenants
   - Primary key: id
   - Unique index: workspace_id

2. **users** - Users within tenants
   - Foreign key: tenant_id → tenants.id
   - Indexes: tenant_id, slack_user_id

3. **oauth_tokens** - OAuth tokens for external services
   - Foreign key: tenant_id → tenants.id
   - Enum: OAuthProvider (GOOGLE, SLACK)

### Google Ads Tables

4. **google_ads_accounts** - Linked Google Ads accounts
   - Foreign key: tenant_id → tenants.id
   - Indexes: tenant_id, customer_id

5. **performance_thresholds** - Detection thresholds
   - Foreign key: tenant_id → tenants.id (unique)

### Reporting Tables

6. **report_schedules** - Report scheduling configuration
   - Foreign key: tenant_id → tenants.id (unique)
   - Enum: ReportFrequency (DAILY, WEEKLY, MONTHLY, DISABLED)

7. **report_history** - Generated report history
   - Foreign key: tenant_id → tenants.id
   - Stores metrics as JSON

### Keyword Tables

8. **keyword_candidates** - Detected inefficient search terms
   - Foreign key: tenant_id → tenants.id
   - Enum: KeywordStatus (PENDING, APPROVED, REJECTED, EXPIRED)
   - Indexes: tenant_id, detected_at

9. **approval_requests** - Keyword exclusion approvals
   - Foreign key: keyword_candidate_id → keyword_candidates.id (unique)
   - Enum: ApprovalAction (APPROVE, IGNORE, EXPIRED)
   - Indexes: keyword_candidate_id, slack_message_ts, expires_at

## Environment-Specific Configurations

### Development

```bash
# .env
DATABASE_URL=postgresql://dev_user:dev_pass@localhost:5432/semdb_dev
```

### Staging

```bash
# .env
DATABASE_URL=postgresql://staging_user:staging_pass@staging-db.internal:5432/semdb_staging
```

### Production

```bash
# .env (use secrets management)
DATABASE_URL=postgresql://prod_user:${DB_PASSWORD}@prod-db.internal:5432/semdb_prod
```

## Monitoring Migrations

### Check Migration Status

```bash
# Current revision
alembic current

# Pending migrations
alembic current --verbose

# History
alembic history
```

### Log Migration Execution

```bash
# Verbose output
alembic upgrade head --verbose

# SQL output (dry-run)
alembic upgrade head --sql
```

## Related Documentation

- [Deployment Guide](DEPLOYMENT.md) - Full deployment instructions
- [Configuration Guide](../QUICKSTART.md) - Environment setup
- [Database Schema](../README.md#database-schema) - Schema overview
