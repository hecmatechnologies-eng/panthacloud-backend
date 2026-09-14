import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger("fussion.secrets")


class SecretStoreError(Exception):
    """Base exception for secret store operations."""


class SecretStore:
    """
    Encryption and storage boundary for sensitive integration credentials.
    Uses AES-128-CBC / HMAC-SHA256 authenticated encryption via Fernet.
    Ensures plaintext credentials never reside in unencrypted database columns.
    """

    def __init__(self, key: str | None = None) -> None:
        self._key = key or settings.effective_secret_encryption_key
        try:
            self._fernet = Fernet(self._key.encode() if isinstance(self._key, str) else self._key)
        except Exception as exc:
            raise SecretStoreError(f"Invalid encryption key configuration: {exc}") from exc

    def encrypt(self, payload: dict[str, Any]) -> str:
        """Encrypt a dictionary of credentials into an opaque ciphertext string."""
        try:
            serialized = json.dumps(payload).encode("utf-8")
            ciphertext_bytes = self._fernet.encrypt(serialized)
            return ciphertext_bytes.decode("utf-8")
        except Exception as exc:
            logger.error("Failed to encrypt secret payload.")
            raise SecretStoreError(f"Encryption failed: {exc}") from exc

    def decrypt(self, ciphertext: str) -> dict[str, Any]:
        """Decrypt an opaque ciphertext string back into credential dictionary."""
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return json.loads(decrypted_bytes.decode("utf-8"))
        except InvalidToken as exc:
            logger.error("Decryption failed: Invalid token or tampered ciphertext.")
            raise SecretStoreError("Decryption failed: Token is invalid or corrupted.") from exc
        except Exception as exc:
            logger.error("Decryption failed unexpectedly.")
            raise SecretStoreError(f"Decryption failed: {exc}") from exc

    def encrypt_text(self, text: str) -> str:
        """Encrypt a plaintext string (e.g. an OAuth access token) into ciphertext."""
        try:
            return self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            logger.error("Failed to encrypt text payload.")
            raise SecretStoreError(f"Encryption failed: {exc}") from exc

    def decrypt_text(self, ciphertext: str) -> str:
        """Decrypt ciphertext back into a plaintext string."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            logger.error("Decryption failed: Invalid token or tampered ciphertext.")
            raise SecretStoreError("Decryption failed: Token is invalid or corrupted.") from exc
        except Exception as exc:
            logger.error("Decryption failed unexpectedly.")
            raise SecretStoreError(f"Decryption failed: {exc}") from exc


# Global default SecretStore instance
secret_store = SecretStore()
