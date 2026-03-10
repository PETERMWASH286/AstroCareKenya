# app/notifications/communications.py

import json
import threading

from flask import Blueprint, abort, current_app, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db
from datetime import date, datetime, timedelta, timezone

from app.appointments.models import Appointment
from app.auth.models import Role, User
from app.notifications.models import EmailBroadcast, EmailLog, MessageTemplate, Notification, NotificationRead, PatientFeedback, PatientSMSLog, SMSBroadcast, StaffSMSLog

# Import TemplateForm (adjust the import path if your form is defined elsewhere)
from app.notifications.forms import TemplateForm
from app.notifications.tasks import queue_sms_broadcast, send_sms_broadcast
from app.patients.models import Patient
from app.user_management.models import Department, EmployeeBio
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
    """Dynamic engagement dashboard with real data"""

    # --- Period selection (default last 30 days) ---
    period = request.args.get('period', '30')
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=int(period))

    # --- Helper to get counts for a period with optional filters ---
    def count_in_period(model, date_field, **filters):
        query = model.query.filter(date_field >= start_date, date_field <= end_date)
        for attr, value in filters.items():
            query = query.filter(getattr(model, attr) == value)
        return query.count()

    # --- 1. Total Messages ---
    sms_sent = count_in_period(PatientSMSLog, PatientSMSLog.sent_at) + \
               count_in_period(StaffSMSLog, StaffSMSLog.sent_at)
    email_sent = count_in_period(EmailLog, EmailLog.sent_at)
    total_messages = sms_sent + email_sent

    # --- 2. Delivery & Open Rates ---
    sms_delivered = count_in_period(PatientSMSLog, PatientSMSLog.sent_at, status='delivered') + \
                    count_in_period(StaffSMSLog, StaffSMSLog.sent_at, status='delivered')
    sms_rate = round((sms_delivered / sms_sent * 100) if sms_sent else 0, 1)

    # For emails, count opened emails via opened_at being not null
    email_opened = EmailLog.query.filter(
        EmailLog.sent_at >= start_date,
        EmailLog.sent_at <= end_date,
        EmailLog.opened_at.isnot(None)
    ).count()
    email_open_rate = round((email_opened / email_sent * 100) if email_sent else 0, 1)

    # Combined delivery rate (weighted)
    total_delivered = sms_delivered + email_sent  # email_sent is already considered "sent"
    delivery_rate = round((total_delivered / total_messages * 100) if total_messages else 0, 1)

    # --- 3. Feedback ---
    feedback_count = count_in_period(PatientFeedback, PatientFeedback.submitted_at)

    # --- 4. Recent Activity (combined logs) ---
    recent = []

    # SMS logs
    for log in PatientSMSLog.query.order_by(PatientSMSLog.sent_at.desc()).limit(10).all():
        recent.append({
            'type': 'SMS',
            'target': log.patient.full_name if log.patient else 'Patient',
            'count': 1,
            'date': log.sent_at.strftime('%Y-%m-%d'),
            'status': log.status.capitalize()
        })
    for log in StaffSMSLog.query.order_by(StaffSMSLog.sent_at.desc()).limit(10).all():
        recent.append({
            'type': 'SMS',
            'target': log.staff.full_name if log.staff else 'Staff',
            'count': 1,
            'date': log.sent_at.strftime('%Y-%m-%d'),
            'status': log.status.capitalize()
        })

    # Email logs
    for log in EmailLog.query.order_by(EmailLog.sent_at.desc()).limit(10).all():
        recent.append({
            'type': 'Email',
            'target': log.email,
            'count': 1,
            'date': log.sent_at.strftime('%Y-%m-%d'),
            'status': 'Opened' if log.opened_at else log.status.capitalize()
        })

    # Feedback
    for fb in PatientFeedback.query.order_by(PatientFeedback.submitted_at.desc()).limit(10).all():
        recent.append({
            'type': 'Feedback',
            'target': fb.patient.full_name if fb.patient else 'Anonymous',
            'count': 1,
            'date': fb.submitted_at.strftime('%Y-%m-%d'),
            'status': fb.sentiment.capitalize() if fb.sentiment else 'Received'
        })

    # Sort by date descending and take latest 10
    recent.sort(key=lambda x: x['date'], reverse=True)
    recent = recent[:10]

    # --- 5. Active Campaigns (SMS & Email) ---
    campaigns = []
    # SMS campaigns
    for bc in SMSBroadcast.query.filter(SMSBroadcast.status.in_(['scheduled', 'processing'])).limit(4).all():
        campaigns.append({
            'name': bc.message[:30] + '...',
            'type': 'SMS',
            'status': bc.status.capitalize(),
            'progress': 50 if bc.status == 'processing' else 0,  # dummy – you can compute based on logs
            'sent': 0,
            'total': len(bc.patient_ids) if bc.patient_ids else 0,
            'color': 'green' if bc.status == 'processing' else 'blue'
        })
    # Email campaigns
    for ec in EmailBroadcast.query.filter(EmailBroadcast.status.in_(['scheduled', 'processing'])).limit(4).all():
        campaigns.append({
            'name': ec.subject[:30] + '...',
            'type': 'Email',
            'status': ec.status.capitalize(),
            'progress': 50 if ec.status == 'processing' else 0,
            'sent': 0,
            'total': len(ec.recipient_ids) if ec.recipient_ids else 0,
            'color': 'indigo' if ec.status == 'processing' else 'amber'
        })

    # --- 6. Weekly trend data for chart (last 7 days) ---
    days = []
    sms_trend = []
    email_trend = []
    for i in range(6, -1, -1):
        day = (end_date - timedelta(days=i)).date()
        days.append(day.strftime('%a'))
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())
        sms_trend.append(
            PatientSMSLog.query.filter(PatientSMSLog.sent_at.between(day_start, day_end)).count() +
            StaffSMSLog.query.filter(StaffSMSLog.sent_at.between(day_start, day_end)).count()
        )
        email_trend.append(
            EmailLog.query.filter(EmailLog.sent_at.between(day_start, day_end)).count()
        )

    metrics = {
        'sms_sent': sms_sent,
        'email_sent': email_sent,
        'delivery_rate': delivery_rate,
        'open_rate': email_open_rate,
        'feedback_responses': feedback_count,
        'total_messages': total_messages
    }

    return render_template(
        'communications/dashboard.html',
        metrics=metrics,
        recent_activity=recent,
        campaigns=campaigns,
        days=days,
        sms_trend=sms_trend,
        email_trend=email_trend,
        period=period,
        title='Engagement Dashboard'
    )

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

