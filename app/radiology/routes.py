# app/radiology/routes.py
import math
from flask import current_app, render_template, redirect, send_from_directory, url_for, request, flash
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta
from app import db
from app.auth.models import User
from app.lab.models import UploadedFile
from app.patients.models import Radiology, Service, Patient, Consultation, Visit
from app.radiology.forms import RadiologyStockRequestForm
from app.radiology.models import RadiologyDailyLogEntry, RadiologyEquipment, RadiologyInventory, RadiologyQualityControl, RadiologyScheduledMaintenanceLog
from app.store.models import Stock, StockRequest
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
    
    
    
    
@radiology_web_bp.route('/radiology/scans')
@login_required
def list_completed_scans():
    """List completed radiology scans with images."""
    try:
        page = request.args.get('page', 1, type=int)
        search_query = request.args.get('q', '')

        # Base query: only completed scans that have images
        base_query = Radiology.query.join(
            Consultation, Radiology.consultation_id == Consultation.id
        ).join(
            Patient, Consultation.patient_id == Patient.id
        ).join(
            Service, Radiology.service_id == Service.id
        ).options(
            db.joinedload(Radiology.consultation).joinedload(Consultation.patient),
            db.joinedload(Radiology.service)
        ).filter(
            Radiology.status == 'completed',
            Radiology.images.isnot(None),
            Radiology.images != ''
        )

        # Apply search if provided
        if search_query:
            base_query = base_query.filter(
                db.or_(
                    Service.name.ilike(f'%{search_query}%'),
                    Patient.first_name.ilike(f'%{search_query}%'),
                    Patient.last_name.ilike(f'%{search_query}%')
                )
            )

        # Order by most recent first
        base_query = base_query.order_by(Radiology.completed_at.desc())

        # Paginate (15 per page)
        scans = base_query.paginate(page=page, per_page=15, error_out=False)

        return render_template(
            'completed_scans.html',
            scans=scans,
            search_query=search_query,
            title="Completed Scans"
        )
    except Exception as e:
        current_app.logger.error(f"Error listing completed scans: {str(e)}")
        flash('An error occurred while retrieving scans.', 'danger')
        return redirect(url_for('dashboard_web.index'))    


