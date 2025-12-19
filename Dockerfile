FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment variables will be overridden by docker-compose
ENV FLASK_APP=app.py

CMD ["gunicorn", "-k", "gthread", "-w", "1", "--threads", "10", "--access-logfile", "-", "-b", "0.0.0.0:5000", "--timeout", "60", "app:app"]
