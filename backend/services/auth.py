import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash


# Password hashing using Argon2
password_hash = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = password_hash.hash(
    "nexa-login-timing-placeholder-not-a-real-password"
)


# JWT configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
if (
    len(JWT_SECRET_KEY.encode("utf-8")) < 32
    or JWT_SECRET_KEY.lower().startswith(("replace_", "changeme", "change_me"))
):
    raise RuntimeError(
        "JWT_SECRET_KEY must be replaced with a unique secret of at least 32 bytes."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def hash_password(password: str) -> str:
    """Securely hash a user's password."""
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    """Verify a password against its stored hash."""
    return password_hash.verify(
        plain_password,
        hashed_password
    )


def create_access_token(user_id: int) -> str:
    """Generate a JWT access token."""

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "exp": expires_at
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""

    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM]
    )