import os
import sys

# Add the current directory to sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Set Flask configuration environment variable
os.environ['FLASK_CONFIG'] = 'production'

# Import your app factory
from app import create_app

# Create the WSGI application
application = create_app('production')
