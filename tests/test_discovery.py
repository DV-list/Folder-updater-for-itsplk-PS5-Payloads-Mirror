import unittest

from app.discovery import discover_missing_payloads
from app.models import LocalFile, PayloadEntry, RowResult, ScanResult
from app.statuses import CURRENT


class MissingPayloadDiscoveryTests(unittest.TestCase):
    @staticmethod
    def _entry(payload, version, checksum):
        return PayloadEntry(
            payload=payload,
            filename=f"{payload}.elf",
            version=version,
            checksum=checksum,
            source_direct=f"https://example.test/{payload}.elf",
        )

    def test_old_local_checksum_suppresses_candidate_and_latest_entry_is_selected(self):
        catalog = [
            self._entry("alpha", "1.0", "a" * 64),
            self._entry("alpha", "2.0", "b" * 64),
            self._entry("beta", "1.0", "c" * 64),
            self._entry("beta", "2.0", "d" * 64),
        ]
        local_files = [
            LocalFile(filename="alpha-old.elf", path="alpha-old.elf", checksum="a" * 64)
        ]
        result = ScanResult(rows=[], state_records=[])

        candidates = discover_missing_payloads(local_files, result, catalog)

        self.assertEqual([(item.payload, item.version) for item in candidates], [("beta", "2.0")])

    def test_catalog_identity_prevents_duplicate_candidate_row(self):
        catalog = [
            self._entry("alpha", "1.0", "a" * 64),
            self._entry("beta", "1.0", "b" * 64),
        ]
        result = ScanResult(
            rows=[
                RowResult(
                    payload="alpha.elf",
                    filename="alpha.elf",
                    curr_checksum="c" * 64,
                    curr_file_version="0.9",
                    curr_file_added_date="2026-01-01 00:00:00",
                    server_version="1.0",
                    server_checksum="a" * 64,
                    status=CURRENT,
                    catalog_payload="alpha",
                )
            ],
            state_records=[],
        )

        candidates = discover_missing_payloads([], result, catalog)

        self.assertEqual([(item.payload, item.version) for item in candidates], [("beta", "1.0")])


if __name__ == "__main__":
    unittest.main()
