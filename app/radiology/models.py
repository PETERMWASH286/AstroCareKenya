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
    low_stock_threshold = db.Column(db.Integer, default=5)   # 👈 add this

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)




class RadiologyDailyLogEntry(db.Model):
    __tablename__ = 'radiology_daily_log_entries'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    equipment = db.Column(db.String(100), nullable=False)
    disinfection_type = db.Column(db.String(100), nullable=True)
    concentration = db.Column(db.String(50), nullable=True)
    maintenance_notes = db.Column(db.Text, nullable=True)
    next_repair_date = db.Column(db.Date, nullable=True)
    qc_done = db.Column(db.Boolean, default=False)
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)

    performed_by = db.Column(db.String(100), nullable=True)

    # QC Fields
    qc_done_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    qc_done_by_name = db.Column(db.String(255), nullable=True)

    qc_person = db.relationship(
        'User',
        foreign_keys=[qc_done_by_id],
        backref='radiology_daily_qc_logs'
    )

    uploaded_file = db.relationship(
        'UploadedFile',
        backref='radiology_daily_log_entry',
        lazy=True,
        uselist=False,
        primaryjoin="RadiologyDailyLogEntry.id == UploadedFile.radiology_daily_log_entry_id"
    )

    def __repr__(self):
        return f"<RadiologyDailyLogEntry {self.equipment} on {self.submission_date.strftime('%Y-%m-%d')}>"


class RadiologyScheduledMaintenanceLog(db.Model):
    __tablename__ = 'radiology_scheduled_maintenance_logs'
    __audit_trail__ = True

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

    performed_by = db.Column(db.String(100), nullable=True)

    # QC Fields
    qc_done_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    qc_done_by_name = db.Column(db.String(255), nullable=True)

    qc_person = db.relationship(
        'User',
        foreign_keys=[qc_done_by_id],
        backref='radiology_scheduled_qc_logs'
    )

    uploaded_file = db.relationship(
        'UploadedFile',
        backref='radiology_scheduled_maintenance_log',
        lazy=True,
        uselist=False,
        primaryjoin="RadiologyScheduledMaintenanceLog.id == UploadedFile.radiology_scheduled_maintenance_log_id"
    )

    def __repr__(self):
        return f"<RadiologyScheduledMaintenanceLog {self.equipment} on {self.maintenance_date.strftime('%Y-%m-%d')}>"



# Equipment model
class RadiologyEquipment(db.Model):
    __tablename__ = 'radiology_equipments'
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
    
    
    
class RadiologyQualityControl(db.Model):
    __tablename__ = 'radiology_quality_controls'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('radiology_equipments.id'), nullable=False)
    test_date = db.Column(db.DateTime, default=datetime.utcnow)
    result = db.Column(db.String(20), nullable=False)  # Pass, Fail, Warning
    comments = db.Column(db.Text)
    performed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # QC metrics
    radiation_dose = db.Column(db.Float)   # Example: measured dose
    reference_dose = db.Column(db.Float)   # Example: expected/target dose
    tolerance_level = db.Column(db.Float)  # Acceptable deviation %

    # Next QC date
    next_qc_date = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    equipment = db.relationship('RadiologyEquipment', backref='quality_controls')
    performer = db.relationship('User', foreign_keys=[performed_by])

    @property
    def deviation_percentage(self):
        if self.reference_dose and self.radiation_dose:
            return round(abs(self.radiation_dose - self.reference_dose) / self.reference_dose * 100, 2)
        return None

    @property
    def status_class(self):
        if self.result == 'Pass':
            return 'bg-green-100 text-green-800'
        elif self.result == 'Fail':
            return 'bg-red-100 text-red-800'
        return 'bg-yellow-100 text-yellow-800'

    @property
    def days_until_next_qc(self):
        if self.next_qc_date:
            return (self.next_qc_date - date.today()).days
        return None
