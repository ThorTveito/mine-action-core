# Single-container image: FastAPI serves the API and the built React app (same origin).
# Build:  docker build -t mine-action-core .
# Run:    docker run -p 8000:8000 -e DATABASE_URL=... -e SECRET_KEY=... mine-action-core

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    STATIC_DIR=/app/static
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY --from=web /web/dist ./static
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
# Migrate, optionally seed an empty demo database, then serve.
CMD ["sh", "-c", "alembic upgrade head && python -m app.bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
