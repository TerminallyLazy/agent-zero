# Visual Document Service - LitePali sidecar container
FROM python:3.11-slim

# Install system dependencies for pdf2image and health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Server file is copied by build.sh to build context
COPY server.py /app/server.py

# Create directories for shared volumes
RUN mkdir -p /a0/usr/visual_docs

# Environment configuration
ENV PORT=9010
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:9010/health || exit 1

# Expose the service port
EXPOSE 9010

# Run the HTTP server
CMD ["python", "server.py"]
