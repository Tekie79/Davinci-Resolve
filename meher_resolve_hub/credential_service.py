"""Secure credential storage for Resolve Hub.

OpenAI API keys are never written to Resolve Hub settings.json, source files,
MCP arguments, logs, or Git.

macOS:
    Uses the native Security.framework Keychain APIs through ctypes, so Resolve
    Hub does not need a third-party package just to store/retrieve the key.

Other platforms:
    Uses Python keyring when available.

Read priority:
1. Explicit key supplied programmatically.
2. OS credential store.
3. OPENAI_API_KEY environment variable as a compatibility fallback.
"""

from dataclasses import dataclass
import ctypes
import os
import platform


SERVICE_NAME = "Meher Flow Resolve Hub"
OPENAI_ACCOUNT = "openai-api-key"
ELEVENLABS_ACCOUNT = "elevenlabs-api-key"

_ERR_SEC_SUCCESS = 0
_ERR_SEC_DUPLICATE_ITEM = -25299
_ERR_SEC_ITEM_NOT_FOUND = -25300


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


class _MacOSKeychainBackend:
    """Minimal native generic-password wrapper for macOS Keychain."""

    def __init__(self):
        security_path = "/System/Library/Frameworks/Security.framework/Security"
        core_path = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        self.security = ctypes.cdll.LoadLibrary(security_path)
        self.core = ctypes.cdll.LoadLibrary(core_path)
        self._configure()

    def _configure(self):
        c_void_p = ctypes.c_void_p
        c_uint32 = ctypes.c_uint32
        c_char_p = ctypes.c_char_p
        c_int32 = ctypes.c_int32

        self.security.SecKeychainAddGenericPassword.argtypes = [
            c_void_p, c_uint32, c_char_p, c_uint32, c_char_p,
            c_uint32, c_void_p, ctypes.POINTER(c_void_p),
        ]
        self.security.SecKeychainAddGenericPassword.restype = c_int32

        self.security.SecKeychainFindGenericPassword.argtypes = [
            c_void_p, c_uint32, c_char_p, c_uint32, c_char_p,
            ctypes.POINTER(c_uint32), ctypes.POINTER(c_void_p),
            ctypes.POINTER(c_void_p),
        ]
        self.security.SecKeychainFindGenericPassword.restype = c_int32

        self.security.SecKeychainItemModifyAttributesAndData.argtypes = [
            c_void_p, c_void_p, c_uint32, c_void_p,
        ]
        self.security.SecKeychainItemModifyAttributesAndData.restype = c_int32

        self.security.SecKeychainItemDelete.argtypes = [c_void_p]
        self.security.SecKeychainItemDelete.restype = c_int32

        self.security.SecKeychainItemFreeContent.argtypes = [c_void_p, c_void_p]
        self.security.SecKeychainItemFreeContent.restype = c_int32

        self.core.CFRelease.argtypes = [c_void_p]
        self.core.CFRelease.restype = None

    @staticmethod
    def _bytes(value):
        return str(value).encode("utf-8")

    def _find(self, service, account):
        service_b = self._bytes(service)
        account_b = self._bytes(account)
        length = ctypes.c_uint32(0)
        data = ctypes.c_void_p()
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(service_b), service_b,
            len(account_b), account_b,
            ctypes.byref(length), ctypes.byref(data), ctypes.byref(item),
        )
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return status, "", None
        if status != _ERR_SEC_SUCCESS:
            raise RuntimeError("macOS Keychain lookup failed (OSStatus %s)." % status)
        try:
            raw = ctypes.string_at(data, length.value) if data else b""
            secret = raw.decode("utf-8")
        finally:
            if data:
                self.security.SecKeychainItemFreeContent(None, data)
        return status, secret, item

    def get(self, service, account):
        status, secret, item = self._find(service, account)
        if item:
            self.core.CFRelease(item)
        return secret if status == _ERR_SEC_SUCCESS else ""

    def set(self, service, account, secret):
        service_b = self._bytes(service)
        account_b = self._bytes(account)
        secret_b = self._bytes(secret)
        item = ctypes.c_void_p()
        status = self.security.SecKeychainAddGenericPassword(
            None,
            len(service_b), service_b,
            len(account_b), account_b,
            len(secret_b), ctypes.c_char_p(secret_b),
            ctypes.byref(item),
        )
        if status == _ERR_SEC_SUCCESS:
            if item:
                self.core.CFRelease(item)
            return

        if status != _ERR_SEC_DUPLICATE_ITEM:
            raise RuntimeError("macOS Keychain save failed (OSStatus %s)." % status)

        _, _, existing = self._find(service, account)
        if not existing:
            raise RuntimeError("macOS Keychain item exists but could not be reopened.")
        try:
            status = self.security.SecKeychainItemModifyAttributesAndData(
                existing, None, len(secret_b), ctypes.c_char_p(secret_b)
            )
            if status != _ERR_SEC_SUCCESS:
                raise RuntimeError(
                    "macOS Keychain update failed (OSStatus %s)." % status
                )
        finally:
            self.core.CFRelease(existing)

    def delete(self, service, account):
        status, _, item = self._find(service, account)
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return
        if not item:
            return
        try:
            status = self.security.SecKeychainItemDelete(item)
            if status not in (_ERR_SEC_SUCCESS, _ERR_SEC_ITEM_NOT_FOUND):
                raise RuntimeError(
                    "macOS Keychain delete failed (OSStatus %s)." % status
                )
        finally:
            self.core.CFRelease(item)


class _PythonKeyringBackend:
    def __init__(self):
        import keyring
        self.keyring = keyring

    def get(self, service, account):
        return str(self.keyring.get_password(service, account) or "")

    def set(self, service, account, secret):
        self.keyring.set_password(service, account, secret)

    def delete(self, service, account):
        try:
            self.keyring.delete_password(service, account)
        except Exception:
            if self.get(service, account):
                raise

    def name(self):
        try:
            backend = self.keyring.get_keyring()
            return "%s.%s" % (
                backend.__class__.__module__,
                backend.__class__.__name__,
            )
        except Exception:
            return "python-keyring"


class OpenAICredentialStore:
    """Secure OpenAI API-key storage backed by the operating system."""

    def __init__(
        self,
        service_name=SERVICE_NAME,
        account=OPENAI_ACCOUNT,
        provider_name="OpenAI",
        environment_variable="OPENAI_API_KEY",
    ):
        self.service_name = str(service_name)
        self.account = str(account)
        self.provider_name = str(provider_name)
        self.environment_variable = str(environment_variable)
        self._backend = None
        self._backend_name = ""
        self._backend_error = ""
        self._load_backend()

    def _load_backend(self):
        if platform.system() == "Darwin":
            try:
                self._backend = _MacOSKeychainBackend()
                self._backend_name = "macOS Keychain"
                return
            except Exception as exc:
                self._backend_error = str(exc)

        try:
            self._backend = _PythonKeyringBackend()
            self._backend_name = self._backend.name()
        except Exception as exc:
            if not self._backend_error:
                self._backend_error = str(exc)

    def backend_name(self):
        return self._backend_name

    def get_key(self):
        if self._backend is None:
            return ""
        try:
            return self._backend.get(self.service_name, self.account)
        except Exception:
            return ""

    def set_key(self, value):
        secret = str(value or "").strip()
        if not secret:
            raise ValueError("%s API key cannot be empty." % getattr(self, "provider_name", "OpenAI"))
        if self._backend is None:
            raise RuntimeError(
                "Secure credential storage is unavailable: %s"
                % (self._backend_error or "no supported backend")
            )
        self._backend.set(self.service_name, self.account, secret)
        if self.get_key() != secret:
            raise RuntimeError(
                "The credential store did not return the key that was just saved."
            )
        return self.status()

    def delete_key(self):
        if self._backend is None:
            raise RuntimeError(
                "Secure credential storage is unavailable: %s"
                % (self._backend_error or "no supported backend")
            )
        self._backend.delete(self.service_name, self.account)
        return self.status()

    def status(self):
        env_name = getattr(self, "environment_variable", "OPENAI_API_KEY")
        env = str(os.environ.get(env_name, "") or "")
        value = self.get_key()
        if self._backend is None:
            return CredentialStatus(
                available=False,
                configured=bool(env),
                backend="environment" if env else "",
                masked=_mask(env),
                reason=(
                    "%s is available from the environment." % env_name
                    if env else
                    "No secure OS credential backend is available."
                ),
            )
        return CredentialStatus(
            available=True,
            configured=bool(value) or bool(env),
            backend=self._backend_name if value else ("environment" if env else self._backend_name),
            masked=_mask(value or env),
            reason="",
        )


