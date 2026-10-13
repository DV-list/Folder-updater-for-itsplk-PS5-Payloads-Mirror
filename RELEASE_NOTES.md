# Folder updater v1.9.9

## Changes

- Added detection of manually downloaded control-app folders whose names start with `PS5Upload` or exactly match `Payload`, so the control-app row no longer incorrectly shows `DOWNLOAD` when either folder is present.
- Added regression tests for both manual folder naming patterns.
- Extracted the installed control-app version from `PS5Upload` folder names and used it for the displayed current version and server-version comparison, instead of trusting stale `local-state.json` version data.
- Kept manual control-app folder discovery and version parsing inside the standalone `ps5upload-control-app` module; normal `.elf` scanning and reconciliation remain unchanged.
- Added a regression test for a `PS5Upload-7.0.22-win-x64` folder with a stale recorded version of `7.0.1`.

## Downloads

- Windows x64: standalone `.exe`
- macOS: `.zip` containing the `.app` bundle
- Linux x64: `.zip` containing the native executable
