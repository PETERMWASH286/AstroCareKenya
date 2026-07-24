# app/inpatient/models.py
from datetime import datetime
from app import db
from app.patients.models import Patient, Service
from app.auth.models import User

# ==========================================
# 1. Ward & Bed (unchanged)
# ==========================================
class Ward(db.Model):
    __tablename__ = 'wards'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    floor = db.Column(db.String(50))
    capacity = db.Column(db.Integer)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    substore_id = db.Column(db.Integer, db.ForeignKey('substores.id'), nullable=True)

    beds = db.relationship('Bed', backref='ward', lazy=True, cascade='all, delete-orphan')
    admissions = db.relationship('InpatientAdmission', backref='ward', lazy=True)

    def __repr__(self):
        return f"<Ward {self.name}>"


class Bed(db.Model):
    __tablename__ = 'beds'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    bed_number = db.Column(db.String(20), nullable=False)
    is_occupied = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    current_admission = db.relationship('InpatientAdmission', backref='bed', uselist=False)
    __table_args__ = (db.UniqueConstraint('ward_id', 'bed_number', name='unique_bed_per_ward'),)

    def __repr__(self):
        return f"<Bed {self.bed_number} (Ward {self.ward_id})>"


# ==========================================
# 2. Core Admission Models (unchanged)
# ==========================================
class InpatientAdmission(db.Model):
    __tablename__ = 'inpatient_admissions'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'), nullable=True)

    file_number = db.Column(db.String(50), unique=True, nullable=False)
    admission_date = db.Column(db.DateTime, default=datetime.utcnow)
    diagnosis = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')  # active, discharged, transferred
    admitting_doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nurse_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    referral_source = db.Column(db.String(100))
    admission_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    daily_bed_fee_rate = db.Column(db.Float, default=0.0)
    bed_admission_fee = db.Column(db.Float, default=0.0)
    doctor_admission_fee = db.Column(db.Float, default=0.0)

    # Relationships
    patient = db.relationship('Patient', backref=db.backref('inpatient_admissions', lazy=True))
    admitting_doctor = db.relationship('User', foreign_keys=[admitting_doctor_id])
    nurse = db.relationship('User', foreign_keys=[nurse_id])

    treatments = db.relationship('InpatientTreatment', backref='admission', lazy=True, cascade='all, delete-orphan')
    drug_orders = db.relationship('InpatientDrugOrder', backref='admission', lazy=True, cascade='all, delete-orphan')
    charge_sheets = db.relationship('InpatientChargeSheet', backref='admission', lazy=True, cascade='all, delete-orphan')
    deposits = db.relationship('InpatientDeposit', backref='admission', lazy=True, cascade='all, delete-orphan')
    
    # ✅ REMOVE the old 'invoices' line and replace with the relationship using back_populates
    invoices = db.relationship('InpatientInvoice', back_populates='admission', lazy=True, cascade='all, delete-orphan')
    
    sha_claims = db.relationship('InpatientSHAClaim', backref='admission', lazy=True, cascade='all, delete-orphan')
    closed_file = db.relationship('InpatientClosedFile', backref='admission', uselist=False)
    
    def __repr__(self):
        return f"<Admission {self.file_number} - {self.patient.full_name}>"


class InpatientTreatment(db.Model):
    __tablename__ = 'inpatient_treatments'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), nullable=False)
    treatment_date = db.Column(db.DateTime, default=datetime.utcnow)
    treatment_type = db.Column(db.String(100))
    description = db.Column(db.Text)
    notes = db.Column(db.Text)
    performed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    performed_by = db.relationship('User', foreign_keys=[performed_by_id])


class InpatientDischarge(db.Model):
    __tablename__ = 'inpatient_discharges'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), unique=True, nullable=False)
    discharge_date = db.Column(db.DateTime, default=datetime.utcnow)
    discharge_type = db.Column(db.String(50))
    final_diagnosis = db.Column(db.Text)
    discharge_instructions = db.Column(db.Text)
    history = db.Column(db.Text)
    examination = db.Column(db.Text)
    investigations = db.Column(db.Text)
    treatment_given = db.Column(db.Text)
    patient_condition = db.Column(db.String(100))
    follow_up_clinic = db.Column(db.String(100))
    advice = db.Column(db.Text)
    recommendations = db.Column(db.Text)
    doctor_name = db.Column(db.String(120))
    code = db.Column(db.String(50))
    kmpdc_no = db.Column(db.String(50))
    discharged_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    discharged_by = db.relationship('User', foreign_keys=[discharged_by_id])


class InpatientClosedFile(db.Model):
    __tablename__ = 'inpatient_closed_files'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), unique=True, nullable=False)
    closed_date = db.Column(db.DateTime, default=datetime.utcnow)
    closed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_by = db.relationship('User', foreign_keys=[closed_by_id])


