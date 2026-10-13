"""User-editable config.ini settings, including support for // comment lines."""

import configparser
import logging
import shutil
from pathlib import Path

DEFAULT_CONFIG = '''[General]\nLOG_LEVEL = 0\n// 0 - Default; 1 - extended logs for HTTP and parsing\n\n[ps5upload-control-app-dl]\nEnabled = true\nPlatform = default\nDownloadOnlyWhenPS5UploadCurrent = true\n\n// Other values must match an asset suffix published by the PS5Upload project.\n// To get PS5Upload client for other platforms - values must match an asset suffix on:\n// https://github.com/phantomptr/ps5upload/releases\n// Example: for MAC on M-processor change Platform=default to Platform="mac-arm64.dmg"\n'''


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


class UserConfig:
    """Load validated settings from appdata/config.ini, migrating v1.8.0 settings."""

    def __init__(self, base_dir: Path) -> None:
        self.appdata_dir = base_dir / "appdata"
        self.path = self.appdata_dir / "config.ini"
        self.appdata_dir.mkdir(parents=True, exist_ok=True)
        legacy_path = base_dir / "config.ini"
        if not self.path.exists() and legacy_path.is_file():
            # Preserve existing v1.8.0 user choices when moving the config location.
            shutil.copy2(legacy_path, self.path)
        if not self.path.exists():
            self.path.write_text(DEFAULT_CONFIG, encoding="utf-8")
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string("\n".join(line for line in self.path.read_text(encoding="utf-8-sig").splitlines() if not line.lstrip().startswith("//")))
        raw_log_level = parser.get("General", "LOG_LEVEL", fallback=None)
        if raw_log_level is not None:
            self.verbose_logging = raw_log_level.strip() == "1"
            self.log_level_name = "DEBUG" if self.verbose_logging else "INFO"
        else:
            # Read the former LogLevel setting for configs created by older builds.
            legacy_level = _unquote(parser.get("General", "LogLevel", fallback="INFO")).upper()
            if legacy_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
                legacy_level = "INFO"
            self.log_level_name = legacy_level
            self.verbose_logging = legacy_level == "DEBUG"
            # Add the new switch to existing config files without discarding user settings.
            existing_text = self.path.read_text(encoding="utf-8-sig")
            if "[General]" in existing_text:
                existing_text = existing_text.replace(
                    "[General]", f"[General]\nLOG_LEVEL = {1 if self.verbose_logging else 0}", 1
                )
                self.path.write_text(existing_text, encoding="utf-8")
        self.log_level = getattr(logging, self.log_level_name)
        self.control_app_enabled = parser.getboolean("ps5upload-control-app-dl", "Enabled", fallback=True)
        self.platform_setting = _unquote(parser.get("ps5upload-control-app-dl", "Platform", fallback="default"))
        self.download_only_when_current = parser.getboolean(
            "ps5upload-control-app-dl", "DownloadOnlyWhenPS5UploadCurrent", fallback=True
        )

    @property
    def platform_suffix(self) -> str:
        """Resolve the default Windows target or preserve the configured asset suffix."""
        suffix = "win-x64.zip" if self.platform_setting.lower() == "default" else self.platform_setting
        if not suffix or suffix.startswith(("/", "\\")) or "/" in suffix or "\\" in suffix or ".." in suffix:
            raise ValueError("config.ini Platform must be 'default' or a release asset suffix")
        if any(ord(char) < 32 or char in '<>:"|?*' for char in suffix):
            raise ValueError("config.ini Platform contains invalid filename characters")
        if not Path(suffix).suffix:
            raise ValueError("config.ini Platform must include the release asset extension")
        return suffix
