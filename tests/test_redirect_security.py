import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ps5upload_control_app_dl import ControlAppDownloadError, Ps5uploadControlAppDL
from app.state_repository import StateRepository
from app.updater import UpdateError, UpdateManager
from app.user_config import UserConfig


def resolved_to(address):
    return [(None, None, None, None, (address, 443))]


class RedirectSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.updater = UpdateManager(self.base)
        self.module = Ps5uploadControlAppDL(
            self.base, StateRepository(self.base / "state.json"), UserConfig(self.base)
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_github_release_redirect_sinkhole_is_allowed_with_tls_still_required(self):
        with patch("app.updater.socket.getaddrinfo", return_value=resolved_to("10.0.0.8")):
            self.updater._validate_source_url("https://release-assets.githubusercontent.com/file.zip")
        with patch("app.ps5upload_control_app_dl.socket.getaddrinfo", return_value=resolved_to("10.0.0.8")):
            self.module._validate_url("https://objects.githubusercontent.com/file.zip")

    def test_arbitrary_host_resolving_private_remains_blocked(self):
        with patch("app.updater.socket.getaddrinfo", return_value=resolved_to("10.0.0.8")):
            with self.assertRaises(UpdateError):
                self.updater._validate_source_url("https://example.test/file.elf")
        with patch("app.ps5upload_control_app_dl.socket.getaddrinfo", return_value=resolved_to("10.0.0.8")):
            with self.assertRaises(ControlAppDownloadError):
                self.module._validate_url("https://example.test/file.zip")

    def test_http_redirect_target_is_rejected(self):
        with self.assertRaises(UpdateError):
            self.updater._validate_source_url("http://github.com/file.zip")
        with self.assertRaises(ControlAppDownloadError):
            self.module._validate_url("http://github.com/file.zip")


if __name__ == "__main__":
    unittest.main()
