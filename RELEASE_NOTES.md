# Folder updater v1.9.11

## Changes

- Set the application version to `1.9.11`; the GUI title, startup log, and packaged application names derive their version from `app/version.py`.
- Hide the `ps5upload-control-app` GUI row when the local `ps5upload` payload is absent, rather than showing an orphaned `Waiting for ps5upload CURRENT` status.
- Keep the control-app row directly below the local `ps5upload` row whenever both are present.
- Retain the modular GUI table and layout implementation, including centered window geometry, responsive status-column sizing, and horizontal scrolling when needed.
- Add regression coverage for control-app row visibility and application version/title consistency.

## Downloads

- Windows x64: standalone `.exe`
- macOS: `.zip` containing the `.app` bundle
- Linux x64: `.zip` containing the native executable
