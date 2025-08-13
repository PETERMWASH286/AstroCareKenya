from flask import Blueprint

# Define the Blueprint for notifications web views
notifications_web_bp = Blueprint(
    'notifications_web', __name__,
    template_folder='templates',
    static_folder='static', # If needed
    # url_prefix='/notifications'
)

from . import routes