#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# Load environment variables from .env
if [ -f .env ]; then
    echo "Loading environment variables from .env file"
    export $(grep -v '^#' .env | xargs)
fi

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Start the MySQL container (if not already running)
echo "Starting MySQL container using docker-compose..."
docker-compose up -d

# Optional: wait a few seconds to ensure the database is ready
echo "Waiting for MySQL to be ready..."
sleep 5

# Drop tables in correct order to avoid foreign key issues
echo "Dropping tables..."
docker exec -i local-mysql mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" -e "
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS chat_message;
DROP TABLE IF EXISTS document;
DROP TABLE IF EXISTS conversation;
DROP TABLE IF EXISTS user;
SET FOREIGN_KEY_CHECKS = 1;
"

# Run the SQL seeder file using the MySQL client within the container
# Using the environment variables loaded from .env
echo "Running SQL seeder..."
docker exec -i local-mysql mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" < seeder.sql

# Create a simple .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating default .env file..."
    cat > .env << EOF
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=dev-key-please-change-in-production
MYSQL_USER=your_db_user
MYSQL_PASSWORD=your_db_password
MYSQL_DATABASE=your_db_name
MYSQL_HOST=localhost
MYSQL_PORT=3306
EOF
    echo ".env file created. Please update with your actual database credentials."
fi

# Run the Flask application
echo "Starting Flask application..."
export FLASK_APP=app.py
export FLASK_ENV=development
flask run
