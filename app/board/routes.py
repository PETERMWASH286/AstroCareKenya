from datetime import datetime
from app.auth.models import BlogPost, Comment, Document, User
from app.board.models import StrategicInitiative
from app.store.models import SupplierInvoice
from . import board_bp
from flask_login import current_user, login_required
import os
from flask import (
    Blueprint, flash, jsonify, render_template, current_app, request, send_from_directory,
    abort, redirect, url_for
)
from sqlalchemy.orm import joinedload

from app.extensions import db

from datetime import datetime, timedelta
from sqlalchemy import func, extract
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.board import board_bp
from app.finance.models import SalesReport, Expense, PayrollPayment, Invoice, BankAccount, CashAccount, SalesReportItem
from app.patients.models import Visit, Patient
from app.extensions import db

@board_bp.route('/')
@login_required
def dashboard():
    # Get date filter parameters
    period = request.args.get('period', 'month')
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    year = request.args.get('year', datetime.now().strftime('%Y'))
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Determine start and end dates
    if period == 'custom' and start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    elif period == 'year':
        start_date = datetime(int(year), 1, 1)
        end_date = datetime(int(year), 12, 31, 23, 59, 59)
    else:  # month default
        y, m = map(int, month.split('-'))
        start_date = datetime(y, m, 1)
        if m == 12:
            end_date = datetime(y+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(y, m+1, 1) - timedelta(seconds=1)

    # --- Revenue ---
    revenue = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).scalar() or 0.0

    # Revenue for previous period (for comparison)
    prev_start = start_date - (end_date - start_date)
    prev_end = start_date - timedelta(seconds=1)
    prev_revenue = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= prev_start,
        SalesReport.sale_date <= prev_end
    ).scalar() or 0.0
    revenue_change = ((revenue - prev_revenue) / prev_revenue * 100) if prev_revenue else 0

    # --- Expenses ---
    expenses = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.status == 'paid'
    ).scalar() or 0.0

    payroll = db.session.query(func.sum(PayrollPayment.amount)).filter(
        PayrollPayment.transaction_date >= start_date,
        PayrollPayment.transaction_date <= end_date
    ).scalar() or 0.0
    total_expenses = expenses + float(payroll)

    # Previous period expenses
    prev_expenses = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= prev_start,
        Expense.expense_date <= prev_end,
        Expense.status == 'paid'
    ).scalar() or 0.0
    prev_payroll = db.session.query(func.sum(PayrollPayment.amount)).filter(
        PayrollPayment.transaction_date >= prev_start,
        PayrollPayment.transaction_date <= prev_end
    ).scalar() or 0.0
    prev_total_expenses = prev_expenses + float(prev_payroll)
    expense_change = ((total_expenses - prev_total_expenses) / prev_total_expenses * 100) if prev_total_expenses else 0

    net_profit = revenue - total_expenses
    prev_net = prev_revenue - prev_total_expenses
    net_change = ((net_profit - prev_net) / prev_net * 100) if prev_net else 0

    # --- Patient Visits ---
    total_visits = Visit.query.filter(
        Visit.visit_date >= start_date,
        Visit.visit_date <= end_date
    ).count()

    walkin_visits = Visit.query.filter(
        Visit.visit_date >= start_date,
        Visit.visit_date <= end_date,
        Visit.is_walk_in == True
    ).count()

    # --- Cash & Bank Balances (current) ---
    cash_balance = db.session.query(func.sum(CashAccount.current_balance)).scalar() or 0.0
    bank_balance = db.session.query(func.sum(BankAccount.current_balance)).scalar() or 0.0
    total_cash = cash_balance + bank_balance

    # --- Accounts Receivable / Payable ---
    ar_total = db.session.query(func.sum(Invoice.balance)).filter(
        Invoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar() or 0.0

    ap_total = db.session.query(func.sum(SupplierInvoice.balance_due)).filter(
        SupplierInvoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar() or 0.0

    # --- Monthly trend data for chart (last 6 months) ---
    months = []
    revenue_trend = []
    expense_trend = []
    for i in range(5, -1, -1):
        d = (start_date - timedelta(days=30*i)).replace(day=1)
        month_start = d
        if d.month == 12:
            month_end = datetime(d.year+1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(d.year, d.month+1, 1) - timedelta(seconds=1)

        month_rev = db.session.query(func.sum(SalesReport.total_amount)).filter(
            SalesReport.sale_date >= month_start,
            SalesReport.sale_date <= month_end
        ).scalar() or 0.0

        month_exp = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
            Expense.expense_date >= month_start,
            Expense.expense_date <= month_end,
            Expense.status == 'paid'
        ).scalar() or 0.0
        month_pay = db.session.query(func.sum(PayrollPayment.amount)).filter(
            PayrollPayment.transaction_date >= month_start,
            PayrollPayment.transaction_date <= month_end
        ).scalar() or 0.0
        month_total_exp = month_exp + float(month_pay)

        months.append(month_start.strftime('%b %Y'))
        revenue_trend.append(month_rev)
        expense_trend.append(month_total_exp)

    # --- Top departments by revenue ---
    top_depts = db.session.query(
        SalesReportItem.department,
        func.sum(SalesReportItem.total_price).label('total')
    ).join(SalesReport).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).group_by(SalesReportItem.department).order_by(func.sum(SalesReportItem.total_price).desc()).limit(5).all()

    # --- Recent sales (last 10) ---
    recent_sales = SalesReport.query.order_by(SalesReport.sale_date.desc()).limit(10).all()

    # --- Recent expenses (last 10) ---
    recent_expenses = Expense.query.filter_by(status='paid').order_by(Expense.expense_date.desc()).limit(10).all()




    return render_template(
        'board_dashboard.html',
        start_date=start_date,
        end_date=end_date,
        period=period,
        selected_month=month,
        selected_year=year,
        revenue=revenue,
        revenue_change=revenue_change,
        total_expenses=total_expenses,
        expense_change=expense_change,
        net_profit=net_profit,
        net_change=net_change,
        total_visits=total_visits,
        walkin_visits=walkin_visits,
        total_cash=total_cash,
        ar_total=ar_total,
        ap_total=ap_total,
        months=months,
        revenue_trend=revenue_trend,
        expense_trend=expense_trend,
        top_depts=top_depts,
        recent_sales=recent_sales,
        recent_expenses=recent_expenses
    )






@board_bp.route('/financial-reports')
@login_required
def financial_reports():
    # Get date filter parameters
    period = request.args.get('period', 'month')
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    year = request.args.get('year', datetime.now().strftime('%Y'))
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Determine start and end dates
    if period == 'custom' and start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    elif period == 'year':
        start_date = datetime(int(year), 1, 1)
        end_date = datetime(int(year), 12, 31, 23, 59, 59)
    else:  # month default
        y, m = map(int, month.split('-'))
        start_date = datetime(y, m, 1)
        if m == 12:
            end_date = datetime(y+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(y, m+1, 1) - timedelta(seconds=1)

    # --- Revenue ---
    revenue = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).scalar() or 0.0

    # Revenue for previous period (for comparison)
    prev_start = start_date - (end_date - start_date)
    prev_end = start_date - timedelta(seconds=1)
    prev_revenue = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= prev_start,
        SalesReport.sale_date <= prev_end
    ).scalar() or 0.0
    revenue_change = ((revenue - prev_revenue) / prev_revenue * 100) if prev_revenue else 0

    # --- Expenses ---
    expenses = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.status == 'paid'
    ).scalar() or 0.0

    payroll = db.session.query(func.sum(PayrollPayment.amount)).filter(
        PayrollPayment.transaction_date >= start_date,
        PayrollPayment.transaction_date <= end_date
    ).scalar() or 0.0
    total_expenses = expenses + float(payroll)

    # Previous period expenses
    prev_expenses = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= prev_start,
        Expense.expense_date <= prev_end,
        Expense.status == 'paid'
    ).scalar() or 0.0
    prev_payroll = db.session.query(func.sum(PayrollPayment.amount)).filter(
        PayrollPayment.transaction_date >= prev_start,
        PayrollPayment.transaction_date <= prev_end
    ).scalar() or 0.0
    prev_total_expenses = prev_expenses + float(prev_payroll)
    expense_change = ((total_expenses - prev_total_expenses) / prev_total_expenses * 100) if prev_total_expenses else 0

    net_profit = revenue - total_expenses
    prev_net = prev_revenue - prev_total_expenses
    net_change = ((net_profit - prev_net) / prev_net * 100) if prev_net else 0

    # --- Cash & Bank Balances (current) ---
    cash_balance = db.session.query(func.sum(CashAccount.current_balance)).scalar() or 0.0
    bank_balance = db.session.query(func.sum(BankAccount.current_balance)).scalar() or 0.0
    total_cash = cash_balance + bank_balance

    # --- Accounts Receivable / Payable ---
    ar_total = db.session.query(func.sum(Invoice.balance)).filter(
        Invoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar() or 0.0

    ap_total = db.session.query(func.sum(SupplierInvoice.balance_due)).filter(
        SupplierInvoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar() or 0.0

    # --- Monthly trend data for chart (last 6 months) ---
    months = []
    revenue_trend = []
    expense_trend = []
    for i in range(5, -1, -1):
        d = (start_date - timedelta(days=30*i)).replace(day=1)
        month_start = d
        if d.month == 12:
            month_end = datetime(d.year+1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(d.year, d.month+1, 1) - timedelta(seconds=1)

        month_rev = db.session.query(func.sum(SalesReport.total_amount)).filter(
            SalesReport.sale_date >= month_start,
            SalesReport.sale_date <= month_end
        ).scalar() or 0.0

        month_exp = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
            Expense.expense_date >= month_start,
            Expense.expense_date <= month_end,
            Expense.status == 'paid'
        ).scalar() or 0.0
        month_pay = db.session.query(func.sum(PayrollPayment.amount)).filter(
            PayrollPayment.transaction_date >= month_start,
            PayrollPayment.transaction_date <= month_end
        ).scalar() or 0.0
        month_total_exp = month_exp + float(month_pay)

        months.append(month_start.strftime('%b %Y'))
        revenue_trend.append(month_rev)
        expense_trend.append(month_total_exp)

    return render_template(
        'board_financial_reports.html',
        start_date=start_date,
        end_date=end_date,
        period=period,
        selected_month=month,
        selected_year=year,
        revenue=revenue,
        revenue_change=revenue_change,
        total_expenses=total_expenses,
        expense_change=expense_change,
        net_profit=net_profit,
        net_change=net_change,
        total_cash=total_cash,
        ar_total=ar_total,
        ap_total=ap_total,
        months=months,
        revenue_trend=revenue_trend,
        expense_trend=expense_trend
    )
    
    



@board_bp.route('/strategic-planning')
@login_required
def strategic_planning():
    # Fetch all initiatives, ordered by priority/end date
    initiatives = StrategicInitiative.query.order_by(
        StrategicInitiative.priority.desc(),
        StrategicInitiative.target_end_date.asc()
    ).all()

    # Group by status for summary (optional, but we'll keep summary stats)
    grouped = {
        'not_started': [],
        'in_progress': [],
        'on_hold': [],
        'completed': []
    }
    for ini in initiatives:
        grouped[ini.status].append(ini)

    # Summary stats
    total_initiatives = len(initiatives)
    completed_count = len(grouped['completed'])
    in_progress_count = len(grouped['in_progress'])
    total_budget_allocated = sum(i.budget_allocated for i in initiatives)
    total_budget_spent = sum(i.budget_spent for i in initiatives)

    # Get all active users for owner dropdown
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    return render_template(
        'strategic_planning.html',
        grouped=grouped,  # still used for summary stats
        total_initiatives=total_initiatives,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        total_budget_allocated=total_budget_allocated,
        total_budget_spent=total_budget_spent,
        users=users,
        initiatives=initiatives  # pass all initiatives for the table
    )
    
    
@board_bp.route('/initiative', methods=['POST'])
@login_required
def create_initiative():
    data = request.json
    ini = StrategicInitiative(
        title=data['title'],
        description=data.get('description'),
        category=data.get('category'),
        start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None,
        target_end_date=datetime.strptime(data['target_end_date'], '%Y-%m-%d').date() if data.get('target_end_date') else None,
        status=data.get('status', 'not_started'),
        priority=data.get('priority', 'medium'),
        owner_id=data.get('owner_id') or None,
        progress_percent=int(data.get('progress_percent', 0)),
        budget_allocated=float(data.get('budget_allocated', 0)),
        budget_spent=float(data.get('budget_spent', 0)),
        notes=data.get('notes')
    )
    db.session.add(ini)
    db.session.commit()
    return jsonify({'success': True, 'id': ini.id})

@board_bp.route('/initiative/<int:id>', methods=['GET'])
@login_required
def get_initiative(id):
    ini = StrategicInitiative.query.get_or_404(id)
    return jsonify({
        'id': ini.id,
        'title': ini.title,
        'description': ini.description,
        'category': ini.category,
        'start_date': ini.start_date.isoformat() if ini.start_date else None,
        'target_end_date': ini.target_end_date.isoformat() if ini.target_end_date else None,
        'status': ini.status,
        'priority': ini.priority,
        'owner_id': ini.owner_id,
        'progress_percent': ini.progress_percent,
        'budget_allocated': ini.budget_allocated,
        'budget_spent': ini.budget_spent,
        'notes': ini.notes
    })

@board_bp.route('/initiative/<int:id>', methods=['PUT'])
@login_required
def update_initiative(id):
    ini = StrategicInitiative.query.get_or_404(id)
    data = request.json
    ini.title = data.get('title', ini.title)
    ini.description = data.get('description', ini.description)
    ini.category = data.get('category', ini.category)
    if data.get('start_date'):
        ini.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    if data.get('target_end_date'):
        ini.target_end_date = datetime.strptime(data['target_end_date'], '%Y-%m-%d').date()
    ini.status = data.get('status', ini.status)
    ini.priority = data.get('priority', ini.priority)
    ini.owner_id = data.get('owner_id', ini.owner_id)
    ini.progress_percent = int(data.get('progress_percent', ini.progress_percent))
    ini.budget_allocated = float(data.get('budget_allocated', ini.budget_allocated))
    ini.budget_spent = float(data.get('budget_spent', ini.budget_spent))
    ini.notes = data.get('notes', ini.notes)
    db.session.commit()
    return jsonify({'success': True})

@board_bp.route('/initiative/<int:id>', methods=['DELETE'])
@login_required
def delete_initiative(id):
    ini = StrategicInitiative.query.get_or_404(id)
    db.session.delete(ini)
    db.session.commit()
    return jsonify({'success': True})

@board_bp.route('/initiative/<int:id>/details')
@login_required
def initiative_details(id):
    ini = StrategicInitiative.query.get_or_404(id)
    milestones = [{'title': m.title, 'due_date': m.due_date.isoformat() if m.due_date else None, 'completed': m.completed} for m in ini.milestones]
    key_results = [{'description': kr.description, 'target_value': kr.target_value, 'current_value': kr.current_value, 'unit': kr.unit} for kr in ini.key_results]
    return jsonify({
        'title': ini.title,
        'description': ini.description,
        'status': ini.status,
        'priority': ini.priority,
        'start_date': ini.start_date.isoformat() if ini.start_date else None,
        'target_end_date': ini.target_end_date.isoformat() if ini.target_end_date else None,
        'progress_percent': ini.progress_percent,
        'budget_allocated': ini.budget_allocated,
        'budget_spent': ini.budget_spent,
        'milestones': milestones,
        'key_results': key_results
    })
    
    
from datetime import datetime, date
from flask import render_template, request, jsonify, url_for, redirect, flash
from flask_login import login_required, current_user
from app.board import board_bp
from app.board.models import BoardMeeting, BoardDocument, ComplianceItem
from app.extensions import db
import os
from werkzeug.utils import secure_filename

# Governance Dashboard
@board_bp.route('/governance')
@login_required
def governance():
    # Upcoming meetings (next 5)
    upcoming_meetings = BoardMeeting.query.filter(
        BoardMeeting.meeting_date >= datetime.now(),
        BoardMeeting.status == 'scheduled'
    ).order_by(BoardMeeting.meeting_date.asc()).limit(5).all()

    # Recent minutes (last 5 held meetings)
    recent_minutes = BoardMeeting.query.filter_by(status='held').order_by(
        BoardMeeting.meeting_date.desc()
    ).limit(5).all()

    # Documents grouped by type
    policies = BoardDocument.query.filter_by(document_type='policy', is_active=True).all()
    charters = BoardDocument.query.filter_by(document_type='charter', is_active=True).all()
    bylaws = BoardDocument.query.filter_by(document_type='bylaw', is_active=True).all()
    other_docs = BoardDocument.query.filter(
        BoardDocument.document_type.notin_(['policy', 'charter', 'bylaw']),
        BoardDocument.is_active == True
    ).all()

    # Compliance items summary
    compliance_items = ComplianceItem.query.all()
    compliant_count = sum(1 for c in compliance_items if c.status == 'compliant')
    pending_count = sum(1 for c in compliance_items if c.status == 'pending')
    overdue_count = sum(1 for c in compliance_items if c.status == 'overdue' or (c.due_date and c.due_date < date.today() and c.status != 'compliant'))
    non_compliant_count = sum(1 for c in compliance_items if c.status == 'non-compliant')

    return render_template(
        'governance.html',
        upcoming_meetings=upcoming_meetings,
        recent_minutes=recent_minutes,
        policies=policies,
        charters=charters,
        bylaws=bylaws,
        other_docs=other_docs,
        compliance_items=compliance_items,
        compliant_count=compliant_count,
        pending_count=pending_count,
        overdue_count=overdue_count,
        non_compliant_count=non_compliant_count,
        users=User.query.filter_by(is_active=True).all()
    )


# ---------- Board Meetings ----------
@board_bp.route('/meeting', methods=['POST'])
@login_required
def create_meeting():
    data = request.json
    meeting = BoardMeeting(
        title=data['title'],
        meeting_date=datetime.strptime(data['meeting_date'], '%Y-%m-%dT%H:%M'),
        agenda=data.get('agenda'),
        status=data.get('status', 'scheduled')
    )
    db.session.add(meeting)
    db.session.commit()
    return jsonify({'success': True, 'id': meeting.id})

@board_bp.route('/meeting/<int:id>', methods=['GET'])
@login_required
def get_meeting(id):
    meeting = BoardMeeting.query.get_or_404(id)
    return jsonify({
        'id': meeting.id,
        'title': meeting.title,
        'meeting_date': meeting.meeting_date.isoformat(),
        'agenda': meeting.agenda,
        'minutes': meeting.minutes,
        'status': meeting.status
    })

@board_bp.route('/meeting/<int:id>', methods=['PUT'])
@login_required
def update_meeting(id):
    meeting = BoardMeeting.query.get_or_404(id)
    data = request.json
    meeting.title = data.get('title', meeting.title)
    if data.get('meeting_date'):
        meeting.meeting_date = datetime.strptime(data['meeting_date'], '%Y-%m-%dT%H:%M')
    meeting.agenda = data.get('agenda', meeting.agenda)
    meeting.minutes = data.get('minutes', meeting.minutes)
    meeting.status = data.get('status', meeting.status)
    db.session.commit()
    return jsonify({'success': True})

@board_bp.route('/meeting/<int:id>', methods=['DELETE'])
@login_required
def delete_meeting(id):
    meeting = BoardMeeting.query.get_or_404(id)
    db.session.delete(meeting)
    db.session.commit()
    return jsonify({'success': True})


# ---------- Board Documents ----------
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@board_bp.route('/document', methods=['POST'])
@login_required
def upload_document():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'})
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Save to a configured upload folder – adjust as needed
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads/board')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        doc = BoardDocument(
            title=request.form['title'],
            document_type=request.form['document_type'],
            description=request.form.get('description'),
            file_path=file_path,
            version=request.form.get('version'),
            effective_date=datetime.strptime(request.form['effective_date'], '%Y-%m-%d').date() if request.form.get('effective_date') else None,
            uploaded_by=current_user.id
        )
        db.session.add(doc)
        db.session.commit()
        return jsonify({'success': True, 'id': doc.id})
    return jsonify({'success': False, 'error': 'File type not allowed'})

@board_bp.route('/document/<int:id>', methods=['DELETE'])
@login_required
def delete_document(id):
    doc = BoardDocument.query.get_or_404(id)
    # Optionally delete file from disk
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'success': True})


