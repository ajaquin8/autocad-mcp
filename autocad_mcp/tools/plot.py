"""Plotting a layout to PDF."""

from __future__ import annotations

import os

import pywintypes

from ..app import acad_tool
from ..com import AcadError
from ..session import session

# The legacy driver: in every AutoCAD, but it writes vectors on a 600 dpi grid, which shows as rough
# edges on small solid fills such as a logo (measured 2026-11-12: 600, against 1200 for General
# Documentation and 2400 for High Quality Print).
PDF_DEVICE = "DWG To PDF.pc3"
PDF_DEVICES = ("AutoCAD PDF (High Quality Print).pc3", PDF_DEVICE)  # best first


def is_pdf_device(device: str) -> bool:
    """True for AutoCAD's own PDF drivers ("DWG To PDF.pc3", "AutoCAD PDF (...).pc3"). Windows'
    "Microsoft Print to PDF" is a system printer that asks for a file name itself: not one of them."""
    text = device.strip().lower()
    return text.endswith(".pc3") and "pdf" in text


def best_pdf_device(names: list[str]) -> str:
    """The best PDF driver among the devices AutoCAD lists (the legacy one if nothing better)."""
    have = {n.lower(): n for n in names}
    return next((have[d.lower()] for d in PDF_DEVICES if d.lower() in have), PDF_DEVICE)


@acad_tool(read_only=True, timeout=600.0)
def plot_pdf(path: str, layout: str = "", overwrite: bool = False, name: str = "",
             plot_device: str = "") -> dict:
    """Plot one layout to a PDF with its own page setup. The PDF driver is the one in the
    sheet's page setup if that is a PDF driver (see set_page_setup), else "DWG To PDF.pc3".
    No geometry is changed and the layout tab the user had open is restored, but AutoCAD
    marks the drawing as having unsaved changes after a plot (verified 2026-10-29).

    Args:
        path: full path of the PDF to write.
        layout: layout name, e.g. "Model" or "A-101" (default: the current layout).
        overwrite: allow replacing an existing file.
        name: which open drawing (default: active); it is made active while plotting.
        plot_device: a PDF driver to use for this plot only, e.g. "AutoCAD PDF (High Quality
            Print).pc3" (2400 dpi vectors) or "DWG To PDF.pc3" (600 dpi). The page setup is
            not changed.
    """
    if not path.lower().endswith(".pdf"):
        raise AcadError("path must end in .pdf")
    if os.path.exists(path) and not overwrite:
        raise AcadError(f"{path} already exists. Pass overwrite=True only if the user agreed to replace it.")
    doc = session.document(name)
    session.require_idle(doc)
    if str(doc.Name) != str(session.app.ActiveDocument.Name):
        doc.Activate()
    previous = doc.ActiveLayout
    background = int(doc.GetVariable("BACKGROUNDPLOT"))
    try:
        if layout:
            try:
                doc.ActiveLayout = doc.Layouts.Item(layout)
            except pywintypes.com_error:
                raise AcadError(f"No layout named '{layout}'.") from None
        # Background plotting returns before the file exists; plot in the foreground.
        doc.SetVariable("BACKGROUNDPLOT", 0)
        sheet = doc.ActiveLayout
        if plot_device:
            from .sheets import _strings, match_one  # sheets imports this module
            sheet.RefreshPlotDeviceInfo()
            device = match_one(plot_device, _strings(sheet.GetPlotDeviceNames()), "plot device")
            if not is_pdf_device(device):
                raise AcadError(f"'{device}' is not one of AutoCAD's PDF drivers; plot_pdf only writes PDFs.")
        else:
            current = str(sheet.ConfigName)
            device = current if is_pdf_device(current) else PDF_DEVICE
        ok = bool(doc.Plot.PlotToFile(path, device))
    finally:
        doc.SetVariable("BACKGROUNDPLOT", background)
        if str(doc.ActiveLayout.Name) != str(previous.Name):
            doc.ActiveLayout = previous
    if not ok or not os.path.exists(path):
        raise AcadError(f"AutoCAD did not write {path} (PlotToFile returned {ok}).")
    return {"pdf": path, "layout": layout or str(previous.Name), "device": device, "bytes": os.path.getsize(path)}
