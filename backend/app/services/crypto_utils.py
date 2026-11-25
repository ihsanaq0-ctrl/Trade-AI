"""
Symmetric encryption helper for sensitive broker credentials at rest.
Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from server secrets.
Transparently handles legacy plaintext values for seamless backward compatibility.
"""

import base64
import hashlib
import logging
from app.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"


def _get_fernet():
    from cryptography.fernet import Fernet
    seed = (
        settings.encryption_key
        or settings.supabase_jwt_secret
        or settings.supabase_service_key
        or "tradeai-fallback-local-key"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string for database storage."""
    if not plaintext:
        return ""
    if plaintext.startswith(_PREFIX):
        return plaintext
    try:
        token = _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"{_PREFIX}{token}"
    except Exception as e:
        logger.warning(f"Encryption fallback triggered: {e}")
        return plaintext


def decrypt_secret(stored: str) -> str:
    """Decrypt a stored secret, gracefully returning legacy plaintext if unencrypted."""
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        return stored
    try:
        token = stored[len(_PREFIX):].encode("utf-8")
        return _get_fernet().decrypt(token).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to decrypt stored credential: {e}")
        return ""
