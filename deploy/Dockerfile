# Optimized Dockerfile for sadeh-app
# Creates a lightweight Python environment with essential requirements

FROM python:3.11-slim-bullseye

# Install netcat (netcat-openbsd) for the wait-for-db.sh script to check the database connection
# Install all required packages in a single layer to optimize image size and avoid caching issues
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    netcat-openbsd \
    default-mysql-client \
    curl \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=100

# Create a non-root user
RUN addgroup --system app && adduser --system --group app


# Set work directory
WORKDIR /home/app

# Copy requirements first for better caching
COPY backend/requirements.txt .

# Install dependencies with explicit pip flags for reliability
RUN pip install --no-cache-dir --timeout=300 --retries=10 pysqlite3-binary -r requirements.txt \
    # These imports are essential for proper functioning
    && pip install --no-cache-dir --timeout=300 --retries=10 httpx

# Copy application code
COPY backend /home/app/backend
COPY deploy/wait-for-db.sh /home/app/deploy/wait-for-db.sh
COPY backend/db/db/migrations /home/app/backend/db/db/migrations

# Create scripts directory and copy ChromaDB setup script
RUN mkdir -p /home/app/scripts


COPY backend/db_folder/setup_chroma_db.py /home/app/scripts/setup_chroma_db.py

# Fix format_sse function reference issue


# Set appropriate ownership and permissions of app files
RUN chown -R app:app /home/app && \
    chmod +x /home/app/deploy/wait-for-db.sh && \
    chmod +x /home/app/scripts/setup_chroma_db.py

# Switch to non-root user
USER app

# Expose port for gunicorn
EXPOSE 5001

# Set entry point to wait for database
ENTRYPOINT ["/home/app/deploy/wait-for-db.sh"]

# Start gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--timeout", "180", "--workers", "1", "backend.sadeh_core.app:app"]
