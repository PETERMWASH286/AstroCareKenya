from flask import Blueprint

# Define the Blueprint for pharmacy web views
pharmacy_web_bp = Blueprint(
    'pharmacy_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/pharmacy'
)

from . import routes #, models, schemas, services