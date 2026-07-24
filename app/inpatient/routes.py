# app/inpatient/routes.py
import json
import uuid

from flask import render_template, request, redirect, url_for, flash, abort, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.auth.models import Role, User
from app.inpatient import bp

from datetime import datetime, timedelta

from app.inpatient.forms import AdmissionForm, GeneralSettingsForm, InpatientStockRequestForm, InventoryItemForm, SettingForm, WardBedFeeForm
from app.inpatient.models import Bed, InpatientAdmission, InpatientChargeSheet, InpatientClosedFile, InpatientDeposit, InpatientDischarge, InpatientInvoice, InpatientInvoiceItem, InpatientSHAClaim, InpatientSetting, InpatientTreatment, InpatientWardShift, Substore, SubstoreInventory, Ward, WardBedFee
from app.patients.models import Patient, Service, Visit
# app/inpatient/routes.py
from sqlalchemy.orm import joinedload
from app.store.models import Stock, StockRequest, BulkRequest  # adjust if model location differs


def parse_int_or_none(value):
    """Safely convert a value to int or return None."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
@bp.route('/')
@bp.route('/dashboard')
@login_required
def dashboard():
    """Main inpatient dashboard."""
    if not current_user.has_privilege('inpatient:dashboard'):
        abort(403)
    # Fetch some stats
    total_admissions = InpatientAdmission.query.filter_by(status='active').count()
    discharged_today = InpatientDischarge.query.filter(
        db.func.date(InpatientDischarge.discharge_date) == datetime.utcnow().date()
    ).count()
    pending_claims = InpatientSHAClaim.query.filter_by(status='submitted').count()
    return render_template('inpatient/dashboard.html',
                           total_admissions=total_admissions,
                           discharged_today=discharged_today,
                           pending_claims=pending_claims)






# ----------------------------------------------------------------------
# Patient Search (AJAX)
# ----------------------------------------------------------------------
@bp.route('/patient-search')
@login_required
def patient_search():
    """Return JSON list of patients matching search term."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    # Search by reg_no, first_name, last_name, phone
    patients = Patient.query.filter(
        db.or_(
            Patient.reg_no.ilike(f'%{q}%'),
            Patient.first_name.ilike(f'%{q}%'),
            Patient.last_name.ilike(f'%{q}%'),
            Patient.phone.ilike(f'%{q}%')
        )
    ).limit(15).all()

    results = [{
        'id': p.id,
        'reg_no': p.reg_no,
        'full_name': p.full_name,
        'gender': p.gender,
        'age': p.age,
        'phone': p.phone,
        'email': p.email,
        'insurance': p.insurance_provider or 'Cash',
        'insurance_number': p.insurance_number or ''
    } for p in patients]

    return jsonify(results)

# app/inpatient/routes.py

from sqlalchemy import or_

@bp.route('/admission', methods=['GET', 'POST'])
@login_required
def admission_form():
    """Patient Admission – table view + AJAX admission."""
    if not current_user.has_privilege('inpatient:admission'):
        abort(403)

    # ----- GET: render the patient table -----
    if request.method == 'GET':
        patients = Patient.query.order_by(Patient.last_name, Patient.first_name).all()
        patient_data = []
        for p in patients:
            active_admission = InpatientAdmission.query.filter_by(
                patient_id=p.id, status='active'
            ).first()
            patient_data.append({
                'id': p.id,
                'reg_no': p.reg_no,
                'full_name': p.full_name,
                'age': p.age,
                'gender': p.gender,
                'phone': p.phone,
                'insurance': p.insurance_provider or 'Cash',
                'moh_ip': p.moh_ip_number,
                'is_admitted': active_admission is not None,
                'admission_id': active_admission.id if active_admission else None
            })
        wards = Ward.query.order_by(Ward.name).all()
        doctors = User.query.join(User.roles).filter(Role.name == 'doctor').order_by(User.full_name).all()
        nurses = User.query.join(User.roles).filter(Role.name == 'nurse').order_by(User.full_name).all()
        return render_template(
            'admission_form.html',
            patients=patient_data,
            wards=wards,
            doctors=doctors,
            nurses=nurses
        )

    # ----- POST: AJAX admission (JSON) -----
    if not request.is_json:
        return jsonify({'error': 'JSON required'}), 400

    data = request.get_json()
    patient_id = data.get('patient_id')
    ward_id = data.get('ward_id')
    bed_id = data.get('bed_id') or None
    diagnosis = data.get('diagnosis', '').strip()
    doctor_id = data.get('doctor_id')
    nurse_id = data.get('nurse_id') or None
    admission_date = data.get('admission_date')

    # Validation
    if not all([patient_id, ward_id, doctor_id, diagnosis]):
        return jsonify({'error': 'Missing required fields'}), 400

    patient = Patient.query.get(patient_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    if not patient.moh_ip_number:
        return jsonify({'error': 'Patient does not have a MOH IP number. Please update patient record first.'}), 400

    existing = InpatientAdmission.query.filter_by(patient_id=patient_id, status='active').first()
    if existing:
        return jsonify({'error': 'Patient already has an active admission'}), 400

    try:
        if admission_date:
            adm_date = datetime.fromisoformat(admission_date.replace('Z', '+00:00'))
        else:
            adm_date = datetime.utcnow()
    except:
        adm_date = datetime.utcnow()

    # ── 1. Create admission ──
    admission = InpatientAdmission(
        patient_id=patient_id,
        ward_id=ward_id,
        bed_id=bed_id,
        diagnosis=diagnosis,
        admitting_doctor_id=doctor_id,
        nurse_id=nurse_id,
        admission_date=adm_date,
        status='active',
        file_number=f"IP-{adm_date.strftime('%Y%m%d')}-{InpatientAdmission.query.count()+1:04d}"
    )
    db.session.add(admission)
    db.session.flush()  # to get admission.id

    # ── 2. Get fees ──
    ward_fee = WardBedFee.query.filter_by(ward_id=ward_id).first()
    bed_admission_fee = ward_fee.admission_fee if ward_fee else 0.0
    daily_bed_fee = ward_fee.daily_bed_fee if ward_fee else 0.0
    doctor_fee_setting = InpatientSetting.query.filter_by(key='default_admission_fee').first()
    doctor_fee = float(doctor_fee_setting.value) if doctor_fee_setting else 0.0

    # ── 3. Store fees on admission ──
    admission.daily_bed_fee_rate = daily_bed_fee
    admission.bed_admission_fee = bed_admission_fee
    admission.doctor_admission_fee = doctor_fee

    # ── 4. Create Proforma Invoice ──
    invoice_number = f"PRO-{adm_date.strftime('%Y%m%d')}-{InpatientInvoice.query.count()+1:04d}"
    invoice = InpatientInvoice(
        admission_id=admission.id,
        invoice_number=invoice_number,
        invoice_type='proforma',           # ✅ Proforma estimate
        subtotal=bed_admission_fee + doctor_fee,
        discount=0.0,
        tax=0.0,
        grand_total=bed_admission_fee + doctor_fee,
        paid_amount=0.0,
        insurance_claim_amount=0.0,
        patient_payable=bed_admission_fee + doctor_fee,
        payment_status='estimated',        # ✅ Not yet a final bill
        issued_date=adm_date,
        due_date=adm_date + timedelta(days=30),
        patient_name=patient.full_name,
        patient_reg_no=patient.reg_no,
        patient_phone=patient.phone,
        patient_insurance=patient.insurance_provider,
        patient_insurance_no=patient.insurance_number
    )
    db.session.add(invoice)
    db.session.flush()

    # Add line items
    invoice.add_item(description='Admission Fee (Bed)', unit_price=bed_admission_fee, quantity=1)
    invoice.add_item(description='Doctor Admission Fee', unit_price=doctor_fee, quantity=1)

    # ── 5. Mark bed as occupied ──
    if bed_id:
        bed = Bed.query.get(bed_id)
        if bed:
            bed.is_occupied = True

    # ── 6. Create or update Visit ──
    visit = Visit.query.filter_by(patient_id=patient_id).order_by(Visit.created_at.desc()).first()
    if not visit:
        visit = Visit(
            patient_id=patient_id,
            visit_status='admitted',
            is_walk_in=False,
            visit_type_category='inpatient',
            visit_date=adm_date
        )
        db.session.add(visit)
    else:
        if visit.visit_status != 'admitted':
            visit.visit_status = 'admitted'
            visit.visit_type_category = 'inpatient'
            visit.visit_date = adm_date
            visit.updated_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Patient {patient.full_name} admitted successfully (File No: {admission.file_number})',
        'admission_id': admission.id,
        'visit_id': visit.id,
        'invoice_id': invoice.id
    }), 201


# ── API: Get available beds for a ward (used by modal) ──
@bp.route('/api/beds-by-ward', methods=['GET'])
@login_required
def get_beds_by_ward():
    ward_id = request.args.get('ward_id', type=int)
    if not ward_id:
        return jsonify([])
    beds = Bed.query.filter_by(ward_id=ward_id, is_occupied=False).order_by(Bed.bed_number).all()
    return jsonify([{'id': b.id, 'bed_number': b.bed_number} for b in beds])


@bp.route('/get-beds')
@login_required
def get_beds():
    ward_id = request.args.get('ward_id', type=int)
    if not ward_id:
        return jsonify([])
    beds = Bed.query.filter_by(ward_id=ward_id, is_occupied=False).all()
    return jsonify([{'id': b.id, 'bed_number': b.bed_number} for b in beds])

def get_or_create_visit(patient_id):
    """Return the most recent visit for a patient, or create a new one."""
    visit = Visit.query.filter_by(patient_id=patient_id).order_by(Visit.created_at.desc()).first()
    if not visit:
        visit = Visit(
            patient_id=patient_id,
            visit_status='admitted',
            is_walk_in=False,
            visit_type_category='inpatient'
        )
        db.session.add(visit)
        db.session.commit()
    return visit



