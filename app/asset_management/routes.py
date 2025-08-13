from sqlalchemy import desc, func
from app.auth.models import User
from app.user_management.models import Department
from . import asset_management_bp
from flask import jsonify, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from .models import Asset, AssetCategory, AssetStatus, MaintenanceRecord, Technician, ReplacedPart, AssetAssignmentHistory, DepreciationRecord
from app import db
from datetime import datetime, timedelta

@asset_management_bp.route('/')
@login_required
def dashboard():
    """Asset Management Dashboard with summary statistics"""
    total_assets = Asset.query.count()
    under_maintenance = Asset.query.filter_by(status=AssetStatus.UNDER_MAINTENANCE.value).count()
    operational_assets = Asset.query.filter_by(status=AssetStatus.OPERATIONAL.value).count()
    
    # Recent maintenance activities
    recent_maintenance = MaintenanceRecord.query.order_by(
        MaintenanceRecord.maintenance_date.desc()
    ).limit(5).all()
    
    # Assets needing attention
    attention_needed = Asset.query.filter(
        (Asset.status == AssetStatus.UNDER_MAINTENANCE.value) |
        (Asset.status == AssetStatus.OUT_OF_SERVICE.value)
    ).limit(5).all()
    
    return render_template('asset_management/dashboard.html',
                           total_assets=total_assets,
                           under_maintenance=under_maintenance,
                           operational_assets=operational_assets,
                           recent_maintenance=recent_maintenance,
                           attention_needed=attention_needed)

@asset_management_bp.route('/assets')
@login_required
def manage_assets():
    """List all assets with pagination"""
    page = request.args.get('page', 1, type=int)
    assets = Asset.query.order_by(Asset.name.asc()).paginate(page=page, per_page=10)
    categories = AssetCategory.query.all()
    statuses = [status.value for status in AssetStatus]
    
    return render_template('manage_assets.html',
                           assets=assets,
                           categories=categories,
                           statuses=statuses)

@asset_management_bp.route('/assets/<int:asset_id>')
@login_required
def asset_details(asset_id):
    """Show detailed information about a specific asset"""
    asset = Asset.query.get_or_404(asset_id)
    maintenance_history = MaintenanceRecord.query.filter_by(asset_id=asset_id).order_by(
        MaintenanceRecord.maintenance_date.desc()
    ).all()
    assignment_history = AssetAssignmentHistory.query.filter_by(asset_id=asset_id).order_by(
        AssetAssignmentHistory.assignment_date.desc()
    ).all()
    depreciation_history = DepreciationRecord.query.filter_by(asset_id=asset_id).order_by(
        DepreciationRecord.record_date.desc()
    ).all()
    
    return render_template('asset_details.html',
                           asset=asset,
                           maintenance_history=maintenance_history,
                           assignment_history=assignment_history,
                           datetime=datetime,
                           depreciation_history=depreciation_history)

@asset_management_bp.route('/assets/add', methods=['GET', 'POST'])
@login_required
def add_asset():
    """Add a new asset to the system"""
    categories = AssetCategory.query.all()
    departments = Department.query.all()
    users = User.query.all()
    
    if request.method == 'POST':
        # Extract form data
        name = request.form.get('name')
        description = request.form.get('description')
        serial_number = request.form.get('serial_number')
        barcode = request.form.get('barcode')
        purchase_date_str = request.form.get('purchase_date')
        purchase_price = request.form.get('purchase_price')
        depreciation_rate = request.form.get('depreciation_rate')
        warranty_expiry_str = request.form.get('warranty_expiry')
        status = request.form.get('status')
        location = request.form.get('location')
        notes = request.form.get('notes')
        category_id = request.form.get('category_id')
        department_id = request.form.get('department_id')
        assigned_to_id = request.form.get('assigned_to_id') or None
        
        # Convert date strings to datetime objects
        purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d') if purchase_date_str else None
        warranty_expiry = datetime.strptime(warranty_expiry_str, '%Y-%m-%d') if warranty_expiry_str else None
        
        # Create new asset
        asset = Asset(
            name=name,
            description=description,
            serial_number=serial_number,
            barcode=barcode,
            purchase_date=purchase_date,
            purchase_price=float(purchase_price),
            depreciation_rate=float(depreciation_rate),
            warranty_expiry=warranty_expiry,
            status=status,
            location=location,
            notes=notes,
            category_id=int(category_id),
            department_id=int(department_id),
            assigned_to_id=int(assigned_to_id) if assigned_to_id else None
        )
        
        db.session.add(asset)
        db.session.commit()
        
        # Create initial depreciation record
        depreciation = DepreciationRecord(
            asset_id=asset.id,
            value=asset.purchase_price,
            depreciation_amount=0
        )
        db.session.add(depreciation)
        db.session.commit()
        
        flash('Asset added successfully!', 'success')
        return redirect(url_for('asset_management.asset_details', asset_id=asset.id))
    
    return render_template('add_asset.html',
                           categories=categories,
                           departments=departments,
                           users=users,
                           statuses=[status.value for status in AssetStatus])

