from flask import Blueprint

# Define the Blueprint for appointments API routes within v1
api_appointments_v1_bp = Blueprint('api_appointments_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas