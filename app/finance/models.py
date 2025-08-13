from datetime import datetime

from flask import current_app
from app.extensions import db

class Insurance(db.Model):
    __tablename__ = 'insurances'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    
    # Basic Insurance Information
    name = db.Column(db.String(120), nullable=False)  # Insurance provider name
    policy_number = db.Column(db.String(60), unique=True, nullable=False)
    insurance_type = db.Column(db.String(64), nullable=False)  # 'Health', 'Auto', 'Life', etc.
    contact_number = db.Column(db.String(20))
    email = db.Column(db.String(120))
    website = db.Column(db.String(255))
    
    # Coverage Details
    coverage_start_date = db.Column(db.Date, nullable=False)
    coverage_end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    max_coverage_amount = db.Column(db.Float)
    deductible = db.Column(db.Float)
    
    # Relationships
    covered_services = db.relationship('InsuranceService', back_populates='insurance', 
                                     cascade='all, delete-orphan')
    
    # Address Information
    address = db.Column(db.Text)
    city = db.Column(db.String(64))
    state = db.Column(db.String(64))
    country = db.Column(db.String(64), default='USA')
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        db.Index('ix_insurance_type', 'insurance_type'),
        db.Index('ix_policy_number', 'policy_number'),
        db.Index('ix_coverage_dates', 'coverage_start_date', 'coverage_end_date'),
    )

    def __repr__(self):
        return f"<Insurance {self.id} {self.name} ({self.policy_number})>"

    @property
    def coverage_status(self):
        if self.coverage_end_date and self.coverage_end_date < datetime.today().date():
            return 'Expired'
        return 'Active' if self.is_active else 'Inactive'

    def covers_service(self, service_id):
        return any(service.service_id == service_id for service in self.covered_services)

class InsuranceService(db.Model):
    __tablename__ = 'insurance_services'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Keys
    insurance_id = db.Column(db.Integer, db.ForeignKey('insurances.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    
    # Coverage Details
    copay = db.Column(db.Float)
    coverage_percentage = db.Column(db.Float)  # 0-100%
    annual_limit = db.Column(db.Float)
    requires_prior_authorization = db.Column(db.Boolean, default=False)
    is_covered = db.Column(db.Boolean, default=True)
    coverage_notes = db.Column(db.Text)
    
    # Service Category (denormalized for faster queries)
    service_category = db.Column(db.String(64), nullable=False)
    
    # Relationships
    insurance = db.relationship('Insurance', back_populates='covered_services')
    # Replace the service relationship with:
    service = db.relationship(
        'Service',
        back_populates='insurance_plans',
        foreign_keys=[service_id]
    )  
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        db.Index('ix_insurance_service', 'insurance_id', 'service_id'),
        db.Index('ix_service_category', 'service_category'),
    )

    def __repr__(self):
        return f"<InsuranceService {self.id} - Ins: {self.insurance_id} Srv: {self.service_id}>"

    @property
    def patient_responsibility(self, service_price):
        if self.coverage_percentage:
            return service_price * (1 - (self.coverage_percentage / 100))
        return service_price - (self.copay or 0)

    def validate_coverage(self, service_date=datetime.today().date()):
        return (
            self.is_covered and
            self.insurance.coverage_start_date <= service_date and
            (self.insurance.coverage_end_date is None or 
             self.insurance.coverage_end_date >= service_date)
        )


class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    invoice_type = db.Column(db.String(20), nullable=False)
    insurance_id = db.Column(db.Integer, db.ForeignKey('insurances.id'), nullable=True)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text)

    items = db.relationship(
        'InvoiceItem',
        back_populates='invoice',
        cascade='all, delete-orphan'
    )
    payments = db.relationship('Payment', back_populates='invoice')
    insurance = db.relationship('Insurance')
    visit = db.relationship('Visit', back_populates='invoice')
    patient = db.relationship('Patient')

    # One-to-many: an invoice can have multiple insurance claims
    insurance_claims = db.relationship(
        'InsuranceClaim',
        backref='invoice',
        cascade='all, delete-orphan'
    )

    @property
    def balance(self):
        """Calculate remaining balance for the invoice"""
        paid = sum(payment.amount for payment in self.payments)
        return max(self.total_amount - paid, 0)



class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)

    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    is_insured = db.Column(db.Boolean, default=False)
    coverage_percentage = db.Column(db.Float)  # 0-100
    copay_amount = db.Column(db.Float)
    notes = db.Column(db.Text)

    invoice = db.relationship('Invoice', back_populates='items')
    service = db.relationship('Service')



class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20))  # 'cash', 'mpesa', 'card', etc.
    status = db.Column(db.String(20), default='completed')  # pending, failed, refunded, etc.
    
    reference = db.Column(db.String(100))  # e.g., M-PESA transaction code
    payer_name = db.Column(db.String(100))
    
    invoice = db.relationship('Invoice', back_populates='payments')


