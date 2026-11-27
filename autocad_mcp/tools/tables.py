"""Tables (schedules, sheet indexes) as real AutoCAD TABLE objects. One undo step per call."""

from __future__ import annotations

from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, point
from ..session import session
from .draw import drawing_space, place
from .layers import find_layer

Point = list[float]

MAX_CELLS = 5000
MAX_COLUMNS = 100


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


@acad_tool()
def add_table(insertion: Point, data: list[list[Any]], col_widths: float | list[float] = 2.0,
              row_height: float = 0.4, text_height: float = 0.125, title: str = "", style: str = "",
              layer: str = "", layout: str = "", name: str = "") -> dict:
    """Add a table (TABLE object) filled with data, as one undo step: a door or window schedule,
    a sheet index. The first row of data is the header row; with title, a title row spanning all
    columns goes above it. Edit the result in AutoCAD like any table.

    Args:
        insertion: the table's top-left corner [x, y].
        data: rows of cell values, e.g. [["MARK", "SIZE"], ["101", "3'-0\\" x 7'-0\\""]]. Short rows
            are padded with empty cells; numbers are written as text. At most 5000 cells, 100 columns.
        col_widths: one width for every column, or a list with one width per column (drawing units).
        row_height: minimum row height; AutoCAD makes a row taller when its text needs it.
        text_height: text height in every cell.
        title: optional title row above the data, merged across all columns.
        style: table style name (default: the drawing's current table style).
        layer: layer to put it on (default: current layer).
        layout: a sheet's layout name to put it on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    if not isinstance(data, list) or not data or not all(isinstance(r, list) for r in data):
        raise AcadError("data is a list of rows, each a list of cell values, with at least one row.")
    columns = max(len(r) for r in data)
    if columns < 1:
        raise AcadError("data needs at least one cell.")
    if columns > MAX_COLUMNS:
        raise AcadError(f"At most {MAX_COLUMNS} columns; data has {columns}.")
    rows = len(data) + (1 if title else 0)
    if rows * columns > MAX_CELLS:
        raise AcadError(f"At most {MAX_CELLS} cells per table; this one has {rows * columns}.")
    widths = [col_widths] * columns if isinstance(col_widths, (int, float)) else list(col_widths)
    if len(widths) != columns:
        raise AcadError(f"col_widths has {len(widths)} widths for {columns} columns; give one per column "
                        f"or a single number.")
    if any(not isinstance(w, (int, float)) or w <= 0 for w in widths):
        raise AcadError("Every column width must be a positive number.")
    if row_height <= 0 or text_height <= 0:
        raise AcadError("row_height and text_height must be positive.")
    doc = session.document(name)
    if layer and find_layer(doc, layer) is None:
        raise AcadError(f"No layer named '{layer}'. Create it with add_layer first.")
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        table = change.add(space.AddTable(point(insertion), rows, columns, float(row_height), float(widths[0])))
        if style:
            try:
                table.StyleName = style.strip()
            except pywintypes.com_error:
                raise AcadError(f"No table style named '{style}' in '{doc.Name}' (or AutoCAD refused it).") from None
        table.RegenerateTableSuppressed = True  # AutoCAD help: rebuild once at the end, not after every cell
        for col, width in enumerate(widths):
            if col and width != widths[0]:
                table.SetColumnWidth(col, float(width))
        merged = _title_row(table, bool(title), columns)
        first = 0
        if title:
            table.SetText(0, 0, title)
            table.SetCellTextHeight(0, 0, float(text_height))
            first = 1
        for r, row in enumerate(data):
            for c in range(columns):
                table.SetText(first + r, c, _cell(row[c]) if c < len(row) else "")
                table.SetCellTextHeight(first + r, c, float(text_height))
        table.RegenerateTableSuppressed = False
        info = place(change, table, layer, where)
        info.update(rows=rows, columns=columns, title=title, header_row=first, col_widths=[float(w) for w in widths],
                    style=str(table.StyleName))
        if merged is not None:
            info["title_merged"] = merged
        for key, prop in (("width", "Width"), ("height", "Height")):
            try:
                info[key] = round(float(getattr(table, prop)), 6)
            except (pywintypes.com_error, AttributeError, TypeError, ValueError):
                pass  # only a report
        return info


def _title_row(table: Any, title: bool, columns: int) -> bool | None:
    """Table styles usually merge row 0 into a title cell. With a title, make sure it spans every
    column; without one, unmerge it so row 0 holds the header cells. Returns whether row 0 ends
    up merged (None for a one-column table, where it makes no difference)."""
    if columns < 2:
        return None
    try:
        if title:
            table.MergeCells(0, 0, 0, columns - 1)
        else:
            table.UnmergeCells(0, 0, 0, columns - 1)
    except pywintypes.com_error:
        pass  # inferred: already in the wanted state (merging merged cells is refused); not seen live
    return title
