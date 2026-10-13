"""Pure helpers for content-driven application window and table layout.

This module deliberately has no Tkinter dependency. Layout calculations can therefore
be exercised with deterministic unit tests without opening a GUI window.
"""

from collections.abc import Callable, Mapping, Sequence


CHECKSUM_COLUMNS = frozenset({"CurrDirChecksum", "ServerChecksum"})
CHECKSUM_CONTENT_RATIO = 0.5
CELL_HORIZONTAL_PADDING = 24


def calculate_natural_column_widths(
    columns: Sequence[str],
    values_by_column: Mapping[str, Sequence[str]],
    minimum_widths: Mapping[str, int],
    measure_body: Callable[[str], int],
    measure_heading: Callable[[str], int],
    *,
    horizontal_padding: int = CELL_HORIZONTAL_PADDING,
    checksum_columns: frozenset[str] = CHECKSUM_COLUMNS,
    checksum_content_ratio: float = CHECKSUM_CONTENT_RATIO,
) -> dict[str, int]:
    """Measure natural widths, limiting checksum text to a fraction of its full width."""
    if not 0 < checksum_content_ratio <= 1:
        raise ValueError("checksum_content_ratio must be in the interval (0, 1].")
    if horizontal_padding < 0:
        raise ValueError("horizontal_padding cannot be negative.")

    widths: dict[str, int] = {}
    for column in columns:
        heading_width = measure_heading(column)
        body_width = max(
            (measure_body(str(value)) for value in values_by_column.get(column, ())),
            default=0,
        )
        if column in checksum_columns:
            body_width = int(body_width * checksum_content_ratio)
        content_width = max(heading_width, body_width)
        widths[column] = max(
            minimum_widths[column],
            content_width + horizontal_padding,
        )
    return widths


def calculate_responsive_column_widths(
    columns: Sequence[str],
    natural_widths: Mapping[str, int],
    minimum_widths: Mapping[str, int],
    weights: Mapping[str, float],
    available_width: int,
) -> dict[str, int]:
    """Distribute available table width while respecting each column's minimum."""
    if available_width < 0:
        raise ValueError("available_width cannot be negative.")
    if any(weights[column] <= 0 for column in columns):
        raise ValueError("Every displayed column must have a positive resize weight.")

    natural_total = sum(natural_widths[column] for column in columns)
    minimum_total = sum(minimum_widths[column] for column in columns)
    target_width = max(available_width, minimum_total)

    if target_width >= natural_total:
        extra = target_width - natural_total
        weight_total = sum(weights[column] for column in columns)
        widths = {
            column: natural_widths[column]
            + int(extra * weights[column] / weight_total)
            for column in columns
        }
    else:
        shrinkable = max(natural_total - minimum_total, 1)
        reduction = natural_total - target_width
        widths = {
            column: max(
                minimum_widths[column],
                natural_widths[column]
                - int(
                    reduction
                    * (natural_widths[column] - minimum_widths[column])
                    / shrinkable
                ),
            )
            for column in columns
        }

    # Integer rounding must not leave an unused strip after the final column.
    delta = target_width - sum(widths.values())
    for column in reversed(columns):
        if delta == 0:
            break
        if delta > 0:
            widths[column] += delta
            delta = 0
            break

        reducible = widths[column] - minimum_widths[column]
        reduction = min(reducible, -delta)
        widths[column] -= reduction
        delta += reduction

    return widths


def centered_window_geometry(
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
    *,
    screen_margin: int = 24,
) -> tuple[int, int, int, int]:
    """Return a screen-bounded (width, height, x, y) geometry centered on screen."""
    if min(width, height, screen_width, screen_height) <= 0:
        raise ValueError("Window and screen dimensions must be positive.")
    if screen_margin < 0:
        raise ValueError("screen_margin cannot be negative.")

    max_width = max(1, screen_width - 2 * screen_margin)
    max_height = max(1, screen_height - 2 * screen_margin)
    actual_width = min(width, max_width)
    actual_height = min(height, max_height)
    x = max(0, (screen_width - actual_width) // 2)
    y = max(0, (screen_height - actual_height) // 2)
    return actual_width, actual_height, x, y
