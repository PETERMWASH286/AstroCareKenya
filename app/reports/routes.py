# /home/pincho/Desktop/astrocare/app/reports/routes.py

from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user
from app.models import AuditLog
from app.extensions import db
from app.patients.models import Consultation, LabTest, Medication, Patient, Radiology, TbScreening, Transaction, Visit, Vitals

# Assuming has_privilege is a helper available in your app context
from . import reports_web_bp


@reports_web_bp.before_request
@login_required
def ensure_logged_in():
    """
    All routes in this blueprint require login.
    If you have a global login_required setup, you can omit this.
    """
    pass  # Decorator enforces login


@reports_web_bp.route('/audit-logs')
def view_audit_logs():
    """
    Display a paginated list of audit log entries.
    Requires 'reports:audit' privilege.
    """


    # Get pagination parameters from query string
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 25))
    except ValueError:
        page = 1
        per_page = 25

    # Optional filtering (e.g., by model_name or action)
    model_filter = request.args.get('model', None)
    action_filter = request.args.get('action', None)

    query = AuditLog.query

    if model_filter:
        query = query.filter(AuditLog.model_name == model_filter)
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)

    # Order by newest first
    query = query.order_by(AuditLog.timestamp.desc())

    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items

    return render_template(
        'audit_logs.html',
        logs=logs,
        pagination=pagination,
        model_filter=model_filter,
        action_filter=action_filter
    )


@reports_web_bp.route('/clinical')
def clinical():
    """
    Clinical Reports page.
    Requires 'reports:clinical' privilege.
    """
    if not current_user.has_privilege('reports:clinical'):
        abort(403)
    
    # Calculate date range (last 30 days)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=30)
    
    # Visit statistics
    visits_count = Visit.query.count()
    new_patients = Patient.query.filter(Patient.created_at >= start_date).count()
    
    # Service utilization
    lab_tests_count = LabTest.query.count()
    pending_lab_tests = LabTest.query.filter_by(status='requested').count()
    radiology_count = Radiology.query.count()
    completed_radiology = Radiology.query.filter_by(status='completed').count()
    medications_count = Medication.query.count()
    dispensed_meds = Medication.query.filter_by(is_dispensed=True).count()
    
    # Vital signs averages
    avg_vitals = db.session.query(
        db.func.avg(Vitals.temperature).label('avg_temp'),
        db.func.avg(Vitals.heart_rate).label('avg_hr'),
        db.func.avg(Vitals.bp_systolic).label('avg_bp_sys'),
        db.func.avg(Vitals.bp_diastolic).label('avg_bp_dia'),
        db.func.avg(Vitals.spo2).label('avg_spo2')
    ).first()
    
    # TB screening results (using symptom-based calculation)
    tb_positive = TbScreening.query.filter(
        (TbScreening.cough_duration >= 2) |
        (TbScreening.fever == 'yes') |
        (TbScreening.night_sweats == 'yes') |
        (TbScreening.weight_loss_flag == 'yes') |
        (TbScreening.hemoptysis == 'yes')
    ).count()

    tb_negative = TbScreening.query.count() - tb_positive
    tb_pending = 0  # No pending concept in current model
    
    # Recent consultations
    recent_consultations = Consultation.query.options(
        db.joinedload(Consultation.patient),
        db.joinedload(Consultation.visit),
        db.joinedload(Consultation.treated_by)
    ).order_by(Consultation.created_at.desc()).limit(5).all()
    
    # Visit trends (last 30 days)
    visits_trend = {'labels': [], 'values': []}
    for i in range(29, -1, -1):
        date = (datetime.today() - timedelta(days=i)).date()
        count = Visit.query.filter(db.func.date(Visit.visit_date) == date).count()
        visits_trend['labels'].append(date.strftime("%m/%d"))
        visits_trend['values'].append(count)
    
    # Top diagnoses (simplified)
    diagnosis_data = {
        'labels': ['Upper Respiratory Infection', 'Hypertension', 'Diabetes', 'Malaria', 'Prenatal Checkup'],
        'values': [120, 85, 76, 64, 58]
    }
    
    # Age distribution
    age_distribution = [125, 210, 180, 150, 95]  # Actual implementation would calculate this
    
    # Gender distribution
    gender_distribution = [520, 480, 15]  # Male, Female, Other
    
    return render_template(
        'clinical_reports.html',
        visits_count=visits_count,
        new_patients=new_patients,
        lab_tests_count=lab_tests_count,
        pending_lab_tests=pending_lab_tests,
        radiology_count=radiology_count,
        completed_radiology=completed_radiology,
        medications_count=medications_count,
        dispensed_meds=dispensed_meds,
        avg_temperature=round(avg_vitals.avg_temp or 0, 1),
        avg_heart_rate=round(avg_vitals.avg_hr or 0),
        avg_bp_systolic=round(avg_vitals.avg_bp_sys or 0),
        avg_bp_diastolic=round(avg_vitals.avg_bp_dia or 0),
        avg_spo2=round(avg_vitals.avg_spo2 or 0),
        tb_positive=tb_positive,
        tb_negative=tb_negative,
        tb_pending=tb_pending,
        recent_consultations=recent_consultations,
        visits_trend=visits_trend,
        diagnosis_data=diagnosis_data,
        age_distribution=age_distribution,
        gender_distribution=gender_distribution
    )

