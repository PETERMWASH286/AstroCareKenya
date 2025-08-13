from flask import Blueprint

# Define the Blueprint for patient records web views (sub-module)
patients_records_web_bp = Blueprint(
    'patients_records_web', __name__, # Unique name
    template_folder='templates',     # Templates in app/patients/records/templates/
    static_folder='static',        # If needed
    # url_prefix='/patients/records' # Prefix set during registration (e.g., in app/__init__.py)
)

# Import routes, models, schemas, services *after* the blueprint is created
from . import routes #, models, schemas, services