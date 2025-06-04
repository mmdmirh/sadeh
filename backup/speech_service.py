import os
import tempfile
import logging
import torch
import nltk
import numpy as np
# Import faster-whisper instead of whisper
from faster_whisper import WhisperModel
import sounddevice as sd
from transformers import AutoProcessor, BarkModel

# Configure logging
logger = logging.getLogger(__name__)

class SpeechService:
    """Service for speech recognition and synthesis using faster-whisper and Bark."""
    
    def __init__(self):
        # Initialize Whisper for speech recognition
        self.whisper_model = None
        # Initialize Bark TTS
        self.tts_service = None
        
    def load_whisper_model(self, model_name="base"):
        """Load the faster-whisper speech recognition model."""
        if self.whisper_model is None:
            try:
                logger.info(f"Loading faster-whisper model: {model_name}")
                # Pass a longer timeout (60 seconds) for downloading the model
                self.whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
                logger.info("faster-whisper model loaded successfully")
            except Exception as e:
                logger.exception(f"Error loading faster-whisper model: {e}")
                # Fallback to CPU with different compute type if needed
                try:
                    self.whisper_model = WhisperModel(model_name, device="cpu", compute_type="float32")
                    logger.info("faster-whisper model loaded with fallback settings")
                except Exception as e2:
                    logger.exception(f"Fallback model loading also failed: {e2}")
                    raise
        return self.whisper_model
    
    def get_tts_service(self):
        """Get or initialize the TTS service."""
        if self.tts_service is None:
            self.tts_service = TextToSpeechService()
        return self.tts_service
    
    def transcribe_audio(self, audio_data, language=None):
        """
        Transcribe audio data to text using faster-whisper.
        
        Args:
            audio_data: Binary audio data
            language: Optional language code to force language
            
        Returns:
            dict: Transcription result with text and detected language
        """
        # Ensure Whisper model is loaded
        if self.whisper_model is None:
            self.load_whisper_model()
            
        # Save audio data to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            temp_path = tmp.name
            tmp.write(audio_data)
        
        try:
            # Set transcription options
            options = {}
            if language:
                options["language"] = language
            
            # Transcribe with faster-whisper
            logger.info("Transcribing with faster-whisper...")
            segments, info = self.whisper_model.transcribe(
                temp_path,
                language=language,
                beam_size=5
            )
            
            # Collect all segments into one text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)
            
            full_text = " ".join(text_parts).strip()
            detected_language = info.language
            
            logger.info(f"Transcription complete: {full_text[:50]}...")
            
            # Return transcription and detected language
            return {
                "text": full_text,
                "language": detected_language
            }
            
        finally:
            # Clean up temporary file
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Error removing temp file: {e}")
    
    def synthesize_speech(self, text, language="english"):
        """
        Convert text to speech using Bark.
        
        Args:
            text: Text to synthesize
            language: Language for voice selection
            
        Returns:
            tuple: (sample_rate, audio_data) or None if failed
        """
        tts = self.get_tts_service()
        
        # Map language to voice preset
        voice_presets = {
            "english": "v2/en_speaker_1",
            "persian": "v2/fa_speaker_1",  # Default for Persian (might need customization)
            "fr": "v2/fr_speaker_1",
            "es": "v2/es_speaker_1",
            "de": "v2/de_speaker_1",
            "it": "v2/it_speaker_1",
            "ja": "v2/ja_speaker_1",
        }
        
        # Get appropriate voice preset
        voice_preset = voice_presets.get(language.lower(), "v2/en_speaker_1")
        
        try:
            # Generate speech with Bark
            return tts.long_form_synthesize(text, voice_preset)
        except Exception as e:
            logger.exception(f"Error synthesizing speech: {e}")
            return None
    
    def save_audio_to_file(self, sample_rate, audio_data):
        """
        Save audio data to a temporary WAV file.
        
        Args:
            sample_rate: Audio sample rate
            audio_data: Audio array
            
        Returns:
            str: Path to saved audio file or None if failed
        """
        try:
            import soundfile as sf
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            file_path = temp_file.name
            temp_file.close()
            
            # Save audio to file
            sf.write(file_path, audio_data, sample_rate)
            return file_path
        except Exception as e:
            logger.exception(f"Error saving audio to file: {e}")
            return None

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
        # Make sure NLTK tokenizers are available
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            logger.info("NLTK 'punkt' not found. Downloading...")
            nltk.download('punkt', quiet=True)
        # === Add check for punkt_tab ===
        try:
            # Check specifically for the English punkt_tab data
            nltk.data.find('tokenizers/punkt_tab/english')
        except LookupError:
            logger.info("NLTK 'punkt_tab' not found. Downloading...")
            nltk.download('punkt_tab', quiet=True)
        # === End check for punkt_tab ===

        pieces = []
        try:
            sentences = nltk.sent_tokenize(text)
        except Exception as e:
            logger.error(f"NLTK sentence tokenization failed: {e}. Synthesizing text as a whole.")
            # Fallback: synthesize the whole text if tokenization fails
            sentences = [text]

        silence = np.zeros(int(0.25 * self.model.generation_config.sample_rate))

        for sent in sentences:
            # Add a small check for empty sentences which can cause issues
            if not sent.strip():
                continue
            try:
                sample_rate, audio_array = self.synthesize(sent, voice_preset)
                pieces += [audio_array, silence.copy()]
            except Exception as synth_error:
                logger.error(f"Error synthesizing sentence: '{sent[:30]}...': {synth_error}")
                # Optionally skip the problematic sentence or handle differently

        if not pieces:
             logger.warning("No audio pieces were generated.")
             # Return silence or handle as appropriate
             return self.model.generation_config.sample_rate, np.zeros(1)


        # Ensure sample_rate is defined even if loop didn't run (though 'if not pieces' handles this)
        final_sample_rate = self.model.generation_config.sample_rate

        return final_sample_rate, np.concatenate(pieces)

# Create a singleton instance
speech_service = SpeechService()
