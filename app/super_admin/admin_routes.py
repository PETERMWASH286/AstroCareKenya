# app/super_admin/admin_routes.py

from datetime import datetime, timedelta
from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.hr.models import Payroll
from app.store.models import LPO, ExternalOrder, PaymentRequest, Requisition, SupplierTransaction
from app import db

# Define the blueprint
admin_web = Blueprint("admin_web_bp", __name__, template_folder="templates", static_folder="static")

# ------------------- Admin Dashboard -------------------
@admin_web.route("/dashboard")
@login_required
def admin_dashboard():
    """Admin dashboard overview with KPIs"""
    return render_template("admin/admin_dashboard.html")


# ------------------- Requisitions (Admin / Director) -------------------

@admin_web.route("/requisitions")
@login_required
def manage_requisitions():
    """
    Show requisitions that have been approved by Finance and are awaiting Director/Admin approval.
    Grouped by requisition number.
    """
    try:
        # Fetch requisitions with their orders, ordered by urgency
        requisitions = (
            Requisition.query
            .join(Requisition.external_orders)
            .filter(
                ExternalOrder.finance_approved.is_(True),
                ExternalOrder.director_approved.is_(False),
                ExternalOrder.status.notin_(["rejected", "cancelled"])
            )
            .options(
                db.joinedload(Requisition.external_orders)
                .joinedload(ExternalOrder.supplier),
                db.joinedload(Requisition.external_orders)
                .joinedload(ExternalOrder.user),
                db.joinedload(Requisition.user)
            )
            .order_by(Requisition.created_at.desc())
            .all()
        )
        
        # Calculate days until required for each order and attach to requisition
        now = datetime.utcnow()
        requisitions_with_info = []
        
        for requisition in requisitions:
            # Process each order in the requisition
            orders_with_info = []
            for order in requisition.external_orders:
                # Only include orders that meet our criteria
                if (order.finance_approved and 
                    not order.director_approved and 
                    order.status not in ["rejected", "cancelled"]):
                    
                    if order.required_by:
                        delta = order.required_by - now
                        days_until = delta.days
                        is_overdue = days_until < 0

                        if days_until < 0:
                            days_text = f"{abs(days_until)} days overdue"
                        elif days_until == 0:
                            days_text = "Today"
                        elif days_until == 1:
                            days_text = "Tomorrow"
                        else:
                            days_text = f"{days_until} days"
                    else:
                        days_until = None
                        is_overdue = False
                        days_text = "Not specified"

                    # Attach attributes to order
                    order.days_until = days_until
                    order.is_overdue = is_overdue
                    order.days_text = days_text
                    orders_with_info.append(order)
            
            # Only include requisitions that have pending orders
            if orders_with_info:
                requisition.pending_orders = orders_with_info
                requisitions_with_info.append(requisition)
        
        # Get currency from config
        currency = current_app.config.get('CURRENCY', 'Ksh')
        
        return render_template(
            "admin/manage_requisitions.html",
            requisitions=requisitions_with_info,
            currency=currency,
            now=now
        )
    
    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error fetching requisitions: {str(e)}")
        flash('An error occurred while fetching requisitions. Please try again.', 'error')
        return redirect(url_for('admin_web_bp.dashboard'))


# Approve by Director route
@admin_web.route("/requisitions/approve/<int:order_id>", methods=["POST", "GET"])
@login_required
def approve_requisition(order_id):
    """
    Director/Admin approves a requisition that was previously finance-approved.
    """

    order = ExternalOrder.query.get_or_404(order_id)

    # Must have been approved by finance first
    if not order.finance_approved:
        flash("This requisition has not yet been approved by Finance.", "warning")
        return redirect(url_for("admin_web.manage_requisitions"))

    if order.director_approved:
        flash("This requisition has already been approved by the Director.", "info")
        return redirect(url_for("admin_web_bp.manage_requisitions"))

    order.director_approved = True
    order.director_approved_by = current_user.id
    order.director_approved_at = datetime.utcnow()
    order.status = "director_approved"
    order.updated_at = datetime.utcnow()

    db.session.commit()
    current_app.logger.info(f"Requisition #{order.id} approved by director {current_user.username}")
    flash(f"Requisition #{order.id} approved successfully.", "success")
    return redirect(url_for("admin_web_bp.manage_requisitions"))
