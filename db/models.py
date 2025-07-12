import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

# Association tables
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

role_models = db.Table('role_models',
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True),
    db.Column('model_id', db.Integer, db.ForeignKey('model.id'), primary_key=True)
)

rag_doc_in_index = db.Table('rag_doc_in_index',
    db.Column('rag_document_id', db.Integer, db.ForeignKey('rag_document.id'), primary_key=True),
    db.Column('rag_index_id', db.Integer, db.ForeignKey('rag_index.id'), primary_key=True)
)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    firstname = db.Column(db.String(100), nullable=True)
    lastname = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(512))
    confirmed = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    conversations = db.relationship('Conversation', backref='user', lazy=True)

    roles = db.relationship('Role', secondary=user_roles,
                            lazy='subquery', backref=db.backref('users_in_role', lazy=True))

    def can_access_page(self, page_endpoint):
        if not self.is_active:
            return False
        if self.has_role('admin'):
            return True
        for role in self.roles:
            if role.has_page_access(page_endpoint):
                return True
        return False

    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)

    def can_access_model(self, model_id):
        if self.has_role('admin'):
            return True
        for role in self.roles:
            if role.has_model_access(model_id):
                return True
        return False

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
    document_mode = db.Column(db.Boolean, default=False)
    messages = db.relationship('ChatMessage', backref='conversation', cascade="all, delete-orphan", lazy=True)
    documents = db.relationship('Document', backref='conversation', cascade="all, delete-orphan", lazy=True)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender = db.Column(db.String(10))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    filename = db.Column(db.String(256))
    data = db.Column(db.LargeBinary)
    mime_type = db.Column(db.String(128))
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class PagePermission(db.Model):
    __tablename__ = 'page_permission'
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    page_endpoint = db.Column(db.String(255), nullable=False)

    __table_args__ = (db.UniqueConstraint('role_id', 'page_endpoint', name='_role_page_uc'),)

    def __repr__(self):
        return f"<PagePermission role_id={self.role_id} page='{self.page_endpoint}'>"

class Role(db.Model):
    __tablename__ = 'role'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    models = db.relationship('Model', secondary=role_models,
                             lazy='subquery', backref=db.backref('roles_having_access', lazy=True))

    page_permissions = db.relationship('PagePermission', backref='role', lazy='dynamic', cascade="all, delete-orphan")

    def has_page_access(self, page_endpoint):
        return self.page_permissions.filter_by(page_endpoint=page_endpoint).first() is not None

    def has_model_access(self, model_id):
        if not hasattr(self, 'models') or not self.models:
            return False
        return any(model.id == model_id for model in self.models)

    def __repr__(self):
        return f'<Role {self.name}>'

class RagDocument(db.Model):
    __tablename__ = 'rag_document'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    stored_filename = db.Column(db.String(256), unique=True, nullable=False)
    filepath = db.Column(db.String(512), nullable=False)
    filesize = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(128), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    uploader = db.relationship('User', backref=db.backref('uploaded_rag_documents', lazy=True))
    indexes = db.relationship('RagIndex', secondary=rag_doc_in_index,
                               lazy='subquery', backref=db.backref('documents', lazy=True))

    def __repr__(self):
        return f'<RagDocument {self.filename}>'

class RagIndex(db.Model):
    __tablename__ = 'rag_index'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    base_model_id = db.Column(db.Integer, db.ForeignKey('model.id'), nullable=False)
    vector_store_path_segment = db.Column(db.String(256), unique=True, nullable=False)
    chunk_size = db.Column(db.Integer, nullable=False, default=500)
    chunk_overlap = db.Column(db.Integer, nullable=False, default=100)
    embedding_model_name = db.Column(db.String(255), nullable=False, default='nomic-embed-text')
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('created_rag_indexes', lazy=True))
    base_model = db.relationship('Model', foreign_keys=[base_model_id], backref=db.backref('used_as_rag_base', lazy=True))
    model_entry = db.relationship('Model', foreign_keys='Model.rag_index_id', backref=db.backref('rag_definition', uselist=False, lazy=True),  primaryjoin="Model.rag_index_id == RagIndex.id")

    indexing_status = db.Column(db.String(20), nullable=False, default='pending')
    indexing_progress = db.Column(db.Integer, nullable=False, default=0)
    indexing_error_message = db.Column(db.Text, nullable=True)

    @property
    def get_vector_store_path(self):
        return f"/path/to/rag_index_folder/{self.vector_store_path_segment}" # Placeholder

    def __repr__(self):
        return f'<RagIndex {self.name}>'

class Model(db.Model):
    __tablename__ = 'model'
    id = db.Column(db.Integer, primary_key=True)
    ollama_model_name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    base_model_identifier = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    is_rag_model = db.Column(db.Boolean, default=False, nullable=False)
    base_rag_model_id = db.Column(db.Integer, db.ForeignKey('model.id'), nullable=True)
    rag_index_id = db.Column(db.Integer, db.ForeignKey('rag_index.id', name='fk_model_rag_index_id', use_alter=True), nullable=True)

    base_rag_model_for = db.relationship('Model', remote_side=[id], foreign_keys=[base_rag_model_id], backref=db.backref('rag_variants_using_this_base', lazy=True))

    def __repr__(self):
        return f'<Model {self.display_name} ({self.ollama_model_name})>'
