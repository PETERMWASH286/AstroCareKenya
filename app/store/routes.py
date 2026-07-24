from datetime import datetime, timedelta
import os
import re
import tempfile
from flask import Blueprint, app, current_app, flash, json, jsonify, redirect, render_template, request, url_for
from weasyprint import HTML
from werkzeug.utils import secure_filename
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.hr.models import HRInventory
from app.inpatient.models import SubstoreInventory
from app.lab.models import LabInventory
from app.patients.models import Service
from app.pharmacy.models import PharmacyInventory
from app.radiology.models import RadiologyInventory
from app.store.audit_log import log_inventory_action
from app.store.models import LPO, ExternalOrder, InventoryAuditLog, InventoryConversation, InventoryMessage, PaymentRequest, PurchaseOrder, PurchaseOrderDelivery, Requisition, Stock, StockDetail, StockFlow, StockRequest, Supplier, SupplierAccount, SupplierInvoice, SupplierTransaction
from app.utils.notifications import notification_manager

from . import store_web_bp

@store_web_bp.route('/inventory')
def inventory_dashboard():
    stock_items = Stock.query.options(db.joinedload(Stock.supplier)).all()
    suppliers = Supplier.query.all()
    return render_template('dashboard.html', 
                         stock_items=stock_items,
                         suppliers=suppliers,
                         datetime=datetime)

# Inventory Management
@store_web_bp.route('/manage-stock')
def manage_stock():
    return render_template('manage_stock.html')


@store_web_bp.route('/suppliers')
def suppliers():
    # Get all suppliers with their latest order
    suppliers = Supplier.query.options(
        db.joinedload(Supplier.orders)
    ).order_by(Supplier.created_at.desc()).all()
    
    return render_template('suppliers.html',
                         suppliers=suppliers,
                         suppliers_count=Supplier.query.count(),
                         active_suppliers=Supplier.query.filter_by(is_active=True).count())

@store_web_bp.route('/purchase-orders')
def purchase_orders():
    orders = PurchaseOrder.query.options(db.joinedload(PurchaseOrder.supplier)) \
                         .order_by(PurchaseOrder.lpo_id.desc(),
                                   PurchaseOrder.order_date.desc()) \
                         .all()

    
    # Get stock information for each purchase order
    order_ids = [order.id for order in orders]
    stock_entries = Stock.query.filter(Stock.purchase_order_id.in_(order_ids)).all()
    
    # Create a dictionary mapping purchase_order_id to stock existence
    stock_exists = {}
    for stock in stock_entries:
        stock_exists[stock.purchase_order_id] = True
    
    # Ensure all orders have quantity_delivered set
    for order in orders:
        if order.quantity_delivered is None:
            order.quantity_delivered = 0
    
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    return render_template('purchase_orders.html', 
                         purchase_orders=orders,
                         suppliers=suppliers,
                         stock_exists=stock_exists)
