# app/user_management/models.py
from app.extensions import db
from datetime import datetime

# Privilege join tables
role_privileges = db.Table('role_privileges',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id')),
    db.Column('privilege_id', db.Integer, db.ForeignKey('privileges.id'))
)

user_privileges = db.Table('user_privileges',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('privilege_id', db.Integer, db.ForeignKey('privileges.id'))
)

class Privilege(db.Model):
    __tablename__ = 'privileges'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, index=True)  # e.g., 'create_user'
    module = db.Column(db.String(40), index=True)          # e.g., 'User Management'
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Privilege {self.module}.{self.name}>"

class UserProfile(db.Model):
    __tablename__ = 'user_profiles'
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    # Add profile fields here (address, phone, etc.)
    # ...


class Department(db.Model):
    __tablename__ = 'departments'
    __audit_trail__ = True  # Enable auditing

    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    def __repr__(self):
        return f"<Department {self.name}>"
    



from datetime import datetime
class EmployeeBio(db.Model):
    __tablename__ = 'employee_bios'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    dob = db.Column(db.Date, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    nationality = db.Column(db.String(100), nullable=True)
    national_id = db.Column(db.String(64), nullable=True, index=True)
    passport_number = db.Column(db.String(64), nullable=True)
    gender = db.Column(db.Enum('Male','Female','Other', name='gender_enum'), nullable=True)
    marital_status = db.Column(db.Enum('Single','Married','Divorced','Widowed', name='marital_enum'), nullable=True)
    blood_type = db.Column(db.String(5), nullable=True)
    bank_name = db.Column(db.String(128), nullable=True)
    bank_branch = db.Column(db.String(128), nullable=True)
    bank_account_number = db.Column(db.String(64), nullable=True)
    bank_routing_number = db.Column(db.String(64), nullable=True)
    tax_id = db.Column(db.String(64), nullable=True)
    social_security_number = db.Column(db.String(64), nullable=True)
    emergency_contact_name = db.Column(db.String(128), nullable=True)
    emergency_contact_relationship = db.Column(db.String(64), nullable=True)
    emergency_contact_phone = db.Column(db.String(32), nullable=True)
    insurance_provider = db.Column(db.String(128), nullable=True)
    insurance_number = db.Column(db.String(64), nullable=True)
    medical_conditions = db.Column(db.Text, nullable=True)
    allergies = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('bio', uselist=False))
    educations = db.relationship('EmployeeEducation', backref='bio', lazy=True, cascade='all, delete-orphan')
    relatives = db.relationship('EmployeeRelative', backref='bio', lazy=True, cascade='all, delete-orphan')
    work_histories = db.relationship('EmployeeWorkHistory', backref='bio', lazy=True, cascade='all, delete-orphan')
    certifications = db.relationship('EmployeeCertification', backref='bio', lazy=True, cascade='all, delete-orphan')
    attachments = db.relationship('BioAttachment', backref='bio', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<EmployeeBio for user_id={self.user_id}>"

class EmployeeEducation(db.Model):
    __tablename__ = 'employee_educations'
    id = db.Column(db.Integer, primary_key=True)
    bio_id = db.Column(db.Integer, db.ForeignKey('employee_bios.id'), nullable=False)
    institution = db.Column(db.String(255), nullable=False)
    degree = db.Column(db.String(128), nullable=False)
    field_of_study = db.Column(db.String(128), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    grade = db.Column(db.String(20), nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_current = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmployeeRelative(db.Model):
    __tablename__ = 'employee_relatives'
    id = db.Column(db.Integer, primary_key=True)
    bio_id = db.Column(db.Integer, db.ForeignKey('employee_bios.id'), nullable=False)
    full_name = db.Column(db.String(128), nullable=False)
    relationship = db.Column(db.String(64), nullable=False)  # e.g., Spouse, Child, Parent
    date_of_birth = db.Column(db.Date, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    occupation = db.Column(db.String(128), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    is_emergency_contact = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmployeeWorkHistory(db.Model):
    __tablename__ = 'employee_work_histories'
    id = db.Column(db.Integer, primary_key=True)
    bio_id = db.Column(db.Integer, db.ForeignKey('employee_bios.id'), nullable=False)
    company = db.Column(db.String(255), nullable=False)
    position = db.Column(db.String(128), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    responsibilities = db.Column(db.Text, nullable=True)
    achievements = db.Column(db.Text, nullable=True)
    is_current = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmployeeCertification(db.Model):
    __tablename__ = 'employee_certifications'
    id = db.Column(db.Integer, primary_key=True)
    bio_id = db.Column(db.Integer, db.ForeignKey('employee_bios.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    issuing_organization = db.Column(db.String(255), nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    expiration_date = db.Column(db.Date, nullable=True)
    credential_id = db.Column(db.String(128), nullable=True)
    credential_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BioAttachment(db.Model):
    __tablename__ = 'bio_attachments'
    id = db.Column(db.Integer, primary_key=True)
    bio_id = db.Column(db.Integer, db.ForeignKey('employee_bios.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)