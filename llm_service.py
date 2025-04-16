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
                host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
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