# ── Page: list admitted patients for treatment ──
@bp.route('/treatment', methods=['GET'])
@login_required
def treatment_form():
    if not current_user.has_privilege('inpatient:treatment'):
        abort(403)

    # Fetch all active admissions with patient, ward, bed
    admissions = InpatientAdmission.query.filter_by(status='active')\
        .join(Patient)\
        .join(Ward)\
        .options(
            db.joinedload(InpatientAdmission.patient),
            db.joinedload(InpatientAdmission.ward),
            db.joinedload(InpatientAdmission.bed)
        ).all()

    admitted = []

    for adm in admissions:
        visit = get_or_create_visit(adm.patient_id)
        admitted.append({
            'id': adm.id,
            'patient_id': adm.patient_id,
            'reg_no': adm.patient.reg_no,
            'full_name': adm.patient.full_name,
            'ward_id': adm.ward_id,
            'ward_name': adm.ward.name,
            'bed_number': adm.bed.bed_number if adm.bed else None,
            'diagnosis': adm.diagnosis,
            'visit_id': visit.id,
            'admission_date': adm.admission_date.isoformat()
        })

    # Get staff (doctors, nurses) for treatment form
    doctors = User.query.join(User.roles).filter(Role.name == 'doctor').order_by(User.full_name).all()
    wards = Ward.query.order_by(Ward.name).all()

    return render_template(
        'treatment_form.html',
        admitted=admitted,
        wards=wards,
        doctors=doctors
    )


# ── API: filter admitted patients for treatment ──
# ── API: filter admitted patients for treatment ──
@bp.route('/api/treatment-patients', methods=['GET'])
@login_required
def get_treatment_patients():
    if not current_user.has_privilege('inpatient:treatment'):
        return jsonify({'error': 'Unauthorized'}), 403

    search = request.args.get('search', '').strip()
    ward_id = request.args.get('ward_id', type=int)

    query = InpatientAdmission.query.filter_by(status='active')\
        .join(Patient)\
        .join(Ward)

    if search:
        query = query.filter(
            or_(
                Patient.reg_no.ilike(f'%{search}%'),
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                Patient.phone.ilike(f'%{search}%')
            )
        )
    if ward_id:
        query = query.filter(InpatientAdmission.ward_id == ward_id)

    admissions = query.options(
        db.joinedload(InpatientAdmission.patient),
        db.joinedload(InpatientAdmission.ward),
        db.joinedload(InpatientAdmission.bed)
    ).all()

    result = []
    for adm in admissions:
        visit = get_or_create_visit(adm.patient_id)   # <--- ensure visit exists
        result.append({
            'id': adm.id,
            'patient_id': adm.patient_id,
            'reg_no': adm.patient.reg_no,
            'full_name': adm.patient.full_name,
            'ward_id': adm.ward_id,
            'ward_name': adm.ward.name,
            'bed_number': adm.bed.bed_number if adm.bed else None,
            'diagnosis': adm.diagnosis,
            'admission_date': adm.admission_date.isoformat(),
            'visit_id': visit.id                      # <--- include visit_id
        })


# ── POST: record a new treatment ──
@bp.route('/api/treatments', methods=['POST'])
@login_required
def add_treatment():
    if not current_user.has_privilege('inpatient:treatment'):
        return jsonify({'error': 'Unauthorized'}), 403

    if not request.is_json:
        return jsonify({'error': 'JSON required'}), 400

    data = request.get_json()
    admission_id = data.get('admission_id')
    treatment_type = data.get('treatment_type', '').strip()
    description = data.get('description', '').strip()
    notes = data.get('notes', '').strip()
    performed_by_id = data.get('performed_by_id')  # optional

    if not admission_id or not treatment_type:
        return jsonify({'error': 'Admission ID and treatment type are required'}), 400

    # Verify admission exists and is active
    admission = InpatientAdmission.query.get(admission_id)
    if not admission or admission.status != 'active':
        return jsonify({'error': 'Invalid or inactive admission'}), 404

    # Optional: validate performed_by if provided
    if performed_by_id:
        performer = User.query.get(performed_by_id)
        if not performer:
            return jsonify({'error': 'Performer not found'}), 404

    treatment = InpatientTreatment(
        admission_id=admission_id,
        treatment_type=treatment_type,
        description=description,
        notes=notes,
        performed_by_id=performed_by_id or None,
        treatment_date=datetime.utcnow()
    )
    db.session.add(treatment)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Treatment recorded successfully',
        'treatment': {
            'id': treatment.id,
            'treatment_type': treatment.treatment_type,
            'description': treatment.description,
            'notes': treatment.notes,
            'performed_by': treatment.performed_by.full_name if treatment.performed_by else None,
            'treatment_date': treatment.treatment_date.isoformat()
        }
    }), 201
    
    
    
# ── Page: list admitted patients ──
@bp.route('/ward-bed-shift', methods=['GET'])
@login_required
def ward_bed_shift():
    if not current_user.has_privilege('inpatient:ward_bed_shift'):
        abort(403)

    # Fetch all active admissions with patient, ward, bed
    admissions = InpatientAdmission.query.filter_by(status='active')\
        .join(Patient)\
        .join(Ward)\
        .options(
            db.joinedload(InpatientAdmission.patient),
            db.joinedload(InpatientAdmission.ward),
            db.joinedload(InpatientAdmission.bed)
        ).all()

    admitted = []
    for adm in admissions:
        admitted.append({
            'id': adm.id,
            'patient_id': adm.patient_id,
            'reg_no': adm.patient.reg_no,
            'full_name': adm.patient.full_name,
            'ward_id': adm.ward_id,
            'ward_name': adm.ward.name,
            'bed_id': adm.bed_id,
            'bed_number': adm.bed.bed_number if adm.bed else None,
            'diagnosis': adm.diagnosis,
            'admission_date': adm.admission_date.isoformat()
        })

    wards = Ward.query.order_by(Ward.name).all()
    return render_template('ward_bed_shift.html',
                           admitted=admitted,
                           wards=wards)


# ── API: filter admitted patients ──
@bp.route('/api/admitted-patients', methods=['GET'])
@login_required
def get_admitted_patients():
    if not current_user.has_privilege('inpatient:ward_bed_shift'):
        return jsonify({'error': 'Unauthorized'}), 403

    search = request.args.get('search', '').strip()
    ward_id = request.args.get('ward_id', type=int)

    query = InpatientAdmission.query.filter_by(status='active')\
        .join(Patient)\
        .join(Ward)

    if search:
        query = query.filter(
            or_(
                Patient.reg_no.ilike(f'%{search}%'),
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                Patient.phone.ilike(f'%{search}%')
            )
        )
    if ward_id:
        query = query.filter(InpatientAdmission.ward_id == ward_id)

    admissions = query.options(
        db.joinedload(InpatientAdmission.patient),
        db.joinedload(InpatientAdmission.ward),
        db.joinedload(InpatientAdmission.bed)
    ).all()

    result = [{
        'id': adm.id,
        'patient_id': adm.patient_id,
        'reg_no': adm.patient.reg_no,
        'full_name': adm.patient.full_name,
        'ward_id': adm.ward_id,
        'ward_name': adm.ward.name,
        'bed_id': adm.bed_id,
        'bed_number': adm.bed.bed_number if adm.bed else None,
        'diagnosis': adm.diagnosis,
        'admission_date': adm.admission_date.isoformat()
    } for adm in admissions]

    return jsonify(result), 200


