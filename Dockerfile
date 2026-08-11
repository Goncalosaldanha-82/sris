FROM python:3.11-slim
WORKDIR /workspace
COPY . .
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -e ".[test]"
EXPOSE 8000
CMD ["sh", "-c", "python -m app.atlas_platform.db_bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
