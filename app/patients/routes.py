import base64
from flask_login import current_user
import requests
from sqlalchemy import or_
from flask import current_app, flash, g, redirect, render_template, request, jsonify, url_for
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, subqueryload
from app.finance.models import CashAccount, CashTransaction, Insurance, InsuranceService, Invoice, InvoiceItem, SalesReport, SalesReportItem
from app.super_admin.models import HospitalProfile
from . import patients_web_bp
from app.extensions import db
from app.patients.models import Consultation, LabTest, Medication, Patient, Radiology, Service, TbScreening, Transaction, Visit, Vitals
from datetime import datetime, timedelta
from .services import mpesa_client
import datetime as _dt
from .hie_integration import generate_encrypted_pin, get_dha_token, make_dha_request
 
# Add this error handler
@patients_web_bp.errorhandler(500)
def handle_internal_error(error):
    return jsonify({'error': 'Internal server error', 'details': str(error)}), 500

@patients_web_bp.route('/hie/debug-token', methods=['GET'])
def debug_token():
    """Debug token generation endpoint"""
    try:
        # Prepare Basic Authentication
        basic_auth = base64.b64encode(
            f"{current_app.config['BASIC_AUTH_USERNAME']}:{current_app.config['BASIC_AUTH_PASSWORD']}".encode()
        ).decode()
        
        # Prepare parameters with proper key format
        params = {
            "key": f"6QP-{current_app.config['AGENT_ID']}"  # Correct format
        }
        
        # Make request
        response = requests.get(
            f"{current_app.config['DHA_BASE_URL']}/v1/hie-auth",
            headers={
                "Authorization": f"Basic {basic_auth}",
                "Accept": "text/plain"  # Match what the API returns
            },
            params=params,
            timeout=10
        )
        
        # Prepare response
        result = {
            'status': 'failure' if response.status_code != 200 else 'success',
            'request_method': 'GET',
            'request_url': response.url,
            'request_headers': {
                "Authorization": f"Basic [REDACTED]",
                "Accept": "text/plain"
            },
            'request_params': params,
            'response_status': response.status_code,
            'response_headers': dict(response.headers),
            'response_body': response.text  # Plain text token
        }
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500



