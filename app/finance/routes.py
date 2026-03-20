import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import tempfile
from time import time
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, extract, func

from app.asset_management.models import Asset
from app.auth.models import Role, User
from app.finance.models import BankAccount, BankStatement, BankStatementLine, BankTransaction, CashAccount, CashTransaction, ClaimResponse, Expense, ExpenseCategory, FinanceConversation, FinanceMessage, Insurance, InsuranceClaim, InsuranceService, Invoice, InvoiceItem, Payment, PayrollPayment, SalesReport, SalesReportItem
from sqlalchemy.exc import IntegrityError

from app.hr.models import DeductionType, EmployeeDeductionAssignment, LoanRepayment, PaymentMethod, Payroll, PayrollLoan, Payslip, PayslipDeduction, PayslipEarning, StatutoryLiability
from app.lab.models import LabInventory
from app.pharmacy.models import PharmacyInventory
from app.radiology.models import RadiologyInventory
from app.store.models import LPO, ExternalOrder, PaymentRequest, PurchaseOrder, Requisition, Stock, Supplier, SupplierAccount, SupplierInvoice, SupplierTransaction
from app.user_management.models import Department

from . import finance_web_bp
from app.patients.models import Consultation, DoctorPayment, LabTest, Medication, Patient, Radiology, ServiceDoctorAssignment, Transaction, Service, Visit, db
from flask import Blueprint, render_template, current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.utils.notifications import notification_manager

# Financial Dashboard
@finance_web_bp.route('/dashboard')
@login_required
def financial_dashboard():
    today = datetime.today()
    current_year = today.year
    current_month = today.month
    first_day_of_month = datetime(current_year, current_month, 1)
    first_day_of_prev_month = (first_day_of_month - timedelta(days=1)).replace(day=1)

    # ----- Revenue (from SalesReport) -----
    revenue_current_month = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= first_day_of_month
    ).scalar() or 0.0

    revenue_prev_month = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= first_day_of_prev_month,
        SalesReport.sale_date < first_day_of_month
    ).scalar() or 0.0

    revenue_current_year = db.session.query(func.sum(SalesReport.total_amount)).filter(
        extract('year', SalesReport.sale_date) == current_year
    ).scalar() or 0.0

    # ----- Expenses -----
    expenses_current_month = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= first_day_of_month
    ).scalar() or 0.0

    expenses_prev_month = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= first_day_of_prev_month,
        Expense.expense_date < first_day_of_month
    ).scalar() or 0.0

    expenses_current_year = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        extract('year', Expense.expense_date) == current_year
    ).scalar() or 0.0

    # ----- Profit -----
    profit_current_month = revenue_current_month - expenses_current_month
    profit_prev_month = revenue_prev_month - expenses_prev_month
    profit_change = profit_current_month - profit_prev_month

    # ----- Cash & Bank Balances -----
    cash_balance = db.session.query(func.sum(CashAccount.current_balance)).filter(
        CashAccount.is_active == True
    ).scalar() or 0.0

    bank_balance = db.session.query(func.sum(BankAccount.current_balance)).filter(
        BankAccount.is_active == True
    ).scalar() or 0.0

    # ----- Pending Approvals -----
    pending_expenses = Expense.query.filter_by(status='submitted').count()
    pending_payrolls = Payroll.query.filter_by(status='Approved').count()  # finance needs to pay these

    # ----- Recent Sales (last 5) -----
    recent_sales = SalesReport.query.order_by(SalesReport.sale_date.desc()).limit(5).all()

    # ----- Recent Expenses (last 5) -----
    recent_expenses = Expense.query.order_by(Expense.expense_date.desc()).limit(5).all()

    # ----- Expense Breakdown by Category (for current month) -----
    category_expenses = db.session.query(
        ExpenseCategory.name,
        func.sum(Expense.amount + Expense.tax_amount).label('total')
    ).join(Expense, Expense.category_id == ExpenseCategory.id).filter(
        Expense.expense_date >= first_day_of_month
    ).group_by(ExpenseCategory.name).all()
    expense_categories = [{'name': c, 'total': t} for c, t in category_expenses]

    # ----- Monthly Revenue vs Expense Trend (last 6 months) -----
    months_data = []
    for i in range(5, -1, -1):
        month_start = (first_day_of_month - timedelta(days=30*i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        rev = db.session.query(func.sum(SalesReport.total_amount)).filter(
            SalesReport.sale_date >= month_start,
            SalesReport.sale_date <= month_end
        ).scalar() or 0.0
        exp = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
            Expense.expense_date >= month_start,
            Expense.expense_date <= month_end
        ).scalar() or 0.0
        months_data.append({
            'month': month_start.strftime('%b'),
            'revenue': rev,
            'expenses': exp
        })

    return render_template(
        'finance_dashboard.html',
        revenue_current_month=revenue_current_month,
        revenue_prev_month=revenue_prev_month,
        revenue_current_year=revenue_current_year,
        expenses_current_month=expenses_current_month,
        expenses_prev_month=expenses_prev_month,
        expenses_current_year=expenses_current_year,
        profit_current_month=profit_current_month,
        profit_prev_month=profit_prev_month,
        profit_change=profit_change,
        cash_balance=cash_balance,
        bank_balance=bank_balance,
        pending_expenses=pending_expenses,
        pending_payrolls=pending_payrolls,
        recent_sales=recent_sales,
        recent_expenses=recent_expenses,
        expense_categories=expense_categories,
        months_data=months_data,
        currency='KES'
    )

@finance_web_bp.route('/invoices')
def invoices():
    """
    Load every invoice except those of type 'cash', along with all related data 
    (patient, visit, insurance, invoice items with service info, and payments).
    """
    # 1) Eager-load everything and exclude cash invoices
    invoices_q = (
        Invoice.query
        .filter(Invoice.invoice_type != 'cash')  # 👈 Filter out cash invoices
        .options(
            joinedload(Invoice.patient),
            joinedload(Invoice.visit),
            joinedload(Invoice.insurance),
            joinedload(Invoice.items).joinedload(InvoiceItem.service),
            joinedload(Invoice.payments)
        )
        .order_by(Invoice.issue_date.desc())
        .all()
    )

    invoice_data = []
    for inv in invoices_q:
        invoice_items = []
        for item in inv.items:
            svc = item.service
            invoice_items.append({
                'service_id': svc.id,
                'service_name': svc.name,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'total_price': item.total_price,
                'is_insured': item.is_insured,
                'coverage_percentage': item.coverage_percentage,
                'copay_amount': item.copay_amount,
                'notes': item.notes
            })

        invoice_payments = []
        amount_paid = 0.0
        for p in inv.payments:
            invoice_payments.append({
                'payment_id': p.id,
                'amount': p.amount,
                'method': p.method,
                'payment_date': p.payment_date,
                'status': p.status,
                'reference': p.reference,
                'payer_name': p.payer_name
            })
            amount_paid += p.amount or 0.0

        invoice_data.append({
            'invoice_id': inv.id,
            'patient_reg_no': inv.patient.reg_no,
            'patient_name': inv.patient.full_name,
            'visit_id': inv.visit.id,
            'invoice_type': inv.invoice_type,
            'insurance_name': (inv.insurance.name if inv.insurance else None),
            'issue_date': inv.issue_date,
            'due_date': inv.due_date,
            'total_amount': inv.total_amount,
            'status': inv.status,
            'invoice_notes': inv.notes,
            'invoice_items': invoice_items,
            'invoice_payments': invoice_payments,
            'amount_paid': round(amount_paid, 2),
            'balance': round(inv.total_amount - amount_paid, 2)
        })

    insurances = Insurance.query.filter_by(is_active=True).order_by(Insurance.name).all()

    return render_template('invoices.html', invoices=invoice_data, insurances=insurances)


@finance_web_bp.route('/invoices/<int:invoice_id>')
def view_invoice(invoice_id):
    """
    Show full invoice details: header, items, payments, and balance.
    """
    inv = Invoice.query.get_or_404(invoice_id)
    # Eager‐load items and payments if needed:
    items = InvoiceItem.query.filter_by(invoice_id=invoice_id).all()
    payments = Payment.query.filter_by(invoice_id=invoice_id).all()
    amount_paid = sum(p.amount or 0.0 for p in payments)
    balance = inv.total_amount - amount_paid
    return render_template(
        'view_invoice.html',
        invoice=inv,
        items=items,
        payments=payments,
        amount_paid=round(amount_paid, 2),
        balance=round(balance, 2)
    )


@finance_web_bp.route('/invoices/<int:invoice_id>/items')
def view_items(invoice_id):
    """
    Redirect to or render a page that lists only the line items for this invoice.
    """
    inv = Invoice.query.get_or_404(invoice_id)
    items = InvoiceItem.query.filter_by(invoice_id=invoice_id).all()
    return render_template(
        'view_items.html',
        invoice=inv,
        items=items
    )


@finance_web_bp.route('/invoices/<int:invoice_id>/payments')
def view_payments(invoice_id):
    """
    Redirect to or render a page that lists only the payments for this invoice.
    """
    inv = Invoice.query.get_or_404(invoice_id)
    payments = Payment.query.filter_by(invoice_id=invoice_id).all()
    amount_paid = sum(p.amount or 0.0 for p in payments)
    balance = inv.total_amount - amount_paid
    return render_template(
        'view_payments.html',
        invoice=inv,
        payments=payments,
        amount_paid=round(amount_paid, 2),
        balance=round(balance, 2)
    )


@finance_web_bp.route('/invoices/<int:invoice_id>/submit-claim', methods=['GET', 'POST'])
def submit_claim(invoice_id):
    """
    If the invoice is insurance-based, allow submitting an insurance claim.
    GET: show form; POST: create InsuranceClaim record.
    """
    inv = Invoice.query.get_or_404(invoice_id)

    # Only allow submitting claim for insurance invoices
    if inv.invoice_type != 'insurance':
        flash("Cannot submit claim on a non-insurance invoice.", "warning")
        return redirect(url_for('finance_web.view_invoice', invoice_id=invoice_id))

    if request.method == 'POST':
        claim_ref = request.form.get('claim_reference', '').strip()
        submitted_by = request.form.get('submitted_by', '').strip()
        notes = request.form.get('notes', '').strip()

        if not claim_ref or not submitted_by:
            flash("Claim Reference and Submitted By are required.", "danger")
            return redirect(request.url)

        try:
            claim = InsuranceClaim(
                invoice_id=invoice_id,
                insurance_id=inv.insurance_id,
                claim_reference=claim_ref,
                submitted_by=submitted_by,
                notes=notes
            )
            db.session.add(claim)
            db.session.commit()
            flash("Insurance claim submitted successfully.", "success")
            return redirect(url_for('finance_web.view_invoice', invoice_id=invoice_id))

        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Error submitting insurance claim")
            flash("An error occurred while submitting the claim.", "danger")
            return redirect(request.url)

    return render_template(
        'submit_claim.html',
        invoice=inv
    )

@finance_web_bp.route('/submit-insurance-claims', methods=['POST'])
def submit_insurance_claims():
    data = request.json  # expecting a list of invoice IDs
    invoice_ids = data.get('invoice_ids', [])

    if not invoice_ids:
        return jsonify({'error': 'No invoices selected'}), 400

    # Optionally, store them in session or temp table
    session['selected_invoice_ids'] = invoice_ids

    # Redirect frontend to review page
    return jsonify({'redirect_url': url_for('finance_web_bp.verify_insurance_claims')})


@finance_web_bp.route('/verify-insurance-claims')
def verify_insurance_claims():
    invoice_ids = session.get('selected_invoice_ids', [])
    if not invoice_ids:
        return redirect(url_for('all_invoices'))

    invoices = Invoice.query.filter(Invoice.id.in_(invoice_ids)).all()
    insurances = Insurance.query.all()

    return render_template('verify_claims.html', invoices=invoices, insurances=insurances)

@finance_web_bp.route('/download-insurance-pdf')
def download_insurance_pdf():
    # Collect invoice IDs from query string
    invoice_ids = request.args.getlist('invoice_ids', type=int)
    if not invoice_ids:
        flash("No invoices selected for PDF download.", "warning")
        return redirect(url_for('finance_web_bp.all_invoices'))

    # Query the invoices
    invoices = Invoice.query.filter(Invoice.id.in_(invoice_ids)).all()
    # … generate PDF (e.g. using WeasyPrint or ReportLab or wkhtmltopdf)
    # Let’s assume you have a helper `generate_insurance_pdf(invoices)` that returns a bytes stream.

    pdf_bytes = generate_insurance_pdf(invoices)
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': 'attachment; filename=insurance_claims_{}.pdf'.format(datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
        }
    )



from io import BytesIO
from weasyprint import HTML
from flask import current_app, render_template
from datetime import datetime
from collections import defaultdict
import os

@finance_web_bp.route('/confirm-insurance-submission', methods=['POST'])
def confirm_insurance_submission():
    print("\n===== STARTING INSURANCE SUBMISSION PROCESS =====")
    print(f"Request method: {request.method}")
    print(f"Form data: {request.form}")
    
    # Get form data from frontend
    subject = request.form.get('subject')
    message = request.form.get('message', '')
    invoice_ids = request.form.getlist('invoice_ids[]')
    
    print(f"\n--- FORM DATA ---")
    print(f"Subject: {subject}")
    print(f"Message: {message}")
    print(f"Invoice IDs: {invoice_ids}")
    
    invoices = Invoice.query.filter(Invoice.id.in_(invoice_ids)).all()
    print(f"\n--- INVOICES FOUND ---")
    print(f"Number of invoices: {len(invoices)}")
    for inv in invoices:
        print(f"  - Invoice #{inv.id} (Insurance: {inv.insurance.name if inv.insurance else 'None'})")

    # Group invoices by insurance
    insurance_groups = defaultdict(list)
    for inv in invoices:
        if inv.insurance:
            insurance_groups[inv.insurance_id].append(inv)
    
    print(f"\n--- INSURANCE GROUPS ---")
    print(f"Number of insurance groups: {len(insurance_groups)}")
    for insurance_id, insurance_invoices in insurance_groups.items():
        print(f"Insurance ID: {insurance_id}, Invoices: {len(insurance_invoices)}")

    # Process each insurance group
    for insurance_id, insurance_invoices in insurance_groups.items():
        print(f"\n--- PROCESSING INSURANCE GROUP {insurance_id} ---")
        insurance = Insurance.query.get(insurance_id)
        
        if not insurance:
            print(f"!! Insurance not found for ID: {insurance_id}")
            current_app.logger.warning(f"No insurance found for ID {insurance_id}")
            continue
            
        if not insurance.email:
            print(f"!! No email found for insurance: {insurance.name} (ID: {insurance.id})")
            current_app.logger.warning(f"No email found for insurance ID {insurance_id}")
            continue
            
        print(f"Processing insurance: {insurance.name} ({insurance.email})")
        print(f"Number of invoices: {len(insurance_invoices)}")
        
        # Generate merged PDF for all invoices in this group
        print("\nGenerating merged PDF...")
        merged_pdf = generate_merged_pdf(insurance_invoices)
        print(f"PDF generated ({len(merged_pdf.getvalue())} bytes)")
        
        # Send email with merged PDF
        print("\nAttempting to send email...")
        send_email_to_insurance(
            insurance, 
            insurance_invoices, 
            subject, 
            message,
            merged_pdf
        )
        
        # Update invoice statuses
        print("\nUpdating invoice statuses...")
        for inv in insurance_invoices:
            inv.status = 'insurance'
            print(f"  - Updated invoice #{inv.id} status to 'insurance'")
    
    print("\nCommitting database changes...")
    db.session.commit()
    print("Database changes committed")
    
    flash('Claims submitted to insurance successfully.', 'success')
    print("\n===== PROCESS COMPLETE - REDIRECTING =====")
    return redirect(url_for('finance_web_bp.invoices'))


def generate_merged_pdf(invoices):
    """Generate a merged PDF for all invoices with professional styling"""
    print("\n--- GENERATING MERGED PDF ---")
    
    # Get hospital details
    hospital = {
        'name': "AstroCare Medical Center",
        'address': "123 Health Street, Nairobi, Kenya",
        'phone': "+254 700 123 456",
        'email': "info@astrocare.com",
        'website': "www.astrocare.com",
        'logo': os.path.join(current_app.root_path, 'static', 'IMG_20241101_140627.jpg')
    }
    
    print(f"Hospital details: {hospital}")
    
    # Render HTML template with all invoices
    print("Rendering HTML template...")
    html = render_template(
        'insurance_claim_pdf.html',
        invoices=invoices,
        hospital=hospital,
        generated_date=datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    )
    
    # Generate PDF
    print("Generating PDF from HTML...")
    pdf_bytes = HTML(string=html).write_pdf()
    print("PDF generation complete")
    return BytesIO(pdf_bytes)


def send_email_to_insurance(insurance, invoices, subject, custom_message, merged_pdf):
    """Send email to insurance with merged PDF attachment"""
    print("\n===== SEND EMAIL TO INSURANCE =====")
    print(f"Insurance: {insurance.name} ({insurance.email})")
    print(f"Subject: {subject}")
    print(f"Custom message: {custom_message}")
    print(f"Number of invoices: {len(invoices)}")
    
    # Construct email body
    invoice_list = "\n".join(
        [f"- Invoice #{inv.id}: {inv.patient.full_name} (KES {inv.total_amount:.2f})" 
         for inv in invoices]
    )
    
    body = f"""
    Dear {insurance.name},

    Please find attached the insurance claims for the following invoices:
    
    {invoice_list}
    
    {custom_message}
    
    Regards,
    AstroCare Finance Team
    """
    
    print("\n--- EMAIL CONTENT ---")
    print(f"Body:\n{body}")
    
    # Create email with attachment
    msg = MIMEMultipart()
    msg['Subject'] = subject
    
    # Use configured sender or fallback with custom name
    sender_email = current_app.config.get('MAIL_DEFAULT_SENDER', 'finance@astrocare.com')
    # Create custom sender format: "Display Name <email@address.com>"
    sender = f"AstroCare Finance"
    msg['From'] = sender
    msg['To'] = insurance.email  # Use the actual insurance email
    
    print(f"\n--- EMAIL HEADERS ---")
    print(f"From: {sender}")
    print(f"To: {insurance.email}")
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Attach PDF
    merged_pdf.seek(0)
    pdf_content = merged_pdf.read()
    pdf_attachment = MIMEApplication(pdf_content, _subtype="pdf")
    filename = f"insurance_claims_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
    msg.attach(pdf_attachment)
    
    print(f"Attached PDF: {filename} ({len(pdf_content)} bytes)")
    
    # Check email configuration
    print("\n--- EMAIL CONFIGURATION ---")
    mail_server = current_app.config.get('MAIL_SERVER')
    mail_port = current_app.config.get('MAIL_PORT')
    mail_username = current_app.config.get('MAIL_USERNAME')
    mail_password = current_app.config.get('MAIL_PASSWORD')
    
    print(f"MAIL_SERVER: {mail_server}")
    print(f"MAIL_PORT: {mail_port}")
    print(f"MAIL_USERNAME: {mail_username}")
    print(f"MAIL_PASSWORD: {'*****' if mail_password else 'None'}")
    
    # Send email if configured, otherwise log
    if mail_server:
        print("\nAttempting to send email via SMTP...")
        try:
            print(f"Connecting to SMTP server: {mail_server}:{mail_port}")
            with smtplib.SMTP(mail_server, mail_port) as server:
                print("Starting TLS...")
                server.starttls()
                print("TLS started")
                
                if mail_username and mail_password:
                    print("Authenticating with SMTP server...")
                    server.login(mail_username, mail_password)
                    print("Authentication successful")
                
                print("Sending email...")
                server.send_message(msg)
                print("Email sent successfully")
            
            current_app.logger.info(f"Sent insurance claim to {insurance.email} with {len(invoices)} invoices")
            print(f"Email sent to {insurance.email}")
        except Exception as e:
            error_msg = f"Failed to send email to {insurance.email}: {str(e)}"
            current_app.logger.error(error_msg)
            print(f"!! ERROR: {error_msg}")
            print("Full traceback:")
            import traceback
            traceback.print_exc()
    else:
        # Log email instead of sending in development
        log_msg = (f"Would send email to {insurance.email}:\n"
                   f"Subject: {subject}\n"
                   f"Body:\n{body}\n"
                   f"With PDF attachment ({len(pdf_content)} bytes)")
        
        current_app.logger.info(log_msg)
        print("\n--- DEVELOPMENT MODE - LOGGING EMAIL ---")
        print(log_msg)
    
    print("===== EMAIL PROCESS COMPLETE =====")
    
# Payments Processing
@finance_web_bp.route('/payments')
def payments():
    return render_template('payments.html')

@finance_web_bp.route('/expenses')
def expenses():
    # Get filter parameters from request
    status = request.args.get('status', 'all')
    category_id = request.args.get('category_id', type=int)
    department_id = request.args.get('department_id', type=int)
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int, default=datetime.utcnow().year)
    priority = request.args.get('priority')
    
    # Base query
    query = Expense.query.options(
        joinedload(Expense.category),
        joinedload(Expense.department),
        joinedload(Expense.supplier),
        joinedload(Expense.initiator),
        joinedload(Expense.approver)
    )
    
    # Apply filters
    if status != 'all':
        query = query.filter(Expense.status == status)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if department_id:
        query = query.filter(Expense.department_id == department_id)
    if month:
        query = query.filter(db.extract('month', Expense.expense_date) == month)
    if year:
        query = query.filter(db.extract('year', Expense.expense_date) == year)
    if priority:
        query = query.filter(Expense.priority == priority)
    
    # Get expenses with related data
    expenses = query.order_by(Expense.expense_date.desc()).all()
    expenses_list = query.order_by(Expense.expense_date.desc()).all()

    # Format expenses for frontend
    formatted_expenses = []
    for expense in expenses:
        formatted_expenses.append({
            "id": expense.id,
            "expense_date": expense.expense_date.strftime('%Y-%m-%d'),
            "amount": f"{expense.currency} {expense.amount:,.2f}",
            "tax_amount": f"{expense.currency} {expense.tax_amount:,.2f}",
            "total": f"{expense.currency} {expense.amount + expense.tax_amount:,.2f}",
            "description": expense.description,
            "payment_method": expense.payment_method.capitalize(),
            "reference": expense.reference_number or "N/A",
            "category": expense.category.name,
            "department": expense.department.name,
            "supplier": expense.supplier.name if expense.supplier else "N/A",
            "initiator": expense.initiator.username,
            "approver": expense.approver.username if expense.approver else "Pending",
            "priority": expense.priority.capitalize(),
            "status": expense.status.capitalize(),
            "status_class": f"status-{expense.status}",
            "priority_class": f"priority-{expense.priority}",
            "expense_type": expense.expense_type.capitalize(),
            "budget_period": expense.budget_period or "Not specified",
            "notes": expense.notes or "",
            "payment_date": expense.payment_date.strftime('%Y-%m-%d') if expense.payment_date else "Unpaid"
        })
    
    # Calculate summary statistics - SAFE VERSION
    total_expenses = sum(e.amount for e in expenses_list) if expenses_list else 0
    medical_expenses = sum(
        e.amount for e in expenses_list 
        if e and e.category.name.lower() in ['pharmaceuticals', 'medical supplies']
    ) if expenses_list else 0
    pending_count = sum(
        1 for e in expenses_list 
        if e and e.status in ['draft', 'submitted']
    ) if expenses_list else 0
    
    current_month = datetime.utcnow().month
    current_year = datetime.utcnow().year
    current_month_expenses = sum(
        e.amount for e in expenses_list 
        if e and e.expense_date.month == current_month and e.expense_date.year == current_year
    ) if expenses_list else 0
    
    # Get filter options
    categories = ExpenseCategory.query.order_by(ExpenseCategory.name).all()
    departments = Department.query.order_by(Department.name).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    # Current year for filter
    current_year_val = datetime.utcnow().year
    
    return render_template(
        'expenses.html',
        expenses=formatted_expenses,
        categories=categories,
        departments=departments,
        suppliers=suppliers,
        status_options=['draft', 'submitted', 'approved', 'rejected', 'paid', 'audited'],
        priority_options=['low', 'medium', 'high', 'critical'],
        expense_types=['operational', 'capital', 'emergency'],
        months=[
            {'id': 1, 'name': 'January'}, {'id': 2, 'name': 'February'}, 
            {'id': 3, 'name': 'March'}, {'id': 4, 'name': 'April'},
            {'id': 5, 'name': 'May'}, {'id': 6, 'name': 'June'},
            {'id': 7, 'name': 'July'}, {'id': 8, 'name': 'August'},
            {'id': 9, 'name': 'September'}, {'id': 10, 'name': 'October'},
            {'id': 11, 'name': 'November'}, {'id': 12, 'name': 'December'}
        ],
        years=[current_year-1, current_year, current_year+1],
        current_year=current_year,
        current_month=datetime.utcnow().month,
        filter_params={
            'status': status,
            'category_id': category_id,
            'department_id': department_id,
            'month': month,
            'year': year,
            'priority': priority
        },
                total_expenses=total_expenses,
        medical_expenses=medical_expenses,
        pending_count=pending_count,
        current_month_expenses=current_month_expenses,
        current_month_name=datetime.utcnow().strftime('%B'),
        currency='KES'  # Or get from config
    )


@finance_web_bp.route('/expense/<int:expense_id>/pay', methods=['GET', 'POST'])
@login_required
def pay_expense(expense_id):
    from app.finance.models import BankAccount, CashAccount, BankTransaction, CashTransaction
    expense = Expense.query.get_or_404(expense_id)

    if expense.status != 'submitted':
        flash('Only approved expenses can be paid.', 'danger')
        return redirect(url_for('finance_web_bp.expenses'))

    if request.method == 'POST':
        supplier_receipt = request.form.get('supplier_receipt', '').strip()
        payment_ref = request.form.get('payment_ref', '').strip()
        notes = request.form.get('notes', '').strip()

        account_id = expense.account_id
        account_type = expense.account_type

        if not account_id or not account_type:
            flash('No account linked to this expense. Please edit expense and select an account.', 'danger')
            return redirect(url_for('finance_web_bp.expenses'))

        try:
            if account_type == 'bank':
                bank = BankAccount.query.get(account_id)
                if not bank or not bank.is_active:
                    raise ValueError("Bank account not found or inactive.")
                if bank.current_balance < expense.amount:
                    raise ValueError("Insufficient balance in selected bank account.")

                tx = BankTransaction(
                    bank_account_id=bank.id,
                    transaction_type='withdrawal',
                    amount=expense.amount,
                    description=f"Payment for expense #{expense.id}: {expense.description}",
                    reference=payment_ref or expense.reference_number,
                    created_by=current_user.id
                )
                db.session.add(tx)
                bank.current_balance -= expense.amount

            elif account_type == 'cash':
                cash = CashAccount.query.get(account_id)
                if not cash or not cash.is_active:
                    raise ValueError("Cash account not found or inactive.")
                if cash.current_balance < expense.amount:
                    raise ValueError("Insufficient balance in selected cash account.")

                tx = CashTransaction(
                    transaction_type='withdrawal',
                    amount=expense.amount,
                    description=f"Payment for expense #{expense.id}: {expense.description}",
                    source_cash_account_id=cash.id,
                    status='completed',
                    completed_at=datetime.utcnow(),
                    external_reference=payment_ref or expense.receipt_number,
                    initiated_by=current_user.id
                )
                tx.transaction_ref = tx.generate_ref()
                db.session.add(tx)
                cash.current_balance -= expense.amount

            else:
                flash('Invalid account type.', 'danger')
                return redirect(url_for('finance_web_bp.expenses'))

            # Update expense
            expense.status = 'paid'
            expense.payment_date = datetime.utcnow()
            if supplier_receipt:
                expense.receipt_number = supplier_receipt
            # Optionally store payment reference in notes or a new field (if you add one)
            expense.notes = (expense.notes or '') + f"\nPayment processed by {current_user.full_name} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}. Payment ref: {payment_ref or 'N/A'}"
            db.session.commit()

            flash(f'Expense #{expense.id} paid successfully.', 'success')
            return redirect(url_for('finance_web_bp.expenses'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error processing payment: {str(e)}', 'danger')
            return redirect(url_for('finance_web_bp.pay_expense', expense_id=expense.id))

    # GET request – show form
    account = None
    if expense.account_type == 'bank':
        account = BankAccount.query.get(expense.account_id)
    elif expense.account_type == 'cash':
        account = CashAccount.query.get(expense.account_id)

    return render_template(
        'pay_expense.html',
        expense=expense,
        account=account
    )


@finance_web_bp.route('/expense/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    # Optional: restrict editing to certain statuses
    if expense.status not in ['draft', 'submitted']:
        flash('Expenses that are approved or paid cannot be edited.', 'danger')
        return redirect(url_for('finance_web_bp.expenses'))

    # Get same form data as new_expense
    categories = ExpenseCategory.query.order_by(ExpenseCategory.name).all()
    departments = Department.query.order_by(Department.name).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()
    cash_accounts = CashAccount.query.filter_by(is_active=True).all()
    payment_methods = ['Bank Transfer', 'Cheque', 'Cash', 'Mobile Money', 'Credit Card']
    expense_types = ['operational', 'capital', 'emergency']
    priority_levels = ['low', 'medium', 'high', 'critical']

    if request.method == 'POST':
        # Update expense with form data (similar to new)
        try:
            expense.expense_date = datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d')
            expense.description = request.form.get('description')
            expense.amount = float(request.form.get('amount'))
            expense.category_id = int(request.form.get('category_id'))
            expense.department_id = int(request.form.get('department_id'))
            expense.supplier_id = int(request.form.get('supplier_id')) if request.form.get('supplier_id') else None
            expense.payment_method = request.form.get('payment_method')
            expense.expense_type = request.form.get('expense_type')
            expense.priority = request.form.get('priority')
            expense.notes = request.form.get('notes')
            expense.account_type = request.form.get('account_type')
            expense.account_id = int(request.form.get('account_id')) if request.form.get('account_id') else None
            expense.receipt_number = request.form.get('receipt_number')
            expense.calculate_tax()

            db.session.commit()
            flash('Expense updated successfully.', 'success')
            return redirect(url_for('finance_web_bp.expenses'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating expense: {str(e)}', 'danger')

    return render_template(
        'edit_expense.html',
        expense=expense,
        categories=categories,
        departments=departments,
        suppliers=suppliers,
        bank_accounts=bank_accounts,
        cash_accounts=cash_accounts,
        payment_methods=payment_methods,
        expense_types=expense_types,
        priority_levels=priority_levels,
        current_date=expense.expense_date.strftime('%Y-%m-%d')
    )

@finance_web_bp.route('/cash/reports')
def financial_report():
    # Calculate time periods
    today = datetime.today().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)
    end_of_week = start_of_week + timedelta(days=7)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1)
    end_of_year = start_of_year.replace(year=start_of_year.year+1)
    
    # Helper function to format currency
    def format_currency(value):
        return "{:,.2f}".format(value) if value else "0.00"
    
    # Get only cash invoices
    cash_invoices = Invoice.query.filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid'
    )
    
    # Daily totals
    daily_invoices = cash_invoices.filter(
        func.date(Invoice.issue_date) == today
    )
    daily_transactions = daily_invoices.count()
    daily_total = db.session.query(
        func.sum(Invoice.total_amount)
    ).filter(
        func.date(Invoice.issue_date) == today,
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid'
    ).scalar() or 0.0
    
    # Weekly totals
    weekly_invoices = cash_invoices.filter(
        Invoice.issue_date >= start_of_week,
        Invoice.issue_date < end_of_week
    )
    weekly_transactions = weekly_invoices.count()
    weekly_total = weekly_invoices.with_entities(
        func.sum(Invoice.total_amount)
    ).scalar() or 0.0
    
    # Monthly totals
    monthly_invoices = cash_invoices.filter(
        Invoice.issue_date >= start_of_month,
        Invoice.issue_date < end_of_month
    )
    monthly_transactions = monthly_invoices.count()
    monthly_total = monthly_invoices.with_entities(
        func.sum(Invoice.total_amount)
    ).scalar() or 0.0
    
    # Yearly totals
    yearly_invoices = cash_invoices.filter(
        Invoice.issue_date >= start_of_year,
        Invoice.issue_date < end_of_year
    )
    yearly_transactions = yearly_invoices.count()
    yearly_total = yearly_invoices.with_entities(
        func.sum(Invoice.total_amount)
    ).scalar() or 0.0
    
    # Revenue trend (last 7 days)
    trend_dates = []
    trend_values = []
    for i in range(29, -1, -1):
        date_val = today - timedelta(days=i)
        trend_dates.append(date_val.strftime("%b %d"))
        
        daily_revenue = db.session.query(
            func.sum(Invoice.total_amount)
        ).filter(
            Invoice.invoice_type == 'cash',
            Invoice.status == 'paid',
            func.date(Invoice.issue_date) == date_val
        ).scalar() or 0.0
        trend_values.append(daily_revenue)
    
    # Revenue by category
    category_revenue = db.session.query(
        Service.category,
        func.sum(InvoiceItem.total_price).label('total_revenue')
    ).join(InvoiceItem, InvoiceItem.service_id == Service.id)\
     .join(Invoice, InvoiceItem.invoice_id == Invoice.id)\
     .filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid',
        Invoice.issue_date >= start_of_month
    ).group_by(Service.category).all()
    
    category_labels = [cat[0] for cat in category_revenue] if category_revenue else []
    category_values = [cat[1] for cat in category_revenue] if category_revenue else []
    
    # Service breakdown (all time by default)
    service_breakdown = db.session.query(
        Service.name,
        Service.category,
        func.count(InvoiceItem.id).label('transaction_count'),
        func.sum(InvoiceItem.total_price).label('total_revenue'),
        func.avg(InvoiceItem.total_price).label('avg_revenue')
    ).join(InvoiceItem, InvoiceItem.service_id == Service.id)\
     .join(Invoice, InvoiceItem.invoice_id == Invoice.id)\
     .filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid'
    ).group_by(Service.id).order_by(func.sum(InvoiceItem.total_price).desc()).all()
    
    # Recent cash invoices
    recent_invoices = cash_invoices.order_by(
        Invoice.issue_date.desc()
    ).limit(10).all()
    
    
    return render_template(
        'financial_report.html',
        daily_total=daily_total,
        daily_transactions=daily_transactions,
        weekly_total=weekly_total,
        weekly_transactions=weekly_transactions,
        monthly_total=monthly_total,
        monthly_transactions=monthly_transactions,
        yearly_total=yearly_total,
        yearly_transactions=yearly_transactions,
        trend_dates=trend_dates,
        trend_values=trend_values,
        category_labels=category_labels,
        category_values=category_values,
        service_breakdown=service_breakdown,
        recent_invoices=recent_invoices
    )




