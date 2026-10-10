"""Regression checks for responsive table column configuration."""
import ast
import unittest
from pathlib import Path


class ColumnConfigurationTests(unittest.TestCase):
    def test_each_displayed_column_has_width_and_weight(self):
        source = Path(__file__).resolve().parents[1] / "app" / "gui.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        main_window = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
        )
        values = {}
        for node in main_window.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {
                        "COLUMNS", "COLUMN_WEIGHTS", "COLUMN_MIN_WIDTHS"
                    }:
                        values[target.id] = ast.literal_eval(node.value)
        columns = set(values["COLUMNS"])
        self.assertEqual(columns, set(values["COLUMN_WEIGHTS"]))
        self.assertEqual(columns, set(values["COLUMN_MIN_WIDTHS"]))
        self.assertIn("Pre-release", columns)
        self.assertGreater(values["COLUMN_WEIGHTS"]["Pre-release"], 0)


if __name__ == "__main__":
    unittest.main()

class TableRowShapeTests(unittest.TestCase):
    def test_normal_and_downloader_rows_match_displayed_column_count(self):
        source = Path(__file__).resolve().parents[1] / "app" / "gui.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        main_window = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
        )
        methods = {node.name: node for node in main_window.body if isinstance(node, ast.FunctionDef)}
        for method_name in ("_populate_table", "_populate_download_rows"):
            method = methods[method_name]
            row_tuple = next(
                node.value for node in ast.walk(method)
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "values" for target in node.targets)
                and isinstance(node.value, ast.Tuple)
            )
            self.assertEqual(len(row_tuple.elts), 9, method_name)
