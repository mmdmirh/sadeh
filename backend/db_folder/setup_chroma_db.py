#!/usr/bin/env python3
import os
import sys
import pymysql
from dotenv import load_dotenv

# Load environment variables from .env file (if available)
load_dotenv(dotenv_path='deploy/.env')

# Monkey patch pymysql to be used as MySQLdb
pymysql.install_as_MySQLdb()

def create_databases():
    """Create both the application and ChromaDB databases if they don't exist"""
    
    # Get MySQL connection details from environment variables
    db_host = os.environ.get('MYSQL_HOST', 'mysql')
    db_port = int(os.environ.get('MYSQL_PORT', 3306))
    db_user = os.environ.get('MYSQL_USER', 'sadeh_user')
    db_password = os.environ.get('MYSQL_PASSWORD', 'sadeh_password')
    root_password = os.environ.get('MYSQL_ROOT_PASSWORD', 'sadeh_root_password')
    
    # Get database names
    app_db = os.environ.get('MYSQL_DATABASE', 'sadeh_db')
    chroma_db = os.environ.get('CHROMA_DB_DATABASE', 'chroma_db')
    
    print(f"Connecting to MySQL at {db_host}:{db_port}")
    
    try:
        # First try to connect with root user to create databases
        try:
            conn = pymysql.connect(
                host=db_host,
                port=db_port,
                user='root',
                password=root_password,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            use_root = True
            print("Connected to MySQL as root")
        except pymysql.err.OperationalError as e:
            # If root login fails, try with regular user
            print(f"Root login failed: {e}, trying with regular user")
            conn = pymysql.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            use_root = False
            
        cursor = conn.cursor()
        
        # Create application database if it doesn't exist
        cursor.execute(f"SHOW DATABASES LIKE '{app_db}'")
        if not cursor.fetchone():
            print(f"Creating application database '{app_db}'")
            cursor.execute(f"CREATE DATABASE {app_db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"Database '{app_db}' created successfully")
        else:
            print(f"Application database '{app_db}' already exists")
        
        # Create ChromaDB database if it doesn't exist
        cursor.execute(f"SHOW DATABASES LIKE '{chroma_db}'")
        if not cursor.fetchone():
            print(f"Creating ChromaDB database '{chroma_db}'")
            cursor.execute(f"CREATE DATABASE {chroma_db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"Database '{chroma_db}' created successfully")
        else:
            print(f"ChromaDB database '{chroma_db}' already exists")
        
        # If we're using root, create or update the user and grant permissions
        if use_root:
            print(f"Ensuring user '{db_user}' exists and has proper permissions")
            cursor.execute(f"CREATE USER IF NOT EXISTS '{db_user}'@'%' IDENTIFIED BY '{db_password}'")
            cursor.execute(f"GRANT ALL PRIVILEGES ON {app_db}.* TO '{db_user}'@'%' ")
            cursor.execute(f"GRANT ALL PRIVILEGES ON {chroma_db}.* TO '{db_user}'@'%' ")
            cursor.execute("FLUSH PRIVILEGES")
        
        conn.commit()
        conn.close()
        print("Database setup completed successfully")
        return True
        
    except Exception as e:
        print(f"Error setting up databases: {str(e)}", file=sys.stderr)
        return False

if __name__ == "__main__":
    success = create_databases()
    sys.exit(0 if success else 1)
