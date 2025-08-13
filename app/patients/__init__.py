from flask import Blueprint

# Define the Blueprint for patient management web views
patients_web_bp = Blueprint(
    'patients_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/patients'
)

# Import main routes, models, schemas, services for the patients module
from . import routes #, models, schemas, services

# Optional: If records and visits sub-modules have their own blueprints
# and you want to register them directly in app/__init__.py, import them here:
# from .records import patients_records_web_bp
# from .visits import patients_visits_web_bp