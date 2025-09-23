from datetime import date, datetime, timedelta

from flask import current_app
from app.extensions import db
from app.patients.models import Service
from sqlalchemy.ext.hybrid import hybrid_property



class Sample(db.Model):
    __tablename__ = 'samples'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    sample_id = db.Column(db.String(20), unique=True, nullable=True, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('lab_tests.id'), nullable=False)

    # Sample details
    sample_type = db.Column(db.String(50), nullable=False)
    sample_quantity = db.Column(db.String(20))
    sample_condition = db.Column(db.String(50))

    # Collection details
    collection_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    collected_by = db.Column(db.String(50))
    collection_site = db.Column(db.String(50))
    collection_method = db.Column(db.String(50))
    collected_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Reception details
    received_by = db.Column(db.String(50))
    received_date = db.Column(db.DateTime, default=datetime.utcnow)
    brought_by = db.Column(db.String(50))
    transportation_mode = db.Column(db.String(50))

    # Origin details
    source_type = db.Column(db.String(20))
    source_department = db.Column(db.String(50))

    # Status tracking (This will now also reflect 'Accepted' or 'Rejected')
    status = db.Column(db.String(50), default='Collected', nullable=False) # Changed default to 'Collected' if that's initial state

    # --- New fields for Sample Verification Checklist ---
    # Overall sample acceptance status (will be 'Accepted' or 'Rejected')
    acceptance_status = db.Column(db.String(20), nullable=False, default='Pending Verification')

    # Rejection details (nullable, only filled if acceptance_status is 'Rejected')
    rejection_reason = db.Column(db.Text, nullable=True)
    person_notified = db.Column(db.String(100), nullable=True)
    patient_advice = db.Column(db.Text, nullable=True)

    # Individual checklist items (can be stored as booleans)
    checklist_enough_sample = db.Column(db.Boolean, default=False)
    checklist_correct_tube = db.Column(db.Boolean, default=False)
    checklist_valid_collection_time = db.Column(db.Boolean, default=False)
    checklist_labeling = db.Column(db.Boolean, default=False)
    checklist_integrity = db.Column(db.Boolean, default=False)
    # --- End new fields ---

    processing_notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    patient = db.relationship('Patient', backref='samples')
    test = db.relationship('LabTest', backref='samples')
    collector = db.relationship('User', foreign_keys=[collected_by_id])

    def __repr__(self):
        return f"<Sample {self.sample_id} ({self.sample_type}) for Test {self.test_id}>"


# Lab Inventory model
class LabInventory(db.Model):
    __tablename__ = 'lab_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Reagent, Consumable, Equipment
    quantity = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=5)
    expiry_date = db.Column(db.Date)
    supplier = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Equipment model
class LabEquipment(db.Model):
    __tablename__ = 'lab_equipments'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(50), unique=True)
    last_maintenance_date = db.Column(db.Date)
    next_maintenance_date = db.Column(db.Date)
    maintenance_frequency = db.Column(db.Integer)  # Days between maintenance
    status = db.Column(db.String(20), default='Active')  # Active, Maintenance, Retired

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --- Database Models ---
class UploadedFile(db.Model):
    __tablename__ = 'uploaded_files'  # Changed table name
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    # Foreign keys to link documents to specific maintenance records
    daily_log_entry_id = db.Column(db.Integer, db.ForeignKey('daily_log_entries.id'), nullable=True)
    scheduled_maintenance_log_id = db.Column(db.Integer, db.ForeignKey('scheduled_maintenance_logs.id'), nullable=True)

    def __repr__(self):
        return f"<UploadedFile {self.filename}>"

