# ADDED: Simple print to confirm this file is being executed
print("--- DEBUG: Executing app/dashboard/routes.py ---")

from flask import render_template, redirect, url_for, flash, current_app # Import current_app for logging
from flask_login import login_required, current_user # Import current_user
from datetime import datetime, date
from sqlalchemy import Transaction, func, cast, Date
from app.finance.models import BankAccount, CashAccount, Expense, InsuranceClaim, Invoice, InvoiceItem, Payment, PayrollPayment
from app.hr.models import Payroll
from app.lab.models import LabInventory
from app.patients.models import (
    Consultation, 
    LabTest, 
    Radiology,
    Medication,
    Service,
    Patient,
    Visit,
    Vitals
)
from app.extensions import db
from app.pharmacy.models import PharmacyInventory
from app.radiology.models import RadiologyEquipment, RadiologyInventory, RadiologyQualityControl, RadiologyScheduledMaintenanceLog
from . import dashboard_web_bp # Import the blueprint instance
# from .services import DashboardService # Import service layer if aggregating data
from app.auth.models import Permission, User # Import Permission class
from app.patients.models import  Transaction as TransactionModel  # alias to avoid conflict


@dashboard_web_bp.route('/')
@login_required # Protect the dashboard route
def index():
    """Renders the dashboard based on user role."""


    if current_user.is_authenticated and current_user.is_active:
         current_app.logger.info(f"User {current_user.get_id()} is authenticated and active.")
         # If your User model has a username or email property
         try:
             current_app.logger.info(f"User identity: {current_user.username if hasattr(current_user, 'username') else (current_user.email if hasattr(current_user, 'email') else 'N/A')}")
         except Exception:
             current_app.logger.info("Could not get user identity property (username/email)")

         # Example: Render different templates based on user role/permissions
         # Assuming current_user has 'is_administrator()' and 'can()' methods
         # and Permission constants are available (e.g., via context processor)

         if current_user.is_administrator():
              current_app.logger.info("User is administrator. Rendering admin dashboard.")
              # Pass data specific to admin dashboard
              # stats = DashboardService.get_admin_stats() # Example
              return redirect(url_for('dashboard_web.admin_overview'))
         elif current_user.can(Permission.CAN_RECORD_VITALS): # Example for Nurse/Doctor
              current_app.logger.info("User can record vitals. Rendering nurse/doctor dashboard placeholder.")
              # Pass data specific to nurse/doctor dashboard
              # tasks = DashboardService.get_nurse_tasks(current_user.id) # Example
              # return render_template('nurse/tasks.html') #, tasks=tasks)
              pass # Placeholder for other roles
         # Add more elif blocks for other roles (Doctor, Lab Tech, etc.)
         else:
             current_app.logger.info("User not administrator and no specific role matched. Rendering generic dashboard placeholder.")
             # Default dashboard for patients or other roles without specific views
             # patient_data = DashboardService.get_patient_data(current_user.id) # Example
             # return render_template('patient/dashboard.html') #, patient_data=patient_data)
             pass # Placeholder

         # Fallback if no specific role template is matched (e.g., render a generic dashboard)
         # For now, we'll just render the admin one as a placeholder if no specific logic matches
         return redirect(url_for('dashboard_web.admin_overview'))

    else:
        # This else block should technically not be reached if @login_required works,
        # but it's here for clarity in debugging.
        current_app.logger.info("User is NOT authenticated or NOT active in dashboard route logic. This should not happen with @login_required.")
        return redirect(url_for('auth_web.login'))

from sqlalchemy import func, select