# ---------- Compliance Items ----------
@board_bp.route('/compliance', methods=['POST'])
@login_required
def create_compliance():
    data = request.json
    item = ComplianceItem(
        name=data['name'],
        description=data.get('description'),
        category=data.get('category'),
        due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
        status=data.get('status', 'pending'),
        assigned_to=data.get('assigned_to'),
        notes=data.get('notes')
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'success': True, 'id': item.id})

@board_bp.route('/compliance/<int:id>', methods=['GET'])
@login_required
def get_compliance(id):
    item = ComplianceItem.query.get_or_404(id)
    return jsonify({
        'id': item.id,
        'name': item.name,
        'description': item.description,
        'category': item.category,
        'due_date': item.due_date.isoformat() if item.due_date else None,
        'status': item.status,
        'assigned_to': item.assigned_to,
        'notes': item.notes
    })

@board_bp.route('/compliance/<int:id>', methods=['PUT'])
@login_required
def update_compliance(id):
    item = ComplianceItem.query.get_or_404(id)
    data = request.json
    item.name = data.get('name', item.name)
    item.description = data.get('description', item.description)
    item.category = data.get('category', item.category)
    if data.get('due_date'):
        item.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
    item.status = data.get('status', item.status)
    item.assigned_to = data.get('assigned_to', item.assigned_to)
    item.notes = data.get('notes', item.notes)
    db.session.commit()
    return jsonify({'success': True})

