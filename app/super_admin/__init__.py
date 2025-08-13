from flask import Blueprint

# Define the Blueprint for lab web views
admin_web_bp = Blueprint(
    'admin_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/lab'
)

from . import routes, models, schemas, services