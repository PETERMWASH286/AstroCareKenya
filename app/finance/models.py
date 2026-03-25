from datetime import datetime

from flask import current_app
from app.extensions import db
from app.hr.models import PaymentMethod

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
    
    
    # In Expense class
    account_type = db.Column(db.String(20), nullable=True)  # 'bank' or 'cash'
    account_id = db.Column(db.Integer, nullable=True)  # ID of BankAccount or CashAccount
    receipt_number = db.Column(db.String(100), nullable=True)
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    payment_date = db.Column(db.DateTime)
    payroll_id = db.Column(db.Integer, db.ForeignKey('payrolls.id'), nullable=True)
    payroll = db.relationship('Payroll', backref=db.backref('expense', uselist=False))
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
    
    

class SalesReport(db.Model):
    __tablename__ = 'sales_reports'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    patient_reg_no = db.Column(db.String(50), nullable=False)
    patient_name = db.Column(db.String(200))          # denormalised for quick access
    visit_id = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), unique=True, nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20))         # e.g., 'mpesa', 'cash'
    receipt_number = db.Column(db.String(50))         # M-Pesa receipt, etc.
    served_by = db.Column(db.String(100))             # staff name
    patient_category = db.Column(db.String(20))       # general, walkin, special_clinic
    visit_type_category = db.Column(db.String(50))    # from visit
    sale_date = db.Column(db.DateTime, nullable=False)   # date/time of payment completion
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    patient = db.relationship('Patient')
    visit = db.relationship('Visit')
    transaction = db.relationship('Transaction')
    invoice = db.relationship('Invoice')
    items = db.relationship('SalesReportItem', backref='report', lazy='dynamic', cascade='all, delete-orphan')


