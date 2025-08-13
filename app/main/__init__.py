# C:\Users\user\Desktop\AstroCare-main\app\main\__init__.py

from flask import Blueprint

# Define the blueprint for the main application routes.
# The 'template_folder' argument tells Flask where to look for templates
# specifically for this blueprint (e.g., app/main/templates/).
# The 'static_folder' is useful if this blueprint has its own static files.
main_bp = Blueprint('main_bp', __name__, template_folder='templates', static_folder='static')

# Import routes here to register them with the blueprint.
# This import needs to be at the end of the file to avoid circular imports,
# as 'routes.py' will itself import 'main_bp'.
from app.main import routes