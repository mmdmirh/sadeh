"""
Database utilities module for Sadeh application.

This module contains all database-related functions that were previously in app.py,
including initialization, connection checking, and model loading functions.
"""

import os
import time
import sqlalchemy
import traceback
from flask import current_app
from flask_migrate import upgrade

from .extensions import db
from .models import User, Model
from .seed import initialize_rbac_data, create_database_if_not_exists


def is_database_initialized():
    """Check if essential database tables exist"""
    try:
        # Try to query a table that should exist if the database is initialized
        db.session.execute(db.select(User).limit(1))
        return True
    except sqlalchemy.exc.ProgrammingError as e:
        current_app.logger.warning(f"Database tables not fully initialized: {str(e)}")
        return False
    except Exception as e:
        current_app.logger.error(f"Error checking database status: {str(e)}")
        return False


def check_database_connection():
    """Check if we can connect to the database"""
    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Try to execute a simple query
            db.session.execute('SELECT 1')
            current_app.logger.info("Successfully connected to the database")
            return True
        except Exception as e:
            retry_count += 1
            current_app.logger.warning(f"Database connection failed (attempt {retry_count}/{max_retries}): {str(e)}")
            if retry_count >= max_retries:
                current_app.logger.error("Max retries reached. Could not connect to the database.")
                return False
            time.sleep(5)  # Wait before retrying


