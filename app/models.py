
from app.extensions import db, bcrypt # Import db and bcrypt from extensions
from datetime import datetime
# ADDED: Import UserMixin from Flask-Login
from flask_login import UserMixin
# from flask_jwt_extended import get_jwt_identity # Useful for user loader (if needed for JWT)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs' # Changed to lowercase 'user' for consistency

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=True)  # Adjust type if using UUID
    username = db.Column(db.String(128), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)  # Supports IPv6
    action = db.Column(db.String(10))  # CREATE/UPDATE/DELETE
    model_name = db.Column(db.String(64))
    record_id = db.Column(db.String(64))  # String to handle non-integer PKs
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.JSON)  # Stores changes, old/new values

    __audit_trail__ = False  # Exclude this model from auditing




