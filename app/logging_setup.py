"""Application logging."""

import logging
from pathlib import Path


def configure_logging(log_path: Path, level: int = logging.INFO) -> None:
    """Configure a compact file log for operational diagnostics."""
    # Logging is kept separate from GUI status so failures remain diagnosable after
    # the application closes.
    logging.basicConfig(
        filename=log_path,
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
    )
