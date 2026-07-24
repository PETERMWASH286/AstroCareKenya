from datetime import datetime, date
from decimal import Decimal
from enum import Enum

from sqlalchemy import text
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
    
    # Add these columns for uniqueness constraint
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('year', 'month', 'frequency', name='unique_period_per_month'),
    )
    
    payrolls = db.relationship('Payroll', backref='period', lazy=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Auto-calculate year and month from start_date
        if self.start_date:
            self.year = self.start_date.year
            self.month = self.start_date.month
    
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
    employee_count = db.Column(db.Integer, default=0)  # Add this if missing
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    paid_at = db.Column(db.DateTime, nullable=True)   # when payroll was marked as paid
    paid_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # who marked it

    # ... relationships (you may want to add a relationship for paid_by)
    payer = db.relationship('User', foreign_keys=[paid_by])
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
    employee = db.relationship('User', backref='payslips')
    # The loan_repayments relationship is automatically created by the backref in LoanRepayment model
    
    def calculate_totals(self):
        """Calculate gross earnings, total deductions, and net pay"""
        # Start with basic salary
        gross = Decimal(str(self.basic_salary or 0))
        
        # Add all earnings
        for earning in self.earnings:
            gross += Decimal(str(earning.amount or 0))
        
        self.gross_earnings = gross
        
        # Calculate total deductions
        total_deductions = Decimal('0')
        for deduction in self.deductions:
            total_deductions += Decimal(str(deduction.amount or 0))
        
        self.total_deductions = total_deductions
        
        # Calculate net pay
        self.net_pay = gross - total_deductions
        
        return self
    
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

class EmployeeEarningAssignment(db.Model):
    """Assign specific earnings to employees"""
    __tablename__ = 'employee_earning_assignments'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    earning_type_id = db.Column(db.Integer, db.ForeignKey('earning_types.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2))  # Override default amount
    is_active = db.Column(db.Boolean, default=True)
    effective_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date)
    
    employee = db.relationship('User', backref='earning_assignments')
    earning_type = db.relationship('EarningType')

class EmployeeDeductionAssignment(db.Model):
    """Assign specific deductions to employees (loans, advances, etc.)"""
    __tablename__ = 'employee_deduction_assignments'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    deduction_type_id = db.Column(db.Integer, db.ForeignKey('deduction_types.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2))
    balance = db.Column(db.Numeric(10, 2))  # For loans
    is_active = db.Column(db.Boolean, default=True)
    effective_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date)
    
    employee = db.relationship('User', backref='deduction_assignments')
    deduction_type = db.relationship('DeductionType')

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

# Remove NHIFRate and create SHARate model
class SHARate(db.Model):
    """Social Health Authority (SHA) rates - replaced NHIF in Kenya"""
    __tablename__ = 'sha_rates'
    id = db.Column(db.Integer, primary_key=True)
    rate = db.Column(db.Numeric(5, 2), nullable=False, default=2.75)  # Percentage (2.75%)
    minimum_amount = db.Column(db.Numeric(10, 2), nullable=False, default=300.00)  # Minimum KES 300
    effective_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SHARate {self.rate}% (Min: KES {self.minimum_amount})>"


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
    staff_no = db.Column(db.String(32), unique=True, index=True, nullable=False)

    bank_name = db.Column(db.String(100))
    bank_branch = db.Column(db.String(100))
    bank_account = db.Column(db.String(50))
    mpesa_number = db.Column(db.String(20))
    kra_pin = db.Column(db.String(20))
    nhif_number = db.Column(db.String(20))
    nssf_number = db.Column(db.String(20))
    sha_number = db.Column(db.String(20))
    # SHA Specific - if both spouses are employed
    is_spouse_employed = db.Column(db.Boolean, default=False)
    # Statutory information
    nssf_tier = db.Column(
        db.Enum('I', 'II', name='nssf_tier_enum'),
        nullable=False,
        server_default=text("'II'")
    )    
    basic_salary = db.Column(db.Numeric(10, 2), nullable=False)
    housing_allowance = db.Column(db.Numeric(10, 2), default=0.00)
    transport_allowance = db.Column(db.Numeric(10, 2), default=0.00)
    other_allowance = db.Column(db.Numeric(10, 2), default=0.00)
    payment_method = db.Column(db.Enum(PaymentMethod), default=PaymentMethod.BANK_TRANSFER)
    
    # NEW: Active status column
    is_active = db.Column(db.Boolean, default=True, nullable=False, 
                          server_default=text("true"))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    employee = db.relationship('User', backref=db.backref('payroll_info', uselist=False))
    
    def calculate_gross_salary(self):
        """Calculate total gross salary"""
        if not self.is_active:
            return Decimal('0')
        
        return (self.basic_salary or Decimal('0')) + \
               (self.housing_allowance or Decimal('0')) + \
               (self.transport_allowance or Decimal('0')) + \
               (self.other_allowance or Decimal('0'))
    
    def __repr__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"<PayrollInfo for Employee {self.employee_id} ({status})>"
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
    
    employee = db.relationship('User', backref='loans', lazy=True)
    repayments = db.relationship('LoanRepayment', backref='loan', lazy=True)
    
    @property
    def employee_name(self):
        """Safely get employee name"""
        return self.employee.full_name if self.employee else f"Employee {self.employee_id}"
    
    @property
    def staff_no(self):
        """Safely get staff number"""
        if self.employee and self.employee.payroll_info:
            return self.employee.payroll_info.staff_no
        return "N/A"
    
    def __repr__(self):
        return f"<PayrollLoan #{self.id} for Employee {self.employee_id}>"

class LoanRepayment(db.Model):
    __tablename__ = 'loan_repayments'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('payroll_loans.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payslip_id = db.Column(db.Integer, db.ForeignKey('payslips.id'))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Add this field
    
    # ADD THIS RELATIONSHIP
    payslip = db.relationship('Payslip', backref=db.backref('loan_repayments', lazy=True))
    
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



class StatutoryLiability(db.Model):
    __tablename__ = 'statutory_liabilities'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(db.Integer, db.ForeignKey('payrolls.id'), nullable=False)
    deduction_type_id = db.Column(db.Integer, db.ForeignKey('deduction_types.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=False)          # e.g., 9th of next month
    paid_at = db.Column(db.DateTime, nullable=True)        # when remitted to authority
    reference = db.Column(db.String(100), nullable=True)   # payment reference
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    payroll = db.relationship('Payroll', backref=db.backref('statutory_liabilities', lazy='dynamic'))
    deduction_type = db.relationship('DeductionType', backref='liabilities')

    def __repr__(self):
        return f'<StatutoryLiability {self.deduction_type.code} KES {self.amount} for Payroll #{self.payroll_id}>'

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
    
    
# Association table for many-to-many relationship between panels and job postings
panel_job_postings = db.Table('panel_job_postings',
    db.Column('panel_id', db.Integer, db.ForeignKey('interview_panels.id'), primary_key=True),
    db.Column('job_posting_id', db.Integer, db.ForeignKey('job_postings.id'), primary_key=True),
    db.Column('assigned_at', db.DateTime, default=datetime.utcnow),
    db.Column('assigned_by', db.Integer, db.ForeignKey('user.id')),
    db.Column('is_primary', db.Boolean, default=False),  # If this is the main panel for the job
    db.Column('notes', db.Text)
)    
    
    
# Recruitment Models
class JobCategory(db.Model):
    __tablename__ = 'job_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    job_postings = db.relationship('JobPosting', backref='category', lazy=True)
    
    def __repr__(self):
        return f"<JobCategory {self.name}>"

class JobPosting(db.Model):
    __tablename__ = 'job_postings'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    reference_no = db.Column(db.String(50), unique=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('job_categories.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    
    # Job Details
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text)
    responsibilities = db.Column(db.Text)
    benefits = db.Column(db.Text)
    
    # Job Specifications
    employment_type = db.Column(db.Enum('Full-Time', 'Part-Time', 'Contract', 'Internship', 'Temporary', name='employment_type_enum'))
    experience_level = db.Column(db.Enum('Entry', 'Mid', 'Senior', 'Executive', name='experience_level_enum'))
    education_level = db.Column(db.Enum('Certificate', 'Diploma', 'Bachelor', 'Master', 'PhD', 'None', name='education_level_enum'))
    
    # Salary Information
    salary_range_min = db.Column(db.Numeric(10, 2))
    salary_range_max = db.Column(db.Numeric(10, 2))
    salary_currency = db.Column(db.String(3), default='KES')
    salary_disclosure = db.Column(db.Enum('Confidential', 'Negotiable', 'Fixed', 'Range', name='salary_disclosure_enum'), default='Confidential')
    
    # Recruitment Details
    positions_available = db.Column(db.Integer, default=1)
    application_deadline = db.Column(db.Date, nullable=False)
    start_date = db.Column(db.Date)
    
    # Status
    status = db.Column(db.Enum('Draft', 'Published', 'Closed', 'Archived', 'Cancelled', name='job_posting_status_enum'), default='Draft')
    is_remote = db.Column(db.Boolean, default=False)
    location = db.Column(db.String(200))
    
    # Metadata
    views_count = db.Column(db.Integer, default=0)
    applications_count = db.Column(db.Integer, default=0)
    shortlisted_count = db.Column(db.Integer, default=0)
    
    # Timestamps
    published_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    candidates = db.relationship('Candidate', backref='job_posting', lazy=True)
    department = db.relationship('Department', backref='job_postings')
    interview_panels = db.relationship('InterviewPanel', 
                                      secondary=panel_job_postings,
                                      backref='assigned_job_postings',  # Changed from 'job_postings'
                                      lazy=True)
    # Add a method to get primary panel
    def get_primary_panel(self):
        """Get the primary panel for this job"""
        from sqlalchemy import select
        
        stmt = select(InterviewPanel).join(
            panel_job_postings,
            InterviewPanel.id == panel_job_postings.c.panel_id
        ).where(
            db.and_(
                panel_job_postings.c.job_posting_id == self.id,
                panel_job_postings.c.is_primary == True
            )
        )
        result = db.session.execute(stmt).scalar()
        return result
    
    def __repr__(self):
        return f"<JobPosting {self.reference_no}: {self.title}>"
    
    @property
    def is_active(self):
        return self.status == 'Published' and datetime.utcnow().date() <= self.application_deadline
    
    @property
    def formatted_salary(self):
        if self.salary_disclosure == 'Confidential':
            return 'Confidential'
        elif self.salary_disclosure == 'Negotiable':
            return 'Negotiable'
        elif self.salary_disclosure == 'Fixed' and self.salary_range_min:
            return f"{self.salary_currency} {self.salary_range_min:,.2f}"
        elif self.salary_disclosure == 'Range' and self.salary_range_min and self.salary_range_max:
            return f"{self.salary_currency} {self.salary_range_min:,.2f} - {self.salary_range_max:,.2f}"
        return 'Not Specified'
    
    @property
    def assigned_panels_count(self):
        """Count of panels assigned to this job"""
        return len(self.interview_panels.all()) if hasattr(self, 'interview_panels') else 0

class Candidate(db.Model):
    __tablename__ = 'candidates'
    id = db.Column(db.Integer, primary_key=True)
    job_posting_id = db.Column(db.Integer, db.ForeignKey('job_postings.id'), nullable=False)
    
    # Personal Information
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    nationality = db.Column(db.String(50))
    gender = db.Column(db.Enum('Male', 'Female', 'Other', 'Prefer not to say', name='gender_enum'))
    
    # Contact Information
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    
    # Professional Information
    current_company = db.Column(db.String(200))
    current_position = db.Column(db.String(200))
    current_salary = db.Column(db.Numeric(10, 2))
    expected_salary = db.Column(db.Numeric(10, 2))
    notice_period = db.Column(db.Integer)  # In days
    years_of_experience = db.Column(db.Integer)
    
    # Education
    highest_qualification = db.Column(db.String(200))
    institution = db.Column(db.String(200))
    graduation_year = db.Column(db.Integer)
    
    # Application Details
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    source = db.Column(db.Enum('Website', 'LinkedIn', 'Referral', 'Agency', 'Other', name='application_source_enum'))
    cover_letter = db.Column(db.Text)
    
    # Documents
    resume_path = db.Column(db.String(500))
    cover_letter_path = db.Column(db.String(500))
    portfolio_url = db.Column(db.String(500))
    linkedin_url = db.Column(db.String(500))
    
    # Status
    status = db.Column(db.Enum(
        'Applied', 
        'Under Review', 
        'Shortlisted', 
        'Interview Scheduled', 
        'Interviewed', 
        'Reference Check', 
        'Offer Extended', 
        'Offer Accepted', 
        'Offer Rejected', 
        'Rejected', 
        'On Hold', 
        'Withdrawn',
        name='candidate_status_enum'
    ), default='Applied')
    
    # Interview Details
    interview_date = db.Column(db.DateTime)
    interview_location = db.Column(db.String(200))
    interview_notes = db.Column(db.Text)
    
    # Assessment Scores
    resume_score = db.Column(db.Numeric(5, 2), default=0)
    technical_score = db.Column(db.Numeric(5, 2), default=0)
    communication_score = db.Column(db.Numeric(5, 2), default=0)
    cultural_fit_score = db.Column(db.Numeric(5, 2), default=0)
    overall_score = db.Column(db.Numeric(5, 2), default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    hired_at = db.Column(db.DateTime)
    
    # Relationships
    interviews = db.relationship('Interview', backref='candidate', lazy=True)
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None
    
    def calculate_overall_score(self):
        """Calculate overall score from all assessment scores"""
        scores = [
            self.resume_score or 0,
            self.technical_score or 0,
            self.communication_score or 0,
            self.cultural_fit_score or 0
        ]
        valid_scores = [s for s in scores if s > 0]
        if valid_scores:
            self.overall_score = sum(valid_scores) / len(valid_scores)
        return self.overall_score

class InterviewPanel(db.Model):
    __tablename__ = 'interview_panels'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    panel_type = db.Column(db.Enum('Technical', 'HR', 'Management', 'Final', 'Other', name='panel_type_enum'))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_shared = db.Column(db.Boolean, default=False)  # Can be shared across multiple jobs
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    panel_members = db.relationship('InterviewPanelMember', backref='panel', lazy=True, cascade='all, delete-orphan')
    interviews = db.relationship('Interview', backref='panel', lazy=True)
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_panels')
    
    # You can add a property to access job_postings if needed
    @property
    def job_postings(self):
        """Get all job postings assigned to this panel"""
        return self.assigned_job_postings
    
    def __repr__(self):
        return f"<InterviewPanel {self.name}>"
    
    @property
    def active_jobs_count(self):
        """Count of active job postings assigned to this panel"""
        return self.job_postings.filter(
            JobPosting.status.in_(['Published', 'Draft'])
        ).count()
    
    def assign_to_job(self, job_posting_id, assigned_by, is_primary=False, notes=None):
        """Assign this panel to a job posting"""
        from sqlalchemy import insert
        
        # Check if already assigned
        existing = db.session.execute(
            db.select([panel_job_postings]).where(
                db.and_(
                    panel_job_postings.c.panel_id == self.id,
                    panel_job_postings.c.job_posting_id == job_posting_id
                )
            )
        ).fetchone()
        
        if not existing:
            # Insert new assignment
            stmt = insert(panel_job_postings).values(
                panel_id=self.id,
                job_posting_id=job_posting_id,
                assigned_by=assigned_by,
                is_primary=is_primary,
                notes=notes
            )
            db.session.execute(stmt)
            return True
        return False
    
    def remove_from_job(self, job_posting_id):
        """Remove this panel from a job posting"""
        from sqlalchemy import delete
        
        stmt = delete(panel_job_postings).where(
            db.and_(
                panel_job_postings.c.panel_id == self.id,
                panel_job_postings.c.job_posting_id == job_posting_id
            )
        )
        db.session.execute(stmt)
        return True

class InterviewPanelMember(db.Model):
    __tablename__ = 'interview_panel_members'
    id = db.Column(db.Integer, primary_key=True)
    panel_id = db.Column(db.Integer, db.ForeignKey('interview_panels.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Role in panel
    role = db.Column(db.Enum('Chairperson', 'Member', 'Recorder', 'Observer', name='panel_role_enum'), default='Member')
    is_required = db.Column(db.Boolean, default=True)  # Whether their presence is required
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='panel_memberships')
    interview_scores = db.relationship('InterviewScore', backref='panel_member', lazy=True)
    
    def __repr__(self):
        return f"<InterviewPanelMember {self.user.full_name} in Panel {self.panel_id}>"

class Interview(db.Model):
    __tablename__ = 'interviews'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    panel_id = db.Column(db.Integer, db.ForeignKey('interview_panels.id'), nullable=False)
    
    # Interview Details
    interview_type = db.Column(db.Enum('Phone', 'Video', 'In-Person', 'Group', 'Panel', name='interview_type_enum'), default='In-Person')
    scheduled_date = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    location = db.Column(db.String(200))
    meeting_link = db.Column(db.String(500))
    
    # Status
    status = db.Column(db.Enum(
        'Scheduled', 
        'Confirmed', 
        'In Progress', 
        'Completed', 
        'Cancelled', 
        'No Show', 
        'Rescheduled',
        name='interview_status_enum'
    ), default='Scheduled')
    
    # Interview Results
    overall_feedback = db.Column(db.Text)
    recommendation = db.Column(db.Enum('Strong Hire', 'Hire', 'Neutral', 'No Hire', 'Strong No Hire', name='recommendation_enum'))
    
    # Timestamps
    actual_start_time = db.Column(db.DateTime)
    actual_end_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    scores = db.relationship('InterviewScore', backref='interview', lazy=True, cascade='all, delete-orphan')
    
    @property
    def duration_hours(self):
        return self.duration_minutes / 60 if self.duration_minutes else 0
    
    @property
    def is_completed(self):
        return self.status == 'Completed'
    
    def calculate_average_score(self):
        scores = [score.score for score in self.scores if score.score is not None]
        return sum(scores) / len(scores) if scores else 0

class InterviewScore(db.Model):
    __tablename__ = 'interview_scores'
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    panel_member_id = db.Column(db.Integer, db.ForeignKey('interview_panel_members.id'), nullable=False)
    
    # Score Criteria
    technical_competence = db.Column(db.Numeric(5, 2))
    communication_skills = db.Column(db.Numeric(5, 2))
    problem_solving = db.Column(db.Numeric(5, 2))
    cultural_fit = db.Column(db.Numeric(5, 2))
    leadership_potential = db.Column(db.Numeric(5, 2))
    
    # Overall Score
    score = db.Column(db.Numeric(5, 2))  # Calculated average
    
    # Qualitative Feedback
    strengths = db.Column(db.Text)
    weaknesses = db.Column(db.Text)
    overall_feedback = db.Column(db.Text)
    recommendation = db.Column(db.Enum('Strong Hire', 'Hire', 'Neutral', 'No Hire', 'Strong No Hire', name='score_recommendation_enum'))
    
    # Timestamps
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def calculate_score(self):
        """Calculate overall score from all criteria"""
        scores = []
        if self.technical_competence is not None:
            scores.append(float(self.technical_competence))
        if self.communication_skills is not None:
            scores.append(float(self.communication_skills))
        if self.problem_solving is not None:
            scores.append(float(self.problem_solving))
        if self.cultural_fit is not None:
            scores.append(float(self.cultural_fit))
        if self.leadership_potential is not None:
            scores.append(float(self.leadership_potential))
        
        if scores:
            self.score = sum(scores) / len(scores)
        return self.score

class OfferLetter(db.Model):
    __tablename__ = 'offer_letters'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    
    # Offer Details
    offer_title = db.Column(db.String(200))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    position = db.Column(db.String(200))
    employment_type = db.Column(db.Enum('Full-Time', 'Part-Time', 'Contract', 'Internship', name='offer_employment_type_enum'))
    
    # Salary Details
    base_salary = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='KES')
    bonus = db.Column(db.Numeric(10, 2), default=0)
    allowances = db.Column(db.Numeric(10, 2), default=0)
    benefits = db.Column(db.Text)
    
    # Contract Details
    start_date = db.Column(db.Date, nullable=False)
    probation_period_months = db.Column(db.Integer, default=3)
    reporting_to = db.Column(db.String(200))
    work_location = db.Column(db.String(200))
    
    # Status
    status = db.Column(db.Enum('Draft', 'Sent', 'Accepted', 'Rejected', 'Expired', 'Withdrawn', name='offer_status_enum'), default='Draft')
    
    # Documents
    offer_document_path = db.Column(db.String(500))
    
    # Timestamps
    sent_date = db.Column(db.DateTime)
    response_date = db.Column(db.DateTime)
    expiry_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    candidate = db.relationship('Candidate', backref='offers')
    department = db.relationship('Department', backref='offers')
    
    @property
    def total_compensation(self):
        return (self.base_salary or 0) + (self.bonus or 0) + (self.allowances or 0)
    
    @property
    def is_active(self):
        if self.status in ['Accepted', 'Rejected', 'Withdrawn']:
            return False
        if self.expiry_date and datetime.utcnow() > self.expiry_date:
            return False
        return True    
    
    
    
    
    
    

class LeaveType(db.Model):
    __tablename__ = 'leave_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True)   # e.g., ANNUAL, SICK
    is_paid = db.Column(db.Boolean, default=True)
    max_days_per_year = db.Column(db.Float, nullable=False)
    requires_document = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LeaveType {self.name}>'


class LeaveAllocation(db.Model):
    __tablename__ = 'leave_allocations'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey('leave_types.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    days_allocated = db.Column(db.Float, nullable=False, default=0)
    days_used = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    employee = db.relationship('User', foreign_keys=[employee_id], backref='leave_allocations')
    leave_type = db.relationship('LeaveType', backref='allocations')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_leave_allocations')

    @property
    def days_remaining(self):
        return self.days_allocated - self.days_used


class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey('leave_types.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_requested = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    attachment = db.Column(db.String(500))
    status = db.Column(db.String(20), default='pending')
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approval_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    employee = db.relationship('User', foreign_keys=[employee_id], backref='leave_requests')
    leave_type = db.relationship('LeaveType', backref='requests')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_leave_requests')