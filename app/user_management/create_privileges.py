# app/user_management/create_privileges.py

from app.extensions import db
from app.user_management.models import Privilege

def create_initial_privileges(session):
    """
    Seed the privileges table with one entry per (action, module).
    Idempotent: existing names are skipped.
    """

    # (name, module, description)
    privileges = [
        ('dashboard:view', 'Dashboard', 'View Dashboard overview'),
        ('users:create', 'User Management', 'Create new user accounts'),
        ('users:list', 'User Management', 'List all users'),
        ('users:edit', 'User Management', 'Edit existing user accounts'),
        ('patients:register', 'Patients', 'Register a new patient'),
        ('patients:manage', 'Patients', 'View & edit patient records'),
        ('patients:triage', 'Patients', 'Perform patient triage'),
        ('consultations:queue', 'Consultations', 'Access consultation queue'),
                ('consultations:special', 'Consultations', 'Access special consultation queue'),

            # New diagnosis privilege added here
    ('diagnosis:manage', 'Medical Services', 'Manage patient diagnoses'),
        ('lab:orders', 'Lab Tests', 'View pending lab orders'),
        ('lab:results', 'Lab Tests', 'View lab test results'),
        ('lab:add_quick', 'Lab Tests', 'Add a quick lab test'),
            ('lab_samples:manage', 'Laboratory', 'Manage sample collection, tracking and storage'),
    ('blood_bank:manage', 'Laboratory', 'Manage blood inventory and transfusions'),
    ('lab_inventory:view', 'Laboratory', 'View lab reagents and consumables'),
    ('lab_equipment:maintain', 'Laboratory', 'Schedule equipment maintenance'),
    ('lab_quality:control', 'Laboratory', 'Manage quality control procedures'),
        ('lab_inventory:manage_consumables', 'Laboratory', 'Manage laboratory consumables and reagents'),
    ('lab_inventory:request_stocks', 'Laboratory', 'Request new stocks for laboratory'),
    ('lab_inventory:stock_flow', 'Laboratory', 'Monitor stock flow and usage in laboratory'),
        ('radiology:requests', 'Radiology', 'View imaging requests (MedSvc)'),
        ('radiology:scan_results', 'Radiology', 'View scan results (MedSvc)'),
    ('radiology:archive', 'Radiology', 'View archived radiology reports'),
    ('radiology:manage_services', 'Radiology', 'Manage radiology services'),
    ('radiology:equipment_maintenance', 'Radiology', 'Schedule and manage radiology equipment maintenance'),
    ('radiology:quality_control', 'Radiology', 'Perform and track radiology quality control procedures'),

    # Radiology Inventory Privileges
    ('radiology_inventory:view', 'Radiology Inventory', 'View radiology consumables and inventory dashboard'),
    ('radiology_inventory:manage_consumables', 'Radiology Inventory', 'Manage radiology consumables and reagents'),
    ('radiology_inventory:request_stocks', 'Radiology Inventory', 'Request new radiology consumable stocks'),
    ('radiology_inventory:stock_flow', 'Radiology Inventory', 'Monitor stock flow and usage in radiology'),
    ('appointments:schedule', 'Appointments', 'Schedule a new appointment'),
        ('appointments:manage', 'Appointments', 'Manage all appointments'),
        ('appointments:my_schedule', 'Appointments', 'View my upcoming appointments'),
        ('billing:create_invoice', 'Billing', 'Create a new invoice'),
        ('billing:process_payment', 'Billing', 'Process payments'),
        ('billing:transactions', 'Billing', 'View transaction history'),
        ('pharmacy:dispense', 'Pharmacy', 'Dispense medication'),
        ('pharmacy:inventory', 'Pharmacy', 'Manage pharmacy inventory'),
        ('pharmacy:track_prescriptions', 'Pharmacy', 'Track prescriptions'),
        ('pharmacy:stock_requests', 'Pharmacy', 'View & respond to stock requests'),
        ('lab_tests:list', 'Laboratory', 'List all lab tests'),
        ('lab_reports:generate', 'Laboratory', 'Generate lab reports'),
        ('lab:test_types', 'Laboratory', 'Manage lab test types'),
        ('lab:view_reports', 'Laboratory', 'View lab reports'),
        ('radiology:imaging_requests', 'Radiology', 'View imaging requests'),
        ('radiology:view_scans', 'Radiology', 'View scans'),
        ('radiology:view_reports', 'Radiology', 'View radiology reports'),
        ('hr:staff_add', 'Human Resources', 'Add New Staff'),
        ('hr:staff_directory', 'Human Resources', 'View Staff Directory'),
        ('hr:staff_profiles', 'Human Resources', 'View/Edit Staff Profiles'),
        ('hr:attendance', 'Human Resources', 'Track Staff Attendance'),
        ('hr:payroll:salary', 'Human Resources', 'Process Staff Salaries'),
        ('hr:payroll:payslips', 'Human Resources', 'Generate/View Payslips'),
        ('hr:payroll:reports', 'Human Resources', 'View Payroll Reports'),
        # Recruitment Privileges - Added here
        ('hr:recruitment:dashboard', 'Human Resources', 'Access recruitment dashboard'),
        ('hr:recruitment:jobs', 'Human Resources', 'Manage job postings'),
        ('hr:recruitment:candidates', 'Human Resources', 'Manage candidates'),
        ('hr:recruitment:interviews', 'Human Resources', 'Manage interviews'),
        ('hr:recruitment:selection', 'Human Resources', 'Manage candidate selection'),
        ('hr:recruitment:reports', 'Human Resources', 'View recruitment reports'),
        ('hr:recruitment:settings', 'Human Resources', 'Configure recruitment settings'),
        # Keep the existing general recruitment privilege for backward compatibility
        ('hr:recruitment', 'Human Resources', 'Manage Recruitment'),
        ('inventory:dashboard', 'Inventory', 'View Inventory Dashboard'),
        ('inventory:manage_stock', 'Inventory', 'Manage Stock Levels'),
        ('inventory:stock_requests', 'Inventory', 'View & Respond to Stock Requests'),
        ('inventory:suppliers', 'Inventory', 'Manage Suppliers'),
        ('inventory:purchase_orders', 'Inventory', 'Manage Purchase Orders'),
        ('inventory:reports', 'Inventory', 'Generate Inventory Reports'),
        ('inventory:inventory_logs', 'Inventory', 'View Inventory Audit Logs'),
            # Stock Level Reports
    ('inventory:reports:stock', 'Inventory Reports', 'View Stock Level Reports'),
    
    # Purchase & Procurement Reports  
    ('inventory:reports:purchase', 'Inventory Reports', 'View Purchase & Procurement Reports'),
    
    # Delivery & Receiving Reports
    ('inventory:reports:delivery', 'Inventory Reports', 'View Delivery & Receiving Reports'),
    
    # Financial Reports
    ('inventory:reports:financial', 'Inventory Reports', 'View Financial Reports'),
    
    # Stock Request & Issuance Reports
    ('inventory:reports:requests', 'Inventory Reports', 'View Stock Request Reports'),
    
    # Expiry & Batch Reports
    ('inventory:reports:expiry', 'Inventory Reports', 'View Expiry & Batch Reports'),
    
    # Audit & Compliance Reports
    ('inventory:reports:audit', 'Inventory Reports', 'View Audit & Compliance Reports'),
    
    # Requisition & Approval Reports
    ('inventory:reports:requisitions', 'Inventory Reports', 'View Requisition Reports'),
    
    # Additional Analysis Reports
    ('inventory:reports:analysis', 'Inventory Reports', 'View Analysis Reports'),
    
        ('finance:dashboard', 'Finance', 'View Financial Dashboard'),
        ('finance:invoices', 'Finance', 'Manage Invoices & Receivables'),
        ('finance:payments', 'Finance', 'Process Payments'),
        ('finance:expenses', 'Finance', 'Track Expenses'),
        ('finance:insurance', 'Finance', 'Manage Insurance Policies'),
        ('finance:reports', 'Finance', 'Generate Financial Reports'),
        
            ('finance:approve_lpo', 'Finance', 'Approve Local Purchase Orders (LPOs)'),
                ('finance:supplier_accounts', 'Finance', 'Manage Supplier Accounts'),
                    ('finance:doctor_accounts', 'Finance', 'Manage Doctor Accounts'),  # New privilege added

                ('finance:approve_payments', 'Finance', 'Approve Payments'),
# Finance - Treasury Management
('finance:bank_reconciliation', 'Finance', 'Access Bank Reconciliation'),
('finance:bank_reports', 'Finance', 'View Bank Reports'),
('finance:cashflow_analysis', 'Finance', 'View Cashflow Analysis'),

# Finance - Operational Reports
('finance:sales_reports', 'Finance', 'View Sales Reports'),
('finance:stock_reports', 'Finance', 'View Stock Reports'),
('finance:expense_reports', 'Finance', 'View Expense Reports'),

# Finance - Accounting
('finance:general_ledger', 'Finance', 'View General Ledger'),
('finance:trial_balance', 'Finance', 'View Trial Balance'),

# Finance - Financial Statements
('finance:income_statement', 'Finance', 'View Income Statement (P&L)'),
('finance:balance_sheet', 'Finance', 'View Balance Sheet'),
('finance:cashflow_statement', 'Finance', 'View Cash Flow Statement'),
('finance:payroll', 'Finance', 'Process and manage payroll'),
        ('reports:clinical', 'Reports', 'Access Clinical Reports'),
        ('reports:financial', 'Reports', 'Access Financial Reports'),
        ('reports:analytics', 'Reports', 'Access Analytics Dashboard'),
        ('doctor_dashboard', 'Dashboard', 'Access Doctor Dashboard'),
        ('nurse_dashboard', 'Dashboard', 'Access Nurse Dashboard'),
        ('labtech_dashboard', 'Dashboard', 'Access Lab Technician Dashboard'),
        ('radiology_dashboard', 'Dashboard', 'Access Radiology Dashboard'),
        ('pharmacy_dashboard', 'Dashboard', 'Access Pharmacy Dashboard'),
        ('registration_dashboard', 'Dashboard', 'Access Registration Dashboard'),
        ('patient_dashboard', 'Dashboard', 'Access Patient Dashboard'),
        ('reports:audit', 'Reports', 'Access Audit Logs'),
        ('finance:services', 'Finance', 'Manage Financial Services'),
        ('pharmacy:dispense_history', 'Pharmacy', 'View Dispense History'),
        ('resource:policies', 'Resource Centre', 'Access System Policies'),
        ('resource:documentation', 'Resource Centre', 'Access System Documentation'),
        ('resource:support', 'Resource Centre', 'Access System Support Resources'),
            ('resource:updates', 'Resource Centre', 'View system updates and changelogs'),
    ('resource:manage', 'Resource Centre', 'Manage resource centre content'),
        ('inventory:external_orders', 'Inventory', 'Manage External Orders'),
        ('finance:manage_orders', 'Finance', 'Approve/Reject Purchase Requisitions'),
        ('reports:mpesa', 'Reports', 'Access M-Pesa Transaction Logs'),
        ('finance:cash_payments', 'Finance', 'Manage Cash Payments and Receipts'),
        ('hr:payroll:periods', 'Human Resources', 'Manage Payroll Periods'),
        ('hr:payroll:adjustments', 'Human Resources', 'Manage Payroll Adjustments'),
        ('hr:payroll:loans', 'Human Resources', 'Manage Employee Loans'),
        ('hr:payroll:settings', 'Human Resources', 'Configure Payroll Settings'),
        ('hr:duty_rota', 'Human Resources', 'Manage Duty Rota Schedules'),
            # NEW: Disciplinary Services privileges
        ('hr:disciplinary:cases', 'Disciplinary Services', 'Manage disciplinary cases'),
        ('hr:disciplinary:actions', 'Disciplinary Services', 'Manage disciplinary actions'),
        ('hr:disciplinary:reports', 'Disciplinary Services', 'View disciplinary reports'),
        ('hr:disciplinary:policies', 'Disciplinary Services', 'Manage disciplinary policies'),
        ('hr:disciplinary:appeals', 'Disciplinary Services', 'Handle appeals process'),
                # Asset Management
        ('asset:manage', 'Asset Management', 'Manage hospital assets'),
        ('asset:track', 'Asset Management', 'Track asset locations'),
        ('asset:maintenance', 'Asset Management', 'Schedule asset maintenance'),
        ('asset:reports', 'Asset Management', 'View asset reports'),
        
        # Board Module
        ('board:dashboard', 'Board Module', 'Access board dashboard'),
        ('board:financials', 'Board Module', 'View financial reports'),
        ('board:performance', 'Board Module', 'View performance metrics'),
        ('board:strategy', 'Board Module', 'Strategic planning'),
        ('board:governance', 'Board Module', 'Governance and compliance'),
        ('board:resources', 'Board Module', 'Access board resources'),

        ('hospital:manage_profile', 'System Administration', 'Manage hospital profile settings'),
        
            # Communication Hub Privileges
    ('comms:dashboard', 'Communication Hub', 'Access Engagement Dashboard'),
    ('comms:sms_patients', 'Communication Hub', 'Send Bulk SMS to Patients'),
    ('comms:sms_staff', 'Communication Hub', 'Send Bulk SMS to Staff'),
    ('comms:email_bulk', 'Communication Hub', 'Send Bulk Email Campaigns'),
    ('comms:templates', 'Communication Hub', 'Manage Message Templates'),
    ('comms:reminders', 'Communication Hub', 'Manage Appointment Reminders'),
    ('comms:notifications', 'Communication Hub', 'Configure System Notifications'),
    ('comms:analytics', 'Communication Hub', 'View Delivery Analytics'),
    ('comms:feedback', 'Communication Hub', 'Manage Feedback Collection'),
            # Dental Clinic Privileges 🦷
    ('dental:consultations', 'Dental Clinic', 'Access Dental Consultation module'),
    ('dental:procedures', 'Dental Clinic', 'Manage Dental Procedures'),
        # Optician Clinic Privileges 👓
    ('optician:examinations', 'Optician Clinic', 'Perform Eye Examinations'),
    ('optician:dispensing', 'Optician Clinic', 'Manage Glasses & Contact Lens Dispensing'),
        ('consultations:manage_services', 'Service Management', 'Manage consultation service types and pricing'),
    # --- Admin & Director Privileges ---
    ('admin:dashboard', 'Admin & Director', 'Access administrative dashboard'),
    ('admin:approve_requisitions', 'Admin & Director', 'Approve or reject purchase requisitions'),
    ('admin:orders_progress', 'Admin & Director', 'View and track progress of purchase orders'),
    ('admin:manage_users', 'Admin & Director', 'High-level user and role management'),
    ('admin:system_settings', 'Admin & Director', 'Manage core system configurations'),
    ('admin:reports_overview', 'Admin & Director', 'Access consolidated reports (financial, clinical, HR, assets)'),
    ('admin:approve_lpo', 'Admin & Director', 'Approve Local Purchase Orders (LPOs)'),
    ('admin:approve_payments', 'Admin & Director', 'Approve Payments'),
    ('admin:approve_payroll', 'Admin & Director', 'Approve processed payrolls'),

    ]

    for name, module, description in privileges:
        existing = session.query(Privilege).filter_by(name=name).first()
        if existing:
            continue

        priv = Privilege(
            name=name,
            module=module,
            description=description
        )
        session.add(priv)

    session.commit()
    print(f"Seeded {len(privileges)} privileges.")

  
# If you’re wiring this up to Flask-CLI, you can do:
# 
# import click
# from flask.cli import with_appcontext
# 
# @click.command('seed-privileges')
# @with_appcontext
# def seed_privileges_command():
#     create_initial_privileges()
#     click.echo('✅ Privileges seeded.')
# 
# Then in your app/__init__.py’s register_commands():
# app.cli.add_command(seed_privileges_command)

