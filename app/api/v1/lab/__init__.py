from flask import Blueprint

# Define the Blueprint for lab API routes within v1
api_lab_v1_bp = Blueprint('api_lab_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas