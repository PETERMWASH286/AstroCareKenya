from flask import Blueprint

# Define the Blueprint for API version 1
api_v1_bp = Blueprint(
    'api_v1', __name__,
    url_prefix='/v1' # Routes in sub-blueprints will be prefixed with /api/v1/
)

# Import sub-blueprints for API modules here
# These sub-blueprints will be registered with api_v1_bp in create_app if needed,
# or they can be registered directly with the main app blueprint if preferred.
# Let's register them here to keep API v1 self-contained.

from .auth import api_auth_v1_bp
# from .patients import api_patients_v1_bp # Example
# ... import other API module blueprints

# Register the sub-blueprints with the api_v1_bp
api_v1_bp.register_blueprint(api_auth_v1_bp, url_prefix='/auth')
# api_v1_bp.register_blueprint(api_patients_v1_bp, url_prefix='/patients') # Example
# ... register other API module blueprints


# Note: The main app blueprint (e.g., in app/__init__.py) will register api_v1_bp:
# app.register_blueprint(api_v1_bp, url_prefix='/api/v1')
# Resulting path: /api/v1/<sub-blueprint-prefix>/<route-path>