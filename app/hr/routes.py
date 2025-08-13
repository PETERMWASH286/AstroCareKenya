# app/hr/routes.py
import json
import uuid
from flask import abort, render_template, send_file, send_from_directory
from flask import request, redirect, url_for, flash, current_app
from wtforms import ValidationError

from app.auth.models import User
from app.hr.forms import DisciplinaryActionForm
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
    AppealStatus, DisciplinaryAction, DisciplinaryActionStatus, DisciplinaryActionType, DisciplinaryAppeal, DisciplinaryCase, DisciplinaryCaseStatus, DisciplinaryCaseType, DisciplinaryDocument, DisciplinaryHearing, DisciplinaryInvestigation, DisciplinaryPolicy, DisciplinaryReport, DisciplinarySeverity, HearingParticipant, HearingStatus, InvestigationEvidence, InvestigationStatus, PayrollPeriod, Payroll, Payslip, EarningType, DeductionType,
    PayslipEarning, PayslipDeduction, PAYEBand, NHIFRate, NSSFRate,
    EmployeePayrollInfo, PayrollAdjustment, PayrollLoan, LoanRepayment,
    PayrollReport, DutyShift, DutyRota, DutyAssignment, AttendanceRecord, LeaveRequest, LeaveType, PolicyCategory
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
    
    # Calculate statistics
    total_staff = User.query.count()
    active_staff = User.query.filter_by(is_active=True).count()
    departments_count = Department.query.count()
    
    # Calculate average tenure (in years)
    avg_tenure = 0  # Placeholder - you'd need a start_date field in User model
    
    # Calculate department distribution
    dept_distribution = db.session.query(
        Department.name.label('dept_name'),
        func.count(User.id).label('staff_count')
    ).outerjoin(User, Department.id == User.department_id)\
     .group_by(Department.name)\
     .order_by(func.count(User.id).desc())\
     .all()
    
    dept_labels = [dept.dept_name for dept in dept_distribution]
    dept_values = [dept.staff_count for dept in dept_distribution]
    
    stats = {
        'total_staff': total_staff,
        'active_staff': active_staff,
        'active_percentage': round((active_staff / total_staff) * 100) if total_staff else 0,
        'departments': departments_count,
        'avg_tenure': avg_tenure
    }
    
    return render_template(
        'staff_directory.html',
        staff=staff,
        stats=stats,
        dept_labels=dept_labels,
        dept_values=dept_values
    )



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

