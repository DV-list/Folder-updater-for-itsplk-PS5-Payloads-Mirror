"""Persistent local history storage."""

import json
import os
import tempfile
from pathlib import Path

from app.models import StateRecord


class StateRepository:
    """Load and atomically save local-state.json."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[StateRecord]:
        """Load historical state; a missing file means an empty history."""
        # A first run is represented by an absent or empty state file.
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)

        if document == []:
            return []

        if not isinstance(document, list):
            raise ValueError("local-state.json must contain an array of records")

        records: list[StateRecord] = []
        for index, item in enumerate(document):
            if not isinstance(item, dict):
                raise ValueError(f"local-state.json record {index} is not an object")

            filename = item.get("CurrDirFilename", "")
            legacy_payload = item.get("Payload")
            record_type = item.get("RecordType")
            if record_type is None and legacy_payload == "ps5upload-PC_client":
                record_type = "control-app"
            catalog_payload = item.get("CatalogPayload")
            if catalog_payload is None and legacy_payload and legacy_payload != filename:
                if legacy_payload != "ps5upload-PC_client":
                    catalog_payload = legacy_payload

            records.append(
                StateRecord(
                    payload=filename or legacy_payload,
                    curr_dir_filename=filename,
                    curr_dir_file_version=item.get("CurrDirFileVersion"),
                    curr_checksum=item.get("CurrChecksum", ""),
                    first_seen=item.get("FirstSeen", ""),
                    last_seen=item.get("LastSeen", ""),
                    last_updated=item.get("LastUpdated"),
                    pre_release=self._normalize_pre_release(item.get("Pre-release")),
                    catalog_payload=catalog_payload,
                    record_type=record_type,
                )
            )

        return records

    def save(self, records: list[StateRecord]) -> None:
        """Atomically replace local-state.json with the supplied history."""
        # Write to a temporary file in the same directory so os.replace remains
        # atomic on the same filesystem. Existing state is not truncated in place.
        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = []
        for record in records:
            item = {
                # Payload is the canonical local identity and always mirrors the
                # current directory filename. Catalog identity is separate metadata.
                "Payload": record.curr_dir_filename,
                "CurrDirFilename": record.curr_dir_filename,
                "CurrDirFileVersion": record.curr_dir_file_version,
                "CurrChecksum": record.curr_checksum,
                "FirstSeen": record.first_seen,
                "LastSeen": record.last_seen,
                "LastUpdated": record.last_updated,
                "Pre-release": self._normalize_pre_release(record.pre_release),
            }
            if record.catalog_payload:
                item["CatalogPayload"] = record.catalog_payload
            if record.record_type:
                item["RecordType"] = record.record_type
            payload.append(item)

        fd, temporary_name = tempfile.mkstemp(
            prefix=f"{self.path.stem}.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    @staticmethod
    def _normalize_pre_release(value) -> bool:
        """Read Boolean values and migrate legacy free-text annotations safely.

        Any old non-empty annotation meant that the user had marked the row as a
        pre-release. Explicit false-like strings remain OFF; arbitrary legacy text
        becomes True so a release upgrade does not silently discard user intent.
        """
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"", "false", "0", "off", "no", "none", "null"}:
                return False
            if normalized in {"true", "1", "on", "yes"}:
                return True
            return True
        return False
