FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Run migrations and start server with debug logging
CMD python -c "import sys; print('=== Python OK ==='); sys.path.insert(0, '/app'); from app import main; print('=== Import OK ===')" && alembic upgrade head && echo "=== Alembic Done ===" && uvicorn app.main:app --host 0.0.0.0 --port $PORT --log-level debug
