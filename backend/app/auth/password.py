"""Password hashing and verification using bcrypt.

Uses passlib's bcrypt handler with 12 rounds (OWASP recommended minimum).
"""
from __future__ import annotations

import warnings

from passlib.context import CryptContext

# Suppress passlib's spurious "__about__" warning with bcrypt 4.x.
# passlib 1.7 looks for bcrypt.__about__.__version__ which was removed in bcrypt 4.x.
# The hashing functionality itself is not affected.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*error reading bcrypt version.*")
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        plain: The raw password string from the user.

    Returns:
        A bcrypt hash string safe to store in the database.
    """
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash.

    Args:
        plain: The raw password string to verify.
        hashed: The stored bcrypt hash from the database.

    Returns:
        True if the password matches, False otherwise.
    """
    return _pwd_context.verify(plain, hashed)
