import os
import subprocess
import io
import tempfile
import datetime
import json
import wave
import logging
import glob
import time  # Add this import for the cleanup delay

from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# For offline speech recognition using Vosk
from vosk import Model, KaldiRecognizer

# For text-to-speech
import pyttsx3

# Load environment variables from .env file
load_dotenv()

# Check if the static folder exists, if not create it
if not os.path.exists('static/css'):
    os.makedirs('static/css')

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'you-will-never-guess')

# Retrieve individual MySQL settings from .env
mysql_user = os.environ.get('MYSQL_USER')
mysql_password = os.environ.get('MYSQL_PASSWORD')
mysql_database = os.environ.get('MYSQL_DATABASE')
mysql_host = os.environ.get('MYSQL_HOST', '127.0.0.1')
mysql_port = os.environ.get('MYSQL_PORT', '3306')

# Build the SQLAlchemy connection string dynamically.
connection_str = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
app.config['SQLALCHEMY_DATABASE_URI'] = connection_str
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configure Flask-Mail (read SMTP settings from environment)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.example.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
mail = Mail(app)

# Configure Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Add logging setup near the top of your file, after imports
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add a template filter for converting newlines to <br> tags
@app.template_filter('nl2br')
def nl2br(value):
    if not value:
        return value
    # First trim the string to remove leading/trailing whitespace
    value = value.strip()
    # Replace newlines with <br> tags
    value = value.replace('\n', '<br>')
    # Remove any double <br> tags that might cause excessive spacing
    while '<br><br><br>' in value:
        value = value.replace('<br><br><br>', '<br><br>')
    return value

# ===========================
# Database Models
# ===========================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    confirmed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    conversations = db.relationship('Conversation', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), default="New Conversation")
    selected_model = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    document_mode = db.Column(db.Boolean, default=False)  # Add this line

    # Update relationship with cascade behavior
    messages = db.relationship('ChatMessage', backref='conversation', cascade="all, delete-orphan", lazy=True)
    documents = db.relationship('Document', backref='conversation', cascade="all, delete-orphan", lazy=True)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender = db.Column(db.String(10))  # 'user' or 'ai'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    filename = db.Column(db.String(256))
    data = db.Column(db.LargeBinary)  # store file as BLOB
    mime_type = db.Column(db.String(128))
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# ===========================
# Flask-Login loader
# ===========================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    return render_template('index.html')

# ===========================
# Ollama model listing at startup
# ===========================
def load_ollama_models():
    try:
        # Run "ollama list" command and capture output.
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
        # Parse the output to extract just the model names (first column)
        models = []
        for line in result.stdout.splitlines():
            if line.strip():
                # Extract just the model name (first word before any whitespace)
                model_name = line.strip().split()[0]
                if model_name and model_name != "NAME":  # Skip header row
                    models.append(model_name)
        logger.info(f"Loaded models: {models}")
        return models
    except Exception as e:
        logger.exception(f"Failed to load Ollama models: {e}")
        return []

ollama_models = load_ollama_models()
app.config['OLLAMA_MODELS'] = ollama_models

def load_vosk_models():
    """Detect available Vosk language models in the models directory"""
    base_path = os.path.join(os.path.dirname(__file__), "models")
    models = []
    
    # Create models directory if it doesn't exist
    if not os.path.exists(base_path):
        try:
            os.makedirs(base_path)
            logger.info(f"Created models directory at {base_path}")
        except Exception as e:
            logger.error(f"Failed to create models directory: {e}")
    
    # Check if the models directory exists and if it has any content
    if os.path.exists(base_path):
        logger.info(f"Checking for models in: {base_path}")
        if not os.listdir(base_path):
            logger.warning(f"Models directory exists but is empty: {base_path}")
    else:
        logger.warning(f"Models directory does not exist at: {base_path}")
    
    # Look for model directories within the models folder
    try:
        # Debug - list found directories to check what's being scanned
        all_dirs = [d for d in glob.glob(os.path.join(base_path, "*")) if os.path.isdir(d)]
        logger.info(f"Found {len(all_dirs)} directories in models folder: {[os.path.basename(d) for d in all_dirs]}")
        
        # Check for models in the main models directory
        for model_dir in all_dirs:
            model_name = os.path.basename(model_dir)
            am_path = os.path.join(model_dir, "am", "final.mdl")
            
            if os.path.exists(am_path):
                logger.info(f"Found valid model: {model_name} at {model_dir}")
                models.append({
                    'id': model_name,
                    'name': get_model_display_name(model_name),
                    'path': model_dir
                })
            else:
                logger.warning(f"Directory {model_name} exists but doesn't have required model files "
                              f"(expected: {am_path})")
        
        # Also check the legacy "model" directory at the app root
        legacy_model = os.path.join(os.path.dirname(__file__), "model")
        if os.path.exists(legacy_model) and os.path.isdir(legacy_model):
            am_path = os.path.join(legacy_model, "am", "final.mdl")
            if os.path.exists(am_path):
                logger.info(f"Found legacy model at: {legacy_model}")
                models.append({
                    'id': 'default',
                    'name': 'English (Default)',
                    'path': legacy_model
                })
            else:
                logger.warning(f"Legacy model directory exists but missing required files: {am_path}")
        else:
            logger.info(f"No legacy model found at: {legacy_model}")
        
        logger.info(f"Found {len(models)} Vosk language models: {[m['id'] for m in models]}")
        return models
    except Exception as e:
        logger.exception(f"Failed to load Vosk language models: {e}")
        return []

def get_model_display_name(model_id):
    """Convert model ID to a user-friendly display name"""
    if model_id == 'default':
        return 'English (Default)'
    
    # Map known model IDs to readable names
    model_names = {
        'vosk-model-fa-0.5': 'Persian',
        'vosk-model-fa-0.4': 'Persian',
        'vosk-model-en-us-0.22': 'English (US)',
        'vosk-model-small-en-us-0.15': 'English (US) - Small',
        'vosk-model-en-us-0.15': 'English (US)',
        'vosk-model-en-us-0.21': 'English (US)',
        'vosk-model-en-in-0.5': 'English (India)',
        'vosk-model-small-fa-0.4': 'Persian - Small',
        'vosk-model-ru-0.22': 'Russian',
        'vosk-model-fr-0.22': 'French',
        'vosk-model-de-0.21': 'German',
        'vosk-model-es-0.42': 'Spanish',
        'vosk-model-it-0.22': 'Italian',
        'vosk-model-cn-0.22': 'Chinese',
        'vosk-model-ja-0.22': 'Japanese',
        'vosk-model-ar-0.22': 'Arabic'
    }
    
    if model_id in model_names:
        return model_names[model_id]
    
    # For unknown models, try to extract language code and clean up the name
    model_id = model_id.replace('vosk-model-', '')
    parts = model_id.split('-')
    
    if len(parts) > 0:
        lang_code = parts[0]
        # Map language codes to full names
        lang_map = {
            'en': 'English',
            'fa': 'Persian',
            'ru': 'Russian',
            'fr': 'French',
            'de': 'German',
            'es': 'Spanish',
            'it': 'Italian',
            'cn': 'Chinese',
            'ja': 'Japanese',
            'ar': 'Arabic'
        }
        if lang_code in lang_map:
            return lang_map[lang_code]
    
    # If all else fails, just use the model ID as the name
    return model_id

