"""Native Treeview presentation component for the payload inventory."""

from collections.abc import Callable, Mapping, Sequence
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk


class PayloadTable:
    """Own the inventory table widgets, visual styling, and input bindings."""

    def __init__(
        self,
        master,
        *,
        columns: Sequence[str],
        minimum_widths: Mapping[str, int],
        accent_color: str,
        on_pre_release_click: Callable,
        on_double_click: Callable,
        on_resize: Callable,
    ) -> None:
        self.outer = ctk.CTkFrame(
            master,
            fg_color="#FFFFFF",
            corner_radius=16,
            border_width=1,
            border_color="#DCE4EF",
        )
        self.outer.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.outer.grid_rowconfigure(0, weight=1)
        self.outer.grid_columnconfigure(0, weight=1)

        style = ttk.Style(master)
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
            background=accent_color,
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
            self.outer,
            columns=columns,
            show="headings",
            style="Payloads.Treeview",
            selectmode="browse",
        )
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 2), pady=(8, 2))

        self.vscroll = ctk.CTkScrollbar(
            self.outer,
            orientation="vertical",
            command=self.tree.yview,
            button_color=accent_color,
            button_hover_color="#819BB9",
            fg_color="#F3F4F1",
            corner_radius=8,
            width=14,
        )
        self.vscroll.grid(row=0, column=1, sticky="ns", padx=(2, 8), pady=(8, 2))
        self.hscroll = ctk.CTkScrollbar(
            self.outer,
            orientation="horizontal",
            command=self.tree.xview,
            button_color=accent_color,
            button_hover_color="#819BB9",
            fg_color="#F3F4F1",
            corner_radius=8,
            height=14,
        )
        self.hscroll.grid(row=1, column=0, sticky="ew", padx=(8, 2), pady=(2, 8))
        self.tree.configure(
            yscrollcommand=self.vscroll.set,
            xscrollcommand=self.hscroll.set,
        )

        for column in columns:
            self.tree.heading(column, text=column, anchor="w")
            self.tree.column(
                column,
                width=minimum_widths[column],
                minwidth=minimum_widths[column],
                anchor="w",
                stretch=(column == "Status"),
            )

        self._configure_status_tags()
        self.tree.bind("<Button-1>", on_pre_release_click)
        self.tree.bind("<Double-1>", on_double_click)
        self.tree.bind("<Configure>", on_resize)
        self.outer.bind("<Configure>", on_resize)

    def _configure_status_tags(self) -> None:
        """Configure semantic row colors independently from window orchestration."""
        tag_colors = {
            "current": ("#F1F8ED", "#326A3B"),
            "manual": ("#F6E6A8", "#5D4A12"),
            "update": ("#FFF4EF", "#A43F28"),
            "unmatched": ("#FCE9E7", "#A82E2E"),
            "unavailable": ("#F2F3F0", "#596579"),
            "removed": ("#F8DEDC", "#8B2520"),
            "download_row": ("#F1F4F8", "#536273"),
            "download_available": ("#FFF0D9", "#9A4D00"),
            "download_busy": ("#DDE8F6", "#2C5687"),
            "download_failed": ("#FCE9E7", "#A82E2E"),
        }
        for tag, (background, foreground) in tag_colors.items():
            self.tree.tag_configure(
                tag, background=background, foreground=foreground
            )