@admin_web.route("/requisitions/approve-all/<int:requisition_id>", methods=["POST"])
@login_required
def approve_requisition_all(requisition_id):
    """
    Approve all pending orders in a requisition at once.
    """
    try:
        requisition = Requisition.query.get_or_404(requisition_id)
        
        # Get all pending orders in this requisition
        pending_orders = [
            order for order in requisition.external_orders 
            if (order.finance_approved and 
                not order.director_approved and 
                order.status not in ["rejected", "cancelled"])
        ]
        
        if not pending_orders:
            flash("No pending orders found in this requisition.", "warning")
            return redirect(url_for("admin_web_bp.manage_requisitions"))
        
        # Approve all pending orders
        approved_count = 0
        for order in pending_orders:
            order.director_approved = True
            order.director_approved_by = current_user.id
            order.director_approved_at = datetime.utcnow()
            order.status = "director_approved"
            order.updated_at = datetime.utcnow()
            approved_count += 1
        
        db.session.commit()
        
        current_app.logger.info(f"Approved {approved_count} orders in requisition #{requisition.id} by director {current_user.username}")
        flash(f"Successfully approved {approved_count} items in requisition #{requisition.requisition_number}.", "success")
        
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error approving requisition: {str(e)}")
        flash('An error occurred while approving the requisition. Please try again.', 'error')
    
    return redirect(url_for("admin_web_bp.manage_requisitions"))

# Reject by Director route
@admin_web.route("/requisitions/reject/<int:order_id>", methods=['POST'])
@login_required
def reject_requisition(order_id):
    """Reject requisition with reason"""
    order = ExternalOrder.query.get_or_404(order_id)
    
    try:
        rejection_reason = request.json.get('reason', '').strip()
        if not rejection_reason:
            return jsonify({'error': 'Rejection reason is required'}), 400
        
        order.status = 'rejected'
        order.rejection_reason = rejection_reason
        order.rejected_by = current_user.id
        order.rejected_at = datetime.utcnow()

        order.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Requisition rejected successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error rejecting requisition: {str(e)}'}), 400





# View requisition details
@admin_web.route("/requisitions/view/<int:order_id>")
@login_required
def view_requisition(order_id):
    order = ExternalOrder.query.options(
        joinedload(ExternalOrder.supplier),
        joinedload(ExternalOrder.user)
    ).get_or_404(order_id)

    return render_template(
        "admin/requisition_detail.html",
        order=order,
        today=datetime.utcnow(),
        currency=current_app.config.get('CURRENCY', 'Ksh')
    )


@admin_web.route("/approve-lpo")
@login_required
def approve_lpo():
    """
    Admin/Director view for approving LPOs that have already been approved by Finance.
    """
    # Fetch only LPOs approved by Finance but not yet approved by Director
    pending_lpos = LPO.query.filter(
        LPO.finance_approved == True,
        LPO.director_approved == False,
        LPO.status != 'rejected'
    ).order_by(LPO.created_at.desc()).all()

    return render_template("admin/admin_approve_lpo.html", lpos=pending_lpos, admin_view=True)


# ---------------------- Admin / Director Routes ----------------------

@admin_web.route("/view-lpo/<int:lpo_id>")
@login_required
def view_lpo(lpo_id):
    """
    Admin view: Detailed info about a single LPO.
    """
    lpo = LPO.query.get_or_404(lpo_id)

    # Only allow viewing LPOs that have been approved by finance
    if not lpo.finance_approved:
        flash("This LPO has not been approved by Finance yet.", "warning")
        return redirect(url_for("admin_web.approve_lpo"))

    return render_template("admin/admin_view_lpo.html", lpo=lpo, admin_view=True)