@board_bp.route('/compliance/<int:id>', methods=['DELETE'])
@login_required
def delete_compliance(id):
    item = ComplianceItem.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})

@board_bp.route('/resources')
@login_required
def resources():
    dept_id = current_user.department_id
    
    # Fetch blog posts with comments count
    blog_posts = (
        BlogPost.query
        .filter_by(department_id=dept_id, status='published')
        .options(db.joinedload(BlogPost.author))
        .options(db.joinedload(BlogPost.comments))
        .order_by(BlogPost.created_at.desc())
        .all()
    )
    
    # Fetch documents with comments count
    documents = (
        Document.query
        .filter_by(department_id=dept_id)
        .options(db.joinedload(Document.uploader))
        .options(db.joinedload(Document.comments))
        .order_by(Document.created_at.desc())
        .all()
    )
    
    return render_template(
        'view_resources.html',
        blog_posts=blog_posts,
        documents=documents
    )

@board_bp.route('/add-comment', methods=['POST'])
@login_required
def add_comment():
    resource_type = request.form['resource_type']
    resource_id = request.form['resource_id']
    content = request.form['content']
    
    new_comment = Comment(
        content=content,
        user_id=current_user.id,
        created_at=datetime.utcnow()
    )
    
    if resource_type == 'blog':
        new_comment.blog_post_id = resource_id
    elif resource_type == 'document':
        new_comment.document_id = resource_id
    
    db.session.add(new_comment)
    db.session.commit()
    
    flash('Comment added successfully!', 'success')
    return redirect(request.referrer)

