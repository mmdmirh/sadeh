#!/bin/sh
# wait-for-db.sh - Waits for MySQL database to be available before starting the application

set -e

# Store the command to execute after successful database check
cmd="$@"

# Check if MYSQL_HOST is set
if [ -z "$MYSQL_HOST" ]; then
  echo "ERROR: MYSQL_HOST environment variable is not set. Cannot wait for database."
  echo "WARN: Proceeding without database check. This may cause application errors."
  exec $cmd
fi

# Use default port 3306 if MYSQL_PORT is not set
port="${MYSQL_PORT:-3306}"
host="$MYSQL_HOST"

echo "INFO: Waiting for MySQL at $host:$port..."

# Add a debugging ping to check host connectivity
echo "DEBUG: Pinging the database host to check network connectivity..."
ping -c 2 "$host" || echo "WARN: Could not ping host $host - DNS may not be resolving properly"

# Wait for the database to become available using netcat
echo "INFO: Checking database port availability..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
  if nc -z -w 2 "$host" "$port"; then
    echo "INFO: MySQL is available at $host:$port"
    echo "INFO: Executing command: $cmd"
    # Execute the passed command once the database is available
    exec $cmd
  else
    attempt=$((attempt + 1))
    echo "WAIT: MySQL is unavailable at $host:$port - sleeping (attempt $attempt/$max_attempts)"
    sleep 2
  fi
done

echo "ERROR: Could not connect to MySQL at $host:$port after $max_attempts attempts"
echo "WARN: Starting application anyway - this may cause errors if database is required"

# If we reach here, the database connection check failed but we'll try to start anyway
exec $cmd

set -e

# wait-for-db.sh: wait for MySQL to be ready, then execute a command.

host="${MYSQL_HOST}"
port="${MYSQL_PORT}"
user="${MYSQL_USER}"
password="${MYSQL_PASSWORD}"
cmd="$@"

max_attempts=30
counter=0

>&2 echo "Waiting for MySQL at $host:$port..."

while ! mysql -h "$host" -P "$port" -u"$user" -p"$password" --ssl -e 'SELECT 1'; do
    counter=$((counter+1))
    if [ $counter -ge $max_attempts ]; then
        >&2 echo "MySQL is unavailable - giving up after $max_attempts attempts."
        exit 1
    fi
    >&2 echo "MySQL is unavailable - sleeping (attempt $counter of $max_attempts)."
    sleep 2
done

>&2 echo "MySQL is up - executing command: $cmd"
# Execute the main command directly
>&2 echo "MySQL is up - starting application..."

# No need for manual migrations or seeding - the app will handle these internally now
exec $cmd
