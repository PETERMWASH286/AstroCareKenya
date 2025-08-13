from flask import Blueprint

# Define the Blueprint for pharmacy API routes within v1
api_pharmacy_v1_bp = Blueprint('api_pharmacy_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas