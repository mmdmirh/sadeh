from flask import current_app
from werkzeug.security import generate_password_hash

from backend.db.extensions import db
from backend.db.models import Role, User, Model

def initialize_rbac_data(app):
    """
    Initializes default roles and populates the Model table
    from available Ollama models if they don't already exist.
    Also assigns all found models to the 'admin' role.
    """
    app.logger.info("FUNC_INIT_RBAC: Entered initialize_rbac_data function.")
        
    # Proceed with initialization if database is ready
    try:
        app.logger.info("FUNC_INIT_RBAC: Attempting to process roles and models...") 

        # 1. Create default roles
        default_roles_data = {
            "admin": "Administrator with full access to all models and system settings.",
            "user": "Standard user with access to a default set of models."
        }
        admin_role_obj = None
        user_role_obj = None

        for role_name, role_desc in default_roles_data.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name, description=role_desc)
                db.session.add(role)
                app.logger.info(f"Created role: {role_name}")
            if role_name == "admin":
                admin_role_obj = role
            elif role_name == "user":
                user_role_obj = role
        
        try:
            db.session.commit() # Commit roles first
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error committing roles: {e}", exc_info=True)
            return # Cannot proceed without roles

        if not admin_role_obj:
            app.logger.error("Admin role could not be found or created. Cannot proceed.")
            return

        # 2. Create and assign 'Admin' role to the default admin user (admin@admin.com)
        default_admin_email = "admin@admin.com"
        admin_user_obj = User.query.filter_by(email=default_admin_email).first()
        if not admin_user_obj:
            app.logger.info(f"Default admin user '{default_admin_email}' not found. Creating new admin user.")
            hashed_password = generate_password_hash("admin")
            admin_user_obj = User(
                username="admin",
                email=default_admin_email,
                firstname="admin",
                lastname="admin",
                password_hash=hashed_password,
                confirmed=True, 
                is_active=True
            )
            db.session.add(admin_user_obj)
        try:
            db.session.commit() # Commit new admin user first
            app.logger.info(f"Successfully created default admin user '{default_admin_email}'.") 
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating default admin user '{default_admin_email}': {e}", exc_info=True)
            # Don't return, try to proceed with other admin if configured
        
        # Ensure the default admin user is active if they exist
        if admin_user_obj and not admin_user_obj.is_active:
            app.logger.info(f"Ensuring default admin user '{default_admin_email}' is active.")
            admin_user_obj.is_active = True
            # Commit this change before proceeding with role assignment
            try:
                db.session.commit()
                app.logger.info(f"Default admin user '{default_admin_email}' set to active.")
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error setting default admin user '{default_admin_email}' to active: {e}", exc_info=True)

        # Assign Admin role to the default admin user if they exist and don't have it
        if admin_user_obj and admin_role_obj not in admin_user_obj.roles:
            admin_user_obj.roles.append(admin_role_obj)
            try:
                db.session.commit()
                app.logger.info(f"Assigned 'admin' role to default admin user '{default_admin_email}'.") 
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error assigning 'admin' role to default admin user '{default_admin_email}': {e}", exc_info=True)
        elif admin_user_obj:
            app.logger.info(f"Default admin user '{default_admin_email}' already has 'admin' role or was just created with it.")

        # 3. Assign 'Admin' role to the admin user from .env (if different from default and exists)
        admin_username_env = app.config.get('ADMIN_USERNAME')
        if admin_username_env and admin_username_env != "admin": # Check if .env admin is set and different from default 'admin'
            env_admin_user = User.query.filter_by(username=admin_username_env).first()
            if env_admin_user:
                if admin_role_obj not in env_admin_user.roles:
                    env_admin_user.roles.append(admin_role_obj)
                    try:
                        db.session.commit()
                        app.logger.info(f"Assigned 'admin' role to .env admin user '{admin_username_env}'.") 
                    except Exception as e:
                        db.session.rollback()
                        app.logger.error(f"Error assigning 'admin' role to .env admin user '{admin_username_env}': {e}", exc_info=True)
                else:
                    app.logger.info(f".env admin user '{admin_username_env}' already has 'admin' role.")
            else:
                app.logger.warning(f"Admin user '{admin_username_env}' specified in .env not found in database. Cannot assign 'admin' role.")
        elif not admin_username_env:
            app.logger.info("ADMIN_USERNAME not set in .env file. Skipping .env admin role assignment.")
        elif admin_username_env == "admin":
            app.logger.info("ADMIN_USERNAME in .env is 'admin', which is already handled as the default admin. Skipping redundant assignment.")

        # 4. Populate Model table from MANAGED_OLLAMA_MODELS and assign to admin
        app.logger.info("Processing managed models for Model table and admin assignment...")
        
        admin_models_assigned_this_run = [] # To track models assigned to admin in this run
        llm_service_type = app.config.get('LLM_SERVICE_TYPE', 'ollama').lower()


        if llm_service_type == 'ollama':
            managed_ollama_models_from_config = app.config.get('MANAGED_OLLAMA_MODELS', [])
            if not managed_ollama_models_from_config:
                app.logger.warning("No managed Ollama models found in app.config (MANAGED_OLLAMA_MODELS is empty or not set). "
                               "Model table population from this list will be skipped.")
            
            for ollama_model_name in managed_ollama_models_from_config:
                model = Model.query.filter_by(ollama_model_name=ollama_model_name).first()
                if not model:
                    # Attempt to create a somewhat friendly display name
                    display_parts = ollama_model_name.split(':')[0].replace('-', ' ').replace('_', ' ')
                    display_name_generated = ' '.join(word.capitalize() for word in display_parts.split(' '))
                    tag_suffix = ""
                    if ':' in ollama_model_name:
                        tag = ollama_model_name.split(':')[-1]
                        if tag.lower() != 'latest':
                             tag_suffix = f" ({tag.capitalize()})"
                        # else: # For 'latest', no specific tag suffix or a generic one like "(Latest)"
                             # tag_suffix = " (Latest)" # Optional: if you want to explicitly mark 'latest'
                    final_display_name = display_name_generated + tag_suffix

                    model = Model(
                        display_name=final_display_name, # This is the user-facing name
                        ollama_model_name=ollama_model_name, # This is for Ollama API
                        description=f"Ollama model: {ollama_model_name}",
                        is_active=True # Managed models are active by default
                    )
                    db.session.add(model)
                    app.logger.info(f"Created new Model DB entry for managed model: {ollama_model_name} (Display: {final_display_name})")
                    try:
                        db.session.commit() # Commit each new model to get its ID for relationships
                    except Exception as e:
                        db.session.rollback()
                        app.logger.error(f"Error committing new model {ollama_model_name}: {e}", exc_info=True)
                        continue # Skip to next model
                elif not model.is_active:
                    app.logger.info(f"Model '{ollama_model_name}' found in DB but was inactive. Activating it as it's a managed model.")
                    model.is_active = True
                    # No immediate commit needed here, will be committed with role assignment or at the end of this section.

                # Assign to admin role if not already assigned and model object exists
                if admin_role_obj and model and model.id is not None: # Ensure model is committed or fetched with an ID
                    if model not in admin_role_obj.models:
                        admin_role_obj.models.append(model)
                        admin_models_assigned_this_run.append(model.display_name)
                        app.logger.info(f"Assigned model '{model.display_name}' to 'admin' role.")
                elif not model:
                    app.logger.warning(f"Skipped assigning model {ollama_model_name} to admin as model object was None (likely due to creation error).")

        
        elif llm_service_type == 'llamacpp':
            app.logger.info("LLM service is LlamaCPP. Checking/creating DB entry for its default model.")
            llamacpp_default_model_name = app.config.get('EFFECTIVE_DEFAULT_MODEL_NAME')
            if llamacpp_default_model_name:
                model = Model.query.filter_by(ollama_model_name=llamacpp_default_model_name).first()
                if not model:
                    model = Model(
                        display_name=llamacpp_default_model_name, 
                        ollama_model_name=llamacpp_default_model_name, # Using ollama_model_name field for identifier consistency
                        description=f"LlamaCPP model: {llamacpp_default_model_name}",
                        is_active=True
                    )
                    db.session.add(model)
                    app.logger.info(f"Created new Model DB entry for LlamaCPP default model: {llamacpp_default_model_name}")
                    try:
                        db.session.commit() # Commit to get ID
                    except Exception as e:
                        db.session.rollback()
                        app.logger.error(f"Error committing LlamaCPP default model {llamacpp_default_model_name} to DB: {e}", exc_info=True)
                        model = None # Ensure model is None if commit failed
                
                if admin_role_obj and model and model.id is not None:
                    if model not in admin_role_obj.models:
                        admin_role_obj.models.append(model)
                        admin_models_assigned_this_run.append(model.display_name)
                        app.logger.info(f"Assigned LlamaCPP model '{model.display_name}' to 'admin' role.")
            else:
                app.logger.warning("LlamaCPP service type, but no EFFECTIVE_DEFAULT_MODEL_NAME found in app.config.")
        else:
            app.logger.info(f"LLM service type is '{llm_service_type}'. Model DB population from managed list is primarily for Ollama.")

        if admin_models_assigned_this_run:
            app.logger.info(f"Models assigned/confirmed for admin role in this initialization run: {', '.join(admin_models_assigned_this_run)}")

        try:
            db.session.commit() # Commit all changes (new models, model activations, role assignments)
            app.logger.info("Committed all model and admin role assignment changes for initialize_rbac_data.")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Final commit in initialize_rbac_data failed: {e}", exc_info=True)

        app.logger.info("FUNC_INIT_RBAC: Exiting initialize_rbac_data function.")
    except Exception as e:
        app.logger.error(f"Error in initialize_rbac_data: {str(e)}")
        # Set the flag in app config to indicate database is not fully initialized
        app.config['DATABASE_INITIALIZED'] = False


