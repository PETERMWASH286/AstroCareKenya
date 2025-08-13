from datetime import datetime
from app.extensions import db
from enum import Enum as PyEnum

class AssetCategory(db.Model):
    __tablename__ = 'asset_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    depreciation_period = db.Column(db.Integer, default=5)  # Years
    # Removed backref to avoid conflict
    assets = db.relationship('Asset', back_populates='category', lazy=True)
    
    def __repr__(self):
        return f'<AssetCategory {self.name}>'

class AssetStatus(PyEnum):
    OPERATIONAL = 'Operational'
    UNDER_MAINTENANCE = 'Under Maintenance'
    OUT_OF_SERVICE = 'Out of Service'
    DECOMMISSIONED = 'Decommissioned'
    RETIRED = 'Retired'
    LOST = 'Lost'
    STOLEN = 'Stolen'

class Technician(db.Model):
    __tablename__ = 'technicians'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    employee_id = db.Column(db.String(50), unique=True)
    specialization = db.Column(db.String(100))
    contact_number = db.Column(db.String(20))
    email = db.Column(db.String(120))
    hire_date = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
    
    maintenance_records = db.relationship('MaintenanceRecord', backref='technician', lazy=True)
    
    def __repr__(self):
        return f'<Technician {self.name} ({self.employee_id})>'

class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    serial_number = db.Column(db.String(100), unique=True)
    barcode = db.Column(db.String(100), unique=True)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    purchase_price = db.Column(db.Float, nullable=False)
    current_value = db.Column(db.Float)
    depreciation_rate = db.Column(db.Float, default=10.0)  # Annual depreciation percentage
    warranty_expiry = db.Column(db.DateTime)
    status = db.Column(db.Enum(AssetStatus), default=AssetStatus.OPERATIONAL.value)
    location = db.Column(db.String(200))
    notes = db.Column(db.Text)
    
    # Relationships
    category_id = db.Column(db.Integer, db.ForeignKey('asset_categories.id'), nullable=False)
    category = db.relationship('AssetCategory', back_populates='assets')  # Fixed relationship
    
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    department = db.relationship('Department', backref='assets')  # Relationship to Department
    
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_to = db.relationship('User', backref='assigned_assets')  # Relationship to User
    
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    supplier = db.relationship('Supplier', backref='supplied_assets')  # Relationship to Supplier
    
    # Backrefs
    maintenance_records = db.relationship('MaintenanceRecord', backref='asset', lazy=True)
    depreciation_history = db.relationship('DepreciationRecord', backref='asset', lazy=True)
    
    def __repr__(self):
        return f'<Asset {self.name} ({self.serial_number})>'
    
    def calculate_current_value(self):
        """Calculate current value based on depreciation"""
        if not self.purchase_date:
            return self.purchase_price
        
        years_owned = (datetime.utcnow() - self.purchase_date).days / 365.25
        depreciation_factor = (1 - (self.depreciation_rate / 100)) ** years_owned
        return round(self.purchase_price * depreciation_factor, 2)

class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    maintenance_date = db.Column(db.DateTime, default=datetime.utcnow)
    next_maintenance_date = db.Column(db.DateTime)
    cost = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)
    maintenance_type = db.Column(db.String(50))  # Preventive, Corrective, Predictive
    technician_id = db.Column(db.Integer, db.ForeignKey('technicians.id'), nullable=False)
    notes = db.Column(db.Text)
    parts_replaced = db.relationship('ReplacedPart', backref='maintenance_record', lazy=True)
    
    def __repr__(self):
        return f'<MaintenanceRecord for Asset {self.asset_id} on {self.maintenance_date}>'

class ReplacedPart(db.Model):
    __tablename__ = 'replaced_parts'
    id = db.Column(db.Integer, primary_key=True)
    maintenance_id = db.Column(db.Integer, db.ForeignKey('maintenance_records.id'), nullable=False)
    part_name = db.Column(db.String(200), nullable=False)
    part_number = db.Column(db.String(100))
    cost = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    supplier = db.relationship('Supplier', backref='supplied_parts')  # Relationship to Supplier
    
    def __repr__(self):
        return f'<ReplacedPart {self.part_name} for Maintenance {self.maintenance_id}>'

class DepreciationRecord(db.Model):
    __tablename__ = 'depreciation_records'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    record_date = db.Column(db.DateTime, default=datetime.utcnow)
    value = db.Column(db.Float, nullable=False)
    depreciation_amount = db.Column(db.Float, nullable=False)
    
    def __repr__(self):
        return f'<DepreciationRecord for Asset {self.asset_id} on {self.record_date}>'

class AssetAssignmentHistory(db.Model):
    __tablename__ = 'asset_assignment_history'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignment_date = db.Column(db.DateTime, default=datetime.utcnow)
    return_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    
    # Relationships
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])
    
    def __repr__(self):
        return f'<AssetAssignmentHistory Asset {self.asset_id} to User {self.assigned_to_id}>'