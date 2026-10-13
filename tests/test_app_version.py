import unittest
from pathlib import Path

from app.config import AppConfig


class AppVersionTests(unittest.TestCase):
    def test_current_version_is_used_for_window_title(self):
        self.assertEqual(AppConfig.APP_VERSION, "1.9.7")
        self.assertEqual(
            AppConfig.WINDOW_TITLE,
            "Folder updater for itsplk PS5 Payloads Mirror v1.9.7",
        )

    def test_build_name_uses_current_version(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn('v1.9.7', (root / "build.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