# ── POST: perform shift ──
@bp.route('/ward-bed-shift', methods=['POST'])
@login_required
def perform_ward_bed_shift():
    if not current_user.has_privilege('inpatient:ward_bed_shift'):
        return jsonify({'error': 'Unauthorized'}), 403

    if not request.is_json:
        return jsonify({'error': 'JSON required'}), 400

    data = request.get_json()
    patient_id = data.get('patient_id')
    new_ward_id = data.get('ward_id')
    new_bed_id = data.get('bed_id')  # optional
    reason = data.get('reason', '').strip()

    if not patient_id or not new_ward_id:
        return jsonify({'error': 'Patient and new ward are required'}), 400

    # Get active admission
    admission = InpatientAdmission.query.filter_by(patient_id=patient_id, status='active').first()
    if not admission:
        return jsonify({'error': 'Patient has no active admission'}), 404

    old_ward_id = admission.ward_id
    old_bed_id = admission.bed_id

    # Check if moving to same ward and bed
    if old_ward_id == new_ward_id:
        if old_bed_id == new_bed_id or (old_bed_id is None and new_bed_id is None):
            return jsonify({'error': 'Patient is already in this bed'}), 400

    # If a new bed is provided, verify it exists and is free
    if new_bed_id:
        bed = Bed.query.get(new_bed_id)
        if not bed:
            return jsonify({'error': 'Bed not found'}), 404
        if bed.is_occupied:
            return jsonify({'error': 'Bed is already occupied'}), 400

    # Begin transaction
    try:
        # Free old bed if any
        if old_bed_id:
            old_bed = Bed.query.get(old_bed_id)
            if old_bed:
                old_bed.is_occupied = False

        # Update admission
        admission.ward_id = new_ward_id
        admission.bed_id = new_bed_id
        admission.updated_at = datetime.utcnow()

        # Mark new bed as occupied
        if new_bed_id:
            new_bed = Bed.query.get(new_bed_id)
            new_bed.is_occupied = True

        # Log the shift
        shift_log = InpatientWardShift(
            admission_id=admission.id,
            from_ward_id=old_ward_id,
            from_bed_id=old_bed_id,
            to_ward_id=new_ward_id,
            to_bed_id=new_bed_id,
            shift_date=datetime.utcnow(),
            reason=reason,
            shifted_by_id=current_user.id
        )
        db.session.add(shift_log)
        db.session.commit()

        # Get names for response
        new_ward_name = Ward.query.get(new_ward_id).name
        new_bed_number = Bed.query.get(new_bed_id).bed_number if new_bed_id else None

        return jsonify({
            'success': True,
            'message': f'Patient shifted to {new_ward_name}',
            'admission': {
                'ward_id': new_ward_id,
                'ward_name': new_ward_name,
                'bed_id': new_bed_id,
                'bed_number': new_bed_number
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ── GET: list admitted patients ──
@bp.route('/discharge', methods=['GET'])
@login_required
def discharge():
    if not current_user.has_privilege('inpatient:discharge'):
        abort(403)

    # Fetch all active admissions with patient, ward, bed
    admissions = InpatientAdmission.query.filter_by(status='active')\
        .join(Patient)\
        .options(
            db.joinedload(InpatientAdmission.patient),
            db.joinedload(InpatientAdmission.ward),
            db.joinedload(InpatientAdmission.bed)
        ).all()

    admitted_list = []
    for adm in admissions:
        admitted_list.append({
            'id': adm.id,
            'patient_id': adm.patient_id,
            'reg_no': adm.patient.reg_no,
            'full_name': adm.patient.full_name,
            'age': adm.patient.age,
            'gender': adm.patient.gender,
            'phone': adm.patient.phone,
            'admission_date': adm.admission_date.strftime('%d-%b-%Y'),
            'ward_name': adm.ward.name,
            'bed_number': adm.bed.bed_number if adm.bed else '—',
            'diagnosis': adm.diagnosis,
            'file_number': adm.file_number,
            'insurance': adm.patient.insurance_provider or 'Cash',
            'insurance_number': adm.patient.insurance_number or '',
            'address': f"{adm.patient.county or ''} {adm.patient.subcounty or ''} {adm.patient.ward or ''}",
            'next_of_kin': adm.patient.kin_name,
            'kin_phone': adm.patient.kin_phone,
            'moh_ip': adm.patient.moh_ip_number
        })

    return render_template('discharge.html', patients=admitted_list)


# ── API: get patient admission details for discharge modal ──
@bp.route('/api/admission/<int:admission_id>', methods=['GET'])
@login_required
def get_admission_details(admission_id):
    if not current_user.has_privilege('inpatient:discharge'):
        return jsonify({'error': 'Unauthorized'}), 403

    admission = InpatientAdmission.query.get_or_404(admission_id)
    if admission.status != 'active':
        return jsonify({'error': 'Patient is not active'}), 400

    return jsonify({
        'id': admission.id,
        'patient_id': admission.patient_id,
        'reg_no': admission.patient.reg_no,
        'full_name': admission.patient.full_name,
        'age': admission.patient.age,
        'sex': admission.patient.gender,
        'address': f"{admission.patient.county or ''} {admission.patient.subcounty or ''} {admission.patient.ward or ''}".strip(),
        'phone': admission.patient.phone,
        'admission_date': admission.admission_date.strftime('%d-%b-%Y'),
        'ward': admission.ward.name,
        'bed': admission.bed.bed_number if admission.bed else '—',
        'diagnosis': admission.diagnosis,
        'file_number': admission.file_number,
        'insurance': admission.patient.insurance_provider or 'Cash',
        'insurance_number': admission.patient.insurance_number or '',
        'next_of_kin': admission.patient.kin_name,
        'kin_phone': admission.patient.kin_phone,
        'moh_ip': admission.patient.moh_ip_number
    }), 200



@bp.route('/api/discharge', methods=['POST'])
@login_required
def process_discharge():
    if not current_user.has_privilege('inpatient:discharge'):
        return jsonify({'error': 'Unauthorized'}), 403

    if not request.is_json:
        return jsonify({'error': 'JSON required'}), 400

    data = request.get_json()
    admission_id = data.get('admission_id')
    if not admission_id:
        return jsonify({'error': 'Admission ID required'}), 400

    admission = InpatientAdmission.query.get(admission_id)
    if not admission or admission.status != 'active':
        return jsonify({'error': 'Invalid or inactive admission'}), 404

    # ── 1. Find or create final invoice ──
    proforma = InpatientInvoice.query.filter_by(admission_id=admission.id, invoice_type='proforma').first()
    invoice = None

    if proforma:
        # Convert proforma to final
        invoice = proforma
        invoice.invoice_type = 'final'
        invoice.payment_status = 'unpaid'  # or 'partially_paid' if deposits exist
        invoice.issued_date = datetime.utcnow()
    else:
        # Create a new final invoice if no proforma exists (fallback)
        invoice = InpatientInvoice(
            admission_id=admission.id,
            invoice_number=f"FIN-{datetime.utcnow().strftime('%Y%m%d')}-{InpatientInvoice.query.count()+1:04d}",
            invoice_type='final',
            patient_name=admission.patient.full_name,
            patient_reg_no=admission.patient.reg_no,
            patient_phone=admission.patient.phone,
            patient_insurance=admission.patient.insurance_provider,
            patient_insurance_no=admission.patient.insurance_number,
            subtotal=0,
            discount=0,
            tax=0,
            grand_total=0,
            patient_payable=0,
            payment_status='unpaid',
            issued_date=datetime.utcnow(),
            due_date=datetime.utcnow() + timedelta(days=30)
        )
        db.session.add(invoice)
        db.session.flush()

    # ── 2. Add daily bed fees ──
    admission_date = admission.admission_date
    discharge_date = datetime.utcnow()
    if admission_date.date() == discharge_date.date():
        days_stayed = 1  # At least one day
    else:
        days_stayed = (discharge_date.date() - admission_date.date()).days
        if days_stayed < 1:
            days_stayed = 1

    daily_fee = admission.daily_bed_fee_rate or 0.0
    if daily_fee > 0 and days_stayed > 0:
        # Check if a daily bed fee item already exists on the invoice
        existing_item = None
        for item in invoice.items:
            if "Daily Bed Fee" in item.description:
                existing_item = item
                break
        if existing_item:
            # Update existing item with new days and total
            existing_item.quantity = days_stayed
            existing_item.total = daily_fee * days_stayed
        else:
            invoice.add_item(
                description=f'Daily Bed Fee ({days_stayed} days @ {daily_fee:.2f}/day)',
                unit_price=daily_fee,
                quantity=days_stayed
            )

    # ── 3. Add any other charges from charge sheets (if not already added) ──
    for charge in admission.charge_sheets:
        # Check if this charge already exists as an invoice item (by charge_sheet_id)
        exists = any(item.charge_sheet_id == charge.id for item in invoice.items)
        if not exists:
            invoice.add_item(
                description=charge.service.name if charge.service else f"Charge (ID: {charge.id})",
                unit_price=charge.unit_price,
                quantity=charge.quantity,
                service_id=charge.service_id,
                charge_sheet_id=charge.id
            )

    # ── 4. Recalculate invoice totals ──
    invoice.calculate_totals()

    # Update patient payable and payment status
    total_deposits = InpatientDeposit.query.filter_by(admission_id=admission.id).with_entities(db.func.sum(InpatientDeposit.amount)).scalar() or 0
    invoice.paid_amount = total_deposits
    invoice.patient_payable = invoice.grand_total - total_deposits
    if invoice.patient_payable < 0:
        invoice.patient_payable = 0
    if invoice.paid_amount >= invoice.grand_total:
        invoice.payment_status = 'paid'
    elif invoice.paid_amount > 0:
        invoice.payment_status = 'partially_paid'
    else:
        invoice.payment_status = 'unpaid'

    db.session.commit()

    # ── 5. Create discharge record ──
    final_diagnosis = data.get('final_diagnosis', '').strip()
    history = data.get('history', '').strip()
    examination = data.get('examination', '').strip()
    investigations = data.get('investigations', '').strip()
    treatment_given = data.get('treatment_given', '').strip()
    patient_condition = data.get('patient_condition', '').strip()
    follow_up_clinic = data.get('follow_up_clinic', '').strip()
    advice = data.get('advice', '').strip()
    recommendations = data.get('recommendations', '').strip()
    doctor_name = data.get('doctor_name', '').strip()
    code = data.get('code', '').strip()
    kmpdc_no = data.get('kmpdc_no', '').strip()
    discharge_date_str = data.get('discharge_date', None)

    if not final_diagnosis or not doctor_name:
        return jsonify({'error': 'Final Diagnosis and Doctor Name are required'}), 400

    discharge = InpatientDischarge(
        admission_id=admission.id,
        discharge_date=datetime.strptime(discharge_date_str, '%Y-%m-%d').date() if discharge_date_str else datetime.utcnow().date(),
        final_diagnosis=final_diagnosis,
        history=history,
        examination=examination,
        investigations=investigations,
        treatment_given=treatment_given,
        patient_condition=patient_condition,
        follow_up_clinic=follow_up_clinic,
        advice=advice,
        recommendations=recommendations,
        doctor_name=doctor_name,
        code=code,
        kmpdc_no=kmpdc_no,
        discharged_by_id=current_user.id
    )
    db.session.add(discharge)

    # Update admission status and free bed
    admission.status = 'discharged'
    if admission.bed_id:
        bed = Bed.query.get(admission.bed_id)
        if bed:
            bed.is_occupied = False

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Patient {admission.patient.full_name} discharged successfully.',
        'discharge_id': discharge.id,
        'invoice_id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'total_amount': invoice.grand_total,
        'deposits': total_deposits,
        'balance': invoice.patient_payable
    }), 201



@bp.route('/closed-files')
@login_required
def closed_files():
    if not current_user.has_privilege('inpatient:closed_files'):
        abort(403)

    # Get all closed files
    closed_files = InpatientClosedFile.query.order_by(InpatientClosedFile.closed_date.desc()).all()

    # Build data with additional info
    files_data = []
    for cf in closed_files:
        admission = cf.admission
        patient = admission.patient
        discharge = InpatientDischarge.query.filter_by(admission_id=admission.id).first()
        invoices = InpatientInvoice.query.filter_by(admission_id=admission.id).all()
        
        # Get visit for this admission (the one created during admission)
        visit = Visit.query.filter_by(patient_id=patient.id, visit_status='admitted').order_by(Visit.created_at.desc()).first()
        # If not found, try getting any visit around admission date
        if not visit:
            visit = Visit.query.filter_by(patient_id=patient.id).order_by(Visit.created_at.desc()).first()
        
        # Theatre notes for this visit (if any)
        theatre_notes = None
        if visit:
            theatre_notes = TheatreNotes.query.filter_by(visit_id=visit.id).first()
        
        # Treatment plan for this visit (if any)
        treatment_plan = None
        if visit:
            treatment_plan = InpatientTreatmentPlan.query.filter_by(visit_id=visit.id).first()

        files_data.append({
            'closed_file': cf,
            'admission': admission,
            'patient': patient,
            'discharge': discharge,
            'invoices': invoices,
            'visit': visit,
            'theatre_notes': theatre_notes,
            'treatment_plan': treatment_plan,
            'ward': admission.ward.name,
            'file_number': admission.file_number,
            'admission_date': admission.admission_date.strftime('%d-%b-%Y'),
            'closed_date': cf.closed_date.strftime('%d-%b-%Y'),
            'closed_by': cf.closed_by.full_name if cf.closed_by else 'System',
            'reason': cf.reason
        })

    return render_template('closed_files.html', files=files_data)

# ----------------------------------------------------------------------
# Pharmacy Subgroup
# ----------------------------------------------------------------------
@bp.route('/drugs-order', methods=['GET', 'POST'])
@login_required
def drugs_order():
    """Drugs Order Form."""
    if not current_user.has_privilege('inpatient:drugs_order'):
        abort(403)
    form = DrugOrderForm()
    if form.validate_on_submit():
        # Save order
        flash('Drug order created.', 'success')
        return redirect(url_for('inpatient_web_bp.dashboard'))
    return render_template('inpatient/drugs_order.html', form=form)

@bp.route('/discharge-medication', methods=['GET', 'POST'])
@login_required
def discharge_medication():
    """Discharge Medication."""
    if not current_user.has_privilege('inpatient:discharge_medication'):
        abort(403)
    # Logic here
    return render_template('inpatient/discharge_medication.html')

@bp.route('/pharmacy-dispense', methods=['GET', 'POST'])
@login_required
def pharmacy_dispense():
    """Pharmacy Dispense."""
    if not current_user.has_privilege('inpatient:pharmacy_dispense'):
        abort(403)
    # Logic for dispensing medication
    return render_template('inpatient/pharmacy_dispense.html')

@bp.route('/stock-return', methods=['GET', 'POST'])
@login_required
def stock_return():
    """Stock Return."""
    if not current_user.has_privilege('inpatient:stock_return'):
        abort(403)
    return render_template('inpatient/stock_return.html')

# ----------------------------------------------------------------------
# Laboratory Subgroup
# ----------------------------------------------------------------------
@bp.route('/laboratory')
@login_required
def laboratory():
    """Laboratory."""
    if not current_user.has_privilege('inpatient:laboratory'):
        abort(403)
    return render_template('inpatient/laboratory.html')

@bp.route('/investigations', methods=['GET', 'POST'])
@login_required
def investigations():
    """Other Investigations Request."""
    if not current_user.has_privilege('inpatient:investigations'):
        abort(403)
    return render_template('inpatient/investigations.html')

# ----------------------------------------------------------------------
# Billing & Claims Subgroup
# ----------------------------------------------------------------------
@bp.route('/proforma-invoice')
@login_required
def proforma_invoice():
    if not current_user.has_privilege('inpatient:proforma_invoice'):
        abort(403)

    proformas = InpatientInvoice.query.filter_by(invoice_type='proforma').order_by(InpatientInvoice.created_at.desc()).all()

    # Add deposit totals
    for inv in proformas:
        total_deposited = InpatientDeposit.query.filter_by(admission_id=inv.admission_id).with_entities(db.func.sum(InpatientDeposit.amount)).scalar() or 0
        inv.total_deposited = total_deposited
        inv.balance = inv.grand_total - total_deposited

    total_proformas = len(proformas)
    total_amount = sum(p.grand_total for p in proformas) if proformas else 0
    unpaid_count = sum(1 for p in proformas if p.payment_status == 'estimated')

    admitted_without_proforma = []
    admitted = InpatientAdmission.query.filter_by(status='active').all()
    for adm in admitted:
        existing = InpatientInvoice.query.filter_by(admission_id=adm.id, invoice_type='proforma').first()
        if not existing:
            admitted_without_proforma.append(adm)

    return render_template(
        'proforma_invoice.html',
        proformas=proformas,
        total_proformas=total_proformas,
        total_amount=total_amount,
        unpaid_count=unpaid_count,
        admitted_without_proforma=admitted_without_proforma
    )


@bp.route('/api/invoice/<int:invoice_id>')
@login_required
def get_invoice_api(invoice_id):
    if not current_user.has_privilege('inpatient:proforma_invoice'):
        return jsonify({'error': 'Unauthorized'}), 403

    invoice = InpatientInvoice.query.get_or_404(invoice_id)
    admission = invoice.admission

    deposits = InpatientDeposit.query.filter_by(admission_id=admission.id).all()
    total_deposited = sum(d.amount for d in deposits)

    return jsonify({
        'invoice_number': invoice.invoice_number,
        'issued_date': invoice.issued_date.isoformat(),
        'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
        'patient_name': invoice.patient_name,
        'patient_reg_no': invoice.patient_reg_no,
        'patient_phone': invoice.patient_phone,
        'admission_date': admission.admission_date.isoformat(),
        'ward': admission.ward.name if admission.ward else None,
        'doctor': admission.admitting_doctor.full_name if admission.admitting_doctor else None,
        'items': [{
            'description': item.description,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total': float(item.total)
        } for item in invoice.items],
        'subtotal': float(invoice.subtotal),
        'discount': float(invoice.discount),
        'tax': float(invoice.tax),
        'grand_total': float(invoice.grand_total),
        'patient_payable': float(invoice.patient_payable),
        'payment_status': invoice.payment_status,
        'total_deposited': total_deposited,
        'balance': invoice.grand_total - total_deposited
    }), 200

# ── API: Generate proforma for a patient ──
@bp.route('/api/generate-proforma', methods=['POST'])
@login_required
def generate_proforma():
    if not current_user.has_privilege('inpatient:proforma_invoice'):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    admission_id = data.get('admission_id')
    if not admission_id:
        return jsonify({'error': 'Admission ID required'}), 400

    admission = InpatientAdmission.query.get(admission_id)
    if not admission or admission.status != 'active':
        return jsonify({'error': 'Invalid or inactive admission'}), 404

    # Check if proforma already exists
    existing = InpatientInvoice.query.filter_by(
        admission_id=admission_id,
        invoice_type='proforma'
    ).first()
    if existing:
        return jsonify({'error': 'Proforma already exists for this admission'}), 400

    # ── Get fees ──
    ward_fee = WardBedFee.query.filter_by(ward_id=admission.ward_id).first()
    bed_admission_fee = ward_fee.admission_fee if ward_fee else 0.0
    doctor_fee_setting = InpatientSetting.query.filter_by(key='default_admission_fee').first()
    doctor_fee = float(doctor_fee_setting.value) if doctor_fee_setting else 0.0

    # ── Create proforma ──
    invoice_number = f"PRO-{datetime.utcnow().strftime('%Y%m%d')}-{InpatientInvoice.query.count()+1:04d}"
    invoice = InpatientInvoice(
        admission_id=admission.id,
        invoice_number=invoice_number,
        invoice_type='proforma',
        subtotal=bed_admission_fee + doctor_fee,
        discount=0.0,
        tax=0.0,
        grand_total=bed_admission_fee + doctor_fee,
        paid_amount=0.0,
        insurance_claim_amount=0.0,
        patient_payable=bed_admission_fee + doctor_fee,
        payment_status='estimated',
        issued_date=datetime.utcnow(),
        due_date=datetime.utcnow() + timedelta(days=30),
        patient_name=admission.patient.full_name,
        patient_reg_no=admission.patient.reg_no,
        patient_phone=admission.patient.phone,
        patient_insurance=admission.patient.insurance_provider,
        patient_insurance_no=admission.patient.insurance_number
    )
    db.session.add(invoice)
    db.session.flush()

    invoice.add_item(
        description='Admission Fee (Bed)',
        unit_price=bed_admission_fee,
        quantity=1
    )
    invoice.add_item(
        description='Doctor Admission Fee',
        unit_price=doctor_fee,
        quantity=1
    )

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Proforma invoice generated successfully.',
        'invoice_id': invoice.id,
        'invoice_number': invoice.invoice_number
    }), 201