@dashboard_web_bp.route('/admin/overview')
@login_required
def admin_overview():


    today = date.today()
    now = datetime.now()
    first_of_month = date(today.year, today.month, 1)
    last_of_month = date(today.year, today.month, 28) + timedelta(days=4)  # works for all months

    # ----- Patient Metrics -----
    total_patients = Patient.query.count()
    new_patients_today = Patient.query.filter(func.date(Patient.created_at) == today).count()
    new_patients_month = Patient.query.filter(Patient.created_at >= first_of_month).count()

    # ----- Appointments / Visits -----
    visits_today = Visit.query.filter(func.date(Visit.visit_date) == today).count()
    visits_in_progress = Visit.query.filter_by(visit_status='in_progress').count()

    # ----- Staff -----
    total_staff = User.query.filter_by(is_active=True).count()

    # ----- Bed Occupancy (proxy: visits in progress, assuming 50 beds) -----
    bed_occupancy_rate = min(100, (visits_in_progress / 50) * 100)

    # ----- Revenue -----
    daily_revenue = db.session.query(func.sum(Payment.amount)).filter(
        func.date(Payment.payment_date) == today
    ).scalar() or 0.0

    monthly_revenue = db.session.query(func.sum(Payment.amount)).filter(
        Payment.payment_date >= first_of_month,
        Payment.payment_date <= last_of_month
    ).scalar() or 0.0

    # ----- Pending Payments (sum of unpaid invoice balances) -----
    subq = (
        select(Payment.invoice_id, func.sum(Payment.amount).label('paid'))
        .group_by(Payment.invoice_id)
        .subquery()
    )
    pending_payments = db.session.query(
        func.sum(Invoice.total_amount - func.coalesce(subq.c.paid, 0))
    ).outerjoin(
        subq, Invoice.id == subq.c.invoice_id
    ).filter(
        Invoice.status.in_(['pending', 'partial'])
    ).scalar() or 0.0

    # ----- Low Stock Alerts across all stores -----
    low_stock = 0
    low_stock += PharmacyInventory.query.filter(PharmacyInventory.quantity <= PharmacyInventory.low_stock_threshold).count()
    low_stock += LabInventory.query.filter(LabInventory.quantity <= LabInventory.low_stock_threshold).count()
    low_stock += RadiologyInventory.query.filter(RadiologyInventory.quantity <= RadiologyInventory.low_stock_threshold).count()

    # ----- Recent Activity (combined) -----
    recent_activity = []

    for p in Patient.query.order_by(Patient.created_at.desc()).limit(3):
        recent_activity.append({
            'description': f"New patient registered: {p.full_name}",
            'time': p.created_at,
            'icon': 'user-plus',
            'color': 'blue'
        })

    for pay in Payment.query.order_by(Payment.payment_date.desc()).limit(3):
        recent_activity.append({
            'description': f"Payment of KES {pay.amount:,.0f} received",
            'time': pay.payment_date,
            'icon': 'dollar-sign',
            'color': 'green'
        })

    for exp in Expense.query.filter_by(status='paid').order_by(Expense.payment_date.desc()).limit(3):
        recent_activity.append({
            'description': f"Expense: {exp.description[:30]}...",
            'time': exp.payment_date,
            'icon': 'shopping-cart',
            'color': 'red'
        })

    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:6]

    # ----- Admissions Chart (last 30 days) -----
    labels = []
    admissions_data = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        count = Visit.query.filter(func.date(Visit.visit_date) == day).count()
        labels.append(day.strftime('%d %b'))
        admissions_data.append(count)

    # ----- Revenue Trend (last 30 days) -----
    revenue_labels = []
    revenue_data = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        total = db.session.query(func.sum(Payment.amount)).filter(
            func.date(Payment.payment_date) == day
        ).scalar() or 0.0
        revenue_labels.append(day.strftime('%d %b'))
        revenue_data.append(total)
    # Recent patients list (for the table)
    recent_patients = Patient.query.order_by(Patient.created_at.desc()).limit(5).all()
    return render_template(
        'admin/overview.html',
        total_patients=total_patients,
        new_patients_today=new_patients_today,
        new_patients_month=new_patients_month,
        visits_today=visits_today,
        visits_in_progress=visits_in_progress,
        total_staff=total_staff,
        bed_occupancy_rate=round(bed_occupancy_rate, 1),
        daily_revenue=daily_revenue,
        monthly_revenue=monthly_revenue,
        pending_payments=pending_payments,
        low_stock=low_stock,
        recent_activity=recent_activity,
        admissions_labels=labels,
        admissions_data=admissions_data,
        revenue_labels=revenue_labels,
        revenue_data=revenue_data,
            recent_patients=recent_patients,

        today=today,
    now=now,
    )

# ... (other dashboard routes need similar login_required/permission_required decorators) ...


from datetime import datetime, date, timedelta

@dashboard_web_bp.route('/doctor')
@login_required
def doctor_dashboard():
    today = date.today()
    current_date = datetime.now().strftime("%B %d, %Y")
    
    # Calculate start and end of today
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = start_of_day + timedelta(days=1)
    
    # Patients Today: Count of unique patients with visits today
    patients_today = db.session.query(
        func.count(func.distinct(Visit.patient_id))
    ).filter(
        Visit.visit_date >= start_of_day,
        Visit.visit_date < end_of_day
    ).scalar()
    
    # Consultations Today: Count of consultations by this doctor today
    consultations_today = Consultation.query.filter(
        Consultation.treated_by_id == current_user.id,
        Consultation.created_at >= start_of_day,
        Consultation.created_at < end_of_day
    ).count()
    
    # Lab Tests
    pending_lab_tests = LabTest.query.join(Consultation).filter(
        Consultation.treated_by_id == current_user.id,
        LabTest.requested_at >= start_of_day,
        LabTest.requested_at < end_of_day,
        LabTest.status.in_(['requested', 'pending'])
    ).count()
    
    completed_lab_tests = LabTest.query.join(Consultation).filter(
        Consultation.treated_by_id == current_user.id,
        LabTest.requested_at >= start_of_day,
        LabTest.requested_at < end_of_day,
        LabTest.status == 'completed'
    ).count()
    
    # Radiology Tests
    pending_radiology_tests = Radiology.query.join(Consultation).filter(
        Consultation.treated_by_id == current_user.id,
        Radiology.requested_at >= start_of_day,
        Radiology.requested_at < end_of_day,
        Radiology.status.in_(['requested', 'pending'])
    ).count()
    
    completed_radiology_tests = Radiology.query.join(Consultation).filter(
        Consultation.treated_by_id == current_user.id,
        Radiology.requested_at >= start_of_day,
        Radiology.requested_at < end_of_day,
        Radiology.status == 'completed'
    ).count()
    
    # Get today's pending prescriptions
    pending_prescriptions = Medication.query.join(Consultation).filter(
        Consultation.treated_by_id == current_user.id,
        Medication.prescribed_at >= start_of_day,
        Medication.prescribed_at < end_of_day,
        Medication.is_dispensed == False
    ).count()
    
    # Get today's vital records
    vital_records = Vitals.query.filter(
        Vitals.recorded_at >= start_of_day,
        Vitals.recorded_at < end_of_day
    ).count()
    
    # Get today's consultations with diagnoses
    consultations_with_diagnoses = Consultation.query.filter(
        Consultation.treated_by_id == current_user.id,
        Consultation.created_at >= start_of_day,
        Consultation.created_at < end_of_day,
        Consultation.diagnosis.isnot(None),
        Consultation.diagnosis != ''
    ).count()
    
    # Get upcoming appointments
    upcoming_appointments = Visit.query.filter(
        Visit.visit_date > datetime.now()
    ).order_by(Visit.visit_date.asc()).limit(5).all()
    
    # Format appointment data
    appointments_data = []
    for appt in upcoming_appointments:
        patient = Patient.query.get(appt.patient_id)
        appointments_data.append({
            'id': appt.id,
            'patient_name': patient.full_name,
            'visit_date': appt.visit_date.strftime("%b %d, %Y %I:%M %p"),
            'purpose': appt.reason_for_visit or 'Checkup'
        })
    
    # Get most prescribed medications today
    top_medications = db.session.query(
        Service.name,
        func.count(Medication.id).label('prescription_count')
    ).join(Medication, Medication.service_id == Service.id
    ).join(Consultation, Consultation.id == Medication.consultation_id
    ).filter(
        Consultation.treated_by_id == current_user.id,
        Medication.prescribed_at >= start_of_day,
        Medication.prescribed_at < end_of_day
    ).group_by(Service.name
    ).order_by(db.desc('prescription_count')
    ).limit(5).all()
    
    return render_template('doctor/dashboard.html', 
                          current_date=current_date,
                          patients_today=patients_today,
                          consultations_today=consultations_today,
                          pending_lab_tests=pending_lab_tests,
                          completed_lab_tests=completed_lab_tests,
                          pending_radiology_tests=pending_radiology_tests,
                          completed_radiology_tests=completed_radiology_tests,
                          pending_prescriptions=pending_prescriptions,
                          vital_records=vital_records,
                          consultations_with_diagnoses=consultations_with_diagnoses,
                          upcoming_appointments=appointments_data,
                          top_medications=top_medications)


