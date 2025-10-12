import subprocess
from app.extensions import db, bcrypt # Import db and bcrypt from extensions
from click import command
from flask import render_template, redirect, url_for, flash, request, g, abort
from flask_login import login_required, current_user
from flask_migrate import Migrate

from app.auth.models import Role
from app.user_management.models import Department, Privilege
from . import admin_web_bp
from .models import Hospital
from app.extensions import db
from .forms import HospitalForm
from flask import current_app
from sqlalchemy import create_engine, text
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
import os

# Restrict to super admins
# @admin_web_bp.before_request
# @login_required
# def require_super_admin():
#     if not current_user.is_super_admin:
#         abort(403)

@admin_web_bp.route('/')
def index():
    """
    Super-Admin Dashboard landing page.
    Shows summary stats across all hospitals.
    """
    total_hospitals = Hospital.query.count()
    total_admins = db.session.query(db.func.count()).select_from(Hospital).scalar()  # example
    return render_template('super_admin/index.html', total_hospitals=total_hospitals, total_admins=total_admins)

# --- Hospital Management ---
@admin_web_bp.route('/hospitals')
def manage_hospitals():
    hospitals = Hospital.query.order_by(Hospital.name).all()
    return render_template('super_admin/manage_hospitals.html', hospitals=hospitals)

# --- Hospital Management ---
@admin_web_bp.route('/list/hospitals')
def list_hospitals():
    hospitals = Hospital.query.order_by(Hospital.name).all()
    return render_template('super_admin/hospitals/list.html', hospitals=hospitals)

import os
import subprocess
import traceback
from werkzeug.security import generate_password_hash
from flask import current_app, flash, redirect, render_template, url_for
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import random
import string
import secrets
from datetime import datetime

