#!/bin/bash
set -e

echo "==============================================="
echo "Docker Status Check and Troubleshooting Script"
echo "==============================================="

# Check Docker service status
echo "Checking Docker service status..."
if command -v docker &> /dev/null; then
    echo "✅ Docker command found"
    
    # Check Docker daemon status
    if docker info &> /dev/null; then
        echo "✅ Docker daemon is running"
    else
        echo "❌ Docker daemon is not running"
        echo "Try starting the Docker desktop application or service"
        exit 1
    fi
else
    echo "❌ Docker command not found"
    echo "Please install Docker Desktop or Docker Engine"
    exit 1
fi

# Check Docker Compose status
echo "Checking Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose command found"
else
    echo "❌ Docker Compose command not found"
    echo "Try installing Docker Compose or using 'docker compose' (without hyphen)"
    exit 1
fi

# Check disk space
echo "Checking disk space..."
if command -v df &> /dev/null; then
    df -h | grep -E '/$|/var|/home|/Users'
    
    # Check for critically low disk space
    free_space=$(df -k / | awk 'NR==2 {print $4}')
    if [ "$free_space" -lt 5242880 ]; then # less than 5GB free
        echo "❌ WARNING: Very low disk space (less than 5GB free)"
        echo "Try removing unused Docker images and volumes:"
        echo "docker system prune -a --volumes"
    else
        echo "✅ Sufficient disk space available"
    fi
fi

# Check Docker resource settings in Docker Desktop
echo "On macOS/Windows, also check Docker Desktop resource allocations:"
echo "• Open Docker Desktop"
echo "• Go to Settings/Preferences → Resources"
echo "• Check Memory allocation (recommend at least 4GB)"

echo "==============================================="
echo "To run the minimal setup:"
echo "1. chmod +x docker_check.sh"
echo "2. ./docker_check.sh"
echo "3. docker-compose down --volumes"
echo "4. docker-compose up -d"
echo "5. Wait a moment, then visit: http://localhost:5001"
echo "==============================================="
