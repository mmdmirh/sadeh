# Optimized Dockerfile for sadeh-app
# Creates a lightweight Python environment with essential requirements

FROM python:3.11-slim-bullseye

# Install MySQL client for wait-for-db.sh
RUN apt-get update && apt-get install -y default-mysql-client libsqlite3-dev && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=100

# Create a non-root user
RUN addgroup --system app && adduser --system --group app


# Set work directory
WORKDIR /home/app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies with explicit pip flags for reliability
RUN pip install --no-cache-dir --timeout=300 --retries=10 pysqlite3-binary -r requirements.txt \
    # These imports are essential for proper functioning
    && pip install --no-cache-dir --timeout=300 --retries=10 httpx

# Copy application code
COPY . .

# Fix format_sse function reference issue


# Set appropriate ownership of app files
RUN chown -R app:app /home/app && \
    chmod +x /home/app/deploy/wait-for-db.sh

# Switch to non-root user
USER app

# Expose port for gunicorn
EXPOSE 5001

# Set entry point to wait for database
ENTRYPOINT ["/home/app/deploy/wait-for-db.sh"]

# Start gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--timeout", "180", "--workers", "1", "app:app"]
