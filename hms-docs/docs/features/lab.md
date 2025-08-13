# Laboratory Management — Complete Workflow

The Laboratory module in **AstroCare** enables streamlined diagnostic operations across all lab sections. From receiving test requests to generating reports, every step is optimized for accuracy, compliance, and speed.

---

## Key Features at a Glance
- **Lab Test Order Management** — Receive & track test requests from clinicians.
- **Sample Collection & Labeling** — Full chain-of-custody.
- **Result Entry & Approval Workflow** — Role-based review before release.
- **Rejection Handling** — Standardized reasons with audit trail.
- **LOINC & FHIR API Support** — Interoperable coding for structured lab data.
- **Dynamic Reference Ranges** — Parameter-based limits for interpretation.
- **Blood Bank Management** — Track donors, inventory, and transfusions.
- **Quality Control & Maintenance Logs** — Compliance-ready operations.
- **Pricing & Billing Integration** — Linked to **Finance** module.
- **Reporting & Analytics** — For clinical, operational, and compliance insights.

---

## Workflow Overview
### 1. **Receiving Lab Test Orders**
- Test requests are generated during consultations or added from reception for walk-ins.
- Orders appear in the **Pending Samples** list in the Lab Dashboard.
- Each order contains:
  - Patient details
  - Requested tests or panels
  - Priority (Routine / Urgent / Stat)
  - Payment status (must be cleared before sample collection if configured)

**Quick link:** [Consultation & Orders](../features/consultation.md)

---

### 2. **Sample Collection & Labeling**
- Lab staff **accept the order**, print **barcode labels**, and attach them to sample containers.
- Supported sample types: Blood, Urine, Sputum, Swab, Tissue, CSF.
- Chain-of-custody tracked:
  - Collected by
  - Date & time
  - Location
- Auto-notify clinicians once sample is collected.

**Tip:** Use barcode scanners for faster workflow and fewer errors.

---

### 3. **Sample Rejection Policy**
A sample can be **rejected** if:
- Incorrect container or anticoagulant used.
- Insufficient volume for analysis.
- Hemolyzed or contaminated specimen.
- Delay in transport causing sample degradation.

When rejecting:
- Select standardized **reason for rejection** in system.
- Notify requesting clinician with instructions for recollection.
- All rejection events are **logged** for quality audits.

---

### 4. **Performing Tests & Result Entry**
- Select the **received sample** and mark as *In Progress*.
- Enter results for each parameter:
  - **Example:** CBC → Hemoglobin, WBC, Platelets, etc.
- Attach **instrument auto-generated files** (PDF, HL7 messages) for traceability.
- Enter **comments** or flags for abnormal values.
- Add **reference ranges** (auto-suggested from test configuration).
- Pending results can be saved as **drafts** before validation.

---

### 5. **Result Approval Workflow**
- **Two-level verification** is recommended:
  - **Technologist** → initial entry.
  - **Lab Supervisor / Pathologist** → approval.
- Once approved, results are:
  - Auto-attached to the patient’s chart.
  - Available to clinicians for review.
  - Visible in the **Patient Portal** (if enabled).

---

## LOINC & FHIR API Integration
AstroCare supports **LOINC codes** for standardized test identification and **FHIR APIs** for interoperability:
- Each lab test can be mapped to a LOINC code.
- Enables exchange with national health systems and DHSH.
- Improves semantic interoperability for analytics & AI-driven care.

**Learn more:**  
- [LOINC Official Site](https://loinc.org/)  
- [FHIR Laboratory Implementation Guide](https://build.fhir.org/ig/HL7/fhir-diagnostic-report/)

---

### Parameters & Reference Ranges
Each lab test in AstroCare has:
- Test name & code
- Parameters (e.g., Hemoglobin, WBC for CBC)
- **Reference ranges** (age/sex-specific if applicable)
- Units of measurement
- Critical values (highlighted in red)
- Comments & interpretation fields

---

### Lab Test Pricing
- **Prices are set in the Finance module** and linked automatically to billing.
- Pricing supports:
  - **Cash**
  - **Insurance** (configured under Finance → Insurance settings)
- If the lab test is unpaid (and **pre-payment rule** is enabled), the order remains in *Pending Payment* status.

---

### Inventory & Test Availability
- If **reagents or kits** for a test are out of stock:
  - The system **automatically disables the test** for ordering.
  - Alerts are sent to Inventory & Lab Admin.
- Integrates with the **Inventory module** for stock levels and reorder triggers.

**Quick link:** [Inventory Management](../features/inventory.md)

---

## Blood Bank Management
AstroCare’s **Blood Bank** feature includes:
- **Donor Management**:
  - Register donors, track blood group, and screening results.
- **Component Tracking**:
  - Whole blood, plasma, platelets, cryoprecipitate.
- **Inventory Monitoring**:
  - Available units, expiry alerts, quarantined stock.
- **Crossmatching & Issue**:
  - Verify compatibility before transfusion.

**Important:** Blood screening results (HIV, HBV, HCV, Syphilis) must be recorded for compliance.

---

## Quality Control (QC)
- Record daily, weekly, and monthly QC checks for instruments.
- Document control ranges, corrective actions, and calibration logs.
- Track **external quality assurance (EQA)** participation and results.

---

## Lab Equipment Maintenance
- Maintain service schedules for analyzers.
- Log calibration dates, maintenance actions, and breakdowns.
- Auto-generate maintenance reminders to prevent downtime.

---

## Lab Reports & Analytics
- **Patient Reports**:
  - Print or share digitally (PDF with QR verification).
- **Operational Reports**:
  - Pending tests, TAT (Turnaround Time), QC logs.
- **Financial Reports**:
  - Revenue per test, insurance claims.
- **Regulatory Reports**:
  - Compliance-ready exports (CSV, HL7).

---

## Why Approval is Critical
- Prevents release of unverified results.
- Maintains **legal and clinical safety**.
- Ensures audit trail compliance (Health Act 2017, ISO 15189).

---

### Visual Examples
- Lab Dashboard: `https://astrocarekenya.com/assets/images/lab-dashboard.png`
- Sample Tracking: `https://astrocarekenya.com/assets/images/sample-tracking.png`
- Blood Bank UI: `https://astrocarekenya.com/assets/images/blood-bank.png`

---

## Learning Resources
- [ISO 15189: Medical Laboratories – Quality & Competence](https://www.iso.org/standard/56115.html)
- [WHO Laboratory Quality Management System](https://www.who.int/ihr/publications/lqms/en/)
- [FHIR Diagnostic Report](https://www.hl7.org/fhir/diagnosticreport.html)

---

## Quick Links
- Billing → `../billing.md`  
- Inventory → `../inventory.md`  
- Finance → `../finance.md`  
- Digital Health Superhighway → `../integrations.md`  

---

### Summary
AstroCare’s Laboratory module ensures **accuracy, compliance, and interoperability**, from order entry to reporting. With **LOINC/FHIR support**, **quality control**, and **integrated billing**, it provides a complete, future-ready diagnostic solution.

---
