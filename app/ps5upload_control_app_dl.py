"""Standalone, platform-configurable downloader for the ps5upload control app."""

import hashlib
import ipaddress
import logging
import os
import shutil
import socket
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.models import PayloadEntry, StateRecord
from app.state_repository import StateRepository
from app.user_config import UserConfig


class ControlAppDownloadError(Exception):
    """Raised when the standalone control-app download cannot complete safely."""


class _NoRedirect(HTTPRedirectHandler):
    """Expose redirects so each destination can be validated before following it."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Ps5uploadControlAppDL:
    """Download and track the control-app asset without using the ELF Downloader."""

    RECORD_TYPE = "control-app"
    TIMEOUT_SECONDS = 30
    MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
    MAX_MEMBERS = 10000
    USER_AGENT = "Folder-updater-ps5upload-control-app/1.9.4"
    MAX_REDIRECTS = 8

    def __init__(self, base_dir: Path, state: StateRepository, config: UserConfig) -> None:
        self.base_dir = base_dir
        self.state = state
        self.config = config
        self.logger = logging.getLogger(__name__)

    def derived_names(self, entry: PayloadEntry) -> tuple[str, str]:
        if entry.payload != "ps5upload":
            raise ControlAppDownloadError("Catalog entry is not ps5upload")
        if not entry.source_direct or not entry.filename:
            raise ControlAppDownloadError("ps5upload source_direct or filename is missing")
        try:
            platform = self.config.platform_suffix
        except ValueError as exc:
            raise ControlAppDownloadError(str(exc)) from exc
        ps5upload_elf_link = entry.source_direct
        ps5upload_elf_filename = entry.filename
        ps5upload_control_app_link = ps5upload_elf_link.removesuffix(".elf") + "-" + platform
        ps5upload_control_app_filename = ps5upload_elf_filename.removesuffix(".elf") + "-" + platform
        self._validate_filename(ps5upload_control_app_filename)
        return ps5upload_control_app_link, ps5upload_control_app_filename

    def describe_client(
        self, catalog: list[PayloadEntry]
    ) -> tuple[PayloadEntry, str, str, str, bool] | None:
        """Resolve the configured control-app asset without downloading or writing state."""
        entry = next((item for item in reversed(catalog) if item.payload == "ps5upload"), None)
        if entry is None:
            return None
        asset_url, asset_filename = self.derived_names(entry)
        is_zip = asset_filename.lower().endswith(".zip")
        install_name = asset_filename[:-4] if is_zip else asset_filename
        return entry, asset_url, asset_filename, install_name, is_zip

    def discover_existing_client(self, catalog: list[PayloadEntry]) -> StateRecord | None:
        """Track an already-present control-app asset without initiating a download."""
        description = self.describe_client(catalog)
        if description is None:
            return next((item for item in self.state.load() if item.record_type == self.RECORD_TYPE), None)

        entry, _asset_url, _asset_filename, install_name, is_zip = description
        expected_path = self.base_dir / install_name
        expected_exists = expected_path.is_dir() if is_zip else expected_path.is_file()
        records = self.state.load()
        record = next((item for item in records if item.record_type == self.RECORD_TYPE), None)

        # Prefer the previously tracked path if it is still present. This avoids
        # silently changing the canonical local filename when Platform changes.
        if record is not None and record.curr_dir_filename:
            tracked_path = self.base_dir / record.curr_dir_filename
            if tracked_path.exists():
                return record

        if not expected_exists:
            return record

        now = datetime.now().astimezone().replace(microsecond=0).isoformat(sep=" ")
        if record is None:
            record = StateRecord(
                payload=install_name,
                curr_dir_filename=install_name,
                curr_dir_file_version=entry.version,
                curr_checksum="",
                first_seen=now,
                last_seen=now,
                pre_release=False,
                record_type=self.RECORD_TYPE,
            )
            records.append(record)
        else:
            record.payload = install_name
            record.curr_dir_filename = install_name
            record.record_type = self.RECORD_TYPE
            record.curr_dir_file_version = entry.version
            record.last_seen = now
            if not record.first_seen:
                record.first_seen = now
        self.state.save(records)
        return record

    def ensure_client(self, catalog: list[PayloadEntry]) -> str:
        """Download/install the configured asset; call only after explicit user action."""
        description = self.describe_client(catalog)
        if description is None:
            self.logger.info("Control-app download skipped: ps5upload was not found in catalog")
            return "ps5upload is not present in the server catalog"

        entry, asset_url, ps5upload_control_app_filename, install_name, is_zip = description
        target_path = self.base_dir / install_name
        records = self.state.load()
        record = next((item for item in records if item.record_type == self.RECORD_TYPE), None)
        asset_checksum: str | None = None

        if is_zip and target_path.is_dir():
            self.logger.info("Control-app directory already exists: %s", install_name)
        elif not is_zip and target_path.is_file():
            self.logger.info("Control-app asset already exists: %s", install_name)
        elif target_path.exists():
            raise ControlAppDownloadError(f"Expected control-app path exists with an incompatible type: {install_name}")
        else:
            download_path: Path | None = None
            installed = False
            try:
                download_path, asset_checksum = self._download_asset(asset_url, ps5upload_control_app_filename)
                if is_zip:
                    self._extract_archive(download_path, install_name)
                    if not target_path.is_dir() or not any(target_path.iterdir()):
                        raise ControlAppDownloadError(f"ZIP extraction did not create a usable directory: {install_name}")
                    installed = True
                else:
                    # Exclusive hard-link install prevents overwriting an existing asset.
                    try:
                        os.link(download_path, target_path)
                    except FileExistsError as exc:
                        raise ControlAppDownloadError(f"Control-app asset already exists; refusing to overwrite: {install_name}") from exc
                    except OSError:
                        with target_path.open("xb") as output, download_path.open("rb") as source:
                            shutil.copyfileobj(source, output)
                    if self._sha256(target_path) != asset_checksum:
                        target_path.unlink(missing_ok=True)
                        raise ControlAppDownloadError("Final control-app asset checksum verification failed")
                    installed = True
                self.logger.info("Control-app asset %s installed; SHA-256=%s", ps5upload_control_app_filename, asset_checksum)
            except Exception:
                if is_zip and target_path.is_dir():
                    shutil.rmtree(target_path, ignore_errors=True)
                raise
            finally:
                # Keep a failed ZIP archive for diagnostics/retry. Successful ZIPs are
                # removed only after extraction and output verification succeed.
                if download_path is not None:
                    if is_zip and installed:
                        try:
                            download_path.unlink(missing_ok=True)
                        except OSError:
                            self.logger.warning("Could not delete verified control-app ZIP: %s", download_path)
                    elif not is_zip:
                        try:
                            download_path.unlink(missing_ok=True)
                        except OSError:
                            self.logger.warning("Could not delete temporary control-app asset: %s", download_path)
                    else:
                        self.logger.error("Control-app extraction failed; ZIP retained at %s", download_path)

        now = datetime.now().astimezone().replace(microsecond=0).isoformat(sep=" ")
        if record is None:
            record = StateRecord(
                payload=install_name,
                curr_dir_filename=install_name,
                curr_dir_file_version=entry.version,
                curr_checksum=asset_checksum or "",
                first_seen=now,
                last_seen=now,
                last_updated=None,
                pre_release=False,
                record_type=self.RECORD_TYPE,
            )
            records.append(record)
        else:
            record.payload = install_name
            record.curr_dir_filename = install_name
            record.record_type = self.RECORD_TYPE
            record.curr_dir_file_version = entry.version
            if asset_checksum is not None:
                record.curr_checksum = asset_checksum
            if not record.first_seen:
                record.first_seen = now
            record.last_seen = now
        self.state.save(records)
        return f"Control app ready: {install_name}"

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ControlAppDownloadError("Control-app URL must be a valid HTTPS URL")
        if parsed.port not in (None, 443):
            raise ControlAppDownloadError("Control-app URL must use the default HTTPS port")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise ControlAppDownloadError(f"Unable to resolve control-app host {parsed.hostname}: {exc}") from exc
        if not addresses:
            raise ControlAppDownloadError(f"Control-app host {parsed.hostname} resolved to no addresses")
        hostname = parsed.hostname.lower().rstrip(".")
        github_owned_host = (
            hostname == "github.com"
            or hostname.endswith(".github.com")
            or hostname.endswith(".githubusercontent.com")
        )
        synthetic_range = ipaddress.ip_network("198.18.0.0/15")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip in synthetic_range:
                self.logger.info("Allowing synthetic DNS response for %s: %s", hostname, ip)
            elif not ip.is_global and github_owned_host:
                self.logger.warning(
                    "Allowing non-public DNS response for GitHub-owned control-app host %s: %s; HTTPS certificate validation remains enabled",
                    hostname, ip,
                )
            elif not ip.is_global:
                raise ControlAppDownloadError(
                    f"Control-app host {hostname} resolved to a non-public address ({ip}); refusing the connection"
                )

    def _download_asset(self, url: str, filename: str) -> tuple[Path, str]:
        """Download a bounded asset, validating every HTTPS redirect before following it."""
        current_url = url
        self._validate_url(current_url)
        suffix = Path(filename).suffix or ".download"
        fd, temp_name = tempfile.mkstemp(prefix="ps5upload-control-app-", suffix=suffix, dir=self.base_dir)
        temp_path = Path(temp_name)
        digest = hashlib.sha256()
        completed = False
        try:
            for redirect_count in range(self.MAX_REDIRECTS + 1):
                self._validate_url(current_url)
                request = Request(current_url, headers={"User-Agent": self.USER_AGENT}, method="GET")
                try:
                    response = build_opener(_NoRedirect()).open(request, timeout=self.TIMEOUT_SECONDS)
                except HTTPError as exc:
                    if exc.code in {301, 302, 303, 307, 308}:
                        location = exc.headers.get("Location")
                        if not location:
                            raise ControlAppDownloadError("Redirect response has no Location header") from exc
                        if redirect_count >= self.MAX_REDIRECTS:
                            raise ControlAppDownloadError("Control-app download exceeded redirect limit") from exc
                        next_url = urljoin(current_url, location)
                        # Validate scheme, credentials, port and every resolved address
                        # before the next network request. Never permit HTTPS downgrade.
                        self._validate_url(next_url)
                        current_url = next_url
                        continue
                    raise ControlAppDownloadError(f"HTTP {exc.code} downloading control-app asset") from exc
                except URLError as exc:
                    raise ControlAppDownloadError(f"Network error downloading control-app asset: {exc.reason}") from exc
                with response:
                    final = urlsplit(response.geturl())
                    if final.scheme.lower() != "https":
                        raise ControlAppDownloadError("Control-app download redirected away from HTTPS")
                    if response.status != 200:
                        raise ControlAppDownloadError(f"HTTP {response.status} downloading control-app asset")
                    with os.fdopen(fd, "wb") as output:
                        fd = -1
                        total = 0
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > self.MAX_DOWNLOAD_BYTES:
                                raise ControlAppDownloadError("Control-app asset exceeds the 512 MiB size limit")
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                if total == 0:
                    raise ControlAppDownloadError("Downloaded control-app asset is empty")
                completed = True
                return temp_path, digest.hexdigest()
            raise ControlAppDownloadError("Control-app download exceeded redirect limit")
        except Exception:
            if fd >= 0:
                os.close(fd)
            # Preserve a complete ZIP if extraction later fails; remove incomplete network transfers.
            if not completed:
                temp_path.unlink(missing_ok=True)
            raise

    def _extract_archive(self, archive: Path, expected_folder: str) -> None:
        destination = self.base_dir.resolve()
        target_dir = destination / expected_folder
        with zipfile.ZipFile(archive, "r") as zf:
            members = zf.infolist()
            if not members or len(members) > self.MAX_MEMBERS:
                raise ControlAppDownloadError("Control-app ZIP has an invalid number of entries")
            total_uncompressed = 0
            plan: list[tuple[zipfile.ZipInfo, Path | None]] = []
            target_resolved = target_dir.resolve()
            for info in members:
                name = info.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or not path.parts or any(":" in part or part.endswith((" ", ".")) for part in path.parts) or any(any(ord(c) < 32 for c in part) for part in path.parts):
                    raise ControlAppDownloadError("Control-app ZIP contains an unsafe path")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ControlAppDownloadError("Control-app ZIP contains a symbolic link")
                total_uncompressed += info.file_size
                if total_uncompressed > self.MAX_DOWNLOAD_BYTES * 4:
                    raise ControlAppDownloadError("Control-app ZIP expands beyond the safety limit")
                parts = path.parts
                if parts[0] == expected_folder:
                    parts = parts[1:]
                if not parts:
                    plan.append((info, None))
                    continue
                output_path = target_resolved.joinpath(*parts).resolve()
                if output_path != target_resolved and target_resolved not in output_path.parents:
                    raise ControlAppDownloadError("Control-app ZIP extraction path escapes the target directory")
                plan.append((info, output_path))
            target_dir.mkdir(parents=True, exist_ok=False)
            for info, output_path in plan:
                if output_path is None:
                    continue
                if info.is_dir() or info.filename.endswith(("/", "\\")):
                    output_path.mkdir(parents=True, exist_ok=True)
                    continue
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as source, output_path.open("xb") as output:
                    shutil.copyfileobj(source, output)

    @staticmethod
    def _validate_filename(filename: str) -> str:
        if not filename or Path(filename).name != filename or filename in {".", ".."}:
            raise ControlAppDownloadError("Control-app asset filename is unsafe")
        if any(ord(c) < 32 or c in '<>:"/\\|?*' for c in filename) or filename.endswith((" ", ".")):
            raise ControlAppDownloadError("Control-app asset filename contains invalid characters")
        if Path(filename).stem.upper() in ({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}):
            raise ControlAppDownloadError("Control-app asset filename is reserved on Windows")
        return filename

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
