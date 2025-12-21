FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set environment variables
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Start Gunicorn
CMD ["gunicorn", "--worker-class", "gevent", "--workers", "1", "--threads", "20", "--bind", "0.0.0.0:5000", "--timeout", "120", "--keep-alive", "5", "app:app"]
