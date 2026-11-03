"""Layouts (paper space sheets) and viewports onto model space."""

from __future__ import annotations

from ..app import acad_tool
from ..com import AcadError, enums, point, xyz
from ..session import session
from .draw import Point, place
from .entities import find_layout


@acad_tool(read_only=True)
def list_layouts(name: str = "") -> list:
    """List the drawing's sheets (layouts) in tab order, with the viewports and block references
    (such as the title block) on each. Use the handles with get_entity and set_block_attributes.

    Args:
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    layouts = sorted((doc.Layouts.Item(i) for i in range(doc.Layouts.Count)), key=lambda lay: int(lay.TabOrder))
    out = []
    for layout in layouts:
        info = {"name": str(layout.Name), "model": bool(layout.ModelType)}
        if not info["model"]:
            block = layout.Block
            items = [block.Item(i) for i in range(block.Count)]
            info["viewports"] = [str(e.Handle) for e in items if str(e.ObjectName) == "AcDbViewport"]
            info["blocks"] = [{"handle": str(e.Handle), "name": str(e.EffectiveName)} for e in items
                              if str(e.ObjectName) == "AcDbBlockReference"]
            info["entities"] = len(items)
        out.append(info)
    return out


@acad_tool()
def add_viewport(layout: str, corner: Point, opposite_corner: Point, view_center: Point, scale: float,
                 layer: str = "", lock: bool = True, name: str = "") -> dict:
    """Add a viewport to a sheet (layout) that shows model space at an exact scale, centred on a
    model point. The sheet becomes the current layout tab. One undo step.

    Args:
        layout: the sheet's layout name (see list_layouts).
        corner, opposite_corner: the viewport rectangle on the sheet, in paper units (inches on an
            inch sheet) [x, y].
        view_center: the model-space point shown in the middle of the viewport [x, y].
        scale: paper units per model unit. 1 is full size (1:1), 0.5 is half size (1:2), 0.25 is
            1:4; for 1/2" = 1'-0" in an inch drawing use 0.5/12.
        layer: layer for the viewport frame (default: current layer).
        lock: lock the view so clicking inside it cannot pan or zoom it (default True).
        name: which open drawing; it must be the active one.
    """
    if scale <= 0:
        raise AcadError("scale must be positive.")
    (x1, y1, _), (x2, y2, _) = xyz(corner), xyz(opposite_corner)
    width, height = abs(x2 - x1), abs(y2 - y1)
    if width == 0 or height == 0:
        raise AcadError("corner and opposite_corner must span a rectangle.")
    doc = session.document(name)
    if str(doc.Name) != str(session.app.ActiveDocument.Name):
        raise AcadError(f"'{doc.Name}' is not the active drawing; AutoCAD only sets up viewports in the active one.")
    sheet = find_layout(doc, layout)
    if bool(sheet.ModelType):
        raise AcadError("Pick a paper layout (a sheet), not Model.")
    cx, cy, _ = xyz(view_center)
    half_w, half_h = width / 2 / scale, height / 2 / scale
    with session.edit(doc) as change:
        previous = doc.ActiveLayout
        if str(previous.Name) != str(sheet.Name):
            doc.ActiveLayout = sheet
            change.on_rollback(lambda: setattr(doc, "ActiveLayout", previous))
        viewport = doc.PaperSpace.AddPViewport(point([(x1 + x2) / 2, (y1 + y2) / 2]), width, height)
        change.add(viewport)
        viewport.Display(True)
        try:
            doc.MSpace = True
            doc.ActivePViewport = viewport
            # Frame exactly the model area the viewport shows at this scale, then pin the scale.
            session.app.ZoomWindow(point([cx - half_w, cy - half_h]), point([cx + half_w, cy + half_h]))
            viewport.StandardScale = enums.acVpCustomScale
            viewport.CustomScale = float(scale)
        finally:
            doc.MSpace = False
        if lock:
            viewport.DisplayLocked = True
        info = place(change, viewport, layer)
        info.update(layout=str(sheet.Name), view_center=[cx, cy])
        return info
