from flask import Blueprint

# Define the Blueprint for dashboard API routes within v1
api_dashboard_v1_bp = Blueprint('api_dashboard_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas