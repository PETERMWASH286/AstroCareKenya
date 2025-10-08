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
from app.lab.models import LabInventory
from app.patients.models import Service
from app.pharmacy.models import PharmacyInventory
from app.radiology.models import RadiologyInventory
from app.store.models import LPO, ExternalOrder, PurchaseOrder, Stock, StockDetail, StockFlow, StockRequest, Supplier, SupplierAccount, SupplierInvoice, SupplierTransaction
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
    # Eager load supplier data with each order
    orders = PurchaseOrder.query.options(db.joinedload(PurchaseOrder.supplier)) \
                         .order_by(PurchaseOrder.order_date.desc()) \
                         .all()
    
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    return render_template('purchase_orders.html', 
                         purchase_orders=orders,
                         suppliers=suppliers)

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
 
# Inventory Reports
@store_web_bp.route('/reports')
def inventory_reports():
    return render_template('store/reports.html')



@store_web_bp.route('/suppliers/create', methods=['POST'])
def create_supplier():
    try:
        # Validate required fields
        required_fields = ['name', 'contact', 'phone', 'category']
        for field in required_fields:
            if not request.form.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate email format if provided
        email = request.form.get('email')
        if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({'error': 'Invalid email format'}), 400

        # Check for existing supplier with same name or email
        existing = Supplier.query.filter(
            (Supplier.name == request.form['name']) | 
            (Supplier.email == email)
        ).first()
        if existing:
            return jsonify({'error': 'Supplier with this name or email already exists'}), 409

        # Convert lead_time to integer
        lead_time = request.form.get('lead_time')
        if lead_time:
            try:
                lead_time = int(lead_time)
            except ValueError:
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
        db.session.commit()

        return jsonify({
            'message': 'Supplier created successfully',
            'supplier_id': supplier.id
        }), 201

    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error creating supplier: {str(e)}')
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

            # Mark approved WITHOUT updating stock
            req.status = 'approved'
            req.quantity_approved = req.quantity_requested
            req.approver_id = current_user.id
            req.approval_date = datetime.utcnow()

            # NO stock deduction here
            # NO inventory updates here
            # NO stock flow records here

        # ✅ Collect request (UPDATE stock and create stock flow)
        elif action == 'collect':
            if req.status != 'approved':
                raise ValueError("Only approved requests can be collected")

            collected_by = data.get('collected_by', '').strip()
            collection_notes = data.get('collection_notes', '').strip()
            
            if not collected_by:
                raise ValueError("Collector name is required")

            # Verify stock is still available
            if req.stock.current_stock < req.quantity_approved:
                raise ValueError(f"Insufficient stock. Available: {req.stock.current_stock}")

            # Deduct from main stock safely
            stock = req.stock
            stock.current_stock -= req.quantity_approved
            if stock.current_stock < 0:
                raise ValueError("Stock deduction went negative, aborting")

            # Route into department-specific inventory
            dept = req.department.lower()
            approved_qty = req.quantity_approved
            service = Service.query.filter_by(name=stock.name, category='Pharmacy').first()

            # Helper function for inventory updates
            def update_inventory(model_cls, has_expiry=True):
                inv = model_cls.query.filter_by(item_name=stock.name).first()
                if not inv:
                    inv = model_cls(
                        item_name=stock.name,
                        category=stock.category,
                        quantity=approved_qty,
                        expiry_date=stock.expiration_date if has_expiry else None,
                        supplier=stock.supplier.name if stock.supplier else None
                    )
                    db.session.add(inv)
                else:
                    inv.quantity += approved_qty

            if dept == "lab":
                update_inventory(LabInventory)
            elif dept == "pharmacy":
                update_inventory(PharmacyInventory)
            elif dept == "radiology":
                update_inventory(RadiologyInventory)
            elif dept == "hr":
                update_inventory(HRInventory, has_expiry=False)
            else:
                raise ValueError(f"Unknown department: {req.department}")

            # ✅ Stock flow records for collection
            db.session.add_all([
                StockFlow(
                    stock_id=stock.id,
                    service_id=service.id if service else None,
                    quantity_change=-req.quantity_approved,
                    flow_type='collection',
                    reference_id=req.id,
                    notes=f'Stock collection for {req.quantity_approved} units'
                ),
                StockFlow(
                    service_id=service.id if service else None,
                    quantity_change=req.quantity_approved,
                    flow_type='collection',
                    reference_id=req.id,
                    notes=f'Stock received from collection {req.id}'
                )
            ])

            # Update collection and issuance details
            req.status = 'fulfilled'
            req.collected_by = collected_by
            req.collection_notes = collection_notes
            req.collected_at = datetime.utcnow()
            req.quantity_issued = req.quantity_approved
            
            # ✅ Set issued_by (current user) and issue_date (current time)
            req.issued_by = current_user.id
            req.issue_date = datetime.utcnow()
            req.issue_reference = req.generate_issue_reference()

        # ✅ Reject request
        elif action == 'reject':
            if req.status != 'submitted':
                raise ValueError("Only submitted requests can be rejected")

            reason = data.get('reason', '').strip()
            if not reason:
                raise ValueError("Rejection reason is required")

            req.status = 'rejected'
            req.approval_notes = reason
            req.approver_id = current_user.id
            req.approval_date = datetime.utcnow()

        else:
            raise ValueError("Invalid action provided")

        # 🔐 Commit transaction
        db.session.commit()

        # 📦 Log activity (good for audit trails)
        current_app.logger.info(
            f"Stock request {req.id} {action} by user {current_user.id}"
        )

        return jsonify({'success': True, 'message': f'Request {action} successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Action failed: {str(e)}")
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
    
    # Fetch external orders (modify this query based on your actual model)
    external_orders = ExternalOrder.query.order_by(ExternalOrder.created_at.desc()).all()
    
    # Get currency from config (add to your config if needed)
    currency = current_app.config.get('CURRENCY', 'Ksh')
    
    return render_template('external_orders.html', 
                          external_orders=external_orders,
                          suppliers=suppliers,
                          currency=currency)



@store_web_bp.route('/external-orders', methods=['POST'])
def create_external_order():
    try:
        # Extract form data with validation
        item_name = request.form.get('item_name', '').strip()
        if not item_name:
            flash('Item name is required', 'error')
            return redirect(url_for('store_web_bp.external_orders'))
        
        try:
            quantity = int(request.form.get('quantity', 0))
            if quantity <= 0:
                flash('Quantity must be greater than zero', 'error')
                return redirect(url_for('store_web_bp.external_orders'))
        except (TypeError, ValueError):
            flash('Invalid quantity value', 'error')
            return redirect(url_for('store_web_bp.external_orders'))
        
        unit = request.form.get('unit', 'pcs')
        
        try:
            unit_price = float(request.form.get('unit_price', 0))
            if unit_price < 0:
                flash('Unit price cannot be negative', 'error')
                return redirect(url_for('store_web_bp.external_orders'))
        except (TypeError, ValueError):
            flash('Invalid unit price', 'error')
            return redirect(url_for('store_web_bp.external_orders'))
        
        try:
            tax_rate = float(request.form.get('tax_rate', 0))
            if tax_rate < 0 or tax_rate > 100:
                flash('Tax rate must be between 0 and 100', 'error')
                return redirect(url_for('store_web_bp.external_orders'))
        except (TypeError, ValueError):
            flash('Invalid tax rate', 'error')
            return redirect(url_for('store_web_bp.external_orders'))
        
        # Recalculate total server-side for security
        subtotal = quantity * unit_price
        tax_amount = subtotal * (tax_rate / 100)
        total_price = subtotal + tax_amount
        
        try:
            supplier_id_raw = request.form.get('supplier_id', '').strip()
            supplier_id = int(supplier_id_raw) if supplier_id_raw else None

            # Treat "0" as not selected
            if supplier_id == 0:
                supplier_id = None
        except (TypeError, ValueError):
            supplier_id = None

        
        contact_person = request.form.get('contact', '').strip()
        contact_info = request.form.get('contact_info', '').strip()
        
        priority = request.form.get('priority', 'medium')
        if priority not in ['low', 'medium', 'high', 'urgent']:
            priority = 'medium'
        

        
        category = request.form.get('category', '').strip()
        if not category:
            flash('Category is required', 'error')
            return redirect(url_for('store_web_bp.external_orders'))
        
        try:
            required_by = datetime.strptime(request.form.get('required_by'), '%Y-%m-%d')
        except (TypeError, ValueError):
            flash('Invalid required by date format', 'error')
            return redirect(url_for('store_web_bp.external_orders'))

        
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Reason is required', 'error')
            return redirect(url_for('store_web_bp.external_orders'))
        
        # Create new order
        new_order = ExternalOrder(
            item_name=item_name,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            tax_rate=tax_rate,
            total_price=total_price,
            supplier_id=supplier_id,
            contact_person=contact_person,
            contact_info=contact_info,
            priority=priority,
            category=category,
            required_by=required_by,
            reason=reason,
            user_id=current_user.id,  # Assuming you have current_user from Flask-Login
            status='pending'
        )
        
        db.session.add(new_order)
        db.session.commit()
        
        flash('Requisition created successfully!', 'success')
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
            order.unit_price = float(request.form['unit_price'])
            order.tax_rate = float(request.form.get('tax_rate', 0))
            
            # Recalculate total
            subtotal = order.quantity * order.unit_price
            tax_amount = subtotal * (order.tax_rate / 100)
            order.total_price = subtotal + tax_amount
            
            order.supplier_id = int(request.form['supplier_id'])
            order.contact_person = request.form.get('contact', '')
            order.contact_info = request.form.get('contact_info', '')
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



@store_web_bp.route('/purchase-orders/<int:id>/record-delivery', methods=['GET', 'POST'])
def record_delivery(id):
    order = PurchaseOrder.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Extract form data
            batch_number = request.form.get('batch_number')
            expiration_date = request.form.get('expiration_date')
            serial_numbers = request.form.get('serial_numbers')
            quantity_received = int(request.form.get('quantity_received'))
            condition = request.form.get('condition')
            storage_temp = request.form.get('storage_temp')
            location = request.form.get('location')
            certification = request.form.get('certification')
            inspector = request.form.get('inspector')
            notes = request.form.get('notes')
            
            # Handle file uploads
            attachment_paths = []
            for file in request.files.getlist('attachments'):
                if file.filename:
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    attachment_paths.append(file_path)
            
            # Get category from requisition if exists, otherwise default to supplier category
            category = order.supplier.category
            if order.requisition:
                category = order.requisition.category
            
            # Check if stock item already exists for this batch and PO
            existing_stock = Stock.query.filter_by(
                batch_number=batch_number,
                purchase_order_id=order.id,
                name=order.item_name
            ).first()
            
            if existing_stock:
                # Update existing stock
                existing_stock.quantity += quantity_received
                existing_stock.current_stock += quantity_received
                existing_stock.last_restocked = datetime.utcnow()
                
                # Update stock detail or create if doesn't exist
                existing_detail = StockDetail.query.filter_by(stock_id=existing_stock.id).first()
                if existing_detail:
                    existing_detail.condition = condition
                    existing_detail.storage_temp = storage_temp
                    existing_detail.certification = certification
                    existing_detail.inspector = inspector
                    existing_detail.delivery_notes = notes
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
                        certification=certification,
                        inspector=inspector,
                        delivery_notes=notes,
                        serial_numbers=serial_numbers,
                        attachments=",".join(attachment_paths) if attachment_paths else None
                    )
                    db.session.add(existing_detail)
                
                stock_item = existing_stock
                stock_detail = existing_detail
                
            else:
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
                    certification=certification,
                    inspector=inspector,
                    delivery_notes=notes,
                    serial_numbers=serial_numbers,
                    attachments=",".join(attachment_paths) if attachment_paths else None
                )
                
                db.session.add(stock_item)
                db.session.add(stock_detail)
            
            # 🔥 NEW: Create or Update Supplier Account
            supplier_account = SupplierAccount.query.filter_by(supplier_id=order.supplier.id).first()
            if not supplier_account:
                supplier_account = SupplierAccount(
                    supplier_id=order.supplier.id,
                    account_type='regular',
                    credit_limit=100000.00,
                    current_balance=0.0
                )
                db.session.add(supplier_account)
                db.session.flush()
                supplier_account.generate_account_number()

            # 🔥 NEW: Create Invoice
            invoice = SupplierInvoice(
                supplier_account_id=supplier_account.id,
                purchase_order_id=order.id,
                invoice_date=datetime.utcnow(),
                delivery_date=datetime.utcnow(),
                subtotal_amount=order.total_price,
                tax_amount= 0.0,  # Assuming tax is included in total_price
                total_amount=order.total_price,
                balance_due=order.total_price,
                payment_terms=order.supplier.payment_terms or 'Net 30',
                status='issued',
                items_delivered={
                    'item_name': order.item_name,
                    'quantity_delivered': quantity_received,
                    'unit_price': order.unit_price,
                    'total_amount': order.total_price,
                    'batch_number': batch_number,
                    'delivery_condition': condition
                }
            )

            # Generate invoice number using the safe method
            invoice.generate_invoice_number()
            invoice.calculate_due_date()

            db.session.add(invoice)
            db.session.flush()

            # Update to final invoice number if temporary was used
            if 'TEMP' in invoice.invoice_number:
                invoice.generate_invoice_number()

            # 🔥 NEW: Create Supplier Transaction
            transaction = SupplierTransaction(
                supplier_account_id=supplier_account.id,
                invoice_id=invoice.id,
                transaction_type='invoice',
                amount=invoice.total_amount,
                balance_after=supplier_account.current_balance + invoice.total_amount,
                description=f"Invoice for {order.item_name} - Qty: {quantity_received}",
                reference=invoice.invoice_number
            )
            
            # Update supplier account balance
            supplier_account.current_balance += invoice.total_amount
            supplier_account.total_orders += 1
            supplier_account.total_order_value += order.total_price
            supplier_account.last_order_date = datetime.utcnow()
            
            # Update order status
            order.status = 'delivered'
            order.delivery_date = datetime.utcnow()
            
            # Update supplier
            order.supplier.last_order_date = datetime.utcnow()
            
            # Update requisition status if exists
            if order.requisition:
                order.requisition.status = 'completed'
            
            # Save to database
            db.session.add(invoice)
            db.session.add(transaction)
            db.session.commit()
            
            flash('Delivery recorded, stock updated, and invoice created successfully!', 'success')
            return redirect(url_for('store_web_bp.purchase_orders'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error recording delivery: {str(e)}")
            flash(f'Error recording delivery: {str(e)}', 'danger')
    
    return render_template('record_delivery.html', order=order, datetime=datetime)