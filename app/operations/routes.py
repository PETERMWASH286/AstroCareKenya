# app/operations/routes.py
import calendar
from collections import defaultdict
from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, current_app, request, url_for
from flask_login import login_required, current_user
from app.auth.models import User
from app.finance.models import PettyCash, PettyCashTransaction
from app.operations import operations_web_bp
from app.extensions import db
from app.operations.models import FarmCrop, FarmExpense, FarmHarvest, FarmHealthRecord, FarmInventory, FarmLivestock, FarmRevenue, FleetFuel, FleetInventory, FleetMaintenance, FleetTrip, FleetVehicle, ItemAssignment, ItemTag, KitchenBudget, KitchenDailyPlan, KitchenInventory, KitchenMenu, KitchenMenuItem, KitchenUsageLog, OperationsSupplier, OperationsSupplierAccount, OperationsSupplierPayment, PettyCashRequest, ProcurementOrder, ProcurementReceiving, ProcurementRequest, ProcurementSupplierInvoice, StoreMaintenance

# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------

@operations_web_bp.route('/dashboard')
@login_required
def dashboard():
    # --- Summary counts ---
    pending_proc_requests = ProcurementRequest.query.filter_by(status='pending').count()
    pending_petty_requests = PettyCashRequest.query.filter_by(status='pending').count()
    total_petty_balance = db.session.query(func.sum(PettyCash.current_balance)).filter_by(is_active=True).scalar() or 0

    # Low stock across modules
    low_stock_kitchen = KitchenInventory.query.filter(KitchenInventory.quantity <= KitchenInventory.reorder_level).count()
    low_stock_store = StoreInventory.query.filter(StoreInventory.quantity <= StoreInventory.reorder_level).count()
    low_stock_farm = FarmInventory.query.filter(FarmInventory.quantity <= FarmInventory.reorder_level).count()
    low_stock_fleet = FleetInventory.query.filter(FleetInventory.quantity <= FleetInventory.reorder_level).count()
    total_low_stock = low_stock_kitchen + low_stock_store + low_stock_farm + low_stock_fleet

    # Recent revenue/expenses (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_revenue = db.session.query(func.sum(FarmRevenue.total_amount)).filter(FarmRevenue.date >= thirty_days_ago).scalar() or 0
    recent_expenses = db.session.query(func.sum(FarmExpense.amount)).filter(FarmExpense.date >= thirty_days_ago).scalar() or 0

    # Monthly revenue/expense for chart (last 6 months)
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    revenues = FarmRevenue.query.filter(FarmRevenue.date >= six_months_ago).all()
    expenses = FarmExpense.query.filter(FarmExpense.date >= six_months_ago).all()

    rev_by_month = defaultdict(float)
    for r in revenues:
        key = r.date.strftime('%Y-%m')
        rev_by_month[key] += r.total_amount
    exp_by_month = defaultdict(float)
    for e in expenses:
        key = e.date.strftime('%Y-%m')
        exp_by_month[key] += e.amount

    labels = []
    monthly_revenue = []
    monthly_expense = []
    for i in range(5, -1, -1):
        d = datetime.utcnow().replace(day=1) - timedelta(days=i*30)
        labels.append(d.strftime('%b %Y'))
        key = d.strftime('%Y-%m')
        monthly_revenue.append(rev_by_month.get(key, 0))
        monthly_expense.append(exp_by_month.get(key, 0))

    # Recent records (limit 5)
    recent_proc_requests = ProcurementRequest.query.order_by(ProcurementRequest.created_at.desc()).limit(5).all()
    recent_petty_txs = PettyCashTransaction.query.order_by(PettyCashTransaction.completed_at.desc()).limit(5).all()
    recent_harvests = FarmHarvest.query.order_by(FarmHarvest.harvest_date.desc()).limit(5).all()
    recent_maintenance = FleetMaintenance.query.order_by(FleetMaintenance.maintenance_date.desc()).limit(5).all()

    # Low stock items (top 3 from each department)
    low_stock_items = []
    for item in KitchenInventory.query.filter(KitchenInventory.quantity <= KitchenInventory.reorder_level).order_by(KitchenInventory.quantity).limit(3):
        low_stock_items.append({'name': item.name, 'department': 'Kitchen', 'quantity': item.quantity, 'reorder': item.reorder_level})
    for item in StoreInventory.query.filter(StoreInventory.quantity <= StoreInventory.reorder_level).order_by(StoreInventory.quantity).limit(3):
        low_stock_items.append({'name': item.name, 'department': 'Store', 'quantity': item.quantity, 'reorder': item.reorder_level})
    for item in FarmInventory.query.filter(FarmInventory.quantity <= FarmInventory.reorder_level).order_by(FarmInventory.quantity).limit(3):
        low_stock_items.append({'name': item.name, 'department': 'Farm', 'quantity': item.quantity, 'reorder': item.reorder_level})
    for item in FleetInventory.query.filter(FleetInventory.quantity <= FleetInventory.reorder_level).order_by(FleetInventory.quantity).limit(3):
        low_stock_items.append({'name': item.name, 'department': 'Fleet', 'quantity': item.quantity, 'reorder': item.reorder_level})
    low_stock_items.sort(key=lambda x: x['quantity'])

    return render_template(
        'operations/dashboard.html',
        pending_proc_requests=pending_proc_requests,
        pending_petty_requests=pending_petty_requests,
        total_petty_balance=total_petty_balance,
        total_low_stock=total_low_stock,
        recent_revenue=recent_revenue,
        recent_expenses=recent_expenses,
        profit=recent_revenue - recent_expenses,
        monthly_labels=labels,
        monthly_revenue=monthly_revenue,
        monthly_expense=monthly_expense,
        recent_proc_requests=recent_proc_requests,
        recent_petty_txs=recent_petty_txs,
        recent_harvests=recent_harvests,
        recent_maintenance=recent_maintenance,
        low_stock_items=low_stock_items
    )


# ----------------------------------------------------------------------
# Kitchen Management
# ----------------------------------------------------------------------
@operations_web_bp.route('/kitchen/inventory', methods=['GET', 'POST'])
@login_required
def kitchen_inventory():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form.get('name')
            quantity = float(request.form.get('quantity', 0))
            unit = request.form.get('unit', 'pcs')
            reorder_level = float(request.form.get('reorder_level', 10))
            location = request.form.get('location')
            notes = request.form.get('notes')
            
            if not name:
                flash('Item name is required.', 'danger')
                return redirect(url_for('operations_web_bp.kitchen_inventory'))
            
            existing = KitchenInventory.query.filter_by(name=name).first()
            if existing:
                flash(f'Item "{name}" already exists.', 'danger')
                return redirect(url_for('operations_web_bp.kitchen_inventory'))
            
            item = KitchenInventory(
                name=name,
                quantity=quantity,
                unit=unit,
                reorder_level=reorder_level,
                location=location,
                notes=notes
            )
            db.session.add(item)
            db.session.commit()
            flash(f'Item "{name}" added.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_inventory'))
        
        elif action == 'record_usage':
            item_id = request.form.get('item_id')
            quantity = float(request.form.get('quantity', 0))
            notes = request.form.get('notes', '')
            item = KitchenInventory.query.get_or_404(item_id)
            
            if quantity <= 0:
                flash('Usage quantity must be positive.', 'danger')
                return redirect(url_for('operations_web_bp.kitchen_inventory'))
            
            if item.quantity < quantity:
                flash(f'Insufficient stock. Available: {item.quantity:.2f} {item.unit}', 'danger')
                return redirect(url_for('operations_web_bp.kitchen_inventory'))
            
            # Deduct quantity
            item.quantity -= quantity
            
            # Create usage log
            usage = KitchenUsageLog(
                item_id=item.id,
                quantity=quantity,
                notes=notes,
                recorded_by=current_user.id
            )
            db.session.add(usage)
            db.session.commit()
            
            flash(f'Recorded usage of {quantity:.2f} {item.unit} for {item.name}.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_inventory'))
        
        elif action == 'adjust_stock':
            item_id = request.form.get('item_id')
            adjustment = float(request.form.get('adjustment', 0))
            notes = request.form.get('notes', '')
            item = KitchenInventory.query.get_or_404(item_id)
            item.quantity += adjustment
            if item.quantity < 0:
                item.quantity = 0
            db.session.commit()
            flash(f'Stock for "{item.name}" adjusted by {adjustment:+.2f}. New quantity: {item.quantity:.2f}.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_inventory'))
        
        elif action == 'delete':
            item_id = request.form.get('item_id')
            item = KitchenInventory.query.get_or_404(item_id)
            db.session.delete(item)
            db.session.commit()
            flash(f'Item "{item.name}" deleted.', 'info')
            return redirect(url_for('operations_web_bp.kitchen_inventory'))

    # GET
    items = KitchenInventory.query.order_by(KitchenInventory.name).all()
    total_items = len(items)
    total_quantity = sum(i.quantity for i in items)
    low_stock = [i for i in items if i.quantity <= i.reorder_level]
    
    recent_usage = KitchenUsageLog.query.order_by(KitchenUsageLog.date_used.desc()).limit(30).all()
    
    return render_template(
        'operations/kitchen/inventory.html',
        items=items,
        total_items=total_items,
        total_quantity=total_quantity,
        low_stock_count=len(low_stock),
        low_stock_items=low_stock,
        recent_usage=recent_usage
    )


from flask import render_template, redirect, url_for, flash, request as flask_request
from flask_login import login_required, current_user


@operations_web_bp.route('/kitchen/budgeting', methods=['GET', 'POST'])
@login_required
def kitchen_budgeting():
    if flask_request.method == 'POST':
        action = flask_request.form.get('action')
        if action == 'add':
            month = int(flask_request.form.get('month'))
            year = int(flask_request.form.get('year'))
            category = flask_request.form.get('category')
            allocated = float(flask_request.form.get('allocated_amount', 0))
            notes = flask_request.form.get('notes')
            budget = KitchenBudget.query.filter_by(month=month, year=year, category=category).first()
            if budget:
                flash('Budget for this category and month already exists. Edit instead.', 'danger')
                return redirect(url_for('operations_web_bp.kitchen_budgeting'))
            budget = KitchenBudget(
                month=month, year=year, category=category,
                allocated_amount=allocated, notes=notes
            )
            db.session.add(budget)
            db.session.commit()
            flash('Budget added.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_budgeting'))
        elif action == 'edit':
            budget_id = flask_request.form.get('budget_id')
            budget = KitchenBudget.query.get_or_404(budget_id)
            budget.allocated_amount = float(flask_request.form.get('allocated_amount'))
            budget.notes = flask_request.form.get('notes')
            db.session.commit()
            flash('Budget updated.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_budgeting'))

    # GET
    year = flask_request.args.get('year', type=int, default=datetime.utcnow().year)
    month = flask_request.args.get('month', type=int, default=datetime.utcnow().month)
    budgets = KitchenBudget.query.filter_by(year=year, month=month).all()
    categories = ['Vegetables', 'Fruits', 'Meat', 'Fish', 'Dairy', 'Dry Goods', 'Spices', 'Beverages', 'Cleaning Supplies', 'Small Equipment', 'Other']

    # Actual spending for the period – based on received goods
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year+1, 1, 1)
    else:
        end_date = datetime(year, month+1, 1)

    # Query receipts of kitchen items within the period
    receipts = ProcurementReceiving.query.join(
        ProcurementOrder, ProcurementReceiving.order_id == ProcurementOrder.id
    ).join(
        ProcurementRequest, ProcurementOrder.request_id == ProcurementRequest.id
    ).filter(
        ProcurementRequest.department == 'kitchen',
        ProcurementReceiving.received_date >= start_date,
        ProcurementReceiving.received_date < end_date
    ).all()

    # Calculate spending per category
    spending = {}
    for rec in receipts:
        order = rec.order
        req = order.request
        category = req.category
        if not category:
            continue
        cost = rec.quantity_received * order.unit_price
        spending[category] = spending.get(category, 0) + cost

    # Build budget vs actual list
    budget_data = []
    for budget in budgets:
        actual = spending.get(budget.category, 0)
        variance = budget.allocated_amount - actual
        variance_pct = (variance / budget.allocated_amount * 100) if budget.allocated_amount else 0
        budget_data.append({
            'id': budget.id,
            'category': budget.category,
            'allocated': budget.allocated_amount,
            'actual': actual,
            'variance': variance,
            'variance_pct': variance_pct,
            'notes': budget.notes or ''
        })

    # Add categories with spending but no budget
    for cat, amount in spending.items():
        if not any(b['category'] == cat for b in budget_data):
            budget_data.append({
                'id': None,
                'category': cat,
                'allocated': 0,
                'actual': amount,
                'variance': -amount,
                'variance_pct': -100,
                'notes': 'No budget set'
            })

    # Sort by variance (most overspent first)
    budget_data.sort(key=lambda x: x['variance'])

    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    return render_template(
        'operations/kitchen/budgeting.html',
        budget_data=budget_data,
        year=year,
        month=month,
        categories=categories,
        month_names=month_names
    )


@operations_web_bp.route('/kitchen/reports')
@login_required
def kitchen_reports():
    from sqlalchemy import func, extract
    from datetime import datetime, timedelta

    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    # Get filter parameters
    period = request.args.get('period', 'month')  # month, year, custom
    month = int(request.args.get('month', datetime.utcnow().month))
    year = int(request.args.get('year', datetime.utcnow().year))
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Determine date range
    if period == 'custom' and start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    elif period == 'year':
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    else:  # month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month+1, 1) - timedelta(seconds=1)

    # ===== 1. Inventory Summary =====
    total_items = KitchenInventory.query.count()
    total_quantity = db.session.query(func.sum(KitchenInventory.quantity)).scalar() or 0
    low_stock_items = KitchenInventory.query.filter(KitchenInventory.quantity <= KitchenInventory.reorder_level).all()
    low_stock_count = len(low_stock_items)

    # ===== 2. Usage Summary (from usage logs) =====
    usage_logs = KitchenUsageLog.query.filter(
        KitchenUsageLog.date_used >= start_date,
        KitchenUsageLog.date_used <= end_date
    ).all()
    total_usage = sum(l.quantity for l in usage_logs) if usage_logs else 0

    # Top consumed items
    top_consumed = db.session.query(
        KitchenInventory.name,
        func.sum(KitchenUsageLog.quantity).label('total_used'),
        KitchenInventory.unit
    ).join(KitchenUsageLog.item).filter(
        KitchenUsageLog.date_used >= start_date,
        KitchenUsageLog.date_used <= end_date
    ).group_by(KitchenInventory.id).order_by(func.sum(KitchenUsageLog.quantity).desc()).limit(10).all()

    # ===== 3. Cost Analysis (from procurement receipts) =====
    receipts = ProcurementReceiving.query.join(
        ProcurementOrder, ProcurementReceiving.order_id == ProcurementOrder.id
    ).join(
        ProcurementRequest, ProcurementOrder.request_id == ProcurementRequest.id
    ).filter(
        ProcurementRequest.department == 'kitchen',
        ProcurementReceiving.received_date >= start_date,
        ProcurementReceiving.received_date <= end_date
    ).all()

    total_cost = 0
    cost_by_category = {}
    for rec in receipts:
        order = rec.order
        req = order.request
        category = req.category or 'Uncategorized'
        cost = rec.quantity_received * order.unit_price
        total_cost += cost
        cost_by_category[category] = cost_by_category.get(category, 0) + cost

    # ===== 4. Budget vs Actual =====
    budgets = KitchenBudget.query.filter(
        KitchenBudget.year == year,
        KitchenBudget.month == month
    ).all()
    budget_vs_actual = []
    for b in budgets:
        actual = cost_by_category.get(b.category, 0)
        variance = b.allocated_amount - actual
        variance_pct = (variance / b.allocated_amount * 100) if b.allocated_amount else 0
        budget_vs_actual.append({
            'category': b.category,
            'budget': b.allocated_amount,
            'actual': actual,
            'variance': variance,
            'variance_pct': variance_pct
        })
    # Add categories with actual but no budget
    for cat, amount in cost_by_category.items():
        if not any(b['category'] == cat for b in budget_vs_actual):
            budget_vs_actual.append({
                'category': cat,
                'budget': 0,
                'actual': amount,
                'variance': -amount,
                'variance_pct': -100
            })

    # ===== 5. Monthly Usage Trend (last 12 months) =====
    months = []
    usage_trend = []
    for i in range(11, -1, -1):
        d = start_date.replace(day=1) - timedelta(days=30*i)
        month_start = d.replace(day=1)
        if month_start.month == 12:
            month_end = datetime(month_start.year+1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(month_start.year, month_start.month+1, 1) - timedelta(seconds=1)
        usage = db.session.query(func.sum(KitchenUsageLog.quantity)).filter(
            KitchenUsageLog.date_used >= month_start,
            KitchenUsageLog.date_used <= month_end
        ).scalar() or 0
        months.append(month_start.strftime('%b %Y'))
        usage_trend.append(usage)

    return render_template(
        'operations/kitchen/reports.html',
        # Inventory
        total_items=total_items,
        total_quantity=total_quantity,
        low_stock_count=low_stock_count,
        low_stock_items=low_stock_items,
        # Usage
        total_usage=total_usage,
        top_consumed=top_consumed,
        # Cost
        total_cost=total_cost,
        cost_by_category=cost_by_category,
        # Budget
        budget_vs_actual=budget_vs_actual,
        # Trend
        months=months,
        usage_trend=usage_trend,
        # Filters
        period=period,
        year=year,
        month=month,
        start_date=start_date.strftime('%Y-%m-%d') if start_date else '',
        end_date=end_date.strftime('%Y-%m-%d') if end_date else '',
        month_names=month_names  # <-- added
    )

def get_week_dates(week_offset=0):
    """Return a list of (date, weekday_name) for the week starting on Monday."""
    today = datetime.utcnow().date()
    start = today - timedelta(days=today.weekday())  # Monday
    start += timedelta(days=7 * week_offset)
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        days.append((d, d.strftime('%A')))  # Monday, Tuesday, ...
    return days

@operations_web_bp.route('/kitchen/menu', methods=['GET', 'POST'])
@login_required
def kitchen_menu():
    if request.method == 'POST':
        action = request.form.get('action')

        # Add menu
        if action == 'add_menu':
            name = request.form.get('name')
            description = request.form.get('description')
            preparation_time = request.form.get('preparation_time')
            servings = request.form.get('servings', 1)
            image_url = request.form.get('image_url')

            if not name:
                flash('Menu name is required.', 'danger')
                return redirect(url_for('operations_web_bp.kitchen_menu'))

            menu = KitchenMenu(
                name=name,
                description=description,
                preparation_time=int(preparation_time) if preparation_time else None,
                servings=int(servings),
                image_url=image_url
            )
            db.session.add(menu)
            db.session.flush()

            # Add menu items
            item_ids = request.form.getlist('item_id[]')
            quantities = request.form.getlist('quantity[]')
            notes_list = request.form.getlist('item_notes[]')

            for i, inv_id in enumerate(item_ids):
                if inv_id and i < len(quantities):
                    qty = float(quantities[i])
                    if qty > 0:
                        menu_item = KitchenMenuItem(
                            menu_id=menu.id,
                            inventory_id=int(inv_id),
                            quantity=qty,
                            notes=notes_list[i] if i < len(notes_list) else ''
                        )
                        db.session.add(menu_item)

            db.session.commit()
            flash(f'Menu "{name}" created successfully.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_menu'))

        # Edit menu
        elif action == 'edit_menu':
            menu_id = request.form.get('menu_id')
            menu = KitchenMenu.query.get_or_404(menu_id)
            menu.name = request.form.get('name')
            menu.description = request.form.get('description')
            menu.preparation_time = int(request.form.get('preparation_time')) if request.form.get('preparation_time') else None
            menu.servings = int(request.form.get('servings', 1))
            menu.image_url = request.form.get('image_url')

            # Replace menu items
            KitchenMenuItem.query.filter_by(menu_id=menu.id).delete()

            item_ids = request.form.getlist('item_id[]')
            quantities = request.form.getlist('quantity[]')
            notes_list = request.form.getlist('item_notes[]')

            for i, inv_id in enumerate(item_ids):
                if inv_id and i < len(quantities):
                    qty = float(quantities[i])
                    if qty > 0:
                        menu_item = KitchenMenuItem(
                            menu_id=menu.id,
                            inventory_id=int(inv_id),
                            quantity=qty,
                            notes=notes_list[i] if i < len(notes_list) else ''
                        )
                        db.session.add(menu_item)

            db.session.commit()
            flash(f'Menu "{menu.name}" updated.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_menu'))

        # Delete menu
        elif action == 'delete_menu':
            menu_id = request.form.get('menu_id')
            menu = KitchenMenu.query.get_or_404(menu_id)
            name = menu.name
            db.session.delete(menu)
            db.session.commit()
            flash(f'Menu "{name}" deleted.', 'info')
            return redirect(url_for('operations_web_bp.kitchen_menu'))

        # ---------- Save Meal Plan ----------
        elif action == 'save_plan':
            plan_id = request.form.get('plan_id')
            date_str = request.form.get('date')
            meal_type = request.form.get('meal_type')
            menu_id = request.form.get('menu_id')
            servings = request.form.get('servings', 1)
            manual_ingredients_json = request.form.get('manual_ingredients', '[]')
            estimated_cost = request.form.get('estimated_cost')
            notes = request.form.get('notes')

            if not date_str or not meal_type:
                flash('Date and meal type are required.', 'danger')
                return redirect(url_for('operations_web_bp.kitchen_menu'))

            # Parse date
            date = datetime.strptime(date_str, '%Y-%m-%d').date()

            if plan_id:  # update existing
                plan = KitchenDailyPlan.query.get_or_404(plan_id)
            else:        # create new
                plan = KitchenDailyPlan(date=date, meal_type=meal_type)
                db.session.add(plan)

            plan.menu_id = int(menu_id) if menu_id else None
            plan.servings = int(servings)
            plan.manual_ingredients = manual_ingredients_json
            plan.estimated_cost = float(estimated_cost) if estimated_cost else None
            plan.notes = notes
            db.session.commit()
            flash('Meal plan saved.', 'success')
            return redirect(url_for('operations_web_bp.kitchen_menu'))

        elif action == 'delete_plan':
            plan_id = request.form.get('plan_id')
            plan = KitchenDailyPlan.query.get_or_404(plan_id)
            db.session.delete(plan)
            db.session.commit()
            flash('Meal plan removed.', 'info')
            return redirect(url_for('operations_web_bp.kitchen_menu'))

    # ---------- GET ----------
    # Retrieve all menus for the recipe library
    menus = KitchenMenu.query.order_by(KitchenMenu.name).all()
    inventory_items = KitchenInventory.query.order_by(KitchenInventory.name).all()

    # Determine week offset from query parameter
    week_offset = int(request.args.get('week_offset', 0))
    week_days = get_week_dates(week_offset)

    # Build a dictionary of plans for quick access: key = (date, meal_type)
    plans_dict = {}
    all_plans = KitchenDailyPlan.query.all()
    for p in all_plans:
        key = (p.date, p.meal_type)
        plans_dict[key] = p

    # Prepare plan data for the template
    plan_data = []
    for date, weekday in week_days:
        row = {
            'date': date,
            'weekday': weekday,
            'breakfast': plans_dict.get((date, 'breakfast')),
            'lunch': plans_dict.get((date, 'lunch')),
            'dinner': plans_dict.get((date, 'dinner'))
        }
        plan_data.append(row)

    return render_template(
        'operations/kitchen/menu.html',
        menus=menus,
        inventory_items=inventory_items,
        plan_data=plan_data,
        week_offset=week_offset,
        prev_week=week_offset - 1,
        next_week=week_offset + 1
    )

@operations_web_bp.route('/kitchen/menu/items/<int:menu_id>')
@login_required
def get_menu_items(menu_id):
    menu = KitchenMenu.query.get_or_404(menu_id)
    items = []
    for mi in menu.items:
        items.append({
            'inventory_id': mi.inventory_id,
            'quantity': mi.quantity,
            'notes': mi.notes or ''
        })
    return {'items': items}

# ----------------------------------------------------------------------
# Store Management
# ----------------------------------------------------------------------
from app.operations.models import StoreInventory

@operations_web_bp.route('/store/inventory', methods=['GET', 'POST'])
@login_required
def store_inventory():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name')
            quantity = float(request.form.get('quantity', 0))
            unit = request.form.get('unit', 'pcs')
            reorder_level = float(request.form.get('reorder_level', 10))
            category = request.form.get('category')
            location = request.form.get('location')
            notes = request.form.get('notes')
            is_tracked = 'is_tracked' in request.form   # <-- define here

            if not name:
                flash('Item name is required.', 'danger')
                return redirect(url_for('operations_web_bp.store_inventory'))

            existing = StoreInventory.query.filter_by(name=name).first()
            if existing:
                flash(f'Item "{name}" already exists.', 'danger')
                return redirect(url_for('operations_web_bp.store_inventory'))

            item = StoreInventory(
                name=name,
                quantity=quantity,
                unit=unit,
                reorder_level=reorder_level,
                category=category,
                location=location,
                notes=notes,
                is_tracked=is_tracked
            )
            db.session.add(item)
            db.session.commit()
            flash('Item added.', 'success')
            return redirect(url_for('operations_web_bp.store_inventory'))

        elif action == 'edit':
            item_id = request.form.get('item_id')
            item = StoreInventory.query.get_or_404(item_id)
            item.name = request.form.get('name')
            item.quantity = float(request.form.get('quantity', 0))
            item.unit = request.form.get('unit', 'pcs')
            item.reorder_level = float(request.form.get('reorder_level', 10))
            item.category = request.form.get('category')
            item.location = request.form.get('location')
            item.notes = request.form.get('notes')
            item.is_tracked = 'is_tracked' in request.form   # <-- define here
            db.session.commit()
            flash('Item updated.', 'success')
            return redirect(url_for('operations_web_bp.store_inventory'))

        elif action == 'adjust_stock':
            item_id = request.form.get('item_id')
            adjustment = float(request.form.get('adjustment', 0))
            notes = request.form.get('notes', '')
            item = StoreInventory.query.get_or_404(item_id)
            item.quantity += adjustment
            if item.quantity < 0:
                item.quantity = 0
            db.session.commit()
            flash(f'Stock for "{item.name}" adjusted by {adjustment:+.2f}. New quantity: {item.quantity:.2f}.', 'success')
            return redirect(url_for('operations_web_bp.store_inventory'))

        elif action == 'delete':
            item_id = request.form.get('item_id')
            item = StoreInventory.query.get_or_404(item_id)
            db.session.delete(item)
            db.session.commit()
            flash('Item deleted.', 'info')
            return redirect(url_for('operations_web_bp.store_inventory'))

    # GET
    items = StoreInventory.query.order_by(StoreInventory.name).all()
    total_items = len(items)
    total_quantity = sum(i.quantity for i in items) if items else 0
    low_stock = [i for i in items if i.quantity <= i.reorder_level]
    low_stock_count = len(low_stock)

    return render_template(
        'operations/store/inventory.html',
        items=items,
        total_items=total_items,
        total_quantity=total_quantity,
        low_stock_count=low_stock_count
    )

@operations_web_bp.route('/store/items-management', methods=['GET', 'POST'])
@login_required
def store_items_management():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_tag':
            item_id = request.form.get('item_id')
            tag_number = request.form.get('tag_number')
            purchase_date = request.form.get('purchase_date')
            expiry_date = request.form.get('expiry_date')
            notes = request.form.get('notes')
            if not item_id or not tag_number:
                flash('Item and tag number are required.', 'danger')
                return redirect(url_for('operations_web_bp.store_items_management'))
            item = StoreInventory.query.get_or_404(item_id)
            if not item.is_tracked:
                flash('This item is not set as tracked. Please edit the item to enable tracking.', 'danger')
                return redirect(url_for('operations_web_bp.store_items_management'))
            # Check duplicate tag
            if ItemTag.query.filter_by(tag_number=tag_number).first():
                flash('Tag number already exists.', 'danger')
                return redirect(url_for('operations_web_bp.store_items_management'))
            tag = ItemTag(
                item_id=item.id,
                tag_number=tag_number,
                purchase_date=datetime.strptime(purchase_date, '%Y-%m-%d') if purchase_date else None,
                expiry_date=datetime.strptime(expiry_date, '%Y-%m-%d') if expiry_date else None,
                notes=notes
            )
            db.session.add(tag)
            db.session.commit()
            flash('Tag added.', 'success')
            return redirect(url_for('operations_web_bp.store_items_management'))

        elif action == 'assign':
            tag_id = request.form.get('tag_id')
            assignee_id = request.form.get('assignee_id')
            due_back = request.form.get('due_back')
            notes = request.form.get('notes')
            tag = ItemTag.query.get_or_404(tag_id)
            if tag.status != 'available':
                flash('Item is not available for assignment.', 'danger')
                return redirect(url_for('operations_web_bp.store_items_management'))
            assignment = ItemAssignment(
                tag_id=tag.id,
                assigned_to=assignee_id,
                assigned_by=current_user.id,
                due_back=datetime.strptime(due_back, '%Y-%m-%d') if due_back else None,
                notes=notes
            )
            tag.status = 'assigned'
            db.session.add(assignment)
            db.session.commit()
            flash(f'Item {tag.tag_number} assigned.', 'success')
            return redirect(url_for('operations_web_bp.store_items_management'))

        elif action == 'return':
            assignment_id = request.form.get('assignment_id')
            assignment = ItemAssignment.query.get_or_404(assignment_id)
            assignment.returned_at = datetime.utcnow()
            assignment.tag.status = 'available'
            db.session.commit()
            flash('Item returned.', 'success')
            return redirect(url_for('operations_web_bp.store_items_management'))

        elif action == 'delete_tag':
            tag_id = request.form.get('tag_id')
            tag = ItemTag.query.get_or_404(tag_id)
            db.session.delete(tag)
            db.session.commit()
            flash('Tag deleted.', 'info')
            return redirect(url_for('operations_web_bp.store_items_management'))

    # GET – fetch all tracked items and tags
    items = StoreInventory.query.filter_by(is_tracked=True).order_by(StoreInventory.name).all()
    tags = ItemTag.query.order_by(ItemTag.created_at.desc()).all()
    assignments = ItemAssignment.query.filter_by(returned_at=None).order_by(ItemAssignment.assigned_at.desc()).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()  # Assuming User model

    # Group tags by item
    items_with_tags = {}
    for item in items:
        items_with_tags[item.id] = {
            'item': item,
            'tags': [t for t in tags if t.item_id == item.id]
        }

    return render_template(
        'operations/store/items_management.html',
        items=items,
        items_with_tags=items_with_tags,
        tags=tags,
        assignments=assignments,
        users=users
    )



@operations_web_bp.route('/store/maintenance', methods=['GET', 'POST'])
@login_required
def store_maintenance():
    from app.operations.models import ItemTag

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            item_id = request.form.get('item_id')
            tag_id = request.form.get('tag_id')
            maintenance_date_str = request.form.get('maintenance_date')
            type_ = request.form.get('type')
            description = request.form.get('description')
            cost = float(request.form.get('cost', 0))
            performed_by = request.form.get('performed_by')
            notes = request.form.get('notes')
            transaction_ref = request.form.get('transaction_reference')
            petty_cash_account_id = request.form.get('petty_cash_account_id')

            if not all([item_id, maintenance_date_str, type_, description]):
                flash('Item, date, type, and description are required.', 'danger')
                return redirect(url_for('operations_web_bp.store_maintenance'))

            maintenance = StoreMaintenance(
                item_id=item_id,
                tag_id=tag_id if tag_id else None,
                maintenance_date=datetime.strptime(maintenance_date_str, '%Y-%m-%d'),
                type=type_,
                description=description,
                cost=cost,
                performed_by=performed_by,
                notes=notes,
                transaction_reference=transaction_ref,
                petty_cash_account_id=petty_cash_account_id
            )
            db.session.add(maintenance)

            # Petty cash deduction (unchanged)
            if cost > 0 and petty_cash_account_id:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if petty_cash and petty_cash.current_balance >= cost:
                    petty_tx = PettyCashTransaction(
                        transaction_type='withdrawal',
                        amount=cost,
                        description=f"Store maintenance: {description} (Item: {item_id})",
                        source_petty_cash_account_id=petty_cash.id,
                        status='completed',
                        completed_at=datetime.utcnow(),
                        initiated_by=current_user.id,
                        external_reference=transaction_ref
                    )
                    petty_tx.transaction_ref = petty_tx.generate_ref()
                    db.session.add(petty_tx)
                    petty_cash.current_balance -= cost
                elif petty_cash:
                    flash(f'Insufficient balance in {petty_cash.name}.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.store_maintenance'))

            db.session.commit()
            flash('Maintenance record added.', 'success')
            return redirect(url_for('operations_web_bp.store_maintenance'))

        # Similar for edit – update tag_id as well
        elif action == 'edit':
            record_id = request.form.get('record_id')
            record = StoreMaintenance.query.get_or_404(record_id)
            record.item_id = request.form.get('item_id')
            record.tag_id = request.form.get('tag_id') or None
            record.maintenance_date = datetime.strptime(request.form.get('maintenance_date'), '%Y-%m-%d')
            record.type = request.form.get('type')
            record.description = request.form.get('description')
            record.cost = float(request.form.get('cost', 0))
            record.performed_by = request.form.get('performed_by')
            record.notes = request.form.get('notes')
            record.transaction_reference = request.form.get('transaction_reference')
            record.petty_cash_account_id = request.form.get('petty_cash_account_id')
            db.session.commit()
            flash('Maintenance record updated.', 'success')
            return redirect(url_for('operations_web_bp.store_maintenance'))

        # Delete unchanged
        elif action == 'delete':
            record_id = request.form.get('record_id')
            record = StoreMaintenance.query.get_or_404(record_id)
            db.session.delete(record)
            db.session.commit()
            flash('Maintenance record deleted.', 'info')
            return redirect(url_for('operations_web_bp.store_maintenance'))

    # GET – fetch data
    items = StoreInventory.query.order_by(StoreInventory.name).all()
    # Fetch only tracked items' tags? Actually we need all tags to show in dropdown
    tags = ItemTag.query.filter(ItemTag.item_id.in_([i.id for i in items if i.is_tracked])).all()
    # But we'll pass all tags and filter on client side
    all_tags = ItemTag.query.all()

    # ... (rest of GET unchanged)

    # GET – fetch data with filters
    item_filter = request.args.get('item', type=int)
    type_filter = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = StoreMaintenance.query
    if item_filter:
        query = query.filter(StoreMaintenance.item_id == item_filter)
    if type_filter:
        query = query.filter(StoreMaintenance.type == type_filter)
    if start_date:
        query = query.filter(StoreMaintenance.maintenance_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(StoreMaintenance.maintenance_date <= datetime.strptime(end_date, '%Y-%m-%d'))

    records = query.order_by(StoreMaintenance.maintenance_date.desc()).all()
    items = StoreInventory.query.order_by(StoreInventory.name).all()
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).all()

    # Summary stats
    total_records = len(records)
    total_cost = sum(r.cost for r in records) if records else 0
    recent_count = sum(1 for r in records if (datetime.utcnow() - r.maintenance_date).days <= 30)

    return render_template(
        'operations/store/maintenance.html',
        records=records,
        items=items,
        petty_cash_accounts=petty_cash_accounts,
        total_records=total_records,
        total_cost=total_cost,
        recent_count=recent_count,
        item_filter=item_filter,
        type_filter=type_filter,
        start_date=start_date,
        end_date=end_date,
        all_tags=all_tags  # <-- ADD THIS
    )
    
    
    
    


