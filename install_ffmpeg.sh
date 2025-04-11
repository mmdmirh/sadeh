#!/bin/bash

# Color codes for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}FFmpeg Installation Helper${NC}"
echo "This script will help you install FFmpeg for your AI Chat application."
echo "FFmpeg is required for voice recognition features to work properly."
echo "========================================================================"

# Function to check if FFmpeg is installed
check_ffmpeg() {
    if command -v ffmpeg &> /dev/null; then
        echo -e "${GREEN}✓ FFmpeg is already installed!${NC}"
        echo "Version information:"
        ffmpeg -version | head -n 1
        return 0
    else
        echo -e "${YELLOW}✗ FFmpeg is not installed or not in your PATH.${NC}"
        return 1
    fi
}

# Check if already installed
check_ffmpeg
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}Your voice recognition feature should work correctly now.${NC}"
    echo "You can return to the application and try the voice feature again."
    exit 0
fi

# Detect OS
echo -e "\n${BLUE}Detecting your operating system...${NC}"
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    echo "Linux detected"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    echo "macOS detected"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    OS="windows"
    echo "Windows detected"
else
    echo "Unknown OS: $OSTYPE"
fi

# Installation instructions by OS
echo -e "\n${BLUE}Installation instructions for your system:${NC}"

case $OS in
    linux)
        echo "We'll attempt to install FFmpeg using apt (for Ubuntu/Debian) or yum (for CentOS/RHEL/Fedora)"
        echo -e "${YELLOW}You may be prompted for your password to execute sudo commands.${NC}\n"
        
        if command -v apt-get &> /dev/null; then
            echo "Using apt package manager"
            read -p "Do you want to install FFmpeg now? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Installing FFmpeg..."
                sudo apt-get update && sudo apt-get install -y ffmpeg
                if [ $? -eq 0 ]; then
                    echo -e "${GREEN}Installation successful!${NC}"
                    check_ffmpeg
                else
                    echo -e "${RED}Installation failed. Please try manually:${NC}"
                    echo "sudo apt-get update && sudo apt-get install -y ffmpeg"
                fi
            fi
        elif command -v yum &> /dev/null; then
            echo "Using yum package manager"
            read -p "Do you want to install FFmpeg now? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Installing FFmpeg..."
                sudo yum install -y epel-release && sudo yum install -y ffmpeg
                if [ $? -eq 0 ]; then
                    echo -e "${GREEN}Installation successful!${NC}"
                    check_ffmpeg
                else
                    echo -e "${RED}Installation failed. Please try manually:${NC}"
                    echo "sudo yum install -y epel-release && sudo yum install -y ffmpeg"
                fi
            fi
        else
            echo -e "${YELLOW}Could not determine package manager. Please install FFmpeg manually:${NC}"
            echo "For Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y ffmpeg"
            echo "For CentOS/RHEL: sudo yum install -y epel-release && sudo yum install -y ffmpeg"
            echo "For Fedora: sudo dnf install -y ffmpeg"
        fi
        ;;
        
    macos)
        echo "On macOS, it's recommended to install FFmpeg using Homebrew."
        
        if command -v brew &> /dev/null; then
            echo "Homebrew is already installed."
            read -p "Do you want to install FFmpeg now? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Installing FFmpeg..."
                brew install ffmpeg
                if [ $? -eq 0 ]; then
                    echo -e "${GREEN}Installation successful!${NC}"
                    check_ffmpeg
                else
                    echo -e "${RED}Installation failed. Please try manually:${NC}"
                    echo "brew install ffmpeg"
                fi
            fi
        else
            echo -e "${YELLOW}Homebrew is not installed. Install Homebrew first:${NC}"
            echo "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo -e "\nThen install FFmpeg:"
            echo "brew install ffmpeg"
            
            read -p "Do you want to install Homebrew now? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                if [ $? -eq 0 ]; then
                    echo -e "${GREEN}Homebrew installed successfully!${NC}"
                    echo "Installing FFmpeg..."
                    brew install ffmpeg
                    if [ $? -eq 0 ]; then
                        echo -e "${GREEN}FFmpeg installation successful!${NC}"
                        check_ffmpeg
                    else
                        echo -e "${RED}FFmpeg installation failed. Please try manually:${NC}"
                        echo "brew install ffmpeg"
                    fi
                else
                    echo -e "${RED}Homebrew installation failed. Please visit:${NC}"
                    echo "https://brew.sh"
                fi
            fi
        fi
        ;;
        
    windows)
        echo -e "${YELLOW}On Windows, FFmpeg needs to be downloaded and added to your PATH manually:${NC}"
        echo "1. Visit: https://ffmpeg.org/download.html#build-windows"
        echo "2. Download the latest release build for Windows"
        echo "3. Extract the ZIP file to a location like C:\\ffmpeg"
        echo "4. Add the bin folder (e.g., C:\\ffmpeg\\bin) to your PATH environment variable:"
        echo "   a. Right-click on 'This PC' or 'My Computer' and select 'Properties'"
        echo "   b. Click on 'Advanced system settings'"
        echo "   c. Click on 'Environment Variables'"
        echo "   d. Under 'System variables', find and select 'Path', then click 'Edit'"
        echo "   e. Click 'New' and add the path to the bin folder"
        echo "   f. Click 'OK' on all dialogs"
        echo "5. Restart your command prompt or terminal"
        echo "6. Verify the installation by typing: ffmpeg -version"
        echo -e "\nAlternatively, if you have Chocolatey package manager installed:"
        echo "choco install ffmpeg"
        ;;
        
    *)
        echo -e "${RED}Could not determine your operating system.${NC}"
        echo "Please install FFmpeg manually from: https://ffmpeg.org/download.html"
        ;;
esac

echo -e "\n${BLUE}Final Steps:${NC}"
echo "1. After installing FFmpeg, restart your terminal/command prompt"
echo "2. Restart the Flask application"
echo "3. Try the voice recognition feature again"
echo -e "\n${YELLOW}Note:${NC} If you're running the application in a Docker container,"
echo "you'll need to rebuild the container to include FFmpeg."

exit 0