def create_database_if_not_exists(app):
    """
    Creates the database if it does not exist.
    This function should be called before any other database operation.
    """
    # First verify that we have a database URI configured
    if 'SQLALCHEMY_DATABASE_URI' not in app.config:
        app.logger.error("SQLALCHEMY_DATABASE_URI not found in app configuration!")
        app.logger.info(f"Available config keys: {', '.join(key for key in app.config.keys() if not key.startswith('_'))}")
        return
    
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    app.logger.info(f"Using database URI: {db_uri[:db_uri.find('@')+1]}[CREDENTIALS_HIDDEN]{db_uri[db_uri.find('@'):]}")  # Log URI with hidden credentials
        
    try:
        # First try to connect to the database
        from sqlalchemy import create_engine
        engine = create_engine(db_uri)
        engine.connect()
        app.logger.info("Database exists. No need to create.")
    except Exception as e:
        app.logger.warning(f"Error connecting to database: {str(e)}")
        app.logger.info("Attempting to create database...")
        
        try:
            # Parse connection string to extract database name
            uri_parts = db_uri.split('/')
            if len(uri_parts) < 4:
                app.logger.error(f"Invalid database URI format: {db_uri[:10]}...")
                return
                
            db_name = uri_parts[-1].split('?')[0]  # Remove query parameters
            app.logger.info(f"Extracted database name: {db_name}")
            
            # Create engine without database name to connect to MySQL server
            base_uri = '/'.join(uri_parts[:-1]) + '/'  # URI without database name
            engine = create_engine(base_uri)
            
            # Create database
            with engine.connect() as conn:
                conn.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                app.logger.info(f"Created database: {db_name}")
                
        except Exception as e:
            app.logger.error(f"Failed to create database: {str(e)}")
            # Print full traceback for debugging
            import traceback
            app.logger.error(f"Traceback: {traceback.format_exc()}")
