import pymysql
import os
import sys

# Get database connection details from environment variables
DB_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('MYSQL_PORT', 3306))
DB_USER = os.getenv('MYSQL_USER')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD')
DB_NAME = os.getenv('MYSQL_DATABASE')

if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    print("Error: MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DATABASE environment variables must be set.")
    sys.exit(1)

try:
    # Connect to the MySQL server (without specifying a database)
    connection = pymysql.connect(host=DB_HOST,
                                 port=DB_PORT,
                                 user=DB_USER,
                                 password=DB_PASSWORD,
                                 charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)
    print(f"Successfully connected to MySQL server at {DB_HOST}:{DB_PORT}")

    with connection.cursor() as cursor:
        # Drop the database if it exists
        print(f"Attempting to drop database '{DB_NAME}'...")
        # Drop the alembic_version table if it exists to reset migration history
        try:
            cursor.execute(f"USE `{DB_NAME}`")
            cursor.execute("DROP TABLE IF EXISTS alembic_version")
            print("Table 'alembic_version' dropped successfully.")
        except pymysql.MySQLError as e:
            # Ignore error if database doesn't exist, as it will be created next
            if e.args[0] != 1049: # Error code for 'Unknown database'
                raise
            else:
                print(f"Database '{DB_NAME}' does not exist yet, skipping alembic_version drop.")

        # Drop the database if it exists
        print(f"Attempting to drop database '{DB_NAME}'...")
        cursor.execute(f"DROP DATABASE IF EXISTS `{DB_NAME}`")
        print(f"Database '{DB_NAME}' dropped successfully.")
        
        # Create the database
        print(f"Attempting to create database '{DB_NAME}'...")
        cursor.execute(f"CREATE DATABASE `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"Database '{DB_NAME}' created successfully.")

except pymysql.MySQLError as e:
    print(f"An error occurred: {e}")
    sys.exit(1)

finally:
    if 'connection' in locals() and connection.open:
        connection.close()
        print("MySQL connection closed.")
