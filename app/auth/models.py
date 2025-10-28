# app/auth/models.py

from flask import url_for
from app.extensions import db, bcrypt # Import db and bcrypt from extensions
from datetime import datetime
# ADDED: Import UserMixin from Flask-Login
from flask_login import UserMixin

from app.notifications.models import Notification, NotificationRead
# from flask_jwt_extended import get_jwt_identity # Useful for user loader (if needed for JWT)


# Using a many-to-many relationship for User and Role
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    # CORRECTED: Reference the actual table name 'roles' instead of 'role'
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)

class Permission: # Using a class for constants
    CAN_VIEW_DASHBOARD = 0x01 # 1
    CAN_REGISTER_PATIENT = 0x02 # 2
    CAN_RECORD_VITALS = 0x04 # 4
    CAN_WRITE_PRESCRIPTIONS = 0x08 # 8
    CAN_SCHEDULE_APPOINTMENTS = 0x10 # 16
    CAN_MANAGE_BILLING = 0x20 # 32
    CAN_DISPENSE_MEDICATION = 0x40 # 64
    CAN_ORDER_LAB_TEST = 0x80 # 128
    CAN_VIEW_LAB_RESULTS = 0x100 # 256
    CAN_ORDER_IMAGING = 0x200 # 512
    CAN_VIEW_IMAGING_REPORTS = 0x400 # 1024
    CAN_VIEW_OWN_RECORD = 0x800 # 2048  <-- This one is crucial and was missing/different
    CAN_VIEW_REPORTS = 0x1000 # 4096
    CAN_MANAGE_USERS = 0x2000 # 8192
    CAN_MANAGE_ROLES = 0x4000 # 16384
    CAN_ADMINISTER_SYSTEM = 0x8000 # 32768 # God mode

    @staticmethod
    def all_permissions():
        """Returns a sum of all permission bits."""
        # Iterate through the class attributes and sum integer values
        return sum(v for k, v in Permission.__dict__.items() if isinstance(v, int))

class Role(db.Model):
    __tablename__ = 'roles' # Ensure tablename is set
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer, default=0) # Bitmap for permissions

    # Relationship to link roles to users
    users = db.relationship('User', secondary=user_roles, backref=db.backref('roles', lazy='dynamic'))
    # ADD THIS: Relationship to privileges (many-to-many)
    privileges = db.relationship(
        'Privilege',
        secondary='role_privileges',
        backref=db.backref('roles', lazy='dynamic')
    )

    def __repr__(self):
        return f"<Role {self.name}>"

    def add_permission(self, perm):
        self.permissions |= perm

    def remove_permission(self, perm):
        self.permissions &= ~perm

    def reset_permissions(self):
        self.permissions = 0

    def has_permission(self, perm):
        return self.permissions & perm == perm

    @staticmethod
    def insert_roles():
        """Inserts default roles and their permissions into the database."""
        # ADDED: Debug print to inspect Permission object just before use
        # print(f"--- DEBUG: Inside insert_roles. Permission object: {Permission}")
        # print(f"--- DEBUG: Permission.__dict__: {Permission.__dict__}")


        roles_data = {
            'Patient': (Permission.CAN_VIEW_OWN_RECORD | Permission.CAN_VIEW_DASHBOARD, True), # Added dashboard view for patients
            'Registration': (Permission.CAN_VIEW_OWN_RECORD | Permission.CAN_REGISTER_PATIENT | Permission.CAN_SCHEDULE_APPOINTMENTS | Permission.CAN_VIEW_DASHBOARD, False), # Added dashboard view
            'Nurse': (Permission.CAN_VIEW_OWN_RECORD | Permission.CAN_RECORD_VITALS | Permission.CAN_SCHEDULE_APPOINTMENTS | Permission.CAN_VIEW_LAB_RESULTS | Permission.CAN_VIEW_IMAGING_REPORTS | Permission.CAN_VIEW_DASHBOARD, False), # Added dashboard view
            'Doctor': (Permission.CAN_VIEW_OWN_RECORD | Permission.CAN_RECORD_VITALS | Permission.CAN_WRITE_PRESCRIPTIONS | Permission.CAN_SCHEDULE_APPOINTMENTS | Permission.CAN_ORDER_LAB_TEST | Permission.CAN_VIEW_LAB_RESULTS | Permission.CAN_ORDER_IMAGING | Permission.CAN_VIEW_IMAGING_REPORTS | Permission.CAN_VIEW_REPORTS | Permission.CAN_VIEW_DASHBOARD, False), # Added dashboard view
            'Pharmacist': (Permission.CAN_DISPENSE_MEDICATION | Permission.CAN_VIEW_OWN_RECORD | Permission.CAN_VIEW_REPORTS | Permission.CAN_VIEW_DASHBOARD, False), # Added dashboard view
            'Lab Tech': (Permission.CAN_ORDER_LAB_TEST | Permission.CAN_VIEW_LAB_RESULTS | Permission.CAN_VIEW_REPORTS | Permission.CAN_VIEW_DASHBOARD, False), # Added dashboard view
            'Radiologist': (Permission.CAN_ORDER_IMAGING | Permission.CAN_VIEW_IMAGING_REPORTS | Permission.CAN_VIEW_REPORTS | Permission.CAN_VIEW_DASHBOARD, False), # Added dashboard view
            'Billing Officer': (Permission.CAN_MANAGE_BILLING | Permission.CAN_VIEW_REPORTS | Permission.CAN_VIEW_DASHBOARD, False), # Added dashboard view
            'Admin': (Permission.all_permissions() | Permission.CAN_VIEW_DASHBOARD, False) # Admin gets all permissions + dashboard view
        }
        # Set 'Patient' as the default role
        default_role_name = 'Patient'

        for r_name, (r_permissions, r_default) in roles_data.items():
            role = Role.query.filter_by(name=r_name).first()
            if role is None:
                role = Role(name=r_name)
            role.permissions = r_permissions
            role.default = (r_name == default_role_name) # Set default flag based on name
            db.session.add(role)
        db.session.commit()


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    __audit_trail__ = True  # Enable auditing
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('activity_logs', lazy='dynamic'))
    
    def __repr__(self):
        return f'<ActivityLog {self.activity_type} by User {self.user_id}>'

