# Go-Live Checklist — AstroCare ✅

A clean, practical checklist to help your team prepare, test, and launch AstroCare with confidence.  
Use this during onboarding, pilot days, and production cutover. Tick items as you complete them — print this page (`Ctrl+P`) if you prefer a paper copy.

---

## Quick links
**Get started / Sign up:** <a href="https://astrocarekenya.com/get-started" target="_blank" rel="noopener noreferrer">https://astrocarekenya.com/get-started</a>  
**Support:** <a href="mailto:support@astrocare.com">support@astrocare.com</a>

---

## Summary — one-line readiness
- [ ] Organization account created and Super Admin configured  
- [ ] Core services (Web, Database, Storage) verified over HTTPS  
- [ ] Critical workflows (Patient registration → Visit → Billing → Payment) tested

---

## Pre-Launch (Admin) — required before user onboarding
**Purpose:** ensure the system and environment are correctly configured.

- [ ] Organization profile completed (name, address, timezone, logo)
- [ ] Facility(s) added (name, departments, contact info)
- [ ] Domain/subdomain mapped and SSL certificate installed (HTTPS enforced)
- [ ] Backups configured and verified (database + file storage)
- [ ] Audit logging enabled and retention policy set
- [ ] System timezone and locale verified

**Network & security**
- [ ] TLS 1.2+ enforced; HTTP redirects to HTTPS
- [ ] Firewall / load-balancer rules allow required ports (443)
- [ ] MPESA callback URL reachable from the internet (if using M-Pesa)
- [ ] SSO / LDAP settings checked (if applicable)

---

## Data & Configuration
**Purpose:** ensure essential data and settings are in place.

- [ ] Core reference data loaded:
  - [ ] Departments, wards
  - [ ] Service catalog (consultation, labs, imaging)
  - [ ] Tariff/pricing lists
  - [ ] Doctor & staff profiles
- [ ] Patient import (if migrating): sample import succeeded and data validated
- [ ] User roles created (Doctor, Nurse, Lab Tech, Pharmacist, Accountant, Receptionist, HR)
- [ ] Default permissions reviewed for each role
- [ ] Notification channels (email/SMS) configured and tested

---

## Functional Smoke Tests
**Purpose:** verify the main workflows work end-to-end.

**Patient workflow**
- [ ] Create new patient record
- [ ] Create visit / encounter for patient
- [ ] Add clinical notes and attach a document/image

**Appointments**
- [ ] Create appointment and confirm from patient view
- [ ] Reschedule and cancel appointment; verify notifications

**Laboratory**
- [ ] Order a lab panel, mark sample received, enter results
- [ ] Results appear in patient record and trigger notifications where configured

**Radiology**
- [ ] Create imaging order, upload report/image, link to patient record

**Pharmacy**
- [ ] Create prescription, dispense item, decrement inventory

**Billing & Payments (critical)**
- [ ] Create invoice for visit / service
- [ ] Apply payment using M-Pesa (sandbox) — STK push / callback processed
- [ ] Mark invoice fully paid and generate receipt

**Reports & Dashboards**
- [ ] Run daily operations report (appointments, admissions)
- [ ] Run financial summary (invoices, payments)

---

## M-Pesa Integration — minimal payment test
- [ ] Sandbox credentials configured
- [ ] STK Push initiated and completed (mobile receives prompt)
- [ ] Callback endpoint receives notification and marks invoice paid
- [ ] Repeat test in live mode (only after sandbox OK)

**MPESA test endpoints**
- Use the callback URL you provided to Safaricom; verify logs for incoming POSTs and DB updates.

---

## Performance & Load (basic)
- [ ] Homepage / Dashboard loads under acceptable time on target network
- [ ] Concurrent users test for key modules (reception + billing + lab) — no critical errors
- [ ] Database connections stable and connection pool configured

---

## Security & Compliance Checklist
- [ ] Role-based access control enforced
- [ ] Two-Factor Authentication (2FA) enabled for Super Admins
- [ ] Data encryption in transit (TLS) and at rest (if applicable)
- [ ] Audit trail reviewed for sample user actions
- [ ] Privacy notices and consent capture configured
- [ ] Data protection policy in place (aligns with Kenya DPA 2019 & Health Act 2017)

---

## Training & Documentation
- [ ] Super Admin training completed
- [ ] Departmental admin training (reception, billing, lab, pharmacy, radiology)
- [ ] Quick reference cards or short videos available for each role
- [ ] All staff have accounts and understand login + basic shortcuts

---

## Go-Live Operations
- [ ] Helpdesk / support contact assigned and available on day one
- [ ] Business continuity plan reviewed (who to call, rollback steps)
- [ ] Pilot schedule agreed (first day/week scope)
- [ ] Communication to staff & patients (what changes, how to pay, contact points)

**Rollback plan (minimal)**
- [ ] Ensure recent backup exists (timestamp: ________)
- [ ] Procedure documented to revert to pre-launch state if critical failure occurs
- [ ] Contact list for vendor/technical support

---

## Final sign-off (print & collect signatures)
> When all required items above are checked, obtain formal sign-off.

- Super Admin name: ______________________  Date: __________  
- IT Lead name: __________________________  Date: __________  
- Clinical Lead name: _____________________  Date: __________  

---

## Quick printable summary (one page)
- Organization created ✅  
- Facility added ✅  
- SSL & domain ✅  
- Core data loaded ✅  
- MPESA test ✅  
- Staff invited & trained ✅

---

## Need help?
If you get stuck, we’re here to help:
- **Email:** <a href="mailto:support@astrocare.com">support@astrocare.com</a>  
- **Onboarding request:** <a href="https://astrocarekenya.com/get-started" target="_blank" rel="noopener noreferrer">Request onboarding</a>

---

*Tip:* Assign one person as the **Go-Live Owner** — they coordinate checks, tests, and the final sign-off. This dramatically improves launch success and staff satisfaction.
