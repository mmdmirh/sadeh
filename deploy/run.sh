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

# 1. Check for dependencies (Docker, curl/wget)
echo "🔎 Checking for dependencies..."
if ! command_exists docker; then
    echo "❌ Error: Docker is not installed. Please install Docker to continue."
    echo "➡️ See: https://docs.docker.com/get-docker/"
    exit 1
fi
if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
    echo "❌ Error: Docker Compose is not installed. Please install it to continue."
    echo "➡️ See: https://docs.docker.com/compose/install/"
    exit 1
fi
if ! command_exists curl && ! command_exists wget; then
    echo "❌ Error: Neither 'curl' nor 'wget' is installed. Please install one to continue."
    exit 1
fi
echo "✅ Dependencies are satisfied."

# 2. Create a directory and download necessary files
INSTALL_DIR="$HOME/sadeh_deploy"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "📁 Using directory: $INSTALL_DIR"

BASE_URL="https://raw.githubusercontent.com/mmdmirh/sadeh/main/deploy"
FILES=(
    "docker-compose.yml"
    ".env.example"
    "ollama_config/ollama_entrypoint.sh"
)

echo "Downloading required files..."
for file in "${FILES[@]}"; do
    mkdir -p "$(dirname "$file")"
    url="$BASE_URL/$file"
    echo "    -> $file"
    if command_exists curl; then
        curl -s -o "$file" "$url"
    else
        wget -q -O "$file" "$url"
    fi
done

# Create empty directory for mysql init scripts
mkdir -p mysql/initdb.d

# Make the ollama entrypoint script executable
chmod +x ollama_config/ollama_entrypoint.sh

echo "✅ All files downloaded and configured."

# 3. Create and configure the .env file
if [ ! -f .env ]; then
    echo "📋 .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ .env file created."
else
    echo "👍 .env file already exists. No changes made."
fi

# 4. Modify .env for container networking
echo "🔧 Configuring .env for Docker networking..."
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
