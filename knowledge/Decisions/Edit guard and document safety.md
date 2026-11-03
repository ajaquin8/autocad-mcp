# Edit guard and document safety

Date: 2026-10-29
Status: **adopted** (Claude design carried over from inventor-mcp, implemented in `autocad_mcp/session.py`)
Owner: Alex

## Decision
- **Edit guard:** a drawing can only be changed if this server created it in the current session (`new_drawing`), or if it was unlocked with `allow_edit_document`. Claude may only unlock a drawing when Alex has asked for that specific drawing to be changed. Read-only tools work on everything. A drawing is identified by its full path, or by its name while it has never been saved; `save_document` carries the permission over to the new path.
- **Busy guard:** edits, new/open/save/close, zoom and plotting are refused while `CMDACTIVE` is not 0 (a command, script or dialog is active) or `GetAcadState().IsQuiescent` is false.
- **One undo step per tool:** every edit runs between `StartUndoMark` and `EndUndoMark`. On any exception the objects the tool created are deleted and recorded property changes are restored in reverse order.
- **No silent data loss:** `save_document` and `plot_pdf` refuse to replace existing files unless `overwrite=True`. `close_document` only closes drawings the server created, and refuses unsaved changes unless `discard_changes=True`.
- **No raw commands by default:** `send_command`, which bypasses the guard and rollback, is only registered when `AUTOCAD_MCP_ENABLE_COMMANDS=1`.
- **Override for a trusted scratch session only:** `AUTOCAD_MCP_ALLOW_ALL_EDITS=1`.

## Evidence and citations
- **verified 2026-10-29 (offline):** `tests/test_offline.py` covers locked drawings, read-only drawings, re-keying after Save As, busy refusal (CMDACTIVE and not quiescent), the undo grouping, rollback of created objects and restore order, and an unknown layer rolling back a new line.
- **unresolved:** whether `StartUndoMark`/`EndUndoMark` from COM really make one Ctrl+Z step in AutoCAD 2027.
- **unresolved:** what `CMDACTIVE` reads while Alex is mid-command, and whether the read itself is rejected (`RPC_E_CALL_REJECTED`) while a modal dialog is open.

## Known gaps
- `delete_entities` cannot be rolled back by the server if it fails halfway (Ctrl+Z can).
- `insert_block` from a `.dwg` file leaves the new block definition in the drawing if the insert is rolled back.
- The edit guard resets when the server restarts, which is intentional.

## Supersedes / superseded by
None.
