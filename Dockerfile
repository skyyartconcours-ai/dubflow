FROM python:3.11-slim

# ffmpeg + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy app
COPY . .

# Create data directory
RUN mkdir -p /app/data/downloads /app/data/dubbed /app/data/output

# Port (Railway sets $PORT automatically)
ENV PORT=5000
EXPOSE 5000

# Run with gunicorn (production)
CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --threads 4 \
    --timeout 600 \
    --keep-alive 5