@dashboard_web_bp.route('/nurse')
@login_required
def nurse_dashboard():
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end   = datetime.combine(date.today(), datetime.max.time())
    last_24h = today_start - timedelta(days=1)

    # --- Stats Cards ---
    patients_today = Patient.query.filter(Patient.created_at.between(today_start, today_end)).count()
    visits_in_progress = Visit.query.filter_by(visit_status='in_progress').count()
    # Appointments – if you have an Appointment model, use it; otherwise count visits today
    appointments_today = Visit.query.filter(Visit.visit_date.between(today_start, today_end)).count()

    # Critical alerts: abnormal vitals in last 24h
    abnormal_vitals = Vitals.query.filter(
        Vitals.recorded_at >= last_24h,
        (Vitals.bp_systolic > 140) | (Vitals.bp_diastolic > 90) |
        (Vitals.temperature > 38.0) | (Vitals.spo2 < 90) |
        (Vitals.heart_rate > 100) | (Vitals.heart_rate < 60)
    ).count()

    # Pending tasks
    pending_labs = LabTest.query.filter_by(status='requested').count()
    pending_meds = Medication.query.filter_by(is_dispensed=False).count()
    pending_tasks = pending_labs + pending_meds

    # --- Recent Activity (combined) ---
    recent_activity = []

    # New patients
    for p in Patient.query.order_by(Patient.created_at.desc()).limit(3):
        recent_activity.append({
            'description': f"New patient registered: {p.full_name}",
            'time': p.created_at,
            'type': 'registration'
        })

    # Abnormal vitals
    for v in Vitals.query.filter(Vitals.recorded_at >= last_24h).order_by(Vitals.recorded_at.desc()).limit(3):
        patient_name = v.patient.full_name if v.patient else 'Unknown'
        recent_activity.append({
            'description': f"Abnormal vitals recorded for {patient_name}",
            'time': v.recorded_at,
            'type': 'vitals'
        })

    # Lab results completed
    # Lab results completed
    for l in LabTest.query.filter(LabTest.status == 'completed').order_by(LabTest.completed_at.desc()).limit(3).all():
        # Get patient via visit
        patient_name = 'Unknown'
        if l.visit and l.visit.patient:
            patient_name = l.visit.patient.full_name
        elif l.consultation and l.consultation.patient:
            patient_name = l.consultation.patient.full_name
        recent_activity.append({
            'description': f"Lab results available for {patient_name}",
            'time': l.completed_at or l.updated_at,
            'type': 'lab'
        })

    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:5]

    # --- Patient volume by hour (for chart) ---
    hours = list(range(8, 19))  # 8am to 6pm
    hourly_counts = []
    for hour in hours:
        hour_start = datetime.combine(date.today(), datetime.min.time().replace(hour=hour))
        hour_end = hour_start + timedelta(hours=1)
        count = Patient.query.filter(Patient.created_at.between(hour_start, hour_end)).count()
        hourly_counts.append(count)

    # --- Current inpatients (visits in progress) ---
    current_inpatients = Visit.query.filter_by(visit_status='in_progress')\
        .order_by(Visit.visit_date.desc()).limit(5).all()

    # Greeting based on time
    hour_now = datetime.now().hour
    if hour_now < 12:
        greeting = "Good morning"
    elif hour_now < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template(
        'nurse/dashboard.html',
        greeting=greeting,
        patients_today=patients_today,
        visits_in_progress=visits_in_progress,
        appointments_today=appointments_today,
        critical_alerts=abnormal_vitals,
        pending_tasks=pending_tasks,
        pending_labs=pending_labs,
        pending_meds=pending_meds,
        recent_activity=recent_activity,
        hourly_labels=[f"{h}:00" for h in hours],
        hourly_counts=hourly_counts,
        current_inpatients=current_inpatients,
        today=date.today()
    )




