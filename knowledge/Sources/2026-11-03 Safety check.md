# 2026-11-03 Safety check

Report-ID: AMCP-LIVE-20261103-03
Writer: Claude Code. Go given by Alex ("Saved, go") after the batch was described; Alex did the AutoCAD steps between phases (Ctrl+Z twice, LINE twice, OPTIONS, Esc and Cancel).
Question: do the safety promises in INSTALL.md hold on a live AutoCAD (edit guard, one Ctrl+Z per tool, edits refused while the user is in a command or dialog), and do blocks, edits by handle and open/close work?

## Setup
- AutoCAD 2026 ("25.1s"), the PC used for the 2026 runs. Open before the run: Alex's blank `Drawing1` (saved state recorded; no client drawings open).
- Script `tests/live/safety_check.py`, one process per phase, calling the tool functions directly (no MCP client); later phases re-mark the scratch drawing they created as the server's own (recorded in `scratch/`). Phases: `tools`, `undo-prepare`, `undo-check`, `undo-check2`, `busy` (inside LINE), `busy-armed` (warm session, inside LINE), `busy` (OPTIONS dialog open), `idle`, `cleanup`.
- Output in `scratch/` (ignored by git): one JSON per phase, `AMCP-LIVE-20261103-03-a.dwg`, the state file.

## Results
- **verified, tools phase 35/35:**
  - Edit guard: `Drawing1` was reported locked; `draw_line` on it was refused ("is locked"), `close_document` on it was refused ("was not created by this server"); its unsaved-changes state was unchanged at the end.
  - Blocks: a test block `AMCP-TAG` (circle, attributes MARK and SIZE) defined by direct COM as setup; `list_blocks` showed it with its tags; `insert_block` with `{"MARK": "W101", "SIZE": "36x48"}` read back exactly; `set_block_attributes` MARK=W102 read back; an insert with an unknown tag was refused with "Nothing was inserted" and the entity count was unchanged.
  - Edits by handle: `move_entities` moved a line by (5, 1) exactly; `change_properties` put a circle on a new layer A-TEST in red; a change of both entities to a missing layer was refused and left both as they were; `delete_entities` removed the circle.
  - Documents: `save_document` to `scratch/`, `close_document` on the saved drawing, `open_drawing` of that file: it came back **locked**, and drawing on it was refused. A new drawing with an unsaved line refused to close without `discard_changes`, and closed with it.
- **verified, one Ctrl+Z per tool (2/2):** three tool calls (line; circle; both made red in one `change_properties`). Alex's first Ctrl+Z turned **both** back to ByLayer and kept both; the second removed only the circle.
- **verified, nothing drawn while busy:** inside LINE (fresh process, then a warmed-up process like the real server) and with the OPTIONS dialog open, every call was rejected at once (about 1 s, no hang). The entity count was 1 before and 1 after; after Esc / Cancel the same draw worked (`idle` 2/2).
- **verified, wrong message while busy (3 steps failed on wording):** the server never reached its own `CMDACTIVE` check. Its first COM access, `Documents.Count`, was rejected, and pywin32's late binding reported that as `AttributeError: <unknown>.Count`, which is what Claude would have shown. Fixed in the same change: `describe_attribute_error` turns `<unknown>.` lookups into the busy message ("press Esc, then retry"); offline test added. The fix itself was not rerun live.
- `cleanup` closed the scratch drawing; the reopened scratch file was left for Alex to close (it is locked to the server by design).

## Conclusion
- **verified:** INSTALL.md's safety promises hold on AutoCAD 2026: user drawings are locked, each action is one Ctrl+Z, and nothing is drawn while the user is in a command or a modal dialog. The refusal while busy comes from AutoCAD rejecting COM calls, before the server's own check.
- **unresolved:** whether AutoCAD accepts COM calls in states the server's `CMDACTIVE` check would then catch (for example a transparent command or a modeless palette); `plot_pdf` and `capture_view` while busy; the new busy message seen live through an MCP client.
