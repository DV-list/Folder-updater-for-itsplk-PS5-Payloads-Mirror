import tempfile
import unittest
from pathlib import Path

from app.user_config import UserConfig


class UserConfigTests(unittest.TestCase):
    def test_creates_defaults_and_accepts_double_slash_comments(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            config = UserConfig(base)
            self.assertEqual(config.platform_suffix, "win-x64.zip")
            self.assertEqual(config.log_level_name, "INFO")
            self.assertFalse(config.verbose_logging)
            self.assertIn("LOG_LEVEL = 0", (base / "appdata" / "config.ini").read_text(encoding="utf-8"))
            self.assertTrue(config.control_app_enabled)
            self.assertTrue(config.download_only_when_current)
            self.assertIn("// Other values", (base / "appdata" / "config.ini").read_text(encoding="utf-8"))
            self.assertFalse((base / "config.ini").exists())


    def test_log_level_one_enables_verbose_debug_logging(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "appdata").mkdir()
            (base / "appdata" / "config.ini").write_text(
                '[General]\nLOG_LEVEL=1\n[ps5upload-control-app-dl]\nEnabled=true\nPlatform=default\nDownloadOnlyWhenPS5UploadCurrent=true\n',
                encoding="utf-8",
            )
            config = UserConfig(base)
            self.assertEqual(config.log_level_name, "DEBUG")
            self.assertTrue(config.verbose_logging)

    def test_log_level_zero_uses_info_logging(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "appdata").mkdir()
            (base / "appdata" / "config.ini").write_text(
                '[General]\nLOG_LEVEL=0\n[ps5upload-control-app-dl]\nEnabled=true\nPlatform=default\nDownloadOnlyWhenPS5UploadCurrent=true\n',
                encoding="utf-8",
            )
            config = UserConfig(base)
            self.assertEqual(config.log_level_name, "INFO")
            self.assertFalse(config.verbose_logging)

    def test_unquotes_platform_and_respects_debug_level(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "appdata").mkdir()
            (base / "appdata" / "config.ini").write_text(
                '[General]\nLogLevel=DEBUG\n[ps5upload-control-app-dl]\nEnabled=true\nPlatform="mac-arm64.dmg"\nDownloadOnlyWhenPS5UploadCurrent=false\n// comment\n',
                encoding="utf-8",
            )
            config = UserConfig(base)
            self.assertEqual(config.platform_suffix, "mac-arm64.dmg")
            self.assertEqual(config.log_level_name, "DEBUG")
            self.assertFalse(config.download_only_when_current)

    def test_accepts_non_zip_release_asset_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "appdata").mkdir()
            (base / "appdata" / "config.ini").write_text(
                '[General]\nLogLevel=INFO\n[ps5upload-control-app-dl]\nEnabled=true\nPlatform=linux-x64.deb\nDownloadOnlyWhenPS5UploadCurrent=true\n',
                encoding="utf-8",
            )
            self.assertEqual(UserConfig(base).platform_suffix, "linux-x64.deb")

    def test_rejects_unsafe_platform_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "appdata").mkdir()
            (base / "appdata" / "config.ini").write_text(
                '[General]\nLogLevel=INFO\n[ps5upload-control-app-dl]\nEnabled=true\nPlatform=../evil.zip\nDownloadOnlyWhenPS5UploadCurrent=true\n',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                _ = UserConfig(base).platform_suffix


    def test_migrates_v180_config_into_appdata_without_losing_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            legacy = base / "config.ini"
            legacy.write_text(
                '[General]\nLogLevel=DEBUG\n[ps5upload-control-app-dl]\nEnabled=false\nPlatform=mac-arm64.dmg\nDownloadOnlyWhenPS5UploadCurrent=true\n',
                encoding="utf-8",
            )
            config = UserConfig(base)
            self.assertEqual(config.path, base / "appdata" / "config.ini")
            self.assertEqual(config.log_level_name, "DEBUG")
            self.assertFalse(config.control_app_enabled)
            self.assertEqual(config.platform_suffix, "mac-arm64.dmg")
            self.assertTrue((base / "appdata" / "config.ini").is_file())
            self.assertIn("LOG_LEVEL = 1", (base / "appdata" / "config.ini").read_text(encoding="utf-8"))
            self.assertTrue(legacy.is_file())

if __name__ == "__main__":
    unittest.main()
