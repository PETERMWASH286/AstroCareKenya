# app/pharmacy/routes.py
from datetime import datetime, timedelta
from flask import current_app, flash, json, make_response, redirect, render_template, url_for
from flask import render_template, request, jsonify
from flask_login import current_user, login_required
from sqlalchemy import and_, exists, func, or_
from app import db
from app.auth.models import User
from app.pharmacy.models import PharmacyInventory, PharmacyStockFlow
from app.store.models import Stock, StockFlow, StockRequest  # Import the db object
from . import pharmacy_web_bp
from app.patients.models import Consultation, Patient, Service, Visit, Medication


@pharmacy_web_bp.route('/pharmacy')
def pharmacy_dashboard():
    """Main pharmacy dashboard route"""
    return render_template('dashboard.html')



@pharmacy_web_bp.route('/pharmacy/dispense')
def dispense_medication():
    """
    Show only visits that have paid, not-yet-dispensed medications.
    Handles medications linked via both consultation and direct visit relationships.
    """
    from sqlalchemy import or_
    
    # Get visits that have undispensed medications through either:
    # 1. Consultation → Medication path, OR
    # 2. Direct Visit → Medication path
    pharmacy_queue = (
        db.session.query(Visit)
        .filter(
            Visit.visit_status == 'in_progress',
            or_(
                # Medications linked via consultation
                exists().where(
                    and_(
                        Consultation.visit_id == Visit.id,
                        Medication.consultation_id == Consultation.id,
                        Medication.is_paid == True,
                        Medication.payment_status == 'paid',
                        Medication.is_dispensed == False
                    )
                ),
                # Medications linked directly to visit
                exists().where(
                    and_(
                        Medication.visit_id == Visit.id,
                        Medication.is_paid == True,
                        Medication.payment_status == 'paid',
                        Medication.is_dispensed == False
                    )
                )
            )
        )
        .order_by(Visit.visit_date.asc())
        .all()
    )

    return render_template('dispense_medication.html', pharmacy_queue=pharmacy_queue, now=datetime.utcnow())




@pharmacy_web_bp.route('/dispense/<int:medication_id>', methods=['POST'])
def dispense_single_medication(medication_id):
    medication = Medication.query.get_or_404(medication_id)

    # Prevent double dispensing
    if medication.is_dispensed:
        return jsonify({
            "success": False,
            "message": "Medication already dispensed"
        }), 400

    quantity_needed = medication.quantity or 1
    service = medication.service
    if not service:
        return jsonify({
            "success": False,
            "message": "Medication has no linked service"
        }), 400

    # Fetch available inventory for this service, ordered by expiry (FIFO)
    inventory_items = PharmacyInventory.query.filter_by(
        service_id=service.id
    ).filter(
        PharmacyInventory.quantity > 0
    ).order_by(PharmacyInventory.expiry_date.asc()).all()

    if not inventory_items:
        return jsonify({
            "success": False,
            "message": f"No stock available for {service.name}"
        }), 400

    total_available = sum(item.quantity for item in inventory_items)
    if total_available < quantity_needed:
        return jsonify({
            "success": False,
            "message": f"Insufficient stock. Available: {total_available}, Required: {quantity_needed}"
        }), 400

    # Deduct from inventory (FIFO)
    remaining = quantity_needed
    deductions = []  # to track which batches and how much
    for item in inventory_items:
        if remaining <= 0:
            break
        deduct = min(item.quantity, remaining)
        item.quantity -= deduct
        remaining -= deduct
        deductions.append({
            'item': item,
            'deducted': deduct
        })

    # Update Service quantity_in_stock (denormalised total)
    if service.quantity_in_stock is not None:
        service.quantity_in_stock -= quantity_needed

    # Create stock flow records
    for ded in deductions:
        flow = PharmacyStockFlow(
            pharmacy_inventory_id=ded['item'].id,
            medication_id=medication.id,
            quantity_change=-ded['deducted'],
            flow_type='dispense',
            notes=f"Dispensed for patient via prescription #{medication.id}",
            created_by=current_user.id
        )
        db.session.add(flow)

    # Mark medication as dispensed
    medication.is_dispensed = True
    medication.dispensed_at = datetime.utcnow()
    medication.dispensed_by = current_user.id  # assuming the column exists

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Medication dispensed successfully"
    })


