"""Application entry point for Folder updater for itsplk PS5 Payloads Mirror v1.9.8."""

import logging
import sys
from pathlib import Path


def _application_directory() -> Path:
    """Return the directory that owns the running application or source entry point."""
    # PyInstaller sets sys.frozen and sys.executable points to the actual EXE.
    # During normal Python execution, main.py remains the application entry point.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _configure_startup_logging() -> Path:
    """Create the startup logger before application modules are imported."""
    # Bootstrap logging must happen before importing the GUI/application layer so
    # import-time failures, including missing dependencies, are captured.
    # Persistent diagnostics live in appdata beside the application executable.
    appdata_dir = _application_directory() / "appdata"
    log_path = appdata_dir / "application.log"
    try:
        from app.user_config import UserConfig
        user_config = UserConfig(_application_directory())
        appdata_dir.mkdir(parents=True, exist_ok=True)
        # Start a fresh log for this launch. Existing local-state.json is untouched.
        logging.basicConfig(
            filename=log_path,
            filemode="w",
            level=user_config.log_level,
            format="%(asctime)s | %(levelname)s | %(message)s",
            encoding="utf-8",
            force=True,
        )
    except OSError:
        # Logging failure must not prevent the application itself from starting.
        logging.basicConfig(
            level=logging.CRITICAL,
            format="%(asctime)s | %(levelname)s | %(message)s",
            force=True,
        )
        logging.getLogger(__name__).critical(
            "Unable to initialize application log at %s", log_path, exc_info=True
        )
    return log_path


def main() -> None:
    """Create and run the application with startup diagnostics."""
    log_path = _configure_startup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Folder updater for itsplk PS5 Payloads Mirror v1.9.8")
    logger.info("Application directory: %s", _application_directory())

    try:
        # Import after startup logging is configured so import errors are logged.
        from app.application import Application

        logger.info("Application modules imported successfully")
        Application().run()
        logger.info("Application exited normally")
    except Exception:
        # Include the full traceback in the log while allowing the process to exit
        # normally after recording the failure for diagnosis.
        logger.exception("Application startup/runtime failure")
        raise
    finally:
        logging.shutdown()


if __name__ == "__main__":
    main()
