# /home/pincho/Desktop/astrocare/app/user_management/routes.py
from datetime import datetime
from flask import current_app, flash, render_template, request, redirect, url_for
from flask import Blueprint, request, jsonify, abort
from flask_login import current_user, login_required
from app.extensions import db
from app.auth.models import Role, User
from app.notifications.services import NotificationService
from app.user_management.models import EmployeeBio, Privilege, role_privileges

from . import user_management_web_bp


@user_management_web_bp.route('/create_user', methods=['POST'])
@login_required # Ensure the user creating the account is logged in
def handle_create_user():
    full_name = request.form.get('full_name')
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    role_id = request.form.get('role_id')
    department_id = request.form.get('department_id')

    # Validation
    if not all([full_name, username, email, password, confirm_password, role_id, department_id]):
        flash("All fields are required.", "error")
        return redirect(url_for('user_management_web.create_user'))

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for('user_management_web.create_user'))

    existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        flash("Username or email already exists.", "error")
        return redirect(url_for('user_management_web.create_user'))
    
    role = Role.query.get(role_id)
    if not role:
        flash("Invalid role selected.", "error")
        return redirect(url_for('user_management_web.create_user'))
    
    department = Department.query.get(department_id)
    if not department:
        flash("Invalid department selected.", "error")
        return redirect(url_for('user_management_web.create_user'))

    new_user = User(
        full_name=full_name,
        username=username,
        email=email,
        department_id=department_id,
        created_at=datetime.utcnow()
    )
    new_user.roles.append(role)

    new_user.password = password  # Uses @password.setter to hash

    db.session.add(new_user)
    
    try:
        db.session.commit()

        # --- Send Notifications ---

        # 1. Notification to Department Administrator
        # Find the 'Administrator' department ID
        admin_department = Department.query.filter_by(name='Administrator').first()
        
        if admin_department:
            notification_title_admin = "New User Created"
            notification_message_admin = (
                f"User '{new_user.full_name}' ({new_user.username}) "
                f"with role '{role.name}' in department '{department.name}' "
                f"was created by '{current_user.full_name or current_user.username}' "
                f"from department '{current_user.department.name if current_user.department else 'N/A'}'.")
            
            NotificationService.send_notification(
                title=notification_title_admin,
                message=notification_message_admin,
                recipient_type='department',
                recipient_id=admin_department.id,
                notification_type='success', # or 'info'
                icon='user-plus',
                sender_id=current_user.id
            )
            current_app.logger.info(f"Notification sent to Administrator department for new user {new_user.username}")
        else:
            current_app.logger.warning("Administrator department not found for sending new user notification.")

        # 2. Welcome Notification to the newly created user
        notification_title_welcome = "Welcome to AstroCare!"
        notification_message_welcome = (
            f"Dear {new_user.full_name or new_user.username}, "
            "Your account has been successfully created. "
            "You can now log in using your credentials. "
            "If you have any questions, please contact your administrator.")
        
        NotificationService.send_notification(
            title=notification_title_welcome,
            message=notification_message_welcome,
            recipient_type='user',
            recipient_id=new_user.id,
            notification_type='info',
            icon='handshake',
            action_url=url_for('auth_web.login', _external=True), # Link to login page
            sender_id=current_user.id # Or 'System' if you prefer an automated sender
        )
        current_app.logger.info(f"Welcome notification sent to new user {new_user.username}")


        flash(f"User '{new_user.full_name}' created successfully. Notifications sent.", "success")
        return redirect(url_for('user_management_web.create_user')) 

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user or sending notification: {e}", exc_info=True)
        flash(f"Failed to create user: {e}", "error")
        return redirect(url_for('user_management_web.create_user'))



@user_management_web_bp.route('/create_user', methods=['GET'])
@login_required # Ensure user is logged in to access current_user
def create_user():
    # Load all departments initially
    all_departments = Department.query.order_by(Department.name).all()
    
    # Filter departments based on current user's department
    departments_for_frontend = []
    if current_user.department and current_user.department.name == 'Information Technology':
        # If current user is from 'IT' department, exclude 'Administrator' department
        for dept in all_departments:
            if dept.name != 'Administrator':
                departments_for_frontend.append(dept)
    else:
        # For any other user, show all departments
        departments_for_frontend = all_departments

    # GET: render the form with filtered departments list
    return render_template(
        'create_user.html',
        departments=departments_for_frontend
    )


# — List all roles —
@user_management_web_bp.route('/api/roles', methods=['GET'])
@login_required # Ensure user is logged in to access current_user
def api_list_roles():
    # Load all roles initially
    all_roles = Role.query.order_by(Role.name).all()
    
    # Filter roles based on current user's department
    roles_for_frontend = []
    if current_user.department and current_user.department.name == 'Information Technology':
        # If current user is from 'IT' department, exclude 'Admin' role
        for role in all_roles:
            if role.name != 'Admin':
                roles_for_frontend.append(role)
    else:
        # For any other user, show all roles
        roles_for_frontend = all_roles

    return jsonify([{'id': r.id, 'name': r.name} for r in roles_for_frontend])

# — Create or update a role —
@user_management_web_bp.route('/api/roles', methods=['POST', 'PUT'])
@login_required # Ensure user is logged in to get current_user details for notification sender
def api_save_role():
    data = request.get_json() or {}
    role_id = data.get('id')
    name = data.get('name')

    if not name:
        return abort(400, 'Missing role name')

    action = "updated" # Default action for PUT
    if role_id:
        role = Role.query.get_or_404(role_id)
        original_name = role.name # Store original name for notification
        role.name = name
    else:
        role = Role(name=name)
        db.session.add(role)
        action = "created" # Action for POST
        original_name = None # No original name if created

    try:
        db.session.commit()

        # --- Send Notification to Administrator ---
        admin_department = Department.query.filter_by(name='Administrator').first()

        if admin_department:
            notification_title = "Role Management Activity"
            
            if action == "created":
                notification_message = (
                    f"New role '{role.name}' was created by "
                    f"'{current_user.full_name or current_user.username}' "
                    f"from department '{current_user.department.name if current_user.department else 'N/A'}'."
                )
            else: # updated
                notification_message = (
                    f"Role '{original_name}' was updated to '{role.name}' by "
                    f"'{current_user.full_name or current_user.username}' "
                    f"from department '{current_user.department.name if current_user.department else 'N/A'}'."
                )
            
            NotificationService.send_notification(
                title=notification_title,
                message=notification_message,
                recipient_type='department',
                recipient_id=admin_department.id,
                notification_type='info',
                icon='user-tag', # Icon for role related activity
                sender_id=current_user.id
            )
            current_app.logger.info(f"Notification sent to Administrator department for role {action}: {role.name}")
        else:
            current_app.logger.warning("Administrator department not found for sending role management notification.")

        return jsonify({'id': role.id, 'name': role.name, 'action': action})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving role or sending notification: {e}", exc_info=True)
        return abort(500, f'Failed to save role: {str(e)}')


# — Delete a role —
@user_management_web_bp.route('/api/roles/<int:role_id>', methods=['DELETE'])
@login_required # Ensure user is logged in to get current_user details for notification sender
def api_delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    role_name = role.name # Store the name before deleting for the notification

    try:
        db.session.delete(role)
        db.session.commit()

        # --- Send Notification to Administrator ---
        admin_department = Department.query.filter_by(name='Administrator').first()

        if admin_department:
            notification_title = "Role Management Activity"
            notification_message = (
                f"Role '{role_name}' was deleted by "
                f"'{current_user.full_name or current_user.username}' "
                f"from department '{current_user.department.name if current_user.department else 'N/A'}'."
            )
            
            NotificationService.send_notification(
                title=notification_title,
                message=notification_message,
                recipient_type='department',
                recipient_id=admin_department.id,
                notification_type='warning', # Warning type for deletion
                icon='trash', # Icon for deletion
                sender_id=current_user.id
            )
            current_app.logger.info(f"Notification sent to Administrator department for deleted role: {role_name}")
        else:
            current_app.logger.warning("Administrator department not found for sending role management notification.")

        return jsonify({'status': 'deleted', 'role_name': role_name})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting role or sending notification: {e}", exc_info=True)
        return abort(500, f'Failed to delete role: {str(e)}')


# — List all privileges —
@user_management_web_bp.route('/api/privileges', methods=['GET'])
def api_list_privileges():
    privs = Privilege.query.order_by(Privilege.module, Privilege.name).all()
    return jsonify([{'id': p.id, 'module': p.module, 'name': p.name, 'description': p.description} for p in privs])

# — List privileges for one role —
@user_management_web_bp.route('/api/roles/<int:role_id>/privileges', methods=['GET'])
def api_role_privileges(role_id):
    role = Role.query.get_or_404(role_id)
    return jsonify([p.id for p in role.privileges])