@bp.route('/charge-sheet', methods=['GET', 'POST'])
@login_required
def charge_sheet():
    if not current_user.has_privilege('inpatient:charge_sheet'):
        abort(403)

    # ----- GET: render the page -----
    if request.method == 'GET':
        admissions = InpatientAdmission.query.filter_by(status='active').all()
        patients_data = []
        total_invoice_amount = 0
        for adm in admissions:
            invoice = InpatientInvoice.query.filter_by(admission_id=adm.id, invoice_type='proforma').first()
            if invoice:
                charge_count = InpatientChargeSheet.query.filter_by(admission_id=adm.id).count()   
                total_invoice_amount += invoice.grand_total
                patients_data.append({
                    'admission_id': adm.id,
                    'patient_name': adm.patient.full_name,
                    'reg_no': adm.patient.reg_no,
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'invoice_total': invoice.grand_total,
                    'ward': adm.ward.name,
                    'admission_date': adm.admission_date.strftime('%d-%b-%Y'),
                    'charge_count': charge_count,
                    'status': adm.status,
                    'substore_id': adm.ward.substore_id if adm.ward.substore_id else None
                })
        services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
        wards = Ward.query.order_by(Ward.name).all()
        return render_template('charge_sheet.html',
                               patients=patients_data,
                               services=services,
                               wards=wards,
                               total_patients=len(patients_data),
                               total_charges=sum(p['charge_count'] for p in patients_data),
                               total_invoice_amount=total_invoice_amount)

    # ----- POST: AJAX (add charge) -----
    if not request.is_json:
        return jsonify({'error': 'JSON required'}), 400

    data = request.get_json()
    admission_id = data.get('admission_id')
    item_type = data.get('item_type')      # 'service' or 'consumable'
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)
    notes = data.get('notes', '')

    if not admission_id or not item_type or not item_id:
        return jsonify({'error': 'Missing required fields'}), 400

    admission = InpatientAdmission.query.get(admission_id)
    if not admission or admission.status != 'active':
        return jsonify({'error': 'Invalid admission'}), 404

    invoice = InpatientInvoice.query.filter_by(admission_id=admission_id, invoice_type='proforma').first()
    if not invoice:
        return jsonify({'error': 'No proforma invoice for this admission'}), 400

    # ── Handle Service ──
    if item_type == 'service':
        service = Service.query.get(item_id)
        if not service:
            return jsonify({'error': 'Service not found'}), 404
        unit_price = service.price
        description = service.name
        total = unit_price * quantity
        charge = InpatientChargeSheet(
            admission_id=admission_id,
            service_id=service.id,
            quantity=quantity,
            unit_price=unit_price,
            total=total,
            notes=notes,
            posted_by_id=current_user.id
        )
        db.session.add(charge)
        db.session.flush()
        invoice.add_item(
            description=description,
            unit_price=unit_price,
            quantity=quantity,
            service_id=service.id,
            charge_sheet_id=charge.id
        )

    # ── Handle Consumable ──
    elif item_type == 'consumable':
        consumable = SubstoreInventory.query.get(item_id)
        if not consumable:
            return jsonify({'error': 'Consumable not found'}), 404
        if consumable.quantity < quantity:
            return jsonify({'error': f'Insufficient stock. Available: {consumable.quantity}'}), 400

        unit_price = consumable.selling_price or consumable.buying_price
        description = f"Consumable: {consumable.item_name}"
        total = unit_price * quantity

        # Deduct from substore inventory
        consumable.quantity -= quantity

        charge = InpatientChargeSheet(
            admission_id=admission_id,
            service_id=None,  # ✅ explicit None (nullable)
            substore_inventory_id=consumable.id,  # ✅ store the inventory item ID
            quantity=quantity,
            unit_price=unit_price,
            total=total,
            notes=f"Consumable: {consumable.item_name} - {notes}" if notes else f"Consumable: {consumable.item_name}",
            posted_by_id=current_user.id
        )
        db.session.add(charge)
        db.session.flush()
        invoice.add_item(
            description=description,
            unit_price=unit_price,
            quantity=quantity,
            service_id=None,
            charge_sheet_id=charge.id
        )

    invoice.calculate_totals()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Added {description}',
        'charge': {
            'id': charge.id,
            'service_name': description,
            'quantity': charge.quantity,
            'unit_price': charge.unit_price,
            'total': charge.total,
            'notes': charge.notes,
            'is_charge_sheet': True
        },
        'invoice_total': invoice.grand_total,
        'invoice_id': invoice.id
    }), 201

