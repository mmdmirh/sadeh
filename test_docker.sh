#!/bin/bash
echo "=========================================="
echo "Docker Simple Test"
echo "=========================================="

# Check Docker version
echo "Docker version:"
docker --version

# Clean up any existing containers/resources
echo "Cleaning up..."
docker-compose down

# Pull the hello-world image
echo "Pulling hello-world image..."
docker pull hello-world

# Run the minimal test
echo "Running hello-world test..."
docker-compose up

echo "Test complete. If you saw 'Hello from Docker!' above, Docker is working."
echo "If you saw errors, there might be deeper issues with your Docker installation."