# ==========================================
# 3. Pharmacy & Medication (unchanged)
# ==========================================
class InpatientDrugOrder(db.Model):
    __tablename__ = 'inpatient_drug_orders'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), nullable=False)
    drug_service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    dosage = db.Column(db.String(100))
    route = db.Column(db.String(50))
    frequency = db.Column(db.String(50))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')
    notes = db.Column(db.Text)
    ordered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    drug_service = db.relationship('Service', foreign_keys=[drug_service_id])
    ordered_by = db.relationship('User', foreign_keys=[ordered_by_id])
    dispenses = db.relationship('InpatientDispense', backref='drug_order', lazy=True, cascade='all, delete-orphan')


class InpatientDispense(db.Model):
    __tablename__ = 'inpatient_dispenses'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    drug_order_id = db.Column(db.Integer, db.ForeignKey('inpatient_drug_orders.id'), nullable=False)
    dispense_date = db.Column(db.DateTime, default=datetime.utcnow)
    quantity_dispensed = db.Column(db.Float)
    batch_number = db.Column(db.String(50))
    expiry_date = db.Column(db.Date)
    dispensed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    dispensed_by = db.relationship('User', foreign_keys=[dispensed_by_id])


# ==========================================
# 4. Billing & Charges – ENHANCED
# ==========================================
# ==========================================
# 4. Billing & Charges – ENHANCED (fixed)
# ==========================================

class InpatientChargeSheet(db.Model):
    __tablename__ = 'inpatient_charge_sheets'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)  # ✅ changed to nullable
    substore_inventory_id = db.Column(db.Integer, db.ForeignKey('substore_inventory.id'), nullable=True)  # ✅ NEW
    quantity = db.Column(db.Float, default=1.0)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    charge_date = db.Column(db.DateTime, default=datetime.utcnow)
    posted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    service = db.relationship('Service', foreign_keys=[service_id])
    substore_inventory = db.relationship('SubstoreInventory', foreign_keys=[substore_inventory_id])  # ✅ NEW
    posted_by = db.relationship('User', foreign_keys=[posted_by_id])


class InpatientDeposit(db.Model):
    __tablename__ = 'inpatient_deposits'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))
    reference = db.Column(db.String(100))
    deposit_date = db.Column(db.DateTime, default=datetime.utcnow)
    received_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    received_by = db.relationship('User', foreign_keys=[received_by_id])


# ─── Invoice Item Model ──────────────────────────────────────────────
class InpatientInvoiceItem(db.Model):
    __tablename__ = 'inpatient_invoice_items'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('inpatient_invoices.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    charge_sheet_id = db.Column(db.Integer, db.ForeignKey('inpatient_charge_sheets.id'), nullable=True)

    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, default=1.0)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoice = db.relationship('InpatientInvoice', back_populates='items')
    service = db.relationship('Service', foreign_keys=[service_id])
    charge_sheet = db.relationship('InpatientChargeSheet', foreign_keys=[charge_sheet_id])

    def __repr__(self):
        return f"<InvoiceItem {self.description} - {self.total}>"


