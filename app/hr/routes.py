# app/hr/routes.py
import json
import uuid
from venv import logger
from flask import abort, render_template, send_file, send_from_directory
from flask import request, redirect, url_for, flash, current_app
from requests import Response
from wtforms import ValidationError
from app.utils.notifications import notification_manager

from app.auth.models import Role, User, user_roles
from app.hr.forms import CandidateForm, DisciplinaryActionForm, InterviewPanelForm, InterviewScoreForm, JobPostingForm
from app.user_management.models import Department, EmployeeBio, EmployeeCertification, EmployeeEducation, EmployeeWorkHistory, EmployeeRelative, BioAttachment
from app import db  # Import the db object from your application
from . import hr_web_bp
import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from .models import (
    AppealStatus, Candidate, DisciplinaryAction, DisciplinaryActionStatus, DisciplinaryActionType, DisciplinaryAppeal, DisciplinaryCase, DisciplinaryCaseStatus, DisciplinaryCaseType, DisciplinaryDocument, DisciplinaryHearing, DisciplinaryInvestigation, DisciplinaryPolicy, DisciplinaryReport, DisciplinarySeverity, EmployeeDeductionAssignment, HearingParticipant, HearingStatus, Interview, InterviewPanel, InterviewPanelMember, InterviewScore, InvestigationEvidence, InvestigationStatus, JobCategory, JobPosting, LeaveAllocation, OfferLetter, PaymentMethod, PayrollPeriod, Payroll, Payslip, EarningType, DeductionType,
    PayslipEarning, PayslipDeduction, PAYEBand, NHIFRate, NSSFRate,
    EmployeePayrollInfo, PayrollAdjustment, PayrollLoan, LoanRepayment, panel_job_postings,
    PayrollReport, DutyShift, DutyRota, DutyAssignment, AttendanceRecord, LeaveRequest, LeaveType, PolicyCategory, SHARate
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from app.utils.calculate_payroll import calculate_payroll
# Staff Management
@hr_web_bp.route('/staff/add')
def staff_add():
    return render_template('hr/staff_add.html')

# app/hr/routes.py
from flask import render_template
from datetime import datetime
from sqlalchemy import func, case

@hr_web_bp.route('/staff/directory')
def staff_directory():
    # Get all staff with their departments and bios
    staff = User.query.options(
        db.joinedload(User.department),
        db.joinedload(User.bio)
    ).order_by(User.full_name.asc()).all()
    
    # For each staff member, load their roles separately
    # Since roles is a dynamic relationship, we need to query them separately
    for employee in staff:
        employee._roles = employee.roles.all()  # Load roles for each user
    
    # Calculate statistics
    total_staff = User.query.count()
    active_staff = User.query.filter_by(is_active=True).count()
    departments_count = Department.query.count()
    
    # Calculate role distribution using a separate query
    role_distribution = db.session.query(
        Role.name.label('role_name'),
        db.func.count(User.id).label('staff_count')
    ).join(user_roles, Role.id == user_roles.c.role_id)\
     .join(User, User.id == user_roles.c.user_id)\
     .group_by(Role.name)\
     .order_by(db.func.count(User.id).desc())\
     .all()
    
    role_labels = [role.role_name for role in role_distribution]
    role_values = [role.staff_count for role in role_distribution]
    
    # Calculate department distribution
    dept_distribution = db.session.query(
        Department.name.label('dept_name'),
        db.func.count(User.id).label('staff_count')
    ).outerjoin(User, Department.id == User.department_id)\
     .group_by(Department.name)\
     .order_by(db.func.count(User.id).desc())\
     .all()
    
    dept_labels = [dept.dept_name for dept in dept_distribution]
    dept_values = [dept.staff_count for dept in dept_distribution]
    
    # Get top roles (most staff)
    top_roles = sorted(role_distribution, key=lambda x: x.staff_count, reverse=True)[:5]
    
    # Count staff with roles
    staff_with_roles = db.session.query(db.func.count(db.distinct(User.id)))\
        .join(user_roles, User.id == user_roles.c.user_id)\
        .scalar() or 0
    
    stats = {
        'total_staff': total_staff,
        'active_staff': active_staff,
        'active_percentage': round((active_staff / total_staff) * 100) if total_staff else 0,
        'departments': departments_count,
        'top_roles': top_roles,
        'total_roles': len(role_labels),
        'staff_with_roles': staff_with_roles
    }
    
    return render_template(
        'staff_directory.html',
        staff=staff,
        stats=stats,
        dept_labels=dept_labels,
        dept_values=dept_values,
        role_labels=role_labels,
        role_values=role_values
    )

@hr_web_bp.route('/staff/<int:user_id>/toggle_payroll_active', methods=['POST'])
@login_required
def toggle_payroll_active(user_id):
    """Toggle employee payroll active status (only in EmployeePayrollInfo)"""
    employee = User.query.get_or_404(user_id)
    
    try:
        # Get the payroll info for this employee
        payroll_info = EmployeePayrollInfo.query.filter_by(employee_id=user_id).first()
        
        if not payroll_info:
            flash(f'No payroll information found for {employee.full_name}.', 'danger')
            return redirect(request.referrer or url_for('hr_web.staff_list'))
        
        # Get current status before toggling
        was_active = payroll_info.is_active
        
        # Toggle the status in EmployeePayrollInfo only
        payroll_info.is_active = not payroll_info.is_active
        db.session.commit()
        
        # Prepare flash message
        if was_active:
            flash(f'Payroll for {employee.full_name} has been deactivated successfully.', 'warning')
        else:
            flash(f'Payroll for {employee.full_name} has been activated successfully.', 'success')
            
        return redirect(request.referrer or url_for('hr_web.staff_list'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error toggling payroll status: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('hr_web.staff_list'))

# Add this route after the staff_add route
@hr_web_bp.route('/staff/edit/<int:user_id>', methods=['GET', 'POST'])
def staff_edit(user_id):
    employee = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Process form submission
        employee.full_name = request.form.get('full_name')
        employee.email = request.form.get('email')
        employee.department_id = request.form.get('department_id')
        employee.position = request.form.get('position')
        employee.is_active = 'is_active' in request.form
        
        try:
            db.session.commit()
            flash('Employee updated successfully!', 'success')
            return redirect(url_for('hr_web.staff_directory'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating employee: {str(e)}', 'danger')
    
    # Fetch departments for dropdown
    departments = Department.query.order_by(Department.name).all()
    
    return render_template(
        'staff_edit.html', 
        employee=employee,
        departments=departments
    )
    
from sqlalchemy.exc import IntegrityError

def generate_staff_no():
    """
    Generates staff numbers like: EMP-2026-000123
    """
    year = datetime.utcnow().year

    # Get last created staff number for the year
    last_staff = (
        EmployeeBio.query
        .filter(EmployeeBio.staff_no.like(f"EMP-{year}-%"))
        .order_by(EmployeeBio.id.desc())
        .first()
    )

    if last_staff and last_staff.staff_no:
        last_seq = int(last_staff.staff_no.split('-')[-1])
        next_seq = last_seq + 1
    else:
        next_seq = 1

    return f"EMP-{year}-{next_seq:06d}"

@hr_web_bp.route('/staff/bio/<int:user_id>', methods=['GET', 'POST'])
def staff_bio(user_id):
    employee = User.query.get_or_404(user_id)
    bio = EmployeeBio.query.filter_by(user_id=user_id).first()

    status = {
        'bio_exists': bool(bio),
        'has_education': bio and bool(bio.educations),
        'has_relatives': bio and bool(bio.relatives),
        'has_work_history': bio and bool(bio.work_histories),
        'has_certifications': bio and bool(bio.certifications),
        'has_attachments': bio and bool(bio.attachments),
    }

    if request.method == 'POST':
        is_new = False

        if not bio:
            bio = EmployeeBio(user_id=user_id)
            is_new = True

        # -------------------
        # Personal Details
        # -------------------
        bio.dob = request.form.get('dob')
        bio.phone = request.form.get('phone')
        bio.address = request.form.get('address')
        bio.city = request.form.get('city')
        bio.state = request.form.get('state')
        bio.postal_code = request.form.get('postal_code')
        bio.country = request.form.get('country')
        bio.nationality = request.form.get('nationality')
        bio.national_id = request.form.get('national_id')
        bio.passport_number = request.form.get('passport_number')
        bio.gender = request.form.get('gender')
        bio.marital_status = request.form.get('marital_status')
        bio.blood_type = request.form.get('blood_type')

        # -------------------
        # Financial Details
        # -------------------
        bio.bank_name = request.form.get('bank_name')
        bio.bank_branch = request.form.get('bank_branch')
        bio.bank_account_number = request.form.get('bank_account_number')
        bio.bank_routing_number = request.form.get('bank_routing_number')
        bio.tax_id = request.form.get('tax_id')
        bio.social_security_number = request.form.get('social_security_number')
        bio.nssf_no = request.form.get('nssf_no')

        # -------------------
        # Emergency & Medical
        # -------------------
        bio.emergency_contact_name = request.form.get('emergency_contact_name')
        bio.emergency_contact_relationship = request.form.get('emergency_contact_relationship')
        bio.emergency_contact_phone = request.form.get('emergency_contact_phone')
        bio.insurance_provider = request.form.get('insurance_provider')
        bio.insurance_number = request.form.get('insurance_number')
        bio.medical_conditions = request.form.get('medical_conditions')
        bio.allergies = request.form.get('allergies')
        bio.place_of_worship = request.form.get('place_of_worship')
        bio.employment_date = request.form.get('employment_date')
        bio.nok_full_name = request.form.get('nok_full_name')
        bio.nok_relationship = request.form.get('nok_relationship')
        bio.nok_phone = request.form.get('nok_phone')
        bio.nok_address = request.form.get('nok_address')

        try:
            if is_new:
                # Generate staff number once
                bio.staff_no = generate_staff_no()
                db.session.add(bio)

            db.session.commit()
            flash('Bio updated successfully!', 'success')

            # -------------------
            # Payroll Info: Create or Update
            # -------------------
            payroll_info = EmployeePayrollInfo.query.filter_by(employee_id=user_id).first()
            if not payroll_info:
                # Create payroll info if missing
                payroll_info = EmployeePayrollInfo(
                    employee_id=user_id,
                    bank_name=bio.bank_name,
                    bank_branch=bio.bank_branch,
                    bank_account=bio.bank_account_number,
                    mpesa_number=bio.phone,  # optional default
                    kra_pin=bio.tax_id,
                    nhif_number=bio.insurance_number,
                    nssf_number=bio.nssf_no,
                    basic_salary=0.0,
                    payment_method=PaymentMethod.BANK_TRANSFER,
                    staff_no=bio.staff_no
                )
                db.session.add(payroll_info)
            else:
                # Update payroll info if needed from bio
                payroll_info.bank_name = bio.bank_name or payroll_info.bank_name
                payroll_info.bank_branch = bio.bank_branch or payroll_info.bank_branch
                payroll_info.bank_account = bio.bank_account_number or payroll_info.bank_account
                payroll_info.mpesa_number = bio.phone or payroll_info.mpesa_number
                payroll_info.kra_pin = bio.tax_id or payroll_info.kra_pin
                payroll_info.nhif_number = bio.insurance_number or payroll_info.nhif_number
                payroll_info.nssf_number = bio.nssf_no or payroll_info.nssf_number

            db.session.commit()
            return redirect(url_for('hr_web.staff_directory'))

        except IntegrityError:
            db.session.rollback()
            flash('Staff number collision detected. Please retry.', 'danger')

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating bio or payroll info: {str(e)}', 'danger')

    return render_template(
        'staff_bio.html',
        employee=employee,
        bio=bio,
        status=status
    )



@hr_web_bp.route('/staff/bio/<int:user_id>/education', methods=['GET', 'POST'])
def manage_education(user_id):
    employee = User.query.get_or_404(user_id)
    bio = EmployeeBio.query.filter_by(user_id=user_id).first_or_404()
    
    if request.method == 'POST':
        education = EmployeeEducation(
            bio_id=bio.id,
            institution=request.form['institution'],
            degree=request.form['degree'],
            certificate_no = request.form.get('certificate_no'),
            field_of_study=request.form.get('field_of_study'),
            start_date=request.form['start_date'],
            end_date=request.form.get('end_date'),
            grade=request.form.get('grade'),
            description=request.form.get('description'),
            is_current='is_current' in request.form
        )
        
        try:
            db.session.add(education)
            db.session.commit()
            flash('Education added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding education: {str(e)}', 'danger')
    
    return render_template(
        'manage_education.html', 
        employee=employee,
        bio=bio
    )

@hr_web_bp.route('/staff/bio/<int:user_id>/relatives', methods=['GET', 'POST'])
def manage_relatives(user_id):
    employee = User.query.get_or_404(user_id)
    bio = EmployeeBio.query.filter_by(user_id=user_id).first_or_404()
    
    if request.method == 'POST':
        relative = EmployeeRelative(
            bio_id=bio.id,
            full_name=request.form['full_name'],
            relationship=request.form['relationship'],
            date_of_birth=request.form.get('date_of_birth'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            occupation=request.form.get('occupation'),
            address=request.form.get('address'),
            is_emergency_contact='is_emergency_contact' in request.form
        )
        
        try:
            db.session.add(relative)
            db.session.commit()
            flash('Relative added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding relative: {str(e)}', 'danger')
    
    return render_template(
        'manage_relatives.html', 
        employee=employee,
        bio=bio
    )

@hr_web_bp.route('/staff/bio/<int:user_id>/work-history', methods=['GET', 'POST'])
def manage_work_history(user_id):
    employee = User.query.get_or_404(user_id)
    bio = EmployeeBio.query.filter_by(user_id=user_id).first_or_404()
    
    if request.method == 'POST':
        work_history = EmployeeWorkHistory(
            bio_id=bio.id,
            company=request.form['company'],
            position=request.form['position'],
            start_date=request.form['start_date'],
            end_date=request.form.get('end_date'),
            responsibilities=request.form.get('responsibilities'),
            achievements=request.form.get('achievements'),
            is_current='is_current' in request.form
        )
        
        try:
            db.session.add(work_history)
            db.session.commit()
            flash('Work history added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding work history: {str(e)}', 'danger')
    
    return render_template(
        'manage_work_history.html', 
        employee=employee,
        bio=bio
    )

@hr_web_bp.route('/staff/bio/<int:user_id>/certifications', methods=['GET', 'POST'])
def manage_certifications(user_id):
    employee = User.query.get_or_404(user_id)
    bio = EmployeeBio.query.filter_by(user_id=user_id).first_or_404()
        # Calculate days remaining for each certification
    today = datetime.utcnow().date()
    for cert in bio.certifications:
        if cert.expiration_date:
            cert.days_remaining = (cert.expiration_date - today).days
        else:
            cert.days_remaining = None

    if request.method == 'POST':
        certification = EmployeeCertification(
            bio_id=bio.id,
            name=request.form['name'],
            issuing_organization=request.form['issuing_organization'],
            issue_date=request.form['issue_date'],
            expiration_date=request.form.get('expiration_date'),
            credential_id=request.form.get('credential_id'),
            credential_url=request.form.get('credential_url')
        )
        
        try:
            db.session.add(certification)
            db.session.commit()
            flash('Certification added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding certification: {str(e)}', 'danger')
    
    return render_template(
        'manage_certifications.html', 
        employee=employee,
        bio=bio,
                datetime=datetime  # Pass datetime module to template

    )

@hr_web_bp.route('/staff/bio/<int:user_id>/attachments', methods=['GET', 'POST'])
def manage_attachments(user_id):
    employee = User.query.get_or_404(user_id)
    bio = EmployeeBio.query.filter_by(user_id=user_id).first_or_404()
    
    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            filename = secure_filename(file.filename)
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            attachment = BioAttachment(
                bio_id=bio.id,
                title=request.form.get('title', filename),
                description=request.form.get('description'),
                file_path=file_path,
                file_type=file.content_type
            )
            
            try:
                db.session.add(attachment)
                db.session.commit()
                flash('Attachment uploaded successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error uploading attachment: {str(e)}', 'danger')
    
    return render_template(
        'manage_attachments.html', 
        employee=employee,
        bio=bio
    )

# Delete handlers for bio components
@hr_web_bp.route('/bio/education/<int:edu_id>/delete', methods=['POST'])
def delete_education(edu_id):
    education = EmployeeEducation.query.get_or_404(edu_id)
    try:
        db.session.delete(education)
        db.session.commit()
        flash('Education record deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting education: {str(e)}', 'danger')
    return redirect(url_for('hr_web.manage_education', user_id=education.bio.user_id))

@hr_web_bp.route('/bio/relative/<int:relative_id>/delete', methods=['POST'])
def delete_relative(relative_id):
    relative = EmployeeRelative.query.get_or_404(relative_id)
    try:
        db.session.delete(relative)
        db.session.commit()
        flash('Relative record deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting relative: {str(e)}', 'danger')
    return redirect(url_for('hr_web.manage_relatives', user_id=relative.bio.user_id))

@hr_web_bp.route('/bio/work-history/<int:work_id>/delete', methods=['POST'])
def delete_work_history(work_id):
    work_history = EmployeeWorkHistory.query.get_or_404(work_id)
    try:
        db.session.delete(work_history)
        db.session.commit()
        flash('Work history deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting work history: {str(e)}', 'danger')
    return redirect(url_for('hr_web.manage_work_history', user_id=work_history.bio.user_id))

@hr_web_bp.route('/bio/certification/<int:cert_id>/delete', methods=['POST'])
def delete_certification(cert_id):
    certification = EmployeeCertification.query.get_or_404(cert_id)
    try:
        db.session.delete(certification)
        db.session.commit()
        flash('Certification deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting certification: {str(e)}', 'danger')
    return redirect(url_for('hr_web.manage_certifications', user_id=certification.bio.user_id))

@hr_web_bp.route('/bio/attachment/<int:attach_id>/delete', methods=['POST'])
def delete_attachment(attach_id):
    attachment = BioAttachment.query.get_or_404(attach_id)
    try:
        # Remove file from filesystem
        if os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)
        db.session.delete(attachment)
        db.session.commit()
        flash('Attachment deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting attachment: {str(e)}', 'danger')
    return redirect(url_for('hr_web.manage_attachments', user_id=attachment.bio.user_id))

@hr_web_bp.route('/staff/profiles/<int:user_id>')  # Correct parameter in path
def staff_profiles(user_id):
    employee = User.query.options(
        db.joinedload(User.department),
        db.joinedload(User.bio).joinedload(EmployeeBio.educations),
        db.joinedload(User.bio).joinedload(EmployeeBio.work_histories),
        db.joinedload(User.bio).joinedload(EmployeeBio.certifications),
        db.joinedload(User.bio).joinedload(EmployeeBio.attachments),
        db.joinedload(User.bio).joinedload(EmployeeBio.relatives)
    ).get_or_404(user_id)
    
    return render_template(
        'staff_profiles.html', 
        employee=employee,
        datetime=datetime
    )





# ====================
# PAYROLL PERIOD ROUTES
# ====================

@hr_web_bp.route('/payroll/periods', methods=['GET', 'POST'])
@login_required
def payroll_periods():
    if request.method == 'POST':
        try:
            data = request.get_json()
            period = PayrollPeriod(
                start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
                pay_date=datetime.strptime(data['pay_date'], '%Y-%m-%d').date(),
                frequency=data['frequency'],
                is_closed=False
            )
            db.session.add(period)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Payroll period created'}), 201
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating payroll period: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 400

    # GET: List all payroll periods
    periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()
    return render_template('payroll_periods.html', periods=periods)

@hr_web_bp.route('/payroll/periods/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def manage_payroll_period(id):
    period = PayrollPeriod.query.get_or_404(id)
    
    if request.method == 'PUT':
        try:
            data = request.get_json()
            
            # Check for required fields
            required_fields = ['start_date', 'end_date', 'pay_date', 'frequency']
            for field in required_fields:
                if field not in data:
                    return jsonify({
                        'success': False, 
                        'message': f'Missing required field: {field}'
                    }), 400
            
            # Check for duplicate period (monthly validation)
            if data.get('frequency') == 'Monthly':
                start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
                year = start_date.year
                month = start_date.month
                
                # Check for duplicate (excluding current period)
                duplicate = PayrollPeriod.query.filter(
                    db.extract('year', PayrollPeriod.start_date) == year,
                    db.extract('month', PayrollPeriod.start_date) == month,
                    PayrollPeriod.frequency == 'Monthly',
                    PayrollPeriod.id != id
                ).first()
                
                if duplicate:
                    return jsonify({
                        'success': False, 
                        'message': f'A monthly payroll period already exists for {start_date.strftime("%B %Y")}'
                    }), 400
            
            # Update period
            period.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            period.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            period.pay_date = datetime.strptime(data['pay_date'], '%Y-%m-%d').date()
            period.frequency = data['frequency']
            period.is_closed = data.get('is_closed', False)
            
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': 'Payroll period updated successfully',
                'id': period.id
            })
            
        except ValueError as e:
            db.session.rollback()
            return jsonify({
                'success': False, 
                'message': 'Invalid date format. Use YYYY-MM-DD'
            }), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False, 
                'message': f'Error updating period: {str(e)}'
            }), 400

    elif request.method == 'DELETE':
        try:
            db.session.delete(period)
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': 'Payroll period deleted successfully'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False, 
                'message': f'Error deleting period: {str(e)}'
            }), 400


# ========================
# EMPLOYEE PAYROLL ROUTE
# ========================
@hr_web_bp.route('/payroll/employee', methods=['GET'])
@login_required
def employee_payroll():
    """
    Display payroll data for selected period.
    Shows processed payrolls and only one 'Create Payroll for All' button if no payroll exists for the period.
    """
    # Get selected period from query parameters
    period_id = request.args.get('period_id', type=int)
    
    # Fetch available periods for dropdown
    periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()
    
    if not period_id and periods:
        period_id = periods[0].id  # default to latest period
    
    selected_period = PayrollPeriod.query.get(period_id) if period_id else None

    # Check if payroll already exists for this period
    payroll_for_period = Payroll.query.filter_by(period_id=period_id).first() if selected_period else None
    create_payroll_button = not bool(payroll_for_period)  # show button if payroll does NOT exist

    # MODIFIED: Fetch only employees with active payroll info and department
    employees = User.query.options(
        db.joinedload(User.payroll_info),
        db.joinedload(User.department)
    ).join(EmployeePayrollInfo, User.id == EmployeePayrollInfo.employee_id)\
     .filter(
        User.is_active == True,
        EmployeePayrollInfo.is_active == True  # Only include employees with active payroll info
    ).all()
    
    # ALTERNATIVE: If you want to include all employees but filter in Python
    # employees = User.query.options(
    #     db.joinedload(User.payroll_info),
    #     db.joinedload(User.department)
    # ).filter_by(is_active=True).all()
    
    payroll_data = []

    for emp in employees:
        info = emp.payroll_info
        
        # Skip if no payroll info (shouldn't happen with the join above, but good for safety)
        if not info:
            continue
            
        payslip = None

        if payroll_for_period:
            payslip = Payslip.query.filter_by(
                employee_id=emp.id, 
                payroll_id=payroll_for_period.id
            ).first()

        if payslip:
            # Calculate allowances total from earnings
            allowances_total = sum(e.amount for e in payslip.earnings)
            
            payroll_data.append({
                'id': emp.id,
                'staff_no': info.staff_no if info else f"EMP{emp.id:04d}",
                'full_name': emp.full_name,
                'department': emp.department,
                'job_title': 'not set',
                'basic_salary': payslip.basic_salary,
                'allowances_total': allowances_total,
                'gross_salary': payslip.gross_earnings,
                'total_deductions': payslip.total_deductions,
                'net_pay': payslip.net_pay,
                'payment_method': payslip.payment_method.value if payslip.payment_method else None,
                'payment_reference': payslip.payment_reference,
                'kra_pin': info.kra_pin if info else '',
                'sha_number': info.sha_number if info else '',
                'nssf_number': info.nssf_number if info else '',
                'bank_account': info.bank_account if info else '',
                'mpesa_number': info.mpesa_number if info else '',
                'has_payroll': True,
                'payslip': payslip,
                'payroll_info': info
            })
        else:
            # No payroll yet for this employee - show basic info
            basic_salary = info.basic_salary if info else 0
            allowances_total = sum([
                info.housing_allowance or 0 if info else 0,
                info.transport_allowance or 0 if info else 0,
                info.other_allowance or 0 if info else 0
            ])
            
            payroll_data.append({
                'id': emp.id,
                'staff_no': info.staff_no if info else f"EMP{emp.id:04d}",
                'full_name': emp.full_name,
                'department': emp.department,
                'job_title': 'not set',
                'basic_salary': basic_salary,
                'allowances_total': allowances_total,
                'gross_salary': basic_salary + allowances_total,
                'total_deductions': 0,
                'net_pay': 0,
                'payment_method': info.payment_method.value if info and info.payment_method else None,
                'kra_pin': info.kra_pin if info else '',
                'sha_number': info.sha_number if info else '',
                'nssf_number': info.nssf_number if info else '',
                'bank_account': info.bank_account if info else '',
                'mpesa_number': info.mpesa_number if info else '',
                'has_payroll': False,
                'payslip': None,
                'payroll_info': info
            })

    return render_template(
        'employee_payroll.html',
        payroll_data=payroll_data,
        periods=periods,
        selected_period_id=period_id,
        create_payroll_button=create_payroll_button,
        payroll_for_period=payroll_for_period
    )
from flask import render_template, make_response, jsonify, request, current_app
import pandas as pd
from io import BytesIO
from datetime import datetime
from sqlalchemy.orm import joinedload
from flask_login import current_user

@hr_web_bp.route('/payroll/<int:payroll_id>/bank-file-preview')
@login_required
def bank_file_preview(payroll_id):
    """Preview bank payment file before downloading"""
    from app.hr.models import Payroll, Payslip
    
    payroll = Payroll.query.get_or_404(payroll_id)
    
    # Get all payslips for this payroll with proper loading
    payslips = Payslip.query.options(
        joinedload(Payslip.employee).joinedload(User.payroll_info)
    ).filter_by(payroll_id=payroll_id).all()
    
    current_app.logger.info(f"Processing {len(payslips)} payslips for payroll {payroll_id}")
    
    payment_data = []
    total_amount = 0
    total_employees = 0
    missing_bank_details = 0
    missing_staff_numbers = 0
    payment_methods = {}
    
    for payslip in payslips:
        info = payslip.employee.payroll_info
        
        # Debug logging
        if not info:
            current_app.logger.warning(f"Employee {payslip.employee.id} has no payroll_info")
        
        # Get staff number with fallback
        staff_no = None
        if info and info.staff_no:
            staff_no = info.staff_no
        else:
            # Try to generate from employee ID
            staff_no = f"EMP{payslip.employee.id:04d}"
            missing_staff_numbers += 1
            current_app.logger.warning(f"Employee {payslip.employee.id} missing staff_no, generated: {staff_no}")
        
        # Check if bank details exist
        has_bank_account = bool(info and info.bank_account and info.bank_name)
        has_mpesa = bool(info and info.mpesa_number)
        
        if not has_bank_account and not has_mpesa:
            missing_bank_details += 1
        
        # Determine payment method
        if payslip.payment_method:
            payment_method = payslip.payment_method.value
        elif info and info.payment_method:
            payment_method = info.payment_method.value
        else:
            payment_method = "Not Set"
        
        # Add to payment methods counter
        payment_methods[payment_method] = payment_methods.get(payment_method, 0) + 1
        
        payment_data.append({
            'employee_id': payslip.employee.id,
            'staff_no': staff_no,
            'name': payslip.employee.full_name,
            'bank_name': info.bank_name if info else 'Not Provided',
            'bank_branch': info.bank_branch if info else '',
            'account_number': info.bank_account if info else '',
            'mpesa_number': info.mpesa_number if info else '',
            'amount': float(payslip.net_pay or 0),
            'payment_method': payment_method,
            'reference': f"SAL-{payroll.period.start_date.strftime('%b-%Y').upper()}-{payslip.employee.id:04d}",
            'has_bank_details': has_bank_account,
            'has_mpesa': has_mpesa,
            'status': 'Ready' if (has_bank_account or has_mpesa) else 'Missing Details'
        })
        
        total_amount += float(payslip.net_pay or 0)
        total_employees += 1
    
    current_app.logger.info(f"Processed {total_employees} employees, {missing_staff_numbers} missing staff numbers, {missing_bank_details} missing bank details")
    
    return render_template(
        'bank_payment_preview.html',
        payroll=payroll,
        payment_data=payment_data,
        total_amount=total_amount,
        total_employees=total_employees,
        missing_bank_details=missing_bank_details,
        missing_staff_numbers=missing_staff_numbers,
        payment_methods=payment_methods,
        now=datetime.now()
    )

@hr_web_bp.route('/payroll/<int:payroll_id>/bank-file/download', methods=['POST'])
@login_required
def generate_bank_file(payroll_id):
    """Generate bank payment file for the payroll"""
    from app.hr.models import Payroll, Payslip
    
    payroll = Payroll.query.get_or_404(payroll_id)
    
    # Get all payslips for this payroll
    payslips = Payslip.query.options(
        joinedload(Payslip.employee).joinedload(User.payroll_info)
    ).filter_by(payroll_id=payroll_id).all()
    
    # Get file format from request
    file_format = request.form.get('format', 'csv')
    
    if file_format == 'excel':
        return generate_excel_file(payroll, payslips)
    else:
        return generate_csv_file(payroll, payslips)

