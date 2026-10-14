from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth_service import AuthContext, require_permission
from database import DATABASE_PATH, DATABASE_URL
from models import AuditLog, BackupRecord


BASE_DIR = Path(__file__).resolve().parent
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", BASE_DIR / "backups"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
TRANSCRIPT_DIR = Path(os.getenv("TRANSCRIPT_DIR", BASE_DIR / "transcripts"))
EVIDENCE_DIR = Path(os.getenv("EVIDENCE_DIR", BASE_DIR / "evidence_uploads"))
GENERATED_FORMS_DIR = Path(os.getenv("GENERATED_FORMS_DIR", BASE_DIR / "generated_forms"))

BACKUP_DIR.mkdir(exist_ok=True)
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "90"))
BACKUP_RETENTION_COUNT = int(os.getenv("BACKUP_RETENTION_COUNT", "30"))


def checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_backup_key() -> bytes:
    secret = os.getenv("BACKUP_ENCRYPTION_KEY", "development-backup-key-change-me").encode("utf-8")
    return hashlib.sha256(secret).digest()


def encrypt_backup(data: bytes) -> tuple[bytes, str]:
    try:
        from cryptography.fernet import Fernet  # type: ignore

        import base64

        key = base64.urlsafe_b64encode(derive_backup_key())
        return Fernet(key).encrypt(data), "fernet-aes"
    except Exception:
        # Development fallback keeps tests and offline installs working. In
        # production, install cryptography so backups use the AES-based Fernet
        # envelope.
        key = derive_backup_key()
        encrypted = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))
        return encrypted, "development-xor-fallback"


def decrypt_backup(data: bytes, algorithm: str) -> bytes:
    if algorithm == "fernet-aes":
        from cryptography.fernet import Fernet  # type: ignore

        import base64

        key = base64.urlsafe_b64encode(derive_backup_key())
        return Fernet(key).decrypt(data)
    key = derive_backup_key()
    return bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))


