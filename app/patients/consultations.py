# app/patients/consultations.py
import json
import re
import threading
import time
from flask import Blueprint, current_app, render_template, request, redirect, session, url_for, flash, jsonify
from flask_login import current_user
import requests
from app.auth.models import User
from app.extensions import db
from datetime import datetime
from sqlalchemy import exc

from app.finance.models import Insurance
from app.lab.models import LabTestResult
from .models import LabTest, Medication, Patient, Radiology, Service, Visit, Consultation, Vitals

consultations_web_bp = Blueprint(
    'consultations_web', __name__,
    url_prefix='/patients'
)

# app/patients/consultations.py
from sqlalchemy.orm import joinedload

@consultations_web_bp.route('/consultation-queue', methods=['GET', 'POST'])
def consultation_queue():
    if request.method == 'POST':
        # This block can handle AJAX requests for setting the active tab
        # or other POST requests if you introduce them later.
        # For now, we'll primarily use GET for initial load and JS for updates.
        pass

    # Get the last active tab from the session, default to 'consultation'
    active_tab = session.get('active_consultation_tab', 'consultation')

    # Define walk-in visit categories that should NOT appear in consultation queue after completion
    # These are visits that inherently don't require a doctor's consultation after lab/rad
    walk_in_visit_types_to_exclude = ['walk_in_lab', 'walk_in_rad', 'walk_in_pharm', 'optician_clinic', 'dental_clinic']

    # 1. Patients currently in the consultation queue
    waiting_for_consultation = (
        Visit.query
        .filter_by(current_position='consultation', visit_status='in_progress')
        .options(joinedload(Visit.vitals))  # Eager load vitals
        .options(joinedload(Visit.patient)) # Eager load patient info
        .order_by(Visit.visit_date)
        .all()
    )

    # 2. Lab tests that are completed and paid AND require consultation (i.e., not a walk-in for lab)
    completed_paid_lab_tests_raw = (
        LabTest.query
        .filter_by(status='completed', payment_status='paid')
        # Filter out lab tests whose *visit type* indicates they are purely walk-in lab
        # We need to join through consultation to get to visit, and then check visit_type_category
        .join(LabTest.consultation) # Inner join ensures only tests with a consultation are considered initially
        .join(Consultation.visit)
        .filter(Visit.visit_type_category.notin_(walk_in_visit_types_to_exclude))
        .options(joinedload(LabTest.consultation).joinedload(Consultation.visit).joinedload(Visit.patient))
        .options(joinedload(LabTest.service)) # Eager load service details (e.g., test name)
        .options(joinedload(LabTest.done_by)) # Eager load who completed it
        .order_by(LabTest.completed_at.desc()) # Order by most recently completed
        .all()
    )

    # 3. Radiology orders that are completed and paid AND require consultation (i.e., not a walk-in for rad)
    completed_paid_radiology_orders_raw = (
        Radiology.query # Assuming you have a Radiology model
        .filter_by(status='completed', payment_status='paid')
        # Filter out radiology orders whose *visit type* indicates they are purely walk-in rad
        .join(Radiology.consultation) # Inner join ensures only tests with a consultation are considered initially
        .join(Consultation.visit)
        .filter(Visit.visit_type_category.notin_(walk_in_visit_types_to_exclude))
        .options(joinedload(Radiology.consultation).joinedload(Consultation.visit).joinedload(Visit.patient))
        .options(joinedload(Radiology.service)) # Eager load service details (e.g., scan type)
        .options(joinedload(Radiology.done_by)) # Eager load who completed it
        .order_by(Radiology.completed_at.desc()) # Order by most recently completed
        .all()
    )

    # Process lab tests to combine by visit
    combined_lab_tests = {}
    for test in completed_paid_lab_tests_raw:
        # Check if consultation exists to avoid errors on pure walk-ins that somehow slipped
        # Although the query should already filter this, it's a good defensive check
        if test.consultation and test.consultation.visit:
            visit_id = test.consultation.visit.id
            if visit_id not in combined_lab_tests:
                combined_lab_tests[visit_id] = {
                    'patient': test.consultation.visit.patient,
                    'visit': test.consultation.visit,
                    'tests': [],
                    'interpretations': set(), # Use a set to store unique interpretations
                    'completed_at': test.completed_at # Add completed_at here
                }
            combined_lab_tests[visit_id]['tests'].append(test.service.name)
            if test.interpretation:
                combined_lab_tests[visit_id]['interpretations'].add(test.interpretation)
    
    # Convert set of interpretations to a string or list as needed for display
    for visit_id in combined_lab_tests:
        combined_lab_tests[visit_id]['interpretations'] = list(combined_lab_tests[visit_id]['interpretations'])


    # Process radiology orders to combine by visit
    combined_radiology_orders = {}
    for order in completed_paid_radiology_orders_raw:
        # Check if consultation exists for the same defensive reason
        if order.consultation and order.consultation.visit:
            visit_id = order.consultation.visit.id
            if visit_id not in combined_radiology_orders:
                combined_radiology_orders[visit_id] = {
                    'patient': order.consultation.visit.patient,
                    'visit': order.consultation.visit,
                    'scans': [],
                    'interpretations': set(),
                    'completed_at': order.completed_at # Add completed_at here
                }
            combined_radiology_orders[visit_id]['scans'].append(order.service.name)
            if order.interpretation:
                combined_radiology_orders[visit_id]['interpretations'].add(order.interpretation)
                
    for visit_id in combined_radiology_orders:
        combined_radiology_orders[visit_id]['interpretations'] = list(combined_radiology_orders[visit_id]['interpretations'])


    return render_template('consultation_queue.html',
                           waiting_for_consultation=waiting_for_consultation,
                           completed_paid_lab_tests=list(combined_lab_tests.values()),
                           completed_paid_radiology_orders=list(combined_radiology_orders.values()),
                           active_tab=active_tab)

