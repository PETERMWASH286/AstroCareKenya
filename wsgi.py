import os
# Import both create_app and make_celery from the app package
from app import create_app
from app.commands import register_commands

# Production entrypoint using FLASK_CONFIG env var
config_name = os.environ.get('FLASK_CONFIG', 'production')
app = create_app(config_name)

# IMPORTANT: Configure Celery *after* creating the app instance
# This binds the app's configuration to the celery_app instance

# Used by WSGI servers like Gunicorn
if __name__ == '__main__':
    # The app object is what Gunicorn/uWSGI will serve
    # No need to call app.run() here
    pass