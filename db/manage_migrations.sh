#!/bin/bash

# Source environment variables from deploy/.env if it exists
ENV_FILE_PATH="deploy/.env"
if [ -f "$ENV_FILE_PATH" ]; then
  echo "Sourcing environment variables from $ENV_FILE_PATH"
  set -a # Automatically export all variables defined from now on
  source "$ENV_FILE_PATH"
  set +a # Stop automatically exporting
else
  echo "Warning: $ENV_FILE_PATH not found. Proceeding with existing environment variables."
fi


# Exit immediately if a command exits with a non-zero status.
set -e

# Default migration message if none is provided
DEFAULT_MESSAGE="Auto-generated migration"
MIGRATION_MESSAGE="${1:-$DEFAULT_MESSAGE}" # Use first argument as message, or default

# Ensure the script is run from the project root where app.py and migrations folder are
# This is a basic check; you might need a more robust one depending on your setup
if [ ! -f "app.py" ] || [ ! -d "db/migrations" ]; then
    echo "Error: This script must be run from the project root directory"
    echo "       and after 'flask db init' has been executed."
    exit 1
fi

echo "------------------------------------"
echo "Step 1: Generating migration script"
echo "------------------------------------"
echo "Using message: \"$MIGRATION_MESSAGE\""

echo "DEBUG: MYSQL_HOST is $MYSQL_HOST"
echo "DEBUG: MYSQL_PORT is $MYSQL_PORT"
echo "DEBUG: MYSQL_USER is $MYSQL_USER"
echo "DEBUG: MYSQL_DATABASE is $MYSQL_DATABASE"
# Be cautious about echoing MYSQL_PASSWORD in logs, consider if this is safe for your environment
# echo "DEBUG: MYSQL_PASSWORD is $MYSQL_PASSWORD"

flask db migrate -m "$MIGRATION_MESSAGE"

echo ""
echo "------------------------------------"
echo "Step 2: Applying migrations to database"
echo "------------------------------------"
flask db upgrade

echo ""
echo "------------------------------------"
echo "Database migration process complete."
echo "------------------------------------"
echo "Remember to commit the new migration script in the 'migrations/versions' directory."
