#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}AI Chat Assistant - Setup and Startup Script${NC}"
echo -e "==============================================="

# Determine Python command (python3 or python)
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    # Try with just 'python' if python3 not found
    if command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo -e "${RED}Neither python3 nor python commands were found. Please install Python first.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}Using Python command: ${PYTHON_CMD}${NC}"

# Define virtual environment directory
VENV_DIR="venv"

# Create and activate virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${BLUE}Creating Python virtual environment in $VENV_DIR...${NC}"
    $PYTHON_CMD -m venv $VENV_DIR
    echo -e "${GREEN}Virtual environment created successfully!${NC}"
else
    echo -e "${GREEN}Using existing virtual environment in $VENV_DIR${NC}"
fi

# Activate the virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    source $VENV_DIR/Scripts/activate
else
    # Unix/Mac
    source $VENV_DIR/bin/activate
fi

# Make sure we're using the virtual environment's Python and pip
PYTHON_CMD="python"
PIP_CMD="pip"
echo -e "${GREEN}Using Python from virtual environment: $(which python)${NC}"

# Load environment variables from .env
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment variables from .env file${NC}"
    export $(grep -v '^#' .env | xargs)
else
    echo -e "${YELLOW}No .env file found. Creating default one...${NC}"
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
    echo -e "${YELLOW}.env file created. Please update with your actual database credentials.${NC}"
    echo -e "Press Enter to continue or Ctrl+C to abort and edit the .env file first."
    read
fi

# Check for PortAudio (required for PyAudio on macOS)
echo -e "\n${BLUE}Checking for PortAudio (required for PyAudio)...${NC}"
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS specific check
    if ! brew list portaudio &>/dev/null; then
        echo -e "${YELLOW}PortAudio not found. Installing via Homebrew...${NC}"
        if ! command -v brew &>/dev/null; then
            echo -e "${RED}Homebrew is not installed. Please install Homebrew first:${NC}"
            echo -e "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo -e "Then run this script again."
            exit 1
        fi
        brew install portaudio
        echo -e "${GREEN}PortAudio installed successfully.${NC}"
    else
        echo -e "${GREEN}PortAudio is already installed.${NC}"
    fi

    # Export needed environment variables for PyAudio installation
    export LDFLAGS="-L/usr/local/lib"
    export CPPFLAGS="-I/usr/local/include"
    export PKG_CONFIG_PATH="/usr/local/lib/pkgconfig"
    
    # For Apple Silicon macs, we may need different paths
    if [[ $(uname -m) == 'arm64' ]]; then
        export LDFLAGS="-L/opt/homebrew/lib ${LDFLAGS}"
        export CPPFLAGS="-I/opt/homebrew/include ${CPPFLAGS}"
        export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:${PKG_CONFIG_PATH}"
    fi
    
    echo -e "${YELLOW}Environment variables set for PyAudio compilation.${NC}"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux specific check
    if ! dpkg -l | grep -q libportaudio2; then
        echo -e "${YELLOW}PortAudio not found. Installing...${NC}"
        sudo apt-get update
        sudo apt-get install -y portaudio19-dev python3-dev
        echo -e "${GREEN}PortAudio installed successfully.${NC}"
    else
        echo -e "${GREEN}PortAudio is already installed.${NC}"
    fi
fi

# Upgrade pip in the virtual environment
echo -e "\n${BLUE}Upgrading pip in virtual environment...${NC}"
$PIP_CMD install --upgrade pip

# Install dependencies for faster-whisper first to avoid issues
echo -e "\n${BLUE}Installing core dependencies first...${NC}"
$PIP_CMD install numpy torch setuptools wheel

# Install Python dependencies
echo -e "\n${BLUE}Installing Python dependencies in virtual environment...${NC}"
# Try to install PyAudio first separately
echo -e "${YELLOW}Attempting to install PyAudio first...${NC}"
$PIP_CMD install PyAudio || {
    echo -e "${YELLOW}PyAudio installation failed. This is often due to missing system dependencies.${NC}"
    echo -e "${YELLOW}Audio functionality might be limited. Continuing with other dependencies...${NC}"
}

