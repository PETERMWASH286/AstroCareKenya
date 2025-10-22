from datetime import date, datetime, timedelta
import io
import json
import math
import os
import re
import requests
from weasyprint import HTML
from flask import abort, app, current_app, jsonify, make_response, render_template, flash, redirect, send_file, url_for, request
from flask_login import login_required, current_user
from app import db
from app.auth.models import User
from app.lab.forms import LabConsumableForm, LabStockRequestForm, NewItemRequestForm
from app.lab.models import BloodInventory, DailyLogEntry, LabConsumable, LabEquipment, LabInventory, LabTestResult, LaboratoryTest, PanelTest, ParameterOption, ParameterRange, QualityControl, Sample, ScheduledMaintenanceLog, TestPanel, TestParameter, UploadedFile
from app.patients.models import Consultation, LabTest, Patient, Service, Visit
from app.store.models import BulkRequest, ItemPurchaseRequest, Stock, StockRequest, Supplier
from . import lab_web_bp
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import joinedload

@lab_web_bp.route('/lab/tests')
@login_required
def list_lab_tests():
    """Lab tests list, including both consultation-based and walk-in (paid) tests."""
    try:
        page = request.args.get('page', 1, type=int)
        status_filter = request.args.get('status', 'all')
        search_query = request.args.get('q', '')

        # --- Query for Consultation-based Lab Tests (Existing Logic) ---
        consultation_base_query = (
            LabTest.query
            .filter(LabTest.is_paid.is_(True))
            .join(Consultation) # Explicitly join Consultation here
            .join(Patient)      # Join Patient through Consultation
            .join(Service)
            .options(
                joinedload(LabTest.consultation).joinedload(Consultation.patient),
                joinedload(LabTest.service)
            )
        )

        # Apply status filter for consultation-based tests
        if status_filter != 'all':
            consultation_base_query = consultation_base_query.filter(LabTest.status == status_filter)

        # Apply search for consultation-based tests
        if search_query:
            term = f'%{search_query}%'
            consultation_base_query = consultation_base_query.filter(or_(
                Service.name.ilike(term),
                Patient.full_name.ilike(term)
            ))
        
        # Order consultation-based tests
        consultation_tests = (
            consultation_base_query
            .order_by(
                Consultation.created_at.desc(),
                LabTest.requested_at.desc()
            )
            .all() # Fetch all for combination later, pagination will be applied to combined list
        )

        # --- Query for Walk-in Lab Tests (New Logic) ---
        # These are linked directly to a Visit and do NOT have a Consultation.
        # They must also be paid.
        walkin_base_query = (
            LabTest.query
            .filter(LabTest.is_paid.is_(True))
            .filter(LabTest.consultation_id.is_(None)) # Crucial: only tests without consultation
            .join(Visit) # Join directly to Visit
            .join(Patient, Visit.patient_id == Patient.id) # Join Patient through Visit
            .join(Service)
            .options(
                joinedload(LabTest.visit).joinedload(Visit.patient), # Load visit and patient through visit
                joinedload(LabTest.service)
            )
        )

        # Apply status filter for walk-in tests
        if status_filter != 'all':
            walkin_base_query = walkin_base_query.filter(LabTest.status == status_filter)
        
        # Apply search for walk-in tests
        if search_query:
            term = f'%{search_query}%'
            walkin_base_query = walkin_base_query.filter(or_(
                Service.name.ilike(term),
                Patient.full_name.ilike(term)
            ))

        # Order walk-in tests
        walkin_tests = (
            walkin_base_query
            .order_by(
                Visit.created_at.desc(), # Order by visit creation time
                LabTest.requested_at.desc()
            )
            .all() # Fetch all for combination
        )

        # --- Combine and Sort All Lab Tests ---
        # Combine both lists
        all_lab_tests = consultation_tests + walkin_tests

        # Sort the combined list (you might need to refine this sort key based on desired display order)
        # A common approach is to sort by patient name, then request time, or simply request time globally.
        # For simplicity, let's sort by the request timestamp, which exists on all LabTests.
        all_lab_tests.sort(key=lambda lt: lt.requested_at if lt.requested_at else datetime.min, reverse=True)


        # Manual Pagination for the combined list
        per_page = 15
        total = len(all_lab_tests)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_tests_items = all_lab_tests[start:end]

        # Create a dummy pagination object to pass to the template
        class CustomPagination:
            def __init__(self, page, per_page, total, items):
                self.page = page
                self.per_page = per_page
                self.total = total
                self.items = items
                self.pages = (total + per_page - 1) // per_page
                self.has_next = self.page < self.pages
                self.has_prev = self.page > 1
                self.next_num = self.page + 1 if self.has_next else None
                self.prev_num = self.page - 1 if self.has_prev else None

        tests_paginated = CustomPagination(page, per_page, total, paginated_tests_items)

        # --- Group tests by their parent entity (Consultation or Visit) ---
        # This grouping logic needs to be flexible enough to handle both.
        # We'll create a list of dictionaries, where each dict represents a group.
        # Each group will have an 'entity' (Consultation or Visit) and a list of 'tests'.
        
        grouped_tests = []
        
        # To avoid duplicating patient info, let's restructure slightly for the frontend.
        # We'll create a list where each item is a test, with its associated patient and parent entity (consultation/visit)
        
        # Prepare tests for rendering, adding patient and parent_entity directly
        rendered_tests_data = []
        for test in tests_paginated.items:
            patient_obj = None
            parent_entity_type = None
            parent_entity_id = None
            parent_entity_created_at = None
            
            if test.consultation:
                patient_obj = test.consultation.patient
                parent_entity_type = 'consultation'
                parent_entity_id = test.consultation.id
                parent_entity_created_at = test.consultation.created_at
            elif test.visit: # For walk-in tests
                patient_obj = test.visit.patient
                parent_entity_type = 'visit'
                parent_entity_id = test.visit.id
                parent_entity_created_at = test.visit.created_at

            rendered_tests_data.append({
                'test': test,
                'patient': patient_obj,
                'parent_entity_type': parent_entity_type, # 'consultation' or 'visit'
                'parent_entity_id': parent_entity_id,
                'parent_entity_created_at': parent_entity_created_at
            })
        
        # Sort these again if needed for specific grouping display, but the initial sort should handle it.
        # For display, you might want to group them again on the template or here.
        # Let's keep the existing `grouped_tests` structure but adapt it for both types.
        
        # New grouping logic to handle both consultation and visit-based tests
        # This will group by a unique identifier combining type and ID
        grouped_tests_by_entity = {} # {('consultation', id): {'entity_obj': obj, 'tests': [...]}}

        for test in tests_paginated.items:
            entity_key = None
            entity_obj = None
            patient_obj = None

            if test.consultation:
                entity_key = ('consultation', test.consultation.id)
                entity_obj = test.consultation
                patient_obj = test.consultation.patient
            elif test.visit and test.consultation_id is None: # Explicitly check for walk-ins
                entity_key = ('visit', test.visit.id)
                entity_obj = test.visit
                patient_obj = test.visit.patient

            if entity_key:
                if entity_key not in grouped_tests_by_entity:
                    grouped_tests_by_entity[entity_key] = {
                        'entity': entity_obj, # This will be either Consultation or Visit object
                        'entity_type': entity_key[0], # 'consultation' or 'visit'
                        'patient': patient_obj,
                        'tests': []
                    }
                grouped_tests_by_entity[entity_key]['tests'].append(test)
        
        # Convert dictionary to list for template iteration, preserving order (if necessary, sort by date)
        # Sorting by the entity's creation date (consultation.created_at or visit.created_at)
        grouped_tests = sorted(
            grouped_tests_by_entity.values(),
            key=lambda x: (x['entity'].created_at if hasattr(x['entity'], 'created_at') else datetime.min),
            reverse=True
        )


        return render_template(
            'lab_tests.html',
            grouped_tests=grouped_tests, # This now contains both consultation and walk-in groups
            pagination=tests_paginated,
            status_filter=status_filter,
            search_query=search_query,
            title="Lab Test Management"
        )

    except Exception as e:
        flash(f'Error retrieving lab tests: {str(e)}', 'danger')
        current_app.logger.exception("Error in list_lab_tests") # Log the full exception
        return redirect(url_for('dashboard_web.index'))
    
    
# ... existing imports ...

