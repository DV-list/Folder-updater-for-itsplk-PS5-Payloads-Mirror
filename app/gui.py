"""CustomTkinter Material-inspired user interface."""

from collections.abc import Callable
import logging
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
import webbrowser

import customtkinter as ctk

from app.gui_layout import (
    calculate_natural_column_widths,
    calculate_responsive_column_widths,
    centered_window_geometry,
)
from app.models import PayloadEntry, ScanResult
from app.statuses import (
    CONTROL_APP_DOWNLOAD,
    CURRENT,
    MANUAL,
    REMOVED_FROM_SERVER,
    SERVER_UNAVAILABLE,
    UNMATCHED,
    UPDATE_AVAILABLE,
)


class MainWindow:
    """Render one reconciliation result with a responsive table."""

    # Material-inspired accents used for the semantic groups and statuses.
    # Glossy Coral / Tangy / Feijoa / Light Steel with Diana + Millie neutrals.
    GLOSSY_CORAL = "#F88379"
    TANGY = "#E95D43"
    FEIJOA = "#A5D785"
    LIGHT_STEEL = "#B0C4DE"
    DIANA = "#D8D9D6"
    MILLIE = "#E8B7C8"
    BLUE = "#2675D8"
    GREEN = "#548C52"
    AMBER = "#D9A441"
    RED = "#C94F4F"
    GRAY = "#858585"
    PRE_RELEASE_ON = "☑ ON"
    PRE_RELEASE_OFF = "☐ OFF"
    UPDATE_BLUE = "#2675D8"
    UPDATE_GRAY = "#858585"
    UPDATE_HOVER_BLUE = "#1D5FAF"
    UPDATE_HOVER_GRAY = "#6E6E6E"

    COLUMNS = (
        "Payload",
        "FileName",
        "CurrDirChecksum",
        "CurrFile Version",
        "CurrFileAddedDate",
        "Pre-release",
        "ServerVersion",
        "ServerChecksum",
        "Status",
    )

    # Relative sizing weights used when the window grows or shrinks.
    COLUMN_WEIGHTS = {
        "Payload": 1.0,
        "FileName": 1.35,
        "CurrDirChecksum": 0.75,
        "CurrFile Version": 0.85,
        "CurrFileAddedDate": 1.05,
        "Pre-release": 0.65,
        "ServerVersion": 0.85,
        "ServerChecksum": 0.75,
        "Status": 0.95,
    }

    # Natural minimum widths keep long, important values readable while still allowing
    # the complete table to fit the minimum application window.
    COLUMN_MIN_WIDTHS = {
        "Payload": 80,
        "FileName": 110,
        "CurrDirChecksum": 190,
        "CurrFile Version": 85,
        "CurrFileAddedDate": 145,
        "Pre-release": 110,
        "ServerVersion": 85,
        "ServerChecksum": 190,
        "Status": 120,
    }

    def __init__(
        self,
        result: ScanResult,
        title: str,
        repository_url: str,
        update_callback: Callable[[], tuple[ScanResult, int, int, str | None]],
        pre_release_callback: Callable[[str, bool], ScanResult],
        download_candidates: list[PayloadEntry] | None = None,
        discovery_error: str | None = None,
        download_callback: Callable[[PayloadEntry], tuple[ScanResult, list[PayloadEntry], str | None, str | None]] | None = None,
        folder_scan_callback: Callable[[], tuple[ScanResult, list[PayloadEntry], str | None]] | None = None,
        control_app_download_callback: Callable[[], tuple[ScanResult, list[PayloadEntry], str | None, str | None]] | None = None,
    ) -> None:
        # Use CustomTkinter for a consistent, Material-inspired application shell.
        self.result = result
        self.repository_url = repository_url
        self.update_callback = update_callback
        self.pre_release_callback = pre_release_callback
        self.download_callback = download_callback
        self.folder_scan_callback = folder_scan_callback
        self.control_app_download_callback = control_app_download_callback
        self._control_app_download_status: str | None = None
        self.download_candidates = list(download_candidates or getattr(result, "download_candidates", []))
        self._discovery_error = discovery_error or getattr(result, "discovery_error", None)
        self.logger = logging.getLogger(__name__)
        self._update_running = False
        self._download_running = False
        self._scan_running = False
        self._update_results: Queue[tuple[str, object]] = Queue()
        self._download_results: Queue[tuple[str, object]] = Queue()
        self._scan_results: Queue[tuple[str, object]] = Queue()
        self._download_rows: dict[str, PayloadEntry] = {}
        self._download_statuses: dict[str, str] = {}
        self._active_download_entry: PayloadEntry | None = None
        self._scan_before_signature: dict[str, tuple] = {}
        self._status_clear_after_id: str | None = None
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self._shutting_down = False
        self.root = ctk.CTk()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.configure(fg_color="#F3F4F1")  # Diana-inspired soft neutral
        self.root.title(title)
        # The first window width is finalized after content measurement so the default
        # presentation can show natural column widths instead of immediately compressing
        # long checksum columns. The lower bound still guarantees every column remains
        # represented when the user makes the window narrower.
        # Bootstrap at a modest size; exact geometry is computed after table content is measured.
        self.root.geometry("1100x800")

        self._natural_widths: dict[str, int] = {}
        self._table_width = 0
        self._resize_after_id: str | None = None
        self._configure_theme()
        self._build_header()
        self._build_table()
        self._populate_table()
        self._populate_download_rows()
        self.root.update_idletasks()
        self._set_initial_window_size()
        self.root.update_idletasks()
        self._sync_table_layout()
        self._show_discovery_error(self._discovery_error)
        self._set_update_button_state()
        self.root.after(120000, self._start_periodic_scan)

    def run(self) -> None:
        """Start the GUI event loop."""
        self.root.mainloop()

    def _on_close(self) -> None:
        """Terminate the application even if a daemon worker is stuck in I/O.

        Python cannot safely kill an individual stuck thread. Closing the window
        therefore destroys the Tk root and hard-exits this process, which also
        terminates all daemon worker threads instead of leaving the app resident.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self.logger.info("Application exit requested; forcing process shutdown")
        except Exception:
            pass
        try:
            self.update_progress.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def _configure_theme(self) -> None:
        """Set the shared light palette; visual controls are CustomTkinter-native."""
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

    def _build_header(self) -> None:
        # The header contains the application identity, repository link, and scan summary.
        frame = ctk.CTkFrame(self.root, fg_color="#FFFFFF", corner_radius=16, border_width=1, border_color="#DCE4EF")
        frame.pack(fill="x", padx=18, pady=(18, 10))

        title_frame = ctk.CTkFrame(frame, fg_color="transparent")
        title_frame.pack(side="left", padx=20, pady=16)

        ctk.CTkLabel(
            title_frame,
            text=self.root.title(),
            font=("Segoe UI", 28, "bold"),
            text_color="#25364A",
        ).pack(anchor="w")

        repository_link = ctk.CTkLabel(
            title_frame,
            text="itsplk PS5 Payloads Mirror",
            text_color=self.TANGY,
            cursor="hand2",
            font=("Segoe UI", 11, "underline"),
        )
        repository_link.pack(anchor="w", pady=(2, 0))
        repository_link.bind(
            "<Button-1>",
            lambda _event: webbrowser.open(self.repository_url),
        )

        # Keep the action immediately to the left of the summary, as requested.
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(side="right", padx=20, pady=16)

        self.update_button = ctk.CTkButton(
            actions,
            text="UPDATE",
            width=120,
            fg_color=self.UPDATE_GRAY,
            hover_color=self.UPDATE_HOVER_GRAY,
            text_color="#FFFFFF",
            text_color_disabled="#FFFFFF",
            corner_radius=10,
            height=38,
            command=self._start_update,
        )
        self.update_button.pack(side="left", padx=(0, 12))

        self.summary_label = ctk.CTkLabel(
            actions,
            text=self._summary_text(),
            font=("Segoe UI", 11),
        )
        self.summary_label.pack(side="left")

        # Put status on its own full-width row so the summary/actions cannot squeeze
        # it out of view in the header on smaller window widths.
        self.update_status_frame = ctk.CTkFrame(self.root, fg_color="#FFFFFF", corner_radius=12, border_width=1, border_color="#DCE4EF")
        self.update_status_frame.pack(fill="x", padx=18, pady=(0, 10))
        # The activity indicator sits beside operation status, not beside the summary.
        self.update_progress = ctk.CTkProgressBar(
            self.update_status_frame, mode="indeterminate", width=110, height=10,
            progress_color=self.UPDATE_BLUE, fg_color="#DCE7F7",
            border_width=0, corner_radius=6, indeterminate_speed=1.5,
        )
        self.update_progress.pack(side="left", padx=(0, 12))
        self.update_progress.stop()
        self.update_progress.pack_forget()
        self.update_status_label = ctk.CTkLabel(
            self.update_status_frame,
            text="",
            font=("Segoe UI", 12),
            text_color="#475467",
            anchor="w",
        )
        self.update_status_label.pack(side="left", fill="x", expand=True)
        self._set_update_button_state()

    def _summary_text(self) -> str:
        """Return the current scan summary shown beside the UPDATE action."""
        return (
            f"Files: {self.result.scanned_files}    "
            f"Current: {self.result.current_count}    "
            f"Updates: {self.result.update_count}    "
            f"Unmatched: {self.result.unmatched_count}    "
            f"Removed: {self.result.removed_count}"
        )

    def _set_update_button_state(self) -> None:
        """Color UPDATE from reconciled state and keep that color while disabled."""
        # ScanResult is the source of truth. A visible Treeview may briefly contain
        # stale rows while the UI is being refreshed, so never let it mask an update
        # already reported by the model or its summary count.
        expected = UPDATE_AVAILABLE.strip().casefold()
        model_has_updates = bool(getattr(self.result, "update_count", 0)) or any(
            str(getattr(row, "status", "")).strip().casefold() == expected
            for row in getattr(self.result, "rows", ())
        )
        visible_has_updates = False
        if hasattr(self, "tree"):
            try:
                if self.tree.winfo_exists():
                    status_index = self.COLUMNS.index("Status")
                    visible_has_updates = any(
                        len(values := self.tree.item(item, "values")) > status_index
                        and str(values[status_index]).strip().casefold() == expected
                        for item in self.tree.get_children()
                    )
            except (tk.TclError, AttributeError):
                # During shutdown or widget reconstruction, rely on the model.
                visible_has_updates = False
        has_updates = model_has_updates or visible_has_updates

        busy = self._update_running or self._download_running or self._scan_running
        if self._update_running:
            button_text = "UPDATING..."
        elif self._download_running:
            button_text = "DOWNLOADING..."
        elif self._scan_running:
            button_text = "SCANNING..."
        else:
            button_text = "UPDATE"

        button_color = self.UPDATE_BLUE if has_updates else self.UPDATE_GRAY
        hover_color = self.UPDATE_HOVER_BLUE if has_updates else self.UPDATE_HOVER_GRAY
        # Explicitly set all visual state colors together: CTkButton doesn't expose
        # a `disabled_color` option. Its disabled state should not erase the blue fill.
        self.update_button.configure(
            fg_color=button_color,
            hover_color=hover_color,
            text_color="#FFFFFF",
            text_color_disabled="#FFFFFF",
            state="disabled" if busy else "normal",
            text=button_text,
        )
        self.logger.debug(
            "UPDATE button state: has_updates=%s model_count=%s busy=%s color=%s",
            has_updates, getattr(self.result, "update_count", 0), busy, button_color,
        )
        self.root.update_idletasks()

    def _set_final_update_status(self, text: str) -> None:
        """Show a final status for five seconds, replacing any previous clear timer."""
        if self._status_clear_after_id is not None:
            try:
                self.root.after_cancel(self._status_clear_after_id)
            except tk.TclError:
                pass
            self._status_clear_after_id = None
        self.update_status_label.configure(text=text)
        self._status_clear_after_id = self.root.after(5000, self._clear_update_status)

    def _clear_update_status(self) -> None:
        """Clear a completed update message without touching an active update message."""
        self._status_clear_after_id = None
        if not (self._update_running or self._download_running or self._scan_running):
            self.update_status_label.configure(text=self._discovery_error_text())

    def _discovery_error_text(self) -> str:
        return f"Download discovery failed: {self._discovery_error}" if self._discovery_error else ""

    def _show_discovery_error(self, error: str | None) -> None:
        """Keep catalog discovery failures visible until a later successful fetch."""
        self._discovery_error = error
        if error:
            self.update_status_label.configure(text=self._discovery_error_text())
        elif self._status_clear_after_id is None and not (
            self._update_running or self._download_running or self._scan_running
        ):
            self.update_status_label.configure(text="")

    def _start_update(self) -> None:
        """Run the updater without blocking the Tk event loop."""
        if self._update_running or self._download_running or self._scan_running:
            return

        self._update_running = True
        if self._status_clear_after_id is not None:
            try:
                self.root.after_cancel(self._status_clear_after_id)
            except tk.TclError:
                pass
            self._status_clear_after_id = None
        self.update_button.configure(state="disabled", text="UPDATING...")
        self.update_status_label.configure(text="Updating payloads…")
        self.update_progress.pack(side="left", padx=(0, 12))
        self.update_progress.start()

        # Poll for worker results from the Tk event loop. Tkinter calls such as
        # root.after() are not made from the worker thread because that is unreliable
        # on some Windows/Tk builds and can leave the UI stuck in the updating state.
        self.root.after(100, self._poll_update_result)
        worker = Thread(target=self._run_update_worker, daemon=True)
        worker.start()

    def _run_update_worker(self) -> None:
        """Run network/filesystem work and place its result on a thread-safe queue."""
        try:
            outcome = self.update_callback()
        except Exception as exc:
            self.logger.exception("UPDATE button operation failed")
            self._update_results.put(("error", exc))
            return

        self._update_results.put(("outcome", outcome))

    def _poll_update_result(self) -> None:
        """Consume worker completion on the GUI thread, retrying while it runs."""
        try:
            result_type, payload = self._update_results.get_nowait()
        except Empty:
            if self._update_running:
                self.root.after(100, self._poll_update_result)
            return

        if result_type == "error":
            self._finish_update(error=payload)
        else:
            self._finish_update(outcome=payload)

    def _finish_update(
        self,
        outcome: tuple[ScanResult, int, int, str | None] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Finish on the GUI thread, then show a five-second final status."""
        final_status = "Update failed"
        self._update_running = False
        self.update_progress.stop()
        self.update_progress.pack_forget()

        try:
            if error is not None:
                self.logger.error("UPDATE failed: %s", error)
                messagebox.showerror(
                    "Update failed",
                    f"The update operation failed.\n\n{error}\n\nSee appdata\\application.log for details.",
                    parent=self.root,
                )
            elif outcome is not None:
                updated, successful, failed, notice = outcome
                self.result = updated
                self.download_candidates = list(getattr(updated, "download_candidates", self.download_candidates))
                self._show_discovery_error(getattr(updated, "discovery_error", None))
                self._replace_table_rows()
                self.summary_label.configure(text=self._summary_text())
                if notice:
                    final_status = "Update stopped"
                    messagebox.showwarning("Update stopped", notice, parent=self.root)
                elif failed:
                    final_status = f"Completed: {successful} updated, {failed} failed"
                    messagebox.showwarning(
                        "Update completed with errors",
                        f"Update completed: {successful} payload(s) updated, {failed} failed.\n\n"
                        "See appdata\\application.log for details.",
                        parent=self.root,
                    )
                else:
                    final_status = f"Update complete: {successful} updated"
                    messagebox.showinfo(
                        "Update completed",
                        f"Update completed successfully.\nPayloads updated: {successful}",
                        parent=self.root,
                    )
        except Exception:
            self.logger.exception("Error while finalizing UPDATE operation")
            final_status = "Update finished with an interface error"
        finally:
            # Re-evaluate from the current table after any refresh. This also
            # restores clickability if displaying a dialog or refreshing the table fails.
            self._update_running = False
            self.update_button.configure(state="normal", text="UPDATE")
            self._set_update_button_state()
            # Modal messageboxes return only after dismissal, so the five-second timer
            # begins after the user has seen and closed the completion notification.
            self._set_final_update_status(final_status)

    def _on_table_double_click(self, event):
        """Download untouched placeholders after confirmation; otherwise show in Explorer."""
        # A double-click anywhere in the Pre-release column is control interaction,
        # never a download/Explorer action. This guard is independent of checkbox
        # toggle handling so rapid repeated clicks cannot fall through to downloads.
        identify_column = getattr(self.tree, "identify_column", None)
        if callable(identify_column) and hasattr(event, "x"):
            try:
                if identify_column(event.x) == f"#{self.COLUMNS.index('Pre-release') + 1}":
                    return "break"
            except (tk.TclError, TypeError):
                pass
        iid = self.tree.row_for_widget(event.widget) if hasattr(self.tree, "row_for_widget") else self.tree.identify_row(event.y)
        if not iid:
            return None
        values = self.tree.item(iid, "values")
        if not values:
            return None
        status = str(values[self.COLUMNS.index("Status")])
        if iid == "control_app_row":
            retryable_status = status in {CONTROL_APP_DOWNLOAD, UPDATE_AVAILABLE} or status.startswith("Download Failed")
            if retryable_status and self.control_app_download_callback is not None:
                if self._download_running:
                    return "break"
                confirmed = messagebox.askokcancel(
                    "Download control app",
                    f"Do you want to download the ps5upload control app ({values[self.COLUMNS.index('FileName')]})?",
                    parent=self.root,
                )
                if confirmed:
                    self._start_download(iid)
                return "break"
            self._show_in_explorer(values)
            return "break"
        if iid in self._download_rows and status == "Not Downloaded":
            entry = self._download_rows[iid]
            if self._download_running and self._active_download_entry == entry:
                return "break"
            confirmed = messagebox.askokcancel(
                "Download payload",
                f"Do you want to download {entry.payload}?",
                parent=self.root,
            )
            if confirmed:
                self._start_download(iid)
            return "break"
        self._show_in_explorer(values)
        return "break"

    def _show_in_explorer(self, values: tuple) -> None:
        """Select a local ELF in Windows Explorer, or open the app folder if absent."""
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parent.parent
        filename = str(values[self.COLUMNS.index("FileName")]).strip()
        candidate = (base_dir / filename).resolve() if filename and filename != "—" else None
        try:
            if candidate is not None and candidate.is_file() and candidate.parent == base_dir.resolve():
                subprocess.Popen(["explorer.exe", "/select,", str(candidate)])
                self.logger.info("Opened Explorer selecting %s", candidate.name)
            else:
                subprocess.Popen(["explorer.exe", str(base_dir)])
                self.logger.info("Opened Explorer at application directory for row without a local file")
        except OSError:
            self.logger.exception("Unable to open Windows Explorer")
            messagebox.showerror(
                "Explorer could not be opened",
                "Windows Explorer could not be opened for this row.",
                parent=self.root,
            )

    def _start_download(self, iid: str) -> None:
        if self._update_running or self._download_running or self._scan_running:
            return
        if iid == "control_app_row":
            self._start_control_app_download()
            return
        entry = self._download_rows.get(iid)
        if entry is None or self.download_callback is None:
            return
        if self._download_statuses.get(entry.payload, "").startswith("Downloading"):
            return

        self._download_running = True
        self._active_download_entry = entry
        self._download_statuses[entry.payload] = "Downloading…"
        if self._status_clear_after_id is not None:
            try:
                self.root.after_cancel(self._status_clear_after_id)
            except tk.TclError:
                pass
            self._status_clear_after_id = None
        self.update_status_label.configure(text=f"Downloading {entry.payload}…")
        self.update_progress.pack(side="left", padx=(0, 12))
        self.update_progress.start()
        self._replace_table_rows()
        self._set_update_button_state()
        self.root.after(100, self._poll_download_result)
        Thread(target=self._run_download_worker, args=(entry,), daemon=True).start()

    def _run_download_worker(self, entry: PayloadEntry) -> None:
        try:
            if self.download_callback is None:
                raise RuntimeError("Downloader is not configured")
            self._download_results.put(("outcome", self.download_callback(entry)))
        except Exception as exc:
            self.logger.exception("Downloader operation failed for %s", entry.payload)
            self._download_results.put(("error", exc))

    def _poll_download_result(self) -> None:
        try:
            result_type, payload = self._download_results.get_nowait()
        except Empty:
            if self._download_running:
                self.root.after(100, self._poll_download_result)
            return
        if result_type == "control_app_error":
            self._finish_control_app_download(error=payload)
        elif result_type == "control_app_outcome":
            self._finish_control_app_download(outcome=payload)
        elif result_type == "error":
            self._finish_download(error=payload)
        else:
            self._finish_download(outcome=payload)

    def _start_control_app_download(self) -> None:
        if (
            self._update_running or self._download_running or self._scan_running
            or self.control_app_download_callback is None
        ):
            return
        self._download_running = True
        self._active_download_entry = None
        self._control_app_download_status = "Downloading…"
        if self._status_clear_after_id is not None:
            try:
                self.root.after_cancel(self._status_clear_after_id)
            except tk.TclError:
                pass
            self._status_clear_after_id = None
        self.update_status_label.configure(text="Downloading ps5upload control app…")
        self.update_progress.pack(side="left", padx=(0, 12))
        self.update_progress.start()
        self._replace_table_rows()
        self.root.after(100, self._poll_download_result)
        Thread(target=self._run_control_app_download_worker, daemon=True).start()

    def _run_control_app_download_worker(self) -> None:
        try:
            if self.control_app_download_callback is None:
                raise RuntimeError("Control-app downloader is not configured")
            self._download_results.put(("control_app_outcome", self.control_app_download_callback()))
        except Exception as exc:
            self.logger.exception("Control-app download operation failed")
            self._download_results.put(("control_app_error", exc))

    def _finish_control_app_download(self, outcome=None, error: Exception | None = None) -> None:
        self._download_running = False
        self._active_download_entry = None
        self.update_progress.stop()
        self.update_progress.pack_forget()
        final_status = "Control-app download failed"

        if error is not None:
            self._control_app_download_status = "Download Failed — double-click to retry"
            final_status = f"Control-app download failed: {error}"
            self.logger.error("Control-app download finalization failed: %s", error)
        elif outcome is not None:
            updated, candidates, download_error, discovery_error = outcome
            self.result = updated
            self.download_candidates = list(candidates)
            self._show_discovery_error(discovery_error)
            if download_error:
                self._control_app_download_status = "Download Failed — double-click to retry"
                final_status = f"Control-app download failed: {download_error}"
                self.logger.warning("Control-app download failed: %s", download_error)
            else:
                self._control_app_download_status = None
                final_status = "Control-app download complete"

        self._replace_table_rows()
        self.summary_label.configure(text=self._summary_text())
        self._set_update_button_state()
        self._set_final_update_status(final_status)

    def _finish_download(self, outcome=None, error: Exception | None = None) -> None:
        entry = self._active_download_entry
        self._download_running = False
        self._active_download_entry = None
        self.update_progress.stop()
        self.update_progress.pack_forget()
        final_status = "Download failed"

        if error is not None:
            download_error = str(error)
            if entry is not None:
                self._download_statuses[entry.payload] = self._download_failure_status(download_error)
            self.logger.error("Download finalization failed: %s", error)
        elif outcome is not None:
            updated, candidates, download_error, discovery_error = outcome
            self.result = updated
            self.download_candidates = list(candidates)
            self._show_discovery_error(discovery_error)
            if download_error:
                if entry is not None:
                    self._download_statuses[entry.payload] = self._download_failure_status(download_error)
                final_status = f"Download failed: {entry.payload if entry else 'payload'}"
                self.logger.warning("Download failed: %s", download_error)
            else:
                if entry is not None:
                    self._download_statuses.pop(entry.payload, None)
                final_status = f"Download complete: {entry.payload if entry else 'payload'}"

        current_payloads = {candidate.payload for candidate in self.download_candidates}
        self._download_statuses = {
            payload: status for payload, status in self._download_statuses.items()
            if payload in current_payloads
        }
        self._replace_table_rows()
        self.summary_label.configure(text=self._summary_text())
        self._set_update_button_state()
        self._set_final_update_status(final_status)

    @staticmethod
    def _download_failure_status(error: str) -> str:
        lowered = error.lower()
        if "checksum" in lowered or "verification" in lowered:
            return "Verification Failed — click to retry"
        if "not confirmed" in lowered:
            return "Installation Not Confirmed — click to retry"
        return "Download Failed — click to retry"

    def _start_periodic_scan(self) -> None:
        """Schedule the next two-minute check and launch a non-overlapping folder scan."""
        self.root.after(120000, self._start_periodic_scan)
        if self.folder_scan_callback is None:
            return
        if self._update_running or self._download_running or self._scan_running:
            self.root.after(10000, self._start_periodic_scan_once)
            return
        self._start_periodic_scan_once()

    def _start_periodic_scan_once(self) -> None:
        if self.folder_scan_callback is None or self._update_running or self._download_running or self._scan_running:
            return
        self._scan_running = True
        self._scan_before_signature = self._row_signature(self.result)
        self.logger.info("Starting scheduled folder scan")
        self.update_status_label.configure(text="Scanning folder…")
        self._set_update_button_state()
        self.root.after(100, self._poll_folder_scan_result)
        Thread(target=self._run_folder_scan_worker, daemon=True).start()

    def _run_folder_scan_worker(self) -> None:
        try:
            if self.folder_scan_callback is None:
                raise RuntimeError("Folder scan is not configured")
            self._scan_results.put(("outcome", self.folder_scan_callback()))
        except Exception as exc:
            self.logger.exception("Automatic folder scan failed")
            self._scan_results.put(("error", exc))

    def _poll_folder_scan_result(self) -> None:
        try:
            result_type, payload = self._scan_results.get_nowait()
        except Empty:
            if self._scan_running:
                self.root.after(100, self._poll_folder_scan_result)
            return

        self._scan_running = False
        if result_type == "error":
            self.logger.error("Scheduled folder scan failed: %s", payload)
            self._show_discovery_error(f"Automatic folder scan failed: {payload}")
        else:
            result, candidates, discovery_error = payload
            new_signature = self._row_signature(result)
            before = self._scan_before_signature
            changed_names = set(before) | set(new_signature)
            changes = sum(1 for name in changed_names if before.get(name) != new_signature.get(name))
            self.logger.info(
                "Scheduled folder scan completed: %s ELF files found, %s changes detected",
                result.scanned_files,
                changes,
            )
            self.result = result
            self.download_candidates = list(candidates)
            self._show_discovery_error(discovery_error)
            current_payloads = {candidate.payload for candidate in self.download_candidates}
            self._download_statuses = {
                name: status for name, status in self._download_statuses.items()
                if name in current_payloads
            }
            self._replace_table_rows()
            self.summary_label.configure(text=self._summary_text())
            if not discovery_error and self._status_clear_after_id is None:
                self.update_status_label.configure(text="")
        self._set_update_button_state()

    @staticmethod
    def _row_signature(result: ScanResult) -> dict[str, tuple]:
        """Return comparable local-row state for scheduled scan change logging."""
        return {
            row.filename: (row.payload, row.curr_checksum, row.curr_file_version, row.status)
            for row in result.rows
        }

    def _replace_table_rows(self) -> None:
        """Replace displayed rows after an update and recalculate natural widths."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._populate_table()
        self._populate_download_rows()
        self.root.update_idletasks()
        self._calculate_natural_widths()
        self._sync_table_layout()
        self._set_update_button_state()

    def _build_table(self) -> None:
        """Build a responsive native Treeview with CustomTkinter scrollbars.

        Treeview is deliberately retained for efficient rendering of many payload rows;
        CTk scrollbars and the surrounding rounded card preserve the modern appearance.
        """
        self.table_outer = ctk.CTkFrame(
            self.root, fg_color="#FFFFFF", corner_radius=16,
            border_width=1, border_color="#DCE4EF",
        )
        self.table_outer.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.table_outer.grid_rowconfigure(0, weight=1)
        self.table_outer.grid_columnconfigure(0, weight=1)

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Payloads.Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground="#263238",
            font=("Segoe UI", 11),
            rowheight=36,
            borderwidth=0,
        )
        style.configure(
            "Payloads.Treeview.Heading",
            background=self.LIGHT_STEEL,
            foreground="#25364A",
            font=("Segoe UI Semibold", 11, "bold"),
            padding=(8, 9),
            relief="flat",
        )
        style.map(
            "Payloads.Treeview.Heading",
            background=[("active", "#C5D4E8")],
        )
        style.map(
            "Payloads.Treeview",
            background=[("selected", "#DCE7F7")],
            foreground=[("selected", "#183B65")],
        )

        self.tree = ttk.Treeview(
            self.table_outer,
            columns=self.COLUMNS,
            show="headings",
            style="Payloads.Treeview",
            selectmode="browse",
        )
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 2), pady=(8, 2))

        self.vscroll = ctk.CTkScrollbar(
            self.table_outer, orientation="vertical", command=self.tree.yview,
            button_color=self.LIGHT_STEEL, button_hover_color="#819BB9",
            fg_color="#F3F4F1", corner_radius=8, width=14,
        )
        self.vscroll.grid(row=0, column=1, sticky="ns", padx=(2, 8), pady=(8, 2))
        self.hscroll = ctk.CTkScrollbar(
            self.table_outer, orientation="horizontal", command=self.tree.xview,
            button_color=self.LIGHT_STEEL, button_hover_color="#819BB9",
            fg_color="#F3F4F1", corner_radius=8, height=14,
        )
        self.hscroll.grid(row=1, column=0, sticky="ew", padx=(8, 2), pady=(2, 8))
        self.tree.configure(yscrollcommand=self.vscroll.set, xscrollcommand=self.hscroll.set)

        for column in self.COLUMNS:
            self.tree.heading(column, text=column, anchor="w")
            self.tree.column(
                column,
                width=self.COLUMN_MIN_WIDTHS[column],
                minwidth=self.COLUMN_MIN_WIDTHS[column],
                anchor="w",
                stretch=(column == "Status"),
            )

        self.tree.tag_configure("current", background="#F1F8ED", foreground="#326A3B")
        self.tree.tag_configure("manual", background="#F6E6A8", foreground="#5D4A12")
        self.tree.tag_configure("update", background="#FFF4EF", foreground="#A43F28")
        self.tree.tag_configure("unmatched", background="#FCE9E7", foreground="#A82E2E")
        self.tree.tag_configure("unavailable", background="#F2F3F0", foreground="#596579")
        self.tree.tag_configure("removed", background="#F8DEDC", foreground="#8B2520")
        self.tree.tag_configure("download_row", background="#F1F4F8", foreground="#536273")
        self.tree.tag_configure("download_available", background="#FFF0D9", foreground="#9A4D00")
        self.tree.tag_configure("download_busy", background="#DDE8F6", foreground="#2C5687")
        self.tree.tag_configure("download_failed", background="#FCE9E7", foreground="#A82E2E")

        self.tree.bind("<Button-1>", self._on_pre_release_click)
        self.tree.bind("<Double-1>", self._on_table_double_click)
        self.tree.bind("<Configure>", lambda _event: self._schedule_layout_sync())
        self.table_outer.bind("<Configure>", lambda _event: self._schedule_layout_sync())

    def _populate_table(self) -> None:
        # Convert reconciliation results directly into display rows; no business
        # decisions are made inside the GUI.
        for row in self.result.rows:
            is_control_app = row.catalog_payload == "__control_app__"
            status = self._control_app_download_status if is_control_app and self._control_app_download_status else row.status
            tag = self._status_tag(status, row.pre_release)
            values = (
                row.payload or "UNKNOWN",
                row.filename,
                row.curr_checksum or "—",
                row.curr_file_version or "—",
                self._format_file_added_date(row.curr_file_added_date),
                self._pre_release_cell_value(row.pre_release, row.curr_checksum),
                row.server_version or "—",
                row.server_checksum or "—",
                status,
            )
            if is_control_app:
                self.tree.insert("", "end", iid="control_app_row", values=values, tags=(tag,))
            else:
                self.tree.insert("", "end", values=values, tags=(tag,))

    def _populate_download_rows(self) -> None:
        """Append clickable placeholders for payloads absent from the local folder."""
        self._download_rows = {}
        for index, entry in enumerate(self.download_candidates):
            iid = f"download_row_{index}"
            self._download_rows[iid] = entry
            status = self._download_statuses.get(entry.payload, "Not Downloaded")
            if status.startswith("Downloading"):
                tag = "download_busy"
            elif "Failed" in status or "not confirmed" in status.lower():
                tag = "download_failed"
            else:
                tag = "download_row"
            values = (
                entry.payload,
                "", "", "", "", "—",
                entry.version,
                entry.checksum,
                status,
            )
            self.tree.insert("", "end", iid=iid, values=values, tags=(tag,))

    def _set_initial_window_size(self) -> None:
        """Fit the table to its content and center the window on the current screen."""
        self._calculate_natural_widths()

        # The root window also contains header/table margins, card borders, and the
        # vertical scrollbar. Account for this fixed chrome around the data columns.
        horizontal_chrome = 80
        minimum_content_width = sum(self.COLUMN_MIN_WIDTHS.values())
        natural_content_width = sum(self._natural_widths.values())
        requested_width = max(
            natural_content_width + horizontal_chrome,
            minimum_content_width + horizontal_chrome,
        )

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width, height, x, y = centered_window_geometry(
            requested_width,
            900,
            screen_width,
            screen_height,
        )
        minimum_width = min(
            minimum_content_width + horizontal_chrome,
            max(1, screen_width - 48),
        )
        minimum_height = min(650, max(1, screen_height - 48))
        self.root.minsize(minimum_width, minimum_height)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _schedule_layout_sync(self) -> None:
        # Coalesce rapid Windows resize events so column calculations do not run for
        # every intermediate frame while the user is dragging the window border.
        if self._resize_after_id is not None:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(25, self._sync_table_layout)

    def _sync_table_layout(self) -> None:
        """Resize columns to fill the visible table area without a trailing gap."""
        self._resize_after_id = None
        available = max(self.tree.winfo_width(), 1)
        if available <= 1:
            return

        self._table_width = available
        widths = self._calculate_responsive_widths(available)
        for column, width in widths.items():
            self.tree.column(
                column,
                width=width,
                minwidth=self.COLUMN_MIN_WIDTHS[column],
                stretch=(column == "Status"),
            )

    def _calculate_natural_widths(self) -> None:
        """Measure visible cell content once per data refresh, not on every resize."""
        # Measure using the same point sizes and weight as the Treeview styles.
        body_font = tkfont.Font(family="Segoe UI", size=11)
        heading_font = tkfont.Font(
            family="Segoe UI Semibold", size=11, weight="bold"
        )

        values_by_column = {column: [] for column in self.COLUMNS}
        for row in self.result.rows:
            values_by_column["Payload"].append(row.payload or "UNKNOWN")
            values_by_column["FileName"].append(row.filename)
            values_by_column["CurrDirChecksum"].append(row.curr_checksum or "—")
            values_by_column["CurrFile Version"].append(row.curr_file_version or "—")
            values_by_column["CurrFileAddedDate"].append(
                self._format_file_added_date(row.curr_file_added_date)
            )
            values_by_column["Pre-release"].append(
                self._pre_release_cell_value(row.pre_release, row.curr_checksum)
            )
            values_by_column["ServerVersion"].append(row.server_version or "—")
            values_by_column["ServerChecksum"].append(row.server_checksum or "—")
            status = (
                self._control_app_download_status
                if row.catalog_payload == "__control_app__"
                and self._control_app_download_status
                else row.status
            )
            values_by_column["Status"].append(status)

        for entry in self.download_candidates:
            values_by_column["Payload"].append(entry.payload)
            values_by_column["ServerVersion"].append(entry.version)
            values_by_column["ServerChecksum"].append(entry.checksum)
            values_by_column["Status"].append(
                self._download_statuses.get(entry.payload, "Not Downloaded")
            )

        self._natural_widths = calculate_natural_column_widths(
            self.COLUMNS,
            values_by_column,
            self.COLUMN_MIN_WIDTHS,
            body_font.measure,
            heading_font.measure,
        )

    def _calculate_responsive_widths(self, available: int) -> dict[str, int]:
        """Delegate column arithmetic to the UI-independent layout module."""
        return calculate_responsive_column_widths(
            self.COLUMNS,
            self._natural_widths,
            self.COLUMN_MIN_WIDTHS,
            self.COLUMN_WEIGHTS,
            available,
        )

    def _format_file_added_date(value: str | None) -> str:
        # The GUI intentionally uses the agreed full timestamp without a timezone suffix.
        if not value:
            return "—"
        return value[:19].replace("T", " ")

    @classmethod
    def _pre_release_cell_value(cls, enabled: bool, checksum: str | None) -> str:
        """Render a compact checkbox-like control only for records with a hash."""
        if not checksum or checksum == "—":
            return "—"
        return cls.PRE_RELEASE_ON if enabled else cls.PRE_RELEASE_OFF

    def _status_tag(self, status: str, pre_release: bool = False) -> str:
        if pre_release or status == MANUAL:
            return "manual"
        if status == CONTROL_APP_DOWNLOAD:
            return "download_available"
        if status.startswith("Downloading"):
            return "download_busy"
        if status.startswith("Download Failed"):
            return "download_failed"
        return {
            CURRENT: "current",
            UPDATE_AVAILABLE: "update",
            UNMATCHED: "unmatched",
            SERVER_UNAVAILABLE: "unavailable",
            REMOVED_FROM_SERVER: "removed",
        }.get(status, "unavailable")

    def _on_pre_release_click(self, event):
        """Toggle the Boolean checkbox while preventing row actions from firing."""
        identify_column = getattr(self.tree, "identify_column", None)
        identify_region = getattr(self.tree, "identify", None)
        identify_row = getattr(self.tree, "identify_row", None)
        if not callable(identify_column) or not callable(identify_row) or not hasattr(event, "x"):
            return None

        try:
            column_id = identify_column(event.x)
            if column_id != f"#{self.COLUMNS.index('Pre-release') + 1}":
                return None
            if callable(identify_region) and identify_region("region", event.x, event.y) != "cell":
                return None
            item = identify_row(event.y)
        except (tk.TclError, TypeError):
            return None

        # Consume every click in this column, even if the row is not eligible for a
        # toggle. In particular, it must never bubble into row/download behavior.
        if not item:
            return "break"
        try:
            if hasattr(self.tree, "selection_set"):
                self.tree.selection_set(item)
            if hasattr(self.tree, "focus"):
                self.tree.focus(item)
        except tk.TclError:
            pass

        if self._update_running or self._download_running or self._scan_running:
            return "break"

        values = self.tree.item(item, "values")
        if not values:
            return "break"
        checksum = str(values[self.COLUMNS.index("CurrDirChecksum")]).strip()
        if not checksum or checksum == "—" or item in self._download_rows:
            return "break"

        current_value = str(values[self.COLUMNS.index("Pre-release")]).strip()
        enabled = current_value != self.PRE_RELEASE_ON
        try:
            result = self.pre_release_callback(checksum, enabled)
        except Exception:
            self.logger.exception("Failed to save Pre-release checkbox state")
            self._set_final_update_status("Failed to save Pre-release setting")
            return "break"

        self.result = result
        self.download_candidates = list(
            getattr(result, "download_candidates", self.download_candidates)
        )
        self._discovery_error = getattr(result, "discovery_error", self._discovery_error)
        self._replace_table_rows()
        self.summary_label.configure(text=self._summary_text())
        self._show_discovery_error(self._discovery_error)
        return "break"
