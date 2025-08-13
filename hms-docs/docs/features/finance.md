# Finance Management — AstroCare

AstroCare’s **Finance Module** is a modern, fully-featured financial management system built specifically for hospitals. It enables administrators, accountants, and finance teams to **manage cash flow, insurance, payments, expenses, and pricing** in a secure, auditable, and user-friendly environment.  

Designed for **real-world hospital operations**, it supports everything from patient billing and insurance management to supplier payments and full financial reporting.

---

## 🚀 Key Features Overview

- **Patient Billing & Cash Payments**
  - Generate invoices for services (consultation, lab, radiology, pharmacy, etc.).
  - Accept **cash payments**, record receipts, and automatically update patient account balances.
  - Support partial payments or pre-payments for services like lab tests or pharmacy.

- **Insurance Management**
  - Define insurance providers, plans, and the services they cover.
  - Record insurance claims and track **receivables**.
  - Automatic validation of patient insurance eligibility during registration or service booking.
  - Support **bulk insurance payment reconciliation**.

- **Service Pricing**
  - Set and manage prices for all medical services.
  - Configure **tiered pricing**: outpatient vs inpatient, walk-in, special clinic pricing.
  - Update pricing centrally — changes propagate to all billing screens.

- **Expense & Supplier Management**
  - Track **operational expenses** (utilities, staff reimbursements, equipment maintenance, etc.).
  - Record **supplier payments**, outstanding balances, and purchase orders.
  - Link expenses to **departments** for accurate cost reporting.

- **Financial Reports & Analytics**
  - Generate **daily, weekly, monthly, and annual reports**.
  - Track revenue streams by payment method (cash, insurance, M-Pesa, Paybill).
  - Monitor **accounts receivable**, outstanding insurance claims, and overdue balances.
  - Dashboard visualizations for revenue, expenses, and profitability.

- **Transaction Logs & Auditability**
  - Every transaction is logged: who performed it, timestamp, and action details.
  - Helps with audits, regulatory compliance, and internal review.

---

## Patient Billing Workflow

1. **Service Selection**
   - When a patient visits, select the services they will receive (consultation, lab, radiology, pharmacy).
   - Each service automatically pulls its price from the **Finance → Services Pricing** module.

2. **Payment Method**
   - **Cash**: receive payment at the point of service.
   - **Insurance**: verify coverage, submit invoice to insurance provider, and record receivable.
   - **M-Pesa**: integrated mobile payment via **STK Push** or **Paybill**. Patients can pay before service delivery.

3. **Invoice Generation**
   - Generate professional PDF/print invoices.
   - Automatic linkage of invoice to patient record, service order, and finance ledger.

4. **Payment Confirmation**
   - Payments are reflected in the patient account and hospital ledger.
   - Notifications can be sent via email or SMS for receipts.

---

## Insurance Management Workflow

- Define **insurance providers** and their **plans**.
- Assign **covered services** for each plan (consultation, lab panels, radiology, pharmacy items).
- During patient registration, select insurance provider and plan.
- When services are rendered, AstroCare automatically:
  - Generates an **insurance invoice**
  - Flags services not covered
  - Tracks **receivables** and payment status
- Reconcile payments when insurance settles claims.

> Learn more about insurance setup: [AstroCare Insurance Setup Guide](../features/insurance.md)

---

## Expense & Supplier Payment Management

- Record hospital expenses under categories: Utilities, Staff Allowances, Medical Supplies, Equipment.
- Track **supplier invoices and payments**.
- Link payments to specific services or departments for **full cost visibility**.
- Generate **cash flow reports** to see liabilities and pending payments.

---

## Financial Reports

AstroCare generates comprehensive financial analytics for decision-making:

- **Revenue by Department**: How much revenue each hospital unit generates.
- **Payments by Method**: Cash, insurance, M-Pesa, Paybill.
- **Expense Reports**: Daily, weekly, monthly, annual.
- **Profit & Loss Statement**: Automatic calculation for management.
- **Insurance Reconciliation Report**: Tracks claims submitted vs. settled.

> Explore reports in detail: [AstroCare Finance Reports](../features/reports.md)

---

## Security & Compliance

- Role-based access ensures only authorized finance staff can view or modify financial data.
- Audit logs track all **transactions, invoice edits, and approvals**.
- Compliance with **Health Act 2017** and **Data Protection Act 2019** for secure handling of patient and financial data.

---

## Integration Points

- **Billing → Finance**: All patient payments flow automatically to finance ledgers.
- **Finance → Inventory**: Service costs and lab/medication usage reflected in financial reports.
- **Insurance Systems**: Supports electronic claims submission and reconciliation.
- **Payment Gateways**: M-Pesa STK Push and Paybill for seamless mobile payments.

---

## Recommended Best Practices

- Predefine **all services and pricing** in Finance before onboarding patients.
- Reconcile insurance payments regularly to maintain accurate receivables.
- Ensure **audit trails** are reviewed periodically.
- Link departmental expenses to service lines for accurate costing.
- Always validate M-Pesa / Paybill callbacks before marking invoices as paid.

---

## Useful Resources & Links

- **AstroCare Billing & Payments**: [Billing Module Guide](billing.md)  
- **Insurance Setup**: [Insurance Management Guide](insurance.md)  
- **Inventory & Pricing**: [Inventory & Service Pricing](../features/inventory.md)  
- **M-Pesa STK Push Integration**: https://developer.safaricom.co.ke  

---

*AstroCare Finance Module gives hospital administrators and finance teams the control, accuracy, and transparency they need to run a modern, multi-service hospital efficiently.*
