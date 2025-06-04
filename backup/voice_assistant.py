import time
import threading
import numpy as np
import tempfile
import logging
import os
import sounddevice as sd
from queue import Queue
import subprocess
import json
import nltk
import torch
import warnings
# Replace whisper with faster-whisper
from faster_whisper import WhisperModel
from transformers import AutoProcessor, BarkModel

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VoiceAssistant")

warnings.filterwarnings(
    "ignore",
    message="torch.nn.utils.weight_norm is deprecated in favor of torch.nn.utils.parametrizations.weight_norm.",
)

class TextToSpeechService:
    def __init__(self, device: str = "cuda" if torch.cuda.is_available() else "cpu"):
        """
        Initializes the TextToSpeechService class with Bark.
        Args:
            device: The device to use for inference (cuda or cpu)
        """
        logger.info(f"Initializing Bark on device: {device}")
        self.device = device
        self.processor = AutoProcessor.from_pretrained("suno/bark-small")
        self.model = BarkModel.from_pretrained("suno/bark-small")
        self.model.to(self.device)
        logger.info("Bark model loaded successfully")

    def synthesize(self, text: str, voice_preset: str = "v2/en_speaker_1"):
        """
        Synthesizes audio from the given text using the specified voice preset.
        Args:
            text: The text to synthesize
            voice_preset: The voice to use for synthesis
        Returns:
            tuple: Sample rate and audio array
        """
        inputs = self.processor(text, voice_preset=voice_preset, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            audio_array = self.model.generate(**inputs, pad_token_id=10000)

        audio_array = audio_array.cpu().numpy().squeeze()
        sample_rate = self.model.generation_config.sample_rate
        return sample_rate, audio_array

    def long_form_synthesize(self, text: str, voice_preset: str = "v2/en_speaker_1"):
        """
        Synthesizes longer text by splitting into sentences.
        Args:
            text: The text to synthesize
            voice_preset: The voice to use for synthesis
        Returns:
            tuple: Sample rate and audio array
        """
        # Make sure NLTK punkt tokenizer is available
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)

        pieces = []
        sentences = nltk.sent_tokenize(text)
        silence = np.zeros(int(0.25 * self.model.generation_config.sample_rate))

        for sent in sentences:
            sample_rate, audio_array = self.synthesize(sent, voice_preset)
            pieces += [audio_array, silence.copy()]

        return self.model.generation_config.sample_rate, np.concatenate(pieces)

