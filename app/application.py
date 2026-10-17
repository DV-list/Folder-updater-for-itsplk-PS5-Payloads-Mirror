"""Application orchestration for scanning, reconciliation, updating, and downloading."""

import logging
import sys
from datetime import datetime
from pathlib import Path

from app.config import AppConfig
from app.downloader import Downloader
from app.discovery import discover_missing_payloads
from app.gui import MainWindow
from app.logging_setup import configure_logging
from app.user_config import UserConfig
from app.models import PayloadEntry, ScanResult
from app.payload_catalog import PayloadCatalog, PayloadCatalogError
from app.ps5upload_control_app_dl import Ps5uploadControlAppDL
from app.reconciler import Reconciler
from app.statuses import (
    CONTROL_APP_DOWNLOAD,
    CURRENT,
    MANUAL,
    SERVER_UNAVAILABLE,
    UPDATE_AVAILABLE,
)
from app.scanner import FileScanner
from app.state_repository import StateRepository
from app.updater import UpdateError, UpdateManager


class Application:
    """Coordinate local scans, server discovery, updates, downloads, and the GUI."""

    def __init__(self) -> None:
        if getattr(sys, "frozen", False):
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.base_dir = Path(__file__).resolve().parent.parent
        self.config = AppConfig(self.base_dir)
        self.user_config = UserConfig(self.base_dir)
        configure_logging(self.config.log_path, self.user_config.log_level)
        self.logger = logging.getLogger(__name__)

        self.scanner = FileScanner()
        self.catalog = PayloadCatalog(self.config.payloads_url)
        self.state = StateRepository(self.config.state_path)
        self.reconciler = Reconciler()
        self.updater = UpdateManager(self.base_dir)
        self.downloader = Downloader(self.base_dir, self.updater)
        # The control app is optional: failure to initialize it must not prevent ELF updates.
        try:
            self.ps5upload_control_app_module = Ps5uploadControlAppDL(
                self.base_dir, self.state, self.user_config
            )
        except Exception:
            self.logger.exception("Control-app module initialization failed; continuing without it")
            self.ps5upload_control_app_module = None
        self.result: ScanResult | None = None
        self.last_catalog: list[PayloadEntry] | None = None
        self.download_candidates: list[PayloadEntry] = []
        self.discovery_error: str | None = None

    def perform_scan(self) -> ScanResult:
        """Scan local files, refresh the catalog, and discover missing payloads."""
        state_records = self.state.load()
        local_files = self.scanner.hash_files(self.scanner.scan(self.base_dir))
        fetched_catalog, catalog_error = self._fetch_catalog()

        if fetched_catalog is not None:
            self.last_catalog = fetched_catalog
            self.discovery_error = None
        else:
            self.discovery_error = catalog_error

        # On a catalog outage, retain the last good catalog for reconciliation and
        # Downloader rows. The error is shown separately rather than treating the
        # catalog as empty or wiping known missing-payload candidates.
        usable_catalog = self.last_catalog
        reconcile_error = catalog_error if usable_catalog is None else None
        result = self._reconcile_and_save(
            local_files, state_records, usable_catalog, reconcile_error
        )
        # Discovery must remain read-only with respect to remote assets: the control
        # app row is offered in the GUI, and installation starts only after confirmation.
        result = self._add_control_app_gui_row(result, usable_catalog)
        self.result = result
        if usable_catalog is not None:
            self.download_candidates = self._discover_missing(local_files, result, usable_catalog)
        result.download_candidates = list(self.download_candidates)
        result.discovery_error = self.discovery_error
        return result

    def perform_folder_scan(self) -> tuple[ScanResult, list[PayloadEntry], str | None]:
        """Rescan the folder every two minutes without fetching payloads.json."""
        state_records = self.state.load()
        local_files = self.scanner.hash_files(self.scanner.scan(self.base_dir))
        reconcile_error = self.discovery_error if self.last_catalog is None else None
        result = self._reconcile_and_save(
            local_files, state_records, self.last_catalog, reconcile_error
        )
        # Periodic scans only reconcile files and update the discovered control-app row.
        # They never download or extract a control-app release asset.
        result = self._add_control_app_gui_row(result, self.last_catalog)
        self.result = result
        if self.last_catalog is not None:
            self.download_candidates = self._discover_missing(
                local_files, result, self.last_catalog
            )
        result.download_candidates = list(self.download_candidates)
        result.discovery_error = self.discovery_error
        return result, list(self.download_candidates), self.discovery_error

    @staticmethod
    def _ps5upload_is_current(result: ScanResult, catalog_error: str | None) -> bool:
        """Return true only when a fresh/known-good reconciliation marks ps5upload CURRENT."""
        if catalog_error is not None:
            return False
        return any((row.catalog_payload or row.payload) == "ps5upload" and row.status == "CURRENT" for row in result.rows)

    def _control_app_download_allowed(self, result: ScanResult | None = None) -> bool:
        """Return whether current configuration and catalog state permit a download."""
        if not self.user_config.control_app_enabled or not self.last_catalog:
            return False
        if not any(item.payload == "ps5upload" for item in self.last_catalog):
            return False
        current_result = result or self.result
        if self.user_config.download_only_when_current:
            return (
                current_result is not None
                and self._ps5upload_is_current(current_result, self.discovery_error)
            )
        return True

    def _add_control_app_gui_row(self, result: ScanResult, catalog: list[PayloadEntry] | None) -> ScanResult:
        """Integrate the optional control-app row without risking ordinary payload rows."""
        try:
            return self._build_control_app_gui_row(result, catalog)
        except Exception:
            self.logger.exception(
                "Control-app row integration failed; continuing with ordinary payload rows"
            )
            result.rows = [
                row for row in result.rows if row.catalog_payload != "__control_app__"
            ]
            return result

    def _build_control_app_gui_row(self, result: ScanResult, catalog: list[PayloadEntry] | None) -> ScanResult:
        """Add a control-app row after ps5upload, without downloading absent assets."""
        from app.models import RowResult

        result.rows = [row for row in result.rows if row.catalog_payload != "__control_app__"]
        records = result.state_records
        record = next((item for item in records if item.record_type == "control-app"), None)
        catalog_entry = next((item for item in reversed(catalog or []) if item.payload == "ps5upload"), None)

        if catalog_entry is not None:
            try:
                discovered_record = self.ps5upload_control_app_module.discover_existing_client(catalog or [])
                if discovered_record is not None:
                    record = discovered_record
                    result.state_records = self.state.load()
                    records = result.state_records
            except Exception:
                self.logger.exception("Control-app discovery failed")

        # Without a state record or catalog entry, the intended filename is unknown.
        # If the feature is disabled, don't advertise a not-yet-installed asset either.
        if record is None and (catalog_entry is None or not self.user_config.control_app_enabled):
            return result
        if catalog_entry is None and record is None:
            return result

        if catalog_entry is not None:
            try:
                description = self.ps5upload_control_app_module.describe_client(catalog or [])
                expected_name = description[3] if description else None
            except Exception:
                self.logger.exception("Could not derive control-app download target")
                expected_name = None
        else:
            expected_name = None

        # Preserve a tracked custom name only while that path still exists. If the
        # tracked control-app folder/file was deleted, show the latest catalog-derived
        # target name rather than a stale filename from local-state.json.
        tracked_filename = None
        if record is not None and record.curr_dir_filename:
            tracked_path = self.base_dir / record.curr_dir_filename
            if tracked_path.exists():
                tracked_filename = record.curr_dir_filename
        # The dedicated control-app module discovers manually copied folders and
        # updates its own state record before this GUI row is assembled. Do not apply
        # folder-name version detection or directory matching to ordinary ELF rows.
        expected_path = self.base_dir / expected_name if expected_name else None
        if tracked_filename:
            filename = tracked_filename
        elif expected_path is not None and expected_path.exists():
            filename = expected_name
        else:
            filename = expected_name or "ps5upload-control-app"
        current_path = self.base_dir / filename
        installed = current_path.is_file() or current_path.is_dir()
        parent_row = next(
            (row for row in result.rows if (row.catalog_payload or row.payload) == "ps5upload"),
            None,
        )
        # The control-app row is subordinate to the local ps5upload ELF. Do not
        # advertise its status or download action when that payload is absent.
        if parent_row is None:
            return result

        server_version = catalog_entry.version if catalog_entry is not None else None

        # Current version metadata is supplied by the control-app module's state record.
        current_version_text = (
            record.curr_dir_file_version
            if record is not None and installed
            else None
        )

        if installed:
            if catalog is None or catalog_entry is None:
                status = SERVER_UNAVAILABLE
            elif not self.user_config.control_app_enabled:
                status = "Disabled in config"
            elif (
                self.user_config.download_only_when_current
                and not self._ps5upload_is_current(result, self.discovery_error)
            ):
                status = "Waiting for ps5upload CURRENT"
            else:
                # The standalone control-app module owns version comparison. ELF rows
                # continue through the ordinary checksum/catalog reconciler.
                status = (
                    UPDATE_AVAILABLE
                    if self.ps5upload_control_app_module.needs_update(
                        current_version_text, server_version
                    )
                    else CURRENT
                )
        elif catalog is None or catalog_entry is None:
            status = SERVER_UNAVAILABLE
        elif not self.user_config.control_app_enabled:
            status = "Disabled in config"
        elif self.user_config.download_only_when_current and not self._ps5upload_is_current(result, self.discovery_error):
            status = "Waiting for ps5upload CURRENT"
        elif expected_name is None:
            status = "Download unavailable"
        else:
            status = CONTROL_APP_DOWNLOAD

        pre_release = bool(record.pre_release) if record is not None else False
        client_row = RowResult(
            payload=filename,
            filename=filename,
            curr_checksum=(record.curr_checksum or None) if record is not None and installed else None,
            curr_file_version=current_version_text if installed else None,
            curr_file_added_date=record.first_seen if record is not None and installed else None,
            server_version=server_version,
            # payloads.json checksum belongs to the ELF, not the control-app asset.
            server_checksum=None,
            status=MANUAL if pre_release else status,
            pre_release=pre_release,
            catalog_payload="__control_app__",
        )
        insert_at = result.rows.index(parent_row) + 1
        result.rows.insert(insert_at, client_row)
        return result

    def perform_control_app_download(
        self,
    ) -> tuple[ScanResult, list[PayloadEntry], str | None, str | None]:
        """Run the special control-app installer after explicit GUI confirmation."""
        if not self.user_config.control_app_enabled:
            result = self.result or ScanResult(rows=[], state_records=[])
            return result, list(self.download_candidates), "Control-app download is disabled in appdata/config.ini", self.discovery_error
        if not self.last_catalog or not any(item.payload == "ps5upload" for item in self.last_catalog):
            result = self.result or ScanResult(rows=[], state_records=[])
            return result, list(self.download_candidates), "ps5upload is not present in the usable server catalog", self.discovery_error
        if not self._control_app_download_allowed(self.result):
            result, candidates, discovery_error = self.perform_folder_scan()
            return result, candidates, "Download requires ps5upload to be CURRENT by configuration", discovery_error

        self.logger.info("Control-app download explicitly requested by user")
        try:
            self.ps5upload_control_app_module.ensure_client(self.last_catalog)
        except Exception as exc:
            self.logger.exception("Explicit control-app download failed")
            result, candidates, discovery_error = self.perform_folder_scan()
            return result, candidates, str(exc), discovery_error

        result, candidates, discovery_error = self.perform_folder_scan()
        control_row = next((row for row in result.rows if row.catalog_payload == "__control_app__"), None)
        if control_row is None or control_row.status in {CONTROL_APP_DOWNLOAD, "Download unavailable", SERVER_UNAVAILABLE}:
            return (
                result, candidates,
                "Control-app download completed but the installation was not confirmed by the folder scan.",
                discovery_error,
            )
        self.logger.info("Explicit control-app download completed and verified")
        return result, candidates, None, discovery_error

    def perform_download(
        self, entry: PayloadEntry
    ) -> tuple[ScanResult, list[PayloadEntry], str | None, str | None]:
        """Download one selected row, verify it, rescan, then rediscover the catalog."""
        self.logger.info("DOWNLOAD operation started for payload %s", entry.payload)
        try:
            filename, checksum = self.downloader.download(entry)
        except (UpdateError, OSError, ValueError) as exc:
            self.logger.warning("Download failed for %s: %s", entry.payload, exc)
            result, candidates, discovery_error = self.perform_folder_scan()
            return result, candidates, str(exc), discovery_error
        except Exception as exc:
            self.logger.exception("Unexpected download failure for %s", entry.payload)
            result, candidates, discovery_error = self.perform_folder_scan()
            return result, candidates, str(exc), discovery_error

        # Successful Download triggers a fresh server discovery, in addition to the
        # local rescan. perform_scan falls back to the last good catalog on network error.
        result = self.perform_scan()
        confirmed = any(
            row.filename == filename
            and (row.curr_checksum or "").lower() == checksum.lower()
            and (row.catalog_payload or row.payload) == entry.payload
            for row in result.rows
        )
        if not confirmed:
            # Keep the placeholder available until a later scan confirms identity and
            # checksum. Avoid duplicate candidate rows if it is already present.
            if not any(item.payload == entry.payload for item in self.download_candidates):
                self.download_candidates.append(entry)
            result.download_candidates = list(self.download_candidates)
            result.discovery_error = self.discovery_error
            self.logger.error(
                "Downloaded file %s was installed but not confirmed by reconciliation", filename
            )
            return (
                result,
                list(self.download_candidates),
                "Download installed, but the rescan could not confirm the payload identity and checksum.",
                self.discovery_error,
            )

        result.download_candidates = list(self.download_candidates)
        result.discovery_error = self.discovery_error
        self.logger.info("DOWNLOAD operation completed and verified for %s", entry.payload)
        return result, list(self.download_candidates), None, self.discovery_error

    def set_pre_release(self, checksum: str, value: bool) -> ScanResult:
        """Persist a Boolean Pre-release switch and re-reconcile using the cached catalog."""
        records = self.state.load()
        target = checksum.lower()
        pre_release = bool(value)
        updated = False
        for record in records:
            if record.curr_checksum.lower() == target:
                record.pre_release = pre_release
                updated = True
                break
        if not updated:
            raise ValueError("Cannot set Pre-release for an unknown checksum")
        self.state.save(records)
        self.logger.info("Updated Pre-release for checksum %s: %s", target, pre_release)

        # Checkbox changes should not block the GUI on a network request. Reuse the
        # last good catalog and refresh local state only; regular scans still fetch it.
        state_records = self.state.load()
        local_files = self.scanner.hash_files(self.scanner.scan(self.base_dir))
        reconcile_error = self.discovery_error if self.last_catalog is None else None
        result = self._reconcile_and_save(
            local_files, state_records, self.last_catalog, reconcile_error
        )
        result = self._add_control_app_gui_row(result, self.last_catalog)
        if self.last_catalog is not None:
            self.download_candidates = self._discover_missing(
                local_files, result, self.last_catalog
            )
        result.download_candidates = list(self.download_candidates)
        result.discovery_error = self.discovery_error
        self.result = result
        return result

    def perform_update(self) -> tuple[ScanResult, int, int, str | None]:
        """Update ordinary payloads, then delegate eligible control-app updates safely."""
        self.logger.info("UPDATE operation started")
        state_records = self.state.load()
        local_files = self.scanner.hash_files(self.scanner.scan(self.base_dir))
        fetched_catalog, catalog_error = self._fetch_catalog()
        if fetched_catalog is not None:
            self.last_catalog = fetched_catalog
            self.discovery_error = None
        else:
            self.discovery_error = catalog_error

        usable_catalog = self.last_catalog
        reconcile_error = catalog_error if usable_catalog is None else None
        result = self._reconcile_and_save(
            local_files, state_records, usable_catalog, reconcile_error
        )
        # Include the dedicated row for visibility, but UpdateManager deliberately
        # skips it: the control-app module alone owns its asset lifecycle.
        result = self._add_control_app_gui_row(result, usable_catalog)
        self.result = result
        if usable_catalog is not None:
            self.download_candidates = self._discover_missing(local_files, result, usable_catalog)
        result.download_candidates = list(self.download_candidates)
        result.discovery_error = self.discovery_error

        if catalog_error:
            self.logger.warning("UPDATE aborted: server catalog unavailable: %s", catalog_error)
            return result, 0, 1, f"Update aborted: server catalog unavailable. {catalog_error}"

        catalog_by_payload = {entry.payload: entry for entry in usable_catalog or []}
        update_results = self.updater.update_rows(result.rows, catalog_by_payload)
        successful = [item for item in update_results if item.success and item.new_checksum]
        failed = [item for item in update_results if not item.success]

        # Reconcile first. The ordinary ps5upload update may have made the prerequisite
        # CURRENT during this same operation, which the control-app policy gate observes.
        final_result = self.perform_scan()
        control_app_updated = False
        control_app_failed = False
        control_row = next(
            (row for row in final_result.rows if row.catalog_payload == "__control_app__"),
            None,
        )
        if control_row is not None and control_row.status == UPDATE_AVAILABLE:
            try:
                if not self._control_app_download_allowed(final_result):
                    self.logger.info(
                        "Control-app update deferred by configuration: ps5upload is not CURRENT"
                    )
                elif self.ps5upload_control_app_module is None:
                    raise RuntimeError("Control-app module is unavailable")
                else:
                    self.logger.info("Control-app update delegated to its dedicated module")
                    self.ps5upload_control_app_module.ensure_client(
                        self.last_catalog or usable_catalog or []
                    )
                    control_app_updated = True
                    self.logger.info("Control-app update completed")
            except Exception:
                # A broken or failed optional module must not undo or crash the main
                # updater after ordinary payload updates have already completed.
                control_app_failed = True
                self.logger.exception(
                    "Control-app update failed; continuing with ordinary payload results"
                )

        if control_app_updated or control_app_failed:
            # Refresh row, folder name, version, and persisted state after an attempted
            # install. The row-integration boundary catches control-app-specific faults.
            final_result = self.perform_scan()

        if successful:
            completed_at = datetime.now().astimezone().replace(microsecond=0).isoformat(sep=" ")
            successful_checksums = {
                item.new_checksum.lower() for item in successful if item.new_checksum
            }
            for record in final_result.state_records:
                if record.curr_checksum.lower() in successful_checksums:
                    record.last_updated = completed_at
            self.state.save(final_result.state_records)
            self.logger.info("Recorded LastUpdated for %d successful payload update(s)", len(successful))

        successful_count = len(successful) + int(control_app_updated)
        failed_count = len(failed) + int(control_app_failed)
        self.logger.info(
            "UPDATE operation completed: successful=%d failed=%d",
            successful_count, failed_count,
        )
        final_result.download_candidates = list(self.download_candidates)
        final_result.discovery_error = self.discovery_error
        self.result = final_result
        return final_result, successful_count, failed_count, None

    def _discover_missing(self, local_files, result: ScanResult, catalog: list[PayloadEntry]) -> list[PayloadEntry]:
        """Delegate the pure missing-payload selection rules."""
        return discover_missing_payloads(local_files, result, catalog)

    def _fetch_catalog(self):
        try:
            return self.catalog.fetch(), None
        except PayloadCatalogError as exc:
            return None, str(exc)

    def _reconcile_and_save(self, local_files, state_records, catalog, catalog_error) -> ScanResult:
        result = self.reconciler.reconcile(
            local_files=local_files,
            state_records=state_records,
            catalog=catalog,
            catalog_error=catalog_error,
        )
        self.state.save(result.state_records)
        return result

    def run(self) -> None:
        """Build the GUI and perform initial local/server discovery."""
        result = self.perform_scan()
        window = MainWindow(
            result=result,
            title=self.config.window_title,
            repository_url=self.config.repository_url,
            update_callback=self.perform_update,
            pre_release_callback=self.set_pre_release,
            download_candidates=list(self.download_candidates),
            discovery_error=self.discovery_error,
            download_callback=self.perform_download,
            folder_scan_callback=self.perform_folder_scan,
            control_app_download_callback=self.perform_control_app_download,
        )
        window.run()