# UPDATED: User model inherits from UserMixin
class User(UserMixin, db.Model):
    __tablename__ = 'user' # Changed to lowercase 'user' for consistency
    __audit_trail__ = True  # Enable auditing

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # Use utcnow for timezone-naive consistency if needed
    last_login_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True) # Added is_active column
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    profile_image = db.Column(db.String(255), nullable=True)
    is_super_admin = db.Column(db.Boolean, default=False)  # Add this field

    # Define a relationship to UserProfile if you have one in user_management.models
    # profile = db.relationship('UserProfile', backref='user', uselist=False)
    department    = db.relationship('Department', backref='users')

    # many-to-many to Role...
    privileges = db.relationship(
        'Privilege',
        secondary='user_privileges',
        backref=db.backref('users', lazy='dynamic')
    )
    # Update relationships with unique backref names
    requested_stock = db.relationship(
        'StockRequest', 
        foreign_keys='StockRequest.requester_id', 
        backref='requester_user'
    )
    approved_stock = db.relationship(
        'StockRequest', 
        foreign_keys='StockRequest.approver_id', 
        backref='approver_user'
    )
    issued_stock = db.relationship(
        'StockRequest', 
        foreign_keys='StockRequest.issued_by', 
        backref='issuer_user'
    )
        # Add this relationship
    two_factor_methods = db.relationship(
        'TwoFactorMethod', 
        back_populates='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    @property
    def requires_2fa(self):
        """Check if user has enabled 2FA"""
        return self.two_factor_methods.filter_by(
            is_primary=True, 
            verified=True
        ).count() > 0
    
    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        # Assign default role if user is new and has no roles yet
        # Use list(self.roles) to trigger loading the dynamic relationship
        if not self.roles.count(): # Check if the dynamic query returns 0
            default_role = Role.query.filter_by(default=True).first()
            if default_role:
                self.roles.append(default_role)
                # db.session.add(self) # Add the user back to the session if roles were modified after creation
                # db.session.commit() # Commit the role assignment if needed immediately


    def __repr__(self):
        # Improved representation for debugging
        # Access roles carefully as it's a dynamic relationship
        role_names = ", ".join([role.name for role in self.roles.all()]) if self.roles.count() > 0 else "None"
        return f'<User {self.username} (ID: {self.id}, Roles: {role_names})>'

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def can(self, permissions):
        """Check if the user has a given set of permissions."""
        if not self.is_active:
            return False
        # Check if ANY of the user's roles have ALL the required permissions
        # Use .all() to execute the dynamic relationship query
        for role in self.roles.all():
             if role.has_permission(permissions):
                 return True
        return False
    def has_privilege(self, privilege_name: str) -> bool:
        # 1. Check direct user privileges (iterate over the list)
        for p in self.privileges:
            if p.name == privilege_name:
                return True

        # 2. Check each role’s list of privileges
        for role in self.roles:
            for rp in role.privileges:
                if rp.name == privilege_name:
                    return True

        return False
    # Use strings for relationships
    read_notifications = db.relationship(
        'NotificationRead', 
        back_populates='user',
        lazy='dynamic'
    )
    
    @property
    def unread_notifications(self):
        from app.notifications.models import NotificationRead
        return NotificationRead.query.filter_by(
            user_id=self.id, 
            read_at=None
        ).count()
    
    @property
    def recent_notifications(self):
        from app.notifications.models import Notification, NotificationRead
        return (
            db.session.query(Notification)
            .join(NotificationRead, Notification.id == NotificationRead.notification_id)
            .filter(NotificationRead.user_id == self.id)
            .order_by(Notification.created_at.desc())
            .limit(10)
            .all()
        )
    @property
    def departments(self):
        """Get user's departments - since user belongs to one department, return list with that department"""
        from app.user_management.models import Department
        if self.department_id:
            dept = Department.query.get(self.department_id)
            return [dept] if dept else []
        return []
    def is_administrator(self):
        """Convenience method to check if user has the Admin role."""
        # Check if the user has the Admin role by name
        # Use .all() to execute the dynamic relationship query
        admin_role = Role.query.filter_by(name='Admin').first()
        return admin_role in self.roles.all() if admin_role else False

    def log_activity(self, description, activity_type, request=None):
        """Log user activity"""
        try:
            activity = ActivityLog(
                user_id=self.id,
                activity_type=activity_type,
                description=description,
                ip_address=request.remote_addr if request else None,
                user_agent=request.headers.get('User-Agent') if request else None
            )
            db.session.add(activity)
            db.session.commit()
            return activity
        except Exception as e:
            db.session.rollback()
            print(f"Error logging activity: {e}")
            return None
        
class BlogPost(db.Model):
    __tablename__ = 'blog_posts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, published, archived
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    department = db.relationship('Department', backref=db.backref('blog_posts', lazy=True))
    author = db.relationship('User', backref=db.backref('blog_posts', lazy=True))

class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    document_type = db.Column(db.String(50))  # policy, procedure, form, etc.
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    department = db.relationship('Department', backref=db.backref('documents', lazy=True))
    uploader = db.relationship('User', backref=db.backref('documents', lazy=True))



# Add to models.py
class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blog_post_id = db.Column(db.Integer, db.ForeignKey('blog_posts.id'))
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('comments', lazy=True))
    blog_post = db.relationship('BlogPost', backref=db.backref('comments', lazy=True, order_by='Comment.created_at.desc()'))
    document = db.relationship('Document', backref=db.backref('comments', lazy=True, order_by='Comment.created_at.desc()'))


