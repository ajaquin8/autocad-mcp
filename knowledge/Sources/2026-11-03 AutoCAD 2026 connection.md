# 2026-11-03 AutoCAD 2026 connection

Report-ID: AMCP-LIVE-20261103-01
Writer: Claude Code. Go given by Alex ("Saved, go") after the batch was described.
Question: on Alex's work PC (AutoCAD 2026 and DWG TrueView 2027), does the server attach to AutoCAD 2026 and not to TrueView, and does the edit guard lock the drawing Alex has open?

## Setup
- AutoCAD 2026 ("25.1s (LMS Tech)"), `C:\Program Files\Autodesk\AutoCAD 2026\acad.exe`. DWG TrueView was not running. One of Alex's own drawings (a project record drawing, inches) was open and active; its name is left out of this note on purpose.
- Script `tests/live/connect_check.py`, read only, calling the tool functions directly (no MCP client), at commit `0ea1b56` (the merged version detection).
- Output: `scratch/AMCP-LIVE-20261103-01.json` (ignored by git).

## Results: 4 of 4 passed
- **verified:** the registry scan listed `AutoCAD.Application.26`, `.25.1`, `.25`, then `AutoCAD.Application`, newest first.
- **verified:** `acad_status` connected and reported version 25.1s, the active drawing, its units (inches) and one open drawing.
- **verified:** the attached application is `AutoCAD` at `...\AutoCAD 2026\acad.exe`, not TrueView.
- **verified:** Alex's open drawing was reported not editable (edit guard on). The script created, opened, changed and saved nothing.
- **not recorded:** which ProgID the running AutoCAD answered to. **inferred:** not `.26`, which on this PC is registered to TrueView, so `.25.1` or a later name in the list.

## Not covered
- TrueView running at the same time (the skip is only tested offline).
- Drawing tools on AutoCAD 2026: no scratch drawing was made. That is the next batch, to be described before it runs.
