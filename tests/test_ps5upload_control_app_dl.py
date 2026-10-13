import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.models import PayloadEntry, StateRecord
from app.ps5upload_control_app_dl import ControlAppDownloadError, Ps5uploadControlAppDL
from app.state_repository import StateRepository
from app.user_config import UserConfig


class Ps5uploadControlAppDLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = StateRepository(self.base / "appdata" / "local-state.json")
        self.config = UserConfig(self.base)
        self.module = Ps5uploadControlAppDL(self.base, self.repo, self.config)
        self.entry = PayloadEntry(
            payload="ps5upload", filename="ps5upload.elf", version="1.2.3",
            checksum="a" * 64, source_direct="https://example.test/releases/ps5upload.elf",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_default_platform_derives_windows_zip_asset(self):
        self.assertEqual(self.module.derived_names(self.entry), (
            "https://example.test/releases/ps5upload-win-x64.zip", "ps5upload-win-x64.zip"
        ))

    def test_explicit_platform_suffix_includes_asset_extension(self):
        path = self.base / "appdata" / "config.ini"
        path.write_text('[General]\nLogLevel=INFO\n[ps5upload-control-app-dl]\nEnabled=true\nPlatform="mac-arm64.dmg"\nDownloadOnlyWhenPS5UploadCurrent=true\n', encoding="utf-8")
        config = UserConfig(self.base)
        module = Ps5uploadControlAppDL(self.base, self.repo, config)
        self.assertEqual(module.derived_names(self.entry), (
            "https://example.test/releases/ps5upload-mac-arm64.dmg", "ps5upload-mac-arm64.dmg"
        ))

    def test_discovery_resolves_target_without_downloading_or_creating_missing_state(self):
        description = self.module.describe_client([self.entry])
        self.assertEqual(description[3], "ps5upload-win-x64")
        self.assertFalse((self.base / "ps5upload-win-x64").exists())
        self.assertIsNone(self.module.discover_existing_client([self.entry]))
        self.assertEqual(self.repo.load(), [])

    def test_discovery_tracks_an_already_existing_target_without_downloading(self):
        (self.base / "ps5upload-win-x64").mkdir()
        record = self.module.discover_existing_client([self.entry])
        self.assertIsNotNone(record)
        self.assertEqual(record.curr_dir_filename, "ps5upload-win-x64")
        self.assertEqual(record.curr_checksum, "")
        self.assertEqual(len(self.repo.load()), 1)

    def test_versioned_manual_folder_overrides_stale_control_app_state(self):
        folder_name = "PS5Upload-7.0.22-win-x64"
        (self.base / folder_name).mkdir()
        old = StateRecord(
            payload=folder_name,
            curr_dir_filename=folder_name,
            curr_dir_file_version="7.0.1",
            curr_checksum="f" * 64,
            first_seen="2026-01-01 00:00:00",
            last_seen="2026-01-02 00:00:00",
            record_type="control-app",
        )
        self.repo.save([old])

        record = self.module.discover_existing_client([self.entry])

        self.assertIsNotNone(record)
        self.assertEqual(record.curr_dir_filename, folder_name)
        self.assertEqual(record.curr_dir_file_version, "7.0.22")
        self.assertEqual(record.curr_checksum, "f" * 64)
        stored = next(item for item in self.repo.load() if item.record_type == "control-app")
        self.assertEqual(stored.curr_dir_file_version, "7.0.22")

    def test_zip_download_hashes_archive_extracts_then_deletes_archive(self):
        archive = self.base / "source.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("PS5Upload.exe", b"client")
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        def fake_download(url, filename):
            target = self.base / "download-temp.zip"
            target.write_bytes(archive.read_bytes())
            return target, checksum
        with patch.object(self.module, "_download_asset", side_effect=fake_download):
            self.module.ensure_client([self.entry])
        self.assertEqual((self.base / "ps5upload-win-x64" / "PS5Upload.exe").read_bytes(), b"client")
        self.assertFalse((self.base / "download-temp.zip").exists())
        record = next(r for r in self.repo.load() if r.record_type == "control-app")
        self.assertEqual(record.curr_dir_filename, "ps5upload-win-x64")
        self.assertEqual(record.payload, "ps5upload-win-x64")
        self.assertEqual(record.curr_checksum, checksum)

    def test_successful_update_archives_obsolete_control_app_folder(self):
        target = self.base / "ps5upload-win-x64"
        target.mkdir()
        (target / "PS5Upload.exe").write_bytes(b"old-client")
        first_seen = "2026-01-01 00:00:00"
        self.repo.save([StateRecord(
            "ps5upload-win-x64", target.name, "1.0.0", "f" * 64,
            first_seen, first_seen, record_type="control-app",
        )])

        archive_source = self.base / "source.zip"
        with zipfile.ZipFile(archive_source, "w") as zf:
            zf.writestr("PS5Upload.exe", b"new-client")
        checksum = hashlib.sha256(archive_source.read_bytes()).hexdigest()

        def fake_download(url, filename):
            downloaded = self.base / "download-temp.zip"
            downloaded.write_bytes(archive_source.read_bytes())
            return downloaded, checksum

        with patch.object(self.module, "_download_asset", side_effect=fake_download):
            self.module.ensure_client([self.entry])

        self.assertEqual((target / "PS5Upload.exe").read_bytes(), b"new-client")
        archived = self.base / "_OLD" / "ps5upload-win-x64"
        self.assertEqual((archived / "PS5Upload.exe").read_bytes(), b"old-client")
        record = next(r for r in self.repo.load() if r.record_type == "control-app")
        self.assertEqual(record.curr_dir_file_version, "1.2.3")
        self.assertEqual(record.curr_checksum, checksum)
        self.assertFalse((self.base / "download-temp.zip").exists())

    def test_dmg_asset_is_kept_and_checksum_is_recorded(self):
        (self.base / "appdata" / "config.ini").write_text('[General]\nLogLevel=INFO\n[ps5upload-control-app-dl]\nEnabled=true\nPlatform=mac-arm64.dmg\nDownloadOnlyWhenPS5UploadCurrent=true\n', encoding="utf-8")
        config = UserConfig(self.base)
        module = Ps5uploadControlAppDL(self.base, self.repo, config)
        asset = self.base / "download.dmg"
        asset.write_bytes(b"disk image")
        checksum = hashlib.sha256(asset.read_bytes()).hexdigest()
        with patch.object(module, "_download_asset", return_value=(asset, checksum)):
            module.ensure_client([self.entry])
        target = self.base / "ps5upload-mac-arm64.dmg"
        self.assertEqual(target.read_bytes(), b"disk image")
        self.assertFalse(asset.exists())
        record = next(r for r in self.repo.load() if r.record_type == "control-app")
        self.assertEqual(record.curr_dir_filename, target.name)
        self.assertEqual(record.payload, target.name)
        self.assertEqual(record.curr_checksum, checksum)

    def test_existing_directory_preserves_checksum_and_first_seen(self):
        (self.base / "ps5upload-win-x64").mkdir()
        first_seen = "2026-01-01 00:00:00"
        self.repo.save([StateRecord("ps5upload-PC_client", "ps5upload-win-x64", "1.2.3", "f"*64, first_seen, first_seen, record_type="control-app")])
        self.module.ensure_client([self.entry])
        record = self.repo.load()[0]
        self.assertEqual(record.curr_checksum, "f"*64)
        self.assertEqual(record.first_seen, first_seen)
        self.assertNotEqual(record.last_seen, first_seen)

    def test_failed_zip_extraction_retains_complete_archive_and_no_state(self):
        archive = self.base / "download-temp.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../evil.exe", b"bad")
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with patch.object(self.module, "_download_asset", return_value=(archive, checksum)):
            with self.assertRaises(ControlAppDownloadError):
                self.module.ensure_client([self.entry])
        self.assertTrue(archive.exists())
        self.assertFalse((self.base / "ps5upload-win-x64").exists())
        self.assertEqual(self.repo.load(), [])

    def test_rejects_non_https_redirect_target(self):
        with self.assertRaises(ControlAppDownloadError):
            self.module._validate_url("http://example.test/file.zip")


if __name__ == "__main__":
    unittest.main()
