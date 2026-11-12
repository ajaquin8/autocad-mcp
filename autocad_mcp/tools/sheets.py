"""Layouts (paper space sheets) and viewports onto model space."""

from __future__ import annotations

from ..app import acad_tool
from ..com import AcadError, enums, point, xyz
from ..session import session
from .draw import Point, place
from .entities import find_layout
from .plot import best_pdf_device


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


def _strings(values) -> list[str]:
    return [str(v) for v in (values or ())]


def match_one(wanted: str, names: list[str], kind: str) -> str:
    """The one name `wanted` means: the same name (ignoring case), else the only one that contains
    it, else the only one that contains all its words. Otherwise an error that lists the candidates."""
    key = " ".join(wanted.lower().split())
    lowered = [" ".join(n.lower().split()) for n in names]
    tests = (lambda n: n == key, lambda n: key in n, lambda n: all(word in n for word in key.split()))
    for test in tests if key else ():
        found = [names[i] for i, n in enumerate(lowered) if test(n)]
        if len(found) == 1:
            return found[0]
        if found:
            more = " ..." if len(found) > 12 else ""
            raise AcadError(f"'{wanted}' matches several {kind}s: {'; '.join(found[:12])}{more}. "
                            "Give one of these names in full.")
    more = " ..." if len(names) > 40 else ""
    raise AcadError(f"No {kind} matches '{wanted}'. Available: {'; '.join(names[:40])}{more}.")


def describe_page_setup(sheet) -> dict:
    return {"layout": str(sheet.Name), "device": str(sheet.ConfigName), "paper": str(sheet.CanonicalMediaName),
            "paper_name": str(sheet.GetLocaleMediaName(sheet.CanonicalMediaName)),
            "plot_style": str(sheet.StyleSheet), "plot_area": "layout", "scale": "1:1"}


@acad_tool()
def set_page_setup(layout: str, paper: str, plot_style: str = "", device: str = "", name: str = "",
                   plot_device: str = "") -> dict:
    """Set a sheet's page setup: plot device, paper size and, if given, the plot style table.
    The sheet then plots its whole layout at 1:1 without rotation, so pick the paper whose first
    number is the width: "ANSI full bleed B (17.00 x 11.00 Inches)" is a landscape 17 x 11
    sheet. One undo step.

    Args:
        layout: the sheet's layout name (see list_layouts).
        paper: the paper size as AutoCAD's Page Setup lists it for the device, in full or a
            part that fits only one, e.g. "ANSI full bleed B (17.00 x 11.00 Inches)". If
            several fit, the error lists them.
        plot_style: a plot style table, e.g. "monochrome.ctb" for black lines ("" keeps the
            sheet's current one).
        device: older name for plot_device. Some MCP hosts do not pass on an argument called
            "device", so use plot_device.
        name: which open drawing (default: active).
        plot_device: the plot device, e.g. "AutoCAD PDF (High Quality Print).pc3". Default: the
            best PDF driver this AutoCAD has, which is that one (2400 dpi vectors), else
            "DWG To PDF.pc3" (600 dpi). plot_pdf plots with the sheet's PDF driver.
    """
    doc = session.document(name)
    sheet = find_layout(doc, layout)
    if bool(sheet.ModelType):
        raise AcadError("Pick a paper layout (a sheet), not Model.")
    kept = ("ConfigName", "CanonicalMediaName", "StyleSheet", "PlotType", "PlotRotation", "UseStandardScale",
            "StandardScale")
    with session.edit(doc) as change:
        old = [(prop, getattr(sheet, prop)) for prop in kept]

        def restore() -> None:
            for prop, value in old:
                # A layout never set up has no paper name, and AutoCAD refuses "" (verified 2026-11-11);
                # it then keeps the default paper of the device that was put back.
                if prop != "CanonicalMediaName" or value:
                    setattr(sheet, prop, value)
        change.on_rollback(restore)
        sheet.RefreshPlotDeviceInfo()
        devices = _strings(sheet.GetPlotDeviceNames())
        wanted = plot_device or device
        sheet.ConfigName = match_one(wanted, devices, "plot device") if wanted else best_pdf_device(devices)
        sheet.RefreshPlotDeviceInfo()  # the paper sizes are the new device's
        canonical = _strings(sheet.GetCanonicalMediaNames())
        shown = {str(sheet.GetLocaleMediaName(c)): c for c in canonical}
        exact = next((c for c in canonical if c.lower() == paper.strip().lower()), None)
        sheet.CanonicalMediaName = exact or shown[match_one(paper, list(shown), "paper size")]
        if plot_style:
            sheet.StyleSheet = match_one(plot_style, _strings(sheet.GetPlotStyleTableNames()), "plot style table")
        sheet.PlotType = enums.acLayout
        sheet.PlotRotation = enums.ac0degrees
        sheet.UseStandardScale = True
        sheet.StandardScale = enums.ac1_1
        doc.Regen(1)  # acAllViewports: the sheet shows its new paper
        return describe_page_setup(sheet)
