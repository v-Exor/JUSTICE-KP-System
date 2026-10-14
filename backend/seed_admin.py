import os

from auth_service import password_hash, seed_roles_and_dev_admin
from database import SessionLocal
from models import User


def main() -> None:
    username = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "Admin12345!")
    full_name = os.getenv("ADMIN_FULL_NAME", "System Admin")
    with SessionLocal() as db:
        seed_roles_and_dev_admin(db)
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.password_hash = password_hash(password)
            user.full_name = full_name
            user.role_name = "system_admin"
            user.is_active = True
        else:
            db.add(
                User(
                    username=username,
                    full_name=full_name,
                    role_name="system_admin",
                    password_hash=password_hash(password),
                    is_active=True,
                )
            )
        db.commit()
    print(f"Seeded system admin user: {username}")


if __name__ == "__main__":
    main()
