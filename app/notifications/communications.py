# app/notifications/communications.py

from flask import Blueprint, abort, current_app, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db
from datetime import date, datetime, timedelta, timezone

from app.appointments.models import Appointment
from app.notifications.models import MessageTemplate, PatientSMSLog, SMSBroadcast

# Import TemplateForm (adjust the import path if your form is defined elsewhere)
from app.notifications.forms import TemplateForm
from app.notifications.tasks import queue_sms_broadcast, send_sms_broadcast
from app.patients.models import Patient
from app.utils.notifications import notification_manager
# Create Blueprint
comms_web_bp = Blueprint('comms_web_bp', __name__,
                         template_folder='templates',
                         static_folder='static',
                         url_prefix='/communications')

# ---------------------------
# Engagement Dashboard Route
# ---------------------------
@comms_web_bp.route('/dashboard', methods=['GET'])
@login_required
def comms_dashboard():
    """Communication engagement dashboard"""
    # Sample data for dashboard metrics
    metrics = {
        'sms_sent': 1250,
        'email_sent': 842,
        'delivery_rate': 92.4,
        'open_rate': 78.2,
        'feedback_responses': 367
    }
    
    # Recent activity log
    recent_activity = [
        {'type': 'SMS', 'target': 'Patients', 'count': 250, 'date': '2025-07-10', 'status': 'Delivered'},
        {'type': 'Email', 'target': 'Staff', 'count': 120, 'date': '2025-07-09', 'status': 'Sent'},
        {'type': 'Reminder', 'target': 'Appointments', 'count': 84, 'date': '2025-07-08', 'status': 'Processed'}
    ]
    
    return render_template('communications/dashboard.html', 
                          metrics=metrics, 
                          recent_activity=recent_activity,
                          title='Engagement Dashboard')

# --------------------------------
# Patient SMS Broadcast Route
# --------------------------------
@comms_web_bp.route('/sms/patients', methods=['GET', 'POST'])
@login_required
def bulk_sms_patients():
    """Bulk SMS to patients"""
    if request.method == 'POST':
        # Process form submission
        message = request.form.get('message')
        patient_group = request.form.get('patient_group')
        schedule = request.form.get('schedule')
        
        # Validate inputs
        if not message:
            flash('Message content is required', 'danger')
        else:
            # In a real app, this would send to SMS gateway
            flash(f'SMS scheduled for {patient_group} group!', 'success')

            return redirect(url_for('comms_web_bp.bulk_sms_patients'))
    
    return render_template('communications/sms_patients.html', 
                          title='Patient SMS Broadcast')


@comms_web_bp.route('/api/patient-groups', methods=['GET'])
@login_required
def get_patient_groups():
    """Get patient group statistics for broadcasting"""
    try:
        # Calculate patient groups dynamically
        all_patients = Patient.query.count()
        
        # Upcoming appointments (next 30 days)
        upcoming_count = Appointment.query.filter(
            Appointment.status == 'scheduled',
            Appointment.scheduled_for > datetime.utcnow(),
            Appointment.scheduled_for < datetime.utcnow() + timedelta(days=30)
        ).count()
        
        # New patients (last 30 days)
        new_patients = Patient.query.filter(
            Patient.created_at > datetime.utcnow() - timedelta(days=30)
        ).count()
        
        return jsonify({
            'groups': {
                'all': {'name': 'All Patients', 'count': all_patients},
                'appointments': {'name': 'Upcoming Appointments', 'count': upcoming_count},
                'new_patients': {'name': 'New Patients (Last 30d)', 'count': new_patients}
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@comms_web_bp.route('/api/message-templates', methods=['GET'])
@login_required
def get_message_templates():
    """Get SMS message templates with names"""
    try:
        templates = MessageTemplate.query.filter_by(
            template_type='sms',
            category='patient'
        ).all()
        
        templates_dict = {}
        for template in templates:
            # Use both name and content
            templates_dict[template.name.lower().replace(' ', '_')] = {
                'name': template.name,
                'content': template.content
            }
        
        return jsonify({'templates': templates_dict})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ---------------------------
# Send Broadcast Endpoint
# ---------------------------
from datetime import datetime, time

@comms_web_bp.route('/send-broadcast', methods=['POST'])
@login_required
def send_broadcast():
    """Process and send an SMS broadcast."""
    data = request.json
    message = data.get('message')
    recipient_type = data.get('recipient_type')  # 'group' or 'individual'
    recipient_data = data.get('recipient_data')
    schedule = data.get('schedule', {})

    # Validate
    if not message:
        return jsonify({'error': 'Message is required'}), 400

    # Determine recipients
    patient_ids = []
    if recipient_type == 'group':
        group_id = recipient_data.get('id')
        if group_id == 'all':
            patients = Patient.query.all()
            patient_ids = [p.id for p in patients]
        elif group_id == 'appointments':
            from app.appointments.models import Appointment
            today = datetime.now().date()
            patients = Patient.query.join(Appointment).filter(Appointment.date >= today).all()
            patient_ids = list(set(p.id for p in patients))  # distinct
        elif group_id == 'new_patients':
            thirty_days_ago = datetime.now() - timedelta(days=30)
            patients = Patient.query.filter(Patient.created_at >= thirty_days_ago).all()
            patient_ids = [p.id for p in patients]
        else:
            return jsonify({'error': 'Invalid group'}), 400
    else:  # individual
        patient_ids = recipient_data.get('ids', [])
        if not patient_ids:
            return jsonify({'error': 'No patients selected'}), 400

    # If scheduled for later, we could store the broadcast and process later.
    # For now, we'll send immediately and ignore schedule.
    # (You can extend with a Celery task later.)

    # Create broadcast record
    broadcast = SMSBroadcast(
        message=message,
        recipient_type=recipient_type,
        group_id=recipient_data.get('id') if recipient_type == 'group' else None,
        patient_ids=patient_ids if recipient_type == 'individual' else None,
        scheduled_time=datetime.strptime(f"{schedule['date']} {schedule['time']}", '%Y-%m-%d %H:%M') if schedule.get('date') and schedule.get('time') else None,
        status='processing',
        created_by=current_user.id
    )
    db.session.add(broadcast)
    db.session.flush()  # to get broadcast.id

    # For each patient, send SMS and log
    # For each patient, send SMS and log
    success_count = 0
    fail_count = 0
    for pid in patient_ids:
        patient = Patient.query.get(pid)
        if not patient or not patient.phone:
            continue

        raw_phone = patient.phone.strip()
        print(f"Patient {pid} raw phone: {raw_phone}")

        # Format to international: remove leading 0 or 1, then add +254
        if raw_phone.startswith('0') or raw_phone.startswith('1'):
            formatted_phone = '+254' + raw_phone[1:]
        else:
            formatted_phone = '+254' + raw_phone
        print(f"Formatted phone: {formatted_phone}")

        sms_result = notification_manager.send_sms(
            message=message,
            recipients=[formatted_phone]
        )

        # Log the attempt
        log = PatientSMSLog(
            broadcast_id=broadcast.id,
            patient_id=pid,
            phone_number=patient.phone,  # store original number
            message=message,
            status='sent' if sms_result else 'failed',
            provider_id=None
        )
        db.session.add(log)
        if sms_result:
            success_count += 1
        else:
            fail_count += 1
    broadcast.status = 'completed' if fail_count == 0 else 'partial'
    broadcast.sent_at = datetime.now()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Broadcast sent to {success_count} recipients, {fail_count} failed.'
    })
    
@comms_web_bp.route('/test-time')
def test_time():
    now = datetime.now(timezone.utc)
    broadcast = SMSBroadcast.query.get(19)  # Use your test ID
    scheduled = broadcast.scheduled_time.astimezone(timezone.utc)
    return jsonify({
        "now_utc": now.isoformat(),
        "scheduled_utc": scheduled.isoformat(),
        "now_timestamp": now.timestamp(),
        "scheduled_timestamp": scheduled.timestamp(),
        "time_diff": (scheduled - now).total_seconds()
    }) 
     
# Helper functions
def get_patients_by_group(group_id):
    if group_id == 'all':
        return Patient.query.all()
    elif group_id == 'appointments':
        return Patient.query.join(Appointment).filter(
            Appointment.status == 'scheduled',
            Appointment.scheduled_for > datetime.utcnow()
        ).distinct().all()
    elif group_id == 'new_patients':
        return Patient.query.filter(
            Patient.created_at > datetime.utcnow() - timedelta(days=30)
        ).all()
    return []

def get_patients_by_ids(patient_ids):
    return Patient.query.filter(Patient.id.in_(patient_ids)).all()
# ----------------------------
# Staff SMS Alerts Route
# ----------------------------
@comms_web_bp.route('/sms/staff', methods=['GET', 'POST'])
@login_required
def bulk_sms_staff():
    """Bulk SMS to staff"""
    if request.method == 'POST':
        message = request.form.get('message')
        department = request.form.get('department')
        priority = request.form.get('priority')
        
        if not message:
            flash('Message content is required', 'danger')
        else:
            flash(f'Alert sent to {department} staff!', 'success')

    
    return render_template('communications/sms_staff.html', 
                          title='Staff SMS Alerts')

# ---------------------------
# Email Campaigns Route
# ---------------------------
@comms_web_bp.route('/email/campaigns', methods=['GET', 'POST'])
@login_required
def email_campaigns():
    """Bulk email campaigns"""
    if request.method == 'POST':
        subject = request.form.get('subject')
        content = request.form.get('content')
        recipient_group = request.form.get('recipient_group')
        
        if not subject or not content:
            flash('Subject and content are required', 'danger')
        else:
            flash(f'Email campaign created for {recipient_group}!', 'success')

    
    return render_template('communications/email_campaigns.html', 
                          title='Email Campaigns')

# ---------------------------
# Message Templates Route
# ---------------------------
# ---------------------------
# Message Templates Route (Updated)
# ---------------------------
@comms_web_bp.route('/templates', methods=['GET', 'POST'])
@login_required
def message_templates():
    """Manage message templates and render dynamic stats cards."""
    form = TemplateForm()

    # Handle form submission for new templates
    if form.validate_on_submit():
        try:
            variables = [v.strip() for v in form.variables.data.split(',')] if form.variables.data else []

            new_template = MessageTemplate(
                name=form.name.data,
                content=form.content.data,
                template_type=form.template_type.data,
                category=form.category.data,
                created_by=current_user.id,
                variables=variables,
                icon=form.icon.data,
                priority=form.priority.data
            )
            db.session.add(new_template)
            db.session.commit()
            flash('Template created successfully!', 'success')
            return redirect(url_for('comms_web_bp.message_templates'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating template: {str(e)}', 'danger')

    # Fetch all templates with creator pre-loaded
    all_templates = MessageTemplate.query.options(
        db.joinedload(MessageTemplate.creator)
    ).order_by(MessageTemplate.name).all()

    # Categorize templates
    employee_templates = {'sms': [], 'email': []}
    patient_templates  = {'sms': [], 'email': []}
    for t in all_templates:
        data = {
            'id': t.id,
            'name': t.name,
            'content': t.content,
            'variables': t.variables or [],
            'icon': t.icon,
            'priority': t.priority,
            'created_at': t.created_at.strftime('%Y-%m-%d'),
            'created_by': t.creator.full_name if t.creator else 'System'
        }
        if t.category == 'employee':
            employee_templates[t.template_type].append(data)
        else:
            patient_templates[t.template_type].append(data)

    # Compute dynamic stats
    now = datetime.utcnow()
    one_week_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    total_templates = len(all_templates)
    new_since_week = sum(1 for t in all_templates if t.created_at >= one_week_ago)

    sms_list   = [t for t in all_templates if t.template_type == 'sms']
    email_list = [t for t in all_templates if t.template_type == 'email']

    sms_count   = len(sms_list)
    email_count = len(email_list)

    most_used_sms   = sms_list[0].name if sms_list else '—'
    most_used_email = email_list[0].name if email_list else '—'

    active_count   = sum(1 for t in all_templates if t.last_updated and t.last_updated >= thirty_days_ago)
    inactive_count = total_templates - active_count

    stats = {
        'total': total_templates,
        'new_since_week': new_since_week,
        'sms': {
            'count': sms_count,
            'most_used': most_used_sms
        },
        'email': {
            'count': email_count,
            'most_used': most_used_email
        },
        'active': {
            'count': active_count,
            'inactive': inactive_count
        }
    }

    # Common variables and icons (unchanged)
    common_variables = {
        'employee': ['name', 'email', 'position', 'department', 'shift_time', 'manager'],
        'patient': ['name', 'email', 'appointment_date', 'appointment_time', 'doctor', 'location', 'invoice_number', 'amount_due']
    }
    available_icons = [
        'fa-envelope', 'fa-comment', 'fa-calendar', 'fa-bell',
        'fa-user-md', 'fa-stethoscope', 'fa-heartbeat', 'fa-pills',
        'fa-file-invoice', 'fa-credit-card', 'fa-clock', 'fa-map-marker'
    ]

    return render_template(
        'communications/templates.html',
        title='Message Templates',
        form=form,
        employee_templates=employee_templates,
        patient_templates=patient_templates,
        common_variables=common_variables,
        available_icons=available_icons,
        stats=stats
    )

# -----------------------------
# Fetch a single template (for the Edit modal)
# -----------------------------
@comms_web_bp.route('/templates/<int:template_id>', methods=['GET'])
@login_required
def get_message_template(template_id):
    """Return a JSON payload of a single MessageTemplate."""
    template = MessageTemplate.query.get_or_404(template_id)

    # Optional permission check: only creator or admin may fetch for edit
    if template.created_by != current_user.id and not current_user.is_admin:
        abort(403)

    return jsonify(template.to_dict()), 200


# -----------------------------
# Update Message Template Route
# -----------------------------
@comms_web_bp.route('/templates/update', methods=['POST'])
@login_required
def update_message_template():
    """Handle the POST from your Edit Template modal form."""
    template_id = request.form.get('id', type=int)
    if not template_id:
        flash('No template ID provided.', 'danger')
        return redirect(url_for('comms_web_bp.message_templates'))

    template = MessageTemplate.query.get_or_404(template_id)

    # Permission check
    if template.created_by != current_user.id and not current_user.is_admin:
        flash('You do not have permission to edit this template.', 'danger')
        return redirect(url_for('comms_web_bp.message_templates'))

    # Pull values from form (names match your inputs)
    template.name          = request.form.get('name')
    template.category      = request.form.get('category')
    template.template_type = request.form.get('template_type')
    template.priority      = request.form.get('priority')
    template.icon          = request.form.get('icon')

    # Normalize variables: comma‑separated string → list
    vars_raw = request.form.get('variables', '')
    template.variables     = [v.strip() for v in vars_raw.split(',')] if vars_raw else []

    # Both your SMS and Email textareas use name="content"
    template.content = request.form.get('content')

    # Persist changes
    try:
        db.session.commit()
        flash(f'Template “{template.name}” updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Failed to update template {template_id}: {e}')
        flash('An error occurred while updating the template.', 'danger')

    return redirect(url_for('comms_web_bp.message_templates'))



@comms_web_bp.route('/templates/delete', methods=['POST'])
@login_required
def delete_message_template():
    """Delete a message template by ID."""
    template_id = request.form.get('id', type=int)
    if not template_id:
        flash('No template ID provided.', 'danger')
        return redirect(url_for('comms_web_bp.message_templates'))

    # Fetch the template
    template = MessageTemplate.query.get(template_id)
    if template is None:
        flash(f'Template with ID {template_id} not found.', 'warning')
        return redirect(url_for('comms_web_bp.message_templates'))

    # (Optional) Check permissions: only creator or admin can delete
    if template.created_by != current_user.id and not current_user.is_admin:
        flash('You do not have permission to delete this template.', 'danger')
        return redirect(url_for('comms_web_bp.message_templates'))

    try:
        db.session.delete(template)
        db.session.commit()
        flash(f'Template "{template.name}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting template {template_id}: {e}')
        flash('An error occurred while trying to delete the template.', 'danger')

    return redirect(url_for('comms_web_bp.message_templates'))

# -------------------------------
# Appointment Reminders Route
# -------------------------------
@comms_web_bp.route('/reminders', methods=['GET', 'POST'])
@login_required
def auto_reminders():
    """Automated appointment reminders"""
    if request.method == 'POST':
        # Process reminder settings
        lead_time = request.form.get('lead_time')
        method = request.form.get('method')
        template_id = request.form.get('template')
        
        # Save settings to database or config
        flash('Reminder settings updated successfully!', 'success')
        return redirect(url_for('comms_web_bp.auto_reminders'))
    
    return render_template('communications/reminders.html', 
                          title='Appointment Reminders')

# --------------------------------
# System Notifications Route
# --------------------------------
@comms_web_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
def system_notifications():
    """System notification settings"""
    if request.method == 'POST':
        # Process notification settings
        event = request.form.get('event')
        channel = request.form.get('channel')
        recipients = request.form.get('recipients')
        
        # Save settings to database or config
        flash('Notification settings updated!', 'success')
    
    return render_template('communications/notifications.html', 
                          title='System Notifications')

# -----------------------------
# Delivery Analytics Route
# -----------------------------
@comms_web_bp.route('/analytics', methods=['GET'])
@login_required
def comms_analytics():
    """Communication analytics dashboard"""
    # Enhanced analytics data
    stats = {
        'sms': {'sent': 1250, 'delivered': 1150, 'failed': 100},
        'email': {'sent': 842, 'opened': 658, 'clicked': 320},
        'reminders': {'sent': 420, 'confirmed': 315}
    }
    
    # Delivery rate trends with more data
    trends = [
        {'month': 'Jan', 'sms': 88, 'email': 60},
        {'month': 'Feb', 'sms': 89, 'email': 62},
        {'month': 'Mar', 'sms': 90, 'email': 61},
        {'month': 'Apr', 'sms': 91, 'email': 63},
        {'month': 'May', 'sms': 92, 'email': 64},
        {'month': 'Jun', 'sms': 93, 'email': 65},
        {'month': 'Jul', 'sms': 94, 'email': 66}
    ]
    
    return render_template('communications/analytics.html', 
                          stats=stats,
                          trends=trends,
                          title='Delivery Analytics')
# -----------------------------
# Feedback Collection Route
# -----------------------------
@comms_web_bp.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback_system():
    """Patient feedback system"""
    
    if request.method == 'POST':
        # Process feedback settings
        survey_status = request.form.get('status') == 'active'
        trigger_event = request.form.get('trigger_event')
        
        # Save settings to database or config
        flash('Feedback system settings updated!', 'success')
    
    return render_template('communications/feedback.html', 
                          title='Feedback Collection')

# -----------------------------
# Template Preview Endpoint
# -----------------------------
@comms_web_bp.route('/template/preview', methods=['POST'])
@login_required
def preview_template():
    """Preview message template"""
    content = request.form.get('content')
    # In a real app, you would render the template with sample data
    return jsonify({'preview': f"<div class='p-4 bg-white border rounded-lg'>{content}</div>"})

# -----------------------------
# Send Test Message Endpoint
# -----------------------------
@comms_web_bp.route('/send/test', methods=['POST'])
@login_required
def send_test_message():
    """Send a test message"""
    message_type = request.form.get('type')
    recipient = request.form.get('recipient')
    content = request.form.get('content')
    
    # Validate inputs
    if not recipient or not content:
        return jsonify({'success': False, 'message': 'Recipient and content required'})
    
    # In a real app, this would actually send a message
    return jsonify({
        'success': True,
        'message': f"Test {message_type} sent to {recipient}"
    })