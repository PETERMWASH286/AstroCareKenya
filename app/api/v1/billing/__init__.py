from flask import Blueprint

# Define the Blueprint for billing API routes within v1
api_billing_v1_bp = Blueprint('api_billing_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas