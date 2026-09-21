import os
import unittest
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.credential_service import (
    OpenAICredentialStore,
    _mask,
    resolve_openai_api_key,
)


class FakeBackend:
    def __init__(self):
        self.value = ""

    def get(self, service, account):
        return self.value

    def set(self, service, account, secret):
        self.value = secret

    def delete(self, service, account):
        self.value = ""


class CredentialServiceTests(unittest.TestCase):
    def store(self):
        store = OpenAICredentialStore.__new__(OpenAICredentialStore)
        store.service_name = "test-service"
        store.account = "test-account"
        store._backend = FakeBackend()
        store._backend_name = "fake-keychain"
        store._backend_error = ""
        return store

    def test_store_round_trip_and_delete(self):
        store = self.store()
        store.set_key("sk-test-secret")
        self.assertEqual(store.get_key(), "sk-test-secret")
        status = store.status()
        self.assertTrue(status.configured)
        self.assertNotIn("sk-test-secret", status.masked)
        store.delete_key()
        self.assertEqual(store.get_key(), "")

    def test_explicit_key_has_priority(self):
        store = self.store()
        store.set_key("stored")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env"}, clear=False):
            self.assertEqual(resolve_openai_api_key("explicit", store), "explicit")

    def test_secure_store_precedes_environment(self):
        store = self.store()
        store.set_key("stored")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env"}, clear=False):
            self.assertEqual(resolve_openai_api_key(None, store), "stored")

    def test_environment_is_fallback(self):
        store = self.store()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env"}, clear=False):
            self.assertEqual(resolve_openai_api_key(None, store), "env")

    def test_mask_shows_only_tail(self):
        masked = _mask("sk-1234567890abcd")
        self.assertTrue(masked.endswith("abcd"))
        self.assertNotIn("1234567890", masked)


if __name__ == "__main__":
    unittest.main()
