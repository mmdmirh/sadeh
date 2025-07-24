"""
Swagger UI integration for Sadeh application

This script shows how to integrate Swagger UI into the Flask application
by adding the flask-swagger-ui extension.

To use:
1. Install flask-swagger-ui: pip install flask-swagger-ui
2. Import and call setup_swagger() in your app.py after Flask app is created
"""

import os
import json
import yaml
from flask_swagger_ui import get_swaggerui_blueprint

def setup_swagger(app):
    """
    Setup Swagger UI for the Flask application
    
    Args:
        app: Flask application instance
    """
    # Path to the OpenAPI/Swagger documentation file
    openapi_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api', 'openapi.yaml')
    
    # URL for accessing the Swagger UI
    SWAGGER_URL = '/api/docs'
    
    # URL for accessing the OpenAPI JSON
    API_URL = '/api/swagger.json'
    
    # Load YAML and serve it as JSON
    with open(openapi_path, 'r') as yaml_file:
        openapi_spec = yaml.safe_load(yaml_file)
    
    # Create Swagger UI blueprint
    swaggerui_blueprint = get_swaggerui_blueprint(
        SWAGGER_URL,
        API_URL,
        config={
            'app_name': "Sadeh API Documentation",
            'validatorUrl': None  # Disable validation
        }
    )
    
    # Register blueprint
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    
    # Route for serving the OpenAPI spec as JSON
    @app.route(API_URL)
    def swagger_json():
        return json.dumps(openapi_spec)
    
    # Log registration
    app.logger.info(f"Swagger UI registered at {SWAGGER_URL}")
    
    return app
