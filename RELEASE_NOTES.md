# Folder updater v1.9.6

## Release highlights

- **Fix control-app status tracking:** The control-app status is now evaluated against its own installed version and the latest server version. Updating `ps5upload.elf` alone no longer marks an outdated control app as `CURRENT`.
- **Archive obsolete control-app packages:** After the replacement asset has downloaded and passed validation, the previous package is moved to `_OLD`. Existing archives are preserved; if the replacement fails, the application attempts to restore the previous package.
- **Use a dedicated control-app update path:** The generic ELF updater skips the control-app row so the control app is updated through its own validated download flow.
- **Add regression tests:** Tests cover independent control-app version comparison and archiving the old package after a successful replacement.

## Downloads

- **Windows x64:** standalone `.exe`
- **macOS:** `.zip` containing the `.app` bundle
- **Linux x64:** `.zip` containing the native executable

## Build and compatibility notes

Builds are produced on their respective operating systems; PyInstaller is not a cross-compiler. Report OS-specific launch or runtime issues with the operating system version and relevant `appdata/application.log` details.