@pharmacy_web_bp.route('/dispense-bulk', methods=['POST'])
@login_required
def dispense_bulk():
    data = request.get_json()
    medication_ids = data.get('medication_ids', [])
    if not medication_ids:
        return jsonify({'success': False, 'message': 'No medication IDs provided'}), 400

    results = {'success': [], 'failed': []}
    for med_id in medication_ids:
        try:
            # Use a savepoint to isolate this medication's transaction
            with db.session.begin_nested():
                medication = Medication.query.get(med_id)
                if not medication:
                    results['failed'].append({'id': med_id, 'reason': 'Medication not found'})
                    continue

                if medication.is_dispensed:
                    results['failed'].append({'id': med_id, 'reason': 'Already dispensed'})
                    continue

                quantity_needed = medication.quantity or 1
                service = medication.service
                if not service:
                    results['failed'].append({'id': med_id, 'reason': 'No linked service'})
                    continue

                # Get available inventory for this service, FIFO by expiry
                inventory_items = PharmacyInventory.query.filter_by(
                    service_id=service.id
                ).filter(
                    PharmacyInventory.quantity > 0
                ).order_by(PharmacyInventory.expiry_date.asc()).all()

                if not inventory_items:
                    results['failed'].append({'id': med_id, 'reason': f'No stock available for {service.name}'})
                    continue

                total_available = sum(item.quantity for item in inventory_items)
                if total_available < quantity_needed:
                    results['failed'].append({
                        'id': med_id,
                        'reason': f'Insufficient stock. Available: {total_available}, Required: {quantity_needed}'
                    })
                    continue

                # Deduct from inventory (FIFO)
                remaining = quantity_needed
                deductions = []
                for item in inventory_items:
                    if remaining <= 0:
                        break
                    deduct = min(item.quantity, remaining)
                    item.quantity -= deduct
                    remaining -= deduct
                    deductions.append({
                        'item': item,
                        'deducted': deduct
                    })

                # Update service quantity_in_stock (denormalised total)
                if service.quantity_in_stock is not None:
                    service.quantity_in_stock -= quantity_needed

                # Create stock flow records for each batch
                # Create pharmacy stock flow records
                for ded in deductions:
                    flow = PharmacyStockFlow(
                        pharmacy_inventory_id=ded['item'].id,
                        medication_id=medication.id,
                        quantity_change=-ded['deducted'],
                        flow_type='dispense',
                        notes=f"Dispensed for patient via prescription #{medication.id}",
                        created_by=current_user.id
                    )
                    db.session.add(flow)

                # Mark medication as dispensed
                medication.is_dispensed = True
                medication.dispensed_at = datetime.utcnow()
                medication.dispensed_by = current_user.id

            # If we reach here, the savepoint was committed
            results['success'].append(med_id)

        except Exception as e:
            db.session.rollback()  # rollback the current savepoint
            results['failed'].append({'id': med_id, 'reason': str(e)})

    # Commit the outer transaction (the savepoints are already committed, but this finalises everything)
    try:
        db.session.commit()
    except Exception as e:
        # This should rarely happen if each inner transaction succeeded
        return jsonify({'success': False, 'message': f'Database commit error: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'results': results,
        'message': f"Dispensed {len(results['success'])} medications, {len(results['failed'])} failed."
    })



@pharmacy_web_bp.route('/inventory')
def manage_inventory():
    from datetime import date, timedelta
    inventory = PharmacyInventory.query.order_by(PharmacyInventory.item_name).all()
    today = date.today()

    total_medications = len(inventory)
    low_stock_items = sum(1 for i in inventory if i.is_low_stock)
    expired_items = sum(1 for i in inventory if i.is_expired)
    expiring_soon_items = sum(1 for i in inventory if i.is_expiring_soon)
    pending_requests = StockRequest.query.filter_by(department='Pharmacy', status='pending').count()
    total_value = sum(i.total_value for i in inventory)

    return render_template('inventory_management.html',
                           inventory=inventory,
                           total_medications=total_medications,
                           low_stock_items=low_stock_items,
                           expired_items=expired_items,
                           expiring_soon_items=expiring_soon_items,
                           pending_requests=pending_requests,
                           total_value=total_value,
                           today=today)
    
    
    
    


