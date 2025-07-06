-- Create ChromaDB database if it doesn't exist
CREATE DATABASE IF NOT EXISTS `chroma_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create application user with appropriate privileges
CREATE USER IF NOT EXISTS 'sadeh_user'@'%' IDENTIFIED BY 'sadeh_password';
GRANT ALL PRIVILEGES ON `sadeh_db`.* TO 'sadeh_user'@'%';
GRANT ALL PRIVILEGES ON `chroma_db`.* TO 'sadeh_user'@'%';

-- Apply privileges
FLUSH PRIVILEGES;
