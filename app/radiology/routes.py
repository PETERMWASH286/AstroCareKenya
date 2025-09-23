# app/radiology/routes.py
from flask import current_app, render_template, redirect, send_from_directory, url_for, request, flash
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta
from app import db
from app.patients.models import Radiology, Service, Patient, Consultation, Visit
from . import radiology_web_bp
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import joinedload

@radiology_web_bp.route('/radiology/imaging-requests')
@login_required
def list_imaging_requests():
    """List only paid radiology imaging orders that are still in 'requested' status."""
    try:
        page = request.args.get('page', 1, type=int)
        search_query  = request.args.get('q', '')

        base_query = (
            Radiology.query
            .join(Consultation)
            .join(Patient)
            .join(Service)
            .options(
                joinedload(Radiology.consultation)
                  .joinedload(Consultation.patient),
                joinedload(Radiology.service)
            )
            # ← only show paid & still requested
            .filter(
                Radiology.is_paid  == True,
            )
        )

        # apply search
        if search_query:
            base_query = base_query.filter(or_(
                Service.name.ilike(f'%{search_query}%'),
                Patient.first_name.ilike(f'%{search_query}%'),
                Patient.last_name.ilike(f'%{search_query}%')
            ))

        requests = base_query \
            .order_by(Radiology.requested_at.desc()) \
            .paginate(page=page, per_page=15, error_out=False)

        return render_template(
            'imaging_requests.html',
            requests=requests,
            search_query=search_query,
            title="Requested Imaging Orders"
        )
    except Exception as e:
        flash(f'Error retrieving imaging requests: {str(e)}', 'danger')
        return redirect(url_for('dashboard_web.index'))


@radiology_web_bp.route('/radiology/scans/<int:order_id>')
@login_required
def view_scan(order_id):
    """View radiology scan details and images"""
    try:
        scan = Radiology.query.options(
            joinedload(Radiology.consultation).joinedload(Consultation.patient),
            joinedload(Radiology.service)
        ).get_or_404(order_id)
        
        return render_template('radiology/scan_detail.html',
                            scan=scan,
                            title=f"Scan - {scan.service.name}")

    except Exception as e:
        flash(f'Error retrieving scan details: {str(e)}', 'danger')
        return redirect(url_for('radiology_web.list_imaging_requests'))

@radiology_web_bp.route('/radiology/reports')
@login_required
def list_radiology_reports():
    """Radiology Reports Dashboard"""

    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = date(today.year, today.month, 1)
    start_of_year = date(today.year, 1, 1)

    # Aggregates (only paid + completed)
    today_count = db.session.query(func.count(Radiology.id))\
        .filter(
            func.date(Radiology.requested_at) == today,
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        ).scalar()

    week_count = db.session.query(func.count(Radiology.id))\
        .filter(
            Radiology.requested_at >= start_of_week,
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        ).scalar()

    month_count = db.session.query(func.count(Radiology.id))\
        .filter(
            Radiology.requested_at >= start_of_month,
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        ).scalar()

    year_count = db.session.query(func.count(Radiology.id))\
        .filter(
            Radiology.requested_at >= start_of_year,
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        ).scalar()

    # ✅ Records: only paid + completed
    records = (
        db.session.query(Radiology)
        .join(Service, Service.id == Radiology.service_id)
        .outerjoin(Consultation, Consultation.id == Radiology.consultation_id)
        .outerjoin(Visit, Visit.id == Radiology.visit_id)
        .outerjoin(
            Patient, db.or_(
                Patient.id == Consultation.patient_id,
                Patient.id == Visit.patient_id
            )
        )
        .filter(
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        )
        .options(
            db.contains_eager(Radiology.service),
            db.contains_eager(Radiology.consultation, alias=Consultation),
            db.contains_eager(Radiology.visit, alias=Visit)
        )
        .order_by(Radiology.requested_at.desc())
        .all()
    )

    return render_template(
        'reports/list_reports.html',
        title="Radiology Reports",
        today_count=today_count,
        week_count=week_count,
        month_count=month_count,
        year_count=year_count,
        records=records
    )



