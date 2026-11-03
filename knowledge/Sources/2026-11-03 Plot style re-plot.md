# 2026-11-03 Plot style re-plot

Report-ID: AMCP-LIVE-20261103-05
Writer: Claude Code. Go given by Alex ("Saved, go") after the batch was described.
Question: after the user installed the sheet's missing plot style table (a `.ctb` copied into AutoCAD 2026's Plot Styles folder), does the part sketch from [[Sources/2026-11-03 Sheet tools]] plot without warnings?

## Setup
- AutoCAD 2026 ("25.1s"), branch `feat/sheet-tools`, tool functions called directly (no MCP client).
- The part-sketch drawing from AMCP-LIVE-20261103-04 in `scratch/` (ignored by git): closed without saving (only the plot had marked it modified), reopened, plotted again.

## Results: 8 of 8 passed
- **verified:** after reopening, the sheet layout's `StyleSheet` read back as the installed `.ctb`.
- **verified:** `plot_pdf` wrote the PDF, and AutoCAD's `PlotandPublishLog.CSV` (in `%LOCALAPPDATA%\Autodesk\AutoCAD 2026\R25.1\enu\`) recorded "Plotted" for the sheet. The earlier plot had "WARNING: Incompatible or missing plot style" and "Plotted with Warning(s)". The PDF is now black with the table's lineweights (looked at).
- **observed (new):** the decimal dimensions printed `1,00`, `1,25`, ... with a comma. The template's dimension style has DIMDSEP `,`. `set_drawing_variables` could not change DIMDSEP; it can now (offline-tested only, not live-verified).
- **observed (new):** hidden lines 1/4" long printed solid at 1:1: the hidden linetype's dash is longer than the line. Not solved.
- **process:** the first run closed the drawing, then failed to reopen it with "interface marshalled for a different thread": the script had connected on the STA worker and then called a tool function on the main thread. Calling everything from one thread (as the other live scripts do) fixed it. Nothing else was touched.

## Not covered
- `set_drawing_variables({"DIMDSEP": "."})` against a live drawing.
