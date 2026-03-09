from datetime import date, datetime, timedelta

from flask import current_app
from app.extensions import db


class PharmacyInventory(db.Model):
    __tablename__ = 'pharmacy_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Tablet, Syrup, Injection, etc.
    quantity = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(20), default='piece')     # e.g., piece, bottle, box
    dosage_form = db.Column(db.String(50))
    strength = db.Column(db.String(50))
    expiry_date = db.Column(db.Date)
    supplier = db.Column(db.String(100))

    # New fields for pricing and inventory management
    buying_price = db.Column(db.Float, nullable=False, default=0.0)          # Cost price per unit
    selling_price = db.Column(db.Float, nullable=True)                       # Can be overridden; if NULL, uses linked service price
    reorder_level = db.Column(db.Integer, default=10)                        # Minimum stock before reorder
    low_stock_threshold = db.Column(db.Integer, default=5)                   # Alert when stock <= this
    manufacturer = db.Column(db.String(100))
    batch_number = db.Column(db.String(50))
    location = db.Column(db.String(100))                                      # Shelf/rack location
    requires_prescription = db.Column(db.Boolean, default=True)

    # Link to Service table (optional)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    service = db.relationship('Service', backref='pharmacy_items')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<PharmacyInventory {self.item_name} (qty: {self.quantity})>'

    @property
    def current_value(self):
        """Total cost value of current stock"""
        return self.quantity * self.buying_price

    @property
    def potential_revenue(self):
        """Total revenue if sold at selling price (or linked service price)"""
        price = self.selling_price or (self.service.price if self.service else 0)
        return self.quantity * price
    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    @property
    def is_expired(self):
        days = self.days_to_expiry
        return days is not None and days < 0

    @property
    def is_expiring_soon(self, days_threshold=30):
        days = self.days_to_expiry
        return days is not None and 0 <= days <= days_threshold

    @property
    def is_low_stock(self):
        if self.low_stock_threshold is None:
            return False
        return self.quantity <= self.low_stock_threshold

    @property
    def total_value(self):
        return (self.quantity or 0) * (self.selling_price or 0)
    
    
    @property
    def valuation_at_cost(self):
        """Total cost value (buying price × quantity)"""
        return (self.quantity or 0) * (self.buying_price or 0)

    @property
    def valuation_at_selling_price(self):
        """Total potential revenue (selling price × quantity)"""
        return (self.quantity or 0) * (self.selling_price or 0)