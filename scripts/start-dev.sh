#!/bin/bash
set -e

echo "Starting SEM-Agent development environment..."

# Start services
docker-compose up -d postgres redis

# Wait for postgres
sleep 3

# Run migrations
alembic upgrade head

# Start web server
uvicorn app.main:app --reload &

# Start celery worker
celery -A app.tasks.celery_app worker --loglevel=info &

# Start celery beat
celery -A app.tasks.celery_app beat --loglevel=info &

echo "All services started!"
