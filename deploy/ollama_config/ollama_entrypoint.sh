#!/bin/bash
set -e

echo "Starting Ollama service..."

# Start Ollama in the background
/usr/bin/ollama serve &
OLLAMA_PID=$!

# Function to check if Ollama is ready
wait_for_ollama() {
    echo "Waiting for Ollama to be ready..."
    # Use 'ollama list' as a readiness check.
    # It should succeed (exit code 0) once the server is up.
    until /usr/bin/ollama list >/dev/null 2>&1; do
        echo "Ollama not ready yet, waiting..."
        sleep 2 # Wait for 2 seconds before retrying
    done
    echo "Ollama is ready."
}

# Wait for Ollama to be ready
wait_for_ollama

echo "Ollama service started. Model pulling will be handled by the application (sadeh-app)."

# Keep the container running by waiting for the Ollama server process
wait $OLLAMA_PID