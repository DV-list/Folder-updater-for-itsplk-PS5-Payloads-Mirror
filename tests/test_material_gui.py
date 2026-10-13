"""Guardrails for the fast Treeview table and CustomTkinter styling."""
import unittest
from pathlib import Path


class MaterialGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.source = (root / "app" / "gui.py").read_text(encoding="utf-8")
        cls.table_source = (root / "app" / "gui_table.py").read_text(encoding="utf-8")

    def test_table_uses_native_treeview_for_fast_row_updates(self):
        self.assertIn("from tkinter import ttk", self.table_source)
        self.assertIn("self.tree = ttk.Treeview(", self.table_source)
        self.assertIn("self.table = PayloadTable(", self.source)
        self.assertNotIn("class MaterialTable", self.table_source)

    def test_treeview_keeps_customtkinter_rounded_scrollbars(self):
        self.assertIn("ctk.CTkScrollbar(", self.table_source)
        self.assertIn("yscrollcommand=self.vscroll.set", self.table_source)
        self.assertIn("xscrollcommand=self.hscroll.set", self.table_source)

    def test_progress_bar_uses_customtkinter_blue_accent(self):
        self.assertIn("ctk.CTkProgressBar(", self.source)
        self.assertIn("progress_color=self.UPDATE_BLUE", self.source)

    def test_progress_indicator_has_no_outline_and_status_panel_uses_neutral_border(self):
        self.assertIn('border_width=0, corner_radius=6, indeterminate_speed=1.5', self.source)
        self.assertIn('border_color="#DCE4EF")', self.source)

    def test_close_handler_forcibly_exits_when_worker_is_stuck(self):
        self.assertIn('self.root.protocol("WM_DELETE_WINDOW", self._on_close)', self.source)
        self.assertIn('def _on_close(self) -> None:', self.source)
        self.assertIn('os._exit(0)', self.source)

    def test_update_button_keeps_dynamic_blue_state(self):
        self.assertIn("button_color = self.UPDATE_BLUE if has_updates else self.UPDATE_GRAY", self.source)
        self.assertIn("hover_color = self.UPDATE_HOVER_BLUE if has_updates else self.UPDATE_HOVER_GRAY", self.source)
        self.assertIn('getattr(self.result, "update_count", 0)', self.source)
        self.assertIn('self.update_button.configure(\n            fg_color=button_color', self.source)
        self.assertNotIn("disabled_color=", self.source)
        self.assertIn('text_color_disabled="#FFFFFF"', self.source)
        self.assertIn("fg_color=button_color", self.source)

    def test_requested_palette_is_defined(self):
        for color in ("GLOSSY_CORAL", "TANGY", "FEIJOA", "LIGHT_STEEL", "DIANA", "MILLIE"):
            self.assertIn(color, self.source)

    def test_control_app_download_status_is_orange_and_uppercase(self):
        from app.reconciler import CONTROL_APP_DOWNLOAD
        self.assertEqual(CONTROL_APP_DOWNLOAD, "DOWNLOAD")
        self.assertIn('"download_available": ("#FFF0D9", "#9A4D00")', self.table_source)
        self.assertIn('if status == CONTROL_APP_DOWNLOAD:', self.source)
        self.assertIn('return "download_available"', self.source)

    def test_treeview_font_and_centered_content_sized_startup(self):
        self.assertIn('font=("Segoe UI", 11)', self.table_source)
        self.assertIn('font=("Segoe UI Semibold", 11, "bold")', self.table_source)
        self.assertIn('font=("Segoe UI", 28, "bold")', self.source)
        self.assertIn("centered_window_geometry(", self.source)
        self.assertIn('self.root.geometry(f"{width}x{height}+{x}+{y}")', self.source)
        self.assertIn("self.root.winfo_screenwidth()", self.source)

    def test_update_color_uses_reconciliation_result_as_authority(self):
        state = self.source.split('    def _set_update_button_state(self) -> None:', 1)[1].split('    def _set_final_update_status', 1)[0]
        self.assertIn('for row in getattr(self.result, "rows", ())', state)
        self.assertIn('self.UPDATE_BLUE if has_updates else self.UPDATE_GRAY', state)
        self.assertIn('getattr(self.result, "update_count", 0)', state)

    def test_update_button_uses_model_update_count(self):
        # The GUI must turn the button blue even if the Treeview is in the middle
        # of a refresh and temporarily has no status rows.
        from app.gui import MainWindow
        from app.models import ScanResult
        import logging

        class Button:
            def __init__(self):
                self.kwargs = {}

            def configure(self, **kwargs):
                self.kwargs.update(kwargs)

        class Root:
            def update_idletasks(self):
                pass

        window = MainWindow.__new__(MainWindow)
        window.result = ScanResult(rows=[], state_records=[], update_count=1)
        window.update_button = Button()
        window.root = Root()
        window.logger = logging.getLogger("test-update-button")
        window._update_running = False
        window._download_running = False
        window._scan_running = False
        window._set_update_button_state()
        self.assertEqual(window.update_button.kwargs["fg_color"], MainWindow.UPDATE_BLUE)
        self.assertEqual(window.update_button.kwargs["hover_color"], MainWindow.UPDATE_HOVER_BLUE)

    def test_treeview_uses_full_widget_width_for_columns(self):
        state = self.source.split('    def _sync_table_layout(self) -> None:', 1)[1].split('    def _calculate_natural_widths', 1)[0]
        self.assertIn('available = max(self.tree.winfo_width(), 1)', state)
        self.assertNotIn('winfo_width() - 28', state)
        self.assertIn('stretch=(column == "Status")', state)


if __name__ == "__main__":
    unittest.main()