@admin_web.route("/approve-lpo-action/<int:lpo_id>/<string:action>")
@login_required
def approve_lpo_action(lpo_id, action):
    """
    Admin/Director approves or rejects an LPO after Finance approval.
    action: 'approve' or 'reject'
    """
    lpo = LPO.query.get_or_404(lpo_id)

    # Only LPOs approved by Finance can be handled by Admin
    if not lpo.finance_approved:
        flash("Cannot approve/reject: LPO not yet approved by Finance.", "warning")
        return redirect(url_for("admin_web_bp.approve_lpo"))

    if lpo.director_approved:
        flash("This LPO has already been approved by Director.", "warning")
        return redirect(url_for("admin_web_bp.approve_lpo"))

    if action == "approve":
        lpo.director_approved = True
        lpo.director_approved_at = datetime.utcnow()
        lpo.director_approved_by = current_user.id
        lpo.status = "director_approved"  # Update overall status
        
        # Update the associated external order status to "completed"
        if lpo.external_order:
            lpo.external_order.status = "completed"
            lpo.external_order.updated_at = datetime.utcnow()
        
        flash(f"LPO {lpo.lpo_number or lpo.id} approved successfully and external order marked as completed.", "success")

    elif action == "reject":
        lpo.director_approved = False
        lpo.status = "rejected"
        
        # Update the associated external order status to "rejected"
        if lpo.external_order:
            lpo.external_order.status = "rejected"
            lpo.external_order.updated_at = datetime.utcnow()
            
        flash(f"LPO {lpo.lpo_number or lpo.id} rejected by Director.", "danger")

    else:
        flash("Invalid action.", "danger")
        return redirect(url_for("admin_web_bp.approve_lpo"))

    db.session.commit()
    return redirect(url_for("admin_web_bp.approve_lpo"))



# ------------------- Orders Progress -------------------
@admin_web.route("/orders-progress")
@login_required
def orders_progress():
    """Track the lifecycle of orders"""
    orders = []
    return render_template("super_admin/orders_progress.html", orders=orders)


# ------------------- Administrative Reports -------------------
@admin_web.route("/reports")
@login_required
def admin_reports():
    """Administrative reports (finance, HR, assets, etc.)"""
    reports = []
    return render_template("super_admin/admin_reports.html", reports=reports)



# ------------------- System Settings -------------------
@admin_web.route("/settings")
@login_required
def system_settings():
    """System configuration (branding, policies, integrations, etc.)"""
    return render_template("super_admin/system_settings.html")


@admin_web.route('/approve-payments')
@login_required
def approve_payments():
    """Director payment approval dashboard"""
    if not current_user.has_privilege('admin:approve_payments'):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('admin_web_bp.admin_dashboard'))
    
    # Get payment requests pending director approval
    pending_requests = PaymentRequest.query.filter_by(
        status='director_approval'
    ).order_by(PaymentRequest.finance_reviewed_at.desc()).all()
    
    # Get comprehensive statistics for director view
    stats = {
        'pending_director': PaymentRequest.query.filter_by(status='director_approval').count(),
        'approved_today': PaymentRequest.query.filter(
            PaymentRequest.status == 'approved',
            PaymentRequest.director_approved_at >= datetime.utcnow().date()
        ).count(),
        'total_approved_month': PaymentRequest.query.filter(
            PaymentRequest.status == 'approved',
            PaymentRequest.director_approved_at >= datetime.utcnow().replace(day=1)
        ).count(),
        'total_amount_pending': db.session.query(db.func.sum(PaymentRequest.amount)).filter(
            PaymentRequest.status == 'director_approval'
        ).scalar() or 0,
        'high_value_requests': PaymentRequest.query.filter(
            PaymentRequest.status == 'director_approval',
            PaymentRequest.amount >= 50000  # High value threshold
        ).count()
    }
    
    # Get recent payment history for context
    recent_approved = PaymentRequest.query.filter_by(status='approved').order_by(
        PaymentRequest.director_approved_at.desc()
    ).limit(10).all()
    
    return render_template('admin/approve_payments.html',
                         pending_requests=pending_requests,
                         recent_approved=recent_approved,
                         stats=stats)
    


