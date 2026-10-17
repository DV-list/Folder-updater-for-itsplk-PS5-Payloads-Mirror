import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

from app.application import Application
from app.models import PayloadEntry, RowResult, ScanResult, StateRecord
from app.ps5upload_control_app_dl import Ps5uploadControlAppDL
from app.reconciler import CONTROL_APP_DOWNLOAD, CURRENT, MANUAL, UPDATE_AVAILABLE
from app.state_repository import StateRepository
from app.user_config import UserConfig


class ControlAppGuiRowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application.__new__(Application)
        self.app.base_dir = Path(self.temp.name)
        self.app.state = StateRepository(self.app.base_dir / "appdata" / "local-state.json")
        self.app.user_config = UserConfig(self.app.base_dir)
        self.app.ps5upload_control_app_module = Ps5uploadControlAppDL(
            self.app.base_dir, self.app.state, self.app.user_config
        )
        self.app.discovery_error = None
        self.app.last_catalog = None
        self.app.result = None
        self.app.download_candidates = []

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _catalog():
        return [PayloadEntry("ps5upload", "ps5upload.elf", "2.0", "3" * 64, "https://example.test/ps5upload.elf")]

    def _result(self, parent_status, include_record=True):
        rows = [
            RowResult("other.elf", "other.elf", "1" * 64, "1.0", "2026-01-01 00:00:00", "1.0", "1" * 64, CURRENT, catalog_payload="other"),
            RowResult("ps5upload.elf", "ps5upload.elf", "2" * 64, "1.0", "2026-01-01 00:00:00", "2.0", "3" * 64, parent_status, catalog_payload="ps5upload"),
        ]
        records = []
        if include_record:
            records.append(StateRecord(
                payload="ps5upload-win-x64",
                curr_dir_filename="ps5upload-win-x64",
                record_type="control-app",
                curr_dir_file_version="1.0",
                curr_checksum="a" * 64,
                first_seen="2026-01-01 00:00:00",
                last_seen="2026-01-02 00:00:00",
            ))
            self.app.state.save(records)
        return ScanResult(rows=rows, state_records=records)

    def test_control_app_row_inserted_immediately_after_ps5upload_and_server_version_refreshed(self):
        (self.app.base_dir / "ps5upload-win-x64").mkdir()
        result = self._result(UPDATE_AVAILABLE)
        result = self.app._add_control_app_gui_row(result, self._catalog())
        payloads = [row.payload for row in result.rows]
        self.assertEqual(payloads, ["other.elf", "ps5upload.elf", "ps5upload-win-x64"])
        pc_row = result.rows[2]
        self.assertEqual(pc_row.server_version, "2.0")
        self.assertEqual(pc_row.curr_file_version, "1.0")
        self.assertEqual(pc_row.curr_checksum, "a" * 64)
        self.assertEqual(pc_row.status, "Waiting for ps5upload CURRENT")
        self.assertEqual(pc_row.payload, pc_row.filename)
        self.assertIsNone(pc_row.server_checksum)

    def test_missing_control_app_uses_latest_catalog_name_not_stale_record(self):
        stale_name = "ps5upload-win-x64-old"
        stale_record = StateRecord(
            payload=stale_name,
            curr_dir_filename=stale_name,
            curr_dir_file_version="1.0",
            curr_checksum="a" * 64,
            first_seen="2026-01-01 00:00:00",
            last_seen="2026-01-02 00:00:00",
            record_type="control-app",
        )
        self.app.state.save([stale_record])
        result = self._result(CURRENT, include_record=False)
        result.state_records = self.app.state.load()

        result = self.app._add_control_app_gui_row(result, self._catalog())

        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.payload, "ps5upload-win-x64")
        self.assertEqual(pc_row.filename, "ps5upload-win-x64")
        self.assertEqual(pc_row.server_version, "2.0")
        self.assertEqual(pc_row.status, CONTROL_APP_DOWNLOAD)
        self.assertIsNone(pc_row.curr_file_version)
        self.assertFalse((self.app.base_dir / stale_name).exists())

    def test_no_control_app_row_without_record_or_catalog_entry(self):
        result = self._result(CURRENT, include_record=False)
        result = self.app._add_control_app_gui_row(result, [])
        self.assertFalse(any(row.catalog_payload == "__control_app__" for row in result.rows))

    def test_control_app_row_is_hidden_when_ps5upload_is_not_in_local_folder(self):
        result = ScanResult(
            rows=[
                RowResult(
                    "other.elf", "other.elf", "1" * 64, "1.0",
                    "2026-01-01 00:00:00", "1.0", "1" * 64, CURRENT,
                    catalog_payload="other",
                )
            ],
            state_records=[],
        )

        result = self.app._add_control_app_gui_row(result, self._catalog())

        self.assertEqual([row.payload for row in result.rows], ["other.elf"])
        self.assertFalse(any(row.catalog_payload == "__control_app__" for row in result.rows))
        self.assertEqual(self.app.state.load(), [])

    def test_missing_control_app_creates_download_row_without_state_record(self):
        result = self._result(CURRENT, include_record=False)
        result = self.app._add_control_app_gui_row(result, self._catalog())
        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.status, CONTROL_APP_DOWNLOAD)
        self.assertEqual(pc_row.payload, "ps5upload-win-x64")
        self.assertEqual(pc_row.filename, "ps5upload-win-x64")
        self.assertIsNone(pc_row.curr_checksum)
        self.assertEqual(self.app.state.load(), [])

    def test_manual_ps5upload_version_folder_prevents_download_state(self):
        manual_folder = self.app.base_dir / "PS5Upload-7.0.22-win-x64"
        manual_folder.mkdir()
        result = self._result(CURRENT, include_record=False)

        result = self.app._add_control_app_gui_row(result, self._catalog())

        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.filename, "PS5Upload-7.0.22-win-x64")
        self.assertTrue((self.app.base_dir / pc_row.filename).is_dir())
        self.assertNotEqual(pc_row.status, CONTROL_APP_DOWNLOAD)

    def test_folder_version_overrides_stale_local_state_and_matches_server(self):
        folder_name = "PS5Upload-7.0.22-win-x64"
        (self.app.base_dir / folder_name).mkdir()
        stale_record = StateRecord(
            payload=folder_name,
            curr_dir_filename=folder_name,
            curr_dir_file_version="7.0.1",
            curr_checksum="a" * 64,
            first_seen="2026-01-01 00:00:00",
            last_seen="2026-01-02 00:00:00",
            record_type="control-app",
        )
        self.app.state.save([stale_record])
        result = self._result(CURRENT, include_record=False)
        result.state_records = self.app.state.load()
        catalog = [
            PayloadEntry("ps5upload", "ps5upload.elf", "7.0.22", "3" * 64, "https://example.test/ps5upload.elf")
        ]

        result = self.app._add_control_app_gui_row(result, catalog)

        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.filename, folder_name)
        self.assertEqual(pc_row.curr_file_version, "7.0.22")
        self.assertEqual(pc_row.server_version, "7.0.22")
        self.assertEqual(pc_row.status, CURRENT)

        # Folder-name version parsing belongs to the control-app module only.
        elf_row = next(row for row in result.rows if row.payload == "ps5upload.elf")
        self.assertEqual(elf_row.curr_file_version, "1.0")
        self.assertEqual(elf_row.status, CURRENT)

    def test_manual_payload_folder_prevents_download_state(self):
        manual_folder = self.app.base_dir / "Payload"
        manual_folder.mkdir()
        result = self._result(CURRENT, include_record=False)

        result = self.app._add_control_app_gui_row(result, self._catalog())

        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.filename, "Payload")
        self.assertTrue((self.app.base_dir / pc_row.filename).is_dir())
        self.assertNotEqual(pc_row.status, CONTROL_APP_DOWNLOAD)

    def test_download_row_waits_when_ps5upload_is_not_current_and_gate_enabled(self):
        result = self._result(UPDATE_AVAILABLE, include_record=False)
        result = self.app._add_control_app_gui_row(result, self._catalog())
        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.status, "Waiting for ps5upload CURRENT")

    def test_existing_client_uses_actual_tracked_filename(self):
        actual = self.app.base_dir / "custom-control-app-dir"
        actual.mkdir()
        record = StateRecord(
            payload=actual.name, curr_dir_filename=actual.name, curr_dir_file_version="1.0",
            curr_checksum="a" * 64, first_seen="2026-01-01 00:00:00", last_seen="2026-01-02 00:00:00",
            record_type="control-app",
        )
        self.app.state.save([record])
        result = self._result(CURRENT, include_record=False)
        # Pull the record from persistent state, as the regular scan does.
        result.state_records = self.app.state.load()
        result = self.app._add_control_app_gui_row(result, self._catalog())
        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.payload, "custom-control-app-dir")
        self.assertEqual(pc_row.filename, "custom-control-app-dir")
        self.assertEqual(pc_row.status, UPDATE_AVAILABLE)

    def test_control_app_status_uses_its_own_version_even_when_ps5upload_is_current(self):
        (self.app.base_dir / "ps5upload-win-x64").mkdir()
        result = self._result(CURRENT)
        result = self.app._add_control_app_gui_row(result, self._catalog())
        pc_row = next(row for row in result.rows if row.catalog_payload == "__control_app__")
        self.assertEqual(pc_row.curr_file_version, "1.0")
        self.assertEqual(pc_row.server_version, "2.0")
        self.assertEqual(pc_row.status, UPDATE_AVAILABLE)

    def test_pre_release_overrides_missing_control_app_status(self):
        result = self._result(CURRENT)
        result.state_records[-1].pre_release = True
        self.app.state.save(result.state_records)
        result = self.app._add_control_app_gui_row(result, self._catalog())
        self.assertEqual(result.rows[-1].status, MANUAL)

    def test_startup_scan_does_not_call_control_app_installer(self):
        self.app.scanner = Mock()
        self.app.scanner.scan.return_value = []
        self.app.scanner.hash_files.return_value = []
        self.app._fetch_catalog = Mock(return_value=(self._catalog(), None))
        self.app._reconcile_and_save = Mock(return_value=self._result(CURRENT, include_record=False))
        self.app._add_control_app_gui_row = Mock(side_effect=lambda result, _catalog: result)
        self.app._discover_missing = Mock(return_value=[])
        self.app.ps5upload_control_app_module.ensure_client = Mock()
        self.app.perform_scan()
        self.app.ps5upload_control_app_module.ensure_client.assert_not_called()

    def test_scheduled_scan_does_not_call_control_app_installer(self):
        self.app.scanner = Mock()
        self.app.scanner.scan.return_value = []
        self.app.scanner.hash_files.return_value = []
        self.app.last_catalog = self._catalog()
        self.app._reconcile_and_save = Mock(return_value=self._result(CURRENT, include_record=False))
        self.app._add_control_app_gui_row = Mock(side_effect=lambda result, _catalog: result)
        self.app._discover_missing = Mock(return_value=[])
        self.app.ps5upload_control_app_module.ensure_client = Mock()
        self.app.perform_folder_scan()
        self.app.ps5upload_control_app_module.ensure_client.assert_not_called()

    def test_control_app_installer_runs_only_from_explicit_download_callback(self):
        result = self._result(CURRENT, include_record=False)
        result.rows.append(RowResult(
            "ps5upload-win-x64", "ps5upload-win-x64", None, None, None, "2.0", None,
            "CURRENT", catalog_payload="__control_app__",
        ))
        self.app.last_catalog = self._catalog()
        self.app.result = result
        self.app.discovery_error = None
        self.app.logger = Mock()
        self.app.ps5upload_control_app_module.ensure_client = Mock()
        self.app.perform_folder_scan = Mock(return_value=(result, [], None))

        outcome = self.app.perform_control_app_download()

        self.app.ps5upload_control_app_module.ensure_client.assert_called_once_with(self.app.last_catalog)
        self.assertIsNone(outcome[2])

    def test_configured_current_gate_blocks_control_app_download(self):
        result = self._result(UPDATE_AVAILABLE, include_record=False)
        self.app.last_catalog = self._catalog()
        self.app.result = result
        self.app.discovery_error = None
        self.app.logger = Mock()
        self.app.ps5upload_control_app_module.ensure_client = Mock()
        self.app.perform_folder_scan = Mock(return_value=(result, [], None))

        outcome = self.app.perform_control_app_download()

        self.app.ps5upload_control_app_module.ensure_client.assert_not_called()
        self.assertIn("requires ps5upload to be CURRENT", outcome[2])

    def test_module_gate_requires_current_and_no_catalog_error(self):
        result = self._result(CURRENT)
        self.assertTrue(Application._ps5upload_is_current(result, None))
        self.assertFalse(Application._ps5upload_is_current(result, "catalog unavailable"))
        result = self._result(UPDATE_AVAILABLE)
        self.assertFalse(Application._ps5upload_is_current(result, None))


if __name__ == "__main__":
    unittest.main()
