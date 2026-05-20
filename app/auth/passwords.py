"""scrypt-based password hashing using stdlib only.

Stored format: ``"<salt_hex>:<hash_hex>"`` (no algorithm prefix; scrypt
parameters are constants in this module). Empty/malformed stored values
are fail-closed: ``verify_password`` returns ``False`` rather than
raising. Verification is constant-time via ``hmac.compare_digest``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024


def _derive(plaintext: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        plaintext.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )


def hash_password(plaintext: str) -> str:
    if not plaintext:
        raise ValueError("plaintext password must be non-empty")
    salt = secrets.token_bytes(SALT_BYTES)
    derived = _derive(plaintext, salt)
    return f"{salt.hex()}:{derived.hex()}"


def verify_password(plaintext: str, stored: str) -> bool:
    if not stored or ":" not in stored:
        return False
    salt_hex, hash_hex = stored.split(":", 1)
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    if not plaintext:
        return False
    try:
        computed = _derive(plaintext, salt)
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(computed, expected)
