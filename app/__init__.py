# ADDED: Simple print to confirm this file is being executed

from datetime import date, datetime
import os
import logging
from logging.handlers import RotatingFileHandler
from sqlalchemy import event

# ADDED: Import redirect, url_for, g, current_user from flask_login, and current_app
from flask import Flask, abort, json, render_template, jsonify, request, g, redirect, send_from_directory, url_for, current_app
# from flask_debugtoolbar import DebugToolbarExtension
from flask.cli import with_appcontext
from flask_login import current_user
import markdown

from app.models import AuditLog
from app.super_admin.models import Hospital
from .audit import after_insert_listener, before_update_listener, before_flush_listener

# Import config and extensions
# UPDATED: Import login_manager
from app.config import config
from app.extensions import db, migrate, jwt, mail, bcrypt, ma, login_manager, get_tenant_engine, clear_tenant_registry, socketio
from sqlalchemy.orm import scoped_session, sessionmaker

# Import core application blueprints
from app.auth import auth_web_bp
from app.dashboard import dashboard_web_bp
from app.store.models import StockRequest
from app.user_management import user_management_web_bp
from app.hr import hr_web_bp
from app.patients import patients_web_bp
from app.appointments import appointments_web_bp
from app.billing import billing_web_bp
from app.pharmacy import pharmacy_web_bp
from app.lab import lab_web_bp
from app.radiology import radiology_web_bp
from app.reports import reports_web_bp
from app.notifications import notifications_web_bp
from app.patients.consultations import consultations_web_bp
# Update imports at the top of the file
from app.store import store_web_bp
from app.finance import finance_web_bp
from app.super_admin import admin_web_bp
from app.asset_management import asset_management_bp
from app.board import board_bp
# Import the main API v1 blueprint
from app.api.v1 import api_v1_bp
from app.notifications import communications as comms_module
from app.utils.notifications import notification_manager

# Import error handlers module
from app.errors import handlers as error_handlers

# Import CLI commands
from app.commands import register_commands

# ADDED: Import User model and Permission class
from app.auth.models import User, Permission
from flask_caching import Cache
from flask_moment import Moment # <--- ADD THIS IMPORT

cache = Cache()

def datetimeformat(value, format='%d/%m/%Y'):
    if isinstance(value, datetime):
        return value.strftime(format)
    return value  # fallback if not a datetime object



def time_ago(value):
    now = datetime.utcnow()
    
    # If value is a date object, convert to datetime at start of day
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    
    diff = now - value
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{int(minutes)} minutes ago"
    hours = minutes // 60
    if hours < 24:
        return f"{int(hours)} hours ago"
    days = hours // 24
    if days < 30:
        return f"{int(days)} days ago"
    months = days // 30
    if months < 12:
        return f"{int(months)} months ago"
    years = days // 365
    return f"{int(years)} years ago"

def register_filters(app: Flask):
    app.jinja_env.filters['datetimeformat'] = datetimeformat
def stock_request_context():
    return {
        'pending_stock_requests': StockRequest.query.filter_by(
            department='Pharmacy', 
            status='pending'
        ).count()
    }

def duration_filter(delta):
    if not delta:
        return "N/A"
    
    total_seconds = delta.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return f"{hours}h {minutes}m"
