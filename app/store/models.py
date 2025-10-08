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
    
    # 🔗 Link to LPO
    lpo_id = db.Column(db.Integer, db.ForeignKey('lpos.id'), nullable=True)
    lpo_number = db.Column(db.String(50), nullable=True)  # Store LPO number for quick reference
    
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
    lpo = db.relationship('LPO', backref=db.backref('purchase_orders', lazy=True))  # Relationship to LPO
    
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
        """Generate unique SKU with null safety"""
        try:
            # Get category components with fallbacks
            item_category = str(self.category[:3]).upper() if self.category else "GEN"
            supplier_category = str(self.supplier.category[:3]).upper() if self.supplier and self.supplier.category else "SUP"
            
            # Use more unique components
            timestamp = datetime.utcnow().strftime("%H%M%S")
            po_id = str(self.purchase_order_id) if self.purchase_order_id else "000"
            batch_part = str(self.batch_number).split('-')[-1][-4:] if self.batch_number else timestamp[-4:]
            
            # Create more unique SKU
            sku = f"{item_category}-{supplier_category}-{po_id}-{batch_part}"
            
            # Check if SKU already exists and make it unique if needed
            counter = 1
            original_sku = sku
            while Stock.query.filter_by(sku=sku).first() is not None:
                sku = f"{original_sku}-{counter}"
                counter += 1
                if counter > 100:  # Safety limit
                    sku = f"{original_sku}-{uuid.uuid4().hex[:4].upper()}"
                    break
            
            return sku
        except Exception as e:
            current_app.logger.error(f"SKU Generation Error: {str(e)}")
            return f"ERR-{uuid.uuid4().hex[:8].upper()}"

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

    # ✅ Collection Details (NEW)
    collected_by = db.Column(db.String(150), nullable=True)  # Full name of person collecting
    collected_at = db.Column(db.DateTime, nullable=True)     # Date/time of collection
    collection_notes = db.Column(db.Text)

    # Relationships
    stock = db.relationship('Stock', backref='requests')
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
            'age': (datetime.utcnow() - self.created_at).days,
            # ✅ Include collection info
            'collected_by': self.collected_by,
            'collected_at': self.collected_at.isoformat() if self.collected_at else None,
            # ✅ Include issuance info
            'issued_by': self.issuer.full_name if self.issuer else None,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'issue_reference': self.issue_reference
        }

    def validate_stock_availability(self):
        """Check if requested stock is available, considering existing requests"""
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
        return f"{prefix}-ISSUE-{date_str}-{self.id[:8].upper()}"

    def update_stock_levels(self):
        """Update stock quantities after issuance"""
        if self.status == 'fulfilled':
            self.stock.current_stock -= self.quantity_issued
            db.session.commit()
            
            
            
class ItemPurchaseRequest(db.Model):
    __tablename__ = 'item_purchase_requests'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Item Information
    item_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    manufacturer = db.Column(db.String(100))
    specifications = db.Column(db.Text)
    
    # Quantity & Requirements
    quantity = db.Column(db.Integer, nullable=False)
    units = db.Column(db.String(50), nullable=False)
    estimated_price = db.Column(db.Float)
    required_date = db.Column(db.Date, nullable=False)
    priority = db.Column(db.String(20), nullable=False)  # low, medium, high, critical
    
    # Business Justification
    reason = db.Column(db.Text, nullable=False)
    alternatives = db.Column(db.Text)
    urgency_reason = db.Column(db.Text)
    
    # Request Details
    department = db.Column(db.String(50), nullable=False, default='lab')
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='submitted')  # submitted, approved, rejected, ordered, received
    
    # Approval Process
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    approval_date = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)
    
    # Order Details (if approved)
    purchase_order_id = db.Column(db.String(50))
    ordered_date = db.Column(db.DateTime)
    expected_delivery = db.Column(db.Date)
    
    # Relationships
    requester = db.relationship('User', foreign_keys=[requester_id], backref='purchase_requests')
    approver = db.relationship('User', foreign_keys=[approver_id], backref='approved_purchases')
    
    def __repr__(self):
        return f'<ItemPurchaseRequest {self.item_name} - {self.quantity} {self.units}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'item_name': self.item_name,
            'category': self.category,
            'quantity': self.quantity,
            'units': self.units,
            'priority': self.priority,
            'status': self.status,
            'required_date': self.required_date.isoformat() if self.required_date else None,
            'created_at': self.created_at.isoformat(),
            'requester': self.requester.full_name if self.requester else 'Unknown'
        }

