import os
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from flask import current_app

class PayslipPDFGenerator:
    """Generate professional PDF payslips"""
    
    @staticmethod
    def generate_payslip_pdf(payslip, employee, company_info=None):
        """Generate a PDF payslip"""
        buffer = BytesIO()
        
        # Create the PDF object
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=30,
            textColor=colors.HexColor('#4F46E5')
        )
        
        heading_style = ParagraphStyle(
            'HeadingStyle',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#1F2937')
        )
        
        normal_style = ParagraphStyle(
            'NormalStyle',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6
        )
        
        bold_style = ParagraphStyle(
            'BoldStyle',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        
        # Title
        elements.append(Paragraph("SALARY PAYSLIP", title_style))
        
        # Company Information
        if company_info:
            company_text = f"""
            <b>{company_info.get('name', 'AstroCare Limited')}</b><br/>
            {company_info.get('address', 'Nairobi, Kenya')}<br/>
            KRA PIN: {company_info.get('kra_pin', 'P051XXXXXX')}<br/>
            Tel: {company_info.get('phone', '+254 700 000 000')}
            """
            elements.append(Paragraph(company_text, normal_style))
            elements.append(Spacer(1, 20))
        
        # Payslip Details Header
        header_data = [
            ["Payslip Details", "Employee Information"],
            [
                f"<b>Payslip #:</b> {payslip.id}<br/>"
                f"<b>Period:</b> {payslip.payroll.period.start_date.strftime('%d/%m/%Y')} - {payslip.payroll.period.end_date.strftime('%d/%m/%Y')}<br/>"
                f"<b>Pay Date:</b> {payslip.payroll.period.pay_date.strftime('%d/%m/%Y')}<br/>"
                f"<b>Status:</b> {'PAID' if payslip.is_paid else 'PENDING'}",
                
                f"<b>Name:</b> {employee.full_name}<br/>"
                f"<b>Employee ID:</b> {employee.id}<br/>"
                f"<b>Department:</b> {employee.department.name if employee.department else 'N/A'}<br/>"
                f"<b>Job Title:</b> {employee.job_title if employee.job_title else 'N/A'}"
            ]
        ]
        
        header_table = Table(header_data, colWidths=[doc.width/2]*2)
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E5E7EB')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#D1D5DB')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 20))
        
        # Earnings Section
        elements.append(Paragraph("EARNINGS", heading_style))
        
        earnings_data = [["Description", "Amount (KES)"]]
        
        # Basic Salary
        earnings_data.append(["Basic Salary", f"{float(payslip.basic_salary or 0):,.2f}"])
        
        # Other Earnings
        total_allowances = 0
        for earning in payslip.earnings:
            earning_name = earning.earning_type.name if earning.earning_type else "Additional Earning"
            earnings_data.append([earning_name, f"{float(earning.amount or 0):,.2f}"])
            total_allowances += float(earning.amount or 0)
        
        earnings_table = Table(earnings_data, colWidths=[doc.width*0.7, doc.width*0.3])
        earnings_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#10B981')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (1, -1), (1, -1), colors.HexColor('#10B981')),
        ]))
        elements.append(earnings_table)
        
        # Add Gross Earnings Total
        earnings_total = [
            ["", f"<b>Total Gross Earnings: KES {float(payslip.gross_earnings or 0):,.2f}</b>"]
        ]
        earnings_total_table = Table(earnings_total, colWidths=[doc.width*0.7, doc.width*0.3])
        earnings_total_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 0), (1, 0), 11),
            ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#10B981')),
            ('PADDING', (0, 0), (-1, 0), 6),
        ]))
        elements.append(earnings_total_table)
        elements.append(Spacer(1, 20))
        
        # Deductions Section
        elements.append(Paragraph("DEDUCTIONS", heading_style))
        
        deductions_data = [["Description", "Amount (KES)"]]
        
        total_statutory = 0
        total_voluntary = 0
        
        for deduction in payslip.deductions:
            deduction_name = deduction.deduction_type.name if deduction.deduction_type else "Deduction"
            deductions_data.append([deduction_name, f"{float(deduction.amount or 0):,.2f}"])
            
            if deduction.deduction_type:
                if deduction.deduction_type.is_statutory:
                    total_statutory += float(deduction.amount or 0)
                elif deduction.deduction_type.is_voluntary:
                    total_voluntary += float(deduction.amount or 0)
        
        deductions_table = Table(deductions_data, colWidths=[doc.width*0.7, doc.width*0.3])
        deductions_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#EF4444')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (1, -1), (1, -1), colors.HexColor('#EF4444')),
        ]))
        elements.append(deductions_table)
        
        # Add Deductions Total
        deductions_total = [
            ["", f"<b>Total Deductions: KES {float(payslip.total_deductions or 0):,.2f}</b>"]
        ]
        deductions_total_table = Table(deductions_total, colWidths=[doc.width*0.7, doc.width*0.3])
        deductions_total_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 0), (1, 0), 11),
            ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#EF4444')),
            ('PADDING', (0, 0), (-1, 0), 6),
        ]))
        elements.append(deductions_total_table)
        elements.append(Spacer(1, 20))
        
        # Summary Section
        elements.append(Paragraph("SUMMARY", heading_style))
        
        summary_data = [
            ["Description", "Amount (KES)"],
            ["Total Gross Earnings", f"{float(payslip.gross_earnings or 0):,.2f}"],
            ["Total Deductions", f"{float(payslip.total_deductions or 0):,.2f}"],
        ]
        
        # Add statutory breakdown if available
        if total_statutory > 0:
            summary_data.append(["  - Statutory Deductions", f"{total_statutory:,.2f}"])
        if total_voluntary > 0:
            summary_data.append(["  - Voluntary Deductions", f"{total_voluntary:,.2f}"])
        
        summary_data.append(["", ""])
        summary_data.append(["<b>NET PAY</b>", f"<b>KES {float(payslip.net_pay or 0):,.2f}</b>"])
        
        summary_table = Table(summary_data, colWidths=[doc.width*0.7, doc.width*0.3])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('GRID', (0, 0), (-1, -3), 1, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#4F46E5')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('TEXTCOLOR', (1, -1), (1, -1), colors.HexColor('#4F46E5')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EEF2FF')),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))
        
        # Payment Information
        payment_info = Paragraph(
            f"<b>Payment Method:</b> {payslip.payment_method.value if payslip.payment_method else 'N/A'} | "
            f"<b>Reference:</b> {payslip.payment_reference or 'N/A'} | "
            f"<b>Paid Date:</b> {payslip.paid_at.strftime('%d/%m/%Y') if payslip.paid_at else 'Pending'}",
            normal_style
        )
        elements.append(payment_info)
        elements.append(Spacer(1, 10))
        
        # Bank Details
        if employee.payroll_info:
            bank_text = f"""
            <b>Bank Details:</b> {employee.payroll_info.bank_name or 'N/A'} - {employee.payroll_info.bank_branch or 'N/A'} | 
            <b>Account:</b> {employee.payroll_info.bank_account or 'N/A'} | 
            <b>M-Pesa:</b> {employee.payroll_info.mpesa_number or 'N/A'}
            """
            elements.append(Paragraph(bank_text, normal_style))
        
        elements.append(Spacer(1, 20))
        
        # Footer with disclaimer
        disclaimer = Paragraph(
            "<i>This is a computer-generated document and does not require a signature. "
            "For any queries, please contact the HR department.</i>",
            ParagraphStyle(
                'Disclaimer',
                parent=styles['Normal'],
                fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.grey
            )
        )
        elements.append(disclaimer)
        
        # Footer with generation date
        generated_date = Paragraph(
            f"Generated on: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            ParagraphStyle(
                'Date',
                parent=styles['Normal'],
                fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.grey
            )
        )
        elements.append(generated_date)
        
        # Build PDF
        doc.build(elements)
        
        # Get the value of the BytesIO buffer
        pdf = buffer.getvalue()
        buffer.close()
        
        return pdf