@consultations_web_bp.route('/optical-consultation-queue', methods=['GET'])
def optical_consultation_queue():
    """
    Displays the queue of patients waiting for an optical consultation.
    This queue includes only visits for the 'optician_clinic' that are paid and in progress.
    """
    
    # 1. Patients currently in the optical consultation queue
    # The query filters for visits with the specific visit_type_category and payment status
    waiting_for_optical_consultation = (
        Visit.query
        .filter_by(
            current_position='optician_clinic',
            visit_status='in_progress',
            payment_status='paid'  # Filtering for paid visits
        )
        .options(joinedload(Visit.vitals))      # Eager load vitals
        .options(joinedload(Visit.patient))     # Eager load patient info
        .order_by(Visit.visit_date)
        .all()
    )

    # You can also add logic to fetch completed lab or radiology results
    # that are for the optician to review, similar to your example.
    # For now, we'll just return the queue of waiting patients.

    return render_template('optician/optical_consultation_queue.html',
                           waiting_for_optical_consultation=waiting_for_optical_consultation)

@consultations_web_bp.route('/dental-consultation-queue', methods=['GET'])
def dental_consultation_queue():
    """
    Displays the queue of patients waiting for a dental consultation.
    This queue includes only visits for the 'dental_clinic' that are paid and in progress.
    """
    
    # Query for patients currently in the dental consultation queue
    waiting_for_dental_consultation = (
        Visit.query
        .filter_by(
            current_position='dental_clinic',
            visit_status='in_progress',
            payment_status='paid'  # Filtering for paid visits
        )
        .options(joinedload(Visit.vitals))      # Eager load vitals
        .options(joinedload(Visit.patient))     # Eager load patient info
        .order_by(Visit.visit_date)
        .all()
    )

    return render_template('dental/dental_consultation_queue.html',
                           waiting_for_dental_consultation=waiting_for_dental_consultation)

# Add a route to update the session with the active tab
@consultations_web_bp.route('/set-active-tab', methods=['POST'])
def set_active_tab():
    data = request.get_json()
    active_tab = data.get('tab')
    if active_tab:
        session['active_consultation_tab'] = active_tab
        return {'status': 'success'}, 200
    return {'status': 'error', 'message': 'No tab provided'}, 400


# Patient Detail View
@consultations_web_bp.route('/<int:patient_id>')
def view_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    latest_vitals = Vitals.query.filter_by(patient_id=patient_id).order_by(Vitals.recorded_at.desc()).first()
    consultations = Consultation.query.filter_by(patient_id=patient_id).order_by(Consultation.created_at.desc()).all()
    return render_template('view_patient.html',
                         patient=patient,
                         latest_vitals=latest_vitals,
                         consultations=consultations)



