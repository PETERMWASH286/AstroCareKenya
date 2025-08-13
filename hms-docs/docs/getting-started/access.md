# Access & Onboarding 🚪

AstroCare is a **web-based** Hospital Management System (HMS).  
There is **no software to install** for everyday users — hospitals access AstroCare through secure web addresses and a short onboarding process.

**Get started now:** <a href="https://astrocarekenya.com" target="_blank" rel="noopener noreferrer">https://astrocarekenya.com</a>

---

## How organizations access AstroCare

### 1. SaaS / Hosted (recommended)
- Each hospital uses a secure subdomain like:  
  `https://<hospital-shortname>.astrocarekenya.com`  
- Subdomains allow custom branding, separate data, and a single platform that’s easy to manage.

### 2. On-premises / Private Cloud (optional)
- For hospitals that require private hosting, we offer deployment guidance and configuration help.
- On-prem deployments include domain mapping, firewall and network setup, and MPESA callback configuration if needed.

### 3. Single Sign-On (SSO) & Enterprise Auth
- AstroCare supports SAML 2.0, OpenID Connect, and LDAP/AD integration.
- We recommend SSO for staff to simplify login and centralize access control.

---

## Quick start — First-time onboarding (super admin flow)

These are the minimal steps to get your hospital running:

1. **Request an account or sign up**  
   Visit **https://astrocarekenya.com/get-started** (or contact our sales team) to request your organization account.

2. **Create the Super Admin**  
   - Complete organization info (name, address, timezone).  
   - Create Super Admin user and enable Two-Factor Authentication (2FA).

3. **Add your facility(ies)**  
   - Add hospital/clinic names, departments, and default settings.

4. **Enable payment methods**  
   - Turn on **M-Pesa** integration (enter MPESA credentials and callback URL).  
   - Optionally enable other gateways.

5. **Invite staff & assign roles**  
   - Create accounts or invite staff by email. Assign roles (Doctor, Nurse, Lab Tech, Pharmacist, Accountant, Receptionist, HR).

6. **Set up departments & services**  
   - Add Outpatient, Inpatient, Lab, Radiology, Pharmacy and the services you offer (consultations, tests, imaging).

7. **(Optional) Import existing data**  
   - Use the Admin import tool to upload patients, tariffs, and historical records via CSV/Excel.

8. **Go-Live checklist**  
   - Verify HTTPS and domain routing.  
   - Test M-Pesa payment flow (sandbox and live).  
   - Confirm user roles & access.  
   - Run a pilot day with a small team.  
   - Enable audit logging and backups.

---

## Recommended browsers & network settings

- **Browsers:** Chrome (latest), Edge (Chromium), Firefox (latest). Mobile: Safari, Chrome.  
- **Security:** TLS 1.2+ (HTTPS enforced).  
- **Ports:** 443 for web traffic. For on-prem please ensure the MPESA callback URL is reachable from outside if using M-Pesa.

---

## Security, privacy & compliance (short)
AstroCare is built with health data protections in mind:
- Compliance with **Health Act 2017** and **Data Protection Act 2019** (Kenya).  
- Role-based access control, audit trails, encrypted transport, and secure backups.  
- Integration-ready for national health exchange (Digital Health Superhighway) to securely share data when authorized.

---

## Support & onboarding services
We provide hands-on support:
- Guided onboarding and admin training  
- Data migration and CSV import help  
- Custom integrations (SSO, LIS/RIS, insurance)  
- On-site or remote training workshops

**Email:** support@astrocare.com  
**Get started (signup & info):** https://astrocarekenya.com/get-started

---

## Next steps (recommended)
- Read **Navigation & Productivity** to learn fast workflows.  
- Visit **Administration & Multi-Hospital** to set up additional facilities and the Super Admin dashboard.  
- Run the **Go-Live checklist** with your IT lead before opening to staff.

---

If you want, I can now:
- Create `docs/getting-started/checklist.md` with a printable go-live checklist, or  
- Draft the **Billing (M-Pesa setup)** page showing exact settings and example callback endpoints you can paste into Safaricom/MPESA.  

Which one should I build next? (Checklist or M-Pesa setup)
