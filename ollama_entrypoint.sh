#!/bin/sh
set -e

# Start ollama serve in the background
/bin/ollama serve &
# Get the process ID of the server
pid=$!

echo "Ollama server started in background (PID: $pid)"

# Wait a bit longer for the server to be fully ready
echo "Waiting 10 seconds for Ollama server to initialize..."
sleep 10

# === Define the default model ===
DEFAULT_MODEL="gemma3:1b"
# === End define default model ===

# Check if the default model exists
echo "Checking for ${DEFAULT_MODEL} model via 'ollama list'..."
# Capture output and exit code separately
list_output=$(ollama list 2>&1)
list_code=$?

echo "ollama list command finished with exit code: $list_code"
echo "ollama list output:"
echo "$list_output"

# Check based on exit code and output content
# Use grep -F to treat the model name literally (in case of special characters)
if [ $list_code -ne 0 ] || ! echo "$list_output" | grep -q -F "${DEFAULT_MODEL}"; then
  echo "${DEFAULT_MODEL} model not found or 'ollama list' failed. Attempting to pull..."
  # Try pulling the model
  ollama pull "${DEFAULT_MODEL}"
  pull_code=$?
  if [ $pull_code -eq 0 ]; then
    echo "${DEFAULT_MODEL} model pulled successfully."
  else
    echo "Error pulling ${DEFAULT_MODEL} model (Exit code: $pull_code). The server might fail if the model is required."
    # Optionally exit here if the model is critical: exit $pull_code
  fi
else
  echo "${DEFAULT_MODEL} model already exists."
fi

# Bring the background server process to the foreground
echo "Bringing Ollama server (PID: $pid) to foreground..."
wait $pid
