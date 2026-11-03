# Working rules for Claude in this repository

Read this first, then `knowledge/Projects/AutoCAD-MCP/index.md` before larger changes.

## Who you work for
- The project is maintained by [ajaquin8](https://github.com/ajaquin8); contributors work in their own forks (see `CONTRIBUTING.md`). "The user" below is whoever you are working with right now.
- Assume the user is a CAD professional who may have little coding experience and may be drafting in AutoCAD while you work.
- Explain in plain language what changed, how it was checked, and what is not done.
- Ask before decisions that are the user's: licences, anything that leaves this repository (pushes, pull requests, publishing), and changes to the user's AutoCAD, Obsidian or Claude settings.

## Hard rules
1. **Live AutoCAD is the user's workplace.** Never call AutoCAD from a test, a script or `send_command` without first describing the batch and waiting for the user to save open work and say go. While the user says they are drafting, do not contact AutoCAD at all. (In inventor-mcp a test once crashed Inventor and lost unsaved work.) See `knowledge/Decisions/Live test protocol.md`.
2. **Edit guard stays on.** Only drawings the server created are editable. Call `allow_edit_document` only when the user has asked for that specific drawing to be changed. Never weaken the guard, the busy check or the rollback to make something pass.
3. **No CAD, company or customer files in git, issues or pull requests:** no `.dwg/.dwt/.dxf/.pdf`, nothing from network drives or company project and template folders, no client names or file paths. Live-test output goes to `scratch/` (ignored).
4. **Every COM call runs on the STA worker** (`autocad_mcp/com.py`). Tool bodies are registered with `@acad_tool`, which handles this. Objects stay late-bound (`session._late_bound`); never use `gencache.EnsureDispatch`.
5. **Points and units:** tools take `[x, y]` or `[x, y, z]` in drawing units (WCS) and angles in degrees. Convert with `point()`, `doubles()` and `rad()`; AutoCAD wants VARIANT arrays of doubles and radians.
6. **Edits go through `session.edit(doc)`**: record new objects with `change.add(...)` and changes to existing ones with `change.on_rollback(...)`, so a failure leaves nothing half-done.
7. **Licences:** runtime dependencies must be MIT, BSD, Apache-2.0, PSF, HPND or similar permissive licences. Name new ones in `THIRD_PARTY_NOTICES.md`.

## Layout
- `autocad_mcp/`: the server. `app.py` (MCP object + `@acad_tool`), `com.py` (STA worker, points, errors, enums), `session.py` (connection, edit/busy guard, undo grouping and rollback), `tools/*.py` (one module per area; `tools/entities.py` holds shared helpers, no tools).
- `tests/test_offline.py`: no AutoCAD needed (fakes in `conftest.py`). `tests/live/`: scripts that run against a live AutoCAD, **only with the user's go**.
- `scripts/`: `check.ps1`, `gen_tool_docs.py`, `check_links.py`, `stdio_smoke.py`, `build_mcpb.py` (Claude desktop bundle).
- `knowledge/`: the Obsidian vault (master notes for this project).

## Build, check, done
- Setup: `python -m venv .venv` then `.venv\Scripts\python -m pip install -e .[dev]`.
- Check: `scripts\check.ps1` (ruff, pytest, tool reference up to date, vault links, stdio handshake).
- **Done means:** all checks green; a new tool has a docstring (it becomes the tool description), an offline test where the logic allows one, and a regenerated `Tool reference.md`; anything not live-verified is said so plainly.
- Check unfamiliar AutoCAD ActiveX members in the AutoCAD 2027 ActiveX reference (help.autodesk.com, "ActiveX Reference Guide") before calling them.
- One task per branch and per PR; small commits with plain-language messages.

## Knowledge vault (`knowledge/`)
- Master Obsidian vault for AutoCAD-MCP. Follow `knowledge/wiki-protocol.md`: evidence labels (verified, user-reported, inferred, unresolved), dated sections instead of rewriting history, append `knowledge/Change log.md`, run `scripts/check_links.py`.
- Record each live test batch as a dated report in `knowledge/Sources/` (Report-ID `AMCP-LIVE-YYYYMMDD-NN`), and API lessons in `knowledge/Research/AutoCAD API gotchas.md`.
- Notes about a particular employer's or client's environment do not belong in this vault.
