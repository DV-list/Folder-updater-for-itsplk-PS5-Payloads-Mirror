import json
import unittest
from unittest.mock import patch

from app.payload_catalog import PayloadCatalog, PayloadCatalogError
from app.version import APP_VERSION


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


class PayloadCatalogSchemaTests(unittest.TestCase):
    def setUp(self):
        self.entry = {
            "name": "example",
            "filename": "example.elf",
            "version": "1.2.3",
            "checksum": "a" * 64,
            "source_direct": "https://example.com/example.elf",
        }

    def _fetch(self, document):
        response = _Response(json.dumps(document).encode("utf-8"))
        with patch("app.payload_catalog.urlopen", return_value=response):
            return PayloadCatalog("https://example.com/payloads.json").fetch()

    def test_user_agent_tracks_application_version(self):
        catalog = PayloadCatalog("https://example.com/payloads.json")
        self.assertEqual(catalog.USER_AGENT, f"Folder-updater/{APP_VERSION}")

    def test_accepts_new_object_with_payloads_array(self):
        result = self._fetch({
            "name": "PS5 Payloads",
            "icons_url": "icons.json",
            "payloads": [self.entry],
        })
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].payload, "example")
        self.assertEqual(result[0].filename, "example.elf")

    def test_keeps_compatibility_with_legacy_array(self):
        result = self._fetch([self.entry])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].payload, "example")

    def test_rejects_object_without_payloads_array(self):
        with self.assertRaisesRegex(PayloadCatalogError, "payloads.*array"):
            self._fetch({"name": "PS5 Payloads", "payloads": {}})


if __name__ == "__main__":
    unittest.main()
