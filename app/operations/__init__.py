# app/operations/__init__.py
from flask import Blueprint

# Create the blueprint
operations_web_bp = Blueprint('operations_web_bp', __name__, template_folder='templates', static_folder='static')

# Import routes (must be after blueprint creation to avoid circular imports)
from . import routes, models