def load_and_ensure_llm_models(application=None):
    """Loads model list, ensures default (and specified) models are pulled if missing."""
    # RequestError will be imported later when needed
    
    # Use the passed application object or import the global app
    if application:
        current_app = application
    else:
        from flask import current_app as flask_current_app
        current_app = flask_current_app
    
    # More robust app context handling
    if not current_app:
        print("LOAD_AND_ENSURE: No Flask app available for context")
        return []
    
    # Define a fallback return outside try block for better error handling
    available_models = []
    
    try:
        # Run everything within app context
        with current_app.app_context():
            # Use the centrally managed list of Ollama models from app.config
            managed_ollama_models = current_app.config.get('MANAGED_OLLAMA_MODELS', [])
            current_app.logger.info(f"LOAD_AND_ENSURE: Using MANAGED_OLLAMA_MODELS from app.config: {managed_ollama_models}")

            # Start with all managed models
            models_to_ensure = set(managed_ollama_models)
            
            # Import here to avoid circular import
            from backend.llm.llm_service import LLMServiceFactory
            import os
            
            # Get the service type and create service instance
            llm_service_type = os.environ.get('LLM_SERVICE', 'ollama').lower()
            llm_service = LLMServiceFactory.create_service()
            DEFAULT_MODEL_NAME = current_app.config.get('DEFAULT_MODEL_NAME')
            if DEFAULT_MODEL_NAME: 
                models_to_ensure.add(DEFAULT_MODEL_NAME)
            
            current_app.logger.info(f"LOAD_AND_ENSURE: Final models_to_ensure (after adding default if needed): {list(models_to_ensure)}")
            
            # Initialize list for tracking available models
            available_models = []
            
            try:
                all_active_db_models = Model.query.filter_by(is_active=True).all()
                active_db_model_names = {model.ollama_model_name for model in all_active_db_models}
                current_app.logger.info(f"Active models from DB: {active_db_model_names}")

                if llm_service_type == 'ollama':
                    try:
                        # Check if we're running in Docker to handle DNS resolution errors
                        in_docker = os.environ.get('RUNNING_IN_DOCKER', 'false').lower() == 'true'
                        if in_docker:
                            current_app.logger.info("Running in Docker environment - will handle DNS resolution errors")
                            
                        try:
                            initial_server_models_list = llm_service.list_models()
                            initial_server_models_set = set(initial_server_models_list)
                            current_app.logger.info(f"LOAD_AND_ENSURE: Initial models on Ollama server: {initial_server_models_set}")
                        except Exception as list_err:
                            current_app.logger.error(f"LOAD_AND_ENSURE: Cannot list models from Ollama server: {list_err}")
                            # Fall back to assuming models are in the database
                            initial_server_models_set = set()
                            current_app.logger.warning("LOAD_AND_ENSURE: Falling back to database models only due to Ollama server connection error")

                        models_pulled_this_run = set()
                        # Ensure managed models are pulled if not on server
                        for model_name_to_pull in managed_ollama_models:
                            if model_name_to_pull not in initial_server_models_set:
                                try:
                                    current_app.logger.info(f"LOAD_AND_ENSURE: Model '{model_name_to_pull}' (managed) not on server. Attempting to pull...")
                                    llm_service.pull_model(model_name_to_pull)
                                    current_app.logger.info(f"LOAD_AND_ENSURE: Successfully pulled model '{model_name_to_pull}'.")
                                    models_pulled_this_run.add(model_name_to_pull)
                                except Exception as e:
                                    current_app.logger.warning(f"LOAD_AND_ENSURE: Failed to pull managed model '{model_name_to_pull}': {e}")
                                    # Try to continue with other models rather than failing completely
                                    if in_docker and ('Name or service not known' in str(e) or 'no such host' in str(e)):
                                        current_app.logger.error(f"LOAD_AND_ENSURE: DNS resolution error when pulling model. This is likely a Docker networking issue.")
                                        # If model exists in DB, assume it will be available later when DNS is fixed
                                        if model_name_to_pull in active_db_model_names:
                                            current_app.logger.info(f"LOAD_AND_ENSURE: Model '{model_name_to_pull}' exists in database, will attempt to use it anyway.")
                                            # Add to set to make it available even though pull failed
                                            models_pulled_this_run.add(model_name_to_pull)
                        
                        final_server_models_set = initial_server_models_set.union(models_pulled_this_run)
                        current_app.logger.info(f"LOAD_AND_ENSURE: Final models on Ollama server (after pulls): {final_server_models_set}")

                        # Populate available_models from all models now on the server that are also active in DB
                        for server_model_name in final_server_models_set:
                            if server_model_name in active_db_model_names:
                                db_model_obj = next((m for m in all_active_db_models if m.ollama_model_name == server_model_name), None)
                                if db_model_obj: # Should be true if server_model_name in active_db_model_names
                                    available_models.append({
                                        'id': db_model_obj.id,
                                        'name': db_model_obj.display_name or db_model_obj.ollama_model_name,
                                        'ollama_model_name': db_model_obj.ollama_model_name,
                                        'is_default': db_model_obj.ollama_model_name == DEFAULT_MODEL_NAME
                                    })
                    except RequestError as re:
                        current_app.logger.error(f"Ollama RequestError when ensuring models: {re}. This might happen if Ollama is not running or not reachable.")
                        # Fallback: only use models already in DB if Ollama is down and they were in models_to_ensure
                        for db_model in all_active_db_models:
                            if db_model.ollama_model_name in models_to_ensure:
                                available_models.append({
                                    'id': db_model.id,
                                    'name': db_model.display_name or db_model.ollama_model_name,
                                    'ollama_model_name': db_model.ollama_model_name,
                                    'is_default': db_model.ollama_model_name == DEFAULT_MODEL_NAME
                                })

                elif llm_service_type == 'llamacpp':
                    if DEFAULT_MODEL_NAME in active_db_model_names:
                        db_model_obj = next((m for m in all_active_db_models if m.ollama_model_name == DEFAULT_MODEL_NAME), None)
                        if db_model_obj:
                            available_models.append({
                                'id': db_model_obj.id,
                                'name': db_model_obj.display_name, 
                                'ollama_model_name': db_model_obj.ollama_model_name,
                                'is_default': True
                            })
                    else:
                        current_app.logger.warning(f"LlamaCPP model '{DEFAULT_MODEL_NAME}' is not marked active in the database.")

                # Consolidate fallback for empty available_models
                if not available_models and DEFAULT_MODEL_NAME and DEFAULT_MODEL_NAME in active_db_model_names:
                    current_app.logger.info(f"No specific models made it to available_models list, but default '{DEFAULT_MODEL_NAME}' is active. Adding it.")
                    db_model_obj = next((m for m in all_active_db_models if m.ollama_model_name == DEFAULT_MODEL_NAME), None)
                    if db_model_obj:
                        available_models.append({
                            'id': db_model_obj.id,
                            'name': db_model_obj.display_name, 
                            'ollama_model_name': db_model_obj.ollama_model_name,
                            'is_default': True
                        })
                
                if DEFAULT_MODEL_NAME:
                    available_models.sort(key=lambda x: x['ollama_model_name'] != DEFAULT_MODEL_NAME)

                return available_models

            except Exception as e:
                current_app.logger.exception(f"Error during model loading and pulling process (within app_context): {e}")
                # Fallback logic handled in outer catch block
                raise
    except Exception as e:
        current_app.logger.exception(f"Error during model loading process: {e}")
        # Fallback logic if an error occurs even within the app_context
        DEFAULT_MODEL_NAME = current_app.config.get('DEFAULT_MODEL_NAME') if current_app else None
        if DEFAULT_MODEL_NAME:
            # Check if DEFAULT_MODEL_NAME exists in the database as a last resort
            try:
                with current_app.app_context():
                    default_db_model = Model.query.filter_by(ollama_model_name=DEFAULT_MODEL_NAME, is_active=True).first()
                    if default_db_model:
                        current_app.logger.warning(f"Proceeding with fallback default model for UI due to error: {default_db_model.ollama_model_name} (from DB)")
                        available_models.append({
                            'id': default_db_model.id,
                            'name': default_db_model.display_name,  
                            'ollama_model_name': default_db_model.ollama_model_name, 
                            'is_default': True,
                            'description': default_db_model.description
                        })
            except Exception as db_e:
                current_app.logger.error(f"Could not even fetch default model from DB during fallback: {db_e}")
            
            current_app.logger.warning(f"Proceeding with fallback default model name (string only) for UI due to error: {DEFAULT_MODEL_NAME}")
            # Return a structure consistent with what the chat route expects if possible, even if it's just the name
            return [{'name': DEFAULT_MODEL_NAME, 'ollama_model_name': DEFAULT_MODEL_NAME, 'is_default': True, 'id': None}]
    
    return available_models