class DailyLogEntry(db.Model):
    __tablename__ = 'daily_log_entries'
    id = db.Column(db.Integer, primary_key=True)
    equipment = db.Column(db.String(100), nullable=False)
    disinfection_type = db.Column(db.String(100), nullable=True)
    concentration = db.Column(db.String(50), nullable=True)
    maintenance_notes = db.Column(db.Text, nullable=True)
    next_repair_date = db.Column(db.Date, nullable=True)
    qc_done = db.Column(db.Boolean, default=False)
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    # New field: Performed By
    performed_by = db.Column(db.String(100), nullable=True) # Added field
    # New fields for QC performed by
    qc_done_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    qc_done_by_name = db.Column(db.String(255), nullable=True) # To store the name fetched

    # Relationship to User model for QC
    qc_person = db.relationship('User', foreign_keys=[qc_done_by_id], backref='daily_qc_logs') # This backref is fine

    # Relationship to UploadedFile
    uploaded_file = db.relationship('UploadedFile', backref='daily_log_entry', lazy=True, uselist=False, primaryjoin="DailyLogEntry.id == UploadedFile.daily_log_entry_id")

    def __repr__(self):
        return f"<DailyLogEntry {self.equipment} on {self.submission_date.strftime('%Y-%m-%d')}>"

class ScheduledMaintenanceLog(db.Model):
    __tablename__ = 'scheduled_maintenance_logs'
    id = db.Column(db.Integer, primary_key=True)
    equipment = db.Column(db.String(100), nullable=False)
    maintenance_date = db.Column(db.Date, nullable=False)
    next_repair_date = db.Column(db.Date, nullable=True)
    troubleshooting = db.Column(db.Text, nullable=True)
    recommended_action = db.Column(db.Text, nullable=True)
    action_taken = db.Column(db.Text, nullable=True)
    labor_charges = db.Column(db.Float, nullable=True)
    spare_parts_cost = db.Column(db.Float, nullable=True)
    qc_done = db.Column(db.Boolean, default=False)
    qc_verification = db.Column(db.Text, nullable=True)
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    # New field: Performed By
    performed_by = db.Column(db.String(100), nullable=True) # Added field
    # New fields for QC performed by
    qc_done_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    qc_done_by_name = db.Column(db.String(255), nullable=True) # To store the name fetched

    # Relationship to User model for QC - CHANGED backref to be unique
    qc_person = db.relationship('User', foreign_keys=[qc_done_by_id], backref='scheduled_qc_logs')

    # Relationship to UploadedFile
    uploaded_file = db.relationship('UploadedFile', backref='scheduled_maintenance_log', lazy=True, uselist=False, primaryjoin="ScheduledMaintenanceLog.id == UploadedFile.scheduled_maintenance_log_id")

    def __repr__(self):
        return f"<ScheduledMaintenanceLog {self.equipment} on {self.maintenance_date.strftime('%Y-%m-%d')}>"

# --- End of Models ---

