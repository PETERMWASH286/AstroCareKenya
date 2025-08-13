from flask import Blueprint

# Define the Blueprint for user management web views
user_management_web_bp = Blueprint(
    'user_management_web', __name__, # Unique name for the blueprint
    template_folder='templates',     # Tells Flask to look for templates in app/user_management/templates/
    static_folder='static',        # Optional: Uncomment if this blueprint has its own static files in app/user_management/static/
    # url_prefix='/users'          # NOTE: url_prefix is usually set during registration in the parent (app/__init__.py) for flexibility
)

# Import routes, models, schemas, services *after* the blueprint is created
# Flask needs to import these files to discover the routes (@blueprint.route)
from . import routes #, models, schemas, services