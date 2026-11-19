# 2026-11-18 Dynamic block tools live runs

Report-IDs: AMCP-LIVE-20261118-02 to AMCP-LIVE-20261118-05 (one series)
Writer: Claude Code, in the session that built the tools. Each batch was described first and run after the user's go ("Saved, go").
Question: what are AutoCAD's real prompts for value sets, visibility, flip, rotation, move, scale and angle offsets in the Block Editor, how can the Block Editor's objects be listed with usable handles, and do the tools built on that (T6 to T10) work?

## Setup
- AutoCAD 2027 on the home PC, with the user's own drawings open (not touched; the drawing active before was made active again at the end of each run).
- `tests/live/block_editor_probe.py` (discovery, -02 and -03) and `tests/live/dynamic_tools_check.py` (verification, -04 and -05), run with the repo's `.venv` on branch `feat/dynamic-block-tools`. One new scratch drawing per run, closed without saving.

## Results
- **-02 (discovery, stopped early):** **verified:** inside the Block Editor, COM's `ModelSpace` is the editor's space: it held the block's objects with new handles, its count rose by one when a LINE was drawn there, and one of those handles was found at a selection prompt. **observed:** right after a `SELECT` there ended, AutoCAD answered once and was then waiting at a prompt; every later call was refused until `cancel_command` (sent in the scratch drawing). The script crashed before putting `BACTIONBARMODE` back; it was set to 1 by hand (the value -03 then read at its start). Fixed: `run_command` now looks a second time for a prompt left open; the probe dropped `SELECT` and always restores the variable.
- **-03 (discovery, 24 of 28 probes):** the prompt orders recorded for: linear value sets (Value set before the start point; List takes one comma-separated answer, Increment asks for step, minimum and maximum); the visibility parameter (label, location, grips 0/1); `-BVSTATE` New (then Hide all/Show all/Current visibility), Set, Delete; `BVHIDE` and `BVSHOW` (selection, Enter, Current/All); move (action type, parameter point, selection, location or Multiplier/Offset); scale (action type, selection, location or Base type); angle offset (`O`, "Enter angle offset <0>"). The flip parameter's Label also asks for the unflipped and flipped values; the rotation parameter asks for label, base, radius, default angle, label location and one more answer. In editor listings, parameters, grips and actions appear as `AcDbBlock*ParameterEntity`, `*GripEntity`, `*ActionEntity`. A placed block offered Width 48/60/72 and the visibility states.
- **-04 (verification, 36 of 40):** the new tools built a dynamic block: listing, value list and increment, stretch, a half-distance move with a 90 degree offset, scale, rotation parameter and rotate action (by handle from the listing), visibility states with the circle hidden in one ("Plain" showed 2 objects, "With circle" 3), Width 72 made it 12 wider on the right. **Failed:** the flip parameter wanted one more answer after the label location; the three other failures followed from it.
- **-05 (verification, 41 of 41):** with the flip parameter answering the number of grips, the flip parameter and flip action were added and the placed block offered the flip; everything else passed again.

## Not covered
- A rotation parameter with an angle value list; an XY or polar parameter; array actions through `add_action`.
- Whether the flip and rotate actions turn the objects correctly on a placed block (only that they were added and the properties are offered); setting a flip state on a placed block is B4, not fixed here.
- Reordering visibility states or choosing the default (T11).
- The installed Claude desktop extension: everything ran with the repo code.

## Follow-up
- [[Change log]] entry of 2026-11-18 (dynamic block tools). API lessons in [[Research/AutoCAD API gotchas]].
