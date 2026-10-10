"""Local/server reconciliation and historical state management."""

from datetime import datetime

from app.models import LocalFile, PayloadEntry, RowResult, ScanResult, StateRecord


CURRENT = "CURRENT"
UPDATE_AVAILABLE = "UPDATE AVAILABLE"
UNMATCHED = "UNMATCHED"
SERVER_UNAVAILABLE = "SERVER UNAVAILABLE"
REMOVED_FROM_SERVER = "REMOVED FROM SERVER"
MANUAL = "MANUAL"
CONTROL_APP_DOWNLOAD = "DOWNLOAD"


class Reconciler:
    """Determine current payload status without modifying local ELF files."""

    def reconcile(
        self,
        local_files: list[LocalFile],
        state_records: list[StateRecord],
        catalog: list[PayloadEntry] | None,
        catalog_error: str | None,
    ) -> ScanResult:
        """Reconcile all current ELF files with history and the remote catalog."""
        now = datetime.now().astimezone().replace(microsecond=0).isoformat(sep=" ")
        history = self._index_history(state_records)
        catalog_entries = catalog or []
        server_by_checksum = self._index_catalog_by_checksum(catalog_entries)
        server_by_payload = self._index_catalog_by_payload(catalog_entries)
        server_by_filename = self._index_catalog_by_filename(catalog_entries)

        rows: list[RowResult] = []
        updated_history = list(state_records)

        # Process every current ELF independently so one bad file does not invalidate
        # the rest of the scan.
        for local_file in local_files:
            if local_file.hash_error or not local_file.checksum:
                rows.append(
                    RowResult(
                        payload=local_file.filename,
                        filename=local_file.filename,
                        curr_checksum=None,
                        curr_file_version=None,
                        curr_file_added_date=None,
                        server_version=None,
                        server_checksum=None,
                        status=UNMATCHED,
                    )
                )
                continue

            checksum = local_file.checksum.lower()
            historical = history.get(checksum)

            # Payload is always the local filename. CatalogPayload is kept separately
            # for internal server-version matching and update selection.
            if historical is not None:
                payload = local_file.filename
                curr_version = historical.curr_dir_file_version
                first_seen = historical.first_seen
                pre_release = bool(historical.pre_release)
                catalog_payload = historical.catalog_payload

                historical.last_seen = now
                historical.curr_dir_filename = local_file.filename
                historical.payload = local_file.filename
            else:
                server_match = server_by_checksum.get(checksum)
                if server_match is None:
                    filename_match = server_by_filename.get(local_file.filename)
                    catalog_payload = filename_match.payload if filename_match else None
                    curr_version = filename_match.version if filename_match else None
                    first_seen = now
                else:
                    catalog_payload = server_match.payload
                    curr_version = server_match.version
                    first_seen = now
                payload = local_file.filename
                pre_release = False

                new_record = StateRecord(
                    payload=payload,
                    curr_dir_filename=local_file.filename,
                    curr_dir_file_version=curr_version,
                    curr_checksum=checksum,
                    first_seen=first_seen,
                    last_seen=now,
                    pre_release=pre_release,
                    catalog_payload=catalog_payload,
                )
                updated_history.append(new_record)
                history[checksum] = new_record
                historical = new_record

            if historical is not None and not catalog_payload:
                checksum_match = server_by_checksum.get(checksum)
                filename_match = server_by_filename.get(local_file.filename)
                fallback_match = checksum_match or filename_match
                if fallback_match is not None:
                    catalog_payload = fallback_match.payload
                    historical.catalog_payload = catalog_payload
                    if curr_version is None:
                        curr_version = fallback_match.version
                        historical.curr_dir_file_version = curr_version

            if catalog_error:
                status = SERVER_UNAVAILABLE
                server_version = None
                server_checksum = None
            elif curr_version is None:
                status = UNMATCHED
                server_version = None
                server_checksum = None
            else:
                server_entry = server_by_payload.get(catalog_payload or "")

                if server_entry is None:
                    status = REMOVED_FROM_SERVER
                    server_version = None
                    server_checksum = None
                else:
                    server_version = server_entry.version
                    server_checksum = server_entry.checksum
                    status = (
                        CURRENT
                        if checksum == server_checksum
                        else UPDATE_AVAILABLE
                    )

            # Pre-release is an explicit user override. It takes precedence over
            # every computed status, including unavailable/removed conditions.
            if pre_release:
                status = MANUAL

            rows.append(
                RowResult(
                    payload=local_file.filename,
                    filename=local_file.filename,
                    curr_checksum=checksum,
                    curr_file_version=curr_version,
                    curr_file_added_date=first_seen,
                    server_version=server_version,
                    server_checksum=server_checksum,
                    status=status,
                    pre_release=pre_release,
                    catalog_payload=catalog_payload,
                )
            )

        return ScanResult(
            rows=rows,
            state_records=updated_history,
            catalog_error=catalog_error,
            scanned_files=len(local_files),
            current_count=sum(row.status == CURRENT for row in rows),
            update_count=sum(row.status == UPDATE_AVAILABLE for row in rows),
            unmatched_count=sum(row.status == UNMATCHED for row in rows),
            removed_count=sum(row.status == REMOVED_FROM_SERVER for row in rows),
        )

    @staticmethod
    def _index_history(records: list[StateRecord]) -> dict[str, StateRecord]:
        """Index history by checksum."""
        # SHA-256 is the rigid binary identity. A checksum must map to its historical
        # observation rather than being inferred from a filename or version string.
        return {
            record.curr_checksum.lower(): record
            for record in records
            if record.curr_checksum
        }

    @staticmethod
    def _index_catalog_by_checksum(
        entries: list[PayloadEntry],
    ) -> dict[str, PayloadEntry]:
        """Index the current server catalog by checksum."""
        return {entry.checksum.lower(): entry for entry in entries}

    @staticmethod
    def _index_catalog_by_payload(
        entries: list[PayloadEntry],
    ) -> dict[str, PayloadEntry]:
        """Index the current server catalog by its internal catalog identity."""
        return {entry.payload: entry for entry in entries}

    @staticmethod
    def _index_catalog_by_filename(
        entries: list[PayloadEntry],
    ) -> dict[str, PayloadEntry]:
        """Index entries by filename for legacy history migration and reconciliation."""
        return {entry.filename: entry for entry in entries}