@dashboard_web_bp.route('/labtech')
@login_required
def labtech_dashboard():
    from app.lab.models import BloodInventory, LabEquipment, LabInventory, QualityControl, Sample

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end   = datetime.combine(date.today(), datetime.max.time())
    today = date.today()
    next_week = today + timedelta(days=7)

    # --- Stats Cards ---
    pending_tests = LabTest.query.filter_by(status='requested').count()
    samples_pending = Sample.query.filter_by(acceptance_status='Pending Verification').count()
    low_stock = LabInventory.query.filter(LabInventory.quantity <= LabInventory.low_stock_threshold).count()
    maintenance_due = LabEquipment.query.filter(LabEquipment.next_maintenance_date <= next_week).count()
    blood_expiring = BloodInventory.query.filter(
        BloodInventory.expiry_date <= next_week,
        BloodInventory.status == 'Available'
    ).count()

    # --- Recent Activity (combine tests, samples, QC) ---
    recent_activity = []

    # Recent completed tests
    for test in LabTest.query.filter_by(status='completed').order_by(LabTest.completed_at.desc()).limit(3).all():
        patient_name = 'Unknown'
        if test.visit and test.visit.patient:
            patient_name = test.visit.patient.full_name
        elif test.consultation and test.consultation.patient:
            patient_name = test.consultation.patient.full_name
        recent_activity.append({
            'description': f"Test completed for {patient_name}",
            'time': test.completed_at or test.updated_at,
            'type': 'test'
        })

    # Recent samples received
    for sample in Sample.query.order_by(Sample.received_date.desc()).limit(3).all():
        patient_name = sample.patient.full_name if sample.patient else 'Unknown'
        recent_activity.append({
            'description': f"Sample received: {sample.sample_type} for {patient_name}",
            'time': sample.received_date,
            'type': 'sample'
        })

    # Recent QC results
    for qc in QualityControl.query.order_by(QualityControl.test_date.desc()).limit(3).all():
        test_name = qc.test.test_name if qc.test else 'Unknown test'
        recent_activity.append({
            'description': f"QC {qc.result}: {test_name}",
            'time': qc.test_date,
            'type': 'qc'
        })

    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:5]

    # --- Daily Test Volume (by hour) ---
    hours = list(range(8, 19))  # 8am to 6pm
    hourly_counts = []
    for hour in hours:
        hour_start = datetime.combine(today, datetime.min.time().replace(hour=hour))
        hour_end = hour_start + timedelta(hours=1)
        count = LabTest.query.filter(
            LabTest.completed_at.between(hour_start, hour_end)
        ).count()
        hourly_counts.append(count)

    # --- Low Stock Items (for table) ---
    low_stock_items = LabInventory.query.filter(
        LabInventory.quantity <= LabInventory.low_stock_threshold
    ).order_by(LabInventory.quantity).limit(5).all()

    # --- Samples Awaiting Verification (for table) ---
    pending_samples = Sample.query.filter_by(acceptance_status='Pending Verification')\
        .order_by(Sample.received_date).limit(5).all()

    # --- Greeting ---
    hour_now = datetime.now().hour
    if hour_now < 12:
        greeting = "Good morning"
    elif hour_now < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template(
        'labtech/dashboard.html',
        greeting=greeting,
        pending_tests=pending_tests,
        samples_pending=samples_pending,
        low_stock=low_stock,
        maintenance_due=maintenance_due,
        blood_expiring=blood_expiring,
        recent_activity=recent_activity,
        hourly_labels=[f"{h}:00" for h in hours],
        hourly_counts=hourly_counts,
        low_stock_items=low_stock_items,
        pending_samples=pending_samples,
        today=today
    )
    
    

