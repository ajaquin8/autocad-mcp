# 2026-10-29 First drawing

Report-ID: AMCP-LIVE-20261029-01
Writer: Claude Code. Go given by Alex ("Saved, go") after the batch was described.
Question: does the scaffold work against the live AutoCAD 2027, and does it leave Alex's drawings alone?

## Setup
- AutoCAD 2027 ("26.0s (LMS Tech)"), plain AutoCAD. Only the Start tab was open (no user drawings).
- Script `tests/live/first_drawing.py`, calling the tool functions directly (no MCP client), commit `a2f065e` plus the fixes below.
- Output in `scratch/` (ignored by git): `AMCP-LIVE-20261029-01.dwg`, `.png`, `.pdf`, `.json`.

## Run 1: stopped at new_drawing
- **verified:** `acad_status` with only the Start tab reported 0 open drawings, as expected.
- **verified:** `Documents.Add()` created Drawing1, but `ReadOnly` on the object it returned failed (`AttributeError: Add.ReadOnly`) while `Name`, `FullName` and `Saved` worked. The same drawing fetched with `Documents.Item(0)` or `ActiveDocument` answered `ReadOnly` normally (type info `IAcadDocument` in both cases).
- **fix:** `new_drawing` and `open_drawing` now fetch the drawing again by name from `Documents`. Offline regression test `test_new_drawing_is_fetched_again_from_the_documents_collection`.
- The blank, never-saved Drawing1 was left open.

## Run 2: 32 of 33 steps passed
- **verified:** Drawing1 (not created by this run's server) was reported locked, and still had no unsaved changes at the end.
- **verified:** `new_drawing` from the default template gave an inches drawing (INSUNITS 1). Six layers were created, including A-SWING with the HIDDEN linetype loaded from `acad.lin`.
- **verified:** rectangles, lines, an arc, a closed polyline with a bulge (semicircular sill nose), a circle, TEXT, MTEXT and horizontal/vertical dimensions (`AcDbRotatedDimension`, measurements 36 and 48) all landed at the requested coordinates, read back with `GetBoundingBox` through dynamic dispatch.
- **verified:** rollback: `draw_line` on a missing layer was refused and the model space count stayed 15 → 15.
- **verified:** `zoom_extents`, `capture_view` (PrintWindow screenshot, see the PNG), `drawing_info`, `query_entities` (3 muntins on A-MUNTIN) and `save_document` (Save As renamed the drawing to `AMCP-LIVE-20261029-01.dwg` and kept edit permission).
- **failed (script bug):** `plot_pdf` was called with the old name "Drawing2.dwg" after Save As. Fixed in the script.
- **verified (separate call, same batch):** `plot_pdf` on the saved drawing wrote a 6,648-byte PDF of the Model layout and restored `BACKGROUNDPLOT` to 2. The PDF's content was not looked at (no PDF renderer here).
- **verified:** after the plot, AutoCAD reported the drawing as having unsaved changes. `plot_pdf`'s description now says so.

## Observations from the screenshot
- Dimension text and arrows are too small to read: the default Standard style has DIMTXT 0.18 and DIMSCALE 1. A dimension scale or a proper dimension style is needed (roadmap).
- The test drawing itself has a drafting error: the swing lines meet at the handle side. In elevations they meet at the hinge side. That is the script's geometry, not a tool problem.

## Not tested
- Whether one Ctrl+Z removes exactly one tool's work (left for Alex to try in the open drawing).
- The busy guard during a real user command or with a dialog open.
- Blocks and attributes, `move_entities`, `change_properties`, `delete_entities`, `close_document`, `open_drawing`, and the MCP stdio path against live AutoCAD.
