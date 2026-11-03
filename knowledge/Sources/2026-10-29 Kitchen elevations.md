# 2026-10-29 Kitchen elevations

Report-ID: AMCP-LIVE-20261029-04
Writer: Claude Code. Go given by Alex ("Saved, go") after the batch was described.
Question: can the server draw cabinet elevations matching the kitchen plan, and edit the plan by handle?

## Setup
- The kitchen scratch drawing `AMCP-LIVE-20261029-02.dwg` (see [[Sources/2026-10-29 Kitchen plan]]), unlocked with `allow_edit_document` for the run. Drawing1 and `AMCP-LIVE-20261029-01.dwg` were open and stayed unchanged.
- Script `tests/live/kitchen_elevations.py`. Output in `scratch/` (ignored by git).

## Results: 87 of 87 steps
- **verified:** `query_entities` on A-CASE-UPPR found the three plan uppers; the east run (handle 95) was picked by its bounding box and removed with `delete_entities`, then redrawn as two runs either side of the range, a dashed hood outline and an upper over the refrigerator. First live use of query → delete by handle.
- **verified:** a north elevation (sink wall) and an east elevation (range wall) beside the plan: wall outline floor to 8'-0", 4" toe kick, 36" counter, uppers 54"–96", base cabinets with doors or drawer stacks, dishwasher, window over the sink (sill 42", head 80"), range with oven door under a hood and chimney, 70" refrigerator with French doors, freezer drawer and a cabinet over it. Width and height dimensions read 14', 3'-6", 1'-6", 3', 5'-6", 2'-6", 4', 3' and 15'.
- **verified:** `capture_view` straight after `zoom_extents` was complete this time; the redraw wait added in -03 works. **superseded:** "not yet proven" in [[Sources/2026-10-29 Kitchen plan]].
- **verified:** saved in place; the PDF of the Model layout is 13,814 bytes.

## Mistake found
- **verified:** `DIMZIN 0` gave 14' and 3', not 14'-0". In architectural units 0 suppresses zero inches; 3 keeps them (14'-0") and suppresses zero feet (6"); 1 keeps both (0'-6"). The tool description was wrong and is corrected. The drawing still has DIMZIN 0.

## Observations
- The plan title's "SCALE" overlaps the UCS icon at this zoom (display only).
- The elevations are 2D line work only: no hatching, door swing marks, hardware or material notes.

## Not tested
- DIMZIN 3 on this drawing.

## Addendum -05: DIMZIN 3
Go given by Alex ("Go, then commit").
- **verified:** `set_drawing_variables({"DIMZIN": 3})` on the kitchen drawing rebuilt 18 dimensions; the screenshot shows 14'-0", 15'-0", 5'-0", 3'-0", 3'-6", 1'-6", 5'-6", 2'-6" and 4'-0". Saved in place. **superseded:** "Not tested: DIMZIN 3" above.
