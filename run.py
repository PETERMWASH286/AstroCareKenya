
import os

# Import both create_app and make_celery from the app package
from app import create_app
from app.commands import register_commands
from app import create_app, socketio

# Determine config name based on environment variable
config_name = os.environ.get('FLASK_CONFIG', 'development')

# Create the Flask application instance using the factory
app = create_app(config_name)
# IMPORTANT: Configure Celery *after* creating the app instance
# This binds the app's configuration to the celery_app instance
# This is for running with 'python run.py' during development
# In production, a WSGI server (like Gunicorn) will use wsgi.py
if __name__ == '__main__':
    app.run(host="127.0.0.1", port=5000, debug=True)