"""Gemini secrets belong only in a trusted OS credential service."""
import os
from .deployment import is_cloud

SERVICE = "InduAI.Gemini"
ACCOUNT = "personal-api-key"


def credential_backend():
    if is_cloud():
        raise RuntimeError("Cloud credentials are configured with GEMINI_API_KEY in the server environment.")
    if os.environ.get("INDU_DISABLE_CREDENTIAL_STORE") == "1":
        raise RuntimeError("Credential storage is disabled in this instance.")
    try:
        import keyring
        backend = keyring.get_keyring()
        # Fail closed for plaintext, third-party file and null backends.
        if type(backend).__module__ not in {
            "keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService",
        }:
            raise RuntimeError("No supported OS credential store is available.")
        return backend
    except ImportError:
        raise RuntimeError("Install keyring to enable secure API key setup.") from None


def load_key():
    try:
        return credential_backend().get_password(SERVICE, ACCOUNT)
    except Exception:
        return None


def save_key(value):
    try:
        credential_backend().set_password(SERVICE, ACCOUNT, value)
    except Exception:
        raise RuntimeError("The OS credential store could not save the key. No plaintext fallback was used.") from None


def delete_key():
    try:
        backend = credential_backend()
        if backend.get_password(SERVICE, ACCOUNT):
            backend.delete_password(SERVICE, ACCOUNT)
    except Exception:
        raise RuntimeError("The OS credential store could not remove the key.") from None
