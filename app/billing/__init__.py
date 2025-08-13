from flask import Blueprint

# Define the Blueprint for billing web views
billing_web_bp = Blueprint(
    'billing_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/billing'
)

from . import routes #, models, schemas, services