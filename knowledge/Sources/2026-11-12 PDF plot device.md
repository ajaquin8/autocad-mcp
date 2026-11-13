# 2026-11-12 PDF plot device: resolution, and why solid fills look rough on screen

Report-ID: AMCP-LIVE-20261112-01
Writer: Claude, in a Claude desktop session building title block templates. Alex asked why a hatched logo "doesn't look crisp from afar" in the plotted PDF, then gave the go ("Lets do it") for a server change and a live plot.
Question: which PDF driver should a sheet use, does the server honour it, and what makes a solid fill look rough in a PDF viewer?

## Setup
- AutoCAD 2027 (26.0s) on the home PC. Scripts under `scratch/` (`diag_pdf_device*.py`, `live_plot_device.py`) run with the repo's `.venv` on branch `feat/plot-device`. Scratch drawings started from a three-sheet template, closed after use. The plotted PDFs were read as text (content streams decompressed) and rendered with poppler 24.02.

## Results: diagnosis
- **verified:** the vector grid of the PDF depends on the driver. `DWG To PDF.pc3` wrote 600 units per inch, `AutoCAD PDF (General Documentation).pc3` 1200, `AutoCAD PDF (High Quality Print).pc3` 2400 (read from the page's `cm` matrix). `PlotToFile(path)` with no device uses the layout's own driver and gave the same files as naming it.
- **verified:** a layout keeps a new `ConfigName` whether or not it is the current layout, and the paper list (112 names) is the same for the three drivers.
- **verified:** `plot_pdf` in 0.1.7 always plotted with `DWG To PDF.pc3`, whatever the sheet's page setup said (`PlotToFile(path, PDF_DEVICE)`).
- **observed:** through the installed 0.1.7 extension, `set_page_setup(..., device="AutoCAD PDF (High Quality Print).pc3")` returned and left "DWG To PDF.pc3", twice. The same function called from a script with the same arguments set the driver. **inferred:** the MCP host does not pass on an argument called `device`. **unresolved:** not confirmed by looking at what the server received.
- **verified:** AutoCAD writes a solid hatch into the PDF as pairs of triangles, each closed, filled and stroked with a zero-width line (operator `b` after `0 w`): about 600 such pairs for a small logo. A zero-width line is one device pixel wide at any zoom and is not anti-aliased, so on screen the fill's edge is a hard stair-step, and the shape looks a little heavier, at every driver resolution.
- **verified:** with only those strokes taken out of the PDF (`b` changed to `f`), the edges are anti-aliased but pale seams show between the triangles. So the strokes are there to hide the seams.
- **observed:** 600 against 2400 dpi made no visible difference to the logo at screen zoom (rendered at 110 and 220 dpi). The finer grid matters on paper and at high zoom.

## Results: the change (28 of 28 checks, repo code)
- `set_page_setup` with no device named put `AutoCAD PDF (High Quality Print).pc3` on all three sheets; the template saved and reopened with it.
- `plot_pdf` plotted each sheet with the sheet's driver: 2400 dpi in all three PDFs.
- `plot_pdf(..., plot_device="DWG To PDF.pc3")` plotted at 600 dpi and left the page setup alone.
- `plot_pdf(..., plot_device="Microsoft Print to PDF")` was refused.

## Not covered
- The change through an installed bundle, and whether `plot_device` reaches the server where `device` did not.
- Other PDF viewers (Acrobat, browsers), and a paper print.
- AutoCAD 2026 and older (no "AutoCAD PDF" drivers before 2016: the code falls back to `DWG To PDF.pc3`, offline-tested only).
