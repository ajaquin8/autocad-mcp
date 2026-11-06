# Roadmap

Status: **proposed** (Claude, 2026-10-29). Alex sets the priorities.

## Now: first live verification
**2026-10-29:** steps 1, 2, 4 and 7 (except `close_document`) passed, see [[Sources/2026-10-29 First drawing]]. Still to do: 3 (Ctrl+Z), 5 (busy guard with Alex), 6 (blocks, move, change, delete). New item: dimensions need a dimension scale or style to be readable. **Done 2026-10-29** with `set_drawing_variables`, see [[Sources/2026-10-29 Kitchen plan]].

**2026-11-03:** steps 3, 5 and 6, plus `close_document`, passed on AutoCAD 2026, see [[Sources/2026-11-03 Safety check]]. The busy guard holds because AutoCAD rejects COM calls during a command or dialog; the message for that case was fixed. All seven steps are now done.

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
- Paper space: layouts, viewports, title block attributes. **Done 2026-11-03** (viewports, layouts, title blocks by handle), see [[Sources/2026-11-03 Sheet tools]]. Still open: creating layouts, scales other than 1:1 for leaders.
- Hatches, leaders/multileaders, dimension styles and text styles. **Leaders and making existing styles current done 2026-11-03**; hatches and creating styles still open.
- A modelling workflow skill or MCP prompt, as planned for inventor-mcp.
- Optionally pair with Autodesk's built-in server for queries (it needs workarounds to reach Claude Code; see [[Research/AutoCAD MCP landscape]]).

## Later
- Office drawing workflows: elevations and details from window/door data, sheet sets, standard blocks from a company library (read-only, never committed).
- Selection-set filters for fast queries on big drawings (the current query reads model space one entity at a time).
- An in-process .NET helper only if COM speed or rollback limits become a real problem.

## 2026-11-03: from the dynamic block series
Status: **proposed** (Claude). See [[Sources/2026-11-03 Dynamic block authoring]].
- Fix: `new_drawing` should wait for AutoCAD to finish initialising the new drawing before looking it up (it can fail with `<unknown>.Count` while the drawing is still opening).
  - 2026-11-04: the same wait is needed after the lookup succeeds. An add-in loading into each new drawing rejected the next calls for several seconds ([[Sources/2026-11-04 Dynamic block shared array]]).
- New tool: set a placed dynamic block's properties (visibility state, distances) and read its attributes, so a fastener or unit block can be placed "size × length" from a description or schedule.
- Possible: a Block Editor helper for the scriptable parts (parameters, states, stretch/array actions with point picks), with the lessons above built in. Tables and fields stay manual.
- 2026-11-04: a Block Editor helper should name the parameter point (`_S`/`_T`), pick on label text within a known zoom, lock attribute positions before `BVSHOW`, and read the saved file back (DXF) to check each action's parameter point and selection. A clean run is not proof that the wiring is right.

## 2026-11-04: less desktop control, more MCP
Status: **proposed** (Claude), added on Alex's request ("Yes, add them"), in the order suggested. Alex sets the priorities.
Why: in the screw-block work ([[Sources/2026-11-03 Dynamic block authoring]], [[Sources/2026-11-04 Dynamic block shared array]]), desktop control was needed for three reasons:
- AutoCAD stuck at a prompt, or refusing calls after a dialog;
- no MCP tool for the job, so raw commands were used;
- settings that exist only in a dialog or the Properties palette.

1. **Handle a busy AutoCAD inside the server** (small). **2026-11-04: built and verified live** ([[Sources/2026-11-04 Busy handling]]) ([[Decisions/Edit guard and document safety]]; live script `tests/live/busy_check.py`).
   - **Retry rejected calls.** Register a COM message filter so that "Call was rejected by callee" is retried for a few seconds instead of failing. The busy guard is unchanged: a drawing that is in a command still refuses edits ([[Decisions/Edit guard and document safety]]).
   - **A cancel tool.** It sends Esc to AutoCAD's window (a window message, not COM) to clear a prompt the server itself left open. It must be used only while a server-created drawing is active, and never while the user's drawing is: Esc would cancel the user's own command.
   - **`new_drawing` waits until the new drawing answers** several calls in a row (add-ins load into each new drawing). This extends the 2026-11-03 fix item above.
2. **Keep ownership across a server restart** (small). **2026-11-04: built and verified live** ([[Sources/2026-11-04 Ownership across restarts]]). Tag drawings the server creates, e.g. with a drawing property, so a restarted server still treats them as its own. Today it lost them and had to fall back to raw COM to save or close. The guard stays as strict for the user's drawings ([[Decisions/Edit guard and document safety]]).
3. **Dynamic block tools** (medium). **2026-11-04: placing and testing built and verified live** (`get_block_properties`, `set_block_properties`, `insert_block(dynamic_properties=…)`, `measure_block`; [[Sources/2026-11-04 Dynamic block tools]]). The inspect read-back and the Block Editor tools are still to do. **2026-11-06: Block Editor tools built, not live-verified:** `open_block_editor`, `close_block_editor`, `add_linear_parameter`, `add_stretch_action`, `lock_attribute_positions`, `check_dynamic_block`, on top of the new `run_command` ([[Sources/2026-11-06 Stretch grips by script]]). Live script: `tests/live/command_check.py`.
   - **Placing and testing:** set a placed block's dynamic properties and read its attributes (the 2026-11-03 item above), plus a "measure what is visible" tool (explode a copy, report extents and counts).
   - **Block Editor tools:** open, close and save; add a parameter; add a stretch or array that always names its parameter point; show objects in all states; create visibility states in a given order. Guardrails built in: picks only inside a fixed zoom window, refuse off-screen picks, lock attribute positions before selections.
   - **An "inspect block" tool:** read a saved block back (DXF via the console engine on a copy, or DXFOUT) and report its parameters, which point each stretch is tied to, each action's selection, and the states. This is how the wrong-end stretches were found.
4. **Short experiments for the "dialog-only" settings,** each with Alex's go.
   - Show properties and Chain actions are stored in the drawing; try setting them with AutoLISP property functions in the Block Editor.
   - Labels: let the placing tool write the label text itself, with no field, no `####` and no regen lag. Keep the field for hand edits.
   - Lookup tables: no automation interface fills them. Try a template block whose table is copied and patched in the file, or design blocks that avoid tables.
5. **An in-process .NET helper** (bigger). Runs commands synchronously with known prompt state, cancels cleanly, and creates fields through the managed API. This brings forward the "only if needed" item under Later. How it is loaded into AutoCAD is Alex's decision (it touches his AutoCAD setup).

Likely to stay manual: filling a lookup or Block Properties Table from scratch (unless the template idea works), and judging the look of a block by eye.