# Bio Management Routes
@hr_web_bp.route('/staff/bio/<int:user_id>', methods=['GET', 'POST'])
def staff_bio(user_id):
    employee = User.query.get_or_404(user_id)
    bio = EmployeeBio.query.filter_by(user_id=user_id).first()
        # Calculate completion status
    status = {
        'bio_exists': bool(bio),
        'has_education': bio and bool(bio.educations),
        'has_relatives': bio and bool(bio.relatives),
        'has_work_history': bio and bool(bio.work_histories),
        'has_certifications': bio and bool(bio.certifications),
        'has_attachments': bio and bool(bio.attachments),
    }
    if request.method == 'POST':
        if not bio:
            bio = EmployeeBio(user_id=user_id)
        
        # Personal Details
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
        
        # Financial Details
        bio.bank_name = request.form.get('bank_name')
        bio.bank_branch = request.form.get('bank_branch')
        bio.bank_account_number = request.form.get('bank_account_number')
        bio.bank_routing_number = request.form.get('bank_routing_number')
        bio.tax_id = request.form.get('tax_id')
        bio.social_security_number = request.form.get('social_security_number')
        
        # Emergency & Medical
        bio.emergency_contact_name = request.form.get('emergency_contact_name')
        bio.emergency_contact_relationship = request.form.get('emergency_contact_relationship')
        bio.emergency_contact_phone = request.form.get('emergency_contact_phone')
        bio.insurance_provider = request.form.get('insurance_provider')
        bio.insurance_number = request.form.get('insurance_number')
        bio.medical_conditions = request.form.get('medical_conditions')
        bio.allergies = request.form.get('allergies')
        
        try:
            if not bio.id:
                db.session.add(bio)
            db.session.commit()
            flash('Bio updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating bio: {str(e)}', 'danger')
    
    return render_template(
        'staff_bio.html', 
        employee=employee,
        bio=bio,
                status=status  # Pass status to template

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
            period.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            period.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            period.pay_date = datetime.strptime(data['pay_date'], '%Y-%m-%d').date()
            period.frequency = data['frequency']
            period.is_closed = data['is_closed']
            db.session.commit()
            return jsonify({'success': True, 'message': 'Period updated'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 400

    elif request.method == 'DELETE':
        try:
            db.session.delete(period)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Period deleted'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 400

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
            
            # Check if payroll already exists for period
            existing = Payroll.query.filter_by(period_id=period_id).first()
            if existing:
                return jsonify({
                    'success': False,
                    'message': 'Payroll already processed for this period'
                }), 400
            
            # Calculate payroll and create records
            payroll_data = calculate_payroll(period_id, current_user.id)
            
            # Create payroll master record
            payroll = Payroll(
                period_id=period_id,
                processed_by=current_user.id,
                total_gross=payroll_data['totals']['gross'],
                total_deductions=payroll_data['totals']['deductions'],
                total_net=payroll_data['totals']['net'],
                status='Draft'
            )
            db.session.add(payroll)
            db.session.flush()  # Get payroll ID before commit
            
            # Create payslips
            for emp_id, details in payroll_data['employees'].items():
                payslip = Payslip(
                    payroll_id=payroll.id,
                    employee_id=emp_id,
                    basic_salary=details['basic_salary'],
                    gross_earnings=details['gross_earnings'],
                    total_deductions=details['total_deductions'],
                    net_pay=details['net_pay'],
                    payment_method=details['payment_method']
                )
                db.session.add(payslip)
                db.session.flush()
                
                # Add earnings
                for earning in details['earnings']:
                    db.session.add(PayslipEarning(
                        payslip_id=payslip.id,
                        earning_type_id=earning['type_id'],
                        amount=earning['amount']
                    ))
                
                # Add deductions
                for deduction in details['deductions']:
                    db.session.add(PayslipDeduction(
                        payslip_id=payslip.id,
                        deduction_type_id=deduction['type_id'],
                        amount=deduction['amount']
                    ))
            
            db.session.commit()
            return jsonify({
                'success': True,
                'payroll_id': payroll.id,
                'message': 'Payroll processed successfully'
            }), 201
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Payroll processing error: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500

    # GET: Show form for payroll processing
    open_periods = PayrollPeriod.query.filter_by(is_closed=False).all()
    
    # Get active employee count
    active_employees = User.query.filter_by(is_active=True).count()
    
    # Get recent payrolls with period relationship
    recent_payrolls = Payroll.query.options(db.joinedload(Payroll.period))\
        .order_by(Payroll.processed_at.desc())\
        .limit(5)\
        .all()
    
    # Prepare period data for frontend
    period_data = []
    for period in open_periods:
        period_data.append({
            'id': period.id,
            'start_date': period.start_date.strftime('%d %b %Y'),
            'end_date': period.end_date.strftime('%d %b %Y'),
            'pay_date': period.pay_date.strftime('%d %b %Y'),
            'frequency': period.frequency.value
        })
    
    return render_template(
        'process_payroll.html',
        periods=open_periods,
        period_data=json.dumps(period_data),
        active_employees=active_employees,
        recent_payrolls=recent_payrolls
    )

@hr_web_bp.route('/payroll/approve/<int:payroll_id>', methods=['POST'])
@login_required
def approve_payroll(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    try:
        payroll.status = 'Approved'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Payroll approved'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

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
    
    query = Payslip.query.join(Payroll).join(PayrollPeriod)
    
    if payroll_id:
        query = query.filter(Payslip.payroll_id == payroll_id)
    if employee_id:
        query = query.filter(Payslip.employee_id == employee_id)
    if period_id:
        query = query.filter(Payroll.period_id == period_id)
    
    payslips = query.order_by(PayrollPeriod.start_date.desc()).all()
    return render_template('employees_payslips.html', payslips=payslips)

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
            loan = PayrollLoan(
                employee_id=data['employee_id'],
                loan_amount=Decimal(data['loan_amount']),
                balance=Decimal(data['loan_amount']),
                monthly_deduction=Decimal(data['monthly_deduction']),
                start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
                is_active=True
            )
            db.session.add(loan)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Loan created'}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 400

    # GET: List loans with filters
    employee_id = request.args.get('employee_id')
    status = request.args.get('status', 'active')  # active/closed
    
    query = PayrollLoan.query
    
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'closed':
        query = query.filter_by(is_active=False)
    
    loans = query.order_by(PayrollLoan.start_date.desc()).all()
    return render_template('payroll_loans.html', loans=loans)

@hr_web_bp.route('/payroll/loans/<int:id>/repayments', methods=['POST'])
@login_required
def add_loan_repayment(id):
    loan = PayrollLoan.query.get_or_404(id)
    try:
        data = request.get_json()
        amount = Decimal(data['amount'])
        
        # Create repayment
        repayment = LoanRepayment(
            loan_id=loan.id,
            amount=amount,
            payment_date=datetime.utcnow().date()
        )
        
        # Update loan balance
        loan.balance -= amount
        if loan.balance <= 0:
            loan.is_active = False
        
        db.session.add(repayment)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Repayment recorded'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

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

@hr_web_bp.route('/payroll/deduction-types', methods=['POST'])
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
# Recruitment
@hr_web_bp.route('/recruitment')
def recruitment():
    return render_template('hr/recruitment.html')


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