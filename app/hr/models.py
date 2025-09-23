from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from app.extensions import db

class PaymentFrequency(Enum):
    MONTHLY = 'Monthly'
    BIWEEKLY = 'Bi-weekly'
    WEEKLY = 'Weekly'
    DAILY = 'Daily'

class PaymentMethod(Enum):
    BANK_TRANSFER = 'Bank Transfer'
    M_PESA = 'M-Pesa'
    CHEQUE = 'Cheque'
    CASH = 'Cash'

class PayrollPeriod(db.Model):
    __tablename__ = 'payroll_periods'
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    pay_date = db.Column(db.Date, nullable=False)
    frequency = db.Column(db.Enum(PaymentFrequency), nullable=False, default=PaymentFrequency.MONTHLY)
    is_closed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    payrolls = db.relationship('Payroll', backref='period', lazy=True)
    
    def __repr__(self):
        return f"<PayrollPeriod {self.start_date} to {self.end_date}>"

class Payroll(db.Model):
    __tablename__ = 'payrolls'
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey('payroll_periods.id'), nullable=False)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    total_gross = db.Column(db.Numeric(12, 2), default=0.00)
    total_deductions = db.Column(db.Numeric(12, 2), default=0.00)
    total_net = db.Column(db.Numeric(12, 2), default=0.00)
    status = db.Column(db.Enum('Draft', 'Approved', 'Processed', 'Paid'), default='Draft')
    notes = db.Column(db.Text)
    
    payslips = db.relationship('Payslip', backref='payroll', lazy=True)
    
    def __repr__(self):
        return f"<Payroll #{self.id} for Period {self.period.start_date}>"

class Payslip(db.Model):
    __tablename__ = 'payslips'
    id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(db.Integer, db.ForeignKey('payrolls.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    basic_salary = db.Column(db.Numeric(10, 2), nullable=False)
    gross_earnings = db.Column(db.Numeric(10, 2), default=0.00)
    total_deductions = db.Column(db.Numeric(10, 2), default=0.00)
    net_pay = db.Column(db.Numeric(10, 2), default=0.00)
    payment_method = db.Column(db.Enum(PaymentMethod), default=PaymentMethod.BANK_TRANSFER)
    payment_reference = db.Column(db.String(100))
    paid_at = db.Column(db.DateTime)
    is_paid = db.Column(db.Boolean, default=False)
    
    earnings = db.relationship('PayslipEarning', backref='payslip', lazy=True, cascade='all, delete-orphan')
    deductions = db.relationship('PayslipDeduction', backref='payslip', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<Payslip #{self.id} for Employee {self.employee_id}>"

class EarningType(db.Model):
    __tablename__ = 'earning_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.Text)
    is_taxable = db.Column(db.Boolean, default=True)
    is_statutory = db.Column(db.Boolean, default=False)
    is_recurring = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    payslip_earnings = db.relationship('PayslipEarning', backref='earning_type', lazy=True)
    
    def __repr__(self):
        return f"<EarningType {self.name} ({self.code})>"

class DeductionType(db.Model):
    __tablename__ = 'deduction_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.Text)
    is_statutory = db.Column(db.Boolean, default=False)  # True for PAYE, NHIF, NSSF
    is_voluntary = db.Column(db.Boolean, default=False)  # True for loans, advances
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    payslip_deductions = db.relationship('PayslipDeduction', backref='deduction_type', lazy=True)
    
    def __repr__(self):
        return f"<DeductionType {self.name} ({self.code})>"

class PayslipEarning(db.Model):
    __tablename__ = 'payslip_earnings'
    id = db.Column(db.Integer, primary_key=True)
    payslip_id = db.Column(db.Integer, db.ForeignKey('payslips.id'), nullable=False)
    earning_type_id = db.Column(db.Integer, db.ForeignKey('earning_types.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text)
    
    def __repr__(self):
        return f"<PayslipEarning {self.earning_type.name}: KES {self.amount}>"

class PayslipDeduction(db.Model):
    __tablename__ = 'payslip_deductions'
    id = db.Column(db.Integer, primary_key=True)
    payslip_id = db.Column(db.Integer, db.ForeignKey('payslips.id'), nullable=False)
    deduction_type_id = db.Column(db.Integer, db.ForeignKey('deduction_types.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text)
    
    def __repr__(self):
        return f"<PayslipDeduction {self.deduction_type.name}: KES {self.amount}>"

# Kenya-specific Statutory Models
class PAYEBand(db.Model):
    __tablename__ = 'paye_bands'
    id = db.Column(db.Integer, primary_key=True)
    lower_bound = db.Column(db.Numeric(10, 2), nullable=False)
    upper_bound = db.Column(db.Numeric(10, 2))
    rate = db.Column(db.Numeric(5, 2), nullable=False)  # Percentage
    deduction_amount = db.Column(db.Numeric(10, 2), nullable=False)
    effective_date = db.Column(db.Date, default=date.today)
    
    def __repr__(self):
        return f"<PAYEBand {self.lower_bound}-{self.upper_bound or '∞'}: {self.rate}%>"

class NHIFRate(db.Model):
    __tablename__ = 'nhif_rates'
    id = db.Column(db.Integer, primary_key=True)
    lower_bound = db.Column(db.Numeric(10, 2), nullable=False)
    upper_bound = db.Column(db.Numeric(10, 2))
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    effective_date = db.Column(db.Date, default=date.today)
    
    def __repr__(self):
        return f"<NHIFRate {self.lower_bound}-{self.upper_bound or '∞'}: KES {self.amount}>"

class NSSFRate(db.Model):
    __tablename__ = 'nssf_rates'
    id = db.Column(db.Integer, primary_key=True)
    tier = db.Column(db.Enum('I', 'II'), nullable=False)
    lower_bound = db.Column(db.Numeric(10, 2), nullable=False)
    upper_bound = db.Column(db.Numeric(10, 2))
    employee_rate = db.Column(db.Numeric(5, 2), nullable=False)  # Percentage
    employer_rate = db.Column(db.Numeric(5, 2), nullable=False)  # Percentage
    effective_date = db.Column(db.Date, default=date.today)
    
    def __repr__(self):
        return f"<NSSFRate Tier {self.tier}: {self.employee_rate}% (Employee), {self.employer_rate}% (Employer)>"

class EmployeePayrollInfo(db.Model):
    __tablename__ = 'employee_payroll_info'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    bank_name = db.Column(db.String(100))
    bank_branch = db.Column(db.String(100))
    bank_account = db.Column(db.String(50))
    mpesa_number = db.Column(db.String(20))
    kra_pin = db.Column(db.String(20))
    nhif_number = db.Column(db.String(20))
    nssf_number = db.Column(db.String(20))
    basic_salary = db.Column(db.Numeric(10, 2), nullable=False)
    housing_allowance = db.Column(db.Numeric(10, 2), default=0.00)
    transport_allowance = db.Column(db.Numeric(10, 2), default=0.00)
    other_allowance = db.Column(db.Numeric(10, 2), default=0.00)
    payment_method = db.Column(db.Enum(PaymentMethod), default=PaymentMethod.BANK_TRANSFER)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    employee = db.relationship('User', backref=db.backref('payroll_info', uselist=False))
    
    def __repr__(self):
        return f"<PayrollInfo for Employee {self.employee_id}>"

class PayrollAdjustment(db.Model):
    __tablename__ = 'payroll_adjustments'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    period_id = db.Column(db.Integer, db.ForeignKey('payroll_periods.id'), nullable=False)
    type = db.Column(db.Enum('Earning', 'Deduction'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text, nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    employee = db.relationship('User', foreign_keys=[employee_id])
    period = db.relationship('PayrollPeriod')
    
    def __repr__(self):
        return f"<PayrollAdjustment {self.type} for {self.employee_id}: KES {self.amount}>"

class PayrollLoan(db.Model):
    __tablename__ = 'payroll_loans'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    loan_amount = db.Column(db.Numeric(10, 2), nullable=False)
    balance = db.Column(db.Numeric(10, 2), nullable=False)
    monthly_deduction = db.Column(db.Numeric(10, 2), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    repayments = db.relationship('LoanRepayment', backref='loan', lazy=True)
    
    def __repr__(self):
        return f"<PayrollLoan #{self.id} for Employee {self.employee_id}>"

class LoanRepayment(db.Model):
    __tablename__ = 'loan_repayments'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('payroll_loans.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payslip_id = db.Column(db.Integer, db.ForeignKey('payslips.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<LoanRepayment #{self.id} for Loan {self.loan_id}>"

class PayrollReport(db.Model):
    __tablename__ = 'payroll_reports'
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey('payroll_periods.id'), nullable=False)
    report_type = db.Column(db.String(50), nullable=False)  # e.g., 'PAYE', 'NHIF', 'NSSF'
    file_path = db.Column(db.String(255), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    generated_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    def __repr__(self):
        return f"<PayrollReport {self.report_type} for Period {self.period_id}>"


# =============================
# DUTY ROTA & ATTENDANCE MODELS
# =============================

class ShiftType(Enum):
    MORNING = 'Morning'
    AFTERNOON = 'Afternoon'
    NIGHT = 'Night'
    CUSTOM = 'Custom'

class AttendanceStatus(Enum):
    PRESENT = 'Present'
    ABSENT = 'Absent'
    LATE = 'Late'
    LEAVE = 'On Leave'
    OFF_DUTY = 'Off Duty'
    SICK = 'Sick Leave'

class DutyShift(db.Model):
    __tablename__ = 'duty_shifts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    shift_type = db.Column(db.Enum(ShiftType), nullable=False, default=ShiftType.CUSTOM)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default='#3B82F6')  # Hex color for UI
    
    def __repr__(self):
        return f"<DutyShift {self.name} ({self.start_time}-{self.end_time})>"

class DutyRota(db.Model):
    __tablename__ = 'duty_rotas'
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    department = db.relationship('Department')
    assignments = db.relationship('DutyAssignment', backref='rota', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<DutyRota {self.name} for {self.department.name}>"

class DutyAssignment(db.Model):
    __tablename__ = 'duty_assignments'
    id = db.Column(db.Integer, primary_key=True)
    rota_id = db.Column(db.Integer, db.ForeignKey('duty_rotas.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('duty_shifts.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    
    employee = db.relationship('User', foreign_keys=[employee_id])
    shift = db.relationship('DutyShift')
    
    def __repr__(self):
        return f"<DutyAssignment {self.employee.full_name} on {self.date}>"

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('duty_shifts.id'))
    status = db.Column(db.Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.PRESENT)
    clock_in = db.Column(db.DateTime)
    clock_out = db.Column(db.DateTime)
    late_minutes = db.Column(db.Integer, default=0)
    overtime_minutes = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    employee = db.relationship('User', foreign_keys=[employee_id])
    shift = db.relationship('DutyShift')
    
    def __repr__(self):
        return f"<AttendanceRecord {self.employee.full_name} on {self.date} - {self.status.value}>"

class LeaveType(db.Model):
    __tablename__ = 'leave_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    max_days = db.Column(db.Integer, nullable=False)
    is_paid = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    
    def __repr__(self):
        return f"<LeaveType {self.name}>"

class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey('leave_types.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_requested = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum('Pending', 'Approved', 'Rejected'), default='Pending')
    reason = db.Column(db.Text, nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    employee = db.relationship('User', foreign_keys=[employee_id])
    leave_type = db.relationship('LeaveType')
    
    def __repr__(self):
        return f"<LeaveRequest {self.employee.full_name} for {self.leave_type.name}>"
    
    
    
    
    
    


# ================================================
# DISCIPLINARY SERVICES MODELS
# ================================================

class DisciplinaryCaseStatus(Enum):
    OPEN = 'Open'
    UNDER_INVESTIGATION = 'Under Investigation'
    HEARING_SCHEDULED = 'Hearing Scheduled'
    DECISION_PENDING = 'Decision Pending'
    CLOSED = 'Closed'
    APPEALED = 'Appealed'
    ARCHIVED = 'Archived'

class DisciplinaryActionStatus(Enum):
    ACTIVE = 'Active'
    COMPLETED = 'Completed'
    SUSPENDED = 'Suspended'
    APPEALED = 'Appealed'
    TERMINATED = 'Terminated'

class DisciplinarySeverity(Enum):
    MINOR = 'Minor'
    MODERATE = 'Moderate'
    MAJOR = 'Major'
    SEVERE = 'Severe'

class AppealStatus(Enum):
    PENDING = 'Pending'
    UNDER_REVIEW = 'Under Review'
    UPHELD = 'Upheld'
    OVERTURNED = 'Overturned'
    DISMISSED = 'Dismissed'

class HearingStatus(Enum):
    SCHEDULED = 'Scheduled'
    IN_PROGRESS = 'In Progress'
    COMPLETED = 'Completed'
    ADJOURNED = 'Adjourned'
    CANCELLED = 'Cancelled'

class DisciplinaryCaseType(db.Model):
    __tablename__ = 'disciplinary_case_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.Text)
    default_severity = db.Column(db.Enum(DisciplinarySeverity), default=DisciplinarySeverity.MODERATE)
    resolution_days = db.Column(db.Integer, default=30)  # Default days to resolve
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    cases = db.relationship('DisciplinaryCase', backref='case_type', lazy=True)
    
    def __repr__(self):
        return f"<CaseType {self.name} ({self.code})>"

class DisciplinaryActionType(db.Model):
    __tablename__ = 'disciplinary_action_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.Text)
    severity_level = db.Column(db.Enum(DisciplinarySeverity), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    actions = db.relationship('DisciplinaryAction', backref='action_type', lazy=True)
    
    def __repr__(self):
        return f"<ActionType {self.name} ({self.code})>"

class DisciplinaryCase(db.Model):
    __tablename__ = 'disciplinary_cases'
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(250), unique=True, nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reported_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    case_type_id = db.Column(db.Integer, db.ForeignKey('disciplinary_case_types.id'), nullable=False)
    date_reported = db.Column(db.Date, default=date.today, nullable=False)
    incident_date = db.Column(db.Date, nullable=False)
    incident_description = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum(DisciplinaryCaseStatus), default=DisciplinaryCaseStatus.OPEN)
    severity = db.Column(db.Enum(DisciplinarySeverity), default=DisciplinarySeverity.MODERATE)
    resolution_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    employee = db.relationship('User', foreign_keys=[employee_id])
    reporter = db.relationship('User', foreign_keys=[reported_by_id])
    actions = db.relationship('DisciplinaryAction', backref='case', lazy=True)
    hearings = db.relationship('DisciplinaryHearing', backref='case', lazy=True)
    documents = db.relationship('DisciplinaryDocument', backref='case', lazy=True)
    appeals = db.relationship('DisciplinaryAppeal', backref='case', lazy=True)
    investigations = db.relationship('DisciplinaryInvestigation', backref='case', lazy=True)
    def __repr__(self):
        return f"<DisciplinaryCase {self.case_number} for {self.employee_id}>"

class InvestigationStatus(Enum):
    ACTIVE = 'Active'
    COMPLETED = 'Completed'
    PENDING_REVIEW = 'Pending Review'
    ON_HOLD = 'On Hold'

class DisciplinaryInvestigation(db.Model):
    __tablename__ = 'disciplinary_investigations'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('disciplinary_cases.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    investigator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    findings = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum(InvestigationStatus), default=InvestigationStatus.ACTIVE)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    investigator = db.relationship('User', foreign_keys=[investigator_id])
    evidence = db.relationship('InvestigationEvidence', backref='investigation', lazy=True)

class InvestigationEvidence(db.Model):
    __tablename__ = 'investigation_evidence'
    id = db.Column(db.Integer, primary_key=True)
    investigation_id = db.Column(db.Integer, db.ForeignKey('disciplinary_investigations.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    uploaded_by_user = db.relationship('User', foreign_keys=[uploaded_by])

class DisciplinaryAction(db.Model):
    __tablename__ = 'disciplinary_actions'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('disciplinary_cases.id'), nullable=False)
    action_type_id = db.Column(db.Integer, db.ForeignKey('disciplinary_action_types.id'), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    effective_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    status = db.Column(db.Enum(DisciplinaryActionStatus), default=DisciplinaryActionStatus.ACTIVE)
    description = db.Column(db.Text)
    outcome = db.Column(db.Text)
    is_appealed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])
    appeal = db.relationship('DisciplinaryAppeal', backref='action', uselist=False, lazy=True)
    
    def __repr__(self):
        return f"<DisciplinaryAction {self.action_type.name} for Case {self.case_id}>"

class DisciplinaryAppeal(db.Model):
    __tablename__ = 'disciplinary_appeals'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('disciplinary_cases.id'), nullable=False)
    action_id = db.Column(db.Integer, db.ForeignKey('disciplinary_actions.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    appeal_date = db.Column(db.Date, default=date.today, nullable=False)
    grounds = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum(AppealStatus), default=AppealStatus.PENDING)
    decision = db.Column(db.Text)
    decided_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    decision_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    employee = db.relationship('User', foreign_keys=[employee_id])
    decided_by = db.relationship('User', foreign_keys=[decided_by_id])
    hearings = db.relationship('DisciplinaryHearing', backref='appeal', lazy=True)
    
    def __repr__(self):
        return f"<DisciplinaryAppeal for Action {self.action_id}>"

class DisciplinaryHearing(db.Model):
    __tablename__ = 'disciplinary_hearings'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('disciplinary_cases.id'))
    appeal_id = db.Column(db.Integer, db.ForeignKey('disciplinary_appeals.id'))
    hearing_date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200))
    status = db.Column(db.Enum(HearingStatus), default=HearingStatus.SCHEDULED)
    chairperson_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.Column(db.Text)
    outcome = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    chairperson = db.relationship('User', foreign_keys=[chairperson_id])
    participants = db.relationship('HearingParticipant', backref='hearing', lazy=True)
    documents = db.relationship('DisciplinaryDocument', backref='hearing', lazy=True)
    
    def __repr__(self):
        return f"<DisciplinaryHearing on {self.hearing_date}>"

class HearingParticipant(db.Model):
    __tablename__ = 'hearing_participants'
    id = db.Column(db.Integer, primary_key=True)
    hearing_id = db.Column(db.Integer, db.ForeignKey('disciplinary_hearings.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # e.g., 'Panel Member', 'Witness', 'Representative'
    attended = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    
    user = db.relationship('User')
    
    def __repr__(self):
        return f"<HearingParticipant {self.user.full_name} ({self.role})>"

class DisciplinaryPolicy(db.Model):
    __tablename__ = 'disciplinary_policies'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    version = db.Column(db.String(20), nullable=False)
    effective_date = db.Column(db.Date, nullable=False)
    review_date = db.Column(db.Date)
    content = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    created_by_user = db.relationship('User', foreign_keys=[created_by])
    categories = db.relationship('PolicyCategory', secondary='policy_category_assoc', backref='policies')
    
    def __repr__(self):
        return f"<DisciplinaryPolicy {self.title} v{self.version}>"

class PolicyCategory(db.Model):
    __tablename__ = 'policy_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    
    def __repr__(self):
        return f"<PolicyCategory {self.name}>"

class PolicyCategoryAssoc(db.Model):
    __tablename__ = 'policy_category_assoc'
    policy_id = db.Column(db.Integer, db.ForeignKey('disciplinary_policies.id'), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('policy_categories.id'), primary_key=True)

class DisciplinaryDocument(db.Model):
    __tablename__ = 'disciplinary_documents'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('disciplinary_cases.id'))
    hearing_id = db.Column(db.Integer, db.ForeignKey('disciplinary_hearings.id'))
    document_type = db.Column(db.String(100), nullable=False)  # e.g., 'Incident Report', 'Evidence', 'Decision Letter'
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    uploaded_by_user = db.relationship('User', foreign_keys=[uploaded_by])
    
    def __repr__(self):
        return f"<DisciplinaryDocument {self.title} ({self.document_type})>"

class DisciplinaryReport(db.Model):
    __tablename__ = 'disciplinary_reports'
    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(100), nullable=False)  # e.g., 'Case Summary', 'Action Tracking'
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    parameters = db.Column(db.JSON)  # Store filter parameters as JSON
    generated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(255), nullable=False)
    
    generated_by_user = db.relationship('User', foreign_keys=[generated_by])
    
    def __repr__(self):
        return f"<DisciplinaryReport {self.report_type} ({self.start_date} to {self.end_date})>"



class HRInventory(db.Model):
    __tablename__ = 'hr_inventory'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Uniforms, Office Supplies
    quantity = db.Column(db.Integer, default=0)
    supplier = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)