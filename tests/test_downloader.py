import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from app.downloader import Downloader
from app.models import PayloadEntry, RowResult, ScanResult
from app.discovery import discover_missing_payloads
from app.updater import UpdateError, UpdateManager


class FakeTransfer:
    def __init__(self, base_dir: Path, content: bytes):
        self.base_dir = base_dir
        self.content = content
        self.download_calls = 0

    def _validate_source_url(self, url):
        if not url.startswith("https://"):
            raise UpdateError("source_direct must use HTTPS")

    def _download_to_temp(self, url):
        self.download_calls += 1
        path = self.base_dir / "fake-download.download"
        path.write_bytes(self.content)
        return path

    def _prepare_verified_payload(self, downloaded_path, entry):
        return downloaded_path

    @staticmethod
    def _sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()


class DownloaderTests(unittest.TestCase):
    def test_filename_from_url_preserves_server_elf_name_and_ignores_query(self):
        name = Downloader.filename_from_url(
            "https://downloads.example/release/ServerName%20v2.elf?download=1"
        )
        self.assertEqual(name, "ServerName v2.elf")

    def test_archive_entry_uses_declared_elf_member_filename(self):
        entry = PayloadEntry("Example", "mirror-name.elf", "1.0", "0" * 64,
                             "https://example.test/release/archive.zip", "folder/ServerName.elf")
        self.assertEqual(
            Downloader.filename_from_url(entry.source_direct, entry), "ServerName.elf"
        )

    def test_download_installs_url_named_file_after_checksum_verification(self):
        content = b"verified ELF payload"
        checksum = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            transfer = FakeTransfer(base, content)
            downloader = Downloader(base, transfer)
            entry = PayloadEntry(
                "Example", "catalog-name.elf", "1.0", checksum,
                "https://downloads.example/path/ServerName.elf?raw=1"
            )
            filename, actual = downloader.download(entry)
            self.assertEqual(filename, "ServerName.elf")
            self.assertEqual(actual, checksum)
            self.assertEqual((base / filename).read_bytes(), content)
            self.assertFalse((base / "fake-download.download").exists())

    def test_archive_source_extracts_and_preserves_server_elf_member_name(self):
        content = b"verified archive ELF"
        checksum = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "source.download"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("nested/ServerName.elf", content)
            transfer = UpdateManager(base)
            transfer._validate_source_url = lambda _url: None
            transfer._download_to_temp = lambda _url: archive_path
            downloader = Downloader(base, transfer)
            entry = PayloadEntry(
                "Example", "mirror-name.elf", "1.0", checksum,
                "https://downloads.example/path/archive.zip?download=1",
                "nested/ServerName.elf",
            )
            filename, actual = downloader.download(entry)
            self.assertEqual(filename, "ServerName.elf")
            self.assertEqual(actual, checksum)
            self.assertEqual((base / filename).read_bytes(), content)
            self.assertFalse(archive_path.exists())

    def test_download_refuses_to_overwrite_existing_file(self):
        content = b"verified ELF payload"
        checksum = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            target = base / "ServerName.elf"
            target.write_bytes(b"keep me")
            transfer = FakeTransfer(base, content)
            downloader = Downloader(base, transfer)
            entry = PayloadEntry(
                "Example", "ignored.elf", "1.0", checksum,
                "https://downloads.example/path/ServerName.elf"
            )
            with self.assertRaises(UpdateError):
                downloader.download(entry)
            self.assertEqual(target.read_bytes(), b"keep me")
            self.assertEqual(transfer.download_calls, 0)

    def test_checksum_mismatch_does_not_install_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            transfer = FakeTransfer(base, b"wrong payload")
            downloader = Downloader(base, transfer)
            entry = PayloadEntry(
                "Example", "catalog-name.elf", "1.0", "0" * 64,
                "https://downloads.example/path/ServerName.elf"
            )
            with self.assertRaises(UpdateError):
                downloader.download(entry)
            self.assertFalse((base / "ServerName.elf").exists())


class DiscoverySelectionTests(unittest.TestCase):
    def test_last_catalog_entry_is_selected_for_missing_payload(self):
        first = PayloadEntry("Missing", "mirror.elf", "1.0", "1" * 64, "https://example.test/one.elf")
        last = PayloadEntry("Missing", "mirror.elf", "2.0", "2" * 64, "https://example.test/two.elf")
        present = PayloadEntry("Present", "present.elf", "1.0", "3" * 64, "https://example.test/present.elf")
        local_files = [SimpleNamespace(checksum="3" * 64)]
        result = ScanResult(
            rows=[RowResult("present.elf", "present.elf", "3" * 64, "1.0", None, "1.0", "3" * 64, "CURRENT", catalog_payload="Present")],
            state_records=[],
        )
        candidates = discover_missing_payloads(local_files, result, [first, present, last])
        self.assertEqual([(item.payload, item.version) for item in candidates], [("Missing", "2.0")])


if __name__ == "__main__":
    unittest.main()