# simple cache to avoid rebuilding engines on every request
def create_app(config_name='default'):
    """
    Factory function to create the Flask application instance.
    """
    app = Flask(__name__)
    app.config.from_object(config[config_name])



    app.config['CACHE_TYPE'] = 'SimpleCache'  # For development
    app.config['CACHE_DEFAULT_TIMEOUT'] = 600  # 10 minutes
    cache.init_app(app)
    app.cache = cache  # 🔑 Attach cache instance to app

    init_extensions(app)
        # ===== Multi-tenancy Setup =====
    # ===== Multi-tenancy Setup =====
    @app.before_request
    def connect_to_tenant_db():
        """Establish tenant-specific database connection and handle root URL redirection."""
        host = request.host.split(':')[0]  # Remove port
        base_domain = app.config['BASE_DOMAIN']
        env = app.config.get('ENV', 'production')

        # --- New Logic for Root URL Redirection to Main Blueprint ---
        # If the request is for the base domain/IP and not already targeting a specific route,
        # redirect to the main blueprint's index.
        # This primarily targets 'http://localhost:5000/' or 'http://0.0.0.0:5000/'
        if (env == 'development' and host in ('0.0.0.0', '127.0.0.1', 'localhost')) or (host == base_domain):
            # Check if the requested endpoint belongs to a non-main blueprint and has no subdomain context.
            # This is to prevent endless redirects if a blueprint's route is directly accessed at the root.
            # We want to redirect *only* when the root URL is hit, not every route.
            # If the current request's endpoint is not explicitly for the 'main_bp.index'
            # and there's no subdomain indicating a tenant, then redirect.
            if request.endpoint != 'main_bp.index' and not (host.endswith(f".{base_domain}") and host != base_domain):
                # Ensure the request path is just '/' or an empty string after stripping leading/trailing slashes
                # or if it's the root domain and no specific path is given.
                if request.path == '/' or request.path == '':
                     # Use the central database for main routes
                    db.session.bind = db.engine 
                    current_app.logger.debug(f"Redirecting root URL from {request.url} to main_bp.index.")
                    return redirect(url_for('main_bp.index'))
            
            # For development, if on localhost/IP and not the root path, proceed with central DB
            if env == 'development' and host in ('0.0.0.0', '127.0.0.1', 'localhost'):
                db.session.bind = db.get_engine(app) # This likely points to your central DB
                g.tenant_subdomain = None # Explicitly set no subdomain for central access
                return # Exit before tenant logic if we're on development root

        # --- Existing Multi-tenancy Logic (modified slightly to integrate) ---

        subdomain = None
        if host == base_domain:
            subdomain = None
        elif host.endswith(f".{base_domain}"):
            subdomain = host[: -len(f".{base_domain}")]
        else:
            # Handle IP addresses/localhost in production or if not caught by dev redirect
            if env == 'development' and host in ('0.0.0.0', '127.0.0.1', 'localhost'):
                # This branch should now primarily handle cases like 'localhost:5000/some-other-path'
                # where it should still use the central DB unless X-Tenant-Subdomain header is present
                subdomain = request.headers.get('X-Tenant-Subdomain', None)
            else:
                # Default case for unknown hosts not matching base_domain
                subdomain = None # Or you might want to redirect to a generic error page

        # Store in g for access throughout request
        g.tenant_subdomain = subdomain
        
        # Handle non-tenant routes (this condition is still valid for explicit non-tenant subdomains)
        if not subdomain or subdomain in app.config['NON_TENANT_SUBDOMAINS']:
            # Use central database for these explicit non-tenant cases
            db.session.bind = db.engine
            return
        
        # Get tenant-specific engine
        engine = get_tenant_engine(subdomain)
        
        if not engine:
            app.logger.error(f"Tenant database not found for subdomain: {subdomain}")
            abort(404, description="Hospital not found")
        
        # Create tenant-scoped session
        g.tenant_session = scoped_session(
            sessionmaker(bind=engine, autocommit=False, autoflush=False)
        )
        
        # Patch db.session to use tenant session
        db.session = g.tenant_session
    
    @app.teardown_request
    def teardown_tenant_db(exception=None):
        """Cleanup tenant database connection"""
        tenant_session = g.pop('tenant_session', None)
        
        if tenant_session:
            tenant_session.remove()
        
        # Reset to original default session if it was patched
        # This ensures db.session is always reset to the central one after a request
        # regardless of whether a tenant session was used.
        if hasattr(db, '_original_session'):
            db.session = db._original_session
    
    # Patch original session during initialization
    with app.app_context():
        db._original_session = db.session
    register_blueprints(app)
    register_commands(app)
    register_error_handlers(app)
    configure_logging(app)
    moment = Moment(app) # <--- INITIALIZE FLASK-MOMENT HERE

