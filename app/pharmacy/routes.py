# app/pharmacy/routes.py
from datetime import datetime
from flask import current_app, flash, json, make_response, redirect, render_template, url_for
from flask import render_template, request, jsonify
from flask_login import current_user
from sqlalchemy import func
from app import db
from app.auth.models import User
from app.store.models import Stock, StockRequest  # Import the db object
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
    """
    # 1) Find all Visit → Consultation → Medication where:
    #    - visit_status is 'in_progress'
    #    - medication.is_paid == True and payment_status == 'paid'
    #    - medication.is_dispensed == False
    #
    # We join Visit → Consultation → Medication and filter out any already-dispensed meds.
    # Then .distinct() ensures each Visit appears only once in the list.
    pharmacy_queue = (
        db.session.query(Visit)
        .join(Visit.consultation)
        .join(Consultation.medications)
        .filter(
            Visit.visit_status == 'in_progress',
            Medication.is_paid == True,
            Medication.payment_status == 'paid',
            Medication.is_dispensed == False
        )
        .order_by(Visit.visit_date.asc())
        .distinct()
        .all()
    )

    return render_template('dispense_medication.html', pharmacy_queue=pharmacy_queue)


@pharmacy_web_bp.route('/dispense/<int:medication_id>', methods=['POST'])
def dispense_single_medication(medication_id):
    medication = Medication.query.get_or_404(medication_id)
    medication.is_dispensed = True
    medication.dispensed_at = datetime.utcnow()
    db.session.commit()

    updated_visit = medication.consultation.visit
    return jsonify({
        "success": True,
        "message": "Medication dispensed successfully"
    })



@pharmacy_web_bp.route('/pharmacy/inventory')
def manage_inventory():
    """Inventory management route: fetch real-time data and stats."""
    # 1. Fetch all pharmacy products
    inventory = (
        Service.query
        .filter(Service.category == 'Pharmacy')            # only pharmacy items
        .order_by(Service.name.asc())
        .all()
    )

    # 2. Compute summary stats
    total_medications   = len(inventory)
    low_stock_items     = sum(1 for item in inventory if item.low_stock)
    # pending_requests: if you have a StockRequest model, uncomment:
    # pending_requests = StockRequest.query.filter_by(status='pending').count()
    pending_requests    = 0

    # 3. Render template with real data
    return render_template(
        'inventory_management.html',
        inventory=inventory,
        total_medications=total_medications,
        low_stock_items=low_stock_items,
        pending_requests=pending_requests
    )

@pharmacy_web_bp.route('/pharmacy/prescriptions')
def track_prescriptions():
    """Prescription tracking route"""
    return render_template('prescription_tracking.html')




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


@pharmacy_web_bp.route('/pharmacy/inventory')
def manage_inventory_stock():
    """Inventory management route"""
    inventory = (
        Service.query
        .filter(Service.category == 'Pharmacy')
        .order_by(Service.name.asc())
        .all()
    )

    # Get real pending requests
    pending_requests = StockRequest.query.filter_by(
        department='Pharmacy',
        status='pending'
    ).count()

    return render_template(
        'inventory_management.html',
        inventory=inventory,
        total_medications=len(inventory),
        low_stock_items=sum(1 for item in inventory if item.low_stock),
        pending_requests=pending_requests
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





@pharmacy_web_bp.route('/pharmacy/dispense/history')
def dispense_history():
    """
    Display all previously‐dispensed medications, including those where dispensed_by is NULL.
    Only users with 'pharmacy:dispense_history' privilege can view this page.
    """
    if not current_user.has_privilege('pharmacy:dispense_history'):
        flash("You do not have permission to view dispense history.", "danger")
        return redirect(url_for('pharmacy_web.dispense_medication'))

    history_records = (
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
        .all()
    )

    # Build a **sorted list of unique (medication_id, medication_name)**:
    med_set = { (rec.medication_id, rec.medication_name) for rec in history_records }
    med_list = sorted(med_set, key=lambda x: x[1])  # sort by name

    return render_template(
        'dispense_history.html',
        history_records=history_records,
        medication_list=med_list
    )



