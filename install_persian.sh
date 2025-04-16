#!/bin/bash

# Color codes for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Persian Language Voice Recognition Setup${NC}"
echo "This script will download and install the Persian voice recognition model"
echo "Required for the AI Chat voice assistant feature"
echo ""

# Create models directory if it doesn't exist
if [ ! -d "models" ]; then
    echo -e "${YELLOW}Creating models directory...${NC}"
    mkdir -p models
fi

# Check if Persian model is already installed
if [ -d "models/vosk-model-small-fa-0.4" ]; then
    echo -e "${GREEN}Persian model is already installed!${NC}"
    exit 0
fi

# Download the Persian model
echo -e "${YELLOW}Downloading Persian voice model (this may take some time)...${NC}"

# Use curl with progress bar
if command -v curl > /dev/null 2>&1; then
    curl -L --progress-bar -o /tmp/persian-model.zip https://alphacephei.com/vosk/models/vosk-model-small-fa-0.4.zip
elif command -v wget > /dev/null 2>&1; then
    wget --progress=bar -O /tmp/persian-model.zip https://alphacephei.com/vosk/models/vosk-model-small-fa-0.4.zip
else
    echo -e "${RED}Error: Neither curl nor wget is installed. Please install one of them and try again.${NC}"
    exit 1
fi

# Extract the model
echo -e "${YELLOW}Extracting model files...${NC}"
unzip -q /tmp/persian-model.zip -d models/

# Clean up the zip file
rm /tmp/persian-model.zip

# Verify installation
if [ -d "models/vosk-model-small-fa-0.4" ]; then
    echo -e "${GREEN}Persian voice model installed successfully!${NC}"
    echo "You can now use the Persian language with the voice assistant."
else
    echo -e "${RED}Installation failed. Please try again or install manually.${NC}"
    exit 1
fi