from datetime import datetime, timezone
import json
import logging
import re

logger = logging.getLogger(__name__)

def format_phone(raw_phone):
    """
    Convert phone number to international format (+254...)
    Handles: 0712345678, 0112345678, 254712345678, +254712345678, 712345678, etc.
    """
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', raw_phone)
    
    # Kenyan numbers: if starts with 0 or 1, replace leading digit with 254
    if digits.startswith('0') or digits.startswith('1'):
        digits = '254' + digits[1:]
    elif digits.startswith('254'):
        # Already correct, but ensure length is 12 (254 + 9 digits)
        if len(digits) != 12:
            # If it's longer, maybe it has country code already, but we'll just keep as is
            pass
    else:
        # Assume it's a local number without leading zero, e.g., 712345678
        digits = '254' + digits
    
    # Ensure it's exactly 12 digits (254 + 9 digits)
    if len(digits) > 12:
        digits = digits[:12]  # trim if too long
    elif len(digits) < 12:
        # Pad? Unlikely, but just log warning
        logger.warning(f"Phone number {raw_phone} resulted in {digits} which is too short")
    
    return '+' + digits

@comms_web_bp.route('/sms/staff', methods=['GET', 'POST'])
@login_required
def bulk_sms_staff():
    """Bulk SMS to staff with dynamic recipient selection and templates"""
    
    if request.method == 'POST':
        # Gather form data
        message = request.form.get('message', '').strip()
        schedule_date = request.form.get('schedule_date')
        schedule_time = request.form.get('schedule_time')
        send_to_all = request.form.get('send_to_all') == 'true'

        # Get recipient selections (JSON strings)
        selected_roles = json.loads(request.form.get('selected_roles', '[]'))
        selected_departments = json.loads(request.form.get('selected_departments', '[]'))
        selected_users = json.loads(request.form.get('selected_users', '[]'))

        # --- DEBUG: Print received data ---
        print("=== FORM DATA RECEIVED ===")
        print(f"Message: {message}")
        print(f"Schedule Date: {schedule_date}")
        print(f"Schedule Time: {schedule_time}")
        print(f"Send to All: {send_to_all}")
        print(f"Selected Roles: {selected_roles}")
        print(f"Selected Departments: {selected_departments}")
        print(f"Selected Users: {selected_users}")
        print("===========================")
        
        # Validate message
        if not message:
            flash('Message content is required', 'danger')
            return redirect(url_for('comms_web_bp.bulk_sms_staff'))
        
        # --- Resolve recipient user IDs ---
        user_ids = set()
        
        if send_to_all:
            # All active staff
            all_users = User.query.filter_by(is_active=True).all()
            user_ids = {u.id for u in all_users}
        else:
            # From roles
            if selected_roles:
                role_users = User.query.filter(
                    User.roles.any(Role.id.in_(selected_roles))
                ).filter_by(is_active=True).all()
                user_ids.update(u.id for u in role_users)
            
            # From departments
            if selected_departments:
                dept_users = User.query.filter(
                    User.department_id.in_(selected_departments)
                ).filter_by(is_active=True).all()
                user_ids.update(u.id for u in dept_users)
            
            # From individuals
            if selected_users:
                user_ids.update(selected_users)
        
        if not user_ids:
            flash('No recipients selected or found.', 'danger')
            return redirect(url_for('comms_web_bp.bulk_sms_staff'))
        
        # --- Retrieve phone numbers from EmployeeBio ---
        bios = EmployeeBio.query.filter(
            EmployeeBio.user_id.in_(user_ids),
            EmployeeBio.phone.isnot(None),
            EmployeeBio.phone != ''
        ).all()
        
        
        

        if not bios:
            flash('No staff members with valid phone numbers found.', 'danger')
            return redirect(url_for('comms_web_bp.bulk_sms_staff'))
        
        # --- Format phone numbers and build mapping: formatted phone -> list of bios ---
        phone_to_bios = {}
        for bio in bios:
            formatted = format_phone(bio.phone)
            phone_to_bios.setdefault(formatted, []).append(bio)
        
        # Unique formatted recipient phones
        recipient_phones = list(phone_to_bios.keys())
        print(f"Staff with phone numbers: {len(bios)}")
        print(f"Unique phone numbers: {len(recipient_phones)}")
        for bio in bios:
            print(f"User {bio.user_id}: {bio.phone} -> {format_phone(bio.phone)}")
        # --- Determine scheduled time (if any) ---
        scheduled_datetime = None
        if schedule_date and schedule_time:
            try:
                scheduled_datetime = datetime.strptime(
                    f"{schedule_date} {schedule_time}", "%Y-%m-%d %H:%M"
                )
                # Make timezone-aware (assume UTC)
                scheduled_datetime = scheduled_datetime.replace(tzinfo=timezone.utc)
            except ValueError:
                flash('Invalid schedule date/time format.', 'warning')
        
        # --- Create SMSBroadcast record ---
        broadcast = SMSBroadcast(
            message=message,
            recipient_type='staff_bulk',
            scheduled_time=scheduled_datetime,
            status='scheduled' if scheduled_datetime else 'processing',
            created_by=current_user.id
        )
        db.session.add(broadcast)
        db.session.flush()  # Get broadcast.id
        
        # --- Send SMS (if not scheduled) or queue for later ---
        sms_success = False
        if scheduled_datetime and scheduled_datetime > datetime.now(timezone.utc):
            broadcast.status = 'scheduled'
            flash(f'SMS scheduled for {scheduled_datetime.strftime("%Y-%m-%d %H:%M")}.', 'success')
            db.session.commit()
            return redirect(url_for('comms_web_bp.bulk_sms_staff'))
        else:
            # Send immediately
            try:
                # Use notification_manager to send bulk SMS
                response = notification_manager.send_sms(
                    message=message,
                    recipients=recipient_phones
                )
                
                if response:
                    # Process response to log individual statuses
                    # Africa's Talking returns a list of recipients with statuses
                    if isinstance(response, dict) and response.get('SMSMessageData'):
                        recipients_data = response['SMSMessageData'].get('Recipients', [])
                        
                        # For each recipient in the response, match by formatted phone
                        for item in recipients_data:
                            phone = item.get('number')

                            status = 'delivered' if item.get('status') == 'Success' else 'failed'
                            provider_id = item.get('messageId')

                            raw_cost = item.get('cost')
                            cost = None
                            if raw_cost:
                                try:
                                    cost = float(raw_cost.replace('KES', '').strip())
                                except ValueError:
                                    cost = None

                            matching_bios = phone_to_bios.get(phone, [])

                            for bio in matching_bios:
                                log = StaffSMSLog(
                                    broadcast_id=broadcast.id,
                                    staff_id=bio.user_id,
                                    phone_number=phone,
                                    message=message,
                                    status=status,
                                    status_message=item.get('status'),
                                    cost=cost,
                                    provider_id=provider_id,
                                    sent_at=datetime.utcnow(),
                                    delivered_at=datetime.utcnow(),
                                )
                                db.session.add(log)
                        
                        broadcast.status = 'completed'
                        sms_success = True
                    else:
                        # Unexpected response format: log all as unknown
                        for phone, bios_list in phone_to_bios.items():
                            for bio in bios_list:
                                log = StaffSMSLog(
                                    broadcast_id=broadcast.id,
                                    staff_id=bio.user_id,
                                    phone_number=phone,
                                    message=message,
                                    status='unknown',
                                    status_message='No detailed response',
                                    sent_at=datetime.utcnow()
                                )
                                db.session.add(log)
                        broadcast.status = 'completed'
                        sms_success = True
                else:
                    # SMS sending failed entirely
                    for phone, bios_list in phone_to_bios.items():
                        for bio in bios_list:
                            log = StaffSMSLog(
                                broadcast_id=broadcast.id,
                                staff_id=bio.user_id,
                                phone_number=phone,
                                message=message,
                                status='failed',
                                status_message='Provider error',
                                sent_at=datetime.utcnow()
                            )
                            db.session.add(log)
                    broadcast.status = 'failed'
                    flash('SMS sending failed. Please check logs.', 'danger')
            except Exception as e:
                logger.exception("Error sending SMS")
                db.session.rollback()
                flash(f'Error sending SMS: {str(e)}', 'danger')
                return redirect(url_for('comms_web_bp.bulk_sms_staff'))
        
        db.session.commit()
        
        if sms_success:
            flash(f'SMS successfully sent to {len(bios)} staff members.', 'success')        
        return redirect(url_for('comms_web_bp.bulk_sms_staff'))
    
    # --- GET request: populate dynamic data (unchanged) ---
    roles = Role.query.order_by(Role.name).all()
    role_data = [{'id': r.id, 'name': r.name, 'count': User.query.filter(User.roles.any(id=r.id)).count()} for r in roles]
    
    departments = Department.query.order_by(Department.name).all()
    dept_data = [{'id': d.id, 'name': d.name, 'count': User.query.filter_by(department_id=d.id).count()} for d in departments]
    
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    individuals = []
    for user in users:
        role_names = ', '.join([r.name for r in user.roles]) if user.roles else 'No Role'
        individuals.append({
            'id': user.id,
            'name': user.full_name or user.username,
            'role': role_names,
            'department': user.department.name if user.department else 'N/A'
        })
    
    templates = MessageTemplate.query.filter_by(template_type='sms', category='employee').order_by(MessageTemplate.name).all()
    template_list = [t.to_dict() for t in templates]
    
    return render_template(
        'communications/sms_staff.html',
        title='Staff SMS Alerts',
        roles=role_data,
        departments=dept_data,
        individuals=individuals,
        templates=template_list
    )
