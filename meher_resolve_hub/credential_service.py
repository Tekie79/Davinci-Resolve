"""Secure credential storage for Resolve Hub.

OpenAI API keys are never written to Resolve Hub settings.json or source files.

Storage priority:
1. Explicit key supplied to a caller.
2. OS credential store via Python keyring (macOS Keychain on macOS).
3. OPENAI_API_KEY environment variable as a compatibility fallback.

The Resolve UI saves/removes the key only through this service.
"""

from dataclasses import dataclass
import os
import platform


SERVICE_NAME = "Meher Flow Resolve Hub"
OPENAI_ACCOUNT = "openai-api-key"


@dataclass(frozen=True)
class CredentialStatus:
    available: bool
    configured: bool
    backend: str
    masked: str = ""
    reason: str = ""


def _mask(secret):
    value = str(secret or "")
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return "•" * max(8, len(value) - 4) + value[-4:]


class OpenAICredentialStore:
    """Store the OpenAI key in the OS credential store through keyring."""

    def __init__(self, service_name=SERVICE_NAME, account=OPENAI_ACCOUNT):
        self.service_name = str(service_name)
        self.account = str(account)

    @staticmethod
    def _keyring():
        try:
            import keyring
            return keyring
        except Exception:
            return None

    def backend_name(self):
        keyring = self._keyring()
        if keyring is None:
            return ""
        try:
            backend = keyring.get_keyring()
            name = backend.__class__.__name__
            module = backend.__class__.__module__
            return ("%s.%s" % (module, name)).strip(".")
        except Exception:
            return "keyring"

    def get_key(self):
        keyring = self._keyring()
        if keyring is None:
            return ""
        try:
            return str(
                keyring.get_password(self.service_name, self.account) or ""
            )
        except Exception:
            return ""

    def set_key(self, value):
        secret = str(value or "").strip()
        if not secret:
            raise ValueError("OpenAI API key cannot be empty.")
        keyring = self._keyring()
        if keyring is None:
            raise RuntimeError(
                "Secure credential storage is unavailable. Install the Python "
                "keyring package in the runtime that launches Resolve Hub."
            )
        try:
            keyring.set_password(self.service_name, self.account, secret)
        except Exception as exc:
            raise RuntimeError(
                "Could not save the OpenAI API key to the OS credential store: %s"
                % exc
            )
        stored = self.get_key()
        if stored != secret:
            raise RuntimeError(
                "The credential store did not return the key that was just saved."
            )
        return self.status()

    def delete_key(self):
        keyring = self._keyring()
        if keyring is None:
            raise RuntimeError(
                "Secure credential storage is unavailable. Install the Python "
                "keyring package first."
            )
        try:
            keyring.delete_password(self.service_name, self.account)
        except Exception as exc:
            # keyring backends raise different errors when an item is absent.
            if not self.get_key():
                return self.status()
            raise RuntimeError(
                "Could not remove the OpenAI API key from the OS credential store: %s"
                % exc
            )
        return self.status()

    def status(self):
        keyring = self._keyring()
        if keyring is None:
            env = str(os.environ.get("OPENAI_API_KEY", "") or "")
            return CredentialStatus(
                available=False,
                configured=bool(env),
                backend="environment" if env else "",
                masked=_mask(env),
                reason=(
                    "Python keyring is not installed. OPENAI_API_KEY is available "
                    "from the environment."
                    if env else
                    "Install Python keyring to save the key securely."
                ),
            )
        value = self.get_key()
        return CredentialStatus(
            available=True,
            configured=bool(value),
            backend=self.backend_name(),
            masked=_mask(value),
            reason="",
        )


def resolve_openai_api_key(explicit_key=None, credential_store=None):
    """Resolve a key without persisting or logging it."""
    explicit = str(explicit_key or "").strip()
    if explicit:
        return explicit

    store = credential_store or OpenAICredentialStore()
    keychain_value = store.get_key()
    if keychain_value:
        return keychain_value

    return str(os.environ.get("OPENAI_API_KEY", "") or "").strip()


def credential_store_label():
    if platform.system() == "Darwin":
        return "macOS Keychain"
    if platform.system() == "Windows":
        return "Windows Credential Manager / keyring backend"
    return "OS credential store / keyring backend"


def test_openai_connection(explicit_key=None, credential_store=None, model="gpt-4o-transcribe-diarize"):
    """Verify that the configured key can authenticate without exposing it."""
    key = resolve_openai_api_key(explicit_key, credential_store)
    if not key:
        return False, "No OpenAI API key is configured."
    try:
        from openai import OpenAI
    except Exception:
        return False, "The OpenAI Python package is not installed in this runtime."

    try:
        client = OpenAI(api_key=key)
        client.models.retrieve(str(model))
        return True, "OpenAI connection verified."
    except Exception as exc:
        text = str(exc or "OpenAI connection test failed.")
        # Never echo a key if an SDK/backend unexpectedly embeds it in an error.
        if key and key in text:
            text = text.replace(key, "[REDACTED]")
        return False, "OpenAI connection test failed: %s" % text
