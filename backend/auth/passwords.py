"""
Password Hashing & Constant-Time Verification (C2)
==================================================
Uses Python stdlib hashlib.scrypt + hmac.compare_digest (no native C compiler needed).
Stored format: scrypt$16384$8$1$<salt_b64>$<hash_b64>
"""

import os
import hmac
import base64
import hashlib

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
MAX_SCRYPT_MEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=MAX_SCRYPT_MEM,
        dklen=SCRYPT_DKLEN,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    hash_b64 = base64.urlsafe_b64encode(derived).decode("ascii")
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt_b64}${hash_b64}"


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or not password or not isinstance(encoded, str):
        return False
    try:
        parts = encoded.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = base64.urlsafe_b64decode(parts[4].encode("ascii"))
        expected = base64.urlsafe_b64decode(parts[5].encode("ascii"))
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            maxmem=MAX_SCRYPT_MEM,
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


# Used to equalize timing when a login targets an unknown username or passwordless service account.
_DUMMY_HASH = hash_password("EloneDummyConstantTimePad_2026!")


def verify_dummy_password(password: str) -> bool:
    verify_password(password or "invalid", _DUMMY_HASH)
    return False


__all__ = [
    "hash_password",
    "verify_password",
    "verify_dummy_password",
]

