"""Regression tests for Boolean Pre-release state and MANUAL status overrides."""
import json
import tempfile
import unittest
from pathlib import Path

from app.models import LocalFile, PayloadEntry, StateRecord
from app.reconciler import CURRENT, MANUAL, UNMATCHED, UPDATE_AVAILABLE, Reconciler
from app.state_repository import StateRepository


class PreReleasePersistenceTests(unittest.TestCase):
    def test_legacy_text_is_migrated_to_boolean_and_false_like_values_stay_off(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local-state.json"
            path.write_text(
                json.dumps([
                    {"Payload": "A", "CurrChecksum": "a", "Pre-release": "experimental"},
                    {"Payload": "B", "CurrChecksum": "b", "Pre-release": "False"},
                    {"Payload": "C", "CurrChecksum": "c"},
                ]),
                encoding="utf-8",
            )
            records = StateRepository(path).load()
            self.assertEqual([record.pre_release for record in records], [True, False, False])

    def test_save_always_writes_json_booleans(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local-state.json"
            repository = StateRepository(path)
            repository.save([
                StateRecord("A", "a.elf", "1", "a" * 64, "t", "t", pre_release=True),
                StateRecord("B", "b.elf", "1", "b" * 64, "t", "t", pre_release=False),
            ])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIs(data[0]["Pre-release"], True)
            self.assertIs(data[1]["Pre-release"], False)
            self.assertEqual([record.pre_release for record in repository.load()], [True, False])

    def test_legacy_control_app_identifier_migrates_to_filename_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local-state.json"
            path.write_text(json.dumps([{
                "Payload": "ps5upload-PC_client",
                "CurrDirFilename": "ps5upload-win-x64",
                "CurrChecksum": "a" * 64,
                "FirstSeen": "t",
                "LastSeen": "t",
            }]), encoding="utf-8")
            repository = StateRepository(path)
            record = repository.load()[0]
            self.assertEqual(record.payload, "ps5upload-win-x64")
            self.assertEqual(record.curr_dir_filename, "ps5upload-win-x64")
            self.assertEqual(record.record_type, "control-app")
            repository.save([record])
            saved = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(saved["Payload"], saved["CurrDirFilename"])
            self.assertEqual(saved["RecordType"], "control-app")

    def test_payload_is_always_curr_dir_filename_and_catalog_identity_is_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local-state.json"
            repository = StateRepository(path)
            repository.save([
                StateRecord(
                    payload="CatalogPayloadName",
                    curr_dir_filename="actual-name.elf",
                    curr_dir_file_version="1.0",
                    curr_checksum="a" * 64,
                    first_seen="t",
                    last_seen="t",
                    catalog_payload="CatalogPayloadName",
                )
            ])
            data = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(data["Payload"], "actual-name.elf")
            self.assertEqual(data["CurrDirFilename"], "actual-name.elf")
            self.assertEqual(data["CatalogPayload"], "CatalogPayloadName")
            loaded = repository.load()[0]
            self.assertEqual(loaded.payload, loaded.curr_dir_filename)
            self.assertEqual(loaded.catalog_payload, "CatalogPayloadName")


class PreReleaseStatusTests(unittest.TestCase):
    def setUp(self):
        self.local_checksum = "a" * 64
        self.server_checksum = "b" * 64
        self.local_file = LocalFile("demo.elf", "/tmp/demo.elf", self.local_checksum)

    def record(self, enabled=True, payload="Demo", version="1.0"):
        return StateRecord(
            payload=payload,
            curr_dir_filename="demo.elf",
            curr_dir_file_version=version,
            curr_checksum=self.local_checksum,
            first_seen="2026-10-10 10:00:00",
            last_seen="2026-10-10 10:00:00",
            pre_release=enabled,
            catalog_payload="Demo",
        )

    def entry(self, checksum):
        return PayloadEntry("Demo", "demo.elf", "2.0", checksum, "https://example.test/demo.elf")

    def test_pre_release_overrides_current_status(self):
        result = Reconciler().reconcile(
            [self.local_file], [self.record()], [self.entry(self.local_checksum)], None
        )
        self.assertEqual(result.rows[0].status, MANUAL)
        self.assertEqual(result.current_count, 0)
        self.assertEqual(result.update_count, 0)

    def test_pre_release_overrides_update_available(self):
        result = Reconciler().reconcile(
            [self.local_file], [self.record()], [self.entry(self.server_checksum)], None
        )
        self.assertEqual(result.rows[0].status, MANUAL)
        self.assertEqual(result.update_count, 0)

    def test_pre_release_overrides_unmatched_and_server_unavailable(self):
        unmatched_record = self.record(payload=None, version=None)
        unmatched = Reconciler().reconcile([self.local_file], [unmatched_record], [], None)
        self.assertEqual(unmatched.rows[0].status, MANUAL)
        self.assertEqual(unmatched.unmatched_count, 0)

        unavailable = Reconciler().reconcile(
            [self.local_file], [self.record()], None, "network unavailable"
        )
        self.assertEqual(unavailable.rows[0].status, MANUAL)

    def test_off_restores_normal_status_classification(self):
        result = Reconciler().reconcile(
            [self.local_file], [self.record(enabled=False)], [self.entry(self.server_checksum)], None
        )
        self.assertEqual(result.rows[0].status, UPDATE_AVAILABLE)
        self.assertEqual(result.update_count, 1)

    def test_new_rows_default_pre_release_to_off(self):
        result = Reconciler().reconcile(
            [self.local_file], [], [self.entry(self.local_checksum)], None
        )
        self.assertIs(result.rows[0].pre_release, False)
        self.assertEqual(result.rows[0].status, CURRENT)
        self.assertEqual(result.rows[0].payload, "demo.elf")
        self.assertEqual(result.rows[0].catalog_payload, "Demo")
        self.assertEqual(result.state_records[0].payload, "demo.elf")
        self.assertEqual(result.state_records[0].curr_dir_filename, "demo.elf")


if __name__ == "__main__":
    unittest.main()