class QualityControl(db.Model):
    __tablename__ = 'quality_controls'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('laboratory_tests.test_id'), nullable=False)
    test_date = db.Column(db.DateTime, default=datetime.utcnow)
    result = db.Column(db.String(20), nullable=False)  # Pass, Fail, Warning
    comments = db.Column(db.Text)
    performed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Quality metrics
    standard_deviation = db.Column(db.Float)
    coefficient_variation = db.Column(db.Float)
    target_value = db.Column(db.Float)
    observed_value = db.Column(db.Float)
    tolerance_level = db.Column(db.Float)  # Acceptable percentage deviation
    
    # Equipment details
    instrument_id = db.Column(db.Integer, db.ForeignKey('lab_equipments.id'))
    next_qc_date = db.Column(db.Date) # Date for the next scheduled QC for this record's instrument/test

    # New column for uploaded file path
    testing_form_path = db.Column(db.String(255)) # Stores the relative path to the uploaded file
    
    # Compliance
    nabl_compliant = db.Column(db.Boolean, default=True)  # For Kenya accreditation
    corrective_actions = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    test = db.relationship('LaboratoryTest', backref='quality_controls')
    performer = db.relationship('User', foreign_keys=[performed_by])
    instrument = db.relationship('LabEquipment')
    
    # Calculated properties
    @property
    def deviation_percentage(self):
        """
        Calculates the percentage deviation between observed and target values.
        Returns 0 if target_value or observed_value is None.
        Returns float('inf') if target_value is 0 to avoid division by zero.
        """
        if self.target_value is not None and self.observed_value is not None:
            if self.target_value == 0:
                # You might want to handle this case more specifically, e.g., return "N/A"
                # For numerical calculation, infinity is mathematically correct for non-zero observed_value.
                return float('inf') if self.observed_value != 0 else 0 
            return round(abs(self.observed_value - self.target_value) / self.target_value * 100, 2)
        return None # Return None if data is incomplete

    @property
    def status_class(self):
        """
        Returns Tailwind CSS classes for the result status.
        """
        if self.result == 'Pass':
            return 'bg-green-100 text-green-800'
        elif self.result == 'Fail':
            return 'bg-red-100 text-red-800'
        return 'bg-yellow-100 text-yellow-800'

    @property
    def days_until_next_qc(self):
        """
        Calculates the number of days until the next scheduled QC date for this specific record.
        This is based on the 'next_qc_date' field of the QualityControl record itself.
        """
        if self.next_qc_date:
            today = date.today()
            delta = self.next_qc_date - today
            return delta.days
        return None # Return None if next_qc_date is not set
    


class BloodInventory(db.Model):
    __tablename__ = 'blood_inventory'
    __audit_trail__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(db.String(250), unique=True, nullable=False)
    # FIX: Increased length of blood_group to accommodate 'Unknown' or longer strings if needed
    blood_group = db.Column(db.String(20), nullable=False) # Uses ISBT 128 standards
    
    # Component Details
    component = db.Column(db.String(20), nullable=False, 
                          comment="Whole Blood, Platelets, Plasma, Cryoprecipitate")
    quantity = db.Column(db.Integer, nullable=False, 
                         comment="Volume in milliliters")
    
    # Date Management
    donation_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False, 
                            index=True, comment="Auto-calculated based on component")
    
    # Donor Information (supports both patients and external donors)
    donor_type = db.Column(db.String(10), default='Patient')  # 'Patient' or 'External'
    donor_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    # For external donors
    donor_full_name = db.Column(db.String(100)) # Changed from donor_name to donor_full_name to match form
    donor_contact = db.Column(db.String(20))
    donor_age = db.Column(db.Integer)
    donor_gender = db.Column(db.String(10)) # This field is not in your current form, but kept for model consistency
    donor_height = db.Column(db.Float) # New: Donor height
    donor_weight = db.Column(db.Float) # New: Donor weight in kgs
    amount_paid = db.Column(db.Float, default=0.0) # New: Amount paid for paid donors

    # Scanned Form Path
    # --- New Fields for Multiple Files ---
    donor_form_path = db.Column(db.String(255), nullable=True) # Path to the uploaded donor form
    screening_form_path = db.Column(db.String(255), nullable=True) # Path to the uploaded screening form    
    # Status Tracking
    # Added 'Waiting Screening' to choices
    STATUS_CHOICES = ['Available', 'Reserved', 'Transfused', 'Discarded', 'Expired', 'Waiting Screening']
    status = db.Column(db.String(20), default='Waiting Screening', index=True) # Default status changed
    
    # Staff Information
    received_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tested_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    stored_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Storage Information
    storage_location = db.Column(db.String(50), comment="Freezer/Shelf location")
    storage_temperature = db.Column(db.String(20)) # This field is not in your current form, but kept for model consistency
    
    # Audit Fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tested = db.Column(db.Boolean, default=False, comment="Screening completed")
    test_results = db.Column(db.Text, comment="Screening test results")
    
    # Calculated Properties
    @property
    def days_to_expire(self):
        # Ensure that comparison is between date objects
        return (self.expiry_date - datetime.utcnow().date()).days
    
    @property
    def is_expiring_soon(self):
        days = self.days_to_expire
        return 0 < days < 7
    
    # Relationships
    staff_received = db.relationship('User', foreign_keys=[received_by])
    staff_tested = db.relationship('User', foreign_keys=[tested_by])
    staff_stored = db.relationship('User', foreign_keys=[stored_by])
    patient_donor = db.relationship('Patient', foreign_keys=[donor_id])

    
    
