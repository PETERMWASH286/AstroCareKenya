from datetime import date, datetime, timedelta

from flask import current_app
from app.extensions import db


class RadiologyInventory(db.Model):
    __tablename__ = 'radiology_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Films, Contrast Agents, Equipment
    quantity = db.Column(db.Integer, default=0)
    expiry_date = db.Column(db.Date)
    supplier = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
