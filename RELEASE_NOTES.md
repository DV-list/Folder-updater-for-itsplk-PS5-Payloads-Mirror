# Folder updater v2.0.0

## Changes

- Refactored the GUI table into the dedicated `app/gui_table.py` module, separating table construction, styling, scrollbars, status tags, and row interaction bindings from the main window.
- Added `app/gui_layout.py` for testable column-width calculations and centered-window geometry.
- Centered the application window on launch and sized it from measured content, constrained by the available screen dimensions.
- Reduced the measured content width of the `CurrDirChecksum` and `ServerChecksum` columns by 50% to keep the table compact, while retaining minimum widths for readability.
- Made the `Status` column use the remaining table width so the final column aligns with the window edge when space permits; when the minimum column widths exceed available space, horizontal scrolling remains available.
- Centralized status identifiers in `app/statuses.py` and application version metadata in `app/version.py`.
- Updated the application, window title, and build naming to use version `2.0.0` from the single version source.
- Restricted GitHub Actions write permissions to the release-publishing job.
- Added GUI layout regression tests and documented module responsibilities and GUI sizing behavior in `ARCHITECTURE.md`.

## Validation

- GitHub Actions tests and package builds passed on Windows x64, macOS, and Linux x64.

## Downloads

- Windows x64: standalone `.exe`
- macOS: `.zip` containing the `.app` bundle
- Linux x64: `.zip` containing the native executable

---

# Folder updater v1.9.10

## Changes

- Added detection of manually downloaded control-app folders whose names start with `PS5Upload` or exactly match `Payload`, so the control-app row no longer incorrectly shows `DOWNLOAD` when either folder is present.
- Added regression tests for both manual folder naming patterns.
- Extracted the installed control-app version from `PS5Upload` folder names and used it for the displayed current version and server-version comparison, instead of trusting stale `local-state.json` version data.
- Kept manual control-app folder discovery, version parsing, and server-version comparison inside the standalone `ps5upload-control-app` module; normal `.elf` scanning and reconciliation remain unchanged.
- Added regression coverage for control-app version comparison in the dedicated module.
- Added a regression test for a `PS5Upload-7.0.22-win-x64` folder with a stale recorded version of `7.0.1`.

## Downloads

- Windows x64: standalone `.exe`
- macOS: `.zip` containing the `.app` bundle
- Linux x64: `.zip` containing the native executable