# ---------------------------
# Email Campaigns Route
# ---------------------------
import os

from werkzeug.utils import secure_filename

# Allowed attachment extensions
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'xlsx', 'ppt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_email_campaign(broadcast_id, recipients, subject, content, attachments):
    """
    Background thread function to send emails for a campaign.
    """
    # Create a new database session for this thread
    from app import create_app
    app = create_app()
    with app.app_context():
        try:
            broadcast = EmailBroadcast.query.get(broadcast_id)
            if not broadcast:
                logger.error(f"Broadcast {broadcast_id} not found in thread")
                return

            success_count = 0
            fail_count = 0
            for rec in recipients:
                try:
                    result = notification_manager.send_email(
                        subject=subject,
                        recipients=[rec['email']],
                        body=content,
                        html_body=content,
                        attachments=attachments
                    )
                    if result:
                        status = 'sent'
                        success_count += 1
                    else:
                        status = 'failed'
                        fail_count += 1
                except Exception as e:
                    logger.exception(f"Error sending to {rec['email']}")
                    status = 'failed'
                    fail_count += 1

                log = EmailLog(
                    broadcast_id=broadcast_id,
                    recipient_type=rec['type'],
                    recipient_id=rec['id'],
                    email=rec['email'],
                    subject=subject,
                    status=status,
                    status_message=str(e) if status == 'failed' else None,
                    sent_at=datetime.utcnow()
                )
                db.session.add(log)

            broadcast.status = 'sent' if fail_count == 0 else 'partially_sent' if success_count > 0 else 'failed'
            broadcast.sent_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Campaign {broadcast_id} completed: {success_count} sent, {fail_count} failed")
        except Exception as e:
            logger.exception("Error in background email thread")
            db.session.rollback()

