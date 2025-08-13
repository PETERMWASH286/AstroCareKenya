# /home/pincho/Desktop/astrocare/app/appointments/routes.py

from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app.appointments.models import Appointment, Clinic
from app.auth.models import User
from app.extensions import db
from app.patients.models import Patient
from app.user_management.models import Department
# (Import any models you need, e.g. Appointment, Patient, etc.)
from . import appointments_web_bp


@appointments_web_bp.route('/appointments/new', methods=['GET', 'POST'])
@login_required
def schedule_new():
    """
    Schedule a brand new appointment.
    GET:  Show a blank form (load clinics + doctors).
    POST: Process form submission and save to the database.
    """
    # 1) Load all clinics
    clinics = Clinic.query.order_by(Clinic.name).all()

    # 2) Load all doctors/clinical officers dynamically
    doctors = (
        User.query
        .join(Department)
        .filter(Department.name.in_(["Doctor", "Clinical Officer"]))
        .order_by(User.full_name)
        .all()
    )

    if request.method == 'POST':
        patient_id     = request.form.get('patient_id')
        clinic_id      = request.form.get('clinic_id')
        doctor_id      = request.form.get('doctor_id')
        date_str       = request.form.get('appointment_date')
        time_str       = request.form.get('appointment_time')
        reason         = request.form.get('reason')

        # Basic validation
        if not (patient_id and clinic_id and doctor_id and date_str and time_str and reason):
            flash('All fields are required.', 'error')
            return redirect(url_for('appointments_web.schedule_new'))

        try:
            appt_dt = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
            new_appt = Appointment(
                patient_id=int(patient_id),
                clinic_id=int(clinic_id),
                doctor_id=int(doctor_id),
                scheduled_for=appt_dt,
                reason=reason,
                created_by=current_user.id
            )
            db.session.add(new_appt)
            db.session.commit()
            flash('Appointment scheduled successfully!', 'success')
            return redirect(url_for('appointments_web.manage_schedule'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling appointment: {str(e)}', 'error')
            return redirect(url_for('appointments_web.schedule_new'))

    return render_template('schedule_new.html', clinics=clinics, doctors=doctors)


@appointments_web_bp.route('/appointments/patient_search')
@login_required
def patient_search():
    """AJAX endpoint: ?q=string → returns JSON list of {id, reg_no, full_name, phone}"""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])

    results = (
        Patient.query
        .filter(
            db.or_(
                Patient.reg_no.ilike(f"%{q}%"),
                Patient.first_name.ilike(f"%{q}%"),
                Patient.last_name.ilike(f"%{q}%"),
                Patient.phone.ilike(f"%{q}%")
            )
        )
        .limit(10)
        .all()
    )
    out = [
        {
            "id": p.id,
            "reg_no": p.reg_no,
            "full_name": p.full_name,
            "phone": p.phone
        }
        for p in results
    ]
    return jsonify(out)

@appointments_web_bp.route('/appointments/manage')
@login_required
def manage_schedule():
    """
    Display all appointments (past, upcoming, cancelled, etc.) in a grid/table.
    """
    # Eager‐load patient, clinic, and doctor relationships
    all_appointments = (
        Appointment.query
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.clinic),
            joinedload(Appointment.doctor)
        )
        .order_by(Appointment.scheduled_for.asc())
        .all()
    )

    return render_template(
        'manage_schedule.html',
        appointments=all_appointments
    )

@appointments_web_bp.route('/appointments/my')
@login_required
def my_schedules():
    """
    Show only the logged‐in doctor’s appointments.
    """
    my_appointments = Appointment.query \
        .filter_by(doctor_id=current_user.id) \
        .order_by(Appointment.scheduled_for.asc()) \
        .all()

    return render_template('my_schedules.html', my_appointments=my_appointments)

@appointments_web_bp.route('/<int:appt_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appt_id):
    """
    Mark an existing appointment as 'cancelled'.
    """
    from .models import Appointment  # or wherever your model lives
    try:
        appt = Appointment.query.get_or_404(appt_id)
        appt.status = 'cancelled'
        appt.updated_at = datetime.utcnow()
        db.session.commit()
        return ('', 204)  # No content; frontend JS will reload
    except Exception as e:
        db.session.rollback()
        return ('', 500)


@appointments_web_bp.route('/appointments/<int:appt_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_appointment(appt_id):
    """
    GET:  Load existing appointment data into a form for editing.
    POST: Validate and save updates.
    """
    # Fetch the appointment, eager‐load related patient/clinic/doctor
    appt = (
        Appointment.query
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.clinic),
            joinedload(Appointment.doctor)
        )
        .get_or_404(appt_id)
    )

    # Prevent editing if appointment is cancelled or completed
    if appt.status in ('cancelled', 'completed'):
        flash('Cannot edit a cancelled or completed appointment.', 'error')
        return redirect(url_for('appointments_web.manage_schedule'))

    # Load dropdown data
    clinics = Clinic.query.order_by(Clinic.name).all()
    doctors = (
        User.query
        .join(Department)
        .filter(Department.name.in_(["Doctor", "Clinical Officer"]))
        .order_by(User.full_name)
        .all()
    )

    if request.method == 'POST':
        # Read form fields
        clinic_id      = request.form.get('clinic_id')
        doctor_id      = request.form.get('doctor_id')
        date_str       = request.form.get('appointment_date')
        time_str       = request.form.get('appointment_time')
        reason         = request.form.get('reason')

        # Validate required fields
        if not (clinic_id and doctor_id and date_str and time_str and reason):
            flash('All fields are required.', 'error')
            return redirect(url_for('appointments_web.edit_appointment', appt_id=appt_id))

        try:
            # Parse new datetime
            new_dt = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')

            # Update appointment properties
            appt.clinic_id = int(clinic_id)
            appt.doctor_id = int(doctor_id)
            appt.scheduled_for = new_dt
            appt.reason = reason
            appt.updated_at = datetime.utcnow()

            db.session.add(appt)
            db.session.commit()
            flash('Appointment updated successfully!', 'success')
            return redirect(url_for('appointments_web.manage_schedule'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating appointment: {str(e)}', 'error')
            return redirect(url_for('appointments_web.edit_appointment', appt_id=appt_id))

    # On GET, pre-fill form with existing data
    return render_template(
        'edit_appointment.html',
        appointment=appt,
        clinics=clinics,
        doctors=doctors
    )



@appointments_web_bp.route('/appointments/<appointment_id>/delete', methods=['POST'])
@login_required
def delete_appointment(appt_id):
    try:
        appt = Appointment.query.get_or_404(appt_id)
        db.session.delete(appt)
        db.session.commit()
        flash('Appointment deleted successfully.', 'success')
        return redirect(url_for('appointments_web.manage_schedule'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting appointment: {str(e)}', 'error')
        return redirect(url_for('appointments_web.manage_schedule'))
