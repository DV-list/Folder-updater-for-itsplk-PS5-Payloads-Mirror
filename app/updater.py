"""Secure download, verification, archival, and replacement of payload files."""

import hashlib
import ipaddress
import logging
import os
import shutil
import socket
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.models import PayloadEntry, RowResult, UpdateResult


class UpdateError(Exception):
    """Raised for an unsafe or unsuccessful update operation."""


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent urllib from silently following an unsafe redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UpdateManager:
    """Download, verify, archive, and port one or more payload updates."""

    TIMEOUT_SECONDS = 30
    MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
    USER_AGENT = "Folder-updater/1.9.7"
    MAX_REDIRECTS = 5

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.old_dir = base_dir / "_OLD"
        self.logger = logging.getLogger(__name__)

    def update_rows(
        self,
        rows: list[RowResult],
        catalog_by_payload: dict[str, PayloadEntry],
    ) -> list[UpdateResult]:
        """Update every row that is currently classified as UPDATE AVAILABLE."""
        results: list[UpdateResult] = []

        # Each payload is isolated so a failed download or verification does not
        # prevent other independently valid updates from being attempted.
        for row in rows:
            # The control app has a dedicated download/update path; it is not an ELF
            # catalog entry and must never be passed through the generic Porter.
            if row.catalog_payload == "__control_app__":
                continue
            if row.status != "UPDATE AVAILABLE" or not row.payload:
                continue

            entry = catalog_by_payload.get(row.catalog_payload or row.payload)
            if entry is None:
                results.append(
                    UpdateResult(
                        payload=row.payload,
                        success=False,
                        error="Payload is no longer present in the refreshed catalog",
                    )
                )
                continue

            try:
                checksum = self._update_one(row, entry)
                results.append(
                    UpdateResult(
                        payload=row.payload,
                        success=True,
                        new_checksum=checksum,
                    )
                )
            except (UpdateError, OSError) as exc:
                self.logger.error("Update failed for %s: %s", row.payload, exc)
                results.append(
                    UpdateResult(
                        payload=row.payload,
                        success=False,
                        error=str(exc),
                    )
                )

        return results

    def _update_one(self, row: RowResult, entry: PayloadEntry) -> str:
        """Download and port one verified payload without overwriting old history."""
        target_name = self._validate_filename(entry.filename)
        if not entry.source_direct:
            raise UpdateError("source_direct is missing")
        self._validate_source_url(entry.source_direct)

        current_path = self.base_dir / row.filename
        if not current_path.is_file():
            raise UpdateError(f"Current ELF file is missing: {row.filename}")

        downloaded_path = self._download_to_temp(entry.source_direct)
        verified_payload = self._prepare_verified_payload(downloaded_path, entry)

        try:
            downloaded_checksum = self._sha256(verified_payload)
            expected_checksum = entry.checksum.lower()
            if downloaded_checksum != expected_checksum:
                raise UpdateError(
                    "Downloaded payload checksum does not match ServerChecksum"
                )

            self.old_dir.mkdir(parents=True, exist_ok=True)
            current_archive = self._unique_archive_path(current_path.name)
            target_path = self.base_dir / target_name
            target_archive: Path | None = None

            # Preserve the current file before changing anything in the live folder.
            shutil.move(str(current_path), str(current_archive))

            try:
                # If the server target filename differs from the current filename and
                # already exists, preserve it as well instead of overwriting it.
                if target_path.exists():
                    target_archive = self._unique_archive_path(target_path.name)
                    shutil.move(str(target_path), str(target_archive))

                shutil.copy2(verified_payload, target_path)

                # Verify the file at its final path, not only the temporary download.
                final_checksum = self._sha256(target_path)
                if final_checksum != expected_checksum:
                    raise UpdateError("Final file checksum verification failed")

            except Exception:
                # Restore the original current file and any displaced target if the
                # Porter/final-verification stage fails.
                try:
                    if target_path.exists():
                        target_path.unlink()
                except OSError:
                    self.logger.exception("Unable to remove failed target %s", target_path)

                if target_archive and target_archive.exists() and not target_path.exists():
                    try:
                        shutil.move(str(target_archive), str(target_path))
                    except OSError:
                        self.logger.exception("Unable to restore displaced target %s", target_path)

                if current_archive.exists() and not current_path.exists():
                    try:
                        shutil.move(str(current_archive), str(current_path))
                    except OSError:
                        self.logger.exception("Unable to restore original file %s", current_path)
                raise

            return final_checksum
        finally:
            for temporary in {downloaded_path, verified_payload}:
                try:
                    if temporary.exists() and temporary.is_file():
                        temporary.unlink()
                except OSError:
                    self.logger.warning("Unable to remove temporary file %s", temporary)

    @staticmethod
    def _safe_url(url: str) -> str:
        """Return an HTTP URL without query parameters or fragments."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def _download_to_temp(self, url: str) -> Path:
        """Download an HTTPS URL to a bounded temporary file."""
        current_url = url
        opener = build_opener(_NoRedirectHandler())

        fd, temporary_name = tempfile.mkstemp(
            prefix="ps5_payload_update_",
            suffix=".download",
            dir=self.base_dir,
        )
        os.close(fd)
        temporary_path = Path(temporary_name)

        try:
            for _ in range(self.MAX_REDIRECTS + 1):
                self._validate_source_url(current_url)
                request = Request(
                    current_url,
                    headers={"User-Agent": self.USER_AGENT},
                    method="GET",
                )
                self.logger.debug("HTTP request starting: GET %s", self._safe_url(current_url))
                try:
                    response = opener.open(request, timeout=self.TIMEOUT_SECONDS)
                except HTTPError as exc:
                    self.logger.debug("HTTP error response: status=%s url=%s", exc.code, self._safe_url(current_url))
                    if exc.code in {301, 302, 303, 307, 308}:
                        location = exc.headers.get("Location")
                        if not location:
                            raise UpdateError("Redirect response has no Location header")
                        current_url = urljoin(current_url, location)
                        self.logger.debug("HTTP redirect received; next URL=%s", self._safe_url(current_url))
                        # The next loop iteration validates the complete redirect URL
                        # and resolves its hostname before making another request.
                        continue
                    raise UpdateError(f"HTTP {exc.code} while downloading payload") from exc
                except URLError as exc:
                    raise UpdateError(f"Network error while downloading payload: {exc.reason}") from exc
                except OSError as exc:
                    raise UpdateError(f"Unable to download payload: {exc}") from exc

                with response:
                    self.logger.debug(
                        "HTTP response: status=%s content_type=%s content_length=%s url=%s",
                        response.status,
                        response.headers.get("Content-Type"),
                        response.headers.get("Content-Length"),
                        self._safe_url(current_url),
                    )
                    if response.status != 200:
                        raise UpdateError(f"HTTP {response.status} while downloading payload")

                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise UpdateError("Invalid Content-Length from download server") from exc
                        if declared_size > self.MAX_DOWNLOAD_BYTES:
                            raise UpdateError("Downloaded payload exceeds the size limit")

                    total = 0
                    with temporary_path.open("wb") as handle:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > self.MAX_DOWNLOAD_BYTES:
                                raise UpdateError("Downloaded payload exceeds the size limit")
                            handle.write(chunk)
                        handle.flush()
                        os.fsync(handle.fileno())
                    self.logger.debug("HTTP download completed: bytes=%s url=%s", total, self._safe_url(current_url))
                    return temporary_path

            raise UpdateError("Too many HTTPS redirects")
        except Exception:
            try:
                temporary_path.unlink()
            except OSError:
                pass
            raise

    def _prepare_verified_payload(self, downloaded_path: Path, entry: PayloadEntry) -> Path:
        """Return the actual ELF payload, extracting a declared archive member when needed."""
        if not entry.extract_file:
            return downloaded_path

        # The current catalog uses extract_file for archive-based source_direct assets.
        # Only ZIP archives are supported here because they are handled by the standard
        # library and allow strict member-path validation without external utilities.
        if not zipfile.is_zipfile(downloaded_path):
            raise UpdateError("source_direct declares extract_file but is not a ZIP archive")

        member = self._validate_archive_member(entry.extract_file)
        fd, extracted_name = tempfile.mkstemp(
            prefix="ps5_payload_extracted_",
            suffix=".elf",
            dir=self.base_dir,
        )
        os.close(fd)
        extracted_path = Path(extracted_name)

        try:
            with zipfile.ZipFile(downloaded_path, "r") as archive:
                names = archive.namelist()
                if member not in names:
                    raise UpdateError(f"extract_file was not found in archive: {member}")
                info = archive.getinfo(member)
                if info.is_dir():
                    raise UpdateError("extract_file points to a directory")
                if info.file_size > self.MAX_DOWNLOAD_BYTES:
                    raise UpdateError("Extracted payload exceeds the size limit")

                with archive.open(info, "r") as source, extracted_path.open("wb") as target:
                    total = 0
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.MAX_DOWNLOAD_BYTES:
                            raise UpdateError("Extracted payload exceeds the size limit")
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
            return extracted_path
        except Exception:
            try:
                extracted_path.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def _validate_archive_member(member: str) -> str:
        """Reject ZIP member traversal and absolute paths."""
        normalized = member.replace("\\", "/")
        path = Path(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise UpdateError("extract_file contains an unsafe archive path")
        return normalized

    def _validate_source_url(self, url: str) -> None:
        """Require an HTTPS public host without embedded credentials."""
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise UpdateError("source_direct must use HTTPS")
        if not parsed.hostname:
            raise UpdateError("source_direct has no hostname")
        if parsed.username or parsed.password:
            raise UpdateError("source_direct must not contain credentials")
        if parsed.port not in (None, 443):
            raise UpdateError("source_direct must use the default HTTPS port")

        # Resolve the host and reject local/private destinations to reduce SSRF risk.
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise UpdateError(f"Unable to resolve source_direct host: {exc}") from exc

        if not addresses:
            raise UpdateError("source_direct hostname resolved to no addresses")

        hostname = parsed.hostname.lower().rstrip(".")
        github_owned_host = (
            hostname == "github.com"
            or hostname.endswith(".github.com")
            or hostname.endswith(".githubusercontent.com")
        )
        for address in addresses:
            ip = ipaddress.ip_address(address)
            # Some private DNS filters synthesize RFC 2544 benchmarking addresses
            # (198.18.0.0/15) for otherwise valid public hosts. Permit only that
            # specific synthetic range for general hosts.
            synthetic_dns_range = ipaddress.ip_network("198.18.0.0/15")
            if ip in synthetic_dns_range:
                self.logger.info("Allowing synthetic DNS response for %s: %s", hostname, ip)
                continue
            # GitHub release URLs redirect to GitHub-owned asset hosts. Some managed
            # DNS/proxy environments return private sinkhole addresses for these names,
            # even though the HTTPS URL works in a browser. Permit that narrow domain
            # allowlist only; urllib still performs normal TLS certificate validation,
            # and arbitrary hosts resolving privately remain blocked.
            if not ip.is_global and github_owned_host:
                self.logger.warning(
                    "Allowing non-public DNS response for GitHub-owned download host %s: %s; HTTPS certificate validation remains enabled",
                    hostname, ip,
                )
                continue
            if not ip.is_global:
                raise UpdateError(
                    f"source_direct host {parsed.hostname} resolved to a non-public address ({ip})"
                )

    @staticmethod
    def _validate_filename(filename: str) -> str:
        """Allow only a simple ELF filename because the working directory is ELF-only."""
        path = Path(filename)
        if not filename or path.name != filename or path.suffix.lower() != ".elf":
            raise UpdateError("Server filename is not a safe ELF filename")
        if filename in {".", ".."} or any(part in {".", ".."} for part in path.parts):
            raise UpdateError("Server filename contains an invalid path component")
        return filename

    def _unique_archive_path(self, filename: str) -> Path:
        """Return a non-existing _OLD path without overwriting history."""
        candidate = self.old_dir / filename
        if not candidate.exists():
            return candidate

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = candidate.stem
        suffix = candidate.suffix
        candidate = self.old_dir / f"{stem}__{stamp}{suffix}"
        counter = 1
        while candidate.exists():
            candidate = self.old_dir / f"{stem}__{stamp}_{counter}{suffix}"
            counter += 1
        return candidate

    @staticmethod
    def _sha256(path: Path) -> str:
        """Calculate SHA-256 using bounded memory."""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
