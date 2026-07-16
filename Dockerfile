# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend
COPY backend/requirements-prod.txt ./requirements-prod.txt
RUN pip install --no-cache-dir -r requirements-prod.txt \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

COPY backend/app ./app
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
RUN mkdir -p /app/backend/data \
    && chown -R appuser:appuser /app/backend/data

USER appuser
EXPOSE 8000
VOLUME ["/app/backend/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
