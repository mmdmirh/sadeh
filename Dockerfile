# Use official Python runtime as a parent image
FROM python:3.11-slim-bullseye

# Set environment variables
ENV PYTHONDONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Set work directory
WORKDIR /app


# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt || \
    (sleep 5 && pip install --no-cache-dir -r requirements.txt) || \
    (sleep 10 && pip install --no-cache-dir -r requirements.txt)

# Copy project
COPY . .

# Expose the port the app runs on
EXPOSE 5001

# Command to run the application
CMD ["python", "app.py"]
