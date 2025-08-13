import os
from dotenv import load_dotenv

# Load environment variables from .env file in the project root
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '.env'))

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Flask application.")
    # Multi-tenancy configuration
    BASE_DOMAIN = os.environ.get('BASE_DOMAIN', 'localhost')  # e.g., 'hms.example.com'
    NON_TENANT_SUBDOMAINS = {
        None,
        'www',
        'admin',
        '0.0.0.0',
        '127.0.0.1',
        'localhost',
    }
    TENANT_CACHE_TIMEOUT = 300  # 5 minutes cache for tenant engines
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']   # ← your “astrocare_db”
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_BINDS = {}  # we’ll populate this at startup

    DB_USER   = os.environ.get('DB_USER', '')
    DB_PASS   = os.environ.get('DB_PASS', '')
    DB_HOST   = os.environ.get('DB_HOST', 'localhost')
    DB_ROOT_URI = 'mysql+pymysql://root:pass@localhost/'
    DB_ROOT_PASS = 'pass'
    # config.py
    AFRICASTALKING_USERNAME = 'your_africastalking_username'
    AFRICASTALKING_API_KEY = 'your_africastalking_api_key'
    SMS_SENDER_ID = 'ASTROCARE'  # 11 characters max
    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    if not JWT_SECRET_KEY:
         raise ValueError("No JWT_SECRET_KEY set for Flask-JWT-Extended.")
    JWT_TOKEN_LOCATION = ["headers", "cookies"] # Configure where JWTs are expected
    # JWT_COOKIE_SECURE = True # Use True in production with HTTPS

    # Mail Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    
    # Handle MAIL_PORT conversion safely
    try:
        MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    except ValueError:
        MAIL_PORT = 587  # Default to 587 if conversion fails
    
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', '').lower() in ('true', '1', 'yes')
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', '').lower() in ('true', '1', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@example.com')
    
    # Handle ADMINS as a list
    admins = os.environ.get('ADMINS', '')
    ADMINS = [email.strip() for email in admins.split(',') if email.strip()]
    

    # Allowed file extensions for uploads
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx'}  # Add/remove as needed

    WHO_CLIENT_ID = os.environ.get('WHO_CLIENT_ID')
    WHO_CLIENT_SECRET = os.environ.get('WHO_CLIENT_SECRET')
    # Particle Health API credentials
    PARTICLE_CLIENT_ID = 'c5796493-83d1-460b-a2e7-4031371ceb27'
    PARTICLE_CLIENT_SECRET = '32d7b1e9f9839b791153c8b430170d17e0d332304fdbe69851d448b4d4b24288156ef111d96fb34154f6863d21c8862fca0fb9879ab83f28eb755483a89c6344'
    # M-Pesa Configuration
    MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY')
    MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET')
    MPESA_BUSINESS_SHORTCODE = os.environ.get('MPESA_BUSINESS_SHORTCODE')
    MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY')
    MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL')

    # Validate M-Pesa configuration
    if not all([MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, 
                MPESA_BUSINESS_SHORTCODE, MPESA_PASSKEY]):
        raise ValueError("Missing M-Pesa configuration in environment variables")

    LOINC_USERNAME = os.environ.get('LOINC_USERNAME', 'pinchokenya')
    LOINC_PASSWORD = os.environ.get('LOINC_PASSWORD', 'j17/MNU/7403/2020')

    # DHA HIE Configuration
    DHA_BASE_URL = os.environ.get('DHA_BASE_URL', 'https://uat.dha.go.ke')
    AGENT_ID = os.environ.get('AGENT_ID')
    BASIC_AUTH_USERNAME = os.environ.get('BASIC_AUTH_USERNAME')
    BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD')
    TOKEN_AUTH_KEY = os.environ.get('TOKEN_AUTH_KEY')
    TOKEN_AUTH_SECRET = os.environ.get('TOKEN_AUTH_SECRET')
    
    # Load keys with proper newline formatting
    PRIVATE_KEY = os.environ.get('PRIVATE_KEY', '').replace('\\n', '\n')
    PUBLIC_KEY = os.environ.get('PUBLIC_KEY', '').replace('\\n', '\n')
    # Celery Configuration
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND')
    if not CELERY_BROKER_URL:
         raise ValueError("No CELERY_BROKER_URL set.")
    if not CELERY_RESULT_BACKEND:
         raise ValueError("No CELERY_RESULT_BACKEND set.")

    # Application Specific Config
    ITEMS_PER_PAGE = 10


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True # Log database queries in development
    # MAIL_SERVER, MAIL_PORT, etc. likely from .env or set specifically here for dev

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory database for tests
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False # Disable CSRF for testing (if using Flask-WTF later)
    JWT_SECRET_KEY = 'testing-jwt-secret' # Use a different key for tests
    SECRET_KEY = 'testing-secret-key' # Use a different key for tests
    # Add testing specific mail/celery config if needed (e.g., celery to use sync mode)

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    # Logging to email or external service like Sentry/Loguru
    # Ensure MAIL_SERVER, MAIL_PORT etc. are set via environment variables
    # Or configure external logging service directly


# Dictionary to easily get config class by name
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig # Default if FLASK_CONFIG env var is not set
}