# 2026-11-03 AutoCAD 2026 drawing

Report-ID: AMCP-LIVE-20261103-02
Writer: Claude Code. Go given by Alex ("Saved, go") after the batch was described.
Question: do the drawing tools work on AutoCAD 2026 as they did on 2027, and do they leave Alex's drawings alone?

## Setup
- Work PC, AutoCAD 2026 ("25.1s (LMS Tech)"), DWG TrueView 2027 installed but closed. Open before the run: one of Alex's project drawings (saved, no unsaved changes; name left out on purpose) and a blank `Drawing1`.
- Script `tests/live/first_drawing.py` (the window elevation from [[Sources/2026-10-29 First drawing]]), run with `AMCP_REPORT=AMCP-LIVE-20261103-02` at commit `0981153`, calling the tool functions directly (no MCP client).
- Output in `scratch/` (ignored by git): `AMCP-LIVE-20261103-02.dwg`, `.png`, `.pdf`, `.json`.

## Results: 33 of 33 passed
- **verified:** both of Alex's open drawings were reported locked, and neither had its unsaved-changes state changed by the end.
- **verified:** `new_drawing` from AutoCAD's default template gave an inches drawing (`Drawing2`). Six layers were created, including A-SWING with HIDDEN loaded.
- **verified:** rectangles, lines, the arc, the closed polyline with a bulge, the circle, TEXT, MTEXT and the horizontal/vertical dimensions (measurements 36 and 48) landed at the requested coordinates, read back with the same values as on 2027.
- **verified:** rollback: a line on a missing layer was refused and the model space count stayed 15 → 15.
- **verified:** `zoom_extents`, `capture_view` (screenshot looked at: the window elevation is drawn as intended), `drawing_info`, `query_entities` (3 muntins), `save_document` (Save As renamed the drawing) and `plot_pdf` (6,729-byte PDF of Model; its content was not looked at).
- **as on 2027, not a 2026 issue:** dimension text and arrows are too small to read, because this script uses the default Standard style (DIMSCALE 1). `set_drawing_variables` handles this, as in [[Sources/2026-10-29 Kitchen plan]].

## Conclusion
- **verified:** the 17 tools this script exercises (of 32 listed) behave the same on AutoCAD 2026 as on 2027. Not covered: blocks and attributes, edit tools (move, re-layer, delete by handle), `set_drawing_variables` and TrueView running alongside AutoCAD.
