import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.application import Application
from app.models import PayloadEntry, RowResult, ScanResult, StateRecord
from app.reconciler import CURRENT, UPDATE_AVAILABLE


class ApplicationControlAppUpdateIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Application.__new__(Application)
        self.app.base_dir = Path(self.temp.name)
        self.app.logger = Mock()
        self.app.state = Mock()
        self.app.state.load.return_value = []
        self.app.state.save = Mock()
        self.app.scanner = Mock()
        self.app.scanner.scan.return_value = []
        self.app.scanner.hash_files.return_value = []
        self.app.user_config = SimpleNamespace(
            control_app_enabled=True,
            download_only_when_current=False,
        )
        self.entry = PayloadEntry(
            "ps5upload", "ps5upload.elf", "2.0", "3" * 64,
            "https://example.test/ps5upload.elf",
        )
        self.catalog = [self.entry]
        self.app.last_catalog = None
        self.app.discovery_error = None
        self.app.download_candidates = []
        self.app._fetch_catalog = Mock(return_value=(self.catalog, None))
        self.app._reconcile_and_save = Mock(return_value=self._result(UPDATE_AVAILABLE))
        self.app._add_control_app_gui_row = Mock(side_effect=lambda result, _catalog: result)
        self.app._discover_missing = Mock(return_value=[])
        self.app.updater = Mock()
        self.app.updater.update_rows.return_value = []
        self.app.ps5upload_control_app_module = Mock()

    @staticmethod
    def _result(control_status):
        return ScanResult(
            rows=[
                RowResult(
                    "ps5upload.elf", "ps5upload.elf", "a" * 64, "1.0",
                    "2026-01-01 00:00:00", "2.0", "3" * 64, CURRENT,
                    catalog_payload="ps5upload",
                ),
                RowResult(
                    "ps5upload-win-x64", "ps5upload-win-x64", "b" * 64, "1.0",
                    "2026-01-01 00:00:00", "2.0", None, control_status,
                    catalog_payload="__control_app__",
                ),
            ],
            state_records=[],
        )

    def test_update_button_path_delegates_control_app_to_its_module(self):
        after_payload_updates = self._result(UPDATE_AVAILABLE)
        after_control_update = self._result(CURRENT)
        self.app.perform_scan = Mock(
            side_effect=[after_payload_updates, after_control_update]
        )

        result, successful, failed, notice = self.app.perform_update()

        self.app.ps5upload_control_app_module.ensure_client.assert_called_once_with(self.catalog)
        self.assertEqual((successful, failed, notice), (1, 0, None))
        self.assertIs(result, after_control_update)

    def test_control_app_failure_is_counted_without_crashing_main_update(self):
        after_payload_updates = self._result(UPDATE_AVAILABLE)
        after_failed_control_update = self._result(UPDATE_AVAILABLE)
        self.app.perform_scan = Mock(
            side_effect=[after_payload_updates, after_failed_control_update]
        )
        self.app.ps5upload_control_app_module.ensure_client.side_effect = RuntimeError(
            "simulated control-app failure"
        )

        result, successful, failed, notice = self.app.perform_update()

        self.app.ps5upload_control_app_module.ensure_client.assert_called_once_with(self.catalog)
        self.assertEqual((successful, failed, notice), (0, 1, None))
        self.assertIs(result, after_failed_control_update)
        self.app.logger.exception.assert_called()

    def test_control_app_row_integration_failure_preserves_ordinary_rows(self):
        old_name = "ps5upload_v7.0.26-win-x64"
        old_folder = self.app.base_dir / old_name
        old_folder.mkdir()
        old_record = StateRecord(
            old_name, old_name, "7.0.26", "f" * 64,
            "2026-01-01 00:00:00", "2026-01-02 00:00:00",
            record_type="control-app",
        )
        self.app.ps5upload_control_app_module.discover_existing_client.return_value = old_record
        self.app.ps5upload_control_app_module.describe_client.return_value = (
            self.entry, "https://example.test/client.zip", "client.zip",
            "ps5upload-win-x64", True,
        )
        self.app.ps5upload_control_app_module.needs_update.side_effect = RuntimeError(
            "broken control-app module"
        )
        result = self._result(CURRENT)
        result.state_records = [old_record]

        safe_result = Application._add_control_app_gui_row(
            self.app, result, self.catalog
        )

        self.assertIs(safe_result, result)
        self.assertIn("ps5upload.elf", [row.filename for row in safe_result.rows])
        self.assertFalse(any(row.catalog_payload == "__control_app__" for row in safe_result.rows))
        self.app.logger.exception.assert_called()


if __name__ == "__main__":
    unittest.main()
