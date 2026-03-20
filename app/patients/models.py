from app.extensions import db
from datetime import datetime
from sqlalchemy.ext.mutable import MutableDict

# Association table for many-to-many relationship between Transaction and Service
transaction_services = db.Table('transaction_services',
    db.Column('transaction_id', db.Integer, db.ForeignKey('transactions.id'), primary_key=True),
    db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
)

visit_services = db.Table('visit_services',
    db.Column('visit_id', db.Integer, db.ForeignKey('visits.id'), primary_key=True),
    db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
)


class Service(db.Model):
    __tablename__ = 'services'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    category = db.Column(db.String(64), nullable=False)  # 'Pharmacy', 'Lab', 'Consultation', etc.
    
    # General Service Information
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False, default=0.0)
    walkin_price = db.Column(db.Float, nullable=False, default=0.0)  # New column for walk-in price
    special_clinic_price = db.Column(db.Float, nullable=False, default=0.0)  # New column for special clinic price
    duration = db.Column(db.Integer)  # In minutes for services, days supply for medications
    
    # Pharmacy-Specific Fields (nullable for non-pharmacy services)
    item_category = db.Column(db.String(64))  # 'Drug', 'Medical Supply', 'Equipment'
    dosage_form = db.Column(db.String(64))    # Tablet, Capsule, Liquid, Injection, etc.
    strength = db.Column(db.String(64))       # e.g., "500mg", "10mg/mL"
    quantity_per_unit = db.Column(db.Integer) # Tablets per bottle, ml per vial
    ndc = db.Column(db.String(20))            # National Drug Code
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    expiration_date = db.Column(db.Date)
    requires_prescription = db.Column(db.Boolean, default=True)
    barcode = db.Column(db.String(50))
    lot_number = db.Column(db.String(50))
    storage_conditions = db.Column(db.String(100))  # "Room temp", "Refrigerate", etc.
    
    # Inventory Management
    quantity_in_stock = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=10)
    reorder_quantity = db.Column(db.Integer)
    last_restocked = db.Column(db.DateTime)
    
    # Relationships
    supplier = db.relationship('Supplier', backref='products')
    predefined_results = db.Column(
        db.JSON,
        nullable=True,
        default=list  # This sets the default in Python, not in SQL
    )

    # Add this relationship
    insurance_plans = db.relationship(
        'InsuranceService',
        back_populates='service',
        foreign_keys='InsuranceService.service_id'
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False, server_default=db.text('1'))
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    lab_test_id = db.Column(db.Integer, db.ForeignKey('laboratory_tests.test_id'), unique=True, nullable=True)
    lab_test = db.relationship('LaboratoryTest', back_populates='service', uselist=False)
    # Add this relationship
    assigned_doctors = db.relationship(
        'User', 
        secondary='service_doctor_assignments',
        primaryjoin='and_(Service.id == ServiceDoctorAssignment.service_id, '
                   'ServiceDoctorAssignment.is_active == True)',
        secondaryjoin='User.id == ServiceDoctorAssignment.doctor_id',
        backref=db.backref('assigned_services', lazy='dynamic'),
        lazy='dynamic',
        viewonly=True  # This is a read-only relationship
    )
    # Indexes
    __table_args__ = (
        db.Index('ix_service_category', 'category'),
        db.Index('ix_ndc', 'ndc'),
        db.Index('ix_barcode', 'barcode'),
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.predefined_results is None:
            self.predefined_results = []

    def __repr__(self):
        return f"<Service {self.id} {self.name} ({self.category})>"

    @property
    def is_pharmacy_product(self):
        return self.category.lower() == 'pharmacy'

    @property
    def expiration_status(self):
        if self.expiration_date:
            remaining_days = (self.expiration_date - datetime.today().date()).days
            return 'expired' if remaining_days < 0 else f'{remaining_days}d remaining'
        return 'N/A'

    @property
    def low_stock(self):
        if self.quantity_in_stock is None or self.min_stock_level is None:
            return False  # or True, depending on your logic
        return self.quantity_in_stock <= self.min_stock_level

    def validate_prescription(self, prescription):
        """Check if prescription is required and valid"""
        if self.requires_prescription and not prescription:
            return False
        return True

# Service-Doctor Assignment Model
# Service-Doctor Assignment Model
class ServiceDoctorAssignment(db.Model):
    __tablename__ = 'service_doctor_assignments'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Commission and Payment Fields
    commission_rate = db.Column(db.Float, default=70.0)  # Percentage (e.g., 70%)
    fixed_amount = db.Column(db.Float, nullable=True)  # Fixed amount instead of percentage
    payment_type = db.Column(db.String(20), default='percentage')  # 'percentage' or 'fixed'
    
    # Additional fields
    schedule = db.Column(db.String(100))
    max_patients_per_day = db.Column(db.Integer, default=20)
    consultation_fee = db.Column(db.Float)
    
    # Relationships
    service = db.relationship('Service', backref=db.backref('doctor_assignments', lazy='dynamic'))
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref=db.backref('doctor_service_assignments', lazy='dynamic'))
    assigned_by_user = db.relationship('User', foreign_keys=[assigned_by])
    
    # Payment tracking
    payments = db.relationship('DoctorPayment', backref='assignment', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('service_id', 'doctor_id', name='unique_service_doctor'),
    )

