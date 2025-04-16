import os
import io
import tempfile
import datetime
import json
import wave
import logging
import glob
import time
import threading

from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file, jsonify, session, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import subprocess
from ollama import RequestError, ResponseError

# Import our new LLM service abstraction
from llm_service import LLMServiceFactory

# Import the speech service we created
from speech_service import speech_service

# Load environment variables from .env file
load_dotenv()

# Ensure static directories exist
if not os.path.exists('static'):
    os.makedirs('static')
if not os.path.exists('static/css'): # Corrected line
    os.makedirs('static/css')
if not os.path.exists('static/js'):
    os.makedirs('static/js')
if not os.path.exists('static/uploads'):
    os.makedirs('static/uploads')

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'you-will-never-guess')

# Retrieve individual MySQL settings from .env
mysql_user = os.environ.get('MYSQL_USER')
mysql_password = os.environ.get('MYSQL_PASSWORD')
mysql_database = os.environ.get('MYSQL_DATABASE')
# Use the Docker service name 'mysql' or the env var if set
mysql_host = os.environ.get('MYSQL_HOST', 'mysql')
mysql_port = os.environ.get('MYSQL_PORT', '3306') # Internal Docker port

# Build the SQLAlchemy connection string dynamically.
connection_str = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
app.config['SQLALCHEMY_DATABASE_URI'] = connection_str
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy AFTER app is created and configured
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

# === Initialize LLM Service ===
llm_service_type = os.environ.get('LLM_SERVICE', 'ollama').lower()
logger.info(f"Initializing LLM service of type: {llm_service_type}")
llm_service = LLMServiceFactory.create_service()

# Define a default model name based on the LLM service type
if llm_service_type == 'ollama':
    DEFAULT_MODEL_NAME = os.environ.get('DEFAULT_MODEL_NAME', "gemma3:1b")
else:  # llamacpp
    DEFAULT_MODEL_NAME = os.environ.get('LLAMACPP_MODEL', "llama-2-7b-chat.Q4_K_M.gguf")

logger.info(f"Using default model: {DEFAULT_MODEL_NAME}")

# Add a template filter for converting newlines to <br> tags
@app.template_filter('nl2br')
def nl2br(value):
    # First trim the string to remove leading/trailing whitespace
    if not value:
        return value
    value = value.strip()
    # Replace newlines with <br> tags
    value = value.replace('\n', '<br>')
    # Remove any double <br> tags that might cause excessive spacing
    while '<br><br><br>' in value:
        value = value.replace('<br><br><br>', '<br><br>')
    return value

# Print all registered routes for debugging (always runs)
print("\n=== Registered Flask Routes ===")
try:
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule}")
except Exception as e:
    print(f"Error printing routes: {e}")
print("==============================\n")

# ===========================
# Database Models
# ===========================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Increase length from 256 to 512 to accommodate modern hashes like scrypt
    password_hash = db.Column(db.String(512))
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
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

# ===========================
# Ollama model listing at startup
# ===========================
def load_llm_models():
    """Load models from the configured LLM service"""
    try:
        logger.info(f"Attempting to list models from {llm_service_type} service")
        models = llm_service.list_models()
        
        if not models:
            logger.warning(f"No models found. Will use default model: {DEFAULT_MODEL_NAME}")
            models.append(DEFAULT_MODEL_NAME)
        else:
            logger.info(f"Successfully loaded models from {llm_service_type} service: {models}")
        return models
    except Exception as e:
        logger.exception(f"Error loading {llm_service_type} models: {e}")
        return [DEFAULT_MODEL_NAME]

llm_models = load_llm_models()
# Ensure there's at least a default model name in the config, even if loading failed
app.config['LLM_MODELS'] = llm_models if llm_models else [DEFAULT_MODEL_NAME]
logger.info(f"Using models for dropdown: {app.config['LLM_MODELS']}")

# ===========================
# Voice Processing functions using faster-whisper & Bark (via speech_service)
# ===========================
def check_whisper_model_exists(model_name="base"):
    """Check if the specified faster-whisper model can be loaded via speech_service"""
    try:
        speech_service.load_whisper_model(model_name)
        logger.info(f"Whisper model '{model_name}' is available via speech_service")
        return True
    except Exception as e:
        logger.exception(f"Error checking Whisper model via speech_service: {e}")
        return False

def check_ffmpeg_installed():
    """Check if FFmpeg is installed and available in the system path"""
    try:
        # Keep using subprocess for ffmpeg check
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        logger.info("FFmpeg is installed and available")
        return True
    except FileNotFoundError:
        logger.warning("FFmpeg is not installed or not in system PATH")
        return False
    except subprocess.CalledProcessError:
        # Handles cases where ffmpeg exists but returns non-zero exit code on -version
        logger.info("FFmpeg is installed (returned non-zero on -version, but likely ok)")
        return True
    except Exception as e:
        logger.error(f"Error checking FFmpeg: {e}")
        return False

def recognize_audio(file_path, language=None):
    """Recognize audio using speech_service"""
    try:
        # Verify the file exists and is readable
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            logger.error(f"Audio file does not exist or is empty: {file_path}")
            return {"text": "Error: Audio file is missing or empty", "language": "en"}

        logger.info(f"Processing audio file: {file_path}, Size: {os.path.getsize(file_path)} bytes")
        # Clarify that 'language' here is the code passed to the service
        logger.info(f"Using language code hint for transcription: {language}")

        # Read the audio file into memory
        with open(file_path, 'rb') as f:
            audio_data = f.read()

        # Transcribe using speech_service
        result = speech_service.transcribe_audio(audio_data, language=language)

        # Return the result dictionary
        return result

    except Exception as e:
        logger.exception(f"Voice recognition failed: {e}")
        return {"text": f"Error processing voice: {str(e)}", "language": "en"}

def convert_audio_format(input_path):
    """Convert audio to the format required by Whisper: WAV, 16kHz, 16-bit, mono"""
    try:
        # First check if ffmpeg is available
        if not check_ffmpeg_installed():
            logger.error("FFmpeg is not installed. Cannot convert audio format.")
            return None
        
        output_path = input_path + ".converted.wav"
        logger.info(f"Converting audio file {input_path} to format required by Whisper")
        
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

def detect_language(audio_file_path):
    """Detects language from audio using faster-whisper via speech_service.
    Returns the detected language code (e.g., 'en', 'fa').
    """
    logger.info("Detecting language from audio sample...")
    try:
        # Read audio file
        with open(audio_file_path, 'rb') as f:
            audio_data = f.read()

        # Use speech service to transcribe without specifying a language
        result = speech_service.transcribe_audio(audio_data)

        # Return the detected language code
        detected_language = result.get("language", "en")
        logger.info(f"Detected language code: {detected_language}")
        return detected_language

    except Exception as e:
        logger.exception(f"Language detection failed: {e}")
        return "en"  # Default to English on error

# ===========================
# Routes for Authentication
# ===========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        logger.info(f"Registration attempt - Username: '{username}', Email: '{email}'") # Add logging

        existing_user_by_username = User.query.filter_by(username=username).first()
        existing_user_by_email = User.query.filter_by(email=email).first()

        error = False
        if existing_user_by_username:
            logger.warning(f"Registration failed: Username '{username}' already exists.") # Add logging
            flash("Username already exists. Please choose a different one.")
            error = True
        if existing_user_by_email:
            logger.warning(f"Registration failed: Email '{email}' already registered.") # Add logging
            flash("Email address already registered. Please log in or use a different email.")
            error = True

        if error:
            logger.info("Redirecting back to register page due to duplicate username/email.") # Add logging
            return redirect(url_for('register'))

        # If checks pass, create the new user
        logger.info(f"Proceeding with registration for Username: '{username}', Email: '{email}'") # Add logging
        user = User(username=username, email=email)
        user.set_password(password)
        user.confirmed = True
        try:
            db.session.add(user)
            db.session.commit()
            logger.info(f"User '{username}' registered successfully.") # Add logging
            flash("Registration successful! You can now log in.")
            return redirect(url_for('login'))
        except Exception as e: # Catch potential commit errors (though checks should prevent most)
             logger.error(f"Error during user registration commit: {e}")
             db.session.rollback()
             flash("An error occurred during registration. Please try again.")
             return redirect(url_for('register'))

    return render_template('register.html')
    
@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        user_id = int(token.split('-')[0])
    except Exception:
        flash("Invalid confirmation token.")
        return redirect(url_for('login'))
    user = db.session.get(User, user_id)
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
    user = db.session.get(User, user_id)
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
    # Check if user has a preferred LLM service
    user_service = session.get('user_llm_service')
    global llm_service
    global llm_service_type
    
    # If user has a preference that's different from current service, switch
    if user_service and user_service != llm_service_type:
        try:
            logger.info(f"Switching to user's preferred LLM service: {user_service}")
            
            # Try to create the service and test it
            temp_service = LLMServiceFactory.create_service_by_type(user_service)
            available_models = temp_service.list_models()
            
            # If we get here, the service is working
            llm_service = temp_service
            llm_service_type = user_service
            
            # Update the application's cached models list
            app.config['LLM_MODELS'] = available_models if available_models else [DEFAULT_MODEL_NAME]
            logger.info(f"Switched to user's preferred service {user_service} with models: {app.config['LLM_MODELS']}")
        except Exception as e:
            logger.exception(f"Failed to switch to user's preferred service {user_service}: {e}")
            # If we can't use the preferred service, clear the preference
            session.pop('user_llm_service', None)
    
    # Continue with the existing chat route logic
    conversation_id = request.args.get('conversation_id', None)
    available_models = app.config['LLM_MODELS']

    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first_or_404()
        # Ensure the conversation's selected model is still valid, fallback if not
        if conversation.selected_model not in available_models:
            logger.warning(f"Conversation {conversation.id} had model '{conversation.selected_model}' which is not available. Falling back to '{available_models[0]}'.")
            conversation.selected_model = available_models[0]
            db.session.commit()
    else:
        conversation = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.created_at.desc()).first()
        if not conversation:
            # Use the first available model or the default
            default_conv_model = available_models[0]
            logger.info(f"Creating first conversation for user {current_user.id} with model '{default_conv_model}'")
            conversation = Conversation(
                user_id=current_user.id,
                title="New Conversation",
                selected_model=default_conv_model
            )
            db.session.add(conversation)
            db.session.commit()
        # Fallback check for existing conversation without a valid model
        elif conversation.selected_model not in available_models:
             logger.warning(f"Latest conversation {conversation.id} had model '{conversation.selected_model}' which is not available. Falling back to '{available_models[0]}'.")
             conversation.selected_model = available_models[0]
             db.session.commit()


    all_conversations = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.created_at.desc()).all()
    messages = ChatMessage.query.filter_by(conversation_id=conversation.id).order_by(ChatMessage.created_at).all()
    
    # Pass the LLM service type to the template
    return render_template('chat.html', 
                          conversation=conversation, 
                          all_conversations=all_conversations,
                          messages=messages, 
                          models=available_models,
                          llm_service_type=llm_service_type) # Add this line

@app.route('/conversation/new', methods=['POST'])
@login_required
def new_conversation():
    available_models = app.config['LLM_MODELS']
    # Get model from form, fallback to first available or default
    selected_model = request.form.get('model', available_models[0])
    
    # Ensure the selected model is actually in the available list
    if selected_model not in available_models:
        logger.warning(f"Model '{selected_model}' requested for new conversation is not available. Falling back to '{available_models[0]}'.")
        selected_model = available_models[0]

    logger.info(f"Creating new conversation for user {current_user.id} with model '{selected_model}'")
    conversation = Conversation(
        user_id=current_user.id,
        title="New Conversation", # Title can be set later based on first message
        selected_model=selected_model
    )
    db.session.add(conversation)
    db.session.commit()
    return redirect(url_for('chat', conversation_id=conversation.id))

@app.route('/conversation/<int:conversation_id>/rename', methods=['POST'])
@login_required
def rename_conversation(conversation_id):
    conversation = db.session.get(Conversation, conversation_id)
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
    conversation = db.session.get(Conversation, conversation_id)
    # Check ownership
    if conversation.user_id != current_user.id:
        flash("Unauthorized access")
        return redirect(url_for('chat'))
    else:
        db.session.delete(conversation)
        db.session.commit()
        flash("Conversation deleted")
    return redirect(url_for('chat'))

@app.route('/switch_model', methods=['POST'])
@login_required
def switch_model():
    conversation_id = request.form['conversation_id']
    new_model = request.form['model']
    conversation = db.session.get(Conversation, conversation_id)
    if conversation and conversation.user_id == current_user.id:
        conversation.selected_model = new_model
        db.session.commit()
        flash("Model switched successfully.")
    return redirect(url_for('chat'))

@app.route('/edit_message/<int:message_id>', methods=['POST'])
@login_required
def edit_message(message_id):
    new_content = request.form['content']
    message = db.session.get(ChatMessage, message_id)
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
            conversation = db.session.get(Conversation, conversation_id)
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
            # Commit here to ensure doc and conversation mode are saved before system message
            db.session.commit() 
            
            # Extract document text for context
            # file.seek(0)  # Reset file pointer
            # doc_text = extract_text_from_document(doc)
            
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
    if not check_whisper_model_exists():
        return jsonify({'success': False, 'error': 'Voice transcription service not available.'}), 500
        
    if 'voice' not in request.files:
        return jsonify({'success': False, 'error': 'No voice file part'}), 400
        
    file = request.files['voice']
    conversation_id = request.form.get('conversation_id')
    language = request.form.get('language', 'english')  # Default to English if not provided

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected voice file'}), 400

    if not conversation_id:
        return jsonify({'success': False, 'error': 'Missing conversation ID'}), 400

    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Conversation not found or unauthorized'}), 404

    # Use a temporary file for processing
    temp_audio_path = None
    transcription_result = None
    detected_language = None
    error_message = None

    try:
        # Save blob to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
            file.save(temp_audio.name)
            temp_audio_path = temp_audio.name
            logger.info(f"Saved temporary voice file to {temp_audio_path}")

        # Transcribe using Whisper
        logger.info(f"Transcribing {temp_audio_path} with language hint: {language}")
        # Let Whisper detect language unless a specific one is strongly needed
        whisper_options = {"language": language if language in ['english', 'persian'] else None} 
        transcription_result = speech_service.transcribe_audio(temp_audio_path, **whisper_options)
        transcribed_text = transcription_result['text'].strip()
        detected_language = transcription_result.get('language', language)  # Use detected or fallback to hint
        logger.info(f"Transcription successful. Detected language: {detected_language}. Text: {transcribed_text}")

        if not transcribed_text:
            raise ValueError("Transcription resulted in empty text.")

        # --- Save User Message (Transcription) ---
        # Prefix with an indicator that it came from voice
        user_message_content = f"🎤: {transcribed_text}"
        user_message = ChatMessage(
            conversation_id=conversation.id,
            sender='user',
            content=user_message_content,
        )
        logger.info(f"Saved user transcription message with ID: {user_message.id}")

        # --- Get AI Response ---
        history = ChatMessage.query.filter_by(conversation_id=conversation.id).order_by(ChatMessage.created_at).all()
        formatted_history = [{"role": msg.sender, "content": msg.content} for msg in history]
        
        # Use the transcribed text as the latest user prompt
        # No need to include the "🎤: " prefix for the AI model context
        latest_prompt = transcribed_text 

        try:
            logger.info(f"Sending prompt to {llm_service_type} model {conversation.selected_model}: {latest_prompt}")
            # Use the new llm_service abstraction
            response = llm_service.chat(
                model=conversation.selected_model,
                messages=formatted_history
            )
            ai_response_text = response['message']['content']
            logger.info(f"Received AI response: {ai_response_text}")

            # --- Save AI Message ---
            ai_message = ChatMessage(
                conversation_id=conversation.id,
                sender='ai',
                content=ai_response_text,
            )
            db.session.add(ai_message)
            db.session.commit()
            logger.info(f"Saved AI response message with ID: {ai_message.id}")

            # --- Prepare JSON Response ---
            return jsonify({
                'success': True,
                'transcription': user_message_content, 
                'message_id': user_message.id,  # ID of the saved user message
                'ai_response': ai_response_text,
                'detected_language': detected_language,
            })

        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            error_message = f"Error getting AI response: {e}"
            # Still return success=True because transcription worked, but include error for AI part
            return jsonify({
                'success': True,  # Transcription succeeded
                'transcription': user_message_content,
                'message_id': user_message.id,
                'ai_response': None,  # Indicate AI response failed
                'error': error_message,  # Provide error detail
                'detected_language': detected_language,
            })

    except Exception as e:
        logger.error(f"Error processing voice file: {e}")
        error_message = f"Error processing voice: {e}"
        # Return success=False as the core voice processing failed
        return jsonify({'success': False, 'error': error_message, 'transcription': error_message}), 500
    finally:
        # Clean up temporary file
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
                logger.info(f"Removed temporary voice file: {temp_audio_path}")
            except Exception as e:
                logger.error(f"Error removing temporary file {temp_audio_path}: {e}")

# Add a new function to call the AI model directly from backend
def call_ai_model(model_name, prompt):
    """Call the AI model synchronously and return the full response using the configured LLM service"""
    # Force use of the fixed model for voice assistant
    fixed_model = os.environ.get('DEFAULT_VOICE_MODEL', "llama2") # Consider making this configurable

    if not isinstance(prompt, str):
        logger.error(f"call_ai_model received non-string prompt: {type(prompt)}")
        raise TypeError("Prompt must be a string")

    logger.info(f"Calling {llm_service_type} model {fixed_model} with prompt: {prompt[:50]}...")

    # Detect if the prompt contains Persian text
    is_persian = any('\u0600' <= c <= '\u06FF' for c in prompt)

    # Add language instruction for Persian
    if is_persian and "پاسخ به زبان فارسی" not in prompt:
        prompt = "لطفا به سوال زیر به زبان فارسی پاسخ دهید:\n\n" + prompt
        logger.info("Added Persian language instruction to prompt")

    try:
        logger.info(f"Sending prompt to {llm_service_type} model {fixed_model}: {prompt}")
        # Use the new llm_service abstraction
        response = llm_service.chat(
            model=fixed_model,
            messages=[{'role': 'user', 'content': prompt}]
        )
        ai_response_text = response['message']['content']
        logger.info(f"Received AI response: {ai_response_text[:50]}...")
        return ai_response_text
    except Exception as e:
        logger.exception(f"Error calling {llm_service_type} API: {e}")
        raise Exception(f"Failed to get response from AI model via API: {e}")

# Add a route to get the voice recording
@app.route('/voice_recording/<int:recording_id>', methods=['GET'])
@login_required 
def get_voice_recording(recording_id):
    """Return the voice recording audio file"""
    temp_file_path = None
    try:
        # Get the document
        voice_doc = db.session.get(Document, recording_id)
        
        # Check if the voice belongs to a conversation owned by the current user
        conversation = db.session.get(Conversation, voice_doc.conversation_id)
        if not conversation or conversation.user_id != current_user.id:
            return "Unauthorized", 403
        
        # Create a temporary file to serve
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
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
                except Exception as e:
                    logger.warning(f"Failed to remove temporary file {temp_file_path}: {e}")
            
            import threading
            cleanup_thread = threading.Thread(target=cleanup_temp_file)
            cleanup_thread.daemon = True
            cleanup_thread.start()

# Update voice help route if needed, or remove if template is removed
@app.route('/voice_help')
def voice_help():
    """Provides detailed instructions for setting up voice recognition"""
    # Update this template or remove the route if the template is removed
    return render_template('voice_help.html') # Make sure this template exists and is updated

# ===========================
# Endpoint to Call the AI Model and Stream Response
# ===========================
def stream_llm_response(model_name, messages_history):
    """Streams response from the configured LLM service."""
    logger.info(f"--> Entering stream_llm_response for model: {model_name}")
    logger.info(f"--> Messages history count: {len(messages_history)}")
    logger.info(f"--> First message: {str(messages_history[0])[:100]}..." if messages_history else "No messages in history")
    
    stream_generator = None
    sent_any_chunk = False
    try:
        logger.info("--> Calling llm_service.stream_chat...")
        # Use the new llm_service abstraction for streaming
        stream_generator = llm_service.stream_chat(model_name, messages_history)
        logger.info("--> Got generator object from llm_service.stream_chat.")
        logger.info("--> Preparing to yield from stream_generator...")
        logger.info("--> Starting the generator iteration loop")
        try:
            for chunk in stream_generator:
                logger.info(f"Yielding chunk from llm_service.stream_chat: {str(chunk)[:60]}")
                # Wrap every chunk in SSE format (data: ...\n\n)
                try:
                    if isinstance(chunk, str) and chunk.startswith('data: '):
                        yield chunk if chunk.endswith('\n\n') else chunk + '\n\n'
                    else:
                        if not isinstance(chunk, str):
                            chunk = json.dumps(chunk)
                        yield f"data: {chunk}\n\n"
                    sent_any_chunk = True
                except Exception as e:
                    logger.exception(f"Error formatting chunk for SSE: {e}")
                    error_text = f"Error formatting chunk: {e}"
                    escaped_text = json.dumps({"error": error_text, "text": f"⚠️ {error_text}"})
                    yield f"data: {escaped_text}\n\n"
                    sent_any_chunk = True
            logger.info("Exited stream_generator loop in stream_llm_response.")
        except Exception as e:
            logger.exception(f"Exception while iterating stream_generator: {e}")
            error_text = json.dumps({"error": str(e), "text": f"⚠️ {str(e)}"})
            yield f"data: {error_text}\n\n"
            sent_any_chunk = True
    except Exception as e:
        logger.exception(f"--> Error during llm_service.stream_chat call or yield from: {e}")
        error_text = f"Error during {llm_service_type} stream: {e}"
        escaped_text = json.dumps({"error": error_text, "text": f"⚠️ {error_text}"})
        yield f"data: {escaped_text}\n\n"
    finally:
        logger.info(f"--> Exiting stream_llm_response for model: {model_name}")
        if not sent_any_chunk:
            logger.warning("No chunks were yielded from llm_service.stream_chat; sending empty response message.")
            empty_text = json.dumps({"error": "No response from model.", "text": "⚠️ No response from model."})
            yield f"data: {empty_text}\n\n"

@app.route('/call_model', methods=['POST'])
@login_required
def call_model():
    logger.info(f"Received /call_model request from user {current_user.id}")
    conversation_id = request.form['conversation_id']
    prompt = request.form['prompt']
    logger.info(f"Request details - conversation_id: {conversation_id}, prompt: {prompt[:50]}...")
    
    # Get conversation
    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        logger.warning(f"Unauthorized access attempt to conversation {conversation_id}")
        return jsonify({"error": "Unauthorized"}), 403
    
    # Prepare message history
    messages_history = []
    for msg in conversation.messages:
        messages_history.append({
            'role': 'user' if msg.sender == 'user' else 'assistant',
            'content': msg.content
        })
    messages_history.append({'role': 'user', 'content': prompt})
    
    model_name = conversation.selected_model if hasattr(conversation, 'selected_model') and conversation.selected_model else DEFAULT_MODEL_NAME
    logger.info(f"Using model: {model_name}")
    
    # Save the user message to the DB
    user_message = ChatMessage(
        conversation_id=conversation_id,
        sender='user',
        content=prompt
    )
    db.session.add(user_message)
    db.session.commit()
    logger.info(f"Saved user message with ID {user_message.id}")
    
    def response_wrapper():
        logger.info("Starting response_wrapper generator")
        full_response = ""
        ai_message_id = None
        user_id = current_user.id if hasattr(current_user, 'id') and current_user.id else 0
        conv_id = conversation_id
        generator_key = f"user_{user_id}_conv_{conv_id}"
        active_response_generators[generator_key] = False
        try:
            logger.info("Preparing message history for LLM API")
            logger.info(f"Streaming from ollama model {model_name}")
            logger.info(f"Attempting ollama stream with model: {model_name}")
            chunk_count = 0
            try:
                logger.info("--> Entering stream_llm_response from response_wrapper...")
                yielded_any = False
                for chunk in stream_llm_response(model_name, messages_history):
                    logger.info(f"Yielding chunk #{chunk_count+1}: {str(chunk)[:60]}")
                    # Accumulate bot response text from each chunk
                    # Each chunk should be like: 'data: {"text": "..."}\n\n'
                    if chunk.startswith('data: '):
                        try:
                            data = json.loads(chunk[6:].strip())
                            if 'text' in data:
                                full_response += data['text']
                        except Exception as e:
                            logger.warning(f"Failed to parse streamed chunk for accumulation: {e}")
                    yield chunk
                    yielded_any = True
                    chunk_count += 1
                logger.info(f"Exited streaming loop after {chunk_count} chunks.")
                if not yielded_any:
                    logger.warning("No chunks were yielded from stream_llm_response; yielding fallback error chunk.")
                    error_text = json.dumps({"error": "No response from model.", "text": "⚠️ No response from model."})
                    yield f"data: {error_text}\n\n"
                # After streaming is done, save the bot message to DB
                if full_response.strip():
                    try:
                        ai_message = ChatMessage(
                            conversation_id=conversation_id,
                            sender='ai',
                            content=full_response
                        )
                        db.session.add(ai_message)
                        db.session.commit()
                        logger.info(f"Saved AI message with ID {ai_message.id}")
                    except Exception as e:
                        logger.error(f"Failed to save AI message to DB: {e}")
                        db.session.rollback()
            except Exception as e:
                logger.exception(f"Exception in streaming loop: {e}")
                error_text = json.dumps({"error": str(e), "text": f"⚠️ {str(e)}"})
                yield f"data: {error_text}\n\n"
        finally:
            logger.info("Exiting response_wrapper generator")
    logger.info("Returning streaming response")
    # Ensure correct mimetype for SSE and use stream_with_context
    return Response(stream_with_context(response_wrapper()), mimetype="text/event-stream")

# Add a dictionary to track active response generators
active_response_generators = {}

@app.route('/stop_response', methods=['POST'])
@login_required
def stop_response():
    """Stop an active AI response for a conversation"""
    conversation_id = request.form.get('conversation_id')
    logger.info(f"Request to stop response for conversation {conversation_id}")
    
    if not conversation_id:
        return jsonify({"success": False, "error": "No conversation ID provided"}), 400
        
    # Check permission (user must own the conversation)
    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    
    # Set the flag to stop the generator for this conversation
    generator_key = f"user_{current_user.id}_conv_{conversation_id}"
    if generator_key in active_response_generators:
        active_response_generators[generator_key] = True
        logger.info(f"Set stop flag for generator {generator_key}")
        return jsonify({"success": True, "message": "Response generation stopping"})
    else:
        return jsonify({"success": False, "error": "No active response found"}), 404

