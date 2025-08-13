from flask import Blueprint

# Define the Blueprint for appointments web views
appointments_web_bp = Blueprint(
    'appointments_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/appointments'
)

from . import routes #, models, schemas, services