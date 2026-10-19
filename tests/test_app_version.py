import unittest
from pathlib import Path

from app.config import AppConfig
from app.version import APP_VERSION


class AppVersionTests(unittest.TestCase):
    def test_current_version_is_used_for_window_title(self):
        self.assertEqual(APP_VERSION, "1.9.13")
        self.assertEqual(AppConfig.APP_VERSION, APP_VERSION)
        self.assertEqual(
            AppConfig.WINDOW_TITLE,
            f"Folder updater for itsplk PS5 Payloads Mirror v{APP_VERSION}",
        )

    def test_build_name_uses_current_version(self):
        root = Path(__file__).resolve().parents[1]
        build_command = (root / "build.txt").read_text(encoding="utf-8")
        self.assertIn("from app.version import APP_VERSION", build_command)
        self.assertIn('v$APP_VERSION', build_command)


if __name__ == "__main__":
    unittest.main()