# Add this new model for stock flow tracking
class StockFlow(db.Model):
    __tablename__ = 'stock_flows'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'))
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)  # now nullable
    entry_id = db.Column(db.Integer, nullable=True)  # will store ID from lab/pharmacy/hr/radiology inventory
    location = db.Column(db.String(255), nullable=True)  # department location (Lab, Pharmacy, HR, Radiology)

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
    __audit_trail__ = True
    
    id = db.Column(db.Integer, primary_key=True)

    # --- existing fields ---
    item_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(50), default='pcs')
    unit_price = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, nullable=False)

    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    contact_person = db.Column(db.String(120), nullable=True)
    contact_info = db.Column(db.String(255), nullable=True)

    priority = db.Column(db.String(20), nullable=False, default='medium')
    delivery_date = db.Column(db.DateTime, nullable=True)

    category = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=True)
    budget_code = db.Column(db.String(50), nullable=True)

    required_by = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reason = db.Column(db.Text, nullable=False)

    # 👇 Change: instead of one status, track approvals separately
    finance_approved = db.Column(db.Boolean, default=False)
    finance_approved_at = db.Column(db.DateTime, nullable=True)
    finance_approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    director_approved = db.Column(db.Boolean, default=False)
    director_approved_at = db.Column(db.DateTime, nullable=True)
    director_approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    rejected_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    # Final status (depends on both approvals)
    status = db.Column(db.String(20), default='pending')  
    # pending / finance_approved / director_approved / rejected / completed

    # User who created requisition
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Relationships
    supplier = db.relationship('Supplier', backref='external_orders')
    user = db.relationship('User', foreign_keys=[user_id], backref='external_orders')
    finance_user = db.relationship('User', foreign_keys=[finance_approved_by], backref='finance_orders')
    director_user = db.relationship('User', foreign_keys=[director_approved_by], backref='director_orders')

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
    
class LPO(db.Model):
    __tablename__ = "lpos"
    __audit_trail__ = True  # keep consistent with your style

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lpo_number = db.Column(db.String(50), unique=True, nullable=True)  # set after insert

    # 🔗 Link to external orders
    external_order_id = db.Column(db.Integer, db.ForeignKey("external_orders.id"), nullable=False)
    external_order = db.relationship("ExternalOrder", backref="lpos")

    # Order details (can mirror external order, but kept here for LPO copy)
    item_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    unit = db.Column(db.String(50))
    quantity = db.Column(db.Integer, nullable=False, default=0)
    unit_price = db.Column(db.Float, nullable=True)
    tax_rate = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float)

    delivery_date = db.Column(db.DateTime, nullable=True)

    # Status
    status = db.Column(db.String(50), default="pending")  # pending / approved / rejected / completed

    # Supplier link
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=True)
    supplier = db.relationship("Supplier", backref="lpos")
    contact_person = db.Column(db.String(120))
    contact_info = db.Column(db.String(255))

    # Approvals
    finance_approved = db.Column(db.Boolean, default=False)
    finance_approved_at = db.Column(db.DateTime, nullable=True)
    finance_approved_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    finance_user = db.relationship("User", foreign_keys=[finance_approved_by], backref="finance_lpos")

    director_approved = db.Column(db.Boolean, default=False)
    director_approved_at = db.Column(db.DateTime, nullable=True)
    director_approved_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    director_user = db.relationship("User", foreign_keys=[director_approved_by], backref="director_lpos")

    # Meta
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", foreign_keys=[created_by], backref="created_lpos")

    def __repr__(self):
        return f"<LPO {self.lpo_number or 'Unassigned'} for Order {self.external_order_id}>"

    def to_dict(self):
        return {
            "id": self.id,
            "lpo_number": self.lpo_number,
            "external_order_id": self.external_order_id,
            "item_name": self.item_name,
            "category": self.category,
            "unit": self.unit,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "tax_rate": self.tax_rate,
            "total_price": self.total_price,
            "status": self.status,
            "supplier_id": self.supplier_id,
            "contact_person": self.contact_person,
            "contact_info": self.contact_info,
            "finance_approved": self.finance_approved,
            "finance_approved_at": self.finance_approved_at.isoformat() if self.finance_approved_at else None,
            "director_approved": self.director_approved,
            "director_approved_at": self.director_approved_at.isoformat() if self.director_approved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by
        }

    def generate_lpo_number(self):
        """Generate LPO number after record has an ID"""
        if not self.lpo_number and self.id:
            self.lpo_number = f"LPO-{self.id}"
            db.session.commit()  # update in DB
    

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
    