@lab_web_bp.route('/tests/<int:test_id>/receive', methods=['POST', 'GET'])
@login_required
def receive_test(test_id):
    """Mark test as received and update status"""
    try:
        test = LabTest.query.get_or_404(test_id)
        
        # Validate test can be received
        if test.status != 'requested':
            flash('Only requested tests can be received', 'warning')
            return redirect(url_for('lab_web.list_lab_tests'))
        
        # Update test status
        test.status = 'waiting processing'
        test.received_at = datetime.utcnow()
        test.received_by_id = current_user.id
        db.session.commit()
        
        flash('Test received successfully', 'success')
        return redirect(url_for('lab_web.list_lab_tests'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error receiving test: {str(e)}', 'danger')
        return redirect(url_for('lab_web.list_lab_tests'))


@lab_web_bp.route('/lab/tests/<int:test_id>/add-samples', methods=['GET', 'POST'])
@login_required
def add_samples(test_id):
    """Add samples to a test, including verification checklist."""
    try:
        test = LabTest.query.get_or_404(test_id)

        # Validate test can have samples added
        if test.status not in ['waiting processing', 'requested']:
            flash('Samples can only be added to requested or processing tests.', 'warning')
            return redirect(url_for('lab_web.list_lab_tests'))

        if request.method == 'POST':
            # Process form submission
            sample_type = request.form.get('sample_type')
            collection_time_str = request.form.get('collection_time')
            quantity = request.form.get('quantity')
            sample_condition = request.form.get('sample_condition')

            # Collection details
            collected_by = request.form.get('collected_by')
            collection_site = request.form.get('collection_site')
            collection_method = request.form.get('collection_method')

            # Reception details
            received_date_str = request.form.get('received_date')
            received_by = request.form.get('received_by')
            transportation_mode = request.form.get('transportation_mode')
            source_type = request.form.get('source_type')

            # Origin details
            brought_by_employee = request.form.get('brought_by_employee')
            source_department = request.form.get('source_department')
            opd_department = request.form.get('opd_department')
            external_source = request.form.get('external_source')
            external_person = request.form.get('external_person')

            processing_notes = request.form.get('processing_notes')

            # --- Capture Sample Verification Checklist Data ---
            acceptance_status = request.form.get('sample_status') # 'Accepted' or 'Rejected'
            rejection_reason = request.form.get('rejection_reason') if acceptance_status == 'Rejected' else None
            person_notified = request.form.get('person_notified') if acceptance_status == 'Rejected' else None
            patient_advice = request.form.get('patient_advice') if acceptance_status == 'Rejected' else None

            # Get individual checklist items (checkboxes return 'on' if checked, None if not)
            checklist_enough_sample = request.form.get('checklist_enough_sample') == 'on'
            checklist_correct_tube = request.form.get('checklist_correct_tube') == 'on'
            checklist_valid_collection_time = request.form.get('checklist_valid_collection_time') == 'on'
            checklist_labeling = request.form.get('checklist_labeling') == 'on'
            checklist_integrity = request.form.get('checklist_integrity') == 'on'
            # --- End Sample Verification Checklist Data Capture ---

            # Convert strings to datetime objects
            try:
                collection_time = datetime.strptime(collection_time_str, '%Y-%m-%dT%H:%M') if collection_time_str else None # Allow None
            except (ValueError, TypeError):
                flash('Invalid collection time format.', 'danger')
                return redirect(url_for('lab_web.add_samples', test_id=test_id)) # Re-render form with error

            try:
                received_date = datetime.strptime(received_date_str, '%Y-%m-%dT%H:%M') if received_date_str else None
            except (ValueError, TypeError):
                flash('Invalid received date/time format.', 'danger')
                return redirect(url_for('lab_web.add_samples', test_id=test_id))


            # Validate required fields for sample (not rejection specific)
            if not all([sample_type, quantity, collection_time]):
                flash('Please fill all essential sample details (Sample Type, Quantity, Collection Time).', 'danger')
                return redirect(url_for('lab_web.add_samples', test_id=test_id))

            # Validate required fields for rejected samples
            if acceptance_status == 'Rejected':
                if not all([rejection_reason, person_notified, patient_advice]):
                    flash('Sample rejected. Please provide a reason, person notified, and advice for the patient.', 'danger')
                    return redirect(url_for('lab_web.add_samples', test_id=test_id))


            # Determine source department based on source type
            final_source = None
            brought_by_name = None
            if source_type == 'ward':
                final_source = source_department
                brought_by_name = brought_by_employee
            elif source_type == 'opd':
                final_source = opd_department
                brought_by_name = brought_by_employee
            else:  # external
                final_source = external_source
                brought_by_name = external_person
            # Determine the patient_id based on whether the test is linked to a consultation or a visit
            if test.consultation:
                patient_id_for_sample = test.consultation.patient_id
            elif test.visit:
                patient_id_for_sample = test.visit.patient_id
            else:
                # Handle cases where neither a consultation nor a visit is linked.
                # This might mean the test record is incomplete or there's another way to get the patient_id.
                # For now, we'll raise an error or assign None if it's acceptable for your model.
                # Consider what should happen if a test has no associated consultation or visit.
                flash('Error: Lab test is not linked to a patient consultation or visit.', 'danger')
                return redirect(url_for('lab_web.list_lab_tests')) # Or handle appropriately
                # Or: patient_id_for_sample = None # If your model allows null patient_id for some reason

            # Create new sample
            new_sample = Sample(
                test_id=test.id,
                patient_id=patient_id_for_sample,
                sample_type=sample_type,
                collection_time=collection_time,
                sample_quantity=quantity,
                collected_by_id=current_user.id, # Assumes current_user.id maps to the collector's ID
                sample_condition=sample_condition,
                collected_by=collected_by, # This is the string name from the form
                collection_site=collection_site,
                collection_method=collection_method,
                received_by=received_by,
                received_date=received_date,
                brought_by=brought_by_name,
                source_department=final_source,
                source_type=source_type,
                transportation_mode=transportation_mode,
                processing_notes=processing_notes,

                # --- Assigning Sample Verification Fields ---
                acceptance_status=acceptance_status,
                rejection_reason=rejection_reason,
                person_notified=person_notified,
                patient_advice=patient_advice,
                checklist_enough_sample=checklist_enough_sample,
                checklist_correct_tube=checklist_correct_tube,
                checklist_valid_collection_time=checklist_valid_collection_time,
                checklist_labeling=checklist_labeling,
                checklist_integrity=checklist_integrity
                # --- End Assignment ---
            )

            # Update test status based on sample acceptance
            if new_sample.acceptance_status == 'Accepted' and test.status == 'waiting processing':
                test.status = 'waiting results' # Or 'sample received', depending on your workflow
            elif new_sample.acceptance_status == 'Rejected':
                test.status = 'rejected'
                # You might want a specific status for the test if its only sample is rejected
                # For example, change test status to 'sample rejected' or keep 'waiting processing'
                # and require a new sample. For now, let's keep it simple.
                pass

            db.session.add(new_sample)
            db.session.commit()

            if new_sample.acceptance_status == 'Rejected':
                flash(f'Sample for {test.service.name} has been rejected.', 'danger')
            else:
                flash(f'Sample for {test.service.name} added and accepted successfully!', 'success')

            return redirect(url_for('lab_web.list_lab_tests'))

        # For GET request, show form
        return render_template('add_samples.html',
                               test=test,
                               title=f"Add Samples - {test.service.name}")

    except Exception as e:
        db.session.rollback()
        flash(f'Error adding samples: {str(e)}', 'danger')
        # You might want to log the full traceback for debugging: app.logger.error(f"Error in add_samples: {e}", exc_info=True)
        return redirect(url_for('lab_web.list_lab_tests'))

@lab_web_bp.route('/lab/samples/<int:test_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_sample(sample_id):
    # Implementation to edit sample details
    pass


@lab_web_bp.route('/lab/tests/<int:test_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_test(test_id):
    """Edit completed test results"""
    try:
        test = LabTest.query.options(
            joinedload(LabTest.consultation).joinedload(Consultation.patient),
            joinedload(LabTest.service)
        ).get_or_404(test_id)
        
        # Validate test can be edited
        if test.status != 'completed':
            flash('Only completed tests can be edited', 'warning')
            return redirect(url_for('lab_web.list_lab_tests'))
        
        if request.method == 'POST':
            # Process form submission
            test.results = request.form.get('results')
            test.notes = request.form.get('notes')
            test.edited_at = datetime.utcnow()
            test.edited_by_id = current_user.id
            
            db.session.commit()
            flash('Test results updated successfully', 'success')
            return redirect(url_for('lab_web.view_test_results', test_id=test_id))
        
        # For GET request, show form with current data
        return render_template('edit_test.html',
                              test=test,
                              title=f"Edit Results - {test.service.name}")
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error editing test: {str(e)}', 'danger')
        return redirect(url_for('lab_web.list_lab_tests'))

# ... existing routes below ...
    
    
    
@lab_web_bp.route('/lab/reports')
@login_required
def generate_lab_reports():
    """Lab reports with proper date filtering, test filtering, and growth comparisons."""
    try:
        page = request.args.get('page', 1, type=int)
        date_filter = request.args.get('date_range', 'current_month') # Default to current month
        test_id_filter = request.args.get('test_id', type=int)
        export_format = request.args.get('export')

        # Base query for completed lab tests
        base_query = LabTest.query.filter_by(status='completed')

        # Fixed date filtering using UTC time
        now = datetime.utcnow()
        start_date = None
        end_date = now

        if date_filter == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_filter == 'yesterday':
            yesterday = now - timedelta(days=1)
            start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif date_filter == 'current_week':
            start_date = now - timedelta(days=now.weekday()) # Monday of current week
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_filter == 'last_week':
            last_week_end = now - timedelta(days=now.weekday() + 1)
            start_date = last_week_end - timedelta(days=6)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = last_week_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif date_filter == 'current_month':
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif date_filter == 'last_month':
            last_month_end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            start_date = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = last_month_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif date_filter == 'current_year':
            start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        elif date_filter == 'last_year':
            last_year_end = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            start_date = last_year_end.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = last_year_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        # 'all' filter means no date range applied

        if start_date:
            base_query = base_query.filter(LabTest.completed_at >= start_date)
        if end_date and date_filter != 'all': # Only apply end_date if a specific range is chosen
            base_query = base_query.filter(LabTest.completed_at <= end_date)

        # Apply specific lab test filter
        if test_id_filter:
            base_query = base_query.filter(LabTest.service_id == test_id_filter)

        # Eager load relationships for efficiency
        query_for_pagination = base_query.options(
            joinedload(LabTest.service),
            joinedload(LabTest.consultation).joinedload(Consultation.patient),
            joinedload(LabTest.done_by)
        )

        reports = query_for_pagination.order_by(LabTest.completed_at.desc()).paginate(
            page=page,
            per_page=15,
            error_out=False
        )

        # --- Growth Comparison Data ---
        total_tests_current_period = base_query.count()

        growth_data = {}
        periods_to_compare = {
            'yesterday': {'current': (now.replace(hour=0, minute=0, second=0, microsecond=0), now),
                          'compare': (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1), now - timedelta(days=1))},
            'last_week': {'current': (now - timedelta(days=now.weekday()), now),
                          'compare': (now - timedelta(days=now.weekday() + 7), now - timedelta(days=now.weekday()))},
            'last_month': {'current': (now.replace(day=1), now),
                           'compare': ((now.replace(day=1) - timedelta(days=1)).replace(day=1), now.replace(day=1) - timedelta(days=1))},
            'last_year': {'current': (now.replace(month=1, day=1), now),
                          'compare': ((now.replace(month=1, day=1) - timedelta(days=1)).replace(month=1, day=1), now.replace(month=1, day=1) - timedelta(days=1))}
        }

        for period, dates in periods_to_compare.items():
            current_start, current_end = dates['current']
            compare_start, compare_end = dates['compare']

            current_count = LabTest.query.filter_by(status='completed').filter(
                LabTest.completed_at >= current_start,
                LabTest.completed_at <= current_end
            ).count()

            compare_count = LabTest.query.filter_by(status='completed').filter(
                LabTest.completed_at >= compare_start,
                LabTest.completed_at <= compare_end
            ).count()

            percentage_change = 0
            if compare_count > 0:
                percentage_change = ((current_count - compare_count) / compare_count) * 100
            elif current_count > 0: # If comparison period had 0, but current has >0
                percentage_change = 100
            growth_data[period] = {
                'current_count': current_count,
                'compare_count': compare_count,
                'percentage_change': percentage_change
            }
        # --- End Growth Comparison Data ---

        all_lab_tests = Service.query.filter_by(is_active=True).order_by(Service.name).all()
        # Handle export requests
        if export_format == 'pdf':
            return export_reports_to_pdf(reports.items, date_filter, test_id_filter, all_lab_tests)
        elif export_format == 'csv': # Changed from excel to csv
            return export_reports_to_csv(reports.items, date_filter, test_id_filter, all_lab_tests)


        return render_template(
            'lab_reports.html',
            reports=reports,
            date_filter=date_filter,
            test_id_filter=test_id_filter,
            all_lab_tests=all_lab_tests,
            growth_data=growth_data,
            title="Lab Reports & Analytics"
        )

    except Exception as e:
        current_app.logger.error(f"Error generating lab reports: {str(e)}", exc_info=True)
        flash(f'Error generating lab reports: {str(e)}', 'danger')
        return redirect(url_for('dashboard_web.index'))


def export_reports_to_pdf(reports_data, date_filter, test_id_filter, all_lab_tests):
    # This will render a separate HTML template specifically for PDF generation
    # You'll create 'lab_reports_pdf_template.html' in the next step
    html_content = render_template(
        'lab_reports_pdf_template.html',
        reports=reports_data,
        date_filter=date_filter,
        test_id_filter=test_id_filter,
        all_lab_tests=all_lab_tests,
        now=datetime.utcnow()
    )

    pdf = HTML(string=html_content, base_url=request.host_url).write_pdf()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"lab_reports_{date_filter}_{test_id_filter or 'all'}.pdf"
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

def export_reports_to_csv(reports_data, date_filter, test_id_filter, all_lab_tests):
    buffer = io.StringIO()
    # CSV Header
    header = [
        'Test ID', 'Patient Name', 'Patient ID', 'Test Name', 'Status',
        'Completed At', 'Done By', 'Interpretation', 'Notes', 'Is Paid',
        'Payment Status', 'Requested At', 'Verified By', 'Verified At'
    ]
    buffer.write(','.join(header) + '\n')

    # CSV Data
    for report in reports_data:
        patient_name = report.consultation.patient.full_name if report.consultation and report.consultation.patient else 'N/A'
        patient_id = report.consultation.patient.id if report.consultation and report.consultation.patient else 'N/A'
        test_name = report.service.name if report.service else 'N/A'
        done_by_name = report.done_by.full_name if report.done_by else 'N/A'
        completed_at_str = report.completed_at.strftime('%Y-%m-%d %H:%M') if report.completed_at else 'N/A'
        requested_at_str = report.requested_at.strftime('%Y-%m-%d %H:%M') if report.requested_at else 'N/A'
        verified_at_str = report.verified_at.strftime('%Y-%m-%d %H:%M') if report.verified_at else 'N/A'
        verified_by_name = report.doctor.full_name if report.doctor else 'N/A' # Assuming 'doctor' is verified_by

        row_data = [
            str(report.id),
            f'"{patient_name}"', # Enclose in quotes to handle commas in names
            f'"{patient_id}"',
            f'"{test_name}"',
            report.status.title(),
            completed_at_str,
            f'"{done_by_name}"',
            f'"{report.interpretation or "N/A"}"',
            f'"{report.notes or "N/A"}"',
            'Yes' if report.is_paid else 'No',
            report.payment_status.title(),
            requested_at_str,
            f'"{verified_by_name}"',
            verified_at_str
        ]
        buffer.write(','.join(row_data) + '\n')

    buffer.seek(0)
    filename = f"lab_reports_{date_filter}_{test_id_filter or 'all'}.csv"
    return send_file(io.BytesIO(buffer.getvalue().encode('utf-8')), as_attachment=True, download_name=filename, mimetype='text/csv')

@lab_web_bp.route('/lab/test_results/<int:test_id>') # <--- This is the route definition
@login_required
def view_lab_test_results(test_id): # <--- This is the function name (endpoint name part)
    # ... logic to fetch and render specific lab test results ...
    pass

@lab_web_bp.route('/reports/<int:test_id>')
@login_required
def view_lab_report(test_id):
    """
    Renders the lab test report as HTML or generates it as a PDF for download.
    """
    try:
        test = LabTest.query.options(
            joinedload(LabTest.consultation).joinedload(Consultation.patient),
            joinedload(LabTest.service),
            joinedload(LabTest.results_detail).joinedload(LabTestResult.parameter).joinedload(TestParameter.ranges),
            joinedload(LabTest.results_detail).joinedload(LabTestResult.parameter).joinedload(TestParameter.options)
        ).get_or_404(test_id)

        if test.status not in ['completed', 'verified']:
            flash(f'Lab test (ID: {test.id}) is not yet completed or verified.', 'warning')
            return redirect(url_for('lab_web.generate_lab_reports'))

        output_format = request.args.get('format', 'html').lower()


        # Patient info for range filtering (get once to avoid repeated access)
        patient_age_in_years = None
        patient_gender = None

        if test.consultation:
            patient_age_in_years = test.consultation.patient.age
            patient_gender = test.consultation.patient.gender
        elif test.visit:
            patient_age_in_years = test.visit.patient.age
            patient_gender = test.visit.patient.gender
        else:
            print(f"Warning: Test {test.id} has no associated consultation or visit for patient details.")

        filtered_ranges = {}
        for result in test.results_detail:
            param_id = result.parameter.parameter_id
            ranges_for_param = ParameterRange.query.filter(
                ParameterRange.parameter_id == param_id,
                (ParameterRange.sex == patient_gender) | (ParameterRange.sex == 'any'),
                (ParameterRange.age_min <= patient_age_in_years) | (ParameterRange.age_min.is_(None)),
                (ParameterRange.age_max >= patient_age_in_years) | (ParameterRange.age_max.is_(None))
            ).all()
            filtered_ranges[param_id] = ranges_for_param

        entered_by_technician = None
        verified_by_person = None 
        
        if test.results_detail:
            first_result = test.results_detail[0]
            entered_by_technician = first_result.entered_by
            verified_by_person = first_result.verified_by
            
        template_context = {
            'test': test,
            'filtered_ranges': filtered_ranges,
            'current_datetime': datetime.now(),
            'entered_by_technician': entered_by_technician,
            'verified_by_person': verified_by_person,
            'title': f"Lab Report - {test.service.name}"
        }

        if output_format == 'pdf':
            # Render the NEW PDF-specific template
            html_content = render_template('report_pdf_clean.html', **template_context)
            
            pdf = HTML(
                string=html_content,
                base_url=request.url_root # Important for WeasyPrint to find your CSS and assets
            ).write_pdf()

            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            patient_for_filename = None
            if test.consultation:
                patient_for_filename = test.consultation.patient
            elif test.visit:
                patient_for_filename = test.visit.patient

            if patient_for_filename:
                filename = f"lab_report_{patient_for_filename.full_name.replace(' ', '_')}_{test.service.name.replace(' ', '_')}_{test.id}.pdf"
            else:
                # Fallback filename if no patient is associated (e.g., if data is missing)
                filename = f"lab_report_unknown_patient_{test.service.name.replace(' ', '_')}_{test.id}.pdf"
                print(f"Warning: Patient details not found for test {test.id}. Using 'unknown_patient' in filename.") # Optional: log a warning
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        
        elif output_format == 'html':
            return render_template('report_detail.html', **template_context) # Still uses the full HTML template
        else:
            flash('Invalid report format requested.', 'danger')
            return redirect(url_for('lab_web.generate_lab_reports'))

    except Exception as e:
        current_app.logger.error(f"Error viewing lab report (ID: {test_id}): {e}", exc_info=True)
        flash(f'An unexpected error occurred while viewing the lab report. Please try again later. Error: {str(e)}', 'danger')
        return redirect(url_for('lab_web.generate_lab_reports'))

@lab_web_bp.route('/lab/tests/new', methods=['GET', 'POST'])
@login_required
def new_test_request():
    """Create new lab test request"""
    try:
        if request.method == 'POST':
            # Process form submission
            patient_id = request.form.get('patient_id')
            service_id = request.form.get('service_id')
            
            # Validate required fields
            if not all([patient_id, service_id]):
                flash('Please fill all required fields', 'danger')
                return redirect(url_for('lab_web.new_test_request'))
            
            # Create new lab test
            new_test = LabTest(
                patient_id=patient_id,
                service_id=service_id,
                status='requested',
                requested_at=datetime.utcnow()
            )
            
            db.session.add(new_test)
            db.session.commit()
            
            flash('Lab test request created successfully', 'success')
            return redirect(url_for('lab_web.list_lab_tests'))

        # Get available patients and services
        patients = Patient.query.order_by(Patient.last_name).all()
        services = Service.query.filter_by(category='Laboratory').all()
        
        return render_template('new_test_request.html',
                            patients=patients,
                            services=services)

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating test request: {str(e)}', 'danger')
        return redirect(url_for('lab_web.list_lab_tests'))
    


@lab_web_bp.route('/lab/results/<int:test_id>')
@login_required
def view_test_results(test_id):
    """View detailed test results"""
    try:
        test = LabTest.query.options(
            joinedload(LabTest.consultation).joinedload(Consultation.patient),
            joinedload(LabTest.service)
        ).get_or_404(test_id)
        
        return render_template('lab/test_results.html',
                            test=test,
                            title=f"Test Results - {test.service.name}")

    except Exception as e:
        flash(f'Error retrieving test results: {str(e)}', 'danger')
        return redirect(url_for('lab_web.list_lab_tests'))




@lab_web_bp.route('/process-test/<int:test_id>', methods=['GET', 'POST'])
@login_required
def process_test(test_id):
    # Load the LabTest with necessary joined loads for efficiency
    # Ensure TestParameter.ranges are eagerly loaded for efficient processing
    test = LabTest.query.options(
        joinedload(LabTest.consultation).joinedload(Consultation.patient),
        joinedload(LabTest.service).joinedload(Service.lab_test)
            .joinedload(LaboratoryTest.parameters)
            .joinedload(TestParameter.options),
        joinedload(LabTest.service).joinedload(Service.lab_test)
            .joinedload(LaboratoryTest.parameters)
            .joinedload(TestParameter.ranges)
    ).get_or_404(test_id)

    # Ensure the LabTest's associated LaboratoryTest exists and has parameters
    if not test.service or not test.service.lab_test:
        flash("Associated laboratory test definition not found or has no parameters.", 'danger')
        return redirect(url_for('lab_web.list_lab_tests'))

    # Get all parameters for this specific laboratory test
    parameters = test.service.lab_test.parameters

    # Fetch existing results for this LabTest
    # Create a dictionary for easy lookup: {parameter_id: LabTestResult_object}
    existing_results = {result.parameter_id: result for result in test.results_detail}

    # Initialize dictionaries for filtered data to pass to template/JS
    parameter_options = {}
    filtered_parameter_ranges = {}
    all_parameters_data_for_js = [] # This will be the JSON-serializable data for JS

    # Patient info for range filtering (get once to avoid repeated access)
    patient_age = None
    patient_gender = None

    if test.consultation:
        patient_age = test.consultation.patient.age
        patient_gender = test.consultation.patient.gender
    elif test.visit:
        patient_age = test.visit.patient.age
        patient_gender = test.visit.patient.gender
    else:
        print(f"Warning: Test {test.id} has no associated consultation or visit for patient details.")


    # --- Debugging Start ---
    print(f"DEBUG: Patient Age: {patient_age}, Patient Gender: {patient_gender}")
    current_app.logger.debug(f"Patient Age: {patient_age}, Patient Gender: {patient_gender}")
    # --- Debugging End ---

    for param in parameters:
        # Populate parameter_options for categorical types
        if param.result_type == 'categorical':
            parameter_options[param.parameter_id] = [opt.option_value for opt in param.options]

        # Prepare ranges for display in HTML and for JS validation
        param_ranges_for_js = []

        # --- Debugging Start ---
        print(f"\nDEBUG: Processing parameter: {param.parameter_name} (ID: {param.parameter_id})")
        print(f"DEBUG: Parameter result_type: {param.result_type}, Has ranges: {bool(param.ranges)}")
        current_app.logger.debug(f"Processing parameter: {param.parameter_name} (ID: {param.parameter_id})")
        current_app.logger.debug(f"Parameter result_type: {param.result_type}, Has ranges: {bool(param.ranges)}")
        # --- Debugging End ---

        if param.result_type == 'numeric' and param.ranges:
            for r in param.ranges:
                # --- Debugging Start ---
                print(f"  DEBUG: Checking range for '{param.parameter_name}':")
                print(f"    Range details: age_min={r.age_min}, age_max={r.age_max}, sex='{r.sex}'")
                current_app.logger.debug(f"  Checking range for '{param.parameter_name}':")
                current_app.logger.debug(f"    Range details: age_min={r.age_min}, age_max={r.age_max}, sex='{r.sex}'")
                # --- Debugging End ---

                # Filter ranges relevant to the patient's age and gender
                age_check = (patient_age is not None and r.age_min is not None and r.age_max is not None and
                             patient_age >= r.age_min and patient_age <= r.age_max)
                gender_check = (r.sex == 'Any' or r.sex == patient_gender)

                # --- Debugging Start ---
                print(f"    DEBUG: age_check: {age_check}, gender_check: {gender_check}")
                current_app.logger.debug(f"    age_check: {age_check}, gender_check: {gender_check}")
                # --- Debugging End ---

                if age_check and gender_check:
                    # Convert Numeric types to float for JSON serialization
                    param_ranges_for_js.append({
                        'normal_min': float(r.normal_min) if r.normal_min is not None else None,
                        'normal_max': float(r.normal_max) if r.normal_max is not None else None,
                        'critical_min': float(r.critical_min) if r.critical_min is not None else None,
                        'critical_max': float(r.critical_max) if r.critical_max is not None else None,
                        'age_min': r.age_min,
                        'age_max': r.age_max,
                        'sex': r.sex,
                        'age_unit': r.age_unit
                    })
            filtered_parameter_ranges[param.parameter_id] = param_ranges_for_js
        
        # --- Debugging Start ---
        print(f"DEBUG: Final param_ranges_for_js for {param.parameter_name}: {param_ranges_for_js}")
        current_app.logger.debug(f"Final param_ranges_for_js for {param.parameter_name}: {param_ranges_for_js}")
        # --- Debugging End ---

        # Build the JSON-serializable data for JS (all_parameters_data_for_js)
        all_parameters_data_for_js.append({
            'parameter_id': param.parameter_id,
            'parameter_name': param.parameter_name,
            'unit': param.unit,
            'result_type': param.result_type,
            'ranges': param_ranges_for_js, # Use the already filtered and serialized ranges
            'options': [opt.option_value for opt in param.options] if param.result_type == 'categorical' else []
        })


    if request.method == 'POST':
        try:
            action = request.form.get('action') # 'save_draft' or 'verify_and_complete'

            # Handle form submission for individual parameter results
            # Clear existing results for this test to avoid duplicates or stale data.
            # This approach simplifies handling updates, but consider a more
            # nuanced update strategy if historical tracking is critical.
            for result in test.results_detail:
                db.session.delete(result)
            db.session.commit() # Commit deletions before adding new ones

            for param in parameters:
                # Use param.parameter_id to match the form field names
                result_value = request.form.get(f'param_{param.parameter_id}')
                if result_value is None or result_value == '': # Don't save empty results
                    continue

                new_result = LabTestResult(
                    lab_test_id=test.id,
                    parameter_id=param.parameter_id, # Use param.parameter_id
                    unit=param.unit,
                    entered_by=current_user.full_name,
                    entered_at=datetime.utcnow()
                )

                if param.result_type == 'numeric':
                    try:
                        new_result.numeric_value = float(result_value)
                    except ValueError:
                        flash(f"Invalid numeric value for {param.parameter_name}.", 'danger')
                        db.session.rollback()
                        return redirect(url_for('lab_web_bp.process_test', test_id=test_id))
                elif param.result_type == 'categorical':
                    new_result.categorical_value = result_value
                elif param.result_type == 'text':
                    new_result.text_value = result_value
                    
                verifier_id_str = request.form.get('verifier_id')
                mark_verified_checked = request.form.get('mark_verified') # Checkbox for 'Mark as Verified'

                if not verifier_id_str:
                    flash('Please enter the Verifier ID to complete and verify the test.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('lab_web.process_test', test_id=test_id))

                try:
                    verifier_id = int(verifier_id_str)
                except ValueError:
                    flash('Invalid Verifier ID. Must be a number.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('lab_web.process_test', test_id=test_id))

                verifier_user = User.query.get(verifier_id)
                if not verifier_user:
                    flash(f'Verifier with ID {verifier_id} not found.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('lab_web.process_test', test_id=test_id))
                
                if not mark_verified_checked:
                    flash('You must check "Mark as Verified" to complete the test.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('lab_web.process_test', test_id=test_id)) 
                   
                new_result.verified_by = verifier_user.full_name # Store their full name
                new_result.verified_at = datetime.utcnow() # Time of verification
                db.session.add(new_result)

            # Handle general test notes and status
            test.notes = request.form.get('notes')
            test.interpretation = request.form.get('interpretation') # Assuming you have this field on LabTest model

            # Update test status if "complete" checkbox is checked
            # --- Verification Logic ---
            if action == 'verify_and_complete':


                # If all checks pass, mark the test as verified
                test.status = 'completed'
                test.completed_at = datetime.utcnow() # When the results were truly finalized
                test.done_by_id = current_user.id # Lab tech who entered/saved results
                test.done_at = datetime.utcnow() # Time lab tech finished data entry

                flash('Lab test successfully VERIFIED and COMPLETED! ✅', 'success')

            elif action == 'save_draft':
                # If 'Save Draft' button was clicked
                if test.status != 'verified': # Don't change status if already verified
                    test.status = 'processing' # Or 'draft', depending on your states
                
                # Clear verification details if it was unverified
                if request.form.get('mark_verified') is None and test.status != 'verified':
                    test.verified_by = None
                    test.verified_by_id = None
                    test.verified_at = None
                    # If it was marked completed but now unverified, revert
                    if test.status == 'completed': # If it was completed by current user, but not yet verified
                        test.status = 'processing'
                        test.completed_at = None
                        test.done_by_id = None
                        test.done_at = None

                flash('Lab test results saved as draft. 📝', 'info')
            
            db.session.commit()
            return redirect(url_for('lab_web.list_lab_tests'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error saving lab test results: {str(e)} ❌', 'danger')
            current_app.logger.error(f"Error processing test {test_id}: {e}", exc_info=True) # Log the error

    return render_template('process_test.html',
                           test=test,
                           parameters=parameters, # Still pass original parameters for primary loop
                           existing_results=existing_results,
                           parameter_options=parameter_options, # For categorical options
                           filtered_parameter_ranges=filtered_parameter_ranges, # For direct display of ranges in HTML
                           all_parameters_data=all_parameters_data_for_js, # For JS logic
                           title=f"Process {test.service.name}")

# New API endpoint to get user by ID
@lab_web_bp.route('/api/users/<int:user_id>', methods=['GET'])
@login_required # Ensure only logged-in users can access this
def get_user_details(user_id):
    user = User.query.get(user_id)
    if user:
        return jsonify({'id': user.id, 'full_name': user.full_name, 'username': user.username}), 200
    return jsonify({'message': 'User not found'}), 404

@lab_web_bp.route('/lab/tests/manage')
@login_required
def manage_test_types():
    """Manage available lab test types and panels"""
    try:
        test_page = request.args.get('test_page', 1, type=int)
        panel_page = request.args.get('panel_page', 1, type=int)
        search = request.args.get('q', '')

        # Query for individual laboratory tests
        tests_query = LaboratoryTest.query
        if search:
            tests_query = tests_query.filter(LaboratoryTest.test_name.ilike(f'%{search}%'))
        tests = tests_query.order_by(LaboratoryTest.test_name.asc()).paginate(
            page=test_page,
            per_page=15,
            error_out=False
        )

        # Query for test panels
        panels_query = TestPanel.query
        if search:
            panels_query = panels_query.filter(TestPanel.panel_name.ilike(f'%{search}%'))
        panels = panels_query.order_by(TestPanel.panel_name.asc()).paginate(
            page=panel_page,
            per_page=15,
            error_out=False
        )
        
        return render_template('manage_test_types.html',
                               tests=tests,
                               panels=panels,
                               search=search,
                               title="Manage Lab Test Types and Panels")

    except Exception as e:
        flash(f'Error retrieving lab tests or panels: {str(e)}', 'danger')
        return redirect(url_for('lab_web.list_lab_tests'))

@lab_web_bp.route('/lab/tests/create', methods=['GET', 'POST'])
@login_required
def create_test_type():
    """Create new lab test type"""
    if request.method == 'POST':
        try:
            # Extract Test Information
            test_name = request.form['test_name']
            department = request.form['department']
            sample_type = request.form['sample_type']
            short_code = request.form.get('short_code')
            device_manufacturer = request.form.get('device_manufacturer')
            
            turnaround_time_value = int(request.form['turnaround_time_value'])
            turnaround_time_unit = request.form['turnaround_time_unit']
            loinc_code = request.form.get('loinc_code')
            is_active = 'active_status' in request.form
            
            # Convert turnaround time to total minutes
            total_minutes = None
            if turnaround_time_unit == 'Hours':
                total_minutes = turnaround_time_value * 60
            elif turnaround_time_unit == 'Days':
                total_minutes = turnaround_time_value * 24 * 60
            elif turnaround_time_unit == 'Minutes': # Assuming you might also have minutes as a unit
                total_minutes = turnaround_time_value
            # else: total_minutes remains None

            new_test = LaboratoryTest(
                test_name=test_name,
                department=department,
                sample_type=sample_type,
                short_code=short_code,
                device_manufacturer=device_manufacturer,
                turnaround_time=total_minutes, # Store the integer total minutes
                is_active=is_active,
                loinc_code=loinc_code
            )
            db.session.add(new_test)
            db.session.flush() # Flush to get new_test.test_id before committing

            new_service = Service(
                name=test_name, # Service name is the same as lab test name
                category='Lab',
                description=f"Service for {test_name} laboratory test.",
                price=new_test.price if new_test.price is not None else 0.0, # Use lab test's price or default
                lab_test=new_test, # Establish the relationship
                is_active=is_active # Keep service active status consistent with test
            )
            db.session.add(new_service)
            # Extract Test Parameters
            parameter_index = 0
            while True:
                param_name_key = f'parameters[{parameter_index}][name]'
                if param_name_key not in request.form:
                    break # No more parameters
                
                param_name = request.form[param_name_key]
                param_synonym = request.form.get(f'parameters[{parameter_index}][synonym]')
                param_result_type = request.form[f'parameters[{parameter_index}][result_type]']
                
                param_unit_predefined = request.form.get(f'parameters[{parameter_index}][unit_predefined]')
                param_unit_custom = request.form.get(f'parameters[{parameter_index}][unit_custom]')
                
                # Prioritize custom unit if provided, otherwise use predefined
                param_unit = param_unit_custom if param_unit_custom else param_unit_predefined

                new_parameter = TestParameter(
                    test_id=new_test.test_id,
                    parameter_name=param_name,
                    synonym=param_synonym,
                    unit=param_unit,
                    result_type=param_result_type
                )
                db.session.add(new_parameter)
                db.session.flush() # Flush to get new_parameter.parameter_id

                # Extract Parameter Ranges (only for numeric result type)
                if param_result_type == 'numeric':
                    range_index = 0
                    while True:
                        range_age_min_key = f'parameters[{parameter_index}][ranges][{range_index}][age_min]'
                        if range_age_min_key not in request.form:
                            break
                        
                        age_min = request.form.get(range_age_min_key)
                        age_max = request.form.get(f'parameters[{parameter_index}][ranges][{range_index}][age_max]')
                        age_unit = request.form.get(f'parameters[{parameter_index}][ranges][{range_index}][age_unit]')
                        sex = request.form.get(f'parameters[{parameter_index}][ranges][{range_index}][sex]')
                        normal_min = request.form.get(f'parameters[{parameter_index}][ranges][{range_index}][normal_min]')
                        normal_max = request.form.get(f'parameters[{parameter_index}][ranges][{range_index}][normal_max]')
                        critical_min = request.form.get(f'parameters[{parameter_index}][ranges][{range_index}][critical_min]')
                        critical_max = request.form.get(f'parameters[{parameter_index}][ranges][{range_index}][critical_max]')

                        new_range = ParameterRange(
                            parameter_id=new_parameter.parameter_id,
                            age_min=int(age_min) if age_min else 0,
                            age_max=int(age_max) if age_max else 120,
                            age_unit=age_unit if age_unit else 'Years',
                            sex=sex if sex else 'Any',
                            normal_min=float(normal_min) if normal_min else None,
                            normal_max=float(normal_max) if normal_max else None,
                            critical_min=float(critical_min) if critical_min else None,
                            critical_max=float(critical_max) if critical_max else None
                        )
                        db.session.add(new_range)
                        range_index += 1
                
                # Extract Parameter Options (only for categorical result type)
                if param_result_type == 'categorical':
                    option_index = 0
                    while True:
                        option_value_key = f'parameters[{parameter_index}][options][{option_index}][value]'
                        if option_value_key not in request.form:
                            break
                        
                        option_value = request.form[option_value_key]
                        option_code = request.form.get(f'parameters[{parameter_index}][options][{option_index}][code]')

                        new_option = ParameterOption(
                            parameter_id=new_parameter.parameter_id,
                            option_value=option_value,
                            option_code=option_code
                        )
                        db.session.add(new_option)
                        option_index += 1

                parameter_index += 1

            # Handle Panels
            # Assign to Existing Panels
            assigned_panels = request.form.getlist('assigned_panels[]')
            for panel_name in assigned_panels:
                existing_panel = TestPanel.query.filter_by(panel_name=panel_name).first()
                if existing_panel:
                    panel_test = PanelTest(panel_id=existing_panel.panel_id, test_id=new_test.test_id)
                    db.session.add(panel_test)
                # else: You might want to log or flash a warning if an assigned panel doesn't exist

            # Create New Panels
            new_panel_index = 0
            while True:
                new_panel_name_key = f'new_panels[{new_panel_index}][name]'
                if new_panel_name_key not in request.form:
                    break
                
                new_panel_name = request.form[new_panel_name_key]
                new_panel_is_active = f'new_panels[{new_panel_index}][active_status]' in request.form

                existing_new_panel = TestPanel.query.filter_by(panel_name=new_panel_name).first()
                if existing_new_panel:
                    # If a panel with this name already exists, link the test to it
                    panel_test = PanelTest(panel_id=existing_new_panel.panel_id, test_id=new_test.test_id)
                    db.session.add(panel_test)
                else:
                    # Otherwise, create a new panel and link the test
                    panel = TestPanel(panel_name=new_panel_name, is_active=new_panel_is_active)
                    db.session.add(panel)
                    db.session.flush() # Get panel.panel_id
                    panel_test = PanelTest(panel_id=panel.panel_id, test_id=new_test.test_id)
                    db.session.add(panel_test)
                
                new_panel_index += 1

            db.session.commit()
            flash('Laboratory test created successfully!', 'success')
            return redirect(url_for('lab_web.create_test_type')) # Redirect to the same page or a success page
        
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
            # You might want to re-render the form with pre-filled data in case of an error
            print(f"Error during test creation: {e}") # For debugging purposes

    return render_template(
        'edit_test_type.html',
        title="Create New Lab Test Type",
        test_type=None # No existing test type for creation
    )


@lab_web_bp.route('/lab/tests/edit/<int:test_id>', methods=['GET', 'POST'])
@login_required
def edit_test_type(test_id):
    # Fetch the test type from the database
    test_type = db.session.get(LaboratoryTest, test_id)

    if not test_type:
        flash('Laboratory test not found.', 'danger')
        abort(404) # Or redirect to a list page

    # If it's a POST request, process the form submission
    if request.method == 'POST':
        try:
            # Update Test Information
            test_type.test_name = request.form['test_name']
            test_type.department = request.form['department']
            test_type.sample_type = request.form['sample_type']
            test_type.short_code = request.form.get('short_code')
            test_type.device_manufacturer = request.form.get('device_manufacturer')
            test_type.loinc_code = request.form.get('loinc_code')
            test_type.is_active = 'active_status' in request.form
            # Combine turnaround time value and unit
            # For turnaround_value
            turnaround_value_str = request.form.get('turnaround_time_value')
            turnaround_unit = request.form.get('turnaround_time_unit')

            total_minutes = None
            if turnaround_value_str and turnaround_unit:
                try:
                    turnaround_value = float(turnaround_value_str)  # Use float instead of int
                    if turnaround_unit == 'Hours':
                        total_minutes = int(turnaround_value * 60)
                    elif turnaround_unit == 'Days':
                        total_minutes = int(turnaround_value * 24 * 60)
                    elif turnaround_unit == 'Minutes':
                        total_minutes = int(turnaround_value)
                    elif turnaround_unit == 'Weeks':
                        total_minutes = int(turnaround_value * 7 * 24 * 60)
                except ValueError:
                    flash('Invalid turnaround time value. Please enter a number.', 'danger')
                    return redirect(request.url)

            # Validate range
            if total_minutes is not None and total_minutes > 2147483647:
                flash('Turnaround time is too long. Maximum allowed is about 4083 years.', 'danger')
                return redirect(request.url)

            test_type.turnaround_time = total_minutes


            # --- Start of Service Management Logic ---
            # Check if an associated service already exists
            # First, try to find an associated service specifically linked to this lab_test_id
            service = Service.query.filter_by(lab_test_id=test_type.test_id, category='Laboratory').first()

            if service:
                # If a service is already directly linked to THIS lab test, update it.
                # Crucially, ensure the name is only updated if it doesn't conflict
                # OR if the existing service is this one.
                existing_service_by_name = Service.query.filter_by(name=test_type.test_name).first()

                if existing_service_by_name and existing_service_by_name.id != service.id:
                    # A service with the new name already exists and it's NOT the one we're trying to update.
                    flash(f"A service with the name '{test_type.test_name}' already exists. Please choose a different test name or link to the existing service manually if intended.", 'danger')
                    db.session.rollback() # Rollback any changes
                    return redirect(request.url)

                service.name = test_type.test_name # Keep service name in sync with test name
                service.is_active = test_type.is_active # Keep active status in sync
                service.price = test_type.price if test_type.price is not None else 0.0 # Update price
                service.description = f"Service for {test_type.test_name} laboratory test."
                # Any other fields you want to keep in sync
            else:
                # No service explicitly linked to this lab_test_id.
                # Now, check if a service with this name already exists at all.
                existing_service_by_name = Service.query.filter_by(name=test_type.test_name).first()

                if existing_service_by_name:
                    # A service with this name exists. Instead of creating a duplicate,
                    # link this existing service to the current lab_test_id if it's not already linked to another.
                    if existing_service_by_name.lab_test_id is None:
                        # If the existing service is unlinked, we can claim it.
                        existing_service_by_name.lab_test_id = test_type.test_id
                        existing_service_by_name.is_active = test_type.is_active
                        existing_service_by_name.price = test_type.price if test_type.price is not None else 0.0
                        existing_service_by_name.description = f"Service for {test_type.test_name} laboratory test."
                        # Update other fields as necessary
                        flash(f"Linked existing service '{test_type.test_name}' to this laboratory test.", 'info')
                    else:
                        # The existing service with this name is already linked to another lab test.
                        flash(f"A service with the name '{test_type.test_name}' already exists and is linked to another laboratory test. Cannot create a duplicate.", 'danger')
                        db.session.rollback() # Rollback any changes
                        return redirect(request.url)
                else:
                    # No existing service found by name or by lab_test_id, so create a new one.
                    new_service = Service(
                        name=test_type.test_name,
                        category='Laboratory', # Ensure this matches your Service model's expected values
                        description=f"Service for {test_type.test_name} laboratory test.",
                        price=test_type.price if test_type.price is not None else 0.0,
                        lab_test=test_type, # Establish the relationship
                        is_active=test_type.is_active,
                        requires_prescription=True # Default as lab tests often require this
                    )
                    db.session.add(new_service)
            # --- End of Service Management Logic ---

            # Delete existing parameters, ranges, and options for this test
            # This is correct for the "delete and re-add" strategy.
            for param in test_type.parameters:
                for rng in param.ranges:
                    db.session.delete(rng)
                for opt in param.options:
                    db.session.delete(opt)
                db.session.delete(param)
            test_type.parameters = [] # Clear the collection in memory

            # 2. Iterate through submitted parameters more robustly
            # Collect all unique parameter indices from the form
            parameter_indices = set()
            for key in request.form:
                if key.startswith('parameters[') and '][name]' in key:
                    try:
                        # Extract the index, e.g., from 'parameters[0][name]' get '0'
                        index_str = key.split('[')[1].split(']')[0]
                        parameter_indices.add(int(index_str))
                    except (IndexError, ValueError):
                        # Handle malformed keys if necessary, or skip
                        continue

            # Sort indices to process them in order, though not strictly necessary for saving
            sorted_parameter_indices = sorted(list(parameter_indices))

            # Iterate through the submitted parameters using the identified indices
            for i in sorted_parameter_indices:
                param_name = request.form.get(f'parameters[{i}][name]')
                # IMPORTANT: Only process if parameter name exists and is not empty
                if not param_name:
                    # You might want to flash a message or log if a parameter name is missing
                    # flash(f"Skipping a parameter due to missing name at index {i}.", 'warning')
                    continue

                result_type = request.form.get(f'parameters[{i}][result_type]')
                unit_predefined = request.form.get(f'parameters[{i}][unit_predefined]')
                unit_custom = request.form.get(f'parameters[{i}][unit_custom]')
                synonym = request.form.get(f'parameters[{i}][synonym]')

                unit = unit_predefined if unit_predefined else unit_custom

                new_parameter = TestParameter(
                    test_id=test_type.test_id,
                    parameter_name=param_name,
                    synonym=synonym,
                    result_type=result_type,
                    unit=unit
                )
                db.session.add(new_parameter)
                db.session.flush() # Flush to get new_parameter.parameter_id

                # Add Ranges for the new parameter
                if result_type == 'numeric':
                    range_idx = 0
                    while True:
                        # Check for the presence of the age_min field for this range
                        age_min_field_name = f'parameters[{i}][ranges][{range_idx}][age_min]'
                        if age_min_field_name not in request.form:
                            break # No more ranges for this parameter

                        new_range = ParameterRange(
                            parameter_id=new_parameter.parameter_id,
                            age_min=request.form.get(age_min_field_name),
                            age_max=request.form.get(f'parameters[{i}][ranges][{range_idx}][age_max]'),
                            age_unit=request.form.get(f'parameters[{i}][ranges][{range_idx}][age_unit]'),
                            sex=request.form.get(f'parameters[{i}][ranges][{range_idx}][sex]'),
                            normal_min=request.form.get(f'parameters[{i}][ranges][{range_idx}][normal_min]'),
                            normal_max=request.form.get(f'parameters[{i}][ranges][{range_idx}][normal_max]'),
                            critical_min=request.form.get(f'parameters[{i}][ranges][{range_idx}][critical_min]'),
                            critical_max=request.form.get(f'parameters[{i}][ranges][{range_idx}][critical_max]')
                        )
                        db.session.add(new_range)
                        range_idx += 1

                # Add Options for the new parameter
                if result_type == 'categorical':
                    option_idx = 0
                    while True:
                        # Check for the presence of the option_value field for this option
                        option_value_field_name = f'parameters[{i}][options][{option_idx}][value]'
                        if option_value_field_name not in request.form:
                            break # No more options for this parameter

                        new_option = ParameterOption(
                            parameter_id=new_parameter.parameter_id,
                            option_value=request.form.get(option_value_field_name),
                            option_code=request.form.get(f'parameters[{i}][options][{option_idx}][code]')
                        )
                        db.session.add(new_option)
                        option_idx += 1
            # Handle Panels (similar clear and re-add strategy for simplicity)
            # Clear existing associations
            # Assuming TestPanel has a many-to-many relationship with LaboratoryTest
            # test_type.panels = [] # If using association table

            # If you're managing panels through TestPanel records themselves
            # and just updating which ones this test is part of, you'd fetch
            # and update the TestPanel.tests relationship or an association table.
            # For this example, let's assume `TestPanel` has `test_ids` or
            # a `test_id` foreign key. This needs to be clarified based on your schema.

            # For now, let's assume `assigned_panels` are panel IDs.
            # This part needs adjustment based on your actual panel-test relationship.
            # For simplicity, let's assume a direct linking mechanism or an association table.
            # For now, we'll just re-associate panels.
            # You might have an association table: test_panel_association_table
            # current_test_panels = db.session.query(test_panel_association_table).filter_by(test_id=test_type.test_id).all()
            # for row in current_test_panels:
            #     db.session.delete(row)

            # Retrieve existing panels to populate the select options
            all_panels = db.session.execute(db.select(TestPanel)).scalars().all()


            # For simplicity, let's assume we update the many-to-many relationship directly
            # First, clear current panels related to this test.
            test_type.panels.clear()

            # 2. Add assigned panels (existing panels)
            assigned_panel_ids = request.form.getlist('assigned_panels[]')
            for panel_id in assigned_panel_ids:
                panel = db.session.get(TestPanel, int(panel_id))
                if panel:
                    # Create a new PanelTest instance to establish the association
                    # and append it to the collection.
                    new_panel_test_association = PanelTest(panel=panel, test=test_type)
                    db.session.add(new_panel_test_association) # Add the association object

            # 3. Add new panels and associate them
            new_panel_names = request.form.getlist('new_panels[][name]')
            for i, panel_name in enumerate(new_panel_names):
                if panel_name:
                    new_panel_active = request.form.get(f'new_panels[{i}][active_status]') == 'on'
                    new_panel = TestPanel(panel_name=panel_name, is_active=new_panel_active)
                    db.session.add(new_panel)
                    db.session.flush() # Flush to get new_panel.panel_id

                    # Create a new PanelTest instance for the newly created panel
                    new_panel_test_association = PanelTest(panel=new_panel, test=test_type)
                    db.session.add(new_panel_test_association) 

            db.session.commit()
            flash('Laboratory test updated successfully!', 'success')
            return redirect(url_for('lab_web.manage_test_types')) # Redirect to test list

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating laboratory test: {str(e)}', 'danger')
            # For debugging, print the full traceback
            import traceback
            traceback.print_exc()

    # If it's a GET request, populate the form with existing data
    # Prepare data for the frontend
    # Note: Flask forms might handle this more elegantly, but for direct rendering,
    # we prepare the structure to match what the frontend expects.
    parameters_for_template = []
    for idx, param in enumerate(test_type.parameters): # Use enumerate here
        param_data = {
            'id': param.parameter_id,
            'name': param.parameter_name,
            'synonym': param.synonym,
            'result_type': param.result_type,
            'unit': param.unit,
            'ranges': [],
            'options': []
        }
        for r_idx, r in enumerate(param.ranges): # Enumerate for ranges too
            param_data['ranges'].append({
                'index': r_idx, # Add index if you want to pass it
                'age_min': r.age_min,
                'age_max': r.age_max,
                'age_unit': r.age_unit,
                'sex': r.sex,
                'normal_min': r.normal_min,
                'normal_max': r.normal_max,
                'critical_min': r.critical_min,
                'critical_max': r.critical_max
            })
        for o_idx, o in enumerate(param.options): # Enumerate for options too
            param_data['options'].append({
                'index': o_idx, # Add index if you want to pass it
                'value': o.option_value,
                'code': o.option_code
            })
        parameters_for_template.append((idx, param_data)) # Pass a tuple (index, dictionary)

    # Get all existing panels to populate the 'Assign to Existing Panels' dropdown
    all_panels = db.session.execute(db.select(TestPanel)).scalars().all()
    # Get the IDs of panels already assigned to this test
    assigned_panel_ids = [panel.panel_id for panel in test_type.panels]


    return render_template('edit_test.html',
                           test_type=test_type, # The main test object
                           parameters_data=parameters_for_template, # Structured parameters
                           all_panels=all_panels, # All available panels for selection
                           assigned_panel_ids=assigned_panel_ids, # IDs of already assigned panels
                           title=f"Edit {test_type.test_name}")

@lab_web_bp.route('/lab/tests/delete/<int:test_id>', methods=['POST'])
@login_required
def delete_test_type(test_id):
    """Delete lab test type"""
    try:
        test_type = Service.query.filter_by(
            id=test_id, 
            category='Laboratory'
        ).first_or_404()
        
        db.session.delete(test_type)
        db.session.commit()
        flash('Lab test type deleted successfully', 'success')
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting test type: {str(e)}', 'danger')
    
    return redirect(url_for('lab_web.manage_test_types'))



@lab_web_bp.route('/tests/<int:test_id>/toggle-status', methods=['PATCH'])
@login_required
def toggle_test_status(test_id):
    test = Service.query.get_or_404(test_id)
    test.is_active = not test.is_active
    db.session.commit()
    return jsonify({'status': 'success', 'is_active': test.is_active})


# Add these new routes to your lab_web_bp blueprint

@lab_web_bp.route('/lab/samples')
@login_required
def manage_samples():
    """Manage laboratory samples with search and status filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        status_filter = request.args.get('status', 'all')
        search_query = request.args.get('q', '')

        # Base query for samples
        query = Sample.query.options(
            joinedload(Sample.patient),
            joinedload(Sample.test).joinedload(LabTest.service)
        )

        # Apply status filter
        if status_filter != 'all':
            query = query.filter(Sample.status == status_filter)

        # Apply search filter
        if search_query:
            # Using .lower() for case-insensitive comparison, adjust as needed for database collation
            lower_search_query = search_query.lower()

            if lower_search_query.startswith('pid:'):
                pid = search_query[4:].strip()
                query = query.join(Patient).filter(Patient.patient_id.ilike(f'%{pid}%')) # Use ilike for partial matching
            elif lower_search_query.startswith('sid:'):
                sid = search_query[4:].strip()
                query = query.filter(Sample.sample_id.ilike(f'%{sid}%')) # Use ilike for partial matching
            else:
                query = query.join(Patient).filter(
                    or_(
                        Patient.full_name.ilike(f'%{search_query}%'),
                        Sample.sample_type.ilike(f'%{search_query}%')
                    )
                )

        # Fix: Order by 'collection_time' instead of 'collection_date'
        samples = query.order_by(Sample.collection_time.desc()).paginate(
            page=page, per_page=15, error_out=False
        )

        return render_template(
            'sample_management.html',
            samples=samples,
            status_filter=status_filter,
            search_query=search_query,
            title="Sample Management"
        )

    except Exception as e:
        flash(f'Error retrieving samples: {str(e)}', 'danger')
        # Log the error for debugging in production
        # current_app.logger.error(f"Error in manage_samples: {e}", exc_info=True)
        return redirect(url_for('lab_web.list_lab_tests'))

@lab_web_bp.route('/lab/samples/new', methods=['GET'])
@login_required
def new_sample():
    """Display form for adding a new sample"""
    try:
        # Get patients and tests for dropdowns
        patients = Patient.query.all()
        tests = LabTest.query.join(Service).order_by(Service.name.asc()).all()
        
        # Generate sample ID
        new_sample_id = generate_sample_id()
        
        return render_template(
            'new_sample.html',
            patients=patients,
            tests=tests,
            sample_id=new_sample_id,
            title="Add New Sample"
        )
    
    except Exception as e:
        flash(f'Error loading form: {str(e)}', 'danger')
        return redirect(url_for('lab_web.manage_samples'))

def generate_sample_id():
    """Generate unique sample ID with timestamp"""
    timestamp = datetime.utcnow().strftime("%y%m%d%H%M")
    return f"SMP-{timestamp}"

@lab_web_bp.route('/lab/samples', methods=['POST'])
@login_required
def add_sample():
    """Add a new sample to the system"""
    try:
        # Get form data
        source_type = request.form.get('source_type')
        source_department = request.form.get('source_department') if source_type != 'external' else None
        external_source = request.form.get('external_source') if source_type == 'external' else None
        
        sample_data = {
            'sample_id': request.form.get('sample_id'),
            'patient_id': request.form.get('patient_id'),
            'test_id': request.form.get('test_id'),
            'sample_type': request.form.get('sample_type'),
            'sample_quantity': request.form.get('sample_quantity'),
            'container_type': request.form.get('container_type'),
            'storage_conditions': request.form.get('storage_conditions'),
            'storage_location': request.form.get('storage_location'),
            'collection_date': datetime.strptime(request.form.get('collection_date'), '%Y-%m-%dT%H:%M'),
            'collected_by': request.form.get('collected_by'),
            'collection_site': request.form.get('collection_site'),
            'collection_method': request.form.get('collection_method'),
            'received_by': request.form.get('received_by'),
            'received_date': datetime.strptime(request.form.get('received_date'), '%Y-%m-%dT%H:%M') if request.form.get('received_date') else None,
            'brought_by_employee': request.form.get('brought_by_employee'),
            'source_department': source_department,
            'source_type': source_type,
            'transportation_mode': request.form.get('transportation_mode'),
            'status': request.form.get('status'),
            'processing_notes': request.form.get('processing_notes')
        }
        
        # Handle external source
        if source_type == 'external':
            sample_data['brought_by'] = f"External: {external_source}"
        else:
            if source_department:
                sample_data['brought_by'] = f"{source_department} (via {sample_data['brought_by_employee'] or 'employee'})"
            else:
                sample_data['brought_by'] = sample_data['brought_by_employee'] or "Employee"
        
        # Create new sample
        new_sample = Sample(**sample_data)
        db.session.add(new_sample)
        db.session.commit()
        
        flash('Sample added successfully!', 'success')
        return redirect(url_for('lab_web.manage_samples'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding sample: {str(e)}', 'danger')
        return redirect(url_for('lab_web.new_sample'))
    
@lab_web_bp.route('/lab/inventory')
@login_required
def inventory_management():
    """Manage laboratory inventory with category and stock filters"""

    from sqlalchemy import case, func
    from datetime import datetime, timedelta

    # Pagination
    page = request.args.get('page', 1, type=int)

    # Filters from query params
    category_filter = request.args.get('category', 'all').strip()
    low_stock = request.args.get('low_stock', 'false').lower() == 'true'

    # Base query
    query = LabInventory.query

    if category_filter != 'all':
        query = query.filter(LabInventory.category == category_filter)

    if low_stock:
        query = query.filter(LabInventory.quantity <= LabInventory.low_stock_threshold)

    # Order by expiry date (soonest first), then name
    query = query.order_by(
        case((LabInventory.expiry_date == None, 1), else_=0),
        LabInventory.expiry_date.asc(),
        LabInventory.item_name.asc()
    )

    # Paginate results
    inventory = query.paginate(page=page, per_page=20, error_out=False)

    # Stats (calculated separately)
    total_items = db.session.query(func.count(LabInventory.id)).scalar()

    low_stock_count = db.session.query(func.count(LabInventory.id)).filter(
        LabInventory.quantity <= LabInventory.low_stock_threshold
    ).scalar()

    expiring_soon_count = db.session.query(func.count(LabInventory.id)).filter(
        LabInventory.expiry_date != None,
        LabInventory.expiry_date <= datetime.utcnow() + timedelta(days=30)
    ).scalar()

    # Distinct categories
    categories = [c[0] for c in db.session.query(LabInventory.category).distinct()]

    return render_template(
        'lab-inventory/inventory_management.html',
        inventory=inventory,
        categories=categories,
        category_filter=category_filter,
        low_stock=low_stock,
        total_items=total_items,
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        timedelta=timedelta,
        now = datetime.utcnow().date(),
        title="Laboratory Inventory"
    )


def get_current_week_dates():
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday()) # Monday as the start of the week
    end_of_week = start_of_week + timedelta(days=6) # Sunday as the end of the week
    return start_of_week, end_of_week

def get_last_week_dates():
    today = datetime.utcnow().date()
    start_of_last_week = today - timedelta(days=today.weekday() + 7)
    end_of_last_week = start_of_last_week + timedelta(days=6)
    return start_of_last_week, end_of_last_week

def get_current_month_dates():
    today = datetime.utcnow().date()
    start_of_month = today.replace(day=1)
    # Calculate end of month: first day of next month minus one day
    if today.month == 12:
        end_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return start_of_month, end_of_month

def get_last_month_dates():
    today = datetime.utcnow().date()
    first_day_current_month = today.replace(day=1)
    last_day_last_month = first_day_current_month - timedelta(days=1)
    start_of_last_month = last_day_last_month.replace(day=1)
    return start_of_last_month, last_day_last_month


@lab_web_bp.route('/lab/equipment')
@login_required
def equipment_maintenance():
    """Track laboratory equipment maintenance schedule and history."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 10  # Number of items per page for the history table

        status_filter = request.args.get('status', 'all')
        due_soon = request.args.get('due_soon', 'false') == 'true'

        # --- Calculate Date Ranges ---
        # Current Week
        start_this_week, end_this_week = get_current_week_dates()
        # Last Week
        start_last_week, end_last_week = get_last_week_dates()
        # Current Month
        start_this_month, end_this_month = get_current_month_dates()
        # Last Month
        start_last_month, end_last_month = get_last_month_dates()

        # --- Dashboard Card Data ---
        total_equipment = LabEquipment.query.count()

        # Maintenance This Week
        maintenance_this_week_programmed = ScheduledMaintenanceLog.query.filter(
            ScheduledMaintenanceLog.qc_done == True,
            func.date(ScheduledMaintenanceLog.maintenance_date) >= start_this_week,
            func.date(ScheduledMaintenanceLog.maintenance_date) <= end_this_week
        ).count()
        maintenance_this_week_daily = DailyLogEntry.query.filter(
            DailyLogEntry.qc_done == True,
            func.date(DailyLogEntry.submission_date) >= start_this_week,
            func.date(DailyLogEntry.submission_date) <= end_this_week
        ).count()
        maintenance_this_week_total = maintenance_this_week_programmed + maintenance_this_week_daily

        # Maintenance Last Week
        maintenance_last_week_programmed = ScheduledMaintenanceLog.query.filter(
            ScheduledMaintenanceLog.qc_done == True,
            func.date(ScheduledMaintenanceLog.maintenance_date) >= start_last_week,
            func.date(ScheduledMaintenanceLog.maintenance_date) <= end_last_week
        ).count()
        maintenance_last_week_daily = DailyLogEntry.query.filter(
            DailyLogEntry.qc_done == True,
            func.date(DailyLogEntry.submission_date) >= start_last_week,
            func.date(DailyLogEntry.submission_date) <= end_last_week
        ).count()
        maintenance_last_week_total = maintenance_last_week_programmed + maintenance_last_week_daily

        # Maintenance This Month
        maintenance_this_month_programmed = ScheduledMaintenanceLog.query.filter(
            ScheduledMaintenanceLog.qc_done == True,
            func.date(ScheduledMaintenanceLog.maintenance_date) >= start_this_month,
            func.date(ScheduledMaintenanceLog.maintenance_date) <= end_this_month
        ).count()
        maintenance_this_month_daily = DailyLogEntry.query.filter(
            DailyLogEntry.qc_done == True,
            func.date(DailyLogEntry.submission_date) >= start_this_month,
            func.date(DailyLogEntry.submission_date) <= end_this_month
        ).count()
        maintenance_this_month_total = maintenance_this_month_programmed + maintenance_this_month_daily

        # Maintenance Last Month
        maintenance_last_month_programmed = ScheduledMaintenanceLog.query.filter(
            ScheduledMaintenanceLog.qc_done == True,
            func.date(ScheduledMaintenanceLog.maintenance_date) >= start_last_month,
            func.date(ScheduledMaintenanceLog.maintenance_date) <= end_last_month
        ).count()
        maintenance_last_month_daily = DailyLogEntry.query.filter(
            DailyLogEntry.qc_done == True,
            func.date(DailyLogEntry.submission_date) >= start_last_month,
            func.date(DailyLogEntry.submission_date) <= end_last_month
        ).count()
        maintenance_last_month_total = maintenance_last_month_programmed + maintenance_last_month_daily

        # Overall Maintenance Status
        pending_programmed_maintenance = ScheduledMaintenanceLog.query.filter_by(qc_done=False).count()
        
        seven_days_from_now = datetime.utcnow().date() + timedelta(days=7)
        urgent_repairs_count = ScheduledMaintenanceLog.query.filter(
            ScheduledMaintenanceLog.next_repair_date <= seven_days_from_now,
            ScheduledMaintenanceLog.qc_done == False
        ).count()
        
        total_maintenance_completed = ScheduledMaintenanceLog.query.filter_by(qc_done=True).count() + \
                                      DailyLogEntry.query.filter_by(qc_done=True).count()


        # --- Maintenance History Table Data (remains largely the same) ---
        daily_maintenance_query = DailyLogEntry.query.order_by(DailyLogEntry.submission_date.desc())
        programmed_maintenance_query = ScheduledMaintenanceLog.query.order_by(ScheduledMaintenanceLog.submission_date.desc())
        
        daily_records = daily_maintenance_query.all()
        programmed_records = programmed_maintenance_query.all()

        all_maintenance_history = []
        for record in daily_records:
            all_maintenance_history.append({
                'equipment': record.equipment,
                'type': 'Daily',
                'date': record.submission_date.strftime('%d %b %Y') if record.submission_date else 'N/A',
                'performed_by': record.performed_by if record.performed_by else 'Internal Staff',
                'qc_done_by_name': record.qc_person.full_name if record.qc_person else 'N/A', # Added QC Performed By Name
                'status': 'Completed' if record.qc_done else 'Pending QC',
                'id': record.id,
                'model_type': 'daily'
            })

        for record in programmed_records:
            all_maintenance_history.append({
                'equipment': record.equipment,
                'type': 'Programmed', # Or 'Scheduled' based on your preference for display
                'date': record.maintenance_date.strftime('%d %b %Y') if record.maintenance_date else 'N/A',
                'performed_by': record.performed_by if record.performed_by else 'External Vendor',
                'qc_done_by_name': record.qc_person.full_name if record.qc_person else 'N/A', # Added QC Performed By Name
                'status': 'Completed' if record.qc_done else 'Pending QC',
                'id': record.id,
                'model_type': 'programmed' # Changed to 'scheduled' for consistency with model name
            })


        all_maintenance_history.sort(key=lambda x: datetime.strptime(x['date'], '%d %b %Y') if x['date'] != 'N/A' else datetime.min, reverse=True)

        if status_filter != 'all':
            all_maintenance_history = [record for record in all_maintenance_history if record['status'] == status_filter]

        total_history_items = len(all_maintenance_history)
        total_pages = math.ceil(total_history_items / per_page)
        
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_history = all_maintenance_history[start_index:end_index]

        # --- Render Template ---
        return render_template(
            'equipment_maintenance.html',
            # Dashboard Card Data
            maintenance_this_week_total=maintenance_this_week_total,
            maintenance_this_week_programmed=maintenance_this_week_programmed,
            maintenance_this_week_daily=maintenance_this_week_daily,
            maintenance_last_week_total=maintenance_last_week_total,

            maintenance_this_month_total=maintenance_this_month_total,
            maintenance_this_month_programmed=maintenance_this_month_programmed,
            maintenance_this_month_daily=maintenance_this_month_daily,
            maintenance_last_month_total=maintenance_last_month_total,

            total_equipment=total_equipment,
            pending_programmed_maintenance=pending_programmed_maintenance,
            urgent_repairs_count=urgent_repairs_count,
            total_maintenance_completed=total_maintenance_completed,

            # Maintenance History Table Data
            maintenance_history=paginated_history,
            current_page=page,
            total_pages=total_pages,
            total_history_items=total_history_items,
            per_page=per_page,

            # Filters for the history table (passed for UI state)
            status_filter=status_filter,
            due_soon=due_soon,
            
            title="Equipment Maintenance"
        )
    except Exception as e:
        current_app.logger.error(f"Error in equipment_maintenance route: {e}")
        flash("An error occurred while fetching maintenance data.", "danger")
        return render_template('error.html', message="Could not load equipment maintenance data.")
    
    
    
# -----------------------------------------------------------------------
# NEW ROUTE TO FIX THE ERROR
# -----------------------------------------------------------------------

@lab_web_bp.route('/lab/maintenance_detail/<string:model_type>/<int:record_id>')
@login_required
def view_maintenance_detail(model_type, record_id):
    """
    Displays the detailed information for a specific daily or programmed maintenance record.
    """
    record = None
    uploaded_documents = [] # Initialize as empty list

    if model_type == 'daily':
        record = DailyLogEntry.query.get_or_404(record_id)
        # Fetch related documents for daily log entry
        uploaded_documents = UploadedFile.query.filter_by(
            daily_log_entry_id=record.id
        ).all()
    elif model_type == 'programmed':
        record = ScheduledMaintenanceLog.query.get_or_404(record_id)
        # Fetch related documents for scheduled maintenance log
        uploaded_documents = UploadedFile.query.filter_by(
            scheduled_maintenance_log_id=record.id
        ).all()
    else:
        flash("Invalid maintenance record type specified.", "danger")
        return redirect(url_for('lab_web.equipment_maintenance'))

    return render_template(
        'maintenance_detail.html',
        record=record,
        model_type=model_type,
        uploaded_documents=uploaded_documents, # Pass the fetched documents
        title=f"{model_type.capitalize()} Maintenance Detail"
    )
    
    
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']    
    
    
    
from werkzeug.utils import secure_filename
 
@lab_web_bp.route('/submit_daily_maintenance', methods=['POST'])
def submit_daily_maintenance():
    if request.method == 'POST':
        # Extract form data
        equipment = request.form.get('equipment')
        disinfection_type = request.form.get('disinfection_type')
        concentration = request.form.get('concentration')
        maintenance_notes = request.form.get('maintenance_notes')
        next_repair_date_str = request.form.get('next_repair_date') # Keep as string for now
        qc_done = 'qc_done' in request.form # Check if the checkbox is checked
        performed_by = request.form.get('performed_by')
        # New fields for QC performed by
        qc_done_by_id = request.form.get('qc_done_by_id')
        qc_done_by_name = request.form.get('qc_done_by_name')
        # Convert date string to Python date object
        next_repair_date = None
        if next_repair_date_str:
            try:
                next_repair_date = datetime.strptime(next_repair_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid "Next Repair Date" format for daily maintenance. Use YYYY-MM-DD.', 'danger')
                return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance
            
        # Convert qc_done_by_id to int if it exists, otherwise None
        qc_done_by_id_int = int(qc_done_by_id) if qc_done_by_id else None

        # Create a new DailyLogEntry record
        new_daily_record = DailyLogEntry(
            equipment=equipment,
            disinfection_type=disinfection_type,
            concentration=concentration,
            maintenance_notes=maintenance_notes,
            next_repair_date=next_repair_date,
            qc_done=qc_done,
             performed_by=performed_by,
                         qc_done_by_id=qc_done_by_id_int, # Store the ID
            qc_done_by_name=qc_done_by_name # Store the fetched name
        )
        db.session.add(new_daily_record)
        db.session.commit() # Commit to get the ID for related documents

        # Handle file upload for daily maintenance
        document_title = request.form.get('document_title')
        document_file = request.files.get('document_upload')

        if document_file and document_file.filename != '':
            if allowed_file(document_file.filename):
                filename = secure_filename(document_file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename) # Use current_app
                document_file.save(file_path)

                new_uploaded_file = UploadedFile(
                    title=document_title,
                    filename=filename,
                    daily_log_entry_id=new_daily_record.id # Link to the just-created record
                )
                db.session.add(new_uploaded_file)
                db.session.commit()
            else:
                flash('Invalid file type for daily maintenance document!', 'danger')
                return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance

        flash('Daily Maintenance form submitted successfully!', 'success')
        return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance
    return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance

# ------------------------------------------------------------------------------------------------------

@lab_web_bp.route('/submit_programmed_maintenance', methods=['POST'])
def submit_programmed_maintenance():
    if request.method == 'POST':
        # Extract form data
        equipment = request.form.get('equipment')
        maintenance_date_str = request.form.get('maintenance_date')
        next_repair_date_str = request.form.get('next_repair_date')
        troubleshooting = request.form.get('troubleshooting')
        recommended_action = request.form.get('recommended_action')
        action_taken = request.form.get('action_taken')
        
        # Convert numeric fields, handling potential errors
        try:
            labor_charges = float(request.form.get('labor_charges') or 0.0)
        except ValueError:
            flash('Invalid labor charges. Please enter a number.', 'danger')
            return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance
        
        try:
            spare_parts_cost = float(request.form.get('spare_parts_cost') or 0.0)
        except ValueError:
            flash('Invalid spare parts cost. Please enter a number.', 'danger')
            return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance
            
        qc_done = 'qc_done' in request.form # Check if the checkbox is checked
        qc_verification = request.form.get('qc_verification')
        performed_by = request.form.get('performed_by')
        # New fields for QC performed by
        qc_done_by_id = request.form.get('qc_done_by_id')
        qc_done_by_name = request.form.get('qc_done_by_name')

        # Convert date strings to Python date objects
        maintenance_date = None
        if maintenance_date_str:
            try:
                maintenance_date = datetime.strptime(maintenance_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid "Maintenance Date" format for programmed maintenance. Use YYYY-MM-DD.', 'danger')
                return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance

        next_repair_date = None
        if next_repair_date_str:
            try:
                next_repair_date = datetime.strptime(next_repair_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid "Next Repair Date" format for programmed maintenance. Use YYYY-MM-DD.', 'danger')
                return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance
            
        # Conditional validation for QC fields
        if qc_done and not qc_done_by_id:
            flash("QC Done requires a QC Performed By User ID.", "danger")
            return redirect(url_for('lab_web_bp.equipment_maintenance'))

        # Convert qc_done_by_id to int if it exists, otherwise None
        qc_done_by_id_int = int(qc_done_by_id) if qc_done_by_id else None
        # Create a new ScheduledMaintenanceLog record
        new_programmed_record = ScheduledMaintenanceLog(
            equipment=equipment,
            maintenance_date=maintenance_date,
            next_repair_date=next_repair_date,
            troubleshooting=troubleshooting,
            recommended_action=recommended_action,
            action_taken=action_taken,
            labor_charges=labor_charges,
            spare_parts_cost=spare_parts_cost,
            qc_done=qc_done,
            qc_verification=qc_verification,
            performed_by=performed_by,
            qc_done_by_id=qc_done_by_id_int, # Store the ID
            qc_done_by_name=qc_done_by_name # Store the fetched name

            
        )
        db.session.add(new_programmed_record)
        db.session.commit() # Commit to get the ID for related documents

        # Handle file upload for programmed maintenance
        document_title = request.form.get('document_title')
        document_file = request.files.get('document_upload')
        uploaded_filename = None

        if document_file and document_file.filename != '':
            if allowed_file(document_file.filename):
                filename = secure_filename(document_file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename) # Use current_app
                document_file.save(file_path)
                uploaded_filename = filename

                new_uploaded_file = UploadedFile(
                    title=document_title,
                    filename=filename,
                    scheduled_maintenance_log_id=new_programmed_record.id # Link to the just-created record
                )
                db.session.add(new_uploaded_file)
                db.session.commit()
            else:
                flash('Invalid file type for programmed maintenance document!', 'danger')
                return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance

        flash('Programmed Maintenance form submitted successfully!', 'success')
        return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance
    return redirect(url_for('lab_web.equipment_maintenance')) # Redirect to equipment_maintenance

@lab_web_bp.route('/lab/quality-control')
@login_required
def quality_control():
    """Quality control records with enhanced filtering for Kenyan standards"""
    try:
        page = request.args.get('page', 1, type=int)
        test_filter = request.args.get('test', 'all')
        result_filter = request.args.get('result', 'all')
        date_range = request.args.get('date_range', 'month')
        
        query = QualityControl.query.options(
            joinedload(QualityControl.test),
            joinedload(QualityControl.performer),
            joinedload(QualityControl.instrument)
        )
        
        # Apply test type filter
        if test_filter != 'all':
            query = query.filter(QualityControl.test_id == test_filter)
        
        # Apply result filter
        if result_filter != 'all':
            query = query.filter(QualityControl.result == result_filter)
        
        # Apply date range filter
        now = datetime.utcnow() # Use datetime.utcnow() for consistency
        today_date = date.today() # Get today's date without time for date comparisons
        
        if date_range == 'week':
            start_date = now - timedelta(days=7)
            query = query.filter(QualityControl.test_date >= start_date)
        elif date_range == 'month':
            start_date = now - timedelta(days=30)
            query = query.filter(QualityControl.test_date >= start_date)
        elif date_range == 'quarter':
            start_date = now - timedelta(days=90)
            query = query.filter(QualityControl.test_date >= start_date)
        elif date_range == 'year':
            start_date = now - timedelta(days=365)
            query = query.filter(QualityControl.test_date >= start_date)
        # 'all' shows all records
        
        # Order by test date descending
        qc_records = query.order_by(QualityControl.test_date.desc()).paginate(
            page=page, per_page=15, error_out=False
        )
        
        # Calculate pass rate for the last 30 days
        pass_count = QualityControl.query.filter(
            QualityControl.result == 'Pass',
            QualityControl.test_date >= now - timedelta(days=30)
        ).count()
        
        # Count due calibrations (using next_qc_date)
        # Calibrations due in the next 7 days, including today, or overdue
        due_calibrations_count = QualityControl.query.filter(
            QualityControl.next_qc_date.isnot(None), # Ensure there's a next_qc_date set
            (QualityControl.next_qc_date <= today_date + timedelta(days=7))
        ).count()
        
        # Get distinct QC tests for filter dropdown
        # Assuming 'Service' in your original code was meant to be 'LabTest'
        qc_tests = LaboratoryTest.query.all() 
        
        # Get lab instruments
        lab_instruments = LabEquipment.query.all()
        
        return render_template(
            'quality_control.html',
            qc_records=qc_records,
            qc_tests=qc_tests,
            lab_instruments=lab_instruments,
            test_filter=test_filter,
            result_filter=result_filter,
            date_range=date_range,
            pass_count=pass_count,
            due_calibrations_count=due_calibrations_count,
            title="Quality Control",
            now=datetime.utcnow # Pass current datetime to the template for calculations like `time_until_next_qc`
        )
    
    except Exception as e:
        current_app.logger.error(f"Error retrieving QC records: {str(e)}", exc_info=True)
        flash(f'Error retrieving QC records: {str(e)}', 'danger')
        return redirect(url_for('lab_web.list_lab_tests')) # Adjust redirection if this route doesn't exist

@lab_web_bp.route('/add_qc_record', methods=['GET', 'POST'])
@login_required
def add_qc_record():
    if request.method == 'POST':
        try:
            # Extract form data
            test_id = request.form.get('test_id')
            instrument_id = request.form.get('instrument_id')
            test_date_str = request.form.get('test_date')
            result = request.form.get('result')
            qc_performed_by_id = request.form.get('qc_performed_by_id')
            next_qc_date_str = request.form.get('next_qc_date')
            comments = request.form.get('comments')
            corrective_actions = request.form.get('corrective_actions')
            nabl_compliant = 'nabl_compliant' in request.form # Checkbox value
            
            # --- New: Get Quality Metrics from form if available ---
            standard_deviation = request.form.get('standard_deviation', type=float)
            coefficient_variation = request.form.get('coefficient_variation', type=float)
            target_value = request.form.get('target_value', type=float)
            observed_value = request.form.get('observed_value', type=float)
            tolerance_level = request.form.get('tolerance_level', type=float)

            # Validate required fields
            if not all([test_id, test_date_str, result, qc_performed_by_id]):
                flash('Please fill in all required fields (Test, Test Date, Result).', 'danger')
                return redirect(url_for('lab_web.quality_control'))

            # Convert date strings to datetime objects
            try:
                test_date = datetime.strptime(test_date_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('Invalid Test Date format.', 'danger')
                return redirect(url_for('lab_web.quality_control'))

            next_qc_date = None
            if next_qc_date_str:
                try:
                    next_qc_date = datetime.strptime(next_qc_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid Next QC Date format. Please use YYYY-MM-DD.', 'warning')
                    # Decide if you want to proceed without this field or abort
                    # For a non-critical field, continuing is often acceptable.

            # --- File Upload Handling for Testing Form ---
            testing_form_path = None # Initialize to None
            if 'testing_form' in request.files:
                file = request.files['testing_form']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    
                    # Define the specific upload folder for QC forms
                    qc_forms_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'qc_forms')
                    os.makedirs(qc_forms_folder, exist_ok=True) # Create if not exists

                    file_path = os.path.join(qc_forms_folder, filename)
                    file.save(file_path)
                    
                    # Store the relative path from 'static', and ensure forward slashes for URLs
                    testing_form_path = os.path.join('uploads', 'qc_forms', filename).replace('\\', '/')
                    flash('Testing form uploaded successfully!', 'info')
                elif file.filename != '': # If a file was selected but not allowed
                    flash('Invalid file type for testing form. Allowed types are PDF, PNG, JPG.', 'warning')
                    # You might want to return/redirect here if the file is mandatory
                    # return redirect(url_for('lab_web.quality_control'))

            # Create new QC record
            new_qc_record = QualityControl(
                test_id=test_id,
                instrument_id=instrument_id if instrument_id else None,
                test_date=test_date,
                result=result,
                comments=comments,
                performed_by=qc_performed_by_id,
                next_qc_date=next_qc_date,
                nabl_compliant=nabl_compliant,
                corrective_actions=corrective_actions,
                testing_form_path=testing_form_path,
                # Add quality metrics fields
                standard_deviation=standard_deviation,
                coefficient_variation=coefficient_variation,
                target_value=target_value,
                observed_value=observed_value,
                tolerance_level=tolerance_level
            )
            
            db.session.add(new_qc_record)
            db.session.commit()
            
            flash('QC Record added successfully! 🎉', 'success')
            return redirect(url_for('lab_web.quality_control'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding QC record: {e}", exc_info=True)
            flash(f'An error occurred: A problem occurred while saving the QC record. {str(e)} 😔', 'danger')
            return redirect(url_for('lab_web.quality_control'))

    # This part handles the GET request, displaying the form
    qc_tests = LabTest.query.all()
    lab_instruments = LabEquipment.query.all()
    return render_template('quality_control.html', qc_tests=qc_tests, lab_instruments=lab_instruments)

@lab_web_bp.route('/quality_control/view/<int:record_id>')
@login_required
def view_qc_record(record_id):
    """
    Displays detailed information for a single Quality Control record.
    """
    record = QualityControl.query.get_or_404(record_id)
    return render_template('view_qc_record.html', record=record)

@lab_web_bp.route('/quality_control/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_qc_record(record_id):
    """
    Handles editing of a Quality Control record.
    """
    record = QualityControl.query.get_or_404(record_id)
    # Assuming you have a Flask-WTF form for QC records
    # from app.lab.forms import QualityControlForm # Import your form

    # Example: If you have a form
    # form = QualityControlForm(obj=record) # Populate form with existing data

    # if form.validate_on_submit():
    #     form.populate_obj(record)
    #     db.session.commit()
    #     flash('Quality Control record updated successfully!', 'success')
    #     return redirect(url_for('lab.quality_control')) # Redirect back to the QC list

    # else: # This block is for GET requests or validation failures
    #     return render_template('edit_qc_record.html', record=record, form=form)

    # Simplified example without a form, just for illustration:
    if request.method == 'POST':
        # In a real application, you'd process form data here
        # For demonstration, let's assume you're getting data from request.form
        # record.test_date = datetime.strptime(request.form['test_date'], '%Y-%m-%d').date()
        # record.result = request.form['result']
        # ... update other fields ...
        # db.session.commit()
        flash('QC Record update logic would go here. (Not actually updated in this simplified example)', 'info')
        return redirect(url_for('lab.quality_control'))
    
    return render_template('edit_qc_record.html', record=record)
# Example of a placeholder view_qc_records route
@lab_web_bp.route('/view_qc_records')
@login_required
def view_qc_records():
    qc_records = QualityControl.query.all()
    return render_template('qc_records_list.html', qc_records=qc_records)

# Example of a placeholder for 'some_qc_form_page' in case of form errors
# You should replace 'your_qc_form_template.html' with the actual path to your HTML form
@lab_web_bp.route('/some_qc_form_page')
@login_required
def some_qc_form_page():
    qc_tests = LabTest.query.all()
    lab_instruments = LabEquipment.query.all()
    return render_template('your_qc_form_template.html', qc_tests=qc_tests, lab_instruments=lab_instruments)    
    

@lab_web_bp.route('/blood-bank/inventory')
@login_required
def blood_inventory():
    """Blood bank inventory management with enhanced filtering"""
    try:
        # Get query parameters
        blood_group = request.args.get('blood_group', 'all')
        component_type = request.args.get('component', 'Whole Blood')
        low_stock = request.args.get('low_stock', 'false') == 'true'
        status_filter = request.args.get('status', 'all')
        
        # Base query
        query = BloodInventory.query
        
        # Apply filters
        if blood_group != 'all':
            query = query.filter(BloodInventory.blood_group == blood_group)
        
        if component_type != 'all':
            query = query.filter(BloodInventory.component == component_type)
        
        if low_stock:
            query = query.filter(BloodInventory.quantity <= BloodInventory.low_stock_threshold)
        
        if status_filter != 'all':
            query = query.filter(BloodInventory.status == status_filter)
        
        # Filter out expired units
        today = date.today()
        query = query.filter(BloodInventory.expiry_date > today)
        
        # Order by expiry date
        inventory = query.order_by(BloodInventory.expiry_date.asc()).all()
        
        # Calculate blood group counts for summary
        group_counts = db.session.query(
            BloodInventory.blood_group,
            db.func.sum(BloodInventory.quantity).label('total')
        ).filter(
            BloodInventory.expiry_date > today,
            BloodInventory.status != 'Discarded'
        ).group_by(BloodInventory.blood_group).all()
        
        # Convert to dictionary for easier access
        group_counts_dict = {group: total for group, total in group_counts}
        
        # Get staff members for "Received By" dropdown
        staff_members = User.query.all()
        
        return render_template(
            'blood_bank.html',
            inventory=inventory,
            group_counts=group_counts_dict,
            blood_group=blood_group,
            
            component_type=component_type,
            low_stock=low_stock,
            status_filter=status_filter,
            staff_members=staff_members,
            now_date=date.today(),
            title="Blood Bank Inventory"
            
        )
    
    except Exception as e:
        flash(f'Error retrieving blood inventory: {str(e)}', 'danger')
        return redirect(url_for('dashboard_web.index'))
    
    
    
@lab_web_bp.route('/blood-bank/add', methods=['POST'])
@login_required
def add_blood_donation():
    try:
        # Extract form data
        form_data = request.form
        
        # --- File Upload Handling for Donor Form ---
        donor_form_path = None # Initialize to None
        if 'scanned_form' in request.files: # Your HTML input needs to be 'scanned_form' or you change this to 'donor_form'
            file = request.files['scanned_form'] # Assuming the input field name is 'scanned_form'
            if file and allowed_file(file.filename): # Use the helper function
                filename = secure_filename(file.filename)
                
                # Define the specific upload folder for donor documents
                # Make sure current_app.config['UPLOAD_FOLDER'] is set (e.g., to 'static/uploads')
                donor_documents_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'donor_documents')
                os.makedirs(donor_documents_folder, exist_ok=True) # Create if not exists

                file_path = os.path.join(donor_documents_folder, filename)
                file.save(file_path)
                
                # Store the relative path from static, and ensure forward slashes
                # THIS IS THE KEY CHANGE: .replace('\\', '/')
                donor_form_path = os.path.join('uploads', 'donor_documents', filename).replace('\\', '/')
                flash('Donor form uploaded successfully!', 'info')
            elif file.filename != '' and not allowed_file(file.filename):
                flash('Invalid file type or no file selected for scanned form.', 'warning')
                # Decide if you want to abort or continue without the file
                # If you abort here, it means the donation won't be added if the file is bad.
                # return redirect(url_for('lab_web.blood_inventory'))


        # Generate a unique donation_id (example, adjust as per your logic)
        # You might have a more robust system for this (e.g., UUID, sequence)
        # For simplicity, let's use a timestamp for now, but ensure uniqueness.
        # It was in your form_data['donation_id'] originally, but not in the HTML form.
        # If your form doesn't have it, you need to generate it here.
        donation_id = f"DON-{datetime.now().strftime('%Y%m%d%H%M%S')}-{os.urandom(2).hex()}"

        # Get donor type and related fields
        donor_type = form_data.get('donor_type', 'Voluntary') # Default to Voluntary if not present
        donor_id = None
        amount_paid = None
        # Assuming if donor_type is 'Paid', amount_paid will be available
        if donor_type == 'Paid':
            try:
                amount_paid = float(form_data.get('amount_paid', 0.0))
            except ValueError:
                flash('Invalid amount paid. Please enter a number.', 'danger')
                return redirect(url_for('lab_web.blood_inventory'))
        
        # Extract donor_height and donor_weight, handling potential missing values or type conversion errors
        try:
            donor_height = float(form_data.get('donor_height')) if form_data.get('donor_height') else None
        except ValueError:
            donor_height = None # Set to None if conversion fails
        
        try:
            donor_weight = float(form_data.get('donor_weight')) if form_data.get('donor_weight') else None
        except ValueError:
            donor_weight = None # Set to None if conversion fails


        # Create new blood donation record
        new_donation = BloodInventory(
            donation_id=donation_id, # Use generated/fetched ID
            blood_group=form_data.get('blood_group', "Unknown"), # You need to add blood group and component to your form!
            component=form_data.get('component', "Whole Blood"), # These fields are missing in your HTML form.
            quantity=int(form_data['quantity']),
            donation_date=datetime.strptime(form_data['donation_date'], '%Y-%m-%d').date(),
            expiry_date=datetime.strptime(form_data['expiry_date'], '%Y-%m-%d').date(),
            donor_type=donor_type,
            # For 'Patient' donor_type, you'd need a 'patient_id' input in your form
            # donor_id=int(form_data['patient_id']) if donor_type == 'Patient' and form_data.get('patient_id') else None,
            donor_id=None, # Your current form doesn't have a patient_id for 'Patient' type
            donor_full_name=form_data['donor_full_name'], # Match new model field name
            donor_contact=form_data['donor_contact'],
            donor_age=int(form_data['donor_age']),
            donor_gender=form_data.get('donor_gender'), # Not in form, but in model
            donor_height=donor_height, # New field
            donor_weight=donor_weight, # New field
            amount_paid=amount_paid, # New field
            donor_form_path=donor_form_path, # New field (now consistently formatted)
            screening_form_path=None, # New donations won't have a screening form path initially
            received_by=current_user.id, # Using current_user.id instead of form data for simplicity
            storage_location=form_data['storage_location'],
            status='Waiting Screening' # Set default status here
        )
        
        db.session.add(new_donation)
        db.session.commit()
        
        flash('Blood donation added successfully!', 'success')
        return redirect(url_for('lab_web.blood_inventory'))
    
    except Exception as e:
        db.session.rollback()
        # Log the error for debugging purposes
        current_app.logger.error(f"Error adding blood donation: {e}", exc_info=True)
        flash(f'Error adding blood donation: A problem occurred while saving the record. {str(e)}', 'danger')
        return redirect(url_for('lab_web.blood_inventory'))

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@lab_web_bp.route('/perform-screening/<int:donation_id>', methods=['GET'])
def perform_screening(donation_id):
    """
    Renders the blood screening form for a specific donation.
    """
    donation = BloodInventory.query.get_or_404(donation_id)
    # Ensure only 'Waiting Screening' or 'Available' (if re-screening) items can be screened
    if donation.status not in ['Waiting Screening', 'Available']:
        flash(f'Blood unit {donation.donation_id} is not in a state to be screened.', 'warning')
        return redirect(url_for('lab_web.blood_inventory'))

    # You might want to pass the current user for `tested_by` field later
    # For now, we'll assume the current user is recorded on submission.
    return render_template('screening_form.html', donation=donation)

@lab_web_bp.route('/submit-screening/<int:donation_id>', methods=['POST'])
def submit_screening(donation_id):
    """
    Handles the submission of the blood screening form.
    Updates blood safety, group, test results, and uploads scanned form.
    """
    donation = BloodInventory.query.get_or_404(donation_id)

    # Basic check for existing screening
    if donation.tested and 're-screen' not in request.form: # Add a hidden input to allow re-screening if needed
        flash('This blood unit has already been screened.', 'info')
        return redirect(url_for('lab_web.blood_inventory'))

    # Get form data
    blood_group = request.form.get('blood_group')
    blood_safety = request.form.get('blood_safety')
    test_results = request.form.get('test_results')
    tested = request.form.get('tested') == 'on' # Checkbox value 'on' if checked

    # Update donation object
    donation.blood_group = blood_group
    donation.test_results = test_results
    donation.tested = tested # Mark as tested if checkbox is checked

    if blood_safety == 'unsafe':
        donation.status = 'Discarded'
        flash(f'Blood unit {donation.donation_id} marked as unsafe and status changed to Discarded.', 'danger')
    elif blood_safety == 'safe' and tested:
        # Only set to 'Available' if marked safe AND screening is complete
        if donation.status == 'Waiting Screening': # Only change from this specific status
            donation.status = 'Available'
        flash(f'Blood unit {donation.donation_id} marked as safe and status updated to Available.', 'success')
    elif blood_safety == 'safe' and not tested:
        flash(f'Blood unit {donation.donation_id} marked as safe, but screening is not marked complete. Status remains "{donation.status}".', 'warning')
    else:
        # If user selects nothing or weird state, revert/don't change status
        flash(f'Could not determine final status for {donation.donation_id}. Please review.', 'warning')

    # Handle file upload
    if 'scanned_form' in request.files:
        file = request.files['scanned_form']
        if file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'screening_forms')
            os.makedirs(upload_folder, exist_ok=True) # Create directory if it doesn't exist
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            # Store relative path to be accessible via Flask's static files
            donation.screening_form_path = os.path.join('uploads', 'screening_forms', filename).replace('\\', '/')
            flash('Scanned form uploaded successfully!', 'info')
        elif file.filename != '' and not allowed_file(file.filename):
            flash('Invalid file type for scanned form. Only PDF, JPG, PNG are allowed.', 'warning')


    # Associate current user (tested_by)
    # You'll need to get the current logged-in user's ID here.
    # Example (assuming Flask-Login is used and current_user is available):
    from flask_login import current_user
    if current_user.is_authenticated:
        donation.tested_by = current_user.id
    else:
        # Handle case where user is not logged in (e.g., redirect to login)
        flash('You must be logged in to perform screening.', 'danger')
        return redirect(url_for('auth.login')) # Assuming an 'auth' blueprint for login

    try:
        db.session.commit()
        flash(f'Screening results for {donation.donation_id} saved successfully! 🎉', 'success')
        return redirect(url_for('lab_web.blood_inventory')) # Redirect to inventory list
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving screening results for {donation.donation_id}: {e}")
        flash(f'An error occurred while saving results. Please try again. Error: {str(e)} 🙁', 'danger')
        return render_template('screening_form.html', donation=donation)

@lab_web_bp.route('/blood-details/<int:donation_id>', methods=['GET'])
@login_required
def view_blood_details(donation_id):
    """
    Displays comprehensive details of a specific blood inventory record.
    """
    donation = BloodInventory.query.get_or_404(donation_id)
    # You might need to fetch related user and patient objects if not eager loaded
    received_by_user = User.query.get(donation.received_by)
    tested_by_user = User.query.get(donation.tested_by) if donation.tested_by else None
    stored_by_user = User.query.get(donation.stored_by) if donation.stored_by else None
    patient_donor = Patient.query.get(donation.donor_id) if donation.donor_id else None

    return render_template('blood_details_page.html',
                           donation=donation,
                           received_by_user=received_by_user,
                           tested_by_user=tested_by_user,
                           stored_by_user=stored_by_user,
                           patient_donor=patient_donor)

@lab_web_bp.route('/edit-blood-record/<int:donation_id>', methods=['GET', 'POST'])
@login_required
def edit_blood_record(donation_id):
    """
    Allows editing of a specific blood inventory record.
    """
    donation = BloodInventory.query.get_or_404(donation_id)

    if request.method == 'POST':
        # Retrieve form data for editing
        # Note: You'll need an HTML form similar to the screening form
        # but with all editable fields from the BloodInventory model.
        # For simplicity, I'm just showing an example of updating a few fields.

        donation.blood_group = request.form.get('blood_group', donation.blood_group)
        donation.component = request.form.get('component', donation.component)
        donation.quantity = request.form.get('quantity', type=int, default=donation.quantity)
        donation.donation_date = datetime.strptime(request.form.get('donation_date'), '%Y-%m-%d').date() if request.form.get('donation_date') else donation.donation_date
        # ... and so on for other fields you want to allow editing

        donation.updated_at = datetime.utcnow() # Update timestamp

        try:
            db.session.commit()
            flash(f'Blood record {donation.donation_id} updated successfully! ✨', 'success')
            return redirect(url_for('lab_web.blood_inventory_list'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating blood record {donation.donation_id}: {e}")
            flash(f'An error occurred while updating the record: {str(e)} 😔', 'danger')

    # For GET request or if POST failed, render the edit form
    return render_template('edit_blood_record.html', donation=donation)


@lab_web_bp.route('/blood-bank/delete/<int:donation_id>', methods=['POST'])
@login_required
def delete_blood_record(donation_id):
    """
    Handles the deletion of a blood inventory record.
    """
    donation = BloodInventory.query.get_or_404(donation_id)
    donation_id_str = donation.donation_id # Store before deleting for flash message

    try:
        db.session.delete(donation)
        db.session.commit()
        flash(f'Blood record {donation_id_str} deleted successfully. 🗑️', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting blood record {donation_id_str}: {e}")
        flash(f'An error occurred while deleting the record: {str(e)} 🚫', 'danger')

    return redirect(url_for('lab_web.blood_inventory'))



@lab_web_bp.route('/inventory/manage-consumables', methods=['GET'])
@login_required
def manage_consumables():
    """List all active laboratory tests and their consumables"""
    try:
        tests = LaboratoryTest.query.filter_by(is_active=True) \
            .order_by(LaboratoryTest.test_name.asc()) \
            .all()

        # Collect consumables for each test
        tests_with_consumables = []
        for test in tests:
            consumables = [
                {
                    "item_name": c.inventory_item.item_name,
                    "quantity_used": c.quantity_used
                }
                for c in test.consumables
            ]
            tests_with_consumables.append({
                "test": test,
                "consumables": consumables
            })

        return render_template(
            "lab-inventory/manage_consumables.html",
            tests=tests_with_consumables,
            title="Manage Consumables"
        )
    except Exception as e:
        flash(f"Error loading laboratory tests: {str(e)}", "danger")
        return redirect(url_for("lab_web.inventory_management"))


@lab_web_bp.route('/inventory/add-consumables/<int:test_id>', methods=['GET', 'POST'])
@login_required
def add_consumables(test_id):
    """Add consumables to a specific laboratory test"""
    test = LaboratoryTest.query.get_or_404(test_id)

    if request.method == 'POST':
        try:
            # safer parsing of JSON
            consumables_data = request.get_json(force=True).get("consumables", [])
            if not consumables_data:
                return jsonify({"error": "No consumables provided"}), 400

            for item in consumables_data:
                inventory_id = item.get("inventory_id")
                qty = int(item.get("quantity_used", 1))

                inv_item = LabInventory.query.get(inventory_id)
                if not inv_item:
                    raise ValueError(f"Inventory item {inventory_id} not found")

                if qty <= 0:
                    raise ValueError(f"Quantity must be positive for {inv_item.item_name}")

                # 🔗 Save link
                consumable = LabConsumable(
                    test_id=test.test_id,
                    inventory_id=inventory_id,
                    quantity_used=qty
                )
                db.session.add(consumable)

            db.session.commit()
            return jsonify({"success": True, "message": f"Consumables added for {test.test_name}"})

        except Exception as e:
            db.session.rollback()
            # print full traceback for debugging
            import traceback
            print("❌ ERROR in add_consumables:", e)
            traceback.print_exc()
            return jsonify({"error": str(e)}), 400

    # GET → load form with available consumables
    inventory_items = LabInventory.query.order_by(LabInventory.item_name).all()

    return render_template(
        "lab-inventory/add_consumables.html",
        test=test,
        inventory_items=inventory_items,
        title=f"Add Consumables for {test.test_name}"
    )


@lab_web_bp.route('/inventory/edit-consumables/<int:test_id>', methods=['GET', 'POST'])
@login_required
def edit_consumables(test_id):
    """Edit consumables for a specific laboratory test"""
    test = LaboratoryTest.query.get_or_404(test_id)
    inventory_items = LabInventory.query.order_by(LabInventory.item_name).all()

    if request.method == 'POST':
        try:
            consumables_data = request.get_json(force=True).get("consumables", [])
            if not consumables_data:
                return jsonify({"error": "No consumables provided"}), 400

            # Delete existing consumables first
            LabConsumable.query.filter_by(test_id=test_id).delete()

            # Add updated consumables
            for item in consumables_data:
                inventory_id = item.get("inventory_id")
                qty = int(item.get("quantity_used", 1))
                if qty <= 0:
                    raise ValueError("Quantity must be positive")

                consumable = LabConsumable(
                    test_id=test_id,
                    inventory_id=inventory_id,
                    quantity_used=qty
                )
                db.session.add(consumable)

            db.session.commit()
            return jsonify({"success": True, "message": f"Consumables updated for {test.test_name}"})

        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 400

    # GET → show current consumables for editing
    current_consumables = [
        {
            "inventory_id": c.inventory_item.id,
            "item_name": c.inventory_item.item_name,
            "quantity_used": c.quantity_used
        } for c in test.consumables
    ]

    return render_template(
        "lab-inventory/edit_consumables.html",
        test=test,
        inventory_items=inventory_items,
        current_consumables=current_consumables,
        title=f"Edit Consumables for {test.test_name}"
    )


@lab_web_bp.route('/inventory/delete-consumables/<int:test_id>', methods=['POST'])
@login_required
def delete_consumable(test_id):
    test = LaboratoryTest.query.get_or_404(test_id)
    try:
        # Delete all consumables linked to this test
        LabConsumable.query.filter_by(test_id=test.test_id).delete()
        db.session.commit()
        flash(f"All consumables for '{test.test_name}' have been deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting consumables: {str(e)}", "danger")
    return redirect(url_for('lab_web.manage_consumables'))



    
@lab_web_bp.route('/inventory/request-stocks')
@login_required
def request_stocks():
    """Display and manage laboratory stock requests"""
    try:
        # Get filter parameters
        status = request.args.get('status', 'all')
        priority = request.args.get('priority', 'all')
        page = request.args.get('page', 1, type=int)
        
        # Base query for lab stock requests with stock relationship joined
        query = StockRequest.query.filter_by(department='lab').options(
            joinedload(StockRequest.stock)
        )
        
        # Apply status filter
        if status != 'all':
            query = query.filter(StockRequest.status == status)
        
        # Apply priority filter
        if priority != 'all':
            query = query.filter(StockRequest.priority == priority)
        
        # Order and paginate
        paginated_requests = query.order_by(StockRequest.created_at.desc()).paginate(
            page=page, per_page=15, error_out=False
        )
        
        # Get bulk requests separately for grouping
        bulk_requests = BulkRequest.query.filter_by(department='lab').order_by(
            BulkRequest.created_at.desc()
        ).all()
        
        # Get status counts for filter badges (include both individual and bulk)
        status_counts = {
            'all': StockRequest.query.filter_by(department='lab').count() + len(bulk_requests),
            'submitted': StockRequest.query.filter_by(department='lab', status='submitted').count() + 
                         len([b for b in bulk_requests if b.status == 'submitted']),
            'approved': StockRequest.query.filter_by(department='lab', status='approved').count() + 
                       len([b for b in bulk_requests if b.status == 'approved']),
            'fulfilled': StockRequest.query.filter_by(department='lab', status='fulfilled').count() + 
                        len([b for b in bulk_requests if b.status == 'fulfilled']),
            'rejected': StockRequest.query.filter_by(department='lab', status='rejected').count() + 
                       len([b for b in bulk_requests if b.status == 'rejected']),
        }
        
        # Get priority options for filter dropdown
        priorities = ['routine', 'urgent', 'emergency']
        
        return render_template(
            'lab-inventory/request_stocks.html',
            requests=paginated_requests.items,
            bulk_requests=bulk_requests,  # Pass bulk requests separately
            pagination=paginated_requests,
            status_counts=status_counts,
            current_status=status,
            priorities=priorities,
            current_priority=priority,
            title="Lab Stock Requests"
        )
    
    except Exception as e:
        flash(f'Error loading stock requests: {str(e)}', 'danger')
        return redirect(url_for('lab_web.inventory_management'))

@lab_web_bp.route('/inventory/bulk-requests/<bulk_id>')
@login_required
def bulk_request_detail(bulk_id):
    """View details of a specific bulk request"""
    bulk_request = BulkRequest.query.get_or_404(bulk_id)
    stock_requests = bulk_request.stock_requests.all()
        
    return render_template('lab-inventory/bulk_request_detail.html',
                         bulk_request=bulk_request,
                         stock_requests=stock_requests,
                         title=f"Bulk Request {bulk_request.bulk_code}")

@lab_web_bp.route('/inventory/request-stocks/new', methods=['GET', 'POST'])
@login_required
def create_stock_request():
    """Create new laboratory stock request - supports both single and bulk requests"""
    # Get lab inventory items with details
    lab_items = Stock.query.filter_by(is_active=True).all()
    
    # Create form with choices populated BEFORE validation
    form = LabStockRequestForm()
    form.item_id.choices = [(item.id, item.name) for item in lab_items]
    
    # Map form priorities to model enum values
    priority_map = {
        'low': 'routine',
        'medium': 'urgent', 
        'high': 'emergency',
        'critical': 'emergency'
    }
    form.priority.choices = [('low', 'Low'), ('medium', 'Medium'), 
                            ('high', 'High'), ('critical', 'Critical')]
    
    if request.method == 'POST':
        # Check if this is a bulk request FIRST
        bulk_items_data = request.form.get('bulk_items')
        
        if bulk_items_data:
            # Process bulk request (skip form validation for single request)
            print("Processing bulk request")  # Debug
            try:
                return process_bulk_request(bulk_items_data, current_user, priority_map)
            except Exception as e:
                db.session.rollback()
                print(f"Bulk request error: {str(e)}")  # Debug
                flash(f'Error creating bulk request: {str(e)}', 'danger')
        elif form.validate_on_submit():
            # Process single request (only if form validates)
            print("Processing single request")  # Debug
            try:
                return process_single_request(form, current_user, priority_map)
            except Exception as e:
                db.session.rollback()
                print(f"Single request error: {str(e)}")  # Debug
                flash(f'Error creating request: {str(e)}', 'danger')
        else:
            # Form validation failed for single request
            print(f"Form validation failed: {form.errors}")  # Debug
            flash('Please correct the form errors for single item request', 'danger')
    
    return render_template('lab-inventory/create_stock_request.html', 
                          form=form, 
                          lab_items=lab_items,
                          title="New Lab Stock Request")
    
def process_single_request(form, current_user, priority_map):
    """Process single stock request"""
    stock_item = Stock.query.get(form.item_id.data)
    if not stock_item:
        flash('Selected item not found', 'danger')
        return redirect(url_for('lab_web.create_stock_request'))
    
    model_priority = priority_map.get(form.priority.data, 'routine')
    
    new_request = StockRequest(
        stock_id=form.item_id.data,
        quantity_requested=form.quantity.data,
        priority=model_priority,
        approval_notes=form.reason.data,
        department='lab',
        requester_id=current_user.id,
        status='submitted',
        batch_number=stock_item.batch_number or 'N/A',
        expiration_date=stock_item.expiration_date or datetime.utcnow() + timedelta(days=365),
        location=stock_item.location or 'Main Lab Storage',
        is_bulk=False
    )
    
    db.session.add(new_request)
    db.session.commit()
    
    flash('Stock request created successfully!', 'success')
    return redirect(url_for('lab_web.request_stocks'))


def process_bulk_request(bulk_items_data, current_user, priority_map):
    """Process bulk stock request with same bulk code"""
    try:
        print(f"Raw bulk data: {bulk_items_data}")  # Debug
        
        bulk_items = json.loads(bulk_items_data)
        print(f"Parsed bulk items: {bulk_items}")  # Debug
        
        if not bulk_items:
            flash('No items in bulk request', 'danger')
            return redirect(url_for('lab_web.create_stock_request'))
        
        # Create bulk request record
        bulk_request = BulkRequest(
            requester_id=current_user.id,
            department='lab',
            total_items=len(bulk_items),
            total_quantity=sum(item['quantity'] for item in bulk_items),
            notes=request.form.get('notes', ''),
            status='submitted'
        )
        
        # Generate bulk code
        bulk_request.bulk_code = bulk_request.generate_bulk_code()
        print(f"Generated bulk code: {bulk_request.bulk_code}")  # Debug
        
        # Determine overall priority (highest priority in the batch)
        priority_order = {'urgent': 3, 'high': 2, 'medium': 1, 'low': 0}
        highest_priority_item = max(bulk_items, 
                                  key=lambda x: priority_order.get(x['priority'], 0))
        bulk_request.overall_priority = priority_map.get(highest_priority_item['priority'], 'routine')
        
        db.session.add(bulk_request)
        db.session.flush()  # Get the bulk_request ID without committing
        
        # Create individual stock requests
        successful_items = 0
        for item_data in bulk_items:
            stock_item = Stock.query.get(item_data['id'])
            if not stock_item:
                print(f"Item not found: {item_data['id']}")  # Debug
                flash(f"Item '{item_data.get('name', 'Unknown')}' not found", 'warning')
                continue
            
            model_priority = priority_map.get(item_data['priority'], 'routine')
            
            stock_request = StockRequest(
                stock_id=item_data['id'],
                quantity_requested=item_data['quantity'],
                priority=model_priority,
                approval_notes=item_data['reason'],
                department='lab',
                requester_id=current_user.id,
                status='submitted',
                batch_number=stock_item.batch_number or 'N/A',
                expiration_date=stock_item.expiration_date or datetime.utcnow() + timedelta(days=365),
                location=stock_item.location or 'Main Lab Storage',
                is_bulk=True,
                bulk_request_id=bulk_request.id
            )
            
            db.session.add(stock_request)
            successful_items += 1
        
        if successful_items == 0:
            db.session.rollback()
            flash('No valid items found in bulk request', 'danger')
            return redirect(url_for('lab_web.create_stock_request'))
        
        db.session.commit()
        
        flash(f'Bulk stock request created successfully! {successful_items} items added. Bulk Code: {bulk_request.bulk_code}', 'success')
        return redirect(url_for('lab_web.request_stocks'))
        
    except json.JSONDecodeError as e:
        db.session.rollback()
        print(f"JSON decode error: {str(e)}")  # Debug
        flash('Invalid bulk request data format', 'danger')
        return redirect(url_for('lab_web.create_stock_request'))
    except Exception as e:
        db.session.rollback()
        print(f"Unexpected error in bulk request: {str(e)}")  # Debug
        import traceback
        print(f"Traceback: {traceback.format_exc()}")  # Debug
        flash(f'Error creating bulk request: {str(e)}', 'danger')
        return redirect(url_for('lab_web.create_stock_request'))


@lab_web_bp.route('/inventory/request-new-item', methods=['GET', 'POST'])
@login_required
def request_new_item():
    """Page for requesting main store to purchase new items"""
    form = NewItemRequestForm()
    
    if form.validate_on_submit():
        try:
            # Create new item request
            new_item_request = ItemPurchaseRequest(
                item_name=form.item_name.data,
                category=form.category.data,
                manufacturer=form.manufacturer.data,
                specifications=form.specifications.data,
                quantity=form.quantity.data,
                units=form.units.data,
                estimated_price=form.estimated_price.data,
                required_date=form.required_date.data,
                priority=form.priority.data,
                reason=form.reason.data,
                alternatives=form.alternatives.data,
                urgency_reason=form.urgency_reason.data if form.urgency_reason.data else None,
                department='lab',
                requester_id=current_user.id,
                status='submitted'
            )
            
            db.session.add(new_item_request)
            db.session.commit()
            
            flash('New item request submitted successfully!', 'success')
            return redirect(url_for('lab_web.request_stocks'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting request: {str(e)}', 'danger')
    
    return render_template('lab-inventory/request_new_item.html', 
                         form=form,
                         title="Request New Item")


# View Stock Request Detail
@lab_web_bp.route('/inventory/request-stocks/<string:request_id>', methods=['GET'])
@login_required
def view_stock_request(request_id):
    """View details of a specific stock request"""
    try:
        # Get request with related stock and requester information
        stock_request = StockRequest.query.options(
            joinedload(StockRequest.stock),
            joinedload(StockRequest.requester)
        ).filter_by(id=request_id, department='lab').first_or_404()
        
        return render_template(
            'lab-inventory/view_stock_request.html', 
            request=stock_request,
            title="Stock Request Details"
        )
    
    except Exception as e:
        flash(f'Error loading stock request: {str(e)}', 'danger')
        return redirect(url_for('lab_web.request_stocks'))

# Edit Stock Request
@lab_web_bp.route('/inventory/request-stocks/<string:request_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_stock_request(request_id):
    """Edit an existing stock request"""
    try:
        # Get the request to edit
        stock_request = StockRequest.query.filter_by(
            id=request_id, 
            department='lab',
            status='pending'  # Only allow editing pending requests
        ).first_or_404()
        
        # Get lab inventory items
        lab_items = Stock.query.filter_by(is_active=True).all()
        
        form = LabStockRequestForm()
        form.item_id.choices = [(item.id, item.name) for item in lab_items]
        
        # Priority mapping for form
        priority_map = {
            'routine': 'low',
            'urgent': 'medium',
            'emergency': 'high'
        }
        reverse_priority_map = {v: k for k, v in priority_map.items()}
        
        if request.method == 'GET':
            # Populate form with existing data
            form.item_id.data = stock_request.stock_id
            form.quantity.data = stock_request.quantity_requested
            form.priority.data = priority_map.get(stock_request.priority, 'low')
            form.reason.data = stock_request.approval_notes
        
        if form.validate_on_submit():
            # Get the selected stock item
            stock_item = Stock.query.get(form.item_id.data)
            if not stock_item:
                flash('Selected item not found', 'danger')
                return redirect(url_for('lab_web.edit_stock_request', request_id=request_id))
            
            # Map form priority to model priority
            model_priority = reverse_priority_map.get(form.priority.data, 'routine')
            
            # Update request
            stock_request.stock_id = form.item_id.data
            stock_request.quantity_requested = form.quantity.data
            stock_request.priority = model_priority
            stock_request.approval_notes = form.reason.data
            stock_request.batch_number = stock_item.batch_number or 'N/A'
            stock_request.expiration_date = stock_item.expiration_date or datetime.utcnow() + timedelta(days=365)
            stock_request.location = stock_item.location or 'Main Lab Storage'
            
            db.session.commit()
            
            flash('Stock request updated successfully!', 'success')
            return redirect(url_for('lab_web.view_stock_request', request_id=request_id))
        
        return render_template(
            'lab-inventory/edit_stock_request.html', 
            form=form, 
            request=stock_request,
            lab_items=lab_items,
            title="Edit Stock Request"
        )
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error editing request: {str(e)}', 'danger')
        return redirect(url_for('lab_web.request_stocks'))

# Cancel Stock Request (via POST)
@lab_web_bp.route('/inventory/request-stocks/<string:request_id>/cancel', methods=['POST'])
@login_required
def cancel_stock_request(request_id):
    """Cancel a pending stock request"""
    try:
        # Find the request
        stock_request = StockRequest.query.filter_by(
            id=request_id, 
            department='lab',
            status='pending'  # Only allow canceling pending requests
        ).first_or_404()
        
        # Update status to cancelled
        stock_request.status = 'cancelled'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Request cancelled successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error cancelling request: {str(e)}'}), 500


@lab_web_bp.route('/lab/inventory/stock-flow')
@login_required
def stock_flow():
    """View stock movement history"""
    # Implementation would go here
    return render_template('lab/stock_flow.html', title="Stock Flow")


# ------------------ LOINC FHIR Integration ------------------
LOINC_BASE = "https://fhir.loinc.org"

from requests.exceptions import ReadTimeout, HTTPError
import re


def loinc_auth():
    """Return HTTP Basic Auth tuple for LOINC server."""
    auth_tuple = (
        current_app.config['LOINC_USERNAME'],
        current_app.config['LOINC_PASSWORD']
    )
    if current_app.debug:
        print(f"[DEBUG] Using LOINC username: {auth_tuple[0]}")  # avoid printing password
    return auth_tuple


def loinc_expand(filter_text=None, count=50, offset=0):
    """Fetch LOINC codes via ValueSet/$expand, optionally filtered."""
    params = {
        'url': 'http://loinc.org/vs/loinc-all',
        'count': count,
        'offset': offset
    }
    if filter_text:
        params['filter'] = filter_text
    if current_app.debug:
        print(f"[DEBUG] Sending expand request with params: {params}")

    try:
        resp = requests.get(
            f"{LOINC_BASE}/ValueSet/$expand",
            params=params,
            auth=loinc_auth(),
            timeout=20  # increased timeout
        )
        if current_app.debug:
            print(f"[DEBUG] Expand Status: {resp.status_code}")
        resp.raise_for_status()
        return resp.json()

    except ReadTimeout as e:
        current_app.logger.error(f"LOINC expand timed out: {e}")
        raise


def loinc_lookup(code):
    """Lookup a specific LOINC code using CodeSystem/$lookup."""
    params = {'system': 'http://loinc.org', 'code': code}
    if current_app.debug:
        print(f"[DEBUG] Looking up LOINC code: {code}")

    try:
        resp = requests.get(
            f"{LOINC_BASE}/CodeSystem/$lookup",
            params=params,
            auth=loinc_auth(),
            timeout=20
        )
        if current_app.debug:
            print(f"[DEBUG] Lookup Status: {resp.status_code}")
        resp.raise_for_status()
        return resp.json()

    except ReadTimeout as e:
        current_app.logger.error(f"LOINC lookup timed out: {e}")
        raise


@lab_web_bp.route('/loinc-tests', methods=['GET'])
@login_required
def get_loinc_tests():
    """Search/fetch LOINC lab test codes via filter or get first batch."""
    q = request.args.get('q', '').strip() or None
    if current_app.debug:
        print(f"[DEBUG] Received q={q}")
    try:
        expand = loinc_expand(filter_text=q)
        entries = expand.get('expansion', {}).get('contains', [])
        tests = [{'loinc_code': e.get('code'), 'display': e.get('display')} for e in entries]
        return jsonify({'results': tests}), 200

    except ReadTimeout:
        return jsonify({'error': 'LOINC service timed out'}), 504
    except HTTPError as ex:
        current_app.logger.error(f"LOINC expand failed: {ex}")
        return jsonify({'error': 'Failed to fetch LOINC codes'}), 502


@lab_web_bp.route('/loinc-test/<string:code>', methods=['GET'])
@login_required
def get_loinc_test_detail(code):
    """Retrieve detailed metadata for specific LOINC code."""
    if current_app.debug:
        print(f"[DEBUG] Detail request for code={code}")
    # Accept alphanumeric codes with dash
    if not re.match(r'^[A-Za-z0-9]+-\d+$', code):
        return jsonify({'error': 'Invalid LOINC code format'}), 400

    try:
        result = loinc_lookup(code)
        params = result.get('parameter', [])
        metadata = {p.get('name'): (p.get('valueString') or p.get('valueCode') or p.get('valueDecimal')) for p in params if p.get('name')}
        return jsonify({'loinc_code': code, 'metadata': metadata}), 200

    except ReadTimeout:
        return jsonify({'error': 'LOINC lookup timed out'}), 504
    except HTTPError as ex:
        current_app.logger.error(f"LOINC lookup failed: {ex}")
        return jsonify({'error': 'LOINC code not found'}), 404