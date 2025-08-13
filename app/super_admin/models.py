# app/super_admin/models.py

from sqlalchemy import JSON
from app.extensions import db

class Hospital(db.Model):
    __tablename__ = 'hospitals'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(128), nullable=False, unique=True)
    subdomain  = db.Column(db.String(64), nullable=False, unique=True)
    db_uri     = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class HospitalProfile(db.Model):
    __tablename__ = 'hospital_profiles'
    id = db.Column(db.Integer, primary_key=True)
    
    # Core Identification
    name = db.Column(db.String(128), nullable=True, unique=True)
    display_name = db.Column(db.String(128))
    tagline = db.Column(db.String(256))
    motto = db.Column(db.String(256))
    slogan = db.Column(db.String(256))
    vision = db.Column(db.Text)
    mission = db.Column(db.Text)
    logo_url = db.Column(db.String(255))
    
    # Contact & Location Details
    address_line1 = db.Column(db.String(128))
    address_line2 = db.Column(db.String(128))
    location = db.Column(db.String(128))
    city = db.Column(db.String(64))
    county = db.Column(db.String(64))
    constituency = db.Column(db.String(64))
    ward = db.Column(db.String(64))
    state = db.Column(db.String(64))
    country = db.Column(db.String(64), default='Kenya')
    postal_code = db.Column(db.String(20))
    primary_contact = db.Column(db.String(20))
    secondary_contact = db.Column(db.String(20))
    emergency_contact = db.Column(db.String(20))
    email = db.Column(db.String(120))
    website = db.Column(db.String(255))
    
    # Domain Configuration
    subdomain = db.Column(db.String(64), unique=True, nullable=True)
    db_url = db.Column(db.String(255), nullable=True)
    
    # Operational Details
    hospital_type = db.Column(db.String(50))
    bed_capacity = db.Column(db.Integer)
    established_date = db.Column(db.Date)
    operating_hours = db.Column(JSON)
    accreditation = db.Column(db.String(128))
    
    # Kenya-Specific Registration Details
    hospital_reg_no = db.Column(db.String(50), unique=True)  # MOH Registration Number
    kra_pin = db.Column(db.String(11), unique=True)  # KRA PIN (format: A123456789X)
    nhif_no = db.Column(db.String(20))  # NHIF Facility Code
    nssf_no = db.Column(db.String(20))  # NSSF Registration Number
    business_permit_no = db.Column(db.String(50))  # County Government Business Permit
    practice_license_no = db.Column(db.String(50))  # Medical Practitioners Board License
    pharmacy_license_no = db.Column(db.String(50))  # Pharmacy and Poisons Board License
    radiation_board_no = db.Column(db.String(50))  # Radiation Protection Board License
    waste_license_no = db.Column(db.String(50))  # NEMA Waste Management License
    
    # Compliance Dates
    reg_certificate_issue = db.Column(db.Date)  # MOH Certificate Issue Date
    reg_certificate_expiry = db.Column(db.Date)  # MOH Certificate Expiry
    license_renewal_date = db.Column(db.Date)  # Annual License Renewal Date
    
    # Organizational Identity
    core_values = db.Column(JSON)
    strategic_goals = db.Column(JSON)
    
    # Additional Metadata
    description = db.Column(db.Text)
    specialties = db.Column(JSON)
    amenities = db.Column(JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    last_updated = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())