@pharmacy_web_bp.route('/prescriptions-tracking')
@login_required
def track_prescriptions():
    # Get filter parameters
    doctor_id = request.args.get('doctor_id', type=int)
    patient_query = request.args.get('patient', '').strip()
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    payment_status = request.args.get('payment_status')
    dispense_status = request.args.get('dispense_status')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Base query – medications are linked either to a consultation (and thus a visit) or directly to a visit
    query = Medication.query.join(Service, Medication.service_id == Service.id).filter(Service.category == 'Pharmacy')

    # Join to Patient via two possible paths: via consultation -> visit -> patient, or direct visit -> patient
    # We'll use outer joins to handle both cases, then filter where either path exists
    query = query.outerjoin(Consultation, Medication.consultation_id == Consultation.id) \
                 .outerjoin(Visit, or_(Consultation.visit_id == Visit.id, Medication.visit_id == Visit.id)) \
                 .join(Patient, Visit.patient_id == Patient.id)

    # Also join for doctor (via consultation)
    query = query.outerjoin(User, Consultation.treated_by_id == User.id)

    # Apply filters
    if doctor_id:
        query = query.filter(Consultation.treated_by_id == doctor_id)
    if patient_query:
        query = query.filter(or_(
            Patient.first_name.ilike(f'%{patient_query}%'),
            Patient.last_name.ilike(f'%{patient_query}%'),
            Patient.reg_no.ilike(f'%{patient_query}%')
        ))
    if date_from:
        query = query.filter(Medication.prescribed_at >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        query = query.filter(Medication.prescribed_at <= datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    if payment_status:
        if payment_status == 'paid':
            query = query.filter(Medication.is_paid == True)
        elif payment_status == 'unpaid':
            query = query.filter(Medication.is_paid == False)
    if dispense_status:
        if dispense_status == 'dispensed':
            query = query.filter(Medication.is_dispensed == True)
        elif dispense_status == 'not_dispensed':
            query = query.filter(Medication.is_dispensed == False)

    # Order by most recent first
    query = query.order_by(Medication.prescribed_at.desc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    medications = pagination.items

    # For filter dropdowns, get all doctors who have prescribed medications
    doctors = db.session.query(User).join(Consultation, Consultation.treated_by_id == User.id) \
                     .join(Medication, Medication.consultation_id == Consultation.id) \
                     .distinct().all()

    return render_template(
        'prescription_tracking.html',
        medications=medications,
        pagination=pagination,
        doctors=doctors,
        filters=request.args
    )

@pharmacy_web_bp.route('/api/prescription/<int:medication_id>')
def get_prescription_details(medication_id):
    med = Medication.query.get_or_404(medication_id)
    # Get patient via consultation or visit
    patient = None
    doctor = None
    if med.consultation:
        patient = med.consultation.patient
        doctor = med.consultation.treated_by
    elif med.visit:
        patient = med.visit.patient
    else:
        patient = None

    return jsonify({
        'success': True,
        'prescription': {
            'id': med.id,
            'medication_name': med.service.name if med.service else 'Unknown',
            'strength': med.service.strength if med.service else None,
            'dose': med.dose,
            'frequency': med.frequency,
            'duration': med.duration,
            'quantity': med.quantity,
            'price': med.price,
            'is_paid': med.is_paid,
            'is_dispensed': med.is_dispensed,
            'prescribed_date': med.prescribed_at.strftime('%d %b %Y'),
            'prescribed_time': med.prescribed_at.strftime('%I:%M %p'),
            'dispensed_at': med.dispensed_at.strftime('%d %b %Y %I:%M %p') if med.dispensed_at else None,
            'dispenser': med.dispenser.full_name if med.dispenser else None,
            'doctor': doctor.full_name if doctor else None,
            'patient_name': patient.full_name if patient else 'Unknown',
            'patient_reg': patient.reg_no if patient else 'N/A',
            'notes': getattr(med, 'notes', '')
        }
    })

@pharmacy_web_bp.route('/pharmacy/inventory/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_inventory(item_id):
    item = Service.query.get_or_404(item_id)

    if request.method == 'POST':
        try:
            # Update core fields
            item.name = request.form['name']
            item.description = request.form['description']
            item.strength = request.form['strength']
            item.dosage_form = request.form['dosage_form']
            item.ndc = request.form['ndc']
            
            # Inventory fields
            item.quantity_in_stock = int(request.form['quantity_in_stock'] or 0)
            item.min_stock_level = int(request.form['min_stock_level'] or 0)
            item.reorder_quantity = int(request.form['reorder_quantity'] or 0)
            item.quantity_per_unit = int(request.form['quantity_per_unit'] or 0)
            
            # Additional fields
            item.expiration_date = request.form.get('expiration_date') or None
            item.lot_number = request.form['lot_number']
            item.storage_conditions = request.form['storage_conditions']
            item.requires_prescription = 'requires_prescription' in request.form

            db.session.commit()
            flash('Medication updated successfully', 'success')
            return redirect(url_for('pharmacy_web.manage_inventory'))
        
        except ValueError as e:
            db.session.rollback()
            flash('Error updating medication: Invalid input values', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating medication: {str(e)}', 'error')

    return render_template('edit_inventory.html', item=item)



@pharmacy_web_bp.route('/pharmacy/stock-requests')
def stock_requests():
    """Stock request management route"""
    requests = StockRequest.query.filter_by(department='Pharmacy').order_by(StockRequest.created_at.desc()).all()
    
    status_counts = {
        'pending': StockRequest.query.filter_by(status='pending', department='Pharmacy').count(),
        'approved': StockRequest.query.filter_by(status='approved', department='Pharmacy').count(),
        'fulfilled': StockRequest.query.filter_by(status='fulfilled', department='Pharmacy').count()
    }
    
    return render_template(
        'stock_requests.html',
        requests=requests,
        status_counts=status_counts,
        current_status=request.args.get('status', 'all')
    )






@pharmacy_web_bp.route('/pharmacy/stock-requests/create', methods=['GET', 'POST'])
def create_stock_request():
    """Create new stock request"""
    if request.method == 'POST':
        try:
            # Get form data with proper validation
            stock_item = Stock.query.get_or_404(request.form.get('stock_id'))
            
            new_request = StockRequest(
                stock_id=stock_item.id,
                quantity_requested=int(request.form['quantity_requested']),
                department='Pharmacy',
                requester_id=current_user.id,
                status='submitted',
                batch_number=request.form['batch_number'],
                expiration_date=datetime.strptime(request.form['expiration_date'], '%Y-%m-%d'),
                location=request.form['location'],
                priority=request.form.get('priority', 'routine'),
                required_by_date=datetime.strptime(request.form['required_by_date'], '%Y-%m-%d') if request.form.get('required_by_date') else None
            )

            db.session.add(new_request)
            db.session.commit()
            flash('Stock request created successfully', 'success')
            return redirect(url_for('pharmacy_web.stock_requests'))
            
        except ValueError as e:
            db.session.rollback()
            flash(f'Invalid input values: {str(e)}', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating stock request: {str(e)}', 'error')
    
    stock_items = Stock.query.filter_by(is_active=True).all()
    return render_template('create_stock_request.html', stock_items=stock_items)

@pharmacy_web_bp.route('/pharmacy/stock-requests/<int:request_id>/approve', methods=['POST'])
def approve_stock_request(request_id):
    """Approve a stock request"""
    stock_request = StockRequest.query.get_or_404(request_id)
    try:
        stock_request.status = 'approved'
        stock_request.approver_id = current_user.id
        stock_request.approval_date = datetime.utcnow()
        stock_request.quantity_approved = stock_request.quantity_requested
        db.session.commit()
        flash('Request approved successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving request: {str(e)}', 'error')
    return redirect(url_for('pharmacy_web.stock_requests'))

@pharmacy_web_bp.route('/pharmacy/stock-requests/<int:request_id>/fulfill', methods=['POST'])
def fulfill_stock_request(request_id):
    """Fulfill a stock request"""
    stock_request = StockRequest.query.get_or_404(request_id)
    try:
        stock_request.status = 'fulfilled'
        stock_request.issued_by = current_user.id
        stock_request.issue_date = datetime.utcnow()
        stock_request.quantity_issued = stock_request.quantity_approved
        stock_request.update_stock_levels()
        flash('Request fulfilled successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error fulfilling request: {str(e)}', 'error')
    return redirect(url_for('pharmacy_web.stock_requests'))

# Then update the route to handle existing quantity
@pharmacy_web_bp.route('/stock-requests/<uuid:request_id>/edit', methods=['GET', 'POST'])
def edit_stock_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    # Validate request is editable - match the enum value
    if stock_request.status not in ['draft', 'submitted']:  # Allow both draft and submitted
        flash('Only draft or submitted requests can be edited', 'error')
        return redirect(url_for('pharmacy_web.stock_requests'))

    if request.method == 'POST':
        try:
            original_quantity = stock_request.quantity_requested
            new_quantity = int(request.form['quantity_requested'])
            
            # Only validate stock if quantity increases
            if new_quantity > original_quantity:
                if not stock_request.validate_stock_availability():
                    available = stock_request.stock.current_stock - sum(
                        req.quantity_requested 
                        for req in stock_request.stock.requests 
                        if req.status in ['submitted', 'approved'] and req.id != stock_request.id
                    )
                    flash(f'Requested quantity exceeds available stock. Maximum available: {available}', 'error')
                    return redirect(url_for('pharmacy_web.edit_stock_request', request_id=request_id))

            # Proceed with updates...
            stock_request.quantity_requested = new_quantity
            # Rest of your update logic...

            db.session.commit()
            flash('Stock request updated successfully', 'success')
            return redirect(url_for('pharmacy_web.stock_requests'))

        except ValueError as e:
            db.session.rollback()
            current_app.logger.error(f"Validation error: {str(e)}")
            flash(f'Invalid input values: {str(e)}', 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating request {request_id}: {str(e)}")
            flash('Error updating stock request', 'error')
    # GET request - pre-fill form with existing data
    stock_items = Stock.query.filter_by(is_active=True).all()
    return render_template(
        'edit_stock_request.html',
        request=stock_request,
        stock_items=stock_items,
        min_date=datetime.utcnow().date().isoformat()
    )


@pharmacy_web_bp.route('/stock-requests/<uuid:request_id>/cancel', methods=['POST'])
def cancel_stock_request(request_id):
    """Cancel a stock request"""
    try:
        stock_request = StockRequest.query.get_or_404(request_id)
        
        # Validate request can be cancelled
        if stock_request.status not in ['draft', 'submitted']:
            flash('Only draft or submitted requests can be cancelled', 'error')
            return redirect(url_for('pharmacy_web.stock_requests'))
            
        # Update request status
        stock_request.status = 'cancelled'
        stock_request.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash('Request cancelled successfully', 'success')
        return redirect(url_for('pharmacy_web.stock_requests'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error cancelling request {request_id}: {str(e)}")
        flash('Error cancelling request', 'error')
        return redirect(url_for('pharmacy_web.stock_requests'))




from sqlalchemy import func
from collections import Counter

@pharmacy_web_bp.route('/dispense/history')
def dispense_history():
    if not current_user.has_privilege('pharmacy:dispense_history'):
        flash("You do not have permission to view dispense history.", "danger")
        return redirect(url_for('pharmacy_web.dispense_medication'))

    # Base query
    base_query = (
        db.session.query(
            Medication.id.label('medication_id'),
            Medication.dispensed_at.label('dispense_date'),
            Medication.quantity.label('quantity'),
            func.coalesce(User.full_name, 'Unknown').label('dispensed_by'),
            Service.name.label('medication_name'),
            func.concat(Patient.first_name, ' ', Patient.last_name).label('patient_name'),
            Patient.reg_no.label('patient_reg_no')
        )
        .outerjoin(User, Medication.dispensed_by == User.id)
        .join(Consultation, Medication.consultation_id == Consultation.id)
        .join(Visit, Consultation.visit_id == Visit.id)
        .join(Patient, Visit.patient_id == Patient.id)
        .join(Service, Medication.service_id == Service.id)
        .filter(Medication.is_dispensed == True)
        .order_by(Medication.dispensed_at.desc())
    )

    history_records = base_query.all()

    # --- Additional summary stats ---
    total_quantity = sum(rec.quantity or 0 for rec in history_records)
    unique_patients = len({rec.patient_reg_no for rec in history_records})

    # Top medications (for chart)
    med_counter = Counter()
    for rec in history_records:
        med_counter[rec.medication_name] += rec.quantity or 0
    top_meds = med_counter.most_common(5)  # list of (name, total_qty)

    # Unique medications list for dropdown (same as before)
    med_set = {(rec.medication_id, rec.medication_name) for rec in history_records}
    med_list = sorted(med_set, key=lambda x: x[1])

    return render_template(
        'dispense_history.html',
        history_records=history_records,
        medication_list=med_list,
        total_quantity=total_quantity,
        unique_patients=unique_patients,
        top_meds=top_meds
    )



@pharmacy_web_bp.route('/pharmacy/prescription/<int:visit_id>')
def view_prescription(visit_id):
    visit = Visit.query.get_or_404(visit_id)
    
    # Get all medications for this visit (directly linked via visit_id)
    medications = []
    for med in visit.medications:
        line_total = (med.price or 0) * (med.quantity or 1)
        medications.append({
            'id': med.id,
            'service_name': med.service.name if med.service else 'Unknown Medication',
            'service': med.service,
            'dose': med.dose,
            'frequency': med.frequency,
            'duration': med.duration,
            'quantity': med.quantity,
            'unit_price': med.price,
            'line_total': line_total,
            'is_dispensed': med.is_dispensed,
            'is_paid': med.is_paid,
            'payment_status': med.payment_status,
            'dispensed_at': med.dispensed_at,
            'dispensed_by': med.dispenser.full_name if med.dispenser else None,
            'notes': getattr(med, 'notes', ''),
        })
    
    # Get consultation details with doctor name
    consultation_details = None
    if visit.consultations:
        latest_consultation = visit.consultations[-1]
        consultation_details = {
            'history': latest_consultation.history,
            'examination': latest_consultation.examination,
            'diagnosis': latest_consultation.diagnosis,
            'treatment_plan': latest_consultation.treatment_plan,
            'notes': latest_consultation.notes,
            'doctor': latest_consultation.treated_by.full_name if latest_consultation.treated_by else None,
            'created_at': latest_consultation.created_at
        }
    
    # Get vitals details, including allergies and chronic conditions
    vitals_details = None
    tb_screening = None
    if visit.vitals:
        latest_vitals = visit.vitals[-1]
        vitals_details = {
            'temperature': latest_vitals.temperature,
            'heart_rate': latest_vitals.heart_rate,
            'bp_systolic': latest_vitals.bp_systolic,
            'bp_diastolic': latest_vitals.bp_diastolic,
            'spo2': latest_vitals.spo2,
            'resp_rate': latest_vitals.resp_rate,
            'weight': latest_vitals.weight,
            'height': latest_vitals.height,
            'bmi': latest_vitals.bmi,
            'recorded_at': latest_vitals.recorded_at,
            'allergy_food': latest_vitals.allergy_food,
            'allergy_drugs': latest_vitals.allergy_drugs,
            'chronic_conditions': latest_vitals.chronic_conditions,
            'current_medications': latest_vitals.current_medications,
            'notes': latest_vitals.notes
        }
        # Get TB screening associated with this vitals
        if latest_vitals.tb_screening:
            tb = latest_vitals.tb_screening
            tb_screening = {
                'cough_duration': tb.cough_duration,
                'fever': tb.fever,
                'fever_duration': tb.fever_duration,
                'night_sweats': tb.night_sweats,
                'weight_loss_flag': tb.weight_loss_flag,
                'weight_loss_amount': tb.weight_loss_amount,
                'hemoptysis': tb.hemoptysis,
                'hiv_status': tb.hiv_status,
                'diabetes': tb.diabetes,
                'prior_tb': tb.prior_tb,
                'prior_tb_year': tb.prior_tb_year,
                'household_contact': tb.household_contact,
                'smoking_history': tb.smoking_history,
                'alcohol_use': tb.alcohol_use,
            }
    
    # Calculate stats
    total_medications = len(medications)
    dispensed_count = sum(1 for med in medications if med['is_dispensed'])
    pending_count = total_medications - dispensed_count
    total_price = sum(med['line_total'] for med in medications)

    return render_template('prescription_view.html',
                         visit=visit,
                         patient=visit.patient,
                         medications=medications,
                         consultation_details=consultation_details,
                         vitals_details=vitals_details,
                         tb_screening=tb_screening,
                         total_medications=total_medications,
                         dispensed_count=dispensed_count,
                         pending_count=pending_count,
                         total_price=total_price)