@dashboard_web_bp.route('/radiology')
@login_required
def radiology_dashboard():

    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    next_week = today + timedelta(days=7)

    # --- Stats Cards ---
    pending_exams = Radiology.query.filter_by(status='requested').count()
    low_stock = RadiologyInventory.query.filter(
        RadiologyInventory.quantity <= RadiologyInventory.low_stock_threshold
    ).count()
    maintenance_due = RadiologyEquipment.query.filter(
        RadiologyEquipment.next_maintenance_date <= next_week
    ).count()
    qc_failed = RadiologyQualityControl.query.filter_by(result='Fail').count()

    # --- Recent Activity ---
    recent_activity = []

    # Completed exams
    for exam in Radiology.query.filter_by(status='completed').order_by(Radiology.completed_at.desc()).limit(3).all():
        patient_name = 'Unknown'
        if exam.visit and exam.visit.patient:
            patient_name = exam.visit.patient.full_name
        elif exam.consultation and exam.consultation.patient:
            patient_name = exam.consultation.patient.full_name
        recent_activity.append({
            'description': f"Exam completed for {patient_name}",
            'time': exam.completed_at or exam.updated_at,
            'type': 'exam'
        })

    # Inventory updates
    for inv in RadiologyInventory.query.order_by(RadiologyInventory.updated_at.desc()).limit(3).all():
        recent_activity.append({
            'description': f"Inventory updated: {inv.item_name} (qty: {inv.quantity})",
            'time': inv.updated_at,
            'type': 'inventory'
        })

    # Maintenance logs
    for maint in RadiologyScheduledMaintenanceLog.query.order_by(RadiologyScheduledMaintenanceLog.submission_date.desc()).limit(3).all():
        recent_activity.append({
            'description': f"Maintenance performed on {maint.equipment}",
            'time': maint.submission_date,
            'type': 'maintenance'
        })

    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:5]

    # --- Exam Volume by Hour (for chart) ---
    hours = list(range(8, 19))  # 8am to 6pm
    hourly_counts = []
    for hour in hours:
        hour_start = datetime.combine(today, datetime.min.time().replace(hour=hour))
        hour_end = hour_start + timedelta(hours=1)
        count = Radiology.query.filter(
            Radiology.completed_at.between(hour_start, hour_end)
        ).count()
        hourly_counts.append(count)

    # --- Tables ---
    pending_exams_list = Radiology.query.filter_by(status='requested').order_by(Radiology.requested_at).limit(5).all()
    low_stock_items = RadiologyInventory.query.filter(
        RadiologyInventory.quantity <= RadiologyInventory.low_stock_threshold
    ).order_by(RadiologyInventory.quantity).limit(5).all()
    upcoming_maintenance = RadiologyEquipment.query.filter(
        RadiologyEquipment.next_maintenance_date <= next_week
    ).order_by(RadiologyEquipment.next_maintenance_date).limit(5).all()

    # --- Greeting ---
    hour_now = datetime.now().hour
    if hour_now < 12:
        greeting = "Good morning"
    elif hour_now < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template(
        'radiology/dashboard.html',
        greeting=greeting,
        pending_exams=pending_exams,
        low_stock=low_stock,
        maintenance_due=maintenance_due,
        qc_failed=qc_failed,
        recent_activity=recent_activity,
        hourly_labels=[f"{h}:00" for h in hours],
        hourly_counts=hourly_counts,
        pending_exams_list=pending_exams_list,
        low_stock_items=low_stock_items,
        upcoming_maintenance=upcoming_maintenance,
        today=today
    )


@dashboard_web_bp.route('/pharmacy')
@login_required
def pharmacy_dashboard():
    # Lazy imports to break circular imports
    from app.pharmacy.models import PharmacyInventory, PharmacyStockFlow

    today = date.today()
    next_30_days = today + timedelta(days=30)

    # Stats
    total_items = PharmacyInventory.query.count()
    low_stock = PharmacyInventory.query.filter(PharmacyInventory.quantity <= PharmacyInventory.low_stock_threshold).count()
    expiring_soon = PharmacyInventory.query.filter(
        PharmacyInventory.expiry_date <= next_30_days,
        PharmacyInventory.expiry_date >= today
    ).count()
    pending_prescriptions = Medication.query.filter_by(is_dispensed=False).count()

    # Inventory value
    total_cost = db.session.query(db.func.sum(PharmacyInventory.buying_price * PharmacyInventory.quantity)).scalar() or 0
    total_revenue = db.session.query(db.func.sum(PharmacyInventory.selling_price * PharmacyInventory.quantity)).scalar() or 0
    expired_count = PharmacyInventory.query.filter(PharmacyInventory.expiry_date < today).count()

    # Recent activity (stock flows and pending prescriptions)
    recent = []
    for flow in PharmacyStockFlow.query.order_by(PharmacyStockFlow.created_at.desc()).limit(5).all():
        item = flow.pharmacy_inventory
        recent.append({
            'description': f"{'Dispensed' if flow.quantity_change < 0 else 'Received'} {abs(flow.quantity_change)} {item.unit if item else ''} of {item.item_name if item else 'Unknown'}",
            'time': flow.created_at,
            'type': 'dispense' if flow.flow_type == 'dispense' else 'stock'
        })
    for med in Medication.query.filter_by(is_dispensed=False).order_by(Medication.prescribed_at.desc()).limit(5).all():
        patient_name = 'Unknown'
        if med.visit and med.visit.patient:
            patient_name = med.visit.patient.full_name
        elif med.consultation and med.consultation.patient:
            patient_name = med.consultation.patient.full_name
        recent.append({
            'description': f"Prescription for {patient_name}: {med.service.name if med.service else 'medication'}",
            'time': med.prescribed_at,
            'type': 'prescription'
        })
    recent.sort(key=lambda x: x['time'], reverse=True)
    recent = recent[:5]

    # Tables
    low_stock_items = PharmacyInventory.query.filter(PharmacyInventory.quantity <= PharmacyInventory.low_stock_threshold).order_by(PharmacyInventory.quantity).limit(5).all()
    expiring_items = PharmacyInventory.query.filter(
        PharmacyInventory.expiry_date <= next_30_days,
        PharmacyInventory.expiry_date >= today
    ).order_by(PharmacyInventory.expiry_date).limit(5).all()
    pending_meds = Medication.query.filter_by(is_dispensed=False).order_by(Medication.prescribed_at).limit(5).all()

    # Greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template(
        'pharmacy/dashboard.html',
        greeting=greeting,
        total_items=total_items,
        low_stock=low_stock,
        expiring_soon=expiring_soon,
        pending_prescriptions=pending_prescriptions,
        total_cost=total_cost,
        total_revenue=total_revenue,
        expired_count=expired_count,
        recent_activity=recent,
        low_stock_items=low_stock_items,
        expiring_items=expiring_items,
        pending_meds=pending_meds,
        today=today
    )




def get_greeting():
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"

