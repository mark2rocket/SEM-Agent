#!/bin/bash
# Railway Environment Setup Script

echo "Setting up Railway environment variables..."

# First, link to your Railway project
echo "Step 1: Linking to Railway project"
echo "Run: railway link"
echo "Press Enter after linking..."
read

# Load .env file and set variables
set -a
source .env
set +a

# Set Slack variables
railway variables set SLACK_CLIENT_ID="$SLACK_CLIENT_ID"
railway variables set SLACK_CLIENT_SECRET="$SLACK_CLIENT_SECRET"
railway variables set SLACK_SIGNING_SECRET="$SLACK_SIGNING_SECRET"
railway variables set SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN"
railway variables set SLACK_APP_TOKEN="$SLACK_APP_TOKEN"
railway variables set SLACK_REDIRECT_URI="https://sem-agent.up.railway.app/oauth/slack/callback"
railway variables set SLACK_ALERT_CHANNEL="$SLACK_ALERT_CHANNEL"

# Set Google variables
railway variables set GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID"
railway variables set GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET"
railway variables set GOOGLE_REDIRECT_URI="https://sem-agent.up.railway.app/oauth/google/callback"
railway variables set GOOGLE_DEVELOPER_TOKEN="$GOOGLE_DEVELOPER_TOKEN"
railway variables set GOOGLE_LOGIN_CUSTOMER_ID="$GOOGLE_LOGIN_CUSTOMER_ID"

# Set Gemini variable
railway variables set GEMINI_API_KEY="$GEMINI_API_KEY"

# Set Security variables
railway variables set TOKEN_ENCRYPTION_KEY="$TOKEN_ENCRYPTION_KEY"
railway variables set SECRET_KEY="$SECRET_KEY"

# Set Celery variables (will use Railway's REDIS_URL)
railway variables set CELERY_BROKER_URL='${{REDIS_URL}}'
railway variables set CELERY_RESULT_BACKEND='${{REDIS_URL}}'
railway variables set CELERY_TIMEZONE="Asia/Seoul"

# Set environment
railway variables set ENVIRONMENT="production"
railway variables set DEBUG="false"

echo "Done! Environment variables set in Railway."
echo "Don't forget to add PostgreSQL and Redis services in Railway dashboard!"