# New create_order route
@store_web_bp.route('/store/create_order', methods=['POST'])
def create_order():
    try:
        # Get form data
        supplier_id = request.form.get('supplier_id')
        delivery_date = datetime.strptime(request.form.get('delivery_date'), '%Y-%m-%d')
        status = request.form.get('status', 'pending')
        total_amount = float(request.form.get('total_amount'))
        items = json.loads(request.form.get('items', '[]'))

        # Create new purchase order
        new_order = PurchaseOrder(
            supplier_id=supplier_id,
            delivery_date=delivery_date,
            status=status,
            total_amount=total_amount,
            items=items,
            order_date=datetime.utcnow()
        )

        # Update supplier's last order date
        supplier = Supplier.query.get(supplier_id)
        if supplier:
            supplier.last_order_date = datetime.utcnow()

        # Save to database
        db.session.add(new_order)
        db.session.commit()

        flash('Order recorded successfully', 'success')

        return redirect(url_for('store_web_bp.purchase_orders'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating order: {str(e)}', 'danger')
        return redirect(url_for('store_web_bp.purchase_orders'))

@store_web_bp.route('/purchase-orders/<int:id>')
def view_order(id):
    order = PurchaseOrder.query.get_or_404(id)
    return render_template('order_detail.html', order=order)

@store_web_bp.route('/purchase-orders/<int:id>/edit')
def edit_order(id):
    order = PurchaseOrder.query.get_or_404(id)
    suppliers = Supplier.query.all()
    return render_template('edit_order.html', 
                         order=order, 
                         suppliers=suppliers)

@store_web_bp.route('/purchase-orders/<int:id>/status', methods=['POST'])
def update_status(id):
    order = PurchaseOrder.query.get_or_404(id)
    new_status = request.args.get('status')
    
    try:
        # Validate status transition
        if order.status == 'delivered' and new_status != 'delivered':
            flash('Cannot modify a delivered order', 'warning')
            return redirect(url_for('store_web_bp.purchase_orders'))
        
        if order.status == 'canceled' and new_status != 'canceled':
            flash('Cannot modify a canceled order', 'warning')
            return redirect(url_for('store_web_bp.purchase_orders'))
        
        # Update status
        order.status = new_status
        
        # Handle cancellation
        if new_status == 'canceled':
            order.notes = (order.notes or "") + "\nOrder canceled on " + datetime.utcnow().strftime('%Y-%m-%d')
        
        db.session.commit()
        flash(f'Order status updated to {new_status}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'danger')
    
    return redirect(url_for('store_web_bp.purchase_orders'))

@store_web_bp.route('/purchase-orders/<int:id>', methods=['DELETE'])
def delete_order(id):
    order = PurchaseOrder.query.get_or_404(id)
    try:
        db.session.delete(order)
        db.session.commit()
        flash('Order deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting order: {str(e)}', 'danger')
    return redirect(url_for('sstore_web_bp.purchase_orders'))

@store_web_bp.route('/purchase-orders/<int:id>/edit', methods=['POST'])
def update_order(id):
    order = PurchaseOrder.query.get_or_404(id)
    order.supplier_id = request.form['supplier_id']
    order.status = request.form['status']
    order.order_date = datetime.strptime(request.form['order_date'], '%Y-%m-%dT%H:%M')
    delivery_date = request.form.get('delivery_date')
    order.delivery_date = datetime.strptime(delivery_date, '%Y-%m-%d') if delivery_date else None
    db.session.commit()
    flash("Order updated successfully", "success")
    return redirect(url_for('store_web_bp.order_detail', id=order.id))
 




@store_web_bp.route('/suppliers/create', methods=['POST'])
def create_supplier():
    try:
        # Log supplier creation attempt
        log_inventory_action(
            action='create_attempt',
            resource_type='supplier',
            resource_id=0,
            description="Attempting to create new supplier",
            module='procurement'
        )

        # Validate required fields
        required_fields = ['name', 'contact', 'phone', 'category']
        for field in required_fields:
            if not request.form.get(field):
                log_inventory_action(
                    action='create_failed',
                    resource_type='supplier',
                    resource_id=0,
                    description=f"Missing required field: {field}",
                    module='procurement'
                )
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate email format if provided
        email = request.form.get('email')
        if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            log_inventory_action(
                action='create_failed',
                resource_type='supplier',
                resource_id=0,
                description=f"Invalid email format: {email}",
                module='procurement'
            )
            return jsonify({'error': 'Invalid email format'}), 400

        # Check for existing supplier with same name or email
        existing = Supplier.query.filter(
            (Supplier.name == request.form['name']) | 
            (Supplier.email == email)
        ).first()
        if existing:
            log_inventory_action(
                action='create_failed',
                resource_type='supplier',
                resource_id=0,
                description=f"Supplier already exists with name: {request.form['name']} or email: {email}",
                module='procurement'
            )
            return jsonify({'error': 'Supplier with this name or email already exists'}), 409

        # Convert lead_time to integer
        lead_time = request.form.get('lead_time')
        if lead_time:
            try:
                lead_time = int(lead_time)
            except ValueError:
                log_inventory_action(
                    action='create_failed',
                    resource_type='supplier',
                    resource_id=0,
                    description=f"Invalid lead time format: {lead_time}",
                    module='procurement'
                )
                return jsonify({'error': 'Lead time must be a number'}), 400

        # Create new supplier
        supplier = Supplier(
            name=request.form['name'],
            contact=request.form['contact'],
            email=email,
            phone=request.form['phone'],
            address=request.form.get('address'),
            category=request.form['category'],
            payment_terms=request.form.get('payment_terms'),
            lead_time=lead_time,
            rating=int(request.form.get('rating', 3))  # Default to 3 if not provided
        )

        db.session.add(supplier)
        db.session.flush()  # Get the supplier ID for logging

        # Log successful supplier creation with all details
        log_inventory_action(
            action='create',
            resource_type='supplier',
            resource_id=supplier.id,
            description=f"Created new supplier: {supplier.name}",
            new_values={
                'name': supplier.name,
                'contact': supplier.contact,
                'email': supplier.email,
                'phone': supplier.phone,
                'address': supplier.address,
                'category': supplier.category,
                'payment_terms': supplier.payment_terms,
                'lead_time': supplier.lead_time,
                'rating': supplier.rating,
                'supplier_id': supplier.id
            },
            changed_fields=['name', 'contact', 'email', 'phone', 'address', 'category', 'payment_terms', 'lead_time', 'rating'],
            module='procurement'
        )

        db.session.commit()

        # Log final success
        log_inventory_action(
            action='create_success',
            resource_type='supplier',
            resource_id=supplier.id,
            description=f"Supplier {supplier.name} created successfully with ID: {supplier.id}",
            module='procurement'
        )

        return jsonify({
            'message': 'Supplier created successfully',
            'supplier_id': supplier.id
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error creating supplier: {str(e)}')
        
        # Log the error with detailed information
        log_inventory_action(
            action='create_error',
            resource_type='supplier',
            resource_id=0,
            description=f"Failed to create supplier: {str(e)}",
            module='procurement'
        )
        
        return jsonify({
            'error': 'Failed to create supplier',
            'details': str(e)
        }), 400


@store_web_bp.route('/suppliers/<int:supplier_id>')
def get_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    return jsonify(supplier.to_dict())


@store_web_bp.route('/suppliers/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    
    try:
        # Parse JSON or form data
        data = request.form if request.form else request.get_json()

        # Validate required fields
        required_fields = ['name', 'contact', 'phone', 'category']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate email format if provided
        email = data.get('email')
        if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({'error': 'Invalid email format'}), 400

        # Check if name or email conflicts with another supplier
        existing = Supplier.query.filter(
            ((Supplier.name == data['name']) | (Supplier.email == email)) &
            (Supplier.id != supplier.id)
        ).first()
        if existing:
            return jsonify({'error': 'Another supplier with this name or email already exists'}), 409

        # Convert lead_time to integer
        lead_time = data.get('lead_time')
        if lead_time:
            try:
                lead_time = int(lead_time)
            except ValueError:
                return jsonify({'error': 'Lead time must be a number'}), 400

        # Update fields
        supplier.name = data['name']
        supplier.contact = data['contact']
        supplier.email = email
        supplier.phone = data['phone']
        supplier.address = data.get('address')
        supplier.category = data['category']
        supplier.payment_terms = data.get('payment_terms')
        supplier.lead_time = lead_time
        supplier.rating = int(data.get('rating', supplier.rating))
        supplier.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'message': 'Supplier updated successfully',
            'supplier_id': supplier.id
        }), 200

    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error updating supplier: {str(e)}')
        return jsonify({
            'error': 'Failed to update supplier',
            'details': str(e)
        }), 400


# Delete supplier
@store_web_bp.route('/suppliers/<int:supplier_id>', methods=['DELETE'])
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    db.session.delete(supplier)
    db.session.commit()
    return jsonify({'message': 'Supplier deleted'})



# app/store/routes.py (or pharmacy/routes.py depending on your structure)
# app/store/routes.py
@store_web_bp.route('/manage/stock-requests')
def manage_stock_requests():
    """Central stock request management for all departments"""
    status = request.args.get('status', 'all')
    
    # Base query
    query = StockRequest.query
    
    # Filter by status
    if status != 'all':
        query = query.filter(StockRequest.status == status)
    
    # Order by most recent first (based on created_at)
    requests = query.order_by(StockRequest.created_at.desc()).all()
    
    # Status counts for filters
    status_counts = {
        'all': StockRequest.query.count(),
        'pending': StockRequest.query.filter_by(status='submitted').count(),
        'approved': StockRequest.query.filter_by(status='approved').count(),
        'rejected': StockRequest.query.filter_by(status='rejected').count(),
        'fulfilled': StockRequest.query.filter_by(status='fulfilled').count()
    }
    
    return render_template(
        'manage_stock_requests.html',
        requests=requests,
        status_counts=status_counts,
        current_status=status
    )



# Updated route handler with issued_by and issue_date during collection
from app.inpatient.models import SubstoreInventory
from app.store.models import StockFlow
from app.patients.models import Service

@store_web_bp.route('/stock-requests/<uuid:request_id>/action', methods=['POST'])
def handle_stock_request_action(request_id):
    req = StockRequest.query.get_or_404(request_id)

    if not request.is_json:
        return jsonify({'error': 'Invalid content type, expected JSON'}), 400

    data = request.get_json()

    try:
        action = data.get('action')
        if not action:
            raise ValueError("Missing action")

        # ✅ Approve request (NO stock update or stock flow)
        if action == 'approve':
            if req.status != 'submitted':
                raise ValueError("Only submitted requests can be approved")

            if req.stock.current_stock < req.quantity_requested:
                raise ValueError(f"Insufficient stock. Available: {req.stock.current_stock}")

            log_inventory_action(
                action='approval_attempt',
                resource_type='stock_request',
                resource_id=req.id,
                description=f"Attempting to approve stock request for {req.quantity_requested} units of {req.stock.name}",
                module='stock_request'
            )

            old_status = req.status
            req.status = 'approved'
            req.quantity_approved = req.quantity_requested
            req.approver_id = current_user.id
            req.approval_date = datetime.utcnow()

            log_inventory_action(
                action='approved',
                resource_type='stock_request',
                resource_id=req.id,
                description=f"Approved stock request for {req.quantity_approved} units of {req.stock.name}",
                old_values={'status': old_status, 'quantity_approved': None},
                new_values={
                    'status': 'approved',
                    'quantity_approved': req.quantity_approved,
                    'approver_id': current_user.id,
                    'approval_date': req.approval_date.isoformat()
                },
                changed_fields=['status', 'quantity_approved', 'approver_id', 'approval_date'],
                module='stock_request'
            )

        # ✅ Collect request (UPDATE stock, create stock flow, update department/substore inventory)
        elif action == 'collect':
            if req.status != 'approved':
                raise ValueError("Only approved requests can be collected")

            collected_by = data.get('collected_by', '').strip()
            collection_notes = data.get('collection_notes', '').strip()
            if not collected_by:
                raise ValueError("Collector name is required")

            log_inventory_action(
                action='collection_attempt',
                resource_type='stock_request',
                resource_id=req.id,
                description=f"Attempting to collect {req.quantity_approved} units of {req.stock.name}",
                module='stock_request'
            )

            stock = req.stock
            if stock.current_stock < req.quantity_approved:
                log_inventory_action(
                    action='collection_failed',
                    resource_type='stock_request',
                    resource_id=req.id,
                    description=f"Insufficient stock. Available: {stock.current_stock}, Requested: {req.quantity_approved}",
                    module='stock_request'
                )
                raise ValueError(f"Insufficient stock. Available: {stock.current_stock}")

            # Deduct from main stock
            old_stock_quantity = stock.current_stock
            stock.current_stock -= req.quantity_approved
            if stock.current_stock < 0:
                raise ValueError("Stock deduction went negative, aborting")

            log_inventory_action(
                action='stock_deducted',
                resource_type='stock',
                resource_id=stock.id,
                description=f"Deducted {req.quantity_approved} units for stock request {req.id}",
                old_values={'current_stock': old_stock_quantity},
                new_values={'current_stock': stock.current_stock},
                changed_fields=['current_stock'],
                module='inventory'
            )

            # ── Determine target inventory ──
            dept = req.department.lower()
            approved_qty = req.quantity_approved

            # Common data
            batch_number = stock.batch_number
            expiry_date = stock.expiration_date
            buying_price = stock.unit_price
            selling_price = stock.selling_price
            location = stock.location
            supplier_name = stock.supplier.name if stock.supplier else None
            unit = stock.unit if hasattr(stock, 'unit') and stock.unit else 'piece'

            default_locations = {
                'pharmacy': 'Pharmacy Store',
                'lab': 'Laboratory Store',
                'radiology': 'Radiology Store',
                'hr': 'HR Store',
                'inpatient': 'Ward Store'
            }
            final_location = location if location else default_locations.get(dept, 'General Store')

            service_id = None  # will be set for pharmacy

            # ── Inpatient: use SubstoreInventory ──
            if dept == "inpatient":
                if not req.substore_id:
                    raise ValueError("Inpatient requests must specify a substore for collection.")

                inv = SubstoreInventory.query.filter_by(
                    substore_id=req.substore_id,
                    item_name=stock.name,
                    batch_number=batch_number
                ).first()

                if not inv:
                    inv = SubstoreInventory(
                        substore_id=req.substore_id,
                        item_name=stock.name,
                        category=stock.category,
                        quantity=approved_qty,
                        unit=unit,
                        buying_price=buying_price,
                        selling_price=selling_price,
                        batch_number=batch_number,
                        expiry_date=expiry_date,
                        supplier=supplier_name,
                        location=final_location
                    )
                    db.session.add(inv)
                    db.session.flush()
                    log_inventory_action(
                        action='substore_inventory_created',
                        resource_type='substore_inventory',
                        resource_id=inv.id,
                        description=f"Created inpatient substore inventory for substore {req.substore_id}, batch {batch_number}",
                        new_values={
                            'item_name': stock.name,
                            'batch': batch_number,
                            'quantity': approved_qty,
                            'buying_price': buying_price,
                            'selling_price': selling_price,
                            'expiry_date': expiry_date.isoformat() if expiry_date else None,
                            'location': final_location,
                            'substore_id': req.substore_id
                        },
                        module='inpatient'
                    )
                else:
                    old_qty = inv.quantity
                    inv.quantity += approved_qty
                    if not inv.location:
                        inv.location = final_location
                    if inv.buying_price != buying_price:
                        current_app.logger.warning(f"Buying price mismatch for batch {batch_number}: {inv.buying_price} vs {buying_price}")
                    if inv.selling_price != selling_price and selling_price is not None:
                        inv.selling_price = selling_price
                    log_inventory_action(
                        action='substore_inventory_updated',
                        resource_type='substore_inventory',
                        resource_id=inv.id,
                        description=f"Updated inpatient substore inventory for substore {req.substore_id}, batch {batch_number}",
                        old_values={'quantity': old_qty},
                        new_values={'quantity': inv.quantity},
                        module='inpatient'
                    )

                service_id = None  # no Service for substore items by default

            # ── Pharmacy: use Service + PharmacyInventory ──
            elif dept == "pharmacy":
                service = Service.query.filter_by(name=stock.name, category='Pharmacy').first()
                if not service:
                    service = Service(
                        name=stock.name,
                        category='Pharmacy',
                        price=selling_price or 0.0,
                        walkin_price=selling_price or 0.0,
                        special_clinic_price=selling_price or 0.0,
                        item_category=stock.category,
                        supplier_id=stock.supplier_id,
                        expiration_date=expiry_date,
                        quantity_in_stock=0,
                        requires_prescription=True,
                    )
                    db.session.add(service)
                    db.session.flush()
                    log_inventory_action(
                        action='service_created',
                        resource_type='service',
                        resource_id=service.id,
                        description=f"Created service for pharmacy item {stock.name}",
                        new_values={'name': stock.name, 'price': selling_price},
                        module='finance'
                    )
                else:
                    if service.price != selling_price:
                        old_price = service.price
                        service.price = selling_price or 0.0
                        log_inventory_action(
                            action='service_updated',
                            resource_type='service',
                            resource_id=service.id,
                            description=f"Updated service price for {stock.name}",
                            old_values={'price': old_price},
                            new_values={'price': service.price},
                            module='finance'
                        )

                old_qty = service.quantity_in_stock
                service.quantity_in_stock += approved_qty
                service.last_restocked = datetime.utcnow()
                log_inventory_action(
                    action='service_stock_updated',
                    resource_type='service',
                    resource_id=service.id,
                    description=f"Increased service stock by {approved_qty}",
                    old_values={'quantity_in_stock': old_qty},
                    new_values={'quantity_in_stock': service.quantity_in_stock},
                    changed_fields=['quantity_in_stock', 'last_restocked'],
                    module='finance'
                )
                service_id = service.id

                # Update PharmacyInventory
                inv_model = PharmacyInventory
                inv = inv_model.query.filter_by(
                    item_name=stock.name,
                    batch_number=batch_number
                ).first()
                if not inv:
                    inv = inv_model(
                        item_name=stock.name,
                        category=stock.category,
                        quantity=approved_qty,
                        unit=unit,
                        buying_price=buying_price,
                        selling_price=selling_price,
                        batch_number=batch_number,
                        expiry_date=expiry_date,
                        supplier=supplier_name,
                        location=final_location,
                        service_id=service_id
                    )
                    db.session.add(inv)
                    db.session.flush()
                    log_inventory_action(
                        action='pharmacy_inventory_created',
                        resource_type='pharmacy_inventory',
                        resource_id=inv.id,
                        description=f"Created pharmacy inventory for batch {batch_number}",
                        module='pharmacy'
                    )
                else:
                    old_qty = inv.quantity
                    inv.quantity += approved_qty
                    if not inv.location:
                        inv.location = final_location
                    if inv.buying_price != buying_price:
                        current_app.logger.warning(f"Buying price mismatch for batch {batch_number}: {inv.buying_price} vs {buying_price}")
                    if inv.selling_price != selling_price and selling_price is not None:
                        inv.selling_price = selling_price
                    log_inventory_action(
                        action='pharmacy_inventory_updated',
                        resource_type='pharmacy_inventory',
                        resource_id=inv.id,
                        description=f"Updated pharmacy inventory for batch {batch_number}",
                        old_values={'quantity': old_qty},
                        new_values={'quantity': inv.quantity},
                        module='pharmacy'
                    )

            # ── Other departments (Lab, Radiology, etc.) ──
            else:
                # Map to appropriate model
                dept_model_map = {
                    'lab': LabInventory,
                    'radiology': RadiologyInventory,
                    'hr': HRInventory,  # if exists
                }
                inv_model = dept_model_map.get(dept)
                if not inv_model:
                    raise ValueError(f"Unknown department: {req.department}")

                inv = inv_model.query.filter_by(
                    item_name=stock.name,
                    batch_number=batch_number
                ).first()
                if not inv:
                    inv = inv_model(
                        item_name=stock.name,
                        category=stock.category,
                        quantity=approved_qty,
                        unit=unit,
                        buying_price=buying_price,
                        selling_price=selling_price,
                        batch_number=batch_number,
                        expiry_date=expiry_date,
                        supplier=supplier_name,
                        location=final_location
                    )
                    db.session.add(inv)
                    db.session.flush()
                    log_inventory_action(
                        action=f'{dept}_inventory_created',
                        resource_type=f'{dept}_inventory',
                        resource_id=inv.id,
                        description=f"Created {dept} inventory for batch {batch_number}",
                        module=dept
                    )
                else:
                    old_qty = inv.quantity
                    inv.quantity += approved_qty
                    if not inv.location:
                        inv.location = final_location
                    if inv.buying_price != buying_price:
                        current_app.logger.warning(f"Buying price mismatch for batch {batch_number}: {inv.buying_price} vs {buying_price}")
                    if inv.selling_price != selling_price and selling_price is not None:
                        inv.selling_price = selling_price
                    log_inventory_action(
                        action=f'{dept}_inventory_updated',
                        resource_type=f'{dept}_inventory',
                        resource_id=inv.id,
                        description=f"Updated {dept} inventory for batch {batch_number}",
                        old_values={'quantity': old_qty},
                        new_values={'quantity': inv.quantity},
                        module=dept
                    )

            # ── Stock Flow Records ──
            stock_flow_out = StockFlow(
                stock_id=stock.id,
                service_id=service_id,
                quantity_change=-req.quantity_approved,
                flow_type='collection',
                reference_id=req.id,
                notes=f'Stock collection for {req.quantity_approved} units by {collected_by}'
            )
            stock_flow_in = StockFlow(
                service_id=service_id,
                quantity_change=req.quantity_approved,
                flow_type='collection',
                reference_id=req.id,
                notes=f'Stock received from collection {req.id} for department {dept}'
            )
            db.session.add_all([stock_flow_out, stock_flow_in])
            db.session.flush()

            log_inventory_action(
                action='stock_flow_created',
                resource_type='stock_flow',
                resource_id=stock_flow_out.id,
                description="Created outgoing stock flow for collection",
                new_values={'stock_id': stock.id, 'quantity_change': -req.quantity_approved, 'flow_type': 'collection', 'reference_id': req.id},
                module='inventory'
            )
            log_inventory_action(
                action='stock_flow_created',
                resource_type='stock_flow',
                resource_id=stock_flow_in.id,
                description=f"Created incoming stock flow for department {dept}",
                new_values={'service_id': service_id, 'quantity_change': req.quantity_approved, 'flow_type': 'collection', 'reference_id': req.id},
                module=dept
            )

            # Update request status
            old_status = req.status
            req.status = 'fulfilled'
            req.collected_by = collected_by
            req.collection_notes = collection_notes
            req.collected_at = datetime.utcnow()
            req.quantity_issued = req.quantity_approved
            req.issued_by = current_user.id
            req.issue_date = datetime.utcnow()
            req.issue_reference = req.generate_issue_reference()

            db.session.commit()

            log_inventory_action(
                action='collected',
                resource_type='stock_request',
                resource_id=req.id,
                description=f"Successfully collected {req.quantity_issued} units of {stock.name} for {dept} department",
                old_values={'status': old_status},
                new_values={
                    'status': 'fulfilled',
                    'collected_by': collected_by,
                    'collection_notes': collection_notes,
                    'collected_at': req.collected_at.isoformat(),
                    'quantity_issued': req.quantity_issued,
                    'issued_by': current_user.id,
                    'issue_date': req.issue_date.isoformat(),
                    'issue_reference': req.issue_reference
                },
                changed_fields=['status', 'collected_by', 'collection_notes', 'collected_at', 'quantity_issued', 'issued_by', 'issue_date', 'issue_reference'],
                module='stock_request'
            )

        # ── Reject request ──
        elif action == 'reject':
            if req.status != 'submitted':
                raise ValueError("Only submitted requests can be rejected")
            reason = data.get('reason', '').strip()
            if not reason:
                raise ValueError("Rejection reason is required")

            log_inventory_action(
                action='rejection_attempt',
                resource_type='stock_request',
                resource_id=req.id,
                description=f"Attempting to reject stock request with reason: {reason}",
                module='stock_request'
            )

            old_status = req.status
            req.status = 'rejected'
            req.approval_notes = reason
            req.approver_id = current_user.id
            req.approval_date = datetime.utcnow()

            log_inventory_action(
                action='rejected',
                resource_type='stock_request',
                resource_id=req.id,
                description=f"Rejected stock request: {reason}",
                old_values={'status': old_status},
                new_values={
                    'status': 'rejected',
                    'approval_notes': reason,
                    'approver_id': current_user.id,
                    'approval_date': req.approval_date.isoformat()
                },
                changed_fields=['status', 'approval_notes', 'approver_id', 'approval_date'],
                module='stock_request'
            )

        else:
            log_inventory_action(
                action='invalid_action',
                resource_type='stock_request',
                resource_id=req.id,
                description=f"Invalid action attempted: {action}",
                module='stock_request'
            )
            raise ValueError("Invalid action provided")

        # 🔐 Commit transaction
        db.session.commit()

        log_inventory_action(
            action=f'{action}_success',
            resource_type='stock_request',
            resource_id=req.id,
            description=f"Stock request {action} completed successfully",
            module='stock_request'
        )

        current_app.logger.info(f"Stock request {req.id} {action} by user {current_user.id}")

        return jsonify({'success': True, 'message': f'Request {action} successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Action failed: {str(e)}")
        log_inventory_action(
            action=f'{action}_failed',
            resource_type='stock_request',
            resource_id=req.id,
            description=f"Stock request {action} failed: {str(e)}",
            module='stock_request'
        )
        return jsonify({'error': str(e)}), 400

    

@store_web_bp.route('/reports/generate')
def generate_stock_report():
    # Example logic – update with actual report generation
    return render_template('store/stock_report.html')


# Inventory Management (continued)...

@store_web_bp.route('/manage-pharmaceuticals')
def manage_pharmaceuticals():
    # all stock items where category == "Pharmaceuticals"
    items = Stock.query.filter_by(category='Pharmaceuticals').options(db.joinedload(Stock.supplier)).all()
    return render_template('manage_pharmaceuticals.html', items=items)


@store_web_bp.route('/manage-lab-equipment')
def manage_lab_equipment():
    items = Stock.query.filter_by(category='Lab Equipment').options(db.joinedload(Stock.supplier)).all()
    return render_template('manage_lab_equipment.html', items=items)


@store_web_bp.route('/manage-surgical')
def manage_surgical():
    items = Stock.query.filter_by(category='Surgical').options(db.joinedload(Stock.supplier)).all()
    return render_template('manage_surgical.html', items=items)


@store_web_bp.route('/manage-assets')
def manage_assets():
    items = Stock.query.filter_by(category='Assets').options(db.joinedload(Stock.supplier)).all()
    return render_template('manage_assets.html', items=items)


@store_web_bp.route('/manage-consumables')
def manage_consumables():
    items = Stock.query.filter_by(category='Consumables').options(db.joinedload(Stock.supplier)).all()
    return render_template('manage_consumables.html', items=items)


@store_web_bp.route('/external-orders')
def external_orders():
    # Fetch active suppliers
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    # Fetch requisitions with their items, ordered by creation date
    requisitions = Requisition.query.options(
        db.joinedload(Requisition.external_orders)
    ).order_by(Requisition.created_at.desc()).all()
    
    # Get currency from config
    currency = current_app.config.get('CURRENCY', 'Ksh')
    
    return render_template('external_orders.html', 
                          requisitions=requisitions,
                          suppliers=suppliers,
                          currency=currency)



@store_web_bp.route('/external-orders', methods=['POST'])
def create_external_order():
    try:
        # Create a new requisition first
        requisition = Requisition(
            user_id=current_user.id,
            overall_priority=request.form.get('overall_priority', 'medium'),
            overall_reason=request.form.get('overall_reason', '')
        )
        requisition.generate_requisition_number()

        db.session.add(requisition)
        db.session.flush()  # Get requisition ID before committing

        # ✅ Dynamically find all item indices in the form
        item_indices = sorted({
            key.split('[')[1].split(']')[0]
            for key in request.form.keys()
            if key.startswith('items[')
        })

        if not item_indices:
            flash('At least one item is required', 'error')
            db.session.rollback()
            return redirect(url_for('store_web_bp.external_orders'))

        item_count = 0

        # ✅ Process each item found
        for i in item_indices:
            item_name = request.form.get(f'items[{i}][item_name]', '').strip()
            if not item_name:
                flash(f'Item name for item #{item_count + 1} is required', 'error')
                db.session.rollback()
                return redirect(url_for('store_web_bp.external_orders'))

            try:
                quantity = int(request.form.get(f'items[{i}][quantity]', 0))
                if quantity <= 0:
                    flash(f'Quantity for item #{item_count + 1} must be greater than zero', 'error')
                    db.session.rollback()
                    return redirect(url_for('store_web_bp.external_orders'))
            except (TypeError, ValueError):
                flash(f'Invalid quantity for item #{item_count + 1}', 'error')
                db.session.rollback()
                return redirect(url_for('store_web_bp.external_orders'))

            unit = request.form.get(f'items[{i}][unit]', 'pcs')
            priority = request.form.get(f'items[{i}][priority]', 'medium')
            category = request.form.get(f'items[{i}][category]', '').strip()

            if not category:
                flash(f'Category for item #{item_count + 1} is required', 'error')
                db.session.rollback()
                return redirect(url_for('store_web_bp.external_orders'))

            try:
                required_by = datetime.strptime(request.form.get(f'items[{i}][required_by]'), '%Y-%m-%d')
            except (TypeError, ValueError):
                flash(f'Invalid required by date for item #{item_count + 1}', 'error')
                db.session.rollback()
                return redirect(url_for('store_web_bp.external_orders'))

            reason = request.form.get(f'items[{i}][reason]', '').strip()
            if not reason:
                flash(f'Reason for item #{item_count + 1} is required', 'error')
                db.session.rollback()
                return redirect(url_for('store_web_bp.external_orders'))

            # ✅ Create external order for this item
            external_order = ExternalOrder(
                requisition_id=requisition.id,
                item_name=item_name,
                quantity=quantity,
                unit=unit,
                unit_price=0,
                tax_rate=0,
                total_price=0,
                priority=priority,
                category=category,
                required_by=required_by,
                reason=reason,
                user_id=current_user.id,
                status='pending'
            )

            db.session.add(external_order)
            item_count += 1

        # ✅ Log the requisition creation
        log_inventory_action(
            action='create',
            resource_type='requisition',
            resource_id=requisition.id,
            description=f"Created requisition {requisition.requisition_number} with {item_count} items",
            new_values={
                'requisition_number': requisition.requisition_number,
                'item_count': item_count,
                'overall_priority': requisition.overall_priority
            },
            module='procurement'
        )

        db.session.commit()

        flash(f'Requisition {requisition.requisition_number} with {item_count} item(s) created successfully!', 'success')
        return redirect(url_for('store_web_bp.external_orders'))

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error creating external order: {str(e)}")
        flash('An error occurred while saving your requisition. Please try again.', 'error')
        return redirect(url_for('store_web_bp.external_orders'))

    except Exception as e:
        current_app.logger.error(f"Unexpected error creating external order: {str(e)}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('store_web_bp.external_orders'))


# View Order Details
@store_web_bp.route('/external-orders/<int:order_id>')
def view_external_order(order_id):
    order = ExternalOrder.query.get_or_404(order_id)
    currency = current_app.config.get('CURRENCY', 'Ksh')
    return render_template('view_external_order.html', order=order, currency=currency)

# Edit Order (only for pending orders)
@store_web_bp.route('/external-orders/<int:order_id>/edit', methods=['GET', 'POST'])
def edit_external_order(order_id):
    order = ExternalOrder.query.get_or_404(order_id)
    
    # Only allow editing of pending orders
    if order.status != 'pending':
        flash('Only pending orders can be edited', 'warning')
        return redirect(url_for('store_web.external_orders'))
    
    if request.method == 'POST':
        # Process form data and update order
        try:
            order.item_name = request.form['item_name']
            order.quantity = int(request.form['quantity'])
            order.unit = request.form['unit']

            


            order.priority = request.form['priority']
            order.category = request.form['category']

            order.reason = request.form['reason']
            order.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash('Requisition updated successfully!', 'success')
            return redirect(url_for('store_web_bp.external_orders'))
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating order: {str(e)}")
            flash('An error occurred while updating the requisition. Please try again.', 'error')
    
    # Pass suppliers and other needed data to the form
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    currency = current_app.config.get('CURRENCY', 'Ksh')
    
    return render_template('edit_external_order.html', 
                          order=order, 
                          suppliers=suppliers, 
                          currency=currency)

# Cancel External Order
@store_web_bp.route('/external-orders/<int:order_id>/cancel', methods=['POST'])
def cancel_external_order(order_id):
    order = ExternalOrder.query.get_or_404(order_id)

    # Allow cancellation if order is pending OR approved by finance (but not yet director-approved)
    if not (
        order.status == 'pending' or 
        (order.finance_approved is True )
    ):
        flash('Only pending or finance-approved orders can be cancelled.', 'warning')
        return redirect(url_for('store_web_bp.external_orders'))

    try:
        order.status = 'cancelled'
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Order has been cancelled successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error cancelling order: {str(e)}")
        flash('An error occurred while cancelling the order.', 'error')

    return redirect(url_for('store_web_bp.external_orders'))

# Generate LPO
@store_web_bp.route('/external-orders/<int:order_id>/generate-lpo')
def generate_lpo(order_id):
    order = ExternalOrder.query.get_or_404(order_id)

    # Only allow for director-approved orders
    if order.status != 'director_approved':
        flash('LPO can only be generated after Director approval.', 'warning')
        return redirect(url_for('store_web_bp.external_orders'))

    return render_template(
        'lpo_template.html',
        order=order,
        now=datetime.utcnow()   # ✅ pass datetime to template
    )

@store_web_bp.route("/lpos/<int:order_id>/generate", methods=["POST"])
def approve_lpo(order_id):
    """
    Generate an LPO for a given external order.
    This prepares the LPO but does not approve it yet.
    """
    try:
        data = request.get_json()
        delivery_date = data.get("delivery_date")

        external_order = ExternalOrder.query.get_or_404(order_id)

        # ✅ Prevent duplicate LPOs for the same order (if one already exists)
        existing_lpo = LPO.query.filter_by(external_order_id=external_order.id).first()
        if existing_lpo:
            return jsonify({
                "success": False,
                "message": f"LPO already exists: {existing_lpo.lpo_number}"
            }), 400

        # ✅ Create new LPO (status = pending, not approved yet)
        new_lpo = LPO(
            external_order_id=external_order.id,
            item_name=external_order.item_name,
            category=external_order.category,
            unit=external_order.unit,
            quantity=external_order.quantity,
            unit_price=external_order.unit_price,
            tax_rate=external_order.tax_rate,
            total_price=external_order.total_price,
            supplier_id=external_order.supplier_id,
            contact_person=external_order.contact_person,
            contact_info=external_order.contact_info,
            status="pending",   # 👈 not approved yet
            created_by=current_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Optional: set delivery date if passed
        if delivery_date:
            try:
                new_lpo.delivery_date = datetime.fromisoformat(delivery_date)
            except Exception:
                pass

        db.session.add(new_lpo)
        db.session.flush()  # get new_lpo.id before commit

        # Generate LPO number
        new_lpo.lpo_number = f"LPO-{new_lpo.id}"

        # Do NOT mark external order completed yet (still under approvals)
        external_order.status = "lpo_generated"
        external_order.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "LPO generated successfully. Awaiting approvals.",
            "lpo_id": new_lpo.id,
            "lpo_number": new_lpo.lpo_number
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@store_web_bp.route("/view-lpo/<int:order_id>")
def view_lpo(order_id):
    """View LPO by external order ID"""
    lpo = LPO.query.filter_by(external_order_id=order_id).first_or_404()
    return render_template("view_lpo.html", lpo=lpo)


@store_web_bp.route('/external-orders/<int:order_id>/place-order')
def place_order(order_id):
    try:
        requisition = ExternalOrder.query.get_or_404(order_id)

        if requisition.status != 'completed':
            flash('Only completed requisitions can be converted to purchase orders', 'warning')
            return redirect(url_for('store_web_bp.external_orders'))

        # Check LPO
        lpo = LPO.query.filter_by(external_order_id=order_id).first()
        if not lpo:
            flash('No LPO found for this requisition', 'warning')
            return redirect(url_for('store_web_bp.external_orders'))

        # Generate Compact PDF with the new template
        html_content = render_template("lpo_pdf.html", lpo=lpo)
        
        # Configure PDF options for compact size
        pdf_options = {
            'page-size': 'A4',
            'margin-top': '0.3in',
            'margin-right': '0.3in',
            'margin-bottom': '0.3in',
            'margin-left': '0.3in',
            'encoding': "UTF-8",
            'no-outline': None,
            'quiet': None
        }
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            HTML(string=html_content).write_pdf(tmp_file.name, options=pdf_options)
            pdf_path = tmp_file.name

        # Send professional email to supplier
        email_sent = False
        if lpo.supplier and lpo.supplier.email:
            subject = f"{lpo.lpo_number} - Medical Center Hospital"
            
            # Plain text email content
            plain_text_body = f"""
Dear {lpo.supplier.name},

Please find attached Local Purchase Order {lpo.lpo_number} from Medical Center Hospital.

ORDER SUMMARY:
• Item: {requisition.item_name}
• Quantity: {requisition.quantity} {requisition.unit}
• Total: KSh {requisition.total_price:,.2f}
• Delivery: {requisition.delivery_date.strftime('%Y-%m-%d') if requisition.delivery_date else 'TBC'}

Please acknowledge receipt and confirm delivery timeline. Reference this LPO number on your invoice.

Best regards,
Procurement Department
Medical Center Hospital
"""
            
            # HTML email content
            html_email_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.4; color: #333;">
    <div style="background: #2563eb; color: white; padding: 15px; text-align: center;">
        <h2 style="margin: 0;">Medical Center Hospital</h2>
    </div>
    
    <div style="padding: 20px;">
        <h3 style="color: #2563eb;">{lpo.lpo_number}</h3>
        
        <p>Dear <strong>{lpo.supplier.name}</strong>,</p>
        
        <p>Please find attached Local Purchase Order <strong>{lpo.lpo_number}</strong>.</p>
        
        <div style="background: #f8fafc; padding: 15px; border-radius: 5px; margin: 15px 0;">
            <h4 style="margin: 0 0 10px 0; color: #1e293b;">Order Summary:</h4>
            <table style="width: 100%;">
                <tr>
                    <td style="padding: 2px 0;"><strong>Item:</strong></td>
                    <td style="padding: 2px 0;">{requisition.item_name}</td>
                </tr>
                <tr>
                    <td style="padding: 2px 0;"><strong>Quantity:</strong></td>
                    <td style="padding: 2px 0;">{requisition.quantity} {requisition.unit}</td>
                </tr>
                <tr>
                    <td style="padding: 2px 0;"><strong>Total Amount:</strong></td>
                    <td style="padding: 2px 0;">KSh {requisition.total_price:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 2px 0;"><strong>Delivery:</strong></td>
                    <td style="padding: 2px 0;">{requisition.delivery_date.strftime('%Y-%m-%d') if requisition.delivery_date else 'To be confirmed'}</td>
                </tr>
            </table>
        </div>
        
        <p>Please acknowledge receipt and confirm delivery timeline. Reference this LPO number on your invoice.</p>
        
        <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #e2e8f0;">
            <p style="margin: 5px 0;"><strong>Best regards,</strong></p>
            <p style="margin: 5px 0; color: #2563eb;"><strong>Procurement Department</strong></p>
            <p style="margin: 5px 0; font-size: 12px; color: #64748b;">
                Medical Center Hospital • procurement@medicalcenter.co.ke • +254 700 123 457
            </p>
        </div>
    </div>
</body>
</html>
"""
            
            email_sent = notification_manager.send_email(
                subject=subject,
                recipients=[lpo.supplier.email],
                body=plain_text_body,  # Changed from 'body' to 'plain_text_body'
                html_body=html_email_body,  # Changed from 'html_body' to 'html_email_body'
                attachments=[pdf_path]
            )

        # Create PurchaseOrder record
        purchase_order = PurchaseOrder(
            requisition_id=requisition.id,
            supplier_id=requisition.supplier_id,
            lpo_id=lpo.id,
            lpo_number=lpo.lpo_number,
            item_name=requisition.item_name,
            quantity=requisition.quantity,
            unit=requisition.unit,
            unit_price=requisition.unit_price,
            total_price=requisition.total_price,
            currency=current_app.config.get('CURRENCY', 'Ksh'),
            delivery_date=requisition.delivery_date,
            status='ordered',
            created_by=current_user.id
        )

        requisition.status = 'placed'
        requisition.updated_at = datetime.utcnow()

        db.session.add(purchase_order)
        db.session.commit()

        # Clean up temporary file
        try:
            os.unlink(pdf_path)
        except:
            pass

        # Show appropriate success message
        if email_sent:
            flash(f'Purchase order #{purchase_order.id} created and LPO sent to {lpo.supplier.name}!', 'success')
        else:
            flash(f'Purchase order #{purchase_order.id} created but email failed to send to supplier.', 'warning')

        return redirect(url_for('store_web_bp.external_orders'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating purchase order or sending LPO: {str(e)}")
        flash('An error occurred while creating the purchase order or sending LPO.', 'error')
        return redirect(url_for('store_web_bp.external_orders'))

    
# Delete Order
@store_web_bp.route('/external-orders/<int:order_id>/delete', methods=['POST'])
def delete_external_order(order_id):
    order = ExternalOrder.query.get_or_404(order_id)
    
    # Only allow deletion of pending or rejected orders
    if order.status not in ['pending', 'rejected']:
        flash('Only pending or rejected orders can be deleted', 'warning')
        return redirect(url_for('store_web.external_orders'))
    
    try:
        db.session.delete(order)
        db.session.commit()
        flash('Requisition deleted successfully!', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting order: {str(e)}")
        flash('An error occurred while deleting the requisition. Please try again.', 'error')
    
    return redirect(url_for('store_web.external_orders'))



@store_web_bp.route('/record-delivery', methods=['GET', 'POST'])
def record_delivery():
    # Check for order_id in query string (for GET) or form (for POST)
    order_id = request.args.get('order_id') or request.form.get('order_id')
    
    if request.method == "POST":
        step = request.form.get('step')
        
        # Step 1: Verify LPO
        if step == 'verify_lpo':
            lpo_number = request.form.get('lpo_number')
            
            # Log LPO verification attempt
            log_inventory_action(
                action='verify_lpo',
                resource_type='lpo',
                resource_id=0,
                description=f"Attempting to verify LPO: {lpo_number}",
                module='delivery'
            )
            
            lpo = LPO.query.filter_by(lpo_number=lpo_number).first()
            
            if not lpo:
                log_inventory_action(
                    action='verify_lpo_failed',
                    resource_type='lpo',
                    resource_id=0,
                    description=f"LPO not found: {lpo_number}",
                    module='delivery'
                )
                flash('LPO number not found. Please check and try again.', 'error')
                return render_template('record_delivery.html', lpo_verified=False)
            
            # Check if there's a purchase order for this LPO
            purchase_order = PurchaseOrder.query.filter_by(lpo_id=lpo.id).first()
            if not purchase_order:
                log_inventory_action(
                    action='verify_lpo_failed',
                    resource_type='purchase_order',
                    resource_id=0,
                    description=f"No purchase order found for LPO: {lpo_number}",
                    module='delivery'
                )
                flash('No purchase order found for this LPO. Please contact procurement.', 'error')
                return render_template('record_delivery.html', lpo_verified=False)
            
            # FIXED: Ensure quantity_delivered is not None
            if purchase_order.quantity_delivered is None:
                purchase_order.quantity_delivered = 0
                db.session.commit()
            
            # Check if order is already fully delivered
            if purchase_order.is_fully_delivered:
                log_inventory_action(
                    action='verify_lpo_warning',
                    resource_type='purchase_order',
                    resource_id=purchase_order.id,
                    description=f"Attempted delivery on fully delivered PO: {lpo_number}",
                    module='delivery'
                )
                flash('This purchase order has been fully delivered. No further deliveries can be recorded.', 'warning')
                return render_template('record_delivery.html', lpo_verified=False)

            # Log successful LPO verification
            log_inventory_action(
                action='verify_lpo_success',
                resource_type='purchase_order',
                resource_id=purchase_order.id,
                description=f"Successfully verified LPO: {lpo_number} for {purchase_order.item_name}",
                new_values={
                    'lpo_number': lpo_number,
                    'item_name': purchase_order.item_name,
                    'pending_quantity': purchase_order.pending_quantity,
                    'total_quantity': purchase_order.quantity
                },
                module='delivery'
            )

            return render_template('record_delivery.html',
                                 lpo_verified=True,
                                 lpo=lpo,
                                 purchase_order=purchase_order,
                                 show_form=False)
        
        # Step 2: Confirm comparison
        elif step == 'confirm_comparison':
            order_id = request.form.get('order_id')
            lpo_number = request.form.get('lpo_number')
            quantity_received = int(request.form.get('quantity_received'))
            preliminary_condition = request.form.get('preliminary_condition')
            comparison_notes = request.form.get('comparison_notes')
            
            # Use order_id if provided, otherwise fallback to lpo_number
            if order_id:
                purchase_order = PurchaseOrder.query.get(order_id)
                lpo = LPO.query.get(purchase_order.lpo_id) if purchase_order else None
            else:
                lpo = LPO.query.filter_by(lpo_number=lpo_number).first()
                purchase_order = PurchaseOrder.query.filter_by(lpo_id=lpo.id).first() if lpo else None
            
            lpo = LPO.query.filter_by(lpo_number=lpo_number).first()
            purchase_order = PurchaseOrder.query.filter_by(lpo_id=lpo.id).first()
            
            if not lpo or not purchase_order:
                log_inventory_action(
                    action='comparison_failed',
                    resource_type='purchase_order',
                    resource_id=0,
                    description=f"LPO or PO not found during comparison: {lpo_number}",
                    module='delivery'
                )
                flash('LPO or purchase order not found. Please start over.', 'error')
                return redirect(url_for('store_web_bp.record_delivery'))
            
            # FIXED: Ensure quantity_delivered is not None
            if purchase_order.quantity_delivered is None:
                purchase_order.quantity_delivered = 0
            
            # Validate quantity doesn't exceed pending quantity
            if quantity_received > purchase_order.pending_quantity:
                log_inventory_action(
                    action='comparison_validation_failed',
                    resource_type='purchase_order',
                    resource_id=purchase_order.id,
                    description=f"Quantity received ({quantity_received}) exceeds pending quantity ({purchase_order.pending_quantity})",
                    old_values={'pending_quantity': purchase_order.pending_quantity},
                    new_values={'attempted_quantity': quantity_received},
                    module='delivery'
                )
                flash(f'Quantity received ({quantity_received}) exceeds pending quantity ({purchase_order.pending_quantity}). Please adjust.', 'error')
                return render_template('record_delivery.html',
                                     lpo_verified=True,
                                     lpo=lpo,
                                     purchase_order=purchase_order,
                                     show_form=False)
            
            # Log successful comparison
            log_inventory_action(
                action='comparison_confirmed',
                resource_type='purchase_order',
                resource_id=purchase_order.id,
                description=f"Delivery comparison confirmed for {quantity_received} units",
                new_values={
                    'quantity_received': quantity_received,
                    'preliminary_condition': preliminary_condition,
                    'comparison_notes': comparison_notes
                },
                module='delivery'
            )
            
            return render_template('record_delivery.html',
                                 lpo_verified=True,
                                 show_form=True,
                                 lpo=lpo,
                                 purchase_order=purchase_order,
                                 quantity_received=quantity_received,
                                 preliminary_condition=preliminary_condition,
                                 comparison_notes=comparison_notes)
        
        # Step 3: Final submission - process delivery
        elif step == 'final_submit':
            try:
                # Get data from previous steps
                order_id = request.form.get('order_id')
                lpo_number = request.form.get('lpo_number')
                # ... other fields ...
                
                if order_id:
                    order = PurchaseOrder.query.get(order_id)
                    lpo = LPO.query.get(order.lpo_id) if order else None
                else:
                    lpo = LPO.query.filter_by(lpo_number=lpo_number).first()
                    order = PurchaseOrder.query.filter_by(lpo_id=lpo.id).first() if lpo else None
                quantity_received = int(request.form.get('quantity_received'))
                preliminary_condition = request.form.get('preliminary_condition')
                comparison_notes = request.form.get('comparison_notes')
                
                # Log delivery processing start
                log_inventory_action(
                    action='delivery_processing_start',
                    resource_type='purchase_order',
                    resource_id=0,
                    description=f"Starting delivery processing for LPO: {lpo_number}",
                    new_values={
                        'quantity_received': quantity_received,
                        'lpo_number': lpo_number
                    },
                    module='delivery'
                )
                
                # Get LPO and PurchaseOrder
                lpo = LPO.query.filter_by(lpo_number=lpo_number).first()
                order = PurchaseOrder.query.filter_by(lpo_id=lpo.id).first()
                
                if not lpo or not order:
                    log_inventory_action(
                        action='delivery_processing_failed',
                        resource_type='purchase_order',
                        resource_id=0,
                        description=f"LPO or PO not found during delivery processing: {lpo_number}",
                        module='delivery'
                    )
                    flash('LPO or purchase order not found. Please start over.', 'error')
                    return redirect(url_for('store_web_bp.record_delivery'))
                
                # FIXED: Ensure quantity_delivered is not None
                old_quantity_delivered = order.quantity_delivered or 0
                if order.quantity_delivered is None:
                    order.quantity_delivered = 0
                
                # Extract form data from final submission
                batch_number = request.form.get('batch_number')
                expiration_date = request.form.get('expiration_date')
                serial_numbers = request.form.get('serial_numbers')
                condition = request.form.get('condition')
                storage_temp = request.form.get('storage_temp')
                location = request.form.get('location')
                inspector = request.form.get('inspector')
                notes = request.form.get('notes')
                
                # Combine notes from comparison and final form
                combined_notes = f"Comparison Notes: {comparison_notes}\n\nDelivery Notes: {notes}"
                
                # Handle file uploads
                attachment_paths = []
                for file in request.files.getlist('attachments'):
                    if file.filename:
                        filename = secure_filename(file.filename)
                        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        attachment_paths.append(file_path)
                
                # 1. Create PurchaseOrderDelivery record
                delivery = PurchaseOrderDelivery(
                    purchase_order_id=order.id,
                    delivery_date=datetime.utcnow(),
                    quantity_delivered=quantity_received,
                    batch_number=batch_number,
                    condition=condition,
                    storage_temp=storage_temp,
                    inspector=inspector,
                    serial_numbers=serial_numbers,
                    expiration_date=datetime.strptime(expiration_date, '%Y-%m-%d') if expiration_date else None,
                    delivery_notes=combined_notes,
                    attachments=",".join(attachment_paths) if attachment_paths else None,
                    created_by=current_user.id
                )
                
                # Generate delivery number
                delivery.generate_delivery_number()
                db.session.add(delivery)
                db.session.flush()  # Get delivery ID
                
                # Log delivery creation
                log_inventory_action(
                    action='delivery_created',
                    resource_type='delivery',
                    resource_id=delivery.id,
                    description=f"Created delivery {delivery.delivery_number} for {quantity_received} units",
                    new_values={
                        'delivery_number': delivery.delivery_number,
                        'quantity_delivered': quantity_received,
                        'batch_number': batch_number,
                        'condition': condition,
                        'inspector': inspector,
                        'expiration_date': expiration_date
                    },
                    module='delivery'
                )
                
                # 2. Update PurchaseOrder delivered quantity and status
                old_status = order.status
                order.quantity_delivered += quantity_received
                order.update_delivery_status()
                
                # Log PO update
                log_inventory_action(
                    action='purchase_order_updated',
                    resource_type='purchase_order',
                    resource_id=order.id,
                    description=f"Updated PO delivered quantity from {old_quantity_delivered} to {order.quantity_delivered}",
                    old_values={
                        'quantity_delivered': old_quantity_delivered,
                        'status': old_status
                    },
                    new_values={
                        'quantity_delivered': order.quantity_delivered,
                        'status': order.status
                    },
                    changed_fields=['quantity_delivered', 'status'],
                    module='delivery'
                )
                
                # If this is the first delivery, set the delivery date
                if order.quantity_delivered == quantity_received:  # First delivery
                    order.delivery_date = datetime.utcnow()
                
                # Get category from requisition if exists, otherwise default to supplier category
                category = order.supplier.category
                if order.requisition:
                    category = order.requisition.category
                
                # 3. Update or Create Stock entry
                existing_stock = Stock.query.filter_by(
                    batch_number=batch_number,
                    purchase_order_id=order.id,
                    name=order.item_name
                ).first()
                
                if existing_stock:
                    # Log existing stock found
                    log_inventory_action(
                        action='existing_stock_found',
                        resource_type='stock',
                        resource_id=existing_stock.id,
                        description=f"Found existing stock for batch {batch_number}, updating quantity",
                        old_values={'quantity': existing_stock.quantity},
                        module='inventory'
                    )
                    
                    # Update existing stock
                    old_stock_quantity = existing_stock.quantity
                    existing_stock.quantity += quantity_received
                    existing_stock.current_stock += quantity_received
                    existing_stock.last_restocked = datetime.utcnow()
                    
                    # Log stock update
                    log_inventory_action(
                        action='stock_updated',
                        resource_type='stock',
                        resource_id=existing_stock.id,
                        description=f"Updated stock quantity from {old_stock_quantity} to {existing_stock.quantity}",
                        old_values={
                            'quantity': old_stock_quantity,
                            'current_stock': old_stock_quantity
                        },
                        new_values={
                            'quantity': existing_stock.quantity,
                            'current_stock': existing_stock.current_stock,
                            'last_restocked': datetime.utcnow().isoformat()
                        },
                        changed_fields=['quantity', 'current_stock', 'last_restocked'],
                        module='inventory'
                    )
                    
                    # Update stock detail or create if doesn't exist
                    existing_detail = StockDetail.query.filter_by(stock_id=existing_stock.id).first()
                    if existing_detail:
                        existing_detail.condition = condition
                        existing_detail.storage_temp = storage_temp
                        existing_detail.inspector = inspector
                        existing_detail.delivery_notes = combined_notes
                        existing_detail.serial_numbers = serial_numbers
                        if attachment_paths:
                            existing_attachments = existing_detail.attachments.split(',') if existing_detail.attachments else []
                            existing_attachments.extend(attachment_paths)
                            existing_detail.attachments = ",".join(existing_attachments)
                    else:
                        existing_detail = StockDetail(
                            stock=existing_stock,
                            condition=condition,
                            storage_temp=storage_temp,
                            inspector=inspector,
                            delivery_notes=combined_notes,
                            serial_numbers=serial_numbers,
                            attachments=",".join(attachment_paths) if attachment_paths else None
                        )
                        db.session.add(existing_detail)
                    
                else:
                    # Log new stock creation
                    log_inventory_action(
                        action='new_stock_creation',
                        resource_type='stock',
                        resource_id=0,
                        description=f"Creating new stock item for {order.item_name} with batch {batch_number}",
                        module='inventory'
                    )
                    
                    # Create new stock entry
                    stock_item = Stock(
                        name=order.item_name,
                        category=category,
                        quantity=quantity_received,
                        unit_price=order.unit_price,
                        batch_number=batch_number,
                        expiration_date=datetime.strptime(expiration_date, '%Y-%m-%d') if expiration_date else None,
                        location=location,
                        supplier_id=order.supplier.id,
                        purchase_order_id=order.id,
                        reorder_level=max(50, quantity_received // 2),
                        current_stock=quantity_received
                    )
                    
                    # Generate derived fields
                    stock_item.sku = stock_item.generate_sku()
                    if not expiration_date:
                        stock_item.expiration_date = stock_item.calculate_expiration()
                    
                    # Create stock detail entry
                    stock_detail = StockDetail(
                        stock=stock_item,
                        condition=condition,
                        storage_temp=storage_temp,
                        inspector=inspector,
                        delivery_notes=combined_notes,
                        serial_numbers=serial_numbers,
                        attachments=",".join(attachment_paths) if attachment_paths else None
                    )
                    
                    db.session.add(stock_item)
                    db.session.add(stock_detail)
                    db.session.flush()  # Get stock ID
                    
                    # Log new stock created
                    log_inventory_action(
                        action='stock_created',
                        resource_type='stock',
                        resource_id=stock_item.id,
                        description=f"Created new stock item: {stock_item.name} (SKU: {stock_item.sku})",
                        new_values={
                            'name': stock_item.name,
                            'sku': stock_item.sku,
                            'category': stock_item.category,
                            'quantity': stock_item.quantity,
                            'batch_number': stock_item.batch_number,
                            'unit_price': stock_item.unit_price,
                            'location': stock_item.location
                        },
                        module='inventory'
                    )
                
                # 4. Create Supplier Account, Invoice, and Transaction
                supplier_account = SupplierAccount.query.filter_by(supplier_id=order.supplier.id).first()
                if not supplier_account:
                    # Log new supplier account creation
                    log_inventory_action(
                        action='supplier_account_created',
                        resource_type='supplier_account',
                        resource_id=0,
                        description=f"Creating new supplier account for {order.supplier.name}",
                        module='finance'
                    )
                    
                    supplier_account = SupplierAccount(
                        supplier_id=order.supplier.id,
                        account_type='regular',
                        credit_limit=100000.00,
                        current_balance=0.0
                    )
                    db.session.add(supplier_account)
                    db.session.flush()
                    supplier_account.generate_account_number()
                    
                    # Log supplier account created
                    log_inventory_action(
                        action='supplier_account_created_success',
                        resource_type='supplier_account',
                        resource_id=supplier_account.id,
                        description=f"Created supplier account: {supplier_account.account_number}",
                        new_values={
                            'account_number': supplier_account.account_number,
                            'supplier_name': order.supplier.name,
                            'credit_limit': supplier_account.credit_limit
                        },
                        module='finance'
                    )

                # CORRECTED: Calculate amount for this delivery ONLY (not proportional to total order)
                delivery_amount = quantity_received * order.unit_price
                
                # If there's tax, calculate it for this delivery
                tax_amount = 0.0
                if hasattr(order, 'tax_rate') and order.tax_rate:
                    tax_amount = (delivery_amount * order.tax_rate) / 100
                
                total_amount = delivery_amount + tax_amount
                
                # Log invoice creation
                log_inventory_action(
                    action='invoice_creation',
                    resource_type='supplier_invoice',
                    resource_id=0,
                    description=f"Creating invoice for delivery {delivery.delivery_number}",
                    new_values={
                        'delivery_amount': delivery_amount,
                        'tax_amount': tax_amount,
                        'total_amount': total_amount,
                        'quantity': quantity_received
                    },
                    module='finance'
                )
                
                invoice = SupplierInvoice(
                    supplier_account_id=supplier_account.id,
                    purchase_order_id=order.id,
                    delivery_id=delivery.id,
                    invoice_date=datetime.utcnow(),
                    delivery_date=datetime.utcnow(),
                    subtotal_amount=delivery_amount,
                    tax_amount=tax_amount,
                    total_amount=total_amount,
                    balance_due=total_amount,
                    payment_terms=order.supplier.payment_terms or 'Net 30',
                    status='issued',
                    items_delivered={
                        'item_name': order.item_name,
                        'quantity_delivered': quantity_received,
                        'unit_price': order.unit_price,
                        'subtotal_amount': delivery_amount,
                        'tax_amount': tax_amount,
                        'total_amount': total_amount,
                        'batch_number': batch_number,
                        'delivery_condition': condition,
                        'comparison_notes': comparison_notes,
                        'delivery_number': delivery.delivery_number,
                        'tax_rate': getattr(order, 'tax_rate', 0)
                    }
                )

                invoice.generate_invoice_number()
                invoice.calculate_due_date()
                db.session.add(invoice)
                db.session.flush()

                if 'TEMP' in invoice.invoice_number:
                    invoice.generate_invoice_number()

                # Log invoice created
                log_inventory_action(
                    action='invoice_created',
                    resource_type='supplier_invoice',
                    resource_id=invoice.id,
                    description=f"Created invoice {invoice.invoice_number} for {total_amount}",
                    new_values={
                        'invoice_number': invoice.invoice_number,
                        'total_amount': total_amount,
                        'due_date': invoice.due_date.isoformat() if invoice.due_date else None
                    },
                    module='finance'
                )

                # Create transaction
                old_supplier_balance = supplier_account.current_balance
                transaction = SupplierTransaction(
                    supplier_account_id=supplier_account.id,
                    invoice_id=invoice.id,
                    transaction_type='invoice',
                    amount=invoice.total_amount,
                    balance_after=supplier_account.current_balance + invoice.total_amount,
                    description=f"Delivery Invoice for {order.item_name} - Qty: {quantity_received} (Delivery: {delivery.delivery_number})",
                    reference=invoice.invoice_number
                )
                
                # Update supplier account balance with this delivery's amount only
                supplier_account.current_balance += invoice.total_amount
                supplier_account.total_orders += 1
                supplier_account.total_order_value += invoice.total_amount
                supplier_account.last_payment_date = datetime.utcnow()
                
                # Log supplier account update
                log_inventory_action(
                    action='supplier_account_updated',
                    resource_type='supplier_account',
                    resource_id=supplier_account.id,
                    description=f"Updated supplier account balance for {order.supplier.name}",
                    old_values={'current_balance': old_supplier_balance},
                    new_values={'current_balance': supplier_account.current_balance},
                    changed_fields=['current_balance'],
                    module='finance'
                )
                
                # Log transaction creation
                log_inventory_action(
                    action='transaction_created',
                    resource_type='supplier_transaction',
                    resource_id=0,
                    description=f"Created transaction for invoice {invoice.invoice_number}",
                    new_values={
                        'amount': invoice.total_amount,
                        'transaction_type': 'invoice',
                        'reference': invoice.invoice_number
                    },
                    module='finance'
                )
                
                # Update LPO status if fully delivered
                if order.is_fully_delivered:
                    old_lpo_status = lpo.status
                    lpo.status = 'delivered'
                    lpo.updated_at = datetime.utcnow()
                    
                    # Log LPO status change
                    log_inventory_action(
                        action='lpo_status_updated',
                        resource_type='lpo',
                        resource_id=lpo.id,
                        description=f"LPO marked as delivered",
                        old_values={'status': old_lpo_status},
                        new_values={'status': 'delivered'},
                        changed_fields=['status'],
                        module='procurement'
                    )
                
                # Update supplier
                order.supplier.last_order_date = datetime.utcnow()
                
                # Update requisition status if exists and fully delivered
                if order.requisition and order.is_fully_delivered:
                    old_requisition_status = order.requisition.status
                    order.requisition.status = 'completed'
                    
                    # Log requisition status change
                    log_inventory_action(
                        action='requisition_completed',
                        resource_type='requisition',
                        resource_id=order.requisition.id,
                        description=f"Requisition marked as completed",
                        old_values={'status': old_requisition_status},
                        new_values={'status': 'completed'},
                        changed_fields=['status'],
                        module='procurement'
                    )
                
                # Update external order status if exists and fully delivered
                if lpo.external_order and order.is_fully_delivered:
                    old_external_order_status = lpo.external_order.status
                    lpo.external_order.status = 'delivered'
                    lpo.external_order.updated_at = datetime.utcnow()
                    
                    # Log external order status change
                    log_inventory_action(
                        action='external_order_delivered',
                        resource_type='external_order',
                        resource_id=lpo.external_order.id,
                        description=f"External order marked as delivered",
                        old_values={'status': old_external_order_status},
                        new_values={'status': 'delivered'},
                        changed_fields=['status'],
                        module='procurement'
                    )
                
                # Save to database
                db.session.add(invoice)
                db.session.add(transaction)
                db.session.commit()
                
                # Log successful delivery completion
                log_inventory_action(
                    action='delivery_completed_success',
                    resource_type='delivery',
                    resource_id=delivery.id,
                    description=f"Successfully completed delivery processing for {quantity_received} units",
                    new_values={
                        'delivery_number': delivery.delivery_number,
                        'invoice_number': invoice.invoice_number,
                        'total_amount': total_amount,
                        'is_fully_delivered': order.is_fully_delivered
                    },
                    module='delivery'
                )
                
                if order.is_fully_delivered:
                    flash(f'Final delivery recorded! Order fully delivered. Stock updated and invoice for {quantity_received} {order.unit} created.', 'success')
                else:
                    flash(f'Partial delivery recorded! {order.pending_quantity} {order.unit} remaining. Stock updated and invoice for {quantity_received} {order.unit} created.', 'success')
                
                return redirect(url_for('store_web_bp.purchase_orders'))
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error recording delivery: {str(e)}")
                
                # Log delivery failure
                log_inventory_action(
                    action='delivery_failed',
                    resource_type='delivery',
                    resource_id=0,
                    description=f"Delivery processing failed: {str(e)}",
                    module='delivery'
                )
                
                flash(f'Error recording delivery: {str(e)}', 'danger')
                return redirect(url_for('store_web_bp.record_delivery'))
    
    else:
        # GET request
        if order_id:
            # Load the specific purchase order
            purchase_order = PurchaseOrder.query.get_or_404(order_id)
            lpo = LPO.query.get(purchase_order.lpo_id) if purchase_order.lpo_id else None
            
            # Ensure quantity_delivered is set
            if purchase_order.quantity_delivered is None:
                purchase_order.quantity_delivered = 0
            
            # Log access
            log_inventory_action(
                action='direct_delivery_access',
                resource_type='purchase_order',
                resource_id=purchase_order.id,
                description=f"Direct delivery access for order #{purchase_order.id}",
                module='delivery'
            )
            
            return render_template('record_delivery.html',
                                 lpo_verified=True,
                                 lpo=lpo,
                                 purchase_order=purchase_order,
                                 show_form=False)  # Show details, not input form
        else:
            # No order_id – show LPO input form
            return render_template('record_delivery.html', lpo_verified=False)

# Keep the old route for backward compatibility, but redirect to new flow
@store_web_bp.route('/purchase-orders/<int:id>/record-delivery', methods=['GET'])
def old_record_delivery(id):
    # Redirect to the new LPO-based flow
    flash('Please use the new delivery recording process by entering the LPO number.', 'info')
    return redirect(url_for('store_web_bp.record_delivery'))



@store_web_bp.route('/inventory-logs')
def inventory_logs():
    """Display inventory audit logs with filtering and pagination"""
    try:
        # Get page number from request args, default to 1
        page = request.args.get('page', 1, type=int)
        per_page = 20  # Number of logs per page
        
        # Get filter parameters
        action_filter = request.args.get('action')
        resource_type_filter = request.args.get('resource_type')
        module_filter = request.args.get('module')
        user_filter = request.args.get('user')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Start with base query
        query = InventoryAuditLog.query
        
        # Apply filters
        if action_filter:
            query = query.filter(InventoryAuditLog.action == action_filter)
        if resource_type_filter:
            query = query.filter(InventoryAuditLog.resource_type == resource_type_filter)
        if module_filter:
            query = query.filter(InventoryAuditLog.module == module_filter)
        if user_filter:
            query = query.filter(InventoryAuditLog.username.ilike(f'%{user_filter}%'))
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(InventoryAuditLog.timestamp >= date_from_obj)
            except ValueError:
                flash('Invalid date format for start date', 'error')
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                # Add one day to include the entire end date
                date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                query = query.filter(InventoryAuditLog.timestamp <= date_to_obj)
            except ValueError:
                flash('Invalid date format for end date', 'error')
        
        # Order by timestamp descending (newest first)
        query = query.order_by(InventoryAuditLog.timestamp.desc())
        
        # Paginate the results
        logs = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Get unique values for filter dropdowns
        actions = db.session.query(
            InventoryAuditLog.action
        ).distinct().all()
        actions = [action[0] for action in actions]
        
        resource_types = db.session.query(
            InventoryAuditLog.resource_type
        ).distinct().all()
        resource_types = [rt[0] for rt in resource_types]
        
        modules = db.session.query(
            InventoryAuditLog.module
        ).distinct().all()
        modules = [module[0] for module in modules]
        
        # Log page access
        log_inventory_action(
            action='page_access',
            resource_type='system',
            resource_id=0,
            description="Accessed inventory logs page",
            module='audit'
        )
        
        return render_template(
            'inventory_logs.html',
            logs=logs,
            actions=actions,
            resource_types=resource_types,
            modules=modules,
            current_filters={
                'action': action_filter,
                'resource_type': resource_type_filter,
                'module': module_filter,
                'user': user_filter,
                'date_from': date_from,
                'date_to': date_to
            }
        )
        
    except Exception as e:
        current_app.logger.error(f"Error loading inventory logs: {str(e)}")
        flash('Error loading inventory logs', 'error')
        return redirect(url_for('store_web_bp.dashboard'))
    
    
    
# Inventory Reports
@store_web_bp.route('/reports')
def inventory_reports():
    return render_template('reports.html')



@store_web_bp.route('/reports/low-stock')
def low_stock_report():
    """Items below reorder level"""
    low_stock = Stock.query.filter(
        Stock.current_stock <= Stock.reorder_level,
        Stock.is_active == True
    ).all()
    
    # Calculate total value at risk for each item
    for item in low_stock:
        item.total_value_at_risk = item.unit_price * item.current_stock
    
    return render_template('reports/low_stock.html', 
                         items=low_stock, 
                         now=datetime.utcnow())
    
@store_web_bp.route('/reports/stock-valuation')
def stock_valuation():
    """Total inventory value by category"""
    valuation = db.session.query(
        Stock.category,
        db.func.sum(Stock.current_stock * Stock.unit_price).label('total_value'),
        db.func.sum(Stock.current_stock).label('total_quantity')
    ).filter(Stock.is_active == True).group_by(Stock.category).all()
    
    # Convert decimal values to float for template calculations
    processed_data = []
    for item in valuation:
        processed_data.append({
            'category': item.category,
            'total_value': float(item.total_value) if item.total_value else 0.0,
            'total_quantity': float(item.total_quantity) if item.total_quantity else 0.0
        })
    
    # Calculate grand total
    grand_total = sum(item['total_value'] for item in processed_data)
    
    # Get top categories
    top_categories = sorted(processed_data, key=lambda x: x['total_value'], reverse=True)[:5]
    
    # Calculate top 3 total for insights
    top_3_total = sum(item['total_value'] for item in top_categories[:3])
    top_3_percentage = (top_3_total / grand_total * 100) if grand_total > 0 else 0
    
    # Get highest and lowest categories
    if processed_data:
        highest_category = max(processed_data, key=lambda x: x['total_value'])
        lowest_category = min(processed_data, key=lambda x: x['total_value'])
    else:
        highest_category = {'category': 'N/A', 'total_value': 0}
        lowest_category = {'category': 'N/A', 'total_value': 0}
    
    return render_template('reports/stock_valuation.html', 
                         data=processed_data, 
                         top_categories=top_categories,
                         grand_total=grand_total,
                         top_3_percentage=top_3_percentage,
                         highest_category=highest_category,
                         lowest_category=lowest_category,
                         now=datetime.utcnow())

# Purchase & Procurement Reports
@store_web_bp.route('/reports/po-status')
def po_status_report():
    """POs by status with delivery progress"""
    pos = PurchaseOrder.query.options(
        db.joinedload(PurchaseOrder.supplier),
        db.joinedload(PurchaseOrder.deliveries)
    ).all()
    return render_template('reports/po_status.html', purchase_orders=pos)

@store_web_bp.route('/reports/supplier-performance')
def supplier_performance():
    """Supplier on-time delivery and quality metrics"""
    suppliers = SupplierAccount.query.options(
        db.joinedload(SupplierAccount.supplier)
    ).all()
    return render_template('reports/supplier_performance.html', suppliers=suppliers)

# Delivery & Receiving Reports
@store_web_bp.route('/reports/delivery-tracking')
def delivery_tracking():
    """Track deliveries against POs"""
    deliveries = PurchaseOrderDelivery.query.options(
        db.joinedload(PurchaseOrderDelivery.purchase_order)
    ).all()
    return render_template('reports/delivery_tracking.html', deliveries=deliveries)

@store_web_bp.route('/reports/quality-inspection')
def quality_inspection():
    """Items by condition and quality status"""
    quality_data = PurchaseOrderDelivery.query.with_entities(
        PurchaseOrderDelivery.condition,
        db.func.count(PurchaseOrderDelivery.id).label('count')
    ).group_by(PurchaseOrderDelivery.condition).all()
    return render_template('reports/quality_inspection.html', data=quality_data)

# Financial Reports
@store_web_bp.route('/reports/accounts-payable')
def accounts_payable():
    """Outstanding supplier invoices"""
    invoices = SupplierInvoice.query.filter(
        SupplierInvoice.status.in_(['pending', 'partially_paid', 'overdue'])
    ).options(
        db.joinedload(SupplierInvoice.supplier_account).joinedload(SupplierAccount.supplier)
    ).all()
    return render_template('reports/accounts_payable.html', invoices=invoices)

@store_web_bp.route('/reports/payment-requests')
def payment_requests_report():
    """Payment requests by approval status"""
    requests = PaymentRequest.query.options(
        db.joinedload(PaymentRequest.invoice).joinedload(SupplierInvoice.supplier_account).joinedload(SupplierAccount.supplier),
        db.joinedload(PaymentRequest.requester)
    ).all()
    return render_template('reports/payment_requests.html', requests=requests)

# Stock Request & Issuance Reports
@store_web_bp.route('/reports/stock-requests')
def stock_requests_report():
    """Requests by department and status"""
    requests = StockRequest.query.options(
        db.joinedload(StockRequest.stock),
        db.joinedload(StockRequest.requester)
    ).all()
    return render_template('reports/stock_requests.html', requests=requests)

@store_web_bp.route('/reports/department-consumption')
def department_consumption():
    """Stock usage by department"""
    consumption = StockRequest.query.with_entities(
        StockRequest.department,
        db.func.sum(StockRequest.quantity_issued).label('total_issued'),
        db.func.count(StockRequest.id).label('request_count')
    ).filter(StockRequest.status == 'fulfilled').group_by(StockRequest.department).all()
    return render_template('reports/department_consumption.html', data=consumption)

# Expiry & Batch Reports
@store_web_bp.route('/reports/expiry-alerts')
def expiry_alerts():
    """Items expiring in next 30/60/90 days"""
    thirty_days = datetime.utcnow() + timedelta(days=30)
    sixty_days = datetime.utcnow() + timedelta(days=60)
    
    expiring_soon = Stock.query.filter(
        Stock.expiration_date <= thirty_days,
        Stock.is_active == True
    ).all()
    
    expiring_later = Stock.query.filter(
        Stock.expiration_date > thirty_days,
        Stock.expiration_date <= sixty_days,
        Stock.is_active == True
    ).all()
    
    return render_template('reports/expiry_alerts.html', 
                         soon=expiring_soon, later=expiring_later)

@store_web_bp.route('/reports/batch-tracking')
def batch_tracking():
    """Track items by batch number"""
    batches = Stock.query.with_entities(
        Stock.batch_number,
        db.func.count(Stock.id).label('item_count'),
        db.func.min(Stock.expiration_date).label('earliest_expiry'),
        db.func.sum(Stock.current_stock).label('total_stock')
    ).group_by(Stock.batch_number).all()
    return render_template('reports/batch_tracking.html', batches=batches)

# Audit & Compliance Reports
@store_web_bp.route('/reports/audit-trail')
def audit_trail():
    """All inventory changes and transactions"""
    audits = InventoryAuditLog.query.order_by(
        InventoryAuditLog.timestamp.desc()
    ).limit(1000).all()
    return render_template('reports/audit_trail.html', audits=audits)

@store_web_bp.route('/reports/stock-movement')
def stock_movement():
    """Incoming/outgoing stock flows"""
    movements = StockFlow.query.options(
        db.joinedload(StockFlow.stock),
        db.joinedload(StockFlow.request)
    ).order_by(StockFlow.date.desc()).limit(500).all()
    return render_template('reports/stock_movement.html', movements=movements)

# Requisition & Approval Reports
@store_web_bp.route('/reports/external-orders')
def external_orders_report():
    """Requisitions by approval status"""
    orders = ExternalOrder.query.options(
        db.joinedload(ExternalOrder.user),
        db.joinedload(ExternalOrder.supplier)
    ).all()
    return render_template('reports/external_orders.html', orders=orders)

@store_web_bp.route('/reports/lpo-status')
def lpo_status_report():
    """LPOs by approval and completion status"""
    lpos = LPO.query.options(
        db.joinedload(LPO.external_order),
        db.joinedload(LPO.supplier)
    ).all()
    return render_template('reports/lpo_status.html', lpos=lpos)

# Additional Analysis Reports
@store_web_bp.route('/reports/inventory-turnover')
def inventory_turnover():
    """Calculate inventory turnover ratios"""
    # Implementation for turnover calculation
    turnover_data = []  # Add your turnover calculation logic
    return render_template('reports/inventory_turnover.html', data=turnover_data)

@store_web_bp.route('/reports/supplier-spend')
def supplier_spend():
    """Supplier spending analysis"""
    spend_data = db.session.query(
        Supplier.name,
        db.func.sum(PurchaseOrder.total_price).label('total_spend'),
        db.func.count(PurchaseOrder.id).label('order_count')
    ).join(PurchaseOrder).group_by(Supplier.id, Supplier.name).all()
    return render_template('reports/supplier_spend.html', data=spend_data)





import os
import json
import logging
import time
import requests
from flask import request, jsonify, Response, stream_with_context
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func



def get_inventory_context():
    """
    Fetch comprehensive inventory data and return a formatted summary.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func

    today = datetime.today().date()
    context_parts = []

    # Helper to convert Decimal to float
    def safe_float(value):
        return float(value) if value is not None else 0.0

    # ----- Stock Summary -----
    all_stocks = Stock.query.filter_by(is_active=True).all()
    total_items = len(all_stocks)
    total_quantity = sum(s.quantity for s in all_stocks)
    total_cost_value = sum(s.valuation_at_cost for s in all_stocks)
    total_selling_value = sum(s.valuation_at_selling_price for s in all_stocks)

    # Low stock items
    low_stock = [s for s in all_stocks if s.quantity <= s.reorder_level]
    low_stock_count = len(low_stock)
    low_stock_list = "\n".join(
        f"  - {s.name} (SKU: {s.sku}): {s.quantity} units, reorder level {s.reorder_level}"
        for s in low_stock[:10]
    )

    # Expiring items (within 30 days)
    expiring = [s for s in all_stocks if s.expiration_date and (s.expiration_date.date() - today).days <= 30]
    expiring_count = len(expiring)
    expiring_list = "\n".join(
        f"  - {s.name} (SKU: {s.sku}): expires on {s.expiration_date.strftime('%Y-%m-%d')}"
        for s in expiring[:10]
    )

    context_parts.append(f"## Inventory Summary (as of {today.isoformat()})\n")
    context_parts.append(f"- **Total Items:** {total_items}\n")
    context_parts.append(f"- **Total Quantity:** {total_quantity}\n")
    context_parts.append(f"- **Total Cost Value:** KES {total_cost_value:,.2f}\n")
    context_parts.append(f"- **Total Selling Value:** KES {total_selling_value:,.2f}\n")
    context_parts.append(f"- **Low Stock Items:** {low_stock_count}\n")
    if low_stock_list:
        context_parts.append(f"\n**Low Stock Items:**\n{low_stock_list}\n")
    context_parts.append(f"- **Items Expiring Soon:** {expiring_count}\n")
    if expiring_list:
        context_parts.append(f"\n**Expiring Items:**\n{expiring_list}\n")
    context_parts.append("\n")

    # ----- Department Stock Reports (Pharmacy, Lab, Radiology) -----
    # Pharmacy
    from app.pharmacy.models import PharmacyInventory
    pharm_items = PharmacyInventory.query.all()
    pharm_total_value = sum(i.quantity * safe_float(i.buying_price) for i in pharm_items)
    pharm_low_stock = [i for i in pharm_items if i.quantity <= (i.reorder_level or 0)]
    context_parts.append("### Pharmacy Stock\n")
    context_parts.append(f"- **Total Value:** KES {pharm_total_value:,.2f}\n")
    context_parts.append(f"- **Low Stock Items:** {len(pharm_low_stock)}\n")
    if pharm_low_stock:
        for i in pharm_low_stock[:5]:
            context_parts.append(f"  - {i.item_name}: {i.quantity} units (reorder at {i.reorder_level})\n")
    context_parts.append("\n")

    # Laboratory
    from app.lab.models import LabInventory
    lab_items = LabInventory.query.all()
    lab_total_value = sum(i.quantity * safe_float(i.buying_price) for i in lab_items)
    lab_low_stock = [i for i in lab_items if i.quantity <= (i.reorder_level or 0)]
    context_parts.append("### Laboratory Stock\n")
    context_parts.append(f"- **Total Value:** KES {lab_total_value:,.2f}\n")
    context_parts.append(f"- **Low Stock Items:** {len(lab_low_stock)}\n")
    if lab_low_stock:
        for i in lab_low_stock[:5]:
            context_parts.append(f"  - {i.item_name}: {i.quantity} units (reorder at {i.reorder_level})\n")
    context_parts.append("\n")

    # Radiology
    from app.radiology.models import RadiologyInventory
    rad_items = RadiologyInventory.query.all()
    rad_total_value = sum(i.quantity * safe_float(i.buying_price) for i in rad_items)
    rad_low_stock = [i for i in rad_items if i.quantity <= (i.reorder_level or 0)]
    context_parts.append("### Radiology Stock\n")
    context_parts.append(f"- **Total Value:** KES {rad_total_value:,.2f}\n")
    context_parts.append(f"- **Low Stock Items:** {len(rad_low_stock)}\n")
    if rad_low_stock:
        for i in rad_low_stock[:5]:
            context_parts.append(f"  - {i.item_name}: {i.quantity} units (reorder at {i.reorder_level})\n")
    context_parts.append("\n")

    # ----- Purchase Orders Summary -----
    pending_pos = PurchaseOrder.query.filter(PurchaseOrder.status.in_(['ordered', 'shipped', 'partially_delivered'])).all()
    overdue_pos = [po for po in pending_pos if po.delivery_date and po.delivery_date.date() < today]
    context_parts.append("### Purchase Orders\n")
    context_parts.append(f"- **Pending Orders:** {len(pending_pos)}\n")
    context_parts.append(f"- **Overdue Orders:** {len(overdue_pos)}\n")
    if overdue_pos:
        for po in overdue_pos[:5]:
            supplier = po.supplier.name if po.supplier else "Unknown"
            context_parts.append(f"  - PO {po.id}: {po.item_name} (Qty: {po.quantity}) from {supplier}, due {po.delivery_date.strftime('%Y-%m-%d')}\n")
    context_parts.append("\n")

    # ----- Stock Requests Summary -----
    pending_requests = StockRequest.query.filter(
        StockRequest.status.in_(['submitted', 'approved', 'processing'])
    ).all()
    high_priority = [r for r in pending_requests if r.priority == 'emergency']
    context_parts.append("### Stock Requests\n")
    context_parts.append(f"- **Pending Requests:** {len(pending_requests)}\n")
    context_parts.append(f"- **Emergency Requests:** {len(high_priority)}\n")
    if high_priority:
        for r in high_priority[:5]:
            context_parts.append(f"  - {r.stock.name} (SKU: {r.stock.sku}) from {r.department}, qty {r.quantity_requested}, priority {r.priority}\n")
    context_parts.append("\n")

    # ----- Supplier Performance (Top 5 by rating) -----
    top_suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.rating.desc()).limit(5).all()
    context_parts.append("### Top Suppliers\n")
    for sup in top_suppliers:
        context_parts.append(f"- **{sup.name}** (Rating: {sup.rating}/5, Lead time: {sup.lead_time} days, Last order: {sup.last_order_date.strftime('%Y-%m-%d') if sup.last_order_date else 'Never'})\n")
    context_parts.append("\n")

    # ----- Inventory Turnover (optional, if COGS data available) -----
    # Not included here – you can extend.

    return "".join(context_parts)





@store_web_bp.route('/ai-conversation')
@login_required
def get_ai_conversation():
    """Return all AI assistant messages for the current user."""
    conversation = InventoryConversation.query.filter_by(user_id=current_user.id).first()
    if not conversation:
        return jsonify([])

    messages = []
    for msg in InventoryMessage.query.filter_by(conversation_id=conversation.id).order_by(InventoryMessage.created_at.asc()):
        messages.append({
            'role': msg.role,
            'content': msg.content,
            'created_at': msg.created_at.isoformat()
        })
    return jsonify(messages)




OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"  # or your preferred model


@store_web_bp.route('/ai-assistant-stream')
@login_required
def ai_assistant_stream():
    message = request.args.get('message', '')
    if not message:
        return jsonify({'error': 'No message'}), 400

    # Get or create conversation for this user
    conversation = InventoryConversation.query.filter_by(user_id=current_user.id).first()
    if not conversation:
        conversation = InventoryConversation(user_id=current_user.id)
        db.session.add(conversation)
        db.session.commit()

    # Build system prompt with inventory context
    context = get_inventory_context()
    system_prompt = f"""You are a state‑of‑the‑art Inventory AI Assistant integrated into a hospital inventory management system. You have access to the following current inventory data:

{context}

**Your Role:**
- Answer inventory‑related questions, provide insights, and help with stock management.
- Suggest reorder levels, identify slow‑moving items, and recommend actions for low stock or expiring items.
- Format your answers in clear Markdown.
- **Include a separate reasoning section** before your final answer. Use the headings:
  - `## Reasoning` for your step‑by‑step thought process.
  - `## Answer` for your final response.
- Be concise, data‑driven, and professional.
- End every response with the disclaimer: *"These suggestions are generated by AI and are not a substitute for professional inventory management decisions. Always verify with physical stock and consult with inventory personnel."*

**Capabilities:**
- You can recommend reorder quantities.
- You can highlight stock that is about to expire.
- You can suggest actions to reduce stockouts.
- You can provide insights on supplier performance.

If you need more information to make a recommendation, ask clarifying questions.
"""

    # Build message list for AI – query messages directly
    previous_messages = []
    for msg in InventoryMessage.query.filter_by(conversation_id=conversation.id).order_by(InventoryMessage.created_at.asc()):
        previous_messages.append({"role": msg.role, "content": msg.content})

    messages_for_ai = [{"role": "system", "content": system_prompt}] + previous_messages
    messages_for_ai.append({"role": "user", "content": message})

    # Save user message
    user_msg = InventoryMessage(conversation_id=conversation.id, role='user', content=message)
    db.session.add(user_msg)
    db.session.commit()

    # Prepare OpenRouter streaming request
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": messages_for_ai,
        "temperature": 0.7,
        "max_tokens": 2000,
        "stream": True
    }

    def generate():
        full_response = ""
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                response = requests.post(OPENROUTER_URL, json=payload, headers=headers, stream=True, timeout=60)
                if response.status_code != 200:
                    logging.error(f"OpenRouter error {response.status_code}: {response.text}")
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        yield f"data: {json.dumps({'error': f'API returned {response.status_code}'})}\n\n"
                        return
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logging.error(f"Connection error attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    yield f"data: {json.dumps({'error': 'Network error connecting to AI service. Please try again later.'})}\n\n"
                    return
            except Exception as e:
                logging.error(f"Unexpected error: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                return

        # Process streaming response
        try:
            chunk_count = 0
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk['choices'][0]['delta'].get('content', '')
                            if delta:
                                chunk_count += 1
                                full_response += delta
                                if chunk_count % 10 == 0:
                                    logging.info(f"Chunk {chunk_count}, length {len(full_response)}")
                                yield f"data: {json.dumps({'chunk': delta})}\n\n"
                        except json.JSONDecodeError:
                            continue
            logging.info(f"Stream finished. Total chunks: {chunk_count}")
            if full_response:
                assistant_msg = InventoryMessage(conversation_id=conversation.id, role='assistant', content=full_response)
                db.session.add(assistant_msg)
                db.session.commit()
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logging.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            db.session.close()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')