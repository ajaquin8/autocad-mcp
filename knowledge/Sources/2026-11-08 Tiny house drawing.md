# 2026-11-08 Tiny house drawing

Report-ID: AMCP-LIVE-20261108-01
Writer: Claude Code. The batch was described first (read-only check, new drawing, layers, plans, elevations, save to `scratch/`) and run after Alex's go ("lets do it", then "Restarted, go" after the first attempt failed). No user action was needed during the run, apart from closing one empty drawing and restarting Claude.
Question: can the released 0.1.3 server (42 tools) draw a small, complete architectural sheet through Claude's own MCP connection: two plans and two elevations with dimensions and labels?

## Setup
- AutoCAD 2027 on Alex's PC. One user drawing (Drawing1, unsaved, no changes) was open and locked (`editable: false`); it was only listed.
- Server: this folder at `main` 66137ba (v0.1.3), started fresh by a Claude restart.
- Every step was a single MCP tool call from Claude Code (about 150 calls). No scripts.

## First attempt: old server after a code switch (failed, nothing drawn)
- **verified:** the folder had been switched from the old private history to the public `main` while Claude was running, so the MCP server process was still the old code. Its `new_drawing` made the drawing (Drawing2) and then failed with `AttributeError: <unknown>.Count` while reading `Documents.Count`. The drawing was left open and **not owned** by the server, so it stayed locked (as the edit guard should).
- **verified:** the traceback showed a line of the *new* `session.py`, because Python reads source lines from disk when it prints a traceback; the code that ran was the old line 137 (`docs.Count`). A mismatched traceback line is a sign the server is older than the files.
- **inferred:** the old `new_drawing` had no settle wait; 0.1.3 waits for a new drawing to settle ([[Sources/2026-11-04 Busy handling]]).
- Alex closed Drawing2 unsaved and restarted Claude. Lesson: after switching branches or pulling server code, restart Claude before any live call.

## Results (second attempt, 0.1.3)
1. **`acad_status`, `list_documents`:** AutoCAD 2027, inches, one locked user drawing.
2. **`new_drawing`:** Drawing3, `created_by_mcp: true`, editable. No error.
3. **`set_drawing_variables`:** LUNITS 4, LUPREC 4, DIMLUNIT 4, DIMSCALE 24, DIMZIN 3, LTSCALE 12, INSUNITS 1, in one call; Standard dimension style updated.
4. **`add_layer` ×9:** walls, glazing, doors, furniture, hidden (HIDDEN linetype loaded), elevation, ground, dimensions, text.
5. **Main floor plan:** 24'-0" × 8'-6" with 4" walls broken at three windows and a 36" glass door (closed polylines per wall piece), bath partition with a pocket door, shower, toilet (polyline with a bulge), vanity, kitchen counter with sink and 2-burner cooktop, closet, W/D, storage stair with arrow, sofa, fold-down table, out-swinging door onto a deck, trailer tongue dashed.
6. **Loft plan:** walls, four clerestory windows and a transom, guard rail, queen mattress, open-to-below cross.
7. **South (long side) and east (end) elevations:** wall, fascia, belt band, clerestory strip, table window, trailer frame, tongue, jack, tandem wheels, deck with railing; shed roof sloping 24" over 8'-6", glass door, transom, tires.
8. **Dimensions:** 5'-8", 7'-0", 11'-4", 24'-0", 8'-6" (twice), `13'-6" MAX` and `LOFT 6'-6" A.F.F.` (text overrides with `<>`) all read correctly at DIMSCALE 24.
9. **Text:** room labels, titles, scales, a title line and an MTEXT notes block.
10. **`capture_view`** after `zoom_extents`, three times: the sheet looked as intended. One overlap (the loft dimension text on the elevation wall) was fixed by deleting and redrawing the dimension.
11. **`save_document`** to `scratch/AMCP-LIVE-20261108-01 tiny house.dwg` (ignored by git).
- **Result: all steps as expected on 0.1.3**, with the two findings below.

## Findings
- **verified (caller error, not a server bug):** a dimension `text_override` must be sent as plain `<>`. Sent HTML-escaped (`&lt;&gt;`), AutoCAD showed it literally. Two dimensions were deleted and redrawn.
- **inferred (from the bounding box, not seen on screen):** `add_leader` in a drawing from the default template used the Standard multileader style at its own text height, far too small at 1/2" = 1'-0" (the box was about 4" wide for 18 characters). DIMSCALE does not scale multileaders. The leader was replaced by a polyline and TEXT. Recorded in [[Research/AutoCAD API gotchas]]. A scaled multileader style (or a scale option in `add_leader`) would fix this; not done.

## Not covered
- `run_command` and the Block Editor tools: not on `main` during this run; merged afterwards in [PR #19](https://github.com/ajaquin8/autocad-mcp/pull/19), still not live-tested.
- Sheet layouts, viewports and plotting of this drawing.