# Lab Consumable Model (Detailed)
class LabConsumable(db.Model):
    __tablename__ = 'lab_consumables'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('laboratory_tests.test_id'), nullable=False)
    inventory_id = db.Column(db.Integer, db.ForeignKey('lab_inventory.id'), nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False, default=1)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 🔗 Relationships
    test = db.relationship("LaboratoryTest", backref=db.backref("consumables", lazy="dynamic"))
    inventory_item = db.relationship("LabInventory", backref=db.backref("consumable_links", lazy="dynamic"))

# Association Table: Lab Test to Consumables
test_consumables = db.Table('test_consumables',
    db.Column('test_id', db.Integer, db.ForeignKey('services.id'), primary_key=True),
    db.Column('consumable_id', db.Integer, db.ForeignKey('lab_consumables.id'), primary_key=True),
    db.Column('quantity_used', db.Float, nullable=False, default=1.0),
    db.Column('is_optional', db.Boolean, default=False)
)

# Add relationship to Service model
Service.consumables = db.relationship(
    'LabConsumable',
    secondary=test_consumables,
    backref=db.backref('tests', lazy='dynamic'),
    lazy='dynamic'
)





from sqlalchemy import CheckConstraint, ForeignKey, Interval
from sqlalchemy.orm import relationship


class LaboratoryTest(db.Model):
    __tablename__ = 'laboratory_tests'

    test_id = db.Column(db.Integer, primary_key=True)
    test_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    sample_type = db.Column(db.String(50), nullable=False)
    short_code = db.Column(db.String(20))
    device_manufacturer = db.Column(db.String(100))
    turnaround_time = db.Column(db.BigInteger)
    is_active = db.Column(db.Boolean, default=True)
    loinc_code = db.Column(db.String(10))
    price = db.Column(db.Float, nullable=False, default=0.0)

    parameters = relationship('TestParameter', back_populates='test', cascade='all, delete-orphan')
    panels = relationship('PanelTest', back_populates='test', cascade='all, delete-orphan')
    service = db.relationship('Service', back_populates='lab_test', uselist=False)

    @property
    def turnaround_timedelta(self):
        if self.turnaround_time is not None:
            return datetime.timedelta(minutes=self.turnaround_time) # Use datetime.timedelta
        return None

#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestParameter(db.Model):
    __tablename__ = 'test_parameters'

    parameter_id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, ForeignKey('laboratory_tests.test_id', ondelete='CASCADE'), nullable=False)
    parameter_name = db.Column(db.String(100), nullable=False)
    synonym = db.Column(db.String(100))
    unit = db.Column(db.String(20))
    result_type = db.Column(db.String(20), nullable=False)

    test = relationship('LaboratoryTest', back_populates='parameters')
    ranges = relationship('ParameterRange', back_populates='parameter', cascade='all, delete-orphan')
    options = relationship('ParameterOption', back_populates='parameter', cascade='all, delete-orphan')
    # ADD THIS LINE: Define the 'results' relationship back to LabTestResult
    results = relationship('LabTestResult', back_populates='parameter', cascade='all, delete-orphan') # Added

    __table_args__ = (
        CheckConstraint(
            "result_type IN ('numeric', 'categorical', 'text')",
            name='valid_result_type'
        ),
    )

