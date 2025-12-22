# Stage 1: Build React Frontend
FROM node:20-slim AS frontend-build
WORKDIR /web
COPY web/package*.json ./
RUN npm install
COPY web/ .
RUN npm run build

# Stage 2: Build Python Backend
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies for psycopg2/gevent
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY api/requirements.txt ./api/
RUN pip install --no-cache-dir -r ./api/requirements.txt

# Copy backend code
COPY api/ ./api/

# Copy frontend build from stage 1
COPY --from=frontend-build /web/dist ./web/dist

# Set environment variables
ENV FLASK_APP=api/app.py
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/api

WORKDIR /app/api

# Uvicorn for FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "4"]
