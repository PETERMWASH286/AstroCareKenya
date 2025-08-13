# app/utils/calculate_payroll.py
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from app.hr.models import (
    PayrollPeriod, EmployeePayrollInfo, PayrollAdjustment, 
    PayrollLoan, PAYEBand, NHIFRate, NSSFRate, EarningType, DeductionType,
    
)
from app.extensions import db
from app.auth.models import User

def calculate_payroll(period_id, processed_by):
    # Fetch payroll period
    period = PayrollPeriod.query.get(period_id)
    if not period:
        raise ValueError("Invalid payroll period")
    
    # Get all active employees with payroll info
    employees = User.query.join(EmployeePayrollInfo).filter(
        User.is_active == True,
        EmployeePayrollInfo.basic_salary > 0
    ).all()
    
    payroll_data = {
        'totals': {
            'gross': Decimal('0'),
            'deductions': Decimal('0'),
            'net': Decimal('0'),
            'employee_count': 0
        },
        'employees': {}
    }
    
    # Get current statutory rates
    paye_bands = PAYEBand.query.order_by(PAYEBand.lower_bound).all()
    nhif_rates = NHIFRate.query.order_by(NHIFRate.lower_bound).all()
    nssf_rate = NSSFRate.query.filter_by(tier='II').first()  # Use Tier II NSSF
    
    # Get recurring earning types
    recurring_earnings = EarningType.query.filter_by(is_recurring=True).all()
    
    for employee in employees:
        payroll_info = employee.payroll_info
        if not payroll_info:
            continue
            
        # Start with basic salary
        earnings = [
            {'type': 'Basic Salary', 'type_id': None, 'amount': payroll_info.basic_salary}
        ]
        
        # Add recurring allowances
        for earning_type in recurring_earnings:
            # Map common allowance types
            if earning_type.code == 'HSA' and payroll_info.housing_allowance:
                earnings.append({
                    'type': earning_type.name,
                    'type_id': earning_type.id,
                    'amount': payroll_info.housing_allowance
                })
            elif earning_type.code == 'TA' and payroll_info.transport_allowance:
                earnings.append({
                    'type': earning_type.name,
                    'type_id': earning_type.id,
                    'amount': payroll_info.transport_allowance
                })
            elif earning_type.code == 'OA' and payroll_info.other_allowance:
                earnings.append({
                    'type': earning_type.name,
                    'type_id': earning_type.id,
                    'amount': payroll_info.other_allowance
                })
        
        # Calculate gross earnings
        gross_earnings = sum(Decimal(e['amount']) for e in earnings)
        
        # =====================
        # DEDUCTIONS CALCULATION
        # =====================
        deductions = []
        
        # 1. NSSF DEDUCTION (Employee portion)
        nssf_deduction = Decimal('0')
        if nssf_rate:
            pensionable_earnings = min(
                gross_earnings, 
                Decimal(nssf_rate.upper_bound or Decimal('18000'))
            )
            nssf_deduction = (pensionable_earnings * nssf_rate.employee_rate / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            deductions.append({
                'type': 'NSSF',
                'type_id': None,
                'amount': nssf_deduction,
                'statutory': True
            })
        
        # 2. NHIF DEDUCTION
        nhif_deduction = Decimal('0')
        for rate in nhif_rates:
            lower = Decimal(rate.lower_bound)
            upper = Decimal(rate.upper_bound) if rate.upper_bound else Decimal('9999999')
            if lower <= gross_earnings <= upper:
                nhif_deduction = Decimal(rate.amount)
                deductions.append({
                    'type': 'NHIF',
                    'type_id': None,
                    'amount': nhif_deduction,
                    'statutory': True
                })
                break
        
        # 3. PAYE CALCULATION
        paye_deduction = Decimal('0')
        taxable_income = gross_earnings - nssf_deduction  # NSSF is tax-deductible
        remaining_income = taxable_income
        
        for band in paye_bands:
            lower = Decimal(band.lower_bound)
            upper = Decimal(band.upper_bound) if band.upper_bound else Decimal('9999999')
            
            if remaining_income <= 0:
                break
                
            band_amount = min(remaining_income, upper - lower)
            if band_amount > 0:
                paye_deduction += (band_amount * Decimal(band.rate) / 100) - Decimal(band.deduction_amount)
                remaining_income -= band_amount
        
        paye_deduction = max(paye_deduction, Decimal('0')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if paye_deduction > 0:
            deductions.append({
                'type': 'PAYE',
                'type_id': None,
                'amount': paye_deduction,
                'statutory': True
            })
        
        # 4. LOAN DEDUCTIONS
        loan_deductions = Decimal('0')
        active_loans = PayrollLoan.query.filter_by(
            employee_id=employee.id,
            is_active=True
        ).all()
        
        for loan in active_loans:
            if loan.balance > 0:
                deduction_amount = min(loan.monthly_deduction, loan.balance)
                deductions.append({
                    'type': 'Loan Repayment',
                    'type_id': loan.id,
                    'amount': deduction_amount,
                    'statutory': False
                })
                loan_deductions += deduction_amount
        
        # 5. PAYROLL ADJUSTMENTS
        adjustments = PayrollAdjustment.query.filter_by(
            employee_id=employee.id,
            period_id=period_id,
            approved_at=None  # Only unprocessed adjustments
        ).all()
        
        for adj in adjustments:
            if adj.type == 'Earning':
                earnings.append({
                    'type': adj.description,
                    'type_id': None,
                    'amount': adj.amount
                })
                gross_earnings += adj.amount
            else:  # Deduction
                deductions.append({
                    'type': adj.description,
                    'type_id': None,
                    'amount': adj.amount,
                    'statutory': False
                })
        
        # Calculate totals
        total_deductions = sum(Decimal(d['amount']) for d in deductions)
        net_pay = gross_earnings - total_deductions
        
        # Add to payroll summary
        payroll_data['employees'][employee.id] = {
            'employee_id': employee.id,
            'employee_name': f"{employee.first_name} {employee.last_name}",
            'basic_salary': payroll_info.basic_salary,
            'gross_earnings': gross_earnings,
            'total_deductions': total_deductions,
            'net_pay': net_pay,
            'payment_method': payroll_info.payment_method.value,
            'earnings': earnings,
            'deductions': deductions
        }
        
        # Update totals
        payroll_data['totals']['gross'] += gross_earnings
        payroll_data['totals']['deductions'] += total_deductions
        payroll_data['totals']['net'] += net_pay
        payroll_data['totals']['employee_count'] += 1
    
    return payroll_data