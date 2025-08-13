# Billing & Payments — AstroCare

AstroCare provides a **secure, transparent, and flexible billing system** designed for hospitals and clinics. The platform ensures **real-time payment processing**, supports multiple payment options, and integrates with **insurance and mobile money (M-Pesa)** for a seamless financial workflow.

---

## Core Principles of Billing in AstroCare
- **Pre-Payment Policy:** Patients must **pay for services before receiving them**.
  - Example: Lab tests → Payment before sending the patient to the lab.
  - Example: Pharmacy → Payment before dispensing medication.
- **Multiple Payment Methods:**  
  - Mobile Money (**M-Pesa STK Push**, Paybill)
  - **Cash**
  - **Insurance Billing** (requires configuration)
- **Complete Transparency:** Every transaction is **logged and auditable**.
- **Instant Receipts:** Patients receive **digital receipts via SMS or email**.

---

## How Billing Works

### **1. Adding Services to the Bill**
- Navigate to **Billing → New Bill**.
- Select **Patient** (by name, ID, or phone).
- Add **Services or Items**:
  - Consultation
  - Lab Tests
  - Radiology
  - Pharmacy
  - Other charges (e.g., Registration)
- The system automatically calculates **total cost** and applies **insurance or discounts** if applicable.

---

### **2. Supported Payment Options**

#### **a) M-Pesa STK Push**
AstroCare integrates with **Safaricom M-Pesa API** to allow **real-time mobile payments**.
- Select **M-Pesa (STK Push)** as the payment method.
- Enter the **patient’s phone number**.
- The patient receives a **pop-up prompt** on their phone to enter M-Pesa PIN.
- Payment is confirmed instantly, and the system updates the bill as **PAID**.

![M-Pesa STK Push Flow](https://astrocarekenya.com/assets/images/mpesa-stk.png)

**Learn more:** [Safaricom Daraja API Documentation](https://developer.safaricom.co.ke/daraja/apis/post/safaricom-sandbox)

---

#### **b) M-Pesa Paybill**
- Hospitals with a **business Paybill number** can accept direct payments.
- The cashier enters the **Transaction Code** after confirmation.
- Optionally, AstroCare can **auto-reconcile transactions** via M-Pesa API.

---

#### **c) Cash Payment**
- Cash can be collected at the cashier desk.
- Always issue a **printed or digital receipt**.

---

#### **d) Insurance Billing**
- Insurance companies **must be configured** in the **Finance Module**.
- Steps:
  1. Go to **Finance → Insurance Providers**.
  2. Add the **Insurance Company**, policy terms, and claim limits.
  3. Assign to patients during registration or billing.
- Insurance claims are tracked for **approval and reconciliation**.

---

## **Pre-Service Payment Enforcement**
AstroCare enforces **payment before service**:
- Lab → Pay before lab order is sent.
- Radiology → Pay before imaging is scheduled.
- Pharmacy → Pay before medication is dispensed.
- Special Clinics → Pay before consultation starts.

If payment is not made, the service status remains **Pending Billing**.

---

## **Transaction Logs & Audit**
Every payment creates:
- A **Transaction Log** with:
  - Patient Name
  - Service Name
  - Amount
  - Payment Method
  - Transaction ID
  - Date & Time
- All logs are accessible under **Finance → Transactions** for full audit compliance.

---

## **Refunds & Adjustments**
- Refunds are allowed for **overpayments or canceled services**.
- Admin users can approve and process refunds via **M-Pesa API or cash**.
- All refunds are logged for audit purposes.

---

## **Reports & Analytics**
- Daily collection reports
- Service-wise revenue
- Insurance pending claims
- M-Pesa vs Cash collection trends

---

### **Example Billing Screen**
![AstroCare Billing Dashboard](https://astrocarekenya.com/assets/images/billing-dashboard.png)

---

## Best Practices
- **Verify M-Pesa transactions** via the integrated API or Safaricom portal.
- Configure **insurance providers** before processing insurance patients.
- Ensure **staff training** on billing workflows.
- Use **transaction logs** to reconcile accounts daily.

---

## Useful Links
- [M-Pesa Integration Details](https://developer.safaricom.co.ke/)
- [Insurance Setup Guide](../features/admin.md)
- [Troubleshooting Billing Issues](../support/troubleshooting.md)

---

### **Next Steps**
- Learn about **Pharmacy Management** → [Pharmacy Features](pharmacy.md)
- Go to **Reports & Analytics** → [View Reports](reports.md)