# — Save privileges for one role —
@user_management_web_bp.route('/api/roles/<int:role_id>/privileges', methods=['POST'])
@login_required # Ensure user is logged in to get current_user details for notification sender
def api_save_role_privileges(role_id):
    data = request.get_json(silent=True) or {}
    new_privilege_ids = set(data.get('privilege_ids', [])) # Convert to set for efficient comparison

    current_app.logger.debug(f"api_save_role_privileges called for role_id={role_id}")
    current_app.logger.debug(f"Received privilege_ids: {new_privilege_ids}")

    role = Role.query.get_or_404(role_id)
    
    # 1. Get current privileges BEFORE the update
    # Convert to set for efficient comparison
    current_privileges = set(role.privileges)
    current_privilege_ids = {p.id for p in current_privileges}
    current_privilege_names = {p.name for p in current_privileges}
    
    current_app.logger.debug(f"Loaded Role: {role.name} (current privilege IDs: {current_privilege_ids})")

    # Query the selected Privilege objects (the new set)
    # Ensure all requested IDs correspond to actual privileges
    all_privileges = {p.id: p for p in Privilege.query.all()} # Map ID to object for easy lookup

    privs_to_assign = []
    for pid in new_privilege_ids:
        if pid in all_privileges:
            privs_to_assign.append(all_privileges[pid])
        else:
            current_app.logger.warning(f"Attempted to assign non-existent privilege ID: {pid}")
            # Optionally, you could abort here if you want strict validation
            # return abort(400, f"Invalid privilege ID: {pid}")

    # Store the actual Privilege objects that will be assigned for later use in notification
    new_assigned_privileges = set(privs_to_assign)
    new_assigned_privilege_ids = {p.id for p in new_assigned_privileges}
    new_assigned_privilege_names = {p.name for p in new_assigned_privileges}


    # 2. Update the role's privileges (in memory)
    role.privileges = privs_to_assign
    
    try:
        # Commit the changes to the database
        db.session.commit()
        current_app.logger.debug(f"After commit, Role privileges: {[p.id for p in role.privileges]}")

        # 3. Calculate Differences for Notification
        added_privilege_ids = new_assigned_privilege_ids - current_privilege_ids
        removed_privilege_ids = current_privilege_ids - new_assigned_privilege_ids

        # Get names for added/removed privileges for a human-readable message
        added_privilege_names = [all_privileges[pid].name for pid in added_privilege_ids if pid in all_privileges]
        removed_privilege_names = [all_privileges[pid].name for pid in removed_privilege_ids if pid in all_privileges]

        # --- Send Notification to Administrator ---
        admin_department = Department.query.filter_by(name='Administrator').first()

        if admin_department:
            notification_title = f"Role Privileges Updated: {role.name}"
            notification_message_parts = []
            
            if added_privilege_names:
                notification_message_parts.append(f"Added: {', '.join(added_privilege_names)}")
            if removed_privilege_names:
                notification_message_parts.append(f"Removed: {', '.join(removed_privilege_names)}")
            
            if not notification_message_parts:
                # If no changes were actually made (e.g., frontend sent same list)
                notification_message_parts.append("No changes were applied to privileges.")
                notification_type = 'info'
            else:
                notification_type = 'warning' if removed_privilege_names else 'info'

            notification_message = (
                f"Privileges for role '{role.name}' were modified by "
                f"'{current_user.full_name or current_user.username}' "
                f"from department '{current_user.department.name if current_user.department else 'N/A'}'.\n"
                f"{'; '.join(notification_message_parts)}"
            )

            NotificationService.send_notification(
                title=notification_title,
                message=notification_message,
                recipient_type='department',
                recipient_id=admin_department.id,
                notification_type=notification_type,
                icon='lock', # A good icon for privilege changes
                sender_id=current_user.id
            )
            current_app.logger.info(f"Notification sent to Administrator department for role privilege update for {role.name}")
        else:
            current_app.logger.warning("Administrator department not found for sending role privilege notification.")

        return jsonify({'status': 'ok'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving role privileges or sending notification: {e}", exc_info=True)
        return abort(500, f'Failed to save role privileges: {str(e)}')


@user_management_web_bp.route('/api/employees', methods=['GET'])
def api_list_employees():
    from app.auth.models import User
    emps = User.query.order_by(User.full_name).all()
    return jsonify([
        {
            'id': e.id,
            'full_name': e.full_name,
            'department': e.department.name if e.department else ''
        } for e in emps
    ])


@user_management_web_bp.route('/api/employees/<int:emp_id>', methods=['GET'])
def api_get_employee(emp_id):
    from app.auth.models import User
    e = User.query.get_or_404(emp_id)

    # Now using the correct backref name: e.bio
    bio = e.bio  # This will be None if no bio exists

    return jsonify({
        'id': e.id,
        'full_name': e.full_name,
        'department': e.department.name if e.department else '',
        'dob': bio.dob.isoformat() if bio and bio.dob else None,
        'gender': bio.gender if bio else None,
        'phone': bio.phone if bio else None,
        'address': bio.address if bio else None,
        'emergency_contact_name': bio.emergency_contact_name if bio else None,
        'emergency_contact_phone': bio.emergency_contact_phone if bio else None,
    })


@user_management_web_bp.route('/employees/bio', methods=['POST'])
def save_employee_bio():
    """
    Handles submission of the bio‐data form for one employee.
    """
    # 1) pull out the form values
    emp_id = request.form.get('employee_id', type=int)
    if not emp_id:
        flash('No employee selected.', 'danger')
        return redirect(url_for('user_management_web.create_user'))

    # 2) find or create the bio record
    bio = EmployeeBio.query.filter_by(user_id=emp_id).first()
    if bio is None:
        bio = EmployeeBio(user_id=emp_id, created_at=datetime.utcnow())
        db.session.add(bio)

    # 3) populate all your fields
    bio.dob                   = request.form.get('date_of_birth') or None
    bio.gender                = request.form.get('gender') or None
    bio.phone                 = request.form.get('phone_number')
    bio.address               = request.form.get('address')
    bio.national_id           = request.form.get('national_id')
    bio.bank_name             = request.form.get('bank_name')
    bio.bank_account_number   = request.form.get('bank_account_number')
    bio.emergency_contact_name  = request.form.get('emergency_contact_name')
    bio.emergency_contact_phone = request.form.get('emergency_contact_phone')
    bio.insurance_provider      = request.form.get('insurance_provider')
    bio.insurance_number        = request.form.get('insurance_number')
    # … any other fields …

    # 4) commit
    db.session.commit()
    flash('Employee bio saved successfully!', 'success')

    # 5) redirect back to the same page (or anywhere you like)
    return redirect(url_for('user_management_web.create_user'))




from app.auth.models import User, Role
from app.user_management.models import EmployeeBio, Department

@user_management_web_bp.route('/manage_users', methods=['GET'])

def manage_users():
    # Fetch all users with their departments
    users = User.query.options(db.joinedload(User.department)).all()
    
    # Prepare user data with roles
    user_data = []
    for user in users:
        # Load roles for each user separately
        roles = user.roles.all()
        user_data.append({
            'id': user.id,
            'full_name': user.full_name,
            'username': user.username,
            'email': user.email,
            'department': user.department.name if user.department else 'N/A',
            'roles': ', '.join([role.name for role in roles]),
            'is_active': user.is_active,
            'last_login': user.last_login_at.strftime('%Y-%m-%d %H:%M') if user.last_login_at else 'Never',
            'created_at': user.created_at.strftime('%Y-%m-%d') if user.created_at else '',
        })
    
    # Get statistics
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    departments = Department.query.count()
    roles = Role.query.count()
    
    return render_template('manage_users.html',
                           users=user_data,
                           total_users=total_users,
                           active_users=active_users,
                           departments=departments,
                           roles=roles)


@user_management_web_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])


