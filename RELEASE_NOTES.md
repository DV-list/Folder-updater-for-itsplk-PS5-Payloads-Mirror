# Folder updater v1.9.7

## Release highlights

- **Support the updated payload catalog schema:** Read payload entries from the top-level `payloads` array in the catalog metadata object.
- **Preserve backward compatibility:** Continue accepting the previous top-level array format.
- **Improve schema validation:** Reject malformed wrapper objects with a clear error instead of treating them as valid catalog data.
- **Add regression tests:** Cover the new object format, the legacy array format, and malformed wrapper objects.

## Downloads

- **Windows x64:** standalone `.exe`
- **macOS:** `.zip` containing the `.app` bundle
- **Linux x64:** `.zip` containing the native executable

## Build and compatibility notes

Builds are produced on their respective operating systems; PyInstaller is not a cross-compiler. Report OS-specific launch or runtime issues with the operating system version and relevant `appdata/application.log` details.
