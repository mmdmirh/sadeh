# AI Chat Application

An AI chat application that uses Ollama to interact with various AI models and provides multilingual voice recognition capabilities.

## Setup and Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up your environment variables in a `.env` file:
   ```
   SECRET_KEY=your-secret-key
   MYSQL_USER=your-db-user
   MYSQL_PASSWORD=your-db-password
   MYSQL_DATABASE=your-db-name
   MYSQL_HOST=localhost
   MYSQL_PORT=3306
   ```
4. Install system dependencies:
   - **FFmpeg**: Required for voice recognition audio processing
     - macOS: `brew install ffmpeg`
     - Ubuntu/Debian: `sudo apt update && sudo apt install ffmpeg`
     - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
     - **Note**: Ensure FFmpeg is added to your system's PATH environment variable. You can verify the installation by running `ffmpeg -version` in your terminal or command prompt.
   
5. Run the application using the provided script:
   ```
   bash run.sh
   ```

## Setting up Voice Recognition

To enable voice recognition in the application, you need to download and install Vosk speech recognition models:

### English Language Support

1. Visit [Vosk Models](https://alphacephei.com/vosk/models/)
2. Download the recommended model: [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip) (91MB)
3. Extract the downloaded ZIP file
4. For single language setup:
   - Rename the extracted folder to `model`
   - Place the renamed folder in the root directory of the application

### Persian Language Support

The application supports Persian voice recognition with these steps:

1. Create a folder named `models` in the application root directory
2. Download the Persian model:
   - [Small Persian Model](https://alphacephei.com/vosk/models/vosk-model-small-fa-0.4.zip) (42MB) - Recommended
   - [Full Persian Model](https://alphacephei.com/vosk/models/vosk-model-fa-0.5.zip) (1.5GB) - Better accuracy but larger
3. Extract the ZIP file and place the extracted folder (keep its original name) in the `models` directory
4. Restart the application

### Multiple Language Support

For multilingual support:

1. Create a `models` directory in the application root
2. Download and extract model files for your desired languages
3. Place each model folder (with original names) in the `models` directory
4. Restart the application
5. Use the language selector button next to the microphone icon to switch languages

Your directory structure should look like this for multiple languages:

## Offline Server Installation Guide

This guide explains how to install and run the AI Chat Application on a server without internet access.

### 1. Prerequisites
- **Python:** Ensure Python 3.9+ is installed.
- **MySQL:** Install and configure MySQL Server offline.
- **FFmpeg:** Download the appropriate offline installer:
  - **Ubuntu/Debian:** Obtain FFmpeg deb packages from an offline source.
  - **macOS:** Pre-download the FFmpeg binary or installer.
  - **Windows:** Download the FFmpeg ZIP from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin` folder to PATH.
- **Python Packages:** On a machine with internet, run:
  ```
  pip download -r requirements.txt -d packages
  ```
  Then transfer the downloaded packages to your offline server.

### 2. Application Setup
- **Transfer Files:** Clone or copy the repository files to your offline server.
- **Install Dependencies:** Use the pre-downloaded packages:
  ```
  pip install --no-index --find-links=/path/to/packages -r requirements.txt
  ```
- **Environment Variables:** Create a `.env` file in the project root with at least:
  ```
  FLASK_APP=app.py
  FLASK_ENV=development
  SECRET_KEY=your-secret-key
  MYSQL_USER=your_db_user
  MYSQL_PASSWORD=your_db_password
  MYSQL_DATABASE=your_db_name
  MYSQL_HOST=localhost
  MYSQL_PORT=3306
  ```

### 3. Database Setup
- **Create Database:** Manually create the database using your MySQL client.
- **Seed Data:** Execute the SQL seeder with:
  ```
  mysql -u your_db_user -p your_db_name < seeder.sql
  ```

### 4. Vosk Voice Recognition Models
- **Download Models:** Prior to going offline, download the required Vosk models.
  - **English:** For example, download [vosk-model-small-en-us-0.15.zip].  
    • For single language mode, extract and rename the folder to `model` in the project root.  
    • For multilingual mode, create a `models` directory and place the extracted folder there.
  - **Other Languages (e.g. Persian):** Download [vosk-model-small-fa-0.4.zip] or [vosk-model-fa-0.5.zip] and extract them into the `models` directory.
  
### 5. AI Model Availability
- **Ollama Dependency:** The application uses Ollama to call AI models. If Ollama normally reaches out online, ensure that the necessary model files are already available or use a pre-configured offline model.

### 6. Running the Application
- **Start Services:** Ensure MySQL is running.
- **Launch:** Run the provided script:
  ```
  bash run.sh
  ```
  This script initializes dependencies, (optionally) starts the MySQL container, seeds the database, and launches the Flask application.

### 7. Access
- Open your web browser on a machine within your offline network and navigate to the server’s address (default port is 5000).

### 8. Troubleshooting
- **FFmpeg:** Verify FFmpeg installation with `ffmpeg -version`.
- **Vosk Models:** Ensure the default model is in the `model` folder (or additional models in `models`) with required files (e.g. `am/final.mdl` and `conf` folder).
- **MySQL Connection:** Confirm credentials in the `.env` file match your MySQL setup.

