from decimal import Decimal
from datetime import date, datetime
from sqlalchemy import and_, or_

def calculate_payroll(period_id, processed_by, include_adjustments=True):
    """
    Calculate payroll for a given period using EXISTING payslips
    Returns: {
        'employees': {
            employee_id: {
                'basic_salary': Decimal,
                'gross_earnings': Decimal,
                'total_deductions': Decimal,
                'net_pay': Decimal,
                'earnings': [
                    {'type_id': int, 'amount': Decimal, 'description': str},
                    ...
                ],
                'deductions': [
                    {'type_id': int, 'amount': Decimal, 'description': str},
                    ...
                ]
            },
            ...
        },
        'totals': {
            'gross': Decimal,
            'deductions': Decimal,
            'net': Decimal,
            'employee_count': int
        }
    }
    """
    from app import db
    from app.hr.models import (User, EmployeePayrollInfo, Payslip, PayslipEarning, 
                              PayslipDeduction, PayrollAdjustment, PayrollLoan,
                              EarningType, DeductionType)
    
    # Get the period
    period = PayrollPeriod.query.get(period_id)
    if not period:
        raise ValueError(f"Payroll period {period_id} not found")
    
    employees_data = {}
    totals = {
        'gross': Decimal('0'),
        'deductions': Decimal('0'),
        'net': Decimal('0'),
        'employee_count': 0
    }
    
    # Get all payslips for this period
    payslips = Payslip.query.join(Payroll).filter(
        Payroll.period_id == period_id
    ).all()
    
    # If no payslips exist, we need to calculate from scratch
    if not payslips:
        return calculate_payroll_from_scratch(period_id, processed_by, include_adjustments)
    
    # Process existing payslips
    for payslip in payslips:
        employee_id = payslip.employee_id
        emp_info = EmployeePayrollInfo.query.filter_by(employee_id=employee_id).first()
        if not emp_info:
            continue
        
        # Initialize employee data
        employees_data[employee_id] = {
            'basic_salary': payslip.basic_salary or Decimal('0'),
            'gross_earnings': Decimal('0'),
            'total_deductions': Decimal('0'),
            'net_pay': Decimal('0'),
            'earnings': [],
            'deductions': []
        }
        
        # Get existing earnings from payslip
        earnings = PayslipEarning.query.filter_by(payslip_id=payslip.id).all()
        for earning in earnings:
            earning_type = EarningType.query.get(earning.earning_type_id)
            employees_data[employee_id]['earnings'].append({
                'type_id': earning.earning_type_id,
                'amount': earning.amount,
                'description': earning.description or earning_type.name if earning_type else 'Earning'
            })
        
        # Get existing deductions from payslip
        deductions = PayslipDeduction.query.filter_by(payslip_id=payslip.id).all()
        for deduction in deductions:
            deduction_type = DeductionType.query.get(deduction.deduction_type_id)
            employees_data[employee_id]['deductions'].append({
                'type_id': deduction.deduction_type_id,
                'amount': deduction.amount,
                'description': deduction.description or deduction_type.name if deduction_type else 'Deduction'
            })
        
        # Calculate totals from existing data
        total_earnings = payslip.basic_salary or Decimal('0')
        for earning in earnings:
            total_earnings += earning.amount or Decimal('0')
        
        total_deductions = Decimal('0')
        for deduction in deductions:
            total_deductions += deduction.amount or Decimal('0')
        
        net_pay = total_earnings - total_deductions
        
        employees_data[employee_id]['gross_earnings'] = total_earnings
        employees_data[employee_id]['total_deductions'] = total_deductions
        employees_data[employee_id]['net_pay'] = net_pay
        
        # Update totals
        totals['gross'] += total_earnings
        totals['deductions'] += total_deductions
        totals['net'] += net_pay
        totals['employee_count'] += 1
    
    # Round all amounts to 2 decimal places
    totals['gross'] = totals['gross'].quantize(Decimal('0.01'))
    totals['deductions'] = totals['deductions'].quantize(Decimal('0.01'))
    totals['net'] = totals['net'].quantize(Decimal('0.01'))
    
    return {
        'employees': employees_data,
        'totals': totals
    }


