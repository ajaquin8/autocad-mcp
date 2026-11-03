# 2026-10-29 Kitchen plan

Report-IDs: AMCP-LIVE-20261029-02 (the plan), AMCP-LIVE-20261029-03 (dimension and screenshot fixes)
Writer: Claude Code. Go given by Alex for each batch ("Saved, go", then "Go") after it was described.
Question: can the server draw a usable architectural plan, and are its dimensions readable?

## Setup
- AutoCAD 2027. Open drawings: Drawing1 (blank, left from the first run) and `AMCP-LIVE-20261029-01.dwg`; both reported locked and unchanged at the end.
- Scripts `tests/live/kitchen_plan.py` and `tests/live/kitchen_dims_fix.py`, with the shared `tests/live/harness.py`. Output in `scratch/` (ignored by git).
- New tool for this run: `set_drawing_variables` (and `get_drawing_variables`).

## -02: the plan, 55 of 55 steps
- **verified:** an inches drawing at 1/2"=1'-0" (LUNITS 4, DIMLUNIT 4, DIMSCALE 24, LTSCALE 12), eight AIA-style layers, a 14'-0" × 15'-0" room with 4½" walls broken at a 2'-8" door (with swing) and a 3'-0" window, an L of 24" base cabinets, dashed 12" uppers clear of the window, a double-bowl sink, DW and REF labels, a 30" range with four burners, a refrigerator, a 60" × 36" island with 42" aisles, a room name, a title, and six dimensions measuring 168, 180, 60, 36, 42 and 42.
- **verified:** saved as `AMCP-LIVE-20261029-02.dwg` and plotted (7,354-byte PDF).
- **failed:** the dimensions showed no text or arrows: their pictures were built with text 0.18" high, as if DIMSCALE were 1.
- **failed:** the screenshot taken straight after `zoom_extents` was blank apart from one line; a second capture a moment later was complete.

## Diagnosis
- **verified:** after setting DIMSCALE through `SetVariable`, a dimension made with `AddDimRotated` reported `ScaleFactor` 24 only once the style had been updated with `ActiveDimStyle.CopyFrom(doc)`, and its picture (bounding box) still had 0.18" text. `REGEN` did not change it. `dim.Update()` rebuilt it: the bounding box grew to 4.32" text (0.18 × 24).
- **inferred:** dimensions made through COM take their settings from the dimension style, not from the drawing's DIM* overrides, and keep their built picture until each one is updated.

## -03: fixes, 5 of 5 steps
- **fix:** `set_drawing_variables` now copies DIM* values into the active dimension style and calls `Update()` on every model space dimension of that style (it rebuilt 6). Offline tests updated.
- **fix:** `capture_view` now waits up to 3 s for AutoCAD to be quiescent, calls `Application.Update()`, then pauses 0.4 s before capturing.
- **verified:** the room depth dimension grew (bounding box width 26.03 → 29.82) and the screenshot shows all six dimensions readable: 14', 15', 5', 3', 3'-6" and 3'-6".
- **verified:** the screenshot was complete. It was taken without a zoom, so the wait after a zoom is **not yet** proven.

## Observations
- Architectural dimensions read 14' rather than 14'-0" (AutoCAD's default zero suppression, DIMZIN). Not changed.
- The island leaves a 3'-6" aisle on each working side; the door swing stays clear of it.

## Not tested
- Dimensions in paper space layouts (the rebuild only walks model space).
- `capture_view` straight after `zoom_extents` with the new wait.
