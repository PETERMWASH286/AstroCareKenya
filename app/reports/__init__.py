from flask import Blueprint

# Define the Blueprint for reports web views
reports_web_bp = Blueprint(
    'reports_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/reports'
)

from . import routes #, models, schemas, services