#!/bin/bash

# Color codes for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Persian Voice Recognition Model Installer${NC}"
echo "This script will download and set up the Persian language model for speech recognition."
echo "================================================================================"

# Get application root directory
APP_DIR="$(pwd)"
MODELS_DIR="${APP_DIR}/models"

# Create models directory if it doesn't exist
if [ ! -d "${MODELS_DIR}" ]; then
    echo "Creating models directory..."
    mkdir -p "${MODELS_DIR}"
fi

# Set model URL and filepath
MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-fa-0.4.zip"
MODEL_ZIP="${MODELS_DIR}/vosk-model-small-fa-0.4.zip"
MODEL_DIR="${MODELS_DIR}/vosk-model-small-fa-0.4"

echo -e "\n${BLUE}Step 1:${NC} Downloading Persian model (42MB)..."
echo "From: ${MODEL_URL}"
echo "To: ${MODEL_ZIP}"

# Download the model
if command -v curl &> /dev/null; then
    curl -L -o "${MODEL_ZIP}" "${MODEL_URL}"
elif command -v wget &> /dev/null; then
    wget -O "${MODEL_ZIP}" "${MODEL_URL}"
else
    echo -e "\n${RED}Error:${NC} Neither curl nor wget is available. Please install one of them and try again."
    exit 1
fi

if [ $? -ne 0 ]; then
    echo -e "\n${RED}Error:${NC} Download failed. Please check your internet connection and try again."
    exit 1
fi

echo -e "\n${BLUE}Step 2:${NC} Extracting model..."
echo "From: ${MODEL_ZIP}"
echo "To: ${MODELS_DIR}"

# Extract the model
if command -v unzip &> /dev/null; then
    unzip -o "${MODEL_ZIP}" -d "${MODELS_DIR}"
else
    echo -e "\n${RED}Error:${NC} unzip command is not available. Please install unzip and try again."
    echo "You can manually extract the ZIP file to: ${MODELS_DIR}"
    exit 1
fi

if [ $? -ne 0 ]; then
    echo -e "\n${RED}Error:${NC} Extraction failed."
    exit 1
fi

# Verify the model was extracted correctly
if [ -d "${MODEL_DIR}" ] && [ -d "${MODEL_DIR}/am" ] && [ -f "${MODEL_DIR}/am/final.mdl" ]; then
    echo -e "\n${GREEN}Success!${NC} Persian model was installed correctly."
    echo "Model location: ${MODEL_DIR}"
    
    # Clean up the ZIP file
    echo -e "\n${BLUE}Step 3:${NC} Cleaning up..."
    rm "${MODEL_ZIP}"
    
    echo -e "\n${GREEN}Persian language model installation complete!${NC}"
    echo "Restart your application to start using Persian voice recognition."
    echo -e "To use Persian recognition, select 'Persian' from the language dropdown menu next to the microphone button.\n"
else
    echo -e "\n${RED}Error:${NC} Persian model was not extracted correctly or has an unexpected structure."
    echo "Please check the extracted directory: ${MODEL_DIR}"
    echo "Expected structure:"
    echo " - ${MODEL_DIR}/am/final.mdl"
    echo " - ${MODEL_DIR}/conf/"
    exit 1
fi

exit 0