@radiology_web_bp.route('/radiology/reports')
@login_required
def list_radiology_reports():
    """Radiology Reports Dashboard with technician performance"""
    from sqlalchemy import func
    from datetime import date, timedelta


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
        ).scalar() or 0

    week_count = db.session.query(func.count(Radiology.id))\
        .filter(
            Radiology.requested_at >= start_of_week,
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        ).scalar() or 0

    month_count = db.session.query(func.count(Radiology.id))\
        .filter(
            Radiology.requested_at >= start_of_month,
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        ).scalar() or 0

    year_count = db.session.query(func.count(Radiology.id))\
        .filter(
            Radiology.requested_at >= start_of_year,
            Radiology.is_paid.is_(True),
            Radiology.status == 'completed'
        ).scalar() or 0

    # Technician performance (completed scans by user)
    technician_stats = db.session.query(
        User.id,
        User.full_name,
        func.count(Radiology.id).label('total_completed')
    ).join(Radiology, Radiology.done_by_id == User.id)\
     .filter(
        Radiology.status == 'completed',
        Radiology.is_paid.is_(True)
     )\
     .group_by(User.id, User.full_name)\
     .order_by(func.count(Radiology.id).desc()).all()

    # Monthly trend for the last 6 months
    months = []
    monthly_data = []
    for i in range(5, -1, -1):
        month_start = date(today.year, today.month, 1) - timedelta(days=30*i)
        month_start = month_start.replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year+1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month+1, 1) - timedelta(days=1)
        month_count = db.session.query(func.count(Radiology.id))\
            .filter(
                Radiology.requested_at >= month_start,
                Radiology.requested_at <= month_end,
                Radiology.is_paid.is_(True),
                Radiology.status == 'completed'
            ).scalar() or 0
        months.append(month_start.strftime('%b %Y'))
        monthly_data.append(month_count)

    # All records (for the table)
    records = (
        db.session.query(Radiology)
        .join(Service, Service.id == Radiology.service_id)
        .outerjoin(Consultation, Consultation.id == Radiology.consultation_id)
        .outerjoin(Visit, Visit.id == Radiology.visit_id)
        .outerjoin(Patient, db.or_(
            Patient.id == Consultation.patient_id,
            Patient.id == Visit.patient_id
        ))
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

    # Get distinct services for filter dropdown
    services = Service.query.filter_by(category='Radiology', is_active=True).all()

    return render_template(
        'reports/list_reports.html',
        title="Radiology Reports",
        today_count=today_count,
        week_count=week_count,
        month_count=month_count,
        year_count=year_count,
        technician_stats=technician_stats,
        months=months,
        monthly_data=monthly_data,
        records=records,
        services=services
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
    """Manage radiology inventory with category and stock filters"""

    from sqlalchemy import case, func
    from datetime import datetime, timedelta

    # Pagination
    page = request.args.get('page', 1, type=int)

    # Filters from query params
    category_filter = request.args.get('category', 'all').strip()
    low_stock = request.args.get('low_stock', 'false').lower() == 'true'

    # Base query
    query = RadiologyInventory.query

    if category_filter != 'all':
        query = query.filter(RadiologyInventory.category == category_filter)

    if low_stock:
        query = query.filter(RadiologyInventory.quantity <= RadiologyInventory.low_stock_threshold)

    # Order by expiry date (soonest first), then name
    query = query.order_by(
        case((RadiologyInventory.expiry_date == None, 1), else_=0),
        RadiologyInventory.expiry_date.asc(),
        RadiologyInventory.item_name.asc()
    )

    # Paginate results
    inventory = query.paginate(page=page, per_page=20, error_out=False)

    # Stats (calculated separately)
    total_items = db.session.query(func.count(RadiologyInventory.id)).scalar()

    low_stock_count = db.session.query(func.count(RadiologyInventory.id)).filter(
        RadiologyInventory.quantity <= RadiologyInventory.low_stock_threshold
    ).scalar()

    expiring_soon_count = db.session.query(func.count(RadiologyInventory.id)).filter(
        RadiologyInventory.expiry_date != None,
        RadiologyInventory.expiry_date <= datetime.utcnow() + timedelta(days=30)
    ).scalar()

    # Distinct categories
    categories = [c[0] for c in db.session.query(RadiologyInventory.category).distinct()]

    return render_template(
        'inventory/dashboard.html',
        inventory=inventory,
        categories=categories,
        category_filter=category_filter,
        low_stock=low_stock,
        total_items=total_items,
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        timedelta=timedelta,
        now=datetime.utcnow().date(),
        title="Radiology Inventory Dashboard"
    )






@radiology_web_bp.route('/inventory/request-stocks')
@login_required
def request_stocks():
    """Display and manage radiology stock requests"""
    try:
        # Get filter parameters
        status = request.args.get('status', 'all')
        priority = request.args.get('priority', 'all')
        page = request.args.get('page', 1, type=int)
        
        # Base query for radiology stock requests with stock relationship joined
        query = StockRequest.query.filter_by(department='radiology').options(
            joinedload(StockRequest.stock)  # Eager load the stock relationship
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
        
        # Get status counts for filter badges
        status_counts = {
            'all': StockRequest.query.filter_by(department='radiology').count(),
            'pending': StockRequest.query.filter_by(department='radiology', status='pending').count(),
            'approved': StockRequest.query.filter_by(department='radiology', status='approved').count(),
            'fulfilled': StockRequest.query.filter_by(department='radiology', status='fulfilled').count(),
            'rejected': StockRequest.query.filter_by(department='radiology', status='rejected').count(),
        }
        
        # Get priority options for filter dropdown
        priorities = ['low', 'medium', 'high', 'critical']
        
        return render_template(
            'inventory/request_stocks.html',
            requests=paginated_requests.items,
            pagination=paginated_requests,
            status_counts=status_counts,
            current_status=status,
            priorities=priorities,
            current_priority=priority,
            title="Radiology Stock Requests"
        )
    except Exception as e:
        flash(f"Error loading stock requests: {str(e)}", "danger")
        return redirect(url_for('dashboard.index'))

@radiology_web_bp.route('/inventory/request-stocks/new', methods=['GET', 'POST'])
@login_required
def create_stock_request():
    """Create new radiology stock request"""
    # Get radiology inventory items with details
    radiology_items = Stock.query.filter_by(is_active=True).all()
    
    # Create form with choices populated BEFORE validation
    form = RadiologyStockRequestForm()
    form.item_id.choices = [(item.id, item.name) for item in radiology_items]
    
    # Map form priorities to model enum values
    priority_map = {
        'low': 'routine',
        'medium': 'urgent',
        'high': 'emergency',
        'critical': 'emergency'  # Map critical to emergency as well
    }
    form.priority.choices = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ]
    
    if form.validate_on_submit():
        try:
            # Get the selected stock item
            stock_item = Stock.query.get(form.item_id.data)
            if not stock_item:
                flash('Selected item not found', 'danger')
                return redirect(url_for('radiology_web.create_stock_request'))
            
            # Map form priority to model priority
            model_priority = priority_map.get(form.priority.data, 'routine')
            
            # Create new request using model-compatible fields
            new_request = StockRequest(
                stock_id=form.item_id.data,
                quantity_requested=form.quantity.data,
                priority=model_priority,
                approval_notes=form.reason.data,
                department='radiology',
                requester_id=current_user.id,
                status='submitted',
                batch_number=stock_item.batch_number or 'N/A',
                expiration_date=stock_item.expiration_date or datetime.utcnow() + timedelta(days=365),
                location=stock_item.location or 'Radiology Storage'
            )
            
            db.session.add(new_request)
            db.session.commit()
            
            flash('Radiology stock request created successfully!', 'success')
            return redirect(url_for('radiology_web.request_stocks'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating request: {str(e)}', 'danger')
    
    return render_template(
        'inventory/create_stock_request.html', 
        form=form, 
        radiology_items=radiology_items,
        title="New Radiology Stock Request"
    )


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

@radiology_web_bp.route('/equipment-maintenance')
@login_required
def equipment_maintenance():
    """Track radiology equipment maintenance schedule and history."""

    page = request.args.get('page', 1, type=int)
    per_page = 10
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
    total_equipment = RadiologyEquipment.query.count()

    # Maintenance This Week
    maintenance_this_week_programmed = RadiologyScheduledMaintenanceLog.query.filter(
        RadiologyScheduledMaintenanceLog.qc_done == True,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) >= start_this_week,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) <= end_this_week
    ).count()
    maintenance_this_week_daily = RadiologyDailyLogEntry.query.filter(
        RadiologyDailyLogEntry.qc_done == True,
        func.date(RadiologyDailyLogEntry.submission_date) >= start_this_week,
        func.date(RadiologyDailyLogEntry.submission_date) <= end_this_week
    ).count()
    maintenance_this_week_total = maintenance_this_week_programmed + maintenance_this_week_daily

    # Maintenance Last Week
    maintenance_last_week_programmed = RadiologyScheduledMaintenanceLog.query.filter(
        RadiologyScheduledMaintenanceLog.qc_done == True,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) >= start_last_week,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) <= end_last_week
    ).count()
    maintenance_last_week_daily = RadiologyDailyLogEntry.query.filter(
        RadiologyDailyLogEntry.qc_done == True,
        func.date(RadiologyDailyLogEntry.submission_date) >= start_last_week,
        func.date(RadiologyDailyLogEntry.submission_date) <= end_last_week
    ).count()
    maintenance_last_week_total = maintenance_last_week_programmed + maintenance_last_week_daily

    # Maintenance This Month
    maintenance_this_month_programmed = RadiologyScheduledMaintenanceLog.query.filter(
        RadiologyScheduledMaintenanceLog.qc_done == True,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) >= start_this_month,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) <= end_this_month
    ).count()
    maintenance_this_month_daily = RadiologyDailyLogEntry.query.filter(
        RadiologyDailyLogEntry.qc_done == True,
        func.date(RadiologyDailyLogEntry.submission_date) >= start_this_month,
        func.date(RadiologyDailyLogEntry.submission_date) <= end_this_month
    ).count()
    maintenance_this_month_total = maintenance_this_month_programmed + maintenance_this_month_daily

    # Maintenance Last Month
    maintenance_last_month_programmed = RadiologyScheduledMaintenanceLog.query.filter(
        RadiologyScheduledMaintenanceLog.qc_done == True,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) >= start_last_month,
        func.date(RadiologyScheduledMaintenanceLog.maintenance_date) <= end_last_month
    ).count()
    maintenance_last_month_daily = RadiologyDailyLogEntry.query.filter(
        RadiologyDailyLogEntry.qc_done == True,
        func.date(RadiologyDailyLogEntry.submission_date) >= start_last_month,
        func.date(RadiologyDailyLogEntry.submission_date) <= end_last_month
    ).count()
    maintenance_last_month_total = maintenance_last_month_programmed + maintenance_last_month_daily

    # Overall Maintenance Status
    pending_programmed_maintenance = RadiologyScheduledMaintenanceLog.query.filter_by(qc_done=False).count()
    
    seven_days_from_now = datetime.utcnow().date() + timedelta(days=7)
    urgent_repairs_count = RadiologyScheduledMaintenanceLog.query.filter(
        RadiologyScheduledMaintenanceLog.next_repair_date <= seven_days_from_now,
        RadiologyScheduledMaintenanceLog.qc_done == False
    ).count()
    
    total_maintenance_completed = (
        RadiologyScheduledMaintenanceLog.query.filter_by(qc_done=True).count() +
        RadiologyDailyLogEntry.query.filter_by(qc_done=True).count()
    )

    # --- Maintenance History Table Data ---
    daily_records = RadiologyDailyLogEntry.query.order_by(RadiologyDailyLogEntry.submission_date.desc()).all()
    programmed_records = RadiologyScheduledMaintenanceLog.query.order_by(RadiologyScheduledMaintenanceLog.submission_date.desc()).all()

    all_maintenance_history = []
    for record in daily_records:
        all_maintenance_history.append({
            'equipment': record.equipment,
            'type': 'Daily',
            'date': record.submission_date.strftime('%d %b %Y') if record.submission_date else 'N/A',
            'performed_by': record.performed_by or 'Internal Staff',
            'qc_done_by_name': record.qc_person.full_name if record.qc_person else 'N/A',
            'status': 'Completed' if record.qc_done else 'Pending QC',
            'id': record.id,
            'model_type': 'daily'
        })

    for record in programmed_records:
        all_maintenance_history.append({
            'equipment': record.equipment,
            'type': 'Scheduled',
            'date': record.maintenance_date.strftime('%d %b %Y') if record.maintenance_date else 'N/A',
            'performed_by': record.performed_by or 'External Vendor',
            'qc_done_by_name': record.qc_person.full_name if record.qc_person else 'N/A',
            'status': 'Completed' if record.qc_done else 'Pending QC',
            'id': record.id,
            'model_type': 'programmed'
        })

    all_maintenance_history.sort(
        key=lambda x: datetime.strptime(x['date'], '%d %b %Y') if x['date'] != 'N/A' else datetime.min,
        reverse=True
    )

    if status_filter != 'all':
        all_maintenance_history = [r for r in all_maintenance_history if r['status'] == status_filter]

    total_history_items = len(all_maintenance_history)
    total_pages = math.ceil(total_history_items / per_page)
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    paginated_history = all_maintenance_history[start_index:end_index]

    # --- Render Template ---
    return render_template(
        'maintenance.html',
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
        # Filters
        status_filter=status_filter,
        due_soon=due_soon,
        title="Radiology Equipment Maintenance"
    )


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@radiology_web_bp.route('/maintenance_detail/<string:model_type>/<int:record_id>')
@login_required
def view_maintenance_detail(model_type, record_id):
    """
    Displays the detailed information for a specific daily or programmed maintenance record (Radiology).
    """
    record = None
    uploaded_documents = []  # Initialize as empty list

    if model_type == 'daily':
        record = RadiologyDailyLogEntry.query.get_or_404(record_id)
        uploaded_documents = UploadedFile.query.filter_by(
            daily_log_entry_id=record.id
        ).all()
    elif model_type == 'programmed':
        record = RadiologyScheduledMaintenanceLog.query.get_or_404(record_id)
        uploaded_documents = UploadedFile.query.filter_by(
            scheduled_maintenance_log_id=record.id
        ).all()
    else:
        flash("Invalid maintenance record type specified.", "danger")
        return redirect(url_for('radiology_web.equipment_maintenance'))

    return render_template(
        'maintenance_detail.html',
        record=record,
        model_type=model_type,
        uploaded_documents=uploaded_documents,
        title=f"Radiology {model_type.capitalize()} Maintenance Detail"
    )


