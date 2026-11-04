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

## 2026-11-04: retried calls and cancel_command
Status: **built; verified live 2026-11-04** ([[Sources/2026-11-04 Busy handling]]) (Claude, on Alex's request "start on item 1 the busy handling"; see [[Projects/AutoCAD-MCP/Roadmap]]).
- **Retried calls:** the COM worker installs a message filter. A call AutoCAD rejects with "retry later" is retried every 250 ms for up to 8 s (`AUTOCAD_MCP_BUSY_RETRY_SECONDS`; 0 switches it off).
  - A rejected call never ran, so a retry cannot repeat work.
  - A call refused outright, or still rejected after the limit, fails as before.
  - The busy guard is unchanged: `CMDACTIVE` and `IsQuiescent` still refuse edits while the user is busy. It may just take up to 8 s to say so.
- **`new_drawing`** waits until the new drawing answers three calls in a row, 0.5 s apart (up to 45 s), before marking it as server-created.
- **`cancel_command`** hands AutoCAD two Ctrl+C (`^C^C`) as command-line input through a WM_COPYDATA window message, not COM, because COM is rejected while a prompt is open. It does not run on the COM worker. It refuses unless AutoCAD's window title shows a server-created drawing as the active one, so it cannot cancel the user's own command in their drawings. It is not for use while the user is working in a server-created drawing.
- **verified 2026-11-04 (offline):** the filter's retry decisions; the filter registers as a COM object on an STA thread; the worker installs it (or not, with 0); `new_drawing` restarts its count after a rejection; `cancel_command` refuses user drawings and longer look-alike names, and sends the cancel for a server drawing.
- **verified 2026-11-04 (live, AMCP-LIVE-20261104-04):**
  - AutoCAD answers "retry later" while a command waits at a prompt (63 times in one run), and the filter retried them.
  - `new_drawing` settled a new drawing.
  - `cancel_command` refused while the user's drawing was active, and cleared LINE waiting at its first prompt in a server drawing.
  - WM_CHAR or WM_KEYDOWN Esc posted to AutoCAD's main window did **not** clear the prompt; the WM_COPYDATA `^C^C` did.

## Supersedes / superseded by
None.