@operations_web_bp.route('/store/reports')
@login_required
def store_reports():
    """Comprehensive store reports dashboard."""
    # --- Inventory stats ---
    total_items = StoreInventory.query.count()
    total_quantity = db.session.query(func.sum(StoreInventory.quantity)).scalar() or 0
    categories = db.session.query(
        StoreInventory.category,
        func.count(StoreInventory.id)
    ).group_by(StoreInventory.category).all()

    # Low stock items (quantity <= reorder_level)
    low_stock_items = StoreInventory.query.filter(
        StoreInventory.quantity <= StoreInventory.reorder_level
    ).order_by(StoreInventory.quantity).all()

    # --- Tag stats ---
    tags = ItemTag.query.all()
    tags_by_status = {
        'available': sum(1 for t in tags if t.status == 'available'),
        'assigned': sum(1 for t in tags if t.status == 'assigned'),
        'other': sum(1 for t in tags if t.status not in ['available', 'assigned'])
    }

    # Active assignments
    active_assignments = ItemAssignment.query.filter(
        ItemAssignment.returned_at.is_(None)
    ).all()
    active_assignments_count = len(active_assignments)
    overdue_assignments = [a for a in active_assignments if a.due_back and a.due_back < datetime.utcnow().date()]

    # --- Maintenance stats ---
    total_maintenance_cost = db.session.query(func.sum(StoreMaintenance.cost)).scalar() or 0
    # Maintenance cost by month (last 12 months)
    now = datetime.utcnow()
    last_year = now - timedelta(days=365)
    monthly_maintenance = db.session.query(
        extract('year', StoreMaintenance.maintenance_date).label('year'),
        extract('month', StoreMaintenance.maintenance_date).label('month'),
        func.sum(StoreMaintenance.cost).label('total_cost')
    ).filter(
        StoreMaintenance.maintenance_date >= last_year
    ).group_by('year', 'month').order_by('year', 'month').all()

    # Maintenance by type
    maintenance_by_type = db.session.query(
        StoreMaintenance.type,
        func.count(StoreMaintenance.id).label('count'),
        func.sum(StoreMaintenance.cost).label('total_cost')
    ).group_by(StoreMaintenance.type).all()

    # Recent maintenance (last 10)
    recent_maintenance = StoreMaintenance.query.order_by(
        StoreMaintenance.maintenance_date.desc()
    ).limit(10).all()

    # --- Recent assignments (last 10) ---
    recent_assignments = ItemAssignment.query.order_by(
        ItemAssignment.assigned_at.desc()
    ).limit(10).all()

    # --- Chart data formatting ---
    # Monthly maintenance labels and data
    month_names = [calendar.month_name[m] for m in range(1, 13)]
    monthly_data = {}
    for row in monthly_maintenance:
        month_key = f"{int(row.year)}-{int(row.month):02d}"
        monthly_data[month_key] = float(row.total_cost)

    # Fill in missing months in last year
    labels = []
    values = []
    for i in range(11, -1, -1):  # last 12 months inclusive
        month_date = now.replace(day=1) - timedelta(days=i*30)  # approximate
        key = month_date.strftime('%Y-%m')
        labels.append(month_date.strftime('%b %Y'))
        values.append(monthly_data.get(key, 0))

    # Categories pie data
    categories_labels = [c[0] or 'Uncategorized' for c in categories]
    categories_counts = [c[1] for c in categories]

    return render_template(
        'operations/store/reports.html',
        total_items=total_items,
        total_quantity=total_quantity,
        low_stock_items=low_stock_items,
        tags_by_status=tags_by_status,
        active_assignments_count=active_assignments_count,
        overdue_assignments=overdue_assignments,
        total_maintenance_cost=total_maintenance_cost,
        maintenance_by_type=maintenance_by_type,
        recent_maintenance=recent_maintenance,
        recent_assignments=recent_assignments,
        monthly_labels=labels,
        monthly_values=values,
        categories_labels=categories_labels,
        categories_counts=categories_counts
    )

# ----------------------------------------------------------------------
# Supplier Management
# ----------------------------------------------------------------------

@operations_web_bp.route('/supplier/list')
@login_required
def supplier_list():
    """List all suppliers (directory)."""
    suppliers = OperationsSupplier.query.filter_by(is_active=True).order_by(OperationsSupplier.name).all()
    return render_template('operations/supplier/list.html', suppliers=suppliers)


@operations_web_bp.route('/supplier/add', methods=['POST'])
@login_required
def supplier_add():
    """Add a new supplier."""
    name = request.form.get('name')
    contact_person = request.form.get('contact_person')
    phone = request.form.get('phone')
    email = request.form.get('email')
    address = request.form.get('address')
    category = request.form.get('category')
    rating = request.form.get('rating', type=int)
    lead_time_days = request.form.get('lead_time_days', type=int, default=7)
    payment_terms = request.form.get('payment_terms')

    if not name:
        flash('Supplier name is required.', 'danger')
        return redirect(url_for('operations_web_bp.supplier_list'))

    supplier = OperationsSupplier(
        name=name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        category=category,
        rating=rating or 3,
        lead_time_days=lead_time_days,
        payment_terms=payment_terms,
        is_active=True
    )
    db.session.add(supplier)
    db.session.commit()
    flash(f'Supplier "{name}" added successfully.', 'success')
    return redirect(url_for('operations_web_bp.supplier_list'))


@operations_web_bp.route('/supplier/edit/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
def supplier_edit(supplier_id):
    """Edit an existing supplier."""
    supplier = OperationsSupplier.query.get_or_404(supplier_id)

    if request.method == 'POST':
        supplier.name = request.form.get('name')
        supplier.contact_person = request.form.get('contact_person')
        supplier.phone = request.form.get('phone')
        supplier.email = request.form.get('email')
        supplier.address = request.form.get('address')
        supplier.category = request.form.get('category')
        supplier.rating = request.form.get('rating', type=int) or 3
        supplier.lead_time_days = request.form.get('lead_time_days', type=int, default=7)
        supplier.payment_terms = request.form.get('payment_terms')
        db.session.commit()
        flash('Supplier updated successfully.', 'success')
        return redirect(url_for('operations_web_bp.supplier_list'))

    return render_template('operations/supplier/edit.html', supplier=supplier)


@operations_web_bp.route('/supplier/delete/<int:supplier_id>', methods=['POST'])
@login_required
def supplier_delete(supplier_id):
    """Deactivate (soft delete) a supplier."""
    supplier = OperationsSupplier.query.get_or_404(supplier_id)
    supplier.is_active = False
    db.session.commit()
    flash(f'Supplier "{supplier.name}" deactivated.', 'info')
    return redirect(url_for('operations_web_bp.supplier_list'))



@operations_web_bp.route('/supplier/orders', methods=['GET', 'POST'])
@login_required
def supplier_orders():
    if request.method == 'POST':
        action = request.form.get('action')
        order_id = request.form.get('order_id')
        order = ProcurementOrder.query.get_or_404(order_id)

        if action == 'edit_order':
            # Only allow editing status and notes (and maybe expected_delivery)
            order.status = request.form.get('status')
            order.notes = request.form.get('notes')
            db.session.commit()
            flash('Order updated successfully.', 'success')
            return redirect(url_for('operations_web_bp.supplier_orders'))

        elif action == 'cancel_order':
            if len(order.deliveries) > 0:
                flash('Cannot cancel an order that already has deliveries.', 'danger')
            else:
                order.status = 'cancelled'
                db.session.commit()
                flash('Order cancelled.', 'success')
            return redirect(url_for('operations_web_bp.supplier_orders'))

    # GET - display orders with filters
    status_filter = request.args.get('status')
    supplier_filter = request.args.get('supplier')

    query = ProcurementOrder.query.order_by(ProcurementOrder.order_date.desc())
    if status_filter:
        query = query.filter(ProcurementOrder.status == status_filter)
    if supplier_filter:
        query = query.filter(ProcurementOrder.supplier_id == supplier_filter)

    orders = query.all()
    suppliers = OperationsSupplier.query.order_by(OperationsSupplier.name).all()
    statuses = ['ordered', 'partially_received', 'received', 'cancelled']

    # Summary stats
    total_orders = len(orders)
    total_value = sum(o.total_amount for o in orders)

    return render_template(
        'operations/supplier/orders.html',
        orders=orders,
        suppliers=suppliers,
        statuses=statuses,
        status_filter=status_filter,
        supplier_filter=supplier_filter,
        total_orders=total_orders,
        total_value=total_value
    )

# app/operations/routes.py

@operations_web_bp.route('/supplier/payments', methods=['GET', 'POST'])
@login_required
def supplier_payments():
    from datetime import datetime

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'make_payment':
            invoice_id = request.form.get('invoice_id')
            amount = float(request.form.get('amount', 0))
            transaction_cost = float(request.form.get('transaction_cost', 0))
            payment_method = request.form.get('payment_method')
            reference = request.form.get('reference')
            notes = request.form.get('notes')
            petty_cash_account_id = request.form.get('petty_cash_account_id')

            if not petty_cash_account_id:
                flash('Please select a petty cash account.', 'danger')
                return redirect(url_for('operations_web_bp.supplier_payments'))

            invoice = ProcurementSupplierInvoice.query.get_or_404(invoice_id)
            if invoice.balance_due < amount:
                flash('Payment amount exceeds invoice balance.', 'danger')
                return redirect(url_for('operations_web_bp.supplier_payments'))

            petty_cash = PettyCash.query.get(petty_cash_account_id)
            if not petty_cash or not petty_cash.is_active:
                flash('Invalid petty cash account.', 'danger')
                return redirect(url_for('operations_web_bp.supplier_payments'))

            total_deduction = amount + transaction_cost
            if petty_cash.current_balance < total_deduction:
                flash(f'Insufficient balance in {petty_cash.name}. Required: {total_deduction:.2f}, Available: {petty_cash.current_balance:.2f}', 'danger')
                return redirect(url_for('operations_web_bp.supplier_payments'))

            # Get supplier and its account (the first one)
            supplier = invoice.order.supplier
            if not supplier.account:
                flash('Supplier account not found.', 'danger')
                return redirect(url_for('operations_web_bp.supplier_payments'))
            account = supplier.account[0]   # take the first account

            # Petty cash transaction for the payment
            payment_tx = PettyCashTransaction(
                transaction_type='withdrawal',
                amount=amount,
                description=f"Payment to supplier {invoice.order.supplier.name} for invoice {invoice.invoice_number}" + (f" - Notes: {notes}" if notes else ""),
                source_petty_cash_account_id=petty_cash.id,
                status='completed',
                completed_at=datetime.utcnow(),
                initiated_by=current_user.id,
                external_reference=reference
            )
            payment_tx.transaction_ref = payment_tx.generate_ref()
            db.session.add(payment_tx)

            # Petty cash transaction for the transaction cost (if > 0)
            if transaction_cost > 0:
                fee_tx = PettyCashTransaction(
                    transaction_type='withdrawal',
                    amount=transaction_cost,
                    description=f"Transaction fee for payment to supplier {invoice.order.supplier.name} (invoice {invoice.invoice_number})" + (f" - Notes: {notes}" if notes else ""),
                    source_petty_cash_account_id=petty_cash.id,
                    status='completed',
                    completed_at=datetime.utcnow(),
                    initiated_by=current_user.id,
                    external_reference=reference
                )
                fee_tx.transaction_ref = fee_tx.generate_ref()
                db.session.add(fee_tx)

            # Reduce petty cash balance
            petty_cash.current_balance -= total_deduction
            db.session.add(petty_cash)

            # Create supplier payment record
            payment = OperationsSupplierPayment(
                supplier_account_id=account.id,
                invoice_id=invoice.id,
                payment_date=datetime.utcnow(),
                amount=amount,
                payment_method=payment_method,
                reference=reference,
                notes=notes,
                created_by=current_user.id
            )
            db.session.add(payment)

            # Update invoice
            invoice.paid_amount += amount
            invoice.update_status()

            # Update supplier account balance
            account.current_balance -= amount
            db.session.commit()

            flash(f'Payment of KES {amount:,.2f} recorded for invoice {invoice.invoice_number}. Transaction cost KES {transaction_cost:,.2f} deducted from petty cash.', 'success')
            return redirect(url_for('operations_web_bp.supplier_payments'))

    # GET
    invoices = ProcurementSupplierInvoice.query.filter(
        ProcurementSupplierInvoice.status.in_(['pending', 'partially_paid'])
    ).order_by(ProcurementSupplierInvoice.due_date.asc()).all()

    grouped = {}
    for inv in invoices:
        supplier = inv.order.supplier
        if supplier.id not in grouped:
            grouped[supplier.id] = {
                'supplier': supplier,
                'total_due': 0.0,
                'invoices': []
            }
        grouped[supplier.id]['total_due'] += inv.balance_due
        grouped[supplier.id]['invoices'].append(inv)

    recent_payments = OperationsSupplierPayment.query.order_by(OperationsSupplierPayment.payment_date.desc()).limit(30).all()

    # Fetch active petty cash accounts for the dropdown
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).all()

    return render_template(
        'operations/supplier/payments.html',
        grouped=grouped,
        recent_payments=recent_payments,
        now=datetime.utcnow(),
        petty_cash_accounts=petty_cash_accounts
    )


# ----------------------------------------------------------------------
# Account Management (Petty Cash)
# ----------------------------------------------------------------------
@operations_web_bp.route('/petty-cash/balance')
@login_required
def petty_cash_balance():
    """
    Display all petty cash accounts with current balances and recent transactions.
    """
    # Get all active petty cash accounts
    accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()

    # Calculate total balance across all accounts
    total_balance = sum(acc.current_balance for acc in accounts)

    # Get recent transactions across all accounts (last 50)
    recent_transactions = PettyCashTransaction.query.filter(
        PettyCashTransaction.status == 'completed'
    ).order_by(PettyCashTransaction.completed_at.desc()).limit(50).all()

    # For each account, get the 5 most recent transactions
    for acc in accounts:
        acc.recent_transactions = PettyCashTransaction.query.filter(
            (PettyCashTransaction.source_petty_cash_account_id == acc.id) |
            (PettyCashTransaction.dest_petty_cash_account_id == acc.id),
            PettyCashTransaction.status == 'completed'
        ).order_by(PettyCashTransaction.completed_at.desc()).limit(5).all()

    return render_template(
        'operations/petty_cash/balance.html',
        accounts=accounts,
        total_balance=total_balance,
        recent_transactions=recent_transactions
    )



