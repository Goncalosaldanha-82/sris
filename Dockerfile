FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml /app/
RUN pip install --no-cache-dir .
COPY backend /app/backend
COPY frontend /app/frontend
COPY migrations /app/migrations
COPY scripts /app/scripts
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "python -m app.scripts.init_db && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