class DoctorPayment(db.Model):
    __tablename__ = 'doctor_payments'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('service_doctor_assignments.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))  # 'cash', 'bank_transfer', 'mpesa'
    reference_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    paid_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='completed')  # 'pending', 'completed', 'failed'
    
    # NEW: Account tracking
    account_type = db.Column(db.String(20), nullable=True)  # 'bank' or 'cash'
    account_id = db.Column(db.Integer, nullable=True)  # ID of the bank or cash account
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transactions.id'), nullable=True)
    cash_transaction_id = db.Column(db.Integer, db.ForeignKey('cash_transactions.id'), nullable=True)

    # Relationships
    paid_by_user = db.relationship('User', foreign_keys=[paid_by])
    # Relationship to assignment (already exists via backref)
    bank_transaction = db.relationship('BankTransaction', foreign_keys=[bank_transaction_id])
    cash_transaction = db.relationship('CashTransaction', foreign_keys=[cash_transaction_id])
    
    
class Transaction(db.Model):
    __tablename__ = 'transactions'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # e.g. 'stk', 'paybill'
    status = db.Column(db.String(20), default='pending')  # Values: pending, requested, completed, failed
    phone = db.Column(db.String(20), nullable=True)
    
    # NEW: Store served_by information
    served_by = db.Column(db.String(100), nullable=True)  # Staff member who processed the transaction
    served_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Link to user table if available
    
    # NEW: Store patient category
    patient_category = db.Column(db.String(20), default='general')  # general, walkin, special_clinic
    
    # Store raw callback JSON
    callback_data = db.Column(db.JSON, nullable=True)  # MySQL JSON type

    # M-Pesa identifiers
    account_ref = db.Column(db.String(64), nullable=True)    # Reference sent to MPESA
    checkout_request_id = db.Column(db.String(100), nullable=True)  # Returned by STK push
    merchant_request_id = db.Column(db.String(100), nullable=True)  # For paybill
    receipt_number = db.Column(db.String(100), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = db.relationship('Patient', backref=db.backref('transactions', lazy=True))
    services = db.relationship('Service', secondary=transaction_services, 
                               backref=db.backref('transactions', lazy=True))
    staff_member = db.relationship('User', backref=db.backref('processed_transactions', lazy=True))

    def __repr__(self):
        return f"<Transaction {self.id} {self.amount} ({self.status})>"

import re

def validate_kenyan_phone(phone):
    """Validate Kenyan phone number format"""
    pattern = r'^(?:254|\+254|0)?(7[0-9]{8})$'
    match = re.match(pattern, phone)
    if match:
        return '254' + match.group(1)
    return None

class Patient(db.Model):
    __tablename__ = 'patients'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    reg_no = db.Column(db.String(64), unique=True, nullable=False)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    age = db.Column(db.Integer)
    email = db.Column(db.String(120))
    gender = db.Column(db.String(120))
    phone = db.Column(db.String(20), nullable=False)
    kin_name = db.Column(db.String(120))
    kin_relationship = db.Column(db.String(64))
    kin_phone = db.Column(db.String(20))
    kin_email = db.Column(db.String(120))
    payment_method = db.Column(db.String(20))
    insurance_provider = db.Column(db.String(120))
    insurance_number  = db.Column(db.String(120))

    # ── New fields ──
    county        = db.Column(db.String(120))
    subcounty     = db.Column(db.String(120))
    ward          = db.Column(db.String(120))
    residence     = db.Column(db.String(120))
    marital_status= db.Column(db.String(64))
    national_id   = db.Column(db.String(64))
    guardian_id   = db.Column(db.String(64))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Patient {self.reg_no} {self.first_name} {self.last_name}>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def formatted_phone(self):
        phone = self.phone.strip()
        if phone.startswith('254'):
            return '0' + phone[3:]
        return phone
    
    @formatted_phone.setter
    def formatted_phone(self, value):
        validated = validate_kenyan_phone(value)
        if validated:
            self.phone = validated
        else:
            raise ValueError("Invalid Kenyan phone number")


class Visit(db.Model):
    __tablename__ = 'visits'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=True)

    # Basic visit info
    visit_date = db.Column(db.DateTime, default=datetime.utcnow)
    visit_status = db.Column(db.String(20), default='in_progress')
    current_position = db.Column(db.String(64), nullable=True)

    # Walk-in flag
    is_walk_in = db.Column(db.Boolean, nullable=True, default=False)
    visit_type_category = db.Column(db.String(50), nullable=False, default='general_consultation')
    visit_type_other_details = db.Column(db.String(255), nullable=True)
    
    # Patient category for pricing
    patient_category = db.Column(db.String(20), nullable=False, default='general')
    
    # Billing
    is_paid = db.Column(db.Boolean, default=False)
    payment_status = db.Column(db.String(20), default='pending')

    # Services (many-to-many)
    services = db.relationship('Service', secondary='visit_services',
                               backref=db.backref('visits', lazy='dynamic'))

    # Relationships - FIXED: Remove uselist=False where multiple records can exist
    patient = db.relationship('Patient', backref=db.backref('visits', lazy=True))
    transaction = db.relationship('Transaction', backref=db.backref('visit', uselist=False))
    
    # CHANGED: Remove uselist=False since multiple vitals can exist per visit
    vitals = db.relationship('Vitals', back_populates='visit')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # CHANGED: Remove uselist=False since multiple consultations can exist per visit
    consultations = db.relationship('Consultation', back_populates='visit')

    # ← Add this relation to match Invoice.visit.back_populates
    invoice = db.relationship(
        'Invoice',
        back_populates='visit',
        uselist=False
    )

    def __repr__(self):
        return f"<Visit {self.id} Patient:{self.patient_id} Status:{self.visit_status} WalkIn:{self.is_walk_in}>"

    # Helper property to get the most recent consultation
    @property
    def latest_consultation(self):
        return Consultation.query.filter_by(visit_id=self.id).order_by(Consultation.created_at.desc()).first()

    # Helper property to get the most recent vitals
    @property
    def latest_vitals(self):
        return Vitals.query.filter_by(visit_id=self.id).order_by(Vitals.recorded_at.desc()).first()



