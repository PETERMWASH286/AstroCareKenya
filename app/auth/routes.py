from datetime import datetime
from functools import cache
import json
import os
import random
from PIL import Image
from flask import abort, g, jsonify, render_template, redirect, send_file, session, url_for, flash, request, current_app, send_from_directory
# UPDATED: Import Flask-Login functions
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename  # Import secure_filename for file handling
from werkzeug.security import check_password_hash  # Import for password hash checking

# from flask_wtf import FlaskForm # If using Flask-WTF for forms
# from wtforms import StringField, PasswordField, BooleanField, SubmitField # If using Flask-WTF
# from wtforms.validators import DataRequired, Length, Email # If using Flask-WTF
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer

from app.audit import log_audit_event
from app.extensions import db
from app.notifications.models import NotificationRead
from app.super_admin.models import HospitalProfile
from app.user_management.models import Department # Import db extension if needed in routes
from . import auth_web_bp # Import the blueprint instance
from .services import AuthService # Import the service layer
from .schemas import LoginSchema # Import schemas for validation (alternative to WTForms)
from app.auth.models import FormTemplate, Role, TwoFactorMethod, User, BlogPost, Document # Import User model if needed directly in routes
from app.extensions import socketio
from app.extensions import mail
import re  # Import regex for email validation

def validate_phone(phone):
    """Validate Kenyan phone number format: starts with 07 or 01 and has 10 digits."""
    pattern = r'^(07|01)\d{8}$'
    return re.match(pattern, phone) is not None

def validate_email(email):
    """Validate email format using regex."""
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(email_regex, email) is not None

@auth_web_bp.route('/login', methods=['GET', 'POST'])
def login():
    # fast return if already logged in
    if current_user.is_authenticated:
        current_app.logger.info(f"User {current_user.get_id()} already authenticated, redirecting from login.")
        return redirect(url_for('dashboard_web.index'))

    if request.method == 'POST':
        username_input = (request.form.get('username') or '').strip()
        password_input = request.form.get('password') or ''
        remember = request.form.get('remember') == 'on'
        ip = request.remote_addr or 'unknown'

        if not username_input or not password_input:
            flash('Please enter username and password.', 'warning')
            return redirect(url_for('.login'))

        # optional: quick rate-limit check (simple example, tune thresholds)
        recent_failures = db.session.query(db.func.count()).select_from(User.__table__).scalar()  # placeholder - see note below

        user = User.query.filter_by(username=username_input).first()

        if user is None:
            # user not found -> audit and return
            log_audit_event(
                'LOGIN',
                target=None,
                connection=None,
                model_name_override='Auth',
                record_id_override=username_input,
                success=False,
                details_extra={'reason': 'user_not_found', 'attempted_username': username_input, 'ip': ip}
            )
            current_app.logger.warning(f"Failed login attempt for username: {username_input} from {ip}")
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('.login'))

        if not getattr(user, 'is_active', True):
            log_audit_event(
                'LOGIN',
                target=user,
                connection=None,
                success=False,
                details_extra={'reason': 'account_inactive', 'ip': ip}
            )
            flash('Your account is inactive. Please contact support.', 'danger')
            return redirect(url_for('.login'))

        # check password (prefer user.check_password if available)
        try:
            if hasattr(user, 'check_password') and callable(user.check_password):
                password_ok = user.check_password(password_input)
            else:
                # fallback to werkzeug
                password_ok = check_password_hash(getattr(user, 'password_hash', ''), password_input)
        except Exception:
            current_app.logger.exception("Password check failed for user id %s", getattr(user, 'id', '<unknown>'))
            password_ok = False

        if not password_ok:
            # record failed attempt
            log_audit_event(
                'LOGIN',
                target=user,
                connection=None,
                success=False,
                details_extra={'reason': 'invalid_password', 'ip': ip}
            )
            current_app.logger.warning(f"Failed login (invalid password) for user id {user.id} from {ip}")
            flash('Invalid username or password.', 'danger')

            # optionally: implement account lockout here (see note at end)
            return redirect(url_for('.login'))

        # password correct -> check 2FA
        if getattr(user, 'requires_2fa', False):
            # set temporary session and send verification code
            session['2fa_user_id'] = user.id
            session['remember_me'] = remember

            primary_method = user.two_factor_methods.filter_by(is_primary=True, verified=True).first()
            if primary_method:
                # log that 2FA was initiated (success = None -> in-progress)
                log_audit_event(
                    'LOGIN',
                    target=user,
                    connection=None,
                    success=None,
                    details_extra={'2fa_initiated': True, 'method': getattr(primary_method, 'method', None), 'ip': ip}
                )
                # send the code (make sure function exists)
                send_verification_code(primary_method)
                return redirect(url_for('auth_web.verify_2fa'))
            else:
                log_audit_event(
                    'LOGIN',
                    target=user,
                    connection=None,
                    success=False,
                    details_extra={'reason': 'no_primary_2fa', 'ip': ip}
                )
                flash('No valid 2FA method found. Please contact support.', 'danger')
                return redirect(url_for('.login'))

        # no 2FA required => final successful login
        login_user(user, remember=remember)
        try:
            user.last_login_at = datetime.utcnow()
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to update last_login_at for user %s", user.id)

        log_audit_event(
            'LOGIN',
            target=user,
            connection=None,
            success=True,
            details_extra={'method': 'password', 'ip': ip}
        )
        current_app.logger.info(f"User {user.id} logged in successfully from {ip}")

        return redirect_after_login(user)

    # GET -> show the form
    return render_template('login.html')

def redirect_after_login(user):
    """Redirect user to appropriate dashboard after login"""
    if user.is_administrator():
        return redirect(url_for('dashboard_web.admin_overview'))
    elif user.has_privilege('doctor_dashboard'):
        return redirect(url_for('dashboard_web.doctor_dashboard'))
    elif user.has_privilege('nurse_dashboard'):
        return redirect(url_for('dashboard_web.nurse_dashboard'))
    elif user.has_privilege('labtech_dashboard'):
        return redirect(url_for('dashboard_web.labtech_dashboard'))
    elif user.has_privilege('radiology_dashboard'):
        return redirect(url_for('dashboard_web.radiology_dashboard'))
    elif user.has_privilege('pharmacy_dashboard'):
        return redirect(url_for('dashboard_web.pharmacy_dashboard'))
    elif user.has_privilege('registration_dashboard'):
        return redirect(url_for('dashboard_web.registration_dashboard'))
    else:
        return redirect(url_for('dashboard_web.patient_dashboard'))

