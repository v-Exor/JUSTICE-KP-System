from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from auth_schemas import LoginRequest, UserCreateRequest, UserPasswordRequest, UserStatusRequest, UserUpdateRequest
from models import AuditLog, LoginAttempt, Role, User, UserSession


SESSION_COOKIE = "justice_kp_session"
CSRF_COOKIE = "justice_kp_csrf"
CSRF_HEADER = "x-csrf-token"
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
PBKDF2_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "210000"))
DEV_ADMIN_PASSWORD = os.getenv("DEV_ADMIN_PASSWORD", "Admin12345!")


ROLE_PERMISSIONS: dict[str, list[str]] = {
    "system_admin": [
        "case.read",
        "sensitive_case.read",
        "case.write",
        "case.delete",
        "case.cancel",
        "transcript.read",
        "transcript.write",
        "evidence.read",
        "evidence.write",
        "evidence.download",
        "phase2.analyze",
        "phase3.decide",
        "phase4.generate",
        "phase5.evaluate",
        "forms.download",
        "reports.export",
        "settings.manage",
        "users.manage",
        "backup.manage",
    ],
    "barangay_secretary": [
        "case.read",
        "sensitive_case.read",
        "case.write",
        "case.cancel",
        "transcript.read",
        "transcript.write",
        "evidence.read",
        "evidence.write",
        "evidence.download",
        "phase2.analyze",
        "phase3.decide",
        "phase4.generate",
        "forms.download",
        "reports.export",
    ],
    "lupon_chair": [
        "case.read",
        "sensitive_case.read",
        "transcript.read",
        "evidence.read",
        "evidence.download",
        "phase3.decide",
        "phase4.generate",
        "forms.download",
        "reports.export",
    ],
    "lupon_member": [
        "case.read",
        "transcript.read",
        "evidence.read",
        "phase3.decide",
        "forms.download",
    ],
    "researcher": [
        "case.read",
        "transcript.read",
        "phase5.evaluate",
        "reports.export",
    ],
    "viewer": ["case.read"],
}

ROLE_DISPLAY_NAMES = {
    "system_admin": "System Admin",
    "barangay_secretary": "Barangay Secretary",
    "lupon_chair": "Lupon Chair/Captain",
    "lupon_member": "Lupon Member/Mediator",
    "researcher": "Researcher/Auditor",
    "viewer": "Viewer",
}


@dataclass
class AuthContext:
    user: User
    role: Role
    session: UserSession
    csrf_token: str

    @property
    def permissions(self) -> list[str]:
        return self.role.permissions_json or []


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_hash(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), actual_salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(actual_salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
        iterations = int(iterations_text)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def seed_roles_and_dev_admin(db: Session) -> None:
    for role_name, permissions in ROLE_PERMISSIONS.items():
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            db.add(
                Role(
                    name=role_name,
                    display_name=ROLE_DISPLAY_NAMES[role_name],
                    permissions_json=permissions,
                )
            )
        else:
            role.display_name = ROLE_DISPLAY_NAMES[role_name]
            role.permissions_json = permissions
    db.flush()

    if not db.query(User).first():
        db.add(
            User(
                username="admin",
                full_name="System Admin",
                role_name="system_admin",
                password_hash=password_hash(DEV_ADMIN_PASSWORD),
                is_active=True,
                must_change_password=False,
            )
        )
    db.commit()


def get_role(db: Session, role_name: str) -> Role:
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=400, detail="Role was not found.")
    return role


def login(db: Session, request: Request, response: Response, payload: LoginRequest) -> dict[str, Any]:
    username = payload.username.strip().lower()
    ip_address = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    user = db.query(User).filter(User.username == username).first()
    success = bool(user and user.is_active and verify_password(payload.password, user.password_hash))
    db.add(
        LoginAttempt(
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            reason="success" if success else "invalid_credentials",
        )
    )
    if not success or not user:
        db.add(
            AuditLog(
                case_id="auth",
                action="login_failed",
                actor=username,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="auth",
                resource_id=username,
                risk_level="medium",
                details_json={"username": username},
            )
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id,
        session_token_hash=hash_secret(token),
        csrf_token_hash=hash_secret(csrf_token),
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
    )
    user.last_login_at = datetime.utcnow()
    db.add(session)
    db.add(
        AuditLog(
            case_id="auth",
            action="login_success",
            actor=user.username,
            actor_user_id=user.id,
            actor_role=user.role_name,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="auth",
            resource_id=str(user.id),
            risk_level="low",
            details_json={"username": user.username},
        )
    )
    db.commit()
    db.refresh(session)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("APP_ENV", "development").lower() == "production",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        samesite="strict",
        secure=os.getenv("APP_ENV", "development").lower() == "production",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return user_payload(db, user, csrf_token)


