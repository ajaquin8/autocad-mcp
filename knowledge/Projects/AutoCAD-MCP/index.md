# AutoCAD-MCP

An MCP server that lets Claude drive the AutoCAD 2027 session already running on Alex's PC: it creates drawings, layers, geometry, text, dimensions and blocks, queries entities, and takes screenshots to check its own work. Code: `autocad_mcp/` in this repository. Tool list: [[Projects/AutoCAD-MCP/Tool reference]].

## Status, 2026-10-29
- **Architecture** (verified 2026-10-29, from the code): a Python process using `pywin32` attaches to the running `AutoCAD.Application.26` over COM. Nothing is installed into AutoCAD. Every COM call runs on one STA thread, and objects are late-bound. MCP over stdio uses the official `mcp` SDK 2.3. See [[Decisions/Python COM server foundation]].
- **30 tools**, all **unresolved** live: written and offline-checked, never run against AutoCAD. **superseded** the same day by the first live run below.
- **Safety** (verified by the offline tests, 2026-10-29): edit guard, busy guard, one undo group per tool with rollback of created objects and recorded changes, no silent overwrites. See [[Decisions/Edit guard and document safety]].
- **Live testing** will follow [[Decisions/Live test protocol]].
- **Registered:** `.mcp.json` in the repository root registers the server as `autocad` for Claude Code. Not yet approved or started in a session.
- **Offline checks** (verified 2026-10-29): run them with `scripts/check.ps1`.

## 2026-10-29: first live run
- **verified** ([[Sources/2026-10-29 First drawing]]): status, new/save drawings, layers, all draw tools, dimensions, rollback, zoom, view capture, queries and PDF plotting work against AutoCAD 2027. One fix was needed (re-fetch a new drawing by name).
- Still **unresolved** live: blocks/attributes, move/change/delete, open/close, the busy guard during a user command, undo grouping, and the MCP stdio path.

## 2026-10-29: kitchen plan
- **verified** ([[Sources/2026-10-29 Kitchen plan]]): a full kitchen plan with readable 1/2"=1'-0" architectural dimensions, after two fixes (dimension style update and rebuild, screenshot wait). 32 tools; `set_drawing_variables` and `get_drawing_variables` are new.

## 2026-10-29: kitchen elevations
- **verified** ([[Sources/2026-10-29 Kitchen elevations]]): two cabinet elevations matching the plan, and the plan edited by handle (query → delete → redraw). The screenshot wait works after a zoom. DIMZIN still needs 3 for 14'-0". **superseded:** set and verified in the addendum the same day.

## 2026-11-03: on GitHub
- **verified 2026-11-03:** pushed to the private repository https://github.com/ajaquin8/autocad-mcp; GitHub's `main` matched the local `HEAD` (`b0894cf`) after the push. The CI workflow (offline checks on a Windows runner) started on that push.

## 2026-11-03: installable for AutoCAD users
- **verified 2026-11-03** (this PC, sandboxed uv): installs without git, Python or a venv, via `uvx` from the GitHub ZIP or the `.mcpb` bundle; both answered the MCP handshake with 32 tools. Not yet installed in the Claude desktop app, and the repository is still private. See [[Decisions/Distribution and install]]; the user guide is `INSTALL.md`. Licence: MIT.

## 2026-11-03: public
- **verified 2026-11-03:** public at https://github.com/ajaquin8/autocad-mcp (fresh one-commit history). The full development history stays in the private `ajaquin8/autocad-mcp-dev`. See [[Decisions/Distribution and install]].

## 2026-11-03: safety check
- **verified** ([[Sources/2026-11-03 Safety check]]): on AutoCAD 2026, user drawings stay locked (draw and close refused), each tool is one Ctrl+Z, nothing is drawn while the user is inside a command or a modal dialog, and blocks/attributes, move/change/delete by handle and save/close/open work. The busy refusal showed a confusing `AttributeError: <unknown>.Count`; now reported as "busy, press Esc" (0.1.2). This answers the first two open questions below (**superseded**).

## History
- 2026-10-29: Alex compared the existing AutoCAD MCP servers ([[Research/AutoCAD MCP landscape]]) and chose to build one in the style of inventor-mcp.

## Open questions
- Do undo marks over COM give one Ctrl+Z step? (first live batch)
- How does the busy guard behave mid-command and with a modal dialog open? (first live batch, with Alex)
- Use Autodesk's built-in MCP server alongside this one for queries? See [[Projects/AutoCAD-MCP/Roadmap]].
