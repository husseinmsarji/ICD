# ---- Stage 1: build the React frontend ----
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY icdweb/frontend/package.json icdweb/frontend/package-lock.json* ./
RUN npm install
COPY icdweb/frontend/ ./
RUN npm run build          # -> /fe/dist

# ---- Stage 2: Python backend + the icdgen library ----
FROM python:3.12-slim AS backend
WORKDIR /app

# System deps: none required at runtime (ReportLab/openpyxl are pure-python or
# ship wheels; lxml ships manylinux wheels). Kept minimal for image size.

# Install the icdgen core library first (changes least often -> better caching).
COPY icdgen/ /opt/icdgen/
RUN pip install --no-cache-dir /opt/icdgen

# Backend deps.
COPY icdweb/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Backend source.
COPY icdweb/backend/app /app/app

# Built frontend, served as static files by FastAPI.
COPY --from=frontend /fe/dist /app/static

ENV ICDGEN_DATA_DIR=/data \
    ICDGEN_STATIC_DIR=/app/static \
    ICDGEN_CORS_ORIGINS=* \
    PORT=8000
EXPOSE 8000
VOLUME ["/data"]

# Single worker by default; compose/orchestrator scales horizontally. When
# moving to many workers, point ICDGEN_DATA_DIR at shared storage.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
