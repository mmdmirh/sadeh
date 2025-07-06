#!/bin/sh
# wait-for-db.sh
# Wait for MySQL to be fully ready

set -e

# Use environment variables for configuration, with defaults
host="${MYSQL_HOST:-mysql}"
port="${MYSQL_PORT:-3306}"
user="${MYSQL_USER}"
password="${MYSQL_PASSWORD}"
cmd="$@"

# Debug information
>&2 echo "=== Starting wait-for-db.sh ==="
>&2 echo "Host: $host"
>&2 echo "Port: $port"
>&2 echo "User: $user"
>&2 echo "Command: $cmd"

# The mysql client is now installed via the Dockerfile, so this check is no longer needed.

# Wait for MySQL to be available
counter=0
max_attempts=30

>&2 echo "Waiting for MySQL to be available at $host:$port..."

while [ $counter -lt $max_attempts ]; do
    if ! mysql -h "$host" -P "$port" -u"$user" -p"$password" -e 'SELECT 1' 2>/dev/null; then
        counter=$((counter+1))
        >&2 echo "MySQL is unavailable - sleeping (attempt $counter/$max_attempts)"
        sleep 2
    else
        >&2 echo "MySQL is up!"
        break
    fi
    
    if [ $counter -eq $max_attempts ]; then
        >&2 echo "Failed to connect to MySQL after $max_attempts attempts. Giving up."
        exit 1
    fi
done

# Additional check to ensure the database is fully initialized
>&2 echo "MySQL is up - checking if database is initialized..."
if ! mysql -h "$host" -P "$port" -u"$user" -p"$password" -e 'SHOW DATABASES' 2>/dev/null; then
    >&2 echo "Failed to list databases. MySQL may be up but not fully initialized."
    exit 1
fi

# Final check
>&2 echo "MySQL is up and database is ready - checking database access..."
if ! mysql -h "$host" -P "$port" -u"$user" -p"$password" -e 'SHOW DATABASES;'; then
    >&2 echo "Failed to access databases. Check user permissions."
    exit 1
fi

>&2 echo "=== MySQL is ready. Applying database migrations... ==="
# First, generate any new migration scripts based on model changes
flask db migrate -m "auto migration" || true

# Then, apply all migrations to bring the schema up to date
flask db upgrade

# Finally, run our custom command to populate the DB with initial data
flask init-db

# Setup ChromaDB database
>&2 echo "=== Setting up ChromaDB MySQL database... ==="
python /app/scripts/setup_chroma_db.py
STATUS=$?
if [ $STATUS -ne 0 ]; then
    >&2 echo "=== Failed to setup ChromaDB database. Continuing anyway... ==="
else
    >&2 echo "=== ChromaDB database setup complete ==="
fi

>&2 echo "=== Database setup complete. Starting application... ==="

exec $cmd
