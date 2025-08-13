from flask import Blueprint

# Define the Blueprint for radiology API routes within v1
api_radiology_v1_bp = Blueprint('api_radiology_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas