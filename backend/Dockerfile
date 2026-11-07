FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --default-timeout=120 --retries=5 -r requirements.txt

RUN groupadd --system --gid 10001 nexa \
    && useradd --system --uid 10001 --gid nexa --home-dir /app nexa \
    && mkdir -p /data/property_documents \
    && chown -R nexa:nexa /app /data

COPY --chown=nexa:nexa . .

EXPOSE 8000

USER nexa

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}"]