def mask_sensitive(value):
    """Mask email addresses and phone numbers for display"""
    if '@' in value:
        local, domain = value.split('@', 1)
        return f"{local[:2]}***@{domain}" if len(local) > 2 else f"{local[0]}***@{domain}"
    
    if len(value) > 6:
        return f"{value[:3]}***{value[-3:]}"
    return f"{value[:2]}***"

@auth_web_bp.route('/logout')
# UPDATED: Use login_required decorator to protect this route
@login_required
def logout():
    # UPDATED: Use logout_user from Flask-Login to clear session
    current_app.logger.info(f"Logging out user: {current_user.get_id()}")
    logout_user()
    flash('You have been logged out.', 'info')
    # Redirect back to the login page after logout
    return redirect(url_for('.login'))


@auth_web_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Decide if public registration is allowed or if users are created by admins
    # For a hospital system, user creation is likely admin/registration staff only.
    # This is a placeholder.
    # You might want to restrict access to this route based on user permissions if registration is not public
    # @login_required # Example: Only logged-in users can access registration (e.g., admins)
    # @permission_required(Permission.CAN_CREATE_USERS) # Example: Only users with this permission

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not email or not password:
             flash('All fields are required.', 'warning')
             return redirect(url_for('.register'))

        try:
            # Default role might be 'Patient'
            new_user = AuthService.create_new_user(username, email, password)
            flash(f'Registration successful for {new_user.username}! Please log in.', 'success')
            current_app.logger.info(f"New user registered: {new_user.username}")
            return redirect(url_for('.login'))
        except ValueError as e:
            flash(str(e), 'danger')
            current_app.logger.warning(f"Registration failed: {e}")
        except Exception as e:
             flash('An unexpected error occurred during registration.', 'danger')
             current_app.logger.error(f"Registration error: {e}")


    # Template path relative to blueprint's template_folder ('templates')
    return render_template('register.html')

# Add routes for password reset, email confirmation etc. here

from sqlalchemy import text

# Add inside create_app function
@auth_web_bp.route('/db-check')
def db_check():
    try:
        # Execute a simple query to show current database
        result = db.session.execute(text('SELECT DATABASE()')).scalar()
        return jsonify({
            "database": result,
            "hospital": g.hospital['name'] if hasattr(g, 'hospital') else "SuperAdmin"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_web_bp.route('/create_user/',   methods=['POST'])
def create_user():
    # always load these for the GET form (and re‐render after a POST failure)
    all_roles = Role.query.order_by(Role.name).all()
    all_depts = Department.query.order_by(Department.name).all()

    if request.method == 'POST':
        full_name = request.form['full_name']
        username  = request.form['username']
        email     = request.form['email']
        password  = request.form['password']
        confirm   = request.form['confirm_password']
        role_id   = int(request.form['role_id'])
        dept_id   = int(request.form['department_id'])

        if password != confirm:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('user_management_web.create_user'))

        # create user + set password
        user = User(username=username, email=email)
        user.password = password

        # attach role
        role = Role.query.get_or_404(role_id)
        user.roles.append(role)

        # attach department (you’ll need to add this relationship on the User model)
        dept = Department.query.get_or_404(dept_id)
        user.department = dept

        db.session.add(user)
        db.session.commit()

        flash('User created successfully!', 'success')
        # redirect back to the blank form, or to your user list
        return redirect(url_for('user_management_web.create_user'))

    # GET → render form
    return render_template(
        'create_user.html',
        roles=all_roles,
        departments=all_depts
    )



def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
@auth_web_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Get all departments and roles for dropdowns
    departments = Department.query.order_by(Department.name).all()
    roles = Role.query.order_by(Role.name).all()

    if request.method == 'POST':
        # Update profile information
        current_user.full_name = request.form.get('full_name', current_user.full_name)
        current_user.email = request.form.get('email', current_user.email)
        current_user.username = request.form.get('username', current_user.username)
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # Create thumbnail/resize image
                img = Image.open(file_path)
                img.thumbnail((400, 400))
                img.save(file_path)
                
                current_user.profile_image = url_for('static', filename='uploads/' + filename)
        # Update department
        new_dept_id = request.form.get('department_id')
        if new_dept_id:
            new_dept = Department.query.get(new_dept_id)
            if new_dept:
                current_user.department = new_dept

        # Update role
        new_role_id = request.form.get('role_id')
        if new_role_id:
            new_role = Role.query.get(new_role_id)
            if new_role and new_role not in current_user.roles:
                current_user.roles = [new_role]  # Replace all roles with new one

        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('auth_web.profile'))

    return render_template('profile.html',
                           departments=departments,
                           roles=roles)

@auth_web_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # Handle password change
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match', 'danger')
        else:
            current_user.password = new_password
            db.session.commit()
            flash('Password updated successfully', 'success')
        
        return redirect(url_for('auth_web.settings'))

    return render_template('settings.html')



# ----------------------------------------
# Resource Centre Routes
# ----------------------------------------

