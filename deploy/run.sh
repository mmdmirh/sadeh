#!/bin/bash

# Sadeh Application Runner
# This script automates the setup and launch of the Sadeh application stack.

# Stop on first error
set -e

# --- Helper Functions ---
# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# --- Main Script ---

echo "🚀 Starting Sadeh Application Setup..."

# 1. Check for Docker and Docker Compose
echo "🔎 Checking for Docker and Docker Compose..."
if ! command_exists docker; then
    echo "❌ Error: Docker is not installed. Please install Docker to continue."
    echo "➡️ See: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check for 'docker compose' (v2) or 'docker-compose' (v1)
if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
    echo "❌ Error: Docker Compose is not installed. Please install it to continue."
    echo "➡️ See: https://docs.docker.com/compose/install/"
    exit 1
fi
echo "✅ Docker and Docker Compose are installed."

# 2. Navigate to the script's directory to ensure paths are correct
cd "$(dirname "$0")"

# 3. Create and configure the .env file
if [ ! -f .env ]; then
    echo "📋 .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ .env file created."
else
    echo "👍 .env file already exists."
fi

# 4. Modify .env for container networking
echo "🔧 Configuring .env for Docker networking..."

# Use sed to replace localhost with service names.
# This handles differences between macOS and Linux sed.
if [[ "$(uname)" == "Darwin" ]]; then # macOS
    sed -i '' 's/MYSQL_HOST=localhost/MYSQL_HOST=mysql/' .env
    sed -i '' 's#OLLAMA_HOST=http://localhost:11434#OLLAMA_HOST=http://ollama:11434#' .env
else # Linux
    sed -i 's/MYSQL_HOST=localhost/MYSQL_HOST=mysql/' .env
    sed -i 's#OLLAMA_HOST=http://localhost:11434#OLLAMA_HOST=http://ollama:11434#' .env
fi

echo "✅ .env file configured."

# 5. Pull the latest images and launch the application
echo "🐳 Pulling latest images and starting services with Docker Compose..."

# Use 'docker compose' if available (v2), otherwise fall back to 'docker-compose' (v1)
if docker compose version >/dev/null 2>&1; then
    docker compose up -d
else
    docker-compose up -d
fi


echo "
🎉 Success! The Sadeh application is starting.

🌐 You can access it at: http://localhost:5001

ℹ️ It might take a minute for all services to be fully available, especially the first time as models are downloaded.

To stop the application, run 'docker-compose down' in this directory.
"
