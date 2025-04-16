#!/bin/bash
echo "=========================================="
echo "Docker Diagnosis and Testing Script"
echo "=========================================="

# Check basic Docker functionality
echo "Testing basic Docker functionality..."

# Create a simple docker-compose file in a separate directory
TEMP_DIR="/tmp/docker-test-$$"
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"

# Write a minimal docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  hello:
    image: hello-world
EOF

echo "Created test docker-compose.yml in $TEMP_DIR"
echo "Trying to run hello-world container..."

# Try to run the container
docker-compose up

# Check results
if [ $? -eq 0 ]; then
  echo "SUCCESS: Docker appears to be working correctly!"
else
  echo "FAILED: Docker couldn't run a simple hello-world container"
  echo "This indicates a fundamental issue with your Docker installation."
fi

# Clean up
cd - > /dev/null
rm -rf "$TEMP_DIR"

# Check Docker daemon status
echo "Checking Docker daemon status..."
docker info > /dev/null 2>&1 || { echo "ERROR: Docker daemon is not running properly!"; exit 1; }

# Check disk space
echo "Checking disk space..."
df -h | grep -E '/$|/Users'

# Print Docker resources
echo "Checking Docker resources..."
docker system df

# Suggest resetting Docker
echo "=========================================="
echo "If you're still experiencing issues, try resetting Docker completely:"
echo "1. Stop all containers: docker stop \$(docker ps -q)"
echo "2. Quit Docker Desktop completely"
echo "3. Restart your computer"
echo "4. Start Docker Desktop again"
echo "5. Run this script again to verify"
echo "=========================================="