class SalesReportItem(db.Model):
    __tablename__ = 'sales_report_items'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    sales_report_id = db.Column(db.Integer, db.ForeignKey('sales_reports.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    service_name = db.Column(db.String(200))          # denormalised
    department = db.Column(db.String(64))             # e.g., Pharmacy, Laboratory, Radiology
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)

    # Optional: link to specific service instance (medication, labtest, radiology) for traceability
    medication_id = db.Column(db.Integer, db.ForeignKey('medications.id'), nullable=True)
    lab_test_id = db.Column(db.Integer, db.ForeignKey('lab_tests.id'), nullable=True)
    radiology_id = db.Column(db.Integer, db.ForeignKey('radiology_orders.id'), nullable=True)
    
    
    
    
    
# app/finance/models.py

class CashAccount(db.Model):
    __tablename__ = 'cash_accounts'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)          # e.g., "Main Paybill", "Cash Drawer 1"
    account_type = db.Column(db.String(50), nullable=False)   # 'paybill', 'cash_drawer', 'mobile_money'
    account_number = db.Column(db.String(50), unique=True)    # paybill number (if applicable)
    current_balance = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(10), default='KES')
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Explicit relationships – no ambiguity
    outgoing_transactions = db.relationship(
        'CashTransaction',
        foreign_keys='CashTransaction.source_cash_account_id',
        backref='source_account',
        lazy='dynamic'
    )
    incoming_transactions = db.relationship(
        'CashTransaction',
        foreign_keys='CashTransaction.dest_cash_account_id',
        backref='dest_account',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<CashAccount {self.name} ({self.account_type}) balance: {self.current_balance}>'
    # In CashAccount model
    def get_ledger_entries(self):
        """Return list of dicts with date, description, debit, credit, balance for this cash account."""
        from app.finance.models import CashTransaction
        entries = []
        # Combine incoming and outgoing transactions
        for tx in self.incoming_transactions.order_by(CashTransaction.completed_at).all():
            entries.append({
                'date': tx.completed_at or tx.initiated_at,
                'description': tx.description,
                'debit': tx.amount,
                'credit': 0,
                'ref': tx.transaction_ref,
                'type': tx.transaction_type
            })
        for tx in self.outgoing_transactions.order_by(CashTransaction.completed_at).all():
            entries.append({
                'date': tx.completed_at or tx.initiated_at,
                'description': tx.description,
                'debit': 0,
                'credit': tx.amount,
                'ref': tx.transaction_ref,
                'type': tx.transaction_type
            })
        # Sort by date
        entries.sort(key=lambda x: x['date'])
        # Compute running balance
        balance = 0
        for e in entries:
            balance += e['debit'] - e['credit']
            e['balance'] = balance
        return entries

class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(100), nullable=False)
    account_name = db.Column(db.String(200), nullable=False)
    account_number = db.Column(db.String(50), nullable=False, unique=True)
    branch = db.Column(db.String(100))
    swift_code = db.Column(db.String(20))
    # NEW: Balance tracking
    initial_balance = db.Column(db.Float, default=0.0)
    current_balance = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cash_transactions = db.relationship(
        'CashTransaction',
        foreign_keys='CashTransaction.dest_bank_account_id',
        backref='bank_account',
        lazy='dynamic'
    )
    manual_transactions = db.relationship(
        'BankTransaction',
        backref='bank_account',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<BankAccount {self.bank_name} - {self.account_number}>'

    # In BankAccount model
    def get_ledger_entries(self):
        """Combine cash transfers and manual bank transactions into one ledger."""
        from app.finance.models import CashTransaction, BankTransaction
        entries = []
        # Cash transfers into this bank
        for tx in self.cash_transactions.order_by(CashTransaction.completed_at).all():
            entries.append({
                'date': tx.completed_at or tx.initiated_at,
                'description': tx.description,
                'debit': tx.amount,   # incoming to bank
                'credit': 0,
                'ref': tx.transaction_ref,
                'type': 'cash_transfer'
            })
        # Manual transactions
        for tx in self.manual_transactions.order_by(BankTransaction.transaction_date).all():
            if tx.transaction_type in ('deposit', 'interest'):
                debit = tx.amount
                credit = 0
            else:  # withdrawal, fee
                debit = 0
                credit = tx.amount
            entries.append({
                'date': tx.transaction_date,
                'description': tx.description,
                'debit': debit,
                'credit': credit,
                'ref': tx.reference,
                'type': tx.transaction_type
            })
        entries.sort(key=lambda x: x['date'])
        balance = self.initial_balance
        for e in entries:
            balance += e['debit'] - e['credit']
            e['balance'] = balance
        return entries

class BankTransaction(db.Model):
    __tablename__ = 'bank_transactions'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    transaction_type = db.Column(db.String(20))  # 'deposit', 'withdrawal', 'fee', 'interest'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    reference = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<BankTransaction {self.transaction_type} {self.amount}>'


class CashTransaction(db.Model):
    __tablename__ = 'cash_transactions'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    transaction_ref = db.Column(db.String(100), unique=True, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'deposit', 'withdrawal', 'transfer', 'bank_transfer'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)

    source_cash_account_id = db.Column(db.Integer, db.ForeignKey('cash_accounts.id'), nullable=True)
    dest_cash_account_id = db.Column(db.Integer, db.ForeignKey('cash_accounts.id'), nullable=True)
    dest_bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    dest_petty_cash_account_id = db.Column(db.Integer, db.ForeignKey('petty_cash_accounts.id'), nullable=True)
    # Link to original M‑Pesa transaction (if deposit)
    source_transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=True)
    source_transaction = db.relationship('Transaction', foreign_keys=[source_transaction_id])

    # Batch tracking
    batch_number = db.Column(db.String(50), nullable=True)
    batch_date = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(20), default='completed')  # 'pending', 'completed', 'failed'
    initiated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    initiated_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    external_reference = db.Column(db.String(100))  # e.g., M‑Pesa business payment receipt

    initiator = db.relationship('User', foreign_keys=[initiated_by])
    dest_petty_cash = db.relationship('PettyCash', foreign_keys=[dest_petty_cash_account_id])

    def __repr__(self):
        return f'<CashTransaction {self.transaction_ref} type={self.transaction_type} amount={self.amount}>'

    def generate_ref(self):
        """Generate a unique reference number."""
        import random
        import string
        date_str = datetime.utcnow().strftime('%Y%m%d')
        rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"{self.transaction_type.upper()}-{date_str}-{rand_part}"
    
    
    
class PayrollPayment(db.Model):
    __tablename__ = 'payroll_payments'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(db.Integer, db.ForeignKey('payrolls.id'), nullable=False)
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    reference = db.Column(db.String(100), nullable=True)  # Bank ref, M-PESA ID, cheque number
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    payroll = db.relationship('Payroll', backref=db.backref('payments', lazy='dynamic'))
    bank_account = db.relationship('BankAccount', backref='payroll_payments')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<PayrollPayment #{self.id} for Payroll {self.payroll_id}: {self.payment_method} KES {self.amount}>'
    
    