@operations_web_bp.route('/petty-cash/transactions')
@login_required
def petty_cash_transactions():
    # Get filter parameters
    account_id = request.args.get('account_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Base query – only completed transactions
    query = PettyCashTransaction.query.filter_by(status='completed')

    # Apply account filter (if provided)
    if account_id:
        query = query.filter(
            (PettyCashTransaction.source_petty_cash_account_id == account_id) |
            (PettyCashTransaction.dest_petty_cash_account_id == account_id)
        )

    # Apply date filters
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(PettyCashTransaction.completed_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        query = query.filter(PettyCashTransaction.completed_at <= end_date)

    # Order by date (ascending for running balance)
    transactions = query.order_by(PettyCashTransaction.completed_at.asc()).all()

    # Build ledger entries with running balance
    ledger_entries = []
    balance = 0
    for tx in transactions:
        # Determine debit/credit based on transaction type
        if tx.transaction_type in ('deposit', 'transfer_in'):
            debit = tx.amount
            credit = 0
            balance += debit
        else:  # withdrawal, transfer_out
            debit = 0
            credit = tx.amount
            balance -= credit

        # Get the associated petty cash account name
        account = None
        if tx.dest_petty_cash_account_id:
            account = tx.dest_account
        elif tx.source_petty_cash_account_id:
            account = tx.source_account

        ledger_entries.append({
            'date': tx.completed_at or tx.initiated_at,
            'reference': tx.transaction_ref,
            'account_name': account.name if account else 'N/A',
            'type': tx.transaction_type,
            'description': tx.description,
            'debit': debit,
            'credit': credit,
            'balance': balance
        })

    # Calculate totals
    total_debits = sum(e['debit'] for e in ledger_entries)
    total_credits = sum(e['credit'] for e in ledger_entries)
    closing_balance = balance

    # Get all active petty cash accounts for filter dropdown
    accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()

    return render_template(
        'operations/petty_cash/transactions.html',
        ledger_entries=ledger_entries,
        total_debits=total_debits,
        total_credits=total_credits,
        closing_balance=closing_balance,
        accounts=accounts,
        selected_account=account_id,
        start_date=start_date_str,
        end_date=end_date_str
    )



@operations_web_bp.route('/petty-cash/requests', methods=['GET', 'POST'])
@login_required
def petty_cash_requests():
    """
    View and manage petty cash requests (user level).
    GET: show all requests (pending and history).
    POST: create, edit, or cancel a request.
    """
    if request.method == 'POST':
        action = request.form.get('action')

        # Create new request
        if action == 'create':
            amount = float(request.form.get('amount', 0))
            reason = request.form.get('reason')
            account_id = request.form.get('account_id')

            if not amount or not reason or not account_id:
                flash('Amount, reason, and account are required.', 'danger')
                return redirect(url_for('operations_web_bp.petty_cash_requests'))

            new_request = PettyCashRequest(
                requester_id=current_user.id,
                petty_cash_account_id=account_id,
                amount=amount,
                reason=reason,
                status='pending',
                created_at=datetime.utcnow()
            )
            db.session.add(new_request)
            db.session.commit()
            flash('Request submitted successfully.', 'success')
            return redirect(url_for('operations_web_bp.petty_cash_requests'))

        # Edit existing request (only if still pending)
        elif action == 'edit':
            request_id = request.form.get('request_id')
            amount = float(request.form.get('amount'))
            reason = request.form.get('reason')
            account_id = request.form.get('account_id')
            req = PettyCashRequest.query.get_or_404(request_id)

            if req.status != 'pending':
                flash('Cannot edit a request that has already been processed.', 'danger')
                return redirect(url_for('operations_web_bp.petty_cash_requests'))

            req.amount = amount
            req.reason = reason
            req.petty_cash_account_id = account_id
            db.session.commit()
            flash(f'Request #{req.id} updated.', 'success')
            return redirect(url_for('operations_web_bp.petty_cash_requests'))

        # Cancel request (delete)
        elif action == 'cancel':
            request_id = request.form.get('request_id')
            req = PettyCashRequest.query.get_or_404(request_id)

            if req.status != 'pending':
                flash('Cannot cancel a request that has already been processed.', 'danger')
                return redirect(url_for('operations_web_bp.petty_cash_requests'))

            db.session.delete(req)
            db.session.commit()
            flash(f'Request #{req.id} cancelled.', 'info')
            return redirect(url_for('operations_web_bp.petty_cash_requests'))

    # GET: display requests
    accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()
    # Only show pending requests that belong to the current user
    pending_requests = PettyCashRequest.query.filter_by(
        requester_id=current_user.id,
        status='pending'
    ).order_by(PettyCashRequest.created_at.desc()).all()
    # Processed requests (approved/denied) for the current user
    processed_requests = PettyCashRequest.query.filter(
        PettyCashRequest.requester_id == current_user.id,
        PettyCashRequest.status.in_(['approved', 'denied'])
    ).order_by(PettyCashRequest.created_at.desc()).all()

    total_pending = len(pending_requests)
    total_approved = sum(1 for r in processed_requests if r.status == 'approved')
    total_denied = len(processed_requests) - total_approved

    return render_template(
        'operations/petty_cash/requests.html',
        accounts=accounts,
        pending_requests=pending_requests,
        processed_requests=processed_requests,
        total_pending=total_pending,
        total_approved=total_approved,
        total_denied=total_denied
    )


# ----------------------------------------------------------------------
# Farm Management
# ----------------------------------------------------------------------


@operations_web_bp.route('/farm/inventory', methods=['GET', 'POST'])
@login_required
def farm_inventory():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name')
            quantity = float(request.form.get('quantity', 0))
            unit = request.form.get('unit', 'pcs')
            reorder_level = float(request.form.get('reorder_level', 10))
            category = request.form.get('category')
            location = request.form.get('location')
            notes = request.form.get('notes')
            type_ = request.form.get('type', 'input')
            price_per_unit = float(request.form.get('price_per_unit', 0))

            if not name:
                flash('Item name is required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_inventory'))

            # Check if item already exists
            existing = FarmInventory.query.filter_by(name=name).first()
            if existing:
                flash(f'Item "{name}" already exists.', 'danger')
                return redirect(url_for('operations_web_bp.farm_inventory'))

            item = FarmInventory(
                name=name,
                quantity=quantity,
                unit=unit,
                reorder_level=reorder_level,
                category=category,
                location=location,
                notes=notes,
                type=type_,
                price_per_unit=price_per_unit
            )
            db.session.add(item)
            db.session.commit()
            flash('Item added.', 'success')
            return redirect(url_for('operations_web_bp.farm_inventory'))

        elif action == 'edit':
            item_id = request.form.get('item_id')
            item = FarmInventory.query.get_or_404(item_id)
            item.name = request.form.get('name')
            item.quantity = float(request.form.get('quantity', 0))
            item.unit = request.form.get('unit', 'pcs')
            item.reorder_level = float(request.form.get('reorder_level', 10))
            item.category = request.form.get('category')
            item.location = request.form.get('location')
            item.notes = request.form.get('notes')
            item.type = request.form.get('type', 'input')
            item.price_per_unit = float(request.form.get('price_per_unit', 0))
            db.session.commit()
            flash('Item updated.', 'success')
            return redirect(url_for('operations_web_bp.farm_inventory'))

        elif action == 'adjust_stock':
            item_id = request.form.get('item_id')
            adjustment = float(request.form.get('adjustment', 0))
            notes = request.form.get('notes', '')
            item = FarmInventory.query.get_or_404(item_id)
            item.quantity += adjustment
            if item.quantity < 0:
                item.quantity = 0
            db.session.commit()
            flash(f'Stock for "{item.name}" adjusted by {adjustment:+.2f}. New quantity: {item.quantity:.2f}.', 'success')
            return redirect(url_for('operations_web_bp.farm_inventory'))

        elif action == 'delete':
            item_id = request.form.get('item_id')
            item = FarmInventory.query.get_or_404(item_id)
            db.session.delete(item)
            db.session.commit()
            flash('Item deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_inventory'))

    # GET
    items = FarmInventory.query.order_by(FarmInventory.name).all()
    total_items = len(items)
    total_quantity = sum(i.quantity for i in items) if items else 0
    low_stock = [i for i in items if i.quantity <= i.reorder_level]
    low_stock_count = len(low_stock)
    # Optional: calculate stock value (sum of quantity * price_per_unit)
    total_value = sum(i.quantity * i.price_per_unit for i in items) if items else 0

    # For filter dropdowns
    categories = sorted(set(i.category for i in items if i.category))
    locations = sorted(set(i.location for i in items if i.location))
    types = ['input', 'harvest']

    return render_template(
        'operations/farm/inventory.html',
        items=items,
        total_items=total_items,
        total_quantity=total_quantity,
        low_stock_count=low_stock_count,
        total_value=total_value,
        categories=categories,
        locations=locations,
        types=types
    )





@operations_web_bp.route('/farm/revenue', methods=['GET', 'POST'])
@login_required
def farm_revenue():
    if request.method == 'POST':
        action = request.form.get('action')

        # Add Revenue
        if action == 'add_revenue':
            source = request.form.get('source')
            date_str = request.form.get('date')
            description = request.form.get('description')
            quantity_sold = float(request.form.get('quantity_sold', 0))
            unit_price = float(request.form.get('unit_price', 0))
            total_amount = float(request.form.get('total_amount', 0))
            customer = request.form.get('customer')
            payment_method = request.form.get('payment_method')
            reference = request.form.get('reference', '').strip()
            notes = request.form.get('notes')
            petty_cash_account_id = request.form.get('petty_cash_account_id')
            transaction_reference = request.form.get('transaction_reference', '').strip()

            # Validate required fields
            if not all([source, date_str, description, total_amount]):
                flash('Source, date, description, and total amount are required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_revenue'))

            # Prepare revenue record
            revenue = FarmRevenue(
                source=source,
                date=datetime.strptime(date_str, '%Y-%m-%d'),
                description=description,
                quantity_sold=quantity_sold,
                unit_price=unit_price,
                total_amount=total_amount,
                customer=customer,
                payment_method=payment_method,
                reference=reference,
                notes=notes
            )

            # Handle source-specific links and inventory adjustments
            if source == 'crop':
                # Must select either crop or inventory item
                crop_id = request.form.get('crop_id')
                inventory_id = request.form.get('inventory_id')
                if not crop_id and not inventory_id:
                    flash('Please select a crop or inventory item for crop revenue.', 'danger')
                    return redirect(url_for('operations_web_bp.farm_revenue'))

                if crop_id:
                    revenue.crop_id = crop_id
                if inventory_id:
                    revenue.inventory_item_id = inventory_id
                    # Deduct from inventory
                    inventory = FarmInventory.query.get(inventory_id)
                    if inventory:
                        if inventory.quantity < quantity_sold:
                            flash(f'Insufficient stock in inventory: only {inventory.quantity} {inventory.unit} available.', 'danger')
                            return redirect(url_for('operations_web_bp.farm_revenue'))
                        inventory.quantity -= quantity_sold
                        db.session.add(inventory)
                    else:
                        flash('Selected inventory item not found.', 'warning')

            elif source == 'livestock':
                # Link to livestock (either for animal sale or product sale)
                livestock_id = request.form.get('livestock_id')
                if not livestock_id:
                    flash('Please select livestock for livestock revenue.', 'danger')
                    return redirect(url_for('operations_web_bp.farm_revenue'))
                revenue.livestock_id = livestock_id

                # Optionally reduce livestock count if selling animals (if quantity_sold > 0 and unit is heads)
                # We need to know if this sale reduces headcount. For simplicity, we'll reduce if quantity_sold > 0 and unit is 'heads' (or the livestock's unit is heads)
                livestock = FarmLivestock.query.get(livestock_id)
                if livestock and livestock.unit.lower() == 'heads' and quantity_sold > 0:
                    if livestock.quantity < quantity_sold:
                        flash(f'Insufficient livestock: only {livestock.quantity} {livestock.unit} available.', 'danger')
                        return redirect(url_for('operations_web_bp.farm_revenue'))
                    livestock.quantity -= quantity_sold
                    db.session.add(livestock)

            elif source == 'other':
                # No special links
                pass
            else:
                flash('Invalid source.', 'danger')
                return redirect(url_for('operations_web_bp.farm_revenue'))

            # Add revenue record
            db.session.add(revenue)
            db.session.flush()  # to get revenue.id

            # Handle petty cash deposit if selected
            if petty_cash_account_id:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if not petty_cash or not petty_cash.is_active:
                    flash('Invalid petty cash account.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_revenue'))

                # Create deposit transaction
                petty_tx = PettyCashTransaction(
                    transaction_type='deposit',
                    amount=total_amount,
                    description=f"Farm revenue: {description}",
                                    dest_petty_cash_account_id=petty_cash.id,   # Correct field

                    status='completed',
                    completed_at=datetime.utcnow(),
                    initiated_by=current_user.id,
                    transaction_ref=transaction_reference,
                    external_reference=f"REV-{revenue.id}"
                )
                db.session.add(petty_tx)
                db.session.flush()
                if not petty_tx.transaction_ref:
                    petty_tx.transaction_ref = petty_tx.generate_ref()

                # Increase petty cash balance
                petty_cash.current_balance += total_amount
                db.session.add(petty_cash)

            db.session.commit()
            flash('Revenue recorded successfully.', 'success')
            return redirect(url_for('operations_web_bp.farm_revenue'))

        # Edit Revenue (no inventory adjustments for simplicity – we don't revert)
        elif action == 'edit_revenue':
            revenue_id = request.form.get('revenue_id')
            revenue = FarmRevenue.query.get_or_404(revenue_id)
            revenue.source = request.form.get('source')
            revenue.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
            revenue.description = request.form.get('description')
            revenue.quantity_sold = float(request.form.get('quantity_sold', 0))
            revenue.unit_price = float(request.form.get('unit_price', 0))
            revenue.total_amount = float(request.form.get('total_amount', 0))
            revenue.customer = request.form.get('customer')
            revenue.payment_method = request.form.get('payment_method')
            revenue.reference = request.form.get('reference')
            revenue.notes = request.form.get('notes')
            # We do not update links or inventory quantities on edit – too complex.
            db.session.commit()
            flash('Revenue record updated.', 'success')
            return redirect(url_for('operations_web_bp.farm_revenue'))

        # Delete Revenue
        elif action == 'delete_revenue':
            revenue_id = request.form.get('revenue_id')
            revenue = FarmRevenue.query.get_or_404(revenue_id)
            # We do not revert inventory/livestock adjustments automatically.
            db.session.delete(revenue)
            db.session.commit()
            flash('Revenue record deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_revenue'))

    # GET – display page with filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    source_filter = request.args.get('source')
    customer_filter = request.args.get('customer')

    query = FarmRevenue.query.order_by(FarmRevenue.date.desc())
    if start_date:
        query = query.filter(FarmRevenue.date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FarmRevenue.date <= datetime.strptime(end_date, '%Y-%m-%d'))
    if source_filter:
        query = query.filter(FarmRevenue.source == source_filter)
    if customer_filter:
        query = query.filter(FarmRevenue.customer.ilike(f'%{customer_filter}%'))

    revenues = query.all()

    # Summary stats
    total_revenue = sum(r.total_amount for r in revenues) if revenues else 0
    total_sales_count = len(revenues)
    # Group by source for card breakdown
    revenue_by_source = {}
    for r in revenues:
        revenue_by_source[r.source] = revenue_by_source.get(r.source, 0) + r.total_amount

    # Unique customers for filter
    customers = sorted(set(r.customer for r in FarmRevenue.query.all() if r.customer))

    # Data for dropdowns
    crops = FarmCrop.query.order_by(FarmCrop.name).all()
    # Only inventory items of type 'harvest' (or you might also include all, but we'll filter)
    inventory_items = FarmInventory.query.filter_by(type='harvest').order_by(FarmInventory.name).all()
    livestock_items = FarmLivestock.query.order_by(FarmLivestock.name).all()
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()

    return render_template(
        'operations/farm/revenue.html',
        revenues=revenues,
        total_revenue=total_revenue,
        total_sales_count=total_sales_count,
        revenue_by_source=revenue_by_source,
        customers=customers,
        crops=crops,
        inventory_items=inventory_items,
        livestock_items=livestock_items,
        petty_cash_accounts=petty_cash_accounts,
        start_date=start_date,
        end_date=end_date,
        source_filter=source_filter,
        customer_filter=customer_filter
    )



@operations_web_bp.route('/farm/expenses', methods=['GET', 'POST'])
@login_required
def farm_expenses():
    if request.method == 'POST':
        action = request.form.get('action')

        # Add Expense (with petty cash)
        if action == 'add_expense':
            date_str = request.form.get('date')
            category = request.form.get('category')
            description = request.form.get('description')
            amount = float(request.form.get('amount', 0))
            payment_method = request.form.get('payment_method')
            reference = request.form.get('reference', '').strip()
            notes = request.form.get('notes')
            petty_cash_account_id = request.form.get('petty_cash_account_id')
            transaction_reference = request.form.get('transaction_reference', '').strip()

            if not all([date_str, description, amount]):
                flash('Date, description, and amount are required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_expenses'))

            if amount <= 0:
                flash('Amount must be greater than zero.', 'danger')
                return redirect(url_for('operations_web_bp.farm_expenses'))

            # Create expense record
            expense = FarmExpense(
                date=datetime.strptime(date_str, '%Y-%m-%d'),
                category=category,
                description=description,
                amount=amount,
                payment_method=payment_method,
                reference=reference,
                notes=notes
            )
            db.session.add(expense)
            db.session.flush()  # get expense.id

            # If payment method is petty cash or if a petty cash account is selected, deduct from petty cash
            # We'll use petty_cash_account_id if provided; otherwise check payment_method
            if petty_cash_account_id:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if not petty_cash or not petty_cash.is_active:
                    flash('Invalid petty cash account.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_expenses'))

                if petty_cash.current_balance < amount:
                    flash(f'Insufficient balance in {petty_cash.name}. Available: {petty_cash.current_balance:.2f}', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_expenses'))

                # Create petty cash transaction
                petty_tx = PettyCashTransaction(
                    transaction_type='withdrawal',
                    amount=amount,
                    description=f"Farm expense: {description}",
                    source_petty_cash_account_id=petty_cash.id,
                    status='completed',
                    completed_at=datetime.utcnow(),
                    initiated_by=current_user.id,
                    transaction_ref=transaction_reference,
                    external_reference=f"EXP-{expense.id}"
                )
                db.session.add(petty_tx)
                db.session.flush()
                if not petty_tx.transaction_ref:
                    petty_tx.transaction_ref = petty_tx.generate_ref()

                petty_cash.current_balance -= amount
                db.session.add(petty_cash)
            elif payment_method == 'petty_cash':
                # Fallback: if payment method is 'petty_cash' but no account selected, require it
                flash('Please select a petty cash account when using petty cash payment method.', 'danger')
                db.session.rollback()
                return redirect(url_for('operations_web_bp.farm_expenses'))

            db.session.commit()
            flash('Expense added successfully.', 'success')
            return redirect(url_for('operations_web_bp.farm_expenses'))

        # Edit Expense (no petty cash adjustment)
        elif action == 'edit_expense':
            expense_id = request.form.get('expense_id')
            expense = FarmExpense.query.get_or_404(expense_id)
            expense.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
            expense.category = request.form.get('category')
            expense.description = request.form.get('description')
            expense.amount = float(request.form.get('amount', 0))
            expense.payment_method = request.form.get('payment_method')
            expense.reference = request.form.get('reference')
            expense.notes = request.form.get('notes')
            db.session.commit()
            flash('Expense updated.', 'success')
            return redirect(url_for('operations_web_bp.farm_expenses'))

        # Delete Expense
        elif action == 'delete_expense':
            expense_id = request.form.get('expense_id')
            expense = FarmExpense.query.get_or_404(expense_id)
            # We don't reverse petty cash transactions automatically – user can handle manually if needed.
            db.session.delete(expense)
            db.session.commit()
            flash('Expense deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_expenses'))

    # GET: display expenses with filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_filter = request.args.get('category')
    payment_method_filter = request.args.get('payment_method')

    query = FarmExpense.query.order_by(FarmExpense.date.desc())
    if start_date:
        query = query.filter(FarmExpense.date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FarmExpense.date <= datetime.strptime(end_date, '%Y-%m-%d'))
    if category_filter:
        query = query.filter(FarmExpense.category == category_filter)
    if payment_method_filter:
        query = query.filter(FarmExpense.payment_method == payment_method_filter)

    expenses = query.all()

    # Summary stats
    total_expenses = len(expenses)
    total_amount = sum(e.amount for e in expenses) if expenses else 0
    recent_count = sum(1 for e in expenses if (datetime.utcnow() - e.date).days <= 30)
    average_amount = total_amount / total_expenses if total_expenses > 0 else 0

    # Unique categories and payment methods for filter dropdowns
    categories = sorted(set(e.category for e in FarmExpense.query.all() if e.category))
    payment_methods = sorted(set(e.payment_method for e in FarmExpense.query.all() if e.payment_method))

    # Petty cash accounts for the modal
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()

    return render_template(
        'operations/farm/expenses.html',
        expenses=expenses,
        total_expenses=total_expenses,
        total_amount=total_amount,
        recent_count=recent_count,
        average_amount=average_amount,
        categories=categories,
        payment_methods=payment_methods,
        petty_cash_accounts=petty_cash_accounts,
        start_date=start_date,
        end_date=end_date,
        category_filter=category_filter,
        payment_method_filter=payment_method_filter
    )



