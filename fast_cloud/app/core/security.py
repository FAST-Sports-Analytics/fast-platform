from datetime import datetime, timedelta, timezone
import hashlib
import secrets

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()
settings = get_settings()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_token(subject: str, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_access_token(user_id: int) -> str:
    return create_token(str(user_id), "access", timedelta(minutes=settings.access_token_minutes))


def create_refresh_token(user_id: int) -> str:
    return create_token(str(user_id), "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_type: str = "access") -> int:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return int(payload["sub"])


def generate_licence_code(tier: str) -> str:
    prefix = "".join(ch for ch in tier.upper() if ch.isalnum())[:4] or "LIC"
    groups = [secrets.token_hex(2).upper() for _ in range(3)]
    return f"FAST-{prefix}-{'-'.join(groups)}"


def normalise_licence_code(code: str) -> str:
    return code.strip().upper()


def hash_licence_code(code: str) -> str:
    return hashlib.sha256(normalise_licence_code(code).encode("utf-8")).hexdigest()