# Load voice recognition models at startup
vosk_models = load_vosk_models()
app.config['VOSK_MODELS'] = vosk_models

# ===========================
# Voice Processing functions using Vosk
# ===========================
def check_vosk_model_exists(model_path=None):
    """Check if the specified Vosk model directory exists and contains model files"""
    # If no model path provided, use the default/legacy location
    if not model_path:
        model_path = os.path.join(os.path.dirname(__file__), "model")
    
    am_dir = os.path.join(model_path, "am")
    model_file = os.path.join(am_dir, "final.mdl")
    conf_dir = os.path.join(model_path, "conf")
    
    # Log detailed checks to help diagnose issues
    logger.debug(f"Checking model path: {model_path}")
    logger.debug(f"- Directory exists: {os.path.exists(model_path)}")
    if os.path.exists(model_path):
        logger.debug(f"- Directory contents: {os.listdir(model_path)[:10]}")
    logger.debug(f"- AM directory exists: {os.path.exists(am_dir)}")
    logger.debug(f"- Model file exists: {os.path.exists(model_file)}")
    logger.debug(f"- Conf directory exists: {os.path.exists(conf_dir)}")
    
    # Return a detailed status assessment
    if not os.path.exists(model_path):
        logger.error(f"Model directory not found: {model_path}")
        return False
    if not os.path.exists(am_dir):
        logger.error(f"AM directory not found in {model_path}")
        return False
    if not os.path.exists(model_file):
        logger.error(f"Final.mdl file not found in {am_dir}")
        return False
    if not os.path.exists(conf_dir):
        logger.error(f"Conf directory not found in {model_path}")
        return False
    
    # If we reach here, all checks have passed
    logger.info(f"Vosk model files found successfully in {model_path}")
    return True

def check_ffmpeg_installed():
    """Check if FFmpeg is installed and available in the system path"""
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        logger.info("FFmpeg is installed and available")
        return True
    except FileNotFoundError:
        logger.warning("FFmpeg is not installed or not in system PATH")
        return False

def recognize_audio(file_path, model_id=None):
    try:
        # Verify the file exists and is readable
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            logger.error(f"Audio file does not exist or is empty: {file_path}")
            return "Error: Audio file is missing or empty"
            
        # Log file information for debugging
        logger.info(f"Processing audio file: {file_path}, Size: {os.path.getsize(file_path)} bytes")
        logger.info(f"Using model ID: {model_id}")
        
        # Determine which model to use
        model_path = None
        if (model_id):
            # Look for the specified model in our available models
            for model in app.config['VOSK_MODELS']:
                if model['id'] == model_id:
                    model_path = model['path']
                    break
        
        # If no model path was found, use the default/legacy location
        if not model_path:
            model_path = os.path.join(os.path.dirname(__file__), "model")
            logger.info(f"Using default model path: {model_path}")
        
        # Check if the chosen model exists
        if not check_vosk_model_exists(model_path):
            model_download_instructions = "Download models from https://alphacephei.com/vosk/models/ " \
                                         "and extract them to the 'models' folder in the application directory."
            logger.error(f"Vosk model not found at {model_path}. {model_download_instructions}")
            return f"Voice recognition model is not installed. {model_download_instructions}"
            
        # Create a model instance for Vosk
        logger.info(f"Loading Vosk model from: {model_path}")
        model = Model(model_path)
        
        try:
            # Open the audio file
            wf = wave.open(file_path, "rb")
            
            # Log wave file properties
            logger.info(f"Wave file properties: channels={wf.getnchannels()}, "
                      f"sample width={wf.getsampwidth()}, "
                      f"frame rate={wf.getframerate()}, "
                      f"frames={wf.getnframes()}")
            
            # Check audio format requirements
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
                logger.warning("Converting audio file to compatible format...")
                converted_path = convert_audio_format(file_path)
                if converted_path:
                    wf.close()
                    wf = wave.open(converted_path, "rb")
                else:
                    logger.error("Could not convert audio to required format")
                    return "Could not process audio. Please try again."
            
            # Create recognizer
            recognizer = KaldiRecognizer(model, wf.getframerate())
            recognizer.SetWords(True)  # Enable word timing
            
            # Process audio file
            result_text = ""
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if recognizer.AcceptWaveform(data):
                    result_json = json.loads(recognizer.Result())
                    if 'text' in result_json and result_json['text'].strip():
                        result_text += result_json['text'] + " "
            
            # Get final processing result
            final_json = json.loads(recognizer.FinalResult())
            result_text += final_json.get('text', '')
            
            # Close the file
            wf.close()
            
            # If converted file was created, remove it
            if 'converted_path' in locals() and os.path.exists(converted_path):
                os.remove(converted_path)
            
            if not result_text.strip():
                return "I couldn't hear anything clear. Please try again."
                
            return result_text.strip()
            
        except wave.Error as we:
            logger.error(f"Wave error opening audio file: {we}")
            return f"Error: The audio file format is invalid. {str(we)}"
        
    except Exception as e:
        logger.exception(f"Voice recognition failed: {e}")
        return f"Error processing voice: {str(e)}"

def convert_audio_format(input_path):
    """Convert audio to the format required by Vosk: WAV, 16kHz, 16-bit, mono"""
    try:
        # First check if ffmpeg is available
        if not check_ffmpeg_installed():
            logger.error("FFmpeg is not installed. Cannot convert audio format.")
            return None
            
        import subprocess
        output_path = input_path + ".converted.wav"
        
        logger.info(f"Converting audio file {input_path} to format required by Vosk")
        
        # Use ffmpeg with more explicit parameters to ensure proper WAV format
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,  # -y to overwrite output file
            "-acodec", "pcm_s16le",  # 16-bit PCM
            "-ar", "16000",          # 16kHz sample rate
            "-ac", "1",              # mono channel
            "-f", "wav",             # force WAV format
            output_path
        ], check=True, stderr=subprocess.PIPE)
        
        # Verify the converted file exists and has content
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("Converted file is empty or does not exist")
            return None
            
        logger.info(f"Successfully converted audio to {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e.stderr.decode() if e.stderr else str(e)}")
        return None
    except Exception as e:
        logger.exception(f"Audio conversion failed: {str(e)}")
        return None