@radiology_web_bp.route('/radiology/requests/new', methods=['GET', 'POST'])
@login_required
def new_imaging_request():
    """Create new radiology imaging request"""
    try:
        if request.method == 'POST':
            consultation_id = request.form.get('consultation_id')
            service_id = request.form.get('service_id')
            
            if not all([consultation_id, service_id]):
                flash('Please fill all required fields', 'danger')
                return redirect(url_for('radiology_web.new_imaging_request'))
            
            new_request = Radiology(
                consultation_id=consultation_id,
                service_id=service_id,
                status='requested',
                requested_at=datetime.utcnow()
            )
            
            db.session.add(new_request)
            db.session.commit()
            
            flash('Imaging request created successfully', 'success')
            return redirect(url_for('radiology_web.list_imaging_requests'))

        # Get active radiology services
        services = Service.query.filter_by(category='Radiology', is_active=True).all()
        return render_template('radiology/new_request.html',
                            services=services)

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating request: {str(e)}', 'danger')
        return redirect(url_for('radiology_web.list_imaging_requests'))

import os
import uuid
from werkzeug.utils import secure_filename
from pydicom import dcmread
from PIL import Image
# Configuration
ALLOWED_EXTENSIONS = {'dcm', 'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_upload_folder():
    """Create upload folder if it doesn't exist"""
    upload_path = current_app.config['UPLOAD_FOLDER']  # Use config value directly
    try:
        os.makedirs(upload_path, exist_ok=True)
        current_app.logger.info(f"Upload directory verified: {upload_path}")
    except Exception as e:
        current_app.logger.error(f"Failed to create upload directory: {str(e)}")
        raise

def save_and_thumbnail(file):
    """
    Saves a DICOM file and creates a PNG thumbnail.
    Returns the DICOM filename and the thumbnail filename.
    """
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    dcm_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(dcm_path)

    thumb_name = None
    try:
        ds = dcmread(dcm_path)
        arr = ds.pixel_array
        img = Image.fromarray(arr).convert('L')
        img.thumbnail((256, 256))

        thumb_name = filename.rsplit('.', 1)[0] + '.png'
        thumb_path = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_name)
        img.save(thumb_path, format='PNG')

        current_app.logger.info(f"Generated thumbnail: {thumb_name}")
    except Exception as e:
        current_app.logger.warning(f"Failed to create thumbnail for {filename}: {e}")

    return filename, thumb_name


@radiology_web_bp.route('/radiology/process/<int:order_id>', methods=['GET', 'POST'])
@login_required
def process_imaging(order_id):
    order = Radiology.query.options(
        joinedload(Radiology.consultation)
          .joinedload(Consultation.patient),
        joinedload(Radiology.consultation)
          .joinedload(Consultation.treated_by),     # ← load the user
        joinedload(Radiology.service)
    ).get_or_404(order_id)

    if request.method == 'POST':
        try:
                        # Ensure upload directory exists
            create_upload_folder()
            current_app.logger.debug(f"Received request with form data: {request.form}")
            current_app.logger.debug(f"Files received: {request.files}")

            # Validate required fields
            if not all([request.form.get('findings'), request.form.get('impression')]):
                flash('Findings and Impression are required fields', 'danger')
                return redirect(url_for('radiology_web.process_imaging', order_id=order_id))

            # Initialize results data
            results_data = {
                'findings': request.form.get('findings'),
                'impression': request.form.get('impression'),
                'recommendations': request.form.get('recommendations', '')
            }

            # Process file uploads
            uploaded_files = request.files.getlist('file-upload')
            current_app.logger.debug(f"Received {len(uploaded_files)} files for upload")
            new_images = []
            new_thumbs = []

            for idx, file in enumerate(uploaded_files):
                current_app.logger.debug(f"Processing file {idx + 1}: {file.filename}")
                
                if file and file.filename != '':
                    current_app.logger.debug(f"File details: "
                        f"Name: {file.filename}, "
                        f"Size: {getattr(file, 'content_length', 0)} bytes, "
                        f"MIME: {file.mimetype}")

                    if not allowed_file(file.filename):
                        msg = f"Invalid file type: {file.filename}"
                        current_app.logger.warning(msg)
                        flash(msg, 'warning')
                        continue

                    try:
                        dcm_name, thumb_name = save_and_thumbnail(file)
                        new_images.append(dcm_name)
                        if thumb_name:
                            new_thumbs.append(thumb_name)
                        current_app.logger.info(f"Successfully saved: {dcm_name}")
                    except Exception as e:
                        current_app.logger.error(f"Error saving file {file.filename}: {str(e)}", exc_info=True)
                        flash(f'Error saving file {file.filename}: {str(e)}', 'warning')



            # Update database record
            order.results = request.form.get('results', '')
            order.notes = request.form.get('notes', '')
            order.status = 'completed' if request.form.get('complete') else 'processing'
            order.completed_at = datetime.utcnow() if order.status == 'completed' else None
            order.results_data = results_data
            order.done_by_id = current_user.id
            order.done_at    = datetime.utcnow()
            # Merge new images with existing ones
            if order.images:
                existing_images = order.images.split(',')
                order.images = ','.join(existing_images + new_images)
            else:
                order.images = ','.join(new_images)
            if hasattr(order, 'thumbnails'):  # optional if thumbnails column exists
                if order.thumbnails:
                    existing_thumbs = order.thumbnails.split(',')
                    order.thumbnails = ','.join(existing_thumbs + new_thumbs)
                else:
                    order.thumbnails = ','.join(new_thumbs)

            db.session.commit()
            flash('Imaging report saved successfully', 'success')
            return redirect(url_for('radiology_web.list_imaging_requests'))

        except Exception as e:
            db.session.rollback()
            # Cleanup any uploaded files on error
            for filename in new_images:
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                except Exception as cleanup_error:
                    current_app.logger.error(f"Error cleaning up file {filename}: {cleanup_error}")
                    
            flash(f'Error saving imaging report: {str(e)}', 'danger')
            current_app.logger.error(f"Imaging processing error: {str(e)}")

    return render_template('process_imaging.html',
                         order=order,
                         title=f"Process {order.service.name}")