@dashboard_web_bp.route('/registration')
@login_required
def registration_dashboard():
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_end - timedelta(days=1)

    # Patients today vs yesterday
    patients_today = Patient.query.filter(Patient.created_at.between(today_start, today_end)).count()
    patients_yesterday = Patient.query.filter(Patient.created_at.between(yesterday_start, yesterday_end)).count()
    if patients_yesterday:
        patient_change = ((patients_today - patients_yesterday) / patients_yesterday) * 100
    else:
        patient_change = 0

    # Visits in progress
    visits_in_progress = Visit.query.filter_by(visit_status='in_progress').count()

    # Pending payments
    pending_payments = db.session.query(TransactionModel).filter_by(status='pending').count()

    # Revenue today vs yesterday
    revenue_today = db.session.query(db.func.sum(TransactionModel.amount)).filter(
        TransactionModel.status == 'completed',
        TransactionModel.paid_at.between(today_start, today_end)
    ).scalar() or 0.0
    revenue_yesterday = db.session.query(db.func.sum(TransactionModel.amount)).filter(
        TransactionModel.status == 'completed',
        TransactionModel.paid_at.between(yesterday_start, yesterday_end)
    ).scalar() or 0.0
    if revenue_yesterday:
        revenue_change = ((revenue_today - revenue_yesterday) / revenue_yesterday) * 100
    else:
        revenue_change = 0

    # Hourly registrations today (for chart)
    hourly_counts = []
    hours = range(8, 18)  # 8am to 5pm
    for hour in hours:
        hour_start = datetime.combine(today, datetime.min.time().replace(hour=hour))
        hour_end = hour_start.replace(hour=hour+1) if hour < 23 else hour_start.replace(hour=23, minute=59)
        count = Patient.query.filter(Patient.created_at.between(hour_start, hour_end)).count()
        hourly_counts.append(count)

    # Recent patients
    recent_patients = Patient.query.order_by(Patient.created_at.desc()).limit(5).all()

    # Pending transactions
    pending_transactions = db.session.query(TransactionModel).filter_by(status='pending').order_by(TransactionModel.created_at.desc()).limit(5).all()

    # Upcoming appointments (if any) - placeholder, assuming you have an Appointment model
    # For now, we'll use an empty list and show a message.
    upcoming_appointments = []  # Replace with actual query if model exists

    greeting = get_greeting()

    return render_template(
        'registration/dashboard.html',
        patients_today=patients_today,
        patient_change=patient_change,
        visits_in_progress=visits_in_progress,
        pending_payments=pending_payments,
        revenue_today=revenue_today,
        revenue_change=revenue_change,
        recent_patients=recent_patients,
        pending_transactions=pending_transactions,
        hourly_counts=hourly_counts,
        hours=hours,
        upcoming_appointments=upcoming_appointments,
        greeting=greeting,
        user=current_user,
        today=today
    )

@dashboard_web_bp.route('/patient/dashboard')
@login_required
def patient_dashboard():
    return render_template('admin/overview.html')  # fallback or patient-specific template


@dashboard_web_bp.route('/billing/dashboard')
@login_required
def billing_dashboard():
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end   = datetime.combine(date.today(), datetime.max.time())
    week_ago = today_start - timedelta(days=6)

    # --- Summary Cards ---
    total_billed_today = db.session.query(func.sum(TransactionModel.amount)).filter(
        TransactionModel.created_at.between(today_start, today_end)
    ).scalar() or 0.0

    pending_amount = db.session.query(func.sum(TransactionModel.amount)).filter(
        TransactionModel.status == 'pending'
    ).scalar() or 0.0

    payments_received_today = db.session.query(func.sum(TransactionModel.amount)).filter(
        TransactionModel.status == 'completed',
        TransactionModel.paid_at.between(today_start, today_end)
    ).scalar() or 0.0

    refunds_today = 0  # adjust if you have refunds

    # --- Recent Transactions ---
    recent_transactions = TransactionModel.query.order_by(TransactionModel.created_at.desc()).limit(10).all()

    # --- Weekly Outstanding ---
    weekly_labels = []
    weekly_data = []
    for i in range(7):
        day = (today_start - timedelta(days=6 - i)).date()
        day_start = datetime.combine(day, datetime.min.time())
        day_end   = datetime.combine(day, datetime.max.time())
        total_pending = db.session.query(func.sum(TransactionModel.amount)).filter(
            TransactionModel.status == 'pending',
            TransactionModel.created_at.between(day_start, day_end)
        ).scalar() or 0
        weekly_labels.append(day.strftime('%a'))
        weekly_data.append(total_pending)

    # --- Payment Methods Breakdown ---
    thirty_days_ago = today_start - timedelta(days=30)
    methods = db.session.query(
        TransactionModel.payment_method,
        func.count(TransactionModel.id).label('count')
    ).filter(TransactionModel.created_at >= thirty_days_ago).group_by(TransactionModel.payment_method).all()

    method_labels = [m[0] for m in methods]
    method_counts = [m[1] for m in methods]

    # --- Notifications ---
    notifications = []
    overdue_cutoff = today_start - timedelta(days=7)
    overdue_invoices = TransactionModel.query.filter(
        TransactionModel.status == 'pending',
        TransactionModel.created_at < overdue_cutoff
    ).limit(5).all()
    for inv in overdue_invoices:
        patient_name = inv.patient.full_name if inv.patient else 'Patient'
        notifications.append({
            'icon': 'bg-red-600',
            'icon_svg': 'M6 18L18 6M6 6l12 12',
            'text': f"Invoice #{inv.id} for {patient_name} is overdue (created {inv.created_at.strftime('%Y-%m-%d')})."
        })

    pending_cutoff = today_start - timedelta(days=3)
    pending_invoices = TransactionModel.query.filter(
        TransactionModel.status == 'pending',
        TransactionModel.created_at.between(pending_cutoff, today_start)
    ).limit(5).all()
    for inv in pending_invoices:
        patient_name = inv.patient.full_name if inv.patient else 'Patient'
        notifications.append({
            'icon': 'bg-indigo-600',
            'icon_svg': 'M13 16h-1v-4h-1m4 4v-4m-3 8a9 9 0 11-9-9 9 9 0 019 9z',
            'text': f"Invoice #{inv.id} for {patient_name} pending for {(today_start - inv.created_at).days} days."
        })

    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template(
        'billing/dashboard.html',
        greeting=greeting,
        total_billed_today=total_billed_today,
        pending_amount=pending_amount,
        payments_received_today=payments_received_today,
        refunds_today=refunds_today,
        recent_transactions=recent_transactions,
        weekly_labels=weekly_labels,
        weekly_data=weekly_data,
        method_labels=method_labels,
        method_counts=method_counts,
        notifications=notifications,
        today=date.today(),
        now=datetime.now()
    )
    
    