@admin_web.route('/payment-requests/<int:request_id>/director-review', methods=['POST'])
@login_required
def director_approve_payment(request_id):
    """Director gives final approval for payment and records payment in supplier invoice"""
    if not current_user.has_privilege('admin:approve_payments'):
        return jsonify({
            'success': False,
            'message': 'Unauthorized: Director approval permission required'
        }), 403
    
    try:
        payment_request = PaymentRequest.query.get_or_404(request_id)
        
        # Validate that request is in correct status for director approval
        if payment_request.status != 'director_approval':
            return jsonify({
                'success': False,
                'message': f'Payment request must be in director approval status. Current status: {payment_request.status}'
            }), 400
        
        data = request.get_json()
        action = data.get('action')  # 'approve' or 'reject'
        notes = data.get('notes', '')
        
        if action == 'approve':
            # Director gives final approval and records payment
            success, message = payment_request.execute_payment_after_approval(current_user.id, notes)
            
            if not success:
                return jsonify({
                    'success': False,
                    'message': message
                }), 400
                
            message = 'Payment request approved and payment recorded in supplier invoice'
            
            
            
        elif action == 'reject':
            # Director rejects the payment request
            payment_request.reject(current_user.id, notes, rejected_by_finance=False)
            message = 'Payment request rejected by director'
            
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid action. Must be "approve" or "reject"'
            }), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': message,
            'payment_request': payment_request.to_dict(),
            'invoice_status': payment_request.invoice.status if action == 'approve' else None,
            'invoice_balance': payment_request.invoice.balance_due if action == 'approve' else None
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in director approval: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error processing director approval: {str(e)}'
        }), 500
        
        
        
@admin_web.route('/payment-requests/<int:request_id>/director-details')
@login_required
def director_payment_details(request_id):
    """Get comprehensive details for director decision"""
    if not current_user.has_privilege('admin:approve_payments'):
        return jsonify({
            'success': False,
            'message': 'Unauthorized'
        }), 403
    
    payment_request = PaymentRequest.query.get_or_404(request_id)
    
    # Get comprehensive details for director decision
    invoice = payment_request.invoice
    supplier_account = invoice.supplier_account
    supplier = supplier_account.supplier
    
    # Get supplier performance metrics
    supplier_performance = supplier_account.get_account_summary()
    
    # Get payment history with this supplier
    recent_payments = SupplierTransaction.query.filter_by(
        supplier_account_id=supplier_account.id
    ).order_by(SupplierTransaction.transaction_date.desc()).limit(5).all()
    
    
    details = {
        'payment_request': payment_request.to_dict(),
        'invoice': invoice.to_dict(),
        'supplier': {
            'name': supplier.name,
            'contact': supplier.contact,
            'phone': supplier.phone,
            'email': supplier.email,
            'rating': supplier.rating,
            'category': supplier.category,
            'payment_terms': supplier.payment_terms
        },
        'supplier_account': {
            'account_number': supplier_account.account_number,
            'current_balance': supplier_account.current_balance,
            'credit_limit': supplier_account.credit_limit,
            'credit_rating': supplier_account.credit_rating,
            'total_orders': supplier_account.total_orders,
            'total_order_value': supplier_account.total_order_value,
            'on_time_delivery_rate': supplier_account.on_time_delivery_rate,
            'average_delivery_time': supplier_account.average_delivery_time
        },
        'supplier_performance': supplier_performance,
        'recent_payments': [{
            'date': payment.transaction_date.isoformat(),
            'amount': payment.amount,
            'type': payment.transaction_type,
            'description': payment.description
        } for payment in recent_payments],
        'finance_reviewer': {
            'name': payment_request.finance_reviewer.username if payment_request.finance_reviewer else 'N/A',
            'reviewed_at': payment_request.finance_reviewed_at.isoformat() if payment_request.finance_reviewed_at else 'N/A',
            'notes': payment_request.finance_notes
        }
    }
    
    return jsonify(details)







