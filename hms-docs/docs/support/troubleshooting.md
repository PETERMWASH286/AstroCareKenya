# Troubleshooting Guide — AstroCare

Welcome to the **AstroCare Troubleshooting Guide**! This page is designed to help hospital staff, administrators, and IT teams quickly resolve **common issues** and keep your hospital operations running smoothly.  
We’ve structured this guide for **clarity, modern readability, and actionable solutions**.

---

## 🔹 Table of Contents

- [General Access Issues](#general-access-issues)  
- [Patient & Appointment Issues](#patient--appointment-issues)  
- [Billing & Payment Issues](#billing--payment-issues)  
- [Laboratory & Radiology Issues](#laboratory--radiology-issues)  
- [HR & Staff Management Issues](#hr--staff-management-issues)  
- [Admin & Multi-Hospital Issues](#admin--multi-hospital-issues)  
- [Security & Login Issues](#security--login-issues)  
- [Integrations & Connectivity](#integrations--connectivity)  
- [System Performance](#system-performance)  
- [Help & Support](#help--support)

---

## General Access Issues

**Q1: I cannot access AstroCare via my browser.**  
- Ensure you are using a **supported browser**: Chrome (latest), Edge (Chromium), Firefox (latest). Mobile: Safari/Chrome.  
- Check the URL format: `https://<hospital-shortname>.astrocarekenya.com`.  
- Verify your **internet connection** and firewall settings.  
- Clear cache and cookies or try **incognito/private mode**.

**Q2: The page is loading very slowly.**  
- Ensure a stable internet connection (minimum 5 Mbps for optimal performance).  
- Large reports may take longer to render—try **filtering or exporting smaller sets**.  
- Contact IT to check for **network or VPN restrictions**.

---

## Patient & Appointment Issues

**Q1: I cannot find a patient in the system.**  
- Make sure the patient is **registered** correctly.  
- Use **Digital Health Superhighway search** if the patient exists in another facility.  
- Check if the **patient status** is inactive or archived.

**Q2: Appointments are overlapping or missing.**  
- Ensure the **doctor’s schedule** is correctly configured.  
- Refresh the dashboard for **real-time updates**.  
- Verify time zone settings in Admin → Facility Settings.

---

## Billing & Payment Issues

**Q1: M-Pesa payment is not completing.**  
- Confirm the **MPESA credentials and callback URL** are correctly configured in Finance → Payment Methods.  
- Ensure patient has sufficient **balance or network coverage**.  
- Verify that the transaction logs are not showing any **duplicate or pending transactions**.  
- Learn more: [AstroCare Billing & Payments](../features/billing.md)

**Q2: Insurance payments are not recorded.**  
- Confirm the **insurance plan is active** and mapped to the patient.  
- Check Finance → Insurance Receivables → Pending Claims.  
- Review system **logs for failed transactions**.

---

## Laboratory & Radiology Issues

**Q1: Lab test results are missing.**  
- Ensure **samples were collected** and linked to the correct patient.  
- Check if the results **require approval** from a lab supervisor.  
- Confirm that **LOINC FHIR API integration** is active for standardized test codes.  
- Rejected samples will appear in **Lab → Rejected Samples** with reasons.

**Q2: Imaging orders are not visible.**  
- Confirm radiology order was **submitted** in the appointment workflow.  
- Verify that **assigned radiology staff** have proper access rights.

---

## HR & Staff Management Issues

**Q1: Attendance not updating for staff.**  
- Check device/system used for clock-in/out.  
- Ensure **duties and schedules** are correctly configured.  
- Audit logs are available in HR → Attendance → Logs for troubleshooting discrepancies.

**Q2: Payroll discrepancies.**  
- Review **attendance, roles, and salary rules**.  
- Verify that **bonus, deductions, and leave adjustments** are correctly entered.

---

## Admin & Multi-Hospital Issues

**Q1: Reports are missing or incomplete.**  
- Confirm that data is **entered and approved** in each module.  
- Use **filters and date ranges** appropriately.  
- Super Admin can check **consolidated reports across hospitals**.

**Q2: Notifications are not received.**  
- Ensure notification settings are **enabled for your role**.  
- Verify email and SMS integrations are active in Admin → System Settings.

---

## Security & Login Issues

**Q1: I forgot my password.**  
- Click **“Forgot Password”** on login page.  
- Follow the email or SMS OTP link to reset your password.  
- For security, 2FA will be prompted after reset.

**Q2: Cannot access patient records.**  
- Confirm your **role has proper permissions**.  
- For Digital Health Superhighway access, patient **OTP consent** is required.

---

## Integrations & Connectivity

**Q1: Digital Health Superhighway data not syncing.**  
- Confirm **API keys, endpoints, and hospital registration** with DHIS.  
- Check network/firewall rules for secure outbound connections.  

**Q2: SMS/Email notifications failing.**  
- Check **Africa’s Talking API** credentials.  
- Ensure email server integration (SMTP) is configured correctly.

---

## System Performance

**Q1: Dashboard charts not loading.**  
- Clear browser cache and refresh.  
- Ensure **data range filters** are set appropriately.  
- Large data sets may require **shorter date ranges**.

**Q2: System crashing or slow response.**  
- Verify server resources (CPU, RAM, Disk).  
- Check **database connection and latency**.  
- Contact IT or AstroCare support for **server-side diagnostics**.

---

## Help & Support

- **Support Email:** support@astrocare.com  
- **Community Forum:** [AstroCare Discussions](#)  
- **Documentation:** [AstroCare User Guide](../index.md)  

> 💡 **Pro Tip:** Always report issues with **screenshots, patient IDs, timestamps, and steps to reproduce**—this helps support resolve issues faster.

---

AstroCare is designed to **minimize downtime** and provide a **smooth, modern user experience**.  
Following this guide ensures **faster problem resolution** and maximizes the **value of your hospital management system**.