@bp.route('/api/services')
@login_required
def get_services():
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    return jsonify([{'id': s.id, 'name': s.name, 'price': s.price} for s in services]), 200

@bp.route('/api/substore-items/<int:substore_id>')
@login_required
def get_substore_items(substore_id):
    if not current_user.has_privilege('inpatient:charge_sheet'):
        return jsonify({'error': 'Unauthorized'}), 403
    items = SubstoreInventory.query.filter_by(substore_id=substore_id).all()
    return jsonify([{
        'id': i.id,
        'name': i.item_name,
        'quantity': i.quantity,
        'price': i.selling_price or i.buying_price,
        'unit': i.unit,
        'stock': i.quantity
    } for i in items if i.quantity > 0]), 200

@bp.route('/api/invoice-items/<int:invoice_id>')
@login_required
def get_invoice_items(invoice_id):
    if not current_user.has_privilege('inpatient:charge_sheet'):
        return jsonify({'error': 'Unauthorized'}), 403
    invoice = InpatientInvoice.query.get_or_404(invoice_id)
    items = []
    for item in invoice.items:
        items.append({
            'id': item.id,
            'description': item.description,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total': item.total,
            'is_charge_sheet': item.charge_sheet_id is not None,
            'charge_sheet_id': item.charge_sheet_id
        })
    return jsonify({'items': items, 'grand_total': invoice.grand_total}), 200

@bp.route('/api/delete-charge/<int:charge_id>', methods=['DELETE'])
@login_required
def delete_charge(charge_id):
    if not current_user.has_privilege('inpatient:charge_sheet'):
        return jsonify({'error': 'Unauthorized'}), 403
    charge = InpatientChargeSheet.query.get_or_404(charge_id)
    invoice_item = InpatientInvoiceItem.query.filter_by(charge_sheet_id=charge_id).first()
    if invoice_item:
        db.session.delete(invoice_item)
    db.session.delete(charge)
    invoice = InpatientInvoice.query.filter_by(admission_id=charge.admission_id, invoice_type='proforma').first()
    if invoice:
        invoice.calculate_totals()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Charge removed'}), 200



@bp.route('/deposits', methods=['GET', 'POST'])
@login_required
def deposits():
    if not current_user.has_privilege('inpatient:deposits'):
        abort(403)

    # ----- GET: render the page -----
    if request.method == 'GET':
        # Fetch all active admissions that have a proforma invoice
        admissions = InpatientAdmission.query.filter_by(status='active').all()
        patient_data = []
        total_deposits_sum = 0
        total_invoice_sum = 0
        for adm in admissions:
            invoice = InpatientInvoice.query.filter_by(admission_id=adm.id, invoice_type='proforma').first()
            if invoice:
                # Total deposits for this admission
                deposits = InpatientDeposit.query.filter_by(admission_id=adm.id).all()
                total_deposited = sum(d.amount for d in deposits)
                total_deposits_sum += total_deposited
                total_invoice_sum += invoice.grand_total
                patient_data.append({
                    'admission_id': adm.id,
                    'patient_name': adm.patient.full_name,
                    'reg_no': adm.patient.reg_no,
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'invoice_total': invoice.grand_total,
                    'total_deposited': total_deposited,
                    'balance': invoice.grand_total - total_deposited,
                    'deposit_count': len(deposits),
                    'ward': adm.ward.name,
                    'admission_date': adm.admission_date.strftime('%d-%b-%Y')
                })

        return render_template('deposits.html',
                               patients=patient_data,
                               total_invoice_sum=total_invoice_sum,
                               total_deposits_sum=total_deposits_sum,
                               patients_count=len(patient_data))

    # ----- POST: add deposit (AJAX) -----
    if not request.is_json:
        return jsonify({'error': 'JSON required'}), 400

    data = request.get_json()
    admission_id = data.get('admission_id')
    amount = data.get('amount')
    payment_method = data.get('payment_method')
    reference = data.get('reference', '').strip()
    notes = data.get('notes', '').strip()

    if not admission_id or not amount or not payment_method:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except:
        return jsonify({'error': 'Invalid amount'}), 400

    admission = InpatientAdmission.query.get(admission_id)
    if not admission or admission.status != 'active':
        return jsonify({'error': 'Invalid admission'}), 404

    invoice = InpatientInvoice.query.filter_by(admission_id=admission_id, invoice_type='proforma').first()
    if not invoice:
        return jsonify({'error': 'No proforma invoice for this admission'}), 400

    # Generate receipt number
    receipt_number = f"DEP-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

    deposit = InpatientDeposit(
        admission_id=admission_id,
        amount=amount,
        payment_method=payment_method,
        reference=reference,
        notes=notes,
        received_by_id=current_user.id
    )
    db.session.add(deposit)
    db.session.flush()

    # Update invoice paid amount
    invoice.paid_amount += amount
    invoice.patient_payable = invoice.grand_total - invoice.paid_amount - invoice.insurance_claim_amount
    if invoice.patient_payable < 0:
        invoice.patient_payable = 0
    if invoice.paid_amount >= invoice.grand_total:
        invoice.payment_status = 'paid'
    elif invoice.paid_amount > 0:
        invoice.payment_status = 'partially_paid'

    db.session.commit()

    # Recalculate totals for the patient
    total_deposited = InpatientDeposit.query.filter_by(admission_id=admission_id).with_entities(db.func.sum(InpatientDeposit.amount)).scalar() or 0
    balance = invoice.grand_total - total_deposited
    deposit_count = InpatientDeposit.query.filter_by(admission_id=admission_id).count()

    return jsonify({
        'success': True,
        'message': f'Deposit of Ksh {amount:.2f} recorded successfully.',
        'receipt_number': receipt_number,
        'total_deposited': total_deposited,
        'balance': balance,
        'deposit_count': deposit_count,
        'invoice_paid_amount': invoice.paid_amount,
        'invoice_payment_status': invoice.payment_status
    }), 201
    
    
@bp.route('/api/deposit-history/<int:admission_id>')
@login_required
def deposit_history(admission_id):
    if not current_user.has_privilege('inpatient:deposits'):
        return jsonify({'error': 'Unauthorized'}), 403

    deposits = InpatientDeposit.query.filter_by(admission_id=admission_id).order_by(InpatientDeposit.deposit_date.desc()).all()
    return jsonify({
        'deposits': [{
            'id': d.id,
            'amount': d.amount,
            'payment_method': d.payment_method,
            'reference': d.reference,
            'deposit_date': d.deposit_date.isoformat(),
            'received_by': d.received_by.full_name if d.received_by else None
        } for d in deposits]
    }), 200

@bp.route('/sha-claims', methods=['GET', 'POST'])
@login_required
def sha_claims():
    """SHA Claims."""
    if not current_user.has_privilege('inpatient:sha_claims'):
        abort(403)
    form = SHAForm()
    if form.validate_on_submit():
        # Submit claim
        result = submit_sha_claim(form.admission_id.data, form.amount.data)
        if result:
            flash('SHA claim submitted.', 'success')
        else:
            flash('Error submitting claim.', 'danger')
        return redirect(url_for('inpatient_web_bp.dashboard'))
    return render_template('inpatient/sha_claims.html', form=form)

