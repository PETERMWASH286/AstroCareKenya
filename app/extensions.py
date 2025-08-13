# This file initializes Flask extensions without binding them to a specific app instance.
# This supports the application factory pattern.

import time
from flask import current_app, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_bcrypt import Bcrypt
from flask_marshmallow import Marshmallow
# ADDED: Import LoginManager
from flask_login import LoginManager
from sqlalchemy import create_engine

from flask import request

from sqlalchemy.engine.url import make_url

from flask import g, request
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import scoped_session, sessionmaker
import threading

# Tenant registry cache
tenant_registry = {}
registry_lock = threading.Lock()

db = SQLAlchemy()

def get_tenant_engine(subdomain):
    """Get or create engine for tenant subdomain"""
    with registry_lock:
        if subdomain in tenant_registry:
            engine, timestamp = tenant_registry[subdomain]
            # Check if cache expired
            if time.time() - timestamp < current_app.config['TENANT_CACHE_TIMEOUT']:
                return engine
        
        # Not in cache or expired - fetch from central DB
        from app.super_admin.models import Hospital
        hospital = Hospital.query.filter_by(subdomain=subdomain).first()
        
        if not hospital:
            return None
        
        engine = create_engine(hospital.db_uri)
        tenant_registry[subdomain] = (engine, time.time())
        return engine

def clear_tenant_registry():
    """Clear the tenant engine cache"""
    with registry_lock:
        tenant_registry.clear()
        
from flask_socketio import SocketIO

# Initialize SocketIO
socketio = SocketIO(async_mode='threading')
migrate = Migrate()

# Authentication
jwt = JWTManager()
bcrypt = Bcrypt()
# UNCOMMENTED: Initialize LoginManager
login_manager = LoginManager()
# UNCOMMENTED: Configure the login view
login_manager.login_view = 'auth_web.login' # The endpoint name for your login route

# Messaging and Background Tasks
mail = Mail()

# Data Serialization/Validation
ma = Marshmallow()

# Example: Initialize other extensions
# cache = Cache()
