# Roadmap

Status: **proposed** (Claude, 2026-10-29). Alex sets the priorities.

## Now: first live verification
**2026-10-29:** steps 1, 2, 4 and 7 (except `close_document`) passed, see [[Sources/2026-10-29 First drawing]]. Still to do: 3 (Ctrl+Z), 5 (busy guard with Alex), 6 (blocks, move, change, delete). New item: dimensions need a dimension scale or style to be readable. **Done 2026-10-29** with `set_drawing_variables`, see [[Sources/2026-10-29 Kitchen plan]].

Run under [[Decisions/Live test protocol]], in a scratch drawing created by the server:
1. `acad_status` (read-only) with Alex's drawings open: are they all reported locked?
2. `new_drawing`, `add_layer`, one of each `draw_*`, `add_text`, `add_mtext`, `add_dimension`, `capture_view`.
3. Undo check: does one Ctrl+Z remove exactly one tool's work?
4. Rollback check: a tool that fails halfway (unknown layer) leaves nothing behind.
5. Busy guard with Alex: refusal mid-command and with a dialog open.
6. `insert_block` with attributes, `set_block_attributes`, `move_entities`, `change_properties`, `delete_entities`.
7. `save_document` to `scratch/`, `plot_pdf`, `close_document`.

Record the run in [[Sources/index]] and the lessons in [[Research/AutoCAD API gotchas]].

## Next: make it fit Alex's work
- Paper space: layouts, viewports, title block attributes.
- Hatches, leaders/multileaders, dimension styles and text styles.
- A modelling workflow skill or MCP prompt, as planned for inventor-mcp.
- Optionally pair with Autodesk's built-in server for queries (it needs workarounds to reach Claude Code; see [[Research/AutoCAD MCP landscape]]).

## Later
- Office drawing workflows: elevations and details from window/door data, sheet sets, standard blocks from a company library (read-only, never committed).
- Selection-set filters for fast queries on big drawings (the current query reads model space one entity at a time).
- An in-process .NET helper only if COM speed or rollback limits become a real problem.
