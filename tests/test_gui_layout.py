"""Unit tests for deterministic, Tk-independent GUI layout helpers."""

import unittest

from app.gui import MainWindow
from app.gui_layout import (
    calculate_natural_column_widths,
    calculate_responsive_column_widths,
    centered_window_geometry,
)


class NaturalColumnWidthTests(unittest.TestCase):
    def test_checksum_columns_use_half_of_the_longest_checksum_width(self):
        columns = ("Payload", "CurrDirChecksum", "ServerChecksum")
        values = {
            "Payload": ("PS5Upload",),
            "CurrDirChecksum": ("a" * 64,),
            "ServerChecksum": ("b" * 64,),
        }
        minimums = {"Payload": 80, "CurrDirChecksum": 120, "ServerChecksum": 120}
        body_width = lambda value: len(value) * 10
        heading_width = lambda value: len(value) * 8

        widths = calculate_natural_column_widths(
            columns, values, minimums, body_width, heading_width
        )

        self.assertEqual(widths["CurrDirChecksum"], 344)
        self.assertEqual(widths["ServerChecksum"], 344)
        self.assertEqual(widths["Payload"], 114)
        self.assertLess(widths["CurrDirChecksum"], body_width("a" * 64) + 24)

    def test_checksum_width_can_never_collapse_below_minimum(self):
        columns = ("CurrDirChecksum", "ServerChecksum")
        widths = calculate_natural_column_widths(
            columns,
            {"CurrDirChecksum": ("",), "ServerChecksum": ("",)},
            {"CurrDirChecksum": 190, "ServerChecksum": 190},
            lambda _value: 0,
            lambda _value: 20,
        )
        self.assertEqual(widths, {"CurrDirChecksum": 190, "ServerChecksum": 190})

    def test_invalid_checksum_ratio_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_natural_column_widths(
                ("CurrDirChecksum",),
                {},
                {"CurrDirChecksum": 100},
                lambda value: len(value),
                lambda value: len(value),
                checksum_content_ratio=0,
            )


class ResponsiveColumnWidthTests(unittest.TestCase):
    COLUMNS = ("Payload", "CurrDirChecksum", "Status")
    NATURAL = {"Payload": 140, "CurrDirChecksum": 340, "Status": 160}
    MINIMUM = {"Payload": 80, "CurrDirChecksum": 120, "Status": 80}
    WEIGHTS = {"Payload": 1.0, "CurrDirChecksum": 1.0, "Status": 1.0}

    def test_columns_exactly_fill_available_width_when_growing(self):
        widths = calculate_responsive_column_widths(
            self.COLUMNS, self.NATURAL, self.MINIMUM, self.WEIGHTS, 760
        )
        self.assertEqual(sum(widths.values()), 760)
        self.assertTrue(all(widths[name] >= self.MINIMUM[name] for name in self.COLUMNS))

    def test_columns_exactly_fill_available_width_when_shrinking(self):
        widths = calculate_responsive_column_widths(
            self.COLUMNS, self.NATURAL, self.MINIMUM, self.WEIGHTS, 500
        )
        self.assertEqual(sum(widths.values()), 500)
        self.assertTrue(all(widths[name] >= self.MINIMUM[name] for name in self.COLUMNS))

    def test_columns_keep_minimum_widths_when_container_is_too_small(self):
        widths = calculate_responsive_column_widths(
            self.COLUMNS, self.NATURAL, self.MINIMUM, self.WEIGHTS, 200
        )
        self.assertEqual(widths, self.MINIMUM)
        self.assertGreater(sum(widths.values()), 200)

    def test_nonpositive_resize_weights_are_rejected(self):
        invalid_weights = dict(self.WEIGHTS, Status=0)
        with self.assertRaises(ValueError):
            calculate_responsive_column_widths(
                self.COLUMNS, self.NATURAL, self.MINIMUM, invalid_weights, 760
            )


class CenteredWindowGeometryTests(unittest.TestCase):
    def test_geometry_is_centered_on_screen(self):
        geometry = centered_window_geometry(800, 600, 1920, 1080)
        self.assertEqual(geometry, (800, 600, 560, 240))

    def test_geometry_is_clamped_to_screen_bounds(self):
        width, height, x, y = centered_window_geometry(3000, 2000, 1366, 768)
        self.assertEqual((width, height), (1318, 720))
        self.assertEqual((x, y), (24, 24))

    def test_invalid_geometry_is_rejected(self):
        with self.assertRaises(ValueError):
            centered_window_geometry(0, 600, 1920, 1080)


class TableColumnNamingTests(unittest.TestCase):
    def test_column_names_are_space_free_and_layout_keys_match(self):
        self.assertTrue(MainWindow.COLUMNS)
        self.assertTrue(all(" " not in name for name in MainWindow.COLUMNS))
        self.assertEqual(set(MainWindow.COLUMNS), set(MainWindow.COLUMN_WEIGHTS))
        self.assertEqual(set(MainWindow.COLUMNS), set(MainWindow.COLUMN_MIN_WIDTHS))


if __name__ == "__main__":
    unittest.main()
