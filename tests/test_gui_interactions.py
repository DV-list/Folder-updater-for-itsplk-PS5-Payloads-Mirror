import unittest
from unittest.mock import Mock, patch

from app.gui import MainWindow
from app.models import PayloadEntry
from app.reconciler import CONTROL_APP_DOWNLOAD


class FakeTree:
    def __init__(self, iid, values):
        self.iid = iid
        self.values = values
        self.column_id = "#9"

    def identify_row(self, _y):
        return self.iid

    def item(self, _iid, _option):
        return self.values

    def identify_column(self, _x):
        return self.column_id

    def identify(self, _region, _x, _y):
        return "cell"

    def selection_set(self, _iid):
        pass

    def focus(self, _iid):
        pass


class TableDoubleClickTests(unittest.TestCase):
    def make_window(self, iid, status):
        window = MainWindow.__new__(MainWindow)
        values = ["Demo Payload", "demo.elf", "abc", "1.0", "2026-01-01 00:00:00", "—", "2.0", "def", status]
        window.tree = FakeTree(iid, values)
        window.COLUMNS = MainWindow.COLUMNS
        window.root = object()
        window._download_rows = {"download_row_0": PayloadEntry("Demo Payload", "demo.elf", "2.0", "def", "https://example.invalid/demo.elf")}
        window._download_running = False
        window._active_download_entry = None
        window.control_app_download_callback = Mock()
        window._start_download = Mock()
        window._show_in_explorer = Mock()
        return window

    @patch("app.gui.messagebox.askokcancel", return_value=True)
    def test_not_downloaded_double_click_prompts_then_starts_download(self, prompt):
        window = self.make_window("download_row_0", "Not Downloaded")
        event = Mock(y=10)
        self.assertEqual(window._on_table_double_click(event), "break")
        prompt.assert_called_once()
        window._start_download.assert_called_once_with("download_row_0")
        window._show_in_explorer.assert_not_called()

    @patch("app.gui.messagebox.askokcancel", return_value=False)
    def test_cancelled_download_does_not_start(self, prompt):
        window = self.make_window("download_row_0", "Not Downloaded")
        window._on_table_double_click(Mock(y=10))
        prompt.assert_called_once()
        window._start_download.assert_not_called()
        window._show_in_explorer.assert_not_called()

    def test_non_not_downloaded_row_opens_explorer(self):
        window = self.make_window("download_row_0", "Download Failed — click to retry")
        window._on_table_double_click(Mock(y=10))
        window._show_in_explorer.assert_called_once()
        window._start_download.assert_not_called()

    @patch("app.gui.messagebox.askokcancel", return_value=True)
    def test_control_app_download_row_prompts_and_starts_special_download(self, prompt):
        window = self.make_window("control_app_row", CONTROL_APP_DOWNLOAD)
        self.assertEqual(window._on_table_double_click(Mock(y=10)), "break")
        prompt.assert_called_once()
        self.assertIn("ps5upload control app", prompt.call_args.args[1])
        window._start_download.assert_called_once_with("control_app_row")
        window._show_in_explorer.assert_not_called()

    @patch("app.gui.messagebox.askokcancel", return_value=False)
    def test_cancel_control_app_download_does_not_start(self, prompt):
        window = self.make_window("control_app_row", CONTROL_APP_DOWNLOAD)
        self.assertEqual(window._on_table_double_click(Mock(y=10)), "break")
        prompt.assert_called_once()
        window._start_download.assert_not_called()
        window._show_in_explorer.assert_not_called()

    def test_control_app_download_failure_row_can_be_retried(self):
        with patch("app.gui.messagebox.askokcancel", return_value=True):
            window = self.make_window("control_app_row", "Download Failed — double-click to retry")
            self.assertEqual(window._on_table_double_click(Mock(y=10)), "break")
            window._start_download.assert_called_once_with("control_app_row")

    def test_control_app_download_status_uses_orange_available_tag(self):
        window = MainWindow.__new__(MainWindow)
        self.assertEqual(window._status_tag(CONTROL_APP_DOWNLOAD), "download_available")

    def test_local_row_opens_explorer(self):
        window = self.make_window("local_row_0", "CURRENT")
        window._on_table_double_click(Mock(y=10))
        window._show_in_explorer.assert_called_once()

    @patch("app.gui.messagebox.askokcancel", return_value=True)
    def test_double_click_in_pre_release_column_never_downloads(self, prompt):
        window = self.make_window("download_row_0", "Not Downloaded")
        window.tree.column_id = f"#{window.COLUMNS.index('Pre-release') + 1}"
        self.assertEqual(window._on_table_double_click(Mock(x=200, y=10)), "break")
        prompt.assert_not_called()
        window._start_download.assert_not_called()
        window._show_in_explorer.assert_not_called()

    def test_pre_release_checkbox_click_saves_boolean_without_row_action(self):
        window = self.make_window("local_row_0", "CURRENT")
        values = list(window.tree.values)
        values[window.COLUMNS.index("Pre-release")] = window.PRE_RELEASE_OFF
        window.tree.values = tuple(values)
        window.tree.column_id = f"#{window.COLUMNS.index('Pre-release') + 1}"
        from app.models import ScanResult
        window.pre_release_callback = Mock(return_value=ScanResult(rows=[], state_records=[]))
        window.result = ScanResult(rows=[], state_records=[])
        window.download_candidates = []
        window._discovery_error = None
        window._update_running = False
        window._download_running = False
        window._scan_running = False
        window.logger = Mock()
        window.summary_label = Mock()
        window._replace_table_rows = Mock()
        window._show_discovery_error = Mock()

        self.assertEqual(window._on_pre_release_click(Mock(x=200, y=10)), "break")
        window.pre_release_callback.assert_called_once_with("abc", True)
        window._replace_table_rows.assert_called_once()

    def test_single_click_in_pre_release_column_on_download_placeholder_is_consumed(self):
        window = self.make_window("download_row_0", "Not Downloaded")
        window.tree.column_id = f"#{window.COLUMNS.index('Pre-release') + 1}"
        window.pre_release_callback = Mock()
        window._update_running = False
        window._scan_running = False
        self.assertEqual(window._on_pre_release_click(Mock(x=200, y=10)), "break")
        window.pre_release_callback.assert_not_called()
        window._start_download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
