# Use an official Python runtime as a parent image with more specific tag
FROM python:3.11-slim-bullseye

# Set environment variables using the modern key=value format
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# - ffmpeg: for audio processing (Whisper)
# - portaudio19-dev: for PyAudio (needed by sounddevice/speech_recognition)
# - build-essential: for compiling some Python packages
# - git: required by some pip installs (e.g., whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    portaudio19-dev \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir reduces image size
# Install PyAudio separately first as it often causes issues
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir PyAudio && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Make port 5001 available to the world outside this container (as used in app.py)
EXPOSE 5001

# Define the command to run the application
# Use gunicorn for production, but flask run for development simplicity here
# For production, consider: CMD ["gunicorn", "--bind", "0.0.0.0:5001", "app:app"]
CMD ["python", "app.py"]
