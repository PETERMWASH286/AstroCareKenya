from flask import render_template, jsonify
from app.extensions import db # Assuming db is needed for session rollback

# --- Web View Error Handlers (Render Templates) ---
# These functions are called by the errorhandler decorators in app/__init__.py
# They should return a rendered template and a status code.

def bad_request(error):
    """Handle 400 Bad Request for web views."""
    return render_template('errors/400.html'), 400

def unauthorized(error):
    """Handle 401 Unauthorized for web views."""
    return render_template('errors/401.html'), 401

def forbidden(error):
    """Handle 403 Forbidden for web views."""
    return render_template('errors/403.html'), 403

def not_found(error):
    """Handle 404 Not Found for web views."""
    return render_template('errors/404.html'), 404

def internal_error(error):
    """Handle 500 Internal Server Error for web views."""
    db.session.rollback() # Ensure session is clean
    return render_template('errors/500.html'), 500


# --- API Error Handlers (Return JSON) ---
# These functions provide a consistent JSON response format for API errors.
# The errorhandler decorators in app/__init__.py check if the path starts with /api/
# and call these instead of rendering templates.

def api_error_response(status_code, message=None, errors=None):
    """Helper function to create a standard JSON error response."""
    payload = {'error': 'An error occurred', 'status': status_code}
    if message:
        payload['message'] = message
    if errors:
        payload['errors'] = errors # For validation errors etc.
    response = jsonify(payload)
    response.status_code = status_code
    return response

def api_bad_request(error):
    """Handle 400 Bad Request for API."""
    # In a real app, parse 'error' object to get specific validation messages
    message = 'The request was malformed or invalid.'
    # Example: if using Flask-WTF or Marshmallow and the error object contains details
    # errors = error.description # Or access specific error details
    return api_error_response(400, message=message) # , errors=errors)

def api_unauthorized(error):
     """Handle 401 Unauthorized for API."""
     message = 'Authentication is required.'
     return api_error_response(401, message=message)

def api_forbidden(error):
     """Handle 403 Forbidden for API."""
     message = 'You do not have permission to access this resource.'
     return api_error_response(403, message=message)

def api_not_found(error):
    """Handle 404 Not Found for API."""
    message = 'The requested resource was not found.'
    return api_error_response(404, message=message)

def api_internal_error(error):
    """Handle 500 Internal Server Error for API."""
    db.session.rollback() # Ensure session is clean
    message = 'An internal server error occurred.'
    # In production, avoid sending detailed error information to the client
    return api_error_response(500, message=message)

def api_unprocessable_entity(error):
    """Handle 422 Unprocessable Entity (common for API validation errors like Marshmallow)."""
    # Marshmallow validation errors often result in a 422 status code
    # The error object typically contains a 'messages' attribute with validation details
    messages = error.exc.messages if hasattr(error, 'exc') and hasattr(error.exc, 'messages') else None
    return api_error_response(422, message="Validation error", errors=messages)


# You would register these API handlers in app/__init__.py using app.register_error_handler(status_code, handler_function)
# or handle them conditionally based on the request path as shown in create_app().