@admin_web.route('/payment-requests/bulk-approve', methods=['POST'])
@login_required
def bulk_approve_payments():
    """Bulk approve multiple payment requests (for efficient processing)"""
    if not current_user.has_privilege('admin:approve_payments'):
        return jsonify({
            'success': False,
            'message': 'Unauthorized: Director approval permission required'
        }), 403
    
    try:
        data = request.get_json()
        request_ids = data.get('request_ids', [])
        notes = data.get('notes', 'Bulk approval')
        
        if not request_ids:
            return jsonify({
                'success': False,
                'message': 'No payment requests selected'
            }), 400
        
        approved_count = 0
        errors = []
        
        for request_id in request_ids:
            try:
                payment_request = PaymentRequest.query.get(request_id)
                
                
                if payment_request and payment_request.status == 'director_approval':
                    payment_request.approve_by_director(current_user.id, notes)
                    approved_count += 1
                else:
                    errors.append(f"Request {request_id}: Invalid status or not found")
                    
            except Exception as e:
                errors.append(f"Request {request_id}: {str(e)}")
        
        
        db.session.commit()
        
        
        

        return jsonify({
            'success': True,
            'message': f'Successfully approved {approved_count} payment requests',
            'approved_count': approved_count,
            'errors': errors
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error in bulk approval: {str(e)}'
        }), 500

@admin_web.route('/admin/payment-analytics')
@login_required
def payment_analytics():
    """Get analytics data for payment approvals"""
    if not current_user.has_privilege('admin:approve_payments'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    # Get analytics data for the last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    analytics = {
        'approval_timeline': get_approval_timeline_data(thirty_days_ago),
        'supplier_breakdown': get_supplier_payment_breakdown(thirty_days_ago),
        'amount_ranges': get_payment_amount_ranges(thirty_days_ago),
        'approval_rates': get_approval_rates(thirty_days_ago)
    }
    
    return jsonify(analytics)

# Helper functions for analytics
def get_approval_timeline_data(since_date):
    """Get approval timeline data for charts"""
    # Implementation for timeline data
    pass

def get_supplier_payment_breakdown(since_date):
    """Get supplier-wise payment breakdown"""
    # Implementation for supplier breakdown
    pass

def get_payment_amount_ranges(since_date):
    """Get payment amount range distribution"""
    # Implementation for amount ranges
    pass

def get_approval_rates(since_date):
    """Get approval/rejection rates"""
    # Implementation for approval rates
    pass



@admin_web.route('/approve-payrolls')
@login_required
def approve_payrolls():
    """Show processed payrolls for approval."""
    processed_payrolls = Payroll.query.filter_by(status='Processed')\
        .order_by(Payroll.processed_at.desc()).all()
    return render_template('admin/approve_payrolls.html', payrolls=processed_payrolls)

@admin_web.route('/approve-payroll/<int:payroll_id>', methods=['POST'])
@login_required
def approve_payroll(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    if payroll.status != 'Processed':
        flash('Only processed payrolls can be approved.', 'danger')
        return redirect(url_for('admin_web_bp.approve_payrolls'))

    # Update payroll status and approver info
    payroll.status = 'Approved'
    payroll.approved_by = current_user.id
    payroll.approved_at = datetime.utcnow()



    # Update all associated payslips to 'Approved'
    for payslip in payroll.payslips:
        payslip.status = 'Approved'

    db.session.commit()

    flash(f'Payroll #{payroll.id} approved successfully.', 'success')
    return redirect(url_for('admin_web_bp.approve_payrolls'))