def synthesize_speech(text):
    """Convert text to speech using pyttsx3"""
    try:
        engine = pyttsx3.init()
        # Save generated speech to a temporary WAV file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        engine.save_to_file(text, temp_file.name)
        engine.runAndWait()
        return temp_file.name
    except Exception as e:
        logger.exception(f"Text-to-speech failed: {e}")
        return None

def detect_language(audio_file_path):
    """
    Detects whether the audio is in English or Persian.
    Returns the model ID of the detected language.
    """
    logger.info("Detecting language from audio sample...")
    
    # Get available models
    available_models = app.config['VOSK_MODELS']
    
    # If we don't have multiple models, return the default
    if len(available_models) <= 1:
        default_model_id = available_models[0]['id'] if available_models else 'default'
        logger.info(f"Only one model available, using: {default_model_id}")
        logger.info(f"For multiple language support, please install additional language models in the 'models' directory")
        return default_model_id
    
    # Find English and Persian models
    english_model = next((m for m in available_models if 'en' in m['id'].lower() or m['id'] == 'default'), None)
    persian_model = next((m for m in available_models if 'fa' in m['id'].lower() or 'persian' in m['name'].lower()), None)
    
    logger.info(f"Found models - English: {english_model['id'] if english_model else 'None'}, "
               f"Persian: {persian_model['id'] if persian_model else 'None'}")
    
    if not english_model or not persian_model:
        # If either language model is missing, return whatever is available
        default_model = english_model or persian_model or available_models[0]
        logger.warning(f"Missing language models. Using default: {default_model['id']}")
        return default_model['id']
    
    logger.info(f"Testing with English model: {english_model['id']} and Persian model: {persian_model['id']}")
    
    # Process a sample of the audio with both models
    results = {}
    for model in [english_model, persian_model]:
        try:
            # Create a model instance with the specified path
            vosk_model = Model(model['path'])
            
            # Open the audio file
            with wave.open(audio_file_path, "rb") as wf:
                # Check if we need to convert audio format
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
                    logger.warning("Converting audio file to compatible format for language detection...")
                    converted_path = convert_audio_format(audio_file_path)
                    if not converted_path:
                        logger.error("Could not convert audio for language detection")
                        continue
                    wf.close()
                    wf = wave.open(converted_path, "rb")
                
                # Create recognizer
                recognizer = KaldiRecognizer(vosk_model, wf.getframerate())
                
                # Process only the first few seconds (faster detection)
                max_frames = min(wf.getnframes(), wf.getframerate() * 3)  # 3 seconds sample
                
                # Process audio file
                word_count = 0
                confidence_sum = 0
                frames_processed = 0
                
                while frames_processed < max_frames:
                    frames_to_read = min(4000, max_frames - frames_processed)
                    data = wf.readframes(frames_to_read)
                    frames_processed += frames_to_read
                    
                    if len(data) == 0:
                        break
                        
                    if recognizer.AcceptWaveform(data):
                        result_json = json.loads(recognizer.Result())
                        if 'result' in result_json:
                            word_count += len(result_json['result'])
                            # Sum up confidence scores if available
                            for word in result_json['result']:
                                if 'conf' in word:
                                    confidence_sum += word['conf']
                
                # Get final result
                final_json = json.loads(recognizer.FinalResult())
                if 'result' in final_json:
                    word_count += len(final_json['result'])
                    for word in final_json['result']:
                        if 'conf' in word:
                            confidence_sum += word['conf']
                
                # Calculate confidence score
                avg_confidence = confidence_sum / max(1, word_count)
                
                results[model['id']] = {
                    'word_count': word_count,
                    'confidence': avg_confidence
                }
                logger.info(f"Model {model['id']} detected {word_count} words with avg confidence {avg_confidence:.4f}")
        
        except Exception as e:
            logger.exception(f"Error detecting language with model {model['id']}: {e}")
    
    # If we couldn't process with any model, return the default
    if not results:
        logger.warning("Could not detect language, falling back to default")
        return 'default'
    
    # Determine the best model based on word count and confidence
    best_model = None
    best_score = -1
    
    for model_id, result in results.items():
        # Score is a combination of word count and confidence
        score = result['word_count'] * result['confidence']
        if score > best_score:
            best_score = score
            best_model = model_id
    
    # If the best model detected very few words, it might be noise
    # In that case, prefer English (or default) as a fallback
    if results.get(best_model, {}).get('word_count', 0) < 2:
        logger.warning("Very few words detected, defaulting to English")
        return english_model['id']
    
    logger.info(f"Detected language model: {best_model}")
    return best_model

# ===========================
# Routes for Authentication
# ===========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return redirect(url_for('register'))
        user = User(username=username, email=email)
        user.set_password(password)
        user.confirmed = True  # Mark user as active immediately
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! You can now log in.")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        user_id = int(token.split('-')[0])
    except Exception:
        flash("Invalid confirmation token.")
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if user:
        user.confirmed = True
        db.session.commit()
        flash("Your account has been confirmed!")
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.confirmed:
                flash("Please confirm your email before logging in.")
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('chat'))
        flash("Invalid email or password.")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/reset', methods=['GET', 'POST'])
def reset_request():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = f"{user.id}-reset-token"  # Replace with secure token generation.
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message("Password Reset", recipients=[email])
            msg.body = f"Reset your password by clicking on the link: {reset_url}"
            mail.send(msg)
            flash("Password reset email sent.")
        else:
            flash("Email not found.")
    return render_template('reset_request.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        user_id = int(token.split('-')[0])
    except Exception:
        flash("Invalid reset token.")
        return redirect(url_for('reset_request'))
    user = User.query.get(user_id)
    if request.method == 'POST':
        new_password = request.form['password']
        user.set_password(new_password)
        db.session.commit()
        flash("Your password has been updated.")
        return redirect(url_for('login'))
    return render_template('reset_password.html')

# ===========================
# Routes for Chat and Conversations
# ===========================
@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    # Get conversation_id from query params if provided
    conversation_id = request.args.get('conversation_id', None)
    
    # If conversation_id provided, load that specific conversation
    if (conversation_id):
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first_or_404()
    else:
        # Otherwise load most recent conversation or create one
        conversation = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.created_at.desc()).first()
        if not conversation:
            conversation = Conversation(
                user_id=current_user.id,
                title="New Conversation",
                selected_model=(app.config['OLLAMA_MODELS'][0] if app.config['OLLAMA_MODELS'] else "default")
            )
            db.session.add(conversation)
            db.session.commit()
    
    # Get all user's conversations for sidebar
    all_conversations = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.created_at.desc()).all()
    
    # Get messages for current conversation
    messages = ChatMessage.query.filter_by(conversation_id=conversation.id).order_by(ChatMessage.created_at).all()
    
    return render_template('chat.html', 
                          conversation=conversation, 
                          all_conversations=all_conversations,
                          messages=messages, 
                          models=app.config['OLLAMA_MODELS'])

