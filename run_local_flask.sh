#!/bin/bash
set -x # Enable verbose execution tracing

# Navigate to the script's directory (project root)
cd "$(dirname "$0")"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
  echo "Activated virtual environment: venv"
elif [ -f ".venv/bin/activate" ]; then # Common alternative venv name
  source .venv/bin/activate
  echo "Activated virtual environment: .venv"
else
  echo "Virtual environment (venv/ or .venv/) not found. Please create and activate it, or install dependencies globally."
  # exit 1 # Uncomment to make venv mandatory
fi

# Load variables from deploy/.env if it exists
DEPLOY_ENV_FILE="./deploy/.env"
if [ -f "$DEPLOY_ENV_FILE" ]; then
  export $(grep -v '^#' $DEPLOY_ENV_FILE | xargs)
else
  echo "Warning: $DEPLOY_ENV_FILE not found. Ensure necessary env vars are set manually."
fi

# Override/set variables for local development connecting to Docker services
export FLASK_APP="app.py"
export FLASK_ENV="development" # Or FLASK_DEBUG=1
export OLLAMA_HOST="http://localhost:11434"
export MYSQL_HOST="localhost"
# Use MYSQL_HOST_PORT from deploy/.env if set, otherwise default to 3307
# Note: This requires MYSQL_HOST_PORT to be in deploy/.env for the logic below to pick it up.
# If it's not there, MYSQL_PORT will default to 3307.
export MYSQL_PORT="${MYSQL_HOST_PORT:-3307}"

# Install/update dependencies
echo "Installing/updating dependencies from requirements.txt..."
pip install -r requirements.txt

# Unset DOCKER_ENV if it was loaded from deploy/.env, as we are not in Docker
unset DOCKER_ENV

echo "--- Starting Flask App with Local Development Settings ---"
echo "Flask App: $FLASK_APP"
echo "Flask Env: $FLASK_ENV"
echo "Ollama Host: $OLLAMA_HOST"
echo "MySQL Host: $MYSQL_HOST"
echo "MySQL Port: $MYSQL_PORT"
echo "----------------------------------------------------------"

# Run the Flask application
python app.py
# Or use: flask run