class SupplierInvoice(db.Model):
    __tablename__ = 'supplier_invoices'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_account_id = db.Column(db.Integer, db.ForeignKey('supplier_accounts.id'), nullable=False)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    
    # Invoice Details
    invoice_date = db.Column(db.DateTime, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    delivery_date = db.Column(db.DateTime, nullable=False)
    
    # Financial Details
    subtotal_amount = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, default=0.0)
    balance_due = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='KSh')
    
    # Invoice Status
    status = db.Column(db.Enum(
        'draft', 'issued', 'pending', 'partially_paid', 
        'paid', 'overdue', 'cancelled', 'disputed',
        name='invoice_status'
    ), default='draft')
    
    # Payment Information
    payment_terms = db.Column(db.String(50), default='Net 30')
    payment_method = db.Column(db.Enum(
        'bank_transfer', 'cheque', 'mobile_money', 'cash', 'credit',
        name='invoice_payment_method'
    ))
    payment_reference = db.Column(db.String(100))
    payment_date = db.Column(db.DateTime)
    
    # Delivery & Items
    delivery_notes = db.Column(db.Text)
    items_delivered = db.Column(db.JSON)  # Store delivered items as JSON
    
    # Approval Workflow
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    verified_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)
    
    # Dispute Resolution
    dispute_reason = db.Column(db.Text)
    dispute_resolved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    dispute_resolved_at = db.Column(db.DateTime)
    
    # Document Management
    invoice_file_path = db.Column(db.String(255))
    delivery_note_path = db.Column(db.String(255))
    payment_proof_path = db.Column(db.String(255))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    purchase_order = db.relationship('PurchaseOrder', backref='supplier_invoices')
    verifier = db.relationship('User', foreign_keys=[verified_by], backref='verified_supplier_invoices')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_supplier_invoices')
    dispute_resolver = db.relationship('User', foreign_keys=[dispute_resolved_by], backref='resolved_supplier_invoices')

    def __repr__(self):
        return f'<SupplierInvoice {self.invoice_number} - {self.total_amount:,.2f}>'

    def generate_invoice_number(self):
        """Generate unique invoice number"""
        if not self.invoice_number:
            prefix = "INV"
            
            # Safely get supplier code
            supplier_code = "UNK"  # Default if account number not available
            if self.supplier_account and self.supplier_account.account_number:
                try:
                    supplier_code = self.supplier_account.account_number.split('-')[1]
                except (AttributeError, IndexError):
                    supplier_code = "UNK"
            
            year_month = datetime.utcnow().strftime("%y%m")
            
            # If we don't have an ID yet, use a temporary number
            if not self.id:
                timestamp = datetime.utcnow().strftime("%H%M%S")
                self.invoice_number = f"{prefix}-{supplier_code}-{year_month}-TEMP-{timestamp}"
            else:
                self.invoice_number = f"{prefix}-{supplier_code}-{year_month}-{self.id:04d}"
    
    def calculate_due_date(self):
        """Calculate due date based on payment terms"""
        if not self.due_date and self.invoice_date:
            terms = self.payment_terms.lower() if self.payment_terms else 'net 30'
            if 'net 30' in terms:
                self.due_date = self.invoice_date + timedelta(days=30)
            elif 'net 15' in terms:
                self.due_date = self.invoice_date + timedelta(days=15)
            elif 'net 45' in terms:
                self.due_date = self.invoice_date + timedelta(days=45)
            elif 'net 60' in terms:
                self.due_date = self.invoice_date + timedelta(days=60)
            else:
                self.due_date = self.invoice_date + timedelta(days=30)  # Default
        elif not self.due_date:
            # If no invoice date, set due date to 30 days from now
            self.due_date = datetime.utcnow() + timedelta(days=30)
    
    def update_balance(self):
        """Update balance due"""
        self.balance_due = self.total_amount - self.amount_paid
        
        # Update status based on balance
        if self.balance_due <= 0:
            self.status = 'paid'
            self.payment_date = datetime.utcnow()
        elif self.amount_paid > 0:
            self.status = 'partially_paid'
        elif self.due_date and datetime.utcnow() > self.due_date:
            self.status = 'overdue'
        else:
            self.status = 'pending'
    
    def add_payment(self, amount, payment_method, reference=None):
        """Record a payment against this invoice with enhanced validation"""
        try:
            if amount <= 0:
                raise ValueError("Payment amount must be positive")
            
            if amount > self.balance_due:
                raise ValueError(f"Payment amount {amount:.2f} exceeds balance due {self.balance_due:.2f}")
            
            # Store previous values for rollback
            previous_amount_paid = self.amount_paid
            previous_balance = self.supplier_account.current_balance
            
            try:
                # Update invoice
                self.amount_paid += amount
                self.payment_method = payment_method
                self.payment_reference = reference
                self.update_balance()
                
                # Create transaction record
                transaction = SupplierTransaction(
                    supplier_account_id=self.supplier_account_id,
                    invoice_id=self.id,
                    transaction_type='payment',
                    amount=amount,
                    balance_after=self.supplier_account.current_balance - amount,
                    description=f"Payment for invoice {self.invoice_number}",
                    reference=reference,
                    payment_method=payment_method
                )
                
                # Update supplier account balance
                self.supplier_account.current_balance -= amount
                self.supplier_account.last_payment_date = datetime.utcnow()
                
                db.session.add(transaction)
                
            except Exception as e:
                # Rollback invoice changes on error
                self.amount_paid = previous_amount_paid
                self.supplier_account.current_balance = previous_balance
                raise e
                
        except Exception as e:
            raise ValueError(f"Payment processing failed: {str(e)}")
    
    def verify_invoice(self, user_id):
        """Verify invoice against purchase order"""
        if not self.verified_by:
            self.verified_by = user_id
            self.verified_at = datetime.utcnow()
            
            # Compare with purchase order
            po = self.purchase_order
            discrepancies = []
            
            if self.total_amount != po.total_price:
                discrepancies.append(f"Amount mismatch: PO {po.total_price} vs Invoice {self.total_amount}")
            
            # You can add more verification logic here
            
            return len(discrepancies) == 0, discrepancies
        return True, []
    
    def to_dict(self):
        """Convert invoice to dictionary"""
        return {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'supplier_name': self.supplier_account.supplier.name,
            'purchase_order_number': self.purchase_order.lpo_number,
            'invoice_date': self.invoice_date.isoformat(),
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'subtotal_amount': self.subtotal_amount,
            'tax_amount': self.tax_amount,
            'discount_amount': self.discount_amount,
            'total_amount': self.total_amount,
            'amount_paid': self.amount_paid,
            'balance_due': self.balance_due,
            'status': self.status,
            'payment_terms': self.payment_terms,
            'days_overdue': (datetime.utcnow() - self.due_date).days if self.due_date and datetime.utcnow() > self.due_date else 0,
            'items_delivered': self.items_delivered or []
        }
    