@app.route('/conversation/new', methods=['POST'])
@login_required
def new_conversation():
    # Create a new conversation with a placeholder title
    model = request.form.get('model', app.config['OLLAMA_MODELS'][0] if app.config['OLLAMA_MODELS'] else "default")
    conversation = Conversation(
        user_id=current_user.id,
        title="New Conversation",
        selected_model=model
    )
    db.session.add(conversation)
    db.session.commit()
    
    # No welcome message - we'll start with a blank conversation
    return redirect(url_for('chat', conversation_id=conversation.id))

@app.route('/conversation/<int:conversation_id>/rename', methods=['POST'])
@login_required
def rename_conversation(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    
    # Check ownership
    if conversation.user_id != current_user.id:
        flash("Unauthorized access")
        return redirect(url_for('chat'))
    
    new_title = request.form.get('title', 'Untitled Conversation')
    conversation.title = new_title
    db.session.commit()
    
    flash("Conversation renamed successfully")
    return redirect(url_for('chat', conversation_id=conversation_id))

@app.route('/conversation/<int:conversation_id>/delete', methods=['POST'])
@login_required
def delete_conversation(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    
    # Check ownership
    if conversation.user_id != current_user.id:
        flash("Unauthorized access")
        return redirect(url_for('chat'))
    
    db.session.delete(conversation)
    db.session.commit()
    flash("Conversation deleted")
    return redirect(url_for('chat'))

@app.route('/switch_model', methods=['POST'])
@login_required
def switch_model():
    conversation_id = request.form['conversation_id']
    new_model = request.form['model']
    conversation = Conversation.query.get(conversation_id)
    if conversation and conversation.user_id == current_user.id:
        conversation.selected_model = new_model
        db.session.commit()
        flash("Model switched successfully.")
    return redirect(url_for('chat'))

@app.route('/edit_message/<int:message_id>', methods=['POST'])
@login_required
def edit_message(message_id):
    new_content = request.form['content']
    message = ChatMessage.query.get(message_id)
    if message and message.conversation.user_id == current_user.id:
        message.content = new_content
        db.session.commit()
        flash("Message updated.")
    return redirect(url_for('chat'))

# ===========================
# File and Voice Upload Routes
# ===========================
def extract_text_from_document(document):
    """Extract text content from a document based on its MIME type"""
    try:
        mime_type = document.mime_type
        
        # For plain text files
        if (mime_type == 'text/plain'):
            return document.data.decode('utf-8')
            
        # For PDF files
        elif mime_type == 'application/pdf':
            try:
                import io
                from pdfminer.high_level import extract_text
                
                pdf_file = io.BytesIO(document.data)
                text = extract_text(pdf_file)
                return text
            except ImportError:
                logger.warning("pdfminer.six not installed. Cannot extract PDF text.")
                return "PDF text extraction requires pdfminer.six. Please install it with: pip install pdfminer.six"
                
        # For docx files
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            try:
                import io
                import docx
                
                docx_file = io.BytesIO(document.data)
                doc = docx.Document(docx_file)
                return "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                logger.warning("python-docx not installed. Cannot extract DOCX text.")
                return "DOCX text extraction requires python-docx. Please install it with: pip install python-docx"
        
        # For other formats, return a message
        else:
            return f"Content extraction not supported for {mime_type}. Using filename only."
            
    except Exception as e:
        logger.exception(f"Error extracting text from document: {str(e)}")
        return f"Error extracting text: {str(e)}"

@app.route('/upload_document', methods=['POST'])
@login_required
def upload_document():
    file = request.files['file']
    conversation_id = request.form['conversation_id']
    
    if file:
        try:
            # Get the conversation
            conversation = Conversation.query.get(conversation_id)
            if not conversation or conversation.user_id != current_user.id:
                flash("Unauthorized access")
                return redirect(url_for('chat'))
            
            # Save document to database
            doc = Document(
                conversation_id=conversation_id,
                filename=file.filename,
                data=file.read(),
                mime_type=file.mimetype
            )
            
            # Enable document mode for this conversation
            conversation.document_mode = True
            
            db.session.add(doc)
            db.session.commit()
            
            # Extract document text for context
            file.seek(0)  # Reset file pointer
            
            # Create a system message to indicate document context mode
            system_message = ChatMessage(
                conversation_id=conversation_id,
                sender='ai',
                content=f"📄 Document '{file.filename}' has been uploaded. My responses will now be based only on knowledge from this document."
            )
            db.session.add(system_message)
            db.session.commit()
            
            flash("Document uploaded successfully. AI will now respond based on document content.")
            
        except Exception as e:
            logger.exception(f"Error uploading document: {str(e)}")
            flash(f"Error uploading document: {str(e)}")
            db.session.rollback()
            
    return redirect(url_for('chat', conversation_id=conversation_id))

@app.route('/upload_voice', methods=['POST'])
@login_required
def upload_voice():
    voice_file = request.files['voice']
    conversation_id = request.form['conversation_id']
    model_id = request.form.get('model_id', None)  # Get the selected model_id
    
    logger.info(f"Voice upload request with model_id: {model_id}")
    
    # Check if we need to auto-detect the language
    auto_detect = (model_id == 'auto-detect')
    
    # If no specific model is selected but we have models available, use the first one
    if not model_id and app.config['VOSK_MODELS']:
        model_id = app.config['VOSK_MODELS'][0]['id']
        logger.info(f"No model specified, using default: {model_id}")
    
    # Check if any Vosk model is available
    if not app.config['VOSK_MODELS']:
        model_download_instructions = "Please download speech recognition models from " \
                                     "https://alphacephei.com/vosk/models/ and extract them to the 'models' " \
                                     "directory in the application root."
        return jsonify({
            "success": False,
            "transcription": f"Voice recognition models are not installed. {model_download_instructions}",
            "error": "No models available"
        }), 200
    
    # Check if FFmpeg is installed
    if not check_ffmpeg_installed():
        ffmpeg_instructions = "FFmpeg is required for audio conversion but is not installed. " \
                              "Please install FFmpeg on your system and ensure it's in your PATH."
        return jsonify({
            "success": False,
            "transcription": f"Cannot process audio. {ffmpeg_instructions}",
            "error": "FFmpeg not installed"
        }), 200
    
    if voice_file:
        try:
            # Create a proper temp file with .wav extension
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                temp_path = tmp.name
                voice_file.save(temp_path)
            
            logger.info(f"Saved voice recording to temporary file: {temp_path}")
            
            # Always convert the audio to ensure proper format
            converted_path = convert_audio_format(temp_path)
            if not converted_path:
                logger.error("Failed to convert audio format")
                return jsonify({
                    "success": False,
                    "error": "Failed to convert audio format",
                    "transcription": "Error processing voice. Please try again or type your message."
                }), 500
            
            # Auto-detect language if requested
            detected_language = None
            if auto_detect:
                detected_language = detect_language(converted_path)
                model_id = detected_language
                logger.info(f"Auto-detected language model: {model_id}")
            
            # Use the converted file for recognition with the specified model
            recognized_text = recognize_audio(converted_path, model_id)
            
            # Store the voice recording in the database
            with open(converted_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                
            # Save as a Document with voice recording type
            voice_doc = Document(
                conversation_id=conversation_id,
                filename=f"voice_recording_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav",
                data=audio_data,
                mime_type="audio/wav"
            )
            db.session.add(voice_doc)
            db.session.commit()
            voice_recording_id = voice_doc.id
            
            # Create a message in the database with reference to the voice recording
            message = ChatMessage(
                conversation_id=conversation_id,
                sender='user',
                content=f"VOICE_RECORDING:{voice_recording_id}:{recognized_text}"
            )
            db.session.add(message)
            db.session.commit()
            
            # Now get AI response directly
            conversation = Conversation.query.get(conversation_id)
            if not conversation or conversation.user_id != current_user.id:
                return jsonify({
                    "success": False, 
                    "error": "Unauthorized access to conversation"
                }), 403
                
            # Get the model name from the conversation
            model_name = conversation.selected_model
            
            # Call the AI model with the recognized text
            try:
                # Process with the AI model
                ai_response = call_ai_model(model_name, recognized_text)
                
                # Create and save the AI message
                ai_message = ChatMessage(
                    conversation_id=conversation_id,
                    sender='ai', 
                    content=ai_response
                )
                db.session.add(ai_message)
                db.session.commit()
                
                # Return both the transcription and AI response
                response_data = {
                    "success": True,
                    "transcription": recognized_text,
                    "ai_response": ai_response,
                    "message_id": message.id,
                    "model_id": model_id,
                    "voice_recording_id": voice_recording_id
                }
                
                # Add detected language info if auto-detection was used
                if auto_detect and detected_language:
                    # Find the display name of the detected language model
                    for model in app.config['VOSK_MODELS']:
                        if model['id'] == detected_language:
                            response_data["detected_language"] = model['name']
                            break
                
                return jsonify(response_data)
                
            except Exception as ai_error:
                logger.exception(f"Error getting AI response: {str(ai_error)}")
                return jsonify({
                    "success": True,  # Still success because voice was processed
                    "transcription": recognized_text,
                    "error": f"Error getting AI response: {str(ai_error)}",
                    "message_id": message.id,
                    "voice_recording_id": voice_recording_id
                })
            
        except Exception as e:
            logger.exception(f"Error processing voice: {str(e)}")
            return jsonify({
                "success": False,
                "error": str(e),
                "transcription": "Error processing voice. Please try again or type your message."
            }), 500
        finally:
            # Clean up temporary files
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
                if 'converted_path' in locals() and os.path.exists(converted_path):
                    os.remove(converted_path)
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup of temp files: {cleanup_error}")
    
    return jsonify({
        "success": False,
        "error": "No voice file received"
    }), 400

# Add a new function to call the AI model directly from backend
def call_ai_model(model_name, prompt):
    """Call the AI model synchronously and return the full response"""
    logger.info(f"Calling AI model {model_name} with prompt: {prompt[:50]}...")
    
    # Format prompt properly for shell execution
    formatted_prompt = prompt.replace('"', '\\"')  # Escape double quotes
    
    # Use Ollama run command to get the response
    cmd = ["ollama", "run", model_name, formatted_prompt]
    
    try:
        # Run the command and capture the output
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        response = result.stdout.strip()
        logger.info(f"Received AI response: {response[:50]}...")
        return response
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running Ollama command: {e.stderr}")
        
        # Try alternative command formats for older Ollama versions
        try:
            # Try generate command as fallback
            alt_cmd = ["ollama", "generate", model_name, formatted_prompt]
            alt_result = subprocess.run(alt_cmd, capture_output=True, text=True, check=True)
            return alt_result.stdout.strip()
        except subprocess.CalledProcessError as alt_e:
            logger.error(f"Error running alternative Ollama command: {alt_e.stderr}")
            raise Exception(f"Failed to get response from AI model: {e.stderr}")

# Add a route to get the voice recording
@app.route('/voice_recording/<int:recording_id>', methods=['GET'])
@login_required
def get_voice_recording(recording_id):
    """Return the voice recording audio file"""
    temp_file_path = None
    try:
        # Get the document
        voice_doc = Document.query.get_or_404(recording_id)
        
        # Check if the voice belongs to a conversation owned by the current user
        conversation = Conversation.query.get(voice_doc.conversation_id)
        if not conversation or conversation.user_id != current_user.id:
            return "Unauthorized", 403
        
        # Create a temporary file to serve
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            tmp.write(voice_doc.data)
            temp_file_path = tmp.name
        
        # Send the file without using the unsupported after_request parameter
        return send_file(
            temp_file_path,
            mimetype=voice_doc.mime_type,
            as_attachment=False,
            download_name=voice_doc.filename
        )
    except Exception as e:
        logger.exception(f"Error retrieving voice recording: {str(e)}")
        return f"Error retrieving voice recording: {str(e)}", 500
    finally:
        # Clean up the temporary file in a background thread to ensure
        # it happens after the file is served
        if temp_file_path and os.path.exists(temp_file_path):
            def cleanup_temp_file():
                try:
                    # Add a small delay to ensure file serving completes
                    time.sleep(1)
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to remove temporary file {temp_file_path}: {cleanup_error}")
            
            import threading
            cleanup_thread = threading.Thread(target=cleanup_temp_file)
            cleanup_thread.daemon = True
            cleanup_thread.start()

@app.route('/vosk_model_status', methods=['GET'])
@login_required
def vosk_model_status():
    """Check if the Vosk model is properly installed and return status information"""
    try:
        model_installed = check_vosk_model_exists()
        model_path = os.path.join(os.path.dirname(__file__), "model")
        
        # Get additional details if model directory exists
        model_details = {}
        if os.path.exists(model_path):
            model_details['path'] = model_path
            model_details['files'] = os.listdir(model_path)[:10]  # List up to first 10 files
            model_details['has_final_mdl'] = os.path.exists(os.path.join(model_path, "am", "final.mdl"))
            model_details['has_conf'] = os.path.exists(os.path.join(model_path, "conf"))
            model_details['directory_size'] = sum(os.path.getsize(os.path.join(model_path, f)) 
                                                 for f in os.listdir(model_path) 
                                                 if os.path.isfile(os.path.join(model_path, f)))
        
        return jsonify({
            "success": model_installed,
            "message": "Voice recognition model is properly installed" if model_installed else 
                      "Voice recognition model is not installed or is missing required files",
            "model_details": model_details if os.path.exists(model_path) else {}
        })
    except Exception as e:
        logger.exception(f"Error checking Vosk model status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Add a new route for the Voice Help page
@app.route('/voice_help')
def voice_help():
    """Provides detailed instructions for setting up voice recognition"""
    return render_template('voice_help.html')

@app.route('/vosk_available_models', methods=['GET'])
@login_required
def vosk_available_models():
    """Return a list of available Vosk speech recognition models"""
    try:
        # Refresh the model list to catch any newly added models
        refreshed_models = load_vosk_models()
        app.config['VOSK_MODELS'] = refreshed_models
        
        # Add model paths in response for debugging
        model_details = []
        for model in refreshed_models:
            model_detail = {
                'id': model['id'],
                'name': model['name'],
                'path': model['path'],
                'valid': check_vosk_model_exists(model['path'])
            }
            model_details.append(model_detail)
            
        return jsonify({
            "success": True,
            "models": refreshed_models,
            "model_details": model_details
        })
    except Exception as e:
        logger.exception(f"Error getting Vosk models: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ===========================
# Endpoint to Call the AI Model and Stream Response
# ===========================
def stream_ollama_response(model_name, prompt):
    """Stream-only function that doesn't touch the database"""
    # Clean up model name - ensure it's just the base name without any metadata
    model_name = model_name.strip().split()[0]
    logger.info(f"Starting Ollama stream with model: {model_name}")
    
    # Format prompt properly for shell execution
    formatted_prompt = prompt.replace('"', '\\"')  # Escape double quotes
    
    # Create a direct fallback model - if one model doesn't work, try the other
    available_models = app.config['OLLAMA_MODELS']
    fallback_model = None
    for m in available_models:
        if m != model_name:
            fallback_model = m
            break
    
    if fallback_model:
        logger.info(f"Will use {fallback_model} as fallback if {model_name} fails")
    
    # Ollama run command (without the --prompt flag)
    cmd = ["ollama", "run", model_name, formatted_prompt]
    logger.info(f"Command: {' '.join(cmd)}")
    
    # First try quick-blocking call to see if model gives any response
    logger.info("Trying quick-blocking call first")
    try:
        test_proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8  # Higher timeout for first call
        )
        
        if test_proc.stdout.strip():
            logger.info(f"Quick-blocking call succeeded! First 50 chars: {test_proc.stdout[:50]}")
            # Since we already have a full response, just return it
            escaped_text = json.dumps({"text": test_proc.stdout})
            yield f"data: {escaped_text}\n\n"
            return
        else:
            logger.warning("Quick-blocking call returned empty response")
            logger.warning(f"stderr: {test_proc.stderr}")
            
            # If we got here, try with the fallback model immediately
            if fallback_model:
                logger.info(f"Trying fallback model {fallback_model} with blocking call")
                fallback_cmd = ["ollama", "run", fallback_model, formatted_prompt]
                try:
                    fallback_proc = subprocess.run(
                        fallback_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=8
                    )
                    
                    if fallback_proc.stdout.strip():
                        logger.info(f"Fallback model succeeded! First 50 chars: {fallback_proc.stdout[:50]}")
                        fallback_message = f"Note: I switched to the {fallback_model} model because {model_name} didn't respond.\n\n"
                        full_response = fallback_message + fallback_proc.stdout
                        escaped_text = json.dumps({"text": full_response})
                        yield f"data: {escaped_text}\n\n"
                        return
                except Exception as e:
                    logger.exception(f"Error with fallback model blocking call: {e}")
    except subprocess.TimeoutExpired:
        logger.warning("Quick-blocking call timed out")
    except Exception as e:
        logger.exception(f"Error in quick-blocking call: {e}")
        
    # If we're here, quick calls failed - try with different approaches
    approaches = [
        # Standard streaming approach
        {
            "cmd": ["ollama", "run", model_name, formatted_prompt],
            "name": "Standard streaming"
        },
        # Try with --verbose flag if available
        {
            "cmd": ["ollama", "run", "--verbose", model_name, formatted_prompt],
            "name": "Verbose streaming"
        },
        # Try with --quiet flag (complete opposite approach)
        {
            "cmd": ["ollama", "run", "--quiet", model_name, formatted_prompt],
            "name": "Quiet mode"
        },
        # Try using different API endpoints
        {
            "cmd": ["ollama", "generate", model_name, formatted_prompt],
            "name": "Generate API"
        },
        # Try with fallback model if available
        {
            "cmd": ["ollama", "run", fallback_model, formatted_prompt] if fallback_model else None,
            "name": f"Fallback model: {fallback_model}"
        }
    ]
    
    # Keep track of which approaches we've tried
    tried_approaches = set()
    
    # Try approaches until one works
    for approach in approaches:
        if not approach["cmd"]:
            continue
            
        cmd_str = " ".join(approach["cmd"])
        if cmd_str in tried_approaches:
            continue
            
        tried_approaches.add(cmd_str)
        logger.info(f"Trying approach: {approach['name']}")
        logger.info(f"Command: {' '.join(approach['cmd'])}")
        
        try:
            process = subprocess.Popen(
                approach["cmd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Set tight timeout for first response
            first_response_deadline = time.time() + 10
            any_output = False
            buffer = ""
            chunk_count = 0
            
            # Set non-blocking mode for stdout
            import fcntl, os
            fd = process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
            
            # Loop until timeout or process ends
            while process.poll() is None:
                # Check for first response timeout
                if not any_output and time.time() > first_response_deadline:
                    logger.warning(f"No initial response after 10 seconds from approach: {approach['name']}")
                    break
                    
                try:
                    # Try to read from stdout
                    chunk = process.stdout.read(100)  # Read up to 100 chars at a time
                    if chunk:
                        any_output = True
                        buffer += chunk
                        
                        # Send when we have enough text
                        if len(buffer) > 10 or '\n' in buffer:
                            chunk_count += 1
                            logger.info(f"Got output from {approach['name']}, chunk #{chunk_count}, length: {len(buffer)}")
                            
                            # Send the chunk to client
                            escaped_text = json.dumps({"text": buffer})
                            yield f"data: {escaped_text}\n\n"
                            buffer = ""
                except (IOError, OSError):
                    # No data available, wait a bit
                    time.sleep(0.1)
            
            # If we got any output, continue reading until the process ends
            if any_output:
                logger.info(f"Approach {approach['name']} produced output, continuing to read")
                
                # Send any remaining buffered content
                if buffer:
                    escaped_text = json.dumps({"text": buffer})
                    yield f"data: {escaped_text}\n\n"
                    buffer = ""
                
                # Read the rest of the output
                stdout_remainder, stderr_output = process.communicate()
                if stdout_remainder:
                    escaped_text = json.dumps({"text": stdout_remainder})
                    yield f"data: {escaped_text}\n\n"
                
                # We're done with this approach
                return
                
            # If we didn't get any output, kill process and try next approach
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        
        except Exception as e:
            logger.exception(f"Error with approach {approach['name']}: {e}")
    
    # If we get here, all approaches failed
    logger.error("All approaches failed - sending emergency response")
    
    # Create a detailed error message for the user
    error_text = f"""
I'm having trouble generating a response right now. 

Technical details:
- Selected model: {model_name}
- Tried {len(tried_approaches)} different approaches
- No output was generated

You can try:
1. Using a simpler prompt
2. Switching to the other available model
3. Restarting the Ollama service
4. Checking if your prompt contains content that the model may be filtering

Here's a simple response instead: Hello! I'm here to help you with any questions you might have.
"""
    
    escaped_text = json.dumps({"text": error_text})
    yield f"data: {escaped_text}\n\n"

@app.route('/call_model', methods=['POST'])
@login_required
def call_model():
    logger.info(f"Received /call_model request from user {current_user.id}")
    conversation_id = request.form['conversation_id']
    prompt = request.form['prompt']
    logger.info(f"Request details - conversation_id: {conversation_id}, prompt: {prompt[:50]}...")

    # Get conversation
    conversation = Conversation.query.get(conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        logger.warning(f"Unauthorized access attempt to conversation {conversation_id}")
        return "Unauthorized", 403

    # Extract needed values
    conv_id = conversation.id
    model_name = conversation.selected_model
    logger.info(f"Using model: {model_name}")

    # Save user message
    user_message = ChatMessage(conversation_id=conv_id, sender='user', content=prompt)
    db.session.add(user_message)
    db.session.commit()
    logger.info(f"Saved user message with ID {user_message.id}")

    # Check if conversation is in document mode
    document_context = ""
    if conversation.document_mode:
        # Get the latest document for this conversation
        latest_doc = Document.query.filter_by(conversation_id=conv_id).order_by(Document.uploaded_at.desc()).first()
        if latest_doc:
            # Extract text from the document
            doc_text = extract_text_from_document(latest_doc)

            # Create a document context preamble
            document_context = f"""
This conversation is in DOCUMENT MODE. You are analyzing a document titled "{latest_doc.filename}".
Your answers should ONLY be based on the content of this document.
If the answer is not in the document, say "I don't see information about this in the document."
Do not make up information or use your general knowledge.

DOCUMENT CONTENT:
{doc_text[:8000]}  # Limiting to 8000 chars to avoid token limits

Now respond to the user's query about this document:
"""
            logger.info(f"Conversation {conv_id} is in document mode, using context from document {latest_doc.id}")

    # Create wrapper that will capture the full response and save after streaming
    def response_wrapper():
        logger.info("Starting response_wrapper generator")
        full_response = ""
        ai_message_saved = False

        try:
            logger.info("Beginning streaming from Ollama")

            # Use the document context if available, otherwise just the user prompt
            final_prompt = document_context + prompt if document_context else prompt

            # Get context from recent messages 
            with app.app_context():
                # Get the last 5 messages from the conversation
                recent_messages = ChatMessage.query.filter_by(conversation_id=conv_id).order_by(ChatMessage.created_at.desc()).limit(5).all()

            # Format the recent messages into a context string
            context = ""
            for msg in reversed(recent_messages):
                context += f"{msg.sender}: {msg.content}\n"

            # Add the context to the prompt
            final_prompt = f"""
You are an AI assistant having a conversation with a user. Remember previous messages and information.
Here is the recent conversation history:
{context}

Now respond to the user's query:
{prompt}
"""

            # Generate streaming response
            for chunk in stream_ollama_response(model_name, final_prompt):
                # Extract text from the SSE format
                if chunk.startswith('data: '):
                    try:
                        data = json.loads(chunk[6:].strip())
                        if 'text' in data:
                            chunk_text = data['text']
                            full_response += chunk_text
                            
                            # Save the response to database after receiving content
                            # but only do it once to avoid duplicate messages
                            if chunk_text.strip() and not ai_message_saved:
                                try:
                                    with app.app_context():
                                        ai_message = ChatMessage(
                                            conversation_id=conv_id,
                                            sender='ai',
                                            content=chunk_text
                                        )
                                        db.session.add(ai_message)
                                        db.session.commit()
                                        ai_message_saved = True
                                        logger.info(f"Saved initial AI response to database")
                                except Exception as db_err:
                                    logger.exception(f"Error saving to database: {db_err}")
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse chunk as JSON: {chunk}")
                        
                yield chunk

            # After all chunks are processed, update the AI message with the complete response
            if full_response and ai_message_saved:
                try:
                    with app.app_context():
                        # Find the message we created earlier and update it
                        ai_message = ChatMessage.query.filter_by(
                            conversation_id=conv_id,
                            sender='ai'
                        ).order_by(ChatMessage.created_at.desc()).first()
                        
                        if ai_message:
                            ai_message.content = full_response
                            db.session.commit()
                            logger.info("Updated AI message with complete response")
                except Exception as db_err:
                    logger.exception(f"Error updating AI message: {db_err}")
            
            # If no AI message was saved but we have a response, create one now
            elif full_response and not ai_message_saved:
                try:
                    with app.app_context():
                        ai_message = ChatMessage(
                            conversation_id=conv_id,
                            sender='ai',
                            content=full_response
                        )
                        db.session.add(ai_message)
                        db.session.commit()
                        logger.info("Saved complete AI response to database")
                except Exception as db_err:
                    logger.exception(f"Error saving complete response: {db_err}")

        except Exception as e:
            logger.exception(f"Error in response_wrapper: {str(e)}")
            error_json = json.dumps({"error": str(e)})
            yield f"data: {error_json}\n\n"

    logger.info("Returning streaming response")
    return Response(response_wrapper(), mimetype='text/event-stream')

# Add a route to toggle document mode
@app.route('/toggle_document_mode/<int:conversation_id>', methods=['POST'])
@login_required
def toggle_document_mode(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    
    # Check ownership
    if conversation.user_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    try:
        # Toggle document mode
        conversation.document_mode = not conversation.document_mode
        
        # Add a system message to indicate the change
        message_text = ""
        if conversation.document_mode:
            # Find the latest document
            latest_doc = Document.query.filter_by(conversation_id=conversation_id).order_by(Document.uploaded_at.desc()).first()
            if latest_doc:
                message_text = f"📄 Document mode enabled. My responses will now be based only on document: '{latest_doc.filename}'."
            else:
                message_text = "📄 Document mode enabled, but no documents found. Please upload a document."
        else:
            message_text = "📄 Document mode disabled. I'll now use my general knowledge to answer your questions."
        
        system_message = ChatMessage(
            conversation_id=conversation_id,
            sender='ai',
            content=message_text
        )
        
        db.session.add(system_message)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "document_mode": conversation.document_mode,
            "message": message_text
        })
    except Exception as e:
        logger.exception(f"Error toggling document mode: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

# Add a new route to update conversation title directly
@app.route('/conversation/<int:conversation_id>/update_title', methods=['POST'])
@login_required
def update_conversation_title(conversation_id):
    """Update a conversation title and save it to the database"""
    try:
        conversation = Conversation.query.get_or_404(conversation_id)
        
        # Check ownership
        if conversation.user_id != current_user.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403
            
        data = request.get_json()
        if not data or 'title' not in data:
            return jsonify({"success": False, "error": "No title provided"}), 400
            
        title = data['title'].strip()
        if not title:
            title = "Untitled Conversation"
        
        # Update the title in the database
        conversation.title = title
        db.session.commit()
        logger.info(f"Title updated for conversation {conversation_id}: '{title}'")
        
        return jsonify({
            "success": True,
            "title": title
        })
    except Exception as e:
        logger.exception(f"Error updating conversation title: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

def generate_ai_title(model_name, user_prompt, ai_response):
    """Generate a conversation title using the AI model"""
    
    # Create a specific prompt to ask the AI for a title
    title_prompt = f"""Based on this conversation:
User: {user_prompt}
Assistant: {ai_response[:200]}...

Generate a very brief, concise title (maximum 4-5 words) that captures the main topic.
Format your response as ONLY the title text with no additional commentary or punctuation."""
    
    try:
        cmd = ["ollama", "run", model_name, title_prompt]
        # Use a synchronous call to get the title
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        
        title = ""
        if process.returncode == 0:
            # Clean up the response - take only the first line and strip any quotes or extra whitespace
            title = stdout.strip().split('\n')[0].strip('"\'').strip()
            if len(title) > 50:
                # If the title is too long, truncate it
                title = title[:47] + "..."
            if not title:
                title = "New Conversation"
        else:
            logger.warning(f"Title generation failed: {stderr}")
            title = "New Conversation"
    except Exception as e:
        logger.exception(f"Error generating title: {str(e)}")
        title = "New Conversation"
    
    return title

# ===========================
# Endpoint to Synthesize Text-to-Speech
# ===========================
@app.route('/synthesize', methods=['POST'])
@login_required
def synthesize():
    text = request.form['text']
    try:
        audio_path = synthesize_speech(text)
        if not audio_path:
            return "Error synthesizing speech", 500
        return send_file(audio_path, mimetype="audio/wav", as_attachment=True, download_name="response.wav")
    except Exception as e:
        return f"Error synthesizing speech: {e}", 500

# Add a new route to test audio file formats
@app.route('/audio_test', methods=['POST'])
@login_required
def audio_test():
    """Diagnostic endpoint for testing audio file formats"""
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
        
    audio_file = request.files['audio']
    
    try:
        # Save the original file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            orig_path = tmp.name
            audio_file.save(orig_path)
        
        # Get file info
        file_info = {
            "original_size": os.path.getsize(orig_path),
            "original_path": orig_path,
        }
        
        # Try to open as wave file
        try:
            with wave.open(orig_path, 'rb') as wf:
                file_info["wave_info"] = {
                    "channels": wf.getnchannels(),
                    "sample_width": wf.getsampwidth(),
                    "frame_rate": wf.getframerate(),
                    "n_frames": wf.getnframes(),
                    "compression": wf.getcomptype()
                }
        except Exception as wave_err:
            file_info["wave_error"] = str(wave_err)
            
        # Try converting with ffmpeg
        try:
            conv_path = convert_audio_format(orig_path)
            if conv_path:
                file_info["converted_path"] = conv_path
                file_info["converted_size"] = os.path.getsize(conv_path)
                
                # Get info about converted file
                with wave.open(conv_path, 'rb') as wf:
                    file_info["converted_wave_info"] = {
                        "channels": wf.getnchannels(),
                        "sample_width": wf.getsampwidth(),
                        "frame_rate": wf.getframerate(),
                        "n_frames": wf.getnframes(),
                        "compression": wf.getcomptype()
                    }
        except Exception as conv_err:
            file_info["conversion_error"] = str(conv_err)
            
        return jsonify({
            "success": True,
            "file_info": file_info
        })
            
    except Exception as e:
        logger.exception("Error in audio test endpoint")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    finally:
        # Cleanup
        if 'orig_path' in locals() and os.path.exists(orig_path):
            os.remove(orig_path)
        if 'conv_path' in locals() and os.path.exists(conv_path):
            os.remove(conv_path)

# Add a function to check system dependencies at startup
def check_system_dependencies():
    """Check if all required system dependencies are available"""
    dependencies = {
        "ffmpeg": check_ffmpeg_installed()
    }
    
    for dep, available in dependencies.items():
        if available:
            logger.info(f"Dependency check: {dep} is available")
        else:
            logger.warning(f"Dependency check: {dep} is NOT available")
    
    return dependencies

# Main entry point
if __name__ == '__main__':
    # Check dependencies
    system_deps = check_system_dependencies()
    
    with app.app_context():
        # Ensure tables exist.
        db.create_all()
    app.run(debug=True)