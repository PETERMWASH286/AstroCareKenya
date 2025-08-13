from flask import Blueprint

# Define the Blueprint for HR API routes within v1
api_hr_v1_bp = Blueprint('api_hr_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas