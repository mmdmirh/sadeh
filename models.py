from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import datetime

# This will be imported in app.py
db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    confirmed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    conversations = db.relationship('Conversation', backref='user', lazy=True)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if the user has the 'admin' role."""
        # Assumes 'self.roles' is populated (relationship defined in app.py).
        # Assumes Role object has a 'name' attribute.
        if not hasattr(self, 'roles') or not self.roles:
            return False 
        return any(hasattr(role, 'name') and role.name == 'admin' for role in self.roles)

    def can_access_model(self, model_id):
        """Check if the user can access a specific model by its ID."""
        # Admins have access to all models.
        if self.is_admin(): # is_admin already checks for self.roles
            return True
        
        # Check if any of the user's roles grant access to the model.
        # Assumes 'self.roles' is populated and Role object has 'has_model_access(model_id)' method.
        if not hasattr(self, 'roles') or not self.roles:
            return False
        return any(hasattr(role, 'has_model_access') and role.has_model_access(model_id) for role in self.roles)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), default="New Conversation")
    selected_model = db.Column(db.String(64))
    document_mode = db.Column(db.Boolean, default=False)  # Add this line
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

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
    data = db.Column(db.LargeBinary)
    mime_type = db.Column(db.String(128))
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
