# JUSTICE-KP Deployment Checklist

- Set `APP_ENV=production`.
- Use PostgreSQL through `DATABASE_URL`.
- Set strong `SESSION_SECRET` and `BACKUP_ENCRYPTION_KEY`.
- Restrict `ALLOWED_ORIGINS` to the barangay LAN frontend URL.
- Run `backend/seed_admin.py` with a strong one-time admin password.
- Confirm all upload directories are outside frontend public folders.
- Run `npx next build` and backend tests.
- Create and verify a backup before live use.
- Confirm a Viewer cannot access sensitive evidence or exports.
- Keep the server on a secured office machine with restricted OS accounts.
