"""Reset the local admin login using values from .env without deleting attendance data."""
import os
from dotenv import load_dotenv

load_dotenv()

from app.database import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password

email = os.getenv("ADMIN_EMAIL", "admin@example.com").strip().lower()
password = os.getenv("ADMIN_PASSWORD", "")
if not password:
    raise SystemExit("ERROR: ADMIN_PASSWORD is empty. Set it in your .env file first.")

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    admin = db.query(User).filter(User.role == "admin").order_by(User.id).first()
    email_owner = db.query(User).filter(User.email == email).first()

    if email_owner and (admin is None or email_owner.id != admin.id):
        raise SystemExit(f"ERROR: {email} is already used by another account. Choose another ADMIN_EMAIL.")

    if admin:
        admin.email = email
        admin.password_hash = hash_password(password)
        admin.active = True
        if not admin.name:
            admin.name = "Administrator"
        action = "updated"
    else:
        admin = User(
            name="Administrator",
            email=email,
            password_hash=hash_password(password),
            role="admin",
            active=True,
        )
        db.add(admin)
        action = "created"

    db.commit()

print(f"Admin account {action} successfully.")
print(f"Email: {email}")
print("Password: taken from ADMIN_PASSWORD in .env")
print("Existing attendance records were not deleted.")