# Install with constraints to avoid dependency issues
echo -e "${BLUE}Installing remaining dependencies...${NC}"
CONSTRAINT_FILE=$(mktemp)
cat > "$CONSTRAINT_FILE" << EOF
# Prevent problematic version combinations
openai-whisper<20240000
ctranslate2>=3.17.0
EOF

# Install the rest of the dependencies with constraints
$PIP_CMD install -r requirements.txt -c "$CONSTRAINT_FILE" || {
    echo -e "${YELLOW}Some packages may have failed to install, trying without constraints...${NC}"
    $PIP_CMD install -r requirements.txt
}

rm -f "$CONSTRAINT_FILE"

# Check if FFmpeg is installed
echo -e "\n${BLUE}Checking for FFmpeg...${NC}"
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}FFmpeg not found. Installing...${NC}"
    if [ -f install_ffmpeg.sh ]; then
        bash install_ffmpeg.sh
    else
        echo -e "${RED}FFmpeg installation script not found. Please install FFmpeg manually.${NC}"
        echo -e "For Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y ffmpeg"
        echo -e "For macOS: brew install ffmpeg"
    fi
else
    echo -e "${GREEN}FFmpeg is already installed.${NC}"
fi

# Check if Ollama is installed and running
echo -e "\n${BLUE}Checking for Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}Ollama not found. Please install Ollama from https://ollama.ai/download${NC}"
    echo -e "After installation, run 'ollama pull llama2' to download the default model."
    echo -e "Press Enter to continue anyway or Ctrl+C to abort and install Ollama first."
    read
else
    echo -e "${GREEN}Ollama is installed.${NC}"
    echo -e "${BLUE}Checking for models...${NC}"
    MODELS=$(ollama list 2>/dev/null || echo "Failed to list models")
    if [[ $MODELS == *"Failed"* ]]; then
        echo -e "${YELLOW}Could not list Ollama models. Is the Ollama service running?${NC}"
        echo -e "Please start Ollama with 'ollama serve' in another terminal."
    else
        echo -e "${GREEN}Available Ollama models:${NC}"
        echo "$MODELS"
        
        # Check if llama2 model exists
        if [[ $MODELS != *"llama2"* ]]; then
            echo -e "${YELLOW}The default llama2 model is not found. Would you like to pull it now? (y/n)${NC}"
            read -r PULL_MODEL
            if [[ $PULL_MODEL =~ ^[Yy]$ ]]; then
                echo -e "${BLUE}Downloading llama2 model (this may take some time)...${NC}"
                ollama pull llama2
            fi
        fi
    fi
fi

# Set up NLTK for Bark text-to-speech
echo -e "\n${BLUE}Setting up NLTK data for Bark text-to-speech...${NC}"
$PYTHON_CMD -c "
import nltk
import os

# Define potential NLTK data paths within the venv
venv_path = os.environ.get('VIRTUAL_ENV', '.')
nltk_data_paths = [
    os.path.join(venv_path, 'nltk_data'),
    os.path.join(venv_path, 'share', 'nltk_data'),
    os.path.join(venv_path, 'lib', 'nltk_data'),
]

# Ensure the first path exists and add it to NLTK's data path
if not os.path.exists(nltk_data_paths[0]):
    os.makedirs(nltk_data_paths[0])
if nltk_data_paths[0] not in nltk.data.path:
    nltk.data.path.insert(0, nltk_data_paths[0])

# Function to check and download NLTK resource
def check_and_download(resource_id, download_path):
    try:
        nltk.data.find(f'tokenizers/{resource_id}')
        print(f'NLTK resource \"{resource_id}\" already available.')
    except LookupError:
        print(f'Downloading NLTK resource \"{resource_id}\" to {download_path}...')
        try:
            nltk.download(resource_id, download_dir=download_path, quiet=True)
            print(f'Downloaded NLTK resource \"{resource_id}\".')
            # Verify download
            nltk.data.find(f'tokenizers/{resource_id}')
        except Exception as e:
            print(f'Error downloading NLTK resource \"{resource_id}\": {e}')
            print('Please try running nltk.download(\"{resource_id}\") manually.')

# Check and download 'punkt' and 'punkt_tab'
check_and_download('punkt', nltk_data_paths[0])
check_and_download('punkt_tab', nltk_data_paths[0]) # <-- Add this line
"