@admin_web_bp.route('/hospitals/new', methods=['GET', 'POST'])
def create_hospital():
    form = HospitalForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        subdomain = form.subdomain.data.strip().lower()
        db_name = f"astrocare_{subdomain}"

        # 1. Construct database URIs
        try:
            db_host = current_app.config['DB_HOST']
            db_user = current_app.config['DB_USER']
            db_pass = current_app.config['DB_PASS']
            db_root_pass = current_app.config['DB_ROOT_PASS']

            root_uri = f"mysql+pymysql://{db_user}:{db_root_pass}@{db_host}/"
            db_uri = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}/{db_name}"

            current_app.logger.info(f"Root URI: {root_uri}")
            current_app.logger.info(f"DB URI: {db_uri}")
        except KeyError as e:
            flash(f"Configuration error: Missing {e}", "danger")
            return render_template('super_admin/create_hospital.html', form=form, action='New')

        # 2. Save hospital record in master DB
        hosp = Hospital(name=name, subdomain=subdomain, db_uri=db_uri)
        db.session.add(hosp)
        try:
            db.session.commit()
            current_app.logger.info(f"Hospital record created: {hosp.id}")
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to save hospital record: {e}", "danger")
            return render_template('super_admin/create_hospital.html', form=form, action='New')

        # 3. Create database and grant privileges
        try:
            root_engine = create_engine(root_uri, pool_pre_ping=True)
            with root_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`"))
                conn.execute(text(
                    f"CREATE USER IF NOT EXISTS '{db_user}'@'%' IDENTIFIED BY '{db_pass}'"
                ))
                conn.execute(text(
                    f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'%'"
                ))
                conn.execute(text("FLUSH PRIVILEGES"))
                current_app.logger.info(f"Database '{db_name}' ensured and privileges granted")

            # Test connection
            test_engine = create_engine(db_uri, pool_pre_ping=True)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                current_app.logger.info(f"Successfully connected to {db_name}")
        except Exception as e:
            error_trace = traceback.format_exc()
            current_app.logger.error(f"Database creation failed: {e}\n{error_trace}")
            flash(f"Database creation failed: {e}", "danger")
            return redirect(url_for('admin_web.create_hospital'))

        # 4. Provision schema using SQLAlchemy create_all()
        try:
            tenant_engine = create_engine(db_uri, pool_pre_ping=True)
            from app.extensions import db as _db
            _db.Model.metadata.create_all(bind=tenant_engine)
            current_app.logger.info(f"Schema created in {db_name}")
        except Exception as e:
            error_trace = traceback.format_exc()
            current_app.logger.error(f"Schema provisioning failed: {e}\n{error_trace}")
            flash(f"Schema provisioning failed: {e}", "danger")
            return redirect(url_for('admin_web.create_hospital'))


        # 5) Seed essential data in‐process on the tenant DB
        tenant_engine = create_engine(db_uri, pool_pre_ping=True)
        Session = sessionmaker(bind=tenant_engine)
        session = Session()

        try:
            PRIVILEGES_LIST = [
            ('dashboard:view', 'Dashboard', 'View Dashboard overview'),
            ('users:create', 'User Management', 'Create new user accounts'),
            ('users:list', 'User Management', 'List all users'),
            ('users:edit', 'User Management', 'Edit existing user accounts'),
            ('patients:register', 'Patients', 'Register a new patient'),
            ('patients:manage', 'Patients', 'View & edit patient records'),
            ('patients:triage', 'Patients', 'Perform patient triage'),
            ('consultations:queue', 'Consultations', 'Access consultation queue'),
            ('lab:orders', 'Lab Tests', 'View pending lab orders'),
            ('lab:results', 'Lab Tests', 'View lab test results'),
            ('lab:add_quick', 'Lab Tests', 'Add a quick lab test'),
            ('radiology:requests', 'Radiology', 'View imaging requests (MedSvc)'),
            ('radiology:scan_results', 'Radiology', 'View scan results (MedSvc)'),
            ('radiology:archive', 'Radiology', 'View archived reports (MedSvc)'),
            ('appointments:schedule', 'Appointments', 'Schedule a new appointment'),
            ('appointments:manage', 'Appointments', 'Manage all appointments'),
            ('appointments:my_schedule', 'Appointments', 'View my upcoming appointments'),
            ('billing:create_invoice', 'Billing', 'Create a new invoice'),
            ('billing:process_payment', 'Billing', 'Process payments'),
            ('billing:transactions', 'Billing', 'View transaction history'),
            ('pharmacy:dispense', 'Pharmacy', 'Dispense medication'),
            ('pharmacy:inventory', 'Pharmacy', 'Manage pharmacy inventory'),
            ('pharmacy:track_prescriptions', 'Pharmacy', 'Track prescriptions'),
            ('pharmacy:stock_requests', 'Pharmacy', 'View & respond to stock requests'),
            ('lab_tests:list', 'Laboratory', 'List all lab tests'),
            ('lab_reports:generate', 'Laboratory', 'Generate lab reports'),
            ('lab:test_types', 'Laboratory', 'Manage lab test types'),
            ('lab:view_reports', 'Laboratory', 'View lab reports'),
                ('lab_samples:manage', 'Laboratory', 'Manage sample collection, tracking and storage'),
    ('blood_bank:manage', 'Laboratory', 'Manage blood inventory and transfusions'),
    ('lab_inventory:view', 'Laboratory', 'View lab reagents and consumables'),
    ('lab_equipment:maintain', 'Laboratory', 'Schedule equipment maintenance'),
    ('lab_quality:control', 'Laboratory', 'Manage quality control procedures'),
        ('lab_inventory:manage_consumables', 'Laboratory', 'Manage laboratory consumables and reagents'),
    ('lab_inventory:request_stocks', 'Laboratory', 'Request new stocks for laboratory'),
    ('lab_inventory:stock_flow', 'Laboratory', 'Monitor stock flow and usage in laboratory'),
            ('radiology:imaging_requests', 'Radiology', 'View imaging requests'),
            ('radiology:view_scans', 'Radiology', 'View scans'),
            ('radiology:view_reports', 'Radiology', 'View radiology reports'),
                ('radiology:archive', 'Radiology', 'View archived radiology reports'),
    ('radiology:manage_services', 'Radiology', 'Manage radiology services'),
    ('radiology:equipment_maintenance', 'Radiology', 'Schedule and manage radiology equipment maintenance'),
    ('radiology:quality_control', 'Radiology', 'Perform and track radiology quality control procedures'),

    # Radiology Inventory Privileges
    ('radiology_inventory:view', 'Radiology Inventory', 'View radiology consumables and inventory dashboard'),
    ('radiology_inventory:manage_consumables', 'Radiology Inventory', 'Manage radiology consumables and reagents'),
    ('radiology_inventory:request_stocks', 'Radiology Inventory', 'Request new radiology consumable stocks'),
    ('radiology_inventory:stock_flow', 'Radiology Inventory', 'Monitor stock flow and usage in radiology'),
            ('hr:staff_add', 'Human Resources', 'Add New Staff'),
            ('hr:staff_directory', 'Human Resources', 'View Staff Directory'),
            ('hr:staff_profiles', 'Human Resources', 'View/Edit Staff Profiles'),
            ('hr:attendance', 'Human Resources', 'Track Staff Attendance'),
            ('hr:payroll:salary', 'Human Resources', 'Process Staff Salaries'),
            ('hr:payroll:payslips', 'Human Resources', 'Generate/View Payslips'),
            ('hr:payroll:reports', 'Human Resources', 'View Payroll Reports'),
            ('hr:recruitment', 'Human Resources', 'Manage Recruitment'),
            ('inventory:dashboard', 'Inventory', 'View Inventory Dashboard'),
            ('inventory:manage_stock', 'Inventory', 'Manage Stock Levels'),
            ('inventory:stock_requests', 'Inventory', 'View & Respond to Stock Requests'),
            ('inventory:suppliers', 'Inventory', 'Manage Suppliers'),
            ('inventory:purchase_orders', 'Inventory', 'Manage Purchase Orders'),
            ('inventory:reports', 'Inventory', 'Generate Inventory Reports'),
                    ('inventory:inventory_logs', 'Inventory', 'View Inventory Audit Logs'),
    # Stock Level Reports
    ('inventory:reports:stock', 'Inventory Reports', 'View Stock Level Reports'),
    
    # Purchase & Procurement Reports  
    ('inventory:reports:purchase', 'Inventory Reports', 'View Purchase & Procurement Reports'),
    
    # Delivery & Receiving Reports
    ('inventory:reports:delivery', 'Inventory Reports', 'View Delivery & Receiving Reports'),
    
    # Financial Reports
    ('inventory:reports:financial', 'Inventory Reports', 'View Financial Reports'),
    
    # Stock Request & Issuance Reports
    ('inventory:reports:requests', 'Inventory Reports', 'View Stock Request Reports'),
    
    # Expiry & Batch Reports
    ('inventory:reports:expiry', 'Inventory Reports', 'View Expiry & Batch Reports'),
    
    # Audit & Compliance Reports
    ('inventory:reports:audit', 'Inventory Reports', 'View Audit & Compliance Reports'),
    
    # Requisition & Approval Reports
    ('inventory:reports:requisitions', 'Inventory Reports', 'View Requisition Reports'),
    
    # Additional Analysis Reports
    ('inventory:reports:analysis', 'Inventory Reports', 'View Analysis Reports'),
            ('finance:dashboard', 'Finance', 'View Financial Dashboard'),
            ('finance:invoices', 'Finance', 'Manage Invoices & Receivables'),
            ('finance:payments', 'Finance', 'Process Payments'),
            ('finance:expenses', 'Finance', 'Track Expenses'),
            ('finance:insurance', 'Finance', 'Manage Insurance Policies'),
            ('finance:reports', 'Finance', 'Generate Financial Reports'),
            
                ('finance:approve_lpo', 'Finance', 'Approve Local Purchase Orders (LPOs)'),
                ('finance:supplier_accounts', 'Finance', 'Manage Supplier Accounts'),
                ('finance:approve_payments', 'Finance', 'Approve Payments'),

            ('reports:clinical', 'Reports', 'Access Clinical Reports'),
            ('reports:financial', 'Reports', 'Access Financial Reports'),
            ('reports:analytics', 'Reports', 'Access Analytics Dashboard'),
            ('doctor_dashboard', 'Dashboard', 'Access Doctor Dashboard'),
            ('nurse_dashboard', 'Dashboard', 'Access Nurse Dashboard'),
            ('labtech_dashboard', 'Dashboard', 'Access Lab Technician Dashboard'),
            ('radiology_dashboard', 'Dashboard', 'Access Radiology Dashboard'),
            ('pharmacy_dashboard', 'Dashboard', 'Access Pharmacy Dashboard'),
            ('registration_dashboard', 'Dashboard', 'Access Registration Dashboard'),
            ('patient_dashboard', 'Dashboard', 'Access Patient Dashboard'),
            ('reports:audit', 'Reports', 'Access Audit Logs'),
            ('finance:services', 'Finance', 'Manage Financial Services'),
            ('pharmacy:dispense_history', 'Pharmacy', 'View Dispense History'),
            ('resource:policies', 'Resource Centre', 'Access System Policies'),
            ('resource:documentation', 'Resource Centre', 'Access System Documentation'),
            ('resource:support', 'Resource Centre', 'Access System Support Resources'),
                ('resource:updates', 'Resource Centre', 'View system updates and changelogs'),
    ('resource:manage', 'Resource Centre', 'Manage resource centre content'),
            ('inventory:external_orders', 'Inventory', 'Manage External Orders'),
            ('finance:manage_orders', 'Finance', 'Approve/Reject Purchase Requisitions'),
            ('reports:mpesa', 'Reports', 'Access M-Pesa Transaction Logs'),
            ('finance:cash_payments', 'Finance', 'Manage Cash Payments and Receipts'),
            ('hr:payroll:periods', 'Human Resources', 'Manage Payroll Periods'),
            ('hr:payroll:adjustments', 'Human Resources', 'Manage Payroll Adjustments'),
            ('hr:payroll:loans', 'Human Resources', 'Manage Employee Loans'),
            ('hr:payroll:settings', 'Human Resources', 'Configure Payroll Settings'),
            ('hr:duty_rota', 'Human Resources', 'Manage Duty Rota Schedules'),
                # NEW: Disciplinary Services privileges
            ('hr:disciplinary:cases', 'Disciplinary Services', 'Manage disciplinary cases'),
            ('hr:disciplinary:actions', 'Disciplinary Services', 'Manage disciplinary actions'),
            ('hr:disciplinary:reports', 'Disciplinary Services', 'View disciplinary reports'),
            ('hr:disciplinary:policies', 'Disciplinary Services', 'Manage disciplinary policies'),
            ('hr:disciplinary:appeals', 'Disciplinary Services', 'Handle appeals process'),
                        # Asset Management
            ('asset:manage', 'Asset Management', 'Manage hospital assets'),
            ('asset:track', 'Asset Management', 'Track asset locations'),
            ('asset:maintenance', 'Asset Management', 'Schedule asset maintenance'),
            ('asset:reports', 'Asset Management', 'View asset reports'),
            
            # Board Module
            ('board:dashboard', 'Board Module', 'Access board dashboard'),
            ('board:financials', 'Board Module', 'View financial reports'),
            ('board:performance', 'Board Module', 'View performance metrics'),
            ('board:strategy', 'Board Module', 'Strategic planning'),
            ('board:governance', 'Board Module', 'Governance and compliance'),
            ('board:resources', 'Board Module', 'Access board resources'),

            ('hospital:manage_profile', 'System Administration', 'Manage hospital profile settings'),
                # Communication Hub Privileges
            ('comms:dashboard', 'Communication Hub', 'Access Engagement Dashboard'),
            ('comms:sms_patients', 'Communication Hub', 'Send Bulk SMS to Patients'),
            ('comms:sms_staff', 'Communication Hub', 'Send Bulk SMS to Staff'),
            ('comms:email_bulk', 'Communication Hub', 'Send Bulk Email Campaigns'),
            ('comms:templates', 'Communication Hub', 'Manage Message Templates'),
            ('comms:reminders', 'Communication Hub', 'Manage Appointment Reminders'),
            ('comms:notifications', 'Communication Hub', 'Configure System Notifications'),
            ('comms:analytics', 'Communication Hub', 'View Delivery Analytics'),
            ('comms:feedback', 'Communication Hub', 'Manage Feedback Collection'),
                # New diagnosis privilege added here
    ('diagnosis:manage', 'Medical Services', 'Manage patient diagnoses'),
        # Dental Clinic Privileges 🦷
    ('dental:consultations', 'Dental Clinic', 'Access Dental Consultation module'),
    ('dental:procedures', 'Dental Clinic', 'Manage Dental Procedures'),
        # Optician Clinic Privileges 👓
    ('optician:examinations', 'Optician Clinic', 'Perform Eye Examinations'),
    ('optician:dispensing', 'Optician Clinic', 'Manage Glasses & Contact Lens Dispensing'),
        ('consultations:manage_services', 'Service Management', 'Manage consultation service types and pricing'),
    # --- Admin & Director Privileges ---
    ('admin:dashboard', 'Admin & Director', 'Access administrative dashboard'),
    ('admin:approve_requisitions', 'Admin & Director', 'Approve or reject purchase requisitions'),
    ('admin:orders_progress', 'Admin & Director', 'View and track progress of purchase orders'),
    ('admin:manage_users', 'Admin & Director', 'High-level user and role management'),
    ('admin:system_settings', 'Admin & Director', 'Manage core system configurations'),
    ('admin:reports_overview', 'Admin & Director', 'Access consolidated reports (financial, clinical, HR, assets)'),
    ('admin:approve_lpo', 'Admin & Director', 'Approve Local Purchase Orders (LPOs)'),
    ('admin:approve_payments', 'Admin & Director', 'Approve Payments'),

            ]
            # --- Privileges ---
            created = 0
            for name, module, desc in PRIVILEGES_LIST:
                if not session.query(Privilege).filter_by(name=name).first():
                    session.add(Privilege(name=name, module=module, description=desc))
                    created += 1

# ... (previous code)

            # --- Roles with Privileges ---
            roles_data = {
                'Patient': (0, True),
                'Registration': (0, False),
                'Nurse': (0, False),
                'Doctor': (0, False),
                'Pharmacist': (0, False),
                'Lab Tech': (0, False),
                'Radiologist': (0, False),
                'Billing Officer': (0, False),
                'Admin': (0, False),
                'Board Memember': (0, False),
                'IT Specialist': (0, False), # ADDED: IT Role
            }

            # Create roles and assign privileges to Admin
            admin_role = None
            for r_name, (r_permissions, r_default) in roles_data.items():
                role = session.query(Role).filter_by(name=r_name).first()
                if role is None:
                    role = Role(name=r_name, permissions=r_permissions, default=r_default)
                    session.add(role)
                else:
                    role.permissions = r_permissions
                    role.default = r_default
                    
                # Assign all privileges to Admin role
                if r_name == 'Admin':
                    admin_role = role
                    all_privileges = session.query(Privilege).all()
                    for priv in all_privileges:
                        if priv not in admin_role.privileges:
                            admin_role.privileges.append(priv)
                # You might also want to assign specific IT-related privileges to the 'IT' role here
                # Example:
                elif r_name == 'IT':
                    # Assuming you have privileges like 'system:settings', 'users:manage_accounts', etc.
                    # You would query for them and append them to role.privileges
                    it_privileges = session.query(Privilege).filter(
                        Privilege.name.in_([
                            'users:create', 'users:list', 'users:edit', # User management
                            'hospital:manage_profile', # Hospital settings
                            'reports:audit', # Audit logs
                            # Add any other IT-specific privileges here
                        ])
                    ).all()
                    for priv in it_privileges:
                        if priv not in role.privileges:
                            role.privileges.append(priv)


            session.commit()

            # --- Departments ---
            dept_names = [
                "General Medicine", "Pediatrics", "Surgery",
                "Pharmacy", "Laboratory", "Radiology",
                "Human Resources", "Billing", "Doctor",
                "Clinical Officer", "Receptionist", "Nursing",
                "Administrator", "Board Memember",
                "Information Technology" # ADDED: IT Department
            ]
            for d in dept_names:
                if not session.query(Department).filter_by(name=d).first():
                    session.add(Department(name=d))

            session.commit()

# ... (rest of your code)

            # --- Generate secure admin password ---
            # Combine hospital name, subdomain, and random elements
            hospital_initials = ''.join([word[0].upper() for word in name.split()[:2]] or ['A', 'S'])
            subdomain_chars = subdomain[:3].lower()
            random_chars = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(4))
            special_char = secrets.choice('!@$%&*')
            year = str(datetime.now().year)[-2:]
            
            # Create password pattern: [HospitalInitials][Subdomain][Year][Random][Special]
            plaintext_password = f"{hospital_initials}{subdomain_chars}{year}{random_chars}{special_char}"

            # --- Create admin user ---
            admin_role = session.query(Role).filter_by(name='Admin').first()
            administrator_dept = session.query(Department).filter_by(name='Administrator').first()
            password_hash = bcrypt.generate_password_hash(plaintext_password).decode('utf-8')

            # 1. Insert the admin user
            session.execute(text("""
                INSERT INTO `user` 
                (username, email, password_hash, is_active, department_id, is_super_admin)
                VALUES
                (:u, :e, :ph, 1, :dept_id, 1)
            """), {
                "u": "admin",
                "e": f"admin@{subdomain}.astrocare.com",
                "ph": password_hash,
                "dept_id": administrator_dept.id if administrator_dept else None
            })
            admin_email = f"admin@{subdomain}.astrocare.com"

            # 2. Get the inserted admin user ID
            admin_user = session.execute(text("""
                SELECT id FROM `user` WHERE username = 'admin'
            """)).fetchone()
            admin_user_id = admin_user[0] if admin_user else None

            if admin_user_id and admin_role:
                # 3. Insert into user_roles table
                session.execute(text("""
                    INSERT INTO user_roles (user_id, role_id)
                    VALUES (:user_id, :role_id)
                """), {
                    "user_id": admin_user_id,
                    "role_id": admin_role.id
                })
            else:
                current_app.logger.error("Failed to create admin user or find Admin role")

            session.commit()
                        # --- Hospital Profile ---
            # Insert the HospitalProfile for the newly created tenant hospital
            # Using raw SQL as requested
            session.execute(text("""
                INSERT INTO hospital_profiles 
                (name, display_name, subdomain, db_url, created_at, last_updated)
                VALUES 
                (:name, :display_name, :subdomain, :db_url, :created_at, :last_updated)
            """), {
                "name": hosp.name,
                "display_name": hosp.name, # Assuming display_name is same as name for initial setup
                "subdomain": subdomain,
                "db_url": db_uri,
                "created_at": datetime.utcnow(), # Use UTC for consistency with default timestamps
                "last_updated": datetime.utcnow() # Use UTC for consistency with default timestamps
            })
            
            session.commit() # Commit after inserting the hospital profile
            # Prepare credentials to pass to frontend
            access_url = f"https://{subdomain}.astrocare.com"
            credentials = {
                "hospital": hosp.name,
                "access_url": access_url,
                "admin_username": "admin",
                "admin_password": plaintext_password,
                "admin_email": admin_email,
                "db_name": db_name,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        except Exception as e:
            session.rollback()
            current_app.logger.error("Tenant seeding failed", exc_info=e)
            flash("Seeding tenant data failed—see logs", "danger")
            # Optional: drop the tenant DB
            with root_engine.connect() as c:
                c.execute(text(f"DROP DATABASE IF EXISTS `{db_name}`"))
            return redirect(url_for('admin_web.create_hospital'))
        finally:
            session.close()



        flash(f'Hospital "{hosp.name}" created successfully!', "success")
        # Pass credentials to template
        return render_template(
            'super_admin/create_hospital_success.html', 
            credentials=credentials,
            hospital_name=name
        )

    return render_template('super_admin/create_hospital.html', form=form, action='New')


    
@admin_web_bp.route('/hospitals/<int:hospital_id>/edit', methods=['GET', 'POST'])
def edit_hospital(hospital_id):
    hosp = Hospital.query.get_or_404(hospital_id)
    form = HospitalForm(obj=hosp)
    if form.validate_on_submit():
        hosp.name = form.name.data.strip()
        hosp.subdomain = form.subdomain.data.strip()
        hosp.db_uri = form.db_uri.data.strip()
        db.session.commit()
        flash('Hospital updated successfully.', 'success')
        return redirect(url_for('admin_web_bp.list_hospitals'))
    return render_template('super_admin/hospitals/form.html', form=form, action='Edit')

@admin_web_bp.route('/hospitals/<int:hospital_id>/delete', methods=['POST'])
def delete_hospital(hospital_id):
    hosp = Hospital.query.get_or_404(hospital_id)
    db.session.delete(hosp)
    db.session.commit()
    flash('Hospital deleted.', 'warning')
    return redirect(url_for('admin_web_bp.list_hospitals'))

@admin_web_bp.route('/hospitals/config/', methods=['GET', 'POST'])
def hospital_config(hospital_id):

    return render_template('super_admin/hospitals/config.html')

# --- Admin Users ---
@admin_web_bp.route('/admins')
def manage_admins():

    return render_template('super_admin/admins/list.html')

@admin_web_bp.route('/admins/new', methods=['GET', 'POST'])
def create_admin():

    return render_template('super_admin/admins/form.html')

@admin_web_bp.route('/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
def edit_admin(admin_id):

    return render_template('super_admin/admins/form.html')

@admin_web_bp.route('/admins/<int:admin_id>/delete', methods=['POST'])
def delete_admin(admin_id):
    from .models import Admin
    admin = Admin.query.get_or_404(admin_id)
    db.session.delete(admin)
    db.session.commit()
    flash('Admin removed.', 'warning')
    return redirect(url_for('admin_web_bp.list_admins'))

@admin_web_bp.route('/admins/logs')
def access_logs():
    return render_template('super_admin/admins/logs.html')

# --- Reports ---
@admin_web_bp.route('/reports/global')
def global_reports():
    data = db.session.query(Hospital.name, db.func.count().label('count')).join('patients', isouter=True).group_by(Hospital.id).all()
    return render_template('super_admin/reports/global.html', data=data)

@admin_web_bp.route('/reports/per-hospital')
def per_hospital_reports():
    return redirect(url_for('admin_web_bp.global_reports'))  # placeholder

@admin_web_bp.route('/reports/performance')
def performance_dashboard():
    return render_template('super_admin/reports/performance.html')

@admin_web_bp.route('/reports/comparison')
def compare_hospitals():
    return render_template('super_admin/reports/comparison.html')

@admin_web_bp.route('/reports/usage')
def usage_analytics():
    return render_template('super_admin/reports/usage.html')

@admin_web_bp.route('/reports/financial')
def financial_reports():
    return render_template('super_admin/reports/financial.html')

@admin_web_bp.route('/reports/clinical')
def clinical_reports():
    return render_template('super_admin/reports/clinical.html')

@admin_web_bp.route('/reports/operational')
def operational_reports():
    return render_template('super_admin/reports/operational.html')

@admin_web_bp.route('/reports/custom', methods=['GET', 'POST'])
def custom_report_builder():

    return render_template('super_admin/reports/custom.html')

# --- System Health & Settings ---
@admin_web_bp.route('/system/health')
def system_health():
    # placeholder for health metrics
    return render_template('super_admin/system/health.html')

@admin_web_bp.route('/settings/global', methods=['GET', 'POST'])
def global_settings():
    return render_template('super_admin/settings/global.html')