class SupplierAccount(db.Model):
    __tablename__ = 'supplier_accounts'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    
    # Account Status & Type
    account_type = db.Column(db.Enum(
        'regular', 'preferred', 'strategic', 'new', 
        name='supplier_account_type'
    ), default='regular')
    status = db.Column(db.Enum(
        'active', 'suspended', 'closed', 'under_review',
        name='supplier_account_status'
    ), default='active')
    credit_limit = db.Column(db.Float, default=0.0)
    current_balance = db.Column(db.Float, default=0.0)
    credit_rating = db.Column(db.Enum(
        'A+', 'A', 'B+', 'B', 'C', 'D',
        name='supplier_credit_rating'
    ), default='B')
    
    # Payment Information
    payment_terms = db.Column(db.String(50), default='Net 30')
    preferred_payment_method = db.Column(db.Enum(
        'bank_transfer', 'cheque', 'mobile_money', 'cash',
        name='payment_method'
    ), default='bank_transfer')
    bank_name = db.Column(db.String(100))
    bank_account_number = db.Column(db.String(50))
    bank_branch = db.Column(db.String(100))
    swift_code = db.Column(db.String(20))
    
    # Performance Metrics
    total_orders = db.Column(db.Integer, default=0)
    total_order_value = db.Column(db.Float, default=0.0)
    average_delivery_time = db.Column(db.Integer)  # in days
    on_time_delivery_rate = db.Column(db.Float)  # percentage
    quality_rating = db.Column(db.Float)  # 1-5 scale
    
    # Contract Details
    contract_start_date = db.Column(db.DateTime)
    contract_end_date = db.Column(db.DateTime)
    contract_value = db.Column(db.Float)
    contract_document_path = db.Column(db.String(255))
    
    # Communication Preferences
    send_payment_reminders = db.Column(db.Boolean, default=True)
    send_statement_emails = db.Column(db.Boolean, default=True)
    statement_frequency = db.Column(db.Enum(
        'weekly', 'monthly', 'quarterly', 'on_demand',
        name='statement_frequency'
    ), default='monthly')
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_payment_date = db.Column(db.DateTime)
    last_order_date = db.Column(db.DateTime)
    
    # Relationships
    supplier = db.relationship('Supplier', backref=db.backref('account', uselist=False))
    invoices = db.relationship('SupplierInvoice', backref='supplier_account', lazy=True)
    transactions = db.relationship('SupplierTransaction', backref='account', lazy=True)
    
    def __repr__(self):
        return f'<SupplierAccount {self.account_number} - {self.supplier.name}>'
    
    def generate_account_number(self):
        """Generate unique supplier account number"""
        if not self.account_number and self.id:  # Only generate if we have an ID
            prefix = "SUP"
            supplier_initials = ''.join([word[0].upper() for word in self.supplier.name.split()[:3]])
            timestamp = datetime.utcnow().strftime("%y%m")
            self.account_number = f"{prefix}-{supplier_initials}-{timestamp}-{self.id:04d}"
        elif not self.account_number:
            # Generate a temporary account number if no ID yet
            prefix = "SUP"
            supplier_initials = ''.join([word[0].upper() for word in self.supplier.name.split()[:3]])
            timestamp = datetime.utcnow().strftime("%y%m")
            random_suffix = str(uuid.uuid4())[:4].upper()
            self.account_number = f"{prefix}-{supplier_initials}-{timestamp}-TEMP-{random_suffix}"
    
    def update_performance_metrics(self):
        """Update supplier performance metrics based on order history"""
        orders = PurchaseOrder.query.filter_by(supplier_id=self.supplier_id).all()
        
        if orders:
            self.total_orders = len(orders)
            self.total_order_value = sum(order.total_price for order in orders)
            
            # Calculate delivery performance
            delivered_orders = [o for o in orders if o.status == 'delivered' and o.delivery_date]
            if delivered_orders:
                # Calculate average delivery time
                delivery_times = []
                for order in delivered_orders:
                    if order.order_date and order.delivery_date:
                        delivery_time = (order.delivery_date - order.order_date).days
                        delivery_times.append(delivery_time)
                
                if delivery_times:
                    self.average_delivery_time = sum(delivery_times) // len(delivery_times)
                
                # Calculate on-time delivery rate (assuming 7-day target)
                on_time_deliveries = sum(1 for time in delivery_times if time <= 7)
                self.on_time_delivery_rate = (on_time_deliveries / len(delivery_times)) * 100
            
            # Update credit rating based on performance
            self._update_credit_rating()
    
    def _update_credit_rating(self):
        """Update credit rating based on performance metrics"""
        if self.on_time_delivery_rate is None:
            return
        
        if self.on_time_delivery_rate >= 95:
            self.credit_rating = 'A+'
        elif self.on_time_delivery_rate >= 90:
            self.credit_rating = 'A'
        elif self.on_time_delivery_rate >= 85:
            self.credit_rating = 'B+'
        elif self.on_time_delivery_rate >= 80:
            self.credit_rating = 'B'
        elif self.on_time_delivery_rate >= 70:
            self.credit_rating = 'C'
        else:
            self.credit_rating = 'D'
    
    def can_place_order(self, order_amount):
        """Check if supplier can accept order based on credit limit"""
        if self.credit_limit == 0:  # No credit limit set
            return True
        return (self.current_balance + order_amount) <= self.credit_limit
    
    def get_account_summary(self):
        """Get comprehensive account summary"""
        pending_invoices = SupplierInvoice.query.filter_by(
            supplier_account_id=self.id,
            status='pending'
        ).all()

        overdue_invoices = SupplierInvoice.query.filter_by(
            supplier_account_id=self.id,
            status='overdue'
        ).all()
        
        return {
            'account_number': self.account_number,
            'supplier_name': self.supplier.name,
            'current_balance': self.current_balance,
            'credit_limit': self.credit_limit,
            'available_credit': self.credit_limit - self.current_balance,
            'pending_invoices': len(pending_invoices),
            'pending_amount': sum(inv.total_amount for inv in pending_invoices),
            'overdue_invoices': len(overdue_invoices),
            'overdue_amount': sum(inv.total_amount for inv in overdue_invoices),
            'performance_rating': self.quality_rating,
            'on_time_delivery': self.on_time_delivery_rate
        }
        
        