def run_unified_db_initialization(app):
    """Unified database initialization function that handles:
    1. Database creation
    2. Schema migrations
    3. RBAC data seeding
    4. LLM model loading
    
    This function is used by both:
    - Regular application startup
    - CLI command 'flask init-db'
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    app.logger.info("DB_INIT: Beginning unified database initialization")
    try:
        # Ensure the database itself exists before trying to apply migrations.
        create_database_if_not_exists(app)

        # Apply any pending schema migrations with enhanced error handling.
        try:
            app.logger.info("DB_INIT: About to run database migrations...")
            # Run migrations using Flask-Migrate public API
            upgrade()
            app.logger.info("DB_INIT: Running Flask-Migrate upgrade to head")
            
            # Upgrade to the latest migration completed
            app.logger.info("DB_INIT: Database migrations applied successfully")
            
        except Exception as migration_error:
            app.logger.error(f"Error applying database migrations: {migration_error}")
            app.logger.error(f"Migration traceback: {traceback.format_exc()}")
            # Continue with initialization despite migration errors
            # The app may still be able to function with existing schema

        # Initialize RBAC data (roles, admin user, etc.)
        app.logger.info("DB_INIT: About to initialize RBAC data")
        initialize_rbac_data()
        app.logger.info("DB_INIT: RBAC data initialized successfully")

        # Load and ensure LLM models are available
        app.logger.info("DB_INIT: About to ensure LLM models")
        llm_models = load_and_ensure_llm_models(app)
        app.config['LLM_MODELS'] = llm_models if llm_models else []
        app.logger.info("DB_INIT: LLM models initialized successfully")

        return True

    except Exception as e:
        app.logger.error(f"DB_INIT ERROR: Unified database initialization failed: {str(e)}")
        app.logger.error(f"DB_INIT ERROR: {traceback.format_exc()}")
        return False


def init_db(app):
    """Initialize the database with Flask-Migrate
    
    This function is meant to be called via the Flask CLI command 'flask init-db'.
    It provides a convenient way to initialize the database from the CLI.
    
    NOTE: This function delegates to the unified database initialization sequence
    that runs during normal application startup to avoid code duplication and ensure
    consistent behavior between CLI and normal startup.
    """
    # We need to make sure this function doesn't duplicate initialization that
    # happens during normal startup. To do this, we'll use the unified block
    # by running it directly rather than duplicating the logic here.
    
    with app.app_context():
        app.logger.info("CLI_INIT_DB: Beginning database initialization from CLI command")
        try:
            # Execute the same unified database initialization sequence
            # that would run during normal application startup
            run_unified_db_initialization(app)
            
            app.logger.info("CLI_INIT_DB: Database initialization completed successfully")
            return True
        except Exception as e:
            app.logger.error(f"CLI_INIT_DB ERROR: Database initialization failed: {str(e)}")
            app.logger.error(f"CLI_INIT_DB ERROR: {traceback.format_exc()}")
            return False


def get_default_model(app):
    """
    Retrieves the default model from the database.
    
    Returns:
        dict: Default model information or None if not found
    """
    default_model_name = app.config.get('DEFAULT_MODEL_NAME')
    if not default_model_name:
        app.logger.warning("get_default_model: No DEFAULT_MODEL_NAME configured.")
        return None
    
    default_db_model = Model.query.filter_by(ollama_model_name=default_model_name, is_active=True).first()
    if default_db_model:
        app.logger.info(f"get_default_model: Found default model '{default_model_name}' in DB.")
        return {
            'id': default_db_model.id,
            'name': default_db_model.display_name,
            'ollama_model_name': default_db_model.ollama_model_name,
            'description': default_db_model.description
        }
    app.logger.warning(f"get_default_model: Default model '{default_model_name}' not found or not active in DB.")
    return None
