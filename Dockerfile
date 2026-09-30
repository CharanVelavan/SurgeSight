# SurgeSight: one Cloud Run service for the API and the built web app.
# Build the web app first (npm --prefix frontend run build); the image copies frontend/dist.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8080
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-overrides.txt ./
RUN pip install uv && uv pip install --system -r requirements.txt --override requirements-overrides.txt

COPY api ./api
COPY services ./services
COPY config ./config
COPY scripts ./scripts
COPY data/processed ./data/processed
COPY data/raw/sample_michaung_bulletin.txt ./data/raw/
COPY data/raw/wind ./data/raw/wind
COPY frontend/dist ./frontend/dist

RUN useradd --create-home app && chown -R app /app
USER app
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'