#     # Initialize SocketIO
#     socketio.init_app(
#         app,
#         async_mode='eventlet',
#         cors_allowed_origins="*",
#         manage_session=False,
#     logger=True,  # Enable for debugging
#     engineio_logger=True
# )
    @socketio.on('connect')
    def on_connect():
        print('client connected')
    # --- Flask-Login Configuration ---
    login_manager.login_view = 'auth_web.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # --- Template Context Processors ---
    @app.context_processor
    def inject_template_globals():
        from flask_login import current_user # Import here
        return dict(current_user=current_user, g=g, Permission=Permission)






    @app.after_request
    def after_request_logic(response):
        return response

    # --- Shell Context Processor ---
    @app.shell_context_processor
    def shell_context():
        from app.auth.models import User, Role, Permission
        return dict(
            db=db,
            User=User,
            Role=Role,
            Permission=Permission,
        )
    # In your Flask app setup
    def format_number(value):
        return "{:,.0f}".format(value)

    app.jinja_env.filters['number_format'] = format_number
    app.jinja_env.filters['time_ago'] = time_ago
    app.jinja_env.globals['datetime'] = datetime 

    # Add custom Jinja filters
    @app.template_filter('mask_email')
    def mask_email_filter(value):
        """Masks email addresses for display"""
        if '@' not in value:
            # Handle phone numbers
            if len(value) > 6:
                return value[:3] + '***' + value[-3:]
            return value[:2] + '***'
        
        # Handle email addresses
        local, domain = value.split('@', 1)
        if len(local) > 2:
            return local[:2] + '***@' + domain
        return local[0] + '***@' + domain
        # Add custom datetime filters
    @app.template_filter('datetime')
    def format_datetime(value, format="medium"):
        if format == "full":
            format = "%Y-%m-%d %H:%M:%S"
        elif format == "medium":
            format = "%Y-%m-%d %H:%M"
        elif format == "time":
            format = "%H:%M"
        return value.strftime(format)

    @app.template_filter('date')
    def format_date(value):
        return value.strftime("%b %d, %Y")

            # Add markdown filter
    @app.template_filter('markdown')
    def markdown_filter(text):
        return markdown.markdown(text, extensions=['extra'])
    

    app.jinja_env.filters['duration'] = duration_filter


    def escapejs_filter(value):
        # Simple JSON string escape for JS safety
        return json.dumps(value)

    app.jinja_env.filters['escapejs'] = escapejs_filter
    # Configure upload settings
    # Set correct upload path inside app/__init__.py
    app.config['UPLOAD_FOLDER'] = os.path.join('app', 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

    # Ensure directory exists
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        app.logger.info(f"Upload directory initialized at: {app.config['UPLOAD_FOLDER']}")
    except Exception as e:
        app.logger.error(f"Failed to create upload directory: {str(e)}")
        raise
    
    @app.context_processor
    def inject_user_helpers():
        return dict(has_privilege=current_user.has_privilege if current_user.is_authenticated else lambda x: False)

    @app.route('/docs/')
    @app.route('/docs/<path:path>')
    def help_docs(path='index.html'):
        # Absolute path to the MkDocs 'site' folder
        docs_path = os.path.abspath(os.path.join(current_app.root_path, '..', 'hms-docs', 'site'))

        # If path ends with a slash, serve index.html inside that folder
        if path.endswith('/'):
            path = os.path.join(path, 'index.html')

        # Try adding .html if missing (MkDocs uses pretty URLs)
        if not os.path.splitext(path)[1]:
            path = f"{path}/index.html"

        # Check if the file exists
        file_path = os.path.join(docs_path, path)
        if os.path.exists(file_path):
            return send_from_directory(docs_path, path)
        else:
            return "404 Not Found", 404


    # Route to redirect the root URL (/) to the login page
    @app.route('/')
    def index_redirect():
        return redirect(url_for('auth_web.login'))

    app.logger.info(f'AstroCare App created with {config_name} configuration.')
    app.context_processor(stock_request_context)
    register_filters(app)


    @app.template_filter('format_currency')
    def format_currency(value):
        return "KES {:,.2f}".format(value)
        # Add this after your other template filters
    @app.template_filter('currency')
    def currency_filter(value):
        """Format value as currency."""
        if value is None:
            return "KES 0.00"
        try:
            # Format as Kenyan Shillings with 2 decimal places
            return "KES {:,.2f}".format(float(value))
        except (ValueError, TypeError):
            return "KES 0.00"

    # Move this inside app context after db initialization
    with app.app_context():
        # Initialize extensions first

        # Attach audit listeners using new registry system
        for mapper in db.Model.registry.mappers:
            model = mapper.class_
            if (
                hasattr(model, '__tablename__') and 
                getattr(model, '__audit_trail__', True) and
                model != AuditLog  # Exclude AuditLog itself
            ):
                event.listen(model, 'after_insert', after_insert_listener)
                event.listen(model, 'before_update', before_update_listener)
        
        event.listen(db.session, 'before_flush', before_flush_listener)
    return app

def init_extensions(app):
    """Initialize Flask extensions with the app instance."""
    db.init_app(app)
    
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    ma.init_app(app)
    login_manager.init_app(app)
    notification_manager.init_app(app)

    # Example: Initialize other extensions
    # cache = Cache()




# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """
    Required by Flask-Login. Loads a user from the database based on user_id.
    The user_id comes from the session.
    """

    if user_id is not None:
        try:
            user = User.query.get(int(user_id))
            # ADDED: Log the result of the user lookup and is_active status
            # ADDED: Print the result before returning
            return user
        except Exception as e:
            current_app.logger.error(f"Error loading user {user_id}: {e}")
            return None
    current_app.logger.info("load_user received None user_id, returning None.")
    return None




def register_blueprints(app):
    """Register application blueprints."""
    app.register_blueprint(auth_web_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_web_bp, url_prefix='/dashboard')
    app.register_blueprint(user_management_web_bp, url_prefix='/user-management')
    app.register_blueprint(hr_web_bp, url_prefix='/hr')
    app.register_blueprint(patients_web_bp, url_prefix='/patients')
    app.register_blueprint(appointments_web_bp, url_prefix='/appointments')
    app.register_blueprint(billing_web_bp, url_prefix='/billing')
    app.register_blueprint(pharmacy_web_bp, url_prefix='/pharmacy')
    app.register_blueprint(lab_web_bp, url_prefix='/lab')
    app.register_blueprint(radiology_web_bp, url_prefix='/radiology')
    app.register_blueprint(reports_web_bp, url_prefix='/reports')
    app.register_blueprint(notifications_web_bp, url_prefix='/notifications')
    app.register_blueprint(consultations_web_bp)
    # New blueprints
    app.register_blueprint(store_web_bp, url_prefix='/inventory')
    app.register_blueprint(finance_web_bp, url_prefix='/finance')

    app.register_blueprint(api_v1_bp, url_prefix='/api/v1')
    app.register_blueprint(admin_web_bp, url_prefix='/super-admin')
    # NEW: Admin
    from app.super_admin.admin_routes import admin_web

    app.register_blueprint(admin_web, url_prefix='/admin')
    
    app.register_blueprint(asset_management_bp, url_prefix='/asset-management')
    app.register_blueprint(board_bp, url_prefix='/board')
# Add this with other blueprint registrations
    app.register_blueprint(comms_module.comms_web_bp)
    from app.main import main_bp
    app.register_blueprint(main_bp) 

def register_error_handlers(app):
    """Register application-wide error handlers."""
    # ... (error handlers remain the same) ...
    @app.errorhandler(400)
    def bad_request_error(error):
        if request.path.startswith('/api/'):
            return error_handlers.api_bad_request(error)
        return render_template('errors/400.html'), 400

    @app.errorhandler(401)
    def unauthorized_error(error):
        if request.path.startswith('/api/'):
            return error_handlers.api_unauthorized(error)
        return render_template('errors/401.html'), 401

    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith('/api/'):
            return error_handlers.api_forbidden(error)
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return error_handlers.api_not_found(error)
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.path.startswith('/api/'):
            return error_handlers.api_internal_error(error)
        return render_template('errors/500.html'), 500

    # --- JWT Error Handlers ---
    @jwt.unauthorized_loader
    def custom_unauthorized_response(callback):
        return jsonify({"message": "Missing or invalid token"}), 401

    @jwt.expired_token_loader
    def custom_expired_token_callback(jwt_header, jwt_payload):
         return jsonify({"message": "The token has expired", "expired_at": jwt_payload['exp']}), 401

    @jwt.invalid_token_loader
    def custom_invalid_token_callback(callback):
         return jsonify({"message": callback}), 422

    @jwt.user_lookup_error_loader
    def custom_user_lookup_error_callback(jwt_header, jwt_payload):
        identity = jwt_payload["sub"]
        return jsonify(f"User ID {identity} not found"), 401

    @jwt.token_verification_loader
    def custom_token_verification_loader(jwt_header, jwt_payload):
        return True # Basic pass-through

    @jwt.needs_fresh_token_loader
    def custom_needs_fresh_token_callback(jwt_header, jwt_payload):
        return jsonify({"message": "Fresh token required"}), 401


def configure_logging(app):
    """Configure application logging."""
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/astrocare.log', maxBytes=10240, backupCount=10)
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.INFO)

        app.logger.addHandler(file_handler)
        app.logger.addHandler(stream_handler)

        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.addHandler(file_handler)
        werkzeug_logger.addHandler(stream_handler)

        app.logger.setLevel(logging.INFO)
        werkzeug_logger.setLevel(logging.INFO)

    else:
        app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

