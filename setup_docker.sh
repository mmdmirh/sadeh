#!/bin/bash
set -e

echo "AI Chat Application - Docker Setup Helper"
echo "=========================================="

# Create required directories for model storage
mkdir -p ~/ai_models_storage/llamacpp_models_host
mkdir -p ~/ai_models_storage/ai_models

echo "Created model storage directories in ~/ai_models_storage/"

# Make entrypoint scripts executable
chmod +x ollama_entrypoint.sh
echo "Made ollama_entrypoint.sh executable"

# Clean up Docker (optional but recommended with low disk space)
echo "Cleaning Docker system..."
docker system prune -f

echo "Setup complete. You can now run:"
echo "docker-compose up -d mysql ollama llamacpp"
echo "docker-compose up -d web"
