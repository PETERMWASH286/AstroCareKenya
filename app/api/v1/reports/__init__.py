from flask import Blueprint

# Define the Blueprint for reports API routes within v1
api_reports_v1_bp = Blueprint('api_reports_v1', __name__) # Unique name

# Import routes and schemas
from . import routes, schemas