@reports_web_bp.route('/financial')
def financial():
    """
    Financial Reports page.
    Requires 'reports:financial' privilege.
    """

    # Example: summarize billing, transactions, revenue, etc.
    # e.g. revenue_summary = ...
    return render_template(
        'financial_reports.html',
        # pass any context needed
    )


@reports_web_bp.route('/analytics')
def analytics():
    """
    Analytics Dashboard page.
    Requires 'reports:analytics' privilege.
    """

    # Example: provide aggregate metrics, usage stats, etc.
    # e.g. dashboard_metrics = ...
    return render_template(
        'reports/analytics_dashboard.html',
        # pass any context needed
    )


# Add this to /home/pincho/Desktop/astrocare/app/reports/routes.py

@reports_web_bp.route('/mpesa-logs')
def mpesa_logs():
    """
    Display M-Pesa transaction logs
    Requires 'reports:mpesa' privilege
    """
    # Check privilege
    if not current_user.has_privilege('reports:mpesa'):
        abort(403)

    # Get pagination parameters
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 25))
    except ValueError:
        page = 1
        per_page = 25

    # Get filter parameters from query string
    status_filter = request.args.get('status', None)
    phone_filter = request.args.get('phone', None)
    date_from = request.args.get('date_from', None)
    date_to = request.args.get('date_to', None)

    # Build query
    base_query = Transaction.query.filter(
        Transaction.payment_method.in_(['stk', 'paybill'])
    )

    # Apply filters
    if status_filter:
        base_query = base_query.filter(Transaction.status == status_filter)
    if phone_filter:
        base_query = base_query.filter(Transaction.phone.contains(phone_filter))
    if date_from:
        base_query = base_query.filter(Transaction.created_at >= date_from)
    if date_to:
        # Add 1 day to include the entire end date
        next_day = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        base_query = base_query.filter(Transaction.created_at < next_day)

    # Order by latest first
    query = base_query.order_by(Transaction.created_at.desc())

    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    transactions = pagination.items

    # Calculate summary statistics - FIXED QUERIES
    total_count = base_query.count()
    completed_count = base_query.filter(Transaction.status == 'completed').count()
    pending_count = base_query.filter(Transaction.status == 'pending').count()
    failed_count = base_query.filter(Transaction.status == 'failed').count()
    requested_count = base_query.filter(Transaction.status == 'requested').count()
    
    # Calculate amounts - FIXED QUERIES
    total_amount_result = base_query.with_entities(
        db.func.coalesce(db.func.sum(Transaction.amount), 0.0)
    ).scalar()
    total_amount = total_amount_result if total_amount_result is not None else 0.0
    
    avg_amount_result = base_query.with_entities(
        db.func.coalesce(db.func.avg(Transaction.amount), 0.0)
    ).scalar()
    avg_amount = avg_amount_result if avg_amount_result is not None else 0.0
    
    # Calculate percentages safely
    completed_percentage = round((completed_count / total_count) * 100) if total_count else 0
    pending_percentage = round((pending_count / total_count) * 100) if total_count else 0
    
    summary = {
        'total_count': total_count,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'failed_count': failed_count,
        'requested_count': requested_count,
        'total_amount': total_amount,
        'avg_amount': avg_amount,
        'completed_percentage': completed_percentage,
        'pending_percentage': pending_percentage,
    }
    
    # Calculate daily trend (last 7 days) - FIXED QUERY
    daily_trend = {
        'labels': [],
        'values': []
    }
    
    # Only calculate if we have at least some transactions
    if total_count > 0:
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).date()
            
            # Query for daily amount
            daily_amount_result = base_query.filter(
                db.func.date(Transaction.created_at) == date
            ).with_entities(
                db.func.coalesce(db.func.sum(Transaction.amount), 0.0)
            ).scalar()
            
            daily_amount = daily_amount_result if daily_amount_result is not None else 0.0
            
            daily_trend['labels'].append(date.strftime("%a"))
            daily_trend['values'].append(daily_amount)
    
    return render_template(
        'mpesa_logs.html',  # Fixed template path
        transactions=transactions,
        pagination=pagination,
        status_filter=status_filter,
        phone_filter=phone_filter,
        date_from=date_from,
        date_to=date_to,
        summary=summary,
        daily_trend=daily_trend
    )


@reports_web_bp.route('/transaction-details/<int:transaction_id>')
def transaction_details(transaction_id):
    """
    Display detailed information about a specific M-Pesa transaction
    Requires 'reports:mpesa' privilege
    """
    # Check privilege
    if not current_user.has_privilege('reports:mpesa'):
        abort(403)
    
    # Get the transaction with related data
    transaction = Transaction.query.options(
        db.joinedload(Transaction.patient),
        db.joinedload(Transaction.services)
    ).get_or_404(transaction_id)
    
    # Verify it's an M-Pesa transaction
    if transaction.payment_method not in ['stk', 'paybill']:
        abort(404, "This is not an M-Pesa transaction")
    
    # Format callback data for display
    callback_data = transaction.callback_data or {}
    formatted_callback = json.dumps(callback_data, indent=4) if callback_data else "No callback data available"
    
    # Get audit logs for this transaction
    audit_logs = AuditLog.query.filter(
        AuditLog.model_name == 'Transaction',
        AuditLog.record_id == transaction_id
    ).order_by(AuditLog.timestamp.desc()).all()
    
    return render_template(
        'transaction_details.html',
        transaction=transaction,
        callback_data=formatted_callback,
        audit_logs=audit_logs
    )