@bp.route('/invoices')
@login_required
def invoices():
    if not current_user.has_privilege('inpatient:invoices'):
        abort(403)

    # Filters
    invoice_type = request.args.get('type', '')
    status = request.args.get('status', '')

    query = InpatientInvoice.query

    if invoice_type:
        query = query.filter(InpatientInvoice.invoice_type == invoice_type)
    if status:
        query = query.filter(InpatientInvoice.payment_status == status)

    invoices = query.order_by(InpatientInvoice.created_at.desc()).all()

    # Add deposit totals and balance
    for inv in invoices:
        total_deposited = InpatientDeposit.query.filter_by(admission_id=inv.admission_id).with_entities(db.func.sum(InpatientDeposit.amount)).scalar() or 0
        inv.total_deposited = total_deposited
        inv.balance = inv.grand_total - total_deposited

    total_count = len(invoices)
    total_amount = sum(inv.grand_total for inv in invoices) if invoices else 0
    paid_count = sum(1 for inv in invoices if inv.payment_status == 'paid')
    unpaid_count = sum(1 for inv in invoices if inv.payment_status == 'unpaid')
    partially_paid_count = sum(1 for inv in invoices if inv.payment_status == 'partially_paid')

    return render_template(
        'final_invoices.html',
        invoices=invoices,
        total_count=total_count,
        total_amount=total_amount,
        paid_count=paid_count,
        unpaid_count=unpaid_count,
        partially_paid_count=partially_paid_count,
        current_type=invoice_type,
        current_status=status
    )

# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
from flask import jsonify

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if not current_user.has_privilege('inpatient:settings'):
        abort(403)

    # ── Load all current settings ──
    general_settings = {s.key: s.value for s in InpatientSetting.query.filter_by(category='general').all()}
    fee_settings = {s.key: s.value for s in InpatientSetting.query.filter_by(category='fees').all()}
    ward_fees = WardBedFee.query.all()

    # ── Forms ──
    general_form = GeneralSettingsForm()
    ward_fee_form = WardBedFeeForm()
    custom_form = SettingForm()

    # Populate ward fee form choices
    ward_fee_form.ward_id.choices = [(w.id, w.name) for w in Ward.query.order_by(Ward.name).all()]

    # Pre-fill general settings for GET
    if request.method == 'GET':
        general_form.default_admission_fee.data = float(general_settings.get('default_admission_fee', 0))
        general_form.default_nursing_fee.data = float(general_settings.get('default_nursing_fee', 0))
        general_form.default_admin_fee.data = float(general_settings.get('default_admin_fee', 0))
        general_form.max_stay_days.data = int(general_settings.get('max_stay_days', 7))
        general_form.default_discharge_fee.data = float(general_settings.get('default_discharge_fee', 0))
        general_form.default_consultation_fee.data = float(general_settings.get('default_consultation_fee', 0))
        general_form.auto_generate_invoice_on_discharge.data = general_settings.get('auto_generate_invoice_on_discharge', 'true') == 'true'

    # ── Handle AJAX POST ──
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        action = data.get('action')
        errors = {}

        if action == 'update_general':
            # Manually populate and validate form from JSON
            form = GeneralSettingsForm()
            form.default_admission_fee.data = data.get('default_admission_fee')
            form.default_nursing_fee.data = data.get('default_nursing_fee')
            form.default_admin_fee.data = data.get('default_admin_fee')
            form.max_stay_days.data = data.get('max_stay_days')
            form.default_discharge_fee.data = data.get('default_discharge_fee')
            form.default_consultation_fee.data = data.get('default_consultation_fee')
            form.auto_generate_invoice_on_discharge.data = data.get('auto_generate_invoice_on_discharge', True)

            if form.validate():
                settings_map = {
                    'default_admission_fee': form.default_admission_fee.data,
                    'default_nursing_fee': form.default_nursing_fee.data,
                    'default_admin_fee': form.default_admin_fee.data,
                    'max_stay_days': form.max_stay_days.data,
                    'default_discharge_fee': form.default_discharge_fee.data,
                    'default_consultation_fee': form.default_consultation_fee.data,
                    'auto_generate_invoice_on_discharge': str(form.auto_generate_invoice_on_discharge.data).lower()
                }
                for key, value in settings_map.items():
                    setting = InpatientSetting.query.filter_by(key=key).first()
                    if setting:
                        setting.value = str(value)
                    else:
                        setting = InpatientSetting(key=key, value=str(value), category='general')
                        db.session.add(setting)
                db.session.commit()
                return jsonify({'success': True, 'message': 'General settings updated successfully.'})
            else:
                return jsonify({'success': False, 'errors': form.errors}), 400

        elif action == 'update_ward_fee':
            form = WardBedFeeForm()
            form.ward_id.data = data.get('ward_id')
            form.admission_fee.data = data.get('admission_fee')
            form.daily_bed_fee.data = data.get('daily_bed_fee')
            form.deposit_required.data = data.get('deposit_required')
            # we need to set choices for ward_id
            form.ward_id.choices = [(w.id, w.name) for w in Ward.query.order_by(Ward.name).all()]

            if form.validate():
                ward_id = form.ward_id.data
                fee = WardBedFee.query.filter_by(ward_id=ward_id).first()
                if fee:
                    fee.admission_fee = form.admission_fee.data
                    fee.daily_bed_fee = form.daily_bed_fee.data
                    fee.deposit_required = form.deposit_required.data
                else:
                    fee = WardBedFee(
                        ward_id=ward_id,
                        admission_fee=form.admission_fee.data,
                        daily_bed_fee=form.daily_bed_fee.data,
                        deposit_required=form.deposit_required.data
                    )
                    db.session.add(fee)
                db.session.commit()
                # Return updated list of fees for table refresh
                updated_fees = WardBedFee.query.all()
                fees_data = [{
                    'id': f.id,
                    'ward_name': f.ward.name,
                    'admission_fee': f.admission_fee,
                    'daily_bed_fee': f.daily_bed_fee,
                    'deposit_required': f.deposit_required
                } for f in updated_fees]
                return jsonify({'success': True, 'message': 'Ward bed fee updated successfully.', 'fees': fees_data})
            else:
                return jsonify({'success': False, 'errors': form.errors}), 400

        elif action == 'delete_ward_fee':
            fee_id = data.get('fee_id')
            fee = WardBedFee.query.get(fee_id)
            if fee:
                db.session.delete(fee)
                db.session.commit()
                # Return updated list
                updated_fees = WardBedFee.query.all()
                fees_data = [{
                    'id': f.id,
                    'ward_name': f.ward.name,
                    'admission_fee': f.admission_fee,
                    'daily_bed_fee': f.daily_bed_fee,
                    'deposit_required': f.deposit_required
                } for f in updated_fees]
                return jsonify({'success': True, 'message': 'Ward fee removed.', 'fees': fees_data})
            else:
                return jsonify({'success': False, 'message': 'Fee not found.'}), 404

        elif action == 'add_custom':
            form = SettingForm()
            form.key.data = data.get('key')
            form.value.data = data.get('value')
            form.description.data = data.get('description')
            form.category.data = data.get('category')

            if form.validate():
                setting = InpatientSetting(
                    key=form.key.data,
                    value=form.value.data,
                    description=form.description.data,
                    category=form.category.data
                )
                db.session.add(setting)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Custom setting added.'})
            else:
                return jsonify({'success': False, 'errors': form.errors}), 400

        else:
            return jsonify({'success': False, 'message': 'Invalid action.'}), 400

    # GET request -> render template with forms
    return render_template(
        'inpatient_settings.html',
        general_form=general_form,
        ward_fee_form=ward_fee_form,
        custom_form=custom_form,
        ward_fees=ward_fees,
        general_settings=general_settings,
        fee_settings=fee_settings
    )




# ----------------------------------------------------------------------
# API / Utilities (optional)
# ----------------------------------------------------------------------
@bp.route('/search-patient')
@login_required
def search_patient():
    """AJAX endpoint to search patients by file number."""
    # Example: used by forms to auto-populate patient info
    if not current_user.has_privilege('inpatient:admission'):
        return jsonify({'error': 'Unauthorized'}), 403
    file_no = request.args.get('file_no')
    if not file_no:
        return jsonify({'error': 'Missing file number'}), 400
    admission = get_admission_by_file_number(file_no)
    if admission:
        return jsonify({
            'id': admission.id,
            'patient_name': admission.patient.full_name,
            'ward': admission.ward.name if admission.ward else None,
            'admission_date': admission.admission_date.isoformat()
        })
    return jsonify({'error': 'Admission not found'}), 404


# ----------------------------------------------------------------------
# Manage Wards & Beds – Page
# ----------------------------------------------------------------------
@bp.route('/manage-wards')
@login_required
def manage_wards():
    if not current_user.has_privilege('inpatient:manage_wards'):
        abort(403)
    wards = Ward.query.order_by(Ward.name).all()
    substores = Substore.query.order_by(Substore.name).all()
    return render_template('manage_wards.html', wards=wards, substores=substores)

# ----------------------------------------------------------------------
# API – Wards
# ----------------------------------------------------------------------

def get_or_create_substore(ward_name, substore_id=None):
    """If substore_id is given, return that substore. Else create a new one."""
    if substore_id:
        substore = Substore.query.get(substore_id)
        if substore:
            return substore
    # Create a new substore with name "Ward {ward_name} Store"
    new_substore = Substore(
        name=f"Ward {ward_name} Store",
        description=f"Automatically created for ward: {ward_name}",
        store_type='ward'
    )
    db.session.add(new_substore)
    db.session.flush()  # to get the id
    return new_substore


@bp.route('/api/wards', methods=['POST'])
@login_required
def add_ward():
    if not current_user.has_privilege('inpatient:manage_wards'):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    name = data.get('name', '').strip()
    floor = data.get('floor', '').strip() or None
    capacity = parse_int_or_none(data.get('capacity'))
    substore_id = parse_int_or_none(data.get('substore_id'))  # optional

    if not name:
        return jsonify({'error': 'Ward name is required'}), 400

    # Get or create substore
    substore = get_or_create_substore(name, substore_id)

    ward = Ward(
        name=name,
        floor=floor,
        capacity=capacity,
        substore_id=substore.id
    )
    db.session.add(ward)
    db.session.commit()

    return jsonify({
        'id': ward.id,
        'name': ward.name,
        'floor': ward.floor,
        'capacity': ward.capacity,
        'substore_id': ward.substore_id,
        'substore_name': substore.name,
        'beds': []
    }), 201

