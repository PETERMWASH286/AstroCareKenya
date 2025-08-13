from flask import Blueprint

# Define the Blueprint for patient visits web views (sub-module)
patients_visits_web_bp = Blueprint(
    'patients_visits_web', __name__, # Unique name
    template_folder='templates',     # Templates in app/patients/visits/templates/
    static_folder='static',        # If needed
    # url_prefix='/patients/visits' # Prefix set during registration (e.g., in app/__init__.py)
)

# Import routes, models, schemas, services *after* the blueprint is created
from . import routes #, models, schemas, services