def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Update user information
        user.full_name = request.form.get('full_name')
        user.email = request.form.get('email')
        user.department_id = request.form.get('department_id')
        
        # Update roles
        role_ids = request.form.getlist('roles')
        user.roles = Role.query.filter(Role.id.in_(role_ids)).all()
        
        # Update active status
        user.is_active = 'is_active' in request.form
        
        db.session.commit()
        flash('User information updated successfully!', 'success')
        return redirect(url_for('user_management_web.manage_users'))
    
    # For GET request
    departments = Department.query.all()
    all_roles = Role.query.all()
    user_roles = [role.id for role in user.roles]
    
    return render_template('edit_user.html',
                           user=user,
                           departments=departments,
                           all_roles=all_roles,
                           user_roles=user_roles)
# --- Toggle User Active / Inactive Status ---
@user_management_web_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    """
    Activate or deactivate a user.
    """
    user = User.query.get_or_404(user_id)

    try:
        # Switch the status
        user.is_active = not user.is_active
        user.updated_at = datetime.utcnow()  # optional if you track update times

        db.session.commit()

        # Send notification (optional)
        status_text = "activated" if user.is_active else "deactivated"
        admin_department = Department.query.filter_by(name='Administrator').first()

        if admin_department:
            NotificationService.send_notification(
                title="User Status Changed",
                message=(
                    f"User '{user.full_name}' was {status_text} by "
                    f"'{current_user.full_name or current_user.username}' "
                    f"from department '{current_user.department.name if current_user.department else 'N/A'}'."
                ),
                recipient_type="department",
                recipient_id=admin_department.id,
                notification_type="info",
                icon="user-check" if user.is_active else "user-slash",
                sender_id=current_user.id,
            )

        flash(f"User '{user.full_name}' has been {status_text}.", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling user status: {e}", exc_info=True)
        flash("An error occurred while updating the user status.", "error")

    return redirect(url_for("user_management_web.manage_users"))


@user_management_web_bp.route('/change_password/<int:user_id>', methods=['GET', 'POST'])
def change_password(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('user_management_web.change_password', user_id=user_id))
        
        user.password = new_password
        db.session.commit()
        flash('Password changed successfully!', 'success')
        return redirect(url_for('user_management_web.manage_users'))
    
    return render_template('change_password.html', user=user)