@dashboard_web_bp.route('/hr')
@login_required
def hr_dashboard():
    # Lazy imports to break circular imports
    from app.hr.models import (
        EmployeePayrollInfo, Payroll, PayrollPeriod,
        LeaveRequest, DisciplinaryCase, JobPosting,
        Candidate, Interview, DutyAssignment, DutyRota,
        AttendanceRecord
    )

    today = date.today()
    first_of_month = date(today.year, today.month, 1)
    last_of_month = date(today.year, today.month, 28) + timedelta(days=4)  # works for all months

    # --- Employee Stats ---
    total_employees = User.query.count()
    active_employees = EmployeePayrollInfo.query.filter_by(is_active=True).count()
    new_hires_this_month = EmployeePayrollInfo.query.filter(
        EmployeePayrollInfo.created_at >= first_of_month
    ).count()

    # --- Payroll Summary (current month) ---
    current_period = PayrollPeriod.query.filter(
        PayrollPeriod.start_date >= first_of_month,
        PayrollPeriod.end_date <= last_of_month
    ).first()
    if current_period:
        current_payroll = Payroll.query.filter_by(period_id=current_period.id).first()
        payroll_gross = current_payroll.total_gross if current_payroll else 0
        payroll_net = current_payroll.total_net if current_payroll else 0
        payroll_status = current_payroll.status if current_payroll else 'Not Processed'
    else:
        payroll_gross = 0
        payroll_net = 0
        payroll_status = 'No Period'

    # --- Leave Requests ---
    pending_leave = LeaveRequest.query.filter_by(status='Pending').count()
    approved_leave = LeaveRequest.query.filter_by(status='Approved').count()
    rejected_leave = LeaveRequest.query.filter_by(status='Rejected').count()

    # --- Disciplinary Cases ---
    open_cases = DisciplinaryCase.query.filter(
        DisciplinaryCase.status.in_(['Open', 'Under Investigation'])
    ).count()
    closed_cases = DisciplinaryCase.query.filter_by(status='Closed').count()

    # --- Recruitment ---
    open_positions = JobPosting.query.filter_by(status='Published').count()
    total_candidates = Candidate.query.count()
    interviews_today = Interview.query.filter(
        db.func.date(Interview.scheduled_date) == today
    ).count()

    # --- Attendance / Duty Rota ---
    absent_today = AttendanceRecord.query.filter_by(
        date=today, status='Absent'
    ).count()
    on_leave_today = AttendanceRecord.query.filter_by(
        date=today, status='On Leave'
    ).count()

    # --- Recent Activity (combined) ---
    recent_activity = []

    # Recent leave requests
    for lr in LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).limit(3).all():
        recent_activity.append({
            'description': f"{lr.employee.full_name} requested {lr.leave_type.name} leave",
            'time': lr.created_at,
            'type': 'leave'
        })

    # Recent disciplinary cases
    for dc in DisciplinaryCase.query.order_by(DisciplinaryCase.created_at.desc()).limit(3).all():
        recent_activity.append({
            'description': f"Case #{dc.case_number} opened for {dc.employee.full_name}",
            'time': dc.created_at,
            'type': 'disciplinary'
        })

    # Recent candidates
    for cand in Candidate.query.order_by(Candidate.created_at.desc()).limit(3).all():
        recent_activity.append({
            'description': f"New candidate: {cand.full_name} for {cand.job_posting.title}",
            'time': cand.created_at,
            'type': 'candidate'
        })

    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:5]

    # --- Pending leave requests (for table) ---
    pending_leave_list = LeaveRequest.query.filter_by(status='Pending').order_by(LeaveRequest.start_date).limit(5).all()

    # --- Recent open cases (for table) ---
    recent_cases = DisciplinaryCase.query.filter(
        DisciplinaryCase.status.in_(['Open', 'Under Investigation'])
    ).order_by(DisciplinaryCase.date_reported.desc()).limit(5).all()

    # --- Upcoming interviews ---
    upcoming_interviews = Interview.query.filter(
        Interview.scheduled_date >= datetime.now()
    ).order_by(Interview.scheduled_date).limit(5).all()

    # --- Job postings with candidate count ---
    job_postings = JobPosting.query.filter_by(status='Published').limit(5).all()
    for jp in job_postings:
        jp.candidate_count = Candidate.query.filter_by(job_posting_id=jp.id).count()

    # --- Greeting ---
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template(
        'hr/hr_dashboard.html',
        greeting=greeting,
        total_employees=total_employees,
        active_employees=active_employees,
        new_hires_this_month=new_hires_this_month,
        payroll_gross=payroll_gross,
        payroll_net=payroll_net,
        payroll_status=payroll_status,
        pending_leave=pending_leave,
        approved_leave=approved_leave,
        rejected_leave=rejected_leave,
        open_cases=open_cases,
        closed_cases=closed_cases,
        open_positions=open_positions,
        total_candidates=total_candidates,
        interviews_today=interviews_today,
        absent_today=absent_today,
        on_leave_today=on_leave_today,
        recent_activity=recent_activity,
        pending_leave_list=pending_leave_list,
        recent_cases=recent_cases,
        upcoming_interviews=upcoming_interviews,
        job_postings=job_postings,
        today=today
    )
    
    
    
    




