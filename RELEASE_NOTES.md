# Folder updater v1.9.8

## Changes

- Added `LOG_LEVEL = 0` as the default configuration setting. Set it to `1` to enable detailed HTTP and catalog parsing diagnostics.
- Added request, response, redirect, and download logging for the payload catalog, ELF updates, and control-app downloads.
- Added catalog parsing diagnostics, including root structure, payload counts, and entry validation details.
- Existing configuration files are migrated to include `LOG_LEVEL`; previous `LogLevel` settings remain supported during migration.
- Added tests for default and verbose logging modes.

## Downloads

- Windows x64: standalone `.exe`
- macOS: `.zip` containing the `.app` bundle
- Linux x64: `.zip` containing the native executable