def calculate_payroll_from_scratch(period_id, processed_by, include_adjustments=True):
    """
    Calculate payroll from scratch (when no payslips exist)
    This is the original calculation logic
    """
    from app import db
    from app.hr.models import (User, EmployeePayrollInfo, EmployeeEarningAssignment,
                              EmployeeDeductionAssignment, PayrollAdjustment, PayrollLoan,
                              EarningType, DeductionType, PAYEBand, SHARate, NSSFRate,
                              PayrollPeriod)
    
    period = PayrollPeriod.query.get(period_id)
    if not period:
        raise ValueError(f"Payroll period {period_id} not found")
    
    # Get all active employees with payroll info
    active_employees = User.query.filter_by(is_active=True).all()
    
    employees_data = {}
    totals = {
        'gross': Decimal('0'),
        'deductions': Decimal('0'),
        'net': Decimal('0'),
        'employee_count': 0
    }
    
    # Get current statutory rates
    current_date = period.end_date
    
    # PAYE bands
    paye_bands = PAYEBand.query.filter(
        PAYEBand.effective_date <= current_date
    ).order_by(PAYEBand.effective_date.desc()).all()
    
    # SHA rates
    sha_rate = SHARate.query.filter(
        SHARate.effective_date <= current_date
    ).order_by(SHARate.effective_date.desc()).first()
    
    # NSSF rates
    nssf_rates = NSSFRate.query.filter(
        NSSFRate.effective_date <= current_date
    ).order_by(NSSFRate.effective_date.desc()).all()
    
    for employee in active_employees:
        emp_info = EmployeePayrollInfo.query.filter_by(employee_id=employee.id).first()
        if not emp_info:
            continue
        
        employee_id = employee.id
        employees_data[employee_id] = {
            'basic_salary': emp_info.basic_salary or Decimal('0'),
            'gross_earnings': Decimal('0'),
            'total_deductions': Decimal('0'),
            'net_pay': Decimal('0'),
            'earnings': [],
            'deductions': []
        }
        
        # 1. CALCULATE EARNINGS
        
        basic_salary = emp_info.basic_salary or Decimal('0')
        if basic_salary > 0:
            basic_earning_type = EarningType.query.filter_by(code='BASIC').first()
            if basic_earning_type:
                employees_data[employee_id]['earnings'].append({
                    'type_id': basic_earning_type.id,
                    'amount': basic_salary,
                    'description': 'Basic Salary'
                })
        
        # Regular allowances
        allowances = [
            ('HOUSING', emp_info.housing_allowance or Decimal('0'), 'Housing Allowance'),
            ('TRANSPORT', emp_info.transport_allowance or Decimal('0'), 'Transport Allowance'),
            ('OTHER', emp_info.other_allowance or Decimal('0'), 'Other Allowance')
        ]
        
        for allowance_code, amount, description in allowances:
            if amount > 0:
                allowance_type = EarningType.query.filter_by(code=allowance_code).first()
                if allowance_type:
                    employees_data[employee_id]['earnings'].append({
                        'type_id': allowance_type.id,
                        'amount': amount,
                        'description': description
                    })
        
        # Additional earnings from assignments
        earning_assignments = EmployeeEarningAssignment.query.filter(
            EmployeeEarningAssignment.employee_id == employee_id,
            EmployeeEarningAssignment.is_active == True,
            EmployeeEarningAssignment.effective_date <= current_date,
            or_(
                EmployeeEarningAssignment.end_date.is_(None),
                EmployeeEarningAssignment.end_date >= current_date
            )
        ).all()
        
        for assignment in earning_assignments:
            if assignment.amount and assignment.amount > 0:
                employees_data[employee_id]['earnings'].append({
                    'type_id': assignment.earning_type_id,
                    'amount': assignment.amount,
                    'description': assignment.earning_type.name if assignment.earning_type else 'Additional Earning'
                })
        
        # Calculate total earnings
        total_earnings = basic_salary + \
                        (emp_info.housing_allowance or Decimal('0')) + \
                        (emp_info.transport_allowance or Decimal('0')) + \
                        (emp_info.other_allowance or Decimal('0'))
        
        for assignment in earning_assignments:
            total_earnings += assignment.amount or Decimal('0')
        
        employees_data[employee_id]['gross_earnings'] = total_earnings
        
        # 2. CALCULATE DEDUCTIONS
        
        # NSSF Calculation
        nssf_deduction = Decimal('0')
        gross_for_nssf = total_earnings
        
        if nssf_rates:
            tier = emp_info.nssf_tier if hasattr(emp_info, 'nssf_tier') else 'II'
            tier_rate = next((rate for rate in nssf_rates if rate.tier == tier), None)
            
            if tier_rate:
                if tier == 'I':
                    nssf_deduction = (tier_rate.employee_rate / Decimal('100')) * min(
                        gross_for_nssf, tier_rate.upper_bound or gross_for_nssf
                    )
                else:
                    if gross_for_nssf > tier_rate.lower_bound:
                        taxable_amount = min(
                            gross_for_nssf, 
                            tier_rate.upper_bound or gross_for_nssf
                        ) - tier_rate.lower_bound
                        nssf_deduction = (tier_rate.employee_rate / Decimal('100')) * taxable_amount
        
        if nssf_deduction > 0:
            nssf_type = DeductionType.query.filter_by(code='NSSF').first()
            if nssf_type:
                employees_data[employee_id]['deductions'].append({
                    'type_id': nssf_type.id,
                    'amount': nssf_deduction,
                    'description': 'NSSF Contribution'
                })
        
        # SHA Calculation
        sha_deduction = Decimal('0')
        if sha_rate:
            sha_deduction = (sha_rate.rate / Decimal('100')) * total_earnings
            if sha_deduction < sha_rate.minimum_amount:
                sha_deduction = sha_rate.minimum_amount
            
            if hasattr(emp_info, 'is_spouse_employed') and emp_info.is_spouse_employed:
                sha_deduction = sha_deduction / Decimal('2')
        
        if sha_deduction > 0:
            sha_type = DeductionType.query.filter_by(code='SHA').first()
            if not sha_type:
                sha_type = DeductionType(
                    name='Social Health Authority',
                    code='SHA',
                    description='SHA Contribution',
                    is_statutory=True
                )
                db.session.add(sha_type)
                db.session.flush()
            
            employees_data[employee_id]['deductions'].append({
                'type_id': sha_type.id,
                'amount': sha_deduction,
                'description': 'SHA Contribution'
            })
        
        # PAYE Calculation
        paye_deduction = Decimal('0')
        taxable_income = total_earnings - nssf_deduction
        personal_relief = Decimal('2400')
        
        if paye_bands and taxable_income > 0:
            paye_deduction = calculate_paye_tax(taxable_income, paye_bands)
            paye_deduction = max(paye_deduction - personal_relief, Decimal('0'))
        
        if paye_deduction > 0:
            paye_type = DeductionType.query.filter_by(code='PAYE').first()
            if paye_type:
                employees_data[employee_id]['deductions'].append({
                    'type_id': paye_type.id,
                    'amount': paye_deduction,
                    'description': 'PAYE Tax'
                })
        
        # Voluntary deductions
        deduction_assignments = EmployeeDeductionAssignment.query.filter(
            EmployeeDeductionAssignment.employee_id == employee_id,
            EmployeeDeductionAssignment.is_active == True,
            EmployeeDeductionAssignment.effective_date <= current_date,
            or_(
                EmployeeDeductionAssignment.end_date.is_(None),
                EmployeeDeductionAssignment.end_date >= current_date
            )
        ).all()
        
        for assignment in deduction_assignments:
            if assignment.amount and assignment.amount > 0:
                employees_data[employee_id]['deductions'].append({
                    'type_id': assignment.deduction_type_id,
                    'amount': assignment.amount,
                    'description': assignment.deduction_type.name if assignment.deduction_type else 'Voluntary Deduction'
                })
        
        # Loan deductions
        active_loans = PayrollLoan.query.filter(
            PayrollLoan.employee_id == employee_id,
            PayrollLoan.is_active == True,
            PayrollLoan.start_date <= current_date,
            PayrollLoan.end_date >= current_date
        ).all()
        
        for loan in active_loans:
            if loan.monthly_deduction and loan.monthly_deduction > 0:
                loan_type = DeductionType.query.filter_by(code='LOAN').first()
                if not loan_type:
                    loan_type = DeductionType(
                        name='Loan Repayment',
                        code='LOAN',
                        description='Staff Loan Deduction',
                        is_voluntary=True
                    )
                    db.session.add(loan_type)
                    db.session.flush()
                
                employees_data[employee_id]['deductions'].append({
                    'type_id': loan_type.id,
                    'amount': loan.monthly_deduction,
                    'description': f'Loan Repayment #{loan.id}'
                })
        
        # Calculate total deductions
        total_deductions = sum(
            Decimal(str(d['amount'])) for d in employees_data[employee_id]['deductions']
        )
        employees_data[employee_id]['total_deductions'] = total_deductions
        
        # Calculate net pay
        net_pay = total_earnings - total_deductions
        employees_data[employee_id]['net_pay'] = max(net_pay, Decimal('0'))
        
        # Update totals
        totals['gross'] += total_earnings
        totals['deductions'] += total_deductions
        totals['net'] += net_pay
        totals['employee_count'] += 1
    
    # Round totals
    totals['gross'] = totals['gross'].quantize(Decimal('0.01'))
    totals['deductions'] = totals['deductions'].quantize(Decimal('0.01'))
    totals['net'] = totals['net'].quantize(Decimal('0.01'))
    
    return {
        'employees': employees_data,
        'totals': totals
    }


def calculate_paye_tax(taxable_income, paye_bands):
    """
    Calculate PAYE tax based on Kenyan tax bands
    """
    paye_tax = Decimal('0')
    remaining_income = taxable_income
    
    # Sort bands by lower bound (ascending)
    bands = sorted([
        {
            'lower': Decimal(str(band.lower_bound)),
            'upper': Decimal(str(band.upper_bound)) if band.upper_bound else None,
            'rate': Decimal(str(band.rate)) / Decimal('100'),
            'deduction': Decimal(str(band.deduction_amount))
        }
        for band in paye_bands
    ], key=lambda x: x['lower'])
    
    for band in bands:
        if remaining_income <= 0:
            break
            
        band_width = None
        if band['upper']:
            band_width = band['upper'] - band['lower']
        
        if band['upper'] is None or remaining_income <= band_width:
            # Income fits in this band
            taxable_in_band = remaining_income
            paye_tax += taxable_in_band * band['rate']
            remaining_income = Decimal('0')
        else:
            # Income exceeds this band
            taxable_in_band = band_width
            paye_tax += taxable_in_band * band['rate']
            remaining_income -= band_width
    
    return paye_tax.quantize(Decimal('0.01'))