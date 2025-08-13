# app/billing/routes.py

from datetime import datetime
from flask import flash, jsonify, redirect, render_template, request, url_for

from app.finance.models import Insurance, InsuranceService, Invoice, InvoiceItem
from app.super_admin.models import HospitalProfile
from . import billing_web_bp
from app.patients.models import Consultation, LabTest, Medication, Patient, Radiology, Transaction, Service, Visit, db

@billing_web_bp.route('/create-invoice')
def create_invoice():
    return render_template('create_invoice.html')

@billing_web_bp.route('/payment-processing')
def payment_processing():
    return render_template('payment_processing.html')

@billing_web_bp.route('/api/patients-with-unpaid-services', methods=['GET'])
def patients_with_unpaid_services():
    patients = Patient.query.all()
    result = []

    for patient in patients:
        unpaid_items = []

        # Check unpaid lab tests
        lab_tests = LabTest.query \
            .join(Consultation, LabTest.consultation_id == Consultation.id) \
            .join(Visit, Consultation.visit_id == Visit.id) \
            .filter(Visit.patient_id == patient.id) \
            .filter(db.or_(LabTest.is_paid == False, LabTest.payment_status != 'paid')) \
            .all()
        for lt in lab_tests:
            service = Service.query.get(lt.service_id)
            if service:
                unpaid_items.append({
                    'id': lt.id, # Add ID for better tracking in frontend if needed
                    'name': service.name,
                    'type': service.category,
                    'date': lt.requested_at.strftime('%Y-%m-%d'),
                    'amount': service.price,
                    'source': 'lab_test',
                    'status': lt.payment_status # Show payment status directly
                })

        # Check unpaid medications
        meds = Medication.query \
            .join(Consultation, Medication.consultation_id == Consultation.id) \
            .join(Visit, Consultation.visit_id == Visit.id) \
            .filter(Visit.patient_id == patient.id) \
            .filter(db.or_(Medication.is_paid == False, Medication.payment_status != 'paid')) \
            .all()
        for med in meds:
            service = Service.query.get(med.service_id)
            if service:
                total_cost = service.price * med.quantity
                unpaid_items.append({
                    'id': med.id, # Add ID
                    'name': service.name,
                    'type': service.category,
                    'date': med.prescribed_at.strftime('%Y-%m-%d'),
                    'amount': total_cost,
                    'source': 'medication',
                    'quantity': med.quantity,
                    'unit_price': service.price,
                    'status': med.payment_status # Show payment status directly
                })

        # Check unpaid radiology
        radios = Radiology.query \
            .join(Consultation, Radiology.consultation_id == Consultation.id) \
            .join(Visit, Consultation.visit_id == Visit.id) \
            .filter(Visit.patient_id == patient.id) \
            .filter(db.or_(Radiology.is_paid == False, Radiology.payment_status != 'paid')) \
            .all()
        for ro in radios:
            service = Service.query.get(ro.service_id)
            if service:
                unpaid_items.append({
                    'id': ro.id, # Add ID
                    'name': service.name,
                    'type': service.category,
                    'date': ro.requested_at.strftime('%Y-%m-%d'),
                    'amount': service.price,
                    'source': 'radiology',
                    'status': ro.payment_status # Show payment status directly
                })
        
        # Now, fetch transactions that are related to these *specific unpaid services*.
        # This is more for context/linking than determining unpaid status,
        # as the services themselves are the authoritative source.
        # You could also consider whether a 'Transaction' being 'pending' or 'failed'
        # itself indicates an unpaid service *if those services aren't linked to a paid item*.
        # However, given your models, `is_paid` and `payment_status` on the service models
        # are the direct indicators.
        # If you still want to list transactions (e.g., failed STK pushes) that haven't
        # been cleared but aren't tied to a `LabTest`/`Medication`/`Radiology` record (which they should be),
        # then you'd add back a modified version of the transaction check.
        # For simplicity and correctness based on your `is_paid` flags, we remove the direct transaction check for now.

        insurance_providers = {str(ins.id): ins.name for ins in Insurance.query.all()}

        # Add only if there are unpaid services
        if unpaid_items: # Only append if the unpaid_items list is not empty
            # Get insurance provider name if available
            insurance_provider_name = None
            if patient.insurance_provider and str(patient.insurance_provider) in insurance_providers:
                insurance_provider_name = insurance_providers[str(patient.insurance_provider)] # Cast to string for key lookup
                
            result.append({
                'patient_id': patient.id,
                'reg_no': patient.reg_no,
                'full_name': patient.full_name,
                'phone': patient.phone,
                'payment_method': patient.payment_method,
                'insurance_provider': patient.insurance_provider,
                'insurance_provider_name': insurance_provider_name,
                'unpaid_services': unpaid_items
            })

    return jsonify(result)