@comms_web_bp.route('/email/campaigns', methods=['GET', 'POST'])
@login_required
def email_campaigns():
    """Bulk email campaigns to patients and staff"""
    if request.method == 'POST':
        # --- 1. Collect form data ---
        subject = request.form.get('subject', '').strip()
        content = request.form.get('content', '').strip()
        recipient_selection = request.form.get('recipient_selection')
        schedule_option = request.form.get('schedule')
        schedule_date = request.form.get('schedule_date')
        schedule_time = request.form.get('schedule_time')

        # Get selected IDs (JSON strings)
        selected_role_ids = json.loads(request.form.get('selected_roles', '[]'))
        selected_dept_ids = json.loads(request.form.get('selected_departments', '[]'))
        selected_user_ids = json.loads(request.form.get('selected_users', '[]'))

        # --- DEBUG: Print received form data ---
        print("\n=== EMAIL CAMPAIGN POST DATA ===")
        print(f"subject: {subject}")
        print(f"recipient_selection: {recipient_selection}")
        print(f"schedule_option: {schedule_option}")
        print(f"selected_role_ids: {selected_role_ids}")
        print(f"selected_dept_ids: {selected_dept_ids}")
        print(f"selected_user_ids: {selected_user_ids}")
        print("================================\n")

        # --- 2. Validate ---
        if not subject or not content:
            flash('Subject and content are required.', 'danger')
            return redirect(url_for('comms_web_bp.email_campaigns'))

        # --- 3. Handle file attachments ---
        uploaded_files = request.files.getlist('attachments')
        saved_attachments = []
        if uploaded_files and uploaded_files[0].filename:
            upload_folder = os.path.join('app', 'static', 'uploads', 'email_attachments')
            os.makedirs(upload_folder, exist_ok=True)
            for file in uploaded_files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_folder, filename)
                    file.save(filepath)
                    saved_attachments.append(filepath)

        # --- 4. Resolve recipients (list of dicts) ---
        recipients = []  # each dict: {'email': str, 'type': 'patient'/'staff', 'id': int}

        if recipient_selection == 'all_patients':
            patients = Patient.query.all()
            recipients = [{'email': p.email, 'type': 'patient', 'id': p.id} for p in patients if p.email]
            print(f"All patients found: {len(patients)}, with email: {len(recipients)}")

        elif recipient_selection == 'staff':
            staff = User.query.filter_by(is_active=True).all()
            print(f"All active staff count: {len(staff)}")
            for u in staff:
                print(f"Staff ID {u.id}: email='{u.email}'")
            recipients = [{'email': u.email, 'type': 'staff', 'id': u.id} for u in staff if u.email]
            print(f"Staff with email: {len(recipients)}")

        elif recipient_selection == 'roles' and selected_role_ids:
            staff = User.query.filter(User.roles.any(Role.id.in_(selected_role_ids))).filter_by(is_active=True).all()
            print(f"Staff in roles {selected_role_ids}: {len(staff)}")
            recipients = [{'email': u.email, 'type': 'staff', 'id': u.id} for u in staff if u.email]

        elif recipient_selection == 'departments' and selected_dept_ids:
            staff = User.query.filter(User.department_id.in_(selected_dept_ids)).filter_by(is_active=True).all()
            print(f"Staff in departments {selected_dept_ids}: {len(staff)}")
            recipients = [{'email': u.email, 'type': 'staff', 'id': u.id} for u in staff if u.email]

        elif recipient_selection == 'individuals' and selected_user_ids:
            staff = User.query.filter(User.id.in_(selected_user_ids)).filter_by(is_active=True).all()
            print(f"Individual staff {selected_user_ids}: {len(staff)}")
            recipients = [{'email': u.email, 'type': 'staff', 'id': u.id} for u in staff if u.email]

        print(f"Final recipients count: {len(recipients)}")
        if not recipients:
            flash('No recipients with valid email addresses found.', 'warning')
            return redirect(url_for('comms_web_bp.email_campaigns'))


        # --- 5. Determine scheduled time ---
        scheduled_datetime = None
        if schedule_option == 'later' and schedule_date and schedule_time:
            try:
                scheduled_datetime = datetime.strptime(
                    f"{schedule_date} {schedule_time}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                flash('Invalid schedule date/time.', 'warning')

        # --- 6. Create EmailBroadcast record ---
        broadcast = EmailBroadcast(
            subject=subject,
            content=content,
            plain_text=None,
            recipient_type=recipient_selection,
            recipient_ids=[r['id'] for r in recipients],
            scheduled_time=scheduled_datetime,
            status='scheduled' if scheduled_datetime else 'processing',
            created_by=current_user.id,
            attachments=saved_attachments if saved_attachments else None
        )
        db.session.add(broadcast)
        db.session.flush()  # get broadcast.id

        # --- 7. Handle sending ---
        if scheduled_datetime and scheduled_datetime > datetime.now(timezone.utc):
            broadcast.status = 'scheduled'
            db.session.commit()
            flash(f'Campaign scheduled for {scheduled_datetime.strftime("%Y-%m-%d %H:%M")}.', 'success')
        else:
            # Send immediately in background thread
            broadcast.status = 'processing'
            db.session.commit()

            # Start background thread
            thread = threading.Thread(
                target=send_email_campaign,
                args=(broadcast.id, recipients, subject, content, saved_attachments)
            )
            thread.daemon = True
            thread.start()

            flash('Campaign is being sent in the background. You will be notified when complete.', 'info')

        return redirect(url_for('comms_web_bp.email_campaigns'))

    # --- GET request: populate dynamic data (unchanged) ---
    total_patients = Patient.query.count()
    total_staff = User.query.filter_by(is_active=True).count()

    roles = Role.query.order_by(Role.name).all()
    role_data = [{'id': r.id, 'name': r.name, 'count': User.query.filter(User.roles.any(id=r.id)).count()} for r in roles]

    departments = Department.query.order_by(Department.name).all()
    dept_data = [{'id': d.id, 'name': d.name, 'count': User.query.filter_by(department_id=d.id).count()} for d in departments]

    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    individuals = []
    for user in users:
        role_names = ', '.join([r.name for r in user.roles]) if user.roles else 'No Role'
        individuals.append({
            'id': user.id,
            'name': user.full_name or user.username,
            'role': role_names,
            'department': user.department.name if user.department else 'N/A',
            'email': user.email
        })

    patient_templates = MessageTemplate.query.filter_by(template_type='email', category='patient').order_by(MessageTemplate.name).all()
    staff_templates = MessageTemplate.query.filter_by(template_type='email', category='employee').order_by(MessageTemplate.name).all()

    recent_campaigns = EmailBroadcast.query.order_by(EmailBroadcast.created_at.desc()).limit(10).all()

    return render_template(
        'communications/email_campaigns.html',
        title='Email Campaigns',
        total_patients=total_patients,
        total_staff=total_staff,
        roles=role_data,
        departments=dept_data,
        individuals=individuals,
        patient_templates=[t.to_dict() for t in patient_templates],
        staff_templates=[t.to_dict() for t in staff_templates],
        recent_campaigns=recent_campaigns
    )
    
    
@comms_web_bp.route('/email/campaigns/<int:campaign_id>/report')
@login_required
def email_campaign_report(campaign_id):
    """Display detailed report for a specific email campaign."""
    campaign = EmailBroadcast.query.get_or_404(campaign_id)
    logs = EmailLog.query.filter_by(broadcast_id=campaign_id).order_by(EmailLog.sent_at).all()

    # Calculate stats
    total = len(logs)
    sent = sum(1 for log in logs if log.status == 'sent')
    failed = sum(1 for log in logs if log.status == 'failed')
    delivered = sum(1 for log in logs if log.status == 'delivered')  # if you use it
    opened = sum(1 for log in logs if log.opened_at)  # if you track opens
    clicked = sum(1 for log in logs if log.clicked_at)

    return render_template(
        'communications/email_campaign_report.html',
        campaign=campaign,
        logs=logs,
        total=total,
        sent=sent,
        failed=failed,
        delivered=delivered,
        opened=opened,
        clicked=clicked
    )
    
    
    
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
from sqlalchemy import func
from datetime import datetime, timedelta

@comms_web_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
def system_notifications():
    """System notification management – send and view notifications"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        recipient_type = request.form.get('recipient_type')  # 'all', 'department', 'individuals'
        department_ids = request.form.getlist('department_ids')  # list of dept IDs
        user_ids = request.form.getlist('user_ids')  # list of user IDs

        if not title or not message:
            flash('Title and message are required.', 'danger')
            return redirect(url_for('comms_web_bp.system_notifications'))

        # Create notification record(s) based on recipient type
        notifications_created = 0

        if recipient_type == 'all':
            # Broadcast to all active users
            users = User.query.filter_by(is_active=True).all()
            for user in users:
                notif = Notification(
                    title=title,
                    message=message,
                    sender_id=current_user.id,
                    user_id=user.id,
                    is_broadcast=False  # individual
                )
                db.session.add(notif)
                notifications_created += 1
            db.session.commit()

        elif recipient_type == 'department' and department_ids:
            dept_ids = [int(did) for did in department_ids if did.isdigit()]
            users = User.query.filter(User.department_id.in_(dept_ids), User.is_active==True).all()
            for user in users:
                notif = Notification(
                    title=title,
                    message=message,
                    sender_id=current_user.id,
                    user_id=user.id,
                    department_id=user.department_id  # optional, store which department triggered
                )
                db.session.add(notif)
                notifications_created += 1
            db.session.commit()

        elif recipient_type == 'individuals' and user_ids:
            uid_list = [int(uid) for uid in user_ids if uid.isdigit()]
            users = User.query.filter(User.id.in_(uid_list), User.is_active==True).all()
            for user in users:
                notif = Notification(
                    title=title,
                    message=message,
                    sender_id=current_user.id,
                    user_id=user.id
                )
                db.session.add(notif)
                notifications_created += 1
            db.session.commit()

        if notifications_created > 0:
            flash(f'Notification sent to {notifications_created} employees.', 'success')
        else:
            flash('No recipients found.', 'warning')

        return redirect(url_for('comms_web_bp.system_notifications'))

    # GET request: populate dynamic data
    departments = Department.query.order_by(Department.name).all()
    # All active users for specific selection (we'll limit for performance, maybe paginate later)
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    # Recent notifications (last 10 sent)
    recent_notifications = Notification.query.order_by(Notification.created_at.desc()).limit(10).all()

    # Statistics
    total_sent = Notification.query.count()
    last_30_days = datetime.utcnow() - timedelta(days=30)
    sent_30_days = Notification.query.filter(Notification.created_at >= last_30_days).count()
    # Read rate: notifications with at least one read
    read_count = NotificationRead.query.filter(NotificationRead.notification_id.in_(
        db.session.query(Notification.id)
    )).count()
    total_individual_notifications = Notification.query.filter(Notification.user_id.isnot(None)).count()
    read_rate = (read_count / total_individual_notifications * 100) if total_individual_notifications else 0

    # Distribution by recipient type (approximate, based on department presence)
    dept_notifications = Notification.query.filter(Notification.department_id.isnot(None)).count()
    individual_notifications = Notification.query.filter(Notification.user_id.isnot(None), Notification.department_id.is_(None)).count()
    broadcast_notifications = Notification.query.filter(Notification.is_broadcast==True).count()
    # Since we are creating individual records per user, we'll compute differently:
    # For this demo, we'll just show counts from our recent query.

    return render_template(
        'communications/notifications.html',
        title='System Notifications',
        departments=departments,
        users=users,
        recent_notifications=recent_notifications,
        total_sent=total_sent,
        sent_30_days=sent_30_days,
        read_rate=round(read_rate, 1),
        dept_notifications=dept_notifications,
        individual_notifications=individual_notifications,
        broadcast_notifications=broadcast_notifications
    )

# -----------------------------
# Delivery Analytics Route
# -----------------------------
from sqlalchemy import func, extract, and_
from datetime import datetime, timedelta, date
import calendar

@comms_web_bp.route('/analytics', methods=['GET'])
@login_required
def comms_analytics():
    """Communication analytics dashboard with real data"""
    # Get date range from request (default last 30 days)
    period = request.args.get('period', '30')
    if period == '7':
        days = 7
    elif period == '90':
        days = 90
    elif period == 'ytd':
        # Year to date: from Jan 1 to today
        start_date = date(datetime.utcnow().year, 1, 1)
        end_date = datetime.utcnow().date()
        days = (end_date - start_date).days
    else:
        days = 30

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # --- Helper to get counts grouped by month for trends ---
    def month_range(start, end):
        months = []
        current = start.replace(day=1)
        while current <= end:
            months.append(current.strftime('%Y-%m'))
            # next month
            if current.month == 12:
                current = current.replace(year=current.year+1, month=1)
            else:
                current = current.replace(month=current.month+1)
        return months

    months = month_range(start_date, end_date)
    month_labels = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months]

    # --- SMS Stats ---
    sms_sent = PatientSMSLog.query.filter(PatientSMSLog.sent_at.between(start_date, end_date)).count() + \
               StaffSMSLog.query.filter(StaffSMSLog.sent_at.between(start_date, end_date)).count()
    sms_delivered = PatientSMSLog.query.filter(PatientSMSLog.status == 'delivered',
                                               PatientSMSLog.sent_at.between(start_date, end_date)).count() + \
                    StaffSMSLog.query.filter(StaffSMSLog.status == 'delivered',
                                             StaffSMSLog.sent_at.between(start_date, end_date)).count()
    sms_failed = PatientSMSLog.query.filter(PatientSMSLog.status == 'failed',
                                             PatientSMSLog.sent_at.between(start_date, end_date)).count() + \
                 StaffSMSLog.query.filter(StaffSMSLog.status == 'failed',
                                          StaffSMSLog.sent_at.between(start_date, end_date)).count()

    # SMS trends per month
    sms_trend = []
    for m in months:
        ym = datetime.strptime(m, '%Y-%m')
        next_month = ym.replace(day=28) + timedelta(days=4)  # safe way to get next month
        start = ym
        end = next_month.replace(day=1) - timedelta(days=1)
        sent = PatientSMSLog.query.filter(PatientSMSLog.sent_at.between(start, end)).count() + \
               StaffSMSLog.query.filter(StaffSMSLog.sent_at.between(start, end)).count()
        delivered = PatientSMSLog.query.filter(PatientSMSLog.status == 'delivered',
                                               PatientSMSLog.sent_at.between(start, end)).count() + \
                    StaffSMSLog.query.filter(StaffSMSLog.status == 'delivered',
                                             StaffSMSLog.sent_at.between(start, end)).count()
        rate = (delivered / sent * 100) if sent > 0 else 0
        sms_trend.append(round(rate, 1))

    # --- Email Stats ---
    email_sent = EmailLog.query.filter(EmailLog.sent_at.between(start_date, end_date)).count()
    email_opened = EmailLog.query.filter(EmailLog.opened_at.isnot(None),
                                         EmailLog.sent_at.between(start_date, end_date)).count()
    email_clicked = EmailLog.query.filter(EmailLog.clicked_at.isnot(None),
                                          EmailLog.sent_at.between(start_date, end_date)).count()
    email_failed = EmailLog.query.filter(EmailLog.status == 'failed',
                                         EmailLog.sent_at.between(start_date, end_date)).count()

    # Email trends per month
    email_trend = []
    for m in months:
        ym = datetime.strptime(m, '%Y-%m')
        next_month = ym.replace(day=28) + timedelta(days=4)
        start = ym
        end = next_month.replace(day=1) - timedelta(days=1)
        sent = EmailLog.query.filter(EmailLog.sent_at.between(start, end)).count()
        opened = EmailLog.query.filter(EmailLog.opened_at.isnot(None),
                                       EmailLog.sent_at.between(start, end)).count()
        rate = (opened / sent * 100) if sent > 0 else 0
        email_trend.append(round(rate, 1))

    # --- Reminders (placeholder – if you have a specific type, adjust) ---
    # For now, we'll treat SMS with "reminder" in message as reminder, but it's not reliable.
    # Instead, we'll use a simple assumption: all SMS are reminders? Not accurate.
    # Better: if you have a separate Reminder model, query it. I'll keep placeholder with a note.
    # We'll use a dummy 75% for now, but you can replace with real logic later.
    reminder_sent = sms_sent  # placeholder
    reminder_confirmed = int(sms_sent * 0.75)  # placeholder
    reminder_rate = 75.0  # placeholder

    # --- Notifications ---
    notif_sent = Notification.query.filter(Notification.created_at.between(start_date, end_date)).count()
    notif_read = NotificationRead.query.join(Notification).filter(
        Notification.created_at.between(start_date, end_date)
    ).count()
    # Notifications can have multiple reads per user? Actually one read per user per notification.
    # Total notifications delivered = number of recipients (if broadcast) or individual notifications.
    # We'll keep it simple: just count notifications.

    # --- Channel Distribution ---
    total_sms = sms_sent
    total_email = email_sent
    total_notif = notif_sent
    total_other = 0  # you can add other channels
    total_all = total_sms + total_email + total_notif + total_other

    # --- Recent Activity (combined logs) ---
    # We'll fetch the last 50 records from SMS, email, and notifications
    recent = []

    # SMS logs
    sms_logs = PatientSMSLog.query.order_by(PatientSMSLog.sent_at.desc()).limit(20).all()
    for log in sms_logs:
        recent.append({
            'recipient_name': log.patient.full_name if log.patient else 'Patient',
            'recipient_detail': log.phone_number,
            'channel': 'SMS',
            'type': 'Message',
            'status': log.status,
            'time': log.sent_at,
            'url': '#'
        })

    staff_sms_logs = StaffSMSLog.query.order_by(StaffSMSLog.sent_at.desc()).limit(20).all()
    for log in staff_sms_logs:
        recent.append({
            'recipient_name': log.staff.full_name if log.staff else 'Staff',
            'recipient_detail': log.phone_number,
            'channel': 'SMS',
            'type': 'Staff Message',
            'status': log.status,
            'time': log.sent_at,
            'url': '#'
        })

    email_logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).limit(20).all()
    for log in email_logs:
        recent.append({
            'recipient_name': log.email,
            'recipient_detail': log.email,
            'channel': 'Email',
            'type': log.subject[:30] + '...' if log.subject else 'Email',
            'status': log.status,
            'time': log.sent_at,
            'url': '#'
        })

    notif_logs = Notification.query.order_by(Notification.created_at.desc()).limit(20).all()
    for notif in notif_logs:
        recent.append({
            'recipient_name': 'System' if notif.is_broadcast else f"User {notif.user_id}",
            'recipient_detail': 'Broadcast' if notif.is_broadcast else 'Individual',
            'channel': 'Notification',
            'type': notif.title,
            'status': 'sent',
            'time': notif.created_at,
            'url': '#'
        })

    # Sort by time descending and take latest 50
    recent.sort(key=lambda x: x['time'], reverse=True)
    recent = recent[:50]

    # Prepare stats dictionary for template
    stats = {
        'total_messages': total_all,
        'total_sms': total_sms,
        'sms_delivered': sms_delivered,
        'sms_failed': sms_failed,
        'sms_rate': round((sms_delivered / total_sms * 100) if total_sms else 0, 1),
        'total_email': total_email,
        'email_opened': email_opened,
        'email_clicked': email_clicked,
        'email_failed': email_failed,
        'email_open_rate': round((email_opened / total_email * 100) if total_email else 0, 1),
        'email_ctr': round((email_clicked / email_opened * 100) if email_opened else 0, 1),
        'reminder_sent': reminder_sent,
        'reminder_confirmed': reminder_confirmed,
        'reminder_rate': reminder_rate,
        'notif_sent': notif_sent,
        'notif_read': notif_read,
    }

    # Trends for chart
    trends = {
        'months': month_labels,
        'sms': sms_trend,
        'email': email_trend,
    }

    # Distribution percentages
    distribution = {
        'sms': round((total_sms / total_all * 100) if total_all else 0, 1),
        'email': round((total_email / total_all * 100) if total_all else 0, 1),
        'notif': round((total_notif / total_all * 100) if total_all else 0, 1),
        'other': round((total_other / total_all * 100) if total_all else 0, 1),
    }

    return render_template(
        'communications/analytics.html',
        title='Communication Analytics',
        stats=stats,
        trends=trends,
        distribution=distribution,
        recent=recent,
        period=period,
        days=days,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )
# Feedback Collection Route
# -----------------------------
@comms_web_bp.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback_system():
    """Patient feedback management – view, filter, and add feedback"""
    if request.method == 'POST':
        # --- Handle manual feedback entry ---
        patient_id = request.form.get('patient_id', type=int)
        source = request.form.get('source')
        sentiment = request.form.get('sentiment')
        rating = request.form.get('rating', type=int)
        comment = request.form.get('comment')
        is_anonymous = request.form.get('is_anonymous') == 'on'
        social_handle = request.form.get('social_handle')

        if not comment:
            flash('Comment is required.', 'danger')
            return redirect(url_for('comms_web_bp.feedback_system'))

        # File upload
        attachment = request.files.get('attachment')
        attachment_path = None
        if attachment and attachment.filename:
            if not allowed_file(attachment.filename):
                flash('File type not allowed.', 'danger')
                return redirect(url_for('comms_web_bp.feedback_system'))
            filename = secure_filename(attachment.filename)
            upload_folder = os.path.join('app', 'static', 'uploads', 'feedback')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            attachment.save(filepath)
            attachment_path = filepath   # store full path (or you can store relative URL)

        feedback = PatientFeedback(
            patient_id=patient_id if patient_id else None,
            source=source,
            sentiment=sentiment,
            rating=rating,
            comment=comment,
            created_by=current_user.id,
            attachment_path=attachment_path,
            social_media_handle=social_handle,
            is_anonymous=is_anonymous
        )
        db.session.add(feedback)
        db.session.commit()
        flash('Feedback added successfully.', 'success')
        return redirect(url_for('comms_web_bp.feedback_system'))

    # --- GET: display feedback list and stats ---
    source_filter = request.args.get('source')
    sentiment_filter = request.args.get('sentiment')
    search = request.args.get('search')

    query = PatientFeedback.query

    if source_filter:
        query = query.filter_by(source=source_filter)
    if sentiment_filter:
        query = query.filter_by(sentiment=sentiment_filter)
    if search:
        query = query.filter(PatientFeedback.comment.ilike(f'%{search}%'))

    feedbacks = query.order_by(PatientFeedback.submitted_at.desc()).all()

    # Stats
    total = PatientFeedback.query.count()
    positive = PatientFeedback.query.filter_by(sentiment='positive').count()
    neutral = PatientFeedback.query.filter_by(sentiment='neutral').count()
    negative = PatientFeedback.query.filter_by(sentiment='negative').count()

    # Trend data (last 7 days)
    end = datetime.utcnow()
    start = end - timedelta(days=6)
    days = []
    pos_data = []
    neu_data = []
    neg_data = []
    for i in range(7):
        day = start + timedelta(days=i)
        next_day = day + timedelta(days=1)
        days.append(day.strftime('%a'))
        pos_data.append(PatientFeedback.query.filter(
            PatientFeedback.sentiment == 'positive',
            PatientFeedback.submitted_at >= day,
            PatientFeedback.submitted_at < next_day
        ).count())
        neu_data.append(PatientFeedback.query.filter(
            PatientFeedback.sentiment == 'neutral',
            PatientFeedback.submitted_at >= day,
            PatientFeedback.submitted_at < next_day
        ).count())
        neg_data.append(PatientFeedback.query.filter(
            PatientFeedback.sentiment == 'negative',
            PatientFeedback.submitted_at >= day,
            PatientFeedback.submitted_at < next_day
        ).count())

    # Highlights (simple topic extraction – in real life you'd use NLP; we'll use placeholder)
    highlights = [
        {'topic': 'Doctor Communication', 'count': 42, 'sentiment': 'positive'},
        {'topic': 'Waiting times', 'count': 28, 'sentiment': 'negative'},
        {'topic': 'Diagnostic accuracy', 'count': 37, 'sentiment': 'positive'},
    ]

    return render_template(
        'communications/feedback.html',
        title='Patient Feedback',
        feedbacks=feedbacks,
        total=total,
        positive=positive,
        neutral=neutral,
        negative=negative,
        days=days,
        pos_data=pos_data,
        neu_data=neu_data,
        neg_data=neg_data,
        highlights=highlights,
        source_filter=source_filter,
        sentiment_filter=sentiment_filter,
        search=search,
        patients=Patient.query.order_by(Patient.first_name).all()  # for the add form
    )
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