def logout(db: Session, request: Request, response: Response, context: AuthContext | None) -> dict[str, str]:
    if context:
        context.session.revoked_at = datetime.utcnow()
        db.add(
            AuditLog(
                case_id="auth",
                action="logout",
                actor=context.user.username,
                actor_user_id=context.user.id,
                actor_role=context.user.role_name,
                ip_address=request.client.host if request.client else "",
                user_agent=request.headers.get("user-agent", ""),
                resource_type="auth",
                resource_id=str(context.user.id),
                risk_level="low",
                details_json={},
            )
        )
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"message": "Logged out."}


def authenticate_request(db: Session, request: Request, require_csrf: bool = False) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    session = (
        db.query(UserSession)
        .filter(UserSession.session_token_hash == hash_secret(token))
        .order_by(UserSession.id.desc())
        .first()
    )
    if not session or session.revoked_at or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired.")
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive.")
    role = get_role(db, user.role_name)
    csrf_token = request.headers.get(CSRF_HEADER, "")
    if require_csrf and not hmac.compare_digest(hash_secret(csrf_token), session.csrf_token_hash):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")
    return AuthContext(user=user, role=role, session=session, csrf_token=csrf_token)


def restore_csrf_token(
    db: Session,
    request: Request,
    response: Response,
    context: AuthContext,
) -> str:
    """Return the session CSRF token, rotating it only for legacy/missing cookies."""
    csrf_token = request.cookies.get(CSRF_COOKIE, "")
    if not csrf_token or not hmac.compare_digest(hash_secret(csrf_token), context.session.csrf_token_hash):
        csrf_token = secrets.token_urlsafe(32)
        context.session.csrf_token_hash = hash_secret(csrf_token)
        db.add(context.session)
        db.commit()

    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        samesite="strict",
        secure=os.getenv("APP_ENV", "development").lower() == "production",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )
    context.csrf_token = csrf_token
    return csrf_token


def user_payload(db: Session, user: User, csrf_token: str = "") -> dict[str, Any]:
    role = get_role(db, user.role_name)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role_name": user.role_name,
        "permissions": role.permissions_json or [],
        "csrf_token": csrf_token,
    }


def require_permission(context: AuthContext, permission: str) -> None:
    if permission not in context.permissions:
        raise HTTPException(status_code=403, detail="You do not have permission for this action.")


def create_user(db: Session, payload: UserCreateRequest, actor: AuthContext) -> User:
    require_permission(actor, "users.manage")
    username = payload.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists.")
    get_role(db, payload.role_name)
    user = User(
        username=username,
        full_name=payload.full_name.strip(),
        role_name=payload.role_name,
        password_hash=password_hash(payload.password),
        is_active=payload.is_active,
        must_change_password=payload.must_change_password,
    )
    db.add(user)
    db.flush()
    audit_user_change(db, actor, "user_created", user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, payload: UserUpdateRequest, actor: AuthContext) -> User:
    require_permission(actor, "users.manage")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User was not found.")
    data = payload.model_dump(exclude_unset=True)
    if "role_name" in data and data["role_name"]:
        get_role(db, data["role_name"])
    if data.get("is_active") is False and user.is_active:
        ensure_user_deactivation_allowed(db, user)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    audit_user_change(db, actor, "user_updated", user)
    db.commit()
    db.refresh(user)
    return user


def update_user_password(db: Session, user_id: int, payload: UserPasswordRequest, actor: AuthContext) -> User:
    require_permission(actor, "users.manage")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User was not found.")
    user.password_hash = password_hash(payload.password)
    user.must_change_password = payload.must_change_password
    audit_user_change(db, actor, "user_password_changed", user)
    db.commit()
    db.refresh(user)
    return user


def update_user_status(db: Session, user_id: int, payload: UserStatusRequest, actor: AuthContext) -> User:
    require_permission(actor, "users.manage")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User was not found.")
    if not payload.is_active and user.is_active:
        ensure_user_deactivation_allowed(db, user)
    user.is_active = payload.is_active
    audit_user_change(db, actor, "user_status_changed", user)
    db.commit()
    db.refresh(user)
    return user


def ensure_user_deactivation_allowed(db: Session, user: User) -> None:
    active_user_count = db.query(User).filter(User.is_active.is_(True)).count()
    if active_user_count <= 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "This account cannot be deactivated because it is the only active user account. "
                "Create or activate another account before deactivating it."
            ),
        )

    if user.role_name == "system_admin":
        active_admin_count = (
            db.query(User)
            .filter(User.is_active.is_(True), User.role_name == "system_admin")
            .count()
        )
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This account cannot be deactivated because it is the only active system administrator. "
                    "Create or activate another system administrator account first."
                ),
            )


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role_name": user.role_name,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
    }


def audit_user_change(db: Session, actor: AuthContext, action: str, target: User) -> None:
    db.add(
        AuditLog(
            case_id="admin",
            action=action,
            actor=actor.user.username,
            actor_user_id=actor.user.id,
            actor_role=actor.user.role_name,
            resource_type="user",
            resource_id=str(target.id),
            risk_level="medium",
            details_json={"target_username": target.username, "target_role": target.role_name},
        )
    )