@asset_management_bp.route('/add_category', methods=['POST'])
@login_required
def add_category():
    """Add a new asset category"""
    name = request.form.get('name')
    description = request.form.get('description')
    depreciation_period = request.form.get('depreciation_period', 5, type=int)
    
    if not name:
        return jsonify(success=False, message="Category name is required"), 400
    
    category = AssetCategory(
        name=name,
        description=description,
        depreciation_period=depreciation_period
    )
    
    try:
        db.session.add(category)
        db.session.commit()
        return jsonify(success=True, 
                       message="Category added successfully",
                       category={
                           'id': category.id,
                           'name': category.name
                       })
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e)), 500


@asset_management_bp.route('/assets/edit/<int:asset_id>', methods=['GET', 'POST'])
@login_required
def edit_asset(asset_id):
    """Edit an existing asset"""
    asset = Asset.query.get_or_404(asset_id)
    categories = AssetCategory.query.all()
    departments = Department.query.all()
    users = User.query.all()
    
    if request.method == 'POST':
        # Update asset with form data
        asset.name = request.form.get('name')
        asset.description = request.form.get('description')
        asset.serial_number = request.form.get('serial_number')
        asset.barcode = request.form.get('barcode')
        
        purchase_date_str = request.form.get('purchase_date')
        if purchase_date_str:
            asset.purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d')
        
        asset.purchase_price = float(request.form.get('purchase_price'))
        asset.depreciation_rate = float(request.form.get('depreciation_rate'))
        
        warranty_expiry_str = request.form.get('warranty_expiry')
        if warranty_expiry_str:
            asset.warranty_expiry = datetime.strptime(warranty_expiry_str, '%Y-%m-%d')
        
        asset.status = request.form.get('status')
        asset.location = request.form.get('location')
        asset.notes = request.form.get('notes')
        asset.category_id = int(request.form.get('category_id'))
        asset.department_id = int(request.form.get('department_id'))
        
        assigned_to_id = request.form.get('assigned_to_id')
        asset.assigned_to_id = int(assigned_to_id) if assigned_to_id else None
        
        db.session.commit()
        flash('Asset updated successfully!', 'success')
        return redirect(url_for('asset_management.asset_details', asset_id=asset.id))
    
    # Convert dates to string for form display
    purchase_date = asset.purchase_date.strftime('%Y-%m-%d') if asset.purchase_date else ''
    warranty_expiry = asset.warranty_expiry.strftime('%Y-%m-%d') if asset.warranty_expiry else ''
    
    return render_template('asset_management/edit_asset.html',
                           asset=asset,
                           categories=categories,
                           departments=departments,
                           users=users,
                           statuses=[status.value for status in AssetStatus],
                           purchase_date=purchase_date,
                           warranty_expiry=warranty_expiry)

@asset_management_bp.route('/maintenance')
@login_required
def maintenance_schedule():
    """Show upcoming and past maintenance activities"""
    # Upcoming maintenance (next 30 days)
    upcoming = MaintenanceRecord.query.filter(
        MaintenanceRecord.next_maintenance_date >= datetime.utcnow(),
        MaintenanceRecord.next_maintenance_date <= datetime.utcnow() + timedelta(days=30)
    ).order_by(MaintenanceRecord.next_maintenance_date.asc()).all()
    
    # Past maintenance
    page = request.args.get('page', 1, type=int)
    past_maintenance = MaintenanceRecord.query.filter(
        MaintenanceRecord.maintenance_date <= datetime.utcnow()
    ).order_by(MaintenanceRecord.maintenance_date.desc()).paginate(page=page, per_page=10)
    
    return render_template('maintenance_schedule.html',
                           upcoming=upcoming,
                           datetime=datetime,
                           past_maintenance=past_maintenance)

