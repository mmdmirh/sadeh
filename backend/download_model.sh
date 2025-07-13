#!/bin/bash
# Simple script to download the Llama.cpp model file

# Create the models directory if it doesn't exist
mkdir -p llamacpp_models_host

# Download the dummy model (a small file) just to allow the service to start
echo "Creating a dummy model file for testing..."
echo "This is a dummy model file" > llamacpp_models_host/dummy.gguf

echo "The llamacpp service should now start successfully with the dummy model."
echo ""
echo "To download the actual model, run these commands:"
echo "curl -L https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf -o llamacpp_models_host/llama-2-7b-chat.Q4_K_M.gguf"
echo ""
echo "Once downloaded, restart with: docker-compose restart llamacpp"