# ─── Enhanced Invoice Model ──────────────────────────────────────────
class InpatientInvoice(db.Model):
    __tablename__ = 'inpatient_invoices'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), nullable=False)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)

    invoice_type = db.Column(db.String(20), default='final')

    subtotal = db.Column(db.Float, nullable=False, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    discount_type = db.Column(db.String(20))
    tax = db.Column(db.Float, default=0.0)
    tax_rate = db.Column(db.Float, default=0.0)
    grand_total = db.Column(db.Float, nullable=False)

    paid_amount = db.Column(db.Float, default=0.0)
    insurance_claim_amount = db.Column(db.Float, default=0.0)
    patient_payable = db.Column(db.Float, nullable=False)

    payment_status = db.Column(db.String(20), default='unpaid')
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    payment_date = db.Column(db.DateTime)
    payment_method = db.Column(db.String(50))

    # Denormalised patient info
    patient_name = db.Column(db.String(200))
    patient_reg_no = db.Column(db.String(64))
    patient_address = db.Column(db.String(255))
    patient_phone = db.Column(db.String(20))
    patient_insurance = db.Column(db.String(120))
    patient_insurance_no = db.Column(db.String(120))

    # Denormalised hospital info
    hospital_name = db.Column(db.String(255))
    hospital_address = db.Column(db.String(255))
    hospital_phone = db.Column(db.String(20))
    hospital_email = db.Column(db.String(120))

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to Admission – this creates the backref 'invoices' on InpatientAdmission
    admission = db.relationship('InpatientAdmission', back_populates='invoices')

    # Relationship to items (using back_populates)
    items = db.relationship('InpatientInvoiceItem', back_populates='invoice', lazy=True, cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        super(InpatientInvoice, self).__init__(**kwargs)
        if self.grand_total is None:
            self.grand_total = self.subtotal - self.discount + self.tax
        if self.patient_payable is None:
            self.patient_payable = self.grand_total - self.insurance_claim_amount - self.paid_amount

    def calculate_totals(self):
        self.subtotal = sum(item.total for item in self.items)
        self.grand_total = self.subtotal - self.discount + self.tax
        self.patient_payable = self.grand_total - self.insurance_claim_amount - self.paid_amount
        return self

    def add_item(self, description, unit_price, quantity=1, service_id=None, charge_sheet_id=None):
        total = unit_price * quantity
        item = InpatientInvoiceItem(
            invoice=self,   # ✅ use the relationship, not just the ID
            description=description,
            unit_price=unit_price,
            quantity=quantity,
            total=total,
            service_id=service_id,
            charge_sheet_id=charge_sheet_id
        )
        db.session.add(item)
        self.calculate_totals()
        return item

    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.grand_total}>"


class InpatientSHAClaim(db.Model):
    __tablename__ = 'inpatient_sha_claims'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), nullable=False)
    claim_number = db.Column(db.String(100), unique=True, nullable=False)
    amount_claimed = db.Column(db.Float, nullable=False)
    amount_approved = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='submitted')
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    approval_date = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==========================================
# 5. Ward Bed Shift (unchanged)
# ==========================================
class InpatientWardShift(db.Model):
    __tablename__ = 'inpatient_ward_shifts'
    __audit_trail__ = True
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('inpatient_admissions.id'), nullable=False)
    from_ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    from_bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'), nullable=True)
    to_ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    to_bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'), nullable=True)
    shift_date = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.Text)
    shifted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    from_ward = db.relationship('Ward', foreign_keys=[from_ward_id])
    from_bed = db.relationship('Bed', foreign_keys=[from_bed_id])
    to_ward = db.relationship('Ward', foreign_keys=[to_ward_id])
    to_bed = db.relationship('Bed', foreign_keys=[to_bed_id])
    shifted_by = db.relationship('User', foreign_keys=[shifted_by_id])
    
    
    
    
    
# ==========================================
# 0. Substore & Substore Inventory (NEW)
# ==========================================

class Substore(db.Model):
    __tablename__ = 'substores'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    store_type = db.Column(db.String(50), default='ward')  # ward, pharmacy, central, etc.
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    wards = db.relationship('Ward', backref='substore', lazy=True)
    inventory_items = db.relationship('SubstoreInventory', backref='substore', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Substore {self.name}>"


class SubstoreInventory(db.Model):
    __tablename__ = 'substore_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    substore_id = db.Column(db.Integer, db.ForeignKey('substores.id'), nullable=False)

    item_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)   # e.g., Medical Supplies, Equipment, Medications
    quantity = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(20), default='piece')
    expiry_date = db.Column(db.Date)
    supplier = db.Column(db.String(100))
    buying_price = db.Column(db.Float, nullable=False, default=0.0)
    selling_price = db.Column(db.Float, nullable=True)
    reorder_level = db.Column(db.Integer, default=5)
    low_stock_threshold = db.Column(db.Integer, default=5)
    manufacturer = db.Column(db.String(100))
    batch_number = db.Column(db.String(50))
    location = db.Column(db.String(100))
    storage_conditions = db.Column(db.String(100))

    # Optional link to Service (for billing/charging)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    service = db.relationship('Service', backref='substore_items')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def current_value(self):
        return self.quantity * self.buying_price

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    @property
    def valuation_at_cost(self):
        return (self.quantity or 0) * (self.buying_price or 0)

    @property
    def valuation_at_selling_price(self):
        return (self.quantity or 0) * (self.selling_price or 0)

    def __repr__(self):
        return f"<SubstoreInventory {self.item_name} (substore: {self.substore_id}, qty: {self.quantity})>"
    
    
    
    
# ==========================================
# 6. Inpatient Settings
# ==========================================

class InpatientSetting(db.Model):
    __tablename__ = 'inpatient_settings'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default='general')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<InpatientSetting {self.key}={self.value}>"


class WardBedFee(db.Model):
    __tablename__ = 'ward_bed_fees'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False, unique=True)
    admission_fee = db.Column(db.Float, nullable=False, default=0.0)
    daily_bed_fee = db.Column(db.Float, nullable=False, default=0.0)
    deposit_required = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ward = db.relationship('Ward', backref='bed_fee')

    def __repr__(self):
        return f"<WardBedFee {self.ward.name} - Admission: {self.admission_fee}, Daily: {self.daily_bed_fee}>"