@bp.route('/api/wards/<int:ward_id>', methods=['PUT'])
@login_required
def update_ward(ward_id):
    if not current_user.has_privilege('inpatient:manage_wards'):
        return jsonify({'error': 'Unauthorized'}), 403

    ward = Ward.query.get_or_404(ward_id)
    data = request.get_json()
    ward.name = data.get('name', ward.name).strip()
    ward.floor = data.get('floor', '').strip() or None
    ward.capacity = parse_int_or_none(data.get('capacity'))
    new_substore_id = parse_int_or_none(data.get('substore_id'))

    if new_substore_id is not None:
        # Check if substore exists
        substore = Substore.query.get(new_substore_id)
        if not substore:
            return jsonify({'error': 'Substore not found'}), 404
        ward.substore_id = new_substore_id
    # else: keep the current one

    db.session.commit()
    return jsonify({
        'id': ward.id,
        'name': ward.name,
        'floor': ward.floor,
        'capacity': ward.capacity,
        'substore_id': ward.substore_id,
        'substore_name': ward.substore.name if ward.substore else None
    })

@bp.route('/api/wards/<int:ward_id>', methods=['DELETE'])
@login_required
def delete_ward(ward_id):
    if not current_user.has_privilege('inpatient:manage_wards'):
        return jsonify({'error': 'Unauthorized'}), 403

    ward = Ward.query.get_or_404(ward_id)
    if any(a.status == 'active' for a in ward.admissions):
        return jsonify({'error': 'Cannot delete ward with active admissions'}), 400

    substore_id = ward.substore_id
    db.session.delete(ward)
    db.session.commit()

    # Check if any other ward uses the same substore; if not, you may optionally delete it
    # For safety, we won't auto-delete; admin can delete substores manually later.

    return jsonify({'message': 'Ward deleted'}), 200

# ----------------------------------------------------------------------
# API – Beds
# ----------------------------------------------------------------------
@bp.route('/api/beds', methods=['POST'])
@login_required
def add_bed():
    if not current_user.has_privilege('inpatient:manage_wards'):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    ward_id = parse_int_or_none(data.get('ward_id'))
    bed_number = data.get('bed_number', '').strip()
    
    if ward_id is None or not bed_number:
        return jsonify({'error': 'Ward ID and bed number are required'}), 400
    
    ward = Ward.query.get(ward_id)
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404
    
    # Check duplicate bed number in same ward
    existing = Bed.query.filter_by(ward_id=ward_id, bed_number=bed_number).first()
    if existing:
        return jsonify({'error': 'Bed number already exists in this ward'}), 400
    
    bed = Bed(ward_id=ward_id, bed_number=bed_number, is_occupied=False)
    db.session.add(bed)
    db.session.commit()
    return jsonify({
        'id': bed.id,
        'ward_id': bed.ward_id,
        'bed_number': bed.bed_number,
        'is_occupied': bed.is_occupied
    }), 201

@bp.route('/api/beds/<int:bed_id>', methods=['PUT'])
@login_required
def update_bed(bed_id):
    if not current_user.has_privilege('inpatient:manage_wards'):
        return jsonify({'error': 'Unauthorized'}), 403
    bed = Bed.query.get_or_404(bed_id)
    data = request.get_json()
    new_number = data.get('bed_number', '').strip()
    if not new_number:
        return jsonify({'error': 'Bed number required'}), 400
    
    # Check duplicate in same ward (excluding itself)
    duplicate = Bed.query.filter(
        Bed.ward_id == bed.ward_id,
        Bed.bed_number == new_number,
        Bed.id != bed.id
    ).first()
    if duplicate:
        return jsonify({'error': 'Bed number already used in this ward'}), 400
    
    bed.bed_number = new_number
    db.session.commit()
    return jsonify({
        'id': bed.id,
        'ward_id': bed.ward_id,
        'bed_number': bed.bed_number,
        'is_occupied': bed.is_occupied
    })

@bp.route('/api/beds/<int:bed_id>', methods=['DELETE'])
@login_required
def delete_bed(bed_id):
    if not current_user.has_privilege('inpatient:manage_wards'):
        return jsonify({'error': 'Unauthorized'}), 403
    bed = Bed.query.get_or_404(bed_id)
    if bed.is_occupied:
        return jsonify({'error': 'Cannot delete occupied bed'}), 400
    db.session.delete(bed)
    db.session.commit()
    return jsonify({'message': 'Bed deleted'}), 200





# ==========================================
# 6. Inventory Management (placeholders)
# ==========================================

