#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Check for Homebrew (only needed for pkg-config)
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing pkg-config..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH for this session
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Install pkg-config if not present
if ! command -v pkg-config &> /dev/null; then
    echo "Installing pkg-config via Homebrew..."
    brew install pkg-config
fi

echo "=== Starting required services (MySQL, Ollama) via Docker ==="
# Ensure the deploy directory exists
mkdir -p deploy

# SOCKS proxy configuration has been removed.
echo "SOCKS proxy configuration has been removed. Docker will use direct connections."

# Start MySQL and Ollama using Docker Compose
docker-compose -f deploy/docker-compose.yml up -d mysql ollama
echo "Services started."

# Wait a moment for MySQL to initialize
echo "Waiting for MySQL to initialize..."
sleep 10

echo "=== Activating Conda Environment: sadeh_env ==="
# Attempt to initialize Conda, then activate the environment
if [ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]; then
    source "/opt/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
else
    echo "Conda initialization script not found. Please ensure Conda is installed and the path is added to this script."
    exit 1
fi
conda activate sadeh_env

echo "=== Sourcing Environment Variables from deploy/.env ==="
if [ -f deploy/.env ]; then
    set -a
    # First, read all environment variables except for OLLAMA_EMBEDDING_MODELS
    eval $(cat deploy/.env | grep -v '^#' | grep -v 'OLLAMA_EMBEDDING_MODELS' | xargs)
    
    # Special handling for OLLAMA_EMBEDDING_MODELS to extract just the model names
    if grep -q 'OLLAMA_EMBEDDING_MODELS' deploy/.env; then
        # Extract just the model names from the OLLAMA_EMBEDDING_MODELS line
        RAW_VALUE_PART=$(grep 'OLLAMA_EMBEDDING_MODELS' deploy/.env | cut -d '=' -f2-)
        MODELS=$(echo "$RAW_VALUE_PART" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" -e 's/^OLLAMA_EMBEDDING_MODELS=//' -e 's/^ollama pull //')
        export OLLAMA_EMBEDDING_MODELS="$MODELS"
        echo "Embedding models configured: $OLLAMA_EMBEDDING_MODELS"
    fi
    set +a
else
    echo "Warning: deploy/.env file not found. Please create it from deploy/.env.example."
    # Set default fallbacks if .env is missing
    export MYSQL_USER=sadeh_user
    export MYSQL_PASSWORD=sadeh_password
    export MYSQL_DATABASE=sadeh_db
    export CHROMA_DB_DATABASE=chroma_db
fi

echo "=== Applying Database Migrations ==="
flask db upgrade

# --- Override hosts for local execution --- #
echo "Overriding hosts for local execution..."

export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=${MYSQL_HOST_PORT:-3306} # Use port exposed on host, default to 3306

# Set ChromaDB connection details
export CHROMA_DB_HOST=127.0.0.1
export CHROMA_DB_PORT=${MYSQL_HOST_PORT:-3307} # Use same port for Chroma's DB

# Ensure CHROMA_DB_USER and CHROMA_DB_PASSWORD are set, fallback to MYSQL_* if not set
export CHROMA_DB_USER=${CHROMA_DB_USER:-$MYSQL_USER}
export CHROMA_DB_PASSWORD=${CHROMA_DB_PASSWORD:-$MYSQL_PASSWORD}

# Set Ollama host
export OLLAMA_HOST=http://localhost:11434 # Correct variable for Ollama host

# Log the database configuration for debugging
echo "Database Configuration:"
echo "- MYSQL_HOST: $MYSQL_HOST"
echo "- MYSQL_PORT: $MYSQL_PORT"
echo "- MYSQL_DATABASE: $MYSQL_DATABASE"
echo "- CHROMA_DB_HOST: $CHROMA_DB_HOST"
echo "- CHROMA_DB_PORT: $CHROMA_DB_PORT"
echo "- CHROMA_DB_DATABASE: $CHROMA_DB_DATABASE"

echo "Connecting as user: $CHROMA_DB_USER"
echo "With password: $CHROMA_DB_PASSWORD"

echo "=== Installing/Updating Python Dependencies ==="
# pip install --no-cache-dir -q -r requirements.txt

echo "=== Setting up MySQL Databases (if needed) ==="
python scripts/setup_chroma_db.py

echo "=== Waiting for MySQL to be ready ==="
# Wait for MySQL to be ready
for i in {1..30}; do
    if python -c "import pymysql; pymysql.connect(host='$MYSQL_HOST', port=$MYSQL_PORT, user='$MYSQL_USER', password='$MYSQL_PASSWORD')" 2>/dev/null; then
        echo "MySQL is ready!"
        break
    fi
    echo "Waiting for MySQL to be ready... (attempt $i/30)"
    sleep 2
done

echo "=== Creating Database Tables ==="
flask db upgrade

# Initialize the database with default data
echo "=== Initializing Database with Default Data ==="
flask init-db

# Kill any existing process on port 5001 to prevent 'Address already in use' error
echo "=== Ensuring port 5001 is free ==="
lsof -ti:5001 | xargs -r kill -9

echo "=== Starting Sadeh Application on http://0.0.0.0:5001 ==="
gunicorn --bind 0.0.0.0:5001 --timeout 180 --workers 2 --threads 4 --access-logfile sadeh_app.log --error-logfile sadeh_app.log app:app
