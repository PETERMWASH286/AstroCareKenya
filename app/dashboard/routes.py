# ADDED: Simple print to confirm this file is being executed
print("--- DEBUG: Executing app/dashboard/routes.py ---")

from flask import render_template, redirect, url_for, flash, current_app # Import current_app for logging
from flask_login import login_required, current_user # Import current_user
from datetime import datetime, date
from sqlalchemy import func, cast, Date
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
from . import dashboard_web_bp # Import the blueprint instance
# from .services import DashboardService # Import service layer if aggregating data
from app.auth.models import Permission # Import Permission class


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
              return render_template('admin/overview.html') #, stats=stats)
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
         return render_template('admin/overview.html') # Default fallback

    else:
        # This else block should technically not be reached if @login_required works,
        # but it's here for clarity in debugging.
        current_app.logger.info("User is NOT authenticated or NOT active in dashboard route logic. This should not happen with @login_required.")
        return redirect(url_for('auth_web.login'))


@dashboard_web_bp.route('/admin/overview')
@login_required # Protect this specific admin route
# Add permission check if only admins should access this specific route
# from app.auth.decorators import permission_required # Assuming you have this decorator
# @permission_required(Permission.CAN_ADMINISTER_SYSTEM) # Example RBAC decorator
def admin_overview():
     """Admin dashboard overview."""
     # Flask-Login ensures current_user is authenticated
     current_app.logger.info(f"Admin overview accessed by user: {current_user.get_id()}")
     # You can now fetch data specific to admin overview via services
     # stats = DashboardService.get_admin_stats()
     # Template path relative to blueprint's template_folder ('templates')
     return render_template('admin/overview.html') #, stats=stats)

# ... (other dashboard routes need similar login_required/permission_required decorators) ...


from datetime import datetime, date, timedelta

@dashboard_web_bp.route('/doctor/dashboard')
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

@dashboard_web_bp.route('/nurse/dashboard')
@login_required
def nurse_dashboard():
    return render_template('nurse/dashboard.html')

@dashboard_web_bp.route('/labtech/dashboard')
@login_required
def labtech_dashboard():
    return render_template('labtech/dashboard.html')

@dashboard_web_bp.route('/radiology/dashboard')
@login_required
def radiology_dashboard():
    return render_template('radiology/dashboard.html')

@dashboard_web_bp.route('/pharmacy/dashboard')
@login_required
def pharmacy_dashboard():
    return render_template('pharmacy/dashboard.html')

@dashboard_web_bp.route('/registration/dashboard')
@login_required
def registration_dashboard():
    return render_template('registration/dashboard.html')

@dashboard_web_bp.route('/patient/dashboard')
@login_required
def patient_dashboard():
    return render_template('admin/overview.html')  # fallback or patient-specific template

@dashboard_web_bp.route('/billing/dashboard')
@login_required
def billing_dashboard():
    return render_template('billing/dashboard.html')