# Architecture and development boundaries

The application is organized around small modules with explicit responsibilities. Keep new behavior in the module that owns that responsibility instead of adding unrelated logic to the GUI or application entry point.

## Module map

- `main.py` — process entry point and startup diagnostics. It delegates application behavior to the application layer.
- `app/version.py` — single source of truth for the application version.
- `app/config.py` and `app/user_config.py` — application paths/defaults and user-editable runtime configuration.
- `app/application.py` — composition root. It wires dependencies and coordinates scans, reconciliation, updates, downloads, and the GUI.
- `app/models.py` and `app/statuses.py` — shared data structures and status identifiers. These should stay lightweight and avoid importing GUI or I/O implementations.
- `app/scanner.py` — local-file discovery and hashing.
- `app/payload_catalog.py` and `app/discovery.py` — remote catalog access and selection of missing payloads.
- `app/reconciler.py` and `app/state_repository.py` — local/server classification and persisted state/history.
- `app/updater.py` and `app/downloader.py` — controlled file-transfer and update operations.
- `app/ps5upload_control_app_dl.py` — independent lifecycle for the separately versioned ps5upload control app.
- `app/gui.py` — window orchestration and user interactions. It receives callbacks rather than owning domain services.
- `app/gui_table.py` — reusable Treeview table widget, styles, scrollbars, and event bindings.
- `app/gui_layout.py` — deterministic, Tk-independent geometry and table-width calculations.

## GUI sizing rules

- At launch, calculate column widths from the displayed content, size the window around those columns, and center it on the available screen.
- Use half of the measured checksum text width for `CurrDirChecksum` and `ServerChecksum`, while retaining configured minimum widths so headings and a useful portion of the hash remain visible.
- On manual resize, recompute column widths from the Treeview's available width. The widths should add up to the available width unless the window is below the sum of minimum column widths; in that case, retain minimums and allow horizontal scrolling rather than silently compressing critical columns.
- Let the final `Status` column stretch to consume any remainder, avoiding an unused gap at the table's right edge.
- Re-measure content after table data changes, not on every intermediate resize event.

## Change and test conventions

- Keep file-system/network side effects in their owning service modules; keep layout arithmetic pure and independently testable.
- Preserve `appdata/local-state.json` compatibility and existing history when changing state serialization.
- Add regression tests for behavior changes, especially version detection, checksum verification, path validation, and GUI sizing.
- Run `python -m unittest discover -s tests -v` before merging. CI builds and tests on each target OS; a successful build does not replace testing the resulting application on that OS.
- The version in `app/version.py` is authoritative. Do not bump it, tag a release, or publish release artifacts unless explicitly requested.
