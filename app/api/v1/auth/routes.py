from flask import jsonify, request, current_app
# Removed 'fresh_jwt_required' from the import statement
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, create_refresh_token, set_access_cookies, set_refresh_cookies, unset_jwt_cookies
from app.extensions import jwt # Import the initialized JWTManager
from app.auth.services import AuthService # Call into the core auth service logic
from app.auth.models import User # Import User model if needed for identity lookup
from app.auth.schemas import LoginSchema, TokenSchema # Import schemas for request validation/response serialization

from . import api_auth_v1_bp # Import the blueprint


# Configure JWT user identity lookup if needed (e.g., to load the User object from token)
# @jwt.user_lookup_loader
# def user_lookup_callback(_jwt_header, jwt_data):
#     identity = jwt_data["sub"] # Assuming 'sub' contains {'id': user.id}
#     return User.query.get(identity['id'])


@api_auth_v1_bp.route('/login', methods=['POST'])
def api_login():
    """Handle API login and return JWT tokens."""
    schema = LoginSchema()
    try:
        # Validate and load request data using Marshmallow schema
        login_data = schema.load(request.json)
    except Exception as err: # Catch Marshmallow ValidationError specifically in a real app
        current_app.logger.error(f"Login validation failed: {err}")
        return jsonify({"message": "Invalid input data"}), 400


    username = login_data['username']
    password = login_data['password']

    user = AuthService.authenticate_user(username, password)

    if not user:
        return jsonify({"message": "Invalid credentials"}), 401

    # Generate tokens using the service layer
    access_token, refresh_token = AuthService.generate_tokens(user)

    response = jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token
    })

    # Example: Setting tokens in HTTP-only cookies (more secure against XSS)
    # set_access_cookies(response, access_token)
    # set_refresh_cookies(response, refresh_token)

    return response, 200


@api_auth_v1_bp.route('/refresh', methods=['POST'])
# @jwt_required(refresh=True) # Require a valid refresh token - Keep this!
# Removed the problematic 'fresh_jwt_required' decorator here
@jwt_required(refresh=True)
def api_refresh():
    """Generate a new access token using a refresh token."""
    current_user_identity = get_jwt_identity()

    # Optional: You might want to load the user from the database here
    # to ensure they are still active, etc.
    # user = User.query.get(current_user_identity['id'])
    # if user is None or not user.is_active:
    #    return jsonify({"message": "User not found or inactive"}), 401

    # Create a new access token
    # Note: The expires_delta=False here means no expiration, which is usually NOT desired.
    # It should use a defined timedelta, like timedelta(minutes=15)
    # Update to use a proper expiration (using default or config expiry):
    new_access_token = create_access_token(identity=current_user_identity)


    response = jsonify({"access_token": new_access_token})

    # Example: Update access token cookie
    # set_access_cookies(response, new_access_token)

    return response, 200


@api_auth_v1_bp.route('/logout', methods=['POST'])
@jwt_required() # Require a valid access token (or refresh token if logging out completely)
def api_logout():
    """Revoke the current token (optional if using stateless JWTs)."""
    response = jsonify({"message": "Successfully logged out"})
    # unset_jwt_cookies(response) # Uncomment if using cookie tokens
    return response, 200


@api_auth_v1_bp.route('/protected', methods=['GET'])
@jwt_required() # Require a valid access token
def protected_api_route():
    """Example of a route that requires authentication."""
    current_user_identity = get_jwt_identity()
    return jsonify({
        "message": "Access granted to protected route",
        "logged_in_as": current_user_identity
    }), 200