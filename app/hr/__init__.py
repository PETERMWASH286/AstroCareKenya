from flask import Blueprint

# Define the Blueprint for HR web views
hr_web_bp = Blueprint(
    'hr_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    url_prefix='/hr'
)

from . import routes , models, schemas, services