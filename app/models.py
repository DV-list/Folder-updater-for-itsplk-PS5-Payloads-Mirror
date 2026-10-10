"""Application data models."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LocalFile:
    """A currently discovered ELF file."""

    filename: str
    path: str
    checksum: Optional[str] = None
    hash_error: Optional[str] = None


@dataclass
class PayloadEntry:
    """Relevant fields extracted from one payloads.json object."""

    payload: str
    filename: str
    version: str
    checksum: str
    source_direct: Optional[str] = None
    extract_file: Optional[str] = None


@dataclass
class StateRecord:
    """One historical observation of a local checksum."""

    payload: Optional[str]
    curr_dir_filename: str
    curr_dir_file_version: Optional[str]
    curr_checksum: str
    first_seen: str
    last_seen: str
    last_updated: Optional[str] = None
    pre_release: bool = False
    catalog_payload: Optional[str] = None
    record_type: Optional[str] = None


@dataclass
class RowResult:
    """One row displayed by the GUI."""

    payload: Optional[str]
    filename: str
    curr_checksum: Optional[str]
    curr_file_version: Optional[str]
    curr_file_added_date: Optional[str]
    server_version: Optional[str]
    server_checksum: Optional[str]
    status: str
    pre_release: bool = False
    catalog_payload: Optional[str] = None


@dataclass
class ScanResult:
    """Complete output of one reconciliation cycle."""

    rows: list[RowResult]
    state_records: list[StateRecord]
    catalog_error: Optional[str] = None
    scanned_files: int = 0
    current_count: int = 0
    update_count: int = 0
    unmatched_count: int = 0
    removed_count: int = 0
    download_candidates: list[PayloadEntry] = field(default_factory=list)
    discovery_error: Optional[str] = None


@dataclass
class UpdateResult:
    """Outcome of one attempted payload update."""

    payload: str
    success: bool
    new_checksum: Optional[str] = None
    error: Optional[str] = None
