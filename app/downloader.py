"""Download missing payloads directly from their source_direct URLs."""

import logging
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.models import PayloadEntry
from app.updater import UpdateError, UpdateManager


class Downloader:
    """Safely install a missing ELF without overwriting any existing file."""

    def __init__(self, base_dir: Path, transfer: UpdateManager) -> None:
        self.base_dir = base_dir
        self.transfer = transfer
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def filename_from_url(url: str, entry: PayloadEntry | None = None) -> str:
        """Extract the URL filename; for declared archives use the ELF member name."""
        path = urlsplit(url).path
        raw_name = path.rsplit("/", 1)[-1]
        filename = unquote(raw_name)
        if not filename or filename in {".", ".."}:
            raise UpdateError("source_direct URL does not contain a filename")
        if Path(filename).suffix.lower() == ".elf":
            return Downloader._validate_server_filename(filename)
        # Some catalog objects point source_direct at a ZIP and declare extract_file.
        # The archive itself is not an ELF and must not be left in the payload folder;
        # preserve the server-provided ELF member filename after verified extraction.
        if entry is not None and entry.extract_file:
            member_name = unquote(entry.extract_file.replace("\\", "/").rsplit("/", 1)[-1])
            return Downloader._validate_server_filename(member_name)
        raise UpdateError("source_direct URL does not identify an ELF filename")

    @staticmethod
    def _validate_server_filename(filename: str) -> str:
        """Reject filenames unsafe or invalid on Windows while preserving valid names."""
        UpdateManager._validate_filename(filename)
        if any(ord(char) < 32 or char in '<>:"/\\|?*' for char in filename):
            raise UpdateError("source_direct filename contains characters invalid on Windows")
        if filename.endswith((" ", ".")):
            raise UpdateError("source_direct filename cannot end with a space or period")
        reserved = {"CON", "PRN", "AUX", "NUL"} | {
            f"COM{i}" for i in range(1, 10)
        } | {f"LPT{i}" for i in range(1, 10)}
        if Path(filename).stem.upper() in reserved:
            raise UpdateError("source_direct filename is reserved by Windows")
        return filename

    def download(self, entry: PayloadEntry) -> tuple[str, str]:
        """Download, checksum-verify, and atomically create the URL-named ELF."""
        if not entry.source_direct:
            raise UpdateError("source_direct is missing")

        self.transfer._validate_source_url(entry.source_direct)
        filename = self.filename_from_url(entry.source_direct, entry)
        target = self.base_dir / filename
        if target.exists():
            raise UpdateError(f"A file named {filename} already exists; refusing to overwrite it")

        downloaded: Path | None = None
        verified: Path | None = None
        installed = False
        try:
            downloaded = self.transfer._download_to_temp(entry.source_direct)
            verified = self.transfer._prepare_verified_payload(downloaded, entry)
            actual_checksum = self.transfer._sha256(verified)
            expected_checksum = entry.checksum.lower()
            if actual_checksum != expected_checksum:
                raise UpdateError("Downloaded payload checksum does not match ServerChecksum")

            # A hard link creates the destination atomically and fails if it already
            # exists. Temporary files are created beside the destination, so they are
            # on the same filesystem. No existing file can be overwritten.
            try:
                os.link(verified, target)
            except FileExistsError as exc:
                raise UpdateError(
                    f"A file named {filename} appeared during download; refusing to overwrite it"
                ) from exc
            except OSError as exc:
                # On filesystems where hard links are unavailable, exclusive creation
                # still guarantees that an existing destination is never overwritten.
                try:
                    with target.open("xb") as destination, verified.open("rb") as source:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            destination.write(chunk)
                        destination.flush()
                        os.fsync(destination.fileno())
                except FileExistsError as exists_exc:
                    raise UpdateError(
                        f"A file named {filename} appeared during download; refusing to overwrite it"
                    ) from exists_exc
                except Exception:
                    try:
                        target.unlink()
                    except OSError:
                        pass
                    raise exc

            installed = True
            final_checksum = self.transfer._sha256(target)
            if final_checksum != expected_checksum:
                target.unlink(missing_ok=True)
                installed = False
                raise UpdateError("Final file checksum verification failed")

            self.logger.info(
                "Downloaded payload %s as %s with verified SHA-256 %s",
                entry.payload,
                filename,
                final_checksum,
            )
            return filename, final_checksum
        finally:
            # If post-install verification fails, remove only the file this operation
            # created. Existing files are never touched.
            if installed and target.exists():
                try:
                    if self.transfer._sha256(target) != entry.checksum.lower():
                        target.unlink(missing_ok=True)
                except OSError:
                    self.logger.exception("Unable to verify installed download %s", target)
            for temporary in {p for p in (downloaded, verified) if p is not None}:
                try:
                    if temporary.exists() and temporary.is_file():
                        temporary.unlink()
                except OSError:
                    self.logger.warning("Unable to remove temporary download %s", temporary)
