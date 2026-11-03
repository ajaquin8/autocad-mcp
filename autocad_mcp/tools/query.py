"""Read-only inspection: drawing summary, entity queries, view capture."""

from __future__ import annotations

import ctypes
import io
import time
from collections import Counter

import win32gui
import win32ui
from mcp.server.mcpserver import Image
from PIL import Image as PILImage

from ..app import acad_tool
from ..com import AcadError, rounded
from ..session import session
from .entities import by_handle, details, layout_space, model_space, summary

SCAN_LIMIT = 50_000  # entities read per call before stopping, so a huge drawing cannot hang a call
PW_RENDERFULLCONTENT = 2
SETTLE_SECONDS = 3.0  # longest wait for AutoCAD to go idle before a screenshot


@acad_tool(read_only=True)
def drawing_info(name: str = "") -> dict:
    """Summarize a drawing: units, extents, layer and layout counts, and model space
    entity counts by type and by layer.

    Args:
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    by_type: Counter = Counter()
    by_layer: Counter = Counter()
    scanned = 0
    for ent in model_space(doc):
        if scanned >= SCAN_LIMIT:
            break
        by_type[str(ent.ObjectName)] += 1
        by_layer[str(ent.Layer)] += 1
        scanned += 1
    info = session.describe(doc)
    info.update(
        units=session.units(doc),
        extents=[rounded(doc.GetVariable("EXTMIN")[:2]), rounded(doc.GetVariable("EXTMAX")[:2])],
        layers=int(doc.Layers.Count),
        layouts=[str(doc.Layouts.Item(i).Name) for i in range(doc.Layouts.Count)],
        current_layer=str(doc.ActiveLayer.Name),
        model_space_entities=int(doc.ModelSpace.Count),
        by_type=dict(by_type.most_common()),
        by_layer=dict(by_layer.most_common()),
    )
    if scanned >= SCAN_LIMIT:
        info["note"] = f"Counts cover the first {SCAN_LIMIT} entities only."
    return info


@acad_tool(read_only=True)
def query_entities(object_type: str = "", layer: str = "", limit: int = 100, offset: int = 0,
                   layout: str = "", name: str = "") -> dict:
    """Find entities by type and/or layer, in model space or on one layout (paper space, where
    title blocks and viewports live). Returns handle, type, layer and bounding box; use
    get_entity for full details.

    Args:
        object_type: part of the AutoCAD type name, case-insensitive, e.g. "Line" (matches
            AcDbLine), "Polyline", "BlockReference", "Dimension", "Text".
        layer: exact layer name, case-insensitive.
        limit: max results (1-500).
        offset: skip this many matches (paging).
        layout: a layout name (see list_layouts) to search its paper space instead of model space.
        name: which open drawing (default: active).
    """
    limit = max(1, min(int(limit), 500))
    doc = session.document(name)
    kind, lay = object_type.lower(), layer.lower()
    matches, results, scanned = 0, [], 0
    for ent in (layout_space(doc, layout) if layout else model_space(doc)):
        scanned += 1
        if scanned > SCAN_LIMIT:
            break
        if kind and kind not in str(ent.ObjectName).lower():
            continue
        if lay and str(ent.Layer).lower() != lay:
            continue
        matches += 1
        if matches > offset and len(results) < limit:
            results.append(summary(ent))
    out = {"matches": matches, "returned": len(results), "offset": offset, "entities": results}
    if scanned > SCAN_LIMIT:
        out["note"] = f"Stopped after scanning {SCAN_LIMIT} entities; narrow the query."
    return out


@acad_tool(read_only=True)
def get_entity(handle: str, name: str = "") -> dict:
    """Full details of one entity: coordinates, sizes, text, block attributes or
    dimension measurement, depending on its type.

    Args:
        handle: the entity's handle.
        name: which open drawing (default: active).
    """
    return details(by_handle(session.document(name), handle))


@acad_tool()
def zoom_extents(name: str = "") -> str:
    """Zoom the active view to show the whole drawing. Changes the user's view, not the drawing.

    Args:
        name: which open drawing; it must be the active one.
    """
    doc = session.document(name)
    session.require_idle(doc)
    if str(doc.Name) != str(session.app.ActiveDocument.Name):
        raise AcadError(f"'{doc.Name}' is not the active drawing; AutoCAD only zooms the active one.")
    session.app.ZoomExtents()
    return "Zoomed to extents."


def window_png(hwnd: int, max_width: int) -> bytes:
    """Grab a window with PrintWindow (works when it is covered by other windows) as PNG."""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise AcadError("The AutoCAD window has no size (is it minimized?).")
    window_dc = win32gui.GetWindowDC(hwnd)
    source = win32ui.CreateDCFromHandle(window_dc)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        memory.SelectObject(bitmap)
        ctypes.windll.user32.PrintWindow(hwnd, memory.GetSafeHdc(), PW_RENDERFULLCONTENT)
        image = PILImage.frombuffer("RGB", (width, height), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)
    if image.width > max_width:
        image = image.resize((max_width, round(image.height * max_width / image.width)))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@acad_tool(read_only=True)
def capture_view(max_width: int = 1600) -> Image:
    """Screenshot the AutoCAD window so you can SEE the drawing. Use after drawing steps
    (zoom_extents first if the new geometry may be off screen).

    Args:
        max_width: scale the picture down to at most this many pixels wide (400-3000).
    """
    app = session.app
    hwnd = int(app.HWND)
    if win32gui.IsIconic(hwnd):
        raise AcadError("AutoCAD is minimized; ask the user to restore the window.")
    # A capture straight after a zoom came back blank (2026-10-29): let AutoCAD finish redrawing.
    deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < deadline and not bool(app.GetAcadState().IsQuiescent):
        time.sleep(0.1)
    app.Update()
    time.sleep(0.4)
    return Image(data=window_png(hwnd, max(400, min(int(max_width), 3000))), format="png")
