# Sadeh: AI Chat Application (Dockerized)

Sadeh is an AI chat application that uses Ollama to interact with various AI models, with multilingual voice recognition (Whisper) and text-to-speech (Bark) capabilities. This setup is fully containerized using Docker Compose for easy deployment and reproducibility.

## Features
- Chat with locally served Ollama models (e.g., gemma3:1b, llama2, phi3, etc.)
- Automatic model download at app startup (no manual pre-pull required)
- MySQL database backend
- Voice recognition (Whisper) and TTS (Bark)

## Quick Start (Docker Compose)

### 1. Prerequisites
- **Docker & Docker Compose** (Docker Desktop recommended)
- Sufficient RAM for your chosen models (at least 4–8GB for most models)

### 2. Clone the Repository
```bash
git clone https://github.com/mmdmirh/sadeh.git
cd sadeh
```

### 3. Configure Environment Variables
- Copy the example env file:
  ```bash
  cp deploy/.env.example deploy/.env
  ```
- Edit `deploy/.env` and set:
  - `SECRET_KEY` (Flask secret)
  - MySQL credentials (`MYSQL_USER`, `MYSQL_PASSWORD`, etc.)
  - `LLM_MODELS` – comma-separated list of Ollama models to ensure are downloaded (e.g. `gemma3:1b,llama2`)
  - `DEFAULT_MODEL_NAME` – the default model the app will use (e.g. `gemma3:1b`)
  - `OLLAMA_HOST` – leave as `http://ollama:11434` for Docker Compose

### 4. Build & Run with Docker Compose
From the `deploy/` directory:
```bash
docker compose up -d --build
```
- This will build your app image and start MySQL, Ollama, and the app.
- The app will wait for Ollama and MySQL to be healthy before starting.

### 5. Model Download Automation
- On first startup, the app will check for all models listed in `LLM_MODELS` and `DEFAULT_MODEL_NAME`.
- Any missing models will be pulled from the Ollama registry automatically via the Ollama API.
- Model files are stored in the `ollama-models` Docker volume (managed by the Ollama container).