def generate_csv_file(payroll, payslips):
    """Generate CSV file for bank payments"""
    from flask_login import current_user
    
    # Bank-standard CSV format
    csv_data = [
        "Payroll Payment File",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Period: {payroll.period.start_date.strftime('%d/%m/%Y')} to {payroll.period.end_date.strftime('%d/%m/%Y')}",
        f"Pay Date: {payroll.period.pay_date.strftime('%d/%m/%Y')}",
        ""
    ]
    
    # Bank columns (standard format)
    bank_header = [
        "S/N",
        "Employee Name",
        "Employee ID",
        "Staff No",
        "Account Name",
        "Account Number",
        "Bank Code",
        "Branch Code", 
        "Amount",
        "Payment Reference",
        "Payment Method",
        "Status"
    ]
    
    csv_data.append(",".join(bank_header))
    
    total_amount = 0
    sn = 1
    
    for payslip in payslips:
        info = payslip.employee.payroll_info
        
        # Get staff number
        if info and info.staff_no:
            staff_no = info.staff_no
        else:
            staff_no = f"EMP{payslip.employee.id:04d}"
        
        # Bank mapping for Kenyan banks
        bank_codes = {
            'EQUITY BANK': '068',
            'KCB BANK': '011', 
            'COOPERATIVE BANK': '110',
            'STANDARD CHARTERED': '020',
            'BARCLAYS BANK': '030',
            'ABSA BANK': '031',
            'DTB': '063',
            'NCBA': '070',
            'HFC': '041',
            'CFC STANBIC': '032',
            'CITIBANK': '023',
            'JAMII BORA': '051',
            'GUARANTY TRUST BANK': '058',
            'UBA KENYA': '033',
            'VICTORIA COMMERCIAL BANK': '048',
            'MIDDLE EAST BANK': '023',
            'PARAMOUNT UNIVERSAL BANK': '050',
            'AFRICAN BANKING CORPORATION': '035',
            'SBM BANK': '057',
            'M-PESA': 'MPESA'
        }
        
        bank_name = info.bank_name.upper() if info and info.bank_name else ''
        bank_code = bank_codes.get(bank_name, '')
        
        row = [
            str(sn),
            f'"{payslip.employee.full_name}"',
            str(payslip.employee.id),
            f'"{staff_no}"',
            f'"{payslip.employee.full_name}"',
            f'"{info.bank_account if info else ""}"',
            bank_code,
            f'"{info.bank_branch if info else "MAIN"}"',
            f'{payslip.net_pay:,.2f}',
            f'SAL-{payroll.period.start_date.strftime("%Y%m")}-{payslip.employee.id:04d}',
            payslip.payment_method.value if payslip.payment_method else 'BANK',
            'PAID' if payslip.is_paid else 'PENDING'
        ]
        
        csv_data.append(",".join(row))
        total_amount += float(payslip.net_pay or 0)
        sn += 1
    
    # Add summary
    csv_data.extend([
        "",
        "SUMMARY",
        f"Total Employees,{len(payslips)}",
        f"Total Amount,{total_amount:,.2f}",
        f"Currency,KES",
        f"Transaction Date,{payroll.period.pay_date.strftime('%Y-%m-%d')}",
        f"Reference,PAYROLL-{payroll.period.start_date.strftime('%Y%m')}",
        f"Generated By,{current_user.full_name}",
        f"Generated On,{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ])
    
    csv_output = "\n".join(csv_data)
    
    response = make_response(csv_output)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="bank_payment_{payroll.period.start_date.strftime("%Y%m")}_v{datetime.now().strftime("%H%M")}.csv"'
    
    return response

def generate_excel_file(payroll, payslips):
    """Generate Excel file for bank payments with formatting"""
    import pandas as pd
    from io import BytesIO
    from flask_login import current_user
    
    # Prepare data for Excel
    data = []
    total_amount = 0
    
    for payslip in payslips:
        info = payslip.employee.payroll_info
        
        # Get staff number
        if info and info.staff_no:
            staff_no = info.staff_no
        else:
            staff_no = f"EMP{payslip.employee.id:04d}"
        
        data.append({
            'Employee ID': payslip.employee.id,
            'Staff Number': staff_no,
            'Employee Name': payslip.employee.full_name,
            'Bank Name': info.bank_name if info else '',
            'Bank Branch': info.bank_branch if info else '',
            'Account Number': info.bank_account if info else '',
            'M-Pesa Number': info.mpesa_number if info else '',
            'Amount (KES)': float(payslip.net_pay or 0),
            'Payment Method': payslip.payment_method.value if payslip.payment_method else '',
            'Payment Reference': f"SAL-{payroll.period.start_date.strftime('%b-%Y').upper()}-{payslip.employee.id:04d}",
            'Status': 'PAID' if payslip.is_paid else 'PENDING'
        })
        
        total_amount += float(payslip.net_pay or 0)
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Create Excel writer with styling
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Payments', index=False)
        
        # Get workbook and worksheet for styling
        workbook = writer.book
        worksheet = writer.sheets['Payments']
        
        # Apply styles
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        
        # Header style
        header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        
        for col in range(1, len(df.columns) + 1):
            cell = worksheet.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
        
        # Auto-adjust column widths
        for column in df:
            column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
            col_letter = get_column_letter(df.columns.get_loc(column) + 1)
            worksheet.column_dimensions[col_letter].width = min(column_width, 30)
        
        # Add summary sheet
        summary_data = {
            'Metric': ['Total Employees', 'Total Amount (KES)', 'Currency', 'Pay Date', 'Period', 'Generated By', 'Generated On'],
            'Value': [
                len(payslips),
                f"{total_amount:,.2f}",
                'KES',
                payroll.period.pay_date.strftime('%d/%m/%Y'),
                f"{payroll.period.start_date.strftime('%d/%m/%Y')} - {payroll.period.end_date.strftime('%d/%m/%Y')}",
                current_user.full_name,
                datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            ]
        }
        
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Style summary sheet
        summary_ws = writer.sheets['Summary']
        for col in range(1, 3):
            cell = summary_ws.cell(row=1, column=col)
            cell.fill = PatternFill(start_color="3498DB", end_color="3498DB", fill_type="solid")
            cell.font = Font(color="FFFFFF", bold=True)
    
    output.seek(0)
    
    response = make_response(output.read())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename="bank_payment_{payroll.period.start_date.strftime("%Y%m")}.xlsx"'
    
    return response

@hr_web_bp.route('/api/payroll/<int:payroll_id>/payment-stats')
@login_required
def get_payment_stats(payroll_id):
    """Get payment statistics for AJAX updates"""
    from app.hr.models import Payroll, Payslip, User
    
    payroll = Payroll.query.get_or_404(payroll_id)
    
    payslips = Payslip.query.options(
        joinedload(Payslip.employee).joinedload(User.payroll_info)
    ).filter_by(payroll_id=payroll_id).all()
    
    stats = {
        'total_employees': len(payslips),
        'total_amount': float(payroll.total_net or 0),
        'by_payment_method': {},
        'by_status': {'paid': 0, 'pending': 0},
        'by_bank': {}
    }
    
    for payslip in payslips:
        method = payslip.payment_method.value if payslip.payment_method else 'Unknown'
        stats['by_payment_method'][method] = stats['by_payment_method'].get(method, 0) + 1
        
        if payslip.is_paid:
            stats['by_status']['paid'] += 1
        else:
            stats['by_status']['pending'] += 1
        
        info = payslip.employee.payroll_info
        if info and info.bank_name:
            stats['by_bank'][info.bank_name] = stats['by_bank'].get(info.bank_name, 0) + 1
    
    return jsonify(stats)
# ========================
# Update Payroll Info
# ========================
@hr_web_bp.route('/payroll/update/<int:employee_id>', methods=['GET', 'POST'])
@login_required
def update_payroll_info(employee_id):
    employee = User.query.get_or_404(employee_id)
    payroll_info = EmployeePayrollInfo.query.filter_by(employee_id=employee_id).first()

    if request.method == 'POST':
        try:
            # Validate required fields
            basic_salary = request.form.get('basic_salary', type=float)
            if basic_salary is None or basic_salary < 0:
                flash('Basic salary is required and must be non-negative.', 'error')
                return redirect(url_for('hr_web.update_payroll_info', employee_id=employee_id))
            
            nssf_tier = request.form.get('nssf_tier')
            if not nssf_tier or nssf_tier not in ['I', 'II']:
                flash('NSSF Tier is required and must be either I or II.', 'error')
                return redirect(url_for('hr_web.update_payroll_info', employee_id=employee_id))
            
            payment_method = request.form.get('payment_method')
            if payment_method:
                try:
                    payment_method_enum = PaymentMethod(payment_method)
                except ValueError:
                    flash('Invalid payment method selected.', 'error')
                    return redirect(url_for('hr_web.update_payroll_info', employee_id=employee_id))
            else:
                payment_method_enum = PaymentMethod.BANK_TRANSFER

            # Get form data with defaults
            housing_allowance = request.form.get('housing_allowance', type=float) or 0.0
            transport_allowance = request.form.get('transport_allowance', type=float) or 0.0
            other_allowance = request.form.get('other_allowance', type=float) or 0.0
            sha_number = request.form.get('sha_number', '').strip()
            is_spouse_employed = request.form.get('is_spouse_employed') == 'true'
            kra_pin = request.form.get('kra_pin', '').strip()
            nssf_number = request.form.get('nssf_number', '').strip()

            if not payroll_info:
                # Create new payroll info
                payroll_info = EmployeePayrollInfo(
                    employee_id=employee_id,
                    basic_salary=basic_salary,
                    housing_allowance=housing_allowance,
                    transport_allowance=transport_allowance,
                    other_allowance=other_allowance,
                    nssf_tier=nssf_tier,
                    sha_number=sha_number,
                    is_spouse_employed=is_spouse_employed,
                    payment_method=payment_method_enum,
                    kra_pin=kra_pin,
                    nssf_number=nssf_number
                )
                db.session.add(payroll_info)
            else:
                # Update existing payroll info
                payroll_info.basic_salary = basic_salary
                payroll_info.housing_allowance = housing_allowance
                payroll_info.transport_allowance = transport_allowance
                payroll_info.other_allowance = other_allowance
                payroll_info.nssf_tier = nssf_tier
                payroll_info.sha_number = sha_number
                payroll_info.is_spouse_employed = is_spouse_employed
                payroll_info.payment_method = payment_method_enum
                payroll_info.kra_pin = kra_pin
                payroll_info.nssf_number = nssf_number

            db.session.commit()
            flash('Payroll information updated successfully.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating payroll information: {str(e)}', 'error')
            return redirect(url_for('hr_web.update_payroll_info', employee_id=employee_id))

        return redirect(url_for('hr_web.employee_payroll'))

    return render_template(
        'update_payroll_info.html',
        employee=employee,
        payroll_info=payroll_info
    )

from decimal import Decimal, ROUND_HALF_UP
from datetime import date

class StatutoryCalculator:
    """Calculate statutory deductions for Kenya (with SHA replacing NHIF)"""
    
    @staticmethod
    def calculate_sha(gross_salary, period_date=None, is_spouse_employed=False):
        """
        Calculate SHA deduction (Social Health Authority)
        - 2.75% of gross monthly salary
        - Minimum KES 300
        - No maximum cap
        - Pre-tax deduction (deducted before PAYE)
        - Both employed spouses must contribute
        """
        print(f"\n  [SHA CALCULATION]")
        print(f"    Gross Salary: {gross_salary}")
        print(f"    Period Date: {period_date}")
        print(f"    Is Spouse Employed: {is_spouse_employed}")
        
        if period_date is None:
            period_date = date.today()
        
        # Get the applicable SHA rate (most recent effective date)
        sha_rate = SHARate.query.filter(
            SHARate.effective_date <= period_date
        ).order_by(SHARate.effective_date.desc()).first()
        
        if sha_rate:
            print(f"    SHA Rate Found: {sha_rate.rate}%")
            print(f"    Minimum Amount: {sha_rate.minimum_amount}")
            
            # Calculate SHA as 2.75% of gross salary
            sha_percentage = Decimal(str(sha_rate.rate)) / Decimal('100')
            calculated_amount = Decimal(str(gross_salary)) * sha_percentage
            
            # Round to 2 decimal places
            calculated_amount = calculated_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            print(f"    Calculated Amount (2.75% of {gross_salary}): {calculated_amount}")
            
            # Apply minimum amount (KES 300)
            final_amount = max(calculated_amount, Decimal(str(sha_rate.minimum_amount)))
            
            print(f"    Final SHA Amount (after minimum check): {final_amount}")
            
            return final_amount
        
        print(f"    WARNING: No SHA rates found! Using default (2.75%, min 300)")
        # Default calculation
        sha_percentage = Decimal('0.0275')  # 2.75%
        calculated_amount = Decimal(str(gross_salary)) * sha_percentage
        calculated_amount = calculated_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        final_amount = max(calculated_amount, Decimal('300'))
        
        return final_amount
    
    @staticmethod
    def calculate_nssf_employee(gross_salary, nssf_tier='II', period_date=None):
        """Calculate NSSF employee contribution"""
        print(f"\n  [NSSF CALCULATION]")
        print(f"    Gross Salary: {gross_salary}")
        print(f"    NSSF Tier: {nssf_tier}")
        print(f"    Period Date: {period_date}")
        
        if period_date is None:
            period_date = date.today()
        
        # Get the applicable NSSF rate
        nssf_rates = NSSFRate.query.filter_by(tier=nssf_tier).filter(
            NSSFRate.effective_date <= period_date
        ).order_by(NSSFRate.effective_date.desc()).all()
        
        print(f"    Found {len(nssf_rates)} NSSF rates for tier {nssf_tier}")
        
        if nssf_rates:
            nssf_rate = nssf_rates[0]  # Get the most recent
            print(f"    Using rate: Tier {nssf_rate.tier}")
            print(f"    Lower Bound: {nssf_rate.lower_bound}")
            print(f"    Upper Bound: {nssf_rate.upper_bound}")
            print(f"    Employee Rate: {nssf_rate.employee_rate}%")
            print(f"    Employer Rate: {nssf_rate.employer_rate}%")
            
            # Determine pensionable earnings (capped at KES 216,000 for Tier II)
            if nssf_rate.upper_bound:
                pensionable_earnings = min(Decimal(str(gross_salary)), Decimal(str(nssf_rate.upper_bound)))
            else:
                pensionable_earnings = Decimal(str(gross_salary))
            
            print(f"    Pensionable Earnings: {pensionable_earnings}")
            
            # Calculate contribution (6% for Tier II)
            employee_rate = Decimal(str(nssf_rate.employee_rate)) / Decimal('100')
            result = pensionable_earnings * employee_rate
            result = result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            print(f"    Employee Contribution (6%): {result}")
            return result
        
        print(f"    WARNING: No NSSF rates found for tier {nssf_tier}! Using default (6% of pensionable earnings)")
        # Default calculation (6% of pensionable earnings, capped at 216,000)
        pensionable_earnings = min(Decimal(str(gross_salary)), Decimal('216000'))
        employee_rate = Decimal('0.06')  # 6%
        result = pensionable_earnings * employee_rate
        result = result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        return result
    
    @staticmethod
    def calculate_paye(gross_salary, nssf_employee, sha_amount, personal_relief=Decimal('2400'), period_date=None):
        """
        Calculate PAYE tax
        Note: SHA is deducted BEFORE calculating taxable income (pre-tax deduction)
        """
        print(f"\n  [PAYE CALCULATION]")
        print(f"    Gross Salary: {gross_salary}")
        print(f"    NSSF Employee: {nssf_employee}")
        print(f"    SHA Amount: {sha_amount}")
        print(f"    Personal Relief: {personal_relief}")
        print(f"    Note: SHA is pre-tax deduction")
        
        if period_date is None:
            period_date = date.today()
        
        # Get applicable PAYE bands
        paye_bands = PAYEBand.query.filter(
            PAYEBand.effective_date <= period_date
        ).order_by(PAYEBand.effective_date.desc()).all()
        
        print(f"    Found {len(paye_bands)} PAYE bands")
        
        if not paye_bands:
            print(f"    WARNING: No PAYE bands configured! Using default bands (Kenya 2024).")
            # Fallback to default bands (Kenya 2024)
            paye_bands = [
                type('obj', (object,), {
                    'lower_bound': Decimal('0'),
                    'upper_bound': Decimal('24000'),
                    'rate': Decimal('10'),
                    'deduction_amount': Decimal('0')
                }),
                type('obj', (object,), {
                    'lower_bound': Decimal('24001'),
                    'upper_bound': Decimal('32333'),
                    'rate': Decimal('25'),
                    'deduction_amount': Decimal('2400')
                }),
                type('obj', (object,), {
                    'lower_bound': Decimal('32334'),
                    'upper_bound': Decimal('500000'),
                    'rate': Decimal('30'),
                    'deduction_amount': Decimal('2400')
                }),
                type('obj', (object,), {
                    'lower_bound': Decimal('500001'),
                    'upper_bound': Decimal('800000'),
                    'rate': Decimal('32.5'),
                    'deduction_amount': Decimal('2400')
                }),
                type('obj', (object,), {
                    'lower_bound': Decimal('800001'),
                    'upper_bound': None,
                    'rate': Decimal('35'),
                    'deduction_amount': Decimal('2400')
                })
            ]
        
        # Print bands for debugging
        for i, band in enumerate(paye_bands):
            print(f"    Band {i+1}: {band.lower_bound} - {band.upper_bound or '∞'}: {band.rate}%")
        
        # Calculate taxable income (SHA is pre-tax deduction)
        taxable_income = Decimal(str(gross_salary)) - nssf_employee - sha_amount
        print(f"    Taxable Income (Gross - NSSF - SHA): {taxable_income}")
        
        # Apply PAYE bands
        tax_payable = Decimal('0')
        previous_limit = Decimal('0')
        
        for band in paye_bands:
            if taxable_income > Decimal(str(band.lower_bound)):
                # Determine the upper limit for this band
                if band.upper_bound:
                    band_limit = Decimal(str(band.upper_bound))
                else:
                    band_limit = taxable_income
                
                # Calculate amount in this band
                band_amount = min(taxable_income, band_limit) - max(previous_limit, Decimal(str(band.lower_bound)))
                if band_amount > 0:
                    band_tax = band_amount * (Decimal(str(band.rate)) / Decimal('100'))
                    band_tax = band_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    tax_payable += band_tax
                    print(f"    Band {band.lower_bound}-{band.upper_bound or '∞'}: {band_amount} × {band.rate}% = {band_tax}")
                
                previous_limit = band_limit
            else:
                break
        
        print(f"    Tax before relief: {tax_payable}")
        
        # Apply personal relief (KES 2,400 monthly)
        tax_payable = max(tax_payable - personal_relief, Decimal('0'))
        tax_payable = tax_payable.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        print(f"    Tax after relief (KES 2,400): {tax_payable}")
        
        return tax_payable
    
    @staticmethod
    def calculate_all_statutory(gross_salary, nssf_tier='II', is_spouse_employed=False, period_date=None):
        """Calculate all statutory deductions at once"""
        print(f"\n=== STATUTORY CALCULATION SUMMARY ===")
        print(f"Gross Salary: {gross_salary}")
        print(f"NSSF Tier: {nssf_tier}")
        print(f"Is Spouse Employed: {is_spouse_employed}")
        print(f"Period Date: {period_date}")
        
        # Calculate SHA (2.75% of gross, min KES 300)
        sha = StatutoryCalculator.calculate_sha(gross_salary, period_date, is_spouse_employed)
        
        # Calculate NSSF Employee (6% of pensionable earnings, capped at 216,000)
        nssf_employee = StatutoryCalculator.calculate_nssf_employee(gross_salary, nssf_tier, period_date)
        
        # Calculate PAYE (after deducting NSSF and SHA)
        paye = StatutoryCalculator.calculate_paye(gross_salary, nssf_employee, sha, period_date=period_date)
        
        total_statutory = sha + nssf_employee + paye
        
        print(f"\n=== FINAL STATUTORY TOTALS ===")
        print(f"SHA (2.75% of gross, min 300): {sha}")
        print(f"NSSF Employee (6% of pensionable): {nssf_employee}")
        print(f"PAYE (after deductions): {paye}")
        print(f"TOTAL STATUTORY DEDUCTIONS: {total_statutory}")
        print(f"Net Salary (Gross - Total Deductions): {gross_salary - total_statutory}")
        
        return {
            'sha': sha,
            'nssf_employee': nssf_employee,
            'paye': paye,
            'total_statutory': total_statutory
        }

@hr_web_bp.route('/payroll/create/<int:employee_id>/<int:period_id>', methods=['POST'])
@login_required
def create_payroll(employee_id, period_id):
    """
    Create a payslip for an employee or for all employees if employee_id=0.
    Only one Payroll exists per period.
    """
    print(f"\n=== DEBUG: Starting payroll creation ===")
    print(f"Employee ID: {employee_id}")
    print(f"Period ID: {period_id}")
    
    period = PayrollPeriod.query.get_or_404(period_id)
    print(f"Period found: {period.start_date} to {period.end_date}")
    
    # Ensure payroll exists for the period
    payroll = Payroll.query.filter_by(period_id=period.id).first()
    if not payroll:
        print("No existing payroll found for period, creating new one...")
        payroll = Payroll(period_id=period.id, status='Draft', processed_by=current_user.id)
        db.session.add(payroll)
        db.session.commit()
        print(f"Created new payroll with ID: {payroll.id}")
    else:
        print(f"Using existing payroll with ID: {payroll.id}")
    
    # Function to get or create earning type safely
    def get_or_create_earning_type(code, name, description, is_taxable=True):
        # First try to find by code (unique)
        earning_type = EarningType.query.filter_by(code=code).first()
        if not earning_type:
            # If not found by code, try by name (also unique)
            earning_type = EarningType.query.filter_by(name=name).first()
            if not earning_type:
                # Create new if doesn't exist
                earning_type = EarningType(
                    name=name,
                    code=code,
                    description=description,
                    is_taxable=is_taxable,
                    is_statutory=False,
                    is_recurring=True
                )
                db.session.add(earning_type)
                print(f"Created new earning type: {name} ({code})")
            else:
                print(f"Found existing earning type by name: {name}")
        else:
            print(f"Found existing earning type by code: {code}")
        return earning_type
    
    # Function to get or create deduction type safely
    def get_or_create_deduction_type(code, name, description, is_statutory=False, is_voluntary=False):
        deduction_type = DeductionType.query.filter_by(code=code).first()
        if not deduction_type:
            deduction_type = DeductionType.query.filter_by(name=name).first()
            if not deduction_type:
                deduction_type = DeductionType(
                    name=name,
                    code=code,
                    description=description,
                    is_statutory=is_statutory,
                    is_voluntary=is_voluntary
                )
                db.session.add(deduction_type)
                print(f"Created new deduction type: {name} ({code})")
            else:
                print(f"Found existing deduction type by name: {name}")
        else:
            print(f"Found existing deduction type by code: {code}")
        return deduction_type
    
    if employee_id == 0:
        # Create payroll for all employees
        print("Creating payroll for ALL employees...")
        employees = User.query.options(db.joinedload(User.payroll_info)).filter_by(is_active=True).all()
        print(f"Total active employees: {len(employees)}")
        
        created_count = 0
        for emp in employees:
            info = emp.payroll_info
            if not info:
                print(f"Skipping employee {emp.id} - {emp.full_name}: No payroll info")
                continue
            
            # Prevent duplicate payslips
            existing_payslip = Payslip.query.filter_by(employee_id=emp.id, payroll_id=payroll.id).first()
            if existing_payslip:
                print(f"Skipping employee {emp.id} - {emp.full_name}: Payslip already exists")
                continue
            
            print(f"\nProcessing employee {emp.id} - {emp.full_name}:")
            
            # Calculate gross salary
            gross_salary = info.calculate_gross_salary()
            print(f"  Basic Salary: {info.basic_salary}")
            print(f"  Housing Allowance: {info.housing_allowance}")
            print(f"  Transport Allowance: {info.transport_allowance}")
            print(f"  Other Allowance: {info.other_allowance}")
            print(f"  Gross Salary: {gross_salary}")
            
            try:
                # Calculate statutory deductions (SHA instead of NHIF)
                statutory = StatutoryCalculator.calculate_all_statutory(
                    gross_salary=gross_salary,
                    nssf_tier=info.nssf_tier,
                    is_spouse_employed=info.is_spouse_employed,
                    period_date=period.end_date
                )
                
                # Create payslip
                payslip = Payslip(
                    payroll_id=payroll.id,
                    employee_id=emp.id,
                    basic_salary=info.basic_salary,
                    gross_earnings=gross_salary,
                    total_deductions=statutory['total_statutory'],
                    net_pay=gross_salary - statutory['total_statutory'],
                    payment_method=info.payment_method,
                    is_paid=False
                )
                db.session.add(payslip)
                db.session.flush()  # Get payslip ID
                
                # Get or create deduction types
                sha_type = get_or_create_deduction_type(
                    code='SHA',
                    name='SHA Contribution',
                    description='Social Health Authority Contribution (2.75% of gross, min KES 300)',
                    is_statutory=True
                )
                
                paye_type = get_or_create_deduction_type(
                    code='PAYE',
                    name='PAYE Tax',
                    description='Pay As You Earn Tax',
                    is_statutory=True
                )
                
                nssf_type = get_or_create_deduction_type(
                    code='NSSF',
                    name='NSSF Employee Contribution',
                    description='National Social Security Fund (6% of pensionable earnings)',
                    is_statutory=True
                )
                
                # Add statutory deductions to payslip
                if statutory['sha'] > 0:
                    payslip.deductions.append(PayslipDeduction(
                        deduction_type_id=sha_type.id,
                        amount=statutory['sha'],
                        description=f'SHA Contribution (2.75% of gross, min 300)'
                    ))
                
                if statutory['paye'] > 0:
                    payslip.deductions.append(PayslipDeduction(
                        deduction_type_id=paye_type.id,
                        amount=statutory['paye'],
                        description=f'PAYE calculated on {period.end_date}'
                    ))
                
                if statutory['nssf_employee'] > 0:
                    payslip.deductions.append(PayslipDeduction(
                        deduction_type_id=nssf_type.id,
                        amount=statutory['nssf_employee'],
                        description=f'NSSF Tier {info.nssf_tier} Employee Contribution (6%)'
                    ))
                

                
                # Add allowances as earnings
                if info.housing_allowance > 0:
                    housing_type = get_or_create_earning_type(
                        code='HOUSE_ALLOW',
                        name='Housing Allowance',
                        description='Monthly housing allowance',
                        is_taxable=True
                    )
                    
                    payslip.earnings.append(PayslipEarning(
                        earning_type_id=housing_type.id,
                        amount=info.housing_allowance,
                        description='Monthly housing allowance'
                    ))
                
                # Add transport allowance
                if info.transport_allowance > 0:
                    transport_type = get_or_create_earning_type(
                        code='TRANS_ALLOW',
                        name='Transport Allowance',
                        description='Monthly transport allowance',
                        is_taxable=True
                    )
                    
                    payslip.earnings.append(PayslipEarning(
                        earning_type_id=transport_type.id,
                        amount=info.transport_allowance,
                        description='Monthly transport allowance'
                    ))
                
                # Add other allowance
                if info.other_allowance > 0:
                    other_type = get_or_create_earning_type(
                        code='OTHER_ALLOW',
                        name='Other Allowance',
                        description='Other allowances',
                        is_taxable=True
                    )
                    
                    payslip.earnings.append(PayslipEarning(
                        earning_type_id=other_type.id,
                        amount=info.other_allowance,
                        description='Other allowances'
                    ))
                
                # Calculate totals
                payslip.calculate_totals()
                
                created_count += 1
                print(f"    Created payslip with SHA deductions")
                
            except Exception as e:
                print(f"    ERROR creating payslip: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        try:
            db.session.commit()
            print(f"\n=== DEBUG: Successfully created {created_count} payslips ===")
            flash(f'Payroll created for {created_count} employees.', 'success')
        except Exception as e:
            db.session.rollback()
            print(f"\n=== DEBUG: Commit failed: {str(e)} ===")
            import traceback
            traceback.print_exc()
            flash(f'Error creating payroll: {str(e)}', 'error')
        
        return redirect(url_for('hr_web.employee_payroll', period_id=period.id))
    else:
        # Create payroll for single employee
        emp = User.query.get_or_404(employee_id)
        info = emp.payroll_info
        
        if not info:
            flash('Employee does not have payroll information.', 'error')
            return redirect(url_for('hr_web.employee_payroll'))
        
        # Check for existing payslip
        existing_payslip = Payslip.query.filter_by(
            employee_id=emp.id, 
            payroll_id=payroll.id
        ).first()
        
        if existing_payslip:
            flash('Payslip for this employee already exists for this period.', 'warning')
            return redirect(url_for('hr_web.employee_payroll', period_id=period.id))
        
        try:
            # Calculate gross salary
            gross_salary = info.calculate_gross_salary()
            
            # Calculate statutory deductions
            statutory = StatutoryCalculator.calculate_all_statutory(
                gross_salary=gross_salary,
                nssf_tier=info.nssf_tier,
                is_spouse_employed=info.is_spouse_employed,
                period_date=period.end_date
            )
            
            # Create payslip
            payslip = Payslip(
                payroll_id=payroll.id,
                employee_id=emp.id,
                basic_salary=info.basic_salary,
                gross_earnings=gross_salary,
                total_deductions=statutory['total_statutory'],
                net_pay=gross_salary - statutory['total_statutory'],
                payment_method=info.payment_method,
                is_paid=False
            )
            db.session.add(payslip)
            db.session.commit()
            
            flash(f'Payslip created for {emp.full_name}.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating payslip: {str(e)}', 'error')
        
        return redirect(url_for('hr_web.employee_payroll', period_id=period.id))




# ========================
# View Employee Payroll
# ========================
@hr_web_bp.route('/payroll/view/<int:employee_id>')
@login_required
def view_employee_payroll(employee_id):
    employee = User.query.get_or_404(employee_id)
    payslips = Payslip.query.filter_by(employee_id=employee_id).order_by(Payslip.paid_at.desc()).all()
    return render_template(
        'view_employee_payroll.html',
        employee=employee,
        payslips=payslips
    )


# ========================
# PAYROLL PROCESSING ROUTES
# ========================

@hr_web_bp.route('/payroll/salary', methods=['GET', 'POST'])
@login_required
def salary_processing():
    if request.method == 'POST':
        try:
            data = request.get_json()
            period_id = data['period_id']
            
            # Check if there's already a "Paid" payroll for this period
            existing_paid = Payroll.query.filter_by(
                period_id=period_id, 
                status='Paid'
            ).first()
            
            if existing_paid:
                return jsonify({
                    'success': False,
                    'message': f'Payroll already PAID for this period (ID: #{existing_paid.id}). Cannot re-process paid payrolls.'
                }), 400
            
            # Get existing payroll for this period
            payroll = Payroll.query.filter_by(period_id=period_id).first()
            
            if not payroll:
                return jsonify({
                    'success': False,
                    'message': 'No payroll found for this period. Please create payroll first.'
                }), 400
            
            # Recalculate totals from existing payslips
            payslips = Payslip.query.filter_by(payroll_id=payroll.id).all()
            
            if not payslips:
                return jsonify({
                    'success': False,
                    'message': 'No payslips found for this payroll.'
                }), 400
            
            # Calculate new totals
            total_gross = Decimal('0')
            total_deductions = Decimal('0')
            total_net = Decimal('0')
            
            for payslip in payslips:
                # Recalculate payslip totals
                payslip.calculate_totals()
                
                total_gross += payslip.gross_earnings or Decimal('0')
                total_deductions += payslip.total_deductions or Decimal('0')
                total_net += payslip.net_pay or Decimal('0')
            
            # Update payroll totals
            payroll.total_gross = total_gross
            payroll.total_deductions = total_deductions
            payroll.total_net = total_net
            payroll.status = 'Processed'
            payroll.processed_at = datetime.utcnow()
            payroll.processed_by = current_user.id
            
            db.session.commit()
            
            current_app.logger.info(f"Payroll totals recalculated: ID #{payroll.id}")
            
            return jsonify({
                'success': True,
                'payroll': {
                    'id': payroll.id,
                    'period_id': period_id,
                    'total_gross': float(payroll.total_gross),
                    'total_deductions': float(payroll.total_deductions),
                    'total_net': float(payroll.total_net),
                    'employee_count': len(payslips),
                    'status': payroll.status,
                    'processed_at': payroll.processed_at.strftime('%Y-%m-%d %H:%M:%S')
                },
                'message': f'Payroll totals recalculated for {len(payslips)} employees'
            }), 200
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Payroll processing error: {str(e)}", exc_info=True)
            return jsonify({
                'success': False, 
                'message': f'Payroll processing failed: {str(e)}'
            }), 500
    
    # ... rest of your GET code remains the same ...

    # GET: Show form for payroll processing
    # Get periods that haven't been processed OR have processed payrolls but are not paid yet
    from sqlalchemy import or_
    
    # Get all periods
    all_periods = PayrollPeriod.query.filter(
        
    ).order_by(PayrollPeriod.start_date.desc()).all()
    
    # Filter periods to show only those that haven't been paid
    unpaid_periods = []
    for period in all_periods:
        # Check if this period has any payroll
        period_payrolls = Payroll.query.filter_by(period_id=period.id).all()
        
        if not period_payrolls:
            # No payroll exists for this period - show it
            unpaid_periods.append(period)
        else:
            # Check if all payrolls for this period are NOT paid
            has_paid_payroll = False
            for payroll in period_payrolls:
                if payroll.status == 'Paid':
                    has_paid_payroll = True
                    break
            
            if not has_paid_payroll:
                # Period has payrolls but none are paid - show it
                unpaid_periods.append(period)
            else:
                # Period has at least one paid payroll - don't show it
                pass
    
    # Alternative: Using SQLAlchemy query with subquery (more efficient)
    """
    unpaid_periods = PayrollPeriod.query.filter(
        PayrollPeriod.end_date <= date.today()
    ).outerjoin(
        Payroll,
        Payroll.period_id == PayrollPeriod.id
    ).group_by(
        PayrollPeriod.id
    ).having(
        db.func.count(Payroll.id) == 0  # No payrolls at all
        | db.func.sum(
            db.case(
                (Payroll.status == 'Paid', 1),
                else_=0
            )
        ) == 0  # No paid payrolls
    ).order_by(
        PayrollPeriod.start_date.desc()
    ).all()
    """
    
    # Get active employee count
    active_employees = User.query.filter_by(is_active=True).count()
    
    # Get recent payrolls with period relationship
    recent_payrolls = Payroll.query.options(db.joinedload(Payroll.period))\
        .order_by(Payroll.processed_at.desc())\
        .limit(5)\
        .all()
    draft_periods = PayrollPeriod.query.outerjoin(
        Payroll, Payroll.period_id == PayrollPeriod.id
    ).filter(
        or_(
            Payroll.id == None,               # no payroll at all
            Payroll.status == 'Draft'          # payroll exists but not yet processed
        )
    ).order_by(PayrollPeriod.start_date.desc()).all()

    # Build period data for the frontend (including payroll status)
    period_data = []
    for period in draft_periods:
        payroll = Payroll.query.filter_by(period_id=period.id).first()
        status = 'Draft' if payroll else 'Ready for Processing'
        period_data.append({
            'id': period.id,
            'start_date': period.start_date.strftime('%d %b %Y'),
            'end_date': period.end_date.strftime('%d %b %Y'),
            'pay_date': period.pay_date.strftime('%d %b %Y'),
            'frequency': period.frequency.value,
            'status': status,
            'has_payroll': payroll is not None,
            'payroll_id': payroll.id if payroll else None
        })

    # Get active employee count
    active_employees = User.query.filter_by(is_active=True).count()

    # Get recent payrolls (all, for history display)
    recent_payrolls = Payroll.query.options(db.joinedload(Payroll.period))\
        .order_by(Payroll.processed_at.desc())\
        .limit(5)\
        .all()

    return render_template(
        'process_payroll.html',
        periods=draft_periods,
        period_data=json.dumps(period_data),
        active_employees=active_employees,
        recent_payrolls=recent_payrolls,
        now=datetime.now()
    )



@hr_web_bp.route('/payroll/<int:payroll_id>/approve/now', methods=['POST'])
@login_required
def approve_payroll(payroll_id):
    """Approve processed payroll"""
    try:
        payroll = Payroll.query.get_or_404(payroll_id)
        
        if payroll.status not in ['Processed', 'Draft']:
            return jsonify({
                'success': False,
                'message': f'Payroll cannot be approved from status: {payroll.status}'
            }), 400
        
        # Update payroll status
        payroll.status = 'Approved'
        payroll.approved_by = current_user.id
        payroll.approved_at = datetime.utcnow()
        
        # Update all payslips status
        for payslip in payroll.payslips:
            payslip.status = 'Approved'
        
        db.session.commit()
        
        # Log the approval
        current_app.logger.info(f"Payroll approved: ID #{payroll.id} by User {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Payroll approved successfully',
            'payroll': {
                'id': payroll.id,
                'status': payroll.status,
                'approved_at': payroll.approved_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Payroll approval error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

import threading
import tempfile
import os
from weasyprint import HTML

@hr_web_bp.route('/payroll/<int:payroll_id>/mark-paid', methods=['POST'])
@login_required
def mark_payroll_batch_paid(payroll_id):
    """Mark approved payroll as paid and record loan repayments"""
    try:
        payroll = Payroll.query.get_or_404(payroll_id)
        
        if payroll.status != 'Approved':
            return jsonify({
                'success': False,
                'message': f'Payroll must be Approved before marking as Paid. Current status: {payroll.status}'
            }), 400
        
        # Get loan deduction type
        loan_deduction_type = DeductionType.query.filter_by(code='LOAN_REPAYMENT').first()
        
        # Update payroll status
        payroll.status = 'Paid'
        payroll.paid_at = datetime.utcnow()
        payroll.paid_by = current_user.id
        
        # Track total loan repayments
        total_loan_repayments = Decimal('0')
        loan_repayments_count = 0
        
        # Process each payslip
        for payslip in payroll.payslips:
            # Update payslip status
            payslip.paid_at = datetime.utcnow()
            payslip.is_paid = True
            
            # Generate payment reference
            payslip.payment_reference = f"PAY-{payroll.id}-{payslip.id}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
            
            # Find and process loan deductions for this payslip
            if loan_deduction_type:
                loan_deductions = PayslipDeduction.query.filter_by(
                    payslip_id=payslip.id,
                    deduction_type_id=loan_deduction_type.id
                ).all()
                
                for loan_deduction in loan_deductions:
                    # Get active loans for this employee
                    active_loans = PayrollLoan.query.filter(
                        PayrollLoan.employee_id == payslip.employee_id,
                        PayrollLoan.is_active == True,
                        PayrollLoan.balance > 0
                    ).order_by(PayrollLoan.created_at.asc()).all()
                    
                    if not active_loans:
                        continue
                    
                    # Distribute loan deduction among active loans (oldest first)
                    remaining_deduction = loan_deduction.amount
                    
                    for loan in active_loans:
                        if remaining_deduction <= 0:
                            break
                        
                        # Calculate how much to deduct from this loan
                        deduction_amount = min(remaining_deduction, loan.balance)
                        
                        if deduction_amount > 0:
                            # Create loan repayment record
                            repayment = LoanRepayment(
                                loan_id=loan.id,
                                amount=deduction_amount,
                                payment_date=datetime.utcnow().date(),
                                payslip_id=payslip.id,
                                description=f"Loan repayment via payroll #{payroll.id}",
                                created_by=current_user.id
                            )
                            db.session.add(repayment)
                            
                            # Update loan balance
                            loan.balance -= deduction_amount
                            
                            # Update EmployeeDeductionAssignment balance
                            assignment = EmployeeDeductionAssignment.query.filter_by(
                                employee_id=payslip.employee_id,
                                deduction_type_id=loan_deduction_type.id,
                                is_active=True
                            ).first()
                            
                            if assignment:
                                assignment.balance = loan.balance
                            
                            # Check if loan is fully paid
                            if loan.balance <= 0:
                                loan.is_active = False
                                loan.end_date = datetime.utcnow().date()
                                
                                # Also deactivate the deduction assignment
                                if assignment:
                                    assignment.is_active = False
                                    assignment.end_date = datetime.utcnow().date()
                            
                            # Update tracking
                            remaining_deduction -= deduction_amount
                            total_loan_repayments += deduction_amount
                            loan_repayments_count += 1
        
        db.session.commit()
        
        # Log the payment
        current_app.logger.info(
            f"Payroll marked as paid: ID #{payroll.id} by User {current_user.id}. "
            f"Processed {loan_repayments_count} loan repayments totaling KES {total_loan_repayments}."
        )
        
        return jsonify({
            'success': True,
            'message': f'Payroll marked as paid successfully. Processed {loan_repayments_count} loan repayments.',
            'payroll': {
                'id': payroll.id,
                'status': payroll.status,
                'paid_at': payroll.paid_at.strftime('%Y-%m-%d %H:%M:%S'),
                'payslips_count': len(payroll.payslips),
                'loan_repayments': loan_repayments_count,
                'total_loan_repayments': str(total_loan_repayments)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking payroll as paid: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to mark payroll as paid: {str(e)}'
        }), 500

def send_payslip_emails_background(app, payroll_id, user_id):
    """Background function to send payslip emails with PDF attachments"""
    with app.app_context():
        try:
            from app.utils.notifications import notification_manager
            from sqlalchemy.orm import joinedload
            
            notification_manager.init_app(app)
            
            # Get payroll with all related data
            payroll = Payroll.query.options(
                joinedload(Payroll.period),
                joinedload(Payroll.payslips).joinedload(Payslip.employee).joinedload(User.payroll_info)
            ).get(payroll_id)
            
            if not payroll:
                app.logger.error(f"Payroll {payroll_id} not found for email sending")
                return
            
            emails_sent = 0
            emails_failed = 0
            
            # Create temporary directory for PDFs
            temp_dir = tempfile.mkdtemp(prefix='payslips_')
            app.logger.info(f"Created temp directory: {temp_dir}")
            
            for payslip in payroll.payslips:
                if payslip.employee and payslip.employee.email:
                    try:
                        # Generate PDF using simplified function without current_user
                        pdf_path = generate_payslip_pdf_safe(payslip, temp_dir)
                        
                        if pdf_path and os.path.exists(pdf_path):
                            # Send email with PDF attachment
                            email_sent = send_payslip_email_with_pdf(
                                notification_manager,
                                payslip,
                                payroll,
                                pdf_path
                            )
                            
                            if email_sent:
                                emails_sent += 1
                                app.logger.info(f"Payslip email with PDF sent to {payslip.employee.email}")
                            else:
                                emails_failed += 1
                                app.logger.error(f"Failed to send email to {payslip.employee.email}")
                            
                            # Clean up PDF file after sending
                            try:
                                os.remove(pdf_path)
                            except:
                                pass
                        else:
                            emails_failed += 1
                            app.logger.error(f"Failed to generate PDF for payslip #{payslip.id}")
                            
                    except Exception as e:
                        emails_failed += 1
                        app.logger.error(f"Error processing payslip #{payslip.id}: {str(e)}")
                        import traceback
                        app.logger.error(traceback.format_exc())
            
            # Clean up temp directory
            try:
                os.rmdir(temp_dir)
            except:
                pass
            
            # Log summary
            app.logger.info(
                f"Background email sending completed for payroll #{payroll_id}. "
                f"Emails sent: {emails_sent}, Failed: {emails_failed}"
            )
            
        except Exception as e:
            app.logger.error(f"Error in background email sending: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())


def generate_payslip_pdf_safe(payslip, temp_dir):
    """Generate PDF for a payslip without using Flask's template rendering"""
    try:
        # Load related data with all necessary joins
        from sqlalchemy.orm import joinedload
        
        # Get payslip with all related data
        payslip_with_data = Payslip.query.options(
            joinedload(Payslip.employee).joinedload(User.payroll_info),
            joinedload(Payslip.payroll).joinedload(Payroll.period),
            joinedload(Payslip.earnings).joinedload(PayslipEarning.earning_type),
            joinedload(Payslip.deductions).joinedload(PayslipDeduction.deduction_type)
        ).filter(Payslip.id == payslip.id).first()
        
        if not payslip_with_data:
            return None
        
        # Prepare data
        employee = payslip_with_data.employee
        employee_name = employee.full_name or f"{employee.first_name} {employee.last_name}"
        payroll_info = employee.payroll_info
        
        # Get department if available
        department = employee.department.name if employee.department else "Not Specified"
        
        # Prepare earnings data with category
        earnings_list = []
        statutory_earnings = []
        other_earnings = []
        
        for earning in payslip_with_data.earnings:
            earning_data = {
                'name': earning.earning_type.name,
                'amount': float(earning.amount) if earning.amount else 0,
                'description': earning.description or earning.earning_type.description or '',
                'is_statutory': earning.earning_type.is_statutory if hasattr(earning.earning_type, 'is_statutory') else False
            }
            earnings_list.append(earning_data)
            if earning_data['is_statutory']:
                statutory_earnings.append(earning_data)
            else:
                other_earnings.append(earning_data)
        
        # Prepare deductions data with category
        deductions_list = []
        statutory_deductions = []
        voluntary_deductions = []
        
        for deduction in payslip_with_data.deductions:
            deduction_data = {
                'name': deduction.deduction_type.name,
                'amount': float(deduction.amount) if deduction.amount else 0,
                'description': deduction.description or deduction.deduction_type.description or '',
                'is_statutory': deduction.deduction_type.is_statutory if hasattr(deduction.deduction_type, 'is_statutory') else False,
                'is_voluntary': deduction.deduction_type.is_voluntary if hasattr(deduction.deduction_type, 'is_voluntary') else False
            }
            deductions_list.append(deduction_data)
            if deduction_data['is_statutory']:
                statutory_deductions.append(deduction_data)
            else:
                voluntary_deductions.append(deduction_data)
        
        # Get payroll period info
        payroll_period = payslip_with_data.payroll.period
        
        # Create HTML content
        html_content = create_payslip_html(
            # Hospital/Company Info
            hospital_name="AstroCare Medical Center",
            hospital_address="123 Health Street, Medical Plaza, Nairobi",
            hospital_phone="+254 700 123 456",
            hospital_email="accounts@astrocare.co.ke",
            hospital_logo_url="",  # Can add logo URL if available
            
            # Employee Info
            employee_name=employee_name,
            employee_id=employee.id,
            department=department,
            
            # Payroll Info
            payroll_info=payroll_info,
            staff_no=payroll_info.staff_no if payroll_info and hasattr(payroll_info, 'staff_no') else f"EMP{employee.id:04d}",
            
            # Period Info
            period_start=payroll_period.start_date.strftime('%d %b %Y'),
            period_end=payroll_period.end_date.strftime('%d %b %Y'),
            pay_date=payroll_period.pay_date.strftime('%d %b %Y'),
            frequency=payroll_period.frequency.value if hasattr(payroll_period.frequency, 'value') else str(payroll_period.frequency),
            
            # Payment Info
            payment_method=payroll_info.payment_method.value if payroll_info and payroll_info.payment_method else 'N/A',
            payment_reference=payslip_with_data.payment_reference or f"PY{payslip_with_data.id:06d}",
            
            # Bank Details
            bank_name=payroll_info.bank_name if payroll_info and payroll_info.bank_name else 'Not Provided',
            bank_branch=payroll_info.bank_branch if payroll_info and payroll_info.bank_branch else '',
            bank_account=payroll_info.bank_account if payroll_info and payroll_info.bank_account else '',
            mpesa_number=payroll_info.mpesa_number if payroll_info and payroll_info.mpesa_number else '',
            
            # Statutory Numbers
            kra_pin=payroll_info.kra_pin if payroll_info and payroll_info.kra_pin else '',
            nhif_number=payroll_info.nhif_number if payroll_info and payroll_info.nhif_number else '',
            nssf_number=payroll_info.nssf_number if payroll_info and payroll_info.nssf_number else '',
            sha_number=payroll_info.sha_number if payroll_info and payroll_info.sha_number else '',
            
            # Salary Details
            basic_salary=float(payslip_with_data.basic_salary) if payslip_with_data.basic_salary else 0,
            gross_earnings=float(payslip_with_data.gross_earnings) if payslip_with_data.gross_earnings else 0,
            total_deductions=float(payslip_with_data.total_deductions) if payslip_with_data.total_deductions else 0,
            net_pay=float(payslip_with_data.net_pay) if payslip_with_data.net_pay else 0,
            
            # Earnings Breakdown
            earnings=earnings_list,
            statutory_earnings=statutory_earnings,
            other_earnings=other_earnings,
            
            # Deductions Breakdown
            deductions=deductions_list,
            statutory_deductions=statutory_deductions,
            voluntary_deductions=voluntary_deductions,
            
            # Allowances
            housing_allowance=float(payroll_info.housing_allowance) if payroll_info and payroll_info.housing_allowance else 0,
            transport_allowance=float(payroll_info.transport_allowance) if payroll_info and payroll_info.transport_allowance else 0,
            other_allowance=float(payroll_info.other_allowance) if payroll_info and payroll_info.other_allowance else 0,
            
            # Additional Info
            payroll_id=payslip_with_data.payroll.id,
            payslip_id=payslip_with_data.id,
            generated_date=datetime.utcnow().strftime('%d %b %Y %H:%M'),
            is_paid=payslip_with_data.is_paid,
            paid_at=payslip_with_data.paid_at.strftime('%d %b %Y %H:%M') if payslip_with_data.paid_at else ''
        )
        
        # Generate PDF
        pdf = HTML(string=html_content).write_pdf()
        
        # Save to temporary file
        filename = f"payslip_{employee_name.replace(' ', '_')}_{payroll_period.start_date.strftime('%Y%m')}.pdf"
        pdf_path = os.path.join(temp_dir, filename)
        
        with open(pdf_path, 'wb') as f:
            f.write(pdf)
        
        return pdf_path
        
    except Exception as e:
        current_app.logger.error(f"Error generating PDF for payslip #{payslip.id}: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return None


def create_payslip_html(**kwargs):
    """Create HTML content for payslip without using template rendering"""
    
    # Extract all variables
    # Hospital Info
    hospital_name = kwargs.get('hospital_name', 'AstroCare Medical Center')
    hospital_address = kwargs.get('hospital_address', '123 Health Street, Medical Plaza, Nairobi')
    hospital_phone = kwargs.get('hospital_phone', '+254 700 123 456')
    hospital_email = kwargs.get('hospital_email', 'accounts@astrocare.co.ke')
    
    # Employee Info
    employee_name = kwargs.get('employee_name', '')
    employee_id = kwargs.get('employee_id', '')
    department = kwargs.get('department', 'Not Specified')
    
    # Payroll Info
    staff_no = kwargs.get('staff_no', '')
    payroll_info = kwargs.get('payroll_info', None)
    
    # Period Info
    period_start = kwargs.get('period_start', '')
    period_end = kwargs.get('period_end', '')
    pay_date = kwargs.get('pay_date', '')
    frequency = kwargs.get('frequency', 'Monthly')
    
    # Payment Info
    payment_method = kwargs.get('payment_method', 'N/A')
    payment_reference = kwargs.get('payment_reference', 'N/A')
    
    # Bank Details
    bank_name = kwargs.get('bank_name', 'Not Provided')
    bank_branch = kwargs.get('bank_branch', '')
    bank_account = kwargs.get('bank_account', '')
    mpesa_number = kwargs.get('mpesa_number', '')
    
    # Statutory Numbers
    kra_pin = kwargs.get('kra_pin', '')
    nhif_number = kwargs.get('nhif_number', '')
    nssf_number = kwargs.get('nssf_number', '')
    sha_number = kwargs.get('sha_number', '')
    
    # Salary Details
    basic_salary = kwargs.get('basic_salary', 0)
    gross_earnings = kwargs.get('gross_earnings', 0)
    total_deductions = kwargs.get('total_deductions', 0)
    net_pay = kwargs.get('net_pay', 0)
    
    # Earnings
    earnings = kwargs.get('earnings', [])
    statutory_earnings = kwargs.get('statutory_earnings', [])
    other_earnings = kwargs.get('other_earnings', [])
    
    # Deductions
    deductions = kwargs.get('deductions', [])
    statutory_deductions = kwargs.get('statutory_deductions', [])
    voluntary_deductions = kwargs.get('voluntary_deductions', [])
    
    # Allowances
    housing_allowance = kwargs.get('housing_allowance', 0)
    transport_allowance = kwargs.get('transport_allowance', 0)
    other_allowance = kwargs.get('other_allowance', 0)
    
    # Additional Info
    payroll_id = kwargs.get('payroll_id', '')
    payslip_id = kwargs.get('payslip_id', '')
    generated_date = kwargs.get('generated_date', '')
    is_paid = kwargs.get('is_paid', False)
    paid_at = kwargs.get('paid_at', '')
    
    # Calculate total allowances
    total_allowances = housing_allowance + transport_allowance + other_allowance
    
    # Build earnings rows HTML
    statutory_earnings_rows = ''
    for earning in statutory_earnings:
        statutory_earnings_rows += f'''
        <tr>
            <td>{earning['name']}</td>
            <td class="text-right">{earning['amount']:,.2f}</td>
        </tr>
        '''
    
    other_earnings_rows = ''
    for earning in other_earnings:
        other_earnings_rows += f'''
        <tr>
            <td>{earning['name']}</td>
            <td class="text-right">{earning['amount']:,.2f}</td>
        </tr>
        '''
    
    # Build deductions rows HTML
    statutory_deductions_rows = ''
    for deduction in statutory_deductions:
        statutory_deductions_rows += f'''
        <tr>
            <td>{deduction['name']}</td>
            <td class="text-right">{deduction['amount']:,.2f}</td>
        </tr>
        '''
    
    voluntary_deductions_rows = ''
    for deduction in voluntary_deductions:
        voluntary_deductions_rows += f'''
        <tr>
            <td>{deduction['name']}</td>
            <td class="text-right">{deduction['amount']:,.2f}</td>
        </tr>
        '''
    
    # Complete HTML with modern design
    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payslip - {employee_name} - {period_start} to {period_end}</title>
        <style>
            @page {{
                size: A4;
                margin: 15mm;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.5;
                color: #333;
                margin: 0;
                padding: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            
            .payslip-container {{
                max-width: 794px; /* A4 width in pixels */
                margin: 20px auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                overflow: hidden;
                position: relative;
            }}
            
            /* Watermark */
            .watermark {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%) rotate(-45deg);
                font-size: 80px;
                font-weight: bold;
                color: rgba(79, 70, 229, 0.08);
                pointer-events: none;
                z-index: 1;
            }}
            
            .content {{
                position: relative;
                z-index: 2;
                padding: 30px;
            }}
            
            /* Header Styles */
            .header {{
                background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
                color: white;
                padding: 25px 30px;
                border-radius: 12px 12px 0 0;
            }}
            
            .hospital-info h1 {{
                font-size: 28px;
                font-weight: 700;
                margin: 0 0 5px 0;
                color: white;
            }}
            
            .hospital-info .tagline {{
                font-size: 14px;
                opacity: 0.9;
                margin: 0 0 10px 0;
            }}
            
            .contact-info {{
                display: flex;
                gap: 20px;
                font-size: 13px;
                margin-top: 10px;
            }}
            
            .contact-item {{
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            
            /* Document Title */
            .document-title {{
                text-align: center;
                margin: 25px 0;
                position: relative;
            }}
            
            .document-title h2 {{
                font-size: 32px;
                font-weight: 700;
                color: #1F2937;
                margin: 0;
                display: inline-block;
                padding: 0 20px;
                background: white;
                position: relative;
                z-index: 2;
            }}
            
            .document-title::before {{
                content: '';
                position: absolute;
                top: 50%;
                left: 0;
                right: 0;
                height: 2px;
                background: linear-gradient(90deg, transparent, #4F46E5, transparent);
                z-index: 1;
            }}
            
            /* Status Badge */
            .status-badge {{
                display: inline-block;
                padding: 6px 16px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                margin-left: 15px;
                vertical-align: middle;
                background: {'#10B981' if is_paid else '#F59E0B'};
                color: white;
            }}
            
            /* Info Grid */
            .info-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 25px;
                margin-bottom: 30px;
            }}
            
            .info-card {{
                background: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 20px;
            }}
            
            .info-card h3 {{
                font-size: 14px;
                font-weight: 600;
                color: #6B7280;
                margin: 0 0 15px 0;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .info-row {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 10px;
                padding-bottom: 10px;
                border-bottom: 1px solid #F3F4F6;
            }}
            
            .info-row:last-child {{
                border-bottom: none;
                margin-bottom: 0;
                padding-bottom: 0;
            }}
            
            .info-label {{
                font-weight: 500;
                color: #6B7280;
                font-size: 13px;
            }}
            
            .info-value {{
                font-weight: 600;
                color: #111827;
                font-size: 13px;
                text-align: right;
            }}
            
            /* Summary Cards */
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin: 30px 0;
            }}
            
            .summary-card {{
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
                border: 2px solid;
                position: relative;
                overflow: hidden;
            }}
            
            .summary-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
            }}
            
            .gross-card {{ border-color: #10B981; }}
            .gross-card::before {{ background: #10B981; }}
            
            .deductions-card {{ border-color: #EF4444; }}
            .deductions-card::before {{ background: #EF4444; }}
            
            .net-card {{ border-color: #4F46E5; }}
            .net-card::before {{ background: #4F46E5; }}
            
            .summary-label {{
                font-size: 13px;
                color: #6B7280;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
            }}
            
            .summary-value {{
                font-size: 24px;
                font-weight: 700;
                color: #111827;
            }}
            
            /* Tables */
            .table-container {{
                margin: 30px 0;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid #E5E7EB;
            }}
            
            .table-header {{
                background: #4F46E5;
                color: white;
                padding: 15px 20px;
                font-weight: 600;
                font-size: 15px;
            }}
            
            .table-subheader {{
                background: #F3F4F6;
                padding: 10px 20px;
                font-weight: 600;
                color: #374151;
                font-size: 13px;
                border-top: 1px solid #E5E7EB;
            }}
            
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            
            th {{
                background: #F9FAFB;
                padding: 12px 20px;
                text-align: left;
                font-weight: 600;
                color: #374151;
                font-size: 13px;
                border-bottom: 2px solid #E5E7EB;
            }}
            
            td {{
                padding: 12px 20px;
                border-bottom: 1px solid #F3F4F6;
                font-size: 13px;
            }}
            
            .text-right {{
                text-align: right;
            }}
            
            .total-row {{
                background: #F9FAFB;
                font-weight: 700;
                border-top: 2px solid #E5E7EB;
            }}
            
            /* Footer */
            .footer {{
                margin-top: 40px;
                padding-top: 20px;
                border-top: 2px solid #E5E7EB;
                text-align: center;
                color: #6B7280;
                font-size: 11px;
                line-height: 1.6;
            }}
            
            .footer-links {{
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 10px;
            }}
            
            .footer-links a {{
                color: #4F46E5;
                text-decoration: none;
                font-weight: 500;
            }}
            
            /* QR Code Area */
            .qr-area {{
                margin-top: 30px;
                text-align: center;
                padding: 20px;
                background: #F9FAFB;
                border-radius: 8px;
                border: 1px dashed #D1D5DB;
            }}
            
            .qr-placeholder {{
                width: 100px;
                height: 100px;
                background: #E5E7EB;
                margin: 0 auto 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 4px;
                color: #6B7280;
                font-size: 10px;
            }}
            
            /* Print styles */
            @media print {{
                body {{
                    background: none;
                    margin: 0;
                    padding: 0;
                }}
                
                .payslip-container {{
                    box-shadow: none;
                    margin: 0;
                    border-radius: 0;
                }}
                
                .watermark {{
                    opacity: 0.3;
                }}
                
                .no-print {{
                    display: none;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="watermark">ASTROCARE PAYSLIP</div>
        
        <div class="payslip-container">
            <div class="header">
                <div class="hospital-info">
                    <h1>{hospital_name}</h1>
                    <p class="tagline">Excellence in Healthcare Services</p>
                    <div class="contact-info">
                        <div class="contact-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                            </svg>
                            <span>{hospital_address}</span>
                        </div>
                        <div class="contact-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                            </svg>
                            <span>{hospital_email}</span>
                        </div>
                        <div class="contact-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M20 15.5c-1.25 0-2.45-.2-3.57-.57-.35-.11-.74-.03-1.02.24l-2.2 2.2c-2.83-1.44-5.15-3.75-6.59-6.59l2.2-2.21c.28-.26.36-.65.25-1C8.7 6.45 8.5 5.25 8.5 4c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1 0 9.39 7.61 17 17 17 .55 0 1-.45 1-1v-3.5c0-.55-.45-1-1-1z"/>
                            </svg>
                            <span>{hospital_phone}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="content">
                <!-- Document Title -->
                <div class="document-title">
                    <h2>EMPLOYEE PAYSLIP
                        <span class="status-badge">{'PAID' if is_paid else 'PROCESSED'}</span>
                    </h2>
                </div>
                
                <!-- Information Grid -->
                <div class="info-grid">
                    <!-- Employee Information -->
                    <div class="info-card">
                        <h3>Employee Information</h3>
                        <div class="info-row">
                            <span class="info-label">Full Name:</span>
                            <span class="info-value">{employee_name}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Staff Number:</span>
                            <span class="info-value">{staff_no}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Employee ID:</span>
                            <span class="info-value">{employee_id}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Department:</span>
                            <span class="info-value">{department}</span>
                        </div>
                    </div>
                    
                    <!-- Payment Information -->
                    <div class="info-card">
                        <h3>Payment Information</h3>
                        <div class="info-row">
                            <span class="info-label">Pay Period:</span>
                            <span class="info-value">{period_start} to {period_end}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Pay Date:</span>
                            <span class="info-value">{pay_date}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Payment Method:</span>
                            <span class="info-value">{payment_method}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Reference:</span>
                            <span class="info-value">{payment_reference}</span>
                        </div>
                    </div>
                </div>
                
                <!-- Bank & Statutory Information Grid -->
                <div class="info-grid">
                    <!-- Bank Details -->
                    <div class="info-card">
                        <h3>Bank Details</h3>
                        <div class="info-row">
                            <span class="info-label">Bank Name:</span>
                            <span class="info-value">{bank_name}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Branch:</span>
                            <span class="info-value">{bank_branch or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Account Number:</span>
                            <span class="info-value">{bank_account or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">M-Pesa Number:</span>
                            <span class="info-value">{mpesa_number or 'N/A'}</span>
                        </div>
                    </div>
                    
                    <!-- Statutory Information -->
                    <div class="info-card">
                        <h3>Statutory Information</h3>
                        <div class="info-row">
                            <span class="info-label">KRA PIN:</span>
                            <span class="info-value">{kra_pin or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">NHIF Number:</span>
                            <span class="info-value">{nhif_number or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">NSSF Number:</span>
                            <span class="info-value">{nssf_number or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">SHA Number:</span>
                            <span class="info-value">{sha_number or 'N/A'}</span>
                        </div>
                    </div>
                </div>
                
                <!-- Summary Cards -->
                <div class="summary-grid">
                    <div class="summary-card gross-card">
                        <div class="summary-label">Gross Earnings</div>
                        <div class="summary-value">KES {gross_earnings:,.2f}</div>
                    </div>
                    
                    <div class="summary-card deductions-card">
                        <div class="summary-label">Total Deductions</div>
                        <div class="summary-value">KES {total_deductions:,.2f}</div>
                    </div>
                    
                    <div class="summary-card net-card">
                        <div class="summary-label">Net Pay</div>
                        <div class="summary-value">KES {net_pay:,.2f}</div>
                    </div>
                </div>
                
                <!-- Earnings Table -->
                <div class="table-container">
                    <div class="table-header">EARNINGS BREAKDOWN</div>
                    
                    <!-- Basic Salary -->
                    <table>
                        <thead>
                            <tr>
                                <th>Description</th>
                                <th class="text-right">Amount (KES)</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><strong>Basic Salary</strong></td>
                                <td class="text-right"><strong>{basic_salary:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <!-- Allowances -->
                    {'<div class="table-subheader">ALLOWANCES</div>' if total_allowances > 0 else ''}
                    {'<table>' if total_allowances > 0 else ''}
                    {'<tbody>' if total_allowances > 0 else ''}
                    {f'<tr><td>Housing Allowance</td><td class="text-right">{housing_allowance:,.2f}</td></tr>' if housing_allowance > 0 else ''}
                    {f'<tr><td>Transport Allowance</td><td class="text-right">{transport_allowance:,.2f}</td></tr>' if transport_allowance > 0 else ''}
                    {f'<tr><td>Other Allowance</td><td class="text-right">{other_allowance:,.2f}</td></tr>' if other_allowance > 0 else ''}
                    {'</tbody>' if total_allowances > 0 else ''}
                    {'</table>' if total_allowances > 0 else ''}
                    
                    <!-- Other Earnings -->
                    {f'<div class="table-subheader">OTHER EARNINGS</div>' if other_earnings else ''}
                    {f'<table>' if other_earnings else ''}
                    {f'<tbody>{other_earnings_rows}</tbody>' if other_earnings else ''}
                    {f'</table>' if other_earnings else ''}
                    
                    <!-- Statutory Earnings -->
                    {f'<div class="table-subheader">STATUTORY EARNINGS</div>' if statutory_earnings else ''}
                    {f'<table>' if statutory_earnings else ''}
                    {f'<tbody>{statutory_earnings_rows}</tbody>' if statutory_earnings else ''}
                    {f'</table>' if statutory_earnings else ''}
                    
                    <!-- Total Gross -->
                    <table>
                        <tbody>
                            <tr class="total-row">
                                <td><strong>TOTAL GROSS EARNINGS</strong></td>
                                <td class="text-right"><strong>{gross_earnings:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Deductions Table -->
                <div class="table-container">
                    <div class="table-header">DEDUCTIONS BREAKDOWN</div>
                    
                    <!-- Statutory Deductions -->
                    {f'<div class="table-subheader">STATUTORY DEDUCTIONS</div>' if statutory_deductions else ''}
                    {f'<table>' if statutory_deductions else ''}
                    {f'<tbody>{statutory_deductions_rows}</tbody>' if statutory_deductions else ''}
                    {f'</table>' if statutory_deductions else ''}
                    
                    <!-- Voluntary Deductions -->
                    {f'<div class="table-subheader">VOLUNTARY DEDUCTIONS</div>' if voluntary_deductions else ''}
                    {f'<table>' if voluntary_deductions else ''}
                    {f'<tbody>{voluntary_deductions_rows}</tbody>' if voluntary_deductions else ''}
                    {f'</table>' if voluntary_deductions else ''}
                    
                    <!-- Total Deductions -->
                    <table>
                        <tbody>
                            <tr class="total-row">
                                <td><strong>TOTAL DEDUCTIONS</strong></td>
                                <td class="text-right"><strong>{total_deductions:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Net Pay Section -->
                <div class="table-container" style="background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); color: white;">
                    <div class="table-header" style="background: transparent; border-bottom: 1px solid rgba(255,255,255,0.2);">
                        PAYMENT SUMMARY
                    </div>
                    <table>
                        <tbody>
                            <tr>
                                <td style="color: white; font-size: 16px;"><strong>GROSS EARNINGS</strong></td>
                                <td class="text-right" style="color: white; font-size: 16px;"><strong>{gross_earnings:,.2f}</strong></td>
                            </tr>
                            <tr>
                                <td style="color: white; opacity: 0.9;">Less: Total Deductions</td>
                                <td class="text-right" style="color: white; opacity: 0.9;">({total_deductions:,.2f})</td>
                            </tr>
                            <tr style="border-top: 2px solid rgba(255,255,255,0.3);">
                                <td style="color: white; font-size: 20px; padding-top: 20px;"><strong>NET PAY</strong></td>
                                <td class="text-right" style="color: white; font-size: 20px; padding-top: 20px;"><strong>KES {net_pay:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Payment Status -->
                {f'<div class="qr-area"><div class="qr-placeholder">PAYMENT CONFIRMED<br>{paid_at}</div><p style="font-size: 12px; color: #6B7280; margin: 0;">Payment confirmed and processed</p></div>' if is_paid else ''}
                
                <!-- Footer -->
                <div class="footer">
                    <p>
                        This payslip was generated by <strong>AstroCare HR System</strong> on {generated_date}.<br>
                        Payroll ID: #{payroll_id} | Payslip ID: #{payslip_id}<br>
                        Frequency: {frequency} | Generated for: {employee_name}
                    </p>
                    <p style="font-size: 10px; margin-top: 15px; color: #9CA3AF;">
                        <strong>Confidential Document:</strong> This payslip contains confidential information and is intended solely for the addressee.<br>
                        Unauthorized disclosure, copying, distribution, or action based on the contents is strictly prohibited.<br>
                        For any discrepancies, please contact the HR department within 7 days of receipt.
                    </p>
                    <div class="footer-links">
                        <span>www.astrocare.co.ke</span>
                        <span>hr@astrocare.co.ke</span>
                        <span>+254 700 123 456</span>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return html


def send_payslip_email_with_pdf(notification_manager, payslip, payroll, pdf_path):
    """Send professional email with PDF attachment"""
    try:
        # Get employee details
        employee = payslip.employee
        employee_name = employee.full_name or f"{employee.first_name} {employee.last_name}"
        
        # Get payroll info for payment details
        payroll_info = employee.payroll_info
        payment_method = payslip.payment_method or (payroll_info.payment_method if payroll_info else None)
        
        # Get bank details
        bank_name = payroll_info.bank_name if payroll_info and payroll_info.bank_name else "Not specified"
        bank_branch = payroll_info.bank_branch if payroll_info and payroll_info.bank_branch else ""
        bank_account = payroll_info.bank_account if payroll_info and payroll_info.bank_account else ""
        mpesa_number = payroll_info.mpesa_number if payroll_info and payroll_info.mpesa_number else ""
        
        # Format payment details based on method
        payment_details = ""
        if payment_method:
            if payment_method.value == "Bank Transfer":
                if bank_account:
                    payment_details = f"<strong>Bank:</strong> {bank_name}<br>"
                    if bank_branch:
                        payment_details += f"<strong>Branch:</strong> {bank_branch}<br>"
                    payment_details += f"<strong>Account:</strong> {bank_account}"
            elif payment_method.value == "M-Pesa":
                if mpesa_number:
                    payment_details = f"<strong>M-Pesa Number:</strong> {mpesa_number}"
            else:
                payment_details = f"<strong>Payment Method:</strong> {payment_method.value}"
        
        # Get period details
        period_start = payroll.period.start_date.strftime('%d %b %Y')
        period_end = payroll.period.end_date.strftime('%d %b %Y')
        payment_date = datetime.utcnow().strftime('%d %b %Y')
        
        # Calculate YTD totals (if available)
        ytd_gross = float(payslip.gross_earnings or 0)  # This would be cumulative in real system
        ytd_deductions = float(payslip.total_deductions or 0)  # This would be cumulative
        
        # Prepare email content
        subject = f"Salary Credited - KES {payslip.net_pay:,.2f} - {period_start} to {period_end}"
        
        # Professional HTML email template
        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Salary Payment Notification</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
                
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    line-height: 1.6;
                    color: #374151;
                    margin: 0;
                    padding: 0;
                    background-color: #f9fafb;
                }}
                
                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                }}
                
                .email-header {{
                    background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
                    color: white;
                    padding: 32px 40px;
                    text-align: center;
                }}
                
                .hospital-logo {{
                    font-size: 24px;
                    font-weight: 700;
                    letter-spacing: -0.5px;
                    margin: 0 0 8px 0;
                }}
                
                .email-title {{
                    font-size: 28px;
                    font-weight: 700;
                    margin: 0;
                    letter-spacing: -0.5px;
                }}
                
                .email-subtitle {{
                    font-size: 16px;
                    opacity: 0.9;
                    margin: 8px 0 0 0;
                    font-weight: 400;
                }}
                
                .email-content {{
                    padding: 40px;
                }}
                
                .greeting {{
                    font-size: 18px;
                    color: #111827;
                    margin-bottom: 24px;
                }}
                
                .salary-amount {{
                    text-align: center;
                    margin: 32px 0;
                    padding: 24px;
                    background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                    border-radius: 12px;
                    color: white;
                }}
                
                .salary-label {{
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    opacity: 0.9;
                    margin-bottom: 8px;
                }}
                
                .salary-value {{
                    font-size: 40px;
                    font-weight: 700;
                    margin: 0;
                }}
                
                .info-card {{
                    background: #F9FAFB;
                    border: 1px solid #E5E7EB;
                    border-radius: 12px;
                    padding: 24px;
                    margin-bottom: 24px;
                }}
                
                .info-card h3 {{
                    color: #4F46E5;
                    margin: 0 0 16px 0;
                    font-size: 16px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .info-grid {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 16px;
                }}
                
                .info-item {{
                    margin-bottom: 12px;
                }}
                
                .info-label {{
                    font-size: 13px;
                    color: #6B7280;
                    font-weight: 500;
                    margin-bottom: 4px;
                }}
                
                .info-value {{
                    font-size: 15px;
                    color: #111827;
                    font-weight: 600;
                }}
                
                .summary-grid {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 16px;
                    margin: 24px 0;
                }}
                
                .summary-box {{
                    background: white;
                    border-radius: 8px;
                    padding: 16px;
                    text-align: center;
                    border: 1px solid #E5E7EB;
                }}
                
                .summary-box.gross {{
                    border-top: 3px solid #10B981;
                }}
                
                .summary-box.deductions {{
                    border-top: 3px solid #EF4444;
                }}
                
                .summary-box.net {{
                    border-top: 3px solid #4F46E5;
                }}
                
                .summary-label {{
                    font-size: 12px;
                    color: #6B7280;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 8px;
                }}
                
                .summary-value {{
                    font-size: 18px;
                    font-weight: 700;
                    color: #111827;
                }}
                
                .attachment-card {{
                    background: #F0F9FF;
                    border: 2px dashed #0EA5E9;
                    border-radius: 12px;
                    padding: 24px;
                    text-align: center;
                    margin: 32px 0;
                }}
                
                .attachment-icon {{
                    background: #0EA5E9;
                    color: white;
                    width: 48px;
                    height: 48px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 16px;
                    font-size: 20px;
                }}
                
                .attachment-text h4 {{
                    color: #0369A1;
                    margin: 0 0 8px 0;
                    font-size: 16px;
                }}
                
                .attachment-text p {{
                    color: #0C4A6E;
                    margin: 0;
                    font-size: 14px;
                }}
                
                .cta-button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
                    color: white;
                    text-decoration: none;
                    padding: 14px 32px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 15px;
                    margin: 8px 0;
                    text-align: center;
                }}
                
                .footer {{
                    margin-top: 40px;
                    padding-top: 24px;
                    border-top: 1px solid #E5E7EB;
                    text-align: center;
                    color: #6B7280;
                    font-size: 13px;
                }}
                
                .contact-info {{
                    display: flex;
                    justify-content: center;
                    gap: 24px;
                    margin-top: 16px;
                }}
                
                .contact-item {{
                    color: #4F46E5;
                    text-decoration: none;
                    font-size: 12px;
                }}
                
                @media (max-width: 600px) {{
                    .info-grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .summary-grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .email-header,
                    .email-content {{
                        padding: 24px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <!-- Header -->
                <div class="email-header">
                    <h1 class="hospital-logo">ASTROCARE MEDICAL CENTER</h1>
                    <h2 class="email-title">Salary Payment Notification</h2>
                    <p class="email-subtitle">Your salary for {period_start} - {period_end} has been processed</p>
                </div>
                
                <!-- Content -->
                <div class="email-content">
                    <!-- Greeting -->
                    <div class="greeting">
                        <p>Dear <strong>{employee_name}</strong>,</p>
                        <p>We are pleased to inform you that your salary for the period <strong>{period_start} to {period_end}</strong> has been successfully processed and credited to your account.</p>
                    </div>
                    
                    <!-- Salary Amount -->
                    <div class="salary-amount">
                        <div class="salary-label">Amount Credited</div>
                        <h2 class="salary-value">KES {payslip.net_pay:,.2f}</h2>
                    </div>
                    
                    <!-- Payment Information -->
                    <div class="info-card">
                        <h3>Payment Information</h3>
                        <div class="info-grid">
                            <div class="info-item">
                                <div class="info-label">Payment Date</div>
                                <div class="info-value">{payment_date}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Payment Method</div>
                                <div class="info-value">{payment_method.value if payment_method else 'N/A'}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Payroll Reference</div>
                                <div class="info-value">#{payroll.id}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Transaction ID</div>
                                <div class="info-value">{payslip.payment_reference}</div>
                            </div>
                        </div>
                        
                        <!-- Bank Details -->
                        {f'<div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #E5E7EB;"><div class="info-label" style="color: #4F46E5; margin-bottom: 8px;">CREDITED TO YOUR ACCOUNT</div><div style="font-size: 14px; color: #111827;">{payment_details}</div></div>' if payment_details else ''}
                    </div>
                    
                    <!-- Salary Summary -->
                    <div class="info-card">
                        <h3>Salary Breakdown</h3>
                        <div class="summary-grid">
                            <div class="summary-box gross">
                                <div class="summary-label">Gross Earnings</div>
                                <div class="summary-value">KES {payslip.gross_earnings:,.2f}</div>
                            </div>
                            <div class="summary-box deductions">
                                <div class="summary-label">Total Deductions</div>
                                <div class="summary-value">KES {payslip.total_deductions:,.2f}</div>
                            </div>
                            <div class="summary-box net">
                                <div class="summary-label">Net Amount</div>
                                <div class="summary-value">KES {payslip.net_pay:,.2f}</div>
                            </div>
                        </div>
                        
                        <!-- Detailed Breakdown -->
                        <div style="margin-top: 24px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #E5E7EB;">
                                <span style="color: #6B7280;">Basic Salary</span>
                                <span style="font-weight: 600;">KES {payslip.basic_salary:,.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #E5E7EB;">
                                <span style="color: #6B7280;">Allowances & Bonuses</span>
                                <span style="font-weight: 600;">KES {(payslip.gross_earnings - payslip.basic_salary):,.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #E5E7EB;">
                                <span style="color: #6B7280;">Statutory Deductions</span>
                                <span style="font-weight: 600; color: #EF4444;">KES {payslip.total_deductions:,.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-top: 16px; padding-top: 16px; border-top: 2px solid #4F46E5;">
                                <span style="color: #4F46E5; font-weight: 700;">Net Salary</span>
                                <span style="font-weight: 700; color: #10B981; font-size: 18px;">KES {payslip.net_pay:,.2f}</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Payslip Attachment -->
                    <div class="attachment-card">
                        <div class="attachment-icon">
                            📄
                        </div>
                        <div class="attachment-text">
                            <h4>Detailed Payslip Attached</h4>
                            <p>Your complete payslip with detailed breakdown is attached as a PDF document.</p>
                        </div>
                        <p style="font-size: 12px; color: #6B7280; margin-top: 12px;">
                            File: payslip_{employee_name.replace(' ', '_')}_{period_start.replace(' ', '')}.pdf
                        </p>
                    </div>
                    
                    <!-- Important Notes -->
                    <div style="background: #FEF3C7; border-left: 4px solid #F59E0B; padding: 16px; border-radius: 8px; margin: 24px 0;">
                        <h4 style="color: #92400E; margin: 0 0 8px 0; font-size: 14px;">⚠️ Important Information</h4>
                        <ul style="color: #92400E; margin: 0; padding-left: 20px; font-size: 13px;">
                            <li>Please verify the credited amount with your bank statement</li>
                            <li>Report any discrepancies to HR within 7 working days</li>
                            <li>Your payslip is a confidential document - keep it secure</li>
                            <li>This is an automated notification - please do not reply</li>
                        </ul>
                    </div>
                    
                    <!-- CTA Buttons -->
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="#" class="cta-button">View in HR Portal</a>
                        <p style="font-size: 12px; color: #6B7280; margin-top: 12px;">
                            Login to the AstroCare HR System for detailed reports
                        </p>
                    </div>
                    
                    <!-- Footer -->
                    <div class="footer">
                        <p>
                            <strong>AstroCare Medical Center - Human Resources Department</strong><br>
                            This is an automated notification generated by the AstroCare HR System.
                        </p>
                        <div class="contact-info">
                            <a href="mailto:hr@astrocare.co.ke" class="contact-item">✉️ hr@astrocare.co.ke</a>
                            <a href="tel:+254700123456" class="contact-item">📞 +254 700 123 456</a>
                            <span class="contact-item">🏥 www.astrocare.co.ke</span>
                        </div>
                        <p style="font-size: 11px; color: #9CA3AF; margin-top: 16px;">
                            Confidentiality Notice: This email contains privileged and confidential information.<br>
                            If you are not the intended recipient, please delete it immediately.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Professional plain text version
        plain_text = f"""
        SALARY PAYMENT NOTIFICATION
        ============================

        Dear {employee_name},

        We are pleased to inform you that your salary for the period {period_start} to {period_end} 
        has been successfully processed and credited to your account.

        PAYMENT DETAILS
        ---------------
        Amount Credited: KES {payslip.net_pay:,.2f}
        Payment Date: {payment_date}
        Payment Method: {payment_method.value if payment_method else 'N/A'}
        Payroll Reference: #{payroll.id}
        Transaction ID: {payslip.payment_reference}

        {f'CREDITED TO: {bank_name} - Account: {bank_account}' if bank_account else ''}
        {f'MPESA NUMBER: {mpesa_number}' if mpesa_number else ''}

        SALARY BREAKDOWN
        ----------------
        Basic Salary: KES {payslip.basic_salary:,.2f}
        Gross Earnings: KES {payslip.gross_earnings:,.2f}
        Total Deductions: KES {payslip.total_deductions:,.2f}
        Net Salary: KES {payslip.net_pay:,.2f}

        ATTACHMENT
        ----------
        Your detailed payslip is attached as a PDF file: 
        payslip_{employee_name.replace(' ', '_')}_{period_start.replace(' ', '')}.pdf

        IMPORTANT NOTES:
        - Please verify the credited amount with your bank statement
        - Report any discrepancies to HR within 7 working days
        - Your payslip is a confidential document
        - This is an automated notification

        For any queries, please contact:
        Human Resources Department
        Email: hr@astrocare.co.ke
        Phone: +254 700 123 456
        Website: www.astrocare.co.ke

        This email contains privileged and confidential information.
        If you are not the intended recipient, please delete it immediately.

        Best regards,
        AstroCare HR System
        """
        
        # Send email with PDF attachment
        return notification_manager.send_email(
            subject=subject,
            recipients=[employee.email],
            body=plain_text,
            html_body=html_body,
            attachments=[pdf_path],
            sender="AstroCare HR System <noreply@astrocare.co.ke>"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error sending email for payslip #{payslip.id}: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return False

# Add a route to check email sending status
@hr_web_bp.route('/payroll/<int:payroll_id>/email-status', methods=['GET'])
@login_required
def get_payslip_email_status(payroll_id):
    """Get status of email sending for a payroll"""
    # This is a placeholder - in a real application, you'd track this in database
    # For now, we just acknowledge that emails are being processed
    
    return jsonify({
        'success': True,
        'message': 'Email sending is in progress',
        'status': 'processing'
    })





def generate_payslip_pdf_in_memory(payslip):
    """Generate PDF in memory (without saving to file)"""
    try:
        from flask import render_template
        
        # Render HTML template
        html = render_template(
            'hr/payslip_pdf_template.html',
            payslip=payslip,
            now=datetime.now()
        )
        
        # Generate PDF
        pdf = HTML(string=html).write_pdf()
        return pdf
        
    except Exception as e:
        current_app.logger.error(f"Error generating PDF in memory: {str(e)}")
        return None

@hr_web_bp.route('/payroll/<int:payroll_id>/mark-paid', methods=['POST'])
@login_required
def mark_payroll_as_paid(payroll_id):
    """Mark payroll as paid and update all payslips"""
    try:
        payroll = Payroll.query.get_or_404(payroll_id)
        
        # Check if payroll can be marked as paid
        if payroll.status not in ['Approved', 'Processed']:
            return jsonify({
                'success': False,
                'message': f'Payroll cannot be marked as paid. Current status: {payroll.status}'
            }), 400
        
        # Get current time
        now = datetime.utcnow()
        
        # Update payroll status
        payroll.status = 'Paid'
        
        # Update all payslips for this payroll
        for payslip in payroll.payslips:
            payslip.is_paid = True
            payslip.paid_at = now
            # Generate payment reference if not exists
            if not payslip.payment_reference:
                payslip.payment_reference = f"PAY-{payroll.period_id}-{payslip.employee_id:04d}-{now.strftime('%Y%m%d%H%M%S')}"
        
        # Close the payroll period
        period = payroll.period
        period.is_closed = True
        
        db.session.commit()
        
        current_app.logger.info(f"Payroll marked as paid: ID #{payroll.id}, Period: {period.id}, {len(payroll.payslips)} payslips updated")
        
        return jsonify({
            'success': True,
            'message': f'Payroll marked as paid. {len(payroll.payslips)} payslips updated.',
            'payroll': {
                'id': payroll.id,
                'status': payroll.status,
                'employee_count': len(payroll.payslips)
            }
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Payroll mark as paid error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Failed to mark payroll as paid: {str(e)}'
        }), 500


@hr_web_bp.route('/payroll/<int:payroll_id>/details')
@login_required
def payroll_details(payroll_id):
    """Get detailed payroll information"""
    payroll = Payroll.query.get_or_404(payroll_id)
    
    # Get detailed payslip information
    payslips_data = []
    for payslip in payroll.payslips:
        # Determine payslip status based on is_paid and paid_at
        if payslip.is_paid and payslip.paid_at:
            payslip_status = 'Paid'
        else:
            payslip_status = 'Generated'
        
        payslips_data.append({
            'id': payslip.id,
            'employee_name': payslip.employee.full_name if payslip.employee else 'Unknown',
            'employee_id': payslip.employee.id if payslip.employee else payslip.employee_id,
            'basic_salary': float(payslip.basic_salary),
            'gross_earnings': float(payslip.gross_earnings),
            'total_deductions': float(payslip.total_deductions),
            'net_pay': float(payslip.net_pay),
            'status': payslip_status,  # Computed from is_paid and paid_at
            'payment_method': payslip.payment_method.value if payslip.payment_method else 'Not Set',
            'is_paid': payslip.is_paid,
            'paid_at': payslip.paid_at.strftime('%d %b %Y %H:%M') if payslip.paid_at else None
        })
    
    return jsonify({
        'success': True,
        'payroll': {
            'id': payroll.id,
            'period': f"{payroll.period.start_date.strftime('%d %b %Y')} - {payroll.period.end_date.strftime('%d %b %Y')}",
            'total_gross': float(payroll.total_gross),
            'total_deductions': float(payroll.total_deductions),
            'total_net': float(payroll.total_net),
            'employee_count': len(payroll.payslips),
            'status': payroll.status,
            'processed_at': payroll.processed_at.strftime('%d %b %Y %H:%M') if payroll.processed_at else None,
            'processed_by': payroll.processed_by,
            'notes': payroll.notes
        },
        'payslips': payslips_data
    })
@hr_web_bp.route('/payroll/<int:payroll_id>/approve', methods=['POST'])
@login_required
def approve_payroll_batch(payroll_id):
    """Approve payroll"""
    from app.hr.models import Payroll
    
    payroll = Payroll.query.get_or_404(payroll_id)
    payroll.status = 'Approved'
    payroll.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Check if request is AJAX/JSON
    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify({
            'success': True,
            'message': f'Payroll #{payroll_id} has been approved',
            'payroll': {
                'id': payroll.id,
                'status': payroll.status,
                'period_id': payroll.period_id
            }
        })
    else:
        flash(f'Payroll #{payroll_id} has been approved', 'success')
        return redirect(url_for('hr_web.employee_payroll', period_id=payroll.period_id))

@hr_web_bp.route('/payroll/history')
@login_required
def payroll_history():
    """View all payroll history"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    payrolls = Payroll.query.options(db.joinedload(Payroll.period))\
        .order_by(Payroll.processing_time.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('payroll/history.html', payrolls=payrolls)



@hr_web_bp.route('/payroll/<int:payroll_id>/process', methods=['POST'])
@login_required
def process_payroll(payroll_id):
    """Process payroll payments"""
    from app.hr.models import Payroll, Payslip
    
    payroll = Payroll.query.get_or_404(payroll_id)
    payroll.status = 'Processed'
    payroll.updated_at = datetime.utcnow()
    
    # Generate payment references for all payslips
    for payslip in payroll.payslips:
        if not payslip.payment_reference:
            payslip.payment_reference = f"SAL-{payroll.period.start_date.strftime('%Y%m')}-{payslip.employee.id:04d}"
    
    db.session.commit()
    
    flash(f'Payroll #{payroll_id} has been processed', 'success')
    return redirect(url_for('hr_web.employee_payroll', period_id=payroll.period_id))

@hr_web_bp.route('/payroll/<int:payroll_id>/mark-paid', methods=['POST'])
@login_required
def mark_payroll_paid(payroll_id):
    """Mark payroll as paid"""
    from app.hr.models import Payroll, Payslip
    
    payroll = Payroll.query.get_or_404(payroll_id)
    payroll.status = 'Paid'
    payroll.updated_at = datetime.utcnow()
    
    # Mark all payslips as paid
    for payslip in payroll.payslips:
        payslip.is_paid = True
        payslip.paid_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Payroll #{payroll_id} has been marked as paid', 'success')
    return redirect(url_for('hr_web.employee_payroll', period_id=payroll.period_id))

@hr_web_bp.route('/payroll/<int:payroll_id>/report')
@login_required
def payroll_report(payroll_id):
    """Generate payroll summary report"""
    from app.hr.models import Payroll, Payslip
    from app.hr.models import PaymentMethod
    
    payroll = Payroll.query.get_or_404(payroll_id)
    
    # Prepare report data
    total_employees = len(payroll.payslips)
    paid_employees = sum(1 for p in payroll.payslips if p.is_paid)
    
    # Calculate totals by payment method
    payment_methods = {}
    for method in PaymentMethod:
        payment_methods[method.value] = {
            'count': 0,
            'total': 0
        }
    
    for payslip in payroll.payslips:
        method = payslip.payment_method.value if payslip.payment_method else 'Unknown'
        if method in payment_methods:
            payment_methods[method]['count'] += 1
            payment_methods[method]['total'] += float(payslip.net_pay or 0)
    
    # Generate HTML report
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payroll Report #{payroll.id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .summary {{ margin-bottom: 30px; }}
            .table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            .table th, .table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            .table th {{ background-color: #f4f4f4; }}
            .total {{ font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Payroll Summary Report</h1>
            <p>Period: {payroll.period.start_date.strftime('%d/%m/%Y')} - {payroll.period.end_date.strftime('%d/%m/%Y')}</p>
            <p>Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        </div>
        
        <div class="summary">
            <h2>Payroll Summary</h2>
            <p><strong>Payroll ID:</strong> #{payroll.id}</p>
            <p><strong>Status:</strong> {payroll.status}</p>
            <p><strong>Total Employees:</strong> {total_employees}</p>
            <p><strong>Paid Employees:</strong> {paid_employees}</p>
            <p><strong>Total Gross:</strong> KES {payroll.total_gross:,.2f}</p>
            <p><strong>Total Deductions:</strong> KES {payroll.total_deductions:,.2f}</p>
            <p><strong>Total Net Pay:</strong> KES {payroll.total_net:,.2f}</p>
        </div>
        
        <div class="payment-methods">
            <h2>Payment Method Summary</h2>
            <table class="table">
                <tr>
                    <th>Payment Method</th>
                    <th>Number of Employees</th>
                    <th>Total Amount</th>
                </tr>
    """
    
    for method, data in payment_methods.items():
        if data['count'] > 0:
            html += f"""
                <tr>
                    <td>{method}</td>
                    <td>{data['count']}</td>
                    <td>KES {data['total']:,.2f}</td>
                </tr>
            """
    
    html += """
            </table>
        </div>
        
        <div class="employee-list">
            <h2>Employee Payments</h2>
            <table class="table">
                <tr>
                    <th>Employee ID</th>
                    <th>Name</th>
                    <th>Net Pay</th>
                    <th>Payment Method</th>
                    <th>Status</th>
                </tr>
    """
    
    for payslip in payroll.payslips:
        html += f"""
                <tr>
                    <td>{payslip.employee.id}</td>
                    <td>{payslip.employee.full_name}</td>
                    <td>KES {payslip.net_pay:,.2f}</td>
                    <td>{payslip.payment_method.value if payslip.payment_method else 'N/A'}</td>
                    <td>{"PAID" if payslip.is_paid else "PENDING"}</td>
                </tr>
        """
    
    html += """
            </table>
        </div>
    </body>
    </html>
    """
    
    # Generate PDF
    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        
        filename = f"payroll_report_{payroll.period.start_date.strftime('%Y%m')}.pdf"
        
        return Response(
            pdf,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Length': len(pdf)
            }
        )
    except Exception as e:
        # Fallback to HTML
        return html

@hr_web_bp.route('/payroll/bulk-update')
@login_required
def bulk_update_payroll():
    """Bulk update payroll information"""
    flash('Bulk update feature is under development', 'info')
    return redirect(url_for('hr_web.employee_payroll'))



# ===================
# PAYSLIP MANAGEMENT
# ===================

@hr_web_bp.route('/payroll/payslips', methods=['GET'])
@login_required
def payslips():
    # Get query parameters
    payroll_id = request.args.get('payroll_id')
    employee_id = request.args.get('employee_id')
    period_id = request.args.get('period_id')
    
    # Eager load all necessary relationships
    from sqlalchemy.orm import joinedload
    
    query = Payslip.query.options(
        joinedload(Payslip.employee),
        joinedload(Payslip.payroll).joinedload(Payroll.period),
        joinedload(Payslip.earnings).joinedload(PayslipEarning.earning_type),
        joinedload(Payslip.deductions).joinedload(PayslipDeduction.deduction_type)
    ).join(Payroll).join(PayrollPeriod)
    
    if payroll_id:
        query = query.filter(Payslip.payroll_id == payroll_id)
    if employee_id:
        query = query.filter(Payslip.employee_id == employee_id)
    if period_id:
        query = query.filter(Payroll.period_id == period_id)
    
    payslips = query.order_by(PayrollPeriod.start_date.desc()).all()
    
    # Get all periods for the filter dropdown
    periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()
    
    return render_template('employees_payslips.html', payslips=payslips, periods=periods)

@hr_web_bp.route('/payroll/payslip/<int:payslip_id>', methods=['GET', 'POST'])
@login_required
def view_payslip_details(payslip_id):
    """View detailed payslip information and manage earnings/deductions"""
    from sqlalchemy.orm import joinedload
    
    # Get payslip with all related data
    payslip = Payslip.query.options(
        joinedload(Payslip.employee).joinedload(User.payroll_info),
        joinedload(Payslip.payroll).joinedload(Payroll.period),
        joinedload(Payslip.earnings).joinedload(PayslipEarning.earning_type),
        joinedload(Payslip.deductions).joinedload(PayslipDeduction.deduction_type)
    ).filter(Payslip.id == payslip_id).first_or_404()
    
    # Get available earning and deduction types for adding new ones
    earning_types = EarningType.query.filter(
        EarningType.code.notin_(['BASIC', 'HOUSE_ALLOW', 'TRANS_ALLOW', 'OTHER_ALLOW'])
    ).all()
    
    deduction_types = DeductionType.query.filter(
        DeductionType.code.notin_(['PAYE', 'NSSF', 'SHA'])
    ).all()
    
    # Handle POST requests for adding/removing items
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_earning':
            earning_type_id = request.form.get('earning_type_id', type=int)
            amount = request.form.get('amount', type=float)
            description = request.form.get('description', '').strip()
            
            if earning_type_id and amount and amount > 0:
                earning = PayslipEarning(
                    payslip_id=payslip.id,
                    earning_type_id=earning_type_id,
                    amount=amount,
                    description=description or 'Additional earning'
                )
                db.session.add(earning)
                # Flush to get the earning into the session identity map
                db.session.flush()
                
                # Refresh the payslip to include the new earning
                db.session.refresh(payslip, attribute_names=['earnings', 'deductions'])
                
                # Now calculate totals
                payslip.calculate_totals()
                db.session.commit()
                flash('Earning added successfully', 'success')
            else:
                flash('Invalid earning data', 'error')
                
        elif action == 'add_deduction':
            deduction_type_id = request.form.get('deduction_type_id', type=int)
            amount = request.form.get('amount', type=float)
            description = request.form.get('description', '').strip()
            
            if deduction_type_id and amount and amount > 0:
                deduction = PayslipDeduction(
                    payslip_id=payslip.id,
                    deduction_type_id=deduction_type_id,
                    amount=amount,
                    description=description or 'Additional deduction'
                )
                db.session.add(deduction)
                # Flush to get the deduction into the session identity map
                db.session.flush()
                
                # Refresh the payslip to include the new deduction
                db.session.refresh(payslip, attribute_names=['earnings', 'deductions'])
                
                # Now calculate totals
                payslip.calculate_totals()
                db.session.commit()
                flash('Deduction added successfully', 'success')
            else:
                flash('Invalid deduction data', 'error')
                
        elif action == 'delete_earning':
            earning_id = request.form.get('earning_id', type=int)
            if earning_id:
                earning = PayslipEarning.query.get_or_404(earning_id)
                if earning.payslip_id == payslip.id:
                    db.session.delete(earning)
                    # Flush to remove the earning from the session
                    db.session.flush()
                    
                    # Refresh the payslip to reflect the deletion
                    db.session.refresh(payslip, attribute_names=['earnings', 'deductions'])
                    
                    payslip.calculate_totals()
                    db.session.commit()
                    flash('Earning removed successfully', 'success')
                    
        elif action == 'delete_deduction':
            deduction_id = request.form.get('deduction_id', type=int)
            if deduction_id:
                deduction = PayslipDeduction.query.get_or_404(deduction_id)
                if deduction.payslip_id == payslip.id:
                    db.session.delete(deduction)
                    # Flush to remove the deduction from the session
                    db.session.flush()
                    
                    # Refresh the payslip to reflect the deletion
                    db.session.refresh(payslip, attribute_names=['earnings', 'deductions'])
                    
                    payslip.calculate_totals()
                    db.session.commit()
                    flash('Deduction removed successfully', 'success')
        
        return redirect(url_for('hr_web.view_payslip_details', payslip_id=payslip_id))
    
    # Calculate totals if needed
    if payslip.gross_earnings == 0 and payslip.basic_salary > 0:
        payslip.calculate_totals()
        db.session.commit()
    
    return render_template('payslip_details.html', 
                         payslip=payslip,
                         earning_types=earning_types,
                         deduction_types=deduction_types)

from weasyprint import HTML
from datetime import datetime

@hr_web_bp.route('/payroll/payslip/<int:payslip_id>/download')
@login_required
def download_payslip(payslip_id):
    """Download payslip as PDF using WeasyPrint"""
    from sqlalchemy.orm import joinedload
    
    # Get payslip with all related data
    payslip = Payslip.query.options(
        joinedload(Payslip.employee).joinedload(User.payroll_info),
        joinedload(Payslip.payroll).joinedload(Payroll.period),
        joinedload(Payslip.earnings).joinedload(PayslipEarning.earning_type),
        joinedload(Payslip.deductions).joinedload(PayslipDeduction.deduction_type)
    ).filter(Payslip.id == payslip_id).first_or_404()
    
    try:
        # Render HTML template
        html = render_template(
            'payslip_pdf_template.html',
            payslip=payslip,
            now=datetime.now()
        )
        
        # Generate PDF
        pdf = HTML(string=html).write_pdf()
        
        # Create filename
        filename = f"payslip_{payslip.employee.full_name.replace(' ', '_')}_{payslip.payroll.period.start_date.strftime('%Y%m')}.pdf"
        
        # Return PDF as response
        from flask import Response
        response = Response(
            pdf,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Length': len(pdf)
            }
        )
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error generating PDF: {str(e)}")
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('hr_web.view_payslip_details', payslip_id=payslip_id))



@hr_web_bp.route('/payroll/payslips/<int:id>', methods=['GET'])
@login_required
def view_payslip(id):
    payslip = Payslip.query.get_or_404(id)
    return render_template('payslip_detail.html', payslip=payslip)

@hr_web_bp.route('/payroll/payslips/<int:id>/mark_paid', methods=['POST'])
@login_required
def mark_payslip_paid(id):
    payslip = Payslip.query.get_or_404(id)
    try:
        data = request.get_json()
        payslip.is_paid = True
        payslip.paid_at = datetime.utcnow()
        payslip.payment_reference = data.get('reference', '')
        db.session.commit()
        return jsonify({'success': True, 'message': 'Payslip marked as paid'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

# ========================
# PAYROLL ADJUSTMENTS
# ========================

@hr_web_bp.route('/payroll/adjustments', methods=['GET', 'POST'])
@login_required
def payroll_adjustments():
    # Get all active employees and payroll periods
    employees = User.query.filter_by(is_active=True).all()
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            adjustment = PayrollAdjustment(
                employee_id=data['employee_id'],
                period_id=data['period_id'],
                type=data['type'],
                amount=Decimal(data['amount']),
                description=data['description'],
                created_by=current_user.id
            )
            db.session.add(adjustment)
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': 'Adjustment created',
                'adjustment': {
                    'id': adjustment.id,
                    'employee_name': adjustment.employee.full_name,
                    'period': f"{adjustment.period.start_date.strftime('%d %b')} - {adjustment.period.end_date.strftime('%d %b %Y')}",
                    'type': adjustment.type,
                    'description': adjustment.description,
                    'amount': float(adjustment.amount),
                    'created_at': adjustment.created_at.strftime('%d %b %Y'),
                    'status': 'Pending'
                }
            }), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 400

    # GET: List adjustments with filters
    employee_id = request.args.get('employee_id')
    period_id = request.args.get('period_id')
    status = request.args.get('status', 'pending')  # pending/approved
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = PayrollAdjustment.query.options(
        db.joinedload(PayrollAdjustment.employee),
        db.joinedload(PayrollAdjustment.period)
    )
    
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if period_id:
        query = query.filter_by(period_id=period_id)
    if status == 'pending':
        query = query.filter_by(approved_at=None)
    elif status == 'approved':
        query = query.filter(PayrollAdjustment.approved_at.isnot(None))
    
    adjustments = query.order_by(PayrollAdjustment.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    # Preserve filters in pagination
    filters = {
        'employee_id': employee_id,
        'period_id': period_id,
        'status': status
    }

    return render_template(
        'payroll_adjustments.html',
        adjustments=adjustments,
        employees=employees,
        payroll_periods=payroll_periods,
        current_page=page,
        total_pages=adjustments.pages,
            filters=filters  # Pass filters to template

    )

@hr_web_bp.route('/payroll/adjustments/<int:id>/approve', methods=['POST'])
@login_required
def approve_adjustment(id):
    adjustment = PayrollAdjustment.query.options(
        db.joinedload(PayrollAdjustment.employee),
        db.joinedload(PayrollAdjustment.period)
    ).get_or_404(id)
    
    try:
        adjustment.approved_by = current_user.id
        adjustment.approved_at = datetime.utcnow()
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': 'Adjustment approved',
            'adjustment': {
                'id': adjustment.id,
                'approved_at': adjustment.approved_at.strftime('%d %b %Y %H:%M')
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@hr_web_bp.route('/payroll/adjustments/<int:id>', methods=['DELETE'])
@login_required
def delete_adjustment(id):
    adjustment = PayrollAdjustment.query.get_or_404(id)
    
    try:
        db.session.delete(adjustment)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Adjustment deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
# ===================
# EMPLOYEE LOANS
# ===================

@hr_web_bp.route('/payroll/loans', methods=['GET', 'POST'])
@login_required
def payroll_loans():
    if request.method == 'POST':
        try:
            data = request.get_json()
            employee_id = data['employee_id']
            loan_amount = Decimal(data['loan_amount'])
            monthly_deduction = Decimal(data['monthly_deduction'])
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            
            # Create the loan
            loan = PayrollLoan(
                employee_id=employee_id,
                loan_amount=loan_amount,
                balance=loan_amount,
                monthly_deduction=monthly_deduction,
                start_date=start_date,
                end_date=end_date,
                is_active=True
            )
            db.session.add(loan)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Loan created'}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 400

    # GET: List loans with filters
    from sqlalchemy.orm import joinedload
    
    employee_id = request.args.get('employee_id')
    status = request.args.get('status', 'active')  # active/closed
    
    query = PayrollLoan.query
    
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'closed':
        query = query.filter_by(is_active=False)
    
    # FIXED: Properly load relationships
    loans = query.options(
        joinedload(PayrollLoan.employee).joinedload(User.payroll_info),
        joinedload(PayrollLoan.repayments)
    ).order_by(PayrollLoan.created_at.desc()).all()
    
    # Get recent repayments for display
    recent_repayments = []
    for loan in loans:
        if loan.repayments:  # This should now be properly loaded
            for repayment in loan.repayments:
                recent_repayments.append({
                    'loan_id': loan.id,
                    'loan': loan,  # Pass the loan object
                    'repayment': repayment,  # Pass the repayment object
                    'payment_date': repayment.payment_date,
                    'amount': repayment.amount,
                    'payslip_id': repayment.payslip_id,
                    'employee_name': loan.employee.full_name if loan.employee else 'Unknown',
                    'staff_no': loan.employee.payroll_info.staff_no if loan.employee and loan.employee.payroll_info else 'N/A'
                })
    
    # Sort by payment date (newest first) and take only 5
    recent_repayments.sort(key=lambda x: x['payment_date'], reverse=True)
    recent_repayments = recent_repayments[:5]
    
    # Get active employees with payroll info for the dropdown
    employees = User.query.filter_by(is_active=True)\
        .join(EmployeePayrollInfo, isouter=True)\
        .add_columns(
            User.id,
            User.full_name,
            EmployeePayrollInfo.staff_no
        )\
        .order_by(User.full_name)\
        .all()
    
    # Format employees data for the template
    employees_list = []
    for employee in employees:
        employees_list.append({
            'id': employee.id,
            'full_name': employee.full_name,
            'staff_no': employee.staff_no or f"EMP{employee.id:04d}"
        })
    
    return render_template('payroll_loans.html', 
                         loans=loans, 
                         employees=employees_list,
                         recent_repayments=recent_repayments)  # Pass the prepared data


@hr_web_bp.route('/payroll/loan/<int:loan_id>')
@login_required
def view_loan(loan_id):
    """View detailed information about a specific loan"""
    from sqlalchemy.orm import joinedload
    
    # Get loan with all related data
    loan = PayrollLoan.query.options(
        joinedload(PayrollLoan.employee).joinedload(User.payroll_info),
        joinedload(PayrollLoan.repayments)  # Remove the nested joinedload for payslip
    ).get_or_404(loan_id)
    
    # Get repayment statistics
    total_paid = db.session.query(db.func.sum(LoanRepayment.amount)).filter(
        LoanRepayment.loan_id == loan_id
    ).scalar() or Decimal('0')
    
    remaining_balance = loan.balance
    percentage_paid = (total_paid / loan.loan_amount * 100) if loan.loan_amount > 0 else 0
    
    # Get recent repayments with payslip info if needed
    recent_repayments = LoanRepayment.query.filter_by(loan_id=loan_id)\
        .order_by(LoanRepayment.payment_date.desc())\
        .limit(10).all()
    
    # If you need payslip info for each repayment, you can fetch it separately
    # Or use a different approach with joinedload
    
    # Get payroll periods for context
    payroll_periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).limit(6).all()
    
    return render_template('view_loan.html',
                         loan=loan,
                         total_paid=total_paid,
                         remaining_balance=remaining_balance,
                         percentage_paid=percentage_paid,
                         recent_repayments=recent_repayments,
                         date=datetime.now().date(),
                         payroll_periods=payroll_periods,)

@hr_web_bp.route('/payroll/loan/<int:loan_id>/record-payment', methods=['GET', 'POST'])
@login_required
def record_loan_payment(loan_id):
    """Record a manual loan payment (outside payroll)"""
    loan = PayrollLoan.query.get_or_404(loan_id)
    
    if request.method == 'GET':
        return render_template('record_loan_payment.html', loan=loan)
    
    elif request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            amount = Decimal(data['amount'])
            payment_date = datetime.strptime(data['payment_date'], '%Y-%m-%d').date()
            payment_method = data.get('payment_method', 'Manual Payment')
            reference = data.get('reference_number', '')
            description = data.get('description', '')
            
            if amount <= 0:
                return jsonify({'success': False, 'message': 'Amount must be positive'}), 400
            
            if amount > loan.balance:
                return jsonify({'success': False, 'message': 'Payment amount exceeds loan balance'}), 400
            
            # Create repayment record
            repayment = LoanRepayment(
                loan_id=loan.id,
                amount=amount,
                payment_date=payment_date,
                payment_method=payment_method,
                reference_number=reference,
                description=description or 'Manual loan payment',
                created_by=current_user.id
            )
            db.session.add(repayment)
            
            # Update loan balance
            loan.balance -= amount
            
            # Mark as inactive if fully paid
            if loan.balance <= 0:
                loan.is_active = False
                loan.balance = Decimal('0')
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Loan payment of KES {amount} recorded successfully',
                'loan': {
                    'id': loan.id,
                    'balance': str(loan.balance),
                    'is_active': loan.is_active
                }
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 400


@hr_web_bp.route('/payroll/loan/<int:loan_id>/close', methods=['POST'])
@login_required
def close_loan(loan_id):
    """Close a loan (mark as inactive)"""
    loan = PayrollLoan.query.get_or_404(loan_id)
    
    try:
        loan.is_active = False
        loan.balance = Decimal('0')  # Write off any remaining balance
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Loan closed successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@hr_web_bp.route('/payroll/loan/<int:loan_id>/reopen', methods=['POST'])
@login_required
def reopen_loan(loan_id):
    """Reopen a closed loan"""
    loan = PayrollLoan.query.get_or_404(loan_id)
    
    try:
        loan.is_active = True
        # You might want to adjust the balance based on your business logic
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Loan reopened successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

def update_existing_payslips_with_loan(employee_id, loan_id, monthly_deduction, deduction_type_id):
    """Update existing payslips with loan deduction and recalculate totals"""
    
    # Get current and future payroll periods
    today = date.today()
    future_periods = PayrollPeriod.query.filter(
        PayrollPeriod.end_date >= today
    ).all()
    
    for period in future_periods:
        # Check if payroll exists for this period
        payroll = Payroll.query.filter_by(period_id=period.id).first()
        if payroll:
            # Get employee's payslip for this period
            payslip = Payslip.query.filter_by(
                payroll_id=payroll.id,
                employee_id=employee_id
            ).first()
            
            if payslip:
                # Check if loan deduction already exists
                existing_loan_deduction = PayslipDeduction.query.filter_by(
                    payslip_id=payslip.id,
                    deduction_type_id=deduction_type_id
                ).first()
                
                if not existing_loan_deduction:
                    # Add loan deduction to payslip
                    loan_deduction = PayslipDeduction(
                        payslip_id=payslip.id,
                        deduction_type_id=deduction_type_id,
                        amount=monthly_deduction,
                        description=f"Loan #{loan_id} repayment"
                    )
                    db.session.add(loan_deduction)
                    
                    # Recalculate totals
                    payslip.calculate_totals()
                    
                    # Update payroll totals
                    payroll.total_deductions = db.session.query(
                        db.func.sum(Payslip.total_deductions)
                    ).filter(Payslip.payroll_id == payroll.id).scalar() or 0
                    
                    payroll.total_net = db.session.query(
                        db.func.sum(Payslip.net_pay)
                    ).filter(Payslip.payroll_id == payroll.id).scalar() or 0

@hr_web_bp.route('/payroll/loan-repayments', methods=['GET'])
@login_required
def loan_repayments():
    """View all loan repayments"""
    try:
        from sqlalchemy.orm import joinedload
        
        # Get query parameters for filtering
        loan_id = request.args.get('loan_id', type=int)
        employee_id = request.args.get('employee_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        payment_type = request.args.get('type')  # payroll, manual
        
        # Build query
        query = LoanRepayment.query.options(
            joinedload(LoanRepayment.loan).joinedload(PayrollLoan.employee)
        ).order_by(LoanRepayment.payment_date.desc(), LoanRepayment.created_at.desc())
        
        # Apply filters
        if loan_id:
            query = query.filter_by(loan_id=loan_id)
        
        if employee_id:
            query = query.join(LoanRepayment.loan).filter(PayrollLoan.employee_id == employee_id)
        
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(LoanRepayment.payment_date >= start_date_obj)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(LoanRepayment.payment_date <= end_date_obj)
            except ValueError:
                pass
        
        if payment_type == 'payroll':
            query = query.filter(LoanRepayment.payslip_id.isnot(None))
        elif payment_type == 'manual':
            query = query.filter(LoanRepayment.payslip_id.is_(None))
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Paginate results
        repayments = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Calculate totals
        total_amount = db.session.query(db.func.sum(LoanRepayment.amount)).filter(
            LoanRepayment.id.in_([r.id for r in repayments.items])
        ).scalar() or 0
        
        # Get unique loans for filter dropdown
        loans = PayrollLoan.query.filter_by(is_active=True).order_by(PayrollLoan.id.desc()).limit(50).all()
        
        # Get active employees for filter dropdown
        active_employees = User.query.filter_by(is_active=True).order_by(User.full_name).all()
        
        return render_template('hr/loan_repayments.html',
                             repayments=repayments,
                             total_amount=float(total_amount),
                             loans=loans,
                             employees=active_employees,
                             current_filters={
                                 'loan_id': loan_id,
                                 'employee_id': employee_id,
                                 'start_date': start_date,
                                 'end_date': end_date,
                                 'type': payment_type
                             })
                             
    except Exception as e:
        current_app.logger.error(f"Error loading loan repayments: {str(e)}")
        flash('Error loading loan repayments', 'error')
        return redirect(url_for('hr_web.payroll_loans'))


@hr_web_bp.route('/payroll/loan/<int:loan_id>/add-repayment', methods=['POST'])
@login_required
def add_loan_repayment(loan_id):
    """Add manual repayment to a loan"""
    try:
        loan = PayrollLoan.query.get_or_404(loan_id)
        
        if not loan.is_active:
            return jsonify({
                'success': False,
                'message': 'Cannot add repayment to closed loan'
            }), 400
        
        data = request.get_json()
        amount = Decimal(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({
                'success': False,
                'message': 'Amount must be greater than 0'
            }), 400
        
        if amount > loan.balance:
            return jsonify({
                'success': False,
                'message': f'Amount exceeds loan balance (KES {loan.balance:,.2f})'
            }), 400
        
        # Create repayment
        repayment = LoanRepayment(
            loan_id=loan_id,
            amount=amount,
            payment_date=data.get('payment_date') or date.today(),
            description=data.get('description', 'Manual repayment'),
            created_by=current_user.id
        )
        
        # Update loan balance
        loan.balance -= amount
        
        # If balance reaches zero, mark loan as closed
        if loan.balance <= 0:
            loan.balance = Decimal('0.00')
            loan.is_active = False
            loan.end_date = date.today()
        
        db.session.add(repayment)
        db.session.commit()
        
        # Log the activity
        current_app.logger.info(
            f"Manual repayment added: Loan #{loan_id}, Amount KES {amount}, "
            f"By User {current_user.id}, New Balance KES {loan.balance}"
        )
        
        return jsonify({
            'success': True,
            'message': 'Repayment added successfully',
            'repayment': {
                'id': repayment.id,
                'amount': float(repayment.amount),
                'payment_date': repayment.payment_date.strftime('%Y-%m-%d'),
                'description': repayment.description
            },
            'loan': {
                'balance': float(loan.balance),
                'is_active': loan.is_active
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding loan repayment: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to add repayment: {str(e)}'
        }), 500


@hr_web_bp.route('/payroll/loan/<int:loan_id>/close', methods=['POST'])
@login_required
def close_payroll_loan(loan_id):
    """Close a payroll loan (mark as fully repaid)"""
    try:
        loan = PayrollLoan.query.get_or_404(loan_id)
        
        if not loan.is_active:
            return jsonify({
                'success': False,
                'message': 'Loan is already closed'
            }), 400
        
        # Check if balance is zero
        if loan.balance > 0:
            return jsonify({
                'success': False,
                'message': f'Loan has remaining balance of KES {loan.balance:,.2f}. Cannot close.'
            }), 400
        
        # Update loan
        loan.is_active = False
        loan.end_date = date.today()
        loan.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        current_app.logger.info(f"Loan #{loan_id} closed by User {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Loan closed successfully',
            'loan': {
                'id': loan.id,
                'is_active': loan.is_active,
                'end_date': loan.end_date.strftime('%Y-%m-%d')
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error closing loan: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to close loan: {str(e)}'
        }), 500


@hr_web_bp.route('/payroll/loan/<int:loan_id>', methods=['DELETE'])
@login_required
def delete_payroll_loan(loan_id):
    """Delete a payroll loan (with validation)"""
    try:
        loan = PayrollLoan.query.get_or_404(loan_id)
        
        # Check if loan has repayments
        if loan.repayments and len(loan.repayments) > 0:
            return jsonify({
                'success': False,
                'message': 'Cannot delete loan with repayment history'
            }), 400
        
        db.session.delete(loan)
        db.session.commit()
        
        current_app.logger.info(f"Loan #{loan_id} deleted by User {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Loan deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting loan: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to delete loan: {str(e)}'
        }), 500


@hr_web_bp.route('/payroll/loan/<int:loan_id>/details', methods=['GET'])
@login_required
def get_loan_details(loan_id):
    """Get detailed information about a loan"""
    try:
        from sqlalchemy.orm import joinedload
        
        loan = PayrollLoan.query.options(
            joinedload(PayrollLoan.employee).joinedload(User.payroll_info),
            joinedload(PayrollLoan.repayments).joinedload(LoanRepayment.payslip)
        ).get_or_404(loan_id)
        
        # Calculate repayment statistics
        total_paid = Decimal('0.00')
        payroll_deductions = Decimal('0.00')
        manual_repayments = Decimal('0.00')
        
        repayments_list = []
        for repayment in loan.repayments:
            total_paid += repayment.amount
            if repayment.payslip_id:
                payroll_deductions += repayment.amount
            else:
                manual_repayments += repayment.amount
            
            repayments_list.append({
                'id': repayment.id,
                'amount': float(repayment.amount),
                'payment_date': repayment.payment_date.strftime('%Y-%m-%d'),
                'description': repayment.description or '',
                'payslip_id': repayment.payslip_id,
                'created_at': repayment.created_at.strftime('%Y-%m-%d %H:%M') if repayment.created_at else ''
            })
        
        # Calculate remaining months
        today = date.today()
        if loan.start_date <= today <= loan.end_date:
            # Calculate months remaining from today
            months_remaining = ((loan.end_date.year - today.year) * 12 + 
                               loan.end_date.month - today.month)
            months_remaining = max(0, months_remaining)
        else:
            months_remaining = 0
        
        # Calculate expected completion date based on current rate
        if loan.balance > 0 and loan.monthly_deduction > 0:
            months_to_complete = (loan.balance / loan.monthly_deduction).quantize(Decimal('1'), rounding='ROUND_UP')
            expected_completion = today + relativedelta(months=+int(months_to_complete))
            expected_completion_str = expected_completion.strftime('%d %b %Y')
        else:
            expected_completion_str = loan.end_date.strftime('%d %b %Y')
        
        return jsonify({
            'success': True,
            'loan': {
                'id': loan.id,
                'employee_name': loan.employee.full_name if loan.employee else 'Unknown',
                'staff_no': loan.employee.payroll_info.staff_no if loan.employee and loan.employee.payroll_info else 'N/A',
                'loan_amount': float(loan.loan_amount),
                'balance': float(loan.balance),
                'monthly_deduction': float(loan.monthly_deduction),
                'start_date': loan.start_date.strftime('%Y-%m-%d'),
                'end_date': loan.end_date.strftime('%Y-%m-%d'),
                'is_active': loan.is_active,
                'created_at': loan.created_at.strftime('%Y-%m-%d %H:%M') if loan.created_at else '',
                'progress_percentage': float((1 - loan.balance / loan.loan_amount) * 100) if loan.loan_amount > 0 else 100,
                'total_paid': float(total_paid),
                'payroll_deductions': float(payroll_deductions),
                'manual_repayments': float(manual_repayments),
                'months_remaining': months_remaining,
                'expected_completion': expected_completion_str
            },
            'repayments': repayments_list
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting loan details: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to load loan details: {str(e)}'
        }), 500


@hr_web_bp.route('/payroll/loans/export', methods=['GET'])
@login_required
def export_loans():
    """Export loans data to CSV/Excel"""
    try:
        from sqlalchemy.orm import joinedload
        
        # Get filter parameters
        status = request.args.get('status', 'active')
        employee_id = request.args.get('employee_id', type=int)
        
        # Build query
        query = PayrollLoan.query.options(
            joinedload(PayrollLoan.employee).joinedload(User.payroll_info)
        )
        
        if status == 'active':
            query = query.filter_by(is_active=True)
        elif status == 'closed':
            query = query.filter_by(is_active=False)
        
        if employee_id:
            query = query.filter_by(employee_id=employee_id)
        
        loans = query.order_by(PayrollLoan.start_date.desc()).all()
        
        # Create CSV content
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Loan ID', 'Employee Name', 'Staff No', 'Loan Amount',
            'Balance', 'Monthly Deduction', 'Start Date', 'End Date',
            'Status', 'Progress %', 'Total Paid'
        ])
        
        # Write data
        for loan in loans:
            total_paid = loan.loan_amount - loan.balance
            progress = ((1 - loan.balance / loan.loan_amount) * 100) if loan.loan_amount > 0 else 100
            
            writer.writerow([
                loan.id,
                loan.employee.full_name if loan.employee else 'Unknown',
                loan.employee.payroll_info.staff_no if loan.employee and loan.employee.payroll_info else 'N/A',
                float(loan.loan_amount),
                float(loan.balance),
                float(loan.monthly_deduction),
                loan.start_date.strftime('%Y-%m-%d'),
                loan.end_date.strftime('%Y-%m-%d'),
                'Active' if loan.is_active else 'Closed',
                f"{progress:.1f}%",
                float(total_paid)
            ])
        
        # Return CSV file
        from flask import Response
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=loans_export_{date.today()}.csv'
            }
        )
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting loans: {str(e)}")
        flash('Error exporting loans data', 'error')
        return redirect(url_for('hr_web.payroll_loans'))
# ========================
# PAYROLL SETTINGS ROUTES
# ========================

@hr_web_bp.route('/payroll/settings', methods=['GET', 'POST'])
@login_required
def payroll_settings():
    # Earnings and Deductions Configuration
    earning_types = EarningType.query.all()
    deduction_types = DeductionType.query.all()
    
    # Statutory Settings
    paye_bands = PAYEBand.query.order_by(PAYEBand.lower_bound).all()
    nhif_rates = NHIFRate.query.order_by(NHIFRate.lower_bound).all()
    nssf_rates = NSSFRate.query.all()
    
    return render_template(
        'payroll_settings.html',
        earning_types=earning_types,
        deduction_types=deduction_types,
        paye_bands=paye_bands,
        nhif_rates=nhif_rates,
        nssf_rates=nssf_rates
    )

@hr_web_bp.route('/payroll/earning-types', methods=['POST', 'PUT'])
def manage_earning_type():
    try:
        data = request.get_json()
        
        if 'id' in data:  # Update existing
            earning_type = EarningType.query.get(data['id'])
            if not earning_type:
                return jsonify({'success': False, 'message': 'Type not found'}), 404
                
            earning_type.name = data['name']
            earning_type.code = data['code']
            earning_type.description = data.get('description', '')
            earning_type.is_taxable = data.get('is_taxable', True)
            earning_type.is_statutory = data.get('is_statutory', False)
            earning_type.is_recurring = data.get('is_recurring', True)
            
        else:  # Create new
            earning_type = EarningType(
                name=data['name'],
                code=data['code'],
                description=data.get('description', ''),
                is_taxable=data.get('is_taxable', True),
                is_statutory=data.get('is_statutory', False),
                is_recurring=data.get('is_recurring', True)
            )
            db.session.add(earning_type)
            
        db.session.commit()
        return jsonify({'success': True, 'message': 'Earning type saved'})
        
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Database error: ' + str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@hr_web_bp.route('/payroll/deduction-types', methods=['POST', 'PUT'])
def manage_deduction_type():
    try:
        data = request.get_json()
        
        if 'id' in data:  # Update existing
            deduction_type = DeductionType.query.get(data['id'])
            if not deduction_type:
                return jsonify({'success': False, 'message': 'Type not found'}), 404
                
            deduction_type.name = data['name']
            deduction_type.code = data['code']
            deduction_type.description = data.get('description', '')
            deduction_type.is_statutory = data.get('is_statutory', False)
            deduction_type.is_voluntary = data.get('is_voluntary', False)
            
        else:  # Create new
            deduction_type = DeductionType(
                name=data['name'],
                code=data['code'],
                description=data.get('description', ''),
                is_statutory=data.get('is_statutory', False),
                is_voluntary=data.get('is_voluntary', False)
            )
            db.session.add(deduction_type)
            
        db.session.commit()
        return jsonify({'success': True, 'message': 'Deduction type saved'})
        
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Database error: ' + str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@hr_web_bp.route('/payroll/settings/statutory', methods=['POST'])
@login_required
def update_statutory_rates():
    try:
        data = request.get_json()
        effective_date = datetime.strptime(data['effective_date'], '%Y-%m-%d').date()
        
        # Validate required fields
        required_fields = {
            'paye_bands': ['lower_bound', 'rate', 'deduction_amount'],
            'nhif_rates': ['lower_bound', 'amount'],
            'nssf_rates': ['tier', 'lower_bound', 'employee_rate', 'employer_rate']
        }
        
        for rate_type, fields in required_fields.items():
            if rate_type in data:
                for i, rate in enumerate(data[rate_type]):
                    for field in fields:
                        if field not in rate:
                            return jsonify({
                                'success': False,
                                'message': f'Missing {field} in {rate_type} at index {i}'
                            }), 400
        
        # Update PAYE Bands
        if 'paye_bands' in data:
            PAYEBand.query.delete()  # Remove old bands
            for band in data['paye_bands']:
                db.session.add(PAYEBand(
                    lower_bound=Decimal(band['lower_bound']),
                    upper_bound=Decimal(band['upper_bound']) if band['upper_bound'] else None,
                    rate=Decimal(band['rate']),
                    deduction_amount=Decimal(band['deduction_amount']),
                    effective_date=effective_date
                ))
        
        # Update NHIF Rates
        if 'nhif_rates' in data:
            NHIFRate.query.delete()
            for rate in data['nhif_rates']:
                db.session.add(NHIFRate(
                    lower_bound=Decimal(rate['lower_bound']),
                    upper_bound=Decimal(rate['upper_bound']) if rate['upper_bound'] else None,
                    amount=Decimal(rate['amount']),
                    effective_date=effective_date
                ))
        
        # Update NSSF Rates
        if 'nssf_rates' in data:
            NSSFRate.query.delete()
            for rate in data['nssf_rates']:
                db.session.add(NSSFRate(
                    tier=rate['tier'],
                    lower_bound=Decimal(rate['lower_bound']),
                    upper_bound=Decimal(rate['upper_bound']) if rate['upper_bound'] else None,
                    employee_rate=Decimal(rate['employee_rate']),
                    employer_rate=Decimal(rate['employer_rate']),
                    effective_date=effective_date
                ))
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Statutory rates updated'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Statutory update error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 400

# =====================
# PAYROLL REPORTS
# =====================

@hr_web_bp.route('/payroll/reports', methods=['GET'])
@login_required
def payroll_reports():
    period_id = request.args.get('period_id')
    report_type = request.args.get('type')
    
    if period_id and report_type:
        # Generate and return report (implementation depends on reporting library)
        pass
    
    # List available reports
    periods = PayrollPeriod.query.order_by(PayrollPeriod.start_date.desc()).all()
    existing_reports = PayrollReport.query.join(PayrollPeriod).order_by(
        PayrollPeriod.start_date.desc()
    ).all()
    
    return render_template(
        'payroll_reports.html', 
        periods=periods,
        reports=existing_reports
    )

@hr_web_bp.route('/payroll/reports/generate', methods=['POST'])
@login_required
def generate_report():
    try:
        data = request.get_json()
        period_id = data['period_id']
        report_type = data['report_type']
        
        # Generate report file (implementation specific)
        # This would typically use a library like ReportLab, XlsxWriter, etc.
        file_path = f"reports/payroll_{report_type}_{period_id}_{datetime.now().timestamp()}.pdf"
        
        # Save report metadata
        report = PayrollReport(
            period_id=period_id,
            report_type=report_type,
            file_path=file_path,
            generated_by=current_user.id
        )
        db.session.add(report)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'report_id': report.id,
            'download_url': f"/download/{file_path}"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500



# routes.py (updated attendance route)
@hr_web_bp.route('/attendance')
@login_required
def attendance_tracking():
    # Fetch filter parameters
    date_filter = request.args.get('date')
    department_id = request.args.get('department_id')
    employee_id = request.args.get('employee_id')
    
    # Build query
    query = AttendanceRecord.query \
        .join(User, AttendanceRecord.employee_id == User.id) \
        .join(Department, User.department_id == Department.id) \
        .options(joinedload(AttendanceRecord.employee), 
                joinedload(AttendanceRecord.shift),
                joinedload(AttendanceRecord.employee).joinedload(User.department))
    
    # Apply filters
    if date_filter:
        query = query.filter(AttendanceRecord.date == date_filter)
    if department_id:
        query = query.filter(User.department_id == department_id)
    if employee_id:
        query = query.filter(AttendanceRecord.employee_id == employee_id)
    
    records = query.order_by(AttendanceRecord.date.desc()).all()
    
    # Get filter dropdown data
    departments = Department.query.all()
    employees = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    
    return render_template(
        'manage_attendance.html',
        records=records,
        departments=departments,
        employees=employees,

    )



# =============================
# DUTY ROTA MANAGEMENT ROUTES
# =============================

@hr_web_bp.route('/duty-rota-management', methods=['GET'])
@login_required
def duty_rota_management():
    # Get all departments, shifts, and active rotas
    departments = Department.query.all()
    shifts = DutyShift.query.all()
    active_rotas = DutyRota.query.filter_by(is_active=True).all()
    
    # Get current date and date range for calendar (current week)
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    # Get assignments for the current week
    assignments = DutyAssignment.query.filter(
        DutyAssignment.date >= start_of_week,
        DutyAssignment.date <= end_of_week
    ).options(
        db.joinedload(DutyAssignment.employee),
        db.joinedload(DutyAssignment.shift)
    ).all()
    
    # Group assignments by date for calendar view
    assignments_by_date = {}
    for assignment in assignments:
        date_str = assignment.date.isoformat()
        if date_str not in assignments_by_date:
            assignments_by_date[date_str] = []
        assignments_by_date[date_str].append(assignment)
    
    return render_template(
        'duty_rota_management.html',
        departments=departments,
        shifts=shifts,
        rotas=active_rotas,
        assignments_by_date=assignments_by_date,
        start_date=start_of_week,
        end_date=end_of_week,
        timedelta=timedelta,
        date=date
    )

@hr_web_bp.route('/duty-rota-management/create-rota', methods=['POST'])
@login_required
def create_rota():
    try:
        data = request.form
        rota = DutyRota(
            department_id=data['department_id'],
            name=data['name'],
            description=data.get('description', ''),
            start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
            created_by=current_user.id
        )
        db.session.add(rota)
        db.session.commit()
        flash('Rota created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating rota: {str(e)}', 'danger')
    return redirect(url_for('hr_web.duty_rota_management'))

@hr_web_bp.route('/duty-rota-management/assign-shift', methods=['POST'])
@login_required
def assign_shift():
    try:
        data = request.form
        assignment = DutyAssignment(
            rota_id=data['rota_id'],
            employee_id=data['employee_id'],
            shift_id=data['shift_id'],
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            notes=data.get('notes', '')
        )
        db.session.add(assignment)
        db.session.commit()
        flash('Shift assigned successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error assigning shift: {str(e)}', 'danger')
    return redirect(url_for('hr_web.duty_rota_management'))

@hr_web_bp.route('/duty-rota-management/create-shift', methods=['POST'])
@login_required
def create_shift():
    try:
        data = request.form
        shift = DutyShift(
            name=data['name'],
            code=data['code'],
            shift_type=data['shift_type'],
            start_time=datetime.strptime(data['start_time'], '%H:%M').time(),
            end_time=datetime.strptime(data['end_time'], '%H:%M').time(),
            description=data.get('description', ''),
            color=data['color']
        )
        db.session.add(shift)
        db.session.commit()
        flash('Shift type created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating shift type: {str(e)}', 'danger')
    return redirect(url_for('hr_web.duty_rota_management'))

@hr_web_bp.route('/duty-rota-management/record-attendance', methods=['POST'])
@login_required
def record_attendance():
    try:
        data = request.form
        record = AttendanceRecord(
            employee_id=data['employee_id'],
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            shift_id=data.get('shift_id'),
            status=data['status'],
            clock_in=datetime.strptime(data['clock_in'], '%H:%M') if data.get('clock_in') else None,
            clock_out=datetime.strptime(data['clock_out'], '%H:%M') if data.get('clock_out') else None,
            late_minutes=data.get('late_minutes', 0),
            overtime_minutes=data.get('overtime_minutes', 0),
            notes=data.get('notes', ''),
            recorded_by=current_user.id
        )
        db.session.add(record)
        db.session.commit()
        flash('Attendance recorded successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error recording attendance: {str(e)}', 'danger')
    return redirect(url_for('hr_web.duty_rota_management'))

@hr_web_bp.route('/duty-rota-management/api/rotas/<int:rota_id>', methods=['GET'])
@login_required
def get_rota_assignments(rota_id):
    rota = DutyRota.query.get_or_404(rota_id)
    assignments = DutyAssignment.query.filter_by(rota_id=rota_id).options(
        db.joinedload(DutyAssignment.employee),
        db.joinedload(DutyAssignment.shift)
    ).all()
    
    assignments_data = [{
        'id': a.id,
        'date': a.date.isoformat(),
        'employee_id': a.employee_id,
        'employee_name': a.employee.full_name,
        'shift_id': a.shift_id,
        'shift_name': a.shift.name,
        'notes': a.notes
    } for a in assignments]
    
    return jsonify({
        'rota': {
            'id': rota.id,
            'name': rota.name,
            'department_id': rota.department_id,
            'department_name': rota.department.name,
            'start_date': rota.start_date.isoformat(),
            'end_date': rota.end_date.isoformat(),
            'description': rota.description
        },
        'assignments': assignments_data
    })

@hr_web_bp.route('/duty-rota-management/api/employees', methods=['GET'])
@login_required
def get_employees_for_rota():
    department_id = request.args.get('department_id')
    employees = User.query.filter_by(is_active=True)
    
    if department_id:
        employees = employees.filter_by(department_id=department_id)
    
    employees_data = [{
        'id': e.id,
        'full_name': e.full_name,
        'department': e.department.name if e.department else ''
    } for e in employees.all()]
    
    return jsonify(employees_data)

@hr_web_bp.route('/duty-rota-management/api/attendance/<date>', methods=['GET'])
@login_required
def get_attendance_for_date(date):
    attendance_date = datetime.strptime(date, '%Y-%m-%d').date()
    records = AttendanceRecord.query.filter_by(date=attendance_date).options(
        db.joinedload(AttendanceRecord.employee),
        db.joinedload(AttendanceRecord.shift)
    ).all()
    
    records_data = [{
        'id': r.id,
        'employee_id': r.employee_id,
        'employee_name': r.employee.full_name,
        'status': r.status.value,
        'clock_in': r.clock_in.strftime('%H:%M') if r.clock_in else None,
        'clock_out': r.clock_out.strftime('%H:%M') if r.clock_out else None,
        'late_minutes': r.late_minutes,
        'overtime_minutes': r.overtime_minutes,
        'notes': r.notes
    } for r in records]
    
    return jsonify(records_data)

@hr_web_bp.route('/duty-rota-management/delete-assignment/<int:assignment_id>', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    assignment = DutyAssignment.query.get_or_404(assignment_id)
    try:
        db.session.delete(assignment)
        db.session.commit()
        flash('Assignment deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting assignment: {str(e)}', 'danger')
    return redirect(url_for('hr_web.duty_rota_management'))







@hr_web_bp.route('/disciplinary/cases')
@login_required
def disciplinary_cases():
    """List and manage disciplinary cases"""
    # Get filter parameters
    status = request.args.get('status')
    severity = request.args.get('severity')
    employee_id = request.args.get('employee_id')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Build query
    query = DisciplinaryCase.query
    
    if status:
        query = query.filter_by(status=status)
    if severity:
        query = query.filter_by(severity=severity)
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    
    # Order by most recent
    cases = query.order_by(DisciplinaryCase.date_reported.desc()).paginate(page=page, per_page=per_page)
    
    # Get employees for filter dropdown
    employees = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    
    return render_template(
        'hr/disciplinary_cases.html', 
        cases=cases,
        employees=employees,
        today=date.today(),
        statuses=[e.value for e in DisciplinaryCaseStatus],
        severities=[e.value for e in DisciplinarySeverity]
    )

@hr_web_bp.route('/disciplinary/cases/<int:case_id>')
@login_required
def view_disciplinary_case(case_id):
    """View details of a specific disciplinary case"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    return render_template('hr/discipline_case_detail.html', case=case, date=date, datetime=datetime)

@hr_web_bp.route('/disciplinary/cases/new', methods=['GET', 'POST'])
@login_required
def new_disciplinary_case():
    """Create a new disciplinary case"""
    if request.method == 'POST':
        try:
            # Generate unique case number
            case_number = f"DISC-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
            
            case = DisciplinaryCase(
                case_number=case_number,
                employee_id=request.form['employee_id'],
                reported_by_id=current_user.id,
                case_type_id=request.form['case_type_id'],
                date_reported=date.today(),
                incident_date=datetime.strptime(request.form['incident_date'], '%Y-%m-%d').date(),
                incident_description=request.form['incident_description'],
                severity=request.form['severity'],
                notes=request.form.get('notes', '')
            )
            
            db.session.add(case)
            db.session.commit()
            flash('Disciplinary case created successfully!', 'success')
            return redirect(url_for('hr_web.view_disciplinary_case', case_id=case.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating disciplinary case: {str(e)}")
            flash(f'Error creating case: {str(e)}', 'danger')
    
    # Get form data
    case_types = DisciplinaryCaseType.query.order_by(DisciplinaryCaseType.name).all()
    employees = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    
    return render_template(
        'hr/new_disciplinary_case.html',
        case_types=case_types,
        employees=employees,
        severities=[e.value for e in DisciplinarySeverity]
    )

@hr_web_bp.route('/disciplinary/cases/<int:case_id>/change-status', methods=['GET'])
@login_required
def change_case_status(case_id):
    """Show form to change case status"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    return render_template(
        'hr/change_case_status.html', 
        case=case,
        statuses=[e.value for e in DisciplinaryCaseStatus]
    )


@hr_web_bp.route('/disciplinary/cases/<int:case_id>/update-status', methods=['POST'])
@login_required
def update_case_status(case_id):
    """Update the status of a disciplinary case"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    new_status = request.form['status']
    
    try:
        # Convert string to enum value
        status_enum = DisciplinaryCaseStatus(new_status)
    except ValueError:
        flash('Invalid status', 'danger')
        return redirect(url_for('hr_web.view_disciplinary_case', case_id=case_id))
    
    try:
        case.status = status_enum  # Use enum value instead of string
        if new_status == DisciplinaryCaseStatus.CLOSED.value:
            case.resolution_date = date.today()
        
        db.session.commit()
        flash('Case status updated successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'danger')
    
    return redirect(url_for('hr_web.view_disciplinary_case', case_id=case_id))

@hr_web_bp.route('/disciplinary/cases/<int:case_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_disciplinary_case(case_id):
    """Edit an existing disciplinary case"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    
    if request.method == 'POST':
        try:
            case.employee_id = request.form['employee_id']
            case.case_type_id = request.form['case_type_id']
            case.incident_date = datetime.strptime(request.form['incident_date'], '%Y-%m-%d').date()
            case.incident_description = request.form['incident_description']
            case.severity = request.form['severity']
            case.notes = request.form.get('notes', '')
            
            db.session.commit()
            flash('Disciplinary case updated successfully!', 'success')
            return redirect(url_for('hr_web.view_disciplinary_case', case_id=case.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating disciplinary case: {str(e)}")
            flash(f'Error updating case: {str(e)}', 'danger')
    
    # Get form data
    case_types = DisciplinaryCaseType.query.order_by(DisciplinaryCaseType.name).all()
    employees = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    
    return render_template(
        'hr/edit_disciplinary_case.html',
        case=case,
        case_types=case_types,
        employees=employees,
        severities=[e.value for e in DisciplinarySeverity]
    )

@hr_web_bp.route('/disciplinary/cases/<int:case_id>/investigations', methods=['GET', 'POST'])
@login_required
def case_investigations(case_id):
    """Manage investigations for a case"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    
    if request.method == 'POST':
        try:
            # Create new investigation
            investigation = DisciplinaryInvestigation(
                case_id=case_id,
                title=request.form.get('title', 'Investigation Findings'),
                investigator_id=current_user.id,
                start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
                findings=request.form['findings'],
                status=request.form.get('status', 'Active')
            )
            
            # Update case status if needed
            if case.status != DisciplinaryCaseStatus.UNDER_INVESTIGATION:
                case.status = DisciplinaryCaseStatus.UNDER_INVESTIGATION
            
            db.session.add(investigation)
            db.session.commit()
            
            # Handle evidence documents
            if 'evidence' in request.files:
                for file in request.files.getlist('evidence'):
                    if file.filename != '':
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid.uuid4()}_{filename}"
                        file_path = os.path.join(
                            current_app.config['UPLOAD_FOLDER'], 
                            'investigations', 
                            unique_filename
                        )
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        file.save(file_path)
                        
                        evidence = InvestigationEvidence(
                            investigation_id=investigation.id,
                            title=filename,
                            file_path=unique_filename,
                            uploaded_by=current_user.id
                        )
                        db.session.add(evidence)
            
            db.session.commit()
            flash('Investigation added successfully', 'success')
            return redirect(url_for('hr_web.case_investigations', case_id=case_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding investigation: {str(e)}', 'danger')
    
    investigations = DisciplinaryInvestigation.query.filter_by(case_id=case_id)\
        .order_by(DisciplinaryInvestigation.start_date.desc()).all()
    
    return render_template(
        'hr/case_investigations.html',
        case=case,
        investigations=investigations,
        today=date.today(),
        statuses=['Active', 'Completed', 'Pending Review', 'On Hold']
    )
    

@hr_web_bp.route('/disciplinary/investigations/<int:investigation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_investigation(investigation_id):
    """Edit an existing investigation"""
    investigation = DisciplinaryInvestigation.query.get_or_404(investigation_id)
    case = investigation.case
    
    if request.method == 'POST':
        try:
            # Update investigation details
            investigation.title = request.form.get('title', investigation.title)
            investigation.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            investigation.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form.get('end_date') else None
            investigation.findings = request.form['findings']
            investigation.status = request.form.get('status', investigation.status)
            
            # Handle new evidence uploads
            if 'evidence' in request.files:
                for file in request.files.getlist('evidence'):
                    if file.filename != '':
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid.uuid4()}_{filename}"
                        file_path = os.path.join(
                            current_app.config['UPLOAD_FOLDER'], 
                            'investigations', 
                            unique_filename
                        )
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        file.save(file_path)
                        
                        evidence = InvestigationEvidence(
                            investigation_id=investigation.id,
                            title=filename,
                            file_path=unique_filename,
                            uploaded_by=current_user.id
                        )
                        db.session.add(evidence)
            
            db.session.commit()
            flash('Investigation updated successfully', 'success')
            return redirect(url_for('hr_web.case_investigations', case_id=case.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating investigation: {str(e)}', 'danger')
    
    return render_template(
        'hr/edit_investigation.html',
        investigation=investigation,
        case=case,
        statuses=[e.value for e in InvestigationStatus],
        today=date.today()
    )

@hr_web_bp.route('/disciplinary/investigations/<int:investigation_id>/delete', methods=['POST'])
@login_required
def delete_investigation(investigation_id):
    """Delete an investigation and its evidence"""
    investigation = DisciplinaryInvestigation.query.get_or_404(investigation_id)
    case_id = investigation.case_id
    
    try:
        # Delete associated evidence files
        for evidence in investigation.evidence:
            file_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'], 
                'investigations', 
                evidence.file_path
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            db.session.delete(evidence)
        
        # Delete the investigation
        db.session.delete(investigation)
        db.session.commit()
        flash('Investigation deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting investigation: {str(e)}', 'danger')
    
    return redirect(url_for('hr_web.case_investigations', case_id=case_id))

# ================================================
# EVIDENCE MANAGEMENT ROUTES
# ================================================

@hr_web_bp.route('/disciplinary/evidence/<int:evidence_id>/delete', methods=['POST'])
@login_required
def delete_evidence(evidence_id):
    """Delete an evidence file from an investigation"""
    evidence = InvestigationEvidence.query.get_or_404(evidence_id)
    investigation_id = evidence.investigation_id
    
    try:
        # Delete the file from storage
        file_path = os.path.join(
            current_app.config['UPLOAD_FOLDER'], 
            'investigations', 
            evidence.file_path
        )
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete the evidence record
        db.session.delete(evidence)
        db.session.commit()
        flash('Evidence deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting evidence: {str(e)}', 'danger')
    
    return redirect(url_for('hr_web.edit_investigation', investigation_id=investigation_id))



# ---------------------------
# Disciplinary Actions
# ---------------------------

@hr_web_bp.route('/disciplinary/actions')
@login_required
def disciplinary_actions():
    """List and manage disciplinary actions"""
    status = request.args.get('status')
    severity = request.args.get('severity')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = DisciplinaryAction.query
    
    if status:
        query = query.filter_by(status=status)
    if severity:
        # Join with action type to filter by severity
        query = query.join(DisciplinaryActionType).filter(
            DisciplinaryActionType.severity_level == severity
        )
    
    actions = query.order_by(DisciplinaryAction.effective_date.desc()).paginate(page=page, per_page=per_page)
    
    return render_template(
        'hr/disciplinary_actions.html', 
        actions=actions,
        statuses=[e.value for e in DisciplinaryActionStatus],
        severities=[e.value for e in DisciplinarySeverity]
    )

@hr_web_bp.route('/disciplinary/cases/available')
@login_required
def disciplinary_cases_available():
    """List and manage disciplinary cases"""
    status = request.args.get('status')
    severity = request.args.get('severity')
    case_type = request.args.get('type')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = DisciplinaryCase.query
    
    if status:
        query = query.filter_by(status=status)
    if severity:
        query = query.filter_by(severity=severity)
    if case_type:
        query = query.filter_by(case_type_id=case_type)
    
    cases = query.order_by(DisciplinaryCase.date_reported.desc()).paginate(page=page, per_page=per_page)
    
    case_types = DisciplinaryCaseType.query.order_by(DisciplinaryCaseType.name).all()
    
    return render_template(
        'hr/disciplinary_case_actions.html', 
        cases=cases,
        statuses=[e.value for e in DisciplinaryCaseStatus],
        severities=[e.value for e in DisciplinarySeverity],
        case_types=case_types
    )

@hr_web_bp.route('/disciplinary/actions/<int:action_id>')
@login_required
def view_disciplinary_action(action_id):
    """View details of a specific disciplinary action"""
    action = DisciplinaryAction.query.get_or_404(action_id)
    return render_template('hr/discipline_action_detail.html', action=action)

@hr_web_bp.route('/disciplinary/cases/<int:case_id>/add-action', methods=['GET', 'POST'])
@login_required
def add_disciplinary_action(case_id):
    """Add a disciplinary action to a case"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    action_types = DisciplinaryActionType.query.order_by(DisciplinaryActionType.name).all()
    
    # Create an empty form just for CSRF protection
    form = DisciplinaryActionForm()
    form.action_type_id.choices = [(at.id, at.name) for at in action_types]
    
    if request.method == 'POST':
        try:
            
            # Manual validation of required fields
            if not request.form.get('action_type_id'):
                flash('Action type is required', 'danger')
                raise ValueError('Action type missing')
            if not request.form.get('effective_date'):
                flash('Effective date is required', 'danger')
                raise ValueError('Effective date missing')
            if not request.form.get('description'):
                flash('Description is required', 'danger')
                raise ValueError('Description missing')
                
            # Create action
            action = DisciplinaryAction(
                case_id=case_id,
                action_type_id=request.form['action_type_id'],
                assigned_by_id=current_user.id,
                effective_date=datetime.strptime(request.form['effective_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form.get('end_date') else None,
                description=request.form['description'],
                outcome=request.form.get('outcome', '')
            )
            
            # Update case status if needed
            if case.status == DisciplinaryCaseStatus.DECISION_PENDING.value:
                case.status = DisciplinaryCaseStatus.CLOSED.value
                case.resolution_date = date.today()
            
            db.session.add(action)
            db.session.commit()
            flash('Disciplinary action added successfully!', 'success')
            return redirect(url_for('hr_web.view_disciplinary_case', case_id=case_id))
            
        except ValidationError:
            db.session.rollback()
            flash('Invalid form submission. Please try again.', 'danger')
            current_app.logger.error("CSRF validation failed for disciplinary action")
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding disciplinary action: {str(e)}")
            flash(f'Error adding action: {str(e)}', 'danger')
    
    return render_template('hr/add_disciplinary_action.html', case=case, action_types=action_types, form=form)




@hr_web_bp.route('/disciplinary/action-types/add', methods=['POST'])
@login_required
def add_disciplinary_action_type():
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('code') or not data.get('severity_level'):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # Check for duplicate code
        existing = DisciplinaryActionType.query.filter_by(code=data['code']).first()
        if existing:
            return jsonify({'success': False, 'message': 'Action type code must be unique'}), 400
        
        # Create new action type
        new_action_type = DisciplinaryActionType(
            name=data['name'],
            code=data['code'],
            description=data.get('description', ''),
            severity_level=data['severity_level']
        )
        
        db.session.add(new_action_type)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Action type added successfully',
            'action_type': {
                'id': new_action_type.id,
                'name': new_action_type.name,
                'code': new_action_type.code
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding action type: {str(e)}")
        return jsonify({'success': False, 'message': 'Server error occurred'}), 500
# ---------------------------
# Appeals
# ---------------------------

@hr_web_bp.route('/disciplinary/appeals')
@login_required
def disciplinary_appeals():
    """Manage appeals against disciplinary decisions"""
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = DisciplinaryAppeal.query
    
    if status:
        query = query.filter_by(status=status)
    
    appeals = query.order_by(DisciplinaryAppeal.appeal_date.desc()).paginate(page=page, per_page=per_page)
    
    return render_template(
        'hr/disciplinary_appeals.html', 
        appeals=appeals,
        statuses=[e.value for e in AppealStatus]
    )

@hr_web_bp.route('/disciplinary/appeals/<int:appeal_id>')
@login_required
def view_disciplinary_appeal(appeal_id):
    """View details of a specific disciplinary appeal"""
    appeal = DisciplinaryAppeal.query.get_or_404(appeal_id)
    return render_template('hr/discipline_appeal_detail.html', appeal=appeal)

@hr_web_bp.route('/disciplinary/appeals/new/<int:case_id>', methods=['GET', 'POST'])
@login_required
def new_disciplinary_appeal(case_id):
    """Create a new appeal against a disciplinary case"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    
    if request.method == 'POST':
        try:
            # Find the latest action for this case
            action = DisciplinaryAction.query.filter_by(case_id=case_id)\
                .order_by(DisciplinaryAction.effective_date.desc())\
                .first()
            
            if not action:
                flash('No disciplinary action found for this case', 'danger')
                return redirect(url_for('hr_web.view_disciplinary_case', case_id=case_id))
            
            appeal = DisciplinaryAppeal(
                case_id=case_id,
                action_id=action.id,
                employee_id=case.employee_id,
                grounds=request.form['grounds'],
                status=AppealStatus.PENDING.value
            )
            
            # Update case status
            case.status = DisciplinaryCaseStatus.APPEALED.value
            
            # Update action status
            action.status = DisciplinaryActionStatus.APPEALED.value
            action.is_appealed = True
            
            db.session.add(appeal)
            db.session.commit()
            flash('Appeal submitted successfully!', 'success')
            return redirect(url_for('hr_web.view_disciplinary_appeal', appeal_id=appeal.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating appeal: {str(e)}")
            flash(f'Error creating appeal: {str(e)}', 'danger')
    
    return render_template('hr/new_disciplinary_appeal.html', case=case)

# ---------------------------
# Hearings
# ---------------------------

@hr_web_bp.route('/disciplinary/hearings')
@login_required
def disciplinary_hearings():
    """Schedule and manage disciplinary hearings"""
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = DisciplinaryHearing.query
    
    if status:
        query = query.filter_by(status=status)
    
    hearings = query.order_by(DisciplinaryHearing.hearing_date.desc()).paginate(page=page, per_page=per_page)
    
    return render_template(
        'hr/discipline_hearings.html', 
        hearings=hearings,
        statuses=[e.value for e in HearingStatus]
    )

@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>')
@login_required
def view_disciplinary_hearing(hearing_id):
    """View details of a specific disciplinary hearing"""
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    return render_template('hr/discipline_hearing_detail.html', hearing=hearing)

@hr_web_bp.route('/disciplinary/cases/<int:case_id>/schedule-hearing', methods=['GET', 'POST'])
@login_required
def schedule_hearing(case_id):
    """Schedule a hearing for a case"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    
    if request.method == 'POST':
        try:
            # Create hearing - use enum member directly, not .value
            hearing = DisciplinaryHearing(
                case_id=case_id,
                hearing_date=datetime.strptime(request.form['hearing_date'], '%Y-%m-%dT%H:%M'),
                location=request.form['location'],
                chairperson_id=request.form['chairperson_id'],
                status=HearingStatus.SCHEDULED  # Removed .value
            )
            
            # Update case status - use enum member directly
            case.status = DisciplinaryCaseStatus.HEARING_SCHEDULED  # Removed .value
            
            # Add participants if selected
            participant_ids = request.form.getlist('participants')
            for user_id in participant_ids:
                role = request.form.get(f'role_{user_id}', 'Participant')
                participant = HearingParticipant(
                    hearing=hearing,
                    user_id=user_id,
                    role=role
                )
                db.session.add(participant)
            
            db.session.add(hearing)
            db.session.commit()
            
            flash('Hearing scheduled successfully!', 'success')
            return redirect(url_for('hr_web.view_disciplinary_hearing', hearing_id=hearing.id))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error scheduling hearing: {str(e)}")
            flash(f'Error scheduling hearing: {str(e)}', 'danger')
    
    # Get potential chairpersons from specific departments
    chairpersons = User.query.join(Department).filter(
        Department.name.in_(['Board Member', 'Administrator', 'Human Resources'])
    ).order_by(User.full_name).all()
    
    # Get other potential participants (excluding chairpersons)
    other_users = User.query.join(Department).filter(
        ~Department.name.in_(['Board Member', 'Administrator', 'Human Resources'])
    ).order_by(User.full_name).all()
    
    return render_template(
        'hr/schedule_hearing.html', 
        case=case,
        chairpersons=chairpersons,
        other_users=other_users,
        today=datetime.utcnow()
    )




@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>/notes', methods=['POST'])
@login_required
def update_hearing_notes(hearing_id):
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    
    notes = request.form.get('notes', '')
    hearing.notes = notes
    hearing.updated_at = datetime.utcnow()
    db.session.commit()
    
    flash('Notes updated successfully', 'success')
    return redirect(url_for('hr_web.view_disciplinary_hearing', hearing_id=hearing_id))

@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>/outcome', methods=['POST'])
@login_required
def update_hearing_outcome(hearing_id):
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    
    outcome = request.form.get('outcome', '')
    status = request.form.get('status', HearingStatus.COMPLETED.value)
    
    hearing.outcome = outcome
    
    # FIX: Convert form value to enum using VALUE (not key)
    hearing.status = HearingStatus(status)  # Use enum constructor with value
    
    hearing.updated_at = datetime.utcnow()
    
    # FIX: Compare using enum member (not string)
    if hearing.status == HearingStatus.COMPLETED:
        case = hearing.case
        case.status = DisciplinaryCaseStatus.DECISION_PENDING
        db.session.add(case)
    
    db.session.commit()
    flash('Outcome and status updated successfully', 'success')
    return redirect(url_for('hr_web.view_disciplinary_hearing', hearing_id=hearing_id))

@hr_web_bp.route('/disciplinary/documents/<int:document_id>/download')
@login_required
def download_document(document_id):
    document = DisciplinaryDocument.query.get_or_404(document_id)
    
    # Basic authorization - user must be associated with the case
    if not document.case.employee_id == current_user.id and not current_user.has_role('HR'):
        abort(403)
    
    return send_from_directory(
        os.path.join(current_app.root_path, UPLOAD_FOLDER),
        document.file_path,
        as_attachment=True
    )

@hr_web_bp.route('/disciplinary/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    document = DisciplinaryDocument.query.get_or_404(document_id)
    
    # Authorization - only HR and document uploader can delete
    if not current_user.has_role('HR') and current_user.id != document.uploaded_by:
        flash('You are not authorized to delete this document', 'danger')
        return redirect(url_for('hr_web.view_hearing', hearing_id=document.hearing_id))
    
    try:
        # Delete file from filesystem
        file_path = os.path.join(current_app.root_path, UPLOAD_FOLDER, document.file_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        db.session.delete(document)
        db.session.commit()
        flash('Document deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting document: {str(e)}', 'danger')
    
    return redirect(url_for('hr_web.view_hearing', hearing_id=document.hearing_id))

@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>/documents/upload', methods=['POST'])
@login_required
def upload_document(hearing_id):
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    
    # Check if the post request has the file part
    if 'document' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('hr_web.view_disciplinary_hearing', hearing_id=hearing_id))
    
    file = request.files['document']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('hr_web.view_hearing', hearing_id=hearing_id))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(os.path.join(current_app.root_path, file_path))
        
        document = DisciplinaryDocument(
            hearing_id=hearing_id,
            case_id=hearing.case_id,
            document_type=request.form.get('document_type', 'Other'),
            title=request.form.get('title', filename),
            description=request.form.get('description', ''),
            file_path=filename,
            uploaded_by=current_user.id
        )
        
        db.session.add(document)
        db.session.commit()
        flash('Document uploaded successfully', 'success')
    else:
        flash('Invalid file type', 'danger')
    
    return redirect(url_for('hr_web.view_hearing', hearing_id=hearing_id))

@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>/edit')
@login_required
def edit_hearing(hearing_id):
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    if not current_user.has_role('HR') and current_user.id != hearing.chairperson_id:
        flash('You are not authorized to edit this hearing', 'danger')
        return redirect(url_for('hr_web.view_hearing', hearing_id=hearing_id))
    
    participants = User.query.join(Department).filter(
        User.id != hearing.chairperson_id
    ).all()
    
    return render_template(
        'edit_hearing.html',
        hearing=hearing,
        participants=participants,
        HearingStatus=HearingStatus
    )

@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>/cancel', methods=['POST'])
@login_required
def cancel_hearing(hearing_id):
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    if not current_user.has_role('HR') and current_user.id != hearing.chairperson_id:
        flash('You are not authorized to cancel this hearing', 'danger')
        return redirect(url_for('hr_web.view_hearing', hearing_id=hearing_id))
    
    hearing.status = HearingStatus.CANCELLED
    hearing.updated_at = datetime.utcnow()
    
    # Update case status
    case = hearing.case
    case.status = DisciplinaryCaseStatus.OPEN
    db.session.add(case)
    
    db.session.commit()
    
    flash('Hearing cancelled successfully', 'success')
    return redirect(url_for('hr_web.view_hearing', hearing_id=hearing_id))

@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>/timeline')
@login_required
def hearing_timeline(hearing_id):
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    
    # Create timeline events
    timeline = [
        {
            'date': hearing.created_at,
            'title': 'Hearing Created',
            'description': f'Created by {hearing.chairperson.full_name}',
            'icon': 'fa-calendar-plus'
        }
    ]
    
    # Add participant notifications
    for participant in hearing.participants:
        timeline.append({
            'date': participant.created_at,
            'title': 'Participant Added',
            'description': f'{participant.user.full_name} added as {participant.role}',
            'icon': 'fa-user-plus'
        })
    
    # Add document upload events
    for doc in hearing.documents:
        timeline.append({
            'date': doc.uploaded_at,
            'title': 'Document Uploaded',
            'description': f'{doc.title} uploaded by {doc.uploaded_by_user.full_name}',
            'icon': 'fa-file-upload'
        })
    
    # Sort timeline by date
    timeline.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('hearing_timeline.html', hearing=hearing, timeline=timeline)

@hr_web_bp.route('/disciplinary/hearings/<int:hearing_id>/export')
@login_required
def export_hearing(hearing_id):
    hearing = DisciplinaryHearing.query.get_or_404(hearing_id)
    
    return send_file(
        as_attachment=True,
        download_name=f"hearing_report_{hearing_id}.pdf",
        mimetype='application/pdf'
    )

@hr_web_bp.route('/disciplinary/participants/<int:participant_id>/update', methods=['POST'])
@login_required
def update_participant(participant_id):
    participant = HearingParticipant.query.get_or_404(participant_id)
    hearing = participant.hearing
    
    # Authorization
    if not current_user.has_role('HR') and current_user.id != hearing.chairperson_id:
        flash('You are not authorized to update participants', 'danger')
        return redirect(url_for('hr_web.view_hearing', hearing_id=hearing.id))
    
    # Update fields
    participant.role = request.form.get('role', participant.role)
    participant.attended = 'attended' in request.form
    participant.notes = request.form.get('notes', participant.notes)
    
    db.session.commit()
    flash('Participant updated successfully', 'success')
    return redirect(url_for('hr_web.view_hearing', hearing_id=hearing.id))    

# ---------------------------
# Policies
# ---------------------------

@hr_web_bp.route('/disciplinary/policies')
@login_required
def disciplinary_policies():
    """View and manage disciplinary policies"""
    policies = DisciplinaryPolicy.query.filter_by(is_active=True)\
        .order_by(DisciplinaryPolicy.effective_date.desc())\
        .all()
    return render_template('hr/disciplinary_policies.html', policies=policies)

@hr_web_bp.route('/disciplinary/policies/<int:policy_id>')
@login_required
def view_disciplinary_policy(policy_id):
    """View details of a specific disciplinary policy"""
    policy = DisciplinaryPolicy.query.get_or_404(policy_id)
    return render_template('hr/discipline_policy_detail.html', policy=policy)

@hr_web_bp.route('/disciplinary/policies/new', methods=['GET', 'POST'])
@login_required
def new_disciplinary_policy():
    """Create a new disciplinary policy"""
    if request.method == 'POST':
        try:
            policy = DisciplinaryPolicy(
                title=request.form['title'],
                code=request.form['code'],
                version=request.form['version'],
                effective_date=datetime.strptime(request.form['effective_date'], '%Y-%m-%d').date(),
                content=request.form['content'],
                created_by=current_user.id
            )
            
            # Handle categories
            category_ids = request.form.getlist('categories')
            for cat_id in category_ids:
                category = PolicyCategory.query.get(cat_id)
                if category:
                    policy.categories.append(category)
            
            db.session.add(policy)
            db.session.commit()
            flash('Policy created successfully!', 'success')
            return redirect(url_for('hr_web.view_disciplinary_policy', policy_id=policy.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating policy: {str(e)}")
            flash(f'Error creating policy: {str(e)}', 'danger')
    
    categories = PolicyCategory.query.order_by(PolicyCategory.name).all()
    return render_template('hr/new_disciplinary_policy.html', categories=categories)

@hr_web_bp.route('/disciplinary/policy-categories/new', methods=['POST'])
@login_required
def new_policy_category():
    """Create a new policy category via AJAX"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Check for existing category
        existing = PolicyCategory.query.filter(
            func.lower(PolicyCategory.name) == func.lower(data['name'])
        ).first()
        if existing:
            return jsonify({'error': 'Category with this name already exists'}), 400
        
        # Create new category
        new_category = PolicyCategory(
            name=data['name'],
            description=data.get('description', '')
        )
        db.session.add(new_category)
        db.session.commit()
        
        return jsonify({
            'id': new_category.id,
            'name': new_category.name,
            'description': new_category.description
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating policy category: {str(e)}")
        return jsonify({'error': str(e)}), 500
# ---------------------------
# Case and Action Types
# ---------------------------

@hr_web_bp.route('/disciplinary/case-types')
@login_required
def disciplinary_case_types():
    """Manage disciplinary case types and categories"""
    case_types = DisciplinaryCaseType.query.order_by(DisciplinaryCaseType.name).all()
    return render_template('hr/discipline_case_types.html', case_types=case_types)

@hr_web_bp.route('/disciplinary/action-types')
@login_required
def disciplinary_action_types():
    """Manage disciplinary action types and severity levels"""
    action_types = DisciplinaryActionType.query.order_by(DisciplinaryActionType.name).all()
    return render_template('hr/discipline_action_types.html', action_types=action_types)

@hr_web_bp.route('/disciplinary/case-types/new', methods=['GET'])
@login_required
def new_disciplinary_case_type():
    """Show form to create a new disciplinary case type"""
    severities = [e.value for e in DisciplinarySeverity]
    return render_template('hr/new_disciplinary_case_type.html', severities=severities)

@hr_web_bp.route('/disciplinary/case-types/create', methods=['POST'])
@login_required
def create_disciplinary_case_type():
    """Create a new disciplinary case type"""
    try:
        case_type = DisciplinaryCaseType(
            name=request.form['name'],
            code=request.form['code'],
            description=request.form.get('description', ''),
            default_severity=request.form['default_severity'],
            resolution_days=request.form['resolution_days']
        )
        
        db.session.add(case_type)
        db.session.commit()
        flash('Case type created successfully!', 'success')
        return redirect(url_for('hr_web.disciplinary_case_types'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating case type: {str(e)}")
        flash(f'Error creating case type: {str(e)}', 'danger')
        return redirect(url_for('hr_web.new_disciplinary_case_type'))
    
@hr_web_bp.route('/disciplinary/case-types/<int:type_id>/edit', methods=['GET'])
@login_required
def edit_disciplinary_case_type(type_id):
    """Show form to edit an existing disciplinary case type"""
    case_type = DisciplinaryCaseType.query.get_or_404(type_id)
    severities = [e.value for e in DisciplinarySeverity]
    return render_template('hr/edit_disciplinary_case_type.html', 
                          case_type=case_type, 
                          severities=severities)

@hr_web_bp.route('/disciplinary/case-types/<int:type_id>/update', methods=['POST'])
@login_required
def update_disciplinary_case_type(type_id):
    """Update an existing disciplinary case type"""
    case_type = DisciplinaryCaseType.query.get_or_404(type_id)
    try:
        case_type.name = request.form['name']
        case_type.code = request.form['code']
        case_type.description = request.form.get('description', '')
        case_type.default_severity = request.form['default_severity']
        case_type.resolution_days = request.form['resolution_days']
        
        db.session.commit()
        flash('Case type updated successfully!', 'success')
        return redirect(url_for('hr_web.disciplinary_case_types'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating case type: {str(e)}")
        flash(f'Error updating case type: {str(e)}', 'danger')
        return redirect(url_for('hr_web.edit_disciplinary_case_type', type_id=type_id))
# ---------------------------
# Reports
# ---------------------------

@hr_web_bp.route('/disciplinary/reports')
@login_required
def disciplinary_reports():
    """Generate disciplinary reports and analytics"""
    # Calculate statistics
    open_cases = DisciplinaryCase.query.filter_by(status=DisciplinaryCaseStatus.OPEN).count()
    closed_cases = DisciplinaryCase.query.filter_by(status=DisciplinaryCaseStatus.CLOSED).count()
    
    # Calculate average resolution time for closed cases
    resolved_cases = DisciplinaryCase.query.filter(
        DisciplinaryCase.status == DisciplinaryCaseStatus.CLOSED,
        DisciplinaryCase.resolution_date.isnot(None)
    ).all()
    
    total_days = 0
    for case in resolved_cases:
        total_days += (case.resolution_date - case.date_reported).days
    avg_resolution = total_days // len(resolved_cases) if resolved_cases else 0
    
    # Get high severity cases
    high_severity = DisciplinaryCase.query.filter(
        DisciplinaryCase.severity.in_([DisciplinarySeverity.MAJOR, DisciplinarySeverity.SEVERE])
    ).count()
    
    # Calculate appeal rate
    appealed_cases = DisciplinaryCase.query.filter(
        DisciplinaryCase.status == DisciplinaryCaseStatus.APPEALED
    ).count()
    appeal_rate = round((appealed_cases / closed_cases * 100), 1) if closed_cases else 0
    
    # Prepare stats cards
    stats = [
        {
            "title": "Open Cases",
            "value": open_cases,
            "trend": "+2 since last week",
            "trend_color": "text-green-500",
            "border_color": "border-blue-500",
            "icon_bg": "bg-blue-100",
            "icon_color": "text-blue-600",
            "icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />'
        },
        {
            "title": "Avg. Resolution Time",
            "value": f"{avg_resolution} days",
            "trend": "-3 days from last month",
            "trend_color": "text-green-500",
            "border_color": "border-green-500",
            "icon_bg": "bg-green-100",
            "icon_color": "text-green-600",
            "icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />'
        },
        {
            "title": "High Severity Cases",
            "value": high_severity,
            "trend": "12% of all cases",
            "trend_color": "text-gray-500",
            "border_color": "border-amber-500",
            "icon_bg": "bg-amber-100",
            "icon_color": "text-amber-600",
            "icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.618 5.984A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016zM12 9v2m0 4h.01" />'
        },
        {
            "title": "Appeal Rate",
            "value": f"{appeal_rate}%",
            "trend": f"{appealed_cases} of {closed_cases} closed cases",
            "trend_color": "text-gray-500",
            "border_color": "border-purple-500",
            "icon_bg": "bg-purple-100",
            "icon_color": "text-purple-600",
            "icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />'
        }
    ]
    
    # Get case status distribution
    status_counts = db.session.query(
        DisciplinaryCase.status, 
        func.count(DisciplinaryCase.id)
    ).group_by(DisciplinaryCase.status).all()
    
    status_labels = [status[0] for status in status_counts]
    status_data = [status[1] for status in status_counts]
    
    # Get severity distribution
    severity_counts = db.session.query(
        DisciplinaryCase.severity, 
        func.count(DisciplinaryCase.id)
    ).group_by(DisciplinaryCase.severity).all()
    
    severity_labels = [severity[0] for severity in severity_counts]
    severity_data = [severity[1] for severity in severity_counts]
    
    # Get monthly trend data (last 12 months) - MySQL version
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)

    # MySQL-compatible date grouping
    monthly_counts = db.session.query(
        func.DATE_FORMAT(DisciplinaryCase.date_reported, '%Y-%m').label('month'),
        func.count(DisciplinaryCase.id)
    ).filter(
        DisciplinaryCase.date_reported.between(start_date, end_date)
    ).group_by(func.DATE_FORMAT(DisciplinaryCase.date_reported, '%Y-%m')
    ).order_by('month').all()

    # Generate all months in the range for consistent chart
    all_months = []
    current = start_date.replace(day=1)
    while current <= end_date:
        all_months.append(current.strftime('%b %Y'))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year+1, month=1)
        else:
            current = current.replace(month=current.month+1)

    # Map counts to months
    trend_data = [0] * len(all_months)
    trend_labels = all_months

    for count in monthly_counts:
        # Convert YYYY-MM to datetime object
        year, month = map(int, count[0].split('-'))
        date_obj = datetime(year, month, 1)
        month_str = date_obj.strftime('%b %Y')
        
        if month_str in trend_labels:
            index = trend_labels.index(month_str)
            trend_data[index] = count[1]
    # Paginate cases
    page = request.args.get('page', 1, type=int)
    cases = DisciplinaryCase.query.order_by(
        DisciplinaryCase.date_reported.desc()
    ).paginate(page=page, per_page=10)
    
    # Get generated reports
    generated_reports = DisciplinaryReport.query.order_by(
        DisciplinaryReport.generated_at.desc()
    ).limit(5).all()
    
    # Get filter options
    case_statuses = [status.value for status in DisciplinaryCaseStatus]
    severities = [severity.value for severity in DisciplinarySeverity]
    case_types = DisciplinaryCaseType.query.all()
    
    return render_template(
        'hr/disciplinary_reports.html',
        stats=stats,
        status_labels=status_labels,
        status_data=status_data,
        severity_labels=severity_labels,
        severity_data=severity_data,
        trend_labels=trend_labels,
        trend_data=trend_data,
        cases=cases,
        generated_reports=generated_reports,
        case_statuses=case_statuses,
        severities=severities,
        case_types=case_types
    )


@hr_web_bp.route('/disciplinary/reports/download/<int:report_id>')
@login_required
def download_report(report_id):
    """Download a generated disciplinary report"""
    report = DisciplinaryReport.query.get_or_404(report_id)
    # In a real implementation, this would send the file
    return f"Downloading report: {report.report_type} ({report.start_date} to {report.end_date})"

# ---------------------------
# Document Management
# ---------------------------

@hr_web_bp.route('/disciplinary/cases/<int:case_id>/add-document', methods=['GET', 'POST'])
@login_required
def add_case_document(case_id):
    """Add a document to a disciplinary case (GET: show form, POST: process upload)"""
    case = DisciplinaryCase.query.get_or_404(case_id)
    
    # Handle GET request - show upload form
    if request.method == 'GET':
        return render_template(
            'hr/add_case_document.html',
            case=case,
        )
    
    # Handle POST request - process file upload
    if 'document' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('hr_web.add_case_document', case_id=case_id))
    
    file = request.files['document']
    
    # Validate file presence
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('hr_web.add_case_document', case_id=case_id))
    
    # Validate file extension
    allowed_extensions = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'txt'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        flash('Invalid file type. Allowed types: PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG, PNG, TXT', 'danger')
        return redirect(url_for('hr_web.add_case_document', case_id=case_id))
    
    try:
        # Secure filename and create unique filename
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        
        # Create upload path
        upload_folder = current_app.config['UPLOAD_FOLDER']
        disciplinary_folder = os.path.join(upload_folder, 'disciplinary')
        os.makedirs(disciplinary_folder, exist_ok=True)
        file_path = os.path.join(disciplinary_folder, unique_filename)
        
        # Save file
        file.save(file_path)
        
        # Create document record
        document = DisciplinaryDocument(
            case_id=case_id,
            document_type=request.form.get('document_type'),  # Changed to document_type
            title=request.form.get('title', filename.rsplit('.', 1)[0]),
            description=request.form.get('description', ''),
            file_path=unique_filename,
            uploaded_by=current_user.id,

        )
        
        db.session.add(document)
        db.session.commit()
        
        flash('Document uploaded successfully', 'success')
        return redirect(url_for('hr_web.view_disciplinary_case', case_id=case_id))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading document: {str(e)}", exc_info=True)
        flash(f'Error uploading document: {str(e)}', 'danger')
        return redirect(url_for('hr_web.add_case_document', case_id=case_id))

@hr_web_bp.route('/disciplinary/documents/<int:doc_id>/download')
@login_required
def download_disciplinary_document(doc_id):
    """Download a disciplinary document"""
    document = DisciplinaryDocument.query.get_or_404(doc_id)
    upload_folder = current_app.config['UPLOAD_FOLDER']
    return send_from_directory(
        os.path.join(upload_folder, 'disciplinary'),
        document.file_path,
        as_attachment=True,
        attachment_filename=f"{document.title}.{document.file_path.split('.')[-1]}"
    )

# ---------------------------
# Additional Utility Routes
# ---------------------------

@hr_web_bp.route('/disciplinary/employees')
@login_required
def get_employees():
    """Get employees for dropdowns (AJAX)"""
    term = request.args.get('term', '')
    employees = User.query.filter(
        User.full_name.ilike(f'%{term}%'),
        User.is_staff == True
    ).order_by(User.full_name).limit(10).all()
    
    results = [{
        'id': emp.id,
        'text': emp.full_name,
        'department': emp.department.name if emp.department else 'No Department'
    } for emp in employees]
    
    return jsonify(results)

@hr_web_bp.route('/disciplinary/case-types/list')
@login_required
def get_case_types():
    """Get case types for dropdowns (AJAX)"""
    case_types = DisciplinaryCaseType.query.order_by(DisciplinaryCaseType.name).all()
    results = [{'id': ct.id, 'name': ct.name} for ct in case_types]
    return jsonify(results)

@hr_web_bp.route('/disciplinary/action-types/list')
@login_required
def get_action_types():
    """Get action types for dropdowns (AJAX)"""
    action_types = DisciplinaryActionType.query.order_by(DisciplinaryActionType.name).all()
    results = [{'id': at.id, 'name': at.name} for at in action_types]
    return jsonify(results)








# ============================================
# RECRUITMENT MANAGEMENT ROUTES
# ============================================

@hr_web_bp.route('/recruitment')
@login_required
def recruitment_dashboard():
    """Recruitment Dashboard"""
    from datetime import datetime, date, timedelta
    
    # Get statistics
    total_jobs = JobPosting.query.count()
    active_jobs = JobPosting.query.filter_by(status='Published').count()
    total_candidates = Candidate.query.count()
    
    # Get interviews for today
    today = date.today()
    interviews_today = Interview.query.filter(
        db.func.date(Interview.scheduled_date) == today,
        Interview.status.in_(['Scheduled', 'Confirmed'])
    ).count()
    
    # Calculate conversion rate (hired candidates / total candidates)
    hired_count = Candidate.query.filter_by(status='Offer Accepted').count()
    
    # Safely calculate conversion rate
    if total_candidates > 0:
        conversion_rate = (hired_count / total_candidates) * 100
    else:
        conversion_rate = 0
    
    # Get candidates from this month
    first_day_of_month = date.today().replace(day=1)
    candidates_this_month = Candidate.query.filter(
        Candidate.application_date >= first_day_of_month
    ).count()
    
    # Recent activity
    recent_jobs = JobPosting.query.order_by(JobPosting.created_at.desc()).limit(5).all()
    recent_candidates = Candidate.query.order_by(Candidate.created_at.desc()).limit(5).all()
    upcoming_interviews = Interview.query.filter(
        Interview.status.in_(['Scheduled', 'Confirmed']),
        Interview.scheduled_date >= datetime.utcnow()
    ).order_by(Interview.scheduled_date).limit(5).all()
    
    return render_template(
        'recruitment/dashboard.html',
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        total_candidates=total_candidates,
        candidates_this_month=candidates_this_month,
        interviews_today=interviews_today,
        hired_count=hired_count,
        conversion_rate=conversion_rate,
        recent_jobs=recent_jobs,
        recent_candidates=recent_candidates,
        upcoming_interviews=upcoming_interviews
    )

@hr_web_bp.route('/recruitment/jobs')
@login_required
def recruitment_jobs():
    """List all job postings with automation stats"""
    from datetime import datetime, date, timedelta
    
    # Get all jobs
    jobs = JobPosting.query.order_by(JobPosting.created_at.desc()).all()
    
    # Calculate statistics for automation
    today = date.today()
    
    # Total applications across all jobs
    total_applications = sum(job.applications_count for job in jobs)
    
    # Jobs closing soon (within 7 days)
    closing_soon_count = sum(1 for job in jobs 
                           if job.application_deadline and 
                           (job.application_deadline - today).days <= 7 and 
                           (job.application_deadline - today).days >= 0)
    
    # Automation rate (percentage of jobs with auto-screening enabled)
    # For now, we'll simulate this. In production, you'd have actual automation settings
    automation_rate = 85  # Simulated automation rate
    
    # Get categories and departments for filters
    categories = JobCategory.query.order_by(JobCategory.name).all()
    departments = Department.query.order_by(Department.name).all()
    
    return render_template('recruitment/jobs.html',
                          jobs=jobs,
                          categories=categories,
                          departments=departments,
                          total_applications=total_applications,
                          closing_soon_count=closing_soon_count,
                          automation_rate=automation_rate,
                          today=today)
    
@hr_web_bp.route('/recruitment/jobs/<int:job_id>/publish', methods=['POST'])
@login_required
def publish_job(job_id):
    """Publish a job posting"""
    job = JobPosting.query.get_or_404(job_id)
    
    if job.status == 'Draft':
        job.status = 'Published'
        job.published_at = datetime.utcnow()
        db.session.commit()
        
        # Trigger automation: Notify team, post to job boards, etc.
        trigger_job_automation(job, 'published')
        
        return jsonify({'success': True, 'message': f'Job "{job.title}" published successfully!'})
    
    return jsonify({'success': False, 'message': 'Job cannot be published'})

@hr_web_bp.route('/recruitment/jobs/<int:job_id>/close', methods=['POST'])
@login_required
def close_job(job_id):
    """Close a job posting"""
    job = JobPosting.query.get_or_404(job_id)
    
    if job.status == 'Published':
        job.status = 'Closed'
        db.session.commit()
        
        # Trigger automation: Notify candidates, generate reports
        trigger_job_automation(job, 'closed')
        
        return jsonify({'success': True, 'message': f'Job "{job.title}" closed successfully!'})
    
    return jsonify({'success': False, 'message': 'Job cannot be closed'})

@hr_web_bp.route('/recruitment/jobs/<int:job_id>/duplicate', methods=['POST'])
@login_required
def duplicate_job(job_id):
    """Duplicate a job posting"""
    original = JobPosting.query.get_or_404(job_id)
    
    # Create a new job with similar details
    new_job = JobPosting(
        title=f"Copy of {original.title}",
        reference_no=f"{original.reference_no}-COPY-{datetime.now().strftime('%Y%m%d')}",
        category_id=original.category_id,
        department_id=original.department_id,
        description=original.description,
        requirements=original.requirements,
        responsibilities=original.responsibilities,
        benefits=original.benefits,
        employment_type=original.employment_type,
        experience_level=original.experience_level,
        education_level=original.education_level,
        salary_disclosure=original.salary_disclosure,
        salary_range_min=original.salary_range_min,
        salary_range_max=original.salary_range_max,
        salary_currency=original.salary_currency,
        positions_available=original.positions_available,
        application_deadline=original.application_deadline + timedelta(days=30),
        start_date=original.start_date,
        status='Draft',  # Always duplicate as draft
        is_remote=original.is_remote,
        location=original.location,
        created_by=current_user.id
    )
    
    db.session.add(new_job)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Job duplicated successfully!', 'job_id': new_job.id})

def trigger_job_automation(job, action):
    """Trigger automation workflows for job actions"""
    # In production, this would integrate with:
    # 1. Email automation system
    # 2. Job board APIs
    # 3. Candidate notification system
    # 4. Analytics tracking
    pass    
    
    

@hr_web_bp.route('/recruitment/jobs/new', methods=['GET', 'POST'])
@login_required
def new_job_posting():
    """Create a new job posting"""
    form = JobPostingForm()
    
    # Populate dropdowns
    form.category_id.choices = [(0, 'Select Category')] + [(c.id, c.name) for c in JobCategory.query.all()]
    form.department_id.choices = [(0, 'Select Department')] + [(d.id, d.name) for d in Department.query.all()]
    
    if form.validate_on_submit():
        # Generate reference number if not provided
        reference_no = form.reference_no.data
        if not reference_no:
            reference_no = f"JOB-{datetime.now().strftime('%Y%m')}-{JobPosting.query.count() + 1:03d}"
        
        job = JobPosting(
            title=form.title.data,
            reference_no=reference_no,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            department_id=form.department_id.data if form.department_id.data != 0 else None,
            description=form.description.data,
            requirements=form.requirements.data,
            responsibilities=form.responsibilities.data,
            benefits=form.benefits.data,
            employment_type=form.employment_type.data,
            experience_level=form.experience_level.data,
            education_level=form.education_level.data,
            salary_disclosure=form.salary_disclosure.data,
            salary_range_min=form.salary_range_min.data,
            salary_range_max=form.salary_range_max.data,
            salary_currency=form.salary_currency.data,
            positions_available=form.positions_available.data,
            application_deadline=form.application_deadline.data,
            start_date=form.start_date.data,
            status=form.status.data,
            is_remote=form.is_remote.data,
            location=form.location.data,
            created_by=current_user.id
        )
        
        # Set published date if publishing
        if form.status.data == 'Published':
            job.published_at = datetime.utcnow()
        
        db.session.add(job)
        db.session.commit()
        
        flash(f'Job posting "{job.title}" has been created successfully!', 'success')
        return redirect(url_for('hr_web.recruitment_jobs'))
    
    return render_template('recruitment/job_form.html', form=form, title='Create Job Posting')
@hr_web_bp.route('/recruitment/jobs/<int:job_id>')
@login_required
def view_job_posting(job_id):
    """View job posting details"""
    from datetime import date
    from sqlalchemy.orm import joinedload, selectinload
    
    # OPTION 1: Use selectinload instead of joinedload for many-to-many
    job = JobPosting.query.options(
        joinedload(JobPosting.department),
        joinedload(JobPosting.category),
        selectinload(JobPosting.interview_panels).selectinload(InterviewPanel.panel_members).joinedload(InterviewPanelMember.user)
    ).get_or_404(job_id)
    
    # OPTION 2: Load panels separately (simpler)
    job = JobPosting.query.options(
        joinedload(JobPosting.department),
        joinedload(JobPosting.category)
    ).get_or_404(job_id)
    
    # Get panels for this job
    panels = InterviewPanel.query.join(panel_job_postings).filter(
        panel_job_postings.c.job_posting_id == job_id
    ).options(
        joinedload(InterviewPanel.panel_members).joinedload(InterviewPanelMember.user)
    ).all()
    
    # Get candidates for this job
    candidates = Candidate.query.filter_by(job_posting_id=job_id).order_by(Candidate.created_at.desc()).all()
    
    # Update view count
    job.views_count = (job.views_count or 0) + 1
    db.session.commit()
    
    # Candidate statistics
    candidate_stats = {
        'total': len(candidates),
        'applied': sum(1 for c in candidates if c.status == 'Applied'),
        'shortlisted': sum(1 for c in candidates if c.status == 'Shortlisted'),
        'interviewed': sum(1 for c in candidates if c.status == 'Interviewed'),
        'hired': sum(1 for c in candidates if c.status == 'Offer Accepted')
    }
    
    return render_template(
        'recruitment/job_view.html',
        job=job,
        candidates=candidates,
        panels=panels,  # Pass separately loaded panels
        candidate_stats=candidate_stats,
        today=date.today()
    )

@hr_web_bp.route('/recruitment/candidates/<int:candidate_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_candidate(candidate_id):
    """Edit candidate information"""
    candidate = Candidate.query.get_or_404(candidate_id)
    form = CandidateForm(obj=candidate)
    
    if form.validate_on_submit():
        # Update candidate fields
        candidate.first_name = form.first_name.data
        candidate.last_name = form.last_name.data
        candidate.email = form.email.data
        candidate.phone = form.phone.data
        candidate.date_of_birth = form.date_of_birth.data
        candidate.nationality = form.nationality.data
        candidate.gender = form.gender.data
        candidate.address = form.address.data
        candidate.city = form.city.data
        candidate.country = form.country.data
        candidate.postal_code = form.postal_code.data
        candidate.current_company = form.current_company.data
        candidate.current_position = form.current_position.data
        candidate.current_salary = form.current_salary.data
        candidate.expected_salary = form.expected_salary.data
        candidate.notice_period = form.notice_period.data
        candidate.years_of_experience = form.years_of_experience.data
        candidate.highest_qualification = form.highest_qualification.data
        candidate.institution = form.institution.data
        candidate.graduation_year = form.graduation_year.data
        candidate.source = form.source.data
        candidate.cover_letter = form.cover_letter.data
        candidate.portfolio_url = form.portfolio_url.data
        candidate.linkedin_url = form.linkedin_url.data
        candidate.status = form.status.data
        
        # Handle file uploads
        if form.resume.data:
            # Save uploaded resume file
            resume_file = form.resume.data
            if resume_file:
                filename = secure_filename(f"resume_{candidate.id}_{candidate.full_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(resume_file.filename)[1]}")
                resume_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'resumes', filename)
                resume_file.save(resume_path)
                candidate.resume_path = resume_path
        
        if form.cover_letter_file.data:
            # Save uploaded cover letter file
            cover_file = form.cover_letter_file.data
            if cover_file:
                filename = secure_filename(f"cover_{candidate.id}_{candidate.full_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(cover_file.filename)[1]}")
                cover_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'covers', filename)
                cover_file.save(cover_path)
                candidate.cover_letter_path = cover_path
        
        db.session.commit()
        
        # Update job statistics if status changed
        if candidate.status == 'Shortlisted' and candidate.status != form.status.old_value:
            candidate.job_posting.shortlisted_count += 1
            db.session.commit()
        
        flash(f'Candidate "{candidate.full_name}" has been updated successfully!', 'success')
        return redirect(url_for('hr_web.view_candidate', candidate_id=candidate_id))
    
    # For GET request, populate form with existing data
    return render_template('recruitment/candidate_form.html', 
                         form=form, 
                         candidate=candidate,
                         job=candidate.job_posting,
                         title=f'Edit {candidate.full_name}')


@hr_web_bp.route('/recruitment/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_job_posting(job_id):
    """Edit job posting"""
    job = JobPosting.query.get_or_404(job_id)
    form = JobPostingForm(obj=job)
    
    # Populate dropdowns
    form.category_id.choices = [(0, 'Select Category')] + [(c.id, c.name) for c in JobCategory.query.all()]
    form.department_id.choices = [(0, 'Select Department')] + [(d.id, d.name) for d in Department.query.all()]
    
    if form.validate_on_submit():
        job.title = form.title.data
        job.reference_no = form.reference_no.data
        job.category_id = form.category_id.data if form.category_id.data != 0 else None
        job.department_id = form.department_id.data if form.department_id.data != 0 else None
        job.description = form.description.data
        job.requirements = form.requirements.data
        job.responsibilities = form.responsibilities.data
        job.benefits = form.benefits.data
        job.employment_type = form.employment_type.data
        job.experience_level = form.experience_level.data
        job.education_level = form.education_level.data
        job.salary_disclosure = form.salary_disclosure.data
        job.salary_range_min = form.salary_range_min.data
        job.salary_range_max = form.salary_range_max.data
        job.salary_currency = form.salary_currency.data
        job.positions_available = form.positions_available.data
        job.application_deadline = form.application_deadline.data
        job.start_date = form.start_date.data
        job.status = form.status.data
        job.is_remote = form.is_remote.data
        job.location = form.location.data
        
        # Update published date if publishing for the first time
        if form.status.data == 'Published' and not job.published_at:
            job.published_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Job posting "{job.title}" has been updated successfully!', 'success')
        return redirect(url_for('hr_web.view_job_posting', job_id=job.id))
    
    return render_template('recruitment/job_form.html', form=form, title='Edit Job Posting', job=job)

@hr_web_bp.route('/recruitment/jobs/<int:job_id>/candidates/new', methods=['GET', 'POST'])
@login_required
def new_candidate(job_id):
    """Add new candidate to job posting"""
    job = JobPosting.query.get_or_404(job_id)
    form = CandidateForm()
    
    if form.validate_on_submit():
        candidate = Candidate(
            job_posting_id=job_id,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            phone=form.phone.data,
            date_of_birth=form.date_of_birth.data,
            nationality=form.nationality.data,
            gender=form.gender.data,
            current_company=form.current_company.data,
            current_position=form.current_position.data,
            current_salary=form.current_salary.data,
            expected_salary=form.expected_salary.data,
            notice_period=form.notice_period.data,
            years_of_experience=form.years_of_experience.data,
            highest_qualification=form.highest_qualification.data,
            institution=form.institution.data,
            graduation_year=form.graduation_year.data,
            source=form.source.data,
            cover_letter=form.cover_letter.data,
            portfolio_url=form.portfolio_url.data,
            linkedin_url=form.linkedin_url.data,
            status=form.status.data
        )
        
        db.session.add(candidate)
        db.session.commit()
        
        # Update job statistics
        job.applications_count = Candidate.query.filter_by(job_posting_id=job_id).count()
        if form.status.data == 'Shortlisted':
            job.shortlisted_count += 1
        
        db.session.commit()
        
        flash(f'Candidate "{candidate.full_name}" has been added successfully!', 'success')
        return redirect(url_for('hr_web.view_job_posting', job_id=job_id))
    
    return render_template('recruitment/candidate_form.html', form=form, job=job, title='Add Candidate')

@hr_web_bp.route('/recruitment/candidates/<int:candidate_id>')
@login_required
def view_candidate(candidate_id):
    """View candidate details"""
    candidate = Candidate.query.get_or_404(candidate_id)
    interviews = Interview.query.filter_by(candidate_id=candidate_id).order_by(Interview.scheduled_date).all()
    
    return render_template(
        'recruitment/candidate_view.html',
        candidate=candidate,
        interviews=interviews
    )

@hr_web_bp.route('/recruitment/jobs/<int:job_id>/panels')
@login_required
def job_panels(job_id):
    """View interview panels for a job"""
    from sqlalchemy.orm import joinedload
    
    # Get the job
    job = JobPosting.query.get_or_404(job_id)
    
    # Get panels through the relationship (simpler)
    panels = InterviewPanel.query.join(
        panel_job_postings,
        InterviewPanel.id == panel_job_postings.c.panel_id
    ).filter(
        panel_job_postings.c.job_posting_id == job_id
    ).options(
        joinedload(InterviewPanel.panel_members).joinedload(InterviewPanelMember.user)
    ).all()
    
    # Get primary panel
    primary_panel = None
    for panel in panels:
        assignment = db.session.execute(
            db.select(panel_job_postings.c.is_primary).where(
                db.and_(
                    panel_job_postings.c.panel_id == panel.id,
                    panel_job_postings.c.job_posting_id == job_id
                )
            )
        ).fetchone()
        
        if assignment and assignment[0]:  # Check if is_primary is True (access first element of tuple)
            primary_panel = panel
            break
    
    return render_template(
        'recruitment/panels.html', 
        job=job, 
        panels=panels,
        primary_panel=primary_panel
    )



@hr_web_bp.route('/recruitment/jobs/<int:job_id>/panels/assign', methods=['GET', 'POST'])
@login_required
def assign_panels_page(job_id):
    """Page to assign panels to a job"""
    from sqlalchemy.orm import joinedload
    
    # Get the job
    job = JobPosting.query.get_or_404(job_id)
    
    if request.method == 'POST':
        # Debug: Print form data
        print("Form data received:")
        print(f"panel_ids: {request.form.getlist('panel_ids[]')}")
        print(f"primary_panel_id: {request.form.get('primary_panel_id')}")
        
        panel_ids = request.form.getlist('panel_ids[]')
        primary_panel_id = request.form.get('primary_panel_id')
        
        # Handle empty panel_ids - checkboxes might be passed differently
        if not panel_ids or panel_ids == ['']:
            # Try alternative way to get checkboxes
            panel_ids = []
            for key in request.form:
                if key.startswith('panel_ids['):
                    panel_ids.append(request.form[key])
            
            if not panel_ids:
                flash('Please select at least one panel to assign', 'error')
                return redirect(url_for('hr_web.assign_panels_page', job_id=job_id))
        
        try:
            assigned_count = 0
            # Assign selected panels
            for panel_id in panel_ids:
                # Convert to integer
                try:
                    panel_id_int = int(panel_id)
                except ValueError:
                    continue
                
                # Check if already assigned
                existing = db.session.execute(
                    db.select(panel_job_postings).where(
                        db.and_(
                            panel_job_postings.c.panel_id == panel_id_int,
                            panel_job_postings.c.job_posting_id == job_id
                        )
                    )
                ).fetchone()
                
                if not existing:
                    # Determine if this panel should be primary
                    is_primary = False
                    if primary_panel_id:
                        try:
                            primary_id_int = int(primary_panel_id)
                            is_primary = (panel_id_int == primary_id_int)
                        except ValueError:
                            pass
                    
                    # If setting as primary, remove primary status from other panels
                    if is_primary:
                        db.session.execute(
                            db.update(panel_job_postings).where(
                                db.and_(
                                    panel_job_postings.c.job_posting_id == job_id,
                                    panel_job_postings.c.is_primary == True
                                )
                            ).values(is_primary=False)
                        )
                    
                    # Insert the assignment
                    stmt = db.insert(panel_job_postings).values(
                        panel_id=panel_id_int,
                        job_posting_id=job_id,
                        assigned_by=current_user.id,
                        is_primary=is_primary,
                        notes=f"Assigned by {current_user.full_name} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
                    )
                    db.session.execute(stmt)
                    assigned_count += 1
            
            db.session.commit()
            
            if assigned_count == 0:
                flash('No new panels were assigned (they may already be assigned)', 'info')
            elif assigned_count == 1:
                flash(f'1 panel has been successfully assigned to this job', 'success')
            else:
                flash(f'{assigned_count} panels have been successfully assigned to this job', 'success')
            
            return redirect(url_for('hr_web.job_panels', job_id=job_id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error assigning panels: {str(e)}")
            flash(f'Error assigning panels: {str(e)}', 'error')
            return redirect(url_for('hr_web.assign_panels_page', job_id=job_id))
    
    # GET request - show the form
    # Get all panels that are NOT already assigned to this job
    # First, get assigned panel IDs
    assigned_results = db.session.execute(
        db.select(panel_job_postings.c.panel_id).where(
            panel_job_postings.c.job_posting_id == job_id
        )
    ).all()
    
    assigned_panel_ids = [pid[0] for pid in assigned_results] if assigned_results else []
    
    # Get available panels (not already assigned)
    query = InterviewPanel.query.options(
        joinedload(InterviewPanel.panel_members).joinedload(InterviewPanelMember.user)
    )
    
    if assigned_panel_ids:
        query = query.filter(InterviewPanel.id.notin_(assigned_panel_ids))
    
    available_panels = query.all()
    
    # Get current primary panel ID
    primary_result = db.session.execute(
        db.select(panel_job_postings.c.panel_id).where(
            db.and_(
                panel_job_postings.c.job_posting_id == job_id,
                panel_job_postings.c.is_primary == True
            )
        )
    ).fetchone()
    
    primary_panel_id = primary_result[0] if primary_result else None
    
    return render_template(
        'recruitment/assign_panels.html',
        job=job,
        available_panels=available_panels,
        primary_panel_id=primary_panel_id
    )
@hr_web_bp.route('/recruitment/panels')
@login_required
def manage_panels():
    """View all interview panels"""
    panels = InterviewPanel.query.all()
    
    return render_template('recruitment/manage_panels.html', panels=panels)



@hr_web_bp.route('/recruitment/panels/create', methods=['GET', 'POST'])
@login_required
def create_panel():
    """Create a new interview panel"""
    form = InterviewPanelForm()
    
    # Get job context if provided
    job_id = request.args.get('job_id')
    job = None
    if job_id:
        job = JobPosting.query.get(job_id)
    
    if form.validate_on_submit():
        panel = InterviewPanel(
            name=form.name.data,
            description=form.description.data,
            panel_type=form.panel_type.data,
            created_by=current_user.id,
            is_active=form.is_active.data if hasattr(form, 'is_active') else True
        )
        
        db.session.add(panel)
        db.session.commit()
        
        # If job_id was provided in URL, assign this panel to that job
        if job_id:
            job = JobPosting.query.get(job_id)
            if job:
                panel.assign_to_job(
                    job_posting_id=job.id,
                    assigned_by=current_user.id,
                    is_primary=True  # Make it the primary panel for this job
                )
                db.session.commit()
                flash(f'Interview panel "{panel.name}" created and assigned to {job.title} successfully!', 'success')
                return redirect(url_for('hr_web.view_panel', panel_id=panel.id, job_id=job.id))
        
        flash(f'Interview panel "{panel.name}" created successfully!', 'success')
        return redirect(url_for('hr_web.manage_panels'))
    
    return render_template('recruitment/panel_form.html', 
                         form=form, 
                         panel=None,
                         job=job,
                         title='Create Interview Panel')
@hr_web_bp.route('/recruitment/panels/<int:panel_id>')
@login_required
def view_panel(panel_id):
    """View panel details"""
    from sqlalchemy.orm import joinedload
    from sqlalchemy import select
    
    panel = InterviewPanel.query.options(
        joinedload(InterviewPanel.panel_members).joinedload(InterviewPanelMember.user),
        joinedload(InterviewPanel.interviews).joinedload(Interview.candidate)
    ).get_or_404(panel_id)
    
    # Get all members
    panel_members = panel.panel_members
    
    # Get all interviews for this panel
    interviews = panel.interviews
    
    # Get assigned jobs for this panel
    assigned_jobs = panel.assigned_job_postings
    
    # Get primary job posting
    primary_job = None
    if assigned_jobs:
        # Query to get primary job posting
        from app.hr.models import panel_job_postings
        stmt = select(panel_job_postings.c.job_posting_id).where(
            db.and_(
                panel_job_postings.c.panel_id == panel_id,
                panel_job_postings.c.is_primary == True
            )
        )
        result = db.session.execute(stmt).scalar()
        if result:
            primary_job = next((job for job in assigned_jobs if job.id == result), None)
    
    # Get job context if available (from query parameter)
    job_id = request.args.get('job_id')
    job = None
    if job_id:
        job = JobPosting.query.get(job_id)
    
    # Get all available users (for adding members)
    # Filter out users already in the panel
    current_user_ids = [member.user_id for member in panel_members]
    available_users = User.query.filter(
        User.is_active == True,
        User.id.notin_(current_user_ids) if current_user_ids else True
    ).all()
    
    # Helper function for template
    def is_primary_job(job_id):
        """Check if a job is primary for this panel"""
        if not primary_job:
            return False
        return primary_job.id == job_id
    
    return render_template('recruitment/panel_view.html', 
                          panel=panel,
                          panel_members=panel_members,
                          interviews=interviews,
                          assigned_jobs=assigned_jobs,
                          primary_job=primary_job,
                          job=job,
                          available_users=available_users,
                          is_primary_job=is_primary_job,
                          get_primary_job=lambda: primary_job)

@hr_web_bp.route('/recruitment/panels/<int:panel_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_panel(panel_id):
    """Edit panel details"""
    panel = InterviewPanel.query.get_or_404(panel_id)
    form = InterviewPanelForm(obj=panel)
    
    # Get job context if provided
    job_id = request.args.get('job_id')
    job = None
    if job_id:
        job = JobPosting.query.get(job_id)
    
    if form.validate_on_submit():
        panel.name = form.name.data
        panel.description = form.description.data
        panel.panel_type = form.panel_type.data
        panel.is_active = form.is_active.data if hasattr(form, 'is_active') else True
        
        db.session.commit()
        flash(f'Interview panel "{panel.name}" updated successfully!', 'success')
        
        # Redirect back to appropriate page
        if job:
            return redirect(url_for('hr_web.view_panel', panel_id=panel_id, job_id=job.id))
        return redirect(url_for('hr_web.view_panel', panel_id=panel_id))
    
    return render_template('recruitment/panel_form.html', 
                         form=form, 
                         panel=panel,
                         job=job,
                         title=f'Edit {panel.name}')
@hr_web_bp.route('/recruitment/jobs/<int:job_id>/create-panel', methods=['GET', 'POST'])
@login_required
def create_interview_panel(job_id):
    """Create new interview panel with clean URL"""
    job = JobPosting.query.get_or_404(job_id)
    form = InterviewPanelForm()
    
    if form.validate_on_submit():
        panel = InterviewPanel(
            name=form.name.data,
            description=form.description.data,
            panel_type=form.panel_type.data
        )
        
        db.session.add(panel)
        db.session.commit()
        
        flash(f'Interview panel "{panel.name}" has been created successfully!', 'success')
        return redirect(url_for('hr_web.job_panels', job_id=job_id))
    
    return render_template('recruitment/panel_form.html', 
                         form=form, 
                         job=job, 
                         title='Create Interview Panel')
    
    
@hr_web_bp.route('/recruitment/panels/<int:panel_id>')
@login_required
def view_interview_panel(panel_id):
    """View interview panel details"""
    panel = InterviewPanel.query.get_or_404(panel_id)
    panel_members = InterviewPanelMember.query.filter_by(panel_id=panel_id).all()
    interviews = Interview.query.filter_by(panel_id=panel_id).order_by(Interview.scheduled_date).all()
    
    # Get available users for adding to panel
    existing_member_ids = [pm.user_id for pm in panel_members]
    available_users = User.query.filter(
        User.is_active == True,
        User.id.notin_(existing_member_ids)
    ).order_by(User.full_name).all()
    
    return render_template(
        'recruitment/panel_view.html',
        panel=panel,
        panel_members=panel_members,
        interviews=interviews,
        available_users=available_users
    )

@hr_web_bp.route('/recruitment/panels/<int:panel_id>/add-member', methods=['POST'])
@login_required
def add_panel_member(panel_id):
    """Add member to interview panel"""
    panel = InterviewPanel.query.get_or_404(panel_id)
    user_id = request.form.get('user_id')
    role = request.form.get('role', 'Member')
    
    if not user_id:
        flash('Please select a user', 'error')
        return redirect(url_for('hr_web.view_interview_panel', panel_id=panel_id))
    
    # Check if user is already a member
    existing = InterviewPanelMember.query.filter_by(panel_id=panel_id, user_id=user_id).first()
    if existing:
        flash('This user is already a panel member', 'error')
        return redirect(url_for('hr_web.view_interview_panel', panel_id=panel_id))
    
    member = InterviewPanelMember(
        panel_id=panel_id,
        user_id=user_id,
        role=role
    )
    
    db.session.add(member)
    db.session.commit()
    
    flash('Panel member added successfully!', 'success')
    return redirect(url_for('hr_web.view_interview_panel', panel_id=panel_id))


@hr_web_bp.route('/recruitment/panels/<int:panel_id>/edit-member', methods=['POST'])
@login_required
def edit_panel_member(panel_id):
    """Edit panel member role"""
    panel = InterviewPanel.query.get_or_404(panel_id)
    member_id = request.form.get('member_id')
    role = request.form.get('role')
    is_required = request.form.get('is_required') == 'on'
    
    member = InterviewPanelMember.query.filter_by(
        id=member_id,
        panel_id=panel_id
    ).first_or_404()
    
    member.role = role
    member.is_required = is_required
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Member updated successfully'})

@hr_web_bp.route('/recruitment/panels/<int:panel_id>/remove-member', methods=['POST'])
@login_required
def remove_panel_member(panel_id):
    """Remove member from panel"""
    data = request.get_json()
    member_id = data.get('member_id')
    
    member = InterviewPanelMember.query.filter_by(
        id=member_id,
        panel_id=panel_id
    ).first_or_404()
    
    db.session.delete(member)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Member removed successfully'})

@hr_web_bp.route('/recruitment/interviews/schedule', methods=['GET', 'POST'])
@login_required
def schedule_interview():
    """Schedule a new interview"""
    from datetime import datetime
    
    if request.method == 'POST':
        candidate_id = request.form.get('candidate_id')
        panel_id = request.form.get('panel_id')
        scheduled_date = request.form.get('scheduled_date')
        interview_type = request.form.get('interview_type')
        
        if not all([candidate_id, panel_id, scheduled_date]):
            flash('Please fill all required fields', 'error')
            return redirect(url_for('hr_web.schedule_interview'))
        
        interview = Interview(
            candidate_id=candidate_id,
            panel_id=panel_id,
            scheduled_date=datetime.strptime(scheduled_date, '%Y-%m-%dT%H:%M'),
            interview_type=interview_type,
            duration_minutes=request.form.get('duration_minutes', 60),
            location=request.form.get('location'),
            meeting_link=request.form.get('meeting_link')
        )
        
        db.session.add(interview)
        
        # Update candidate status
        candidate = Candidate.query.get(candidate_id)
        candidate.status = 'Interview Scheduled'
        candidate.interview_date = interview.scheduled_date
        
        db.session.commit()
        
        flash('Interview scheduled successfully!', 'success')
        return redirect(url_for('hr_web.view_interview_panel', panel_id=panel_id))
    
    # GET request - show form
    candidates = Candidate.query.filter_by(status='Shortlisted').all()
    panels = InterviewPanel.query.filter_by(is_active=True).all()
    
    return render_template(
        'recruitment/schedule_interview.html',
        candidates=candidates,
        panels=panels,
        now=datetime.now()  # Add this line
    )

@hr_web_bp.route('/recruitment/jobs/<int:job_id>/selection')
@login_required
def candidate_selection(job_id):
    """View and select best candidate for job"""
    job = JobPosting.query.get_or_404(job_id)
    
    # Get shortlisted candidates with their interview scores
    candidates = Candidate.query.filter_by(
        job_posting_id=job_id,
        status='Interviewed'
    ).order_by(Candidate.overall_score.desc()).all()
    
    # Calculate statistics
    for candidate in candidates:
        candidate.interviews = Interview.query.filter_by(candidate_id=candidate.id).all()
        candidate.average_interview_score = 0
        
        if candidate.interviews:
            all_scores = []
            for interview in candidate.interviews:
                for score in interview.scores:
                    if score.score:
                        all_scores.append(float(score.score))
            
            if all_scores:
                candidate.average_interview_score = sum(all_scores) / len(all_scores)
    
    return render_template(
        'recruitment/selection.html',
        job=job,
        candidates=candidates
    )

@hr_web_bp.route('/recruitment/candidates/<int:candidate_id>/select', methods=['POST'])
@login_required
def select_candidate(candidate_id):
    """Select candidate for job offer"""
    candidate = Candidate.query.get_or_404(candidate_id)
    
    # Update candidate status
    candidate.status = 'Offer Extended'
    candidate.updated_at = datetime.utcnow()
    
    # Update job statistics
    job = candidate.job_posting
    job.shortlisted_count = Candidate.query.filter_by(
        job_posting_id=job.id,
        status='Shortlisted'
    ).count()
    
    db.session.commit()
    
    flash(f'Offer extended to {candidate.full_name}!', 'success')
    return redirect(url_for('hr_web.candidate_selection', job_id=candidate.job_posting_id))

@hr_web_bp.route('/recruitment/candidates/<int:candidate_id>/reject', methods=['POST'])
@login_required
def reject_candidate(candidate_id):
    """Reject candidate"""
    candidate = Candidate.query.get_or_404(candidate_id)
    candidate.status = 'Rejected'
    candidate.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Candidate {candidate.full_name} has been rejected', 'info')
    return redirect(url_for('hr_web.candidate_selection', job_id=candidate.job_posting_id))

@hr_web_bp.route('/recruitment/reports')
@login_required
def recruitment_reports():
    """Recruitment reports and analytics"""
    # Time-based statistics
    today = date.today()
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)
    
    # Job statistics
    total_jobs = JobPosting.query.count()
    active_jobs = JobPosting.query.filter_by(status='Published').count()
    jobs_this_month = JobPosting.query.filter(
        JobPosting.created_at >= start_of_month
    ).count()
    
    # Candidate statistics
    total_candidates = Candidate.query.count()
    candidates_this_month = Candidate.query.filter(
        Candidate.created_at >= start_of_month
    ).count()
    
    # Interview statistics
    total_interviews = Interview.query.count()
    interviews_this_month = Interview.query.filter(
        Interview.scheduled_date >= start_of_month
    ).count()
    
    # Conversion rates
    hired_count = Candidate.query.filter_by(status='Offer Accepted').count()
    conversion_rate = (hired_count / total_candidates * 100) if total_candidates > 0 else 0
    
    # Source analysis
    sources = db.session.query(
        Candidate.source,
        db.func.count(Candidate.id).label('count')
    ).group_by(Candidate.source).all()
    
    # Status distribution
    statuses = db.session.query(
        Candidate.status,
        db.func.count(Candidate.id).label('count')
    ).group_by(Candidate.status).all()
    
    return render_template(
        'recruitment/reports.html',
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        jobs_this_month=jobs_this_month,
        total_candidates=total_candidates,
        candidates_this_month=candidates_this_month,
        total_interviews=total_interviews,
        interviews_this_month=interviews_this_month,
        conversion_rate=conversion_rate,
        hired_count=hired_count,
        sources=sources,
        statuses=statuses
    )
    
    
    
# app/hr/routes.py

@hr_web_bp.route('/recruitment/settings')
@login_required
def recruitment_settings():
    """Recruitment Settings Page"""
    categories = JobCategory.query.order_by(JobCategory.name).all()
    return render_template('recruitment/settings.html', 
                          categories=categories,
                          title='Recruitment Settings')

@hr_web_bp.route('/recruitment/settings/category/add', methods=['POST'])
@login_required
def add_job_category():
    """Add a new job category"""
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Category name is required', 'error')
        return redirect(url_for('hr_web.recruitment_settings'))
    
    # Check if category already exists
    existing = JobCategory.query.filter_by(name=name).first()
    if existing:
        flash(f'Category "{name}" already exists', 'error')
        return redirect(url_for('hr_web.recruitment_settings'))
    
    category = JobCategory(name=name, description=description)
    db.session.add(category)
    db.session.commit()
    
    flash(f'Category "{name}" has been added successfully!', 'success')
    return redirect(url_for('hr_web.recruitment_settings'))

@hr_web_bp.route('/recruitment/settings/category/<int:category_id>/edit', methods=['POST'])
@login_required
def edit_job_category(category_id):
    """Edit a job category"""
    category = JobCategory.query.get_or_404(category_id)
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Category name is required', 'error')
        return redirect(url_for('hr_web.recruitment_settings'))
    
    # Check if another category with same name exists
    existing = JobCategory.query.filter(
        JobCategory.name == name,
        JobCategory.id != category_id
    ).first()
    if existing:
        flash(f'Category "{name}" already exists', 'error')
        return redirect(url_for('hr_web.recruitment_settings'))
    
    category.name = name
    category.description = description
    db.session.commit()
    
    flash(f'Category "{name}" has been updated successfully!', 'success')
    return redirect(url_for('hr_web.recruitment_settings'))

@hr_web_bp.route('/recruitment/settings/category/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_job_category(category_id):
    """Delete a job category"""
    category = JobCategory.query.get_or_404(category_id)
    
    # Check if category is being used by any job postings
    if category.job_postings:
        flash(f'Cannot delete category "{category.name}" because it is used by {len(category.job_postings)} job posting(s)', 'error')
        return redirect(url_for('hr_web.recruitment_settings'))
    
    db.session.delete(category)
    db.session.commit()
    
    flash(f'Category "{category.name}" has been deleted successfully!', 'success')
    return redirect(url_for('hr_web.recruitment_settings'))    




@hr_web_bp.route('/recruitment/candidates')
@login_required
def recruitment_candidates():
    """List all candidates across all jobs with filtering options"""
    from datetime import datetime, date, timedelta
    
    # Get filter parameters
    job_id = request.args.get('job_id', type=int)
    status = request.args.get('status')
    source = request.args.get('source')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Base query
    query = Candidate.query
    
    # Apply filters
    if job_id:
        query = query.filter_by(job_posting_id=job_id)
    if status:
        query = query.filter_by(status=status)
    if source:
        query = query.filter_by(source=source)
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Candidate.application_date >= date_from_obj)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(Candidate.application_date <= date_to_obj)
        except ValueError:
            pass
    
    # Order by application date (newest first)
    query = query.order_by(Candidate.application_date.desc())
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    candidates_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    candidates = candidates_pagination.items
    
    # Get statistics for the current filter
    total_candidates = query.count()
    
    # Count by status for the current filter
    status_counts = {}
    for status_option in ['Applied', 'Under Review', 'Shortlisted', 'Interview Scheduled', 
                         'Interviewed', 'Reference Check', 'Offer Extended', 'Offer Accepted', 
                         'Rejected', 'On Hold', 'Withdrawn']:
        status_counts[status_option] = query.filter_by(status=status_option).count()
    
    # Get all jobs for filter dropdown
    jobs = JobPosting.query.filter_by(status='Published').order_by(JobPosting.title).all()
    
    # Get sources for filter dropdown
    sources = db.session.query(Candidate.source).distinct().all()
    sources = [s[0] for s in sources if s[0]]
    
    return render_template('recruitment/candidates.html',
                         candidates=candidates,
                         candidates_pagination=candidates_pagination,
                         total_candidates=total_candidates,
                         status_counts=status_counts,
                         jobs=jobs,
                         sources=sources,
                         job_id=job_id,
                         status_filter=status,
                         source_filter=source,
                         date_from=date_from,
                         date_to=date_to,
                         current_date=date.today())
    
    
@hr_web_bp.route('/recruitment/candidates/export')
@login_required
def export_candidates():
    """Export candidates to CSV"""
    import csv
    from io import StringIO
    
    # Get filter parameters (same as recruitment_candidates)
    job_id = request.args.get('job_id', type=int)
    status = request.args.get('status')
    source = request.args.get('source')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Build query (same as recruitment_candidates)
    query = Candidate.query
    
    if job_id:
        query = query.filter_by(job_posting_id=job_id)
    if status:
        query = query.filter_by(status=status)
    if source:
        query = query.filter_by(source=source)
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Candidate.application_date >= date_from_obj)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(Candidate.application_date <= date_to_obj)
        except ValueError:
            pass
    
    candidates = query.all()
    
    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Job Applied',
        'Status', 'Application Date', 'Source', 'Current Company',
        'Current Position', 'Expected Salary', 'Years of Experience',
        'Highest Qualification', 'Overall Score'
    ])
    
    # Write data
    for candidate in candidates:
        writer.writerow([
            candidate.id,
            candidate.first_name,
            candidate.last_name,
            candidate.email,
            candidate.phone or '',
            candidate.job_posting.title if candidate.job_posting else '',
            candidate.status,
            candidate.application_date.strftime('%Y-%m-%d') if candidate.application_date else '',
            candidate.source or '',
            candidate.current_company or '',
            candidate.current_position or '',
            candidate.expected_salary or '',
            candidate.years_of_experience or '',
            candidate.highest_qualification or '',
            candidate.overall_score or ''
        ])
    
    output.seek(0)
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=candidates_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-type'] = 'text/csv'
    
    return response    





@hr_web_bp.route('/recruitment/interviews')
@login_required
def recruitment_interviews():
    """List all interviews with filtering options"""
    from datetime import datetime, date, timedelta
    
    # Get filter parameters
    status = request.args.get('status', 'upcoming')  # upcoming, today, in_progress, past, completed, cancelled, all
    job_id = request.args.get('job_id', type=int)
    candidate_id = request.args.get('candidate_id', type=int)
    panel_id = request.args.get('panel_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Base query
    query = Interview.query
    
    # Apply status filter
    today = datetime.utcnow().date()
    now = datetime.utcnow()
    
    if status == 'upcoming':
        query = query.filter(
            Interview.scheduled_date >= now,
            Interview.status.in_(['Scheduled', 'Confirmed'])
        )
    elif status == 'today':
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        query = query.filter(
            Interview.scheduled_date >= start_of_day,
            Interview.scheduled_date <= end_of_day,
            Interview.status.in_(['Scheduled', 'Confirmed', 'In Progress'])
        )
    elif status == 'in_progress':
        # Show interviews that are currently in progress
        query = query.filter(
            Interview.status == 'In Progress'
        )
    elif status == 'past':
        # Show past interviews (scheduled time has passed) but not completed
        query = query.filter(
            Interview.scheduled_date < now,
            ~Interview.status.in_(['Completed', 'Cancelled'])
        )
    elif status == 'completed':
        query = query.filter_by(status='Completed')
    elif status == 'cancelled':
        query = query.filter_by(status='Cancelled')
    elif status == 'no_show':
        query = query.filter_by(status='No Show')
    elif status == 'rescheduled':
        query = query.filter_by(status='Rescheduled')
    elif status:
        # If any other status is passed directly
        query = query.filter_by(status=status)
    
    # Apply other filters
    if job_id:
        query = query.join(Candidate).filter(Candidate.job_posting_id == job_id)
    if candidate_id:
        query = query.filter_by(candidate_id=candidate_id)
    if panel_id:
        query = query.filter_by(panel_id=panel_id)
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Interview.scheduled_date >= date_from_obj)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            date_to_obj = datetime.combine(date_to_obj.date(), datetime.max.time())
            query = query.filter(Interview.scheduled_date <= date_to_obj)
        except ValueError:
            pass
    
    # Order by appropriate field
    if status in ['upcoming', 'today']:
        query = query.order_by(Interview.scheduled_date.asc())
    elif status == 'in_progress':
        # For in-progress interviews, order by actual start time (most recent first)
        # MySQL handles NULL values differently - we need to handle NULL actual_start_time
        # Option 1: Order by actual_start_time if not NULL, else scheduled_date
        query = query.order_by(
            db.case(
                (Interview.actual_start_time.isnot(None), Interview.actual_start_time),
                else_=Interview.scheduled_date
            ).desc(),
            Interview.scheduled_date.asc()
        )
    else:
        # For past, completed, etc., order by scheduled date (most recent first)
        query = query.order_by(Interview.scheduled_date.desc())
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    interviews_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    interviews = interviews_pagination.items
    
    # Get statistics for each status
    total_interviews = Interview.query.count()
    
    upcoming_interviews = Interview.query.filter(
        Interview.scheduled_date >= now,
        Interview.status.in_(['Scheduled', 'Confirmed'])
    ).count()
    
    interviews_today = Interview.query.filter(
        db.func.date(Interview.scheduled_date) == today,
        Interview.status.in_(['Scheduled', 'Confirmed', 'In Progress'])
    ).count()
    
    in_progress_interviews = Interview.query.filter_by(status='In Progress').count()
    completed_interviews = Interview.query.filter_by(status='Completed').count()
    cancelled_interviews = Interview.query.filter_by(status='Cancelled').count()
    
    # Get filter options
    jobs = JobPosting.query.filter_by(status='Published').order_by(JobPosting.title).all()
    panels = InterviewPanel.query.filter_by(is_active=True).order_by(InterviewPanel.name).all()
    
    # Get candidates for filter dropdown
    candidates = Candidate.query.order_by(Candidate.first_name, Candidate.last_name).all()
    
    return render_template('recruitment/interviews.html',
                         interviews=interviews,
                         interviews_pagination=interviews_pagination,
                         total_interviews=total_interviews,
                         upcoming_interviews=upcoming_interviews,
                         interviews_today=interviews_today,
                         in_progress_interviews=in_progress_interviews,
                         completed_interviews=completed_interviews,
                         cancelled_interviews=cancelled_interviews,
                         jobs=jobs,
                         panels=panels,
                         candidates=candidates,
                         status_filter=status,
                         job_id=job_id,
                         candidate_id=candidate_id,
                         panel_id=panel_id,
                         date_from=date_from,
                         date_to=date_to,
                         current_date=date.today(),
                         timedelta=timedelta,
                         now=now)
    
    
@hr_web_bp.route('/recruitment/interviews/<int:interview_id>')
@login_required
def view_interview(interview_id):
    """View interview details"""
    interview = Interview.query.get_or_404(interview_id)
    
    # Get panel members and their scores for this interview
    panel_members = InterviewPanelMember.query.filter_by(panel_id=interview.panel_id).all()
    
    # Get scores for this interview
    scores = InterviewScore.query.filter_by(interview_id=interview_id).all()
    
    return render_template('recruitment/interview_view.html',
                         interview=interview,
                         panel_members=panel_members,
                         scores=scores)

@hr_web_bp.route('/recruitment/interviews/new', methods=['GET', 'POST'])
@login_required
def new_interview():
    """Schedule a new interview"""
    from datetime import datetime, timedelta
    
    # Get candidate_id from query parameter if provided
    candidate_id = request.args.get('candidate_id', type=int)
    
    if request.method == 'POST':
        # Create new interview
        interview = Interview(
            candidate_id=request.form.get('candidate_id'),
            panel_id=request.form.get('panel_id'),
            interview_type=request.form.get('interview_type'),
            scheduled_date=datetime.strptime(request.form.get('scheduled_date'), '%Y-%m-%dT%H:%M'),
            duration_minutes=request.form.get('duration_minutes', 60),
            location=request.form.get('location'),
            meeting_link=request.form.get('meeting_link'),
            status='Scheduled'
        )
        
        # Update candidate status
        candidate = Candidate.query.get(interview.candidate_id)
        if candidate and candidate.status != 'Interview Scheduled':
            candidate.status = 'Interview Scheduled'
            candidate.interview_date = interview.scheduled_date
            candidate.interview_location = interview.location
        
        db.session.add(interview)
        db.session.commit()
        
        # Send notification (you can implement this later)
        # send_interview_notification(interview)
        
        flash(f'Interview scheduled successfully for {candidate.full_name}!', 'success')
        return redirect(url_for('hr_web.recruitment_interviews'))
    
    # For GET request, populate form data
    candidates = Candidate.query.filter(
        Candidate.status.in_(['Shortlisted', 'Under Review'])
    ).order_by(Candidate.first_name, Candidate.last_name).all()
    
    panels = InterviewPanel.query.filter_by(is_active=True).order_by(InterviewPanel.name).all()
    
    # Default scheduled date (next business day at 10 AM)
    default_date = datetime.now() + timedelta(days=1)
    default_date = default_date.replace(hour=10, minute=0, second=0, microsecond=0)
    
    return render_template('recruitment/interview_form.html',
                         candidates=candidates,
                         panels=panels,
                         candidate_id=candidate_id,
                         default_date=default_date,
                         title='Schedule New Interview')

@hr_web_bp.route('/recruitment/interviews/<int:interview_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_interview(interview_id):
    """Edit interview details"""
    interview = Interview.query.get_or_404(interview_id)
    
    if request.method == 'POST':
        # Update interview
        interview.panel_id = request.form.get('panel_id')
        interview.interview_type = request.form.get('interview_type')
        interview.scheduled_date = datetime.strptime(request.form.get('scheduled_date'), '%Y-%m-%dT%H:%M')
        interview.duration_minutes = request.form.get('duration_minutes', 60)
        interview.location = request.form.get('location')
        interview.meeting_link = request.form.get('meeting_link')
        interview.status = request.form.get('status')
        
        # Update candidate status if needed
        if interview.status == 'Completed' and interview.candidate.status != 'Interviewed':
            interview.candidate.status = 'Interviewed'
        
        db.session.commit()
        
        flash('Interview updated successfully!', 'success')
        return redirect(url_for('hr_web.view_interview', interview_id=interview_id))
    
    # For GET request
    panels = InterviewPanel.query.filter_by(is_active=True).order_by(InterviewPanel.name).all()
    
    return render_template('recruitment/interview_form.html',
                         interview=interview,
                         panels=panels,
                         title='Edit Interview')

@hr_web_bp.route('/recruitment/interviews/<int:interview_id>/cancel', methods=['POST'])
@login_required
def cancel_interview(interview_id):
    """Cancel an interview"""
    interview = Interview.query.get_or_404(interview_id)
    
    if interview.status in ['Scheduled', 'Confirmed']:
        interview.status = 'Cancelled'
        
        # Update candidate status back to Shortlisted
        if interview.candidate.status == 'Interview Scheduled':
            interview.candidate.status = 'Shortlisted'
        
        db.session.commit()
        
        # Send cancellation notification (implement later)
        # send_interview_cancellation_notification(interview)
        
        return jsonify({'success': True, 'message': 'Interview cancelled successfully!'})
    
    return jsonify({'success': False, 'message': 'Cannot cancel this interview'})

@hr_web_bp.route('/recruitment/interviews/<int:interview_id>/complete', methods=['POST'])
@login_required
def complete_interview(interview_id):
    """Mark interview as completed"""
    interview = Interview.query.get_or_404(interview_id)
    
    # Check if user has permission (HR, Admin, or panel member)
    panel_member = InterviewPanelMember.query.filter_by(
        panel_id=interview.panel_id,
        user_id=current_user.id
    ).first()
    

    
    if interview.status in ['Scheduled', 'Confirmed', 'In Progress']:
        interview.status = 'Completed'
        interview.actual_end_time = datetime.utcnow()
        
        # Update candidate status
        if interview.candidate.status == 'Interview Scheduled':
            interview.candidate.status = 'Interviewed'
        
        db.session.commit()
        
        flash('Interview marked as completed successfully!', 'success')
        return redirect(url_for('hr_web.view_interview', interview_id=interview_id))
    
    flash('Cannot complete this interview. Invalid status.', 'error')
    return redirect(url_for('hr_web.view_interview', interview_id=interview_id))

@hr_web_bp.route('/recruitment/interviews/<int:interview_id>/score', methods=['GET', 'POST'])
@login_required
def score_interview(interview_id):
    """Submit interview scores and feedback"""
    interview = Interview.query.get_or_404(interview_id)
    
    if request.method == 'POST':
        # Check if user is a panel member for this interview
        panel_member = InterviewPanelMember.query.filter_by(
            panel_id=interview.panel_id,
            user_id=current_user.id
        ).first()
        
        if not panel_member:
            flash('You are not a member of this interview panel.', 'error')
            return redirect(url_for('hr_web.view_interview', interview_id=interview_id))
        
        # Check if score already exists
        existing_score = InterviewScore.query.filter_by(
            interview_id=interview_id,
            panel_member_id=panel_member.id
        ).first()
        
        if existing_score:
            # Update existing score
            existing_score.technical_competence = request.form.get('technical_competence', type=float)
            existing_score.communication_skills = request.form.get('communication_skills', type=float)
            existing_score.problem_solving = request.form.get('problem_solving', type=float)
            existing_score.cultural_fit = request.form.get('cultural_fit', type=float)
            existing_score.leadership_potential = request.form.get('leadership_potential', type=float)
            existing_score.strengths = request.form.get('strengths')
            existing_score.weaknesses = request.form.get('weaknesses')
            existing_score.overall_feedback = request.form.get('overall_feedback')
            existing_score.recommendation = request.form.get('recommendation')
            existing_score.calculate_score()
            existing_score.submitted_at = datetime.utcnow()
        else:
            # Create new score
            score = InterviewScore(
                interview_id=interview_id,
                panel_member_id=panel_member.id,
                technical_competence=request.form.get('technical_competence', type=float),
                communication_skills=request.form.get('communication_skills', type=float),
                problem_solving=request.form.get('problem_solving', type=float),
                cultural_fit=request.form.get('cultural_fit', type=float),
                leadership_potential=request.form.get('leadership_potential', type=float),
                strengths=request.form.get('strengths'),
                weaknesses=request.form.get('weaknesses'),
                overall_feedback=request.form.get('overall_feedback'),
                recommendation=request.form.get('recommendation')
            )
            score.calculate_score()
            db.session.add(score)
        
        # Check if this is the first score being submitted
        if not existing_score:
            # This is the first score submission for this interview
            # Check if interview hasn't started yet
            if interview.status in ['Scheduled', 'Confirmed']:
                # Change status to "In Progress"
                interview.status = 'In Progress'
                # Set actual start time if not already set
                if not interview.actual_start_time:
                    interview.actual_start_time = datetime.utcnow()
                flash('Interview started and score submitted successfully!', 'success')
            else:
                flash('Interview score submitted successfully!', 'success')
        else:
            flash('Interview score updated successfully!', 'success')
        
        db.session.commit()
        
        # Update interview overall feedback if all panel members have submitted
        update_interview_overall_feedback(interview)
        
        return redirect(url_for('hr_web.view_interview', interview_id=interview_id))
    
    # For GET request
    # Check if user is a panel member
    panel_member = InterviewPanelMember.query.filter_by(
        panel_id=interview.panel_id,
        user_id=current_user.id
    ).first()
    
    if not panel_member:
        flash('You are not a member of this interview panel.', 'error')
        return redirect(url_for('hr_web.view_interview', interview_id=interview_id))
    
    # Check if score already exists
    existing_score = InterviewScore.query.filter_by(
        interview_id=interview_id,
        panel_member_id=panel_member.id
    ).first()
    
    return render_template('recruitment/score_form.html',
                         interview=interview,
                         panel_member=panel_member,
                         existing_score=existing_score,
                         title='Submit Interview Score')

def update_interview_overall_feedback(interview):
    """Update interview overall feedback based on panel scores"""
    scores = InterviewScore.query.filter_by(interview_id=interview.id).all()
    
    if not scores:
        return
    
    # Calculate average score
    total_score = sum(score.score or 0 for score in scores)
    avg_score = total_score / len(scores)
    
    # Determine overall recommendation based on average score
    if avg_score >= 4.5:
        recommendation = 'Strong Hire'
    elif avg_score >= 3.5:
        recommendation = 'Hire'
    elif avg_score >= 2.5:
        recommendation = 'Neutral'
    elif avg_score >= 1.5:
        recommendation = 'No Hire'
    else:
        recommendation = 'Strong No Hire'
    
    # Update interview
    interview.recommendation = recommendation
    
    # Update candidate overall score
    if interview.candidate:
        # Calculate weighted average with previous scores
        candidate = interview.candidate
        if candidate.overall_score and candidate.overall_score > 0:
            candidate.overall_score = (candidate.overall_score + avg_score) / 2
        else:
            candidate.overall_score = avg_score
        candidate.calculate_overall_score()
    
    db.session.commit()
    
    
    
    
@hr_web_bp.route('/recruitment/interviews/<int:interview_id>/select-winner', methods=['GET', 'POST'])
@login_required
def select_interview_winner(interview_id):
    """Select winner from interview panel and make offer"""
    interview = Interview.query.get_or_404(interview_id)
    
    # Check if interview is completed
    if interview.status != 'Completed':
        flash('Winner can only be selected from completed interviews.', 'error')
        return redirect(url_for('hr_web.view_interview', interview_id=interview_id))
    
   
    # Check if candidate already has an offer
    # FIX: Use filter() instead of filter_by() for __in operator
    existing_offer = OfferLetter.query.filter(
        OfferLetter.candidate_id == interview.candidate_id,
        OfferLetter.status.in_(['Draft', 'Sent', 'Accepted'])
    ).first()
    
    if existing_offer:
        flash(f'Candidate already has an offer ({existing_offer.status}).', 'warning')
        return redirect(url_for('hr_web.view_offer', offer_id=existing_offer.id))
    
    if request.method == 'POST':
        # Create offer letter
        offer = OfferLetter(
            candidate_id=interview.candidate_id,
            offer_title=request.form.get('position', interview.candidate.job_posting.title),
            department_id=interview.candidate.job_posting.department_id,
            position=request.form.get('position', interview.candidate.job_posting.title),
            employment_type=request.form.get('employment_type', 'Full-Time'),
            base_salary=request.form.get('base_salary', type=float),
            currency=request.form.get('currency', 'KES'),
            bonus=request.form.get('bonus', type=float) or 0,
            allowances=request.form.get('allowances', type=float) or 0,
            benefits=request.form.get('benefits', ''),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date(),
            probation_period_months=request.form.get('probation_period_months', type=int) or 3,
            reporting_to=request.form.get('reporting_to', ''),
            work_location=request.form.get('work_location', interview.candidate.job_posting.location or 'Main Office'),
            status='Draft'
        )
        
        db.session.add(offer)
        
        # Update candidate status
        interview.candidate.status = 'Offer Extended'
        
        # Update interview recommendation
        interview.recommendation = 'Strong Hire'
        
        db.session.commit()
        
        flash('Offer created successfully! Candidate marked as winner.', 'success')
        return redirect(url_for('hr_web.view_offer', offer_id=offer.id))
    
    # Get job posting details for pre-filling
    job = interview.candidate.job_posting
    
    return render_template('recruitment/select_winner.html',
                         interview=interview,
                         job=job,
                         timedelta=timedelta,
                         candidate=interview.candidate,
                         title=f'Select Winner - {interview.candidate.full_name}')
    
    
    
    
@hr_web_bp.route('/recruitment/selection')
@login_required
def recruitment_selection():
    """Main selection page - shows jobs with completed interviews and job offers"""
    # Get jobs that have interviews completed
    jobs = JobPosting.query.join(
        Candidate, Candidate.job_posting_id == JobPosting.id
    ).join(
        Interview, Interview.candidate_id == Candidate.id
    ).filter(
        Interview.status == 'Completed',
        JobPosting.status.in_(['Published', 'Closed']),
        Candidate.status == 'Interviewed'
    ).distinct().order_by(JobPosting.application_deadline.desc()).all()
    
    # For each job, get candidates who have completed interviews
    jobs_with_candidates = []
    for job in jobs:
        candidates = Candidate.query.filter_by(
            job_posting_id=job.id,
            status='Interviewed'
        ).all()
        
        # Calculate scores for each candidate
        candidates_with_scores = []
        for candidate in candidates:
            # Get the latest completed interview for this candidate
            interview = Interview.query.filter_by(
                candidate_id=candidate.id,
                status='Completed'
            ).order_by(Interview.actual_end_time.desc()).first()
            
            if interview:
                # Calculate average score from all panel members
                scores = InterviewScore.query.filter_by(
                    interview_id=interview.id
                ).all()
                
                avg_score = 0
                if scores:
                    total_score = sum([s.score or 0 for s in scores])
                    avg_score = total_score / len(scores)
                
                candidates_with_scores.append({
                    'candidate': candidate,
                    'interview': interview,
                    'avg_score': round(avg_score, 2)
                })
        
        if candidates_with_scores:
            jobs_with_candidates.append({
                'job': job,
                'candidates': sorted(candidates_with_scores, 
                                   key=lambda x: x['avg_score'], 
                                   reverse=True)
            })
    
    # Get all job offers with their relationships
    job_offers = OfferLetter.query.join(
        Candidate, Candidate.id == OfferLetter.candidate_id
    ).join(
        Department, Department.id == OfferLetter.department_id
    ).options(
        db.joinedload(OfferLetter.candidate),
        db.joinedload(OfferLetter.department)
    ).order_by(OfferLetter.created_at.desc()).all()
    
    return render_template('recruitment/selection.html',
                         jobs_with_candidates=jobs_with_candidates,
                         job_offers=job_offers,
                         datetime=datetime)
    
    


@hr_web_bp.route('/recruitment/selection/<int:job_id>/candidate/<int:candidate_id>/details')
@login_required
def selection_candidate_details(job_id, candidate_id):
    """View detailed interview scores for a candidate"""
    job = JobPosting.query.get_or_404(job_id)
    candidate = Candidate.query.get_or_404(candidate_id)
    
    # Verify candidate belongs to this job
    if candidate.job_posting_id != job.id:
        flash('Candidate does not belong to this job!', 'error')
        return redirect(url_for('hr_web.recruitment_selection'))
    
    # Get the completed interview for this candidate
    interview = Interview.query.filter_by(
        candidate_id=candidate.id,
        status='Completed'
    ).order_by(Interview.actual_end_time.desc()).first()
    
    if not interview:
        flash('No completed interview found for this candidate!', 'error')
        return redirect(url_for('hr_web.recruitment_selection'))
    
    # Get all scores for this interview
    scores = InterviewScore.query.filter_by(
        interview_id=interview.id
    ).all()
    
    # Calculate averages
    categories = ['technical_competence', 'communication_skills', 
                 'problem_solving', 'cultural_fit', 'leadership_potential']
    category_averages = {}
    
    for category in categories:
        valid_scores = [getattr(score, category) for score in scores 
                       if getattr(score, category) is not None]
        if valid_scores:
            category_averages[category] = sum(valid_scores) / len(valid_scores)
    
    return render_template('recruitment/selection_candidate_details.html',
                         job=job,
                         candidate=candidate,
                         interview=interview,
                         scores=scores,
                         category_averages=category_averages)    
    
    
    
    
@hr_web_bp.route('/recruitment/selection/<int:job_id>/select-winner/<int:candidate_id>', methods=['GET', 'POST'])
@login_required
def create_job_offer(job_id, candidate_id):
    """Create a job offer for the selected candidate"""
    job = JobPosting.query.get_or_404(job_id)
    candidate = Candidate.query.get_or_404(candidate_id)
    
    # Verify candidate belongs to this job
    if candidate.job_posting_id != job.id:
        flash('Candidate does not belong to this job!', 'error')
        return redirect(url_for('hr_web.recruitment_selection'))
    
    # Check if candidate already has an offer
    existing_offer = OfferLetter.query.filter(
        OfferLetter.candidate_id == candidate.id,
        OfferLetter.status.in_(['Draft', 'Sent', 'Accepted'])
    ).first()
    
    if existing_offer:
        flash(f'Candidate already has an offer ({existing_offer.status}).', 'warning')
        return redirect(url_for('hr_web.view_job_offer', offer_id=existing_offer.id))
    
    if request.method == 'POST':
        # Validate required fields
        start_date_str = request.form.get('start_date')
        if not start_date_str:
            flash('Start date is required!', 'error')
            return redirect(url_for('hr_web.create_job_offer', job_id=job_id, candidate_id=candidate_id))
        
        try:
            # Parse start date
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            
            # Parse expiry date if provided
            expiry_date = None
            expiry_date_str = request.form.get('expiry_date')
            if expiry_date_str:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            
            # Parse salary fields with default values
            base_salary = float(request.form.get('base_salary', 0))
            bonus = float(request.form.get('bonus', 0))
            allowances = float(request.form.get('allowances', 0))
            
            # Create offer letter
            offer = OfferLetter(
                candidate_id=candidate.id,
                offer_title=request.form.get('offer_title', f"Offer for {job.title}"),
                department_id=request.form.get('department_id', job.department_id),
                position=request.form.get('position', job.title),
                employment_type=request.form.get('employment_type', job.employment_type or 'Full-Time'),
                base_salary=base_salary,
                currency=request.form.get('currency', job.salary_currency or 'KES'),
                bonus=bonus,
                allowances=allowances,
                benefits=request.form.get('benefits', job.benefits or ''),
                start_date=start_date,
                probation_period_months=int(request.form.get('probation_period_months', 3)),
                reporting_to=request.form.get('reporting_to', ''),
                work_location=request.form.get('work_location', job.location or 'Head Office'),
                expiry_date=expiry_date,
                status='Draft',
                created_at=datetime.utcnow()
            )
            
            db.session.add(offer)
            
            # Update candidate status
            candidate.status = 'Offer Extended'
            candidate.updated_at = datetime.utcnow()
            
            # Get the completed interview for this candidate
            interview = Interview.query.filter_by(
                candidate_id=candidate.id,
                status='Completed'
            ).order_by(Interview.actual_end_time.desc()).first()
            
            if interview:
                interview.recommendation = 'Strong Hire'
            
            # Reject other interviewed candidates for this job (optional)
            if request.form.get('reject_others') == 'yes':
                other_candidates = Candidate.query.filter(
                    Candidate.job_posting_id == job.id,
                    Candidate.status == 'Interviewed',
                    Candidate.id != candidate.id
                ).all()
                
                for other_candidate in other_candidates:
                    other_candidate.status = 'Rejected'
                    other_candidate.updated_at = datetime.utcnow()
            
            # Update job status if all positions are filled
            if job.positions_available <= 1:
                job.status = 'Closed'
            
            db.session.commit()
            
            flash(f'Job offer created for {candidate.full_name}!', 'success')
            return redirect(url_for('hr_web.preview_job_offer', offer_id=offer.id))
            
        except ValueError as e:
            flash(f'Error parsing date or number: {str(e)}', 'error')
            return redirect(url_for('hr_web.create_job_offer', job_id=job_id, candidate_id=candidate_id))
    
    # Default start date (30 days from now)
    default_start_date = datetime.utcnow() + timedelta(days=30)
    # Default expiry date (7 days from now)
    default_expiry_date = datetime.utcnow() + timedelta(days=7)
    

    
    return render_template('recruitment/create_job_offer.html',
                         job=job,
                         candidate=candidate,
                         default_start_date=default_start_date.date(),
                         default_expiry_date=default_expiry_date.date())
    
    
    
    
@hr_web_bp.route('/recruitment/offers/<int:offer_id>/preview')
@login_required
def preview_job_offer(offer_id):
    """Preview job offer with email template"""
    offer = OfferLetter.query.get_or_404(offer_id)
    
    # Get company information (you might want to store this in a config or database)
    company_info = {
        'name': 'AstroCare Hospital',
        'address': '123 Medical Street, Health City',
        'city': 'Nairobi',
        'country': 'Kenya',
        'phone': '+254 700 123 456',
        'email': 'hr@astrocare.com',
        'website': 'www.astrocare.com',
        'logo_url': '/static/img/logo.png'
    }
    
    return render_template('recruitment/job_offer_preview.html',
                         offer=offer,
                         company=company_info)

import hashlib
import hmac
from itsdangerous import URLSafeTimedSerializer
from flask import current_app

def generate_offer_token(offer):
    """Generate a secure token for offer acceptance"""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    
    # Create token data
    token_data = {
        'offer_id': offer.id,
        'candidate_id': offer.candidate.id,
        'email': offer.candidate.email
    }
    
    # Generate token
    token = serializer.dumps(token_data)
    return token

def verify_offer_token(token, max_age=604800):  # 7 days expiry
    """Verify and decode offer token"""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        data = serializer.loads(token, max_age=max_age)
        return data
    except:
        return None


@hr_web_bp.route('/recruitment/offers/<int:offer_id>/send', methods=['POST', 'GET'])
@login_required
def send_job_offer(offer_id):
    """Send job offer via email"""
    offer = OfferLetter.query.get_or_404(offer_id)
    
    if offer.status != 'Draft':
        flash('Only draft offers can be sent.', 'error')
        return redirect(url_for('hr_web.view_job_offer', offer_id=offer_id))
    
    try:
        # Prepare email content
        subject = f"Job Offer: {offer.offer_title} - AstroCare"
        
        # Get offer acceptance URL
        offer_acceptance_url = url_for('hr_web.accept_offer', offer_id=offer.id, token=generate_offer_token(offer), _external=True)
        
        # Prepare plain text email
        plain_body = f"""
Dear {offer.candidate.full_name},

Congratulations! We are pleased to offer you the position of {offer.position} at AstroCare.

Position: {offer.position}
Department: {offer.department.name if offer.department else 'To be assigned'}
Start Date: {offer.start_date.strftime('%B %d, %Y')}
Employment Type: {offer.employment_type}
Reporting To: {offer.reporting_to or 'To be assigned'}

COMPENSATION DETAILS:
- Base Salary: {offer.currency} {offer.base_salary:,.2f} per month
- Performance Bonus: {offer.currency} {offer.bonus:,.2f} per year (if applicable)
- Allowances: {offer.currency} {offer.allowances:,.2f} per month
- Total Monthly Compensation: {offer.currency} {offer.total_compensation:,.2f}

CONTRACT DETAILS:
- Probation Period: {offer.probation_period_months} months
- Work Location: {offer.work_location or 'As assigned'}
- Benefits: {offer.benefits if offer.benefits else 'Standard company benefits'}

Please review the offer details and accept or decline through our portal. The offer will expire on {offer.expiry_date.strftime('%B %d, %Y') if offer.expiry_date else '7 days from receipt'}.

To view your offer details and respond, please visit:
{offer_acceptance_url}

If you have any questions, please don't hesitate to contact our HR department.

Best regards,
AstroCare HR Team
        """
        
        # Prepare HTML email
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; color: white; }}
        .content {{ padding: 30px; background: #f9f9f9; }}
        .details {{ background: white; border-radius: 8px; padding: 25px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
        .section-title {{ color: #667eea; border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-top: 30px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; color: #667eea; }}
        .highlight {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0; }}
        .deadline {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Congratulations!</h1>
            <p>Job Offer from AstroCare</p>
        </div>
        
        <div class="content">
            <p>Dear <strong>{offer.candidate.full_name}</strong>,</p>
            
            <p>We are delighted to extend an offer for the position of:</p>
            
            <div class="highlight">
                <h2>{offer.position}</h2>
                <p>{offer.offer_title}</p>
            </div>
            
            <div class="details">
                <h3 class="section-title">Offer Summary</h3>
                <table>
                    <tr>
                        <th>Position</th>
                        <td>{offer.position}</td>
                    </tr>
                    <tr>
                        <th>Department</th>
                        <td>{offer.department.name if offer.department else 'To be assigned'}</td>
                    </tr>
                    <tr>
                        <th>Employment Type</th>
                        <td>{offer.employment_type}</td>
                    </tr>
                    <tr>
                        <th>Start Date</th>
                        <td>{offer.start_date.strftime('%B %d, %Y')}</td>
                    </tr>
                    <tr>
                        <th>Reporting To</th>
                        <td>{offer.reporting_to or 'To be assigned'}</td>
                    </tr>
                </table>
                
                <h3 class="section-title">Compensation Package</h3>
                <table>
                    <tr>
                        <th>Base Salary (Monthly)</th>
                        <td>{offer.currency} {offer.base_salary:,.2f}</td>
                    </tr>
                    <tr>
                        <th>Performance Bonus (Annual)</th>
                        <td>{offer.currency} {offer.bonus:,.2f}</td>
                    </tr>
                    <tr>
                        <th>Allowances (Monthly)</th>
                        <td>{offer.currency} {offer.allowances:,.2f}</td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <th><strong>Total Monthly Compensation</strong></th>
                        <td><strong>{offer.currency} {offer.total_compensation:,.2f}</strong></td>
                    </tr>
                </table>
                
                <h3 class="section-title">Additional Details</h3>
                <table>
                    <tr>
                        <th>Probation Period</th>
                        <td>{offer.probation_period_months} months</td>
                    </tr>
                    <tr>
                        <th>Work Location</th>
                        <td>{offer.work_location or 'As assigned'}</td>
                    </tr>
                </table>
                
                {f'<p><strong>Benefits:</strong><br>{offer.benefits}</p>' if offer.benefits else ''}
            </div>
            
            <div class="deadline">
                <h4>⏰ Important Deadline</h4>
                <p>This offer expires on: <strong>{offer.expiry_date.strftime('%B %d, %Y %I:%M %p') if offer.expiry_date else '7 days from receipt'}</strong></p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{offer_acceptance_url}" class="button">VIEW FULL OFFER & RESPOND</a>
            </div>
            
            <p>You can also respond by:</p>
            <ul>
                <li>Clicking the button above</li>
                <li>Replying to this email</li>
                <li>Contacting our HR department directly</li>
            </ul>
            
            <p>If you have any questions about the offer or need clarification on any terms, please don't hesitate to contact us.</p>
            
            <p>We look forward to welcoming you to the AstroCare team!</p>
            
            <p>Best regards,<br>
            <strong>AstroCare HR Team</strong><br>
            Email: hr@astrocare.com<br>
            Phone: +254 700 000 000</p>
        </div>
        
        <div class="footer">
            <p>This is a confidential communication. If you are not the intended recipient, please delete this email.</p>
            <p>Offer ID: #{offer.id} | Generated on: {datetime.utcnow().strftime('%B %d, %Y')}</p>
        </div>
    </div>
</body>
</html>
        """
        
        # Send email using notification manager
        email_sent = notification_manager.send_email(
            subject=subject,
            recipients=[offer.candidate.email],
            body=plain_body,
            html_body=html_body,
            sender="AstroCare HR <hr@astrocare.com>"
        )
        
        if email_sent:
            # Update offer status
            offer.status = 'Sent'
            offer.sent_date = datetime.utcnow()
            
            # Set expiry date if not already set (default: 7 days)
            if not offer.expiry_date:
                offer.expiry_date = datetime.utcnow() + timedelta(days=7)
            
            # Update candidate status
            offer.candidate.status = 'Offer Extended'
            
            # Optional: Send SMS notification if phone is available
            if offer.candidate.phone:
                sms_message = f"Hi {offer.candidate.first_name}, AstroCare has sent you a job offer for {offer.position}. Check your email for details. Offer expires: {offer.expiry_date.strftime('%d/%m') if offer.expiry_date else '7 days'}. Reply to accept."
                notification_manager.send_sms(
                    message=sms_message,
                    recipients=[offer.candidate.phone]
                )
            
            db.session.commit()
            
            flash(f'Job offer successfully sent to {offer.candidate.full_name}! Email and SMS notifications have been dispatched.', 'success')
            
            # Log the action
            
        else:
            flash('Failed to send email notification. Please check your email configuration and try again.', 'error')
            logger.error(f"Failed to send job offer #{offer.id} to {offer.candidate.email}")
            
    except Exception as e:
        flash(f'Error sending job offer: {str(e)}', 'error')
        logger.error(f"Error sending job offer #{offer.id}: {str(e)}")
    
    return redirect(url_for('hr_web.view_job_offer', offer_id=offer_id))

@hr_web_bp.route('/recruitment/offers/<int:offer_id>/accept', methods=['GET', 'POST'])
def accept_offer(offer_id):
    """Candidate offer acceptance page"""
    token = request.args.get('token')
    
    if not token:
        flash('Invalid or missing offer link.', 'error')
        return redirect(url_for('main.index'))
    
    # Verify token
    token_data = verify_offer_token(token)
    if not token_data or token_data.get('offer_id') != offer_id:
        flash('Invalid or expired offer link.', 'error')
        return redirect(url_for('main.index'))
    
    offer = OfferLetter.query.get_or_404(offer_id)
    
    # Verify candidate matches token
    if offer.candidate.email != token_data.get('email'):
        flash('Unauthorized access to offer.', 'error')
        return redirect(url_for('main.index'))
    
    # Check if offer is still valid
    if offer.status != 'Sent':
        flash(f'This offer has already been {offer.status.lower()}.', 'warning')
        return render_template('recruitment/offer_response.html', offer=offer, status=offer.status)
    
    # Check if expired
    if offer.expiry_date and datetime.utcnow() > offer.expiry_date:
        offer.status = 'Expired'
        db.session.commit()
        flash('This offer has expired.', 'error')
        return render_template('recruitment/offer_response.html', offer=offer, status='Expired')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'accept':
            # Candidate accepts the offer
            offer.status = 'Accepted'
            offer.response_date = datetime.utcnow()
            offer.candidate.status = 'Offer Accepted'
            
            # Send acceptance confirmation email
            send_offer_response_notification(offer, 'accepted')
            
            flash('Congratulations! You have accepted the job offer. We will contact you with further instructions.', 'success')
            
        elif action == 'reject':
            # Candidate rejects the offer
            offer.status = 'Rejected'
            offer.response_date = datetime.utcnow()
            offer.candidate.status = 'Offer Rejected'
            
            # Send rejection confirmation email
            send_offer_response_notification(offer, 'rejected')
            
            flash('You have declined the job offer. Thank you for your time.', 'info')
        
        db.session.commit()
        return render_template('recruitment/offer_response.html', offer=offer, status=offer.status)
    
    # Calculate days remaining
    days_remaining = None
    if offer.expiry_date:
        days_remaining = (offer.expiry_date.date() - datetime.utcnow().date()).days
    
    return render_template('recruitment/accept_offer.html', 
                         offer=offer, 
                         days_remaining=days_remaining,
                         token=token)

def send_offer_response_notification(offer, response_type):
    """Send notification when candidate responds to offer"""
    try:
        if response_type == 'accepted':
            subject = f"Offer Accepted: {offer.candidate.full_name} - {offer.position}"
            body = f"""
            Great news! {offer.candidate.full_name} has accepted the job offer for {offer.position}.
            
            Candidate: {offer.candidate.full_name}
            Email: {offer.candidate.email}
            Phone: {offer.candidate.phone or 'Not provided'}
            Position: {offer.position}
            Start Date: {offer.start_date.strftime('%B %d, %Y')}
            Salary: {offer.currency} {offer.total_compensation:,.2f} per month
            
            Please proceed with onboarding.
            """
            
            # Send to HR team
            hr_email = current_app.config.get('HR_EMAIL', 'coinvillage.ke@gmail.com')
            notification_manager.send_email(
                subject=subject,
                recipients=[hr_email],
                body=body
            )
            
            # Send welcome email to candidate
            welcome_subject = f"Welcome to AstroCare!"
            welcome_body = f"""
            Dear {offer.candidate.full_name},
            
            We're thrilled to confirm your acceptance of the {offer.position} position!
            
            Next Steps:
            1. Our HR team will contact you within 48 hours
            2. You'll receive onboarding documents to complete
            3. Your start date is {offer.start_date.strftime('%B %d, %Y')}
            
            Welcome to the AstroCare family!
            
            Best regards,
            AstroCare HR Team
            """
            
            notification_manager.send_email(
                subject=welcome_subject,
                recipients=[offer.candidate.email],
                body=welcome_body
            )
            
        else:  # rejected
            subject = f"Offer Declined: {offer.candidate.full_name} - {offer.position}"
            body = f"""
            {offer.candidate.full_name} has declined the job offer for {offer.position}.
            
            Candidate: {offer.candidate.full_name}
            Email: {offer.candidate.email}
            Position: {offer.position}
            Reason: {request.form.get('reason', 'Not provided')}
            
            Please update the recruitment pipeline.
            """
            
            hr_email = current_app.config.get('HR_EMAIL', 'hr@astrocare.com')
            notification_manager.send_email(
                subject=subject,
                recipients=[hr_email],
                body=body
            )
            
    except Exception as e:
        logger.error(f"Error sending offer response notification: {str(e)}")

@hr_web_bp.route('/recruitment/offers/<int:offer_id>')
@login_required
def view_job_offer(offer_id):
    """View job offer details"""
    offer = OfferLetter.query.get_or_404(offer_id)
    
    # Calculate days remaining
    days_remaining = None
    if offer.expiry_date:
        days_remaining = (offer.expiry_date.date() - datetime.utcnow().date()).days
    
    return render_template('recruitment/view_job_offer.html',
                         offer=offer,
                         days_remaining=days_remaining)

@hr_web_bp.route('/recruitment/offers/<int:offer_id>/update-status', methods=['POST'])
@login_required
def update_offer_status(offer_id):
    """Update job offer status"""
    offer = OfferLetter.query.get_or_404(offer_id)
    new_status = request.form.get('status')
    
    valid_statuses = ['Draft', 'Sent', 'Accepted', 'Rejected', 'Withdrawn']
    
    if new_status not in valid_statuses:
        flash('Invalid status.', 'error')
        return redirect(url_for('hr_web.view_job_offer', offer_id=offer_id))
    
    offer.status = new_status
    offer.response_date = datetime.utcnow() if new_status in ['Accepted', 'Rejected'] else None
    
    # Update candidate status based on offer status
    if new_status == 'Accepted':
        offer.candidate.status = 'Offer Accepted'
        offer.candidate.hired_at = datetime.utcnow()
    elif new_status == 'Rejected':
        offer.candidate.status = 'Offer Rejected'
    
    db.session.commit()
    
    flash(f'Offer status updated to {new_status}.', 'success')
    return redirect(url_for('hr_web.view_job_offer', offer_id=offer_id))    




@hr_web_bp.route('/leave/request')
@login_required
def leave_request():
    """Request a new leave."""
    return render_template('leave-management/leave_request.html')

@hr_web_bp.route('/leave/requests')
@login_required
def leave_requests():
    """View all leave requests (for staff or admin)."""
    return render_template('leave-management/leave_requests.html')

@hr_web_bp.route('/leave/balances')
@login_required
def leave_balances():
    """View leave balances for staff."""
    return render_template('leave-management/leave_balances.html')

@hr_web_bp.route('/leave/calendar')
@login_required
def leave_calendar():
    """View a calendar of leave schedules."""
    return render_template('leave-management/leave_calendar.html')


@hr_web_bp.route('/leave/types', methods=['GET', 'POST'])
@login_required
def leave_types():
    if not current_user.has_privilege('hr:leave:types'):
        flash('You do not have permission to manage leave types.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            name = request.form.get('name')
            code = request.form.get('code')
            is_paid = request.form.get('is_paid') == '1'
            max_days = request.form.get('max_days_per_year')
            requires_doc = request.form.get('requires_document') == '1'
            description = request.form.get('description')

            if not all([name, code, max_days]):
                flash('Name, code, and maximum days are required.', 'danger')
                return redirect(url_for('hr_web.leave_types'))

            lt = LeaveType(
                name=name,
                code=code.upper(),
                is_paid=is_paid,
                max_days_per_year=float(max_days),
                requires_document=requires_doc,
                description=description,
                is_active=True
            )
            db.session.add(lt)
            db.session.commit()
            flash(f'Leave type "{name}" added.', 'success')
            return redirect(url_for('hr_web.leave_types'))

        elif action == 'edit':
            lt_id = request.form.get('leave_type_id')
            lt = LeaveType.query.get_or_404(lt_id)
            lt.name = request.form.get('name')
            lt.code = request.form.get('code').upper()
            lt.is_paid = request.form.get('is_paid') == '1'
            lt.max_days_per_year = float(request.form.get('max_days_per_year'))
            lt.requires_document = request.form.get('requires_document') == '1'
            lt.description = request.form.get('description')
            db.session.commit()
            flash(f'Leave type "{lt.name}" updated.', 'success')
            return redirect(url_for('hr_web.leave_types'))

        elif action == 'toggle':
            lt_id = request.form.get('leave_type_id')
            lt = LeaveType.query.get_or_404(lt_id)
            lt.is_active = not lt.is_active
            db.session.commit()
            status = 'activated' if lt.is_active else 'deactivated'
            flash(f'Leave type "{lt.name}" {status}.', 'success')
            return redirect(url_for('hr_web.leave_types'))

        elif action == 'delete':
            lt_id = request.form.get('leave_type_id')
            lt = LeaveType.query.get_or_404(lt_id)
            # Check if there are existing allocations/requests? For simplicity, we delete if none
            if lt.allocations.first() or lt.requests.first():
                flash(f'Cannot delete "{lt.name}" because it has existing allocations or requests.', 'danger')
            else:
                db.session.delete(lt)
                db.session.commit()
                flash(f'Leave type "{lt.name}" deleted.', 'info')
            return redirect(url_for('hr_web.leave_types'))

    # GET – display
    leave_types = LeaveType.query.order_by(LeaveType.name).all()
    return render_template('leave-management/leave_types.html', leave_types=leave_types)

@hr_web_bp.route('/leave/approvals')
@login_required
def leave_approvals():
    """Approve or reject pending leave requests."""
    return render_template('leave-management/leave_approvals.html')

@hr_web_bp.route('/leave/reports')
@login_required
def leave_reports():
    """Generate reports on leave usage."""
    return render_template('leave-management/leave_reports.html')





@hr_web_bp.route('/leave/manage', methods=['GET', 'POST'])
@login_required
def leave_manage():
    if request.method == 'POST':
        action = request.form.get('action')

        # --- Individual allocation ---
        if action == 'allocate_individual':
            employee_id = request.form.get('employee_id')
            leave_type_id = request.form.get('leave_type_id')
            start_date_str = request.form.get('start_date')
            days = float(request.form.get('days', 0))
            notes = request.form.get('notes')

            if not all([employee_id, leave_type_id, start_date_str, days]):
                flash('All fields are required.', 'danger')
                return redirect(url_for('hr_web.leave_manage'))

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = start_date + timedelta(days=int(days) - 1)
            reason = f"Leave allocation by HR"  # or use notes as reason

            # Create approved leave request
            leave_req = LeaveRequest(
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                start_date=start_date,
                end_date=end_date,
                days_requested=days,
                reason=notes or reason,
                status='approved',
                approved_by=current_user.id,
                approved_at=datetime.utcnow(),
                approval_notes='Allocated by HR'
            )
            db.session.add(leave_req)
            db.session.commit()

            flash('Leave allocated successfully.', 'success')
            # Redirect back to same department and year
            return redirect(url_for('hr_web.leave_manage',
                                    department=request.form.get('department_id'),
                                    year=start_date.year))

        # --- Bulk allocation by department ---
        elif action == 'allocate_department':
            department_id = request.form.get('department_id')
            leave_type_id = request.form.get('leave_type_id')
            start_date_str = request.form.get('start_date')
            days = float(request.form.get('days', 0))
            notes = request.form.get('notes')

            if not all([department_id, leave_type_id, start_date_str, days]):
                flash('All fields are required.', 'danger')
                return redirect(url_for('hr_web.leave_manage'))

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = start_date + timedelta(days=int(days) - 1)

            employees = User.query.filter_by(department_id=department_id, is_active=True).all()
            if not employees:
                flash('No active employees found in this department.', 'warning')
                return redirect(url_for('hr_web.leave_manage'))

            count = 0
            for emp in employees:
                leave_req = LeaveRequest(
                    employee_id=emp.id,
                    leave_type_id=leave_type_id,
                    start_date=start_date,
                    end_date=end_date,
                    days_requested=days,
                    reason=notes or f"Bulk allocation for department",
                    status='approved',
                    approved_by=current_user.id,
                    approved_at=datetime.utcnow(),
                    approval_notes='Bulk allocation by HR'
                )
                db.session.add(leave_req)
                count += 1
            db.session.commit()
            flash(f'Leave allocated to {count} employees.', 'success')
            return redirect(url_for('hr_web.leave_manage',
                                    department=department_id,
                                    year=start_date.year))

        else:
            flash('Invalid action.', 'danger')
            return redirect(url_for('hr_web.leave_manage'))

    # --- GET: display form for department selection ---
    year = request.args.get('year', datetime.utcnow().year, type=int)
    department_id = request.args.get('department', type=int)

    employees = []
    if department_id:
        employees = User.query.filter_by(department_id=department_id, is_active=True).order_by(User.full_name).all()

    leave_types = LeaveType.query.filter_by(is_active=True).all()
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        'leave-management/leave_manage.html',
        year=year,
        employees=employees,
        leave_types=leave_types,
        departments=departments,
        selected_department=department_id
    )
    
    

@hr_web_bp.route('/leave/offs')
@login_required
def leave_offs():
    """Manage public holidays, rest days, and company offs."""
    return render_template('hr/leave_offs.html')