@operations_web_bp.route('/farm/livestock', methods=['GET', 'POST'])
@login_required
def farm_livestock():
    if request.method == 'POST':
        action = request.form.get('action')

        # Add Livestock (with petty cash)
        if action == 'add_livestock':
            name = request.form.get('name')
            breed = request.form.get('breed')
            quantity = request.form.get('quantity', 0)
            unit = request.form.get('unit', 'heads')
            purchase_date = request.form.get('purchase_date')
            purchase_cost = float(request.form.get('purchase_cost', 0))
            notes = request.form.get('notes')
            petty_cash_account_id = request.form.get('petty_cash_account_id')
            transaction_reference = request.form.get('transaction_reference', '').strip()

            if not name:
                flash('Livestock name is required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_livestock'))

            if purchase_cost > 0 and not petty_cash_account_id:
                flash('Please select a petty cash account for the payment.', 'danger')
                return redirect(url_for('operations_web_bp.farm_livestock'))

            # Create livestock record
            livestock = FarmLivestock(
                name=name,
                breed=breed,
                quantity=int(quantity) if quantity else 0,
                unit=unit,
                purchase_date=datetime.strptime(purchase_date, '%Y-%m-%d') if purchase_date else None,
                purchase_cost=purchase_cost,
                notes=notes
            )
            db.session.add(livestock)
            db.session.flush()  # to get livestock.id

            # If cost > 0, deduct from petty cash
            if purchase_cost > 0:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if not petty_cash or not petty_cash.is_active:
                    flash('Invalid petty cash account.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_livestock'))

                if petty_cash.current_balance < purchase_cost:
                    flash(f'Insufficient balance in {petty_cash.name}. Available: {petty_cash.current_balance:.2f}', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_livestock'))

                # Create petty cash transaction
                petty_tx = PettyCashTransaction(
                    transaction_type='withdrawal',
                    amount=purchase_cost,
                    description=f"Livestock purchase: {name} (Quantity: {quantity})",
                    source_petty_cash_account_id=petty_cash.id,
                    status='completed',
                    completed_at=datetime.utcnow(),
                    initiated_by=current_user.id,
                    transaction_ref=transaction_reference,  # will be overridden if blank
                    external_reference=f"LIVESTOCK-{livestock.id}"
                )
                db.session.add(petty_tx)
                db.session.flush()  # to get ID for reference

                # Generate a proper reference if needed
                if not petty_tx.transaction_ref:
                    petty_tx.transaction_ref = petty_tx.generate_ref()

                # Deduct balance
                petty_cash.current_balance -= purchase_cost
                db.session.add(petty_cash)

            db.session.commit()
            flash(f'Livestock "{name}" added successfully.', 'success')
            return redirect(url_for('operations_web_bp.farm_livestock'))

        # Edit Livestock (no petty cash adjustment)
        elif action == 'edit_livestock':
            livestock_id = request.form.get('livestock_id')
            livestock = FarmLivestock.query.get_or_404(livestock_id)
            livestock.name = request.form.get('name')
            livestock.breed = request.form.get('breed')
            livestock.quantity = int(request.form.get('quantity', 0))
            livestock.unit = request.form.get('unit', 'heads')
            purchase_date = request.form.get('purchase_date')
            livestock.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d') if purchase_date else None
            livestock.purchase_cost = float(request.form.get('purchase_cost', 0))
            livestock.notes = request.form.get('notes')
            db.session.commit()
            flash(f'Livestock "{livestock.name}" updated.', 'success')
            return redirect(url_for('operations_web_bp.farm_livestock'))

        # Delete Livestock (optionally reverse petty cash? We'll skip for simplicity)
        elif action == 'delete_livestock':
            livestock_id = request.form.get('livestock_id')
            livestock = FarmLivestock.query.get_or_404(livestock_id)
            name = livestock.name
            db.session.delete(livestock)
            db.session.commit()
            flash(f'Livestock "{name}" deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_livestock'))

        # Add Health Record (with petty cash)
        elif action == 'add_health_record':
            livestock_id = request.form.get('livestock_id')
            date_str = request.form.get('date')
            type_ = request.form.get('type')
            description = request.form.get('description')
            cost = float(request.form.get('cost', 0))
            performed_by = request.form.get('performed_by')
            notes = request.form.get('notes')
            petty_cash_account_id = request.form.get('petty_cash_account_id')
            transaction_reference = request.form.get('transaction_reference', '').strip()

            if not livestock_id or not date_str or not description:
                flash('Livestock, date, and description are required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_livestock'))

            if cost > 0 and not petty_cash_account_id:
                flash('Please select a petty cash account for the payment.', 'danger')
                return redirect(url_for('operations_web_bp.farm_livestock'))

            # Create health record
            record = FarmHealthRecord(
                livestock_id=livestock_id,
                date=datetime.strptime(date_str, '%Y-%m-%d'),
                type=type_,
                description=description,
                cost=cost,
                performed_by=performed_by,
                notes=notes
            )
            db.session.add(record)
            db.session.flush()  # to get record.id

            # If cost > 0, deduct from petty cash
            if cost > 0:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if not petty_cash or not petty_cash.is_active:
                    flash('Invalid petty cash account.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_livestock'))

                if petty_cash.current_balance < cost:
                    flash(f'Insufficient balance in {petty_cash.name}. Available: {petty_cash.current_balance:.2f}', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_livestock'))

                # Create petty cash transaction
                petty_tx = PettyCashTransaction(
                    transaction_type='withdrawal',
                    amount=cost,
                    description=f"Livestock health: {description} (Livestock ID: {livestock_id})",
                    source_petty_cash_account_id=petty_cash.id,
                    status='completed',
                    completed_at=datetime.utcnow(),
                    initiated_by=current_user.id,
                    transaction_ref=transaction_reference,
                    external_reference=f"HEALTH-{record.id}"
                )
                db.session.add(petty_tx)
                db.session.flush()
                if not petty_tx.transaction_ref:
                    petty_tx.transaction_ref = petty_tx.generate_ref()

                # Deduct balance
                petty_cash.current_balance -= cost
                db.session.add(petty_cash)

            db.session.commit()
            flash('Health record added.', 'success')
            return redirect(url_for('operations_web_bp.farm_livestock'))

        # Delete Health Record (no reversal)
        elif action == 'delete_health_record':
            record_id = request.form.get('health_record_id')
            record = FarmHealthRecord.query.get_or_404(record_id)
            db.session.delete(record)
            db.session.commit()
            flash('Health record deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_livestock'))

    # GET - display page
    livestock_list = FarmLivestock.query.order_by(FarmLivestock.name).all()
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()

    # Summary stats
    total_livestock = sum(l.quantity for l in livestock_list) if livestock_list else 0
    total_purchase_cost = sum(l.purchase_cost for l in livestock_list if l.purchase_cost) if livestock_list else 0
    health_records = FarmHealthRecord.query.all()
    health_records_count = len(health_records)
    total_health_cost = sum(r.cost for r in health_records) if health_records else 0

    return render_template(
        'operations/farm/livestock.html',
        livestock_list=livestock_list,
        total_livestock=total_livestock,
        total_purchase_cost=total_purchase_cost,
        health_records_count=health_records_count,
        total_health_cost=total_health_cost,
        petty_cash_accounts=petty_cash_accounts
    )


@operations_web_bp.route('/farm/livestock/health/<int:livestock_id>')
@login_required
def get_livestock_health(livestock_id):
    livestock = FarmLivestock.query.get_or_404(livestock_id)
    records = []
    for r in livestock.health_records.order_by(FarmHealthRecord.date.desc()).all():
        records.append({
            'id': r.id,
            'date': r.date.strftime('%Y-%m-%d'),
            'type': r.type or '—',
            'description': r.description,
            'cost': r.cost,
            'performed_by': r.performed_by or '—',
            'notes': r.notes or '—'
        })
    return jsonify({'health_records': records})





@operations_web_bp.route('/farm/crops', methods=['GET', 'POST'])
@login_required
def farm_crops():
    if request.method == 'POST':
        action = request.form.get('action')

        # --- Add Crop ---
        if action == 'add_crop':
            name = request.form.get('name')
            variety = request.form.get('variety')
            planting_date = request.form.get('planting_date')
            expected_harvest_date = request.form.get('expected_harvest_date')
            area = request.form.get('area')
            quantity_planted = request.form.get('quantity_planted')
            notes = request.form.get('notes')

            if not name:
                flash('Crop name is required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_crops'))

            crop = FarmCrop(
                name=name,
                variety=variety,
                planting_date=datetime.strptime(planting_date, '%Y-%m-%d') if planting_date else None,
                expected_harvest_date=datetime.strptime(expected_harvest_date, '%Y-%m-%d') if expected_harvest_date else None,
                area=float(area) if area else None,
                quantity_planted=float(quantity_planted) if quantity_planted else None,
                notes=notes
            )
            db.session.add(crop)
            db.session.commit()
            flash(f'Crop "{name}" added successfully.', 'success')
            return redirect(url_for('operations_web_bp.farm_crops'))

        # --- Edit Crop ---
        elif action == 'edit_crop':
            crop_id = request.form.get('crop_id')
            crop = FarmCrop.query.get_or_404(crop_id)
            crop.name = request.form.get('name')
            crop.variety = request.form.get('variety')
            planting_date = request.form.get('planting_date')
            crop.planting_date = datetime.strptime(planting_date, '%Y-%m-%d') if planting_date else None
            expected_harvest_date = request.form.get('expected_harvest_date')
            crop.expected_harvest_date = datetime.strptime(expected_harvest_date, '%Y-%m-%d') if expected_harvest_date else None
            crop.area = float(request.form.get('area')) if request.form.get('area') else None
            crop.quantity_planted = float(request.form.get('quantity_planted')) if request.form.get('quantity_planted') else None
            crop.notes = request.form.get('notes')
            db.session.commit()
            flash(f'Crop "{crop.name}" updated successfully.', 'success')
            return redirect(url_for('operations_web_bp.farm_crops'))

        # --- Delete Crop ---
        elif action == 'delete_crop':
            crop_id = request.form.get('crop_id')
            crop = FarmCrop.query.get_or_404(crop_id)
            name = crop.name
            db.session.delete(crop)
            db.session.commit()
            flash(f'Crop "{name}" deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_crops'))

        # --- Add Harvest ---
        elif action == 'add_harvest':
            crop_id = request.form.get('crop_id')
            harvest_date = request.form.get('harvest_date')
            quantity = request.form.get('quantity')
            unit = request.form.get('unit')
            notes = request.form.get('notes')
            inventory_entry_id = request.form.get('inventory_entry_id')

            if not crop_id or not harvest_date or not quantity:
                flash('Crop, harvest date, and quantity are required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_crops'))

            harvest = FarmHarvest(
                crop_id=crop_id,
                harvest_date=datetime.strptime(harvest_date, '%Y-%m-%d'),
                quantity=float(quantity),
                unit=unit or 'kg',
                notes=notes,
                inventory_entry_id=inventory_entry_id if inventory_entry_id else None
            )
            db.session.add(harvest)

            # Update inventory if linked
            if inventory_entry_id:
                inventory = FarmInventory.query.get(inventory_entry_id)
                if inventory:
                    inventory.quantity += float(quantity)
                else:
                    flash('Selected inventory item not found.', 'warning')

            db.session.commit()
            flash('Harvest record added.', 'success')
            return redirect(url_for('operations_web_bp.farm_crops'))

        # --- Delete Harvest ---
        elif action == 'delete_harvest':
            harvest_id = request.form.get('harvest_id')
            harvest = FarmHarvest.query.get_or_404(harvest_id)
            db.session.delete(harvest)
            db.session.commit()
            flash('Harvest record deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_crops'))

    # --- GET: Display page ---
    crops = FarmCrop.query.order_by(FarmCrop.planting_date.desc()).all()
    # Get harvest‑type inventory items for the harvest modal
    inventory_items = FarmInventory.query.filter_by(type='harvest').order_by(FarmInventory.name).all()

    # Summary stats
    total_crops = len(crops)
    total_area = sum(c.area for c in crops if c.area) or 0
    total_harvest_quantity = db.session.query(db.func.sum(FarmHarvest.quantity)).scalar() or 0
    total_harvest_value = db.session.query(
        db.func.sum(FarmHarvest.quantity * FarmInventory.price_per_unit)
    ).join(FarmInventory, FarmHarvest.inventory_entry_id == FarmInventory.id).scalar() or 0

    return render_template(
        'operations/farm/crops.html',
        crops=crops,
        inventory_items=inventory_items,
        total_crops=total_crops,
        total_area=total_area,
        total_harvest_quantity=total_harvest_quantity,
        total_harvest_value=total_harvest_value
    )
    
    
@operations_web_bp.route('/farm/crops/harvests/<int:crop_id>')
@login_required
def get_crop_harvests(crop_id):
    crop = FarmCrop.query.get_or_404(crop_id)
    harvests = []
    for h in crop.harvests.order_by(FarmHarvest.harvest_date.desc()).all():
        # Manually fetch the inventory item if an ID exists
        inventory_name = None
        if h.inventory_entry_id:
            inventory = FarmInventory.query.get(h.inventory_entry_id)
            inventory_name = inventory.name if inventory else 'Deleted Item'

        harvests.append({
            'id': h.id,
            'date': h.harvest_date.strftime('%Y-%m-%d'),
            'quantity': h.quantity,
            'unit': h.unit,
            'notes': h.notes,
            'inventory_item': inventory_name
        })
    return {'harvests': harvests}



