"""Plotting a layout to PDF."""

from __future__ import annotations

import os

import pywintypes

from ..app import acad_tool
from ..com import AcadError
from ..session import session

PDF_DEVICE = "DWG To PDF.pc3"


@acad_tool(read_only=True, timeout=600.0)
def plot_pdf(path: str, layout: str = "", overwrite: bool = False, name: str = "") -> dict:
    """Plot one layout to a PDF with its own page setup, using the DWG To PDF device.
    No geometry is changed and the layout tab the user had open is restored, but AutoCAD
    marks the drawing as having unsaved changes after a plot (verified 2026-10-29).

    Args:
        path: full path of the PDF to write.
        layout: layout name, e.g. "Model" or "A-101" (default: the current layout).
        overwrite: allow replacing an existing file.
        name: which open drawing (default: active); it is made active while plotting.
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
        ok = bool(doc.Plot.PlotToFile(path, PDF_DEVICE))
    finally:
        doc.SetVariable("BACKGROUNDPLOT", background)
        if str(doc.ActiveLayout.Name) != str(previous.Name):
            doc.ActiveLayout = previous
    if not ok or not os.path.exists(path):
        raise AcadError(f"AutoCAD did not write {path} (PlotToFile returned {ok}).")
    return {"pdf": path, "layout": layout or str(previous.Name), "bytes": os.path.getsize(path)}