@radiology_web_bp.route('/uploads/radiology/<filename>')
@login_required
def serve_radiology_image(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@radiology_web_bp.route('/delete/<int:order_id>', methods=['POST'])
@login_required
def delete_request(order_id):
    try:
        request_to_delete = Radiology.query.get_or_404(order_id)
        db.session.delete(request_to_delete)
        db.session.commit()
        flash('Imaging request deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting request: {str(e)}', 'danger')
    return redirect(url_for('radiology_web.list_imaging_requests'))



# -------------------------
# NEW ROUTES FOR STATUS FLOW
# -------------------------

@radiology_web_bp.route('/accept-request/<int:order_id>', methods=['POST'])
@login_required
def accept_request(order_id):
    """Accept a requested imaging order → status: waiting_processing"""
    order = Radiology.query.get_or_404(order_id)
    try:
        if order.status != 'requested':
            flash(f"Request cannot be accepted because it is currently '{order.status}'.", "warning")
        else:
            order.status = "waiting processing"
            db.session.commit()
            flash("Request accepted successfully. Status set to waiting processing.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error accepting request: {str(e)}", "danger")
    return redirect(url_for('radiology_web.list_imaging_requests'))


@radiology_web_bp.route('/mark-processing/<int:order_id>', methods=['POST'])
@login_required
def mark_processing(order_id):
    """Mark an accepted request as 'processing' before uploading results"""
    order = Radiology.query.get_or_404(order_id)
    try:
        if order.status != 'waiting_processing':
            flash(f"Request cannot be moved to processing because it is currently '{order.status}'.", "warning")
        else:
            order.status = "processing"
            order.done_by_id = current_user.id
            order.done_at = datetime.utcnow()
            db.session.commit()
            flash("Request status updated to processing.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating status: {str(e)}", "danger")
    return redirect(url_for('radiology_web.list_imaging_requests'))





# -------------------------
# Radiology Inventory Routes
# -------------------------

@radiology_web_bp.route('/inventory/dashboard')
@login_required
def inventory_dashboard():
    return render_template('inventory/dashboard.html',
                           title="Radiology Inventory Dashboard")





@radiology_web_bp.route('/inventory/request-stocks', methods=['GET', 'POST'])
@login_required
def request_stocks():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        qty = request.form.get('quantity')
        # TODO: save into DB
        flash("Stock request submitted successfully", "success")
        return redirect(url_for('radiology_web.request_stocks'))

    return render_template('inventory/request_stocks.html',
                           title="Request Stocks")


@radiology_web_bp.route('/inventory/stock-flow')
@login_required
def stock_flow():
    return render_template('inventory/stock_flow.html',
                           title="Stock Flow")



@radiology_web_bp.route('/reports')
@login_required
def archived_reports():
    """Radiology Reports Dashboard"""

    # --- Date references ---
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    start_of_month = date(today.year, today.month, 1)
    start_of_year = date(today.year, 1, 1)

    # --- Queries (not filtering paid/completed, as per request) ---
    today_count = db.session.query(func.count(Radiology.id))\
        .filter(func.date(Radiology.requested_at) == today).scalar()

    week_count = db.session.query(func.count(Radiology.id))\
        .filter(Radiology.requested_at >= start_of_week).scalar()

    month_count = db.session.query(func.count(Radiology.id))\
        .filter(Radiology.requested_at >= start_of_month).scalar()

    year_count = db.session.query(func.count(Radiology.id))\
        .filter(Radiology.requested_at >= start_of_year).scalar()

    # --- Individual records ---
    records = (
        db.session.query(Radiology)
        .join(Service, Service.id == Radiology.service_id)
        .join(Patient, (Radiology.consultation_id == Consultation.id) | (Radiology.visit_id == Visit.id), isouter=True)
        .order_by(Radiology.requested_at.desc())
        .all()
    )

    return render_template(
        'reports/list_reports.html',
        title="Radiology Reports",
        today_count=today_count,
        week_count=week_count,
        month_count=month_count,
        year_count=year_count,
        records=records
    )


# --- Equipment Maintenance ---
@radiology_web_bp.route('/equipment-maintenance')
@login_required
def equipment_maintenance():
    return render_template('maintenance.html',
                           title="Equipment Maintenance")


# --- Quality Control ---
@radiology_web_bp.route('/quality-control')
@login_required
def quality_control():
    return render_template('quality_control.html',
                           title="Quality Control")
    
    
    
    
# --- Manage Services ---
@radiology_web_bp.route('/manage-services')
@login_required
def manage_services():
    """List all Radiology services"""
    services = Service.query.filter_by(category="Radiology").all()
    
    return render_template(
            'manage_services.html',
            title="Radiology Services",
            services=services
        )



@radiology_web_bp.route('/services/add', methods=['GET', 'POST'])
@login_required
def add_service():
    """Add a new Radiology service"""
    if request.method == 'POST':
        try:
            new_service = Service(
                name=request.form.get('name'),
                category="Radiology",
                description=request.form.get('description'),
                duration=request.form.get('duration') or None,
                predefined_results=request.form.get('predefined_results') or []
            )
            db.session.add(new_service)
            db.session.commit()
            flash("Radiology service added successfully", "success")
            return redirect(url_for('radiology_web.manage_services'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding Radiology service: {str(e)}", "danger")

    return render_template('add_service.html', title="Add Radiology Service")


@radiology_web_bp.route('/radiology/services/<int:service_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_service(service_id):
    """Edit an existing Radiology service"""
    service = Service.query.get_or_404(service_id)
    if service.category != "Radiology":
        flash("Invalid service category", "danger")
        return redirect(url_for('radiology_web.list_services'))

    if request.method == 'POST':
        try:
            service.name = request.form.get('name')
            service.description = request.form.get('description')
            service.price = float(request.form.get('price'))
            service.duration = request.form.get('duration') or None
            service.requires_prescription = bool(request.form.get('requires_prescription'))
            db.session.commit()
            flash("Radiology service updated successfully", "success")
            return redirect(url_for('radiology_web.list_services'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating service: {str(e)}", "danger")

    return render_template('radiology/services/edit.html',
                           title="Edit Radiology Service",
                           service=service)


@radiology_web_bp.route('/radiology/services/<int:service_id>/delete', methods=['POST'])
@login_required
def delete_service(service_id):
    """Delete a Radiology service"""
    service = Service.query.get_or_404(service_id)
    if service.category != "Radiology":
        flash("Invalid service category", "danger")
        return redirect(url_for('radiology_web.list_services'))

    try:
        db.session.delete(service)
        db.session.commit()
        flash("Radiology service deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting service: {str(e)}", "danger")

    return redirect(url_for('radiology_web.list_services'))