@operations_web_bp.route('/farm/harvest', methods=['GET', 'POST'])
@login_required
def farm_harvest():
    if request.method == 'POST':
        action = request.form.get('action')

        # Add Harvest
        if action == 'add_harvest':
            crop_id = request.form.get('crop_id')
            harvest_date = request.form.get('harvest_date')
            quantity = request.form.get('quantity')
            unit = request.form.get('unit')
            notes = request.form.get('notes')
            inventory_entry_id = request.form.get('inventory_entry_id')

            if not crop_id or not harvest_date or not quantity:
                flash('Crop, harvest date, and quantity are required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_harvest'))

            harvest = FarmHarvest(
                crop_id=crop_id,
                harvest_date=datetime.strptime(harvest_date, '%Y-%m-%d'),
                quantity=float(quantity),
                unit=unit or 'kg',
                notes=notes,
                inventory_entry_id=inventory_entry_id if inventory_entry_id else None
            )
            db.session.add(harvest)

            # Update inventory if linked
            if inventory_entry_id:
                inventory = FarmInventory.query.get(inventory_entry_id)
                if inventory:
                    inventory.quantity += float(quantity)
                else:
                    flash('Selected inventory item not found.', 'warning')

            db.session.commit()
            flash('Harvest record added.', 'success')
            return redirect(url_for('operations_web_bp.farm_harvest'))

        # Edit Harvest
        elif action == 'edit_harvest':
            harvest_id = request.form.get('harvest_id')
            harvest = FarmHarvest.query.get_or_404(harvest_id)
            old_quantity = harvest.quantity
            old_inventory_id = harvest.inventory_entry_id

            new_crop_id = request.form.get('crop_id')
            new_harvest_date = request.form.get('harvest_date')
            new_quantity = float(request.form.get('quantity', 0))
            new_unit = request.form.get('unit')
            new_notes = request.form.get('notes')
            new_inventory_id = request.form.get('inventory_entry_id')

            # Update harvest fields
            harvest.crop_id = new_crop_id
            harvest.harvest_date = datetime.strptime(new_harvest_date, '%Y-%m-%d')
            harvest.quantity = new_quantity
            harvest.unit = new_unit or 'kg'
            harvest.notes = new_notes
            harvest.inventory_entry_id = new_inventory_id if new_inventory_id else None

            # Adjust inventory if changed
            # If previously linked to an inventory item, revert the old quantity
            if old_inventory_id:
                old_inv = FarmInventory.query.get(old_inventory_id)
                if old_inv:
                    old_inv.quantity -= old_quantity
            # If now linked to a new inventory item, add the new quantity
            if new_inventory_id:
                new_inv = FarmInventory.query.get(new_inventory_id)
                if new_inv:
                    new_inv.quantity += new_quantity

            db.session.commit()
            flash('Harvest record updated.', 'success')
            return redirect(url_for('operations_web_bp.farm_harvest'))

        # Delete Harvest
        elif action == 'delete_harvest':
            harvest_id = request.form.get('harvest_id')
            harvest = FarmHarvest.query.get_or_404(harvest_id)

            # Revert inventory quantity if linked
            if harvest.inventory_entry_id:
                inventory = FarmInventory.query.get(harvest.inventory_entry_id)
                if inventory:
                    inventory.quantity -= harvest.quantity

            db.session.delete(harvest)
            db.session.commit()
            flash('Harvest record deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_harvest'))

    # GET: display page with filters
    crop_filter = request.args.get('crop', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = FarmHarvest.query.join(FarmCrop).order_by(FarmHarvest.harvest_date.desc())
    if crop_filter:
        query = query.filter(FarmHarvest.crop_id == crop_filter)
    if start_date:
        query = query.filter(FarmHarvest.harvest_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FarmHarvest.harvest_date <= datetime.strptime(end_date, '%Y-%m-%d'))

    harvests = query.all()
    crops = FarmCrop.query.order_by(FarmCrop.name).all()
    # Harvest‑type inventory items for linking
    harvest_inventory = FarmInventory.query.filter_by(type='harvest').order_by(FarmInventory.name).all()

    # Summary stats
    total_harvests = len(harvests)
    total_quantity = sum(h.quantity for h in harvests) if harvests else 0
    # Total value: sum of quantity * price_per_unit (if linked inventory has price)
    total_value = 0
    for h in harvests:
        if h.inventory_entry_id and h.inventory_entry:
            total_value += h.quantity * h.inventory_entry.price_per_unit
    recent_count = sum(1 for h in harvests if (datetime.utcnow() - h.harvest_date).days <= 30)

    return render_template(
        'operations/farm/harvest.html',
        harvests=harvests,
        crops=crops,
        harvest_inventory=harvest_inventory,
        total_harvests=total_harvests,
        total_quantity=total_quantity,
        total_value=total_value,
        recent_count=recent_count,
        crop_filter=crop_filter,
        start_date=start_date,
        end_date=end_date
    )


@operations_web_bp.route('/farm/inputs', methods=['GET', 'POST'])
@login_required
def farm_inputs():
    if request.method == 'POST':
        action = request.form.get('action')

        # Add Input (with petty cash)
        if action == 'add_input':
            name = request.form.get('name')
            quantity = float(request.form.get('quantity', 0))
            unit = request.form.get('unit', 'pcs')
            reorder_level = float(request.form.get('reorder_level', 10))
            category = request.form.get('category')
            location = request.form.get('location')
            notes = request.form.get('notes')
            price_per_unit = float(request.form.get('price_per_unit', 0))
            petty_cash_account_id = request.form.get('petty_cash_account_id')
            transaction_reference = request.form.get('transaction_reference', '').strip()

            if not name:
                flash('Item name is required.', 'danger')
                return redirect(url_for('operations_web_bp.farm_inputs'))

            # Check if item already exists
            existing = FarmInventory.query.filter_by(name=name, type='input').first()
            if existing:
                flash(f'Item "{name}" already exists.', 'danger')
                return redirect(url_for('operations_web_bp.farm_inputs'))

            if price_per_unit * quantity > 0 and not petty_cash_account_id:
                flash('Please select a petty cash account for the payment.', 'danger')
                return redirect(url_for('operations_web_bp.farm_inputs'))

            # Create input item
            item = FarmInventory(
                name=name,
                quantity=quantity,
                unit=unit,
                reorder_level=reorder_level,
                category=category,
                location=location,
                notes=notes,
                type='input',
                price_per_unit=price_per_unit
            )
            db.session.add(item)
            db.session.flush()  # get item.id

            # If cost > 0, deduct from petty cash
            total_cost = price_per_unit * quantity
            if total_cost > 0:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if not petty_cash or not petty_cash.is_active:
                    flash('Invalid petty cash account.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_inputs'))

                if petty_cash.current_balance < total_cost:
                    flash(f'Insufficient balance in {petty_cash.name}. Available: {petty_cash.current_balance:.2f}', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.farm_inputs'))

                # Create petty cash transaction
                petty_tx = PettyCashTransaction(
                    transaction_type='withdrawal',
                    amount=total_cost,
                    description=f"Farm input purchase: {name} (Qty: {quantity})",
                    source_petty_cash_account_id=petty_cash.id,
                    status='completed',
                    completed_at=datetime.utcnow(),
                    initiated_by=current_user.id,
                    transaction_ref=transaction_reference,
                    external_reference=f"INPUT-{item.id}"
                )
                db.session.add(petty_tx)
                db.session.flush()
                if not petty_tx.transaction_ref:
                    petty_tx.transaction_ref = petty_tx.generate_ref()

                petty_cash.current_balance -= total_cost
                db.session.add(petty_cash)

            db.session.commit()
            flash(f'Input "{name}" added successfully.', 'success')
            return redirect(url_for('operations_web_bp.farm_inputs'))

        # Edit Input (no petty cash)
        elif action == 'edit_input':
            item_id = request.form.get('item_id')
            item = FarmInventory.query.get_or_404(item_id)
            item.name = request.form.get('name')
            item.quantity = float(request.form.get('quantity', 0))
            item.unit = request.form.get('unit', 'pcs')
            item.reorder_level = float(request.form.get('reorder_level', 10))
            item.category = request.form.get('category')
            item.location = request.form.get('location')
            item.notes = request.form.get('notes')
            item.price_per_unit = float(request.form.get('price_per_unit', 0))
            db.session.commit()
            flash(f'Input "{item.name}" updated.', 'success')
            return redirect(url_for('operations_web_bp.farm_inputs'))

        # Adjust Stock
        elif action == 'adjust_stock_input':
            item_id = request.form.get('item_id')
            adjustment = float(request.form.get('adjustment', 0))
            notes = request.form.get('notes', '')
            item = FarmInventory.query.get_or_404(item_id)
            old_qty = item.quantity
            item.quantity += adjustment
            if item.quantity < 0:
                item.quantity = 0
            db.session.commit()
            flash(f'Stock for "{item.name}" adjusted by {adjustment:+.2f}. New quantity: {item.quantity:.2f}.', 'success')
            return redirect(url_for('operations_web_bp.farm_inputs'))

        # Delete Input (with checks)
        elif action == 'delete_input':
            item_id = request.form.get('item_id')
            item = FarmInventory.query.get_or_404(item_id)
            # Check for dependencies
            harvests = FarmHarvest.query.filter_by(inventory_entry_id=item_id).first()
            revenues = FarmRevenue.query.filter_by(inventory_item_id=item_id).first()
            if harvests or revenues:
                flash(f'Cannot delete "{item.name}" because it is linked to harvest or revenue records.', 'danger')
                return redirect(url_for('operations_web_bp.farm_inputs'))

            db.session.delete(item)
            db.session.commit()
            flash('Input deleted.', 'info')
            return redirect(url_for('operations_web_bp.farm_inputs'))

    # GET: fetch inputs with filters
    search = request.args.get('search', '')
    category_filter = request.args.get('category')
    location_filter = request.args.get('location')

    query = FarmInventory.query.filter_by(type='input')
    if search:
        query = query.filter(FarmInventory.name.ilike(f'%{search}%'))
    if category_filter:
        query = query.filter(FarmInventory.category == category_filter)
    if location_filter:
        query = query.filter(FarmInventory.location == location_filter)

    inputs = query.order_by(FarmInventory.name).all()

    # Summary stats
    total_inputs = len(inputs)
    total_quantity = sum(i.quantity for i in inputs)
    low_stock_count = sum(1 for i in inputs if i.quantity <= i.reorder_level)
    total_value = sum(i.quantity * i.price_per_unit for i in inputs)

    # Unique filter options
    categories = sorted(set(i.category for i in inputs if i.category))
    locations = sorted(set(i.location for i in inputs if i.location))

    # Petty cash accounts for the modal
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()

    return render_template(
        'operations/farm/inputs.html',
        inputs=inputs,
        total_inputs=total_inputs,
        total_quantity=total_quantity,
        low_stock_count=low_stock_count,
        total_value=total_value,
        categories=categories,
        locations=locations,
        petty_cash_accounts=petty_cash_accounts,
        search=search,
        category_filter=category_filter,
        location_filter=location_filter
    )


# ----------------------------------------------------------------------
# Fleet Management
# ----------------------------------------------------------------------

@operations_web_bp.route('/fleet/inventory')
@login_required
def fleet_inventory():
    """Manage fleet inventory (spare parts, consumables)."""
    items = FleetInventory.query.order_by(FleetInventory.name).all()
    total_items = len(items)
    total_quantity = sum(i.quantity for i in items)
    low_stock = [i for i in items if i.quantity <= i.reorder_level]
    return render_template('operations/fleet/inventory.html',
                           items=items,
                           total_items=total_items,
                           total_quantity=total_quantity,
                           low_stock_count=len(low_stock),
                           low_stock_items=low_stock)
    
    
    
@operations_web_bp.route('/fleet/vehicles', methods=['GET', 'POST'])
@login_required
def fleet_vehicles():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            reg = request.form.get('registration')
            make = request.form.get('make')
            model = request.form.get('model')
            year = int(request.form.get('year'))
            capacity = request.form.get('capacity')
            status = request.form.get('status', 'active')
            insurance_expiry = request.form.get('insurance_expiry')
            last_service = request.form.get('last_service_date')
            next_service_km = request.form.get('next_service_km', type=int)
            current_odometer = request.form.get('current_odometer', type=int, default=0)
            fuel_type = request.form.get('fuel_type')
            notes = request.form.get('notes')

            if not reg or not make or not model or not year:
                flash('Registration, make, model, and year are required.', 'danger')
                return redirect(url_for('operations_web_bp.fleet_vehicles'))

            # Check if registration already exists
            if FleetVehicle.query.filter_by(registration=reg).first():
                flash(f'Vehicle with registration {reg} already exists.', 'danger')
                return redirect(url_for('operations_web_bp.fleet_vehicles'))

            vehicle = FleetVehicle(
                registration=reg,
                make=make,
                model=model,
                year=year,
                capacity=capacity,
                status=status,
                insurance_expiry=datetime.strptime(insurance_expiry, '%Y-%m-%d').date() if insurance_expiry else None,
                last_service_date=datetime.strptime(last_service, '%Y-%m-%d').date() if last_service else None,
                next_service_km=next_service_km,
                current_odometer=current_odometer,
                fuel_type=fuel_type,
                notes=notes
            )
            db.session.add(vehicle)
            db.session.commit()
            flash(f'Vehicle {reg} added.', 'success')
            return redirect(url_for('operations_web_bp.fleet_vehicles'))

        elif action == 'edit':
            vehicle_id = request.form.get('vehicle_id')
            vehicle = FleetVehicle.query.get_or_404(vehicle_id)
            vehicle.registration = request.form.get('registration')
            vehicle.make = request.form.get('make')
            vehicle.model = request.form.get('model')
            vehicle.year = int(request.form.get('year'))
            vehicle.capacity = request.form.get('capacity')
            vehicle.status = request.form.get('status')
            insurance_expiry = request.form.get('insurance_expiry')
            vehicle.insurance_expiry = datetime.strptime(insurance_expiry, '%Y-%m-%d').date() if insurance_expiry else None
            last_service = request.form.get('last_service_date')
            vehicle.last_service_date = datetime.strptime(last_service, '%Y-%m-%d').date() if last_service else None
            vehicle.next_service_km = request.form.get('next_service_km', type=int)
            vehicle.current_odometer = request.form.get('current_odometer', type=int)
            vehicle.fuel_type = request.form.get('fuel_type')
            vehicle.notes = request.form.get('notes')
            db.session.commit()
            flash(f'Vehicle {vehicle.registration} updated.', 'success')
            return redirect(url_for('operations_web_bp.fleet_vehicles'))

        elif action == 'delete':
            vehicle_id = request.form.get('vehicle_id')
            vehicle = FleetVehicle.query.get_or_404(vehicle_id)
            db.session.delete(vehicle)
            db.session.commit()
            flash(f'Vehicle {vehicle.registration} deleted.', 'info')
            return redirect(url_for('operations_web_bp.fleet_vehicles'))

    # GET
    vehicles = FleetVehicle.query.order_by(FleetVehicle.registration).all()
    total_vehicles = len(vehicles)
    active_vehicles = sum(1 for v in vehicles if v.status == 'active')
    maintenance_vehicles = sum(1 for v in vehicles if v.status == 'maintenance')
    retired_vehicles = sum(1 for v in vehicles if v.status == 'retired')
    return render_template(
        'operations/fleet/vehicles.html',
        vehicles=vehicles,
        total_vehicles=total_vehicles,
        active_vehicles=active_vehicles,
        maintenance_vehicles=maintenance_vehicles,
        retired_vehicles=retired_vehicles
    )




@operations_web_bp.route('/fleet/maintenance', methods=['GET', 'POST'])
@login_required
def fleet_maintenance():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            vehicle_id = request.form.get('vehicle_id')
            maintenance_date_str = request.form.get('maintenance_date')
            type_ = request.form.get('type')
            description = request.form.get('description')
            cost = float(request.form.get('cost', 0))
            performed_by = request.form.get('performed_by')
            odometer = int(request.form.get('odometer')) if request.form.get('odometer') else None
            notes = request.form.get('notes')
            petty_cash_account_id = request.form.get('petty_cash_account_id')
            transaction_reference = request.form.get('transaction_reference', '').strip()

            if not all([vehicle_id, maintenance_date_str, type_, description]):
                flash('Vehicle, date, type, and description are required.', 'danger')
                return redirect(url_for('operations_web_bp.fleet_maintenance'))

            if cost > 0 and not petty_cash_account_id:
                flash('Please select a petty cash account for the payment.', 'danger')
                return redirect(url_for('operations_web_bp.fleet_maintenance'))

            # Create maintenance record
            maintenance = FleetMaintenance(
                vehicle_id=vehicle_id,
                maintenance_date=datetime.strptime(maintenance_date_str, '%Y-%m-%d'),
                type=type_,
                description=description,
                cost=cost,
                performed_by=performed_by,
                odometer=odometer,
                notes=notes
            )
            db.session.add(maintenance)

            # If cost > 0, deduct from petty cash
            if cost > 0:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if not petty_cash or not petty_cash.is_active:
                    flash('Invalid petty cash account.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.fleet_maintenance'))

                if petty_cash.current_balance < cost:
                    flash(f'Insufficient balance in {petty_cash.name}. Available: {petty_cash.current_balance:.2f}', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.fleet_maintenance'))

                # Create petty cash transaction (withdrawal)
                petty_tx = PettyCashTransaction(
                    transaction_type='withdrawal',
                    amount=cost,
                    description=f"Fleet maintenance: {description} (Vehicle: {vehicle_id})",
                    source_petty_cash_account_id=petty_cash.id,
                    status='completed',
                    completed_at=datetime.utcnow(),
                    initiated_by=current_user.id,
                    transaction_ref=transaction_reference,  # will set after flush
                    external_reference=f"MAINT-{maintenance.id}"  # fallback
                )
                # We'll set reference after we have maintenance.id
                db.session.add(petty_tx)
                db.session.flush()  # to get IDs

                # Set reference using actual maintenance ID
                petty_tx.external_reference = f"MAINT-{maintenance.id}"
                petty_tx.transaction_ref = petty_tx.generate_ref()

                # Reduce petty cash balance
                petty_cash.current_balance -= cost
                db.session.add(petty_cash)

            db.session.commit()
            flash('Maintenance record added.', 'success')
            return redirect(url_for('operations_web_bp.fleet_maintenance'))

        elif action == 'edit':
            record_id = request.form.get('record_id')
            record = FleetMaintenance.query.get_or_404(record_id)
            record.vehicle_id = request.form.get('vehicle_id')
            record.maintenance_date = datetime.strptime(request.form.get('maintenance_date'), '%Y-%m-%d')
            record.type = request.form.get('type')
            record.description = request.form.get('description')
            record.cost = float(request.form.get('cost', 0))
            record.performed_by = request.form.get('performed_by')
            record.odometer = int(request.form.get('odometer')) if request.form.get('odometer') else None
            record.notes = request.form.get('notes')
            # Note: We don't adjust petty cash on edit (payment already made)
            db.session.commit()
            flash('Maintenance record updated.', 'success')
            return redirect(url_for('operations_web_bp.fleet_maintenance'))

        elif action == 'delete':
            record_id = request.form.get('record_id')
            record = FleetMaintenance.query.get_or_404(record_id)
            # Optionally reverse petty cash deduction (if cost > 0)
            # For simplicity, we skip reversal; user can manually adjust petty cash.
            db.session.delete(record)
            db.session.commit()
            flash('Maintenance record deleted.', 'info')
            return redirect(url_for('operations_web_bp.fleet_maintenance'))

    # GET – fetch data
    vehicle_filter = request.args.get('vehicle', type=int)
    type_filter = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = FleetMaintenance.query
    if vehicle_filter:
        query = query.filter(FleetMaintenance.vehicle_id == vehicle_filter)
    if type_filter:
        query = query.filter(FleetMaintenance.type == type_filter)
    if start_date:
        query = query.filter(FleetMaintenance.maintenance_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FleetMaintenance.maintenance_date <= datetime.strptime(end_date, '%Y-%m-%d'))

    records = query.order_by(FleetMaintenance.maintenance_date.desc()).all()
    vehicles = FleetVehicle.query.filter_by(is_active=True).order_by(FleetVehicle.registration).all()
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).order_by(PettyCash.name).all()

    total_records = len(records)
    total_cost = sum(r.cost for r in records) if records else 0
    recent_count = sum(1 for r in records if (datetime.utcnow() - r.maintenance_date).days <= 30)

    return render_template(
        'operations/fleet/maintenance.html',
        records=records,
        vehicles=vehicles,
        petty_cash_accounts=petty_cash_accounts,
        total_records=total_records,
        total_cost=total_cost,
        recent_count=recent_count,
        vehicle_filter=vehicle_filter,
        type_filter=type_filter,
        start_date=start_date,
        end_date=end_date
    )



