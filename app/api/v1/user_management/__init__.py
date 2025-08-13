from flask import Blueprint

# Define the Blueprint for user management API routes within v1
api_user_management_v1_bp = Blueprint('api_user_management_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas