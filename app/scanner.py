"""Filesystem scanning and SHA-256 calculation."""

import hashlib
from pathlib import Path

from app.models import LocalFile


class FileScanner:
    """Find ELF files and calculate their SHA-256 checksums."""

    CHUNK_SIZE = 1024 * 1024

    def scan(self, directory: Path) -> list[LocalFile]:
        """Return ELF files directly inside the supplied directory."""
        # Only the application's working directory is scanned; subdirectories such as
        # _OLD are deliberately excluded from the v1 current-file scan.
        return [
            LocalFile(filename=path.name, path=str(path))
            for path in sorted(directory.glob("*.elf"), key=lambda p: p.name.lower())
            if path.is_file()
        ]

    def hash_files(self, files: list[LocalFile]) -> list[LocalFile]:
        """Calculate SHA-256 for each local file."""
        # Hash files independently so one inaccessible/corrupt file does not prevent
        # the remaining payloads from being processed.
        for local_file in files:
            try:
                local_file.checksum = self._sha256(Path(local_file.path))
            except OSError as exc:
                local_file.hash_error = str(exc)
        return files

    def _sha256(self, path: Path) -> str:
        """Calculate a SHA-256 digest using bounded memory."""
        digest = hashlib.sha256()

        # Read incrementally instead of loading potentially large ELF files into memory.
        with path.open("rb") as handle:
            while chunk := handle.read(self.CHUNK_SIZE):
                digest.update(chunk)

        return digest.hexdigest()