@app.route('/toggle_document_mode/<int:conversation_id>', methods=['POST'])
@login_required
def toggle_document_mode(conversation_id):
    conversation = db.session.get(Conversation, conversation_id)
    
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
            latest_doc = Document.query.filter(
                Document.conversation_id == conversation_id,
                Document.mime_type != 'audio/wav' # Exclude voice recordings
            ).order_by(Document.uploaded_at.desc()).first()
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
        conversation = db.session.get(Conversation, conversation_id)
        
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
        return jsonify({"success": True, "title": title})
    except Exception as e:
        logger.exception(f"Error updating conversation title: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

# Add routes for text-to-speech capabilities
@app.route('/voice_for_message/<int:message_id>', methods=['GET'])
@login_required
def voice_for_message(message_id):
    """Check if a voice recording exists for a message and return it"""
    try:
        message = db.session.get(ChatMessage, message_id)
        
        # Check if this message belongs to a conversation owned by the current user
        conversation = db.session.get(Conversation, message.conversation_id)
        if not conversation or conversation.user_id != current_user.id:
            return "Unauthorized", 403
        
        # Check if this is a voice response message
        if message.sender == 'ai' and message.content.startswith('VOICE_RESPONSE:'):
            parts = message.content.split(':')
            if len(parts) >= 3:
                language = parts[1]
                content = ':'.join(parts[2:])
                
                # Check if we already have a voice recording for this AI message
                # We'll search for documents with a filename containing the message_id
                voice_doc = Document.query.filter(
                    Document.conversation_id == message.conversation_id,
                    Document.filename.like(f'ai_voice_response_%_{message_id}.wav')
                ).first()
                
                if voice_doc:
                    # Create a temporary file to serve
                    temp_file_path = None
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                        tmp.write(voice_doc.data)
                        temp_file_path = tmp.name
                    
                    # Function to clean up temporary file
                    def cleanup_temp_file():
                        try:
                            # Add a small delay to ensure file serving completes
                            time.sleep(1)
                            if os.path.exists(temp_file_path):
                                os.remove(temp_file_path)
                        except Exception as e:
                            logger.warning(f"Failed to remove temporary file {temp_file_path}: {e}")
                    
                    # Start cleanup thread
                    cleanup_thread = threading.Thread(target=cleanup_temp_file)
                    cleanup_thread.daemon = True
                    cleanup_thread.start()
                    
                    # Return the file
                    return send_file(
                        temp_file_path,
                        mimetype="audio/wav",
                        as_attachment=False
                    )
        
        # If we get here, no voice recording was found
        return "No voice recording found for this message", 404
    
    except Exception as e:
        logger.exception(f"Error retrieving voice for message: {e}")
        return f"Error retrieving voice: {e}", 500

@app.route('/synthesize_for_message', methods=['POST'])
@login_required
def synthesize_for_message():
    """Generate text-to-speech for a message and store it"""
    try:
        text = request.form['text']
        language = request.form.get('language', 'english')
        message_id = request.form.get('message_id')
        
        if not text.strip():
            return "No text provided", 400
        
        # Generate speech
        speech_file = synthesize_speech(text, language) # This function needs to be defined or imported
        if not speech_file:
            return "Failed to generate speech", 500
        
        # Find the associated message if message_id was provided
        if message_id:
            message = db.session.get(ChatMessage, int(message_id))
            if message:
                conversation_id = message.conversation_id
            else:
                return "Message not found", 404
        else:
            # If no specific message, use the active conversation
            conversation_id = request.form.get('conversation_id')
            if not conversation_id:
                return "No conversation ID provided", 400
        
        # Check user authorization for this conversation
        conversation = db.session.get(Conversation, conversation_id)
        if not conversation or conversation.user_id != current_user.id:
            return "Unauthorized", 403
        
        # Read the generated audio file
        with open(speech_file, 'rb') as audio_file:
            audio_data = audio_file.read()
        
        # Save the speech as a document with reference to the message
        filename = f"ai_voice_response_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if message_id:
            filename += f"_{message_id}"
        filename += ".wav"
        
        voice_doc = Document(
            conversation_id=conversation_id,
            filename=filename,
            data=audio_data,
            mime_type="audio/wav"
        )
        
        db.session.add(voice_doc)
        db.session.commit()
        
        # Clean up the temporary file
        try:
            os.remove(speech_file)
        except:
            pass
        
        # Return the audio
        return send_file(
            io.BytesIO(audio_data),
            mimetype="audio/wav",
            as_attachment=False
        )
    except Exception as e:
        logger.exception(f"Error synthesizing speech: {e}")
        return f"Error synthesizing speech: {e}", 500

# Add a function to check system dependencies at startup
def check_system_dependencies():
    deps = {
        "ffmpeg": check_ffmpeg_installed(),
        "whisper": check_whisper_model_exists() # Check if base model can load
    }
    return deps

# === Add Placeholder for synthesize_speech ===
def synthesize_speech(text, language):
    """Placeholder function for text-to-speech synthesis."""
    logger.warning(f"Placeholder synthesize_speech called for language '{language}'. Text: {text[:50]}...")
    # In a real implementation, this would call Bark via speech_service
    # and return the path to the generated audio file.
    # For now, return None to indicate failure.
    # Example call (if speech_service had this method):
    # return speech_service.synthesize_speech(text, language)
    return None
# === End Placeholder ===

# Create a session variable to store the user's LLM service preference
@app.route('/switch_llm_service', methods=['POST'])
@login_required
def switch_llm_service():
    """Switch the LLM service (Ollama or Llama.cpp) for the current user"""
    try:
        new_service = request.form.get('llm_service', 'ollama').lower()
        
        # Validate the service type
        if new_service not in ['ollama', 'llamacpp']:
            return jsonify({"success": False, "error": f"Invalid LLM service type: {new_service}"}), 400
        
        logger.info(f"User {current_user.id} switching LLM service to {new_service}")
        
        # Store the user's preference in session
        session['user_llm_service'] = new_service
        
        # Create a new LLM service instance
        global llm_service
        global llm_service_type
        
        # Create temp service to test connectivity
        try:
            # Use the factory to create the new service
            temp_service = LLMServiceFactory.create_service_by_type(new_service)
            # Test listing models to ensure connectivity
            available_models = temp_service.list_models()
            
            if not available_models:
                logger.warning(f"No models found for {new_service} service")
                
            # If we get here, the service is working
            llm_service = temp_service
            llm_service_type = new_service
            
            # Update the application's cached models list
            app.config['LLM_MODELS'] = available_models if available_models else [DEFAULT_MODEL_NAME]
            logger.info(f"Successfully switched to {new_service} service with models: {app.config['LLM_MODELS']}")
            
            return jsonify({
                "success": True, 
                "service": new_service,
                "models": app.config['LLM_MODELS']
            })
            
        except Exception as e:
            logger.exception(f"Error switching to {new_service} service: {e}")
            return jsonify({"success": False, "error": f"Failed to connect to {new_service} service: {str(e)}"}), 500
            
    except Exception as e:
        logger.exception(f"Error in switch_llm_service: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/test_ollama', methods=['GET'])
def test_ollama():
    """
    Test connectivity to Ollama service and return detailed diagnostics.
    """
    results = {
        "status": "Running diagnostics...",
        "ollama_host": os.environ.get("OLLAMA_HOST", "http://ollama:11434"),
        "llm_service_type": os.environ.get("LLM_SERVICE", "ollama"),
        "tests": []
    }
    
    try:
        # Test 1: Basic connectivity via requests
        results["tests"].append({"name": "Basic connectivity test"})
        try:
            import requests
            ollama_url = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
            health_url = f"{ollama_url}/api/tags"
            logger.info(f"Testing basic connectivity to Ollama at {health_url}")
            response = requests.get(health_url, timeout=5)
            results["tests"][-1]["status"] = f"Success ({response.status_code})"
            results["tests"][-1]["details"] = f"Connected to {health_url}"
            
            # Include the first 500 chars of the response for verification
            response_data = response.json()
            results["tests"][-1]["response_preview"] = str(response_data)[:500]
        except Exception as e:
            results["tests"][-1]["status"] = "Failed"
            results["tests"][-1]["details"] = f"Error: {str(e)}"
            logger.exception(f"Basic connectivity test failed: {e}")
        
        # Test 2: Try to list models
        results["tests"].append({"name": "List models test"})
        try:
            models = llm_service.list_models()
            results["tests"][-1]["status"] = "Success"
            results["tests"][-1]["details"] = f"Found {len(models)} models"
            results["tests"][-1]["models"] = models
        except Exception as e:
            results["tests"][-1]["status"] = "Failed"
            results["tests"][-1]["details"] = f"Error: {str(e)}"
            logger.exception(f"List models test failed: {e}")
        
        # Test 3: Simple completion without streaming
        results["tests"].append({"name": "Simple completion test"})
        try:
            import requests
            import json
            
            ollama_url = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
            api_url = f"{ollama_url}/api/chat"
            payload = {
                "model": DEFAULT_MODEL_NAME,
                "messages": [{"role": "user", "content": "Hello, say hi in one word"}],
                "stream": False
            }
            logger.info(f"Testing simple completion to {api_url}")
            response = requests.post(api_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                response_data = response.json()
                results["tests"][-1]["status"] = "Success"
                results["tests"][-1]["details"] = "Completion received"
                results["tests"][-1]["response"] = str(response_data)[:500]
            else:
                results["tests"][-1]["status"] = "Failed"
                results["tests"][-1]["details"] = f"Error: Status {response.status_code}"
                results["tests"][-1]["response"] = response.text[:500]
        except Exception as e:
            results["tests"][-1]["status"] = "Failed"
            results["tests"][-1]["details"] = f"Error: {str(e)}"
            logger.exception(f"Simple completion test failed: {e}")
        
        # Overall status
        failed_tests = [t for t in results["tests"] if t.get("status", "").startswith("Failed")]
        if failed_tests:
            results["status"] = f"Failed ({len(failed_tests)}/{len(results['tests'])} tests failed)"
        else:
            results["status"] = "Success (all tests passed)"
            
    except Exception as e:
        results["status"] = "Error running diagnostics"
        results["error"] = str(e)
        logger.exception(f"Error in /test_ollama endpoint: {e}")
    
    return jsonify(results)

# Main entry point
if __name__ == '__main__':
    # Check dependencies
    system_deps = check_system_dependencies()
    if not system_deps['ffmpeg']:
        logger.error("FFmpeg is not installed. Please install FFmpeg to use this application.")
        # Don't exit in Docker, let it try to run
        # exit(1) 
    if not system_deps['whisper']:
        logger.error("Whisper models are not available. Please install faster-whisper to use this application.")
        # Don't exit in Docker, let it try to run
        # exit(1)
    
    # === Add a startup message showing the LLM service type ===
    logger.info(f"Starting AI Chat application with {llm_service_type.upper()} as the LLM service")
    
    with app.app_context():
        # Ensure tables exist.
        db.create_all()
    
    # === Update app.run for Docker ===
    # Use host='0.0.0.0' to be accessible outside the container
    # Use port=5001 as exposed in Dockerfile/docker-compose.yml
    app.run(debug=True, host='0.0.0.0', port=5001)