class TwoFactorMethod(db.Model):
    __tablename__ = 'two_factor_methods'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    method = db.Column(db.String(20), nullable=False)  # 'email', 'sms', 'authenticator'
    destination = db.Column(db.String(255), nullable=False)  # Email or phone number
    is_primary = db.Column(db.Boolean, default=False)
    verified = db.Column(db.Boolean, default=False)  # Add this field
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)

    # Relationship to user
    user = db.relationship('User', back_populates='two_factor_methods')
    
    
    
class FormTemplate(db.Model):
    __tablename__ = 'form_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    template_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    version = db.Column(db.String(20), default='1.0')
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255), nullable=False)  # Full path to file
    file_name = db.Column(db.String(255), nullable=False)  # Original filename
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    download_count = db.Column(db.Integer, default=0)

    uploader = db.relationship('User', backref=db.backref('form_templates', lazy=True))
    
    def __repr__(self):
        return f'<FormTemplate {self.template_name} v{self.version}>'
    
    @property
    def download_url(self):
        return url_for('auth_web.download_template', template_id=self.id)
    
    @property
    def file_extension(self):
        return self.file_name.rsplit('.', 1)[1].lower() if '.' in self.file_name else ''
    
    @property
    def file_icon(self):
        extensions = {
            'pdf': 'file-pdf',
            'doc': 'file-word',
            'docx': 'file-word',
            'xls': 'file-excel',
            'xlsx': 'file-excel'
        }
        return extensions.get(self.file_extension, 'file')