class Vitals(db.Model):
    __tablename__ = 'vitals'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    patient_id    = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    visit_id      = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=True)

    # Common vitals
    temperature   = db.Column(db.Float, nullable=False)
    heart_rate    = db.Column(db.Integer)
    bp_systolic   = db.Column(db.Integer)
    bp_diastolic  = db.Column(db.Integer)
    spo2          = db.Column(db.Integer)
    resp_rate     = db.Column(db.Integer, nullable=False)
    pain_score    = db.Column(db.Integer)
    notes         = db.Column(db.Text)
    recorded_at   = db.Column(db.DateTime, default=datetime.utcnow)

    # Adult-specific
    weight        = db.Column(db.Float)
    height        = db.Column(db.Float)
    bmi           = db.Column(db.Float)

    # Pediatric-specific
    muac          = db.Column(db.Float)  # optional malnutrition screening

    # Optional medical history / allergies
    allergy_food        = db.Column(db.Text)
    allergy_drugs       = db.Column(db.Text)
    chronic_conditions  = db.Column(db.Text)  # can store JSON
    current_medications = db.Column(db.Text)

    # relationships
    patient = db.relationship('Patient', backref=db.backref('vitals', lazy='dynamic'))
    visit = db.relationship('Visit', back_populates='vitals')
    tb_screening = db.relationship('TbScreening', back_populates='vitals', uselist=False)

    def to_dict(self):
        base = {
            'id': self.id,
            'patient_name': f"{self.patient.first_name} {self.patient.last_name}",
            'reg_no':      self.patient.reg_no,
            'temperature': self.temperature,
            'heart_rate':  self.heart_rate,
            'bp_systolic': self.bp_systolic,
            'bp_diastolic':self.bp_diastolic,
            'spo2':        self.spo2,
            'resp_rate':   self.resp_rate,
            'pain_score':  self.pain_score,
            'weight':      self.weight,
            'height':      self.height,
            'bmi':         self.bmi,
            'muac':        self.muac,
            'allergy_food':        self.allergy_food,
            'allergy_drugs':       self.allergy_drugs,
            'chronic_conditions':  self.chronic_conditions,
            'current_medications': self.current_medications,
            'notes':       self.notes,
            'recorded_at': self.recorded_at.isoformat(),
            'visit_id':    self.visit_id,
        }
        base['tb_screening'] = self.tb_screening.to_dict() if self.tb_screening else None
        return base