@operations_web_bp.route('/fleet/fuel', methods=['GET', 'POST'])
@login_required
def fleet_fuel():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            vehicle_id = request.form.get('vehicle_id')
            date_str = request.form.get('date')
            liters = float(request.form.get('liters', 0))
            cost = float(request.form.get('cost', 0))
            odometer = int(request.form.get('odometer', 0))
            location = request.form.get('location')
            notes = request.form.get('notes')
            transaction_ref = request.form.get('transaction_reference')
            petty_cash_account_id = request.form.get('petty_cash_account_id')

            if not all([vehicle_id, date_str, liters, cost, odometer]):
                flash('Vehicle, date, liters, cost, and odometer are required.', 'danger')
                return redirect(url_for('operations_web_bp.fleet_fuel'))

            # Create fuel record
            fuel = FleetFuel(
                vehicle_id=vehicle_id,
                date=datetime.strptime(date_str, '%Y-%m-%d'),
                liters=liters,
                cost=cost,
                odometer=odometer,
                location=location,
                notes=notes,
                transaction_reference=transaction_ref,
                petty_cash_account_id=petty_cash_account_id
            )
            db.session.add(fuel)

            # Deduct from petty cash if cost > 0 and petty cash account selected
            if cost > 0 and petty_cash_account_id:
                petty_cash = PettyCash.query.get(petty_cash_account_id)
                if petty_cash and petty_cash.current_balance >= cost:
                    # Create petty cash transaction
                    petty_tx = PettyCashTransaction(
                        transaction_type='withdrawal',
                        amount=cost,
                        description=f"Fuel purchase: {liters}L for vehicle {vehicle_id}",
                        source_petty_cash_account_id=petty_cash.id,
                        status='completed',
                        completed_at=datetime.utcnow(),
                        initiated_by=current_user.id,
                        external_reference=transaction_ref
                    )
                    petty_tx.transaction_ref = petty_tx.generate_ref()
                    db.session.add(petty_tx)
                    # Reduce balance
                    petty_cash.current_balance -= cost
                elif petty_cash:
                    flash(f'Insufficient balance in petty cash account {petty_cash.name}.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('operations_web_bp.fleet_fuel'))

            db.session.commit()
            flash('Fuel record added.', 'success')
            return redirect(url_for('operations_web_bp.fleet_fuel'))

        elif action == 'edit':
            record_id = request.form.get('record_id')
            record = FleetFuel.query.get_or_404(record_id)
            old_cost = record.cost
            record.vehicle_id = request.form.get('vehicle_id')
            record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
            record.liters = float(request.form.get('liters', 0))
            record.cost = float(request.form.get('cost', 0))
            record.odometer = int(request.form.get('odometer', 0))
            record.location = request.form.get('location')
            record.notes = request.form.get('notes')
            record.transaction_reference = request.form.get('transaction_reference')
            record.petty_cash_account_id = request.form.get('petty_cash_account_id')
            # Adjust petty cash if cost changed (simplified: not handling adjustment for now)
            db.session.commit()
            flash('Fuel record updated.', 'success')
            return redirect(url_for('operations_web_bp.fleet_fuel'))

        elif action == 'delete':
            record_id = request.form.get('record_id')
            record = FleetFuel.query.get_or_404(record_id)
            # Optionally refund petty cash if needed (skip for simplicity)
            db.session.delete(record)
            db.session.commit()
            flash('Fuel record deleted.', 'info')
            return redirect(url_for('operations_web_bp.fleet_fuel'))

    # GET
    vehicle_filter = request.args.get('vehicle', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = FleetFuel.query
    if vehicle_filter:
        query = query.filter(FleetFuel.vehicle_id == vehicle_filter)
    if start_date:
        query = query.filter(FleetFuel.date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FleetFuel.date <= datetime.strptime(end_date, '%Y-%m-%d'))

    records = query.order_by(FleetFuel.date.desc()).all()
    vehicles = FleetVehicle.query.filter_by(is_active=True).order_by(FleetVehicle.registration).all()
    petty_cash_accounts = PettyCash.query.filter_by(is_active=True).all()

    # Summary stats
    total_liters = sum(r.liters for r in records) if records else 0
    total_cost = sum(r.cost for r in records) if records else 0
    avg_price_per_liter = total_cost / total_liters if total_liters > 0 else 0

    # Fuel efficiency per vehicle (km/l)
    # Group by vehicle, sort by date, compute efficiency
    efficiency_by_vehicle = {}
    for r in records:
        if r.vehicle_id not in efficiency_by_vehicle:
            efficiency_by_vehicle[r.vehicle_id] = []
        efficiency_by_vehicle[r.vehicle_id].append(r)
    for vid, recs in efficiency_by_vehicle.items():
        recs.sort(key=lambda x: x.date)
        prev_odometer = None
        for r in recs:
            if prev_odometer is not None:
                distance = r.odometer - prev_odometer
                if distance > 0 and r.liters > 0:
                    r.efficiency = distance / r.liters
                else:
                    r.efficiency = None
            else:
                r.efficiency = None
            prev_odometer = r.odometer

    return render_template(
        'operations/fleet/fuel.html',
        records=records,
        vehicles=vehicles,
        total_liters=total_liters,
        total_cost=total_cost,
        avg_price_per_liter=avg_price_per_liter,
        vehicle_filter=vehicle_filter,
        start_date=start_date,
        end_date=end_date,
        petty_cash_accounts=petty_cash_accounts
    )


@operations_web_bp.route('/fleet/trips', methods=['GET', 'POST'])
@login_required
def fleet_trips():
    from datetime import datetime, timedelta

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            vehicle_id = request.form.get('vehicle_id')
            driver = request.form.get('driver')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            start_odometer = request.form.get('start_odometer')
            end_odometer = request.form.get('end_odometer')
            distance = request.form.get('distance', '')
            destination = request.form.get('destination')
            purpose = request.form.get('purpose')
            passengers = request.form.get('passengers', type=int)
            notes = request.form.get('notes')

            # Validation
            if not all([vehicle_id, driver, start_time_str, end_time_str]):
                flash('Vehicle, driver, start/end times are required.', 'danger')
                return redirect(url_for('operations_web_bp.fleet_trips'))

            start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')

            # Convert odometer strings to int if provided
            start_odometer = int(start_odometer) if start_odometer else None
            end_odometer = int(end_odometer) if end_odometer else None

            # Compute distance if odometer readings are both present
            if start_odometer is not None and end_odometer is not None:
                if end_odometer < start_odometer:
                    flash('End odometer cannot be less than start odometer.', 'danger')
                    return redirect(url_for('operations_web_bp.fleet_trips'))
                computed_distance = end_odometer - start_odometer
                if distance:
                    distance = int(distance)
                else:
                    distance = computed_distance
            elif distance:
                distance = int(distance)
            else:
                distance = None

            trip = FleetTrip(
                vehicle_id=vehicle_id,
                driver=driver,
                start_time=start_time,
                end_time=end_time,
                start_odometer=start_odometer,
                end_odometer=end_odometer,
                distance=distance,
                destination=destination,
                purpose=purpose,
                passengers=passengers,
                notes=notes
            )
            db.session.add(trip)
            db.session.commit()
            flash('Trip record added.', 'success')
            return redirect(url_for('operations_web_bp.fleet_trips'))

        elif action == 'edit':
            record_id = request.form.get('record_id')
            trip = FleetTrip.query.get_or_404(record_id)
            trip.vehicle_id = request.form.get('vehicle_id')
            trip.driver = request.form.get('driver')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            trip.start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
            trip.end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
            start_odometer = request.form.get('start_odometer')
            end_odometer = request.form.get('end_odometer')
            trip.start_odometer = int(start_odometer) if start_odometer else None
            trip.end_odometer = int(end_odometer) if end_odometer else None
            distance = request.form.get('distance', '')
            if distance:
                trip.distance = int(distance)
            elif trip.start_odometer is not None and trip.end_odometer is not None:
                trip.distance = trip.end_odometer - trip.start_odometer
            else:
                trip.distance = None
            trip.destination = request.form.get('destination')
            trip.purpose = request.form.get('purpose')
            trip.passengers = request.form.get('passengers', type=int)
            trip.notes = request.form.get('notes')
            db.session.commit()
            flash('Trip record updated.', 'success')
            return redirect(url_for('operations_web_bp.fleet_trips'))

        elif action == 'delete':
            record_id = request.form.get('record_id')
            trip = FleetTrip.query.get_or_404(record_id)
            db.session.delete(trip)
            db.session.commit()
            flash('Trip record deleted.', 'info')
            return redirect(url_for('operations_web_bp.fleet_trips'))

    # GET – fetch trips with filters
    vehicle_filter = request.args.get('vehicle', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = FleetTrip.query
    if vehicle_filter:
        query = query.filter(FleetTrip.vehicle_id == vehicle_filter)
    if start_date:
        query = query.filter(FleetTrip.start_time >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FleetTrip.start_time <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))

    trips = query.order_by(FleetTrip.start_time.desc()).all()
    vehicles = FleetVehicle.query.filter_by(is_active=True).order_by(FleetVehicle.registration).all()

    total_trips = len(trips)
    total_distance = sum(t.distance for t in trips if t.distance) if trips else 0
    avg_distance = total_distance / total_trips if total_trips > 0 else 0

    return render_template(
        'operations/fleet/trips.html',
        trips=trips,
        vehicles=vehicles,
        total_trips=total_trips,
        total_distance=total_distance,
        avg_distance=avg_distance,
        vehicle_filter=vehicle_filter,
        start_date=start_date,
        end_date=end_date
    )



from sqlalchemy import func, extract
from datetime import datetime, timedelta

@operations_web_bp.route('/fleet/reports')
@login_required
def fleet_reports():
    # Get filter parameters
    period = request.args.get('period', 'month')
    year = int(request.args.get('year', datetime.utcnow().year))
    month = int(request.args.get('month', datetime.utcnow().month))
    vehicle_id = request.args.get('vehicle_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Determine date range
    if period == 'custom' and start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    elif period == 'year':
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    else:  # month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month+1, 1) - timedelta(seconds=1)

    # Month names for dropdown
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    # Base filters
    vehicle_filter = None
    if vehicle_id:
        vehicle_filter = FleetVehicle.query.get(vehicle_id)

    # Vehicles summary
    vehicles = FleetVehicle.query.filter_by(is_active=True).all()
    total_vehicles = len(vehicles)
    active_vehicles = sum(1 for v in vehicles if v.status == 'active')
    under_maintenance = sum(1 for v in vehicles if v.status == 'maintenance')

    # Maintenance costs
    maint_query = FleetMaintenance.query.filter(
        FleetMaintenance.maintenance_date >= start_date,
        FleetMaintenance.maintenance_date <= end_date
    )
    if vehicle_id:
        maint_query = maint_query.filter(FleetMaintenance.vehicle_id == vehicle_id)
    maintenance_total = maint_query.with_entities(func.sum(FleetMaintenance.cost)).scalar() or 0
    maintenance_by_type = maint_query.with_entities(
        FleetMaintenance.type,
        func.sum(FleetMaintenance.cost).label('total')
    ).group_by(FleetMaintenance.type).all()
    maintenance_by_vehicle = maint_query.with_entities(
        FleetVehicle.registration,
        func.sum(FleetMaintenance.cost).label('total')
    ).join(FleetMaintenance.vehicle).group_by(FleetVehicle.id).order_by(func.sum(FleetMaintenance.cost).desc()).limit(10).all()

    # Fuel consumption
    fuel_query = FleetFuel.query.filter(
        FleetFuel.date >= start_date,
        FleetFuel.date <= end_date
    )
    if vehicle_id:
        fuel_query = fuel_query.filter(FleetFuel.vehicle_id == vehicle_id)
    total_liters = fuel_query.with_entities(func.sum(FleetFuel.liters)).scalar() or 0
    total_fuel_cost = fuel_query.with_entities(func.sum(FleetFuel.cost)).scalar() or 0
    avg_price_per_liter = total_fuel_cost / total_liters if total_liters > 0 else 0
    fuel_by_vehicle = fuel_query.with_entities(
        FleetVehicle.registration,
        func.sum(FleetFuel.liters).label('liters'),
        func.sum(FleetFuel.cost).label('cost')
    ).join(FleetFuel.vehicle).group_by(FleetVehicle.id).order_by(func.sum(FleetFuel.liters).desc()).limit(10).all()

    # Trips
    trip_query = FleetTrip.query.filter(
        FleetTrip.start_time >= start_date,
        FleetTrip.start_time <= end_date
    )
    if vehicle_id:
        trip_query = trip_query.filter(FleetTrip.vehicle_id == vehicle_id)
    total_trips = trip_query.count()
    total_distance = trip_query.with_entities(func.sum(FleetTrip.distance)).scalar() or 0
    avg_distance_per_trip = total_distance / total_trips if total_trips > 0 else 0
    trips_by_vehicle = trip_query.with_entities(
        FleetVehicle.registration,
        func.count(FleetTrip.id).label('trip_count'),
        func.sum(FleetTrip.distance).label('total_distance')
    ).join(FleetTrip.vehicle).group_by(FleetVehicle.id).order_by(func.sum(FleetTrip.distance).desc()).limit(10).all()

    # Monthly trends (last 12 months)
    months = []
    maintenance_trend = []
    fuel_trend = []
    trips_trend = []
    for i in range(11, -1, -1):
        month_start = datetime.utcnow().replace(day=1) - timedelta(days=30*i)
        month_start = month_start.replace(day=1)
        if month_start.month == 12:
            month_end = datetime(month_start.year+1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(month_start.year, month_start.month+1, 1) - timedelta(seconds=1)

        # Maintenance cost
        maint_cost = FleetMaintenance.query.filter(
            FleetMaintenance.maintenance_date >= month_start,
            FleetMaintenance.maintenance_date <= month_end
        )
        if vehicle_id:
            maint_cost = maint_cost.filter(FleetMaintenance.vehicle_id == vehicle_id)
        maint_cost = maint_cost.with_entities(func.sum(FleetMaintenance.cost)).scalar() or 0

        # Fuel cost
        fuel_cost = FleetFuel.query.filter(
            FleetFuel.date >= month_start,
            FleetFuel.date <= month_end
        )
        if vehicle_id:
            fuel_cost = fuel_cost.filter(FleetFuel.vehicle_id == vehicle_id)
        fuel_cost = fuel_cost.with_entities(func.sum(FleetFuel.cost)).scalar() or 0

        # Trip count
        trip_count = FleetTrip.query.filter(
            FleetTrip.start_time >= month_start,
            FleetTrip.start_time <= month_end
        )
        if vehicle_id:
            trip_count = trip_count.filter(FleetTrip.vehicle_id == vehicle_id)
        trip_count = trip_count.count()

        months.append(month_start.strftime('%b %Y'))
        maintenance_trend.append(maint_cost)
        fuel_trend.append(fuel_cost)
        trips_trend.append(trip_count)

    return render_template(
        'operations/fleet/reports.html',
        # Vehicle summary
        total_vehicles=total_vehicles,
        active_vehicles=active_vehicles,
        under_maintenance=under_maintenance,
        # Maintenance
        maintenance_total=maintenance_total,
        maintenance_by_type=maintenance_by_type,
        maintenance_by_vehicle=maintenance_by_vehicle,
        # Fuel
        total_liters=total_liters,
        total_fuel_cost=total_fuel_cost,
        avg_price_per_liter=avg_price_per_liter,
        fuel_by_vehicle=fuel_by_vehicle,
        # Trips
        total_trips=total_trips,
        total_distance=total_distance,
        avg_distance_per_trip=avg_distance_per_trip,
        trips_by_vehicle=trips_by_vehicle,
        # Trends
        months=months,
        maintenance_trend=maintenance_trend,
        fuel_trend=fuel_trend,
        trips_trend=trips_trend,
        # Filters
        period=period,
        year=year,
        month=month,
        vehicle_id=vehicle_id,
        vehicles=vehicles,
        start_date=start_date.strftime('%Y-%m-%d') if start_date else '',
        end_date=end_date.strftime('%Y-%m-%d') if end_date else '',
        month_names=month_names
    )


# ----------------------------------------------------------------------
# Operations Reports
# ----------------------------------------------------------------------



@operations_web_bp.route('/reports/supplier')
@login_required
def supplier_reports():
    return render_template('operations/reports/supplier.html')

@operations_web_bp.route('/reports/account')
@login_required
def account_reports():
    return render_template('operations/reports/account.html')

@operations_web_bp.route('/reports/farm', methods=['GET', 'POST'])
@login_required
def farm_reports():
    # Date range filters
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    else:
        start_date = datetime(2020, 1, 1)  # default far past
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        end_date = datetime.utcnow()

    # ---------- Inventory Summary ----------
    # Inputs (type='input')
    inputs = FarmInventory.query.filter_by(type='input').all()
    total_input_qty = sum(i.quantity for i in inputs)
    total_input_value = sum(i.quantity * i.price_per_unit for i in inputs)
    low_stock_inputs = [i for i in inputs if i.quantity <= i.reorder_level]
    low_stock_count = len(low_stock_inputs)

    # Harvest items (type='harvest')
    harvest_items = FarmInventory.query.filter_by(type='harvest').all()
    total_harvest_qty = sum(h.quantity for h in harvest_items)
    total_harvest_value = sum(h.quantity * h.price_per_unit for h in harvest_items)

    # ---------- Livestock ----------
    livestock = FarmLivestock.query.all()
    total_livestock_count = sum(l.quantity for l in livestock)
    total_livestock_value = sum(l.purchase_cost for l in livestock)

    # ---------- Crops ----------
    crops = FarmCrop.query.all()
    total_crop_area = sum(c.area for c in crops if c.area)
    total_planted_qty = sum(c.quantity_planted for c in crops if c.quantity_planted)

    # ---------- Harvest Records ----------
    harvest_records = FarmHarvest.query.filter(
        FarmHarvest.harvest_date.between(start_date, end_date)
    ).all()
    total_harvest_record_qty = sum(h.quantity for h in harvest_records)
    # Value from linked inventory prices (if any)
    harvest_value = 0
    for h in harvest_records:
        if h.inventory_entry:
            harvest_value += h.quantity * h.inventory_entry.price_per_unit
    # If no inventory link, we cannot compute value; maybe fallback? We'll just report quantity.

    # ---------- Expenses ----------
    expenses = FarmExpense.query.filter(
        FarmExpense.date.between(start_date, end_date)
    ).all()
    total_expenses = sum(e.amount for e in expenses) if expenses else 0
    expense_by_category = {}
    for e in expenses:
        cat = e.category or 'Uncategorized'
        expense_by_category[cat] = expense_by_category.get(cat, 0) + e.amount

    # ---------- Revenue ----------
    revenues = FarmRevenue.query.filter(
        FarmRevenue.date.between(start_date, end_date)
    ).all()
    total_revenue = sum(r.total_amount for r in revenues) if revenues else 0
    revenue_by_source = {}
    for r in revenues:
        rev_source = r.source or 'other'
        revenue_by_source[rev_source] = revenue_by_source.get(rev_source, 0) + r.total_amount

    # Profit/Loss
    net_profit = total_revenue - total_expenses
    profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0

    # ---------- Monthly Trends (last 12 months) ----------
    # We'll get data from expenses and revenue grouped by month
    now = datetime.utcnow()
    last_year = now - timedelta(days=365)
    # Monthly expenses
    monthly_expenses = db.session.query(
        func.extract('year', FarmExpense.date).label('year'),
        func.extract('month', FarmExpense.date).label('month'),
        func.sum(FarmExpense.amount).label('total')
    ).filter(FarmExpense.date >= last_year).group_by('year', 'month').all()
    # Monthly revenue
    monthly_revenue = db.session.query(
        func.extract('year', FarmRevenue.date).label('year'),
        func.extract('month', FarmRevenue.date).label('month'),
        func.sum(FarmRevenue.total_amount).label('total')
    ).filter(FarmRevenue.date >= last_year).group_by('year', 'month').all()

    # Build dictionary for quick lookup
    expense_dict = {}
    for row in monthly_expenses:
        key = f"{int(row.year)}-{int(row.month):02d}"
        expense_dict[key] = float(row.total)
    revenue_dict = {}
    for row in monthly_revenue:
        key = f"{int(row.year)}-{int(row.month):02d}"
        revenue_dict[key] = float(row.total)

    # Generate last 12 months labels and values
    labels = []
    expense_values = []
    revenue_values = []
    profit_values = []
    for i in range(11, -1, -1):
        month_date = now.replace(day=1) - timedelta(days=i*30)
        key = month_date.strftime('%Y-%m')
        labels.append(month_date.strftime('%b %Y'))
        exp = expense_dict.get(key, 0)
        rev = revenue_dict.get(key, 0)
        expense_values.append(exp)
        revenue_values.append(rev)
        profit_values.append(rev - exp)

    # ---------- Recent Data (last 5 each) ----------
    recent_expenses = FarmExpense.query.order_by(FarmExpense.date.desc()).limit(5).all()
    recent_revenues = FarmRevenue.query.order_by(FarmRevenue.date.desc()).limit(5).all()

    # ---------- Data for pie charts ----------
    expense_categories_labels = list(expense_by_category.keys())
    expense_categories_values = list(expense_by_category.values())
    revenue_sources_labels = list(revenue_by_source.keys())
    revenue_sources_values = list(revenue_by_source.values())

    # ---------- Top performing (by revenue) ----------
    # For simplicity, just show top 5 revenue records
    top_revenues = FarmRevenue.query.order_by(FarmRevenue.total_amount.desc()).limit(5).all()

    # ---------- Low stock inputs table ----------
    low_stock_inputs_data = [
        {
            'name': i.name,
            'quantity': i.quantity,
            'unit': i.unit,
            'reorder_level': i.reorder_level,
            'status': 'Critical' if i.quantity <= 0 else 'Low Stock'
        }
        for i in low_stock_inputs
    ]

    # Pass everything to template
    return render_template(
        'operations/farm/reports.html',
        total_input_qty=total_input_qty,
        total_input_value=total_input_value,
        low_stock_count=low_stock_count,
        low_stock_inputs=low_stock_inputs_data,
        total_harvest_qty=total_harvest_qty,
        total_harvest_value=total_harvest_value,
        total_livestock_count=total_livestock_count,
        total_livestock_value=total_livestock_value,
        total_crop_area=total_crop_area,
        total_planted_qty=total_planted_qty,
        total_harvest_record_qty=total_harvest_record_qty,
        total_expenses=total_expenses,
        total_revenue=total_revenue,
        net_profit=net_profit,
        profit_margin=profit_margin,
        monthly_labels=labels,
        monthly_expenses=expense_values,
        monthly_revenue=revenue_values,
        monthly_profit=profit_values,
        expense_categories_labels=expense_categories_labels,
        expense_categories_values=expense_categories_values,
        revenue_sources_labels=revenue_sources_labels,
        revenue_sources_values=revenue_sources_values,
        recent_expenses=recent_expenses,
        recent_revenues=recent_revenues,
        top_revenues=top_revenues,
        start_date=start_date_str,
        end_date=end_date_str
    )






@operations_web_bp.route('/procurement/requests', methods=['GET', 'POST'])
@login_required
def procurement_requests():
    """View user's own requests and create new ones."""
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            department = request.form.get('department')
            category = request.form.get('category')
            item_name = request.form.get('item_name')
            quantity = float(request.form.get('quantity', 0))
            unit = request.form.get('unit', 'pcs')
            priority = request.form.get('priority', 'medium')
            reason = request.form.get('reason')
            if not all([department, category, item_name, quantity, reason]):
                flash('Please fill all required fields.', 'danger')
                return redirect(url_for('operations_web_bp.procurement_requests'))
            req = ProcurementRequest(
                requester_id=current_user.id,
                department=department,
                category=category,
                item_name=item_name,
                quantity=quantity,
                unit=unit,
                priority=priority,
                reason=reason,
                status='pending'
            )
            db.session.add(req)
            db.session.commit()
            flash('Request submitted.', 'success')
            return redirect(url_for('operations_web_bp.procurement_requests'))

        elif action == 'edit':
            req_id = request.form.get('request_id')
            req = ProcurementRequest.query.get_or_404(req_id)
            if req.requester_id != current_user.id or req.status != 'pending':
                flash('Cannot edit this request.', 'danger')
                return redirect(url_for('operations_web_bp.procurement_requests'))
            req.department = request.form.get('department')
            req.category = request.form.get('category')
            req.item_name = request.form.get('item_name')
            req.quantity = float(request.form.get('quantity'))
            req.unit = request.form.get('unit')
            req.priority = request.form.get('priority')
            req.reason = request.form.get('reason')
            db.session.commit()
            flash('Request updated.', 'success')
            return redirect(url_for('operations_web_bp.procurement_requests'))

        elif action == 'cancel':
            req_id = request.form.get('request_id')
            req = ProcurementRequest.query.get_or_404(req_id)
            if req.requester_id != current_user.id or req.status != 'pending':
                flash('Cannot cancel this request.', 'danger')
                return redirect(url_for('operations_web_bp.procurement_requests'))
            db.session.delete(req)
            db.session.commit()
            flash('Request cancelled.', 'info')
            return redirect(url_for('operations_web_bp.procurement_requests'))

    # GET
    user_requests = ProcurementRequest.query.filter_by(requester_id=current_user.id).order_by(ProcurementRequest.created_at.desc()).all()
    departments = ['kitchen', 'store', 'farm', 'fleet']
    priorities = ['low', 'medium', 'high', 'critical']
    units = ['pcs', 'kg', 'liters', 'boxes', 'packets']
    return render_template(
        'operations/procurement/requests.html',
        requests=user_requests,
        departments=departments,
        priorities=priorities,
        units=units
    )
    
    
    
@operations_web_bp.route('/procurement/requests/approve', methods=['GET', 'POST'])
@login_required
def procurement_requests_approve():
    # Fetch active suppliers for dropdown
    suppliers = OperationsSupplier.query.filter_by(is_active=True).order_by(OperationsSupplier.name).all()

    if request.method == 'POST':
        action = request.form.get('action')
        req_id = request.form.get('request_id')
        req = ProcurementRequest.query.get_or_404(req_id)

        if req.status != 'pending':
            flash('This request has already been processed.', 'danger')
            return redirect(url_for('operations_web_bp.procurement_requests_approve'))

        if action == 'approve':
            supplier_id = request.form.get('supplier_id')
            unit_price = request.form.get('unit_price', type=float)
            expected_delivery_str = request.form.get('expected_delivery')
            notes = request.form.get('approval_notes', '')

            if not supplier_id or not unit_price or not expected_delivery_str:
                flash('Please select supplier, enter unit price, and expected delivery date.', 'danger')
                return redirect(url_for('operations_web_bp.procurement_requests_approve'))

            supplier = OperationsSupplier.query.get(supplier_id)
            if not supplier:
                flash('Invalid supplier.', 'danger')
                return redirect(url_for('operations_web_bp.procurement_requests_approve'))

            total_amount = req.quantity * unit_price

            # Create purchase order
            order = ProcurementOrder(
                request_id=req.id,
                supplier_id=supplier.id,
                order_number='',
                order_date=datetime.utcnow(),
                expected_delivery=datetime.strptime(expected_delivery_str, '%Y-%m-%d').date(),
                total_amount=total_amount,
                unit_price=unit_price,
                notes=notes,
                created_by=current_user.id,
                status='ordered'
            )
            order.order_number = order.generate_order_number()
            db.session.add(order)
            db.session.flush()

            # Ensure supplier account exists
            # Ensure supplier account exists
            account = OperationsSupplierAccount.query.filter_by(supplier_id=supplier.id).first()
            if not account:
                account = OperationsSupplierAccount(supplier_id=supplier.id, current_balance=0.0)
                db.session.add(account)
                db.session.commit()

            req.status = 'ordered'
            req.approved_by = current_user.id
            req.approved_at = datetime.utcnow()
            req.approval_notes = notes
            db.session.commit()

            flash(f'Request #{req.id} approved and purchase order {order.order_number} created.', 'success')

        elif action == 'reject':
            reason = request.form.get('rejection_reason', '')
            req.status = 'rejected'
            req.approved_by = current_user.id
            req.approved_at = datetime.utcnow()
            req.approval_notes = reason
            db.session.commit()
            flash(f'Request #{req.id} rejected.', 'warning')
        else:
            flash('Invalid action.', 'danger')
        return redirect(url_for('operations_web_bp.procurement_requests_approve'))

    # GET
    pending_requests = ProcurementRequest.query.filter_by(status='pending').order_by(ProcurementRequest.created_at.asc()).all()
    return render_template('operations/procurement/approve_requests.html',
                           pending_requests=pending_requests,
                           suppliers=suppliers)




@operations_web_bp.route('/procurement/orders')
@login_required
def procurement_orders():
    # Get filter parameters
    status_filter = request.args.get('status')
    supplier_filter = request.args.get('supplier', type=int)
    department_filter = request.args.get('department')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search')

    query = ProcurementOrder.query

    if status_filter:
        query = query.filter(ProcurementOrder.status == status_filter)
    if supplier_filter:
        query = query.filter(ProcurementOrder.supplier_id == supplier_filter)
    if department_filter:
        query = query.join(ProcurementOrder.request).filter(ProcurementRequest.department == department_filter)
    if start_date:
        query = query.filter(ProcurementOrder.order_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(ProcurementOrder.order_date <= datetime.strptime(end_date, '%Y-%m-%d'))
    if search:
        query = query.join(ProcurementOrder.request).filter(
            (ProcurementRequest.item_name.ilike(f'%{search}%')) |
            (ProcurementOrder.order_number.ilike(f'%{search}%')) |
            (ProcurementOrder.supplier.has(OperationsSupplier.name.ilike(f'%{search}%')))
        )

    orders = query.order_by(ProcurementOrder.order_date.desc()).all()

    # Distinct options for filters
    all_suppliers = OperationsSupplier.query.filter_by(is_active=True).order_by(OperationsSupplier.name).all()
    departments = db.session.query(ProcurementRequest.department).distinct().all()
    statuses = ['ordered', 'shipped', 'partially_received', 'received', 'cancelled']

    return render_template('operations/procurement/orders.html',
                           orders=orders,
                           suppliers=all_suppliers,
                           departments=[d[0] for d in departments],
                           statuses=statuses,
                           selected_status=status_filter,
                           selected_supplier=supplier_filter,
                           selected_department=department_filter,
                           start_date=start_date,
                           end_date=end_date,
                           search=search)
    
    
    
@operations_web_bp.route('/procurement/receiving', methods=['GET', 'POST'])
@login_required
def procurement_receiving():
    """Record receipt of goods against purchase orders."""
    now=datetime.utcnow()

    if request.method == 'POST':
        order_id = request.form.get('order_id')
        quantity_received = float(request.form.get('quantity_received', 0))
        batch_number = request.form.get('batch_number')
        expiration_date_str = request.form.get('expiration_date')
        condition = request.form.get('condition', 'good')
        notes = request.form.get('notes')
        order = ProcurementOrder.query.get_or_404(order_id)
        if order.status in ['received', 'cancelled']:
            flash('This order is already closed.', 'danger')
            return redirect(url_for('operations_web_bp.procurement_receiving'))

        # Create receiving record
        receiving = ProcurementReceiving(
            order_id=order.id,
            received_date=datetime.utcnow(),
            quantity_received=quantity_received,
            batch_number=batch_number,
            expiration_date=datetime.strptime(expiration_date_str, '%Y-%m-%d') if expiration_date_str else None,
            condition=condition,
            notes=notes,
            received_by=current_user.id
        )
        db.session.add(receiving)
        db.session.flush()
        receiving.after_receive()   # updates order status and inventory
        flash(f'Received {quantity_received} units for order {order.order_number}.', 'success')
        return redirect(url_for('operations_web_bp.procurement_receiving'))

    # GET – filter parameters
    status_filter = request.args.get('status')
    supplier_filter = request.args.get('supplier', type=int)
    department_filter = request.args.get('department')
    search = request.args.get('search')

    query = ProcurementOrder.query.filter(
        ProcurementOrder.status.in_(['ordered', 'shipped', 'partially_received'])
    )
    if status_filter:
        query = query.filter(ProcurementOrder.status == status_filter)
    if supplier_filter:
        query = query.filter(ProcurementOrder.supplier_id == supplier_filter)
    if department_filter:
        query = query.join(ProcurementOrder.request).filter(ProcurementRequest.department == department_filter)
    if search:
        query = query.join(ProcurementOrder.request).filter(
            (ProcurementRequest.item_name.ilike(f'%{search}%')) |
            (ProcurementOrder.order_number.ilike(f'%{search}%')) |
            (ProcurementOrder.supplier.has(OperationsSupplier.name.ilike(f'%{search}%')))
        )

    orders = query.order_by(ProcurementOrder.expected_delivery.asc()).all()

    # Compute remaining quantity for each order
    for order in orders:
        total_received = sum(r.quantity_received for r in order.deliveries)
        order.remaining_quantity = order.request.quantity - total_received

    # Recent receipts (last 20)
    recent_receipts = ProcurementReceiving.query.order_by(ProcurementReceiving.created_at.desc()).limit(20).all()

    # Filter options
    all_suppliers = OperationsSupplier.query.filter_by(is_active=True).order_by(OperationsSupplier.name).all()
    departments = db.session.query(ProcurementRequest.department).distinct().all()
    statuses = ['ordered', 'shipped', 'partially_received']
    today_receipts_count = sum(1 for r in recent_receipts if r.received_date.date() == now.date())
    return render_template('operations/procurement/receiving.html',
                           orders=orders,
                           recent_receipts=recent_receipts,
                           suppliers=all_suppliers,
                           departments=[d[0] for d in departments],
                           statuses=statuses,
                           selected_status=status_filter,
                           selected_supplier=supplier_filter,
                           selected_department=department_filter,
                           now=datetime.utcnow(),
                           search=search,
                           today_receipts_count=today_receipts_count
                           )