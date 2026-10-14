# JUSTICE-KP Threat Model

Primary threats:
- Unauthorized barangay staff access to sensitive cases.
- Lost or stolen barangay PC or backup drive.
- Accidental export of VAWC, child abuse, or referral data.
- Evidence file leakage through direct paths or weak permissions.
- Weak passwords and shared accounts.
- Malicious upload files.
- Research dataset deanonymization.

Required controls:
- Local accounts with role-based permissions.
- HttpOnly session cookies and CSRF protection.
- Sensitive case defaulting for VAWC/referral workflows.
- Authorized file download endpoints only.
- Encrypted backups and restore verification.
- Audit logs for authentication, exports, downloads, decisions, and admin actions.
