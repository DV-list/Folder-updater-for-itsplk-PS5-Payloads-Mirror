"""Pure catalog-to-local payload discovery rules."""

from app.models import PayloadEntry, ScanResult


def discover_missing_payloads(
    local_files,
    result: ScanResult,
    catalog: list[PayloadEntry],
) -> list[PayloadEntry]:
    """Select the last catalog entry for each payload not represented locally."""
    latest_by_payload: dict[str, PayloadEntry] = {}
    payloads_present_by_checksum: set[str] = set()

    local_payloads = {
        row.catalog_payload
        for row in result.rows
        if row.catalog_payload and row.catalog_payload != "__control_app__"
    }
    local_checksums = {
        item.checksum.lower()
        for item in local_files
        if item.checksum
    }

    # Keep the newest entry for each payload, but remember checksums for every
    # catalog version so an older local version still suppresses a download row.
    for entry in catalog:
        latest_by_payload[entry.payload] = entry
        if entry.checksum.lower() in local_checksums:
            payloads_present_by_checksum.add(entry.payload)

    return [
        entry
        for payload, entry in latest_by_payload.items()
        if payload not in local_payloads
        and payload not in payloads_present_by_checksum
    ]