class BankStatement(db.Model):
    __tablename__ = 'bank_statements'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    statement_date = db.Column(db.Date, nullable=False)
    opening_balance = db.Column(db.Float, default=0.0)
    closing_balance = db.Column(db.Float, default=0.0)
    file_path = db.Column(db.String(255))  # original uploaded file
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_reconciled = db.Column(db.Boolean, default=False)

    # Relationships
    account = db.relationship('BankAccount')
    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    lines = db.relationship('BankStatementLine', backref='statement', lazy='dynamic', cascade='all, delete-orphan')


class BankStatementLine(db.Model):
    __tablename__ = 'bank_statement_lines'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    statement_id = db.Column(db.Integer, db.ForeignKey('bank_statements.id'), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255))
    reference = db.Column(db.String(100))
    amount = db.Column(db.Float, nullable=False)  # positive for credit, negative for debit
    balance = db.Column(db.Float)  # running balance after this line
    matched_transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transactions.id'), nullable=True)
    matched_transaction = db.relationship('BankTransaction', foreign_keys=[matched_transaction_id])
    is_matched = db.Column(db.Boolean, default=False)
    
    
    
    
class FinanceConversation(db.Model):
    __tablename__ = 'finance_conversations'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('finance_conversations', lazy='dynamic'))
    messages = db.relationship('FinanceMessage', back_populates='conversation', order_by='FinanceMessage.created_at', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('user_id', name='unique_user_finance_conversation'),
    )


class FinanceMessage(db.Model):
    __tablename__ = 'finance_messages'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('finance_conversations.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    conversation = db.relationship('FinanceConversation', back_populates='messages')
    
    
    
    
class PettyCash(db.Model):
    __tablename__ = 'petty_cash_accounts'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)   # 'petty_cash', 'advance', 'float'
    account_number = db.Column(db.String(50), unique=True)     # NEW: unique account number
    current_balance = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(10), default='KES')
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Relationships
    outgoing_transactions = db.relationship(
        'PettyCashTransaction',
        foreign_keys='PettyCashTransaction.source_petty_cash_account_id',
        backref='source_account',
        lazy='dynamic'
    )
    incoming_transactions = db.relationship(
        'PettyCashTransaction',
        foreign_keys='PettyCashTransaction.dest_petty_cash_account_id',
        backref='dest_account',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<PettyCash {self.name} balance: {self.current_balance}>'


    def get_ledger_entries(self):
        """Return list of dicts with date, description, debit, credit, balance for this petty cash account."""
        entries = []
        for tx in self.incoming_transactions.order_by(PettyCashTransaction.completed_at).all():
            entries.append({
                'date': tx.completed_at or tx.initiated_at,
                'description': tx.description,
                'debit': tx.amount,
                'credit': 0,
                'ref': tx.transaction_ref,
                'type': tx.transaction_type
            })
        for tx in self.outgoing_transactions.order_by(PettyCashTransaction.completed_at).all():
            entries.append({
                'date': tx.completed_at or tx.initiated_at,
                'description': tx.description,
                'debit': 0,
                'credit': tx.amount,
                'ref': tx.transaction_ref,
                'type': tx.transaction_type
            })
        entries.sort(key=lambda x: x['date'])
        balance = 0
        for e in entries:
            balance += e['debit'] - e['credit']
            e['balance'] = balance
        return entries

class PettyCashTransaction(db.Model):
    __tablename__ = 'petty_cash_transactions'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    transaction_ref = db.Column(db.String(100), unique=True, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'deposit', 'withdrawal', 'transfer_in', 'transfer_out'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)

    source_petty_cash_account_id = db.Column(db.Integer, db.ForeignKey('petty_cash_accounts.id'), nullable=True)
    dest_petty_cash_account_id = db.Column(db.Integer, db.ForeignKey('petty_cash_accounts.id'), nullable=True)
    source_cash_account_id = db.Column(db.Integer, db.ForeignKey('cash_accounts.id'), nullable=True)  # when transfer from cash account

    batch_number = db.Column(db.String(50), nullable=True)
    batch_date = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(20), default='completed')  # 'pending', 'completed', 'failed'
    initiated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    initiated_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    external_reference = db.Column(db.String(100))  # e.g., receipt number

    initiator = db.relationship('User', foreign_keys=[initiated_by])

    def __repr__(self):
        return f'<PettyCashTransaction {self.transaction_ref} type={self.transaction_type} amount={self.amount}>'

    def generate_ref(self):
        """Generate a unique reference number."""
        import random
        import string
        date_str = datetime.utcnow().strftime('%Y%m%d')
        rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"PETTY-{self.transaction_type.upper()}-{date_str}-{rand_part}"