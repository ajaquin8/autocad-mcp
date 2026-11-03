# 2026-11-03 Sheet tools

Report-ID: AMCP-LIVE-20261103-04
Writer: Claude Code. Go given by Alex ("Saved, go") after the batch was described.
Question: do the new sheet tools (viewport, layouts, leader, centre mark, current styles) produce a complete, plotted part sketch on a real title-block sheet?

## Setup
- AutoCAD 2026 ("25.1s"). Branch `feat/sheet-tools` (commits `4be74fa`, then `set_current_styles`), calling the tool functions directly (no MCP client).
- The sheet: the user's private sketch-sheet template (ANSI B 17 × 11 layout with a title block of 22 attributes), saved once from the user's DXF to a private `.dwt` outside this repository. The DXF was opened read-only and not changed. Neither file is in git.
- The part: a small bent angle (1/4" plate, 3 × 2 × 3, four 1/4" holes), recreated from the user's existing PDF drawing of it, in three views.
- Output in `scratch/` (ignored by git): DWG, PDF (238,486 bytes), PNG.

## Results: 39 of 39 passed
- **verified:** `new_drawing(template=…dwt)` gave an inches drawing with the template's layout, layers and styles; it was created by the server, so editable.
- **verified:** `set_current_styles` made the template's dimension, multileader and text styles current. That was needed: the template's current dimension style named a style that was not in the file, and its default multileader style was metric-sized.
- **verified:** `set_drawing_variables` DIMLUNIT 2 / DIMDEC 2 gave decimal dimensions; the six dimensions measured 1.00, 1.25, 1.29, 3.00, 2.00, 3.00.
  - **Correction (2026-11-03, later the same day, [[Sources/2026-11-03 Plot style re-plot]]):** those are the measured values. The printed text read `1,00` etc., because the template's dimension style has a comma as decimal separator (DIMDSEP). This was missed when the screenshot was looked at.
- **verified:** `draw_circle` + `draw_center_mark` (two lines each, on the centre layer), hidden edges on the hidden layer, the bent profile as one closed polyline with quarter-circle bulges.
- **verified:** `add_leader` created an `AcDbMLeader` with the callout text on the leader layer.
- **verified:** `add_viewport` created a viewport on the sheet layout at the requested paper rectangle, scale read back as 1.0 (1:1), locked, framing the views as intended (screenshot looked at).
- **verified:** `list_layouts` reported the sheet's two viewports and the title block's handle; `set_block_attributes` filled seven title-block attributes on that paper-space block by handle.
- **verified:** `save_document` and `plot_pdf` of the sheet layout. AutoCAD reported "errors and warnings" for the plot job: the layout's plot style table is not installed on this PC, so the PDF uses layer colours. Not a tool problem.
- **observed:** a non-plotting guide text at the template's model origin showed through the viewport; the user's private playbook deletes it after creating a drawing.

## Not covered
- `add_radial_dimension` (written and tested offline, not used in this part), viewports at scales other than 1:1, `add_viewport` on a drawing that is not the active one, and leader/dimension sizes at other scales (the multileader style is sized for 1:1).
