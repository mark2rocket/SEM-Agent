web: exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --log-level info
worker: celery -A app.tasks.celery_app worker --loglevel=info
beat: celery -A app.tasks.celery_app beat --loglevel=info
