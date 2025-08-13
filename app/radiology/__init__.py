from flask import Blueprint

# Define the Blueprint for radiology web views
radiology_web_bp = Blueprint(
    'radiology_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/radiology'
)

from . import routes #, models, schemas, services