# Set up AI voice models directory
MODELS_DIR="ai_models"
if [ ! -d "$MODELS_DIR" ]; then
    echo -e "\n${BLUE}Creating AI models directory...${NC}"
    mkdir -p $MODELS_DIR
    echo -e "${GREEN}Created $MODELS_DIR directory for Whisper and Bark models${NC}"
    echo -e "${YELLOW}Models will be downloaded automatically when first used${NC}"
fi

# Check for Docker
USE_DOCKER=false
if command -v docker-compose &> /dev/null; then
    USE_DOCKER=true
    echo -e "\n${BLUE}Docker found, will use for MySQL if needed.${NC}"
else
    echo -e "\n${YELLOW}Docker not found. Will attempt to use local MySQL.${NC}"
fi

# Initialize database
echo -e "\n${BLUE}Initializing database...${NC}"

# Try to create database if it doesn't exist (for both Docker and local)
if [ "$USE_DOCKER" = true ]; then
    docker exec -i local-mysql mysql -u root -p"${MYSQL_PASSWORD}" -e "CREATE DATABASE IF NOT EXISTS ${MYSQL_DATABASE};" 2>/dev/null || true
    
    # Drop tables in correct order to avoid foreign key issues
    echo -e "Resetting database tables..."
    docker exec -i local-mysql mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" -e "
    SET FOREIGN_KEY_CHECKS = 0;
    DROP TABLE IF EXISTS chat_message;
    DROP TABLE IF EXISTS document;
    DROP TABLE IF EXISTS conversation;
    DROP TABLE IF EXISTS user;
    SET FOREIGN_KEY_CHECKS = 1;
    "
    
    # Run the SQL seeder file
    echo -e "${BLUE}Running SQL seeder...${NC}"
    docker exec -i local-mysql mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" < seeder.sql
else
    # Try to use local MySQL client
    if command -v mysql &> /dev/null; then
        echo -e "Creating database if needed..."
        mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS ${MYSQL_DATABASE};" 2>/dev/null || true
        
        echo -e "Resetting database tables..."
        mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" "${MYSQL_DATABASE}" -e "
        SET FOREIGN_KEY_CHECKS = 0;
        DROP TABLE IF EXISTS chat_message;
        DROP TABLE IF EXISTS document;
        DROP TABLE IF EXISTS conversation;
        DROP TABLE IF EXISTS user;
        SET FOREIGN_KEY_CHECKS = 1;
        " 2>/dev/null || echo -e "${RED}Failed to reset database tables. Will try to continue.${NC}"
        
        echo -e "${BLUE}Running SQL seeder...${NC}"
        mysql -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" "${MYSQL_DATABASE}" < seeder.sql 2>/dev/null || echo -e "${RED}Failed to seed database. Will try to continue.${NC}"
    else
        echo -e "${YELLOW}MySQL client not found. Using Flask's built-in database setup...${NC}"
    fi
fi

# Create static/css directory if it doesn't exist
if [ ! -d "static/css" ]; then
    echo -e "\n${BLUE}Creating static/css directory...${NC}"
    mkdir -p static/css
fi

# Standalone voice assistant check
if [ -f "voice_assistant.py" ]; then
    echo -e "\n${GREEN}Standalone voice assistant is available!${NC}"
    echo -e "You can run the voice assistant separately with: $PYTHON_CMD voice_assistant.py"
else
    echo -e "\n${YELLOW}Creating standalone voice assistant script...${NC}"
    # Copy the code for the voice assistant from the previous implementation
    cp voice_assistant.py voice_assistant.py.bak 2>/dev/null || true
fi

# Run the Flask application
echo -e "\n${GREEN}All set! Starting Flask application...${NC}"
export FLASK_APP=app.py
export FLASK_ENV=development
# === Add Environment Variable for Tokenizers ===
export TOKENIZERS_PARALLELISM=false
# === End Add Environment Variable ===
# Ensure we run on port 5001 as intended
echo -e "${YELLOW}Attempting to run on 0.0.0.0:5001...${NC}"
python -m flask run --host=0.0.0.0 --port=5001

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}AI Chat Application Runner${NC}"
echo "============================"

# --- Check for Docker ---
if ! command -v docker &> /dev/null || ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Error: Docker and Docker Compose are required to run this application.${NC}"