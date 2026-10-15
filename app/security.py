import hashlib, hmac, os, secrets
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY", "dev-only-change-me"), salt="attendance-session")

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, expected = encoded.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, AttributeError):
        return False

def make_session(user_id: int) -> str:
    return serializer.dumps({"uid": user_id})

def read_session(token: str | None):
    if not token:
        return None
    try:
        return int(serializer.loads(token, max_age=604800)["uid"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None
