"""
LLM Service module that abstracts different LLM backends (Ollama)
"""
import os
import json
import logging
import requests
from typing import List, Dict, Any, Generator, Union, Optional

# Configure logging
logger = logging.getLogger(__name__)

class LLMServiceFactory:
    """Factory that creates the appropriate LLM service based on environment settings"""
    
    @staticmethod
    def create_service():
        """Create and return the configured LLM service based on environment variables"""
        service_type = os.environ.get('LLM_SERVICE', 'ollama').lower()
        return LLMServiceFactory.create_service_by_type(service_type)
    
    @staticmethod
    def create_service_by_type(service_type: str):
        """Create and return an LLM service based on the specified type
        
        Raises:
            ValueError: If the service type is not supported
        """
        if service_type == 'ollama':
            try:
                host = os.environ.get('OLLAMA_HOST', 'http://local-ollama:11434')  # Default to local-ollama service name
                return OllamaService(host)
            except Exception as e:
                logger.error("Error creating Ollama service: %s", e)
                raise
        else:
            logger.error("Unsupported LLM service type: {}. Set LLM_SERVICE=ollama in your .env file.".format(service_type))
            raise ValueError("Unsupported LLM service type: {}".format(service_type))

class OllamaService:
    """Service that interacts with Ollama API"""
    
    def __init__(self, host: str):
        self.host = host
        # We won't use the ollama client library to avoid potential issues
        logger.info("Initialized Ollama service with host: {}".format(host))
        self.test_connection()
    
    def test_connection(self, max_retries=3, retry_delay=2):
        import time, requests
        for attempt in range(max_retries):
            try:
                health_url = "{}/api/tags".format(self.host)
                logger.info("Testing connection to Ollama at {}".format(health_url))
                response = requests.get(health_url, timeout=5)
                if response.status_code == 200:
                    logger.info("Successfully connected to Ollama service at {}".format(self.host))
                    return True
                else:
                    logger.warning("Ollama service returned status code {}".format(response.status_code))
            except Exception as e:
                logger.warning("Attempt {}/{} to connect to Ollama failed: {}".format(attempt+1, max_retries, e))
            if attempt < max_retries - 1:
                logger.info("Waiting {} seconds before retrying...".format(retry_delay))
                time.sleep(retry_delay)
        logger.error("Failed to connect to Ollama service at {} after {} attempts".format(self.host, max_retries))
        return False
    
    def list_models_info(self) -> List[Dict[str, Any]]:
        """Fetches detailed information for all available Ollama models."""
        try:
            import requests
            response = requests.get(f"{self.host}/api/tags", timeout=10) # Increased timeout slightly
            response.raise_for_status() # Raise an exception for bad status codes
            
            data = response.json()
            logger.debug(f"Raw response from Ollama /api/tags: {str(data)[:500]}...") # Log more for debug
            
            models_info = data.get("models", [])
            if not isinstance(models_info, list):
                logger.error(f"Ollama /api/tags returned 'models' but it's not a list: {type(models_info)}")
                return []
            
            logger.info(f"Successfully fetched info for {len(models_info)} models from Ollama.")
            return models_info
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException listing detailed Ollama models: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"JSONDecodeError listing detailed Ollama models: {response.text[:200]}... Error: {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error listing detailed Ollama models: {e}")
            return []

    def list_models(self) -> List[str]:
        try:
            import requests
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code != 200:
                logger.error(f"Failed to list models: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            logger.info(f"Raw response from Ollama list models: {str(data)[:200]}...")
            
            models = []
            if "models" in data:
                for model_item in data["models"]:
                    if isinstance(model_item, dict) and "name" in model_item:
                        models.append(model_item["name"])
            
            logger.info(f"Found {len(models)} models: {models}")
            return models
        except Exception as e:
            logger.exception(f"Error listing Ollama models: {e}")
            return []
    
    def chat(self, model: str, messages: List[Dict[str, str]], stream: bool = False) -> Union[Dict[str, Any], Generator]:
        """
        Simplified direct API call for chat completions
        """
        import requests
        import json
        
        api_url = f"{self.host}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        logger.info(f"Making chat request to {api_url} with stream={stream}")
        
        if not stream:
            try:
                response = requests.post(api_url, json=payload, timeout=30)
                if response.status_code != 200:
                    logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                    raise Exception(f"Ollama API returned status {response.status_code}: {response.text}")
                return response.json()
            except Exception as e:
                logger.exception(f"Error in Ollama chat: {e}")
                raise
        else:
            # For streaming, return a generator that will be processed elsewhere
            return self._stream_response(api_url, payload)
    
    def _stream_response(self, api_url, payload):
        """
        Internal helper to handle streaming responses
        """
        import requests
        import json
        
        try:
            response = requests.post(api_url, json=payload, stream=True, timeout=60)
            if response.status_code != 200:
                logger.error(f"Ollama streaming API error: {response.status_code} - {response.text}")
                error_msg = {"error": f"API error {response.status_code}", "text": response.text[:100]}
                yield json.dumps(error_msg)
                return
                
            # Process the streaming response
            for line in response.iter_lines():
                if not line:
                    continue
                
                try:
                    # Parse the JSON response
                    chunk_data = json.loads(line.decode('utf-8'))
                    logger.debug(f"Received chunk: {str(chunk_data)[:100]}...")
                    
                    # For Ollama API, extract the message content
                    if "message" in chunk_data and "content" in chunk_data["message"]:
                        content = chunk_data["message"]["content"]
                        yield json.dumps({"text": content})
                    else:
                        logger.warning(f"Unexpected chunk format: {str(chunk_data)[:200]}")
                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode JSON from line: {line.decode('utf-8', errors='replace')[:100]}...")
        except Exception as e:
            logger.exception(f"Error in streaming response: {e}")
            yield json.dumps({"error": str(e), "text": f"⚠️ {str(e)}"})
    
    def stream_chat(self, model: str, messages: List[Dict[str, str]]) -> Generator:
        """
        Stream chat completions
        """
        logger.info(f"Starting stream_chat for model: {model}")
        api_url = f"{self.host}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }
        
        logger.info(f"Payload for streaming: {str(payload)[:500]}...")
        chunk_count = 0
        stream_yielded_content = False
        
        try:
            # Direct API call for better error handling
            import requests
            logger.info(f"Making streaming request to {api_url}")
            
            response = requests.post(api_url, json=payload, stream=True, timeout=30)
            
            if response.status_code != 200:
                error_msg = f"Ollama API returned error {response.status_code}: {response.text}"
                logger.error(error_msg)
                escaped_text = json.dumps({"error": error_msg, "text": f"⚠️ {error_msg}"})
                yield f"data: {escaped_text}\n\n"
                return
            
            logger.info("Successfully connected to streaming API, processing response...")
            
            # Process the streaming response line by line
            for line in response.iter_lines():
                if not line:
                    continue
                
                chunk_count += 1
                stream_yielded_content = True
                
                try:
                    # Parse the JSON response
                    chunk_data = json.loads(line.decode('utf-8'))
                    logger.info(f"Received chunk {chunk_count}: {str(chunk_data)[:100]}...")
                    
                    # For Ollama API, extract the message content
                    chunk_text = None
                    if "message" in chunk_data and "content" in chunk_data["message"]:
                        chunk_text = chunk_data["message"]["content"]
                    
                    if chunk_text is not None:
                        escaped_text = json.dumps({"text": chunk_text})
                        logger.info(f"Yielding chunk {chunk_count} with text: {chunk_text[:30]}...")
                        yield f"data: {escaped_text}\n\n"
                    else:
                        logger.warning(f"Could not extract text from chunk: {str(chunk_data)[:200]}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode JSON from line: {line.decode('utf-8', errors='replace')[:100]}...")
                    error_text = f"Error parsing response: {str(e)}"
                    escaped_text = json.dumps({"error": error_text, "text": f"⚠️ {error_text}"})
                    yield f"data: {escaped_text}\n\n"
            
            if not stream_yielded_content:
                logger.warning("No content was yielded from the stream")
                error_text = "No content generated by the model"
                escaped_text = json.dumps({"error": error_text, "text": f"⚠️ {error_text}"})
                yield f"data: {escaped_text}\n\n"
                
            logger.info(f"Finished processing {chunk_count} chunks from the stream")
            
        except Exception as e:
            logger.exception(f"Error in stream_chat: {e}")
            error_text = f"Error streaming from Ollama: {str(e)}"
            escaped_text = json.dumps({"error": error_text, "text": f"⚠️ {error_text}"})
            yield f"data: {escaped_text}\n\n"

    def pull_model(self, model_name: str, retries: int = 2, initial_delay: int = 10) -> bool:
        import time
        import requests
        import json

        api_url = f"{self.host}/api/pull"
        payload = {"name": model_name, "stream": True}
        
        logger.info(f"Attempting to pull model '{model_name}' from {self.host}...")

        for attempt in range(retries):
            try:
                # Set a longer timeout for the initial request, but iter_lines will keep it alive
                response = requests.post(api_url, json=payload, stream=True, timeout=300) # Increased timeout for pull 
                response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

                last_status_message = {}
                logger.info(f"Streaming pull status for '{model_name}' (attempt {attempt + 1}/{retries}):")
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk_data = json.loads(line.decode('utf-8'))
                            last_status_message = chunk_data # Keep track of the latest message
                            if "status" in chunk_data:
                                # Log progress more selectively to avoid flooding logs
                                if "total" in chunk_data and "completed" in chunk_data and chunk_data.get("total", 0) > 0:
                                    progress = (chunk_data["completed"] * 100) // chunk_data["total"]
                                    # Log at 0%, every 10%, and 100%
                                    if progress == 0 or progress == 100 or (progress % 10 == 0 and progress > 0 and progress < 100):
                                         logger.info(f"Pulling '{model_name}': {chunk_data['status']} - {progress}% ({chunk_data.get('completed', 0)}/{chunk_data.get('total', 0)})")
                                elif chunk_data['status'] != 'pulling manifest' and not ('total' in chunk_data): # Avoid logging every single pulling manifest message unless it's different
                                    logger.info(f"Pulling '{model_name}': {chunk_data['status']}")
                            if "error" in chunk_data:
                                logger.error(f"Error detail during pull of '{model_name}': {chunk_data['error']}")
                                # Error in stream, likely means failure for this attempt
                                break 
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to decode JSON line from pull stream: {line.decode('utf-8', errors='replace')[:100]}")
                
                # After stream ends, check the last message for definitive status
                if "status" in last_status_message and last_status_message["status"] == "success":
                    logger.info(f"Successfully pulled model '{model_name}'.")
                    return True
                elif "error" in last_status_message:
                    logger.error(f"Failed to pull model '{model_name}'. Final error: {last_status_message['error']}")
                else:
                    # Check if the model now appears in the list as a fallback success check
                    current_models = self.list_models()
                    if any(m.startswith(model_name) for m in current_models):
                        logger.info(f"Pull stream for '{model_name}' ended without explicit success, but model now appears in list. Assuming success.")
                        return True
                    logger.warning(f"Pull stream for '{model_name}' ended without clear success status. Last message: {last_status_message}. Model not found in list.")

            except requests.exceptions.RequestException as e:
                logger.error(f"RequestException while pulling model '{model_name}' (attempt {attempt + 1}/{retries}): {e}")
            except Exception as e:
                logger.error(f"Unexpected error while pulling model '{model_name}' (attempt {attempt + 1}/{retries}): {e}")

            if attempt < retries - 1:
                current_delay = initial_delay * (2 ** attempt) # Exponential backoff
                logger.info(f"Retrying pull for '{model_name}' in {current_delay} seconds...")
                time.sleep(current_delay)
            else:
                logger.error(f"Failed to pull model '{model_name}' after {retries} attempts.")
                return False
        
        return False # Should only be reached if retries is 0 or less
