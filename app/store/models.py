import uuid
from flask import current_app
from app.extensions import db
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import UUID

class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey('external_orders.id'), nullable=True)  # Allow NULL for direct orders
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    item_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(50), default='pcs')
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='Ksh')
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='ordered')  # ordered, shipped, delivered, canceled
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    notes = db.Column(db.Text)
    
    # Relationships
    requisition = db.relationship('ExternalOrder', backref=db.backref('purchase_orders', lazy=True))
    creator = db.relationship('User', backref='created_purchase_orders')
    
    def __repr__(self):
        return f'<PurchaseOrder {self.id}>'
    
class Supplier(db.Model):
    __tablename__ = 'suppliers'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    contact = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text)
    category = db.Column(db.String(50), nullable=False)
    payment_terms = db.Column(db.String(50))
    lead_time = db.Column(db.Integer)
    rating = db.Column(db.Integer, default=3)
    is_active = db.Column(db.Boolean, default=True)
    last_order_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = db.relationship('PurchaseOrder', backref='supplier', lazy=True)

    def __repr__(self):
        return f'<Supplier {self.name}>'

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "contact": self.contact,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "category": self.category,
            "payment_terms": self.payment_terms,
            "lead_time": self.lead_time,
            "rating": self.rating,
            "is_active": self.is_active,
            "last_order_date": self.last_order_date.isoformat() if self.last_order_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Stock Model
class Stock(db.Model):
    __tablename__ = 'stock'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    batch_number = db.Column(db.String(50), nullable=False)
    expiration_date = db.Column(db.DateTime)
    reorder_level = db.Column(db.Integer, default=50)
    current_stock = db.Column(db.Integer)
    location = db.Column(db.String(100))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_restocked = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    supplier = db.relationship('Supplier', backref='stock_items')
    purchase_order = db.relationship('PurchaseOrder', backref='stock_entries')
    # One-to-one relationship with StockDetail
    detail = db.relationship('StockDetail', back_populates='stock', uselist=False)
    def __repr__(self):
        return f'<Stock {self.sku} - {self.name}>'
    
    def generate_sku(self):
        """Generate SKU with null safety"""
        try:
            # Get category components with fallbacks
            item_category = str(self.category[:3]).upper() if self.category else "GEN"
            supplier_category = str(self.supplier.category[:3]).upper() if self.supplier and self.supplier.category else "SUP"
            batch = str(self.batch_number).split('-')[-1] if self.batch_number else "000"
            
            return f"{item_category}-{supplier_category}-{batch}"
        except Exception as e:
            current_app.logger.error(f"SKU Generation Error: {str(e)}")
            return f"ERR-{uuid.uuid4().hex[:6].upper()}"

    def calculate_expiration(self):
        """Safer expiration date calculation"""
        try:
            base_date = self.created_at or datetime.utcnow()
            if self.category and self.category.lower() in ['pharmaceuticals', 'drugs']:
                return base_date + timedelta(days=730)
            return base_date + timedelta(days=1825)
        except Exception as e:
            current_app.logger.error(f"Expiration Calculation Error: {str(e)}")
            return datetime.utcnow() + timedelta(days=1825)



