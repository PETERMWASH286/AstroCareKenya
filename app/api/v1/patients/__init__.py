from flask import Blueprint

# Define the Blueprint for patients API routes within v1
api_patients_v1_bp = Blueprint('api_patients_v1', __name__) # Unique name
# No template_folder or static_folder for API blueprints
# url_prefix set during registration in app/api/v1/__init__.py

# Import routes and schemas *after* the blueprint is created
from . import routes, schemas