from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import func

from app.finance.models import Expense, ExpenseCategory, Insurance, InsuranceClaim, InsuranceService, Invoice, InvoiceItem, Payment
from sqlalchemy.exc import IntegrityError

from app.store.models import ExternalOrder, Supplier
from app.user_management.models import Department

from . import finance_web_bp
from app.patients.models import Consultation, LabTest, Medication, Patient, Radiology, Transaction, Service, Visit, db
from flask import Blueprint, render_template, current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from app.extensions import db

# Financial Dashboard
@finance_web_bp.route('/dashboard')
def financial_dashboard():
    return render_template('dashboard.html')

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



# NEW: Manage Orders Route
@finance_web_bp.route('/manage-orders')
def manage_orders():
    try:
        # Fetch pending orders ordered by urgency (required_by date)
        pending_orders = (
            ExternalOrder.query
            .filter_by(status='pending')
            .options(
                joinedload(ExternalOrder.supplier),
                joinedload(ExternalOrder.user)
            )
            .order_by(ExternalOrder.required_by.asc(), ExternalOrder.created_at.desc())
            .all()
        )
        
        # Calculate days until required for each order
        now = datetime.utcnow()
        orders_with_info = []
        
        for order in pending_orders:
            # Calculate days until required
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
            
            # Add calculated properties directly to the order object
            order.days_until = days_until
            order.is_overdue = is_overdue
            order.days_text = days_text
            
            orders_with_info.append(order)
        
        # Get currency from config
        currency = current_app.config.get('CURRENCY', 'Ksh')
        
        return render_template('manage_orders.html', 
                              orders=orders_with_info,
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
        
        # Ensure order is pending
        if order.status != 'pending':
            flash('Only pending orders can be approved', 'warning')
            return redirect(url_for('finance_web_bp.manage_orders'))
        
        # Update order status
        order.status = 'approved'
        order.updated_at = datetime.utcnow()
        
        # Add audit trail note
        # (Assuming you have an audit trail system)
        # audit_trail.add(f"Order approved by {current_user.username}")
        
        db.session.commit()
        
        # Send notification (optional)
        # notification.send(
        #     f"Your requisition #{order.id} has been approved",
        #     recipients=[order.user.email]
        # )
        
        flash(f'Requisition #{order.id} approved successfully!', 'success')
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



@finance_web_bp.route('/expenses/new', methods=['GET', 'POST'])
def new_expense():
    # Get current user ID
    user_id = current_user.id
    
    # Get form data
    form_data = {
        'categories': ExpenseCategory.query.order_by(ExpenseCategory.name).all(),
        'departments': Department.query.order_by(Department.name).all(),
        'suppliers': Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all(),
        'payment_methods': ['Bank Transfer', 'Cheque', 'Cash', 'Mobile Money', 'Credit Card'],
        'expense_types': ['operational', 'capital', 'emergency'],
        'priority_levels': ['low', 'medium', 'high', 'critical'],
        'current_date': datetime.utcnow().strftime('%Y-%m-%d')
    }
    
    if request.method == 'POST':
        try:
            # Extract form data
            expense_data = {
                'expense_date': datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d'),
                'description': request.form.get('description'),
                'amount': float(request.form.get('amount')),
                'category_id': int(request.form.get('category_id')),
                'department_id': int(request.form.get('department_id')),
                'supplier_id': int(request.form.get('supplier_id')) if request.form.get('supplier_id') else None,
                'payment_method': request.form.get('payment_method'),
                'expense_type': request.form.get('expense_type'),
                'priority': request.form.get('priority'),
                'notes': request.form.get('notes'),
                'initiated_by': user_id,
                'status': 'draft' if request.form.get('save_draft') else 'submitted'
            }
            
            # Create new expense
            new_expense = Expense(**expense_data)
            new_expense.currency = 'KES'  # Set default currency
            new_expense.calculate_tax()  # Calculate tax
            
            # Save to database
            db.session.add(new_expense)
            db.session.commit()
            
            # Generate reference number after commit (when ID is available)
            new_expense.reference_number = new_expense.generate_reference()
            db.session.commit()
            
            flash('Expense created successfully!', 'success')
            return redirect(url_for('finance_web_bp.expenses'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating expense: {str(e)}', 'danger')
    
    return render_template('new_expense.html', **form_data)



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