@board_bp.route('/blog/<int:blog_id>', methods=['GET', 'POST'])
@login_required
def view_blog(blog_id):
    """
    Show a single published blog post with comments, 
    only if it belongs to the current_user's department.
    Also handles new comment submissions via POST.
    """
    # Load post with all related data
    post = BlogPost.query.options(
        db.joinedload(BlogPost.author),
        db.joinedload(BlogPost.department),
        db.joinedload(BlogPost.comments).joinedload(Comment.user)
    ).get_or_404(blog_id)

    # Permission check
    if post.department_id != current_user.department_id or post.status != 'published':
        abort(404)

    # Handle comment form submission
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('Comment cannot be empty.', 'error')
        else:
            new_comment = Comment(
                content=content,
                user_id=current_user.id,
                blog_post_id=post.id,
                created_at=datetime.utcnow()
            )
            db.session.add(new_comment)
            db.session.commit()
            flash('Your comment has been posted!', 'success')
        return redirect(url_for('board.view_blog', blog_id=blog_id))

    # Get related posts from the same department
    related_posts = BlogPost.query.filter(
        BlogPost.department_id == current_user.department_id,
        BlogPost.status == 'published',
        BlogPost.id != post.id
    ).order_by(db.func.random()).limit(3).all()

    return render_template(
        'blog.html',
        post=post,
        related_posts=related_posts
    )

@board_bp.route('/delete-comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    """Delete a comment with full security and auditing"""

    
    # Get comment with associated blog post
    comment = Comment.query.options(
        db.joinedload(Comment.blog_post)
    ).get_or_404(comment_id)
    
    # Permission check
    if comment.user_id != current_user.id and not current_user.is_admin():
        abort(403, description="You don't have permission to delete this comment")
    
    # Get blog ID before deletion
    blog_id = comment.blog_post_id
    

    db.session.delete(comment)
    db.session.commit()
    
    flash('Comment deleted successfully', 'success')
    return redirect(url_for('board.view_blog', blog_id=blog_id))

@board_bp.route('/download-resource-document/<int:document_id>', methods=['GET'])
def download_resource_document(document_id):
    """
    Serve a document file for download, only if it belongs to
    the current_user’s department.
    """
    doc = Document.query.get_or_404(document_id)

    # Enforce department-level access
    if doc.department_id != current_user.department_id:
        abort(404)

    upload_folder = current_app.config['UPLOAD_FOLDER']
    full_path = os.path.join(upload_folder, doc.file_path)
    if not os.path.isfile(full_path):
        abort(404)

    return send_from_directory(
        directory=upload_folder,
        path=doc.file_path,
        as_attachment=True,
        download_name=doc.title + os.path.splitext(doc.file_path)[1]
    )