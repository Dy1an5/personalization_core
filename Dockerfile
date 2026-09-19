FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY pyproject.toml README.md plan.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN pip install --no-cache-dir ".[postgres]"

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn personalization_core.api.server:create_server_app --factory --host 0.0.0.0 --port 8000"]