class SupplierTransaction(db.Model):
    __tablename__ = 'supplier_transactions'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    supplier_account_id = db.Column(db.Integer, db.ForeignKey('supplier_accounts.id'), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('supplier_invoices.id'), nullable=True)
    
    # Transaction Details
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    transaction_type = db.Column(db.Enum(
        'invoice', 'payment', 'credit_note', 'debit_note', 'adjustment',
        name='transaction_type'
    ), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    
    # Description & Reference
    description = db.Column(db.Text, nullable=False)
    reference = db.Column(db.String(100))
    payment_method = db.Column(db.Enum(
        'bank_transfer', 'cheque', 'mobile_money', 'cash', 'credit',
        name='transaction_payment_method'
    ))
    
    # Status
    status = db.Column(db.Enum(
        'pending', 'completed', 'failed', 'reversed',
        name='transaction_status'
    ), default='completed')
    
    # Reversal tracking
    reversed_transaction_id = db.Column(db.Integer, db.ForeignKey('supplier_transactions.id'), nullable=True)
    reversal_reason = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    invoice = db.relationship('SupplierInvoice', backref='transactions')
    reversed_transaction = db.relationship('SupplierTransaction', remote_side=[id], 
                                         backref=db.backref('reversal', uselist=False))
    
    def __repr__(self):
        return f'<SupplierTransaction {self.transaction_type} - {self.amount:,.2f}>'
    
    
    
class PaymentRequest(db.Model):
    __tablename__ = 'payment_requests'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('supplier_invoices.id'), nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Payment Details
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.Enum(
        'bank_transfer', 'cheque', 'mobile_money', 'cash',
        name='payment_method'
    ), nullable=False)
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    
    # Approval Workflow
    status = db.Column(db.Enum(
        'draft', 'submitted', 'finance_review', 'director_approval', 
        'approved', 'rejected', 'cancelled', 'paid',
        name='payment_request_status'
    ), default='draft')
    
    # Approval Tracking
    finance_reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    finance_reviewed_at = db.Column(db.DateTime)
    finance_notes = db.Column(db.Text)
    
    director_approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    director_approved_at = db.Column(db.DateTime)
    director_notes = db.Column(db.Text)
    
    # Payment Execution
    paid_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    paid_at = db.Column(db.DateTime)
    payment_proof_path = db.Column(db.String(255))
    
    # Timestamps
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    invoice = db.relationship('SupplierInvoice', backref='payment_requests')
    requester = db.relationship('User', foreign_keys=[requested_by], backref='requested_payments')
    finance_reviewer = db.relationship('User', foreign_keys=[finance_reviewed_by], backref='finance_reviewed_payments')
    director_approver = db.relationship('User', foreign_keys=[director_approved_by], backref='director_approved_payments')
    payment_executor = db.relationship('User', foreign_keys=[paid_by], backref='executed_payments')

    def __repr__(self):
        return f'<PaymentRequest {self.id} - KSh {self.amount:,.2f} for {self.invoice.invoice_number}>'

    def submit_for_approval(self):
        """Submit payment request for finance review"""
        if self.status == 'draft':
            self.status = 'submitted'
            self.updated_at = datetime.utcnow()

    def approve_by_finance(self, user_id, notes=None):
        """Approve by finance and send to director"""
        if self.status in ['submitted', 'finance_review']:
            self.status = 'director_approval'
            self.finance_reviewed_by = user_id
            self.finance_reviewed_at = datetime.utcnow()
            self.finance_notes = notes
            self.updated_at = datetime.utcnow()

    def approve_by_director(self, user_id, notes=None):
        """Approve by director - ready for payment"""
        if self.status == 'director_approval':
            self.status = 'approved'
            self.director_approved_by = user_id
            self.director_approved_at = datetime.utcnow()
            self.director_notes = notes
            self.updated_at = datetime.utcnow()

    def reject(self, user_id, notes, rejected_by_finance=False):
        """Reject payment request"""
        if rejected_by_finance:
            self.finance_reviewed_by = user_id
            self.finance_reviewed_at = datetime.utcnow()
            self.finance_notes = notes
        else:
            self.director_approved_by = user_id
            self.director_approved_at = datetime.utcnow()
            self.director_notes = notes
        
        self.status = 'rejected'
        self.updated_at = datetime.utcnow()

    def execute_payment_after_approval(self, user_id, notes=None):
        """Execute payment immediately after director approval and update invoice"""
        if self.status == 'director_approval':
            try:
                # First approve by director
                self.approve_by_director(user_id, notes)
                
                # Then execute the payment against the invoice
                success, message = self.execute_payment(user_id)
                
                if not success:
                    # Rollback the director approval if payment fails
                    self.status = 'director_approval'
                    self.director_approved_by = None
                    self.director_approved_at = None
                    self.director_notes = None
                    return False, message
                
                return True, "Payment approved and executed successfully"
                
            except Exception as e:
                # Rollback on any exception
                self.status = 'director_approval'
                self.director_approved_by = None
                self.director_approved_at = None
                self.director_notes = None
                return False, f"Error executing payment: {str(e)}"
        
        return False, "Payment request is not in director approval status"

    def execute_payment(self, user_id, proof_path=None):
        """Execute the payment and update invoice with enhanced status tracking"""
        if self.status == 'approved':
            try:
                # Get the invoice and current payment status
                invoice = self.invoice
                previous_amount_paid = invoice.amount_paid
                previous_balance = invoice.balance_due
                previous_status = invoice.status
                
                # Apply payment to invoice
                self.invoice.add_payment(self.amount, self.payment_method, self.reference)
                
                # Update payment request status
                self.status = 'paid'
                self.paid_by = user_id
                self.paid_at = datetime.utcnow()
                self.payment_proof_path = proof_path
                self.updated_at = datetime.utcnow()
                
                # Log the payment execution
                current_app.logger.info(
                    f"Payment executed: Request {self.id}, "
                    f"Invoice {invoice.invoice_number}, "
                    f"Amount: {self.amount}, "
                    f"Previous Status: {previous_status}, "
                    f"New Status: {invoice.status}, "
                    f"Previous Balance: {previous_balance}, "
                    f"New Balance: {invoice.balance_due}"
                )
                
                return True, "Payment executed successfully"
                
            except Exception as e:
                return False, f"Error executing payment: {str(e)}"
        
        return False, "Payment request is not approved"
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'invoice_number': self.invoice.invoice_number,
            'supplier_name': self.invoice.supplier_account.supplier.name,
            'amount': self.amount,
            'payment_method': self.payment_method,
            'reference': self.reference,
            'status': self.status,
            'requested_by': self.requester.username if self.requester else None,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'finance_reviewer': self.finance_reviewer.username if self.finance_reviewer else None,
            'finance_reviewed_at': self.finance_reviewed_at.isoformat() if self.finance_reviewed_at else None,
            'director_approver': self.director_approver.username if self.director_approver else None,
            'director_approved_at': self.director_approved_at.isoformat() if self.director_approved_at else None,
            'paid_by': self.payment_executor.username if self.payment_executor else None,
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
            'notes': self.notes
        }