from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_MASTER_KEY_PLACEHOLDER = "replace-with-a-generated-encryption-key"

_fernet: Fernet | None = None


def generate_master_key() -> str:
    """Generate a new Fernet-compatible master key and return it as a string."""
    return Fernet.generate_key().decode()


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance, initializing from settings if needed.

    If the master key is still the default placeholder, a temporary key is
    generated and a warning is logged so the operator knows encrypted data
    will not survive a restart.
    """
    global _fernet
    if _fernet is not None:
        return _fernet

    settings = get_settings()
    master_key = settings.gateway_master_key

    if master_key == _DEFAULT_MASTER_KEY_PLACEHOLDER:
        master_key = generate_master_key()
        logger.warning(
            "GATEWAY_MASTER_KEY is set to the default placeholder. "
            "A temporary key has been generated for this session — encrypted "
            "provider keys will NOT be decryptable after restart. "
            "Set GATEWAY_MASTER_KEY to a persistent value "
            "(call generate_master_key() to obtain one)."
        )

    try:
        _fernet = Fernet(master_key.encode())
    except (ValueError, TypeError) as exc:
        logger.error(
            "GATEWAY_MASTER_KEY is not a valid Fernet key (%s). Falling back to a temporary key.",
            exc,
        )
        master_key = generate_master_key()
        _fernet = Fernet(master_key.encode())

    return _fernet


def encrypt_key(plaintext: str) -> str:
    """Encrypt a plaintext string using the master key.

    Returns a Fernet token as a string suitable for database storage.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    """Decrypt a ciphertext string using the master key.

    Raises ``ValueError`` if the ciphertext is invalid or was encrypted
    with a different master key.
    """
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        logger.error("Failed to decrypt key — ciphertext may be corrupted or encrypted with a different master key.")
        raise ValueError("Decryption failed: invalid ciphertext") from exc