class InsuranceClaim(db.Model):
    __tablename__ = 'insurance_claims'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    insurance_id = db.Column(db.Integer, db.ForeignKey('insurances.id'), nullable=False)
    claim_date = db.Column(db.DateTime, default=datetime.utcnow)
    claim_reference = db.Column(db.String(100), unique=True)
    status = db.Column(db.String(20), default='submitted')
    submitted_by = db.Column(db.String(100))
    response_received = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)

    insurance = db.relationship('Insurance')

    # One-to-many: a claim can have multiple responses
    claim_responses = db.relationship(
        'ClaimResponse',
        backref='claim',
        cascade='all, delete-orphan'
    )


class ClaimResponse(db.Model):
    __tablename__ = 'claim_responses'
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('insurance_claims.id'), nullable=False)
    response_date = db.Column(db.DateTime, default=datetime.utcnow)
    approved_amount = db.Column(db.Float)
    denied_amount = db.Column(db.Float)
    reason = db.Column(db.Text)
    response_status = db.Column(db.String(20))  # e.g., 'approved', 'partial', 'rejected'

    # Remove explicit relationship here—backref='claim' on InsuranceClaim.claim_responses covers it.
    # claim = db.relationship('InsuranceClaim')


class ExpenseCategory(db.Model):
    __tablename__ = 'expense_categories'
    __audit_trail__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    budget_allocation = db.Column(db.Float, default=0.0)  # Annual budget allocated
    is_active = db.Column(db.Boolean, default=True)
    
    # Hospital department association
    department = db.Column(db.String(100), nullable=False)
    
    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'

class Expense(db.Model):
    __tablename__ = 'expenses'
    __audit_trail__ = True  # Enable auditing
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Core expense information
    expense_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='Ksh', nullable=False)
    description = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)  # cash, cheque, mobile, bank transfer
    reference_number = db.Column(db.String(100))  # payment reference
    
    # Hospital-specific associations
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    initiated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Medical expense details
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))  # If patient-related
    
    # Financial tracking
    budget_period = db.Column(db.String(20))  # e.g., "Q1-2023", "FY2024"
    tax_amount = db.Column(db.Float, default=0.0)
    tax_rate = db.Column(db.Float, default=0.0)
    is_reimbursable = db.Column(db.Boolean, default=False)
    
    # Operational details
    expense_type = db.Column(db.String(50), nullable=False)  # operational, capital, emergency
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    
    # Status tracking
    status = db.Column(db.Enum(
        'draft', 
        'submitted', 
        'approved', 
        'rejected', 
        'paid',
        'reimbursed',
        'audited',
        name='expense_status'
    ), default='draft')
    
    # Documentation
    attachments = db.Column(db.Text)  # Comma-separated file paths
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    payment_date = db.Column(db.DateTime)
    
    # Relationships - FIXED Department reference
    category = db.relationship('ExpenseCategory', backref='expenses')
    department = db.relationship('Department', backref='expenses')  # Fixed
    supplier = db.relationship('Supplier', backref='expenses')
    patient = db.relationship('Patient', backref='expenses')
    initiator = db.relationship('User', foreign_keys=[initiated_by], backref='initiated_expenses')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_expenses')
    
    def __repr__(self):
        return f'<Expense {self.id} - {self.description[:20]}>'
    
    def to_dict(self):
        return {
            "id": self.id,
            "expense_date": self.expense_date.isoformat(),
            "amount": self.amount,
            "currency": self.currency,
            "description": self.description,
            "category": self.category.name,
            "department": self.department.name,
            "status": self.status,
            "payment_method": self.payment_method,
            "initiated_by": self.initiator.username,
            "approved_by": self.approver.username if self.approver else None,
            "budget_period": self.budget_period
        }
    
    def calculate_tax(self):
        """Calculate tax amount based on category tax rules"""
        try:
            # Medical supplies often have different tax rates
            if self.category.name.lower() in ['pharmaceuticals', 'medical supplies']:
                self.tax_rate = 0.0  # Often tax-exempt for medical essentials
            else:
                self.tax_rate = 0.16  # Standard VAT rate
                
            self.tax_amount = round(self.amount * self.tax_rate, 2)
        except Exception as e:
            current_app.logger.error(f"Tax calculation error: {str(e)}")
            self.tax_rate = 0.16
            self.tax_amount = round(self.amount * 0.16, 2)
    
    def generate_reference(self):
        """Generate expense reference number"""
        prefix = "EXP"
        date_str = self.expense_date.strftime("%y%m%d")
        return f"{prefix}-{date_str}-{self.id:06d}"