class TbScreening(db.Model):
    __tablename__ = 'tb_screenings'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)

    # link back to a single Vitals record
    vitals_id = db.Column(
        db.Integer,
        db.ForeignKey('vitals.id'),
        nullable=False
    )

    # --- Symptom screening ---
    cough_duration    = db.Column(db.Integer)           # in weeks
    fever             = db.Column(db.String(3), nullable=False, default='no')   # 'yes' / 'no'
    fever_duration    = db.Column(db.Integer)           # in weeks
    night_sweats      = db.Column(db.String(3), nullable=False, default='no')   # 'yes' / 'no'
    weight_loss_flag  = db.Column(db.String(3), nullable=False, default='no')   # 'yes' / 'no'
    weight_loss_amount= db.Column(db.Integer)           # kg lost
    hemoptysis        = db.Column(db.String(3), nullable=False, default='no')   # 'yes' / 'no'

    # --- Risk factors / comorbidities ---
    hiv_status        = db.Column(db.String(10), nullable=False, default='unknown')
    diabetes          = db.Column(db.String(3), nullable=False, default='no')
    prior_tb          = db.Column(db.String(3), nullable=False, default='no')
    prior_tb_year     = db.Column(db.Integer)           # year of last treatment
    household_contact = db.Column(db.String(3), nullable=False, default='no')
    smoking_history   = db.Column(db.String(10), nullable=False, default='never')
    alcohol_use       = db.Column(db.String(10), nullable=False, default='none')

    recorded_at       = db.Column(db.DateTime, default=datetime.utcnow)

    # relationship back to Vitals
    vitals = db.relationship(
        'Vitals',
        back_populates='tb_screening',
        uselist=False,
        foreign_keys=[vitals_id]
    )

    def to_dict(self):
        return {
            'id': self.id,
            'vitals_id': self.vitals_id,
            'cough_duration':    self.cough_duration,
            'fever':             self.fever,
            'fever_duration':    self.fever_duration,
            'night_sweats':      self.night_sweats,
            'weight_loss_flag':  self.weight_loss_flag,
            'weight_loss_amount':self.weight_loss_amount,
            'hemoptysis':        self.hemoptysis,
            'hiv_status':        self.hiv_status,
            'diabetes':          self.diabetes,
            'prior_tb':          self.prior_tb,
            'prior_tb_year':     self.prior_tb_year,
            'household_contact': self.household_contact,
            'smoking_history':   self.smoking_history,
            'alcohol_use':       self.alcohol_use,
            'recorded_at':       self.recorded_at.isoformat()
        }
    

