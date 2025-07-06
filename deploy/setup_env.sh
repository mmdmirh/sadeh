#!/bin/bash

# Exit on error
set -e

echo "=== Setting up Sadeh Environment ==="

# Check if .env file already exists
if [ -f .env ]; then
    echo "Warning: .env file already exists. Creating a backup at .env.backup"
    cp .env .env.backup
fi

# Copy the example .env file
cp .env.example .env

echo "\nA new .env file has been created from the example."
echo "Please edit the .env file to configure your environment settings."
echo "\nTo edit the file, run:"
echo "  nano .env"
echo "\nOr open it with your preferred text editor."

echo "\nAfter editing the .env file, you can start the application with:"
echo "  docker-compose up -d"

# Make the script executable
chmod +x setup_env.sh