# ---------------------------
# VIEW DETAILS
# ---------------------------
@billing_web_bp.route('/patient/<reg_no>/details')
def patient_details(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    # Reuse your unpaid-services logic or call the same function
    unpaid = get_unpaid_for_patient(patient)
    return render_template(
        'patient_details.html',
        patient=patient,
        unpaid_services=unpaid
    )

# ---------------------------
# PAY PAGE
# ---------------------------
@billing_web_bp.route('/patient/<reg_no>/pay')
def patient_pay(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    unpaid = get_unpaid_for_patient(patient)
    total = sum(item['amount'] for item in unpaid)

    # Fetch hospital info - assuming you have a way to get the current hospital's profile
    # For simplicity, fetching the first one. In a multi-tenant app, this would be based on subdomain/user session.
    hospital_info = HospitalProfile.query.first() 
    return render_template(
        'patient_pay.html',
        patient=patient,
        unpaid_services=unpaid,
        total_amount=total,
        hospital_info=hospital_info # Pass hospital_info to the template
    )

@billing_web_bp.route('/patient/<reg_no>/verify')
def patient_verify(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    unpaid_services = get_unpaid_for_patient(patient)
    total_amount = sum(item['amount'] for item in unpaid_services)

    # Initialize billing collections
    insurance = None
    covered_services = []
    uncovered_services = []
    insurance_coverage = {}
    total_insurance_coverable = 0
    total_cash_payment = 0

    # Check if patient uses insurance
    if patient.payment_method == 'insurance' and patient.insurance_provider:
        insurance = Insurance.query.get(patient.insurance_provider)
        if insurance:
            # Build coverage lookup
            insurance_coverage = {
                svc.service_id: svc
                for svc in insurance.covered_services
                if svc.is_covered
            }
            # Categorize each service
            for svc in unpaid_services:
                sid = svc['id']
                if sid in insurance_coverage:
                    cov = insurance_coverage[sid]
                    pct = cov.coverage_percentage or 0
                    copay = cov.copay or 0
                    amt = svc['amount']
                    # Calculate covered & patient costs
                    covered_amt = amt * (pct / 100)
                    patient_pay = amt - copay
                    # Cap at full amount
                    patient_pay = min(patient_pay, amt)

                    covered_services.append({
                        **svc,
                        'covered_amount': covered_amt,
                        'patient_responsibility': patient_pay,
                        'coverage_details': {
                            'coverage_percentage': pct,
                            'copay': copay,
                            'requires_prior_authorization': cov.requires_prior_authorization
                        }
                    })
                    total_insurance_coverable += covered_amt
                    total_cash_payment += patient_pay
                else:
                    # Service not covered
                    uncovered_services.append(svc)
                    total_cash_payment += svc['amount']
        else:
            # Invalid insurance provider: treat all as cash
            uncovered_services = unpaid_services
            total_cash_payment = total_amount
    else:
        # No insurance: all cash
        uncovered_services = unpaid_services
        total_cash_payment = total_amount

    selected_service_ids = [s['id'] for s in unpaid_services]

    return render_template(
        'patient_verify.html',
        patient=patient,
        insurance=insurance,
        covered_services=covered_services,
        uncovered_services=uncovered_services,
        total_amount=total_amount,
        total_insurance_coverable=total_insurance_coverable,
        total_cash_payment=total_cash_payment,
        selected_service_ids=selected_service_ids
    )



# ---------------------------
# DELETE UNPAID SERVICES
# ---------------------------
# Assuming you have necessary imports like db, jsonify, Patient, Transaction, LabTest, Medication, Radiology, Consultation, Visit, billing_web_bp

@billing_web_bp.route('/api/delete-unpaid-services/<reg_no>', methods=['DELETE'])
def delete_unpaid_services(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()

    # --- REMOVE THIS SECTION ---
    # Delete any pending transactions
    # Transaction.query.filter(
    #     Transaction.patient_id == patient.id,
    #     Transaction.status.notin_(['completed', 'paid'])
    # ).delete(synchronize_session=False)
    # ---------------------------

    # Delete unpaid lab tests
    LabTest.query.filter(
        LabTest.consultation.has(Consultation.visit.has(Visit.patient_id == patient.id)),
        db.or_(LabTest.is_paid == False, LabTest.payment_status != 'paid')
    ).delete(synchronize_session=False)

    # Delete unpaid medications
    Medication.query.filter(
        Medication.consultation.has(Consultation.visit.has(Visit.patient_id == patient.id)),
        db.or_(Medication.is_paid == False, Medication.payment_status != 'paid')
    ).delete(synchronize_session=False)

    # Delete unpaid radiology orders
    Radiology.query.filter(
        Radiology.consultation.has(Consultation.visit.has(Visit.patient_id == patient.id)),
        db.or_(Radiology.is_paid == False, Radiology.payment_status != 'paid')
    ).delete(synchronize_session=False)

    db.session.commit()
    return jsonify({'status': 'success'}), 200

# ---------------------------
# Helper to get unpaid items
# ---------------------------
def get_unpaid_for_patient(patient):
    """Return a list of unpaid services dicts for this patient."""
    items = []

    # Lab tests
    lts = LabTest.query.join(Consultation).join(Visit).filter(
        Visit.patient_id == patient.id,
        db.or_(LabTest.is_paid == False, LabTest.payment_status != 'paid')
    ).all()
    for lt in lts:
        svc = Service.query.get(lt.service_id)
        if svc: # Ensure service exists before adding
            items.append({
                'id': svc.id, # Use LabTest ID as the item ID
                'name': svc.name,
                'type': svc.category,
                'date': lt.requested_at.strftime('%Y-%m-%d'),
                'amount': svc.price,
                'source': 'lab_test',
                'status': lt.payment_status # Include payment status for clarity
            })

    # Medications
    meds = Medication.query.join(Consultation).join(Visit).filter(
        Visit.patient_id == patient.id,
        db.or_(Medication.is_paid == False, Medication.payment_status != 'paid')
    ).all()
    for med in meds:
        svc = Service.query.get(med.service_id)
        if svc: # Ensure service exists before adding
            total = svc.price * med.quantity
            items.append({
                'id': svc.id, # Use Medication ID as the item ID
                'name': svc.name,
                'type': svc.category,
                'date': med.prescribed_at.strftime('%Y-%m-%d'),
                'amount': total,
                'source': 'medication',
                'quantity': med.quantity, # Add quantity for meds
                'unit_price': svc.price,  # Add unit price for meds
                'status': med.payment_status # Include payment status for clarity
            })

    # Radiology
    ros = Radiology.query.join(Consultation).join(Visit).filter(
        Visit.patient_id == patient.id,
        db.or_(Radiology.is_paid == False, Radiology.payment_status != 'paid')
    ).all()
    for ro in ros:
        svc = Service.query.get(ro.service_id)
        if svc: # Ensure service exists before adding
            items.append({
                'id': svc.id, # Use Radiology ID as the item ID
                'name': svc.name,
                'type': svc.category,
                'date': ro.requested_at.strftime('%Y-%m-%d'),
                'amount': svc.price,
                'source': 'radiology',
                'status': ro.payment_status # Include payment status for clarity
            })

    return items



@billing_web_bp.route('/transaction-history')
def transaction_history():
    return render_template('transaction_history.html')


@billing_web_bp.route('/api/patients/search', methods=['GET'])
def search_patients():
    search_query = request.args.get('q', '').strip()
    if not search_query:
        return jsonify([])

    # Split search query for name search
    name_parts = search_query.split()
    queries = [
        Patient.reg_no.ilike(f"%{search_query}%"),
        Patient.phone.ilike(f"%{search_query}%")
    ]
    
    # Handle first/last name search
    if len(name_parts) >= 2:
        queries.extend([
            Patient.first_name.ilike(f"%{name_parts[0]}%"),
            Patient.last_name.ilike(f"%{name_parts[1]}%")
        ])
    else:
        queries.extend([
            Patient.first_name.ilike(f"%{search_query}%"),
            Patient.last_name.ilike(f"%{search_query}%")
        ])

    patients = Patient.query.filter(db.or_(*queries)).limit(10).all()
    
    return jsonify([{
        'id': p.id,
        'reg_no': p.reg_no,
        'full_name': p.full_name,
        'phone': p.phone,
        'insurance_provider': p.insurance_provider
    } for p in patients])

@billing_web_bp.route('/api/patients/<int:patient_id>/unpaid-services', methods=['GET'])
def get_unpaid_services(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    unpaid_services = []

    # Get unpaid transactions and their services
    transactions = Transaction.query.filter(
        Transaction.patient_id == patient_id,
        Transaction.status.notin_(['completed', 'paid'])
    ).all()

    for transaction in transactions:
        for service in transaction.services:
            unpaid_services.append({
                'name': service.name,
                'type': service.category,
                'date': transaction.created_at.strftime('%Y-%m-%d'),
                'amount': service.price,
                'source': 'transaction'
            })

    # Get unpaid lab tests through consultations and visits
    lab_tests = LabTest.query \
        .join(Consultation, LabTest.consultation_id == Consultation.id) \
        .join(Visit, Consultation.visit_id == Visit.id) \
        .filter(Visit.patient_id == patient_id) \
        .filter(db.or_(LabTest.is_paid == False, LabTest.payment_status != 'paid')) \
        .all()

    for lt in lab_tests:
        service = Service.query.get(lt.service_id)
        if service:
            unpaid_services.append({
                'name': service.name,
                'type': service.category,
                'date': lt.requested_at.strftime('%Y-%m-%d'),
                'amount': service.price,
                'source': 'lab_test'
            })

    # Get unpaid medications through consultations and visits
    medications = Medication.query \
        .join(Consultation, Medication.consultation_id == Consultation.id) \
        .join(Visit, Consultation.visit_id == Visit.id) \
        .filter(Visit.patient_id == patient_id) \
        .filter(db.or_(Medication.is_paid == False, Medication.payment_status != 'paid')) \
        .all()

    for med in medications:
        service = Service.query.get(med.service_id)
        if service:
            # Calculate total medication cost = service price × quantity
            total_cost = service.price * med.quantity
            
            unpaid_services.append({
                'name': service.name,
                'type': service.category,
                'date': med.prescribed_at.strftime('%Y-%m-%d'),
                'amount': total_cost,  # Use calculated total instead of service price
                'source': 'medication',
                'quantity': med.quantity,  # Send quantity to frontend
                'unit_price': service.price  # Send unit price to frontend
            })
    

    # Get unpaid radiology orders through consultations and visits
    radiology_orders = Radiology.query \
        .join(Consultation, Radiology.consultation_id == Consultation.id) \
        .join(Visit, Consultation.visit_id == Visit.id) \
        .filter(Visit.patient_id == patient_id) \
        .filter(db.or_(Radiology.is_paid == False, Radiology.payment_status != 'paid')) \
        .all()

    for ro in radiology_orders:
        service = Service.query.get(ro.service_id)
        if service:
            unpaid_services.append({
                'name': service.name,
                'type': service.category,
                'date': ro.requested_at.strftime('%Y-%m-%d'),
                'amount': service.price,
                'source': 'radiology'
            })

    return jsonify(unpaid_services)

@billing_web_bp.route('/payments/process', methods=['POST'])
def process_payment():
    data = request.get_json()
    
    # Validate patient exists
    patient = Patient.query.get(data['patient_id'])
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    # Get current visit (assuming active visit exists)
    current_visit = Visit.query.filter_by(
        patient_id=patient.id,
        visit_status='in_progress'
    ).order_by(Visit.visit_date.desc()).first()
    
    if not current_visit:
        return jsonify({'error': 'No active visit found'}), 400

    # Create transaction
    new_transaction = Transaction(
        patient_id=patient.id,
        amount=data['amount'],
        payment_method=data['payment_method'],
        status='pending',
        phone=data.get('phone'),
        account_ref=data.get('account_ref')
    )

    # Track service categories for position update
    service_categories = set()
    positions = {
        'Pharmacy': 'pharmacy',
        'Lab': 'lab',
        'Radiology': 'radiology'
    }

    # Process each service being paid
    for service_id in data.get('service_ids', []):
        service = Service.query.get(service_id)
        if service:
            # Add service to transaction
            new_transaction.services.append(service)
            
            # Track service category
            service_categories.add(service.category)
            
            # Mark specific service records as paid
            if service.category == 'Pharmacy':
                med = Medication.query.filter_by(
                    service_id=service_id,
                    consultation_id=current_visit.consultation.id
                ).first()
                if med:
                    med.is_paid = True
                    med.payment_status = 'paid'
            
            elif service.category == 'Lab':
                lab = LabTest.query.filter_by(
                    service_id=service_id,
                    consultation_id=current_visit.consultation.id
                ).first()
                if lab:
                    lab.is_paid = True
                    lab.payment_status = 'paid'
            
            elif service.category == 'Radiology':
                rad = Radiology.query.filter_by(
                    service_id=service_id,
                    consultation_id=current_visit.consultation.id
                ).first()
                if rad:
                    rad.is_paid = True
                    rad.payment_status = 'paid'

    # Update visit's current position
    for category in ['Pharmacy', 'Lab', 'Radiology']:
        if category in service_categories:
            current_visit.current_position = positions[category]
            break  # Prioritize first relevant position

    # Add services to transaction    
    db.session.add(new_transaction)
    db.session.commit()

    # Simulate payment success (replace with actual payment processing)
    new_transaction.status = 'completed'
    new_transaction.paid_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message': 'Payment completed',
        'transaction_id': new_transaction.id,
        'visit_id': current_visit.id,
        'current_position': current_visit.current_position
    }), 201

@billing_web_bp.route('/api/patients/search', methods=['GET'])
def search_patient():
    search_query = request.args.get('q', '').strip()
    if not search_query:
        return jsonify([])

    # Split search query for name search
    name_parts = search_query.split()
    queries = [
        Patient.reg_no.ilike(f"%{search_query}%"),
        Patient.phone.ilike(f"%{search_query}%")
    ]
    
    # Handle first/last name search
    if len(name_parts) >= 2:
        queries.extend([
            Patient.first_name.ilike(f"%{name_parts[0]}%"),
            Patient.last_name.ilike(f"%{name_parts[1]}%")
        ])
    else:
        queries.extend([
            Patient.first_name.ilike(f"%{search_query}%"),
            Patient.last_name.ilike(f"%{search_query}%")
        ])

    patients = Patient.query.filter(db.or_(*queries)).limit(10).all()
    
    return jsonify([{
        'id': p.id,
        'reg_no': p.reg_no,
        'full_name': p.full_name,
        'phone': p.phone,
        'insurance_provider': p.insurance_provider
    } for p in patients])



@billing_web_bp.route('/patients/verify-insurance', methods=['POST'])
def verify_insurance():
    # 1. grab form data
    reg_no = request.form.get('reg_no')
    raw_ids = request.form.get('covered_service_ids', '')
    try:
        service_ids = [int(sid) for sid in raw_ids.split(',') if sid.strip()]
    except ValueError:
        flash("Invalid service IDs.", "error")
        return redirect(url_for('billing_web_bp.patient_verify', reg_no=reg_no))

    # 2. load patient & active visit
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    visit = Visit.query.filter_by(patient_id=patient.id, visit_status='in_progress')\
                       .order_by(Visit.visit_date.desc()).first_or_404()

    # 3. create Invoice
    invoice = Invoice(
        visit_id=visit.id,
        patient_id=patient.id,
        invoice_type='insurance',
        insurance_id=patient.insurance_provider,
        issue_date=datetime.utcnow(),
        total_amount=0.0  # we'll accumulate below
    )
    db.session.add(invoice)
    db.session.flush()  # so invoice.id is available

    total = 0.0

    # 4. for each covered service, mark paid & add InvoiceItem
    for sid in service_ids:
        # fetch the InsService record to get coverage details
        ins_svc = InsuranceService.query.filter_by(
            insurance_id=patient.insurance_provider,
            service_id=sid
        ).first()
        cov_pct = ins_svc.coverage_percentage if ins_svc else 0
        copay  = ins_svc.copay if ins_svc else 0

        # look up and mark the actual service record
        # --- Medication ---
        med = Medication.query.join(Consultation)\
            .join(Visit)\
            .filter(Visit.id==visit.id, Medication.service_id==sid, Medication.is_paid==False)\
            .first()
        if med:
            unit_price = med.price or med.service.price
            qty        = med.quantity
            med.is_paid = True
            med.payment_status = 'paid'
            med.verified_at = datetime.utcnow()
            db.session.add(med)
        else:
            # --- LabTest ---
            lt = LabTest.query.join(Consultation)\
                .join(Visit)\
                .filter(Visit.id==visit.id, LabTest.service_id==sid, LabTest.is_paid==False)\
                .first()
            if lt:
                unit_price = lt.service.price
                qty        = 1
                lt.is_paid = True
                lt.payment_status = 'paid'
                lt.verified_at = datetime.utcnow()
                db.session.add(lt)
            else:
                # --- Radiology ---
                ro = Radiology.query.join(Consultation)\
                    .join(Visit)\
                    .filter(Visit.id==visit.id, Radiology.service_id==sid, Radiology.is_paid==False)\
                    .first()
                if ro:
                    unit_price = ro.service.price
                    qty        = 1
                    ro.is_paid = True
                    ro.payment_status = 'paid'
                    ro.verified_at = datetime.utcnow()
                    db.session.add(ro)
                else:
                    # no matching record found
                    continue

        # compute totals
        line_total    = unit_price * qty
        insured_amount = line_total * (cov_pct / 100)
        total        += line_total

        # add InvoiceItem
        item = InvoiceItem(
            invoice_id=invoice.id,
            service_id=sid,
            quantity=qty,
            unit_price=unit_price,
            total_price=line_total,
            is_insured=True,
            coverage_percentage=cov_pct,
            copay_amount=copay
        )
        db.session.add(item)

    # 5. finalize invoice total & commit
    invoice.total_amount = total
    db.session.commit()

    flash("Insurance coverage verified and invoice created.", "success")
    return redirect(url_for('billing_web.payment_processing'))