class Consultation(db.Model):
    __tablename__ = 'consultations'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    visit_id = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    treated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # clinical fields
    history = db.Column(db.Text, nullable=False)
    examination = db.Column(db.Text, nullable=False)
    diagnosis = db.Column(db.Text, nullable=False)
    treatment_plan = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)

    # Relationships - FIXED
    patient = db.relationship('Patient', backref=db.backref('consultations', lazy='dynamic'))
    
    # CHANGED: Remove uselist=False and use proper back_populates
    visit = db.relationship('Visit', back_populates='consultations')
    
    treated_by = db.relationship('User', backref='consultations')

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat(),
            'history': self.history,
            'examination': self.examination,
            'diagnosis': self.diagnosis,
            'treatment_plan': self.treatment_plan,
            'notes': self.notes
        }



# In Medication model
class Medication(db.Model):
    __tablename__ = 'medications'
    __audit_trail__ = True

    id              = db.Column(db.Integer, primary_key=True)
    
    # --- MODIFIED: consultation_id can now be NULL ---
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultations.id'), nullable=True) 
    # --- NEW: Add visit_id which can also be NULL ---
    visit_id        = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=True)
    
    service_id      = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    dose            = db.Column(db.String(64))
    frequency       = db.Column(db.String(64))
    duration        = db.Column(db.Integer)   # Days
    quantity        = db.Column(db.Integer)
    prescribed_at   = db.Column(db.DateTime, default=datetime.utcnow)
    price           = db.Column(db.Float)
    is_paid         = db.Column(db.Boolean, default=False)
    payment_status  = db.Column(db.String(20), default='pending')

    # --- MODIFIED: Relationships ---
    consultation    = db.relationship('Consultation', backref=db.backref('medications', lazy=True))
    visit           = db.relationship('Visit', backref=db.backref('medications', lazy=True)) # New relationship
    service         = db.relationship('Service',        backref=db.backref('prescriptions', lazy=True))

    is_dispensed    = db.Column(db.Boolean, default=False)
    dispensed_at    = db.Column(db.DateTime)

    # ─── ADD THESE TWO LINES ─────────────────────────────────────────────────────
    dispensed_by    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    dispenser       = db.relationship('User', foreign_keys=[dispensed_by])
    # ─────────────────────────────────────────────────────────────────────────────
    
    # Add a check constraint to ensure one of the IDs is always present, but not both
    # This might be tricky to enforce directly in SQLAlchemy for both nullables.
    # Application logic should ensure either consultation_id or visit_id is set.

    # The above check constraint requires that either consultation_id is NOT NULL and visit_id IS NULL,
    # OR consultation_id IS NULL and visit_id IS NOT NULL. This ensures a medication always belongs to one path.
    # ✅ Add standard timestamp columns
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# In LabTest model
class LabTest(db.Model):
    __tablename__ = 'lab_tests'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    
    # --- MODIFIED: consultation_id can now be NULL ---
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultations.id'), nullable=True)
    # --- NEW: Add visit_id which can also be NULL ---
    visit_id        = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=True)

    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    status = db.Column(db.String(20), default='requested')
    results = db.Column(db.Text)
    results_data = db.Column(MutableDict.as_mutable(db.JSON))
    notes = db.Column(db.Text)
    doctor_signature = db.Column(db.Text)
    interpretation = db.Column(db.Text)
    
        # ✅ Add price column
    price = db.Column(db.Float, nullable=False, default=0.0)
    is_paid = db.Column(db.Boolean, default=False)  # Added
    payment_status = db.Column(db.String(20), default='pending')  # Added
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Fixed table name
    verified_at = db.Column(db.DateTime)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    
    # ✅ Add standard timestamp columns
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ───────── Done By ─────────
    done_by_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    done_at         = db.Column(db.DateTime)
    done_by         = db.relationship(
                                'User',
                                foreign_keys=[done_by_id],
                                backref=db.backref('completed_tests', lazy='dynamic')
                            )

    # --- MODIFIED: Relationships ---
    consultation    = db.relationship('Consultation', backref=db.backref('lab_tests', lazy=True))
    visit           = db.relationship('Visit', backref=db.backref('lab_tests', lazy=True)) # New relationship
    service         = db.relationship('Service', backref=db.backref('lab_orders', lazy=True))
    doctor          = db.relationship('User', foreign_keys=[verified_by]) # Renamed from 'doctor' to 'verified_by_user' for clarity in Radiology
    results_detail  = db.relationship('LabTestResult', back_populates='lab_test_order', cascade='all, delete-orphan')