@asset_management_bp.route('/maintenance/add', methods=['GET', 'POST'])
@login_required
def add_maintenance():
    """Record a new maintenance activity"""
    assets = Asset.query.all()
    technicians = Technician.query.all()
    
    if request.method == 'POST':
        # Extract form data
        asset_id = request.form.get('asset_id')
        maintenance_date_str = request.form.get('maintenance_date')
        next_maintenance_date_str = request.form.get('next_maintenance_date')
        cost = request.form.get('cost')
        description = request.form.get('description')
        maintenance_type = request.form.get('maintenance_type')
        technician_id = request.form.get('technician_id')
        notes = request.form.get('notes')
        update_status = request.form.get('update_status') == 'yes'
        new_status = request.form.get('new_status')
        
        # Convert dates
        maintenance_date = datetime.strptime(maintenance_date_str, '%Y-%m-%d') if maintenance_date_str else datetime.utcnow()
        next_maintenance_date = datetime.strptime(next_maintenance_date_str, '%Y-%m-%d') if next_maintenance_date_str else None
        
        # Create maintenance record
        maintenance = MaintenanceRecord(
            asset_id=int(asset_id),
            maintenance_date=maintenance_date,
            next_maintenance_date=next_maintenance_date,
            cost=float(cost),
            description=description,
            maintenance_type=maintenance_type,
            technician_id=int(technician_id),
            notes=notes
        )
        
        db.session.add(maintenance)
        
        # Update asset status if requested
        if update_status:
            asset = Asset.query.get(int(asset_id))
            asset.status = new_status
            db.session.add(asset)
        
        db.session.commit()
        
        flash('Maintenance record added!', 'success')
        return redirect(url_for('asset_management.maintenance_schedule'))
    
    return render_template('add_maintenance.html',
                           assets=assets,
                           datetime=datetime,
                           technicians=technicians,
                           statuses=[status.value for status in AssetStatus])

@asset_management_bp.route('/maintenance/<int:record_id>')
@login_required
def maintenance_details(record_id):
    """Show maintenance record details"""
    record = MaintenanceRecord.query.get_or_404(record_id)
    replaced_parts = ReplacedPart.query.filter_by(maintenance_id=record_id).all()
    
    return render_template('asset_management/maintenance_details.html',
                           record=record,
                           replaced_parts=replaced_parts)

@asset_management_bp.route('/technicians')
@login_required
def list_technicians():
    """List all technicians"""
    technicians = Technician.query.order_by(Technician.name.asc()).all()
    return render_template('technicians.html', technicians=technicians, datetime=datetime)

from urllib.parse import urlparse  # Replace werkzeug.url_parse with this

@asset_management_bp.route('/technicians/add', methods=['GET', 'POST'])
@login_required
def add_technician():
    """Add a new technician"""
    # Get next_page from request args
    next_page = request.args.get('next')
    
    # Validate next_page URL to prevent open redirects
    if next_page:
        parsed_url = urlparse(next_page)
        # Allow only relative URLs (no netloc) or URLs from the same host
        if parsed_url.netloc and parsed_url.netloc != request.host:
            next_page = None
    
    if not next_page:
        next_page = url_for('asset_management.list_technicians')
    
    if request.method == 'POST':
        # Extract form data
        name = request.form.get('name')
        employee_id = request.form.get('employee_id')
        specialization = request.form.get('specialization')
        contact_number = request.form.get('contact_number')
        email = request.form.get('email')
        hire_date_str = request.form.get('hire_date')
        
        # Convert date
        hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d') if hire_date_str else datetime.utcnow()
        
        # Create technician
        technician = Technician(
            name=name,
            employee_id=employee_id,
            specialization=specialization,
            contact_number=contact_number,
            email=email,
            hire_date=hire_date
        )
        
        db.session.add(technician)
        db.session.commit()
        
        flash('Technician added successfully!', 'success')
        
        # Redirect to stored page (maintenance form)
        return redirect(next_page)
    
    
    return render_template('add_technician.html', 
                           next_page=next_page, datetime=datetime)

@asset_management_bp.route('/technicians/<int:tech_id>')
@login_required
def technician_details(tech_id):
    """Show technician details and maintenance history"""
    technician = Technician.query.get_or_404(tech_id)
    maintenance_records = MaintenanceRecord.query.filter_by(
        technician_id=tech_id
    ).order_by(MaintenanceRecord.maintenance_date.desc()).all()
    
    return render_template('asset_management/technician_details.html',
                           technician=technician,
                           maintenance_records=maintenance_records)

