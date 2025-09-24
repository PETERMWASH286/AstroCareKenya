
from app.extensions import db, bcrypt # Import db and bcrypt from extensions
from datetime import datetime
# ADDED: Import UserMixin from Flask-Login
from flask_login import UserMixin
# from flask_jwt_extended import get_jwt_identity # Useful for user loader (if needed for JWT)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(128), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    patient_name = db.Column(db.String(255), nullable=True)
    method = db.Column(db.String(10), nullable=True)
    endpoint = db.Column(db.String(255), nullable=True)

    action = db.Column(db.String(20))   # expanded length: CREATE/UPDATE/DELETE/LOGIN/LOGOUT/etc
    model_name = db.Column(db.String(64))
    record_id = db.Column(db.String(128))

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.JSON)

    # NEW:
    success = db.Column(db.Boolean, nullable=True)          # NULL = not applicable, True/False for e.g. LOGIN
    message = db.Column(db.String(1024), nullable=True)     # human readable interpretation

    __audit_trail__ = False
    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))

    def __repr__(self):
        return f"<AuditLog {self.id} - {self.action} on {self.model_name} by User {self.user_id}>"