class BackupService:
    def run_backup(self, db: Session, actor: AuthContext, backup_type: str = "manual") -> dict[str, Any]:
        require_permission(actor, "backup.manage")
        backup_id = f"backup-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:8]}"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / f"{backup_id}.zip"
            manifest = self.build_manifest()
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, indent=2))
                if self.is_postgres():
                    dump_path = temp_path / "justicekp.sql"
                    self.write_postgres_dump(dump_path)
                    archive.write(dump_path, "database/justicekp.sql")
                elif DATABASE_PATH.exists():
                    archive.write(DATABASE_PATH, "database/justicekp.db")
                for root_dir, prefix in [
                    (UPLOAD_DIR, "uploads"),
                    (TRANSCRIPT_DIR, "transcripts"),
                    (EVIDENCE_DIR, "evidence_uploads"),
                    (GENERATED_FORMS_DIR, "generated_forms"),
                ]:
                    self.add_directory(archive, root_dir, prefix)

            raw = archive_path.read_bytes()
            encrypted, algorithm = encrypt_backup(raw)
            output_path = BACKUP_DIR / f"{backup_id}.jkpbackup"
            output_path.write_bytes(encrypted)
            checksum = checksum_bytes(encrypted)
            manifest["encrypted_size_bytes"] = len(encrypted)
            manifest["encryption_algorithm"] = algorithm
            record = BackupRecord(
                backup_id=backup_id,
                file_path=str(output_path),
                backup_type=backup_type,
                manifest_json=manifest,
                checksum=checksum,
                status="created",
                created_by=actor.user.username,
            )
            db.add(record)
            self.audit(db, actor, "backup_created", record, "high")
            db.commit()
            db.refresh(record)
            result = self.serialize(record)
            self.enforce_retention(db, actor)
            return result

    def list_backups(self, db: Session, actor: AuthContext) -> list[dict[str, Any]]:
        require_permission(actor, "backup.manage")
        records = db.query(BackupRecord).order_by(BackupRecord.created_at.desc()).all()
        return [self.serialize(record) for record in records]

    def backup_file(self, db: Session, backup_id: str, actor: AuthContext) -> BackupRecord:
        require_permission(actor, "backup.manage")
        record = db.query(BackupRecord).filter(BackupRecord.backup_id == backup_id).first()
        if not record or not Path(record.file_path).exists():
            raise HTTPException(status_code=404, detail="Backup was not found.")
        self.audit(db, actor, "backup_downloaded", record, "high")
        db.commit()
        return record

    def verify_backup(self, db: Session, backup_id: str, actor: AuthContext) -> dict[str, Any]:
        require_permission(actor, "backup.manage")
        record = self.backup_file(db, backup_id, actor)
        encrypted = Path(record.file_path).read_bytes()
        if checksum_bytes(encrypted) != record.checksum:
            record.status = "failed_verification"
            db.commit()
            raise HTTPException(status_code=400, detail="Backup checksum verification failed.")
        raw = decrypt_backup(encrypted, record.manifest_json.get("encryption_algorithm", "development-xor-fallback"))
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / "verify.zip"
            zip_path.write_bytes(raw)
            with ZipFile(zip_path, "r") as archive:
                names = set(archive.namelist())
                if "manifest.json" not in names:
                    raise HTTPException(status_code=400, detail="Backup manifest missing.")
        record.status = "verified"
        record.verified_at = datetime.utcnow()
        self.audit(db, actor, "backup_verified", record, "medium")
        db.commit()
        db.refresh(record)
        return self.serialize(record)

    def restore_backup(self, db: Session, backup_id: str, actor: AuthContext) -> dict[str, Any]:
        require_permission(actor, "backup.manage")
        record = self.backup_file(db, backup_id, actor)
        if record.status != "verified":
            raise HTTPException(status_code=400, detail="Verify the backup before restore.")
        pre_restore = self.run_backup(db, actor, backup_type="pre_restore")
        record.status = "restore_ready"
        self.audit(
            db,
            actor,
            "backup_restore_requested",
            record,
            "high",
            {"pre_restore_backup_id": pre_restore["backup_id"], "restore_mode": "manual_operator_required"},
        )
        db.commit()
        return {
            **self.serialize(record),
            "restore_note": "Pre-restore backup created. Manual operator restore is required while the app is offline.",
            "pre_restore_backup_id": pre_restore["backup_id"],
        }

    def build_manifest(self) -> dict[str, Any]:
        files = []
        for root_dir in [UPLOAD_DIR, TRANSCRIPT_DIR, EVIDENCE_DIR, GENERATED_FORMS_DIR]:
            if not root_dir.exists():
                continue
            for path in root_dir.rglob("*"):
                if path.is_file():
                    files.append({"path": str(path), "size": path.stat().st_size})
        db_size = DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0
        return {
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            "app": "JUSTICE-KP",
            "database_engine": "postgresql" if self.is_postgres() else "sqlite",
            "database_backup_format": "pg_dump_sql" if self.is_postgres() else "sqlite_file",
            "database_size_bytes": db_size,
            "file_count": len(files),
            "file_size_bytes": sum(item["size"] for item in files),
            "files": files[:500],
        }

    def is_postgres(self) -> bool:
        return DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://"))

    def write_postgres_dump(self, output_path: Path) -> None:
        pg_dump = os.getenv("PG_DUMP_PATH", "pg_dump")
        dump_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        try:
            with output_path.open("wb") as dump_file:
                subprocess.run(
                    [pg_dump, "--no-owner", "--no-privileges", dump_url],
                    stdout=dump_file,
                    stderr=subprocess.PIPE,
                    check=True,
                )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="pg_dump was not found on the backend host.") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="ignore").strip() or "pg_dump failed."
            raise HTTPException(status_code=500, detail=detail) from exc

    def enforce_retention(self, db: Session, actor: AuthContext) -> dict[str, Any]:
        require_permission(actor, "backup.manage")
        records = db.query(BackupRecord).order_by(BackupRecord.created_at.desc()).all()
        cutoff = datetime.utcnow() - timedelta(days=BACKUP_RETENTION_DAYS)
        expired: list[BackupRecord] = []

        for index, record in enumerate(records):
            if record.status == "retention_expired":
                continue
            too_many = index >= BACKUP_RETENTION_COUNT
            too_old = record.created_at < cutoff
            if too_many or too_old:
                expired.append(record)

        for record in expired:
            Path(record.file_path).unlink(missing_ok=True)
            record.status = "retention_expired"
            self.audit(
                db,
                actor,
                "backup_retention_expired",
                record,
                "medium",
                {
                    "backup_id": record.backup_id,
                    "retention_days": BACKUP_RETENTION_DAYS,
                    "retention_count": BACKUP_RETENTION_COUNT,
                },
            )

        db.commit()
        return {"expired_count": len(expired), "retention_days": BACKUP_RETENTION_DAYS, "retention_count": BACKUP_RETENTION_COUNT}

    def add_directory(self, archive: ZipFile, root_dir: Path, prefix: str) -> None:
        if not root_dir.exists():
            return
        for path in root_dir.rglob("*"):
            if path.is_file():
                archive.write(path, f"{prefix}/{path.relative_to(root_dir)}")

    def serialize(self, record: BackupRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "backup_id": record.backup_id,
            "backup_type": record.backup_type,
            "manifest": record.manifest_json,
            "checksum": record.checksum,
            "status": record.status,
            "created_by": record.created_by,
            "created_at": record.created_at,
            "verified_at": record.verified_at,
        }

    def audit(
        self,
        db: Session,
        actor: AuthContext,
        action: str,
        record: BackupRecord,
        risk_level: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        db.add(
            AuditLog(
                case_id="backup",
                action=action,
                actor=actor.user.username,
                actor_user_id=actor.user.id,
                actor_role=actor.user.role_name,
                resource_type="backup",
                resource_id=record.backup_id,
                risk_level=risk_level,
                details_json=details or {"backup_id": record.backup_id},
            )
        )