@asset_management_bp.route('/technicians/edit/<int:tech_id>', methods=['GET', 'POST'])
@login_required
def edit_technician(tech_id):
    """Edit an existing technician"""
    technician = Technician.query.get_or_404(tech_id)
    
    if request.method == 'POST':
        # Update technician with form data
        technician.name = request.form.get('name')
        technician.employee_id = request.form.get('employee_id')
        technician.specialization = request.form.get('specialization')
        technician.contact_number = request.form.get('contact_number')
        technician.email = request.form.get('email')
        
        hire_date_str = request.form.get('hire_date')
        if hire_date_str:
            technician.hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d')
        
        db.session.commit()
        flash('Technician updated successfully!', 'success')
        return redirect(url_for('asset_management.technician_details', tech_id=technician.id))
    
    # Convert hire date to string for form display
    hire_date = technician.hire_date.strftime('%Y-%m-%d') if technician.hire_date else ''
    
    return render_template('asset_management/edit_technician.html',
                           technician=technician,
                           hire_date=hire_date)

@asset_management_bp.route('/reports')
@login_required
def asset_reports():
    """Generate comprehensive asset reports, with all sums defaulting to 0."""
    # Depreciation report with category details
    depreciation_data = (
        db.session.query(
            AssetCategory.name,
            AssetCategory.depreciation_period,
            func.count(Asset.id).label('asset_count'),
            func.coalesce(func.sum(Asset.purchase_price), 0).label('total_value'),
            func.coalesce(func.sum(Asset.current_value), 0).label('current_value'),
            (
                func.coalesce(func.sum(Asset.purchase_price), 0)
                - func.coalesce(func.sum(Asset.current_value), 0)
            ).label('total_depreciation')
        )
        .join(Asset.category)
        .group_by(AssetCategory.id)
        .all()
    )

    # Maintenance costs with technician details
    maintenance_costs = (
        db.session.query(
            Asset.name,
            Asset.serial_number,
            func.coalesce(func.sum(MaintenanceRecord.cost), 0).label('total_maintenance_cost'),
            func.coalesce(func.count(MaintenanceRecord.id), 0).label('maintenance_count'),
            Technician.name.label('technician_name')
        )
        .join(MaintenanceRecord.asset)
        .join(MaintenanceRecord.technician)
        .group_by(Asset.id, Technician.id)
        .order_by(desc('total_maintenance_cost'))
        .all()
    )

    # Status distribution with location details
    status_counts = (
        db.session.query(
            Asset.status,
            Asset.location,
            func.count(Asset.id).label('count'),
            func.coalesce(func.sum(Asset.current_value), 0).label('sum')
        )
        .group_by(Asset.status, Asset.location)
        .all()
    )

    # Overdue maintenance report
    overdue_maintenance = (
        db.session.query(
            Asset.name,
            Asset.serial_number,
            MaintenanceRecord.next_maintenance_date,
            Technician.name.label('technician_name')
        )
        .join(MaintenanceRecord.asset)
        .join(MaintenanceRecord.technician)
        .filter(MaintenanceRecord.next_maintenance_date < datetime.utcnow())
        .all()
    )

    # Current assignments report
    current_assignments = (
        db.session.query(
            Asset.name,
            Asset.serial_number,
            User.username.label('assigned_to'),
            Department.name.label('department')
        )
        .join(Asset.assigned_to)
        .join(Asset.department)
        .filter(Asset.assigned_to_id.isnot(None))
        .all()
    )

    # Depreciation trends (last 12 months)
    one_year_ago = datetime(datetime.utcnow().year - 1, 1, 1)
    depreciation_trend = (
        db.session.query(
            func.date_format(DepreciationRecord.record_date, '%Y-%m').label('month'),
            func.coalesce(func.avg(DepreciationRecord.depreciation_amount), 0).label('avg_depreciation')
        )
        .filter(DepreciationRecord.record_date >= one_year_ago)
        .group_by('month')
        .order_by('month')
        .all()
    )

    return render_template(
        'asset_reports.html',
        depreciation_data=depreciation_data,
        maintenance_costs=maintenance_costs,
        status_counts=status_counts,
        overdue_maintenance=overdue_maintenance,
        current_assignments=current_assignments,
        depreciation_trend=depreciation_trend
    )

@asset_management_bp.route('/track')
@login_required
def track_assets():
    return redirect(url_for('asset_management.manage_assets'))