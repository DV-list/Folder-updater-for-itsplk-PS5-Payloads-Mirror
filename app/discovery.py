"""Pure catalog-to-local payload discovery rules."""

from app.models import PayloadEntry, ScanResult


def discover_missing_payloads(local_files, result: ScanResult, catalog: list[PayloadEntry]) -> list[PayloadEntry]:
    """Select the last catalog entry for each payload not represented locally."""
    latest_by_payload: dict[str, PayloadEntry] = {}
    all_checksums_by_payload: dict[str, set[str]] = {}
    for entry in catalog:
        latest_by_payload[entry.payload] = entry
        all_checksums_by_payload.setdefault(entry.payload, set()).add(entry.checksum.lower())

    local_payloads = {
        row.catalog_payload
        for row in result.rows
        if row.catalog_payload and row.catalog_payload != "__control_app__"
    }
    local_checksums = {item.checksum.lower() for item in local_files if item.checksum}
    candidates: list[PayloadEntry] = []
    for payload, entry in latest_by_payload.items():
        # If a payload identity is already represented locally, the existing Updater
        # owns it. Matching any catalog checksum also proves that the payload exists.
        if payload in local_payloads:
            continue
        if all_checksums_by_payload[payload] & local_checksums:
            continue
        candidates.append(entry)
    return candidates