@finance_web_bp.route('/cash/reports/data')
def financial_report_data():
    # Calculate time periods
    today = datetime.today().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)
    end_of_week = start_of_week + timedelta(days=7)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1)
    end_of_year = start_of_year.replace(year=start_of_year.year+1)
    
    # Get parameters from request
    period = request.args.get('period', '7')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    breakdown_period = request.args.get('breakdown_period', 'weekly')
    
    # Convert to date objects if provided
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Daily totals
    daily_query = Invoice.query.filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid',
        func.date(Invoice.issue_date) == today
    )
    daily_transactions = daily_query.count()
    daily_total = daily_query.with_entities(
        func.sum(Invoice.total_amount)
    ).scalar() or 0.0
    
    # Weekly totals
    weekly_query = Invoice.query.filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid',
        Invoice.issue_date >= start_of_week,
        Invoice.issue_date < end_of_week
    )
    weekly_transactions = weekly_query.count()
    weekly_total = weekly_query.with_entities(
        func.sum(Invoice.total_amount)
    ).scalar() or 0.0
    
    # Monthly totals
    monthly_query = Invoice.query.filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid',
        Invoice.issue_date >= start_of_month,
        Invoice.issue_date < end_of_month
    )
    monthly_transactions = monthly_query.count()
    monthly_total = monthly_query.with_entities(
        func.sum(Invoice.total_amount)
    ).scalar() or 0.0
    
    # Yearly totals
    yearly_query = Invoice.query.filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid',
        Invoice.issue_date >= start_of_year,
        Invoice.issue_date < end_of_year
    )
    yearly_transactions = yearly_query.count()
    yearly_total = yearly_query.with_entities(
        func.sum(Invoice.total_amount)
    ).scalar() or 0.0
    
    # Determine date range for trend
    if start_date and end_date:
        trend_start = start_date
        trend_end = end_date
    else:
        period_days = int(period)
        trend_start = today - timedelta(days=period_days-1)
        trend_end = today
    
    # Revenue trend
    trend_dates = []
    trend_values = []
    current_date = trend_start
    
    while current_date <= trend_end:
        trend_dates.append(current_date.strftime("%b %d"))
        
        daily_revenue = db.session.query(
            func.sum(Invoice.total_amount)
        ).filter(
            Invoice.invoice_type == 'cash',
            Invoice.status == 'paid',
            func.date(Invoice.issue_date) == current_date
        ).scalar() or 0.0
        trend_values.append(daily_revenue)
        
        current_date += timedelta(days=1)
    
    # Determine date range for service breakdown
    if breakdown_period == 'daily':
        breakdown_start = today
        breakdown_end = today + timedelta(days=1)
    elif breakdown_period == 'weekly':
        breakdown_start = start_of_week
        breakdown_end = end_of_week
    elif breakdown_period == 'monthly':
        breakdown_start = start_of_month
        breakdown_end = end_of_month
    else:  # yearly
        breakdown_start = start_of_year
        breakdown_end = end_of_year
    
    # Service breakdown
    service_breakdown = db.session.query(
        Service.name,
        Service.category,
        func.count(InvoiceItem.id).label('transaction_count'),
        func.sum(InvoiceItem.total_price).label('total_revenue'),
        func.avg(InvoiceItem.total_price).label('avg_revenue')
    ).join(InvoiceItem, InvoiceItem.service_id == Service.id)\
     .join(Invoice, InvoiceItem.invoice_id == Invoice.id)\
     .filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid',
        Invoice.issue_date >= breakdown_start,
        Invoice.issue_date < breakdown_end
    ).group_by(Service.id).order_by(func.sum(InvoiceItem.total_price).desc()).all()
    
    # Convert to dictionary format for JSON
    service_breakdown_data = [{
        'name': s.name,
        'category': s.category,
        'transaction_count': s.transaction_count,
        'total_revenue': float(s.total_revenue) if s.total_revenue else 0.0,
        'avg_revenue': float(s.avg_revenue) if s.avg_revenue else 0.0
    } for s in service_breakdown]
    
    # Revenue by category
    category_revenue = db.session.query(
        Service.category,
        func.sum(InvoiceItem.total_price).label('total_revenue')
    ).join(InvoiceItem, InvoiceItem.service_id == Service.id)\
     .join(Invoice, InvoiceItem.invoice_id == Invoice.id)\
     .filter(
        Invoice.invoice_type == 'cash',
        Invoice.status == 'paid',
        Invoice.issue_date >= breakdown_start,
        Invoice.issue_date < breakdown_end
    ).group_by(Service.category).all()
    
    category_labels = [cat[0] for cat in category_revenue] if category_revenue else []
    category_values = [float(cat[1]) if cat[1] else 0.0 for cat in category_revenue] if category_revenue else []
    
    return jsonify({
        'daily_total': daily_total,
        'daily_transactions': daily_transactions,
        'weekly_total': weekly_total,
        'weekly_transactions': weekly_transactions,
        'monthly_total': monthly_total,
        'monthly_transactions': monthly_transactions,
        'yearly_total': yearly_total,
        'yearly_transactions': yearly_transactions,
        'trend_dates': trend_dates,
        'trend_values': trend_values,
        'category_labels': category_labels,
        'category_values': category_values,
        'service_breakdown': service_breakdown_data
    })
@finance_web_bp.route('/insurance')
def insurance():
    # Fetch all policies
    insurances = Insurance.query.order_by(Insurance.created_at.desc()).all()

    # Count active policies
    active_insurances = sum(1 for i in insurances if i.coverage_status == 'Active')

    # Count “expiring soon” (within 30 days)
    today = datetime.utcnow().date()
    expiring_threshold = today + timedelta(days=30)
    expiring_soon = sum(
        1
        for i in insurances
        if i.coverage_end_date
        and today < i.coverage_end_date <= expiring_threshold
    )

    # Pass `today` into the template as `current_date`
    return render_template(
        'insurance.html',
        insurances=insurances,
        active_insurances=active_insurances,
        expiring_soon=expiring_soon,
        current_date=today
    )


@finance_web_bp.route('/insurance/create')
def create_insurance():
    return render_template('create_insurance.html')

@finance_web_bp.route('/insurance/store', methods=['POST'])
def store_insurance():
    # --- 1) Read form values ---
    name           = request.form.get('name', '').strip()
    policy_number  = request.form.get('policy_number', '').strip()
    insurance_type = request.form.get('insurance_type', '').strip()
    start_str      = request.form.get('coverage_start_date', '').strip()
    end_str        = request.form.get('coverage_end_date', '').strip()
    is_active      = True if request.form.get('is_active') == 'on' else False
    max_coverage_raw = request.form.get('max_coverage_amount', '').strip()
    deductible_raw   = request.form.get('deductible', '').strip()
    contact_number   = request.form.get('contact_number', '').strip() or None
    email            = request.form.get('email', '').strip() or None
    website          = request.form.get('website', '').strip() or None
    address          = request.form.get('address', '').strip() or None
    city             = request.form.get('city', '').strip() or None
    state            = request.form.get('state', '').strip() or None
    country          = request.form.get('country', '').strip() or None

    # --- 2) Validate required fields ---
    if not name:
        flash('Provider Name is required.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))
    if not policy_number:
        flash('Policy Number is required.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))
    if not insurance_type:
        flash('Please select an Insurance Type.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))
    if not start_str:
        flash('Coverage Start Date is required.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))

    # --- 3) Parse dates ---
    try:
        coverage_start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid format for Coverage Start Date. Use YYYY-MM-DD.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))

    if end_str:
        try:
            coverage_end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid format for Coverage End Date. Use YYYY-MM-DD.', 'error')
            return redirect(url_for('finance_web_bp.insurance_new', **request.form))
    else:
        coverage_end_date = None

    # --- 4) Convert numeric fields (if provided) ---
    try:
        max_coverage = float(max_coverage_raw) if max_coverage_raw else None
    except ValueError:
        flash('Max Coverage must be a valid number.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))

    try:
        deductible = float(deductible_raw) if deductible_raw else None
    except ValueError:
        flash('Deductible must be a valid number.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))

    # --- 5) Build the new Insurance object ---
    new_insurance = Insurance(
        name=name,
        policy_number=policy_number,
        insurance_type=insurance_type,
        coverage_start_date=coverage_start_date,
        coverage_end_date=coverage_end_date,
        is_active=is_active,
        max_coverage_amount=max_coverage,
        deductible=deductible,
        contact_number=contact_number,
        email=email,
        website=website,
        address=address,
        city=city,
        state=state,
        country=country
    )

    # --- 6) Attempt to save, catching integrity or other DB errors ---
    try:
        db.session.add(new_insurance)
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        # Assume policy_number uniqueness violation
        if 'ix_policy_number' in str(e.orig).lower() or 'unique constraint' in str(e.orig).lower():
            flash(f'Policy Number "{policy_number}" already exists. Choose a different one.', 'error')
        else:
            flash('An unexpected database error occurred. Please try again.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))
    except Exception:
        db.session.rollback()
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('finance_web_bp.insurance_new', **request.form))

    # --- 7) On success, flash a message and redirect to listing ---
    flash('Insurance policy created successfully!', 'success')
    return redirect(url_for('finance_web_bp.insurance'))


@finance_web_bp.route('/insurance/<int:insurance_id>/add-services', methods=['GET', 'POST'])
def add_services(insurance_id):
    insurance = Insurance.query.get_or_404(insurance_id)
    services = Service.query.all()
    
    if request.method == 'POST':
        # Process form data and create InsuranceService entries
        pass
    
    return render_template('add_services.html', 
                         insurance=insurance,
                         services=services)



@finance_web_bp.route('/insurance/<int:insurance_id>/manage-services', methods=['GET', 'POST'])
def manage_services(insurance_id):
    """
    GET:  Display a list of all available Services and mark which ones this policy already covers.
    POST: Add or update coverage entries (InsuranceService) for the given insurance_id.
    """
    insurance = Insurance.query.get_or_404(insurance_id)
    all_services = Service.query.order_by(Service.name).all()

    # Fetch existing coverage entries as a dict keyed by service_id
    existing_coverage = {
        cov.service_id: cov
        for cov in insurance.covered_services
    }

    if request.method == 'POST':
        # The form is expected to send one row per service ID, for example:
        #   service_id[]=3, copay_3=20.00, coverage_pct_3=80, annual_limit_3=5000, is_covered_3=on, notes_3=…
        #   service_id[]=5, copay_5=0.00, coverage_pct_5=100, annual_limit_5=10000, is_covered_5=, notes_5=…
        #
        # Under this convention, the template needs to output inputs named like:
        #   <input type="hidden" name="service_id[]" value="{{ service.id }}">
        #   <input type="number" name="copay_{{ service.id }}" … >
        #   <input type="number" name="coverage_pct_{{ service.id }}" … >
        #   <input type="number" name="annual_limit_{{ service.id }}" … >
        #   <input type="checkbox" name="is_covered_{{ service.id }}" … >
        #   <textarea name="notes_{{ service.id }}" …></textarea>
        #
        # Then we loop over request.form.getlist('service_id[]') to process each row.

        service_ids = request.form.getlist('service_id[]')
        try:
            for sid_str in service_ids:
                sid = int(sid_str)
                # Read each field for this service:
                copay_raw = request.form.get(f'copay_{sid}', '').strip()
                pct_raw   = request.form.get(f'coverage_pct_{sid}', '').strip()
                limit_raw = request.form.get(f'annual_limit_{sid}', '').strip()
                covered   = True if request.form.get(f'is_covered_{sid}') == 'on' else False
                notes     = request.form.get(f'notes_{sid}', '').strip() or None

                # Convert to floats/ints as needed (or set None)
                copay = float(copay_raw) if copay_raw != '' else None
                coverage_pct = float(pct_raw) if pct_raw != '' else None
                annual_limit = float(limit_raw) if limit_raw != '' else None

                svc = all_services and next((s for s in all_services if s.id == sid), None)
                if not svc:
                    # Skip unknown service IDs
                    continue

                # Determine service_category (you might store it on Service model)
                service_category = svc.category if hasattr(svc, 'category') else svc.name

                if sid in existing_coverage:
                    # Update existing InsuranceService
                    cov_entry = existing_coverage[sid]
                    cov_entry.copay = copay
                    cov_entry.coverage_percentage = coverage_pct
                    cov_entry.annual_limit = annual_limit
                    cov_entry.is_covered = covered
                    cov_entry.coverage_notes = notes
                    cov_entry.service_category = service_category
                    db.session.add(cov_entry)
                else:
                    # Create a new InsuranceService record
                    new_cov = InsuranceService(
                        insurance_id=insurance.id,
                        service_id=sid,
                        copay=copay,
                        coverage_percentage=coverage_pct,
                        annual_limit=annual_limit,
                        requires_prior_authorization=False,  # or adjust if your form includes this
                        is_covered=covered,
                        coverage_notes=notes,
                        service_category=service_category
                    )
                    db.session.add(new_cov)

            db.session.commit()
            flash('Coverage services updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error saving coverage services. Please try again.', 'error')

        return redirect(url_for('finance_web_bp.manage_services', insurance_id=insurance.id))

    # GET: render the “Manage Services” form
    return render_template(
        'manage_services.html',
        insurance=insurance,
        all_services=all_services,
        existing_coverage=existing_coverage
    )


@finance_web_bp.route('/insurance/<int:insurance_id>/edit', methods=['GET', 'POST'])
def edit_insurance(insurance_id):
    """
    GET:  Render a form prefilled with Insurance data so the user can update it.
    POST: Validate incoming data and write changes back to that Insurance record.
    """
    insurance = Insurance.query.get_or_404(insurance_id)

    if request.method == 'POST':
        # --- 1) Read updated values ---
        name           = request.form.get('name', '').strip()
        policy_number  = request.form.get('policy_number', '').strip()
        insurance_type = request.form.get('insurance_type', '').strip()
        start_str      = request.form.get('coverage_start_date', '').strip()
        end_str        = request.form.get('coverage_end_date', '').strip()
        is_active      = True if request.form.get('is_active') == 'on' else False
        max_cov_raw    = request.form.get('max_coverage_amount', '').strip()
        deduct_raw     = request.form.get('deductible', '').strip()
        contact_number = request.form.get('contact_number', '').strip() or None
        email          = request.form.get('email', '').strip() or None
        website        = request.form.get('website', '').strip() or None
        address        = request.form.get('address', '').strip() or None
        city           = request.form.get('city', '').strip() or None
        state          = request.form.get('state', '').strip() or None
        country        = request.form.get('country', '').strip() or None

        # --- 2) Validate required fields (same as store_insurance) ---
        if not name:
            flash('Provider Name is required.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))
        if not policy_number:
            flash('Policy Number is required.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))
        if not insurance_type:
            flash('Please select an Insurance Type.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))
        if not start_str:
            flash('Coverage Start Date is required.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))

        # --- 3) Parse dates ---
        try:
            coverage_start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid format for Coverage Start Date. Use YYYY-MM-DD.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))

        if end_str:
            try:
                coverage_end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid format for Coverage End Date. Use YYYY-MM-DD.', 'error')
                return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))
        else:
            coverage_end_date = None

        # --- 4) Convert numeric fields ---
        try:
            max_coverage = float(max_cov_raw) if max_cov_raw else None
        except ValueError:
            flash('Max Coverage must be a valid number.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))

        try:
            deductible = float(deduct_raw) if deduct_raw else None
        except ValueError:
            flash('Deductible must be a valid number.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))

        # --- 5) Apply changes to the model instance ---
        insurance.name = name
        insurance.policy_number = policy_number
        insurance.insurance_type = insurance_type
        insurance.coverage_start_date = coverage_start_date
        insurance.coverage_end_date = coverage_end_date
        insurance.is_active = is_active
        insurance.max_coverage_amount = max_coverage
        insurance.deductible = deductible
        insurance.contact_number = contact_number
        insurance.email = email
        insurance.website = website
        insurance.address = address
        insurance.city = city
        insurance.state = state
        insurance.country = country

        # --- 6) Commit updates ---
        try:
            db.session.commit()
            flash('Insurance policy updated successfully.', 'success')
        except IntegrityError as e:
            db.session.rollback()
            if 'ix_policy_number' in str(e.orig).lower() or 'unique constraint' in str(e.orig).lower():
                flash(f'Policy Number "{policy_number}" already exists. Choose a different one.', 'error')
            else:
                flash('An unexpected database error occurred. Please try again.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))
        except Exception:
            db.session.rollback()
            flash('An unexpected error occurred while updating. Please try again.', 'error')
            return redirect(url_for('finance_web_bp.edit_insurance', insurance_id=insurance.id))

        # --- 7) Redirect back to the main list ---
        return redirect(url_for('finance_web_bp.insurance'))

    # GET: render the “Edit Insurance” form with data prefilled
    return render_template(
        'edit_insurance.html',
        insurance=insurance
    )


@finance_web_bp.route('/manage-service-prices')
def manage_services_prices():
    """
    List all services with current pricing. Also pass distinct categories
    for the filter dropdown.
    """
    # Fetch all active/inactive services, ordered by name
    services = Service.query.order_by(Service.name).all()

    # Distinct list of categories for the filter
    categories = (
        db.session
        .query(Service.category)
        .distinct()
        .order_by(Service.category)
        .all()
    )
    # `categories` is a list of tuples like [('Consultation',), ('Lab',), ...]
    categories = [c[0] for c in categories]

    return render_template(
        'manage_services_prices.html',
        services=services,
        categories=categories
    )


@finance_web_bp.route('/manage-service-prices/add', methods=['GET', 'POST'])
def add_service_price():
    """
    GET: Show empty form to create a new service.
    POST: Validate input, insert a new Service, then redirect back to list.
    """
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '').strip()
        walkin_price = request.form.get('walkin_price', '').strip()  # New field
        special_clinic_price = request.form.get('special_clinic_price', '').strip()  # New field
        duration = request.form.get('duration', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Basic validation
        if not name or not category or not price:
            flash('Name, category, and price are required.', 'danger')
            return redirect(url_for('finance_web_bp.add_service_price'))

        try:
            price_val = float(price)
        except ValueError:
            flash('Price must be a valid number.', 'danger')
            return redirect(url_for('finance_web_bp.add_service_price'))

        # Validate walkin_price
        try:
            walkin_price_val = float(walkin_price) if walkin_price else 0.0
        except ValueError:
            flash('Walk-in price must be a valid number.', 'danger')
            return redirect(url_for('finance_web_bp.add_service_price'))

        # Validate special_clinic_price
        try:
            special_clinic_price_val = float(special_clinic_price) if special_clinic_price else 0.0
        except ValueError:
            flash('Special clinic price must be a valid number.', 'danger')
            return redirect(url_for('finance_web_bp.add_service_price'))

        try:
            duration_val = int(duration) if duration else None
        except ValueError:
            flash('Duration must be an integer.', 'danger')
            return redirect(url_for('finance_web_bp.add_service_price'))

        new_service = Service(
            name=name,
            category=category,
            description=description or None,
            price=price_val,
            walkin_price=walkin_price_val,  # New field
            special_clinic_price=special_clinic_price_val,  # New field
            duration=duration_val,
            is_active=is_active
        )

        try:
            db.session.add(new_service)
            db.session.commit()
            flash(f'Service "{name}" created successfully.', 'success')
            return redirect(url_for('finance_web_bp.manage_services_prices'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception("Error adding new service")
            flash('An error occurred while creating the service. '
                  'It may already exist.', 'danger')
            return redirect(url_for('finance_web_bp.add_service_price'))

    # GET: render blank form
    # Pass existing categories so the user can pick or type a new one.
    categories = (
        db.session
        .query(Service.category)
        .distinct()
        .order_by(Service.category)
        .all()
    )
    categories = [c[0] for c in categories]

    return render_template(
        'service_form.html',
        action='add',
        service=None,
        categories=categories
    )


@finance_web_bp.route('/manage-service-prices/<int:service_id>/edit', methods=['GET', 'POST'])
def edit_service_price(service_id):
    """
    GET: Load the existing Service and show its data in a form.
    POST: Validate input and update the Service row.
    """
    service = Service.query.get_or_404(service_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '').strip()
        walkin_price = request.form.get('walkin_price', '').strip()  # New field
        special_clinic_price = request.form.get('special_clinic_price', '').strip()  # New field
        duration = request.form.get('duration', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Basic validation
        if not name or not category or not price:
            flash('Name, category, and price are required.', 'danger')
            return redirect(url_for(
                'finance_web_bp.edit_service_price',
                service_id=service.id
            ))

        try:
            price_val = float(price)
        except ValueError:
            flash('Price must be a valid number.', 'danger')
            return redirect(url_for(
                'finance_web_bp.edit_service_price',
                service_id=service.id
            ))

        # Validate walkin_price
        try:
            walkin_price_val = float(walkin_price) if walkin_price else 0.0
        except ValueError:
            flash('Walk-in price must be a valid number.', 'danger')
            return redirect(url_for(
                'finance_web_bp.edit_service_price',
                service_id=service.id
            ))

        # Validate special_clinic_price
        try:
            special_clinic_price_val = float(special_clinic_price) if special_clinic_price else 0.0
        except ValueError:
            flash('Special clinic price must be a valid number.', 'danger')
            return redirect(url_for(
                'finance_web_bp.edit_service_price',
                service_id=service.id
            ))

        try:
            duration_val = int(duration) if duration else None
        except ValueError:
            flash('Duration must be an integer.', 'danger')
            return redirect(url_for(
                'finance_web_bp.edit_service_price',
                service_id=service.id
            ))

        # Apply updates
        service.name = name
        service.category = category
        service.description = description or None
        service.price = price_val
        service.walkin_price = walkin_price_val  # New field
        service.special_clinic_price = special_clinic_price_val  # New field
        service.duration = duration_val
        service.is_active = is_active

        try:
            db.session.commit()
            flash(f'Service "{service.name}" updated successfully.', 'success')
            return redirect(url_for('finance_web_bp.manage_services_prices'))
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Error updating service")
            flash('An error occurred while updating the service.', 'danger')
            return redirect(url_for(
                'finance_web_bp.edit_service_price',
                service_id=service.id
            ))

    # GET: render form pre-filled with existing values
    categories = (
        db.session
        .query(Service.category)
        .distinct()
        .order_by(Service.category)
        .all()
    )
    categories = [c[0] for c in categories]

    return render_template(
        'service_form.html',
        action='edit',
        service=service,
        categories=categories
    )


@finance_web_bp.route('/manage-service-prices/<int:service_id>/delete', methods=['POST'])
def delete_service_price(service_id):
    """
    Deletes the specified Service and all related InsuranceService rows.
    Returns JSON for AJAX calls.
    """
    # 1) Fetch the Service; if not found, return 404 automatically
    service = Service.query.get_or_404(service_id)

    try:
        # 2) Delete any InsuranceService rows that reference this service
        InsuranceService.query.filter_by(service_id=service.id).delete()
        db.session.flush()  # ensure deletion is sent to the DB

        # 3) Now delete the Service itself
        db.session.delete(service)
        db.session.commit()

        return jsonify({'success': True}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("Error deleting service and related insurance_services")
        return jsonify({'success': False, 'error': 'Could not delete service.'}), 500



@finance_web_bp.route('/manage-orders')
def manage_orders():
    try:
        # Fetch requisitions with their orders, ordered by urgency
        requisitions = (
            Requisition.query
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
            supplier_groups = {}
            
            for order in requisition.external_orders:
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
                
                # Group by supplier for LPO generation
                supplier_id = order.supplier_id if order.supplier else None
                if supplier_id not in supplier_groups:
                    supplier_groups[supplier_id] = {
                        'supplier': order.supplier,
                        'orders': [],
                        'total_amount': 0,
                        'item_count': 0
                    }
                supplier_groups[supplier_id]['orders'].append(order)
                supplier_groups[supplier_id]['total_amount'] += order.total_price
                supplier_groups[supplier_id]['item_count'] += 1
            
            # Attach processed orders and supplier groups to requisition
            requisition.processed_orders = orders_with_info
            requisition.supplier_groups = supplier_groups
            requisitions_with_info.append(requisition)
        
        # Get currency from config
        currency = current_app.config.get('CURRENCY', 'Ksh')
        
        return render_template('manage_orders.html', 
                              requisitions=requisitions_with_info,
                              currency=currency,
                              now=now)
    
    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error fetching orders: {str(e)}")
        flash('An error occurred while fetching orders. Please try again.', 'error')
        return redirect(url_for('finance_web_bp.financial_dashboard'))




@finance_web_bp.route('/approve-order/<int:order_id>')
def approve_order(order_id):
    try:
        order = ExternalOrder.query.get_or_404(order_id)

        # If already fully approved
        if order.status == 'director_approved':
            flash('This requisition is already fully approved.', 'info')
            return redirect(url_for('finance_web_bp.manage_orders'))

        # Finance approval step
        if not order.finance_approved:
            order.finance_approved = True
            order.finance_approved_at = datetime.utcnow()
            order.finance_approved_by = current_user.id
            order.status = 'finance_approved'
            flash(f'Requisition #{order.id} approved by Finance.', 'success')

        else:
            flash('Finance has already approved this requisition.', 'warning')

        db.session.commit()
        return redirect(url_for('finance_web_bp.manage_orders'))

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving order {order_id}: {str(e)}")
        flash('An error occurred while approving the order. Please try again.', 'error')
        return redirect(url_for('finance_web_bp.manage_orders'))


@finance_web_bp.route('/reject-order/<int:order_id>')
def reject_order(order_id):
    try:
        order = ExternalOrder.query.get_or_404(order_id)
        
        # Ensure order is pending
        if order.status != 'pending':
            flash('Only pending orders can be rejected', 'warning')
            return redirect(url_for('finance_web_bp.manage_orders'))
        
        # Update order status
        order.status = 'rejected'
        order.updated_at = datetime.utcnow()
        
        # Add audit trail note
        # audit_trail.add(f"Order rejected by {current_user.username}")
        
        db.session.commit()
        
        # Send notification (optional)
        # notification.send(
        #     f"Your requisition #{order.id} has been rejected",
        #     recipients=[order.user.email]
        # )
        
        flash(f'Requisition #{order.id} has been rejected', 'info')
        return redirect(url_for('finance_web_bp.manage_orders'))
    
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Error rejecting order {order_id}: {str(e)}")
        flash('An error occurred while rejecting the order. Please try again.', 'error')
        return redirect(url_for('finance_web_bp.manage_orders'))

@finance_web_bp.route('/view-order/<int:order_id>')
def view_order(order_id):
    try:
        order = (
            ExternalOrder.query
            .options(
                joinedload(ExternalOrder.supplier),
                joinedload(ExternalOrder.user)
            )
            .get_or_404(order_id)
        )
        
        # Get currency from config
        currency = current_app.config.get('CURRENCY', 'Ksh')
        
        # Calculate days until required
        now = datetime.utcnow()
        delta = order.required_by - now
        days_until = delta.days
        is_overdue = days_until < 0
        
        # Format days display text
        if days_until < 0:
            days_text = f"{abs(days_until)} days overdue"
        elif days_until == 0:
            days_text = "Today"
        elif days_until == 1:
            days_text = "Tomorrow"
        else:
            days_text = f"{days_until} days"
        
        # Format dates
        created_at = order.created_at.strftime('%d %b %Y %H:%M')
        required_by = order.required_by.strftime('%d %b %Y')
        delivery_date = order.delivery_date.strftime('%d %b %Y')
        
        return render_template('view_order.html',
                              order=order,
                              currency=currency,
                              days_text=days_text,
                              is_overdue=is_overdue,
                              created_at=created_at,
                              required_by=required_by,
                              delivery_date=delivery_date)
    
    except SQLAlchemyError as e:
        current_app.logger.error(f"Error fetching order {order_id}: {str(e)}")
        flash('An error occurred while loading the order details. Please try again.', 'error')
        return redirect(url_for('finance_web_bp.manage_orders'))


@finance_web_bp.route('/external-orders/<int:order_id>/add-details', methods=['GET', 'POST'])
@login_required
def add_details(order_id):
    """Page for finance to add/edit order details and verify information"""
    order = ExternalOrder.query.get_or_404(order_id)
    suppliers = Supplier.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        try:
            # Update all editable fields
            order.item_name = request.form.get('item_name')
            order.quantity = int(request.form.get('quantity'))
            order.unit = request.form.get('unit')
            order.category = request.form.get('category')
            order.priority = request.form.get('priority', 'medium')
            order.reason = request.form.get('reason')
            
            # Supplier details
            order.supplier_id = request.form.get('supplier_id') or None
            order.contact_person = request.form.get('contact_person')
            
            # Combine phone and email for contact_info
            contact_phone = request.form.get('contact_phone', '')
            contact_email = request.form.get('contact_email', '')
            order.contact_info = f"{contact_phone}" + (f" | {contact_email}" if contact_email else "")
            
            # Financial details
            order.unit_price = float(request.form.get('unit_price'))
            order.tax_rate = float(request.form.get('tax_rate', 0))
            order.total_price = float(request.form.get('total_price'))
            
            # Dates
            if request.form.get('required_by'):
                order.required_by = datetime.strptime(request.form.get('required_by'), '%Y-%m-%d')
            if request.form.get('delivery_date'):
                order.delivery_date = datetime.strptime(request.form.get('delivery_date'), '%Y-%m-%d')
            
            order.updated_at = datetime.utcnow()
            
            db.session.commit()

            flash('Order details updated successfully! Now you can approve the order.', 'success')
            return redirect(url_for('finance_web_bp.manage_orders'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating order details: {str(e)}', 'danger')

    return render_template('add_requisition_details.html',
                         order=order,
                         suppliers=suppliers,
                         title=f"Edit Details - {order.item_name}")



@finance_web_bp.route("/lpos/<int:order_id>/generate", methods=["POST", "GET"])
def generate_lpo(order_id):
    """
    Generate an LPO for a given external order.
    Sets all approvals to True and redirects to LPO page.
    """
    try:
        external_order = ExternalOrder.query.get_or_404(order_id)

        # ✅ Prevent duplicate LPOs for the same order
        existing_lpo = LPO.query.filter_by(external_order_id=external_order.id).first()
        if existing_lpo:
            flash(f"LPO already exists: {existing_lpo.lpo_number}", "warning")
            return redirect(url_for('finance_web_bp.view_order_lpo', lpo_id=existing_lpo.id))

        # ✅ Create new LPO with all approvals set to True
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
            status="approved",  # Set status to approved
            created_by=current_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            delivery_date=external_order.delivery_date,
            # Set all approvals to True
            finance_approved=True,
            finance_approved_at=datetime.utcnow(),
            finance_approved_by=current_user.id,
            director_approved=True,
            director_approved_at=datetime.utcnow(),
            director_approved_by=external_order.director_approved_by,
        )

        db.session.add(new_lpo)
        db.session.flush()  # Get new_lpo.id before commit

        # Generate LPO number
        new_lpo.lpo_number = f"LPO-{new_lpo.id}"

        # Update external order status
        external_order.status = "lpo_generated"  # Or "lpo_generated" if you prefer
        external_order.updated_at = datetime.utcnow()

        db.session.commit()

        flash(f"LPO generated successfully: {new_lpo.lpo_number}", "success")
        
        # ✅ Redirect to LPO page after creation
        return redirect(url_for('finance_web_bp.view_order_lpo', lpo_id=new_lpo.id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error generating LPO: {str(e)}", "error")
        return redirect(url_for('finance_web_bp.external_orders'))
    
    
@finance_web_bp.route('/generate-bulk-lpo/<int:requisition_id>/<int:supplier_id>')
@login_required
def generate_bulk_lpo(requisition_id, supplier_id):
    """
    Generate a single LPO for all items from a specific supplier in a requisition
    """
    try:
        requisition = Requisition.query.get_or_404(requisition_id)
        supplier = Supplier.query.get_or_404(supplier_id)
        
        # Get all director_approved orders for this supplier in this requisition
        orders = ExternalOrder.query.filter(
            ExternalOrder.requisition_id == requisition_id,
            ExternalOrder.supplier_id == supplier_id,
            ExternalOrder.status == 'director_approved'
        ).all()
        
        if not orders:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'No approved orders found'}), 400
            flash('No approved orders found for this supplier in the requisition.', 'warning')
            return redirect(url_for('finance_web_bp.manage_orders'))

        # ✅ Check for existing LPOs
        existing_lpos = []
        for order in orders:
            if order.lpos:
                existing_lpos.append(f"Order #{order.id} already has LPO: {order.lpos[0].lpo_number}")
        
        if existing_lpos:
            error_msg = "Some orders already have LPOs: " + ", ".join(existing_lpos)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': error_msg}), 400
            flash(error_msg, 'warning')
            return redirect(url_for('finance_web_bp.manage_orders'))

        # Use the first order as the base for the LPO relationship
        first_order = orders[0]
        total_amount = sum(order.total_price for order in orders)
        
        # ✅ Create bulk LPO record
        new_lpo = LPO(
            # Main order relationship (link to first order)
            external_order_id=first_order.id,
            
            # Bulk order specific fields
            requisition_id=requisition_id,
            is_bulk_order=True,
            bulk_order_count=len(orders),
            
            # LPO details (combined information)
            item_name=f"Bulk Order - {supplier.name}",
            category="bulk",
            unit="multiple",
            quantity=len(orders),
            unit_price=total_amount / len(orders) if orders else 0,
            tax_rate=0,  # You might want to calculate this based on individual orders
            total_price=total_amount,
            supplier_id=supplier_id,
            contact_person=first_order.contact_person or supplier.contact_person,
            contact_info=first_order.contact_info or supplier.contact_info,
            delivery_date=min([order.delivery_date for order in orders if order.delivery_date], default=None),
            
            # Status and approvals
            status="approved",
            finance_approved=True,
            finance_approved_at=datetime.utcnow(),
            finance_approved_by=current_user.id,
            director_approved=True,
            director_approved_at=datetime.utcnow(),
            director_approved_by=first_order.director_approved_by or current_user.id,
            
            # Meta
            created_by=current_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.session.add(new_lpo)
        db.session.flush()

        # Generate bulk LPO number
        new_lpo.lpo_number = f"LPO-BULK-{new_lpo.id}"

        # ✅ Update ALL orders to mark as processed
        for order in orders:
            order.status = "lpo_generated"
            order.updated_at = datetime.utcnow()
            # Note: Only the first order is directly linked to the LPO via external_order_id
            # Other orders are associated through requisition_id and is_bulk_order flag

        db.session.commit()

        current_app.logger.info(f"Generated bulk LPO #{new_lpo.id} for {len(orders)} items from supplier {supplier.name}")
        
        # Return JSON response for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Successfully generated LPO for {len(orders)} items from {supplier.name}',
                'lpo_id': new_lpo.id,
                'redirect_url': url_for('finance_web_bp.view_order_lpo', lpo_id=new_lpo.id)
            })
        
        flash(f'Successfully generated LPO for {len(orders)} items from {supplier.name}', 'success')
        return redirect(url_for('finance_web_bp.view_order_lpo', lpo_id=new_lpo.id))
        
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating bulk LPO: {str(e)}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        
        flash(f'An error occurred while generating the LPO: {str(e)}', 'error')
        return redirect(url_for('finance_web_bp.manage_orders'))
    
    
@finance_web_bp.route("/orders/<int:order_id>/send-lpo", methods=["POST", 'GET'])
def send_order_lpo(order_id):
    """Send LPO to supplier from order ID"""
    external_order = ExternalOrder.query.get_or_404(order_id)
    
    # Check if LPO exists for this order
    if not external_order.lpos:
        return jsonify({
            "success": False,
            "message": "No LPO found for this order"
        }), 400
    
    lpo = external_order.lpos[0]
    return place_order(lpo.id)  # Call the existing place_order function

@finance_web_bp.route("/lpos/<int:lpo_id>/send-to-supplier", methods=["POST", 'GET'])
def place_order(lpo_id):
    try:
        lpo = LPO.query.get_or_404(lpo_id)
        
        # Check if LPO is approved
        if not (lpo.finance_approved and lpo.director_approved and lpo.status == 'approved'):
            flash('LPO must be fully approved before sending to supplier', 'error')
            return redirect(url_for('finance_web_bp.view_lpo', lpo_id=lpo.id))

        # Get all external orders linked to this LPO
        external_orders = []
        if hasattr(lpo, 'external_orders') and lpo.external_orders:
            # Using direct relationship (recommended)
            external_orders = lpo.external_orders
        elif lpo.is_bulk_order and lpo.requisition_id and lpo.supplier_id:
            # Fallback: query by requisition and supplier
            external_orders = ExternalOrder.query.filter_by(
                requisition_id=lpo.requisition_id,
                supplier_id=lpo.supplier_id
            ).filter(
                ExternalOrder.status.in_(['lpo_generated', 'director_approved'])
            ).all()
        elif lpo.external_order:
            # Single item LPO
            external_orders = [lpo.external_order]
        else:
            flash('No external orders found for this LPO', 'error')
            return redirect(url_for('finance_web_bp.view_lpo', lpo_id=lpo.id))

        if not external_orders:
            flash('No external orders found for this LPO', 'error')
            return redirect(url_for('finance_web_bp.view_lpo', lpo_id=lpo.id))

        # --- Generate professional text-based LPO file (combined) ---
        # Header
        lpo_content = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         MEDICAL CENTER HOSPITAL                             ║
║                         LOCAL PURCHASE ORDER                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ LPO Number: {lpo.lpo_number:<60} ║
║ Date: {datetime.utcnow().strftime('%Y-%m-%d'):<64} ║
║ Status: APPROVED{' ' * 58} ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                           SUPPLIER INFORMATION                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Supplier: {lpo.supplier.name if lpo.supplier else 'N/A':<65} ║
║ Contact: {lpo.contact_person or 'N/A':<67} ║
║ Email: {(lpo.supplier.email if lpo.supplier else 'N/A')[:65]:<65} ║
║ Phone: {lpo.contact_info or 'N/A':<66} ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                            ORDER DETAILS                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
"""
        # List each item
        total_amount = 0
        for idx, order in enumerate(external_orders, 1):
            line_total = order.total_price or (order.quantity * order.unit_price * (1 + (order.tax_rate or 0)/100))
            total_amount += line_total
            lpo_content += f"""║ Item #{idx}: {order.item_name:<67} ║
║   └ Category: {order.category or 'General':<60} ║
║   └ Quantity: {order.quantity} {order.unit}{' ' * (54 - len(str(order.quantity) + ' ' + order.unit))} ║
║   └ Unit Price: KSh {order.unit_price:>12,.2f}{' ' * (47 - len(f"{order.unit_price:,.2f}"))} ║
║   └ Tax Rate: {order.tax_rate or 0}%{' ' * (62 - len(str(order.tax_rate or 0)))} ║
║   └ Line Total: KSh {line_total:>10,.2f}{' ' * (46 - len(f"{line_total:,.2f}"))} ║
"""
            if idx != len(external_orders):
                lpo_content += "║" + " " * 78 + "║\n"

        lpo_content += f"""╠══════════════════════════════════════════════════════════════════════════════╣
║ Total Amount (incl. tax): KSh {total_amount:>10,.2f}{' ' * (43 - len(f"{total_amount:,.2f}"))} ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Delivery Date(s):                                                            ║
"""
        # Add delivery dates if they differ
        delivery_dates = set(o.delivery_date.strftime('%Y-%m-%d') for o in external_orders if o.delivery_date)
        if delivery_dates:
            for d in delivery_dates:
                lpo_content += f"║   • {d:<74} ║\n"
        else:
            lpo_content += "║   • To be confirmed                                                      ║\n"

        lpo_content += f"""╠══════════════════════════════════════════════════════════════════════════════╣
║                          TERMS & CONDITIONS                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ 1. Acknowledge receipt within 24 hours                                     ║
║ 2. Reference LPO number on all invoices                                    ║
║ 3. Deliver to Medical Center Hospital                                      ║
║ 4. Contact procurement for clarifications                                  ║
║ 5. Prices include all taxes and delivery                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                         AUTHORIZED SIGNATURE                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║ _________________________              _________________________            ║
║ Procurement Manager                     Date: {datetime.utcnow().strftime('%Y-%m-%d'):<10}            ║
║ Medical Center Hospital                                                     ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║           procurement@medicalcenter.co.ke • +254 700 123 457                ║
║          Computer Generated LPO - No Physical Signature Required            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

        # Save as text file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
            tmp_file.write(lpo_content.encode('utf-8'))
            attachment_path = tmp_file.name

        # Send professional email to supplier
        email_sent = False
        if lpo.supplier and lpo.supplier.email:
            subject = f"{lpo.lpo_number} - Medical Center Hospital"

            # Build items list for email body
            items_list = ""
            for order in external_orders:
                items_list += f"• {order.item_name}: {order.quantity} {order.unit} @ KSh {order.unit_price:,.2f} = KSh {order.total_price:,.2f}\n"

            # Plain text email content
            plain_text_body = f"""
Dear {lpo.supplier.name},

Please find attached Local Purchase Order {lpo.lpo_number} from Medical Center Hospital.

ORDER SUMMARY:
{items_list}
Total Amount: KSh {total_amount:,.2f}

Delivery Dates: {', '.join(delivery_dates) if delivery_dates else 'To be confirmed'}

Please acknowledge receipt and confirm delivery timeline. Reference this LPO number on your invoice.

Best regards,
Procurement Department
Medical Center Hospital
"""
            
            # HTML email content
            items_html = ""
            for order in external_orders:
                items_html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{order.item_name}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: center;">{order.quantity} {order.unit}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right;">KSh {order.unit_price:,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right;">KSh {order.total_price:,.2f}</td>
                </tr>
                """

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
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: #e2e8f0;">
                        <th style="padding: 8px; text-align: left;">Item</th>
                        <th style="padding: 8px; text-align: center;">Qty</th>
                        <th style="padding: 8px; text-align: right;">Unit Price</th>
                        <th style="padding: 8px; text-align: right;">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="3" style="padding: 8px; text-align: right; font-weight: bold;">Grand Total:</td>
                        <td style="padding: 8px; text-align: right; font-weight: bold; color: #2563eb;">KSh {total_amount:,.2f}</td>
                    </tr>
                </tfoot>
            </table>
        </div>
        
        <p><strong>Delivery Dates:</strong> {', '.join(delivery_dates) if delivery_dates else 'To be confirmed'}</p>
        
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
                body=plain_text_body,
                html_body=html_email_body,
                attachments=[attachment_path]
            )

        # Create PurchaseOrder records for each item (if model exists)
        purchase_orders_created = 0
        try:
            for order in external_orders:
                purchase_order = PurchaseOrder(
                    requisition_id=order.id,           # or link to requisition if appropriate
                    supplier_id=order.supplier_id,
                    lpo_id=lpo.id,
                    lpo_number=lpo.lpo_number,
                    item_name=order.item_name,
                    quantity=order.quantity,
                    unit=order.unit,
                    unit_price=order.unit_price,
                    total_price=order.total_price,
                    currency=current_app.config.get('CURRENCY', 'Ksh'),
                    delivery_date=order.delivery_date,
                    status='ordered',
                    created_by=current_user.id
                )
                db.session.add(purchase_order)
                purchase_orders_created += 1
        except NameError:
            # PurchaseOrder model might not exist, skip
            pass

        # Update external orders and LPO status
        for order in external_orders:
            order.status = 'order_placed'
            order.updated_at = datetime.utcnow()
        
        lpo.status = 'sent_to_supplier'
        lpo.updated_at = datetime.utcnow()

        db.session.commit()

        # Clean up temporary file
        if attachment_path:
            try:
                os.unlink(attachment_path)
            except:
                pass

        # Show appropriate success message
        if email_sent:
            flash(f'Purchase order(s) created and LPO sent to {lpo.supplier.name}!', 'success')
        else:
            flash(f'Purchase order(s) created but email failed to send to supplier.', 'warning')

        return redirect(url_for('finance_web_bp.view_order_lpo', lpo_id=lpo.id))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating purchase order or sending LPO: {str(e)}")
        flash('An error occurred while creating the purchase order or sending LPO.', 'error')
        return redirect(url_for('finance_web_bp.view_lpo', lpo_id=lpo_id))

@finance_web_bp.route("/orders/<int:order_id>/lpo")
def view_lpo_for_order(order_id):
    """View LPO details from order ID - redirects to LPO view"""
    external_order = ExternalOrder.query.get_or_404(order_id)
    
    # Check if LPO exists for this order
    if not external_order.lpos:
        flash('No LPO found for this order', 'error')
        return redirect(url_for('finance_web_bp.view_order', order_id=order_id))
    
    lpo = external_order.lpos[0]  # Get the first LPO
    return redirect(url_for('finance_web_bp.view_order_lpo', lpo_id=lpo.id))


@finance_web_bp.route("/lpos/<int:lpo_id>")
def view_order_lpo(lpo_id):
    """View LPO details – handles both single and bulk LPOs"""
    lpo = LPO.query.get_or_404(lpo_id)
    items = []
    subtotal = 0
    tax_amount = 0
    tax_rate_display = 0  # for display purposes only

    if lpo.is_bulk_order and lpo.requisition_id and lpo.supplier_id:
        # Bulk LPO: fetch all external orders from same requisition & supplier
        orders = ExternalOrder.query.filter_by(
            requisition_id=lpo.requisition_id,
            supplier_id=lpo.supplier_id
        ).filter(
            ExternalOrder.status.in_(['director_approved', 'lpo_generated'])
        ).all()

        for order in orders:
            # Calculate tax breakdown if needed
            order_tax_rate = order.tax_rate or 0
            order_total = order.total_price or 0
            order_subtotal = order_total / (1 + order_tax_rate/100) if order_tax_rate else order_total
            order_tax = order_total - order_subtotal

            items.append({
                'item_name': order.item_name,
                'quantity': order.quantity,
                'unit': order.unit,
                'unit_price': order.unit_price,
                'total_price': order_total,
                'tax_rate': order_tax_rate,
                'subtotal': order_subtotal,
                'tax_amount': order_tax,
                'category': order.category,
                'reason': order.reason
            })

            subtotal += order_subtotal
            tax_amount += order_tax

    else:
        # Single item LPO
        if lpo.external_order:
            order = lpo.external_order
            order_tax_rate = order.tax_rate or 0
            order_total = order.total_price or 0
            order_subtotal = order_total / (1 + order_tax_rate/100) if order_tax_rate else order_total
            order_tax = order_total - order_subtotal
        else:
            # Fallback to LPO fields
            order_tax_rate = lpo.tax_rate or 0
            order_total = lpo.total_price or 0
            order_subtotal = order_total / (1 + order_tax_rate/100) if order_tax_rate else order_total
            order_tax = order_total - order_subtotal

        items.append({
            'item_name': lpo.item_name,
            'quantity': lpo.quantity,
            'unit': lpo.unit,
            'unit_price': lpo.unit_price,
            'total_price': order_total,
            'tax_rate': order_tax_rate,
            'subtotal': order_subtotal,
            'tax_amount': order_tax,
            'category': lpo.category,
            'reason': lpo.external_order.reason if lpo.external_order else None
        })

        subtotal = order_subtotal
        tax_amount = order_tax
        tax_rate_display = order_tax_rate

    total = subtotal + tax_amount

    return render_template(
        "view_supplier_lpo.html",
        lpo=lpo,
        items=items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        tax_rate=tax_rate_display,
        total=total
    )

@finance_web_bp.route("/approve-lpo")

def approve_lpo():
    """
    Page for approving LPOs pending finance approval.
    Fetch LPOs that are:
    - Not yet finance approved
    - Status is pending
    """
    # Query all LPOs pending finance approval
    pending_lpos = (
        LPO.query
        .filter(LPO.finance_approved == False)  # not approved yet
        .filter(LPO.status == "pending")        # only pending LPOs
        .order_by(LPO.created_at.desc())
        .all()
    )

    # Optional: convert to dict if needed in template
    lpos_data = [lpo.to_dict() for lpo in pending_lpos]

    return render_template("approve_lpo.html", lpos=lpos_data)


@finance_web_bp.route("/view-lpo/<int:lpo_id>")
def view_lpo(lpo_id):
    """
    View detailed LPO information – supports both single and bulk orders.
    """
    lpo = LPO.query.get_or_404(lpo_id)
    items = []
    subtotal = 0
    tax_amount = 0
    tax_rate_display = 0

    # Try to get all external orders linked to this LPO
    external_orders = []
    if hasattr(lpo, 'external_orders') and lpo.external_orders:
        # Direct relationship (if you added lpo_id to ExternalOrder)
        external_orders = lpo.external_orders
    elif lpo.is_bulk_order and lpo.requisition_id and lpo.supplier_id:
        # Include all statuses that indicate the order is linked to this LPO
        external_orders = ExternalOrder.query.filter_by(
            requisition_id=lpo.requisition_id,
            supplier_id=lpo.supplier_id
        ).filter(
            ExternalOrder.status.in_(['director_approved', 'lpo_generated', 'order_placed'])
        ).all()
    elif lpo.external_order:
        # Single item LPO
        external_orders = [lpo.external_order]

    if external_orders:
        for order in external_orders:
            # Tax breakdown
            order_tax_rate = order.tax_rate or 0
            order_total = order.total_price or 0
            order_subtotal = order_total / (1 + order_tax_rate/100) if order_tax_rate else order_total
            order_tax = order_total - order_subtotal

            items.append({
                'item_name': order.item_name,
                'quantity': order.quantity,
                'unit': order.unit,
                'unit_price': order.unit_price,
                'total_price': order_total,
                'tax_rate': order_tax_rate,
                'subtotal': order_subtotal,
                'tax_amount': order_tax,
                'category': order.category,
                'reason': order.reason
            })

            subtotal += order_subtotal
            tax_amount += order_tax
    else:
        # Fallback to LPO fields (shouldn't happen, but safe)
        order_tax_rate = lpo.tax_rate or 0
        order_total = lpo.total_price or 0
        order_subtotal = order_total / (1 + order_tax_rate/100) if order_tax_rate else order_total
        order_tax = order_total - order_subtotal

        items.append({
            'item_name': lpo.item_name,
            'quantity': lpo.quantity,
            'unit': lpo.unit,
            'unit_price': lpo.unit_price,
            'total_price': order_total,
            'tax_rate': order_tax_rate,
            'subtotal': order_subtotal,
            'tax_amount': order_tax,
            'category': lpo.category,
            'reason': lpo.external_order.reason if lpo.external_order else None
        })

        subtotal = order_subtotal
        tax_amount = order_tax
        tax_rate_display = order_tax_rate

    total = subtotal + tax_amount

    return render_template(
        "lpo_detail.html",                # 👈 new template name
        lpo=lpo,
        items=items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        tax_rate=tax_rate_display,
        total=total
    )


@finance_web_bp.route("/approve-lpo-action/<int:lpo_id>/<string:action>")

def approve_lpo_action(lpo_id, action):
    """
    Approve or reject an LPO
    action: 'approve' or 'reject'
    """
    lpo = LPO.query.get_or_404(lpo_id)

    if lpo.finance_approved:
        flash("This LPO has already been approved by finance.", "warning")
        return redirect(url_for("finance_web_bp.approve_lpo"))

    if action == "approve":
        lpo.finance_approved = True
        lpo.finance_approved_at = datetime.utcnow()
        lpo.finance_approved_by = current_user.id
        lpo.status = "finance_approved"  # Update overall status
        flash(f"LPO {lpo.lpo_number or lpo.id} approved successfully.", "success")
    elif action == "reject":
        lpo.finance_approved = False
        lpo.status = "rejected"
        flash(f"LPO {lpo.lpo_number or lpo.id} rejected.", "danger")
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for("finance_web_bp.approve_lpo"))

    db.session.commit()
    return redirect(url_for("finance_web_bp.approve_lpo"))

@finance_web_bp.route('/expenses/new', methods=['GET', 'POST'])
@login_required
def new_expense():
    from app.finance.models import BankAccount, CashAccount
    from flask import jsonify

    # GET – fetch all needed data
    categories = ExpenseCategory.query.order_by(ExpenseCategory.name).all()
    departments = Department.query.order_by(Department.name).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()
    cash_accounts = CashAccount.query.filter_by(is_active=True).all()
    payment_methods = ['Bank Transfer', 'Cheque', 'Cash', 'Mobile Money', 'Credit Card']
    expense_types = ['operational', 'capital', 'emergency']
    priority_levels = ['low', 'medium', 'high', 'critical']
    current_date = datetime.utcnow().strftime('%Y-%m-%d')

    # AJAX: Add new category
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        if data.get('action') == 'add_category':
            name = data.get('name')
            description = data.get('description')
            department = data.get('department', 'General')
            budget_str = data.get('budget', '0')
            # Convert to float, default to 0 if empty or invalid
            try:
                budget = float(budget_str) if budget_str else 0.0
            except ValueError:
                budget = 0.0

            if not name:
                return jsonify({'success': False, 'error': 'Category name is required'}), 400

            cat = ExpenseCategory(
                name=name,
                description=description,
                department=department,
                budget_allocation=budget
            )
            db.session.add(cat)
            db.session.commit()
            return jsonify({'success': True, 'id': cat.id, 'name': cat.name})
        elif data.get('action') == 'delete_category':
            cat_id = data.get('id')
            cat = ExpenseCategory.query.get(cat_id)
            if cat:
                cat.is_active = False
                db.session.commit()
                return jsonify({'success': True})
            return jsonify({'success': False, 'error': 'Category not found'}), 404

    # POST – create expense
    if request.method == 'POST' and not request.is_json:
        try:
            expense = Expense(
                expense_date=datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d'),
                description=request.form.get('description'),
                amount=float(request.form.get('amount')),
                category_id=int(request.form.get('category_id')),
                department_id=int(request.form.get('department_id')),
                supplier_id=int(request.form.get('supplier_id')) if request.form.get('supplier_id') else None,
                payment_method=request.form.get('payment_method'),
                expense_type=request.form.get('expense_type'),
                priority=request.form.get('priority'),
                notes=request.form.get('notes'),
                initiated_by=current_user.id,
                status='draft' if request.form.get('save_draft') else 'submitted',
                account_type=request.form.get('account_type'),
                account_id=int(request.form.get('account_id')) if request.form.get('account_id') else None,
                receipt_number=request.form.get('receipt_number')
            )
            expense.currency = 'KES'
            expense.calculate_tax()
            db.session.add(expense)
            db.session.commit()
            expense.reference_number = expense.generate_reference()
            db.session.commit()
            flash('Expense created successfully!', 'success')
            return redirect(url_for('finance_web_bp.expenses'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating expense: {str(e)}', 'danger')

    return render_template(
        'new_expense.html',
        categories=categories,
        departments=departments,
        suppliers=suppliers,
        bank_accounts=bank_accounts,
        cash_accounts=cash_accounts,
        payment_methods=payment_methods,
        expense_types=expense_types,
        priority_levels=priority_levels,
        current_date=current_date
    )


@finance_web_bp.route('/cash-payments')
def cash_payments():
    """
    Display cash payments management page
    Requires 'finance:payments' privilege
    """

    
    # Get pagination parameters
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 25))
    except ValueError:
        page = 1
        per_page = 25

    # Get filter parameters
    status_filter = request.args.get('status')
    patient_filter = request.args.get('patient')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    min_amount = request.args.get('min_amount')
    max_amount = request.args.get('max_amount')

    # Build query for cash invoices
    query = Invoice.query.filter_by(invoice_type='CASH').options(
        db.joinedload(Invoice.patient),
        db.joinedload(Invoice.visit)
    )

    # Apply filters
    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    
    if patient_filter:
        query = query.filter(Patient.full_name.ilike(f'%{patient_filter}%'))
    
    if date_from:
        query = query.filter(Invoice.issue_date >= date_from)
    
    if date_to:
        next_day = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        query = query.filter(Invoice.issue_date < next_day)
    
    if min_amount:
        query = query.filter(Invoice.total_amount >= float(min_amount))
    
    if max_amount:
        query = query.filter(Invoice.total_amount <= float(max_amount))

    # Order by latest first
    query = query.order_by(Invoice.issue_date.desc())

    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    invoices = pagination.items

    # Calculate summary statistics
    today = datetime.today().date()
    
    # Total cash invoices
    total_count = query.count()
    
    # Paid amount and count
    paid_query = query.filter(Invoice.status == 'paid')
    paid_count = paid_query.count()
    paid_amount = paid_query.with_entities(db.func.sum(Invoice.total_amount)).scalar() or 0.0
    
    # Pending amount and count
    pending_query = query.filter(Invoice.status == 'pending')
    pending_count = pending_query.count()
    pending_amount = pending_query.with_entities(db.func.sum(Invoice.total_amount)).scalar() or 0.0
    
    # Overdue count
    overdue_count = query.filter(
        Invoice.status == 'pending',
        Invoice.due_date < today
    ).count()
    
    # Partial count
    partial_count = query.filter(Invoice.status == 'partially_paid').count()
    
    # Today's cash
    today_query = Invoice.query.filter(
        Invoice.invoice_type == 'CASH',
        Invoice.status == 'paid',
        db.func.date(Invoice.issue_date) == today
    )
    today_count = today_query.count()
    today_amount = today_query.with_entities(db.func.sum(Invoice.total_amount)).scalar() or 0.0
    
    summary = {
        'total_count': total_count,
        'paid_count': paid_count,
        'pending_count': pending_count,
        'overdue_count': overdue_count,
        'partial_count': partial_count,
        'paid_amount': paid_amount,
        'pending_amount': pending_amount,
        'today_count': today_count,
        'today_amount': today_amount,
        'paid_percentage': round((paid_amount / (paid_amount + pending_amount)) * 100) if (paid_amount + pending_amount) > 0 else 0
    }
    
    # Calculate daily trend (last 7 days)
    daily_trend = {
        'labels': [],
        'values': []
    }
    
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).date()
        daily_amount = db.session.query(
            db.func.coalesce(db.func.sum(Invoice.total_amount), 0.0)
        ).filter(
            Invoice.invoice_type == 'CASH',
            Invoice.status == 'paid',
            db.func.date(Invoice.issue_date) == date
        ).scalar() or 0.0
        
        daily_trend['labels'].append(date.strftime("%a"))
        daily_trend['values'].append(daily_amount)

    return render_template(
        'cash_payments.html',
        invoices=invoices,
        pagination=pagination,
        summary=summary,
        daily_trend=daily_trend
    )

# Add to your finance/routes.py

@finance_web_bp.route('/invoices/<int:invoice_id>')
def invoice_details(invoice_id):
    """
    Display detailed information about a specific invoice
    Requires 'finance:invoices' privilege
    """
    if not current_user.has_privilege('finance:invoices'):
        abort(403)
    
    # Get invoice with related data
    invoice = Invoice.query.options(
        db.joinedload(Invoice.patient),
        db.joinedload(Invoice.visit),
        db.joinedload(Invoice.items).joinedload(InvoiceItem.service),
        db.joinedload(Invoice.payments)
    ).get_or_404(invoice_id)
    
    # Verify it's a cash invoice
    if invoice.invoice_type != 'CASH':
        abort(404, "This is not a cash invoice")
    
    # Calculate balance
    paid_amount = sum(payment.amount for payment in invoice.payments)
    balance = invoice.total_amount - paid_amount
    
    return render_template(
        'finance/invoice_details.html',
        invoice=invoice,
        paid_amount=paid_amount,
        balance=balance
    )

@finance_web_bp.route('/invoices/<int:invoice_id>/record-payment', methods=['GET', 'POST'])
def record_cash_payment(invoice_id):
    """
    Record a cash payment against an invoice
    Requires 'finance:payments' privilege
    """
    if not current_user.has_privilege('finance:payments'):
        abort(403)
    
    invoice = Invoice.query.get_or_404(invoice_id)
    
    # Calculate current balance
    paid_amount = sum(payment.amount for payment in invoice.payments)
    balance = invoice.total_amount - paid_amount
    
    form = CashPaymentForm()
    
    if form.validate_on_submit():
        try:
            payment_amount = form.amount.data
            
            # Validate payment amount
            if payment_amount <= 0:
                flash('Payment amount must be positive', 'danger')
            elif payment_amount > balance:
                flash(f'Payment amount exceeds balance of {balance:.2f}', 'danger')
            else:
                # Create new payment
                payment = Payment(
                    invoice_id=invoice_id,
                    amount=payment_amount,
                    payment_method='cash',
                    payment_date=datetime.utcnow(),
                    received_by=current_user.id,
                    notes=form.notes.data
                )
                
                db.session.add(payment)
                
                # Update invoice status
                new_paid_amount = paid_amount + payment_amount
                if new_paid_amount >= invoice.total_amount:
                    invoice.status = 'paid'
                elif new_paid_amount > 0:
                    invoice.status = 'partially_paid'
                
                db.session.commit()
                
                flash('Payment recorded successfully', 'success')
                return redirect(url_for('finance_web_bp.invoice_details', invoice_id=invoice_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording payment: {str(e)}', 'danger')
    
    # Pre-fill form with balance
    form.amount.data = balance
    
    return render_template(
        'finance/record_payment.html',
        invoice=invoice,
        form=form,
        balance=balance
    )

@finance_web_bp.route('/invoices/<int:invoice_id>/receipt')

def print_receipt(invoice_id):
    """
    Generate a printable receipt for an invoice
    Requires 'finance:invoices' privilege
    """
    if not current_user.has_privilege('finance:invoices'):
        abort(403)
    
    # Get invoice with related data
    invoice = Invoice.query.options(
        db.joinedload(Invoice.patient),
        db.joinedload(Invoice.items).joinedload(InvoiceItem.service),
        db.joinedload(Invoice.payments)
    ).get_or_404(invoice_id)
    
    # Verify it's a cash invoice
    if invoice.invoice_type != 'CASH':
        abort(404, "This is not a cash invoice")
    
    # Calculate paid amount
    paid_amount = sum(payment.amount for payment in invoice.payments)
    
    return render_template(
        'finance/receipt.html',
        invoice=invoice,
        paid_amount=paid_amount,
        today=datetime.utcnow().date()
    )
    


@finance_web_bp.route('/supplier-accounts')
def supplier_accounts():
    """Manage supplier accounts"""
    accounts = SupplierAccount.query.all()
    suppliers_without_accounts = Supplier.query.filter(
        ~Supplier.id.in_([acc.supplier_id for acc in accounts])
    ).all()
    
    return render_template('supplier_accounts.html',
                         accounts=accounts,
                         suppliers_without_accounts=suppliers_without_accounts)
    

    
@finance_web_bp.route('/doctor-accounts')
@login_required
def doctor_accounts():
    """
    Display doctor accounts with commission and payment tracking
    """
    # Get filter parameters
    date_filter = request.args.get('date_filter', 'all')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    doctor_id = request.args.get('doctor_id', type=int)
    
    # Base query for doctors
    doctors_query = User.query.join(User.roles).filter(Role.name == 'Doctor')
    
    if doctor_id:
        doctors_query = doctors_query.filter(User.id == doctor_id)
    
    doctors = doctors_query.all()
    
    doctor_accounts_data = []
    
    for doctor in doctors:
        # Get date range for filtering
        date_filter_condition = True
        if date_filter == 'today':
            today = datetime.now().date()
            date_filter_condition = func.date(Visit.visit_date) == today
        elif date_filter == 'week':
            week_ago = datetime.now() - timedelta(days=7)
            date_filter_condition = Visit.visit_date >= week_ago
        elif date_filter == 'month':
            month_ago = datetime.now() - timedelta(days=30)
            date_filter_condition = Visit.visit_date >= month_ago
        elif date_filter == 'custom' and start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            date_filter_condition = and_(Visit.visit_date >= start, Visit.visit_date <= end)
        
        # Get services assigned to this doctor
        assigned_services = ServiceDoctorAssignment.query.filter_by(
            doctor_id=doctor.id,
            is_active=True
        ).all()
        
        if not assigned_services:
            doctor_accounts_data.append({
                'doctor': doctor,
                'assigned_services': [],
                'total_visits': 0,
                'period_earned': 0,
                'total_paid': 0,
                'balance_due': 0,
                'last_visit': None,
                'has_services': False,
                'service_revenue_breakdown': {}
            })
            continue
        
        assigned_service_ids = [assignment.service_id for assignment in assigned_services]
        
        # Get visits with date filtering
        doctor_visits_query = Visit.query.join(Visit.services).filter(
            Service.id.in_(assigned_service_ids),
            Visit.payment_status == 'paid',
            date_filter_condition
        ).options(
            joinedload(Visit.patient),
            joinedload(Visit.services)
        )
        
        doctor_visits = doctor_visits_query.all()
        
        # Calculate earnings and payments
        total_services_count = len(doctor_visits)
        period_earned = 0
        service_revenue_breakdown = {}
        service_visits_count = {}

        for visit in doctor_visits:
            for service in visit.services:
                if service.id in assigned_service_ids:
                    assignment = next((a for a in assigned_services if a.service_id == service.id), None)
                    if assignment:
                        # Calculate service revenue (total amount from visits)
                        service_revenue = service.special_clinic_price
                        
                        # Calculate doctor's earnings based on commission type
                        if assignment.payment_type == 'percentage':
                            service_earned = service_revenue * (assignment.commission_rate / 100)
                        else:
                            service_earned = assignment.fixed_amount or 0
                        
                        period_earned += service_earned
                        
                        # Track revenue by service
                        if service.name in service_revenue_breakdown:
                            service_revenue_breakdown[service.name] += service_revenue
                        else:
                            service_revenue_breakdown[service.name] = service_revenue
                        
                        # Track visits count per service
                        if service.name in service_visits_count:
                            service_visits_count[service.name] += 1
                        else:
                            service_visits_count[service.name] = 1
        
        # Calculate total payments made to this doctor (with date filtering)
        total_paid = 0
        for assignment in assigned_services:
            assignment_payments_query = DoctorPayment.query.filter_by(
                assignment_id=assignment.id,
                status='completed'
            )
            
            # Apply the same date filter to payments
            if date_filter == 'today':
                assignment_payments_query = assignment_payments_query.filter(func.date(DoctorPayment.payment_date) == today)
            elif date_filter == 'week':
                assignment_payments_query = assignment_payments_query.filter(DoctorPayment.payment_date >= week_ago)
            elif date_filter == 'month':
                assignment_payments_query = assignment_payments_query.filter(DoctorPayment.payment_date >= month_ago)
            elif date_filter == 'custom' and start_date and end_date:
                assignment_payments_query = assignment_payments_query.filter(and_(DoctorPayment.payment_date >= start, DoctorPayment.payment_date <= end))
            
            assignment_payments = assignment_payments_query.all()
            total_paid += sum(payment.amount for payment in assignment_payments)
        
        balance_due = period_earned - total_paid
        
        # Add visits count to each assignment for the frontend
        for assignment in assigned_services:
            service = assignment.service
            assignment.visits_count = service_visits_count.get(service.name, 0)
        
        doctor_accounts_data.append({
            'doctor': doctor,
            'assigned_services': assigned_services,
            'assigned_service_ids': assigned_service_ids,
            'total_visits': total_services_count,
            'period_earned': period_earned,
            'total_paid': total_paid,
            'balance_due': balance_due,
            'service_revenue_breakdown': service_revenue_breakdown,
            'last_visit': max([v.visit_date for v in doctor_visits]) if doctor_visits else None,
            'has_services': True,
            'visit_details': doctor_visits[:10]
        })
    
    return render_template(
        'doctor_accounts.html',
        title='Doctor Accounts',
        doctor_accounts=doctor_accounts_data,
        current_time=datetime.now(),
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date,
        doctor_id=doctor_id
    )
    
@finance_web_bp.route('/api/doctor-visits/<int:doctor_id>')
@login_required
def get_doctor_visits(doctor_id):
    """
    API endpoint to get detailed visit information for a specific doctor
    """
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Get services assigned to this doctor
    assigned_services = ServiceDoctorAssignment.query.filter_by(
        doctor_id=doctor_id,
        is_active=True
    ).all()
    
    assigned_service_ids = [assignment.service_id for assignment in assigned_services]
    
    # Build query with date filtering
    visits_query = Visit.query.join(Visit.services).filter(
        Service.id.in_(assigned_service_ids),
        Visit.payment_status == 'paid'
    ).options(
        joinedload(Visit.patient),
        joinedload(Visit.services)
    )
    
    if start_date and end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        visits_query = visits_query.filter(and_(Visit.visit_date >= start, Visit.visit_date <= end))
    
    visits = visits_query.order_by(Visit.visit_date.desc()).all()
    
    visit_data = []
    for visit in visits:
        visit_services = []
        doctor_revenue = 0
        
        for service in visit.services:
            if service.id in assigned_service_ids:
                visit_services.append({
                    'id': service.id,
                    'name': service.name,
                    'price': service.special_clinic_price,
                    'category': service.category
                })
                doctor_revenue += service.special_clinic_price

        visit_data.append({
            'visit_id': visit.id,
            'visit_date': visit.visit_date.isoformat(),
            'patient_name': visit.patient.full_name if visit.patient else 'Unknown',
            'patient_id': visit.patient_id,
            'services': visit_services,
            'total_amount': doctor_revenue,
            'payment_status': visit.payment_status,
            'visit_status': visit.visit_status
        })
    
    return jsonify({
        'success': True,
        'doctor_id': doctor_id,
        'visits': visit_data,
        'total_visits': len(visits),
        'total_revenue': sum([v['total_amount'] for v in visit_data])
    })
    
@finance_web_bp.route('/api/doctor-commissions/<int:doctor_id>')
@login_required
def get_doctor_commissions(doctor_id):
    """
    API endpoint to get commission settings for a specific doctor
    """
    try:
        # Get doctor info
        doctor = User.query.get_or_404(doctor_id)
        
        # Get assigned services with commission details
        assigned_services = ServiceDoctorAssignment.query.filter_by(
            doctor_id=doctor_id,
            is_active=True
        ).options(
            joinedload(ServiceDoctorAssignment.service)
        ).all()
        
        # Get service statistics for revenue information
        service_data = []
        for assignment in assigned_services:
            # Calculate revenue generated by this service for the doctor
            service_visits = Visit.query.join(Visit.services).filter(
                Service.id == assignment.service_id,
                Visit.payment_status == 'paid'
            ).all()
            
            total_revenue = 0
            visits_count = len(service_visits)
            
            for visit in service_visits:
                for service in visit.services:
                    if service.id == assignment.service_id:
                        total_revenue += service.special_clinic_price
            
            # Calculate doctor's earnings
            if assignment.payment_type == 'percentage':
                doctor_earnings = total_revenue * (assignment.commission_rate / 100)
            else:
                doctor_earnings = (assignment.fixed_amount or 0) * visits_count
            
            service_data.append({
                'assignment_id': assignment.id,
                'service_id': assignment.service.id,
                'service_name': assignment.service.name,
                'service_price': assignment.service.special_clinic_price,
                'service_category': assignment.service.category,
                'payment_type': assignment.payment_type,
                'commission_rate': assignment.commission_rate,
                'fixed_amount': assignment.fixed_amount,
                'total_revenue': total_revenue,
                'visits_count': visits_count,
                'doctor_earnings': doctor_earnings
            })
        
        return jsonify({
            'success': True,
            'doctor': {
                'id': doctor.id,
                'name': doctor.full_name or doctor.username,
                'email': doctor.email
            },
            'assigned_services': service_data,
            'total_services': len(service_data)
        })
        
    except Exception as e:
        import traceback
        print(f"Error in get_doctor_commissions: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@finance_web_bp.route('/api/update-commission/<int:assignment_id>', methods=['POST'])
@login_required
def update_commission(assignment_id):
    """
    API endpoint to update commission settings for a service assignment
    """
    try:
        data = request.get_json()
        assignment = ServiceDoctorAssignment.query.get_or_404(assignment_id)
        
        # Update commission settings
        assignment.payment_type = data.get('payment_type', assignment.payment_type)
        
        if data['payment_type'] == 'percentage':
            assignment.commission_rate = float(data.get('commission_rate', assignment.commission_rate))
            assignment.fixed_amount = None
        else:
            assignment.fixed_amount = float(data.get('fixed_amount', assignment.fixed_amount or 0))
            assignment.commission_rate = None
        
        # Add updated_at field if it doesn't exist in your model
        # If you don't have updated_at, you can skip this or add it to your model
        if hasattr(assignment, 'updated_at'):
            assignment.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log the change
        current_user.log_activity(
            f"Updated commission for service {assignment.service.name} - Doctor: {assignment.doctor.full_name}",
            'commission_update'
        )
        
        return jsonify({
            'success': True,
            'message': 'Commission settings updated successfully',
            'assignment': {
                'id': assignment.id,
                'payment_type': assignment.payment_type,
                'commission_rate': assignment.commission_rate,
                'fixed_amount': assignment.fixed_amount
            }
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error in update_commission: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@finance_web_bp.route('/api/doctor-services/<int:doctor_id>')
@login_required
def get_available_services(doctor_id):
    """
    Get services available for assignment to a doctor
    """
    try:
        # Get services not currently assigned to this doctor
        assigned_service_ids = db.session.query(ServiceDoctorAssignment.service_id).filter(
            ServiceDoctorAssignment.doctor_id == doctor_id,
            ServiceDoctorAssignment.is_active == True
        ).subquery()
        
        available_services = Service.query.filter(
            Service.is_active == True,
            ~Service.id.in_(assigned_service_ids)
        ).all()
        
        services_data = [{
            'id': service.id,
            'name': service.name,
            'price': service.special_clinic_price,
            'category': service.category
        } for service in available_services]
        
        return jsonify({
            'success': True,
            'available_services': services_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@finance_web_bp.route('/api/doctor-payment-info/<int:doctor_id>')
@login_required
def get_doctor_payment_info(doctor_id):
    """
    API endpoint to get doctor's payment information including balance due
    """
    try:
        # Get doctor info
        doctor = User.query.get_or_404(doctor_id)
        
        # Get date filter from request
        date_filter = request.args.get('date_filter', 'all')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Get assigned services
        assigned_services = ServiceDoctorAssignment.query.filter_by(
            doctor_id=doctor_id,
            is_active=True
        ).all()
        
        if not assigned_services:
            return jsonify({
                'success': True,
                'doctor': {
                    'id': doctor.id,
                    'name': doctor.full_name or doctor.username,
                    'email': doctor.email
                },
                'balance_due': 0,
                'period_earned': 0,
                'total_paid': 0,
                'assigned_services_count': 0
            })
        
        assigned_service_ids = [assignment.service_id for assignment in assigned_services]
        
        # Build date filter condition
        date_filter_condition = True
        if date_filter == 'today':
            today = datetime.now().date()
            date_filter_condition = func.date(Visit.visit_date) == today
        elif date_filter == 'week':
            week_ago = datetime.now() - timedelta(days=7)
            date_filter_condition = Visit.visit_date >= week_ago
        elif date_filter == 'month':
            month_ago = datetime.now() - timedelta(days=30)
            date_filter_condition = Visit.visit_date >= month_ago
        elif date_filter == 'custom' and start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            date_filter_condition = and_(Visit.visit_date >= start, Visit.visit_date <= end)
        
        # Calculate period earned
        doctor_visits = Visit.query.join(Visit.services).filter(
            Service.id.in_(assigned_service_ids),
            Visit.payment_status == 'paid',
            date_filter_condition
        ).all()
        
        period_earned = 0
        for visit in doctor_visits:
            for service in visit.services:
                if service.id in assigned_service_ids:
                    assignment = next((a for a in assigned_services if a.service_id == service.id), None)
                    if assignment:
                        if assignment.payment_type == 'percentage':
                            service_earned = service.special_clinic_price * (assignment.commission_rate / 100)
                        else:
                            service_earned = assignment.fixed_amount or 0
                        period_earned += service_earned
        
        # Calculate total paid with date filtering
        total_paid = 0
        for assignment in assigned_services:
            assignment_payments_query = DoctorPayment.query.filter_by(
                assignment_id=assignment.id,
                status='completed'
            )
            
            # Apply date filter to payments
            if date_filter == 'today':
                assignment_payments_query = assignment_payments_query.filter(func.date(DoctorPayment.payment_date) == today)
            elif date_filter == 'week':
                assignment_payments_query = assignment_payments_query.filter(DoctorPayment.payment_date >= week_ago)
            elif date_filter == 'month':
                assignment_payments_query = assignment_payments_query.filter(DoctorPayment.payment_date >= month_ago)
            elif date_filter == 'custom' and start_date and end_date:
                assignment_payments_query = assignment_payments_query.filter(and_(DoctorPayment.payment_date >= start, DoctorPayment.payment_date <= end))
            
            assignment_payments = assignment_payments_query.all()
            total_paid += sum(payment.amount for payment in assignment_payments)
        
        balance_due = period_earned - total_paid
        
        return jsonify({
            'success': True,
            'doctor': {
                'id': doctor.id,
                'name': doctor.full_name or doctor.username,
                'email': doctor.email
            },
            'balance_due': balance_due,
            'period_earned': period_earned,
            'total_paid': total_paid,
            'assigned_services_count': len(assigned_services),
            'date_filter': date_filter
        })
        
    except Exception as e:
        import traceback
        print(f"Error in get_doctor_payment_info: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@finance_web_bp.route('/api/process-payment/<int:doctor_id>', methods=['POST'])
@login_required
def process_payment(doctor_id):
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['amount', 'payment_method', 'assignment_ids', 'account_type', 'account_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        amount = float(data['amount'])
        payment_method = data['payment_method']
        assignment_ids = data['assignment_ids']
        reference_number = data.get('reference_number', '')
        notes = data.get('notes', '')
        account_type = data['account_type']
        account_id = data['account_id']
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Payment amount must be greater than 0'}), 400
        
        doctor = User.query.get_or_404(doctor_id)
        assignments = ServiceDoctorAssignment.query.filter(
            ServiceDoctorAssignment.id.in_(assignment_ids),
            ServiceDoctorAssignment.doctor_id == doctor_id
        ).all()
        
        if len(assignments) != len(assignment_ids):
            return jsonify({'success': False, 'error': 'Invalid assignment IDs or assignments do not belong to this doctor'}), 400
        
        # Validate account and balance
        if account_type == 'bank':
            account = BankAccount.query.get(account_id)
        elif account_type == 'cash':
            account = CashAccount.query.get(account_id)
        else:
            return jsonify({'success': False, 'error': 'Invalid account type'}), 400
        
        if not account or not account.is_active:
            return jsonify({'success': False, 'error': 'Selected account not found or inactive'}), 400
        
        if account.current_balance < amount:
            return jsonify({'success': False, 'error': f'Insufficient balance in selected account. Available: {account.current_balance:.2f}'}), 400
        
        # Create hospital account transaction (bank or cash)
        bank_tx = None
        cash_tx = None
        if account_type == 'bank':
            bank_tx = BankTransaction(
                bank_account_id=account.id,
                transaction_type='withdrawal',
                amount=amount,
                description=f"Payment to Dr. {doctor.full_name or doctor.username}",
                reference=reference_number,
                created_by=current_user.id
            )
            db.session.add(bank_tx)
            db.session.flush()  # get bank_tx.id
        else:  # cash
            cash_tx = CashTransaction(
                transaction_type='withdrawal',
                amount=amount,
                description=f"Payment to Dr. {doctor.full_name or doctor.username}",
                source_cash_account_id=account.id,
                status='completed',
                completed_at=datetime.utcnow(),
                external_reference=reference_number,
                initiated_by=current_user.id
            )
            cash_tx.transaction_ref = cash_tx.generate_ref()
            db.session.add(cash_tx)
            db.session.flush()  # get cash_tx.id
        
        # Decrease account balance
        account.current_balance -= amount
        
        # Create payment records for each assignment, linking to the transaction
        payments = []
        total_amount = 0
        for assignment in assignments:
            assignment_share = amount / len(assignments)
            payment = DoctorPayment(
                assignment_id=assignment.id,
                amount=assignment_share,
                payment_method=payment_method,
                reference_number=reference_number,
                notes=notes,
                paid_by=current_user.id,
                status='completed',
                payment_date=datetime.utcnow(),
                account_type=account_type,
                account_id=account.id,
                bank_transaction_id=bank_tx.id if bank_tx else None,
                cash_transaction_id=cash_tx.id if cash_tx else None
            )
            db.session.add(payment)
            payments.append(payment)
            total_amount += assignment_share
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Payment of KSH {amount:,.2f} processed successfully',
            'payment': {
                'total_amount': total_amount,
                'payment_method': payment_method,
                'reference_number': reference_number,
                'assignments_count': len(assignments)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        # log error
        return jsonify({'success': False, 'error': str(e)}), 500

@finance_web_bp.route('/doctor-ledger/<int:doctor_id>')
@login_required
def doctor_ledger(doctor_id):


    doctor = User.query.get_or_404(doctor_id)

    # Get all active assignments for this doctor
    assignments = ServiceDoctorAssignment.query.filter_by(
        doctor_id=doctor_id, is_active=True
    ).options(
        db.joinedload(ServiceDoctorAssignment.service)
    ).all()
    assignment_ids = [a.id for a in assignments]

    # ---------------------------
    # 1. Earnings (credits) from paid visits
    # ---------------------------
    earnings = []
    for assignment in assignments:
        service = assignment.service
        # Find all paid visits where this service was provided
        # Using the many-to-many relationship: Visit.services
        visits = Visit.query.filter(
            Visit.services.any(id=service.id),
            Visit.payment_status == 'paid'
        ).options(
            db.joinedload(Visit.patient)
        ).all()

        for visit in visits:
            # Determine the price used for this service based on patient category
            patient_category = visit.patient_category if hasattr(visit, 'patient_category') else 'general'
            if patient_category == 'walkin':
                price = service.walkin_price or service.price
            elif patient_category == 'special_clinic':
                price = service.special_clinic_price or service.price
            else:
                price = service.price

            # Calculate doctor's earning
            if assignment.payment_type == 'percentage':
                earning_amount = price * (assignment.commission_rate / 100)
            else:
                earning_amount = assignment.fixed_amount or 0

            earnings.append({
                'date': visit.visit_date,
                'description': f"Service: {service.name} for {visit.patient.full_name}",
                'credit': earning_amount,
                'debit': 0,
                'type': 'earning',
                'ref': visit.visit_number if hasattr(visit, 'visit_number') else f"Visit #{visit.id}"
            })

    # ---------------------------
    # 2. Payments (debits)
    # ---------------------------
    payments = DoctorPayment.query.filter(
        DoctorPayment.assignment_id.in_(assignment_ids)
    ).order_by(DoctorPayment.payment_date).all()

    payment_entries = []
    for p in payments:
        assignment = next((a for a in assignments if a.id == p.assignment_id), None)
        service_name = assignment.service.name if assignment else 'N/A'

        # Get account name (where money came from)
        account_name = 'N/A'
        if p.account_type == 'bank' and p.bank_transaction_id:
            bank_tx = BankTransaction.query.get(p.bank_transaction_id)
            if bank_tx and bank_tx.bank_account:
                account_name = f"{bank_tx.bank_account.bank_name} ({bank_tx.bank_account.account_number})"
        elif p.account_type == 'cash' and p.cash_transaction_id:
            cash_tx = CashTransaction.query.get(p.cash_transaction_id)
            if cash_tx and cash_tx.source_account:
                account_name = f"{cash_tx.source_account.name} ({cash_tx.source_account.account_type})"

        payment_entries.append({
            'date': p.payment_date,
            'description': f"Payment for {service_name}" + (f" - {p.notes}" if p.notes else ""),
            'credit': 0,
            'debit': p.amount,
            'type': 'payment',
            'ref': p.reference_number or '—',
            'method': p.payment_method,
            'account_name': account_name,
            'paid_by': p.paid_by_user.username if p.paid_by_user else 'System'
        })

    # ---------------------------
    # 3. Combine and sort by date
    # ---------------------------
    all_entries = earnings + payment_entries
    all_entries.sort(key=lambda x: x['date'])

    # Compute running balance
    balance = 0
    for entry in all_entries:
        balance += entry['credit'] - entry['debit']
        entry['balance'] = balance

    # Calculate summary totals
    total_earnings = sum(e['credit'] for e in all_entries)
    total_payments = sum(e['debit'] for e in all_entries)
    net_balance = total_earnings - total_payments

    return render_template(
        'doctor_ledger.html',
        doctor=doctor,
        entries=all_entries,
        total_earnings=total_earnings,
        total_payments=total_payments,
        net_balance=net_balance
    )

@finance_web_bp.route('/api/doctor-assignments/<int:doctor_id>')
@login_required
def get_doctor_assignments(doctor_id):
    """
    API endpoint to get all service assignments for a doctor with current balances
    """
    try:
        # Get assigned services with commission details
        assigned_services = ServiceDoctorAssignment.query.filter_by(
            doctor_id=doctor_id,
            is_active=True
        ).options(
            joinedload(ServiceDoctorAssignment.service)
        ).all()
        
        assignments_data = []
        total_balance_due = 0
        
        for assignment in assigned_services:
            # Calculate earnings for this assignment
            service_visits = Visit.query.join(Visit.services).filter(
                Service.id == assignment.service_id,
                Visit.payment_status == 'paid'
            ).all()
            
            total_revenue = 0
            for visit in service_visits:
                for service in visit.services:
                    if service.id == assignment.service_id:
                        total_revenue += service.special_clinic_price
            
            # Calculate doctor's earnings
            if assignment.payment_type == 'percentage':
                doctor_earnings = total_revenue * (assignment.commission_rate / 100)
            else:
                doctor_earnings = (assignment.fixed_amount or 0) * len(service_visits)
            
            # Calculate payments for this assignment
            assignment_payments = DoctorPayment.query.filter_by(
                assignment_id=assignment.id,
                status='completed'
            ).all()
            
            total_paid = sum(payment.amount for payment in assignment_payments)
            balance_due = doctor_earnings - total_paid
            
            assignments_data.append({
                'assignment_id': assignment.id,
                'service_name': assignment.service.name,
                'service_price': assignment.service.special_clinic_price,
                'payment_type': assignment.payment_type,
                'commission_rate': assignment.commission_rate,
                'fixed_amount': assignment.fixed_amount,
                'total_earnings': doctor_earnings,
                'total_paid': total_paid,
                'balance_due': balance_due,
                'visits_count': len(service_visits)
            })
            
            total_balance_due += balance_due
        
        return jsonify({
            'success': True,
            'assignments': assignments_data,
            'total_balance_due': total_balance_due,
            'assignments_count': len(assignments_data)
        })
        
    except Exception as e:
        import traceback
        print(f"Error in get_doctor_assignments: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@finance_web_bp.route('/supplier-accounts/create', methods=['POST'])
def create_supplier_account():
    """Create a new supplier account"""
    try:
        supplier_id = request.form.get('supplier_id')
        account_type = request.form.get('account_type', 'regular')
        credit_limit = float(request.form.get('credit_limit', 100000.00))
        payment_terms = request.form.get('payment_terms', 'Net 30')
        
        # Check if account already exists
        existing_account = SupplierAccount.query.filter_by(supplier_id=supplier_id).first()
        if existing_account:
            flash('Account already exists for this supplier!', 'warning')
            return redirect(url_for('finance_web_bp.supplier_accounts'))
        
        supplier = Supplier.query.get_or_404(supplier_id)
        
        # Get the next available ID
        last_account = SupplierAccount.query.order_by(SupplierAccount.id.desc()).first()
        next_id = (last_account.id + 1) if last_account else 1
        
        # Generate account number before creating the object
        prefix = "SUP"
        supplier_initials = ''.join([word[0].upper() for word in supplier.name.split()[:3]])
        timestamp = datetime.utcnow().strftime("%y%m")
        account_number = f"{prefix}-{supplier_initials}-{timestamp}-{next_id:04d}"
        
        # Create new account with pre-generated account number
        account = SupplierAccount(
            account_number=account_number,  # Set it directly
            supplier_id=supplier_id,
            account_type=account_type,
            credit_limit=credit_limit,
            current_balance=0.0,
            payment_terms=payment_terms,
            preferred_payment_method='bank_transfer'
        )
        
        db.session.add(account)
        db.session.commit()
        
        flash(f'Account created successfully for {supplier.name}!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating account: {str(e)}', 'danger')

    return redirect(url_for('finance_web_bp.supplier_accounts'))

@finance_web_bp.route('/supplier-accounts/<int:account_id>/update', methods=['POST'])
def update_supplier_account(account_id):
    """Update supplier account"""
    try:
        account = SupplierAccount.query.get_or_404(account_id)
        
        account.credit_limit = float(request.form.get('credit_limit', account.credit_limit))
        account.payment_terms = request.form.get('payment_terms', account.payment_terms)
        account.preferred_payment_method = request.form.get('payment_method', account.preferred_payment_method)
        account.status = request.form.get('status', account.status)
        
        # Update bank details if provided
        if request.form.get('bank_name'):
            account.bank_name = request.form.get('bank_name')
            account.bank_account_number = request.form.get('bank_account_number')
            account.bank_branch = request.form.get('bank_branch')
            account.swift_code = request.form.get('swift_code')
        
        db.session.commit()
        flash('Account updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating account: {str(e)}', 'danger')

    return redirect(url_for('finance_web_bp.supplier_accounts'))




@finance_web_bp.route('/supplier-accounts/<int:account_id>/invoices')
def supplier_invoices(account_id):
    account = SupplierAccount.query.get_or_404(account_id)
    invoices = SupplierInvoice.query.filter_by(
        supplier_account_id=account_id
    ).order_by(SupplierInvoice.invoice_date.desc()).all()

    # Aging buckets
    upcoming_invoices = [
        inv for inv in invoices
        if inv.due_date and inv.due_date <= (datetime.utcnow() + timedelta(days=30))
    ]
    upcoming_balance = sum(inv.balance_due for inv in upcoming_invoices)

    upcoming_31_60 = sum(
        inv.balance_due for inv in invoices
        if inv.due_date and (datetime.utcnow() + timedelta(days=31)) <= inv.due_date <= (datetime.utcnow() + timedelta(days=60))
    )

    overdue_61_plus = sum(
        inv.balance_due for inv in invoices
        if inv.due_date and inv.due_date > (datetime.utcnow() + timedelta(days=60))
    )

    return render_template(
        'supplier_invoices.html',
        account=account,
        invoices=invoices,
        upcoming_31_60=upcoming_31_60,
        upcoming_balance=upcoming_balance,
        overdue_61_plus=overdue_61_plus
    )
    
    
@finance_web_bp.route('/supplier-accounts/<int:account_id>/ledger')
def supplier_account_ledger(account_id):
    account = SupplierAccount.query.get_or_404(account_id)
    transactions = SupplierTransaction.query.filter_by(supplier_account_id=account_id)\
        .order_by(SupplierTransaction.transaction_date.asc()).all()
    
    # Build ledger entries with running balance
    entries = []
    balance = 0
    for tx in transactions:
        if tx.transaction_type == 'invoice':
            debit = tx.amount
            credit = 0
        elif tx.transaction_type == 'payment':
            debit = 0
            credit = tx.amount
        elif tx.transaction_type == 'credit_note':
            debit = 0
            credit = tx.amount
        elif tx.transaction_type == 'debit_note':
            debit = tx.amount
            credit = 0
        else:  # adjustment – treat as debit (you can customize)
            debit = tx.amount if tx.amount > 0 else 0
            credit = -tx.amount if tx.amount < 0 else 0

        balance += debit - credit
        entries.append({
            'date': tx.transaction_date,
            'description': tx.description,
            'reference': tx.reference,
            'invoice_number': tx.invoice.invoice_number if tx.invoice else None,
            'debit': debit,
            'credit': credit,
            'balance': balance
        })
    
    return render_template(
        'supplier_account_ledger.html',
        account=account,
        entries=entries
    )

@finance_web_bp.route('/supplier-invoice/<int:invoice_id>/json')
def get_supplier_invoice(invoice_id):
    invoice = SupplierInvoice.query.get_or_404(invoice_id)
    # Ensure to_dict() includes all fields you want to display
    data = invoice.to_dict()
    return jsonify(data)



@finance_web_bp.route('/supplier-invoice/<int:invoice_id>/payments')
def invoice_payment_history(invoice_id):
    invoice = SupplierInvoice.query.get_or_404(invoice_id)
    # Fetch related payment requests and transactions
    payment_requests = PaymentRequest.query.filter_by(invoice_id=invoice_id).order_by(PaymentRequest.requested_at.desc()).all()
    transactions = SupplierTransaction.query.filter_by(invoice_id=invoice_id).order_by(SupplierTransaction.transaction_date.desc()).all()
    return render_template('invoice_payment_history.html', invoice=invoice, payment_requests=payment_requests, transactions=transactions)
    
@finance_web_bp.route('/supplier-invoice/<int:invoice_id>/void', methods=['POST'])
def void_invoice(invoice_id):
    invoice = SupplierInvoice.query.get_or_404(invoice_id)
    # Only allow voiding if status is not paid or already cancelled
    if invoice.status in ['paid', 'cancelled']:
        return jsonify({'success': False, 'message': 'Invoice cannot be voided in its current state.'}), 400

    invoice.status = 'cancelled'
    # Optionally add a note or audit trail
    db.session.commit()
    return jsonify({'success': True, 'message': 'Invoice voided successfully.'})
    
    
@finance_web_bp.route('/accounts-by-method', methods=['GET'])
def accounts_by_method():
    """Return active accounts for a given payment method."""
    method = request.args.get('method')
    if method in ['bank_transfer', 'cheque']:
        accounts = BankAccount.query.filter_by(is_active=True).all()
        return jsonify([{
            'id': a.id,
            'name': f"{a.bank_name} - {a.account_number}",
            'balance': a.current_balance,
            'type': 'bank'
        } for a in accounts])
    elif method in ['mobile_money', 'cash']:
        accounts = CashAccount.query.filter_by(is_active=True).all()
        return jsonify([{
            'id': a.id,
            'name': f"{a.name} ({a.account_type})",
            'balance': a.current_balance,
            'type': 'cash'
        } for a in accounts])
    else:
        return jsonify([])    

@finance_web_bp.route('/supplier-invoices/<int:invoice_id>/request-payment', methods=['POST'])
def request_invoice_payment(invoice_id):
    try:
        invoice = SupplierInvoice.query.get_or_404(invoice_id)
        payment_data = request.get_json()
        amount = float(payment_data.get('amount'))
        payment_method = payment_data.get('payment_method')
        reference = payment_data.get('reference')
        notes = payment_data.get('notes', '')
        account_type = payment_data.get('account_type')
        account_id = payment_data.get('account_id')

        # Validate basic fields
        if not amount or amount <= 0:
            return jsonify({'success': False, 'message': 'Please enter a valid payment amount'}), 400
        if amount > invoice.balance_due:
            return jsonify({'success': False, 'message': f'Payment amount cannot exceed the balance due of KSh {invoice.balance_due:.2f}'}), 400
        if not reference:
            return jsonify({'success': False, 'message': 'Please enter a payment reference number'}), 400
        if not account_type or not account_id:
            return jsonify({'success': False, 'message': 'Account selection is required'}), 400

        # Validate account and balance
        if account_type == 'bank':
            account = BankAccount.query.get(account_id)
        elif account_type == 'cash':
            account = CashAccount.query.get(account_id)
        else:
            return jsonify({'success': False, 'message': 'Invalid account type'}), 400

        if not account or not account.is_active:
            return jsonify({'success': False, 'message': 'Selected account not found or inactive'}), 400
        if account.current_balance < amount:
            return jsonify({'success': False, 'message': f'Insufficient balance in selected account. Available: {account.current_balance:.2f}'}), 400

        # Check for existing pending payment requests
        existing_request = PaymentRequest.query.filter(
            PaymentRequest.invoice_id == invoice_id,
            PaymentRequest.status.in_(['draft', 'submitted', 'finance_review', 'director_approval'])
        ).first()
        if existing_request:
            return jsonify({'success': False, 'message': f'There is already a pending payment request (ID: {existing_request.id}) for this invoice'}), 400

        # Update invoice status to 'pending'
        invoice.status = 'pending'

        # Create payment request
        payment_request = PaymentRequest(
            invoice_id=invoice_id,
            requested_by=current_user.id,
            amount=amount,
            payment_method=payment_method,
            reference=reference,
            notes=notes,
            status='submitted',
            account_type=account_type,
            account_id=account_id
        )

        db.session.add(payment_request)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Payment request for KSh {amount:.2f} submitted for approval',
            'payment_request_id': payment_request.id,
            'next_approval_step': 'Finance Department Review',
            'invoice_status': invoice.status
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating payment request: {str(e)}")
        return jsonify({'success': False, 'message': f'Error creating payment request: {str(e)}'}), 500
        
        
        
        
@finance_web_bp.route('/approve-payments')
@login_required
def approve_payments():
    """Finance department payment approval dashboard"""
    if not current_user.has_privilege('finance:approve_payments'):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('finance_web_bp.financial_dashboard'))
    
    # Get payment requests pending finance review
    pending_requests = PaymentRequest.query.filter(
        PaymentRequest.status.in_(['submitted', 'finance_review'])
    ).order_by(PaymentRequest.requested_at.desc()).all()
    
    # Get payment request statistics
    stats = {
        'pending_finance': PaymentRequest.query.filter_by(status='submitted').count(),
        'under_review': PaymentRequest.query.filter_by(status='finance_review').count(),
        'pending_director': PaymentRequest.query.filter_by(status='director_approval').count(),
        'total_approved': PaymentRequest.query.filter_by(status='approved').count(),
        'total_rejected': PaymentRequest.query.filter_by(status='rejected').count(),
    }
    
    return render_template('approve_payments.html',
                         pending_requests=pending_requests,
                         stats=stats)

@finance_web_bp.route('/payment-requests/<int:request_id>/finance-review', methods=['POST'])
@login_required
def finance_review_payment(request_id):
    """Finance department reviews and forwards payment request to director"""
    if not current_user.has_privilege('finance:approve_payments'):
        return jsonify({
            'success': False,
            'message': 'Unauthorized: Finance approval permission required'
        }), 403
    
    try:
        payment_request = PaymentRequest.query.get_or_404(request_id)
        
        # Validate that request is in correct status for finance review
        if payment_request.status not in ['submitted', 'finance_review']:
            return jsonify({
                'success': False,
                'message': f'Payment request must be in submitted status. Current status: {payment_request.status}'
            }), 400
        
        data = request.get_json()
        action = data.get('action')  # 'approve' or 'reject'
        notes = data.get('notes', '')
        
        if action == 'approve':
            # Finance approves and forwards to director
            payment_request.approve_by_finance(current_user.id, notes)
            message = 'Payment request forwarded to director for final approval'
            
        elif action == 'reject':
            # Finance rejects the payment request
            payment_request.reject(current_user.id, notes, rejected_by_finance=True)
            message = 'Payment request rejected by finance department'
            
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid action. Must be "approve" or "reject"'
            }), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': message,
            'payment_request': payment_request.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in finance review: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error processing finance review: {str(e)}'
        }), 500

@finance_web_bp.route('/payment-requests/<int:request_id>/finance-details')
@login_required
def finance_payment_details(request_id):
    """Get detailed information for finance review"""
    if not current_user.has_privilege('finance:approve_payments'):
        return jsonify({
            'success': False,
            'message': 'Unauthorized'
        }), 403
    
    payment_request = PaymentRequest.query.get_or_404(request_id)
    
    # Get additional details for finance review
    invoice = payment_request.invoice
    supplier_account = invoice.supplier_account
    supplier = supplier_account.supplier
    
    details = {
        'payment_request': payment_request.to_dict(),
        'invoice': {
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'total_amount': invoice.total_amount,
            'amount_paid': invoice.amount_paid,
            'balance_due': invoice.balance_due,
            'invoice_date': invoice.invoice_date.isoformat(),
            'due_date': invoice.due_date.isoformat(),
            'days_overdue': (datetime.utcnow().date() - invoice.due_date.date()).days if invoice.due_date and datetime.utcnow().date() > invoice.due_date.date() else 0
        },
        'supplier': {
            'name': supplier.name,
            'contact': supplier.contact,
            'phone': supplier.phone,
            'email': supplier.email,
            'rating': supplier.rating
        },
        'supplier_account': {
            'account_number': supplier_account.account_number,
            'current_balance': supplier_account.current_balance,
            'credit_limit': supplier_account.credit_limit,
            'credit_rating': supplier_account.credit_rating
        },
        'purchase_order': {
            'lpo_number': invoice.purchase_order.lpo_number,
            'order_date': invoice.purchase_order.order_date.isoformat(),
            'item_name': invoice.purchase_order.item_name,
            'quantity': invoice.purchase_order.quantity
        }
    }
    
    return jsonify(details)

@finance_web_bp.route('/finance/payment-requests/export')
@login_required
def export_finance_payment_requests():
    """Export payment requests for finance department"""
    if not current_user.has_privilege('finance:approve_payments'):
        flash('Unauthorized', 'danger')
        return redirect(url_for('finance_web_bp.approve_payments'))
    
    # Implementation for exporting to Excel/PDF
    # This would generate and return a file download
    pass





from collections import defaultdict

@finance_web_bp.route('/payroll/payment')
@login_required
def payroll_payment():
    from app.hr.models import Payroll, Payslip
    from app.finance.models import PayrollPayment, BankAccount
    from collections import defaultdict

    approved_payrolls = Payroll.query.filter_by(status='Approved')\
        .order_by(Payroll.approved_at.desc()).all()
    processed_payrolls = Payroll.query.filter_by(status='Processed')\
        .order_by(Payroll.processed_at.desc()).all()
    paid_payrolls = Payroll.query.filter_by(status='Paid')\
        .order_by(Payroll.paid_at.desc()).all()

    for p in paid_payrolls:
        # Fetch payments for this payroll
        p.payments_list = PayrollPayment.query.filter_by(payroll_id=p.id)\
            .order_by(PayrollPayment.transaction_date).all()

        # Group payslips by payment method
        method_groups = defaultdict(list)
        for slip in p.payslips:
            method_name = slip.payment_method.name  # e.g., 'BANK_TRANSFER'
            method_groups[method_name].append({
                'name': slip.employee.full_name,
                'staff_no': slip.employee.payroll_info.staff_no if slip.employee.payroll_info else None,
                'net': slip.net_pay,
                'payment_reference': slip.payment_reference,
                'bank': slip.employee.payroll_info.bank_name if slip.employee.payroll_info else None,
                'account': slip.employee.payroll_info.bank_account if slip.employee.payroll_info else None,
            })
        p.method_employees = dict(method_groups)

    total_approved_net = sum(p.total_net or 0 for p in approved_payrolls)
    total_approved_employees = sum(p.employee_count or len(p.payslips) for p in approved_payrolls)
    total_paid_net = sum(p.total_net or 0 for p in paid_payrolls)
    total_paid_count = len(paid_payrolls)

    return render_template(
        'payroll_payment.html',
        approved_payrolls=approved_payrolls,
        processed_payrolls=processed_payrolls,
        paid_payrolls=paid_payrolls,
        total_approved_net=total_approved_net,
        total_approved_employees=total_approved_employees,
        approved_count=len(approved_payrolls),
        total_paid_net=total_paid_net,
        total_paid_count=total_paid_count
    )



@finance_web_bp.route('/payroll/<int:payroll_id>/process-payment', methods=['GET', 'POST'])
@login_required
def payroll_process_payment(payroll_id):
    from app.hr.models import Payroll, PaymentMethod, DeductionType, PayrollLoan, LoanRepayment, PayslipDeduction, EmployeeDeductionAssignment
    from app.finance.models import BankAccount, CashAccount, BankTransaction, CashTransaction, PayrollPayment
    from decimal import Decimal
    import re

    payroll = Payroll.query.get_or_404(payroll_id)
    if payroll.status != 'Approved':
        flash('Only approved payrolls can be processed.', 'danger')
        return redirect(url_for('finance_web_bp.payroll_payment'))

    if request.method == 'POST':
        # --- Collect payment data from form ---
        payment_records = []
        total_recorded = Decimal('0')
        group_keys = set()

        # Identify all group keys from amount_* fields
        for key in request.form:
            if key.startswith('amount_'):
                group_key = key.replace('amount_', '')
                group_keys.add(group_key)

        for group_key in group_keys:
            amount = Decimal(request.form.get(f'amount_{group_key}', '0') or '0')
            if amount <= 0:
                flash(f"Amount for group must be positive.", 'danger')
                return redirect(url_for('finance_web_bp.payroll_process_payment', payroll_id=payroll.id))

            method_name = request.form.get(f'method_{group_key}')
            if not method_name or method_name not in [m.name for m in PaymentMethod]:
                flash(f"Invalid payment method for group.", 'danger')
                return redirect(...)
            method = PaymentMethod[method_name]

            ref = request.form.get(f'ref_{group_key}', '').strip()
            notes = request.form.get(f'notes_{group_key}', '').strip()
            bank_account_id = request.form.get(f'bank_account_{group_key}')

            # For bank transfers and cheques, a bank account is required
            if method in (PaymentMethod.BANK_TRANSFER, PaymentMethod.CHEQUE) and not bank_account_id:
                flash(f"Bank account is required for {method.value}.", 'danger')
                return redirect(...)

            # Create payment record (not yet committed)
            payment = PayrollPayment(
                payroll_id=payroll.id,
                payment_method=method,
                amount=amount,
                reference=ref,
                bank_account_id=bank_account_id if bank_account_id else None,
                notes=notes,
                created_by=current_user.id
            )
            payment_records.append(payment)
            total_recorded += amount

        # Verify total matches payroll net
        if abs(total_recorded - payroll.total_net) > Decimal('0.01'):
            flash(f"Total recorded amount ({total_recorded:.2f}) does not match payroll net ({payroll.total_net:.2f}).", 'danger')
            return redirect(url_for('finance_web_bp.payroll_process_payment', payroll_id=payroll.id))

        # --- Process each payment and create financial transactions ---
        try:
            for payment in payment_records:
                # Bank Transfer / Cheque
                if payment.payment_method in (PaymentMethod.BANK_TRANSFER, PaymentMethod.CHEQUE):
                    bank = BankAccount.query.get(payment.bank_account_id)
                    if not bank:
                        raise ValueError("Selected bank account not found.")
                    if bank.current_balance < float(payment.amount):
                        raise ValueError(f"Insufficient balance in {bank.bank_name}.")
                    # Create bank transaction
                    bank_tx = BankTransaction(
                        bank_account_id=bank.id,
                        transaction_type='withdrawal',
                        amount=float(payment.amount),
                        description=f"Payroll #{payroll.id} payment",
                        reference=payment.reference,
                        created_by=current_user.id
                    )
                    db.session.add(bank_tx)
                    bank.current_balance -= float(payment.amount)

                # M‑PESA (paybill cash account)
                elif payment.payment_method == PaymentMethod.M_PESA:
                    cash = CashAccount.query.filter_by(account_type='paybill', is_active=True).first()
                    if not cash:
                        raise ValueError("No active paybill cash account configured.")
                    if cash.current_balance < float(payment.amount):
                        raise ValueError(f"Insufficient balance in paybill account.")
                    cash_tx = CashTransaction(
                        transaction_type='withdrawal',
                        amount=float(payment.amount),
                        description=f"Payroll #{payroll.id} via M‑PESA",
                        source_cash_account_id=cash.id,
                        status='completed',
                        completed_at=datetime.utcnow(),
                        external_reference=payment.reference,
                        initiated_by=current_user.id
                    )
                    cash_tx.transaction_ref = cash_tx.generate_ref()
                    db.session.add(cash_tx)
                    cash.current_balance -= float(payment.amount)

                # Cash (cash drawer)
                elif payment.payment_method == PaymentMethod.CASH:
                    cash = CashAccount.query.filter_by(account_type='cash_drawer', is_active=True).first()
                    if not cash:
                        raise ValueError("No active cash drawer account configured.")
                    if cash.current_balance < float(payment.amount):
                        raise ValueError(f"Insufficient balance in cash drawer.")
                    cash_tx = CashTransaction(
                        transaction_type='withdrawal',
                        amount=float(payment.amount),
                        description=f"Payroll #{payroll.id} cash payment",
                        source_cash_account_id=cash.id,
                        status='completed',
                        completed_at=datetime.utcnow(),
                        external_reference=payment.reference,
                        initiated_by=current_user.id
                    )
                    cash_tx.transaction_ref = cash_tx.generate_ref()
                    db.session.add(cash_tx)
                    cash.current_balance -= float(payment.amount)

                # Save payment record
                db.session.add(payment)

            # --- Mark payroll as paid and process loan repayments ---
            payroll.status = 'Paid'
            payroll.paid_at = datetime.utcnow()
            payroll.paid_by = current_user.id
            payroll.paid_at = datetime.utcnow()
            loan_deduction_type = DeductionType.query.filter_by(code='LOAN_REPAYMENT').first()
            total_loan_repayments = Decimal('0')
            loan_repayments_count = 0

            for payslip in payroll.payslips:
                payslip.paid_at = datetime.utcnow()
                payslip.is_paid = True
                payslip.payment_reference = f"PAY-{payroll.id}-{payslip.id}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"

                if loan_deduction_type:
                    loan_deductions = PayslipDeduction.query.filter_by(
                        payslip_id=payslip.id,
                        deduction_type_id=loan_deduction_type.id
                    ).all()

                    for loan_deduction in loan_deductions:
                        active_loans = PayrollLoan.query.filter(
                            PayrollLoan.employee_id == payslip.employee_id,
                            PayrollLoan.is_active == True,
                            PayrollLoan.balance > 0
                        ).order_by(PayrollLoan.created_at.asc()).all()

                        remaining = loan_deduction.amount
                        for loan in active_loans:
                            if remaining <= 0:
                                break
                            deduction = min(remaining, loan.balance)
                            if deduction > 0:
                                repayment = LoanRepayment(
                                    loan_id=loan.id,
                                    amount=deduction,
                                    payment_date=datetime.utcnow().date(),
                                    payslip_id=payslip.id,
                                    description=f"Loan repayment via payroll #{payroll.id}",
                                    created_by=current_user.id
                                )
                                db.session.add(repayment)
                                loan.balance -= deduction
                                # Update assignment balance if exists
                                assignment = EmployeeDeductionAssignment.query.filter_by(
                                    employee_id=payslip.employee_id,
                                    deduction_type_id=loan_deduction_type.id,
                                    is_active=True
                                ).first()
                                if assignment:
                                    assignment.balance = loan.balance
                                if loan.balance <= 0:
                                    loan.is_active = False
                                    loan.end_date = datetime.utcnow().date()
                                    if assignment:
                                        assignment.is_active = False
                                        assignment.end_date = datetime.utcnow().date()
                                remaining -= deduction
                                total_loan_repayments += deduction
                                loan_repayments_count += 1
            # --- Record expense for payroll (salaries) ---
            from app.finance.models import Expense, ExpenseCategory

            # Get or create salaries expense category
            salaries_category = ExpenseCategory.query.filter_by(name='Salaries & Wages').first()
            if not salaries_category:
                salaries_category = ExpenseCategory(
                    name='Salaries & Wages',
                    description='Employee salaries and wages',
                    department='HR',  # or use a default department
                    is_active=True
                )
                db.session.add(salaries_category)
                db.session.flush()  # get id

            # Get HR department (or fallback to first department)
            hr_dept = Department.query.filter_by(name='Human Resources').first()
            if not hr_dept:
                hr_dept = Department.query.first()
                if not hr_dept:
                    # Create a default department if none exists
                    hr_dept = Department(name='General', code='GEN')
                    db.session.add(hr_dept)
                    db.session.flush()

            # Create expense record
            expense = Expense(
                expense_date=datetime.utcnow(),
                amount=float(payroll.total_net),  # net amount paid
                description=f"Payroll #{payroll.id} – {payroll.period.start_date.strftime('%b %Y')}",
                payment_method='Multiple',  # could be refined, but okay
                    expense_type='operational',          # <-- ADD THIS LINE

                category_id=salaries_category.id,
                department_id=hr_dept.id,
                initiated_by=current_user.id,
                status='paid',
                payment_date=datetime.utcnow(),
                payroll_id=payroll.id,
                notes=f"Paid via {len(payment_records)} method(s). References: {', '.join([p.reference or '-' for p in payment_records])}"
            )
            db.session.add(expense)


            # Get all statutory deduction types
            statutory_types = DeductionType.query.filter_by(is_statutory=True).all()
            # Map deduction_type_id -> total amount for this payroll
            stat_totals = {}
            for payslip in payroll.payslips:
                for ded in payslip.deductions:
                    if ded.deduction_type.is_statutory:
                        key = ded.deduction_type_id
                        stat_totals[key] = stat_totals.get(key, 0) + ded.amount

            # For each statutory type, create a liability record (due next month 9th)
            due_date = date.today().replace(day=9) + timedelta(days=30)  # e.g., 9th next month
            for ded_type_id, total_amount in stat_totals.items():
                if total_amount > 0:
                    liability = StatutoryLiability(
                        payroll_id=payroll.id,
                        deduction_type_id=ded_type_id,
                        amount=total_amount,
                        due_date=due_date,
                        paid_at=None
                    )
                    db.session.add(liability)
            # (Optional) also record statutory deductions as separate expenses/liabilities
            # For advanced accounting, you'd split gross into salary expense and deduction liabilities.
            # For now, we keep it simple.
            db.session.commit()
                        # Trigger background email sending for payslips
            try:
                import threading
                thread = threading.Thread(
                    target=send_payslip_emails_background,
                    args=(current_app._get_current_object(), payroll.id, current_user.id)
                )
                thread.daemon = True
                thread.start()
                current_app.logger.info(f"Background email sending started for payroll #{payroll.id}")
            except Exception as email_error:
                current_app.logger.error(f"Failed to start background email sending: {str(email_error)}")
                # Do not rollback; the main transaction succeeded.
                
            flash(f'Payroll #{payroll.id} paid successfully. Processed {loan_repayments_count} loan repayments.', 'success')
            return redirect(url_for('finance_web_bp.payroll_payment'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Payroll payment error: {str(e)}")
            flash(f'Error processing payment: {str(e)}', 'danger')
            return redirect(url_for('finance_web_bp.payroll_process_payment', payroll_id=payroll.id))

    # --- GET request – show form (existing code) ---
    # ... (group payslips, fetch bank_accounts, render template) ...
        # GET – show payment breakdown form
    # Group payslips by payment method and within bank transfer, by bank name
    groups = defaultdict(lambda: {'total': 0, 'count': 0, 'details': []})
    for slip in payroll.payslips:
        method = slip.payment_method
        if method == PaymentMethod.BANK_TRANSFER:
            # Try to get bank name from employee payroll info
            bank_name = 'Unknown Bank'
            if slip.employee.payroll_info and slip.employee.payroll_info.bank_name:
                bank_name = slip.employee.payroll_info.bank_name
            key = f'BANK_TRANSFER_{bank_name}'
            groups[key]['bank_name'] = bank_name
        else:
            key = method.name
        groups[key]['method'] = method
        groups[key]['total'] += slip.net_pay
        groups[key]['count'] += 1
        groups[key]['details'].append(slip)

    # For bank transfer groups, we'll allow selecting a hospital bank account
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()

    return render_template(
        'payroll_process_payment.html',
        payroll=payroll,
        groups=groups,
        bank_accounts=bank_accounts
    )


import threading
import tempfile
import os
from weasyprint import HTML

@finance_web_bp.route('/payroll/<int:payroll_id>/mark-paid', methods=['POST'])
@login_required
def mark_payroll_batch_paid(payroll_id):
    """Mark approved payroll as paid and record loan repayments"""
    try:
        payroll = Payroll.query.get_or_404(payroll_id)
        
        if payroll.status != 'Approved':
            return jsonify({
                'success': False,
                'message': f'Payroll must be Approved before marking as Paid. Current status: {payroll.status}'
            }), 400
        
        # Get loan deduction type
        loan_deduction_type = DeductionType.query.filter_by(code='LOAN_REPAYMENT').first()
        
        # Update payroll status
        payroll.status = 'Paid'
        payroll.paid_at = datetime.utcnow()
        payroll.paid_by = current_user.id
        
        # Track total loan repayments
        total_loan_repayments = Decimal('0')
        loan_repayments_count = 0
        
        # Process each payslip
        for payslip in payroll.payslips:
            # Update payslip status
            payslip.paid_at = datetime.utcnow()
            payslip.is_paid = True
            
            # Generate payment reference
            payslip.payment_reference = f"PAY-{payroll.id}-{payslip.id}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
            
            # Find and process loan deductions for this payslip
            if loan_deduction_type:
                loan_deductions = PayslipDeduction.query.filter_by(
                    payslip_id=payslip.id,
                    deduction_type_id=loan_deduction_type.id
                ).all()
                
                for loan_deduction in loan_deductions:
                    # Get active loans for this employee
                    active_loans = PayrollLoan.query.filter(
                        PayrollLoan.employee_id == payslip.employee_id,
                        PayrollLoan.is_active == True,
                        PayrollLoan.balance > 0
                    ).order_by(PayrollLoan.created_at.asc()).all()
                    
                    if not active_loans:
                        continue
                    
                    # Distribute loan deduction among active loans (oldest first)
                    remaining_deduction = loan_deduction.amount
                    
                    for loan in active_loans:
                        if remaining_deduction <= 0:
                            break
                        
                        # Calculate how much to deduct from this loan
                        deduction_amount = min(remaining_deduction, loan.balance)
                        
                        if deduction_amount > 0:
                            # Create loan repayment record
                            repayment = LoanRepayment(
                                loan_id=loan.id,
                                amount=deduction_amount,
                                payment_date=datetime.utcnow().date(),
                                payslip_id=payslip.id,
                                description=f"Loan repayment via payroll #{payroll.id}",
                                created_by=current_user.id
                            )
                            db.session.add(repayment)
                            
                            # Update loan balance
                            loan.balance -= deduction_amount
                            
                            # Update EmployeeDeductionAssignment balance
                            assignment = EmployeeDeductionAssignment.query.filter_by(
                                employee_id=payslip.employee_id,
                                deduction_type_id=loan_deduction_type.id,
                                is_active=True
                            ).first()
                            
                            if assignment:
                                assignment.balance = loan.balance
                            
                            # Check if loan is fully paid
                            if loan.balance <= 0:
                                loan.is_active = False
                                loan.end_date = datetime.utcnow().date()
                                
                                # Also deactivate the deduction assignment
                                if assignment:
                                    assignment.is_active = False
                                    assignment.end_date = datetime.utcnow().date()
                            
                            # Update tracking
                            remaining_deduction -= deduction_amount
                            total_loan_repayments += deduction_amount
                            loan_repayments_count += 1
        
        db.session.commit()
        
        # Log the payment
        current_app.logger.info(
            f"Payroll marked as paid: ID #{payroll.id} by User {current_user.id}. "
            f"Processed {loan_repayments_count} loan repayments totaling KES {total_loan_repayments}."
        )
        
        return jsonify({
            'success': True,
            'message': f'Payroll marked as paid successfully. Processed {loan_repayments_count} loan repayments.',
            'payroll': {
                'id': payroll.id,
                'status': payroll.status,
                'paid_at': payroll.paid_at.strftime('%Y-%m-%d %H:%M:%S'),
                'payslips_count': len(payroll.payslips),
                'loan_repayments': loan_repayments_count,
                'total_loan_repayments': str(total_loan_repayments)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking payroll as paid: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to mark payroll as paid: {str(e)}'
        }), 500

def send_payslip_emails_background(app, payroll_id, user_id):
    """Background function to send payslip emails with PDF attachments"""
    with app.app_context():
        try:
            from app.utils.notifications import notification_manager
            from sqlalchemy.orm import joinedload
            
            notification_manager.init_app(app)
            
            # Get payroll with all related data
            payroll = Payroll.query.options(
                joinedload(Payroll.period),
                joinedload(Payroll.payslips).joinedload(Payslip.employee).joinedload(User.payroll_info)
            ).get(payroll_id)
            
            if not payroll:
                app.logger.error(f"Payroll {payroll_id} not found for email sending")
                return
            
            emails_sent = 0
            emails_failed = 0
            
            # Create temporary directory for PDFs
            temp_dir = tempfile.mkdtemp(prefix='payslips_')
            app.logger.info(f"Created temp directory: {temp_dir}")
            
            for payslip in payroll.payslips:
                if payslip.employee and payslip.employee.email:
                    try:
                        # Generate PDF using simplified function without current_user
                        pdf_path = generate_payslip_pdf_safe(payslip, temp_dir)
                        
                        if pdf_path and os.path.exists(pdf_path):
                            # Send email with PDF attachment
                            email_sent = send_payslip_email_with_pdf(
                                notification_manager,
                                payslip,
                                payroll,
                                pdf_path
                            )
                            
                            if email_sent:
                                emails_sent += 1
                                app.logger.info(f"Payslip email with PDF sent to {payslip.employee.email}")
                            else:
                                emails_failed += 1
                                app.logger.error(f"Failed to send email to {payslip.employee.email}")
                            
                            # Clean up PDF file after sending
                            try:
                                os.remove(pdf_path)
                            except:
                                pass
                        else:
                            emails_failed += 1
                            app.logger.error(f"Failed to generate PDF for payslip #{payslip.id}")
                            
                    except Exception as e:
                        emails_failed += 1
                        app.logger.error(f"Error processing payslip #{payslip.id}: {str(e)}")
                        import traceback
                        app.logger.error(traceback.format_exc())
            
            # Clean up temp directory
            try:
                os.rmdir(temp_dir)
            except:
                pass
            
            # Log summary
            app.logger.info(
                f"Background email sending completed for payroll #{payroll_id}. "
                f"Emails sent: {emails_sent}, Failed: {emails_failed}"
            )
            
        except Exception as e:
            app.logger.error(f"Error in background email sending: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())


def generate_payslip_pdf_safe(payslip, temp_dir):
    """Generate PDF for a payslip without using Flask's template rendering"""
    try:
        # Load related data with all necessary joins
        from sqlalchemy.orm import joinedload
        
        # Get payslip with all related data
        payslip_with_data = Payslip.query.options(
            joinedload(Payslip.employee).joinedload(User.payroll_info),
            joinedload(Payslip.payroll).joinedload(Payroll.period),
            joinedload(Payslip.earnings).joinedload(PayslipEarning.earning_type),
            joinedload(Payslip.deductions).joinedload(PayslipDeduction.deduction_type)
        ).filter(Payslip.id == payslip.id).first()
        
        if not payslip_with_data:
            return None
        
        # Prepare data
        employee = payslip_with_data.employee
        employee_name = employee.full_name or f"{employee.first_name} {employee.last_name}"
        payroll_info = employee.payroll_info
        
        # Get department if available
        department = employee.department.name if employee.department else "Not Specified"
        
        # Prepare earnings data with category
        earnings_list = []
        statutory_earnings = []
        other_earnings = []
        
        for earning in payslip_with_data.earnings:
            earning_data = {
                'name': earning.earning_type.name,
                'amount': float(earning.amount) if earning.amount else 0,
                'description': earning.description or earning.earning_type.description or '',
                'is_statutory': earning.earning_type.is_statutory if hasattr(earning.earning_type, 'is_statutory') else False
            }
            earnings_list.append(earning_data)
            if earning_data['is_statutory']:
                statutory_earnings.append(earning_data)
            else:
                other_earnings.append(earning_data)
        
        # Prepare deductions data with category
        deductions_list = []
        statutory_deductions = []
        voluntary_deductions = []
        
        for deduction in payslip_with_data.deductions:
            deduction_data = {
                'name': deduction.deduction_type.name,
                'amount': float(deduction.amount) if deduction.amount else 0,
                'description': deduction.description or deduction.deduction_type.description or '',
                'is_statutory': deduction.deduction_type.is_statutory if hasattr(deduction.deduction_type, 'is_statutory') else False,
                'is_voluntary': deduction.deduction_type.is_voluntary if hasattr(deduction.deduction_type, 'is_voluntary') else False
            }
            deductions_list.append(deduction_data)
            if deduction_data['is_statutory']:
                statutory_deductions.append(deduction_data)
            else:
                voluntary_deductions.append(deduction_data)
        
        # Get payroll period info
        payroll_period = payslip_with_data.payroll.period
        
        # Create HTML content
        html_content = create_payslip_html(
            # Hospital/Company Info
            hospital_name="AstroCare Medical Center",
            hospital_address="123 Health Street, Medical Plaza, Nairobi",
            hospital_phone="+254 700 123 456",
            hospital_email="accounts@astrocare.co.ke",
            hospital_logo_url="",  # Can add logo URL if available
            
            # Employee Info
            employee_name=employee_name,
            employee_id=employee.id,
            department=department,
            
            # Payroll Info
            payroll_info=payroll_info,
            staff_no=payroll_info.staff_no if payroll_info and hasattr(payroll_info, 'staff_no') else f"EMP{employee.id:04d}",
            
            # Period Info
            period_start=payroll_period.start_date.strftime('%d %b %Y'),
            period_end=payroll_period.end_date.strftime('%d %b %Y'),
            pay_date=payroll_period.pay_date.strftime('%d %b %Y'),
            frequency=payroll_period.frequency.value if hasattr(payroll_period.frequency, 'value') else str(payroll_period.frequency),
            
            # Payment Info
            payment_method=payroll_info.payment_method.value if payroll_info and payroll_info.payment_method else 'N/A',
            payment_reference=payslip_with_data.payment_reference or f"PY{payslip_with_data.id:06d}",
            
            # Bank Details
            bank_name=payroll_info.bank_name if payroll_info and payroll_info.bank_name else 'Not Provided',
            bank_branch=payroll_info.bank_branch if payroll_info and payroll_info.bank_branch else '',
            bank_account=payroll_info.bank_account if payroll_info and payroll_info.bank_account else '',
            mpesa_number=payroll_info.mpesa_number if payroll_info and payroll_info.mpesa_number else '',
            
            # Statutory Numbers
            kra_pin=payroll_info.kra_pin if payroll_info and payroll_info.kra_pin else '',
            nhif_number=payroll_info.nhif_number if payroll_info and payroll_info.nhif_number else '',
            nssf_number=payroll_info.nssf_number if payroll_info and payroll_info.nssf_number else '',
            sha_number=payroll_info.sha_number if payroll_info and payroll_info.sha_number else '',
            
            # Salary Details
            basic_salary=float(payslip_with_data.basic_salary) if payslip_with_data.basic_salary else 0,
            gross_earnings=float(payslip_with_data.gross_earnings) if payslip_with_data.gross_earnings else 0,
            total_deductions=float(payslip_with_data.total_deductions) if payslip_with_data.total_deductions else 0,
            net_pay=float(payslip_with_data.net_pay) if payslip_with_data.net_pay else 0,
            
            # Earnings Breakdown
            earnings=earnings_list,
            statutory_earnings=statutory_earnings,
            other_earnings=other_earnings,
            
            # Deductions Breakdown
            deductions=deductions_list,
            statutory_deductions=statutory_deductions,
            voluntary_deductions=voluntary_deductions,
            
            # Allowances
            housing_allowance=float(payroll_info.housing_allowance) if payroll_info and payroll_info.housing_allowance else 0,
            transport_allowance=float(payroll_info.transport_allowance) if payroll_info and payroll_info.transport_allowance else 0,
            other_allowance=float(payroll_info.other_allowance) if payroll_info and payroll_info.other_allowance else 0,
            
            # Additional Info
            payroll_id=payslip_with_data.payroll.id,
            payslip_id=payslip_with_data.id,
            generated_date=datetime.utcnow().strftime('%d %b %Y %H:%M'),
            is_paid=payslip_with_data.is_paid,
            paid_at=payslip_with_data.paid_at.strftime('%d %b %Y %H:%M') if payslip_with_data.paid_at else ''
        )
        
        # Generate PDF
        pdf = HTML(string=html_content).write_pdf()
        
        # Save to temporary file
        filename = f"payslip_{employee_name.replace(' ', '_')}_{payroll_period.start_date.strftime('%Y%m')}.pdf"
        pdf_path = os.path.join(temp_dir, filename)
        
        with open(pdf_path, 'wb') as f:
            f.write(pdf)
        
        return pdf_path
        
    except Exception as e:
        current_app.logger.error(f"Error generating PDF for payslip #{payslip.id}: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return None


def create_payslip_html(**kwargs):
    """Create HTML content for payslip without using template rendering"""
    
    # Extract all variables
    # Hospital Info
    hospital_name = kwargs.get('hospital_name', 'AstroCare Medical Center')
    hospital_address = kwargs.get('hospital_address', '123 Health Street, Medical Plaza, Nairobi')
    hospital_phone = kwargs.get('hospital_phone', '+254 700 123 456')
    hospital_email = kwargs.get('hospital_email', 'accounts@astrocare.co.ke')
    
    # Employee Info
    employee_name = kwargs.get('employee_name', '')
    employee_id = kwargs.get('employee_id', '')
    department = kwargs.get('department', 'Not Specified')
    
    # Payroll Info
    staff_no = kwargs.get('staff_no', '')
    payroll_info = kwargs.get('payroll_info', None)
    
    # Period Info
    period_start = kwargs.get('period_start', '')
    period_end = kwargs.get('period_end', '')
    pay_date = kwargs.get('pay_date', '')
    frequency = kwargs.get('frequency', 'Monthly')
    
    # Payment Info
    payment_method = kwargs.get('payment_method', 'N/A')
    payment_reference = kwargs.get('payment_reference', 'N/A')
    
    # Bank Details
    bank_name = kwargs.get('bank_name', 'Not Provided')
    bank_branch = kwargs.get('bank_branch', '')
    bank_account = kwargs.get('bank_account', '')
    mpesa_number = kwargs.get('mpesa_number', '')
    
    # Statutory Numbers
    kra_pin = kwargs.get('kra_pin', '')
    nhif_number = kwargs.get('nhif_number', '')
    nssf_number = kwargs.get('nssf_number', '')
    sha_number = kwargs.get('sha_number', '')
    
    # Salary Details
    basic_salary = kwargs.get('basic_salary', 0)
    gross_earnings = kwargs.get('gross_earnings', 0)
    total_deductions = kwargs.get('total_deductions', 0)
    net_pay = kwargs.get('net_pay', 0)
    
    # Earnings
    earnings = kwargs.get('earnings', [])
    statutory_earnings = kwargs.get('statutory_earnings', [])
    other_earnings = kwargs.get('other_earnings', [])
    
    # Deductions
    deductions = kwargs.get('deductions', [])
    statutory_deductions = kwargs.get('statutory_deductions', [])
    voluntary_deductions = kwargs.get('voluntary_deductions', [])
    
    # Allowances
    housing_allowance = kwargs.get('housing_allowance', 0)
    transport_allowance = kwargs.get('transport_allowance', 0)
    other_allowance = kwargs.get('other_allowance', 0)
    
    # Additional Info
    payroll_id = kwargs.get('payroll_id', '')
    payslip_id = kwargs.get('payslip_id', '')
    generated_date = kwargs.get('generated_date', '')
    is_paid = kwargs.get('is_paid', False)
    paid_at = kwargs.get('paid_at', '')
    
    # Calculate total allowances
    total_allowances = housing_allowance + transport_allowance + other_allowance
    
    # Build earnings rows HTML
    statutory_earnings_rows = ''
    for earning in statutory_earnings:
        statutory_earnings_rows += f'''
        <tr>
            <td>{earning['name']}</td>
            <td class="text-right">{earning['amount']:,.2f}</td>
        </tr>
        '''
    
    other_earnings_rows = ''
    for earning in other_earnings:
        other_earnings_rows += f'''
        <tr>
            <td>{earning['name']}</td>
            <td class="text-right">{earning['amount']:,.2f}</td>
        </tr>
        '''
    
    # Build deductions rows HTML
    statutory_deductions_rows = ''
    for deduction in statutory_deductions:
        statutory_deductions_rows += f'''
        <tr>
            <td>{deduction['name']}</td>
            <td class="text-right">{deduction['amount']:,.2f}</td>
        </tr>
        '''
    
    voluntary_deductions_rows = ''
    for deduction in voluntary_deductions:
        voluntary_deductions_rows += f'''
        <tr>
            <td>{deduction['name']}</td>
            <td class="text-right">{deduction['amount']:,.2f}</td>
        </tr>
        '''
    
    # Complete HTML with modern design
    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payslip - {employee_name} - {period_start} to {period_end}</title>
        <style>
            @page {{
                size: A4;
                margin: 15mm;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.5;
                color: #333;
                margin: 0;
                padding: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            
            .payslip-container {{
                max-width: 794px; /* A4 width in pixels */
                margin: 20px auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                overflow: hidden;
                position: relative;
            }}
            
            /* Watermark */
            .watermark {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%) rotate(-45deg);
                font-size: 80px;
                font-weight: bold;
                color: rgba(79, 70, 229, 0.08);
                pointer-events: none;
                z-index: 1;
            }}
            
            .content {{
                position: relative;
                z-index: 2;
                padding: 30px;
            }}
            
            /* Header Styles */
            .header {{
                background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
                color: white;
                padding: 25px 30px;
                border-radius: 12px 12px 0 0;
            }}
            
            .hospital-info h1 {{
                font-size: 28px;
                font-weight: 700;
                margin: 0 0 5px 0;
                color: white;
            }}
            
            .hospital-info .tagline {{
                font-size: 14px;
                opacity: 0.9;
                margin: 0 0 10px 0;
            }}
            
            .contact-info {{
                display: flex;
                gap: 20px;
                font-size: 13px;
                margin-top: 10px;
            }}
            
            .contact-item {{
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            
            /* Document Title */
            .document-title {{
                text-align: center;
                margin: 25px 0;
                position: relative;
            }}
            
            .document-title h2 {{
                font-size: 32px;
                font-weight: 700;
                color: #1F2937;
                margin: 0;
                display: inline-block;
                padding: 0 20px;
                background: white;
                position: relative;
                z-index: 2;
            }}
            
            .document-title::before {{
                content: '';
                position: absolute;
                top: 50%;
                left: 0;
                right: 0;
                height: 2px;
                background: linear-gradient(90deg, transparent, #4F46E5, transparent);
                z-index: 1;
            }}
            
            /* Status Badge */
            .status-badge {{
                display: inline-block;
                padding: 6px 16px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                margin-left: 15px;
                vertical-align: middle;
                background: {'#10B981' if is_paid else '#F59E0B'};
                color: white;
            }}
            
            /* Info Grid */
            .info-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 25px;
                margin-bottom: 30px;
            }}
            
            .info-card {{
                background: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 20px;
            }}
            
            .info-card h3 {{
                font-size: 14px;
                font-weight: 600;
                color: #6B7280;
                margin: 0 0 15px 0;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .info-row {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 10px;
                padding-bottom: 10px;
                border-bottom: 1px solid #F3F4F6;
            }}
            
            .info-row:last-child {{
                border-bottom: none;
                margin-bottom: 0;
                padding-bottom: 0;
            }}
            
            .info-label {{
                font-weight: 500;
                color: #6B7280;
                font-size: 13px;
            }}
            
            .info-value {{
                font-weight: 600;
                color: #111827;
                font-size: 13px;
                text-align: right;
            }}
            
            /* Summary Cards */
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin: 30px 0;
            }}
            
            .summary-card {{
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
                border: 2px solid;
                position: relative;
                overflow: hidden;
            }}
            
            .summary-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
            }}
            
            .gross-card {{ border-color: #10B981; }}
            .gross-card::before {{ background: #10B981; }}
            
            .deductions-card {{ border-color: #EF4444; }}
            .deductions-card::before {{ background: #EF4444; }}
            
            .net-card {{ border-color: #4F46E5; }}
            .net-card::before {{ background: #4F46E5; }}
            
            .summary-label {{
                font-size: 13px;
                color: #6B7280;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
            }}
            
            .summary-value {{
                font-size: 24px;
                font-weight: 700;
                color: #111827;
            }}
            
            /* Tables */
            .table-container {{
                margin: 30px 0;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid #E5E7EB;
            }}
            
            .table-header {{
                background: #4F46E5;
                color: white;
                padding: 15px 20px;
                font-weight: 600;
                font-size: 15px;
            }}
            
            .table-subheader {{
                background: #F3F4F6;
                padding: 10px 20px;
                font-weight: 600;
                color: #374151;
                font-size: 13px;
                border-top: 1px solid #E5E7EB;
            }}
            
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            
            th {{
                background: #F9FAFB;
                padding: 12px 20px;
                text-align: left;
                font-weight: 600;
                color: #374151;
                font-size: 13px;
                border-bottom: 2px solid #E5E7EB;
            }}
            
            td {{
                padding: 12px 20px;
                border-bottom: 1px solid #F3F4F6;
                font-size: 13px;
            }}
            
            .text-right {{
                text-align: right;
            }}
            
            .total-row {{
                background: #F9FAFB;
                font-weight: 700;
                border-top: 2px solid #E5E7EB;
            }}
            
            /* Footer */
            .footer {{
                margin-top: 40px;
                padding-top: 20px;
                border-top: 2px solid #E5E7EB;
                text-align: center;
                color: #6B7280;
                font-size: 11px;
                line-height: 1.6;
            }}
            
            .footer-links {{
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 10px;
            }}
            
            .footer-links a {{
                color: #4F46E5;
                text-decoration: none;
                font-weight: 500;
            }}
            
            /* QR Code Area */
            .qr-area {{
                margin-top: 30px;
                text-align: center;
                padding: 20px;
                background: #F9FAFB;
                border-radius: 8px;
                border: 1px dashed #D1D5DB;
            }}
            
            .qr-placeholder {{
                width: 100px;
                height: 100px;
                background: #E5E7EB;
                margin: 0 auto 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 4px;
                color: #6B7280;
                font-size: 10px;
            }}
            
            /* Print styles */
            @media print {{
                body {{
                    background: none;
                    margin: 0;
                    padding: 0;
                }}
                
                .payslip-container {{
                    box-shadow: none;
                    margin: 0;
                    border-radius: 0;
                }}
                
                .watermark {{
                    opacity: 0.3;
                }}
                
                .no-print {{
                    display: none;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="watermark">ASTROCARE PAYSLIP</div>
        
        <div class="payslip-container">
            <div class="header">
                <div class="hospital-info">
                    <h1>{hospital_name}</h1>
                    <p class="tagline">Excellence in Healthcare Services</p>
                    <div class="contact-info">
                        <div class="contact-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                            </svg>
                            <span>{hospital_address}</span>
                        </div>
                        <div class="contact-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                            </svg>
                            <span>{hospital_email}</span>
                        </div>
                        <div class="contact-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M20 15.5c-1.25 0-2.45-.2-3.57-.57-.35-.11-.74-.03-1.02.24l-2.2 2.2c-2.83-1.44-5.15-3.75-6.59-6.59l2.2-2.21c.28-.26.36-.65.25-1C8.7 6.45 8.5 5.25 8.5 4c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1 0 9.39 7.61 17 17 17 .55 0 1-.45 1-1v-3.5c0-.55-.45-1-1-1z"/>
                            </svg>
                            <span>{hospital_phone}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="content">
                <!-- Document Title -->
                <div class="document-title">
                    <h2>EMPLOYEE PAYSLIP
                        <span class="status-badge">{'PAID' if is_paid else 'PROCESSED'}</span>
                    </h2>
                </div>
                
                <!-- Information Grid -->
                <div class="info-grid">
                    <!-- Employee Information -->
                    <div class="info-card">
                        <h3>Employee Information</h3>
                        <div class="info-row">
                            <span class="info-label">Full Name:</span>
                            <span class="info-value">{employee_name}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Staff Number:</span>
                            <span class="info-value">{staff_no}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Employee ID:</span>
                            <span class="info-value">{employee_id}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Department:</span>
                            <span class="info-value">{department}</span>
                        </div>
                    </div>
                    
                    <!-- Payment Information -->
                    <div class="info-card">
                        <h3>Payment Information</h3>
                        <div class="info-row">
                            <span class="info-label">Pay Period:</span>
                            <span class="info-value">{period_start} to {period_end}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Pay Date:</span>
                            <span class="info-value">{pay_date}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Payment Method:</span>
                            <span class="info-value">{payment_method}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Reference:</span>
                            <span class="info-value">{payment_reference}</span>
                        </div>
                    </div>
                </div>
                
                <!-- Bank & Statutory Information Grid -->
                <div class="info-grid">
                    <!-- Bank Details -->
                    <div class="info-card">
                        <h3>Bank Details</h3>
                        <div class="info-row">
                            <span class="info-label">Bank Name:</span>
                            <span class="info-value">{bank_name}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Branch:</span>
                            <span class="info-value">{bank_branch or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Account Number:</span>
                            <span class="info-value">{bank_account or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">M-Pesa Number:</span>
                            <span class="info-value">{mpesa_number or 'N/A'}</span>
                        </div>
                    </div>
                    
                    <!-- Statutory Information -->
                    <div class="info-card">
                        <h3>Statutory Information</h3>
                        <div class="info-row">
                            <span class="info-label">KRA PIN:</span>
                            <span class="info-value">{kra_pin or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">NHIF Number:</span>
                            <span class="info-value">{nhif_number or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">NSSF Number:</span>
                            <span class="info-value">{nssf_number or 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">SHA Number:</span>
                            <span class="info-value">{sha_number or 'N/A'}</span>
                        </div>
                    </div>
                </div>
                
                <!-- Summary Cards -->
                <div class="summary-grid">
                    <div class="summary-card gross-card">
                        <div class="summary-label">Gross Earnings</div>
                        <div class="summary-value">KES {gross_earnings:,.2f}</div>
                    </div>
                    
                    <div class="summary-card deductions-card">
                        <div class="summary-label">Total Deductions</div>
                        <div class="summary-value">KES {total_deductions:,.2f}</div>
                    </div>
                    
                    <div class="summary-card net-card">
                        <div class="summary-label">Net Pay</div>
                        <div class="summary-value">KES {net_pay:,.2f}</div>
                    </div>
                </div>
                
                <!-- Earnings Table -->
                <div class="table-container">
                    <div class="table-header">EARNINGS BREAKDOWN</div>
                    
                    <!-- Basic Salary -->
                    <table>
                        <thead>
                            <tr>
                                <th>Description</th>
                                <th class="text-right">Amount (KES)</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><strong>Basic Salary</strong></td>
                                <td class="text-right"><strong>{basic_salary:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <!-- Allowances -->
                    {'<div class="table-subheader">ALLOWANCES</div>' if total_allowances > 0 else ''}
                    {'<table>' if total_allowances > 0 else ''}
                    {'<tbody>' if total_allowances > 0 else ''}
                    {f'<tr><td>Housing Allowance</td><td class="text-right">{housing_allowance:,.2f}</td></tr>' if housing_allowance > 0 else ''}
                    {f'<tr><td>Transport Allowance</td><td class="text-right">{transport_allowance:,.2f}</td></tr>' if transport_allowance > 0 else ''}
                    {f'<tr><td>Other Allowance</td><td class="text-right">{other_allowance:,.2f}</td></tr>' if other_allowance > 0 else ''}
                    {'</tbody>' if total_allowances > 0 else ''}
                    {'</table>' if total_allowances > 0 else ''}
                    
                    <!-- Other Earnings -->
                    {f'<div class="table-subheader">OTHER EARNINGS</div>' if other_earnings else ''}
                    {f'<table>' if other_earnings else ''}
                    {f'<tbody>{other_earnings_rows}</tbody>' if other_earnings else ''}
                    {f'</table>' if other_earnings else ''}
                    
                    <!-- Statutory Earnings -->
                    {f'<div class="table-subheader">STATUTORY EARNINGS</div>' if statutory_earnings else ''}
                    {f'<table>' if statutory_earnings else ''}
                    {f'<tbody>{statutory_earnings_rows}</tbody>' if statutory_earnings else ''}
                    {f'</table>' if statutory_earnings else ''}
                    
                    <!-- Total Gross -->
                    <table>
                        <tbody>
                            <tr class="total-row">
                                <td><strong>TOTAL GROSS EARNINGS</strong></td>
                                <td class="text-right"><strong>{gross_earnings:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Deductions Table -->
                <div class="table-container">
                    <div class="table-header">DEDUCTIONS BREAKDOWN</div>
                    
                    <!-- Statutory Deductions -->
                    {f'<div class="table-subheader">STATUTORY DEDUCTIONS</div>' if statutory_deductions else ''}
                    {f'<table>' if statutory_deductions else ''}
                    {f'<tbody>{statutory_deductions_rows}</tbody>' if statutory_deductions else ''}
                    {f'</table>' if statutory_deductions else ''}
                    
                    <!-- Voluntary Deductions -->
                    {f'<div class="table-subheader">VOLUNTARY DEDUCTIONS</div>' if voluntary_deductions else ''}
                    {f'<table>' if voluntary_deductions else ''}
                    {f'<tbody>{voluntary_deductions_rows}</tbody>' if voluntary_deductions else ''}
                    {f'</table>' if voluntary_deductions else ''}
                    
                    <!-- Total Deductions -->
                    <table>
                        <tbody>
                            <tr class="total-row">
                                <td><strong>TOTAL DEDUCTIONS</strong></td>
                                <td class="text-right"><strong>{total_deductions:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Net Pay Section -->
                <div class="table-container" style="background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); color: white;">
                    <div class="table-header" style="background: transparent; border-bottom: 1px solid rgba(255,255,255,0.2);">
                        PAYMENT SUMMARY
                    </div>
                    <table>
                        <tbody>
                            <tr>
                                <td style="color: white; font-size: 16px;"><strong>GROSS EARNINGS</strong></td>
                                <td class="text-right" style="color: white; font-size: 16px;"><strong>{gross_earnings:,.2f}</strong></td>
                            </tr>
                            <tr>
                                <td style="color: white; opacity: 0.9;">Less: Total Deductions</td>
                                <td class="text-right" style="color: white; opacity: 0.9;">({total_deductions:,.2f})</td>
                            </tr>
                            <tr style="border-top: 2px solid rgba(255,255,255,0.3);">
                                <td style="color: white; font-size: 20px; padding-top: 20px;"><strong>NET PAY</strong></td>
                                <td class="text-right" style="color: white; font-size: 20px; padding-top: 20px;"><strong>KES {net_pay:,.2f}</strong></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Payment Status -->
                {f'<div class="qr-area"><div class="qr-placeholder">PAYMENT CONFIRMED<br>{paid_at}</div><p style="font-size: 12px; color: #6B7280; margin: 0;">Payment confirmed and processed</p></div>' if is_paid else ''}
                
                <!-- Footer -->
                <div class="footer">
                    <p>
                        This payslip was generated by <strong>AstroCare HR System</strong> on {generated_date}.<br>
                        Payroll ID: #{payroll_id} | Payslip ID: #{payslip_id}<br>
                        Frequency: {frequency} | Generated for: {employee_name}
                    </p>
                    <p style="font-size: 10px; margin-top: 15px; color: #9CA3AF;">
                        <strong>Confidential Document:</strong> This payslip contains confidential information and is intended solely for the addressee.<br>
                        Unauthorized disclosure, copying, distribution, or action based on the contents is strictly prohibited.<br>
                        For any discrepancies, please contact the HR department within 7 days of receipt.
                    </p>
                    <div class="footer-links">
                        <span>www.astrocare.co.ke</span>
                        <span>hr@astrocare.co.ke</span>
                        <span>+254 700 123 456</span>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return html


def send_payslip_email_with_pdf(notification_manager, payslip, payroll, pdf_path):
    """Send professional email with PDF attachment"""
    try:
        # Get employee details
        employee = payslip.employee
        employee_name = employee.full_name or f"{employee.first_name} {employee.last_name}"
        
        # Get payroll info for payment details
        payroll_info = employee.payroll_info
        payment_method = payslip.payment_method or (payroll_info.payment_method if payroll_info else None)
        
        # Get bank details
        bank_name = payroll_info.bank_name if payroll_info and payroll_info.bank_name else "Not specified"
        bank_branch = payroll_info.bank_branch if payroll_info and payroll_info.bank_branch else ""
        bank_account = payroll_info.bank_account if payroll_info and payroll_info.bank_account else ""
        mpesa_number = payroll_info.mpesa_number if payroll_info and payroll_info.mpesa_number else ""
        
        # Format payment details based on method
        payment_details = ""
        if payment_method:
            if payment_method.value == "Bank Transfer":
                if bank_account:
                    payment_details = f"<strong>Bank:</strong> {bank_name}<br>"
                    if bank_branch:
                        payment_details += f"<strong>Branch:</strong> {bank_branch}<br>"
                    payment_details += f"<strong>Account:</strong> {bank_account}"
            elif payment_method.value == "M-Pesa":
                if mpesa_number:
                    payment_details = f"<strong>M-Pesa Number:</strong> {mpesa_number}"
            else:
                payment_details = f"<strong>Payment Method:</strong> {payment_method.value}"
        
        # Get period details
        period_start = payroll.period.start_date.strftime('%d %b %Y')
        period_end = payroll.period.end_date.strftime('%d %b %Y')
        payment_date = datetime.utcnow().strftime('%d %b %Y')
        
        # Calculate YTD totals (if available)
        ytd_gross = float(payslip.gross_earnings or 0)  # This would be cumulative in real system
        ytd_deductions = float(payslip.total_deductions or 0)  # This would be cumulative
        
        # Prepare email content
        subject = f"Salary Credited - KES {payslip.net_pay:,.2f} - {period_start} to {period_end}"
        
        # Professional HTML email template
        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Salary Payment Notification</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
                
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    line-height: 1.6;
                    color: #374151;
                    margin: 0;
                    padding: 0;
                    background-color: #f9fafb;
                }}
                
                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                }}
                
                .email-header {{
                    background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
                    color: white;
                    padding: 32px 40px;
                    text-align: center;
                }}
                
                .hospital-logo {{
                    font-size: 24px;
                    font-weight: 700;
                    letter-spacing: -0.5px;
                    margin: 0 0 8px 0;
                }}
                
                .email-title {{
                    font-size: 28px;
                    font-weight: 700;
                    margin: 0;
                    letter-spacing: -0.5px;
                }}
                
                .email-subtitle {{
                    font-size: 16px;
                    opacity: 0.9;
                    margin: 8px 0 0 0;
                    font-weight: 400;
                }}
                
                .email-content {{
                    padding: 40px;
                }}
                
                .greeting {{
                    font-size: 18px;
                    color: #111827;
                    margin-bottom: 24px;
                }}
                
                .salary-amount {{
                    text-align: center;
                    margin: 32px 0;
                    padding: 24px;
                    background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                    border-radius: 12px;
                    color: white;
                }}
                
                .salary-label {{
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    opacity: 0.9;
                    margin-bottom: 8px;
                }}
                
                .salary-value {{
                    font-size: 40px;
                    font-weight: 700;
                    margin: 0;
                }}
                
                .info-card {{
                    background: #F9FAFB;
                    border: 1px solid #E5E7EB;
                    border-radius: 12px;
                    padding: 24px;
                    margin-bottom: 24px;
                }}
                
                .info-card h3 {{
                    color: #4F46E5;
                    margin: 0 0 16px 0;
                    font-size: 16px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .info-grid {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 16px;
                }}
                
                .info-item {{
                    margin-bottom: 12px;
                }}
                
                .info-label {{
                    font-size: 13px;
                    color: #6B7280;
                    font-weight: 500;
                    margin-bottom: 4px;
                }}
                
                .info-value {{
                    font-size: 15px;
                    color: #111827;
                    font-weight: 600;
                }}
                
                .summary-grid {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 16px;
                    margin: 24px 0;
                }}
                
                .summary-box {{
                    background: white;
                    border-radius: 8px;
                    padding: 16px;
                    text-align: center;
                    border: 1px solid #E5E7EB;
                }}
                
                .summary-box.gross {{
                    border-top: 3px solid #10B981;
                }}
                
                .summary-box.deductions {{
                    border-top: 3px solid #EF4444;
                }}
                
                .summary-box.net {{
                    border-top: 3px solid #4F46E5;
                }}
                
                .summary-label {{
                    font-size: 12px;
                    color: #6B7280;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 8px;
                }}
                
                .summary-value {{
                    font-size: 18px;
                    font-weight: 700;
                    color: #111827;
                }}
                
                .attachment-card {{
                    background: #F0F9FF;
                    border: 2px dashed #0EA5E9;
                    border-radius: 12px;
                    padding: 24px;
                    text-align: center;
                    margin: 32px 0;
                }}
                
                .attachment-icon {{
                    background: #0EA5E9;
                    color: white;
                    width: 48px;
                    height: 48px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 16px;
                    font-size: 20px;
                }}
                
                .attachment-text h4 {{
                    color: #0369A1;
                    margin: 0 0 8px 0;
                    font-size: 16px;
                }}
                
                .attachment-text p {{
                    color: #0C4A6E;
                    margin: 0;
                    font-size: 14px;
                }}
                
                .cta-button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
                    color: white;
                    text-decoration: none;
                    padding: 14px 32px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 15px;
                    margin: 8px 0;
                    text-align: center;
                }}
                
                .footer {{
                    margin-top: 40px;
                    padding-top: 24px;
                    border-top: 1px solid #E5E7EB;
                    text-align: center;
                    color: #6B7280;
                    font-size: 13px;
                }}
                
                .contact-info {{
                    display: flex;
                    justify-content: center;
                    gap: 24px;
                    margin-top: 16px;
                }}
                
                .contact-item {{
                    color: #4F46E5;
                    text-decoration: none;
                    font-size: 12px;
                }}
                
                @media (max-width: 600px) {{
                    .info-grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .summary-grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .email-header,
                    .email-content {{
                        padding: 24px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <!-- Header -->
                <div class="email-header">
                    <h1 class="hospital-logo">ASTROCARE MEDICAL CENTER</h1>
                    <h2 class="email-title">Salary Payment Notification</h2>
                    <p class="email-subtitle">Your salary for {period_start} - {period_end} has been processed</p>
                </div>
                
                <!-- Content -->
                <div class="email-content">
                    <!-- Greeting -->
                    <div class="greeting">
                        <p>Dear <strong>{employee_name}</strong>,</p>
                        <p>We are pleased to inform you that your salary for the period <strong>{period_start} to {period_end}</strong> has been successfully processed and credited to your account.</p>
                    </div>
                    
                    <!-- Salary Amount -->
                    <div class="salary-amount">
                        <div class="salary-label">Amount Credited</div>
                        <h2 class="salary-value">KES {payslip.net_pay:,.2f}</h2>
                    </div>
                    
                    <!-- Payment Information -->
                    <div class="info-card">
                        <h3>Payment Information</h3>
                        <div class="info-grid">
                            <div class="info-item">
                                <div class="info-label">Payment Date</div>
                                <div class="info-value">{payment_date}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Payment Method</div>
                                <div class="info-value">{payment_method.value if payment_method else 'N/A'}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Payroll Reference</div>
                                <div class="info-value">#{payroll.id}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Transaction ID</div>
                                <div class="info-value">{payslip.payment_reference}</div>
                            </div>
                        </div>
                        
                        <!-- Bank Details -->
                        {f'<div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #E5E7EB;"><div class="info-label" style="color: #4F46E5; margin-bottom: 8px;">CREDITED TO YOUR ACCOUNT</div><div style="font-size: 14px; color: #111827;">{payment_details}</div></div>' if payment_details else ''}
                    </div>
                    
                    <!-- Salary Summary -->
                    <div class="info-card">
                        <h3>Salary Breakdown</h3>
                        <div class="summary-grid">
                            <div class="summary-box gross">
                                <div class="summary-label">Gross Earnings</div>
                                <div class="summary-value">KES {payslip.gross_earnings:,.2f}</div>
                            </div>
                            <div class="summary-box deductions">
                                <div class="summary-label">Total Deductions</div>
                                <div class="summary-value">KES {payslip.total_deductions:,.2f}</div>
                            </div>
                            <div class="summary-box net">
                                <div class="summary-label">Net Amount</div>
                                <div class="summary-value">KES {payslip.net_pay:,.2f}</div>
                            </div>
                        </div>
                        
                        <!-- Detailed Breakdown -->
                        <div style="margin-top: 24px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #E5E7EB;">
                                <span style="color: #6B7280;">Basic Salary</span>
                                <span style="font-weight: 600;">KES {payslip.basic_salary:,.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #E5E7EB;">
                                <span style="color: #6B7280;">Allowances & Bonuses</span>
                                <span style="font-weight: 600;">KES {(payslip.gross_earnings - payslip.basic_salary):,.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #E5E7EB;">
                                <span style="color: #6B7280;">Statutory Deductions</span>
                                <span style="font-weight: 600; color: #EF4444;">KES {payslip.total_deductions:,.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-top: 16px; padding-top: 16px; border-top: 2px solid #4F46E5;">
                                <span style="color: #4F46E5; font-weight: 700;">Net Salary</span>
                                <span style="font-weight: 700; color: #10B981; font-size: 18px;">KES {payslip.net_pay:,.2f}</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Payslip Attachment -->
                    <div class="attachment-card">
                        <div class="attachment-icon">
                            📄
                        </div>
                        <div class="attachment-text">
                            <h4>Detailed Payslip Attached</h4>
                            <p>Your complete payslip with detailed breakdown is attached as a PDF document.</p>
                        </div>
                        <p style="font-size: 12px; color: #6B7280; margin-top: 12px;">
                            File: payslip_{employee_name.replace(' ', '_')}_{period_start.replace(' ', '')}.pdf
                        </p>
                    </div>
                    
                    <!-- Important Notes -->
                    <div style="background: #FEF3C7; border-left: 4px solid #F59E0B; padding: 16px; border-radius: 8px; margin: 24px 0;">
                        <h4 style="color: #92400E; margin: 0 0 8px 0; font-size: 14px;">⚠️ Important Information</h4>
                        <ul style="color: #92400E; margin: 0; padding-left: 20px; font-size: 13px;">
                            <li>Please verify the credited amount with your bank statement</li>
                            <li>Report any discrepancies to HR within 7 working days</li>
                            <li>Your payslip is a confidential document - keep it secure</li>
                            <li>This is an automated notification - please do not reply</li>
                        </ul>
                    </div>
                    
                    <!-- CTA Buttons -->
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="#" class="cta-button">View in HR Portal</a>
                        <p style="font-size: 12px; color: #6B7280; margin-top: 12px;">
                            Login to the AstroCare HR System for detailed reports
                        </p>
                    </div>
                    
                    <!-- Footer -->
                    <div class="footer">
                        <p>
                            <strong>AstroCare Medical Center - Human Resources Department</strong><br>
                            This is an automated notification generated by the AstroCare HR System.
                        </p>
                        <div class="contact-info">
                            <a href="mailto:hr@astrocare.co.ke" class="contact-item">✉️ hr@astrocare.co.ke</a>
                            <a href="tel:+254700123456" class="contact-item">📞 +254 700 123 456</a>
                            <span class="contact-item">🏥 www.astrocare.co.ke</span>
                        </div>
                        <p style="font-size: 11px; color: #9CA3AF; margin-top: 16px;">
                            Confidentiality Notice: This email contains privileged and confidential information.<br>
                            If you are not the intended recipient, please delete it immediately.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Professional plain text version
        plain_text = f"""
        SALARY PAYMENT NOTIFICATION
        ============================

        Dear {employee_name},

        We are pleased to inform you that your salary for the period {period_start} to {period_end} 
        has been successfully processed and credited to your account.

        PAYMENT DETAILS
        ---------------
        Amount Credited: KES {payslip.net_pay:,.2f}
        Payment Date: {payment_date}
        Payment Method: {payment_method.value if payment_method else 'N/A'}
        Payroll Reference: #{payroll.id}
        Transaction ID: {payslip.payment_reference}

        {f'CREDITED TO: {bank_name} - Account: {bank_account}' if bank_account else ''}
        {f'MPESA NUMBER: {mpesa_number}' if mpesa_number else ''}

        SALARY BREAKDOWN
        ----------------
        Basic Salary: KES {payslip.basic_salary:,.2f}
        Gross Earnings: KES {payslip.gross_earnings:,.2f}
        Total Deductions: KES {payslip.total_deductions:,.2f}
        Net Salary: KES {payslip.net_pay:,.2f}

        ATTACHMENT
        ----------
        Your detailed payslip is attached as a PDF file: 
        payslip_{employee_name.replace(' ', '_')}_{period_start.replace(' ', '')}.pdf

        IMPORTANT NOTES:
        - Please verify the credited amount with your bank statement
        - Report any discrepancies to HR within 7 working days
        - Your payslip is a confidential document
        - This is an automated notification

        For any queries, please contact:
        Human Resources Department
        Email: hr@astrocare.co.ke
        Phone: +254 700 123 456
        Website: www.astrocare.co.ke

        This email contains privileged and confidential information.
        If you are not the intended recipient, please delete it immediately.

        Best regards,
        AstroCare HR System
        """
        
        # Send email with PDF attachment
        return notification_manager.send_email(
            subject=subject,
            recipients=[employee.email],
            body=plain_text,
            html_body=html_body,
            attachments=[pdf_path],
            sender="AstroCare HR System <noreply@astrocare.co.ke>"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error sending email for payslip #{payslip.id}: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return False

# Add a route to check email sending status
@finance_web_bp.route('/payroll/<int:payroll_id>/email-status', methods=['GET'])
@login_required
def get_payslip_email_status(payroll_id):
    """Get status of email sending for a payroll"""
    # This is a placeholder - in a real application, you'd track this in database
    # For now, we just acknowledge that emails are being processed
    
    return jsonify({
        'success': True,
        'message': 'Email sending is in progress',
        'status': 'processing'
    })





def generate_payslip_pdf_in_memory(payslip):
    """Generate PDF in memory (without saving to file)"""
    try:
        from flask import render_template
        
        # Render HTML template
        html = render_template(
            'payslip_pdf_template.html',
            payslip=payslip,
            now=datetime.now()
        )
        
        # Generate PDF
        pdf = HTML(string=html).write_pdf()
        return pdf
        
    except Exception as e:
        current_app.logger.error(f"Error generating PDF in memory: {str(e)}")
        return None


# ----------------------------------------------------------------------
# Treasury Management
# ----------------------------------------------------------------------


@finance_web_bp.route('/bank-reports')
@login_required
def bank_reports():
    # TODO: generate bank summary reports (e.g., deposits, withdrawals, balances)
    return render_template('finance/bank_reports.html')




# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------

@finance_web_bp.route('/sales-reports')
def sales_reports():
    from datetime import datetime
    from sqlalchemy import func, and_

    # Get filter parameters (including new patient_category)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    department_filter = request.args.get('department', '')
    served_by_filter = request.args.get('served_by', '')
    patient_category_filter = request.args.get('patient_category', '')

    today = datetime.today().date()
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today.replace(day=1)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
    except ValueError:
        flash('Invalid date format. Use YYYY-MM-DD.', 'danger')
        start_date = today.replace(day=1)
        end_date = today

    # Base query for SalesReport
    report_query = SalesReport.query.filter(
        SalesReport.sale_date >= datetime.combine(start_date, datetime.min.time()),
        SalesReport.sale_date <= datetime.combine(end_date, datetime.max.time())
    )

    if served_by_filter:
        report_query = report_query.filter(SalesReport.served_by == served_by_filter)
    if patient_category_filter:
        report_query = report_query.filter(SalesReport.patient_category == patient_category_filter)

    reports = report_query.order_by(SalesReport.sale_date.desc()).all()

    # All departments for filter
    all_departments = db.session.query(SalesReportItem.department).distinct().all()
    all_departments = [d[0] for d in all_departments if d[0]]

    # All cashiers for filter dropdown
    distinct_cashiers = db.session.query(SalesReport.served_by).distinct().all()
    distinct_cashiers = sorted([c[0] for c in distinct_cashiers if c[0]])

    # All patient categories for filter
    distinct_categories = db.session.query(SalesReport.patient_category).distinct().all()
    distinct_categories = sorted([c[0] for c in distinct_categories if c[0]])

    # Items query (with all filters)
    items_query = SalesReportItem.query.join(SalesReport).filter(
        SalesReport.sale_date >= datetime.combine(start_date, datetime.min.time()),
        SalesReport.sale_date <= datetime.combine(end_date, datetime.max.time())
    )
    if served_by_filter:
        items_query = items_query.filter(SalesReport.served_by == served_by_filter)
    if department_filter:
        items_query = items_query.filter(SalesReportItem.department == department_filter)
    if patient_category_filter:
        items_query = items_query.filter(SalesReport.patient_category == patient_category_filter)

    items = items_query.all()

    # --- TOTALS AND BREAKDOWNS ---
    total_sales = 0.0
    total_profit = 0.0
    dept_totals = {}               # {department: {'total': x, 'count': y}}
    category_totals = {}            # {category: {'total': x, 'count': y}}
    dept_category_matrix = {}       # {department: {category: {'total': x, 'count': y}}}
    profit_data = []

    for item in items:
        total_sales += item.total_price

        dept = item.department
        cat = item.report.patient_category

        # Department totals
        if dept not in dept_totals:
            dept_totals[dept] = {'total': 0.0, 'count': 0}
        dept_totals[dept]['total'] += item.total_price
        dept_totals[dept]['count'] += item.quantity

        # Category totals
        if cat not in category_totals:
            category_totals[cat] = {'total': 0.0, 'count': 0}
        category_totals[cat]['total'] += item.total_price
        category_totals[cat]['count'] += item.quantity

        # Matrix: department × category
        if dept not in dept_category_matrix:
            dept_category_matrix[dept] = {}
        if cat not in dept_category_matrix[dept]:
            dept_category_matrix[dept][cat] = {'total': 0.0, 'count': 0}
        dept_category_matrix[dept][cat]['total'] += item.total_price
        dept_category_matrix[dept][cat]['count'] += item.quantity

        # Pharmacy profit (existing logic)
        if dept and dept.lower() == 'pharmacy':
            service = Service.query.get(item.service_id)
            buying_price = 0.0
            if service and service.pharmacy_items:
                buying_price = service.pharmacy_items[0].buying_price or 0.0
            item_profit = (item.unit_price - buying_price) * item.quantity
            total_profit += item_profit
            profit_data.append({
                'item_name': item.service_name,
                'quantity': item.quantity,
                'selling_price': item.unit_price,
                'buying_price': buying_price,
                'profit': item_profit,
                'date': item.report.sale_date,
                'served_by': item.report.served_by,
                'patient_category': cat
            })

    grand_total = total_sales

    return render_template(
        'sales_reports.html',
        reports=reports,
        items=items,
        dept_totals=dept_totals,
        category_totals=category_totals,
        dept_category_matrix=dept_category_matrix,
        grand_total=grand_total,
        total_profit=total_profit,
        profit_data=profit_data,
        start_date=start_date,
        end_date=end_date,
        all_departments=all_departments,
        selected_department=department_filter,
        served_by_filter=served_by_filter,
        distinct_cashiers=distinct_cashiers,
        distinct_categories=distinct_categories,
        selected_patient_category=patient_category_filter
    )
    
    
@finance_web_bp.route('/stock-reports')
@login_required
def stock_reports():
    from datetime import datetime, date

    # Fetch all active items from each store
    main_stock = Stock.query.filter_by(is_active=True).all()
    pharmacy_stock = PharmacyInventory.query.all()
    lab_stock = LabInventory.query.all()
    radiology_stock = RadiologyInventory.query.all()

    all_items = []

    # --- Main Store ---
    for item in main_stock:
        all_items.append({
            'id': item.id,
            'name': item.name,
            'category': item.category,
            'quantity': item.quantity or 0,
            'unit': 'units',  # adjust if Stock has a unit field
            'buying_price': item.unit_price or 0.0,
            'selling_price': item.selling_price or 0.0,
            'valuation_cost': item.valuation_at_cost or 0.0,
            'valuation_selling': item.valuation_at_selling_price or 0.0,
            'store_type': 'Main Store',
            'batch': item.batch_number,
            'expiry': item.expiration_date.date() if item.expiration_date else None,
            'location': item.location,
            'reorder_level': item.reorder_level or 0   # added
        })

    # --- Pharmacy ---
    for item in pharmacy_stock:
        all_items.append({
            'id': item.id,
            'name': item.item_name,
            'category': item.category,
            'quantity': item.quantity or 0,
            'unit': item.unit,
            'buying_price': item.buying_price or 0.0,
            'selling_price': item.selling_price or 0.0,
            'valuation_cost': item.valuation_at_cost or 0.0,
            'valuation_selling': item.valuation_at_selling_price or 0.0,
            'store_type': 'Pharmacy',
            'batch': item.batch_number,
            'expiry': item.expiry_date,
            'location': item.location,
            'reorder_level': item.reorder_level or 0
        })

    # --- Laboratory ---
    for item in lab_stock:
        all_items.append({
            'id': item.id,
            'name': item.item_name,
            'category': item.category,
            'quantity': item.quantity or 0,
            'unit': item.unit,
            'buying_price': item.buying_price or 0.0,
            'selling_price': item.selling_price or 0.0,
            'valuation_cost': item.valuation_at_cost or 0.0,
            'valuation_selling': item.valuation_at_selling_price or 0.0,
            'store_type': 'Laboratory',
            'batch': item.batch_number,
            'expiry': item.expiry_date,
            'location': item.location,
            'reorder_level': item.reorder_level or 0
        })

    # --- Radiology ---
    for item in radiology_stock:
        all_items.append({
            'id': item.id,
            'name': item.item_name,
            'category': item.category,
            'quantity': item.quantity or 0,
            'unit': item.unit,
            'buying_price': item.buying_price or 0.0,
            'selling_price': item.selling_price or 0.0,
            'valuation_cost': item.valuation_at_cost or 0.0,
            'valuation_selling': item.valuation_at_selling_price or 0.0,
            'store_type': 'Radiology',
            'batch': item.batch_number,
            'expiry': item.expiry_date,
            'location': item.location,
            'reorder_level': item.reorder_level or 0
        })

    # Overall totals
    total_items = len(all_items)
    total_quantity = sum(item['quantity'] for item in all_items)
    total_cost_value = sum(item['valuation_cost'] for item in all_items)
    total_selling_value = sum(item['valuation_selling'] for item in all_items)

    # Store‑wise summary
    store_summary = {}
    for item in all_items:
        st = item['store_type']
        if st not in store_summary:
            store_summary[st] = {
                'count': 0,
                'quantity': 0,
                'cost_value': 0,
                'selling_value': 0
            }
        store_summary[st]['count'] += 1
        store_summary[st]['quantity'] += item['quantity']
        store_summary[st]['cost_value'] += item['valuation_cost']
        store_summary[st]['selling_value'] += item['valuation_selling']

    # --- Compute alert counts ---
    today = date.today()
    low_stock_count = 0
    expiring_count = 0
    for item in all_items:
        # Low stock: quantity <= reorder_level
        if item['quantity'] <= item['reorder_level']:
            low_stock_count += 1
        # Expiring soon: expiry within 30 days (and not already expired)
        if item['expiry'] and (item['expiry'] - today).days <= 30:
            expiring_count += 1

    return render_template(
        'stock_reports.html',
        all_items=all_items,
        store_summary=store_summary,
        total_items=total_items,
        total_quantity=total_quantity,
        total_cost_value=total_cost_value,
        total_selling_value=total_selling_value,
        low_stock_count=low_stock_count,
        expiring_count=expiring_count,
        now=datetime.utcnow()   # <-- passes current datetime to template
    )

@finance_web_bp.route('/expense-reports')
@login_required
def expense_reports():
    from sqlalchemy import extract, func
    from datetime import datetime, timedelta

    # Get filter parameters
    period = request.args.get('period', 'month')
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    year = request.args.get('year', datetime.now().strftime('%Y'))
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    category_id = request.args.get('category_id', type=int)
    department_id = request.args.get('department_id', type=int)
    status_filter = request.args.get('status')

    # Determine date range
    if period == 'custom' and start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    elif period == 'year':
        start_date = datetime(int(year), 1, 1)
        end_date = datetime(int(year), 12, 31, 23, 59, 59)
    else:  # month default
        year, month_num = map(int, month.split('-'))
        start_date = datetime(year, month_num, 1)
        if month_num == 12:
            end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month_num+1, 1) - timedelta(seconds=1)

    # Base query for paid expenses (or all, depending on need – we'll include status filter)
    query = Expense.query.filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date
    )

    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if department_id:
        query = query.filter(Expense.department_id == department_id)
    if status_filter:
        query = query.filter(Expense.status == status_filter)

    expenses = query.order_by(Expense.expense_date.desc()).all()

    # --- Summary calculations ---
    total_amount = sum(e.amount for e in expenses)
    total_tax = sum(e.tax_amount for e in expenses)
    total_with_tax = total_amount + total_tax

    # Status breakdown
    status_counts = {}
    status_totals = {}
    for e in expenses:
        status_counts[e.status] = status_counts.get(e.status, 0) + 1
        status_totals[e.status] = status_totals.get(e.status, 0) + e.amount + e.tax_amount

    # Category breakdown
    cat_totals = {}
    for e in expenses:
        cat = e.category.name
        cat_totals[cat] = cat_totals.get(cat, 0) + e.amount + e.tax_amount

    # Department breakdown
    dept_totals = {}
    for e in expenses:
        dept = e.department.name
        dept_totals[dept] = dept_totals.get(dept, 0) + e.amount + e.tax_amount

    # Monthly trend (last 12 months)
    months = []
    monthly_data = []
    for i in range(11, -1, -1):
        d = (start_date - timedelta(days=30*i)).replace(day=1)
        month_start = d
        if d.month == 12:
            month_end = datetime(d.year+1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(d.year, d.month+1, 1) - timedelta(seconds=1)
        month_total = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
            Expense.expense_date >= month_start,
            Expense.expense_date <= month_end
        ).scalar() or 0.0
        months.append(d.strftime('%b %Y'))
        monthly_data.append(month_total)

    # For filter dropdowns
    categories = ExpenseCategory.query.all()
    departments = Department.query.all()
    status_options = ['draft', 'submitted', 'approved', 'rejected', 'paid', 'audited']

    return render_template(
        'expense_reports.html',
        start_date=start_date,
        end_date=end_date,
        period=period,
        selected_month=month,
        selected_year=year,
        selected_category=category_id,
        selected_department=department_id,
        selected_status=status_filter,
        categories=categories,
        departments=departments,
        status_options=status_options,
        total_amount=total_amount,
        total_tax=total_tax,
        total_with_tax=total_with_tax,
        status_counts=status_counts,
        status_totals=status_totals,
        cat_totals=cat_totals,
        dept_totals=dept_totals,
        months=months,
        monthly_data=monthly_data,
        expenses=expenses
    )

# ----------------------------------------------------------------------
# Accounting
# ----------------------------------------------------------------------








@finance_web_bp.route('/stock-pricing', methods=['GET', 'POST'])
@login_required
def stock_pricing():
    """
    View and update selling prices of stock items.
    Items are split into two lists: those with selling price set and those without.
    """
    if request.method == 'POST':
        # Update selling price for a single item
        stock_id = request.form.get('stock_id')
        new_price = request.form.get('selling_price')
        
        try:
            stock = Stock.query.get_or_404(stock_id)
            # Validate input
            if new_price is not None and new_price.strip() != '':
                stock.selling_price = float(new_price)
            else:
                stock.selling_price = None   # clear price
            db.session.commit()
            flash(f'Selling price for {stock.name} updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating price: {str(e)}', 'danger')
        
        return redirect(url_for('finance_web_bp.stock_pricing'))
    
    # Get all active stock items with joined supplier
    all_stock = Stock.query.filter_by(is_active=True).options(db.joinedload(Stock.supplier)).all()

    # Split categories for filter
    categories = sorted(set(item.category for item in all_stock if item.category))
    suppliers = sorted(set(item.supplier.name for item in all_stock if item.supplier), key=lambda x: x)

    # Prepare data for template
    stock_list = []
    for s in all_stock:
        stock_list.append({
            'id': s.id,
            'name': s.name,
            'sku': s.sku,
            'category': s.category,
            'unit_price': s.unit_price,
            'selling_price': s.selling_price,
            'supplier': s.supplier.name if s.supplier else 'N/A',
            'quantity': s.quantity,
            'current_stock': s.current_stock,
            'created_at': s.created_at,
            'last_restocked': s.last_restocked,
            'has_price': s.selling_price is not None
        })

    with_price = [s for s in stock_list if s['has_price']]
    without_price = [s for s in stock_list if not s['has_price']]

    return render_template('stock_pricing.html',
                           with_price=with_price,
                           without_price=without_price,
                           categories=categories,
                           suppliers=suppliers,
                           total_items=len(stock_list),
                           priced_count=len(with_price),
                           unpriced_count=len(without_price))
    
    
    

@finance_web_bp.route('/cash-management', methods=['GET', 'POST'])
@login_required
def cash_management():
    from datetime import datetime
    from app.finance.models import CashAccount, BankAccount, CashTransaction

    # Handle form submissions
    if request.method == 'POST':
        action = request.form.get('action')

        # --- Add new cash account ---
        if action == 'add_cash_account':
            name = request.form.get('name')
            account_type = request.form.get('account_type')
            account_number = request.form.get('account_number')
            description = request.form.get('description')
            initial_balance = float(request.form.get('initial_balance', 0))

            if not name or not account_type:
                flash('Name and account type are required.', 'danger')
                return redirect(url_for('finance_web_bp.cash_management'))

            cash_account = CashAccount(
                name=name,
                account_type=account_type,
                account_number=account_number,
                current_balance=initial_balance,
                description=description,
                is_active=True
            )
            db.session.add(cash_account)
            db.session.commit()
            flash(f'Cash account "{name}" created successfully.', 'success')
            return redirect(url_for('finance_web_bp.cash_management'))

        # --- Transfer from cash account to bank ---
        # --- Transfer from cash account to bank ---
        elif action == 'transfer_to_bank':
            cash_account_id = request.form.get('cash_account_id')
            bank_account_id = request.form.get('bank_account_id')
            amount = float(request.form.get('amount'))
            description = request.form.get('description', '')
            batch_ref = request.form.get('batch_ref')

            cash_account = CashAccount.query.get(cash_account_id)
            bank_account = BankAccount.query.get(bank_account_id)

            if not cash_account or not bank_account:
                flash('Invalid cash or bank account.', 'danger')
                return redirect(url_for('finance_web_bp.cash_management'))

            if cash_account.current_balance < amount:
                flash('Insufficient balance in cash account.', 'danger')
                return redirect(url_for('finance_web_bp.cash_management'))

            # Create cash transaction instance without reference
            cash_tx = CashTransaction(
                transaction_type='bank_transfer',
                amount=amount,
                description=description,
                source_cash_account_id=cash_account.id,
                dest_bank_account_id=bank_account.id,
                status='completed',
                completed_at=datetime.utcnow(),
                batch_number=batch_ref,
                initiated_by=current_user.id
            )
            # Generate reference after type is set
            cash_tx.transaction_ref = cash_tx.generate_ref()
            db.session.add(cash_tx)

            # Update cash account balance (decrease)
            cash_account.current_balance -= amount
            db.session.add(cash_account)

            # Update bank account balance (increase)
            bank_account.current_balance += amount
            db.session.add(bank_account)

            db.session.commit()
            flash(f'Successfully transferred {amount} to {bank_account.bank_name}.', 'success')
            return redirect(url_for('finance_web_bp.cash_management'))

    # GET request – fetch data
    cash_accounts = CashAccount.query.filter_by(is_active=True).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()
    # Get recent transactions (last 50)
    recent_transactions = CashTransaction.query.order_by(CashTransaction.initiated_at.desc()).limit(50).all()

    return render_template(
        'cash_management.html',
        cash_accounts=cash_accounts,
        bank_accounts=bank_accounts,
        recent_transactions=recent_transactions
    )
    
    
    
@finance_web_bp.route('/bank-accounts', methods=['GET', 'POST'])
@login_required
def bank_accounts_management():
    from app.finance.models import BankAccount, BankTransaction, CashTransaction
    from datetime import datetime

    if request.method == 'POST':
        action = request.form.get('action')

        # --- Add new bank account ---
        if action == 'add':
            bank_name = request.form.get('bank_name')
            account_name = request.form.get('account_name')
            account_number = request.form.get('account_number')
            branch = request.form.get('branch')
            swift_code = request.form.get('swift_code')
            initial_balance = float(request.form.get('initial_balance', 0))

            if not bank_name or not account_name or not account_number:
                flash('Bank name, account name, and account number are required.', 'danger')
                return redirect(url_for('finance_web_bp.bank_accounts_management'))

            bank = BankAccount(
                bank_name=bank_name,
                account_name=account_name,
                account_number=account_number,
                branch=branch,
                swift_code=swift_code,
                initial_balance=initial_balance,
                current_balance=initial_balance,
                is_active=True
            )
            db.session.add(bank)
            db.session.commit()
            flash('Bank account added successfully.', 'success')
            return redirect(url_for('finance_web_bp.bank_accounts_management'))

        # --- Edit bank account ---
        elif action == 'edit':
            bank_id = request.form.get('bank_id')
            bank = BankAccount.query.get_or_404(bank_id)
            bank.bank_name = request.form.get('bank_name')
            bank.account_name = request.form.get('account_name')
            bank.account_number = request.form.get('account_number')
            bank.branch = request.form.get('branch')
            bank.swift_code = request.form.get('swift_code')
            db.session.commit()
            flash('Bank account updated successfully.', 'success')
            return redirect(url_for('finance_web_bp.bank_accounts_management'))

        # --- Soft delete bank account ---
        elif action == 'delete':
            bank_id = request.form.get('bank_id')
            bank = BankAccount.query.get_or_404(bank_id)
            bank.is_active = False
            db.session.commit()
            flash('Bank account deactivated.', 'success')
            return redirect(url_for('finance_web_bp.bank_accounts_management'))

        # --- Manual deposit ---
        elif action == 'deposit':
            bank_id = request.form.get('bank_id')
            amount = float(request.form.get('amount'))
            description = request.form.get('description')
            reference = request.form.get('reference')

            bank = BankAccount.query.get_or_404(bank_id)
            tx = BankTransaction(
                bank_account_id=bank.id,
                transaction_type='deposit',
                amount=amount,
                description=description,
                reference=reference,
                created_by=current_user.id
            )
            bank.current_balance += amount
            db.session.add(tx)
            db.session.commit()
            flash(f'Deposited {amount} to {bank.bank_name}.', 'success')
            return redirect(url_for('finance_web_bp.bank_accounts_management'))

        # --- Manual withdrawal ---
        elif action == 'withdraw':
            bank_id = request.form.get('bank_id')
            amount = float(request.form.get('amount'))
            description = request.form.get('description')
            reference = request.form.get('reference')

            bank = BankAccount.query.get_or_404(bank_id)
            if bank.current_balance < amount:
                flash('Insufficient balance.', 'danger')
                return redirect(url_for('finance_web_bp.bank_accounts_management'))
            tx = BankTransaction(
                bank_account_id=bank.id,
                transaction_type='withdrawal',
                amount=amount,
                description=description,
                reference=reference,
                created_by=current_user.id
            )
            bank.current_balance -= amount
            db.session.add(tx)
            db.session.commit()
            flash(f'Withdrew {amount} from {bank.bank_name}.', 'success')
            return redirect(url_for('finance_web_bp.bank_accounts_management'))

    # GET request – show all active bank accounts
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()

    # For each account, combine manual and cash transfer transactions for display
    for bank in bank_accounts:
        # Get cash transfers (from CashTransaction) that went to this bank
        cash_transfers = CashTransaction.query.filter_by(
            dest_bank_account_id=bank.id,
            transaction_type='bank_transfer'
        ).all()
        # Get manual transactions
        manual_txs = bank.manual_transactions.order_by(BankTransaction.transaction_date.desc()).all()
        # Combine and sort by date
        combined = []
        for ct in cash_transfers:
            combined.append({
                'date': ct.completed_at or ct.initiated_at,
                'type': 'cash_transfer',
                'amount': ct.amount,
                'description': ct.description,
                'reference': ct.external_reference,
                'source': ct.source_account.name if ct.source_account else 'Cash'
            })
        for mt in manual_txs:
            combined.append({
                'date': mt.transaction_date,
                'type': mt.transaction_type,
                'amount': mt.amount,
                'description': mt.description,
                'reference': mt.reference,
                'source': 'Manual'
            })
        # Sort descending by date
        combined.sort(key=lambda x: x['date'], reverse=True)
        bank.combined_transactions = combined

    # ✅ Compute total recent transactions across all banks
    total_recent_transactions = sum(len(bank.combined_transactions) for bank in bank_accounts)

    return render_template(
        'bank_accounts_management.html',
        bank_accounts=bank_accounts,
        total_recent_transactions=total_recent_transactions
    )


@finance_web_bp.route('/general-ledger')
@login_required
def general_ledger():
    """Show all cash and bank accounts with current balances."""
    cash_accounts = CashAccount.query.filter_by(is_active=True).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()

    # Combine both types with a type indicator
    accounts = []
    for ca in cash_accounts:
        accounts.append({
            'id': ca.id,
            'type': 'cash',
            'name': ca.name,
            'account_number': ca.account_number,
            'balance': ca.current_balance,
            'currency': ca.currency
        })
    for ba in bank_accounts:
        accounts.append({
            'id': ba.id,
            'type': 'bank',
            'name': f"{ba.bank_name} - {ba.account_name}",
            'account_number': ba.account_number,
            'balance': ba.current_balance,
            'currency': 'KES'  # or ba.currency if added
        })

    # Optionally sort by name
    accounts.sort(key=lambda x: x['name'])

    return render_template('general_ledger.html', accounts=accounts)


@finance_web_bp.route('/bank-account/<int:account_id>/ledger')
@login_required
def bank_account_ledger(account_id):
    from datetime import datetime
    account = BankAccount.query.get_or_404(account_id)
    entries = account.get_ledger_entries()  # returns list of dicts with date, description, debit, credit, ref, etc.

    # Date filtering from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        entries = [e for e in entries if e['date'] and e['date'].date() >= start.date()]
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d')
        entries = [e for e in entries if e['date'] and e['date'].date() <= end.date()]

    # Calculate summary totals
    total_debits = sum(e['debit'] for e in entries)
    total_credits = sum(e['credit'] for e in entries)
    # Opening balance = current balance - net change (debits - credits)
    opening_balance = account.current_balance - (total_debits - total_credits)
    closing_balance = account.current_balance

    return render_template(
        'account_ledger.html',
        account=account,
        entries=entries,
        account_type='Bank',
        total_debits=total_debits,
        total_credits=total_credits,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        start_date=start_date,
        end_date=end_date
    )

@finance_web_bp.route('/cash-account/<int:account_id>/ledger')
@login_required
def cash_account_ledger(account_id):
    from datetime import datetime
    account = CashAccount.query.get_or_404(account_id)
    entries = account.get_ledger_entries()  # already sorted

    # Date filtering
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        entries = [e for e in entries if e['date'] and e['date'].date() >= start.date()]
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d')
        entries = [e for e in entries if e['date'] and e['date'].date() <= end.date()]

    # Calculate summary
    total_debits = sum(e['debit'] for e in entries)
    total_credits = sum(e['credit'] for e in entries)
    opening_balance = account.current_balance - (total_debits - total_credits)
    closing_balance = account.current_balance

    return render_template(
        'account_ledger.html',
        account=account,
        entries=entries,
        account_type='Cash',
        total_debits=total_debits,
        total_credits=total_credits,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        start_date=start_date,
        end_date=end_date
    )
    
    
    
# ----------------------------------------------------------------------
# Financial Statements
# ----------------------------------------------------------------------

@finance_web_bp.route('/income-statement', methods=['GET', 'POST'])
@login_required
def income_statement():
    from datetime import datetime, date
    from sqlalchemy import func, extract
    from app.finance.models import Expense, ExpenseCategory
    from app.pharmacy.models import PharmacyInventory

    # Handle date range from request
    period_type = request.args.get('period', 'month')  # 'month', 'year', 'custom'
    selected_month = request.args.get('month', datetime.today().strftime('%Y-%m'))
    selected_year = request.args.get('year', datetime.today().strftime('%Y'))
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    today = date.today()

    if period_type == 'custom' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except:
            flash('Invalid date format. Use YYYY-MM-DD.', 'danger')
            start_date = datetime(today.year, today.month, 1)
            end_date = datetime.now()
    elif period_type == 'year':
        year = int(selected_year)
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    else:  # default month
        year, month = map(int, selected_month.split('-'))
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month+1, 1) - timedelta(seconds=1)

    # --- Revenue ---
    # Total revenue from SalesReport
    revenue_total = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).scalar() or 0.0

    # Revenue by department (from SalesReportItem)
    dept_revenue = db.session.query(
        SalesReportItem.department,
        func.sum(SalesReportItem.total_price).label('total')
    ).join(SalesReport).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).group_by(SalesReportItem.department).all()

    # --- COGS (Pharmacy) ---
    cogs = db.session.query(
        func.sum(PharmacyInventory.buying_price * Medication.quantity)
    ).select_from(Medication).join(
        Service, Medication.service_id == Service.id
    ).join(
        PharmacyInventory, PharmacyInventory.service_id == Service.id
    ).filter(
        Medication.is_paid == True,
        Medication.created_at >= start_date,
        Medication.created_at <= end_date
    ).scalar() or 0.0

    # --- Expenses ---
    # --- Expenses (use expense_date and include tax) ---
    expenses_total = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.status == 'paid'  # optional: only paid expenses
    ).scalar() or 0.0

    # Expenses by category (same fix)
    expenses_by_cat = db.session.query(
        ExpenseCategory.name,
        func.sum(Expense.amount + Expense.tax_amount).label('total')
    ).join(Expense, Expense.category_id == ExpenseCategory.id).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.status == 'paid'
    ).group_by(ExpenseCategory.name).all()

    # --- Calculations ---
    gross_profit = revenue_total - cogs
    net_profit = gross_profit - expenses_total

    return render_template(
        'income_statement.html',
        revenue_total=revenue_total,
        dept_revenue=dept_revenue,
        cogs=cogs,
        expenses_total=expenses_total,
        expenses_by_cat=expenses_by_cat,
        gross_profit=gross_profit,
        net_profit=net_profit,
        start_date=start_date,
        end_date=end_date,
        period_type=period_type,
        selected_month=selected_month,
        selected_year=selected_year
    )







@finance_web_bp.route('/bank-reconciliation')
@login_required
def bank_reconciliation():
    # Get all statements, most recent first
    statements = BankStatement.query.order_by(BankStatement.statement_date.desc()).all()
    # Get accounts for the upload button
    accounts = BankAccount.query.filter_by(is_active=True).all()
    # Statistics
    total_statements = len(statements)
    reconciled = sum(1 for s in statements if s.is_reconciled)
    unreconciled = total_statements - reconciled

    return render_template(
        'bank_reconciliation.html',
        statements=statements,
        accounts=accounts,
        total_statements=total_statements,
        reconciled=reconciled,
        unreconciled=unreconciled
    )


@finance_web_bp.route('/bank-reconciliation/<int:statement_id>')
@login_required
def reconcile_bank(statement_id):
    statement = BankStatement.query.get_or_404(statement_id)
    account = statement.account

    # Get unmatched statement lines
    unmatched_lines = statement.lines.filter_by(is_matched=False).all()

    # Get unmatched bank transactions for this account (not yet matched to any statement line)
    matched_tx_ids = db.session.query(BankStatementLine.matched_transaction_id).filter(
        BankStatementLine.matched_transaction_id.isnot(None)
    ).subquery()
    unmatched_transactions = BankTransaction.query.filter(
        BankTransaction.bank_account_id == account.id,
        BankTransaction.id.notin_(matched_tx_ids)
    ).order_by(BankTransaction.transaction_date).all()

    return render_template(
        'reconcile_bank.html',
        statement=statement,
        account=account,
        unmatched_lines=unmatched_lines,
        unmatched_transactions=unmatched_transactions
    )


ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@finance_web_bp.route('/bank-reconciliation/upload', methods=['GET', 'POST'])
@login_required
def upload_bank_statement():
    if request.method == 'POST':
        account_id = request.form.get('account_id')
        statement_date = request.form.get('statement_date')
        file = request.files.get('statement_file')

        if not account_id or not statement_date or not file:
            flash('All fields are required.', 'danger')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('Only CSV files are allowed.', 'danger')
            return redirect(request.url)

        # Save file
        filename = secure_filename(file.filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        # Create statement record
        statement = BankStatement(
            account_id=account_id,
            statement_date=datetime.strptime(statement_date, '%Y-%m-%d').date(),
            file_path=file_path,
            uploaded_by=current_user.id
        )
        db.session.add(statement)
        db.session.flush()  # get id

        # Parse CSV and create lines
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            # Assume CSV has columns: date, description, reference, amount, balance
            for row in reader:
                line = BankStatementLine(
                    statement_id=statement.id,
                    transaction_date=datetime.strptime(row['date'], '%Y-%m-%d').date(),
                    description=row['description'],
                    reference=row.get('reference', ''),
                    amount=float(row['amount']),
                    balance=float(row.get('balance', 0))
                )
                db.session.add(line)

        # Optionally compute opening/closing balance
        lines = statement.lines.order_by(BankStatementLine.transaction_date).all()
        if lines:
            statement.opening_balance = lines[0].balance - lines[0].amount  # rough estimate
            statement.closing_balance = lines[-1].balance

        db.session.commit()
        flash('Statement uploaded successfully.', 'success')
        return redirect(url_for('finance_web_bp.reconcile_bank', statement_id=statement.id))

    # GET – show upload form
    accounts = BankAccount.query.filter_by(is_active=True).all()
    return render_template('upload_statement.html', accounts=accounts)




@finance_web_bp.route('/bank-reconciliation/match', methods=['POST'])
@login_required
def match_transaction():
    data = request.get_json()
    line_id = data.get('line_id')
    tx_id = data.get('transaction_id')

    line = BankStatementLine.query.get_or_404(line_id)
    tx = BankTransaction.query.get_or_404(tx_id)

    line.matched_transaction_id = tx.id
    line.is_matched = True
    db.session.commit()

    return jsonify({'success': True})



@finance_web_bp.route('/cashflow-analysis')
@login_required
def cashflow_analysis():
    # Date range parameters
    period = request.args.get('period', 'month')  # month, quarter, year, custom
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
        year, month_num = map(int, month.split('-'))
        start_date = datetime(year, month_num, 1)
        if month_num == 12:
            end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month_num+1, 1) - timedelta(seconds=1)

    # ===== Operating Activities =====
    # Inflows: Sales (patient payments)
    operating_inflows = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).scalar() or 0.0

    # Outflows: Operational expenses (non‑capital)
    op_expenses = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.expense_type == 'operational',
        Expense.status == 'paid'
    ).scalar() or 0.0

    # Outflows: Payroll payments
    payroll_payments = db.session.query(func.sum(PayrollPayment.amount)).filter(
        PayrollPayment.transaction_date >= start_date,
        PayrollPayment.transaction_date <= end_date
    ).scalar() or 0.0

    operating_outflows = op_expenses + float(payroll_payments)
    operating_net = operating_inflows - operating_outflows

    # ===== Investing Activities =====
    # Outflows: Capital expenses (equipment, etc.)
    investing_outflows = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.expense_type == 'capital',
        Expense.status == 'paid'
    ).scalar() or 0.0

    # Inflows from asset sales? (Not implemented yet – add later if needed)
    investing_inflows = 0.0
    investing_net = investing_inflows - investing_outflows

    # ===== Financing Activities =====
    # (Optional – you can add Loan model later)
    financing_inflows = 0.0
    financing_outflows = 0.0
    financing_net = financing_inflows - financing_outflows

    # Net cash flow
    net_cash_flow = operating_net + investing_net + financing_net

    # Ending cash balance (sum of all cash and bank accounts)
    total_cash = db.session.query(func.sum(CashAccount.current_balance)).scalar() or 0.0
    total_bank = db.session.query(func.sum(BankAccount.current_balance)).scalar() or 0.0
    ending_balance = total_cash + total_bank

    # ===== Monthly trend data (for chart) =====
    # Get last 12 months of data
    trend_start = end_date - timedelta(days=365)
    months = []
    op_in_trend = []
    op_out_trend = []
    net_trend = []

    current = trend_start.replace(day=1)
    while current <= end_date:
        month_start = current
        if current.month == 12:
            month_end = datetime(current.year+1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(current.year, current.month+1, 1) - timedelta(seconds=1)

        # Calculate monthly operating net
        month_in = db.session.query(func.sum(SalesReport.total_amount)).filter(
            SalesReport.sale_date >= month_start,
            SalesReport.sale_date <= month_end
        ).scalar() or 0.0

        month_op_out = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
            Expense.expense_date >= month_start,
            Expense.expense_date <= month_end,
            Expense.expense_type == 'operational',
            Expense.status == 'paid'
        ).scalar() or 0.0

        month_payroll = db.session.query(func.sum(PayrollPayment.amount)).filter(
            PayrollPayment.transaction_date >= month_start,
            PayrollPayment.transaction_date <= month_end
        ).scalar() or 0.0

        month_out = month_op_out + float(month_payroll or 0)
        month_net = month_in - month_out

        months.append(month_start.strftime('%b %Y'))
        op_in_trend.append(month_in)
        op_out_trend.append(month_out)
        net_trend.append(month_net)

        # next month
        if current.month == 12:
            current = datetime(current.year+1, 1, 1)
        else:
            current = datetime(current.year, current.month+1, 1)

    # ===== Detailed breakdown for display =====
    # Operating details: list of expenses by category
    op_expense_details = db.session.query(
        ExpenseCategory.name,
        func.sum(Expense.amount + Expense.tax_amount).label('total')
    ).join(Expense, Expense.category_id == ExpenseCategory.id).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.expense_type == 'operational',
        Expense.status == 'paid'
    ).group_by(ExpenseCategory.name).all()

    # Payroll details (by month, or just total)
    # Investing details
    investing_details = db.session.query(
        ExpenseCategory.name,
        func.sum(Expense.amount + Expense.tax_amount).label('total')
    ).join(Expense, Expense.category_id == ExpenseCategory.id).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.expense_type == 'capital',
        Expense.status == 'paid'
    ).group_by(ExpenseCategory.name).all()

    return render_template(
        'cashflow_analysis.html',
        start_date=start_date,
        end_date=end_date,
        period=period,
        selected_month=month,
        selected_year=year,
        operating_inflows=operating_inflows,
        operating_outflows=operating_outflows,
        operating_net=operating_net,
        investing_inflows=investing_inflows,
        investing_outflows=investing_outflows,
        investing_net=investing_net,
        financing_inflows=financing_inflows,
        financing_outflows=financing_outflows,
        financing_net=financing_net,
        net_cash_flow=net_cash_flow,
        ending_balance=ending_balance,
        months=months,
        op_in_trend=op_in_trend,
        op_out_trend=op_out_trend,
        net_trend=net_trend,
        op_expense_details=op_expense_details,
        investing_details=investing_details,
        payroll_total=float(payroll_payments)
    )
    
    
@finance_web_bp.route('/reports/ar-aging')
@login_required
def ar_aging():
    from datetime import date, timedelta
    today = date.today()

    invoices = Invoice.query.filter(
        Invoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).all()

    aging = {
        'current': [],
        '30_60': [],
        '60_90': [],
        '90_plus': []
    }

    for inv in invoices:
        due = inv.due_date.date() if inv.due_date else inv.issue_date.date() + timedelta(days=30)
        days_diff = (today - due).days
        balance = inv.balance

        entry = {
            'invoice_number': inv.invoice_number if hasattr(inv, 'invoice_number') else f"INV-{inv.id}",
            'patient_name': inv.patient.full_name,
            'invoice_type': inv.invoice_type,
            'insurance_name': inv.insurance.name if inv.insurance else None,
            'total_amount': inv.total_amount,
            'balance_due': balance,
            'due_date': due.strftime('%Y-%m-%d'),
            'days_overdue': max(0, days_diff)
        }

        if days_diff <= 30:
            aging['current'].append(entry)
        elif 31 <= days_diff <= 60:
            aging['30_60'].append(entry)
        elif 61 <= days_diff <= 90:
            aging['60_90'].append(entry)
        else:
            aging['90_plus'].append(entry)

    # Calculate totals for summary cards
    bucket_totals = {
        'current': sum(e['balance_due'] for e in aging['current']),
        '30_60': sum(e['balance_due'] for e in aging['30_60']),
        '60_90': sum(e['balance_due'] for e in aging['60_90']),
        '90_plus': sum(e['balance_due'] for e in aging['90_plus']),
    }
    total_outstanding = sum(bucket_totals.values())

    return render_template(
        'ar_aging.html',
        aging=aging,
        bucket_totals=bucket_totals,
        total_outstanding=total_outstanding
    )
    
@finance_web_bp.route('/reports/ap-aging')
@login_required
def ap_aging():
    from datetime import date, timedelta
    today = date.today()

    invoices = SupplierInvoice.query.filter(
        SupplierInvoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).all()

    aging = {
        'current': [],
        '30_60': [],
        '60_90': [],
        '90_plus': []
    }

    for inv in invoices:
        due = inv.due_date.date() if inv.due_date else inv.invoice_date.date() + timedelta(days=30)
        days_diff = (today - due).days

        entry = {
            'invoice_number': inv.invoice_number,
            'supplier_name': inv.supplier_account.supplier.name,
            'total_amount': inv.total_amount,
            'balance_due': inv.balance_due,
            'due_date': due.strftime('%Y-%m-%d'),
            'days_overdue': max(0, days_diff)
        }

        if days_diff <= 30:
            aging['current'].append(entry)
        elif 31 <= days_diff <= 60:
            aging['30_60'].append(entry)
        elif 61 <= days_diff <= 90:
            aging['60_90'].append(entry)
        else:
            aging['90_plus'].append(entry)

    # Calculate totals for summary cards
    bucket_totals = {
        'current': sum(inv['balance_due'] for inv in aging['current']),
        '30_60': sum(inv['balance_due'] for inv in aging['30_60']),
        '60_90': sum(inv['balance_due'] for inv in aging['60_90']),
        '90_plus': sum(inv['balance_due'] for inv in aging['90_plus']),
    }
    total_outstanding = sum(bucket_totals.values())

    return render_template(
        'ap_aging.html',
        aging=aging,
        bucket_totals=bucket_totals,
        total_outstanding=total_outstanding
    )





@finance_web_bp.route('/reports/insurance-claims')
@login_required
def insurance_claims_report():
    from sqlalchemy import func

    # Fetch claims with eager loading
    claims = InsuranceClaim.query.options(
        db.joinedload(InsuranceClaim.insurance),
        db.joinedload(InsuranceClaim.claim_responses),
        db.joinedload(InsuranceClaim.invoice).joinedload(Invoice.patient)
    ).order_by(InsuranceClaim.claim_date.desc()).all()

    # Calculate summary totals
    total_claims = len(claims)
    total_approved = sum(
        resp.approved_amount for claim in claims for resp in claim.claim_responses if resp.approved_amount
    ) if claims else 0
    total_denied = sum(
        resp.denied_amount for claim in claims for resp in claim.claim_responses if resp.denied_amount
    ) if claims else 0
    pending_claims = sum(1 for claim in claims if claim.status == 'submitted' and not claim.response_received)

    # Get all insurances for filter dropdown
    insurances = Insurance.query.all()

    return render_template(
        'insurance_claims.html',
        claims=claims,
        total_claims=total_claims,
        total_approved=total_approved,
        total_denied=total_denied,
        pending_claims=pending_claims,
        insurances=insurances
    )




@finance_web_bp.route('/reports/departmental-pnl')
@login_required
def departmental_pnl():
    from sqlalchemy import func
    from datetime import datetime

    period = request.args.get('period', 'month')
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))

    # Define start and end dates
    if period == 'month':
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month+1, 1) - timedelta(seconds=1)
    else:  # year
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)

    # Revenue by department (from SalesReportItem)
    revenue_data = db.session.query(
        SalesReportItem.department,
        func.sum(SalesReportItem.total_price).label('total')
    ).join(SalesReport).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).group_by(SalesReportItem.department).all()

    # Expenses by department (from Expense via Department)
    expense_data = db.session.query(
        Department.name,
        func.sum(Expense.amount + Expense.tax_amount).label('total')
    ).join(Expense, Expense.department_id == Department.id).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.status == 'paid'
    ).group_by(Department.name).all()

    # Merge into a dictionary keyed by department name
    pnl = {}
    for dept, rev in revenue_data:
        pnl.setdefault(dept, {'revenue': 0, 'expenses': 0})
        pnl[dept]['revenue'] = rev

    for dept, exp in expense_data:
        pnl.setdefault(dept, {'revenue': 0, 'expenses': 0})
        pnl[dept]['expenses'] = exp

    # Calculate net profit per department
    for dept in pnl:
        pnl[dept]['net'] = pnl[dept]['revenue'] - pnl[dept]['expenses']

    return render_template(
        'departmental_pnl.html',
        pnl=pnl,
        period=period,
        year=year,
        month=month
    )
    
    
    
    
@finance_web_bp.route('/reports/budget-vs-actual')
@login_required
def budget_vs_actual():
    from sqlalchemy import func
    from datetime import datetime

    year = int(request.args.get('year', datetime.now().year))

    # Get all expense categories with budgets
    categories = ExpenseCategory.query.filter(
        ExpenseCategory.is_active == True,
        ExpenseCategory.budget_allocation > 0
    ).all()

    # Actual expenses for the year
    actuals = db.session.query(
        Expense.category_id,
        func.sum(Expense.amount + Expense.tax_amount).label('total')
    ).filter(
        Expense.expense_date >= datetime(year, 1, 1),
        Expense.expense_date <= datetime(year, 12, 31, 23, 59, 59),
        Expense.status == 'paid'
    ).group_by(Expense.category_id).all()

    actual_dict = {cat_id: total for cat_id, total in actuals}

    report = []
    for cat in categories:
        actual = actual_dict.get(cat.id, 0)
        budget = cat.budget_allocation
        variance = budget - actual
        variance_percent = (variance / budget * 100) if budget else 0
        report.append({
            'category': cat.name,
            'budget': budget,
            'actual': actual,
            'variance': variance,
            'variance_percent': variance_percent
        })

    return render_template('budget_vs_actual.html', report=report, year=year)



@finance_web_bp.route('/trial-balance')
@login_required
def trial_balance():
    from datetime import datetime
    from sqlalchemy import func
    as_at_date = request.args.get('as_at_date')
    if as_at_date:
        as_at = datetime.strptime(as_at_date, '%Y-%m-%d')
    else:
        as_at = datetime.now()

    # --- Debit balances (Assets, Expenses) ---
    # Cash and bank accounts
    cash_total = float(db.session.query(func.sum(CashAccount.current_balance)).scalar() or 0.0)
    bank_total = float(db.session.query(func.sum(BankAccount.current_balance)).scalar() or 0.0)
    cash_bank = cash_total + bank_total

    # Accounts Receivable (unpaid patient invoices)
    ar_total = float(db.session.query(func.sum(Invoice.balance)).filter(
        Invoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar() or 0.0)

    # Inventory valuation (cost) from sub‑stores
    pharm_inv = float(db.session.query(func.sum(PharmacyInventory.buying_price * PharmacyInventory.quantity)).scalar() or 0.0)
    lab_inv = float(db.session.query(func.sum(LabInventory.buying_price * LabInventory.quantity)).scalar() or 0.0)
    rad_inv = float(db.session.query(func.sum(RadiologyInventory.buying_price * RadiologyInventory.quantity)).scalar() or 0.0)
    inventory_total = pharm_inv + lab_inv + rad_inv

    # Paid expenses up to as_at date
    expense_total = float(db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date <= as_at,
        Expense.status == 'paid'
    ).scalar() or 0.0)

    # --- Credit balances (Liabilities, Revenue, Equity) ---
    # Accounts Payable (unpaid supplier invoices)
    ap_total = float(db.session.query(func.sum(SupplierInvoice.balance_due)).filter(
        SupplierInvoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar() or 0.0)

    # Statutory liabilities (unpaid)
    stat_liab = float(db.session.query(func.sum(StatutoryLiability.amount)).filter(
        StatutoryLiability.paid_at.is_(None)
    ).scalar() or 0.0)

    # Revenue (paid sales up to as_at date)
    revenue_total = float(db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date <= as_at
    ).scalar() or 0.0)

    # --- Build the accounts list ---
    accounts = [
        {'name': 'Cash & Bank', 'debit': cash_bank, 'credit': 0.0},
        {'name': 'Accounts Receivable', 'debit': ar_total, 'credit': 0.0},
        {'name': 'Inventory', 'debit': inventory_total, 'credit': 0.0},
        {'name': 'Expenses', 'debit': expense_total, 'credit': 0.0},
        {'name': 'Accounts Payable', 'debit': 0.0, 'credit': ap_total},
        {'name': 'Statutory Liabilities', 'debit': 0.0, 'credit': stat_liab},
        {'name': 'Revenue', 'debit': 0.0, 'credit': revenue_total},
    ]

    # Balancing figure (equity) – ensures debits = credits
    total_debits = sum(a['debit'] for a in accounts)
    total_credits = sum(a['credit'] for a in accounts)
    equity_balancing = total_debits - total_credits

    if abs(equity_balancing) > 0.01:
        # Add as credit if positive, debit if negative
        if equity_balancing > 0:
            accounts.append({'name': 'Equity (Retained Earnings)', 'debit': 0.0, 'credit': equity_balancing})
        else:
            accounts.append({'name': 'Equity (Deficit)', 'debit': -equity_balancing, 'credit': 0.0})

    # Recalculate totals
    total_debits = sum(a['debit'] for a in accounts)
    total_credits = sum(a['credit'] for a in accounts)
    balanced = abs(total_debits - total_credits) < 0.01

    return render_template(
        'trial_balance.html',
        accounts=accounts,
        total_debits=total_debits,
        total_credits=total_credits,
        balanced=balanced,
        as_at_date=as_at.strftime('%Y-%m-%d')
    )
    
    
    
    
from datetime import datetime, timedelta
from sqlalchemy import func

@finance_web_bp.route('/cashflow-statement')
@login_required
def cashflow_statement():
    # Get filter parameters
    period = request.args.get('period', 'month')
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    year = request.args.get('year', datetime.now().strftime('%Y'))
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Determine date range
    if period == 'custom' and start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    elif period == 'year':
        start_date = datetime(int(year), 1, 1)
        end_date = datetime(int(year), 12, 31, 23, 59, 59)
    else:  # month
        y, m = map(int, month.split('-'))
        start_date = datetime(y, m, 1)
        if m == 12:
            end_date = datetime(y+1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(y, m+1, 1) - timedelta(seconds=1)

    # --- Opening cash balance (beginning of period) ---
    opening_cash = db.session.query(
        func.sum(CashAccount.current_balance) + func.sum(BankAccount.current_balance)
    ).filter(
        CashAccount.created_at < start_date,  # approximate; better to use a ledger
        BankAccount.created_at < start_date
    ).scalar() or 0.0
    # Simplified: using current balances as at today. For accurate opening, you'd need historical balances.
    # For demo, we'll compute as (cash at end - net flow). We'll adjust later.
    # Instead, we can compute from transactions: sum of all deposits - withdrawals up to start_date.
    # But that's complex. We'll approximate using current balances minus net flow in period.
    # We'll handle this by computing net cash flow and then deriving opening as closing - net.

    # --- OPERATING ACTIVITIES ---
    # Inflows: cash received from patients
    op_inflows = db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_date,
        SalesReport.sale_date <= end_date
    ).scalar() or 0.0

    # Outflows: operational expenses (paid) + payroll payments
    op_expenses = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.expense_type == 'operational',
        Expense.status == 'paid'
    ).scalar() or 0.0

    payroll_payments = db.session.query(func.sum(PayrollPayment.amount)).filter(
        PayrollPayment.transaction_date >= start_date,
        PayrollPayment.transaction_date <= end_date
    ).scalar() or 0.0

    op_outflows = op_expenses + float(payroll_payments)
    op_net = op_inflows - op_outflows

    # --- INVESTING ACTIVITIES ---
    # Outflows: purchase of fixed assets (capital expenses)
    inv_outflows = db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
        Expense.expense_type == 'capital',
        Expense.status == 'paid'
    ).scalar() or 0.0

    inv_inflows = 0.0  # no asset sales tracked yet
    inv_net = inv_inflows - inv_outflows

    # --- FINANCING ACTIVITIES ---
    fin_inflows = 0.0
    fin_outflows = 0.0
    fin_net = 0.0

    # Net cash flow for the period
    net_cash_flow = op_net + inv_net + fin_net

    # Closing cash balance (actual at end date) – using current balances as proxy
    closing_cash = db.session.query(
        func.sum(CashAccount.current_balance) + func.sum(BankAccount.current_balance)
    ).scalar() or 0.0

    # Derive opening balance from closing minus net flow (for consistency)
    opening_cash = closing_cash - net_cash_flow

    return render_template(
        'cashflow_statement.html',
        start_date=start_date,
        end_date=end_date,
        period=period,
        selected_month=month,
        selected_year=year,
        opening_cash=opening_cash,
        closing_cash=closing_cash,
        op_inflows=op_inflows,
        op_outflows=op_outflows,
        op_net=op_net,
        inv_inflows=inv_inflows,
        inv_outflows=inv_outflows,
        inv_net=inv_net,
        fin_inflows=fin_inflows,
        fin_outflows=fin_outflows,
        fin_net=fin_net,
        net_cash_flow=net_cash_flow
    )
    
    
    
    
@finance_web_bp.route('/balance-sheet')
@login_required
def balance_sheet():


    as_at_date_str = request.args.get('as_at_date')
    if as_at_date_str:
        as_at_date = datetime.strptime(as_at_date_str, '%Y-%m-%d')
    else:
        as_at_date = datetime.now()

    # --- ASSETS ---
    cash_bank = float(db.session.query(func.sum(CashAccount.current_balance)).scalar() or 0.0) + \
                float(db.session.query(func.sum(BankAccount.current_balance)).scalar() or 0.0)

    accounts_receivable = float(db.session.query(func.sum(Invoice.balance)).filter(
        Invoice.status.in_(['pending', 'overdue', 'partially_paid']),
        Invoice.issue_date <= as_at_date
    ).scalar() or 0.0)

    pharm_inv = float(db.session.query(func.sum(PharmacyInventory.buying_price * PharmacyInventory.quantity)).scalar() or 0.0)
    lab_inv = float(db.session.query(func.sum(LabInventory.buying_price * LabInventory.quantity)).scalar() or 0.0)
    rad_inv = float(db.session.query(func.sum(RadiologyInventory.buying_price * RadiologyInventory.quantity)).scalar() or 0.0)
    inventory = pharm_inv + lab_inv + rad_inv

    fixed_assets = float(db.session.query(func.sum(Asset.current_value)).filter(
        Asset.purchase_date <= as_at_date
    ).scalar() or 0.0)

    total_assets = cash_bank + accounts_receivable + inventory + fixed_assets

    # --- LIABILITIES ---
    accounts_payable = float(db.session.query(func.sum(SupplierInvoice.balance_due)).filter(
        SupplierInvoice.status.in_(['pending', 'overdue', 'partially_paid']),
        SupplierInvoice.invoice_date <= as_at_date
    ).scalar() or 0.0)

    statutory_liabilities = float(db.session.query(func.sum(StatutoryLiability.amount)).filter(
        StatutoryLiability.paid_at.is_(None),
        StatutoryLiability.created_at <= as_at_date
    ).scalar() or 0.0)

    loans_payable = 0.0  # placeholder for future loans

    total_liabilities = accounts_payable + statutory_liabilities + loans_payable

    # --- EQUITY ---
    equity = total_assets - total_liabilities

    assets_breakdown = [
        {'name': 'Cash & Bank', 'amount': cash_bank},
        {'name': 'Accounts Receivable', 'amount': accounts_receivable},
        {'name': 'Inventory', 'amount': inventory},
        {'name': 'Fixed Assets', 'amount': fixed_assets},
    ]

    liabilities_breakdown = [
        {'name': 'Accounts Payable', 'amount': accounts_payable},
        {'name': 'Statutory Liabilities', 'amount': statutory_liabilities},
        {'name': 'Loans Payable', 'amount': loans_payable},
    ]

    current_assets = cash_bank + accounts_receivable + inventory
    current_liabilities = accounts_payable + statutory_liabilities   # loans excluded
    working_capital = current_assets - current_liabilities

    return render_template(
        'balance_sheet.html',
        as_at_date=as_at_date.strftime('%Y-%m-%d'),
        assets_breakdown=assets_breakdown,
        liabilities_breakdown=liabilities_breakdown,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        equity=equity,
        working_capital=working_capital
    )
    
    
    
    
    
    
    
    

def get_detailed_financial_data(question):
    """
    Fetch detailed financial data based on keywords in the user's question.
    Returns a formatted string with relevant sections.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func

    today = datetime.today().date()
    start_of_month = today.replace(day=1)
    start_of_quarter = today.replace(month=(today.month - 2) // 3 * 3 + 1, day=1)
    start_of_year = today.replace(month=1, day=1)

    q_lower = question.lower()
    context_parts = []

    # Helper to safely convert any numeric result to float
    def safe_float(value):
        return float(value) if value is not None else 0.0

    # ----------------------------------------------------------------------
    # 1. ALWAYS include the core summary (revenue, expenses, profit, cash)
    # ----------------------------------------------------------------------
    monthly_sales = safe_float(db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_of_month,
        SalesReport.sale_date <= today
    ).scalar())

    monthly_expenses = safe_float(db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_of_month,
        Expense.expense_date <= today,
        Expense.status == 'paid'
    ).scalar())

    quarterly_sales = safe_float(db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_of_quarter,
        SalesReport.sale_date <= today
    ).scalar())

    quarterly_expenses = safe_float(db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_of_quarter,
        Expense.expense_date <= today,
        Expense.status == 'paid'
    ).scalar())

    ytd_sales = safe_float(db.session.query(func.sum(SalesReport.total_amount)).filter(
        SalesReport.sale_date >= start_of_year,
        SalesReport.sale_date <= today
    ).scalar())

    ytd_expenses = safe_float(db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
        Expense.expense_date >= start_of_year,
        Expense.expense_date <= today,
        Expense.status == 'paid'
    ).scalar())

    cash_total = safe_float(db.session.query(func.sum(CashAccount.current_balance)).scalar())
    bank_total = safe_float(db.session.query(func.sum(BankAccount.current_balance)).scalar())

    ar_total = safe_float(db.session.query(func.sum(Invoice.balance)).filter(
        Invoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar())

    ap_total = safe_float(db.session.query(func.sum(SupplierInvoice.balance_due)).filter(
        SupplierInvoice.status.in_(['pending', 'overdue', 'partially_paid'])
    ).scalar())

    context_parts.append(f"## Financial Summary (as of {today.isoformat()})\n")
    context_parts.append(f"### Monthly (from {start_of_month.strftime('%Y-%m-%d')} to {today})\n")
    context_parts.append(f"- Revenue: KES {monthly_sales:,.2f}\n")
    context_parts.append(f"- Expenses: KES {monthly_expenses:,.2f}\n")
    context_parts.append(f"- Profit: KES {monthly_sales - monthly_expenses:,.2f}\n\n")
    context_parts.append(f"### Quarterly (from {start_of_quarter.strftime('%Y-%m-%d')} to {today})\n")
    context_parts.append(f"- Revenue: KES {quarterly_sales:,.2f}\n")
    context_parts.append(f"- Expenses: KES {quarterly_expenses:,.2f}\n")
    context_parts.append(f"- Profit: KES {quarterly_sales - quarterly_expenses:,.2f}\n\n")
    context_parts.append(f"### Year‑to‑Date (from {start_of_year.strftime('%Y-%m-%d')} to {today})\n")
    context_parts.append(f"- Revenue: KES {ytd_sales:,.2f}\n")
    context_parts.append(f"- Expenses: KES {ytd_expenses:,.2f}\n")
    context_parts.append(f"- Profit: KES {ytd_sales - ytd_expenses:,.2f}\n\n")
    context_parts.append(f"### Balance\n")
    context_parts.append(f"- Total Cash & Bank: KES {cash_total + bank_total:,.2f}\n")
    context_parts.append(f"- Accounts Receivable: KES {ar_total:,.2f}\n")
    context_parts.append(f"- Accounts Payable: KES {ap_total:,.2f}\n\n")

    # ----------------------------------------------------------------------
    # 2. Keyword‑based additional sections
    # ----------------------------------------------------------------------

    # --- Income Statement (detailed) ---
    if any(kw in q_lower for kw in ['income statement', 'profit and loss', 'pnl', 'p&l']):
        # Revenue by department
        dept_rev = db.session.query(
            SalesReportItem.department,
            func.sum(SalesReportItem.total_price).label('total')
        ).join(SalesReport).filter(
            SalesReport.sale_date >= start_of_year
        ).group_by(SalesReportItem.department).all()
        # Expenses by category
        expense_cat = db.session.query(
            ExpenseCategory.name,
            func.sum(Expense.amount + Expense.tax_amount).label('total')
        ).join(Expense, Expense.category_id == ExpenseCategory.id).filter(
            Expense.expense_date >= start_of_year,
            Expense.status == 'paid'
        ).group_by(ExpenseCategory.name).all()
        context_parts.append("### Income Statement (Year‑to‑Date)\n")
        context_parts.append("**Revenue:**\n")
        for dept, total in dept_rev:
            context_parts.append(f"- {dept}: KES {safe_float(total):,.2f}\n")
        context_parts.append(f"\n**Total Revenue:** KES {ytd_sales:,.2f}\n\n")
        context_parts.append("**Expenses:**\n")
        for cat, total in expense_cat:
            context_parts.append(f"- {cat}: KES {safe_float(total):,.2f}\n")
        context_parts.append(f"\n**Total Expenses:** KES {ytd_expenses:,.2f}\n")
        context_parts.append(f"**Net Profit:** KES {ytd_sales - ytd_expenses:,.2f}\n\n")

    # --- Balance Sheet ---
    if any(kw in q_lower for kw in ['balance sheet', 'statement of financial position']):
        # Assets
        cash = cash_total + bank_total
        inventory = (
            safe_float(db.session.query(func.sum(PharmacyInventory.buying_price * PharmacyInventory.quantity)).scalar())
            + safe_float(db.session.query(func.sum(LabInventory.buying_price * LabInventory.quantity)).scalar())
            + safe_float(db.session.query(func.sum(RadiologyInventory.buying_price * RadiologyInventory.quantity)).scalar())
        )
        fixed_assets = safe_float(db.session.query(func.sum(Asset.current_value)).filter(
            Asset.purchase_date <= today
        ).scalar())
        total_assets = cash + ar_total + inventory + fixed_assets

        # Liabilities
        statutory = safe_float(db.session.query(func.sum(StatutoryLiability.amount)).filter(
            StatutoryLiability.paid_at.is_(None)
        ).scalar())
        loans = 0.0  # placeholder
        total_liabilities = ap_total + statutory + loans

        equity = total_assets - total_liabilities

        context_parts.append("### Balance Sheet\n")
        context_parts.append("**Assets**\n")
        context_parts.append(f"- Cash & Bank: KES {cash:,.2f}\n")
        context_parts.append(f"- Accounts Receivable: KES {ar_total:,.2f}\n")
        context_parts.append(f"- Inventory: KES {inventory:,.2f}\n")
        context_parts.append(f"- Fixed Assets: KES {fixed_assets:,.2f}\n")
        context_parts.append(f"**Total Assets:** KES {total_assets:,.2f}\n\n")
        context_parts.append("**Liabilities**\n")
        context_parts.append(f"- Accounts Payable: KES {ap_total:,.2f}\n")
        context_parts.append(f"- Statutory Liabilities: KES {statutory:,.2f}\n")
        context_parts.append(f"- Loans Payable: KES {loans:,.2f}\n")
        context_parts.append(f"**Total Liabilities:** KES {total_liabilities:,.2f}\n\n")
        context_parts.append(f"**Equity:** KES {equity:,.2f}\n\n")

    # --- Cash Flow Statement ---
    if any(kw in q_lower for kw in ['cash flow', 'statement of cash flows']):
        # Operating cash flow (simplified)
        op_inflows = ytd_sales
        op_outflows = ytd_expenses
        operating_cf = op_inflows - op_outflows

        # Investing cash flow (capital expenses)
        investing_outflows = safe_float(db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
            Expense.expense_date >= start_of_year,
            Expense.expense_type == 'capital',
            Expense.status == 'paid'
        ).scalar())

        # Financing cash flow (e.g., loans, dividends – not tracked yet)
        financing_cf = 0.0

        net_cash_flow = operating_cf - investing_outflows + financing_cf
        ending_cash = cash_total + bank_total
        opening_cash = ending_cash - net_cash_flow

        context_parts.append("### Cash Flow Statement (Year‑to‑Date)\n")
        context_parts.append("**Operating Activities**\n")
        context_parts.append(f"- Cash from Sales: KES {op_inflows:,.2f}\n")
        context_parts.append(f"- Cash Paid for Expenses: KES {op_outflows:,.2f}\n")
        context_parts.append(f"- Net Operating Cash Flow: KES {operating_cf:,.2f}\n\n")
        context_parts.append("**Investing Activities**\n")
        context_parts.append(f"- Purchase of Fixed Assets: KES {investing_outflows:,.2f}\n")
        context_parts.append(f"- Net Investing Cash Flow: KES -{investing_outflows:,.2f}\n\n")
        context_parts.append("**Financing Activities**\n")
        context_parts.append(f"- Net Financing Cash Flow: KES {financing_cf:,.2f}\n\n")
        context_parts.append(f"**Net Cash Flow:** KES {net_cash_flow:,.2f}\n")
        context_parts.append(f"**Opening Cash Balance:** KES {opening_cash:,.2f}\n")
        context_parts.append(f"**Closing Cash Balance:** KES {ending_cash:,.2f}\n\n")

    # --- Trial Balance ---
    if any(kw in q_lower for kw in ['trial balance']):
        # Debit balances (assets, expenses)
        # We need fixed_assets and inventory defined here – they are not always defined; we can recalc or use previously computed if in scope.
        # For safety, recalc inside this block.
        fixed_assets = safe_float(db.session.query(func.sum(Asset.current_value)).filter(
            Asset.purchase_date <= today
        ).scalar())
        inventory = (
            safe_float(db.session.query(func.sum(PharmacyInventory.buying_price * PharmacyInventory.quantity)).scalar())
            + safe_float(db.session.query(func.sum(LabInventory.buying_price * LabInventory.quantity)).scalar())
            + safe_float(db.session.query(func.sum(RadiologyInventory.buying_price * RadiologyInventory.quantity)).scalar())
        )
        debit_total = cash_total + bank_total + ar_total + inventory + fixed_assets + ytd_expenses
        # Credit balances (liabilities, revenue, equity)
        statutory = safe_float(db.session.query(func.sum(StatutoryLiability.amount)).filter(
            StatutoryLiability.paid_at.is_(None)
        ).scalar())
        credit_total = ap_total + statutory + loans + ytd_sales
        # Equity (balancing figure)
        equity_balance = debit_total - credit_total
        credit_total += equity_balance

        context_parts.append("### Trial Balance\n")
        context_parts.append(f"- **Total Debits:** KES {debit_total:,.2f}\n")
        context_parts.append(f"- **Total Credits:** KES {credit_total:,.2f}\n")
        if abs(debit_total - credit_total) < 0.01:
            context_parts.append("✓ The trial balance is balanced.\n\n")
        else:
            context_parts.append("⚠️ The trial balance is **not** balanced. Investigate discrepancies.\n\n")

    # --- General Ledger ---
    if any(kw in q_lower for kw in ['general ledger', 'ledger']):
        # Combine cash and bank account entries
        ledger = []
        # Cash accounts
        for ca in CashAccount.query.filter_by(is_active=True):
            entries = ca.get_ledger_entries()
            for e in entries:
                ledger.append({
                    'date': e['date'],
                    'account': f"Cash: {ca.name}",
                    'debit': e['debit'],
                    'credit': e['credit'],
                    'balance': e['balance'],
                    'description': e['description']
                })
        # Bank accounts
        for ba in BankAccount.query.filter_by(is_active=True):
            entries = ba.get_ledger_entries()
            for e in entries:
                ledger.append({
                    'date': e['date'],
                    'account': f"Bank: {ba.bank_name} - {ba.account_number}",
                    'debit': e['debit'],
                    'credit': e['credit'],
                    'balance': e['balance'],
                    'description': e['description']
                })
        # Sort by date
        ledger.sort(key=lambda x: x['date'])
        # Limit to last 50 entries for brevity
        context_parts.append("### General Ledger (Last 50 entries)\n")
        for entry in ledger[-50:]:
            date_str = entry['date'].strftime('%Y-%m-%d') if entry['date'] else 'N/A'
            context_parts.append(f"- {date_str} | {entry['account']} | {entry['description']} | Debit: {entry['debit']:,.2f} | Credit: {entry['credit']:,.2f} | Balance: {entry['balance']:,.2f}\n")
        context_parts.append("\n")

    # --- Stock Valuation Report ---
    if any(kw in q_lower for kw in ['stock valuation', 'inventory valuation', 'stock report']):
        # Main store stock
        main_stock = db.session.query(Stock).filter_by(is_active=True).all()
        main_value = sum(safe_float(s.quantity or 0) * safe_float(s.unit_price or 0) for s in main_stock)
        # Pharmacy
        pharm_items = db.session.query(PharmacyInventory).all()
        pharm_value = sum(safe_float(i.quantity) * safe_float(i.buying_price) for i in pharm_items)
        # Lab
        lab_items = db.session.query(LabInventory).all()
        lab_value = sum(safe_float(i.quantity) * safe_float(i.buying_price) for i in lab_items)
        # Radiology
        rad_items = db.session.query(RadiologyInventory).all()
        rad_value = sum(safe_float(i.quantity) * safe_float(i.buying_price) for i in rad_items)

        total_stock_value = main_value + pharm_value + lab_value + rad_value
        context_parts.append("### Stock Valuation Report\n")
        context_parts.append(f"- **Main Store:** KES {main_value:,.2f}\n")
        context_parts.append(f"- **Pharmacy:** KES {pharm_value:,.2f}\n")
        context_parts.append(f"- **Laboratory:** KES {lab_value:,.2f}\n")
        context_parts.append(f"- **Radiology:** KES {rad_value:,.2f}\n")
        context_parts.append(f"**Total Inventory Value:** KES {total_stock_value:,.2f}\n\n")

    # --- Budget vs Actual ---
    if any(kw in q_lower for kw in ['budget vs actual', 'budget variance']):
        # Get budgeted amounts per category (from ExpenseCategory)
        budget_cats = ExpenseCategory.query.filter(
            ExpenseCategory.is_active == True,
            ExpenseCategory.budget_allocation > 0
        ).all()
        actuals = {}
        for cat in budget_cats:
            actual = safe_float(db.session.query(func.sum(Expense.amount + Expense.tax_amount)).filter(
                Expense.category_id == cat.id,
                Expense.expense_date >= start_of_year,
                Expense.status == 'paid'
            ).scalar())
            actuals[cat.name] = actual
        context_parts.append("### Budget vs Actual (Year‑to‑Date)\n")
        for cat in budget_cats:
            budget = safe_float(cat.budget_allocation)
            actual = actuals.get(cat.name, 0)
            variance = budget - actual
            var_pct = (variance / budget * 100) if budget else 0
            context_parts.append(f"- **{cat.name}:** Budget KES {budget:,.2f}, Actual KES {actual:,.2f}, Variance KES {variance:,.2f} ({var_pct:+.1f}%)\n")
        context_parts.append("\n")

    # --- Departmental P&L ---
    if any(kw in q_lower for kw in ['departmental p&l', 'profit by department', 'department performance']):
        # Revenue by department (YTD)
        dept_rev = db.session.query(
            SalesReportItem.department,
            func.sum(SalesReportItem.total_price).label('revenue')
        ).join(SalesReport).filter(
            SalesReport.sale_date >= start_of_year
        ).group_by(SalesReportItem.department).all()
        # Expenses by department (YTD)
        dept_exp = db.session.query(
            Department.name,
            func.sum(Expense.amount + Expense.tax_amount).label('expense')
        ).join(Expense, Expense.department_id == Department.id).filter(
            Expense.expense_date >= start_of_year,
            Expense.status == 'paid'
        ).group_by(Department.name).all()
        exp_dict = {dept: safe_float(expense) for dept, expense in dept_exp}
        context_parts.append("### Departmental Profit & Loss (Year‑to‑Date)\n")
        for dept, rev in dept_rev:
            rev = safe_float(rev)
            expense = exp_dict.get(dept, 0)
            profit = rev - expense
            context_parts.append(f"- **{dept}:** Revenue KES {rev:,.2f}, Expenses KES {expense:,.2f}, Profit KES {profit:,.2f}\n")
        context_parts.append("\n")

    # --- Insurance Claims Report ---
    if any(kw in q_lower for kw in ['insurance claims', 'claims report']):
        total_claims = InsuranceClaim.query.count()
        approved = safe_float(db.session.query(func.sum(ClaimResponse.approved_amount)).scalar())
        denied = safe_float(db.session.query(func.sum(ClaimResponse.denied_amount)).scalar())
        pending = db.session.query(InsuranceClaim).filter(InsuranceClaim.response_received == False).count()
        context_parts.append("### Insurance Claims Report\n")
        context_parts.append(f"- **Total Claims Submitted:** {total_claims}\n")
        context_parts.append(f"- **Total Approved Amount:** KES {approved:,.2f}\n")
        context_parts.append(f"- **Total Denied Amount:** KES {denied:,.2f}\n")
        context_parts.append(f"- **Pending Claims:** {pending}\n\n")

    # --- Supplier Invoices Aging ---
    if any(kw in q_lower for kw in ['supplier invoices', 'vendor aging', 'ap aging details']):
        invoices = SupplierInvoice.query.filter(
            SupplierInvoice.status.in_(['pending', 'overdue', 'partially_paid'])
        ).order_by(SupplierInvoice.due_date).limit(20).all()
        context_parts.append("### Supplier Invoices Aging (Top 20 by due date)\n")
        for inv in invoices:
            due = inv.due_date.date() if inv.due_date else inv.invoice_date.date() + timedelta(days=30)
            days = (today - due).days
            status = "Overdue" if days > 0 else "Current"
            context_parts.append(f"- **{inv.supplier_account.supplier.name}** Invoice {inv.invoice_number}: KES {safe_float(inv.balance_due):,.2f} due {due.strftime('%Y-%m-%d')} ({status} {abs(days)} days)\n")
        context_parts.append("\n")

    # --- Daily / Monthly Trends (enhanced) ---
    if any(kw in q_lower for kw in ['trend', 'daily', 'monthly', 'over time']):
        month_start = today.replace(day=1)
        monthly_rev = []
        for i in range(11, -1, -1):
            month = month_start - timedelta(days=30*i)
            month_start_dt = month.replace(day=1)
            if month_start_dt.month == 12:
                month_end_dt = datetime(month_start_dt.year+1, 1, 1) - timedelta(seconds=1)
            else:
                month_end_dt = datetime(month_start_dt.year, month_start_dt.month+1, 1) - timedelta(seconds=1)
            rev = safe_float(db.session.query(func.sum(SalesReport.total_amount)).filter(
                SalesReport.sale_date >= month_start_dt,
                SalesReport.sale_date <= month_end_dt
            ).scalar())
            monthly_rev.append((month_start_dt.strftime('%b %Y'), rev))
        context_parts.append("### Monthly Revenue (Last 12 months)\n")
        for label, rev in monthly_rev:
            context_parts.append(f"- {label}: KES {rev:,.2f}\n")
        context_parts.append("\n")

    # --- Profit Margin ---
    if any(kw in q_lower for kw in ['margin', 'profitability', 'ratio']):
        profit_margin = ((ytd_sales - ytd_expenses) / ytd_sales * 100) if ytd_sales else 0
        context_parts.append(f"### Profit Margin (YTD)\n")
        context_parts.append(f"- Net Profit Margin: {profit_margin:.2f}%\n\n")

    # --- Cash Runway ---
    if any(kw in q_lower for kw in ['cash flow', 'liquidity', 'runway']):
        monthly_outflow = monthly_expenses
        cash_runway = (cash_total + bank_total) / monthly_outflow if monthly_outflow else 999
        context_parts.append(f"### Cash Flow\n")
        context_parts.append(f"- Average Monthly Outflow: KES {monthly_outflow:,.2f}\n")
        context_parts.append(f"- Cash Runway (months): {cash_runway:.1f}\n\n")

    return "".join(context_parts)






from flask import request, jsonify, Response, stream_with_context
import json
import logging
import requests

# In‑memory conversation store (optional – we'll use DB)
# Remove if you use database exclusively.

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"  # or your preferred model

@finance_web_bp.route('/ai-assistant-stream')
@login_required
def ai_assistant_stream():
    message = request.args.get('message', '')
    if not message:
        return jsonify({'error': 'No message'}), 400

    # Get or create conversation for this user
    conversation = FinanceConversation.query.filter_by(user_id=current_user.id).first()
    if not conversation:
        conversation = FinanceConversation(user_id=current_user.id)
        db.session.add(conversation)
        db.session.commit()

    # Build system prompt with **detailed** financial context based on the user's question
    detailed_context = get_detailed_financial_data(message)
    system_prompt = f"""You are a state‑of‑the‑art Finance AI Assistant integrated into a hospital financial system. You have access to the following current financial data:

{detailed_context}

**Your Role:**
- Answer financial questions, provide insights, and help with reporting.
- Suggest ways to improve revenue, control expenses, or optimize cash flow.
- Format your answers in clear Markdown.
- **Include a separate reasoning section** before your final answer. Use the headings:
  - `## Reasoning` for your step‑by‑step thought process.
  - `## Answer` for your final response.
- Be concise, data‑driven, and professional.
- End every response with the disclaimer: *"These suggestions are generated by AI and are not a substitute for professional financial advice. Always verify with official records and consult with qualified finance personnel."*

**Capabilities:**
- You can recommend cost‑cutting measures.
- You can highlight financial trends.
- You can explain accounting concepts.
- You can suggest ways to increase revenue (e.g., service bundles, insurance partnerships).

If you need more information to make a recommendation, ask clarifying questions.
"""

    # Build message list for AI – query messages directly
    previous_messages = []
    for msg in FinanceMessage.query.filter_by(conversation_id=conversation.id).order_by(FinanceMessage.created_at.asc()):
        previous_messages.append({"role": msg.role, "content": msg.content})

    messages_for_ai = [{"role": "system", "content": system_prompt}] + previous_messages
    messages_for_ai.append({"role": "user", "content": message})

    # Save user message
    user_msg = FinanceMessage(conversation_id=conversation.id, role='user', content=message)
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
        retry_delay = 2  # seconds, doubled each retry

        # Try to send request with retries
        for attempt in range(max_retries):
            try:
                logging.info(f"Sending request to OpenRouter (attempt {attempt+1}/{max_retries})")
                response = requests.post(OPENROUTER_URL, json=payload, headers=headers, stream=True, timeout=60)
                if response.status_code != 200:
                    logging.error(f"OpenRouter error status {response.status_code}: {response.text}")
                    # If it's a server error (5xx) and we have retries left, wait and retry
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        yield f"data: {json.dumps({'error': f'API returned {response.status_code}'})}\n\n"
                        return
                # Success, break out of retry loop
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logging.error(f"Connection error (attempt {attempt+1}): {e}")
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
                            logging.info("Received [DONE] marker, ending stream.")
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk['choices'][0]['delta'].get('content', '')
                            if delta:
                                chunk_count += 1
                                full_response += delta
                                if chunk_count % 10 == 0:
                                    logging.info(f"Received chunk {chunk_count}, current length: {len(full_response)}")
                                yield f"data: {json.dumps({'chunk': delta})}\n\n"
                        except json.JSONDecodeError as e:
                            logging.warning(f"JSON decode error on line: {line[:100]}... Error: {e}")
                            continue
            logging.info(f"Stream finished. Total chunks: {chunk_count}, final response length: {len(full_response)}")

            # Save assistant response to database
            if full_response:
                assistant_msg = FinanceMessage(conversation_id=conversation.id, role='assistant', content=full_response)
                db.session.add(assistant_msg)
                db.session.commit()
                logging.info("Assistant response saved to database.")
            else:
                logging.warning("No content received from OpenRouter.")
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logging.error(f"Streaming processing error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            db.session.close()
            logging.info("Database session closed.")

    return Response(stream_with_context(generate()), mimetype='text/event-stream')




@finance_web_bp.route('/ai-conversation')
@login_required
def get_ai_conversation():
    """Return all AI assistant messages for the current user."""
    conversation = FinanceConversation.query.filter_by(user_id=current_user.id).first()
    if not conversation:
        return jsonify([])

    messages = []
    for msg in FinanceMessage.query.filter_by(conversation_id=conversation.id).order_by(FinanceMessage.created_at.asc()):
        messages.append({
            'role': msg.role,
            'content': msg.content,
            'created_at': msg.created_at.isoformat()
        })
    return jsonify(messages)