@consultations_web_bp.route('/visits/<int:visit_id>/add-treatment', methods=['GET', 'POST'])
def add_treatment(visit_id):
    visit = Visit.query.get_or_404(visit_id)
    
    # Fetch existing consultation if it exists
    consultation = Consultation.query.filter_by(visit_id=visit_id).first()
    
    # Fetch existing treatments
    existing_medications = []
    existing_lab_tests = []
    existing_radiology = []
    existing_lab_results = {} # Dictionary to hold lab results keyed by lab_test_id

    if consultation:
        existing_medications = Medication.query.filter_by(consultation_id=consultation.id).all()
        existing_lab_tests = LabTest.query.filter_by(consultation_id=consultation.id).all()
        existing_radiology = Radiology.query.filter_by(consultation_id=consultation.id).all()

        # Fetch lab results for each existing lab test
        for lab_test_order in existing_lab_tests:
            results = LabTestResult.query.filter_by(lab_test_id=lab_test_order.id).all()
            if results:
                existing_lab_results[lab_test_order.id] = results


    # Fetch the patient's insurance record
    insurance_obj = None
    if visit.patient.payment_method == 'insurance' and visit.patient.insurance_provider:
        insurance_obj = Insurance.query.get(visit.patient.insurance_provider)

    # Get services grouped by category
    services = Service.query.all()
    medications_list = [s for s in services if s.category == 'Pharmacy'] # Renamed to avoid conflict with Medication model
    lab_tests_list = [s for s in services if s.category == 'Laboratory']
    imaging_services = [s for s in services if s.category == 'Radiology']

    if request.method == 'POST':
        try:
            # Create or update Consultation
            if not consultation:
                consultation = Consultation(
                    patient_id=visit.patient_id,
                    visit_id=visit_id,
                    history=request.form.get('history'),
                    examination=request.form.get('examination'),
                    diagnosis=request.form.get('diagnosis'),
                    treatment_plan=request.form.get('treatment_plan'),
                    notes=request.form.get('notes')
                )
                consultation.treated_by = current_user
                db.session.add(consultation)
            else:
                consultation.history = request.form.get('history')
                consultation.examination = request.form.get('examination')
                consultation.diagnosis = request.form.get('diagnosis')
                consultation.treatment_plan = request.form.get('treatment_plan')
                consultation.notes = request.form.get('notes')
                consultation.treated_by = current_user

            db.session.flush() # Flush to get consultation.id if it's new

            # --- Process Medications (Updated Logic) ---
            drug_ids = request.form.getlist('drug[]')
            drug_doses = request.form.getlist('drug_dose[]')
            drug_frequencies = request.form.getlist('drug_frequency[]')
            drug_durations = request.form.getlist('drug_duration[]')
            drug_quantities = request.form.getlist('drug_quantity[]')
            drug_prices = request.form.getlist('drug_price[]')

            # Map existing medications by service_id for quick lookup
            # This is crucial for the "add or update" logic
            existing_medications_map = {med.service_id: med for med in Medication.query.filter_by(consultation_id=consultation.id).all()}
            
            submitted_medication_service_ids = set() # To track which medications were submitted

            for i, service_id_str in enumerate(drug_ids):
                # Only process if a medication was actually selected (service_id is not empty)
                if not service_id_str:
                    continue 
                
                service_id = int(service_id_str)
                service = Service.query.get(service_id)
                
                if not service or service.category != 'Pharmacy':
                    flash(f"Invalid medication selected for ID: {service_id_str}. Skipping.", 'warning')
                    continue # Skip invalid entries or non-pharmacy services

                submitted_medication_service_ids.add(service_id) # Mark as submitted

                # Safely get values, providing a default if the index is out of range
                dose = drug_doses[i] if i < len(drug_doses) else ''
                frequency = drug_frequencies[i] if i < len(drug_frequencies) else 'OD'
                
                duration_str = drug_durations[i] if i < len(drug_durations) else ''
                duration = None # Default to None if empty or invalid, allowing NULL in DB

                if duration_str:
                    try:
                        duration = int(duration_str)
                    except ValueError:
                        flash(f"Invalid duration value '{duration_str}' for {service.name}. Please enter a number.", 'warning')
                        duration = None # Set to None if conversion fails

                try:
                    quantity = int(drug_quantities[i]) if i < len(drug_quantities) and drug_quantities[i] else 1
                except ValueError:
                    quantity = 1 # Default to 1 if quantity is invalid
                
                try:
                    price = float(drug_prices[i]) if i < len(drug_prices) and drug_prices[i] else service.price
                except ValueError:
                    price = service.price # Fallback to service price if hidden price is invalid

                # Check if this medication already exists for this consultation
                if service_id in existing_medications_map:
                    # Update existing medication
                    medication = existing_medications_map[service_id]
                    medication.dose = dose
                    medication.frequency = frequency
                    medication.duration = duration
                    medication.quantity = quantity
                    medication.price = price
                    # No need to add to session, it's already tracked
                else:
                    # Add new medication
                    medication = Medication(
                        consultation=consultation,
                        service=service,
                        dose=dose,
                        frequency=frequency,
                        duration=duration,
                        quantity=quantity,
                        price=price,
                        prescribed_at=datetime.utcnow() # Add prescribed_at
                    )
                    db.session.add(medication)
            
            # Delete medications that were removed by the user (not in submitted_medication_service_ids)
            for med_id, medication_obj in existing_medications_map.items():
                if med_id not in submitted_medication_service_ids:
                    db.session.delete(medication_obj)
            # --- End Process Medications ---


            # Process Lab Tests (Existing logic, no changes needed here for the medication error)
            submitted_lab_service_ids = [int(sid) for sid in request.form.getlist('lab_tests') if sid] # Filter out empty strings
            
            current_consultation_lab_tests = LabTest.query.filter_by(consultation_id=consultation.id).all()
            existing_lab_service_ids = {lt.service_id for lt in current_consultation_lab_tests} # Use a set for faster lookup

            # Delete lab tests that were removed by the user
            for lab_test_order in current_consultation_lab_tests:
                if lab_test_order.service_id not in submitted_lab_service_ids:
                    # Consider adding checks for status before deleting to prevent data loss
                    # e.g., if lab_test_order.status == 'requested':
                    db.session.delete(lab_test_order)

            # Add new lab tests
            for service_id in submitted_lab_service_ids:
                if service_id not in existing_lab_service_ids:
                    service = Service.query.get(service_id)
                    if service and service.category == 'Laboratory':
                        lab_test = LabTest(
                            consultation=consultation,
                            service=service,
                            status='requested'
                        )
                        db.session.add(lab_test)
            
            # Process Radiology Orders (Existing logic, no changes needed here)
            # This logic explicitly deletes all and re-adds, which is fine if that's the intended behavior for radiology
            Radiology.query.filter_by(consultation_id=consultation.id).delete()
            for service_id_str in request.form.getlist('imaging_studies'):
                if not service_id_str: # Skip if empty
                    continue
                service_id = int(service_id_str)
                service = Service.query.get(service_id)
                if service and service.category == 'Radiology':
                    radiology = Radiology(
                        consultation=consultation,
                        service=service,
                        status='requested'
                    )
                    db.session.add(radiology)

            db.session.commit() # Commit after processing medications, lab tests, and radiology

            # IMPORTANT: Process Lab Test Results (Your existing logic for this section is good)
            # Make sure to re-fetch existing_lab_tests after the above commit
            # to ensure you're working with the most up-to-date lab test orders.
            
            # Re-fetch existing_lab_tests to include newly added ones after the commit
            db.session.refresh(consultation) # Refresh consultation object if it was added/modified
            existing_lab_tests = LabTest.query.filter_by(consultation_id=consultation.id).all()

            for lab_test_order in existing_lab_tests: 
                lab_test_id = str(lab_test_order.id)
                
                submitted_params_for_test = False
                for key in request.form:
                    if key.startswith(f'lab_results[{lab_test_id}]'):
                        submitted_params_for_test = True
                        break

                if submitted_params_for_test:
                    laboratory_test_info = lab_test_order.service.lab_test 
                    if not laboratory_test_info:
                        continue 

                    # Delete existing results for this lab_test_order to replace them
                    # This is appropriate for lab test results, as you're replacing the set of results
                    LabTestResult.query.filter_by(lab_test_id=lab_test_order.id).delete()
                    
                    results_added_for_this_test = False
                    for param in laboratory_test_info.parameters:
                        param_id = str(param.parameter_id)
                        
                        value = None
                        if param.result_type == 'numeric':
                            input_name = f'lab_results[{lab_test_id}][{param_id}][numeric_value]'
                            raw_value = request.form.get(input_name)
                            if raw_value is not None and raw_value != '':
                                try:
                                    value = float(raw_value)
                                    new_result = LabTestResult(
                                        lab_test_id=lab_test_order.id,
                                        parameter_id=param.parameter_id,
                                        numeric_value=value,
                                        unit=param.unit,
                                        entered_by=current_user.username,
                                        entered_at=datetime.datetime.utcnow()
                                    )
                                    db.session.add(new_result)
                                    results_added_for_this_test = True
                                except ValueError:
                                    flash(f"Invalid numeric value for {param.parameter_name} in Lab Test {lab_test_order.service.name}", 'danger')
                                    continue
                        elif param.result_type == 'categorical':
                            input_name = f'lab_results[{lab_test_id}][{param_id}][categorical_value]'
                            value = request.form.get(input_name)
                            if value is not None and value != '':
                                new_result = LabTestResult(
                                    lab_test_id=lab_test_order.id,
                                    parameter_id=param.parameter_id,
                                    categorical_value=value,
                                    unit=param.unit,
                                    entered_by=current_user.username,
                                    entered_at=datetime.datetime.utcnow()
                                )
                                db.session.add(new_result)
                                results_added_for_this_test = True
                        elif param.result_type == 'text':
                            input_name = f'lab_results[{lab_test_id}][{param_id}][text_value]'
                            value = request.form.get(input_name)
                            if value is not None and value != '':
                                new_result = LabTestResult(
                                    lab_test_id=lab_test_order.id,
                                    parameter_id=param.parameter_id,
                                    text_value=value,
                                    unit=param.unit,
                                    entered_by=current_user.username,
                                    entered_at=datetime.datetime.utcnow()
                                )
                                db.session.add(new_result)
                                results_added_for_this_test = True
                        
                        # Add interpretation and comments if they are submitted for the parameter
                        interpretation_input_name = f'lab_results[{lab_test_id}][{param_id}][interpretation]'
                        comments_input_name = f'lab_results[{lab_test_id}][{param_id}][comments]'

                        interpretation = request.form.get(interpretation_input_name)
                        comments = request.form.get(comments_input_name)

                        if results_added_for_this_test and 'new_result' in locals() and new_result:
                            new_result.interpretation = interpretation if interpretation else None
                            new_result.comments = comments if comments else None
                        else:
                            # If a result wasn't added but interpretation/comments are provided for an existing one
                            # You would need to load existing result, update it, and then save.
                            # For now, we only save interpretation/comments if a result value is submitted too.
                            # To handle updates to interpretation/comments for existing results without value changes:
                            # existing_result = LabTestResult.query.filter_by(lab_test_id=lab_test_order.id, parameter_id=param.parameter_id).first()
                            # if existing_result:
                            #     existing_result.interpretation = interpretation if interpretation else existing_result.interpretation
                            #     existing_result.comments = comments if comments else existing_result.comments
                            pass


                    # Update the status of the LabTest order if results were actually processed for it
                    if results_added_for_this_test:
                        lab_test_order.status = 'results_entered' 
                        lab_test_order.done_by = current_user
                        lab_test_order.done_at = datetime.datetime.utcnow()

                    # Update overall interpretation and comments for the LabTest order
                    overall_interpretation_name = f'lab_test_overall_interpretation[{lab_test_id}]'
                    overall_comments_name = f'lab_test_overall_comments[{lab_test_id}]'

                    lab_test_order.interpretation = request.form.get(overall_interpretation_name)
                    lab_test_order.notes = request.form.get(overall_comments_name) # Assuming 'notes' maps to overall comments

            db.session.commit() # Final commit after all operations (including lab results)

            flash('Treatment plan and lab results saved successfully', 'success')
            return redirect(url_for('consultations_web.consultation_queue'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error saving treatment: {str(e)}', 'danger')
            current_app.logger.error(f"Error in add_treatment: {e}", exc_info=True) # Log the full traceback


    return render_template(
        'add_treatment.html',
        visit=visit,
        consultation=consultation, 
        insurance_obj=insurance_obj,
        medications=medications_list, # Changed variable name
        lab_tests=lab_tests_list, # Changed variable name
        imaging_services=imaging_services,
        existing_medications=existing_medications,
        existing_lab_tests=existing_lab_tests,
        existing_radiology=existing_radiology,
        existing_lab_results=existing_lab_results 
    )



@consultations_web_bp.route('/consultations/<int:consultation_id>/edit', methods=['GET', 'POST'])
def edit_treatment(consultation_id):
    consultation = Consultation.query.get_or_404(consultation_id)
    services = Service.query.all()
    visit = Visit.query.get_or_404(consultation.visit_id)  # Get visit from consultation

    # Get all services grouped by category
    medications = [s for s in services if s.category == 'Pharmacy']
    lab_tests = [s for s in services if s.category == 'Laboratory']
    imaging_services = [s for s in services if s.category == 'Radiology']
    
    # Get existing associations
    existing_medications = consultation.medications
    existing_lab_ids = [lt.service_id for lt in consultation.lab_tests]
    existing_radiology_ids = [ro.service_id for ro in consultation.radiology_orders]

    if request.method == 'POST':
        try:
            # Update basic consultation info
            consultation.history = request.form.get('history')
            consultation.examination = request.form.get('examination')
            consultation.diagnosis = request.form.get('diagnosis')
            consultation.treatment_plan = request.form.get('treatment_plan')
            consultation.notes = request.form.get('notes')
            consultation.updated_at = datetime.utcnow()

            # Clear existing relationships
            # Proper way to delete associations
            Medication.query.filter_by(consultation_id=consultation.id).delete()
            LabTest.query.filter_by(consultation_id=consultation.id).delete()
            Radiology.query.filter_by(consultation_id=consultation.id).delete()

            # Process Medications
            for i, service_id in enumerate(request.form.getlist('drug[]')):
                service = Service.query.get(service_id)
                if not service or service.category != 'Pharmacy':
                    continue
                
                medication = Medication(
                    consultation=consultation,
                    service=service,
                    dose=request.form.getlist('drug_dose[]')[i],
                    frequency=request.form.getlist('drug_frequency[]')[i],
                    duration=request.form.getlist('drug_duration[]')[i],
                    quantity=request.form.getlist('drug_quantity[]')[i]
                )
                db.session.add(medication)

            # Process Lab Tests
            for service_id in request.form.getlist('lab_tests'):
                service = Service.query.get(service_id)
                if service and service.category == 'Laboratory':
                    lab_test = LabTest(
                        consultation=consultation,
                        service=service,
                        status='requested'
                    )
                    db.session.add(lab_test)

            # Process Radiology Orders
            for service_id in request.form.getlist('imaging_studies'):
                service = Service.query.get(service_id)
                if service and service.category == 'Radiology':
                    radiology = Radiology(
                        consultation=consultation,
                        service=service,
                        status='requested'
                    )
                    db.session.add(radiology)

            # ✅ SET THE POSITION TO BILLING
            visit.current_position = 'billing'
            db.session.commit()
            flash('Treatment plan updated successfully', 'success')
            return redirect(url_for('consultations_web.consultation_queue'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating treatment: {str(e)}', 'danger')

    return render_template(
        'edit_treatment.html',
        consultation=consultation,
        medications=medications,
        lab_tests=lab_tests,
        visit=visit,
        imaging_services=imaging_services,
        existing_medications=existing_medications,
        existing_lab_ids=existing_lab_ids,
        existing_radiology_ids=existing_radiology_ids
    )
# Complete Visit
@consultations_web_bp.route('/visits/<int:visit_id>/complete', methods=['POST'])
def complete_visit(visit_id):
    try:
        visit = Visit.query.get_or_404(visit_id)
        visit.visit_status = 'completed'
        visit.current_position = None
        visit.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': 'Visit marked as completed'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error completing visit: {str(e)}'
        }), 500

from flask import render_template, make_response
from weasyprint import HTML
from io import BytesIO

@consultations_web_bp.route('/download_report/<int:consultation_id>')
def download_report(consultation_id):
    consultation = Consultation.query.options(
        joinedload(Consultation.medications).joinedload(Medication.service),
        joinedload(Consultation.lab_tests).joinedload(LabTest.service),
        joinedload(Consultation.radiology_orders).joinedload(Radiology.service),
        joinedload(Consultation.patient),
        joinedload(Consultation.visit)
    ).get_or_404(consultation_id)
    
    html = render_template(
        'medical_report.html',
        consultation=consultation,
        now=datetime.utcnow()
    )
    
    pdf = HTML(string=html, base_url=request.host_url).write_pdf()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"AstroCare_Report_{consultation.patient.reg_no}_{consultation.created_at.date()}.pdf"
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@consultations_web_bp.route('/lab-results')
def lab_results():
    # Get all completed lab tests with related data
    lab_tests = LabTest.query.options(
        joinedload(LabTest.consultation).joinedload(Consultation.patient),
        joinedload(LabTest.service)
    ).filter(
        LabTest.status == 'completed',
        LabTest.results.isnot(None)
    ).order_by(LabTest.completed_at.desc()).all()

    return render_template('lab_results.html', lab_tests=lab_tests)



from flask_login import login_required, current_user

@consultations_web_bp.route('/lab-tests/<int:test_id>', methods=['GET', 'POST'])
@login_required  # Add login requirement
def view_lab_test(test_id):
    lab_test = LabTest.query.options(
        joinedload(LabTest.consultation).joinedload(Consultation.patient),
        joinedload(LabTest.service),
        joinedload(LabTest.consultation).joinedload(Consultation.visit),
        joinedload(LabTest.consultation).joinedload(Consultation.medications)
    ).get_or_404(test_id)

    if not current_user.is_authenticated:
        flash('You need to be logged in to access this page', 'danger')
        return redirect(url_for('auth.login'))

    medications = Service.query.filter_by(category='Pharmacy').all()

    if request.method == 'POST':
        try:
            # ── LabTest fields ──
            lab_test.interpretation  = request.form.get('interpretation', lab_test.interpretation)
            lab_test.status         = request.form.get('status', lab_test.status)

            # ── Consultation fields ──
            consult = lab_test.consultation
            consult.diagnosis       = request.form.get('additional_diagnosis', consult.diagnosis)
            consult.treatment_plan  = request.form.get('followup_treatment_plan', consult.treatment_plan)
            consult.notes           = request.form.get('additional_notes', consult.notes)

            
            # Handle verification data
            if lab_test.status == 'verified':
                if not current_user.is_authenticated:
                    flash('Authentication required for verification', 'danger')
                    return redirect(url_for('auth.login'))
                
                lab_test.verified_at = datetime.utcnow()
                lab_test.verified_by = current_user.id
                lab_test.doctor_signature = request.form.get('signature_data')
                lab_test.interpretation = request.form.get('interpretation', '')

            # Process medications
            consultation = lab_test.consultation
            # Process medications - only add new ones
            try:
                # Get form data lists
                new_drug_ids = request.form.getlist('drug[]')
                
                # Only process if there are new medications
                if new_drug_ids:
                    for i, service_id in enumerate(new_drug_ids):
                        service = Service.query.get(service_id)
                        if service and service.category == 'Pharmacy':
                            try:
                                # Check if medication already exists
                                existing = Medication.query.filter_by(
                                    consultation_id=consultation.id,
                                    service_id=service_id,
                                    dose=request.form.getlist('drug_dose[]')[i],
                                    frequency=request.form.getlist('drug_frequency[]')[i]
                                ).first()

                                if not existing:
                                    medication = Medication(
                                        consultation=consultation,
                                        service=service,
                                        dose=request.form.getlist('drug_dose[]')[i],
                                        frequency=request.form.getlist('drug_frequency[]')[i],
                                        quantity=int(request.form.getlist('drug_quantity[]')[i]),
                                        price=float(request.form.getlist('drug_price[]')[i])
                                    )
                                    db.session.add(medication)
                                    flash('New medication added successfully', 'success')
                                else:
                                    # Update existing if needed
                                    existing.quantity = int(request.form.getlist('drug_quantity[]')[i])
                                    existing.price = float(request.form.getlist('drug_price[]')[i])
                                    flash('Medication updated successfully', 'info')
                                    
                            except (ValueError, IndexError) as e:
                                flash(f'Error processing medication: {str(e)}', 'warning')

            except Exception as e:
                db.session.rollback()
                flash(f'Error processing medications: {str(e)}', 'danger')

            db.session.commit()
            flash('Lab results updated successfully', 'success')
            return redirect(url_for('consultations_web.view_lab_test', test_id=test_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating results: {str(e)}', 'danger')

    # Get reference ranges safely
    reference_ranges = {}
    if lab_test.service.predefined_results:
        try:
            reference_ranges = (lab_test.service.predefined_results if isinstance(lab_test.service.predefined_results, dict)
                else json.loads(lab_test.service.predefined_results))
        except (TypeError, json.JSONDecodeError):
            pass

    return render_template(
        'view_lab_test.html',
        lab_test=lab_test,
        reference_ranges=reference_ranges,
        medications=medications,
        now=datetime.now(),
    )



# Add these new routes to the existing consultations_web blueprint

@consultations_web_bp.route('/imaging-requests')
def imaging_requests():
    """Display all requested imaging orders"""
    requests = Radiology.query.options(
        joinedload(Radiology.consultation).joinedload(Consultation.patient),
        joinedload(Radiology.service)
    ).filter(
        Radiology.status == 'requested'
    ).order_by(Radiology.requested_at.asc()).all()
    
    return render_template('imaging_requests.html', requests=requests)

@consultations_web_bp.route('/scan-results')
def scan_results():
    """Show completed radiology reports"""
    results = Radiology.query.options(
        joinedload(Radiology.consultation).joinedload(Consultation.patient),
        joinedload(Radiology.service),
        joinedload(Radiology.verified_by_user)  # Now correctly references the relationship
    ).filter(
        Radiology.status.in_(['completed', 'verified'])
    ).order_by(Radiology.completed_at.desc()).all()
    
    return render_template('scan_results.html', results=results)

@consultations_web_bp.route('/archived-reports')
def archived_reports():
    """Display archived radiology reports"""
    reports = Radiology.query.options(
        joinedload(Radiology.consultation).joinedload(Consultation.patient),
        joinedload(Radiology.service)
    ).filter(
        Radiology.status == 'archived'
    ).order_by(Radiology.archived_at.desc()).all()
    
    return render_template('archived_reports.html', reports=reports)

@consultations_web_bp.route('/radiology/<int:order_id>', methods=['GET', 'POST'])
@login_required
def view_radiology_order(order_id):
    """View and update radiology order details"""
    order = Radiology.query.options(
        joinedload(Radiology.consultation).joinedload(Consultation.patient),
        joinedload(Radiology.consultation).joinedload(Consultation.visit),
        joinedload(Radiology.consultation).joinedload(Consultation.medications),  # 🔥 Add this line
        joinedload(Radiology.service),
        joinedload(Radiology.verified_by_user),
    ).get_or_404(order_id)
    medications = Service.query.filter_by(category='Pharmacy').all()

    if not current_user.is_authenticated:
        flash('You need to be logged in to access this page', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        try:
            # ── Radiology fields ──
            order.results = request.form.get('results', order.results)
            order.notes = request.form.get('notes', order.notes)
            order.status = request.form.get('status', order.status)
            order.interpretation = request.form.get('interpretation', order.interpretation)

            results_json = request.form.get('results_data')
            if results_json:
                try:
                    order.results_data = json.loads(results_json)
                except json.JSONDecodeError:
                    flash('Invalid format in results_data', 'warning')

            # ── Consultation fields ──
            consult = order.consultation
            consult.diagnosis = request.form.get('additional_diagnosis', consult.diagnosis)
            consult.treatment_plan = request.form.get('followup_treatment_plan', consult.treatment_plan)
            consult.notes = request.form.get('additional_notes', consult.notes)

            # ── Verification ──
            if order.status == 'verified':
                order.verified_by = current_user.id
                order.verified_at = datetime.utcnow()
                order.doctor_signature = request.form.get('signature_data', '')

            if order.status == 'completed':
                order.completed_at = datetime.utcnow()

            if request.form.get('done_by_me') == '1':
                order.done_by_id = current_user.id
                order.done_at = datetime.utcnow()

            # ── Process medications ──
            try:
                new_drug_ids = request.form.getlist('drug[]')
                if new_drug_ids:
                    for i, service_id in enumerate(new_drug_ids):
                        service = Service.query.get(service_id)
                        if service and service.category == 'Pharmacy':
                            dose = request.form.getlist('drug_dose[]')[i]
                            frequency = request.form.getlist('drug_frequency[]')[i]
                            quantity = int(request.form.getlist('drug_quantity[]')[i])
                            price = float(request.form.getlist('drug_price[]')[i])

                            existing = Medication.query.filter_by(
                                consultation_id=consult.id,
                                service_id=service_id,
                                dose=dose,
                                frequency=frequency
                            ).first()

                            if not existing:
                                medication = Medication(
                                    consultation=consult,
                                    service=service,
                                    dose=dose,
                                    frequency=frequency,
                                    quantity=quantity,
                                    price=price
                                )
                                db.session.add(medication)
                                flash('New medication added successfully', 'success')
                            else:
                                existing.quantity = quantity
                                existing.price = price
                                flash('Medication updated successfully', 'info')

            except Exception as e:
                db.session.rollback()
                flash(f'Error processing medications: {str(e)}', 'danger')

            db.session.commit()
            flash('Radiology order updated successfully', 'success')
            return redirect(url_for('consultations_web.view_radiology_order', order_id=order_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating radiology order: {str(e)}', 'danger')


    # ── Optional: load reference ranges if needed ──
    reference_ranges = {}
    if order.service.predefined_results:
        try:
            reference_ranges = (
                order.service.predefined_results
                if isinstance(order.service.predefined_results, dict)
                else json.loads(order.service.predefined_results)
            )
        except (TypeError, json.JSONDecodeError):
            pass

    return render_template(
        'view_order.html',
        order=order,
        medications=medications,
        reference_ranges=reference_ranges,
        now=datetime.now()
    )

@consultations_web_bp.route('/radiology/<int:order_id>/archive', methods=['POST'])
@login_required
def archive_radiology_order(order_id):
    """Archive a completed radiology report"""
    try:
        order = Radiology.query.get_or_404(order_id)
        order.status = 'archived'
        order.archived_at = datetime.utcnow()
        db.session.commit()
        flash('Report archived successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error archiving report: {str(e)}', 'danger')
    
    return redirect(url_for('consultations_web.archived_reports'))


@consultations_web_bp.route('/lab-orders')
@login_required  # protect if you only want logged-in users to see it
def lab_orders():
    """
    Show all pending ('requested') LabTest entries, with patient and service info.
    """
    # Eager‐load LabTest.consultation → Consultation.patient and LabTest.service
    pending_orders = (
        LabTest.query
        .filter_by(status='requested')
        .options(
            joinedload(LabTest.consultation).joinedload(Consultation.patient),
            joinedload(LabTest.service)
        )
        .order_by(LabTest.requested_at.asc())
        .all()
    )

    return render_template('lab_orders.html', lab_orders=pending_orders)



# Backend Implementation with Local Cache
import re
import threading
import time
import requests
from flask import jsonify, request, current_app

# Local cache for disease details (using data from your search results)
DISEASE_DETAILS_CACHE = {
    "B52.9": {
        "code": "B52.9",
        "title": "Plasmodium malariae malaria without complication",
        "definition": "Malaria caused by Plasmodium malariae without complications",
        "long_definition": "A type of malaria caused by the Plasmodium malariae parasite, typically transmitted through the bite of an infected Anopheles mosquito. After entering the bloodstream, the parasite infects red blood cells, leading to symptoms like high fever, chills, headaches, and nausea. Characterized by fever episodes occurring every 72 hours.",
        "fully_specified_name": "Plasmodium malariae malaria without complication",
        "synonyms": ["Quartan malaria", "Plasmodium malariae malaria NOS"],
        "exclusions": [
            "Plasmodium falciparum malaria (B50.-)",
            "Plasmodium vivax malaria (B51.-)"
        ],
        "inclusions": ["Mixed infections of Plasmodium malariae with other Plasmodium species"],
        "parent_categories": [
            {"code": "B52", "title": "Plasmodium malariae malaria"},
            {"code": "B50-B64", "title": "Protozoal diseases"},
            {"code": "A00-B99", "title": "Certain infectious and parasitic diseases"}
        ],
        "related_entities": [
            {"code": "B52.0", "title": "Plasmodium malariae malaria with nephropathy", "relation_type": "Subtype"},
            {"code": "B52.8", "title": "Plasmodium malariae malaria with other complications", "relation_type": "Subtype"}
        ]
    }
}

# Token management system for WHO API
token_lock = threading.Lock()
cached_token = None
token_expiry = 0

def get_who_token():
    global cached_token, token_expiry
    with token_lock:
        if cached_token and time.time() < token_expiry:
            return cached_token
        
        token_url = "https://icdaccessmanagement.who.int/connect/token"
        payload = {
            'client_id': current_app.config['WHO_CLIENT_ID'],
            'client_secret': current_app.config['WHO_CLIENT_SECRET'],
            'scope': 'icdapi_access',
            'grant_type': 'client_credentials'
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        try:
            response = requests.post(token_url, data=payload, headers=headers, timeout=5)
            response.raise_for_status()
            token_data = response.json()
            cached_token = token_data['access_token']
            token_expiry = time.time() + token_data['expires_in'] - 300
            return cached_token
        except Exception as e:
            current_app.logger.error(f"Token fetch failed: {str(e)}")
            return None

@consultations_web_bp.route('/_search_diseases', methods=['GET'])
def search_diseases():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify(results=[])

    try:
        # Use ClinicalTables for initial search
        url = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
        params = {
            "terms": query,
            "sf": "code,name",
            "df": "code,name",
            "maxList": 50
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        results = []
        if len(data) >= 4:
            codes = data[1]
            display_values = data[3]
            for i in range(len(codes)):
                # Check if we have cached details for this code
                cached_details = DISEASE_DETAILS_CACHE.get(codes[i], {})
                
                results.append({
                    "code": codes[i],
                    "name": display_values[i][1],
                    "description": cached_details.get("definition", f"ICD-10: {codes[i]} - {display_values[i][1]}")
                })
        return jsonify(results=results)
    except Exception as e:
        return jsonify(error=str(e)), 500

@consultations_web_bp.route('/disease-details', methods=['GET'])
def disease_details():
    code = request.args.get('code')
    if not code:
        return jsonify(error="Missing ICD-10 code"), 400

    # First check local cache
    if code in DISEASE_DETAILS_CACHE:
        return jsonify(DISEASE_DETAILS_CACHE[code])
    
    # Try WHO API as fallback
    token = get_who_token()
    if not token:
        return jsonify(error="API authentication failed"), 500

    try:
        # Step 1: Search WHO API to get entity ID for this ICD-10 code
        search_url = "https://id.who.int/icd/entity/search"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Accept-Language": "en",
            "API-Version": "v2"
        }
        params = {"q": code}
        search_response = requests.get(search_url, headers=headers, params=params, timeout=5)
        
        if search_response.status_code != 200:
            return jsonify(error=f"Search API error: {search_response.status_code}"), 500
        
        search_data = search_response.json()
        entity_id = None
        best_match = None
        highest_score = 0
        
        # Find the best matching entity
        for entity in search_data.get("destinationEntities", []):
            entity_code = entity.get("theCode", "")
            
            # Exact match
            if entity_code == code:
                if "@id" in entity:
                    match = re.search(r'/(\d+)$', entity["@id"])
                    if match:
                        entity_id = match.group(1)
                        break
            
            # Partial match scoring
            else:
                # Score based on code similarity
                score = 0
                if entity_code.startswith(code.split('.')[0]):
                    score = 80  # Same category
                elif code in entity_code:
                    score = 60
                elif entity_code in code:
                    score = 40
                
                # Score based on title similarity
                title = entity.get("title", "").lower()
                if code.lower() in title:
                    score += 20
                
                # Track best match
                if score > highest_score:
                    highest_score = score
                    best_match = entity
        
        # Fallback to best match if no exact match found
        if not entity_id and best_match and "@id" in best_match:
            match = re.search(r'/(\d+)$', best_match["@id"])
            if match:
                entity_id = match.group(1)
        
        if not entity_id:
            return jsonify(error=f"No matching entity found for ICD-10 code: {code}"), 404

        # Step 2: Get detailed information using entity ID
        detail_url = f"https://id.who.int/icd/entity/{entity_id}"
        detail_response = requests.get(detail_url, headers=headers, timeout=10)
        
        if detail_response.status_code == 200:
            detail_data = detail_response.json()
            # Cache this result for future use
            parsed_data = parse_detailed_disease_data(detail_data, code)
            DISEASE_DETAILS_CACHE[code] = parsed_data.json
            return parsed_data
        else:
            return jsonify(error=f"Detail API error: {detail_response.status_code}"), 500
            
    except Exception as e:
        return jsonify(error=f"Connection Error: {str(e)}"), 500

def parse_detailed_disease_data(data, icd_code):
    """Parse detailed disease information from WHO API response"""
    result = {
        "code": icd_code,
        "title": data.get("title", "N/A"),
        "definition": data.get("definition", {}).get("@value", "No definition available"),
        "long_definition": data.get("longDefinition", {}).get("@value", ""),
        "fully_specified_name": data.get("fullySpecifiedName", {}).get("@value", ""),
        "synonyms": [synonym["label"] for synonym in data.get("synonyms", [])],
        "exclusions": [excl["label"] for excl in data.get("exclusion", [])],
        "inclusions": [incl["label"] for incl in data.get("inclusion", [])],
        "parent_categories": [],
        "related_entities": []
    }

    # Extract parent categories
    for parent in data.get("parent", []):
        result["parent_categories"].append({
            "title": parent.get("title", "N/A"),
            "code": parent.get("theCode", "N/A")
        })
    
    # Extract related entities
    for relation in data.get("child", []):
        result["related_entities"].append({
            "title": relation.get("title", "N/A"),
            "code": relation.get("theCode", "N/A"),
            "relation_type": "Subtype"
        })
    
    return jsonify(result)

@consultations_web_bp.route('/manage-diagnosis', methods=['GET'])
def manage_diagnosis():
    return render_template('manage_diagnosis.html')




# --- NEW DENTAL ROUTES ---
@consultations_web_bp.route('/dental-consultations')
def dental_consultations():
    """
    Renders the page for managing dental consultations.
    This could show a queue, list of ongoing consultations, etc.
    """
    # For now, just a placeholder. You'll add logic here later.
    return render_template('dental/dental_consultations.html', title="Dental Consultations")

@consultations_web_bp.route('/dental-procedures')
def dental_procedures():
    """
    Renders the page for managing dental procedures.
    This could include adding new procedures, viewing completed ones, etc.
    """
    # For now, just a placeholder. You'll add logic here later.
    return render_template('dental/dental_procedures.html', title="Dental Procedures")

# --- NEW OPTICIAN ROUTES ---
@consultations_web_bp.route('/eye-examinations')
def eye_examinations():
    """
    Renders the page for managing eye examinations.
    This could show a schedule, past exams, etc.
    """
    # For now, just a placeholder. You'll add logic here later.
    return render_template('optician/eye_examinations.html', title="Eye Examinations")

@consultations_web_bp.route('/glasses-dispensing')
def glasses_dispensing():
    """
    Renders the page for managing glasses dispensing.
    This could include new dispensing requests, inventory lookup, etc.
    """
    # For now, just a placeholder. You'll add logic here later.
    return render_template('optician/glasses_dispensing.html', title="Glasses Dispensing")


@consultations_web_bp.route('/manage-consultation-services')
def manage_consultation_services():
    """
    Renders the page for managing consultation services.
    Fetches all services with the 'Consultation' category from the database.
    """
    # Query the database to get all services with the category 'Consultation'
    consultation_services = Service.query.filter_by(category='Consultation').all()
    
    return render_template(
        'services/manage-consultation-services.html',
        title="Manage Consultation Services",
        services=consultation_services
    )
    
    
    
@consultations_web_bp.route('/add-new-service', methods=['GET', 'POST'])
def add_new_service():
    """
    Handles the creation of a new consultation service.
    GET: Displays a form to add a new service.
    POST: Processes the form data and saves the new service to the database.
    """
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        duration = request.form.get('duration')

        # Basic form validation - price is now handled by the form
        if not name:
            flash('Service Name is a required field.', 'danger')
            return redirect(url_for('consultations_web.add_new_service'))

        try:
            new_service = Service(
                name=name,
                category='Consultation',  # Automatically set the category
                price=0.00,  # Explicitly set price to 0 as per new requirement
                description=description,
                duration=int(duration) if duration else None
            )
            db.session.add(new_service)
            db.session.commit()
            flash(f'Successfully added new service: "{new_service.name}"', 'success')
            return redirect(url_for('consultations_web.manage_consultation_services'))

        except (ValueError, exc.IntegrityError) as e:
            db.session.rollback()
            flash(f'An error occurred: {e}. Please check your input.', 'danger')
            return redirect(url_for('consultations_web.add_new_service'))

    # GET request: render the form
    return render_template('services/add_new_service.html', title="Add New Service")

@consultations_web_bp.route('/edit-service/<int:service_id>', methods=['GET', 'POST'])
def edit_service(service_id):
    """
    Handles the editing of an existing consultation service.
    GET: Displays a pre-filled form for the specified service.
    POST: Processes the form data and updates the service in the database.
    """
    service = Service.query.get_or_404(service_id)

    if request.method == 'POST':
        try:
            service.name = request.form.get('name')
            # The price is NOT updated here, as per your requirement.
            # service.price = float(request.form.get('price')) 
            service.description = request.form.get('description')
            service.duration = int(request.form.get('duration')) if request.form.get('duration') else None
            
            db.session.commit()
            flash(f'Service "{service.name}" updated successfully.', 'success')
            return redirect(url_for('consultations_web.manage_consultation_services'))
        
        except (ValueError, exc.IntegrityError) as e:
            db.session.rollback()
            flash(f'An error occurred: {e}. Please check your input.', 'danger')
            # Stay on the edit page with the error message
            return render_template('services/edit_service.html', service=service, title="Edit Service")
            
    # GET request: render the form with existing service data
    return render_template('services/edit_service.html', service=service, title="Edit Service")

@consultations_web_bp.route('/delete-service/<int:service_id>', methods=['POST', 'GET'])
def delete_service(service_id):
    """
    Deletes a consultation service from the database.
    Note: Using POST is generally more secure for delete operations, but a GET is used here to match
    the simple JavaScript call from the template.
    """
    service = Service.query.get_or_404(service_id)
    
    try:
        db.session.delete(service)
        db.session.commit()
        flash(f'Service "{service.name}" has been deleted.', 'warning')
    except exc.IntegrityError:
        db.session.rollback()
        flash(f'Cannot delete service "{service.name}" because it is in use elsewhere.', 'danger')

    return redirect(url_for('consultations_web_bp.manage_consultation_services'))


@consultations_web_bp.route('/manage-doctors/<int:service_id>')
def manage_doctors(service_id):
    """
    Renders the page for managing doctors assigned to a specific service.
    
    This route fetches the specified service and a list of doctors to be
    assigned or unassigned.
    """
    # Find the service by its ID, or return a 404 error if not found.
    service = Service.query.get_or_404(service_id)
    
    # ---
    # NOTE: You'll need to define a relationship between Service and doctors
    # For now, let's just fetch all users that have a 'Doctor' role.
    # You would replace this with your actual logic to get assigned doctors.
    
    # Assuming 'role_name' is a column in your User model
    # and there's a Role model linked to it.
    # Replace this with your specific database schema logic.
    doctors = User.query.filter_by(role_name='Doctor').all()
    # ---

    return render_template(
        'services/manage_doctors.html',
        title=f"Manage Doctors for {service.name}",
        service=service,
        doctors=doctors
    )
    
    
    
    
@consultations_web_bp.route('/toggle-service-status/<int:service_id>', methods=['GET'])
def toggle_service_status(service_id):
    """
    Toggles the 'is_active' status of a specified service.
    """
    service = Service.query.get_or_404(service_id)
    
    # Toggle the boolean status
    service.is_active = not service.is_active
    db.session.commit()
    
    status_message = "activated" if service.is_active else "deactivated"
    flash(f'Service "{service.name}" has been successfully {status_message}.', 'success')
    
    return redirect(url_for('consultations_web.manage_consultation_services'))