class ElevenLabsCredentialStore(OpenAICredentialStore):
    """Secure ElevenLabs API-key storage backed by the operating system."""

    def __init__(self, service_name=SERVICE_NAME, account=ELEVENLABS_ACCOUNT):
        super().__init__(
            service_name=service_name,
            account=account,
            provider_name="ElevenLabs",
            environment_variable="ELEVENLABS_API_KEY",
        )


def resolve_openai_api_key(explicit_key=None, credential_store=None):
    """Resolve a key without persisting, returning, or logging it elsewhere."""
    explicit = str(explicit_key or "").strip()
    if explicit:
        return explicit

    store = credential_store or OpenAICredentialStore()
    secure_value = store.get_key()
    if secure_value:
        return secure_value

    return str(os.environ.get("OPENAI_API_KEY", "") or "").strip()


def resolve_elevenlabs_api_key(explicit_key=None, credential_store=None):
    """Resolve ElevenLabs key without persisting or logging it elsewhere."""
    explicit = str(explicit_key or "").strip()
    if explicit:
        return explicit

    store = credential_store or ElevenLabsCredentialStore()
    secure_value = store.get_key()
    if secure_value:
        return secure_value

    return str(os.environ.get("ELEVENLABS_API_KEY", "") or "").strip()


def test_elevenlabs_connection(explicit_key=None, credential_store=None):
    """Verify ElevenLabs authentication using the user endpoint."""
    key = resolve_elevenlabs_api_key(explicit_key, credential_store)
    if not key:
        return False, "No ElevenLabs API key is configured."

    try:
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        request = Request(
            "https://api.elevenlabs.io/v1/user",
            headers={
                "xi-api-key": key,
                "User-Agent": "Meher-Flow-Resolve-Hub",
            },
            method="GET",
        )
        with urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", 200) or 200)
        if 200 <= status < 300:
            return True, "ElevenLabs connection verified."
        return False, "ElevenLabs connection test returned HTTP %s." % status
    except HTTPError as exc:
        return False, "ElevenLabs connection test returned HTTP %s." % exc.code
    except Exception as exc:
        text = str(exc or "ElevenLabs connection test failed.")
        if key and key in text:
            text = text.replace(key, "[REDACTED]")
        return False, "ElevenLabs connection test failed: %s" % text


def credential_store_label():
    if platform.system() == "Darwin":
        return "macOS Keychain"
    if platform.system() == "Windows":
        return "Windows Credential Manager / OS keyring"
    return "OS credential store"


def test_openai_connection(explicit_key=None, credential_store=None, model="gpt-4o-transcribe-diarize"):
    """Verify authentication with the models endpoint using only stdlib HTTP."""
    key = resolve_openai_api_key(explicit_key, credential_store)
    if not key:
        return False, "No OpenAI API key is configured."

    try:
        from urllib.parse import quote
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        url = "https://api.openai.com/v1/models/%s" % quote(str(model), safe="")
        request = Request(
            url,
            headers={
                "Authorization": "Bearer " + key,
                "User-Agent": "Meher-Flow-Resolve-Hub",
            },
            method="GET",
        )
        with urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", 200) or 200)
        if 200 <= status < 300:
            return True, "OpenAI connection verified."
        return False, "OpenAI connection test returned HTTP %s." % status
    except HTTPError as exc:
        return False, "OpenAI connection test returned HTTP %s." % exc.code
    except Exception as exc:
        text = str(exc or "OpenAI connection test failed.")
        if key and key in text:
            text = text.replace(key, "[REDACTED]")
        return False, "OpenAI connection test failed: %s" % text
