# JUSTICE-KP Backup And Restore

Default policy:
- Daily backup retained for 14 days.
- Weekly full backup retained for 8 weeks.
- Backups include database, uploads, transcripts, evidence, and generated forms.
- Production backups should use the `cryptography` package so the archive uses the AES-based Fernet envelope.

Restore policy:
- Only System Admin may request restore.
- Verify the backup first.
- Create a pre-restore backup.
- Stop the app before manual database/file replacement.
- Audit the restore request and keep the pre-restore backup.
