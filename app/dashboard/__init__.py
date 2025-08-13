from flask import Blueprint

# Define the Blueprint for web dashboard views
dashboard_web_bp = Blueprint(
    'dashboard_web', __name__,
    template_folder='templates', # Specifies where templates for this blueprint are located
    static_folder='static',    # Optional: Specifies static folder if blueprint has its own
    url_prefix='/dashboard'    # All routes in routes.py will be prefixed with /dashboard
)

# Import routes and models here to register them with the blueprint
# This needs to be done *after* the Blueprint is created
from . import routes # models, schemas, services might also be here