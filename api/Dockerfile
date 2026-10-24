# Clawback API. Build from the repo root: docker compose build api (context is ., see docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# The API reads data/ (scenario files, fixtures), config/policy.yaml, eval/run.py and the web fixture run at runtime.
COPY api api
COPY config config
COPY data data
COPY eval eval
COPY web/fixtures web/fixtures

EXPOSE 8000
# One worker: runs, questions and the audit chain live in memory until the database lands.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
