# Consultation — Clinical Workflow (Consultation Module)

This page explains how clinicians (doctors, clinical officers, nurse practitioners) run consultations in AstroCare.  
The consultation flow is streamlined so clinicians can focus on patient care while the system handles documentation, orders, and follow-up.

---

## Quick overview — what happens in a consultation
1. Patient enters the **Consultation Queue** (from Appointments or Walk-in).  
2. Clinician **accepts** the patient and opens the **Treatment Form**.  
3. Complete clinical assessment (SOAP note) and record **diagnosis**.  
4. Create **lab** and **radiology** requests if needed.  
5. Add **prescriptions** for pharmacy dispensing.  
6. Mark consultation **complete** — orders are sent and results will link back to the patient record for review.

---

## Consultation Queue (How patients arrive)
- Patients are added to the queue from:
  - Booked appointments (appointments module)
  - Reception check-in (walk-ins)
  - Referral intake (from other facilities)
- Queue features:
  - Sort by arrival time, priority, or appointment type (e.g., emergency, consult, follow-up)
  - Filter by clinic/room/specialty
  - Quick actions: **Call patient**, **View record**, **Start consultation**

**Tip:** Use the queue filter to focus on a specific clinician, clinic, or visit type.

---

## Starting & Managing a Consultation
1. Select patient from the queue and click **Start Consultation**.  
2. The system opens the **Treatment Form** pre-filled with demographics and relevant medical history.

### Treatment Form — typical fields
- Patient demographics (auto-filled)
- Visit type (General Consultation / Special Clinic / Follow-up)
- Presenting complaint
- History of present illness
- Past medical history & allergies
- Vital signs (BP, HR, Temp, SpO₂) — manual entry or integrated devices
- Triage category (if applicable)
- Attachments (images, referral letters)

**Save frequently.** AstroCare auto-saves drafts but saving ensures clinical notes are preserved and auditable.

---

## Clinical Assessment (SOAP-style)
AstroCare encourages a structured note to improve clarity:

- **S (Subjective):** Patient’s own words — complaint, duration, symptoms
- **O (Objective):** Exam findings, vitals, labs already available
- **A (Assessment):** Working diagnosis (use ICD-10 codes if available)
- **P (Plan):** Tests ordered, treatments, prescriptions, follow-up plan

You can add multiple assessments and link them to problem lists for chronic care.

---

## Recording Diagnoses & Problem List
- Add one or more diagnoses during the visit.
- Optionally select standardized codes (ICD-10) for each diagnosis — helps billing, reporting, and referrals.
- The patient’s **Problem List** is updated automatically if you mark a diagnosis as chronic.

---

## Lab Requests (Order tests during consultation)
- From the treatment form, add lab tests or panels (e.g., CBC, LFTs).
- Choose priority (routine / urgent) and sample type.
- The order is assigned a tracking number and printed label if required.
- **Pre-payment enforcement:** If your facility requires payment before processing, the system will mark the order as *pending payment* until cleared.

**Quick link:** See detailed lab workflow — `../lab.md`

---

## Radiology Requests
- Order imaging (X-ray, CT, Ultrasound, MRI) from the same form.
- Add clinical notes for the radiology team (indication, history, relevant prior imaging).
- Attach physical files (previous reports, images) to help the radiologist.

**Tip:** For urgent imaging, set request priority to *stat* and notify radiology via the in-app notification.

**Quick link:** See radiology workflow — `../radiology.md`

---

## Prescribing & Medication (Pharmacy integration)
- Create prescriptions directly in the consultation form.
- Select medication, dose, frequency, duration, and special instructions.
- The order is sent to **Pharmacy** where stock is checked and dispensed.
- **Pre-dispensation payment rule:** Pharmacy ensures payment is settled before dispensing if configured.

**Insurance payments:** If the patient is insured, select the insurance provider during billing so claims are recorded. Insurance setup is managed in **Finance**.

**Quick link:** Pharmacy details — `../pharmacy.md`  
**Image:** Medication order UI — `https://astrocarekenya.com/assets/images/medication-order.png`

---

## Review & Results (Post-consultation)
- Lab and radiology results are **automatically attached** to the patient’s record when available.
- Clinicians get notified (in-app / SMS / email) when results are ready.
- To review results:
  - Open patient record → Results tab → Filter by date or test type.
  - Add interpretation, comments, or refer for further care.
- Results review can trigger follow-up appointments or treatment changes.

**Interoperability:** If your site is connected to the **Digital Health Superhighway**, searches can retrieve verified results shared by other facilities (consent-based).

---

## Follow-up, Referrals & Care Plan
- Schedule follow-up appointments from within the consultation (quick-create).
- Create referrals with attached notes and selected relevant files — send electronically if DHSH / external referral integrations are enabled.
- Maintain a longitudinal **Care Plan** for chronic patients (diabetes, hypertension, TB).

---

## Attachments & Media
- Attach images (wound photos), scanned documents, and prior reports to the visit.
- File types allowed: PDF, JPG, PNG, DICOM links for large imaging (stored in PACS or linked via Radiology module).

**Privacy note:** All attachments are stored securely and logged for audit.

---

## Audit Trail & Legal Safety
- Every action (create, update, delete) in a consultation is logged with user, timestamp, and IP (where available).
- Edits are versioned; the original entry remains in the audit log.
- This supports compliance with Health Act 2017 and Data Protection Act 2019.

---

## Shortcuts & Productivity Tips
- Use global search (`/`) to bring up patient by name/ID quickly.
- Start a consult directly from the patient profile: **Patient → New Visit → Start Consultation**.
- Use **templates** for common visit types (e.g., antenatal, TB follow-up, chronic care) to speed documentation.
- Use **pinned checklists** for procedure safety steps.

---

## Best Practices for Clinicians
- Always confirm patient identity before starting (name + DOB or national ID).
- Document allergies and current medications at the top of the note.
- Use standardized diagnosis codes for accurate reporting and billing.
- Attach key images/reports during the encounter to avoid lost information.
- Schedule follow-ups during the consult to increase compliance.

---

## Quick Links
- Patient Management → `../patients.md`  
- Appointments → `../appointments.md`  
- Laboratory → `../lab.md`  
- Radiology → `../radiology.md`  
- Pharmacy → `../pharmacy.md`  
- Digital Health Superhighway integration → `../integrations.md`

---

## Visuals (example)
- Consultation form: `https://astrocarekenya.com/assets/images/consultation-form.png`  
- Queue & doctor dashboard: `https://astrocarekenya.com/assets/images/doctor-queue.png`  
- Results view: `https://astrocarekenya.com/assets/images/results-view.png`

---

### Wrap-up
AstroCare’s consultation module is designed to be fast, safe, and integrated so clinicians can document care, place orders, prescribe, and arrange follow-up without leaving the patient’s chart. Use templates, shortcuts, and the queue filters to become a power user quickly.