@radiology_web_bp.route('/submit_daily_maintenance', methods=['POST'])
@login_required
def submit_daily_maintenance():
    """Handles submission of Radiology Daily Maintenance form with file upload"""
    if request.method == 'POST':
        # Extract form data
        equipment = request.form.get('equipment')
        disinfection_type = request.form.get('disinfection_type')
        concentration = request.form.get('concentration')
        maintenance_notes = request.form.get('maintenance_notes')
        next_repair_date_str = request.form.get('next_repair_date')
        qc_done = 'qc_done' in request.form
        performed_by = request.form.get('performed_by')

        # QC fields
        qc_done_by_id = request.form.get('qc_done_by_id')
        qc_done_by_name = request.form.get('qc_done_by_name')

        # Convert date
        next_repair_date = None
        if next_repair_date_str:
            try:
                next_repair_date = datetime.strptime(next_repair_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid "Next Repair Date" format. Use YYYY-MM-DD.', 'danger')
                return redirect(url_for('radiology_web.equipment_maintenance'))

        qc_done_by_id_int = int(qc_done_by_id) if qc_done_by_id else None

        # Create new record
        new_daily_record = RadiologyDailyLogEntry(
            equipment=equipment,
            disinfection_type=disinfection_type,
            concentration=concentration,
            maintenance_notes=maintenance_notes,
            next_repair_date=next_repair_date,
            qc_done=qc_done,
            performed_by=performed_by,
            qc_done_by_id=qc_done_by_id_int,
            qc_done_by_name=qc_done_by_name
        )
        db.session.add(new_daily_record)
        db.session.commit()  # Commit to get ID for linking documents

        # Handle file upload
        document_title = request.form.get('document_title')
        document_file = request.files.get('document_upload')

        if document_file and document_file.filename != '':
            if allowed_file(document_file.filename):
                filename = secure_filename(document_file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                document_file.save(file_path)

                new_uploaded_file = UploadedFile(
                    title=document_title,
                    filename=filename,
                    daily_log_entry_id=new_daily_record.id
                )
                db.session.add(new_uploaded_file)
                db.session.commit()
            else:
                flash('Invalid file type for maintenance document!', 'danger')
                return redirect(url_for('radiology_web.equipment_maintenance'))

        flash('Radiology Daily Maintenance form submitted successfully!', 'success')
        return redirect(url_for('radiology_web.equipment_maintenance'))

    return redirect(url_for('radiology_web.equipment_maintenance'))




@radiology_web_bp.route('/submit_programmed_maintenance', methods=['POST'])
@login_required
def submit_programmed_maintenance():
    if request.method == 'POST':
        # Extract form data
        equipment = request.form.get('equipment')
        maintenance_date_str = request.form.get('maintenance_date')
        next_repair_date_str = request.form.get('next_repair_date')
        troubleshooting = request.form.get('troubleshooting')
        recommended_action = request.form.get('recommended_action')
        action_taken = request.form.get('action_taken')

        # Convert numeric fields safely
        try:
            labor_charges = float(request.form.get('labor_charges') or 0.0)
        except ValueError:
            flash('Invalid labor charges. Please enter a number.', 'danger')
            return redirect(url_for('radiology_web.equipment_maintenance'))

        try:
            spare_parts_cost = float(request.form.get('spare_parts_cost') or 0.0)
        except ValueError:
            flash('Invalid spare parts cost. Please enter a number.', 'danger')
            return redirect(url_for('radiology_web.equipment_maintenance'))

        qc_done = 'qc_done' in request.form
        qc_verification = request.form.get('qc_verification')
        performed_by = request.form.get('performed_by')

        # QC fields
        qc_done_by_id = request.form.get('qc_done_by_id')
        qc_done_by_name = request.form.get('qc_done_by_name')

        # Convert date fields
        maintenance_date = None
        if maintenance_date_str:
            try:
                maintenance_date = datetime.strptime(maintenance_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid "Maintenance Date". Use YYYY-MM-DD.', 'danger')
                return redirect(url_for('radiology_web.equipment_maintenance'))

        next_repair_date = None
        if next_repair_date_str:
            try:
                next_repair_date = datetime.strptime(next_repair_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid "Next Repair Date". Use YYYY-MM-DD.', 'danger')
                return redirect(url_for('radiology_web.equipment_maintenance'))

        # Validation for QC
        if qc_done and not qc_done_by_id:
            flash("QC Done requires a QC Performed By User ID.", "danger")
            return redirect(url_for('radiology_web.equipment_maintenance'))

        qc_done_by_id_int = int(qc_done_by_id) if qc_done_by_id else None

        # Create a new Radiology Scheduled Maintenance Log
        new_programmed_record = RadiologyScheduledMaintenanceLog(
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
            qc_done_by_id=qc_done_by_id_int,
            qc_done_by_name=qc_done_by_name
        )
        db.session.add(new_programmed_record)
        db.session.commit()

        # Handle file upload
        document_title = request.form.get('document_title')
        document_file = request.files.get('document_upload')

        if document_file and document_file.filename != '':
            if allowed_file(document_file.filename):
                filename = secure_filename(document_file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                document_file.save(file_path)

                new_uploaded_file = UploadedFile(
                    title=document_title,
                    filename=filename,
                    scheduled_maintenance_log_id=new_programmed_record.id
                )
                db.session.add(new_uploaded_file)
                db.session.commit()
            else:
                flash('Invalid file type for programmed maintenance document!', 'danger')
                return redirect(url_for('radiology_web.equipment_maintenance'))

        flash('Radiology Programmed Maintenance form submitted successfully!', 'success')
        return redirect(url_for('radiology_web.equipment_maintenance'))

    return redirect(url_for('radiology_web.equipment_maintenance'))

# --- Quality Control ---
@radiology_web_bp.route('/quality-control')
@login_required
def quality_control():
    try:
        page = request.args.get('page', 1, type=int)
        result_filter = request.args.get('result', 'all')
        date_range = request.args.get('date_range', 'month')

        query = RadiologyQualityControl.query.options(
            joinedload(RadiologyQualityControl.equipment),
            joinedload(RadiologyQualityControl.performer)
        )

        # Apply result filter
        if result_filter != 'all':
            query = query.filter(RadiologyQualityControl.result == result_filter)

        # Apply date range
        now = datetime.utcnow()
        if date_range == 'week':
            query = query.filter(RadiologyQualityControl.test_date >= now - timedelta(days=7))
        elif date_range == 'month':
            query = query.filter(RadiologyQualityControl.test_date >= now - timedelta(days=30))
        elif date_range == 'quarter':
            query = query.filter(RadiologyQualityControl.test_date >= now - timedelta(days=90))
        elif date_range == 'year':
            query = query.filter(RadiologyQualityControl.test_date >= now - timedelta(days=365))

        # Pagination
        qc_records = query.order_by(RadiologyQualityControl.test_date.desc()).paginate(
            page=page, per_page=15, error_out=False
        )

        # Pass rate
        pass_count = RadiologyQualityControl.query.filter(
            RadiologyQualityControl.result == 'Pass',
            RadiologyQualityControl.test_date >= now - timedelta(days=30)
        ).count()

        # Due calibrations
        due_calibrations_count = RadiologyQualityControl.query.filter(
            RadiologyQualityControl.next_qc_date.isnot(None),
            RadiologyQualityControl.next_qc_date <= date.today() + timedelta(days=7)
        ).count()

        return render_template(
            'quality_control.html',
            qc_records=qc_records,
            result_filter=result_filter,
            date_range=date_range,
            pass_count=pass_count,
            due_calibrations_count=due_calibrations_count,
            title="Radiology Quality Control"
        )
    
    except Exception as e:
        current_app.logger.error(f"Error retrieving Radiology QC records: {str(e)}", exc_info=True)
        flash(f'Error retrieving Radiology QC records: {str(e)}', 'danger')
        return redirect(url_for('radiology_web.equipment_list'))

    
@radiology_web_bp.route('/add_qc_record', methods=['GET', 'POST'])
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
            new_qc_record = RadiologyQualityControl(
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
    qc_tests = Radiology.query.all()
    lab_instruments = RadiologyEquipment.query.all()
    return render_template('quality_control.html', qc_tests=qc_tests, lab_instruments=lab_instruments)    
    
    
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
