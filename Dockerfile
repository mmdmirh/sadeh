# ---- Builder Stage ----
# This stage compiles Python dependencies into wheels.
FROM python:3.11-slim-bullseye as builder

# Set environment variables for build
ENV PYTHONDONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    libpq-dev \
    pkg-config \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create a wheelhouse directory
WORKDIR /wheelhouse

# Copy requirements and build wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/wheelhouse -r requirements.txt


# ---- Final Stage ----
# This stage creates the final, lean runtime image.
FROM python:3.11-slim-bullseye

# Set environment variables for runtime
ENV PYTHONDONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create a non-root user to run the application
RUN addgroup --system app && adduser --system --group app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    ffmpeg \
    libmariadb3 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /home/app

# Copy built wheels from the builder stage
COPY --from=builder /wheelhouse /wheelhouse

# Install Python dependencies from wheels
RUN pip install --no-cache-dir /wheelhouse/*

# Copy application code
COPY . .

# Change ownership of the app directory to the non-root user
RUN chown -R app:app /home/app

# Make wait script executable
RUN chmod +x /home/app/wait-for-db.sh

# Switch to the non-root user
USER app

# Expose the port the app runs on
EXPOSE 5001

# Set the entrypoint to our wait script
ENTRYPOINT ["/home/app/wait-for-db.sh"]

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--timeout", "120", "app:app"]
