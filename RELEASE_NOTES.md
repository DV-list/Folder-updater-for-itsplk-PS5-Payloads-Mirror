# Folder updater v1.9.12

## Changes

- Route the UPDATE button through the dedicated ps5upload_control_app_dl module for eligible control-app updates; keep the generic ELF updater from handling control-app assets.
- Archive the previously tracked versioned control-app folder into _OLD when installing a new catalog-derived folder, so old and new versions do not remain side by side in the working directory.
- Make control-app folder replacement transactional: validate the new asset first, restore archived paths on installation failure, and retain safe recovery behavior if rollback itself encounters an error.
- Add failure isolation around optional control-app module initialization, row integration, and update execution so a control-app error does not stop ordinary payload updates.
- Respect the configured requirement for local ps5upload to be CURRENT before updating the control app.
- Add regression tests for control-app UPDATE-button delegation, failed-module isolation, versioned-folder archival, and installation rollback.
- Keep the version source centralized in app/version.py, including download User-Agent strings.

## Downloads

- Windows x64: standalone .exe
- macOS: .zip containing the .app bundle
- Linux x64: .zip containing the native executable