@patients_web_bp.route('/hie/test-credentials', methods=['GET'])
def test_hie_credentials():
    """Test DHA HIE credentials and token generation"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    
    test_results = {}
    
    # 1. Test token generation
    try:
        token = get_dha_token()
        if token:
            test_results['token_generation'] = {
                'status': 'success',
                'token': f"{token[:10]}... (truncated)",
                'message': 'Token generated successfully'
            }
        else:
            test_results['token_generation'] = {
                'status': 'failure',
                'message': 'Failed to generate token'
            }
    except Exception as e:
        test_results['token_generation'] = {
            'status': 'error',
            'message': f'Token generation error: {str(e)}'
        }
    
    # 2. Test encrypted PIN generation
    try:
        encrypted_pin = generate_encrypted_pin()
        test_results['pin_generation'] = {
            'status': 'success',
            'encrypted_pin': encrypted_pin,
            'message': 'PIN generated successfully'
        }
    except Exception as e:
        test_results['pin_generation'] = {
            'status': 'error',
            'message': f'PIN generation error: {str(e)}'
        }
    
    # 3. Test API connection using the "Fetch CR Client" endpoint
    try:
        # Prepare query parameters for the fetch client endpoint
        params = {
            "identification_type": "National ID",
            "identification_number": "TEST123456",
            "agent": f"6QP-{current_app.config['AGENT_ID']}"
        }
        
        # Make the API request
        response = make_dha_request('/v3/client-registry/fetch-client', 
                                method='GET', 
                                params=params)
        
        # Handle response - 404 is expected since we're using test data
        if isinstance(response, tuple) and response[1] >= 400:
            if response[1] == 404:
                test_results['api_connection'] = {
                    'status': 'success',
                    'response': response[0],
                    'message': 'API connection successful (404 expected with test data)'
                }
            else:
                test_results['api_connection'] = {
                    'status': 'failure',
                    'message': f'API error (HTTP {response[1]}): {response[0].get("error", "Unknown error")}',
                    'raw_response': str(response[0])[:500] + '...'  # Truncate long responses
                }
        else:
            test_results['api_connection'] = {
                'status': 'success',
                'response': response,
                'message': 'API connection successful'
            }
    except Exception as e:
        test_results['api_connection'] = {
            'status': 'error',
            'message': f'API connection error: {str(e)}'
        }
    
    # 4. Verify credentials configuration
    config_status = {}
    required_keys = [
        'AGENT_ID', 'BASIC_AUTH_USERNAME', 'BASIC_AUTH_PASSWORD',
        'TOKEN_AUTH_KEY', 'TOKEN_AUTH_SECRET', 'PRIVATE_KEY', 'PUBLIC_KEY'
    ]
    
    for key in required_keys:
        value = current_app.config.get(key)
        if not value:
            config_status[key] = {
                'status': 'missing',
                'message': 'Configuration value not set'
            }
        elif key in ['PRIVATE_KEY', 'PUBLIC_KEY']:
            # Verify if keys are valid
            try:
                key_content = value.encode()
                if 'PRIVATE' in key:
                    serialization.load_pem_private_key(
                        key_content, password=None, backend=default_backend()
                    )
                else:
                    serialization.load_pem_public_key(
                        key_content, backend=default_backend()
                    )
                config_status[key] = {
                    'status': 'valid',
                    'message': 'Key is valid'
                }
            except Exception as e:
                config_status[key] = {
                    'status': 'invalid',
                    'message': f'Key error: {str(e)}'
                }
        else:
            config_status[key] = {
                'status': 'configured',
                'value': value[:2] + '****' + value[-2:] if len(value) > 4 else '****'
            }
    
    test_results['configuration'] = config_status
    
    # Determine overall status
    overall_success = all(
        test['status'] in ['success', 'valid', 'configured']
        for test in test_results.values()
    )
    
    return jsonify({
        'status': 'success' if overall_success else 'failure',
        'tests': test_results,
        'timestamp': datetime.utcnow().isoformat()
    })

# Add these routes at the bottom
@patients_web_bp.route('/hie/register-client', methods=['POST'])
def hie_register_client():
    """Register client in HIE Superhighway"""
    data = request.get_json()
    identification_number = data.get('identification_number')
    identification_type = data.get('identification_type', 'National ID')
    
    if not identification_number:
        return jsonify({'error': 'Missing identification_number'}), 400
    
    payload = {
        "agent": current_app.config['AGENT_ID'],
        "encrypted_pin": generate_encrypted_pin(),
        "identification_number": identification_number,
        "identification_type": identification_type
    }
    
    return make_dha_request('/v3/uat-cr-registration', method='POST', json_data=payload)

@patients_web_bp.route('/hie/fetch-client/<client_id>', methods=['GET'])
def hie_fetch_client(client_id):
    """Fetch client from HIE registry"""
    return make_dha_request('/v3/client-registry/fetch-client', params={'client_id': client_id})

@patients_web_bp.route('/hie/check-eligibility', methods=['GET'])
def hie_check_eligibility():
    """Check patient eligibility"""
    patient_id = request.args.get('patient_id')
    service_code = request.args.get('service_code')
    
    if not patient_id or not service_code:
        return jsonify({'error': 'Missing patient_id or service_code'}), 400
    
    params = {
        "patient_id": patient_id,
        "service_code": service_code
    }
    return make_dha_request('/v2/eligibility', params=params)

@patients_web_bp.route('/hie/submit-claim', methods=['POST'])
def hie_submit_claim():
    """Submit medical claim"""
    claim_data = request.get_json()
    return make_dha_request('/v1/shr-med/bundle', method='POST', json_data=claim_data)

@patients_web_bp.route('/hie/claim-status/<claim_id>', methods=['GET'])
def hie_claim_status(claim_id):
    """Check claim status"""
    return make_dha_request('/v1/shr-med/claim-status', params={'claim_id': claim_id})

@patients_web_bp.route('/hie/search-facilities', methods=['GET'])
def hie_search_facilities():
    """Search healthcare facilities"""
    params = {
        "name": request.args.get('name'),
        "county": request.args.get('county'),
        "facility_type": request.args.get('facility_type')
    }
    return make_dha_request('/v1/facility-search', params=params)

@patients_web_bp.route('/hie/terminology/<system>', methods=['GET'])
def hie_get_terminology(system):
    """Get medical terminology"""
    valid_systems = {
        "sha-intervention": "/terminology/v1/sha-intervention",
        "ichi": "/terminology/v1/ichi",
        "loinc": "/terminology/v1/loinc",
        "icd11": "/terminology/v1/icd11",
        "active-component": "/terminology/v1/active-component",
        "product": "/terminology/v1/product"
    }
    
    if system not in valid_systems:
        return jsonify({'error': 'Invalid terminology system'}), 400
    
    params = {"search": request.args.get('search')}
    return make_dha_request(valid_systems[system], params=params)
 
@patients_web_bp.route('/register', methods=['GET'])
def register_patient():
    insurance_providers = Insurance.query.filter_by(is_active=True).order_by(Insurance.name).all()
    return render_template('register_patient.html', 
                         insurance_providers=insurance_providers)

@patients_web_bp.route('/api/add/patients', methods=['POST'])
def api_add_or_update_patient():
    data = request.get_json(silent=True) or {}

    # Basic validation
    for fld in ('firstName', 'lastName', 'dob', 'phone'):
        if not data.get(fld):
            return jsonify({'error': f'Missing field: {fld}'}), 400

    # If regNo provided, try to update existing
    reg_no = data.get('regNo')
    if reg_no:
        patient = Patient.query.filter_by(reg_no=reg_no).first()
        if not patient:
            return jsonify({'error': f'No patient with regNo {reg_no}'}), 404
    else:
        # Create new patient and generate reg_no
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        reg_no = f'PAT-{timestamp}'
        patient = Patient(reg_no=reg_no)

    # Map incoming fields to model attributes
    patient.first_name         = data['firstName']
    patient.last_name          = data['lastName']
    patient.date_of_birth      = datetime.strptime(data['dob'], '%Y-%m-%d').date()
    patient.age                = data.get('age')
    patient.email              = data.get('email')
    patient.gender             = data.get('gender')
    patient.phone              = data['phone']
    patient.kin_name           = data.get('kinName')
    patient.kin_relationship   = data.get('kinRelationship')
    patient.kin_phone          = data.get('kinPhone')
    patient.kin_email          = data.get('kinEmail')
    patient.payment_method     = data.get('paymentMethod')
    patient.insurance_provider = data.get('insuranceProvider')
    patient.insurance_number   = data.get('insuranceNumber')

    # ── New assignments ──
    patient.county        = data.get('county')
    patient.subcounty     = data.get('subcounty')
    patient.ward          = data.get('ward')
    patient.residence     = data.get('residence')
    patient.marital_status= data.get('maritalStatus')
    patient.national_id   = data.get('nationalId')
    patient.guardian_id   = data.get('guardianId')

    db.session.add(patient)
    db.session.commit()

    return jsonify({
        'id':                patient.id,
        'regNo':             patient.reg_no,
        'paymentMethod':     patient.payment_method,
        'insuranceProvider': patient.insurance_provider,
        'insuranceNumber':   patient.insurance_number,
        'message':           reg_no and data.get('regNo')
                                and 'Patient updated'
                                or 'Patient created'
    }), 201



@patients_web_bp.route('/api/search', methods=['GET'])
def api_search_patients():
    q = request.args.get('query', '').strip()
    if not q:
        return jsonify([])

    # search by first/last name, phone or reg_no
    pattern = f"%{q}%"
    matches = (
        Patient.query
        .filter(
            or_(
                Patient.first_name.ilike(pattern),
                Patient.last_name.ilike(pattern),
                Patient.phone.ilike(pattern),
                Patient.reg_no.ilike(pattern),
            )
        )
        .order_by(Patient.last_name, Patient.first_name)
        .limit(10)
        .all()
    )

    # serialize to JSON
    results = []
    for p in matches:
        results.append({
            'regNo': p.reg_no,
            'firstName': p.first_name,
            'lastName': p.last_name,
            'dob': p.date_of_birth.isoformat(),
            'phone': p.phone,
            'email': p.email,
            'gender': p.gender,
            'kinName': p.kin_name,
            'kinRelationship': p.kin_relationship,
            'kinPhone': p.kin_phone,
            'kinEmail': p.kin_email
        })
    return jsonify(results)

@patients_web_bp.route('/cash-payment/<reg_no>', methods=['GET'])
def cash_payment(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    
    # Get services from database, sorted by category
    all_services = Service.query.order_by(Service.category).all()
    
    # ⭐ Fetch the hospital profile
    # Assuming there's only one hospital profile entry
    hospital_info = HospitalProfile.query.first() 
    # You might want to add error handling here if hospital_info could be None,
    # e.g., hospital_info = HospitalProfile.query.first_or_404() if you want to ensure it exists.
    
    return render_template('cash_payment.html', 
                            patient=patient, 
                            all_services=all_services,
                            hospital_info=hospital_info) # ⭐ Pass the hospital_info to the template


@patients_web_bp.route('/insurance-booking/<reg_no>', methods=['GET', 'POST'])
def insurance_booking(reg_no):
    # 1) Lookup patient (404 if not found)
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()

    # 2) Ensure they have an insurance_provider on file
    if not patient.insurance_provider:
        flash("This patient has no insurance on file.", "warning")
        return redirect(url_for('patients_web.triage'))

    insurance = Insurance.query.get(patient.insurance_provider)
    if not insurance:
        flash("Insurance record not found for this patient.", "danger")
        return redirect(url_for('patients_web.triage'))

    # 3) Build two lists: (a) covered services via InsuranceService, (b) cash-only services
    covered_services_q = InsuranceService.query.filter_by(
        insurance_id=insurance.id, is_covered=True
    ).all()

    service_coverage_list = []
    covered_ids = set()
    for ins_srv in covered_services_q:
        svc = Service.query.get(ins_srv.service_id)
        if svc:
            service_coverage_list.append((svc, ins_srv))
            covered_ids.add(svc.id)

    cash_services = Service.query.filter(~Service.id.in_(covered_ids)).all()

    # 4) If this is a form submission, process bookings + invoice creation
    if request.method == 'POST':
        chosen_ins_ids = request.form.getlist('service_ids')       # covered services
        chosen_cash_ids = request.form.getlist('cash_service_ids')  # cash-only services

        if not (chosen_ins_ids or chosen_cash_ids):
            flash("Please select at least one service to book.", "warning")
            return redirect(request.url)

        try:
            # ──────────────────────────────────────────────────────────────────────────
            # 4.1) Create the Visit
            # ──────────────────────────────────────────────────────────────────────────
            visit = Visit(
                patient_id=patient.id,
                visit_status='in_progress',
                current_position='Triage'
            )
            db.session.add(visit)
            db.session.flush()  # so that visit.id is populated

            # 4.2) Attach all selected services (covered + cash) to the visit
            for sid_str in chosen_ins_ids + chosen_cash_ids:
                sid = int(sid_str)
                svc = Service.query.get(sid)
                if svc:
                    visit.services.append(svc)

            # ──────────────────────────────────────────────────────────────────────────
            # 4.3) Create the Invoice (we do this before the Transaction so that
            #       all InvoiceItems can be associated, and total_amount computed)
            # ──────────────────────────────────────────────────────────────────────────
            # Determine invoice_type
            if chosen_ins_ids and not chosen_cash_ids:
                invoice_type = 'insurance'
            elif chosen_cash_ids and not chosen_ins_ids:
                invoice_type = 'cash'
            else:
                # If there's a mix, you can still mark it 'insurance' (or 'mixed' if you extended your model).
                invoice_type = 'insurance'

            invoice = Invoice(
                visit_id=visit.id,
                patient_id=patient.id,
                invoice_type=invoice_type,
                insurance_id=(insurance.id if invoice_type == 'insurance' else None),
                issue_date=datetime.utcnow(),
                due_date=datetime.utcnow() + timedelta(days=30),  # due in 30 days
                total_amount=0.0,  # we’ll recalc below
                status='pending',
                notes=f"Auto-generated invoice on {datetime.utcnow().date()}",
            )
            db.session.add(invoice)
            db.session.flush()  # so that invoice.id is populated

            # 4.3.a) Loop through covered services → build InvoiceItems
            total_invoice_amount = 0.0
            for sid_str in chosen_ins_ids:
                sid = int(sid_str)
                svc = Service.query.get(sid)
                # Find the InsuranceService row to get coverage_percentage & copay
                ins_srv = InsuranceService.query.filter_by(
                    insurance_id=insurance.id,
                    service_id=sid
                ).first()

                if not svc or not ins_srv:
                    continue

                # Compute patient “copay” or responsibility
                coverage_perc = ins_srv.coverage_percentage or 0.0
                # e.g. if coverage_perc = 80, patient pays 20% of svc.price
                patient_responsibility = svc.price * (1.0 - coverage_perc / 100.0)
                # If copay is a flat fee instead of % coverage, you could override:
                if ins_srv.copay:
                    patient_responsibility = ins_srv.copay

                # Build the InvoiceItem
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    service_id=sid,
                    quantity=1,
                    unit_price=svc.price,
                    total_price=round(patient_responsibility, 2),
                    is_insured=True,
                    coverage_percentage=coverage_perc,
                    copay_amount=round(patient_responsibility, 2),
                    notes=ins_srv.coverage_notes or None
                )
                invoice.items.append(item)
                total_invoice_amount += patient_responsibility

            # 4.3.b) Loop through cash‐only services → build InvoiceItems
            for sid_str in chosen_cash_ids:
                sid = int(sid_str)
                svc = Service.query.get(sid)
                if not svc:
                    continue

                # Entire price is patient’s responsibility
                patient_responsibility = svc.price

                item = InvoiceItem(
                    invoice_id=invoice.id,
                    service_id=sid,
                    quantity=1,
                    unit_price=svc.price,
                    total_price=round(patient_responsibility, 2),
                    is_insured=False,
                    coverage_percentage=0.0,
                    copay_amount=round(patient_responsibility, 2),
                    notes="Cash payment"
                )
                invoice.items.append(item)
                total_invoice_amount += patient_responsibility

            # 4.3.c) Update invoice.total_amount
            invoice.total_amount = round(total_invoice_amount, 2)
            db.session.flush()

            # ──────────────────────────────────────────────────────────────────────────
            # 4.4) If there are cash services, create a Transaction as before
            # ──────────────────────────────────────────────────────────────────────────
            if chosen_cash_ids:
                txn_total = sum(Service.query.get(int(s)).price for s in chosen_cash_ids)
                txn = Transaction(
                    amount=round(txn_total, 2),
                    patient_id=patient.id,
                    payment_method='cash',
                    status='pending'
                )
                db.session.add(txn)
                db.session.flush()

                # Link visit ↔ transaction
                visit.transaction_id = txn.id
                # Link each cash service to the transaction
                for sid_str in chosen_cash_ids:
                    sid = int(sid_str)
                    svc = Service.query.get(sid)
                    if svc:
                        txn.services.append(svc)

            # ──────────────────────────────────────────────────────────────────────────
            # 4.5) Everything is ready. Commit once.
            # ──────────────────────────────────────────────────────────────────────────
            db.session.commit()

            flash("Visit, Invoice, and services booked successfully.", "success")
            return redirect(url_for('patients_web.insurance_booking', reg_no=reg_no))

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception("Error booking services + creating invoice")
            flash("An error occurred while booking services. Please try again.", "danger")
            return redirect(request.url)

    # 5) Render the booking template (the GET path)
    return render_template(
        'insurance_booking.html',
        patient=patient,
        insurance=insurance,
        service_coverage_list=service_coverage_list,
        cash_services=cash_services
    )


@patients_web_bp.route('/process-payment', methods=['POST'])
def process_payment():
    try:
        # 1) Get and validate service_ids_raw
        service_ids_raw = request.form.get('selectedServiceIds', '').strip()
        if not service_ids_raw:
            raise ValueError("No services selected.")
        # Build a list of integers, ignoring any non‐digits
        service_ids = []
        for part in service_ids_raw.split(','):
            part = part.strip()
            if part.isdigit():
                service_ids.append(int(part))
        if not service_ids:
            raise ValueError("Invalid service IDs provided.")

        # 2) Get and validate total_amount
        total_str = request.form.get('totalAmountValue', '').strip()
        if not total_str:
            raise ValueError("Total amount is required.")
        try:
            total_amount = float(total_str)
        except ValueError:
            raise ValueError("Total amount must be a valid number.")
        if total_amount <= 0:
            raise ValueError("Total amount must be greater than zero.")

        # 3) Get patient RegNo
        reg_no = request.form.get('patientRegNo', '').strip()
        if not reg_no:
            raise ValueError("Patient RegNo is required.")

        # --- NEW: Get patient category ---
        patient_category = request.form.get('patientCategory', 'general').strip()
        if patient_category not in ['general', 'walkin', 'special_clinic']:
            patient_category = 'general'  # default if invalid


        # --- VISIT TYPE LOGIC ---
        final_visit_type = request.form.get('finalVisitType', '').strip()
        other_visit_type_details = None
                # --- NEW: Get served by information ---
        # --- NEW: Get served by information ---
        served_by = request.form.get('servedBy', '').strip()
        if not served_by:
            # Use current_user.full_name if available
            if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                served_by = current_user.full_name
            else:
                served_by = "System"  # fallback

        # If 'other' was selected, get the detailed description
        if final_visit_type == 'other':
            other_visit_type_details = request.form.get('otherVisitType', '').strip()
            if not other_visit_type_details:
                raise ValueError("Please specify the 'Other' visit type.")

        # --- END NEW LOGIC ---

        # 4) Get payment_method
        payment_method = request.form.get('paymentMethod', '')
        if not payment_method:
            raise ValueError("Payment method is required.")
        payment_method = payment_method.strip().lower()

        # 5) For STK: get stkPhone (optional if not STK)
        phone = request.form.get('stkPhone', '').strip()

        # 6) For Paybill: get selectedTransactionId and selectedTransactionAmount
        transaction_id_raw = request.form.get('selectedTransactionId', '').strip()
        transaction_amount_raw = request.form.get('selectedTransactionAmount', '').strip()

        # 7) Verify patient exists
        patient = Patient.query.filter_by(reg_no=reg_no).first()
        if not patient:
            raise ValueError(f"Patient with RegNo '{reg_no}' not found.")

        # ───────────────────────────────────────────────────────────
        # A) STK Push path
        # ───────────────────────────────────────────────────────────
        if payment_method == 'stk':
            # 7.a) Validate phone "7XXXXXXXX"
            if not (
                phone
                and len(phone) == 10
                and phone.isdigit()
                and (phone.startswith("07") or phone.startswith("01"))
            ):
                raise ValueError("Invalid phone number format. Use 07XXXXXXXX or 01XXXXXXXX.")

            # Strip the leading "0" to produce a 9-digit suffix (e.g. "712345678")
            phone_suffix = phone[1:]

            # Prepend country code
            full_phone = f"254{phone_suffix}"  # e.g. "254712345678"

            # 7.b) Pull Service objects to ensure they exist
            services = Service.query.filter(Service.id.in_(service_ids)).all()
            if not services:
                raise ValueError("No matching services found for the given IDs.")

            # 7.c) Build description string
            service_names = ", ".join([s.name for s in services])

            # 7.d) Initiate STK push
            response = mpesa_client.initiate_stk_push(
                phone=phone_suffix,           # without leading "0"
                amount=total_amount,
                account_ref=reg_no,
                description=f"Medical services: {service_names}",
                patient_id=patient.id
            )

            if not response.get('success', False):
                raise ValueError(response.get('error_message', 'Payment initiation failed.'))

            # 8) Assume mpesa_client gives you a Transaction model instance
            mpesa_tx = response.get('transaction')
            if not isinstance(mpesa_tx, Transaction):
                raise ValueError("Unexpected transaction object from MPESA client.")
            
            tx_record = mpesa_tx
            
            # ────────────── NEW: Set served_by and patient_category ──────────────
            tx_record.served_by = served_by
            
            
            # If you have user authentication, set served_by_id
            if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                tx_record.served_by_id = current_user.id
            # ────────────────────────────────────────────────────────────────────
            
            db.session.add(tx_record)
            db.session.flush()  # get tx_record.id

            # Associate each Service with this Transaction (writes into transaction_services)
            tx_record.services.extend(services)
            db.session.flush()

            # 9) Either reuse an existing in_progress visit or create a new one
            visit = (
                Visit.query
                .filter_by(patient_id=patient.id, visit_status='in_progress')
                .first()
            )
            if visit:
                # update the existing visit
                visit.transaction_id = tx_record.id
                visit.is_paid = (payment_method == 'paybill')
                visit.payment_status = 'paid' if payment_method == 'paybill' else 'pending'
                # Ensure existing visit services are not duplicated
                existing_visit_service_ids = {svc.id for svc in visit.services}
                new_services_for_visit = [svc for svc in services if svc.id not in existing_visit_service_ids]
                visit.services.extend(new_services_for_visit) # Add only new services
                tx_record.patient_category = visit.patient_category
                visit.visit_type_other_details = other_visit_type_details
            else:
                # no existing in-progress visit → create new
                visit = Visit(
                    patient_id     = patient.id,
                    transaction_id = tx_record.id,
                    visit_status   = 'in_progress',
                    current_position = 'billing',
                    visit_type_category = final_visit_type,
                    visit_type_other_details = other_visit_type_details, # Store details if 'other'
                    is_paid        = (payment_method == 'paybill'),
                    payment_status = ('paid' if payment_method == 'paybill' else 'pending'),
                    patient_category = patient_category  # NEW: Store patient category in visit too
                )
                tx_record.patient_category = patient_category
                db.session.add(visit)
                visit.services.extend(services)

            db.session.flush()  # so visit.id is set

            # ───────────────────────────────────────────────────────────
            # ───────────────────────────────────────────────────────────
            # --- NEW LOGIC: Create respective LabTest, Medication, Radiology records ---
            # ───────────────────────────────────────────────────────────
            # ───────────────────────────────────────────────────────────
            # --- COMPREHENSIVE LOGIC: Handle all scenarios for service records ---
            current_app.logger.info(f"Processing services for visit {visit.id}. Category: {visit.visit_type_category}")

            computed_total = 0.0
            for svc in services:
                if patient_category == 'walkin':
                    unit_price = svc.walkin_price or svc.price
                elif patient_category == 'special_clinic':
                    unit_price = svc.special_clinic_price or svc.price
                else:  # general
                    unit_price = svc.price

                # Optional: verify that the computed total matches the submitted total_amount
                computed_total += unit_price


            # ───────────────────────────────────────────────────────────
            # --- Create service records with the correct price ---
            # ───────────────────────────────────────────────────────────
            for svc in services:
                # Determine price again (or reuse from above)
                if patient_category == 'walkin':
                    unit_price = svc.walkin_price or svc.price
                elif patient_category == 'special_clinic':
                    unit_price = svc.special_clinic_price or svc.price
                else:
                    unit_price = svc.price

                consultation_ids = [c.id for c in visit.consultations] if visit.consultations else []

                if svc.category.lower() == 'pharmacy':
                    # Strategy: Prefer updating consultation records, fallback to creating visit records
                    existing_medication = None
                    
                    # First, check for pending consultation medications
                    if consultation_ids:
                        existing_medication = Medication.query.filter(
                            Medication.consultation_id.in_(consultation_ids),
                            Medication.service_id == svc.id,
                            Medication.payment_status == 'pending'
                        ).first()
                    
                    if existing_medication:
                        # Update existing consultation medication
                        existing_medication.visit_id = visit.id
                        existing_medication.payment_status = 'pending'
                        existing_medication.is_paid = False
                        existing_medication.price = unit_price  # <-- use category‑specific price

                        current_app.logger.info(f"UPDATED: Consultation Medication {existing_medication.id} for {svc.name} -> Visit {visit.id}, marked as paid")
                    
                    else:
                        # Check if already exists in visit (shouldn't normally happen)
                        existing_visit_medication = Medication.query.filter_by(visit_id=visit.id, service_id=svc.id).first()
                        if existing_visit_medication:
                            # Update existing visit medication payment status
                            existing_visit_medication.payment_status = 'pending'
                            existing_visit_medication.is_paid = False
                            current_app.logger.info(f"UPDATED: Existing Visit Medication {existing_visit_medication.id} for {svc.name} -> marked as paid")
                        else:
                            # Create new medication record
                            medication = Medication(
                                service_id=svc.id,
                                visit_id=visit.id, 
                                quantity=1, 
                            price=unit_price,  # <-- use category‑specific price
                                is_paid=True,          
                                payment_status='paid'
                            )
                            db.session.add(medication)
                            current_app.logger.info(f"CREATED: New Medication for {svc.name} in Visit {visit.id}")

                elif svc.category == 'Laboratory':
                    existing_lab_test = None
                    if consultation_ids:
                        existing_lab_test = LabTest.query.filter(
                            LabTest.consultation_id.in_(consultation_ids),
                            LabTest.service_id == svc.id,
                            LabTest.payment_status == 'pending'
                        ).first()

                    if existing_lab_test:
                        # Update existing consultation lab test
                        existing_lab_test.visit_id = visit.id
                        existing_lab_test.payment_status = 'pending'
                        existing_lab_test.is_paid = False
                        existing_lab_test.price = unit_price
                        current_app.logger.info(f"UPDATED: Consultation LabTest {existing_lab_test.id} for {svc.name} -> Visit {visit.id}, marked as paid")

                    else:
                        existing_visit_lab_test = LabTest.query.filter_by(visit_id=visit.id, service_id=svc.id).first()
                        if existing_visit_lab_test:
                            existing_visit_lab_test.payment_status = 'paid'
                            existing_visit_lab_test.is_paid = True
                            existing_visit_lab_test.price = svc.price
                            current_app.logger.info(f"UPDATED: Existing Visit LabTest {existing_visit_lab_test.id} for {svc.name} -> marked as paid")
                        else:
                            lab_test = LabTest(
                                service_id=svc.id,
                                visit_id=visit.id,
                                status='requested',
                                is_paid=True,
                                payment_status='paid',
                            price=unit_price,  # <-- use category‑specific price
                                requested_at=datetime.utcnow()
                            )
                            db.session.add(lab_test)
                            current_app.logger.info(f"CREATED: New LabTest for {svc.name} in Visit {visit.id}")
                elif svc.category.lower() == 'radiology':
                    existing_radiology = None
                    if consultation_ids:
                        existing_radiology = Radiology.query.filter(
                            Radiology.consultation_id.in_(consultation_ids),
                            Radiology.service_id == svc.id,
                            Radiology.payment_status == 'pending'
                        ).first()

                    if existing_radiology:
                        existing_radiology.visit_id = visit.id
                        existing_radiology.payment_status = 'pending'
                        existing_radiology.is_paid = False
                        existing_radiology.price = svc.price   # 👈 set price
                        current_app.logger.info(f"UPDATED: Consultation Radiology {existing_radiology.id} for {svc.name} -> Visit {visit.id}, marked as paid")

                    else:
                        existing_visit_radiology = Radiology.query.filter_by(visit_id=visit.id, service_id=svc.id).first()
                        if existing_visit_radiology:
                            existing_visit_radiology.payment_status = 'pending'
                            existing_visit_radiology.is_paid = False
                            existing_radiology.price = unit_price
                            current_app.logger.info(f"UPDATED: Existing Visit Radiology {existing_visit_radiology.id} for {svc.name} -> marked as paid")
                        else:
                            radiology_order = Radiology(
                                service_id=svc.id,
                                visit_id=visit.id,
                                status='requested',
                                is_paid=True,
                                payment_status='paid',
                            price=unit_price,  # <-- use category‑specific price
                                requested_at=datetime.utcnow()
                            )
                            db.session.add(radiology_order)
                            current_app.logger.info(f"CREATED: New Radiology for {svc.name} in Visit {visit.id}")
            # 10) Create CASH invoice (pending)
            invoice = Invoice(
                visit_id=visit.id,
                patient_id=patient.id,
                invoice_type='cash',
                insurance_id=None,
                issue_date=datetime.utcnow(),
                due_date=datetime.utcnow(),  # due immediately
                total_amount=0.0,  # we'll set it below
                status='pending',
                notes=f"Auto‐generated cash invoice on {datetime.utcnow().date()}. Served by: {served_by}"  # NEW: Include served_by in notes
            )
            db.session.add(invoice)
            db.session.flush()  # get invoice.id

            # 11) Build InvoiceItem for each service (cash = full price)
            total_invoice_amount = 0.0
            for svc in services:
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    service_id=svc.id,
                    quantity=1,
                    unit_price=svc.price,
                    total_price=round(svc.price, 2),
                    is_insured=False,
                    coverage_percentage=0.0,
                    copay_amount=round(svc.price, 2),
                    notes="Cash payment (STK pending)"
                )
                invoice.items.append(item)
                total_invoice_amount += svc.price

            invoice.total_amount = round(total_invoice_amount, 2)
            db.session.flush()

            # 12) Commit Visit, Transaction, Invoice, InvoiceItems all at once
            db.session.commit()

            # NEW: Return served_by in response for receipt generation
            return jsonify({
                "status": "success",
                "message": response['customer_message'],
                "checkout_id": response['checkout_request_id'],
                "served_by": served_by,  # NEW: Return served_by information
                "patient_category": patient_category  # NEW: Return patient category
            })
        # ───────────────────────────────────────────────────────────
        # B) Paybill confirmation path
        # ───────────────────────────────────────────────────────────
        elif payment_method == 'paybill':
            # 8.a) Ensure transaction_id_raw is present
            if not transaction_id_raw:
                raise ValueError("Transaction ID is required for Paybill.")
            if not transaction_id_raw.isdigit():
                raise ValueError("Transaction ID must be numeric.")
            transaction_id = int(transaction_id_raw)

            # 8.b) Ensure transaction_amount_raw is present
            if not transaction_amount_raw:
                raise ValueError("Selected transaction amount is required for Paybill.")
            try:
                transaction_amount = float(transaction_amount_raw)
            except ValueError:
                raise ValueError("Selected transaction amount must be a valid number.")
            if transaction_amount != total_amount:
                raise ValueError("Selected transaction amount does not match total amount.")

            # 8.c) Confirm payment via your helper (returns True/False)
            payment_confirmed = confirm_paybill_payment(transaction_id, reg_no, service_ids)
            if not payment_confirmed:
                raise ValueError("Could not confirm Paybill payment.")

            # 9) Fetch existing Transaction record and update to 'completed'
            tx_record = Transaction.query.filter_by(
                id=transaction_id,
                patient_id=patient.id
            ).first()
            if not tx_record:
                raise ValueError("Transaction record not found for Paybill.")

            tx_record.status = 'completed'
            tx_record.paid_at = datetime.utcnow()
            db.session.flush()

            # 10) Create a new Visit (paid)
            services = Service.query.filter(Service.id.in_(service_ids)).all()
            if not services:
                raise ValueError("No matching services found for the given IDs.")

            new_visit = Visit(
                patient_id=patient.id,
                transaction_id=tx_record.id,
                visit_status='in_progress',
                current_position='billing',
                is_paid=True,
                payment_status='paid'
            )
            new_visit.services.extend(services)
            db.session.add(new_visit)
            db.session.flush()  # get new_visit.id

            # 11) Create a CASH Invoice (immediately paid)
            invoice = Invoice(
                visit_id=new_visit.id,
                patient_id=patient.id,
                invoice_type='cash',
                insurance_id=None,
                issue_date=datetime.utcnow(),
                due_date=datetime.utcnow(),  # due now
                total_amount=0.0,            # recalc below
                status='paid',
                notes=f"Auto‐generated cash invoice (Paybill) on {datetime.utcnow().date()}"
            )
            db.session.add(invoice)
            db.session.flush()  # get invoice.id

            # 12) Build InvoiceItem for each service
            total_invoice_amount = 0.0
            for svc in services:
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    service_id=svc.id,
                    quantity=1,
                    unit_price=svc.price,
                    total_price=round(svc.price, 2),
                    is_insured=False,
                    coverage_percentage=0.0,
                    copay_amount=round(svc.price, 2),
                    notes="Cash payment (Paybill)"
                )
                invoice.items.append(item)
                total_invoice_amount += svc.price

            invoice.total_amount = round(total_invoice_amount, 2)
            db.session.flush()

            # 13) Commit the Visit, Transaction update, Invoice, InvoiceItems
            db.session.commit()

            return jsonify({
                "status": "success",
                "message": "Payment confirmed and invoice generated successfully."
            })

        else:
            return jsonify({"status": "error", "message": "Invalid payment method."}), 400

    except SQLAlchemyError as sqle:
        db.session.rollback()
        current_app.logger.exception("Database error during process_payment")
        return jsonify({
            "status": "error",
            "message": "A database error occurred. Please try again."
        }), 500

    except ValueError as ve:
        # This covers missing or non‐numeric fields, and any manual checks we raised.
        return jsonify({
            "status": "error",
            "message": str(ve)
        }), 400

    except Exception as e:
        current_app.logger.exception("Unexpected error in process_payment")
        return jsonify({
            "status": "error",
            "message": "An unexpected error occurred."
        }), 500

# Example payment confirmation function
def confirm_paybill_payment(transaction_id, reg_no, service_ids):
    # Your payment verification logic here
    return True



@patients_web_bp.route('/check-status')
def check_status():
    """Return payment status and receipt data when completed."""
    checkout_id = request.args.get('checkout_id')
    if not checkout_id:
        return jsonify({"status": "error", "message": "Missing checkout_id"}), 400

    tx = Transaction.query.filter_by(checkout_request_id=checkout_id).first()
    if not tx:
        return jsonify({"status": "error", "message": "Transaction not found"}), 404

    status = tx.status.lower() if tx.status else ''
    if status == 'completed':
        patient = tx.patient

        # 🚀 Get services directly from the transaction
        services = [
            {"id": s.id, "name": s.name, "price": s.price}
            for s in tx.services
        ]

        return jsonify({
            "status": "success",
            "message": "Transaction completed successfully",
            "transaction": {
                "checkout_id":         tx.checkout_request_id,
                "merchant_request_id": tx.merchant_request_id,
                "receipt_number":      tx.receipt_number,
                "amount":              tx.amount,
                "paid_at":             tx.paid_at.isoformat() if tx.paid_at else None,
                "payment_method":      tx.payment_method,
                # NEW: Add served_by and patient_category
                "served_by":           tx.served_by,
                "patient_category":    tx.patient_category
            },
            "patient": {
                "reg_no":     patient.reg_no,
                "first_name": patient.first_name,
                "last_name":  patient.last_name
            },
            "services": services
        }), 200

    elif status == 'failed':
        return jsonify({"status": "failed", "message": "Transaction failed"}), 200

    else:
        return jsonify({"status": "pending", "message": "Transaction still pending"}), 200





from flask import request, jsonify, current_app
from app.extensions import db
from app.patients.models import Transaction

@patients_web_bp.route('/mpesa-callback', methods=['POST'])
def mpesa_callback():
    try:
        payload = request.get_json(force=True)
        
        # Store the raw payload immediately
        tx = None
        if 'Body' in payload and 'stkCallback' in payload['Body']:
            cb = payload['Body']['stkCallback']
            checkout_id = cb.get('CheckoutRequestID')
            
            if checkout_id:
                # Find transaction by CheckoutRequestID
                tx = Transaction.query.filter_by(checkout_request_id=checkout_id).first()
                
                # STORE RAW CALLBACK DATA
                if tx:
                    tx.callback_data = payload  # Store the entire JSON payload

        if not tx:
            return jsonify({"status": "error", "message": "Transaction not found"}), 404
        cb      = payload['Body']['stkCallback']

        merchant_id = cb.get('MerchantRequestID')
        result_code = cb.get('ResultCode')
        result_desc = cb.get('ResultDesc')


        # 2) Update merchant_request_id on the transaction
        tx.merchant_request_id = merchant_id

        # 3) Extract metadata (Amount, MpesaReceiptNumber, TransactionDate, PhoneNumber)
        items = cb.get('CallbackMetadata', {}).get('Item', [])
        meta = {item['Name']: item.get('Value') for item in items if 'Name' in item}

        if result_code == 0:
            # 4) STK push succeeded: update transaction fields
            tx.status         = 'completed'
            tx.amount         = meta.get('Amount', tx.amount)
            tx.receipt_number = meta.get('MpesaReceiptNumber')

            ts = meta.get('TransactionDate')
            if ts:
                # Format is YYYYMMDDHHMMSS, e.g. "20250517032833"
                tx.paid_at = datetime.strptime(str(ts), '%Y%m%d%H%M%S')

            tx.phone = meta.get('PhoneNumber', tx.phone)

            # 5) If this transaction has a linked visit, mark that visit paid
            if hasattr(tx, 'visit') and tx.visit:
                tx.visit.is_paid          = True
                tx.visit.payment_status   = 'paid'
                
                # --- NEW LOGIC: Determine current_position based on visit_type_category ---
                walk_in_lab_types = ['walk_in_lab']
                walk_in_rad_types = ['walk_in_rad']
                walk_in_pharm_types = ['walk_in_pharm']
                optician_clinic_types = ['optician_clinic']  # New list
                dental_clinic_types = ['dental_clinic']      # New list

                if tx.visit.visit_type_category in walk_in_lab_types:
                    tx.visit.current_position = 'laboratory'
                    current_app.logger.info(f"Visit {tx.visit.id} is walk-in lab, setting position to 'laboratory'.")
                elif tx.visit.visit_type_category in walk_in_rad_types:
                    tx.visit.current_position = 'radiology'
                    current_app.logger.info(f"Visit {tx.visit.id} is walk-in radiology, setting position to 'radiology'.")
                elif tx.visit.visit_type_category in walk_in_pharm_types:
                    tx.visit.current_position = 'pharmacy'
                    current_app.logger.info(f"Visit {tx.visit.id} is walk-in pharmacy, setting position to 'pharmacy'.")
                elif tx.visit.visit_type_category in optician_clinic_types:
                    tx.visit.current_position = 'optician_clinic'
                    current_app.logger.info(f"Visit {tx.visit.id} is for optician clinic, setting position to 'optician_clinic'.")
                elif tx.visit.visit_type_category in dental_clinic_types:
                    tx.visit.current_position = 'dental_clinic'
                    current_app.logger.info(f"Visit {tx.visit.id} is for dental clinic, setting position to 'dental_clinic'.")
                else:
                    tx.visit.current_position = 'triage' # Default for normal patients
                    current_app.logger.info(f"Visit {tx.visit.id} is standard, setting position to 'triage'.")
                # --- END NEW LOGIC ---
                # 6) Locate the invoice for that visit and mark it as paid
                inv = Invoice.query.filter_by(visit_id=tx.visit.id).first()
                if inv:
                    inv.status = 'paid'

                    # 7) Update each InvoiceItem.notes now that payment succeeded
                    receipt = tx.receipt_number or 'N/A'
                    for item in inv.items:
                        item.notes = f"Cash payment (STK completed: {receipt})"

            # ──────────────────────────────────────────────────────────
            # 8) For each Service in this transaction, mark associated
            #    LabTest / Medication / Radiology records as paid:
            # ──────────────────────────────────────────────────────────
            if hasattr(tx, 'services'):
                for svc in tx.services:
                    # a) Mark any LabTest under this visit with service_id == svc.id
                    # Removed .join(Consultation) to allow direct linking to Visit
                    lab_tests = (
                        LabTest.query
                        .filter(
                            LabTest.visit_id == tx.visit.id,  # Direct link to Visit
                            LabTest.service_id == svc.id
                        )
                        .all()
                    )
                    for lt in lab_tests:
                        lt.is_paid = True
                        lt.payment_status = 'paid'
                        current_app.logger.info(f"Marked LabTest (ID: {lt.id}) for service {svc.name} in Visit {tx.visit.id} as PAID.")

                    # b) Mark any Medication under this visit with service_id == svc.id
                    # Removed .join(Consultation) to allow direct linking to Visit
                    medications = (
                        Medication.query
                        .filter(
                            Medication.visit_id == tx.visit.id,  # Direct link to Visit
                            Medication.service_id == svc.id
                        )
                        .all()
                    )
                    for med in medications:
                        med.is_paid = True
                        med.payment_status = 'paid'
                        current_app.logger.info(f"Marked Medication (ID: {med.id}) for service {svc.name} in Visit {tx.visit.id} as PAID.")

                    # c) Mark any Radiology under this visit with service_id == svc.id
                    # Removed .join(Consultation) to allow direct linking to Visit
                    radiology_orders = (
                        Radiology.query
                        .filter(
                            Radiology.visit_id == tx.visit.id,  # Direct link to Visit
                            Radiology.service_id == svc.id
                        )
                        .all()
                    )
                    for ro in radiology_orders:
                        ro.is_paid = True
                        ro.payment_status = 'paid'
                        current_app.logger.info(f"Marked Radiology (ID: {ro.id}) for service {svc.name} in Visit {tx.visit.id} as PAID.")
            # ──────────────────────────────────────────────────────────

        else:
            # 9) STK push failed at M-Pesa: mark transaction failed
            tx.status        = 'failed'
            tx.error_message = result_desc


        # Create SalesReport if it doesn't already exist for this transaction
        if not SalesReport.query.filter_by(transaction_id=tx.id).first():
            # Gather patient name from patient object
            patient = tx.visit.patient if tx.visit and tx.visit.patient else None
            patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown"
            invoice = Invoice.query.filter_by(visit_id=tx.visit.id).first()

            # Create the sales report record
            sales_report = SalesReport(
                patient_id=tx.visit.patient_id,
                patient_reg_no=patient.reg_no if patient else "",
                patient_name=patient_name,
                visit_id=tx.visit.id,
                transaction_id=tx.id,
                invoice_id=invoice.id if invoice else None,
                total_amount=tx.amount,
                payment_method='mpesa',
                receipt_number=tx.receipt_number,
                served_by=tx.served_by if hasattr(tx, 'served_by') else None,
                patient_category=tx.visit.patient_category,
                visit_type_category=tx.visit.visit_type_category,
                sale_date=datetime.utcnow()  # or use tx.paid_at if set
            )
            db.session.add(sales_report)
            db.session.flush()  # to get sales_report.id

            # Add items for each service in the transaction
            for svc in tx.services:
                # Determine department (service.category)
                department = svc.category
                # For each service, there may be multiple items (e.g., multiple medications)
                # We'll collect all relevant instances paid under this transaction.
                # For simplicity, we'll create one item per service, but if you need per‑instance,
                # you can query Medication/LabTest/Radiology filtered by visit and service.
                # We'll also link to the specific instance if possible.

                # For medications
                if department.lower() == 'pharmacy':
                    meds = Medication.query.filter_by(visit_id=tx.visit.id, service_id=svc.id, is_paid=True).all()
                    for med in meds:
                        price = med.price if med.price is not None else svc.price
                        if med.price is None:
                            current_app.logger.warning(f"Medication #{med.id} had NULL price; using service price {price}")
                        quantity = med.quantity or 1
                        item = SalesReportItem(
                            sales_report_id=sales_report.id,
                            service_id=svc.id,
                            service_name=svc.name,
                            department=department,
                            quantity=quantity,
                            unit_price=price,
                            total_price=price * quantity,
                            medication_id=med.id
                        )
                        db.session.add(item)

                # For laboratory
                elif department == 'Laboratory':
                    labs = LabTest.query.filter_by(visit_id=tx.visit.id, service_id=svc.id, is_paid=True).all()
                    for lab in labs:
                        price = lab.price if lab.price is not None else svc.price
                        if lab.price is None:
                            current_app.logger.warning(f"LabTest #{lab.id} had NULL price; using service price {price}")
                        item = SalesReportItem(
                            sales_report_id=sales_report.id,
                            service_id=svc.id,
                            service_name=svc.name,
                            department=department,
                            quantity=1,
                            unit_price=price,
                            total_price=price,
                            lab_test_id=lab.id
                        )
                        db.session.add(item)

                # For radiology
                elif department.lower() == 'radiology':
                    rads = Radiology.query.filter_by(visit_id=tx.visit.id, service_id=svc.id, is_paid=True).all()
                    for rad in rads:
                        price = rad.price if rad.price is not None else svc.price
                        if rad.price is None:
                            current_app.logger.warning(f"Radiology #{rad.id} had NULL price; using service price {price}")
                        item = SalesReportItem(
                            sales_report_id=sales_report.id,
                            service_id=svc.id,
                            service_name=svc.name,
                            department=department,
                            quantity=1,
                            unit_price=price,
                            total_price=price,
                            radiology_id=rad.id
                        )
                        db.session.add(item)
                else:
                    # Fallback: generic item
                    item = SalesReportItem(
                        sales_report_id=sales_report.id,
                        service_id=svc.id,
                        service_name=svc.name,
                        department=department,
                        quantity=1,
                        unit_price=svc.price,
                        total_price=svc.price
                    )
                    db.session.add(item)

            # Optional: log creation
            current_app.logger.info(f"SalesReport {sales_report.id} created for transaction {tx.id}")
        # --- Credit the Paybill Cash Account ---
        paybill_account = CashAccount.query.filter_by(account_type='paybill', is_active=True).first()

        if paybill_account:
            # Create cash transaction instance with all fields except transaction_ref
            cash_tx = CashTransaction(
                transaction_type='deposit',
                amount=tx.amount,
                description=f"M-Pesa payment from {tx.phone} - Receipt: {tx.receipt_number}",
                dest_cash_account_id=paybill_account.id,
                source_transaction_id=tx.id,
                status='completed',
                completed_at=datetime.utcnow()
            )
            # Generate reference after transaction_type is set
            cash_tx.transaction_ref = cash_tx.generate_ref()
            db.session.add(cash_tx)

            # Update cash account balance
            paybill_account.current_balance += tx.amount
            db.session.add(paybill_account)

            current_app.logger.info(f"Paybill account {paybill_account.name} credited with {tx.amount}")
        else:
            current_app.logger.warning("No active paybill cash account found. Money not recorded in cash account.")
        db.session.commit()
        return jsonify({"status": "success"}), 200

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Database error in mpesa_callback")
        return jsonify({"status": "error", "message": "Database error"}), 500

    except Exception as e:
        current_app.logger.exception("M-Pesa callback error")
        return jsonify({"status": "error", "message": str(e)}), 500



@patients_web_bp.route('/triage', methods=['GET'])
def triage():
    # Define the visit types that are considered "walk-in"
    walk_in_visit_types = ['walk_in_lab', 'walk_in_rad', 'walk_in_pharm']

    # Load patient + services relationships in one go
    # Filter out walk-in patients directly in the query
    triage_visits = (
        Visit.query
        .filter_by(visit_status='in_progress', current_position='triage')
        .filter(
            # Exclude visits where the visit_type_category is in the walk_in_visit_types list
            ~Visit.visit_type_category.in_(walk_in_visit_types)
        )
        .options(
            joinedload(Visit.patient),
            subqueryload(Visit.services)
        )
        .order_by(Visit.visit_date.asc())
        .all()
    )
    
    patients = []
    for visit in triage_visits:
        patients.append({
            'reg_no': visit.patient.reg_no,
            'first_name': visit.patient.first_name,
            'last_name': visit.patient.last_name,
            'age': visit.patient.age,
            'arrival_time': visit.visit_date,
            'priority': visit.priority if hasattr(visit, 'priority') else None,
            'services': [svc.name for svc in visit.services],
            'visit_type': visit.visit_type_category, # Still good to have for internal debugging or future use
            'other_details': visit.visit_type_other_details 
        })
    
    # You no longer need to pass 'current_filter' if there's no frontend filter control for this exclusion
    return render_template('triage.html', patients=patients)



# Add these routes in your patients/routes.py

@patients_web_bp.route('/vitals/<reg_no>', methods=['GET'])
def vitals(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    return render_template('vitals.html', patient=patient)

@patients_web_bp.route('/edit-patient/<reg_no>', methods=['GET'])
def edit_patient(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    return render_template('edit_patient.html', patient=patient)

@patients_web_bp.route('/patient/<reg_no>', methods=['GET'])
def view_patient(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    return render_template('view_patient.html', patient=patient)

@patients_web_bp.route('/edit-patient/<patient_id>', methods=['GET'])
def edit_patient_details(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    return render_template('edit_patient.html', patient=patient)

@patients_web_bp.route('/patient/<patient_id>', methods=['GET'])
def view_patient_details(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    return render_template('view_patient.html', patient=patient)


@patients_web_bp.route('/api/vitals/<reg_no>', methods=['GET', 'POST'])
def api_vitals(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}

        # Determine if pediatric
        is_pediatric = patient.age <= 5

        # Required fields
        if is_pediatric:
            required_fields = ['weight', 'temperature', 'resp_rate']
        else:
            required_fields = [
                'temperature', 'heart_rate', 'bp_systolic', 'bp_diastolic',
                'spo2', 'resp_rate', 'pain_score'
            ]

        # Validate required fields
        for fld in required_fields:
            if fld not in data:
                return jsonify({'message': f'Missing field {fld}'}), 400

        # Find in-progress visit
        visit = (
            Visit.query
            .filter_by(patient_id=patient.id, visit_status='in_progress')
            .order_by(Visit.visit_date.desc())
            .first()
        )

        # Create vitals record
        vit = Vitals(
            patient_id = patient.id,
            visit_id   = visit.id if visit else None,
            temperature = float(data['temperature']),
            resp_rate   = int(data['resp_rate']),
            notes       = data.get('notes')
        )

        if is_pediatric:
            vit.weight = float(data['weight'])
            vit.muac   = float(data.get('muac', 0))
            vit.heart_rate = 0
            vit.bp_systolic = 0
            vit.bp_diastolic = 0
            vit.spo2 = 0
            vit.pain_score = 0
            vit.height = 0
            vit.bmi = 0

        else:
            vit.weight     = float(data['weight'])
            vit.height     = float(data['height'])
            vit.bmi        = float(data.get('bmi', 0))
            vit.heart_rate = int(data['heart_rate'])
            vit.bp_systolic= int(data['bp_systolic'])
            vit.bp_diastolic=int(data['bp_diastolic'])
            vit.spo2       = int(data['spo2'])
            vit.pain_score = int(data['pain_score'])
            # Medical history can be handled in a separate table or as JSON
            vit.allergy_food        = data.get('allergy_food')
            vit.allergy_drugs       = data.get('allergy_drugs')
            vit.chronic_conditions  = data.get('chronic_conditions')  # maybe JSON
            vit.current_medications = data.get('current_medications')

        db.session.add(vit)
        db.session.flush()

        # TB screening only for non-pediatric patients if needed
        if not is_pediatric:
            def parse_int_or_none(key):
                val = data.get(key)
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    return None
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return None

            tb = TbScreening(
                vitals_id          = vit.id,
                cough_duration     = parse_int_or_none('cough_duration'),
                fever              = data.get('fever', 'no'),
                fever_duration     = parse_int_or_none('fever_duration'),
                night_sweats       = data.get('night_sweats', 'no'),
                weight_loss_flag   = data.get('weight_loss_flag', 'no'),
                weight_loss_amount = parse_int_or_none('weight_loss_amount'),
                hemoptysis         = data.get('hemoptysis', 'no'),
                hiv_status         = data.get('hiv_status', 'unknown'),
                diabetes           = data.get('diabetes', 'no'),
                prior_tb           = data.get('prior_tb', 'no'),
                prior_tb_year      = parse_int_or_none('prior_tb_year'),
                household_contact  = data.get('household_contact', 'no'),
                smoking_history    = data.get('smoking_history', 'never'),
                alcohol_use        = data.get('alcohol_use', 'none')
            )
            db.session.add(tb)

        if visit:
            visit.current_position = 'consultation'
            db.session.add(visit)

        db.session.commit()

        resp = vit.to_dict()
        resp['visit_id'] = visit.id if visit else None
        return jsonify(resp), 201

    # ===== GET: fetch vitals =====
    recent_n = request.args.get('recent', type=int)
    query = Vitals.query.filter_by(patient_id=patient.id).order_by(Vitals.recorded_at.desc())
    if recent_n:
        query = query.limit(recent_n)
    records = query.all()
    return jsonify([v.to_dict() for v in records]), 200



@patients_web_bp.route('/api/get/vitals/<reg_no>', methods=['GET'])
def vitals_view(reg_no):
    patient = Patient.query.filter_by(reg_no=reg_no).first_or_404()
    return render_template('vitals.html', patient=patient)


@patients_web_bp.route('/api/vitals/recent', methods=['GET'])
def api_recent_vitals():
    """
    Returns the last N vitals *for all patients*,
    default N=5 or ?limit=10 etc.
    """
    limit = request.args.get('limit', type=int, default=5)
    # pull the latest recordings across all patients:
    recents = (
        Vitals.query
              .order_by(Vitals.recorded_at.desc())
              .limit(limit)
              .all()
    )
    # to_dict() already includes patient_name & reg_no
    return jsonify([v.to_dict() for v in recents])


@patients_web_bp.route('/patients')
def view_patients():
    # pagination parameters
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.args.get('per_page', 25))  # default 25 rows per page
    except (ValueError, TypeError):
        per_page = 25

    # base query
    base_q = Patient.query

    # ordering (by last_name then first_name)
    base_q = base_q.order_by(Patient.last_name.asc(), Patient.first_name.asc())

    # paginate
    pagination = base_q.paginate(page=page, per_page=per_page, error_out=False)
    patients = pagination.items

    # summary counts (do simple fast queries)
    total_patients = db.session.query(db.func.count(Patient.id)).scalar()
    insured_count = db.session.query(db.func.count(Patient.id)).filter(Patient.insurance_provider.isnot(None)).scalar()
    minors_count = db.session.query(db.func.count(Patient.id)).filter(Patient.age < 18).scalar()
    seniors_count = db.session.query(db.func.count(Patient.id)).filter(Patient.age >= 60).scalar()

    return render_template(
        'view_patients.html',
        patients=patients,
        pagination=pagination,
        total_patients=total_patients,
        insured_count=insured_count,
        minors_count=minors_count,
        seniors_count=seniors_count,
        per_page=per_page,
        now=datetime.utcnow()
    )


    
    
    
