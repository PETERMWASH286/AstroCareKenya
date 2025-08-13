from flask import Blueprint

# Define the Blueprint for authentication API routes within v1
api_auth_v1_bp = Blueprint('api_auth_v1', __name__)
# No url_prefix here, as it's registered with api_v1_bp which provides '/auth'


# Import routes and schemas for this API blueprint
from . import routes, schemas

# Optional: Register API-specific error handlers here if needed
# @api_auth_v1_bp.errorhandler(CustomAuthAPIError)
# def handle_api_auth_error(error):
#     return jsonify({"message": error.message}), error.status_code