@auth_web_bp.route('/system-policies')
@login_required
def system_policies():
    """
    Show the hospital’s system policies.
    """
    details = [
        {
            'id': 'data-security',
            'title': 'Data Protection & Security',
            'color': 'blue',
            'content': [
                'Patient records are encrypted and stored on secure Kenyan-based servers.',
                'User accounts require strong passwords and role-based access.',
                'Staff must log out of terminals when not in use.',
                'Regular audits are conducted for data access.',
            ]
        },
        {
            'id': 'confidentiality',
            'title': 'Confidentiality & Ethics',
            'color': 'purple',
            'content': [
                'Patient information shall not be disclosed without consent.',
                'Only authorized medical staff may access sensitive records.',
                'All users must sign confidentiality agreements during onboarding.',
            ]
        },
        {
            'id': 'usage-policy',
            'title': 'System Usage Policy',
            'color': 'teal',
            'content': [
                'AstroCare is to be used only for official hospital functions.',
                'No personal media or software may be installed on hospital systems.',
                'Internet usage should comply with ICT and MOH guidelines.',
            ]
        },
        {
            'id': 'compliance',
            'title': 'Regulatory Compliance',
            'color': 'amber',
            'content': [
                'AstroCare complies with Kenyan Data Protection Act, NHIF and MOH regulations.',
                'All medical entries must reflect real-time and accurate information.',
                'Audit trails are stored to meet legal and clinical governance standards.',
            ]
        },
        {
            'id': 'updates',
            'title': 'System Updates & Maintenance',
            'color': 'rose',
            'content': [
                'The system undergoes monthly updates with minimum downtime.',
                'All staff shall be notified 3 days prior to any major update.',
                'Emergency patches are applied instantly to address security threats.',
            ]
        },
    ]

    cards = [
        {
            'id': 'data-security',
            'title': 'Data Security',
            'icon': 'fa-shield-alt',
            'color': 'blue',
            'summary': 'We ensure encryption, secure access, and audit logs to protect patient data.'
        },
        {
            'id': 'confidentiality',
            'title': 'Confidentiality',
            'icon': 'fa-user-secret',
            'color': 'purple',
            'summary': 'Access to sensitive records is tightly controlled and based on roles.'
        },
        {
            'id': 'usage-policy',
            'title': 'Usage Policy',
            'icon': 'fa-laptop-code',
            'color': 'teal',
            'summary': 'AstroCare is used strictly for authorized medical and administrative tasks.'
        },
        {
            'id': 'compliance',
            'title': 'Compliance',
            'icon': 'fa-scale-balanced',
            'color': 'amber',
            'summary': 'Built to align with MOH, NHIF, and Kenyan Data Protection laws.'
        },
        {
            'id': 'updates',
            'title': 'System Updates',
            'icon': 'fa-sync-alt',
            'color': 'rose',
            'summary': 'AstroCare is improved monthly with timely feature and security updates.'
        },
    ]

    return render_template("system_policies.html", details=details, cards=cards)