class VoiceAssistant:
    def __init__(self, model_name="llama2", language="english"):
        """Initialize the voice assistant with specified model and language."""
        self.model_name = model_name
        self.language = language
        
        # Map language to voice preset for Bark
        self.voice_presets = {
            "english": "v2/en_speaker_1",
            "persian": "v2/fa_speaker_1",  # Persian may need a custom voice
        }
        
        # Load Whisper for speech recognition
        logger.info("Loading WhisperModel (faster-whisper)...")
        try:
            # Initialize with int8 precision for better performance on CPU 
            self.whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("WhisperModel loaded successfully")
        except Exception as e:
            logger.exception(f"Error loading WhisperModel: {e}")
            # Fallback to float32 if int8 fails
            logger.info("Trying fallback with float32 compute type...")
            self.whisper_model = WhisperModel("base", device="cpu", compute_type="float32")
        
        # Load Bark for text-to-speech
        logger.info("Loading Bark for text-to-speech...")
        self.tts = TextToSpeechService()
        
        logger.info(f"Voice Assistant initialized with model: {model_name}, language: {language}")
    
    def record_audio(self, stop_event, data_queue):
        """Record audio from microphone and add to queue."""
        def callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio recording status: {status}")
            data_queue.put(bytes(indata))

        with sd.RawInputStream(samplerate=16000, dtype="int16", channels=1, callback=callback):
            logger.info("Started recording audio...")
            while not stop_event.is_set():
                time.sleep(0.1)
            logger.info("Stopped recording audio")
    
    def transcribe_audio(self, audio_data):
        """Transcribe audio data to text using faster-whisper."""
        # Save audio data to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            temp_path = tmp.name
            tmp.write(audio_data)
        
        logger.info(f"Saved audio to temporary file: {temp_path}")
        
        try:
            # Set language if specified
            language_code = None
            if self.language.lower() == "persian":
                language_code = "fa"
            elif self.language.lower() == "english":  
                language_code = "en"
            
            # Transcribe with faster-whisper
            logger.info(f"Transcribing with faster-whisper (language: {language_code})...")
            segments, info = self.whisper_model.transcribe(
                temp_path,
                language=language_code,
                beam_size=5
            )
            
            # Collect all segments into one text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)
            
            full_text = " ".join(text_parts).strip()
            
            logger.info(f"Transcription: {full_text}")
            return full_text
        finally:
            # Clean up temporary file
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Error removing temp file: {e}")
    
    def get_ollama_response(self, prompt_text):
        """Get response from Ollama model."""
        try:
            logger.info(f"Calling Ollama with model {self.model_name}")
            
            # Add language-specific instruction
            if self.language.lower() == "persian":
                prompt_text = "لطفا به این سوال به زبان فارسی پاسخ دهید:\n\n" + prompt_text
                logger.info("Added Persian language instruction")
            
            cmd = ["ollama", "run", self.model_name, prompt_text]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Ollama error: {result.stderr}")
                return "Sorry, I encountered an error while processing your request."
            
            response = result.stdout.strip()
            logger.info(f"Got response from Ollama: {response[:50]}...")
            return response
        except subprocess.TimeoutExpired:
            logger.warning("Ollama response timed out")
            return "Sorry, it's taking me too long to think. Could you try a simpler question?"
        except Exception as e:
            logger.error(f"Error getting Ollama response: {e}")
            return "I encountered an error while processing your request."
    
    def speak_text(self, text):
        """Convert text to speech and play it using Bark."""
        try:
            logger.info(f"Synthesizing speech: {text[:50]}...")
            
            # Get appropriate voice preset based on language
            voice_preset = self.voice_presets.get(
                self.language.lower(), 
                "v2/en_speaker_1"  # Default to English
            )
            
            # Generate audio with Bark
            sample_rate, audio_array = self.tts.long_form_synthesize(text, voice_preset)
            
            # Play the audio
            logger.info("Playing synthesized speech...")
            sd.play(audio_array, sample_rate)
            sd.wait()
            
            return True
        except Exception as e:
            logger.error(f"Error in text-to-speech: {e}")
            return False
    
    def run_conversation(self):
        """Run the main conversation loop."""
        logger.info("Starting conversation loop")
        print(f"\nVoice Assistant started using the {self.model_name} model")
        print("Press Ctrl+C to exit\n")
        
        try:
            while True:
                # Instructions for user
                print("\nPress Enter to start recording, then press Enter again to stop...")
                input()
                
                # Start recording thread
                data_queue = Queue()
                stop_event = threading.Event()
                recording_thread = threading.Thread(
                    target=self.record_audio,
                    args=(stop_event, data_queue)
                )
                recording_thread.start()
                
                # Wait for user to press Enter again to stop recording
                print("Recording... Press Enter to stop.")
                input()
                stop_event.set()
                recording_thread.join()
                
                # Process audio data
                print("Processing your speech...")
                audio_data = b"".join(list(data_queue.queue))
                
                if len(audio_data) > 0:
                    # Transcribe audio to text
                    text = self.transcribe_audio(audio_data)
                    print(f"You said: {text}")
                    
                    # Get AI response
                    print("Thinking...")
                    response = self.get_ollama_response(text)
                    print(f"AI response: {response}")
                    
                    # Speak the response
                    self.speak_text(response)
                else:
                    print("No audio recorded. Please check your microphone.")
        
        except KeyboardInterrupt:
            print("\nExiting voice assistant...")
        
        print("Voice assistant session ended.")


if __name__ == "__main__":
    # Allow user to select model and language
    available_models = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
    print("Available Ollama models:")
    print(available_models)
    
    model_name = input("Enter model name (default: llama2): ") or "llama2"
    language = input("Enter language (english/persian, default: english): ") or "english"
    
    # Create and run the assistant
    assistant = VoiceAssistant(model_name=model_name, language=language)
    assistant.run_conversation()