### 6. Access the Application
- Open your browser and go to: [http://localhost:5001](http://localhost:5001)

### 7. Logs & Troubleshooting
- View app logs:
  ```bash
  docker compose logs -f web
  ```
- View Ollama logs:
  ```bash
  docker compose logs -f ollama
  ```
- If you encounter DNS/network errors with model downloads, check your Docker Desktop network settings and ensure your host has internet access.

### 8. Stopping & Cleaning Up
- Stop all services:
  ```bash
  docker compose down
  ```
- To remove all data volumes (including MySQL and Ollama models):
  ```bash
  docker compose down -v
  ```

### Running the Pre-built Image from Docker Hub

A pre-built image is available on Docker Hub for convenience. This is suitable if you are running your own MySQL and Ollama services separately.

1.  **Prerequisites:**
    *   A running MySQL server.
    *   A running Ollama service.
    *   Docker installed.

2.  **Run the container:**
    You must provide the necessary environment variables for the application to connect to your database and Ollama instance.

    ```bash
    docker run -d -p 5001:5001 \
      -e SECRET_KEY='your-super-secret-key' \
      -e MYSQL_HOST='your_mysql_host_ip' \
      -e MYSQL_USER='your_mysql_user' \
      -e MYSQL_PASSWORD='your_mysql_password' \
      -e MYSQL_DATABASE='your_mysql_db' \
      -e OLLAMA_HOST='http://your_ollama_host_ip:11434' \
      --name sadeh-app \
      mmdmirh/sadeh-app:latest
    ```

3.  **Access the Application:**
    *   Open your browser and go to: [http://localhost:5001](http://localhost:5001)

## Environment Variables Reference
See `deploy/.env.example` for all available options. Key variables:
- `SECRET_KEY` – Flask app secret
- `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_ROOT_PASSWORD` – MySQL configuration
- `LLM_MODELS` – comma-separated models to ensure are present (e.g. `gemma3:1b,llama2`)
- `DEFAULT_MODEL_NAME` – default model for chat
- `OLLAMA_HOST` – should be `http://ollama:11434` in Docker Compose

## Notes
- Ollama models are cached in the Docker volume `ollama-models` and are not lost between restarts unless you remove volumes.
- The app will always check and pull missing models at startup for robustness.
- No manual model download is required for Ollama models listed in your `.env` file.

---

For advanced configuration or manual (non-Docker) usage, see older instructions or contact the maintainer.

1.  **Prerequisites:**
    *   **Docker and Docker Compose:** Install from [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine/Compose for Linux.
    *   **Sufficient RAM:** LLM models require memory (RAM).
        *   **Ollama:** The default model `gemma3:1b` benefits from **at least 4-5GB of RAM allocated to Docker**. Larger models like `llama2` (7B) typically need **at least 8GB**.
        *   **Llama.cpp:** Memory needs depend on the model size (e.g., the default 7B Q4 model needs ~5-6GB).
        *   Check your Docker Desktop settings (Settings -> Resources -> Advanced -> Memory) and increase the allocation if necessary. Insufficient memory will cause errors or slow performance.
    *   **(Optional) NVIDIA Container Toolkit:** If you have an NVIDIA GPU and want GPU acceleration for Ollama or Llama.cpp, install the toolkit: [NVIDIA Container Toolkit Installation Guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). You may need to uncomment the `deploy` section in `docker-compose.yml`.

2.  **Environment Variables:**
    *   Create a `.env` file in the project root (if it doesn't exist). You can copy the example:
        ```bash
        cp .env.example .env
        ```
    *   **Important:** Review and update the `.env` file, especially:
        *   `SECRET_KEY` and MySQL credentials (`MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_ROOT_PASSWORD`).
        *   `LLM_SERVICE`: Set to `ollama` (default) or `llamacpp`.
        *   `OLLAMA_HOST`: Should typically be left as the default (`http://ollama:11434`).
        *   `LLAMACPP_HOST`: Should typically be left as the default (`http://llamacpp`).
        *   `LLAMACPP_MODEL`: Specifies the Llama.cpp model file. The default (`llama-2-7b-chat.Q4_K_M.gguf`) will be downloaded automatically if missing. **If you set this to a different model, you must download it manually (see step 3).**

3.  **Model Downloads (Automatic for Defaults):**
    *   **Ollama:** The `ollama` service will automatically download the default model (`gemma3:1b`) on first startup if it's not already present in the `ollama-models` volume.
    *   **Llama.cpp (Default Model):** The `llamacpp` service will automatically download the default model specified in `.env` (e.g., `llama-2-7b-chat.Q4_K_M.gguf`) into the `./llamacpp_models_host` directory on your host machine if it's not found there on startup.
    *   **Llama.cpp (Other Models - Manual Download Required):** If you change `LLAMACPP_MODEL` in your `.env` file to use a *different* model, the automatic download will **not** work for it. You must manually download that specific `.gguf` model file and place it in the `./llamacpp_models_host` directory before starting the containers. Create the directory if it doesn't exist:
        ```bash
        mkdir -p llamacpp_models_host
        # Example manual download (replace URL and filename):
        # curl -L <URL_to_your_model.gguf> -o ./llamacpp_models_host/<your_model_filename.gguf>
        ```
    *   **Whisper/Bark Models:** These models (used by the `web` service for voice features) are downloaded into the `./ai_models` directory on first use.

4.  **Build and Run Containers:**
    *   Open a terminal in the project root directory.
    *   **Make entrypoint scripts executable (first time only):**
        ```bash
        chmod +x ollama_entrypoint.sh
        chmod +x llamacpp_entrypoint.sh # Ensure this is executable again
        ```
    *   Build the application image and start the services:
        ```bash
        docker-compose up --build -d
        ```
        *   `--build`: Forces Docker to rebuild the application image.
        *   `-d`: Runs the containers in detached mode.
    *   **Monitor Startup:** Check the logs, especially for Ollama and Llama.cpp, to see model download progress or loading status:
        ```bash
        docker-compose logs -f ollama llamacpp
        ```
        *(Press Ctrl+C to stop viewing logs)*. The first startup might take longer while models are downloaded. Healthchecks will wait for services to become ready.

5.  **Database Initialization:**
    *   The first time you run `docker-compose up`, the MySQL container will initialize.
    *   The web application container will attempt to create the necessary database tables on startup. Check logs (`docker-compose logs web`).

6.  **Access the Application:**
    *   Open your web browser and navigate to: `http://localhost:5001` (or the port you configured if different).

7.  **Model Caching:**
    *   **Ollama Models:** Cached in the `ollama-models` Docker volume.
    *   **Llama.cpp Models:** Located in the `./llamacpp_models_host` directory on your host machine (mounted into the `llamacpp` container).
    *   **Whisper/Bark Models:** Cached inside the `ai_models` directory within the project folder (mounted into the `web` container).

8.  **Stopping the Application:**
    *   To stop the running containers:
        ```bash
        docker-compose down
        ```
    *   To stop and remove the volumes (including database data and Ollama models cache, but **NOT** your local Llama.cpp models in `./llamacpp_models_host` or Whisper/Bark models in `./ai_models`):
        ```bash
        docker-compose down -v
        ```

## Running Locally (Without Docker)

This method runs the application directly on your host machine, requiring manual setup of Python, dependencies, MySQL, **and Ollama**.

1.  **Prerequisites:**
    *   **Python 3.9+**
    *   **FFmpeg**: Required for audio processing.
        *   macOS: `brew install ffmpeg`
        *   Ubuntu/Debian: `sudo apt update && sudo apt install ffmpeg portaudio19-dev`
        *   Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.
    *   **PortAudio** (for PyAudio):
        *   macOS: `brew install portaudio` (Handled by `run.sh`)
        *   Ubuntu/Debian: `sudo apt install portaudio19-dev` (Handled by `run.sh`)
    *   **(Optional) CUDA Toolkit**: For GPU acceleration.
    *   **Sufficient RAM:** Ensure your host machine has enough free RAM for the Ollama models you intend to run (e.g., 4-5GB+ for `gemma3:1b`, 8GB+ for `llama2`).
    *   **Ollama:** Install Ollama on your **host machine** by following instructions at [ollama.ai](https://ollama.ai/). Ensure the Ollama service is running (`ollama serve` in a separate terminal if needed) and pull the default model:
        ```bash
        ollama pull gemma3:1b
        ```

2.  **Set up Python Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
3.  **Install Python Dependencies:**
    The `run.sh` script handles this automatically. If running manually:
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    # PyAudio might need special flags on macOS, handled by run.sh
    ```
4.  **Set up Environment Variables:** Create a `.env` file in the project root:
    ```dotenv
    FLASK_APP=app.py
    FLASK_ENV=development
    SECRET_KEY=your-very-secret-key # Change this!
    MYSQL_USER=your_db_user
    MYSQL_PASSWORD=your_db_password
    MYSQL_DATABASE=your_db_name
    MYSQL_HOST=localhost # Or your DB host
    MYSQL_PORT=3306
    # === Point OLLAMA_HOST to your local Ollama service ===
    OLLAMA_HOST=http://localhost:11434

    # Optional: Email settings for password reset
    MAIL_SERVER=smtp.example.com
    MAIL_PORT=587
    MAIL_USE_TLS=true
    MAIL_USERNAME=your-email@example.com
    MAIL_PASSWORD=your-email-password
    MAIL_DEFAULT_SENDER=your-email@example.com
    ```
5.  **Run the Application:**
    ```bash
    bash run.sh
    ```
    This script handles setup and starts the Flask application.

## Voice Features (Whisper & Bark)

*   **Speech Recognition (Whisper):** Uses `faster-whisper`. Models (`base`, `small`, etc.) are downloaded automatically on first use. Supports multiple languages including English and Persian. Language can be selected in the UI or set to auto-detect.
*   **Text-to-Speech (Bark):** Uses `suno/bark-small`. Models are downloaded automatically. Provides high-quality speech synthesis in multiple languages based on the detected or selected language.

## Offline Server Installation Guide

This guide explains how to install and run the AI Chat Application on a server without internet access, **using Docker**.

### 1. Prepare Docker Images and Models (Online Machine)
*   **Application Image:** Build the application image:
    ```bash
    docker-compose build web
    ```
    Save the image to a tar file:
    ```bash
    docker save pythonproject6-web:latest > ai-chat-web.tar
    # Verify image name with 'docker images' if needed
    ```
*   **MySQL Image:** Pull the MySQL image:
    ```bash
    docker pull mysql:8.0
    ```
    Save the image:
    ```bash
    docker save mysql:8.0 > mysql-8.0.tar
    ```
*   **Ollama Image:** Pull the Ollama image:
    ```bash
    docker pull ollama/ollama:latest
    ```
    Save the image:
    ```bash
    docker save ollama/ollama:latest > ollama-latest.tar
    ```
*   **Ollama Models:**
    *   Run `docker-compose up -d ollama` on the online machine. This will trigger the `ollama_entrypoint.sh` to download the default model (`gemma3:1b`) into the `ollama-models` volume if needed.
    *   Pull any *additional* models you require: `docker-compose exec ollama ollama pull <other_model_name>`
    *   Stop the container: `docker-compose down`
    *   Copy the models from the Docker volume. Find the volume path: `docker volume inspect pythonproject6_ollama-models` (look for `Mountpoint`).
    *   Copy the contents of the mountpoint to `offline_ollama_models/`.
    *   Remove the volume if desired: `docker volume rm pythonproject6_ollama-models`
*   **Llama.cpp Models:**
    *   Run `docker-compose up -d llamacpp` on the online machine. This will trigger the `llamacpp_entrypoint.sh` to download the default model (`llama-2-7b-chat.Q4_K_M.gguf`) into the `./llamacpp_models_host` directory if needed.
    *   If you need *other* Llama.cpp models, download them manually into `./llamacpp_models_host`.
    *   Stop the container: `docker-compose down`
    *   Copy the contents of the `./llamacpp_models_host` directory to `offline_llamacpp_models/`.
*   **Whisper/Bark Models:**
    *   Run the full application via Docker (`docker-compose up -d web`) once and use the voice features to trigger the download of Whisper/Bark models into the `./ai_models` directory.
    *   Stop the containers: `docker-compose down`
    *   Copy the contents of the `./ai_models` directory to `offline_ai_models/`.
*   **Python Packages:** (Optional, if not relying solely on the Docker image build)
    ```bash
    # Create and activate venv first
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip download -r requirements.txt -d packages/
    ```

### 2. Transfer Files to Offline Server
*   Copy the following to the offline server:
    *   The entire project directory (including `docker-compose.yml`, `.env.example`, `Dockerfile`, etc.)
    *   The saved Docker image tar files (`ai-chat-web.tar`, `mysql-8.0.tar`, `ollama-latest.tar`)
    *   The copied Ollama models directory (`offline_ollama_models/`)
    *   The copied Whisper/Bark models directory (`offline_ai_models/`)
    *   The copied Llama.cpp models directory (`offline_llamacpp_models/`)
    *   (Optional) The downloaded Python packages (`packages/` directory and `requirements.txt`)

### 3. Setup on Offline Server
*   **Install Docker & Docker Compose:** Install using offline packages suitable for the OS.
*   **Load Docker Images:**
    ```bash
    docker load < ai-chat-web.tar
    docker load < mysql-8.0.tar
    docker load < ollama-latest.tar
    # Load Llama.cpp server image if needed
    # docker load < llamacpp-server.tar 
    ```
*   **Prepare Volumes/Directories:**
    *   Create directories for the model volumes/mounts on the host:
        ```bash
        mkdir -p /opt/ai-chat/ollama-models
        mkdir -p /opt/ai-chat/ai_models
        mkdir -p /opt/ai-chat/llamacpp_models_host # For Llama.cpp models
        ```
    *   Copy the pre-downloaded models into these directories:
        ```bash
        cp -r /path/to/offline_ollama_models/* /opt/ai-chat/ollama-models/
        cp -r /path/to/offline_ai_models/* /opt/ai-chat/ai_models/
        cp -r /path/to/offline_llamacpp_models/* /opt/ai-chat/llamacpp_models_host/ # Copy Llama.cpp models
        ```
    *   Ensure correct permissions if necessary (Docker user needs read/write).
*   **Modify `docker-compose.yml` (Offline Version):**
    *   Change the volume mounts to use the host paths you created:
        ```yaml
        services:
          ollama:
            # ...
            volumes:
              - /opt/ai-chat/ollama-models:/root/.ollama # Mount host path
          llamacpp:
            # ...
            volumes:
              - /opt/ai-chat/llamacpp_models_host:/models # Mount host path for Llama.cpp
          web:
            # ...
            volumes:
              - /opt/ai-chat/ai_models:/app/ai_models # Mount host path
        # Remove named volume definitions at the bottom, except mysql-data
        # volumes:
        #   mysql-data: 
        #   ollama-models: # Remove this
        ```
*   **Configure `.env`:** Create a `.env` file from `.env.example`. Set secrets/passwords. Ensure `LLM_SERVICE`, `OLLAMA_HOST`, `LLAMACPP_HOST`, and `LLAMACPP_MODEL` are correct for the offline setup.

### 4. Run the Application (Offline Server)
*   Navigate to the project directory on the offline server.
*   Start the services:
    ```bash
    docker-compose up -d
    ```
    *   *(No `--build` needed as images are pre-loaded)*

### 5. Access
*   Open a web browser on a machine within the offline network and navigate to the server’s IP address and port (default 5001).

### 6. Troubleshooting (Offline)
*   **Docker:** Verify images loaded (`docker images`) and containers are running (`docker-compose ps`). Check logs (`docker-compose logs ollama`, `docker-compose logs web`).
*   **Model Volumes:** Double-check mount paths in `docker-compose.yml` and permissions on the host directories (`/opt/ai-chat/...`).
*   **Ollama Container:** Check if models are listed inside the container: `docker-compose exec ollama ollama list`.
*   **Network:** Ensure containers can communicate (Docker handles this by default on the `default` network).