@auth_web_bp.route('/documentation')
@login_required
def documentation():
    """
    Show user & API documentation.
    """
    modules = [
        {
            'id': 'dashboard',
            'name': 'Dashboard',
            'description': 'Overview of KPIs, alerts, and quick links.',
            'topics': [
                {
                    'title': 'Overview Widgets',
                    'content': [
                        'The dashboard displays bed occupancy, pending lab tests, and billing stats in real time.',
                        'Use the filter dropdown to customize time ranges.'
                    ],
                    'code': None
                },
                {
                    'title': 'API Endpoint',
                    'content': ['Retrieve dashboard data via REST:'],
                    'code': 'GET /api/dashboard/data\nResponse: { "bed_occupancy": 75, "pending_lab": 12, ... }'
                }
            ]
        },
        {
            'id': 'patients',
            'name': 'Patients',
            'description': 'Managing patient registration, profiles, and medical history.',
            'topics': [
                {
                    'title': 'Register Patient',
                    'content': [
                        'Collect demographic details and next of kin.',
                        'Assign unique registration number (Reg No).'
                    ],
                    'code': None
                },
                {
                    'title': 'API Endpoint',
                    'content': ['Create a new patient record:'],
                    'code': 'POST /api/patients\nBody: { "first_name": "...", "last_name": "...", ... }'
                }
            ]
        },
        {
            'id': 'consultations',
            'name': 'Consultations',
            'description': 'Queue management, history, and clinical notes.',
            'topics': [
                {
                    'title': 'Triage & Queue',
                    'content': [
                        'Patients are triaged and placed in the consultation queue.',
                        'Clinicians pull from the queue based on priority.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'lab',
            'name': 'Lab Tests',
            'description': 'Order, result entry, and report generation.',
            'topics': [
                {
                    'title': 'Order a Lab Test',
                    'content': [
                        'Select test type and urgency.',
                        'Tests appear in the laboratory queue.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'radiology',
            'name': 'Radiology',
            'description': 'Imaging requests, result uploads, and archive.',
            'topics': [
                {
                    'title': 'Request Imaging',
                    'content': [
                        'Choose imaging modality and body part.',
                        'Technician reviews request and schedules slot.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'appointments',
            'name': 'Appointments',
            'description': 'Scheduling, rescheduling, and reminders.',
            'topics': [
                {
                    'title': 'Book an Appointment',
                    'content': [
                        'Select doctor and preferred time.',
                        'Patient receives SMS reminder 24‑hrs prior.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'user_management',
            'name': 'User Management',
            'description': 'Roles, privileges, and audit trails.',
            'topics': [
                {
                    'title': 'Create/Edit Users',
                    'content': [
                        'Assign roles and departments.',
                        'Enforce password policies.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'hr',
            'name': 'Human Resources',
            'description': 'Staff directory, attendance, and payroll.',
            'topics': [
                {
                    'title': 'Attendance Tracking',
                    'content': [
                        'Clock‑in/out via biometric or web portal.',
                        'Generate monthly attendance reports.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'billing',
            'name': 'Billing',
            'description': 'Invoice creation, insurance verification, and payments.',
            'topics': [
                {
                    'title': 'Create Invoice',
                    'content': [
                        'Select services and generate PDF invoice.',
                        'Submit to NHIF or process cash payment.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'pharmacy',
            'name': 'Pharmacy',
            'description': 'Dispense meds, manage stock, and fulfill requests.',
            'topics': [
                {
                    'title': 'Dispense Medication',
                    'content': [
                        'Scan prescription and update inventory.',
                        'Print dispensing label with patient details.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'inventory',
            'name': 'Inventory',
            'description': 'Suppliers, stock levels, and purchase orders.',
            'topics': [
                {
                    'title': 'Manage Stock',
                    'content': [
                        'Set min/max levels and automatic reorder alerts.',
                        'Receive supplier shipments and update quantities.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'finance',
            'name': 'Finance',
            'description': 'Financial dashboard, expenses, and reporting.',
            'topics': [
                {
                    'title': 'Expense Tracking',
                    'content': [
                        'Log expenses against departments.',
                        'Generate month‑end financial statements.'
                    ],
                    'code': None
                }
            ]
        },
        {
            'id': 'reports',
            'name': 'Reports',
            'description': 'Clinical, financial, and operational analytics.',
            'topics': [
                {
                    'title': 'Generate Reports',
                    'content': [
                        'Choose report type and date range.',
                        'Download as PDF or Excel.'
                    ],
                    'code': None
                }
            ]
        }
    ]
    return render_template('documentation.html', modules=modules)




@auth_web_bp.route('/support')
@login_required
def support():
    """
    Show contact & support resources.
    """
    return render_template('support.html')
@auth_web_bp.route('/view-updates')
@login_required
def view_updates():
    return render_template('auth/view_updates.html')



from app.notifications.services import NotificationService
from app.user_management.models import Department

@auth_web_bp.route('/manage-resources', methods=['GET', 'POST'])
@login_required
def manage_resources():
    departments = Department.query.all()
    
    # Handle Blog Post Creation
    if request.method == 'POST' and 'blogTitle' in request.form:
        title = request.form['blogTitle']
        content = request.form['blogContent']
        department_id = request.form['blogDepartment']
        status = request.form['blogStatus']
        
        new_blog = BlogPost(
            title=title,
            content=content,
            department_id=department_id,
            status=status,
            author_id=current_user.id,
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_blog)
        db.session.commit()
        
        # Send notification if published
        if status == 'published':
            department = Department.query.get(department_id)
            NotificationService.send_notification(
                title="New Blog Post Published",
                message=f"A new blog '{title}' is now available in {department.name}",
                recipient_type='department',
                recipient_id=department_id,
                notification_type='info',
                icon='fas fa-blog',
                action_url=url_for('auth_web.view_blog', blog_id=new_blog.id),
                sender_id=current_user.id
            )
        
        flash('Blog post created successfully!', 'success')
        return redirect(url_for('auth_web.manage_resources'))
    
    # Handle Document Upload
    if request.method == 'POST' and 'documentTitle' in request.form:
        title = request.form['documentTitle']
        department_id = request.form['documentDepartment']
        document_type = request.form['documentType']
        description = request.form['documentDescription']
        file = request.files['documentFile']
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(upload_path)
            
            new_document = Document(
                title=title,
                file_path=unique_filename,
                description=description,
                department_id=department_id,
                document_type=document_type,
                uploaded_by=current_user.id,
                created_at=datetime.utcnow()
            )
            
            db.session.add(new_document)
            db.session.commit()
            
            # Send notification for document
            department = Department.query.get(department_id)
            NotificationService.send_notification(
                title="New Document Available",
                message=f"A new {document_type} document '{title}' has been added to {department.name}",
                recipient_type='department',
                recipient_id=department_id,
                notification_type='info',
                icon='fas fa-file-alt',
                action_url=url_for('auth_web.download_resource_document', document_id=new_document.id),
                sender_id=current_user.id
            )
            
            flash('Document uploaded successfully!', 'success')
        else:
            flash('Invalid file type. Allowed formats: PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX', 'error')
        
        return redirect(url_for('auth_web.manage_resources'))
    
    # Fetch existing resources
        # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 5  # Items per page
    
    # Fetch paginated blog posts
    blog_query = BlogPost.query.order_by(BlogPost.created_at.desc())
    blog_posts = blog_query.paginate(page=page, per_page=per_page)
    documents = Document.query.order_by(Document.created_at.desc()).limit(4).all()
    
    # Get counts for stats
    total_resources = BlogPost.query.count() + Document.query.count()
    published_blogs = BlogPost.query.filter_by(status='published').count()
    document_count = Document.query.count()
    # — Build Recent Activity —
    raw_acts = []
    # Latest 5 blog events
    for post in BlogPost.query.order_by(BlogPost.created_at.desc()).limit(5):
        desc = (
            f"\"{post.title}\" published"
            if post.status == 'published'
            else f"{post.title} updated"
        )
        raw_acts.append({
            'type': 'blog',
            'desc': desc,
            'user': post.author.username,
            'ts': post.created_at
        })
    # Latest 5 document events
    for doc in Document.query.order_by(Document.created_at.desc()).limit(5):
        raw_acts.append({
            'type': 'doc',
            'desc': f"New {doc.document_type} document uploaded",
            'user': doc.uploader.username,
            'ts': doc.created_at
        })

    # Sort & trim to 5
    sorted_acts = sorted(raw_acts, key=lambda x: x['ts'], reverse=True)[:5]

    recent_activity = []
    now = datetime.utcnow()
    for a in sorted_acts:
        # icon & color by type
        if a['type'] == 'blog':
            icon = 'fas fa-blog'
            color = 'bg-green-100 text-green-500'
        else:
            icon = 'fas fa-file-alt'
            color = 'bg-blue-100 text-blue-500'
        # compute human time ago
        delta = now - a['ts']
        if delta.days == 0 and delta.seconds < 3600:
            hours = max(1, delta.seconds // 3600)
            ago = f"{hours} hours ago"
        elif delta.days == 1:
            ago = "Yesterday"
        else:
            ago = f"{delta.days} days ago"

        recent_activity.append({
            'icon': icon,
            'color': color,
            'message': a['desc'],
            'user': a['user'],
            'when': ago
        })

    # — Build Resource Statistics —
    total_blogs = BlogPost.query.count()
    published_blogs = BlogPost.query.filter_by(status='published').count()
    blog_pct = int(published_blogs * 100 / total_blogs) if total_blogs else 0

    total_docs = Document.query.count()
    policy_count = Document.query.filter_by(document_type='policy').count()
    form_count = Document.query.filter(Document.document_type.in_(['form','template'])).count()

    policy_pct = int(policy_count * 100 / total_docs) if total_docs else 0
    forms_pct  = int(form_count  * 100 / total_docs) if total_docs else 0

    resource_stats = [
        {'label': 'Blog Posts',         'pct': blog_pct,   'bar_color': 'bg-blue-600'},
        {'label': 'Policy Documents',   'pct': policy_pct, 'bar_color': 'bg-green-600'},
        {'label': 'Forms & Templates',  'pct': forms_pct,  'bar_color': 'bg-purple-600'},
    ]

    return render_template(
        'manage_resources.html',
        departments=departments,
        blog_posts=blog_posts,
        documents=documents,
        total_resources=total_resources,
        published_blogs=published_blogs,
        document_count=document_count,
                recent_activity=recent_activity,
        resource_stats=resource_stats,
    )


@auth_web_bp.route('/download-document/<int:document_id>')
@login_required
def download_document(document_id):
    """Serve the document file as an attachment."""
    document = Document.query.get_or_404(document_id)

    upload_folder = current_app.config['UPLOAD_FOLDER']
    full_path = os.path.join(upload_folder, document.file_path)
    if not os.path.isfile(full_path):
        flash('File not found on server.', 'error')
        return redirect(url_for('auth_web.manage_resources'))

    return send_from_directory(
        directory=upload_folder,
        path=document.file_path,
        as_attachment=True,
        download_name=document.title + os.path.splitext(document.file_path)[1]
    )

# VIEW a single blog post
@auth_web_bp.route('/view-blog/<int:blog_id>')
@login_required
def view_blog(blog_id):
    post = BlogPost.query.get_or_404(blog_id)
    return render_template('view_blog.html', post=post)

# EDIT a blog post (GET shows form, POST processes update)
@auth_web_bp.route('/blog/<int:blog_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_blog(blog_id):
    post = BlogPost.query.get_or_404(blog_id)
    # Only the author (or admins) may edit
    if post.author_id != current_user.id:
        abort(403)

    departments = Department.query.all()

    if request.method == 'POST':
        post.title = request.form['blogTitle']
        post.content = request.form['blogContent']
        post.department_id = request.form['blogDepartment']
        post.status = request.form['blogStatus']
        post.updated_at = datetime.utcnow()
        db.session.commit()

        flash('Blog post updated successfully!', 'success')
        return redirect(url_for('auth_web.view_blog', blog_id=post.id))

    # GET: render edit form populated with existing values
    return render_template(
        'edit_blog.html',
        post=post,
        departments=departments
    )

# DELETE a blog post
@auth_web_bp.route('/blog/<int:blog_id>/delete')
@login_required
def delete_blog(blog_id):
    post = BlogPost.query.get_or_404(blog_id)

    db.session.delete(post)
    db.session.commit()

    flash('Blog post deleted.', 'info')
    return redirect(url_for('auth_web.manage_resources'))


@auth_web_bp.route('/document/<int:document_id>/delete')
@login_required
def delete_document(document_id):
    """
    Delete a document record and its file.
    Only the uploader (or admins) may delete.
    """
    # 1. Fetch or 404
    doc = Document.query.get_or_404(document_id)

    # 2. Permission check: only uploader or admin
    if doc.uploaded_by != current_user.id and not current_user.is_admin:
        abort(403)

    # 3. Delete file from disk
    upload_folder = current_app.config['UPLOAD_FOLDER']
    file_path = os.path.join(upload_folder, doc.file_path)
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            # Log e if you have a logger; continue anyway
            pass

    # 4. Delete DB record
    db.session.delete(doc)
    db.session.commit()

    # 5. Feedback & redirect
    flash(f"Document “{doc.title}” has been deleted.", 'info')
    return redirect(url_for('auth_web.manage_resources'))


    
@auth_web_bp.route('/document/download/<int:document_id>')
def download_resource_document(document_id):
    # Document download implementation
    pass



@auth_web_bp.route('/api/user/departments')
@login_required
def user_departments():
    return jsonify([{
        'id': dept.id,
        'name': dept.name
    } for dept in current_user.departments])



# In app/auth/routes.py, add session verification
@auth_web_bp.route('/session-check')
@login_required
def session_check():
    return jsonify({
        'user_id': current_user.id,
        'is_authenticated': current_user.is_authenticated
    })



@auth_web_bp.route('/test-notification')
def test_notification():
    # Send to current user
    NotificationService.send_notification(
        title="Test Notification",
        message="This is a test notification",
        recipient_type='user',
        recipient_id=current_user.id,
        notification_type='info',
        icon='fas fa-bell',  # Add icon
        action_url='#'  # Add action URL
    )
    
    # Broadcast test - CORRECTED
    socketio.emit('test_event', {'data': 'Test event data'}, namespace='/')
    
    return jsonify({"status": "test notifications sent"})




import os
import json
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

@auth_web_bp.route('/hospital-profile', methods=['GET', 'POST'])
@login_required
def manage_hospital_profile():
    """
    Manage the single hospital profile in the system.
    """
    profile = HospitalProfile.query.first()
    if not profile:
        profile = HospitalProfile()
        db.session.add(profile)
        db.session.commit()

    if request.method == 'POST':
        form = request.form
        files = request.files
        
        # Handle logo upload
        logo_file = files.get('logo')  # Corrected to match the file input name
        if logo_file and logo_file.filename != '':
            try:
                # Validate file
                if not allowed_file(logo_file.filename):
                    flash('Invalid file type. Only JPG, PNG, GIF allowed.', 'danger')
                else:
                    # Delete old logo if exists
                    if profile.logo_url:
                        try:
                            delete_logo_file(profile.logo_url)
                        except Exception as e:
                            current_app.logger.error(f"Error deleting old logo: {str(e)}")
                            flash('Error removing old logo', 'warning')
                    
                    # Generate unique filename
                    ext = os.path.splitext(logo_file.filename)[1]
                    filename = f"logo_{uuid.uuid4().hex}{ext}"
                    
                    # Save file
                    upload_path = os.path.join(
                        current_app.config['UPLOAD_FOLDER'], 
                        'logos', 
                        filename
                    )
                    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                    logo_file.save(upload_path)
                    
                    # Set logo URL
                    profile.logo_url = url_for('static', filename=f'uploads/logos/{filename}', _external=False)
            except Exception as e:
                current_app.logger.error(f"Logo upload error: {str(e)}")
                flash('Error uploading logo file', 'danger')

        # Core Identification
        profile.name            = form.get('name', profile.name)
        profile.display_name    = form.get('display_name', profile.display_name)
        profile.tagline         = form.get('tagline', profile.tagline)
        profile.motto           = form.get('motto', profile.motto)
        profile.slogan          = form.get('slogan', profile.slogan)
        profile.vision          = form.get('vision', profile.vision)
        profile.mission         = form.get('mission', profile.mission)

        # Contact & Location Details
        profile.address_line1   = form.get('address_line1', profile.address_line1)
        profile.address_line2   = form.get('address_line2', profile.address_line2)
        profile.location        = form.get('location', profile.location)
        profile.city            = form.get('city', profile.city)
        profile.county          = form.get('county', profile.county)
        profile.constituency    = form.get('constituency', profile.constituency)
        profile.ward            = form.get('ward', profile.ward)
        profile.state           = form.get('state', profile.state)
        profile.country         = form.get('country', profile.country) or 'Kenya'
        profile.postal_code     = form.get('postal_code', profile.postal_code)
        profile.primary_contact   = form.get('primary_contact', profile.primary_contact)
        profile.secondary_contact = form.get('secondary_contact', profile.secondary_contact)
        profile.emergency_contact = form.get('emergency_contact', profile.emergency_contact)
        profile.email             = form.get('email', profile.email)
        profile.website           = form.get('website', profile.website)

        # Domain Configuration
        profile.subdomain       = form.get('subdomain', profile.subdomain)
        profile.db_url          = form.get('db_url', profile.db_url)

        # Operational Details
        profile.hospital_type   = form.get('hospital_type', profile.hospital_type)
        
        # Handle integer conversion safely
        try:
            profile.bed_capacity = int(form.get('bed_capacity', profile.bed_capacity)) if form.get('bed_capacity') else None
        except (TypeError, ValueError):
            profile.bed_capacity = None
            flash('Invalid value for bed capacity', 'warning')
        
        # Date handling
        date_fields = ['established_date', 'reg_certificate_issue', 
                      'reg_certificate_expiry', 'license_renewal_date']
        for field in date_fields:
            value = form.get(field)
            if value:
                try:
                    setattr(profile, field, datetime.strptime(value, '%Y-%m-%d').date())
                except ValueError:
                    flash(f'Invalid date format for {field.replace("_", " ")}', 'warning')
        
        # Handle operating hours
        operating_hours = {
            'weekdays': form.get('weekdays_hours', ''),
            'weekends': form.get('weekends_hours', ''),
            'holidays': form.get('holidays_hours', ''),
            'emergency': form.get('emergency_hours', '')
        }
        profile.operating_hours = operating_hours
        
        # Handle array fields
        array_fields = {
            'specialties': form.get('specialties', ''),
            'amenities': form.get('amenities', ''),
            'core_values': form.get('core_values', ''),
            'strategic_goals': form.get('strategic_goals', '')
        }
        
        for field, value in array_fields.items():
            if value:
                # Split comma-separated values and remove empty items
                items = [item.strip() for item in value.split(',') if item.strip()]
                setattr(profile, field, items)
            else:
                setattr(profile, field, [])

        # Kenya-Specific Registration Details
        profile.accreditation   = form.get('accreditation', profile.accreditation)
        profile.hospital_reg_no     = form.get('hospital_reg_no', profile.hospital_reg_no)
        profile.kra_pin             = form.get('kra_pin', profile.kra_pin)
        profile.nhif_no             = form.get('nhif_no', profile.nhif_no)
        profile.nssf_no             = form.get('nssf_no', profile.nssf_no)
        profile.business_permit_no  = form.get('business_permit_no', profile.business_permit_no)
        profile.practice_license_no = form.get('practice_license_no', profile.practice_license_no)
        profile.pharmacy_license_no = form.get('pharmacy_license_no', profile.pharmacy_license_no)
        profile.radiation_board_no  = form.get('radiation_board_no', profile.radiation_board_no)
        profile.waste_license_no    = form.get('waste_license_no', profile.waste_license_no)

        # Additional Metadata
        profile.description = form.get('description', profile.description)

        try:
            db.session.commit()
            flash('Hospital profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database error: {str(e)}")
            flash('Error saving profile to database', 'danger')

        return redirect(url_for('auth_web.manage_hospital_profile'))
    return render_template('manage_hospital_profile.html', profile=profile)

def allowed_file(filename):
    """Check if file has allowed extension"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def delete_logo_file(logo_url):
    """Delete logo file from filesystem"""
    try:
        if logo_url.startswith('/static/'):
            # Convert URL to filesystem path
            relative_path = logo_url[len('/static/'):]
            file_path = os.path.join(current_app.static_folder, relative_path)
            if os.path.exists(file_path):
                os.remove(file_path)
    except Exception as e:
        current_app.logger.error(f"Error deleting logo file: {str(e)}")
        raise




# Add this to your config.py
SECRET_KEY = 'efyhry55@$$3dcxhh'  # Should be a long, random string
SECURITY_PASSWORD_SALT = 'pass@2025'

# Initialize the token serializer
def get_token_serializer():
    return URLSafeTimedSerializer(SECRET_KEY)

@auth_web_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate a password reset token
            serializer = get_token_serializer()
            token = serializer.dumps(email, salt=SECURITY_PASSWORD_SALT)
            
            # Create reset link
            reset_url = url_for('auth_web.reset_password', token=token, _external=True)
            
            # Send password reset email with improved sender info
            try:
                msg = Message(
                    subject="Reset Your AstroCare Password",
                    sender=("AstroCare Support", "support@astrocare.example.com"),
                    recipients=[email],
                    html=render_template('email/reset_password.html', 
                                        reset_url=reset_url,
                                        user=user,
                                        current_year=datetime.now().year)
                )
                mail.send(msg)
                flash('Password reset instructions have been sent to your email.', 'success')
            except Exception as e:
                current_app.logger.error(f"Error sending password reset email: {str(e)}")
                flash('We encountered an issue sending the reset email. Please try again later.', 'danger')
        else:
            # Show success message even if email doesn't exist (for security)
            flash('If your email is registered with us, you will receive password reset instructions shortly.', 'success')
        
        return redirect(url_for('auth_web.forgot_password'))
    
    return render_template('forgot_password.html')

@auth_web_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'GET':
        # Validate token
        serializer = get_token_serializer()
        try:
            email = serializer.loads(
                token,
                salt=SECURITY_PASSWORD_SALT,
                max_age=3600  # Token valid for 1 hour
            )
            user = User.query.filter_by(email=email).first()
            if not user:
                flash('Invalid password reset token.', 'danger')
                return redirect(url_for('auth_web.forgot_password'))
            
            return render_template('reset_password.html', token=token)
        except:
            flash('The password reset link is invalid or has expired.', 'danger')
            return redirect(url_for('auth_web.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        token = request.form.get('token')
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        
        # Validate token again
        serializer = get_token_serializer()
        try:
            email = serializer.loads(
                token,
                salt=SECURITY_PASSWORD_SALT,
                max_age=3600
            )
            user = User.query.filter_by(email=email).first()
            if not user:
                flash('Invalid password reset token.', 'danger')
                return redirect(url_for('auth_web.forgot_password'))
            
            # Update password
            user.password = password  # Assuming you have a set_password method
            db.session.commit()
            
            flash('Your password has been updated! You can now log in.', 'success')
            return redirect(url_for('auth_web.login'))
        except:
            flash('The password reset link is invalid or has expired.', 'danger')
            return redirect(url_for('auth_web.forgot_password'))


@auth_web_bp.route('/setup-2fa', methods=['POST'])
@login_required
def setup_2fa():
    method = request.form.get('method')
    destination = request.form.get('destination')
    
    # Validate input
    if method not in ['email', 'sms']:
        return jsonify({'success': False, 'message': 'Invalid verification method'}), 400
    
    if method == 'email' and not validate_email(destination):
        return jsonify({'success': False, 'message': 'Invalid email address'}), 400
    
    if method == 'sms' and not validate_phone(destination):
        return jsonify({'success': False, 'message': 'Invalid phone number'}), 400
    
    # Create new 2FA method (temporary until verified)
    new_method = TwoFactorMethod(
        user_id=current_user.id,
        method=method,
        destination=destination,
        is_primary=False,
        verified=False
    )
    
    db.session.add(new_method)
    db.session.commit()
    
    # Send verification code
    send_verification_code(new_method)
    
    return jsonify({
        'success': True,
        'message': 'Verification code sent!',
        'method_id': new_method.id  # Return the ID for verification
    })

@auth_web_bp.route('/verify-2fa-setup', methods=['POST'])
@login_required
def verify_2fa_setup():
    data = request.get_json()
    method_id = data.get('method_id')  # Get method ID directly
    code = data.get('code')
    
    # Find the method by ID and user ID
    method_obj = TwoFactorMethod.query.filter_by(
        id=method_id,
        user_id=current_user.id
    ).first()
    
    if not method_obj:
        return jsonify({'success': False, 'message': 'Method not found'}), 404
    
    if verify_code(method_obj, code):
        # Mark as verified and set as primary
        method_obj.verified = True
        method_obj.is_primary = True
        
        # Deactivate other primary methods
        TwoFactorMethod.query.filter(
            TwoFactorMethod.user_id == current_user.id,
            TwoFactorMethod.is_primary == True,
            TwoFactorMethod.id != method_obj.id
        ).update({'is_primary': False})
        
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Invalid verification code'}), 400

@auth_web_bp.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    # Must be in a 2FA session
    if '2fa_user_id' not in session:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth_web.login'))

    user = User.query.get(session['2fa_user_id'])
    ip = request.remote_addr or 'unknown'

    if not user:
        flash('User session expired. Please log in again.', 'danger')
        session.pop('2fa_user_id', None)
        session.pop('remember_me', None)
        return redirect(url_for('auth_web.login'))

    # Get primary 2FA method
    primary_method = user.two_factor_methods.filter_by(
        is_primary=True,
        verified=True
    ).first()

    if not primary_method:
        log_audit_event(
            'LOGIN',
            target=user,
            connection=None,
            success=False,
            details_extra={'reason': 'no_primary_2fa', 'ip': ip}
        )
        flash('No valid 2FA method found. Please contact support.', 'danger')
        session.pop('2fa_user_id', None)
        session.pop('remember_me', None)
        return redirect(url_for('auth_web.login'))

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()

        if verify_code(primary_method, code):
            # Finalize login
            remember = session.pop('remember_me', False)
            login_user(user, remember=remember)

            # Update timestamps
            user.last_login_at = datetime.utcnow()
            primary_method.last_used = datetime.utcnow()
            db.session.commit()

            # Clear session
            session.pop('2fa_user_id', None)

            log_audit_event(
                'LOGIN',
                target=user,
                connection=None,
                success=True,
                details_extra={'method': '2fa', 'ip': ip}
            )

            flash('Logged in successfully!', 'success')
            return redirect_after_login(user)
        else:
            log_audit_event(
                'LOGIN',
                target=user,
                connection=None,
                success=False,
                details_extra={'reason': '2fa_invalid_code', 'ip': ip}
            )
            flash('Invalid verification code.', 'danger')

    # Mask destination for display (email/phone)
    masked_destination = mask_sensitive(primary_method.destination)
    return render_template(
        'verify_2fa_login.html',
        method=primary_method.method,
        masked_destination=masked_destination
    )


def send_verification_code(method):
    code = generate_verification_code()
    
    # Use the cache instance
    current_app.cache.set(f'2fa_code:{method.id}', code, timeout=600)
    
    if method.method == 'email':
        msg = Message(
            "Your AstroCare Verification Code",
            sender=("AstroCare Support", "support@astrocare.example.com"),
            recipients=[method.destination]
        )
        msg.html = render_template(
            'email/2fa_code.html', 
            code=code,
            current_year=datetime.now().year
        )
        mail.send(msg)
    elif method.method == 'sms':
        # Implement SMS sending logic here
        # Example: twilio_client.messages.create(...)
        pass

def verify_code(method, code):
    cached_code = current_app.cache.get(f'2fa_code:{method.id}')
    return cached_code and cached_code == code

# Generate random 6-digit code
def generate_verification_code():
    return str(random.randint(100000, 999999))




# Add these routes to your auth_web_bp blueprint

@auth_web_bp.route('/disable-2fa', methods=['POST'])
@login_required
def disable_2fa():
    # Delete all 2FA methods for the current user
    TwoFactorMethod.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True})

@auth_web_bp.route('/delete-2fa/<int:method_id>', methods=['POST'])
@login_required
def delete_2fa(method_id):
    method = TwoFactorMethod.query.get_or_404(method_id)
    if method.user_id != current_user.id:
        return jsonify({'success': False}), 403
    db.session.delete(method)
    db.session.commit()
    return jsonify({'success': True})

@auth_web_bp.route('/resend-2fa-code', methods=['POST'])
@login_required
def resend_2fa_code():
    data = request.get_json()
    method = data.get('method')
    destination = data.get('destination')
    
    # Find existing method or create a temporary one
    method_obj = TwoFactorMethod.query.filter_by(
        user_id=current_user.id,
        method=method,
        destination=destination
    ).first()
    
    if not method_obj:
        method_obj = TwoFactorMethod(
            user_id=current_user.id,
            method=method,
            destination=destination
        )
    
    # Send verification code
    send_verification_code(method_obj)
    
    return jsonify({'success': True})




@auth_web_bp.route('/resend-2fa-login', methods=['POST'])
def resend_2fa_login():
    if '2fa_user_id' not in session:
        return jsonify({'success': False, 'message': 'Session expired'}), 400
    
    user = User.query.get(session['2fa_user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    primary_method = user.two_factor_methods.filter_by(
        is_primary=True, 
        verified=True
    ).first()
    
    if not primary_method:
        return jsonify({'success': False, 'message': 'No valid 2FA method'}), 400
    
    send_verification_code(primary_method)
    return jsonify({'success': True})




@auth_web_bp.route('/form-templates')
@login_required
def form_templates():
    # Get search query
    search_query = request.args.get('q', '').strip().lower()
    
    # Get filter query
    category_filter = request.args.get('category', '').strip()
    
    # Get all templates
    templates = FormTemplate.query.filter_by(is_active=True).order_by(FormTemplate.uploaded_at.desc()).all()
    
    # Get all unique categories
    categories = sorted(set([t.category for t in templates]))
    
    # Apply search filter
    if search_query:
        templates = [t for t in templates if 
                     search_query in t.template_name.lower() or 
                     (t.description and search_query in t.description.lower())]
    
    # Apply category filter
    if category_filter:
        templates = [t for t in templates if t.category == category_filter]
    
    # Group templates by category
    grouped_templates = {}
    for template in templates:
        if template.category not in grouped_templates:
            grouped_templates[template.category] = []
        grouped_templates[template.category].append(template)
    
    # Get most downloaded template
    most_downloaded = max(templates, key=lambda x: x.download_count, default=None)
    
    # Get stats
    stats = {
        'total_templates': len(templates),
        'most_downloaded': most_downloaded.template_name if most_downloaded else 'N/A',
        'last_added': templates[0].template_name if templates else 'N/A'
    }
    
    return render_template('form_templates.html', 
                          grouped_templates=grouped_templates,
                          categories=categories,
                          stats=stats,
                          search_query=search_query,
                          category_filter=category_filter)
    
    
@auth_web_bp.route('/form-builder/create')
@login_required
def create_template():
    """Form builder engine interface"""
    return render_template('form_builder.html', now=datetime.utcnow())


@auth_web_bp.route('/upload-template', methods=['POST'])
@login_required
def upload_template():
    # Get form data
    template_name = request.form.get('template_name')
    category = request.form.get('category')
    version = request.form.get('version')
    description = request.form.get('description')
    file = request.files.get('file')
    
    # Validate required fields
    if not all([template_name, category, file]):
        flash('Template name, category, and file are required', 'error')
        return redirect(url_for('auth_web.form_templates'))
    
    # Validate file type and size
    allowed_extensions = {'pdf', 'doc', 'docx', 'xls', 'xlsx'}
    max_size = 10 * 1024 * 1024  # 10MB
    
    if file:
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_ext not in allowed_extensions:
            flash('Invalid file type. Allowed types: PDF, DOC, DOCX, XLS, XLSX', 'error')
            return redirect(url_for('auth_web.form_templates'))
        
        if len(file.read()) > max_size:
            flash('File size exceeds 10MB limit', 'error')
            return redirect(url_for('auth_web.form_templates'))
        file.seek(0)  # Reset file pointer after reading
        
        # Create unique filename
        unique_id = uuid.uuid4().hex
        new_filename = f"{unique_id}_{filename}"
        
        # Create upload path
        upload_dir = os.path.join(
            current_app.config['UPLOAD_FOLDER'], 
            'form_templates'
        )
        os.makedirs(upload_dir, exist_ok=True)
        upload_path = os.path.join(upload_dir, new_filename)
        
        try:
            # Save file
            file.save(upload_path)
            
            # Create and save template record
            new_template = FormTemplate(
                template_name=template_name,
                category=category,
                version=version or '1.0',
                description=description,
                file_path=upload_path,
                file_name=filename,
                uploaded_by=current_user.id
            )
            
            db.session.add(new_template)
            db.session.commit()
            
            flash('Template uploaded successfully!', 'success')
            return redirect(url_for('auth_web.form_templates'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error uploading template: {str(e)}")
            flash('Error uploading template. Please try again.', 'error')
            return redirect(url_for('auth_web.form_templates'))
    
    flash('No file uploaded', 'error')
    return redirect(url_for('auth_web.form_templates'))


@auth_web_bp.route('/download-template/<int:template_id>')
@login_required
def download_template(template_id):
    template = FormTemplate.query.get_or_404(template_id)
    return send_file(template.file_path, as_attachment=True, download_name=template.file_name)



@auth_web_bp.route('/notifications/<int:notification_id>/dismiss', methods=['POST'])
@login_required
def dismiss_notification(notification_id):
    """
    Marks a single notification as read/dismissed for the current user.
    """
    # Find the NotificationRead record for this user and notification
    notification_read_record = NotificationRead.query.filter_by(
        user_id=current_user.id,
        notification_id=notification_id
    ).first()

    if not notification_read_record:
        return jsonify({'message': 'Notification not found or already dismissed for this user.'}), 200

    try:
        # Mark as dismissed (using your 'dismissed' column)
        notification_read_record.dismissed = True
        notification_read_record.read_at = datetime.utcnow() # Update read_at timestamp when dismissed
        
        db.session.commit()
        return jsonify({'message': 'Notification dismissed successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error dismissing notification {notification_id} for user {current_user.id}: {e}")
        return jsonify({'error': 'Failed to dismiss notification.'}), 500


@auth_web_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_as_read():
    """
    Marks all unread notifications for the current user as read (dismissed).
    """
    try:
        # Find all un-dismissed NotificationRead records for the current user
        # Note: 'dismissed=False' is used to find "unread" notifications
        unread_notifications = NotificationRead.query.filter_by(
            user_id=current_user.id,
            dismissed=False # Corrected column name
        ).all()

        # Update each record to 'dismissed' and set read_at
        for record in unread_notifications:
            record.dismissed = True # Corrected column name
            record.read_at = datetime.utcnow() # Set the time they were read
        
        db.session.commit()
        return jsonify({'message': 'All notifications marked as read.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking all notifications as read for user {current_user.id}: {e}")
        return jsonify({'error': 'Failed to mark all notifications as read.'}), 500