# In Radiology model
class Radiology(db.Model):
    __tablename__ = 'radiology_orders'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    
    # --- MODIFIED: consultation_id can now be NULL ---
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultations.id'), nullable=True)
    # --- NEW: Add visit_id which can also be NULL ---
    visit_id        = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=True)

    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    status = db.Column(db.String(20), default='requested')
    results = db.Column(db.Text)
    notes = db.Column(db.Text)
    images = db.Column(db.Text)
    thumbnails = db.Column(db.Text)    # comma-separated PNG thumbnail names
    interpretation = db.Column(db.Text)
    doctor_signature = db.Column(db.Text)
    # ✅ Add price column
    price = db.Column(db.Float, nullable=False, default=0.0)
    is_paid = db.Column(db.Boolean, default=False)  # Added
    payment_status = db.Column(db.String(20), default='pending')  # Added
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # --- MODIFIED: Relationships ---
    consultation = db.relationship('Consultation', backref=db.backref('radiology_orders', lazy=True))
    visit        = db.relationship('Visit', backref=db.backref('radiology_orders', lazy=True)) # New relationship
    service      = db.relationship('Service', backref=db.backref('imaging_orders', lazy=True))
    
    results_data = db.Column(MutableDict.as_mutable(db.JSON))
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Ensure this line exists
    verified_at = db.Column(db.DateTime)
    # ✅ Add standard timestamp columns
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ───────── Done By ─────────
    done_by_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    done_at         = db.Column(db.DateTime)
    done_by         = db.relationship(
                                'User',
                                foreign_keys=[done_by_id],
                                backref=db.backref('completed_radiology', lazy='dynamic')
                            )
    # Add this relationship
    verified_by_user = db.relationship('User', foreign_keys=[verified_by])



class AIConversation(db.Model):
    __tablename__ = 'ai_conversations'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # the user/doctor
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    patient = db.relationship('Patient', backref=db.backref('ai_conversations', lazy='dynamic'))
    doctor = db.relationship('User', backref=db.backref('ai_conversations', lazy='dynamic'))
    messages = db.relationship('AIMessage', back_populates='conversation', order_by='AIMessage.created_at', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('patient_id', 'doctor_id', name='unique_patient_doctor_conversation'),
    )


class AIMessage(db.Model):
    __tablename__ = 'ai_messages'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('ai_conversations.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    conversation = db.relationship('AIConversation', back_populates='messages')