#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class ParameterRange(db.Model):
    __tablename__ = 'parameter_ranges'

    range_id = db.Column(db.Integer, primary_key=True)
    parameter_id = db.Column(db.Integer, ForeignKey('test_parameters.parameter_id', ondelete='CASCADE'), nullable=False)
    age_min = db.Column(db.Integer, default=0)
    age_max = db.Column(db.Integer, default=120)
    age_unit = db.Column(db.String(10), default='years')
    sex = db.Column(db.String(10))
    normal_min = db.Column(db.Numeric(12, 4))
    normal_max = db.Column(db.Numeric(12, 4))
    critical_min = db.Column(db.Numeric(12, 4))
    critical_max = db.Column(db.Numeric(12, 4))

    parameter = relationship('TestParameter', back_populates='ranges')

    __table_args__ = (
        CheckConstraint(
            "sex IN ('any', 'male', 'female')",
            name='valid_sex'
        ),
        CheckConstraint(
            "age_unit IN ('years', 'months', 'days')",
            name='valid_age_unit'
        ),
    )

#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class ParameterOption(db.Model):
    __tablename__ = 'parameter_options'

    option_id = db.Column(db.Integer, primary_key=True)
    parameter_id = db.Column(db.Integer, ForeignKey('test_parameters.parameter_id', ondelete='CASCADE'), nullable=False)
    option_value = db.Column(db.String(50), nullable=False)
    option_code = db.Column(db.String(10))

    parameter = relationship('TestParameter', back_populates='options')

#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestPanel(db.Model):
    __tablename__ = 'test_panels'

    panel_id = db.Column(db.Integer, primary_key=True)
    panel_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    tests = relationship('PanelTest', back_populates='panel', cascade='all, delete-orphan')

#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class PanelTest(db.Model):
    __tablename__ = 'panel_tests'

    panel_id = db.Column(db.Integer, ForeignKey('test_panels.panel_id', ondelete='CASCADE'), primary_key=True)
    test_id = db.Column(db.Integer, ForeignKey('laboratory_tests.test_id', ondelete='CASCADE'), primary_key=True)

    panel = relationship('TestPanel', back_populates='tests')
    test = relationship('LaboratoryTest', back_populates='panels')

#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class LabTestResult(db.Model):
    __tablename__ = 'lab_test_results'

    result_id = db.Column(db.Integer, primary_key=True)

    lab_test_id = db.Column(db.Integer, db.ForeignKey('lab_tests.id', ondelete='CASCADE'), nullable=False)
    lab_test_order = relationship('LabTest', back_populates='results_detail')

    parameter_id = db.Column(db.Integer, db.ForeignKey('test_parameters.parameter_id', ondelete='CASCADE'), nullable=False)
    parameter = relationship('TestParameter', back_populates='results') # This back_populates requires 'results' on TestParameter

    numeric_value = db.Column(db.Numeric(12, 4), nullable=True)
    categorical_value = db.Column(db.String(255), nullable=True)
    text_value = db.Column(db.Text, nullable=True)

    unit = db.Column(db.String(20))
    interpretation = db.Column(db.String(50))
    comments = db.Column(db.Text)
    result_date = db.Column(db.DateTime, default=datetime.utcnow)
    entered_by = db.Column(db.String(100))
    entered_at = db.Column(db.DateTime, default=datetime.utcnow) 

    verified_by = db.Column(db.String(100), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        CheckConstraint("NOT (numeric_value IS NOT NULL AND categorical_value IS NOT NULL)", name='check_numeric_categorical_mutually_exclusive'),
        CheckConstraint("NOT (numeric_value IS NOT NULL AND text_value IS NOT NULL)", name='check_numeric_text_mutually_exclusive'),
        CheckConstraint("NOT (categorical_value IS NOT NULL AND text_value IS NOT NULL)", name='check_categorical_text_mutually_exclusive'),
        CheckConstraint("numeric_value IS NOT NULL OR categorical_value IS NOT NULL OR text_value IS NOT NULL", name='check_at_least_one_result_populated'),
    )

    def __repr__(self):
        return f"<LabTestResult {self.result_id} for {self.parameter.parameter_name} of LabTest {self.lab_test_id}>"