class StockRequest(db.Model):
    __tablename__ = 'stock_requests'
    __audit_trail__ = True  # Enable auditing
   
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Requester Information
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    department = db.Column(db.String(100), nullable=False)  # e.g., "Pharmacy", "Surgery"
    required_by_date = db.Column(db.DateTime, nullable=True)
    
    # Stock Item Details
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    batch_number = db.Column(db.String(50), nullable=False)
    expiration_date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    
    # Quantities
    quantity_requested = db.Column(db.Integer, nullable=False)
    quantity_approved = db.Column(db.Integer)
    quantity_issued = db.Column(db.Integer, default=0)
    
    # Status Tracking
    status = db.Column(db.Enum(
        'draft', 
        'submitted', 
        'approved', 
        'rejected', 
        'processing', 
        'partially_issued', 
        'fulfilled', 
        'cancelled',
        name='request_status'
    ), default='draft', nullable=False)
    
    # Priority System
    priority = db.Column(db.Enum(
        'routine', 
        'urgent', 
        'emergency',
        name='request_priority'
    ), default='routine', nullable=False)
    
    # Approval Process
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    approval_date = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)
    
    # Issuance Details
    issue_date = db.Column(db.DateTime)
    issued_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    issue_reference = db.Column(db.String(50))
    
    # Relationships
    stock = db.relationship('Stock', backref='requests')
    # Update relationships with back_populates
    requester = db.relationship(
        'User', 
        foreign_keys=[requester_id], 
        back_populates='requested_stock'
    )
    approver = db.relationship(
        'User', 
        foreign_keys=[approver_id], 
        back_populates='approved_stock'
    )
    issuer = db.relationship(
        'User', 
        foreign_keys=[issued_by], 
        back_populates='issued_stock'
    )
    
    # Indexes
    __table_args__ = (
        db.Index('ix_stock_request_status', 'stock_id', 'status'),
        db.Index('ix_request_department', 'department', 'status'),
        db.Index('ix_batch_expiration', 'batch_number', 'expiration_date'),
    )

    def __repr__(self):
        return f'<StockRequest {self.stock.sku} - {self.quantity_requested} units>'

    def to_dict(self):
        return {
            'id': str(self.id),
            'stock_item': self.stock.name,
            'sku': self.stock.sku,
            'batch': self.batch_number,
            'expiration': self.expiration_date.isoformat(),
            'department': self.department,
            'requested': self.quantity_requested,
            'issued': self.quantity_issued,
            'status': self.status,
            'priority': self.priority,
            'location': self.location,
            'requester': self.requester.full_name,
            'age': (datetime.utcnow() - self.created_at).days
        }

    def validate_stock_availability(self):
        """Check if requested stock is available, considering existing requests"""
        # Get available stock (current stock minus pending requests)
        pending_requests = sum(
            req.quantity_requested 
            for req in self.stock.requests 
            if req.status in ['submitted', 'approved'] and req.id != self.id
        )
        
        available = self.stock.current_stock - pending_requests
        return available >= self.quantity_requested


    def generate_issue_reference(self):
        """Generate issuance reference number"""
        prefix = self.department[:3].upper()
        date_str = datetime.utcnow().strftime("%y%m%d")
        return f"{prefix}-ISSUE-{date_str}-{self.id.hex[:6].upper()}"

    def update_stock_levels(self):
        """Update stock quantities after issuance"""
        if self.status == 'fulfilled':
            self.stock.current_stock -= self.quantity_issued
            db.session.commit()



# Add this new model for stock flow tracking
class StockFlow(db.Model):
    __tablename__ = 'stock_flows'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'))
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'))
    quantity_change = db.Column(db.Integer)
    flow_type = db.Column(db.String(50))  # approval, transfer, adjustment
    reference_id = db.Column(
        db.String(36),
        db.ForeignKey('stock_requests.id'),
        nullable=True
    )
    notes = db.Column(db.Text)

    stock = db.relationship('Stock', backref='flows')
    service = db.relationship('Service', backref='flows')
    request = db.relationship('StockRequest', backref='flows')


class ExternalOrder(db.Model):
    __tablename__ = 'external_orders'
    __audit_trail__ = True  # Enable auditing if needed
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Item details
    item_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(50), default='pcs')
    unit_price = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, nullable=False)
    
    # Supplier details
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    contact_person = db.Column(db.String(120))  # From supplier auto-fill
    contact_info = db.Column(db.String(255))    # From supplier auto-fill
    
    # Order metadata
    priority = db.Column(db.String(20), nullable=False, default='medium')
    delivery_date = db.Column(db.DateTime, nullable=False)
    
    # Categorization
    category = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    budget_code = db.Column(db.String(50))
    
    # Timing information
    required_by = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional information
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected/completed
    
    # User information
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    supplier = db.relationship('Supplier', backref='external_orders')
    user = db.relationship('User', backref='external_orders')
    
    def __repr__(self):
        return f'<ExternalOrder {self.item_name} x {self.quantity}>'
    
    def to_dict(self):
        return {
            "id": self.id,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "tax_rate": self.tax_rate,
            "total_price": self.total_price,
            "supplier_id": self.supplier_id,
            "contact_person": self.contact_person,
            "contact_info": self.contact_info,
            "priority": self.priority,
            "delivery_date": self.delivery_date.isoformat() if self.delivery_date else None,
            "category": self.category,
            "department": self.department,
            "budget_code": self.budget_code,
            "required_by": self.required_by.isoformat() if self.required_by else None,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "user_id": self.user_id
        }
    
class StockDetail(db.Model):
    __tablename__ = 'stock_details'
    __audit_trail__ = True  # Enable auditing
    
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    condition = db.Column(db.String(50), nullable=False, default='good')
    storage_temp = db.Column(db.String(50))
    certification = db.Column(db.String(100))
    inspector = db.Column(db.String(100))
    delivery_notes = db.Column(db.Text)
    serial_numbers = db.Column(db.Text)
    attachments = db.Column(db.Text)  # Store file paths
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to Stock (no backref here)
    stock = db.relationship('Stock', back_populates='detail')
    
    def __repr__(self):
        return f'<StockDetail {self.id} for Stock {self.stock_id}>'