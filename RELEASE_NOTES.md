# Folder updater v1.9.14

## Changes

- Refactor shared inventory refresh and local scanning paths to reduce repeated orchestration while preserving scan, update, and Pre-release behavior.
- Simplify missing-payload discovery by tracking payloads whose catalog checksums are already present locally, without building a set of checksums for every payload.
- Calculate reconciliation summary counts in a single pass over the result rows.
- Derive the catalog HTTP User-Agent from the application version instead of a stale hard-coded release number.
- Update version regression coverage and confirm no obsolete status assertions remain in the tests.

## Downloads

- Windows x64: standalone .exe
- macOS: .zip containing the .app bundle
- Linux x64: .zip containing the native executable
