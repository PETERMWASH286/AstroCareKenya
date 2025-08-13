# app/radiology/routes.py
from flask import current_app, render_template, redirect, send_from_directory, url_for, request, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.patients.models import Radiology, Service, Patient, Consultation
from . import radiology_web_bp
from sqlalchemy import or_, and_
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
                Radiology.status   == 'requested'
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
    """List completed radiology reports"""
    try:
        page = request.args.get('page', 1, type=int)
        date_filter = request.args.get('date_range', 'all')
        
        base_query = Radiology.query.filter_by(status='completed')
        
        if date_filter == 'today':
            start_date = datetime.utcnow().replace(hour=0, minute=0, second=0)
            base_query = base_query.filter(Radiology.completed_at >= start_date)
        elif date_filter == 'week':
            start_date = datetime.utcnow() - timedelta(days=7)
            base_query = base_query.filter(Radiology.completed_at >= start_date)

        reports = base_query.order_by(Radiology.completed_at.desc()).paginate(
            page=page, 
            per_page=15,
            error_out=False
        )
        
        return render_template('radiology/reports.html',
                            reports=reports,
                            date_filter=date_filter,
                            title="Radiology Reports")
    
    except Exception as e:
        flash(f'Error retrieving reports: {str(e)}', 'danger')
        return redirect(url_for('dashboard_web.index'))

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

@radiology_web_bp.route('/radiology/delete/<int:order_id>', methods=['POST'])
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



