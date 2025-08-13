from flask import Blueprint

# Define the Blueprint for web views related to authentication
auth_web_bp = Blueprint(
    'auth_web', __name__,
    template_folder='templates', # Specifies where templates for this blueprint are located
    static_folder='static',    # Optional: Specifies static folder if blueprint has its own
    url_prefix='/auth'         # All routes in routes.py will be prefixed with /auth
)

# Import routes and models here to register them with the blueprint
# This needs to be done *after* the Blueprint is created
from . import routes, models, schemas, services

# You can also register error handlers specific to this blueprint here if needed
# @auth_web_bp.errorhandler(AuthError)
# def handle_auth_error(error):
#    return render_template('errors/auth_error.html', error=error.message), 401