@dashboard_web_bp.route('/finance')
@login_required
def finance_dashboard():


    today = date.today()
    first_of_month = date(today.year, today.month, 1)
    last_of_month = date(today.year, today.month, 28) + timedelta(days=4)  # works for all months

    # --- Revenue & Payments (using Payment model) ---
    daily_revenue = db.session.query(db.func.sum(Payment.amount)).filter(
        db.func.date(Payment.payment_date) == today
    ).scalar() or 0.0

    monthly_revenue = db.session.query(db.func.sum(Payment.amount)).filter(
        Payment.payment_date >= first_of_month,
        Payment.payment_date <= last_of_month
    ).scalar() or 0.0

    # --- Pending Payments (using Invoice.total - sum(Payments)) ---
    from sqlalchemy import func, select
    subq = (
        select(Payment.invoice_id, func.sum(Payment.amount).label('paid'))
        .group_by(Payment.invoice_id)
        .subquery()
    )
    pending_payments = db.session.query(
        func.sum(Invoice.total_amount - func.coalesce(subq.c.paid, 0))
    ).outerjoin(
        subq, Invoice.id == subq.c.invoice_id
    ).filter(
        Invoice.status.in_(['pending', 'partial'])
    ).scalar() or 0.0

    # --- Expenses ---
    daily_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.status == 'paid',
        db.func.date(Expense.payment_date) == today
    ).scalar() or 0.0

    monthly_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.status == 'paid',
        Expense.payment_date >= first_of_month,
        Expense.payment_date <= last_of_month
    ).scalar() or 0.0

    # --- Cash & Bank Balances ---
    cash_balance = db.session.query(db.func.sum(CashAccount.current_balance)).scalar() or 0.0
    bank_balance = db.session.query(db.func.sum(BankAccount.current_balance)).scalar() or 0.0

    # --- Payroll ---
    current_payroll = Payroll.query.filter(
        Payroll.status.in_(['Processed', 'Paid'])
    ).order_by(Payroll.processed_at.desc()).first()
    payroll_total = current_payroll.total_net if current_payroll else 0

    # --- Insurance Claims ---
    pending_claims = InsuranceClaim.query.filter_by(status='submitted').count()
    approved_claims = InsuranceClaim.query.filter_by(status='approved').count()

    # --- Sales by Department (for chart) – based on paid invoices (no date filter to keep simple) ---
    dept_sales = db.session.query(
        Service.category,
        db.func.sum(InvoiceItem.total_price).label('total')
    ).join(InvoiceItem.service).join(InvoiceItem.invoice).filter(
        Invoice.status == 'paid'
    ).group_by(Service.category).all()

    dept_labels = [item[0] for item in dept_sales]
    dept_data = [float(item[1]) for item in dept_sales]

    # --- Payment Method Breakdown (last 30 days) ---
    thirty_days_ago = datetime.now() - timedelta(days=30)
    payment_methods = db.session.query(
        Payment.method,
        db.func.count(Payment.id).label('count')
    ).filter(Payment.payment_date >= thirty_days_ago).group_by(Payment.method).all()
    method_labels = [m[0] for m in payment_methods]
    method_counts = [m[1] for m in payment_methods]

    # --- Recent Payments (latest 5) ---
    recent_payments = Payment.query.order_by(Payment.payment_date.desc()).limit(5).all()

    # --- Recent Expenses (latest 5) ---
    recent_expenses = Expense.query.filter_by(status='paid').order_by(Expense.payment_date.desc()).limit(5).all()

    # --- Cash Accounts with balances ---
    cash_accounts = CashAccount.query.filter_by(is_active=True).limit(5).all()

    # --- Bank Accounts with balances ---
    bank_accounts = BankAccount.query.filter_by(is_active=True).limit(5).all()

    # --- Greeting ---
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template(
        'finance/finance_dashboard.html',
        greeting=greeting,
        daily_revenue=daily_revenue,
        monthly_revenue=monthly_revenue,
        pending_payments=pending_payments,
        daily_expenses=daily_expenses,
        monthly_expenses=monthly_expenses,
        cash_balance=cash_balance,
        bank_balance=bank_balance,
        payroll_total=payroll_total,
        pending_claims=pending_claims,
        approved_claims=approved_claims,
        dept_labels=dept_labels,
        dept_data=dept_data,
        method_labels=method_labels,
        method_counts=method_counts,
        recent_payments=recent_payments,
        recent_expenses=recent_expenses,
        cash_accounts=cash_accounts,
        bank_accounts=bank_accounts,
        today=today
    )