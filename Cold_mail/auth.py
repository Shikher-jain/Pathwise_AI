from __future__ import annotations

import hashlib
import hmac
import os
import re

from db import create_user, get_user_by_email

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def init_auth_db() -> None:
    # Schema creation is handled centrally in db.init_db().
    return None


def _hash_password(password: str, salt: bytes | None = None) -> str:
    pwd = password.encode("utf-8")
    salt_bytes = salt if salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pwd, salt_bytes, 120_000)
    return f"{salt_bytes.hex()}${digest.hex()}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split("$", maxsplit=1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    candidate = _hash_password(password, salt=salt)
    return hmac.compare_digest(candidate, f"{salt_hex}${digest_hex}")


def _valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email.strip().lower()))


def register_user(email: str, password: str) -> tuple[bool, str]:
    normalized_email = email.strip().lower()

    if not _valid_email(normalized_email):
        return False, "Enter a valid email address"
    if len(password) < 8:
        return False, "Password must be at least 8 characters"

    password_hash = _hash_password(password)

    ok, message, _ = create_user(normalized_email, password_hash)
    return ok, message


def authenticate_user(email: str, password: str) -> tuple[bool, int | None]:
    normalized_email = email.strip().lower()
    row = get_user_by_email(normalized_email)

    if not row:
        return False, None

    return _verify_password(password, row["password_hash"]), int(row["id"])