@bp.route('/inventory-dashboard')
@login_required
def inventory_dashboard():
    """Inpatient Inventory Dashboard."""
    if not current_user.has_privilege('inpatient:inventory_dashboard'):
        abort(403)

    from datetime import datetime, timedelta
    from sqlalchemy import func
    from app.inpatient.models import SubstoreInventory, Substore, InpatientAdmission, InpatientWardShift
    from app.store.models import StockRequest

    # ── Stats ──
    total_items = SubstoreInventory.query.count()
    total_substores = Substore.query.filter_by(store_type='ward').count()

    low_stock_count = SubstoreInventory.query.filter(
        SubstoreInventory.quantity <= SubstoreInventory.low_stock_threshold
    ).count()

    # Expiring within 30 days
    thirty_days_later = datetime.utcnow() + timedelta(days=30)
    expiring_count = SubstoreInventory.query.filter(
        SubstoreInventory.expiry_date <= thirty_days_later,
        SubstoreInventory.expiry_date >= datetime.utcnow()
    ).count()

    pending_requests = StockRequest.query.filter_by(
        department='inpatient',
        status='submitted'
    ).count()

    # ── Low Stock Items (top 10) ──
    low_stock_items = SubstoreInventory.query.filter(
        SubstoreInventory.quantity <= SubstoreInventory.low_stock_threshold
    ).order_by(
        (SubstoreInventory.quantity - SubstoreInventory.low_stock_threshold).asc()
    ).limit(10).all()

    # ── Expiring Soon (top 10) ──
    expiring_items = SubstoreInventory.query.filter(
        SubstoreInventory.expiry_date <= thirty_days_later,
        SubstoreInventory.expiry_date >= datetime.utcnow()
    ).order_by(SubstoreInventory.expiry_date.asc()).limit(10).all()

    # ── Recent Stock Requests (last 10) ──
    recent_requests = StockRequest.query.filter_by(
        department='inpatient'
    ).order_by(StockRequest.created_at.desc()).limit(10).all()

    # ── Inventory by Substore (for chart) ──
    substore_inventory = db.session.query(
        Substore.name,
        func.sum(SubstoreInventory.quantity).label('total')
    ).join(SubstoreInventory, Substore.id == SubstoreInventory.substore_id)\
     .group_by(Substore.id).all()
    substore_labels = [s.name for s in substore_inventory]
    substore_data = [s.total or 0 for s in substore_inventory]

    # ── Request trend (last 7 days) ──
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    request_trend = db.session.query(
        func.date(StockRequest.created_at).label('day'),
        func.count(StockRequest.id).label('count')
    ).filter(
        StockRequest.department == 'inpatient',
        StockRequest.created_at >= seven_days_ago
    ).group_by('day').order_by('day').all()

    trend_days = [r.day.strftime('%a') for r in request_trend]
    trend_counts = [r.count for r in request_trend]
    # ── For filters ──
    substores = Substore.query.filter_by(store_type='ward').order_by(Substore.name).all()
    categories = db.session.query(SubstoreInventory.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    selected_substore = request.args.get('substore', type=int)
    return render_template(
        'inventory_dashboard.html',
        total_items=total_items,
        total_substores=total_substores,
        low_stock_count=low_stock_count,
        expiring_count=expiring_count,
        pending_requests=pending_requests,
        low_stock_items=low_stock_items,
        expiring_items=expiring_items,
        recent_requests=recent_requests,
        substore_labels=substore_labels,
        substore_data=substore_data,
        trend_days=trend_days,
        trend_counts=trend_counts,
        substores=substores,
        categories=categories,
        selected_substore=selected_substore,
    )


@bp.route('/inventory-manage', methods=['GET', 'POST'])
@login_required
def inventory_manage():
    """Manage Inpatient Inventory Items."""
    if not current_user.has_privilege('inpatient:inventory_manage'):
        abort(403)

    # ── Handle AJAX POST (Add/Edit/Delete) ──
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        action = data.get('action')

        if action == 'add':
            # Validate form
            form = InventoryItemForm(data=data)
            if form.validate():
                item = SubstoreInventory(
                    substore_id=form.substore_id.data,
                    item_name=form.item_name.data,
                    category=form.category.data,
                    quantity=form.quantity.data,
                    unit=form.unit.data,
                    buying_price=form.buying_price.data,
                    selling_price=form.selling_price.data or None,
                    reorder_level=form.reorder_level.data,
                    low_stock_threshold=form.low_stock_threshold.data,
                    batch_number=form.batch_number.data,
                    expiry_date=form.expiry_date.data,
                    supplier=form.supplier.data,
                    location=form.location.data,
                    storage_conditions=form.storage_conditions.data,
                    service_id=form.service_id.data or None
                )
                db.session.add(item)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Item added successfully'}), 201
            else:
                return jsonify({'success': False, 'errors': form.errors}), 400

        elif action == 'edit':
            item_id = data.get('id')
            item = SubstoreInventory.query.get_or_404(item_id)
            form = InventoryItemForm(data=data, obj=item)
            if form.validate():
                form.populate_obj(item)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Item updated successfully'}), 200
            else:
                return jsonify({'success': False, 'errors': form.errors}), 400

        elif action == 'delete':
            item_id = data.get('id')
            item = SubstoreInventory.query.get_or_404(item_id)
            db.session.delete(item)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Item deleted successfully'}), 200

        return jsonify({'success': False, 'message': 'Invalid action'}), 400

    # ── GET: render the manage page ──
    # Filters
    substore_id = request.args.get('substore', type=int)
    category = request.args.get('category')
    search = request.args.get('search', '').strip()
    status = request.args.get('status')  # 'low', 'expiring', 'all'

    query = SubstoreInventory.query.join(Substore)

    if substore_id:
        query = query.filter(SubstoreInventory.substore_id == substore_id)
    if category:
        query = query.filter(SubstoreInventory.category == category)
    if search:
        query = query.filter(
            or_(
                SubstoreInventory.item_name.ilike(f'%{search}%'),
                SubstoreInventory.batch_number.ilike(f'%{search}%'),
                SubstoreInventory.supplier.ilike(f'%{search}%')
            )
        )
    if status == 'low':
        query = query.filter(SubstoreInventory.quantity <= SubstoreInventory.low_stock_threshold)
    elif status == 'expiring':
        thirty_days_later = datetime.utcnow() + timedelta(days=30)
        query = query.filter(
            SubstoreInventory.expiry_date <= thirty_days_later,
            SubstoreInventory.expiry_date >= datetime.utcnow()
        )

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    paginated = query.order_by(SubstoreInventory.item_name).paginate(page=page, per_page=per_page, error_out=False)

    # Get filter options
    substores = Substore.query.filter_by(store_type='ward').order_by(Substore.name).all()
    categories = db.session.query(SubstoreInventory.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]

    return render_template(
        'inventory_manage.html',
        items=paginated.items,
        pagination=paginated,
        substores=substores,
        categories=categories,
        selected_substore=substore_id,
        selected_category=category,
        search_query=search,
        selected_status=status
    )




@bp.route('/inventory-requests')
@login_required
def inventory_requests():
    """Inpatient Stock Requests."""
    if not current_user.has_privilege('inpatient:inventory_requests'):
        abort(403)

    try:
        # Get filter parameters
        status = request.args.get('status', 'all')
        priority = request.args.get('priority', 'all')
        page = request.args.get('page', 1, type=int)

        # Base query for inpatient stock requests with stock relationship joined
        query = StockRequest.query.filter_by(department='inpatient').options(
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

        # Get bulk requests separately for grouping (if your system uses them)
        bulk_requests = BulkRequest.query.filter_by(department='inpatient').order_by(
            BulkRequest.created_at.desc()
        ).all()

        # Get status counts for filter badges (include both individual and bulk)
        status_counts = {
            'all': StockRequest.query.filter_by(department='inpatient').count() + len(bulk_requests),
            'submitted': StockRequest.query.filter_by(department='inpatient', status='submitted').count() +
                         len([b for b in bulk_requests if b.status == 'submitted']),
            'approved': StockRequest.query.filter_by(department='inpatient', status='approved').count() +
                       len([b for b in bulk_requests if b.status == 'approved']),
            'fulfilled': StockRequest.query.filter_by(department='inpatient', status='fulfilled').count() +
                        len([b for b in bulk_requests if b.status == 'fulfilled']),
            'rejected': StockRequest.query.filter_by(department='inpatient', status='rejected').count() +
                       len([b for b in bulk_requests if b.status == 'rejected']),
        }

        # Get priority options for filter dropdown (optional)
        priorities = ['routine', 'urgent', 'emergency']

        return render_template(
            'inventory_requests.html',  # template we created
            requests=paginated_requests.items,
            bulk_requests=bulk_requests,
            pagination=paginated_requests,
            status_counts=status_counts,
            current_status=status,
            priorities=priorities,
            current_priority=priority,
            title="Inpatient Stock Requests"
        )

    except Exception as e:
        flash(f'Error loading stock requests: {str(e)}', 'danger')
        return redirect(url_for('inpatient_web_bp.inventory_requests'))


# app/inpatient/routes.py

@bp.route('/inventory/request-stocks/new', methods=['GET', 'POST'])
@login_required
def create_stock_request():
    if not current_user.has_privilege('inpatient:inventory_requests'):
        abort(403)

    items = Stock.query.filter_by(is_active=True).all()
    substores = Substore.query.order_by(Substore.name).all()

    form = InpatientStockRequestForm()
    form.item_id.choices = [(item.id, item.name) for item in items]
    form.substore_id.choices = [(s.id, s.name) for s in substores]

    priority_map = {
        'low': 'routine',
        'medium': 'urgent',
        'high': 'emergency',
        'critical': 'emergency'
    }
    form.priority.choices = [('low', 'Low'), ('medium', 'Medium'),
                             ('high', 'High'), ('critical', 'Critical')]

    if request.method == 'POST':
        # ── Get substore_id from request (required for both) ──
        substore_id = request.form.get('substore_id')
        if substore_id:
            try:
                substore_id = int(substore_id)
            except ValueError:
                substore_id = None
        else:
            substore_id = None

        # ── Check if it's a bulk request ──
        bulk_items_data = request.form.get('bulk_items')

        if bulk_items_data:
            # 🔹 Bulk request – skip form validation
            if not substore_id:
                flash('Please select a substore.', 'danger')
                return render_template('create_inpatient_stock_request.html',
                                      form=form,
                                      items=items,
                                      substores=substores,
                                      title="New Inpatient Stock Request")

            try:
                return process_bulk_request(bulk_items_data, current_user, priority_map, substore_id)
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating bulk request: {str(e)}', 'danger')
                return redirect(url_for('inpatient_web_bp.create_stock_request'))

        else:
            # 🔹 Single request – use form validation
            if not form.validate_on_submit():
                # Re‑render with errors
                return render_template('create_inpatient_stock_request.html',
                                      form=form,
                                      items=items,
                                      substores=substores,
                                      title="New Inpatient Stock Request")

            # Now we can safely use form.substore_id.data (validated)
            # But we already have substore_id from request; use either
            try:
                return process_single_request(form, current_user, priority_map, substore_id)
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating request: {str(e)}', 'danger')
                return redirect(url_for('inpatient_web_bp.create_stock_request'))

    # GET request
    return render_template('create_inpatient_stock_request.html',
                          form=form,
                          items=items,
                          substores=substores,
                          title="New Inpatient Stock Request")


def process_single_request(form, current_user, priority_map, substore_id=None):
    """Process single stock request"""
    stock_item = Stock.query.get(form.item_id.data)
    if not stock_item:
        flash('Selected item not found', 'danger')
        return redirect(url_for('inpatient_web_bp.create_stock_request'))

    model_priority = priority_map.get(form.priority.data, 'routine')

    new_request = StockRequest(
        stock_id=form.item_id.data,
        quantity_requested=form.quantity.data,
        priority=model_priority,
        approval_notes=form.reason.data,
        department='inpatient',  # ✅ changed from 'lab'
        requester_id=current_user.id,
        status='submitted',
        batch_number=stock_item.batch_number or 'N/A',
        expiration_date=stock_item.expiration_date or datetime.utcnow() + timedelta(days=365),
        location=stock_item.location or 'Main Ward Store',
        is_bulk=False,
        substore_id=substore_id  # ✅ NEW
    )

    db.session.add(new_request)
    db.session.commit()

    flash('Stock request created successfully!', 'success')
    return redirect(url_for('inpatient_web_bp.inventory_requests'))


def process_bulk_request(bulk_items_data, current_user, priority_map, substore_id=None):
    """Process bulk stock request with same bulk code"""
    try:
        bulk_items = json.loads(bulk_items_data)

        if not bulk_items:
            flash('No items in bulk request', 'danger')
            return redirect(url_for('inpatient_web_bp.create_stock_request'))

        # Create bulk request record
        bulk_request = BulkRequest(
            requester_id=current_user.id,
            department='inpatient',  # ✅ changed from 'lab'
            total_items=len(bulk_items),
            total_quantity=sum(item['quantity'] for item in bulk_items),
            notes=request.form.get('notes', ''),
            status='submitted',
            substore_id=substore_id  # ✅ NEW
        )

        bulk_request.bulk_code = bulk_request.generate_bulk_code()

        # Determine overall priority (highest priority in the batch)
        priority_order = {'emergency': 3, 'urgent': 2, 'high': 1, 'medium': 0, 'low': 0}
        highest_priority_item = max(bulk_items,
                                  key=lambda x: priority_order.get(x.get('priority', 'low'), 0))
        bulk_request.overall_priority = priority_map.get(highest_priority_item.get('priority', 'low'), 'routine')

        db.session.add(bulk_request)
        db.session.flush()

        successful_items = 0
        for item_data in bulk_items:
            stock_item = Stock.query.get(item_data.get('id'))
            if not stock_item:
                flash(f"Item '{item_data.get('name', 'Unknown')}' not found", 'warning')
                continue

            model_priority = priority_map.get(item_data.get('priority', 'low'), 'routine')

            stock_request = StockRequest(
                stock_id=item_data['id'],
                quantity_requested=item_data['quantity'],
                priority=model_priority,
                approval_notes=item_data.get('reason', ''),
                department='inpatient',
                requester_id=current_user.id,
                status='submitted',
                batch_number=stock_item.batch_number or 'N/A',
                expiration_date=stock_item.expiration_date or datetime.utcnow() + timedelta(days=365),
                location=stock_item.location or 'Main Ward Store',
                is_bulk=True,
                bulk_request_id=bulk_request.id,
                substore_id=substore_id  # ✅ NEW
            )

            db.session.add(stock_request)
            successful_items += 1

        if successful_items == 0:
            db.session.rollback()
            flash('No valid items found in bulk request', 'danger')
            return redirect(url_for('inpatient_web_bp.create_stock_request'))

        db.session.commit()

        flash(f'Bulk stock request created successfully! {successful_items} items added. Bulk Code: {bulk_request.bulk_code}', 'success')
        return redirect(url_for('inpatient_web_bp.inventory_requests'))

    except json.JSONDecodeError:
        db.session.rollback()
        flash('Invalid bulk request data format', 'danger')
        return redirect(url_for('inpatient_web_bp.create_stock_request'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating bulk request: {str(e)}', 'danger')
        return redirect(url_for('inpatient_web_bp.create_stock_request'))

@bp.route('/inventory-flow')
@login_required
def inventory_flow():
    """Inpatient Stock Flow."""
    if not current_user.has_privilege('inpatient:inventory_flow'):
        abort(403)
    return render_template('inpatient/inventory_flow.html')