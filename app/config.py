"""Application configuration."""

from pathlib import Path


class AppConfig:
    """Stable application paths and remote catalog configuration."""

    APP_VERSION = "1.9.5"
    APP_NAME = "Folder updater for itsplk PS5 Payloads Mirror"
    REPOSITORY_URL = "https://github.com/itsPLK/ps5-payloads-mirror"
    PAYLOADS_URL = "https://itsplk.github.io/ps5-payloads-mirror/payloads.json"
    WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"
    STATE_FILENAME = "local-state.json"
    LOG_FILENAME = "application.log"

    def __init__(self, base_dir: Path) -> None:
        # Keep payload files beside the application while persistent app data lives in appdata.
        self.base_dir = base_dir
        self.appdata_dir = self.base_dir / "appdata"

    @property
    def payloads_url(self) -> str:
        return self.PAYLOADS_URL

    @property
    def window_title(self) -> str:
        return self.WINDOW_TITLE

    @property
    def repository_url(self) -> str:
        return self.REPOSITORY_URL

    @property
    def state_path(self) -> Path:
        return self.appdata_dir / self.STATE_FILENAME

    @property
    def log_path(self) -> Path:
        return self.appdata_dir / self.LOG_FILENAME
