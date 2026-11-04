# autocad-mcp

An MCP server that lets Claude drive the AutoCAD session already running on your PC (tested on 2026 and 2027).
It attaches over COM (`GetActiveObject` on the newest `AutoCAD.Application.<release>` that is running), so there is no add-in to
install and no AutoCAD restart. It follows the design of
inventor-mcp (the author's Autodesk Inventor server, not public yet): one COM thread, an edit guard, a busy
guard and one undo step per tool.

Notes, decisions and test reports live in the Obsidian vault [`knowledge/`](knowledge/README.md).
Working rules for Claude are in [CLAUDE.md](CLAUDE.md).

## Install (AutoCAD users)

Windows with full AutoCAD or a vertical (not AutoCAD LT, not Mac). No git, Python or venv needed.
In the Claude desktop app (Chat and Cowork), install the `.mcpb` bundle from the
[Releases page](https://github.com/ajaquin8/autocad-mcp/releases). For Claude Code, install
[uv](https://docs.astral.sh/uv/) and run

```powershell
claude mcp add autocad --scope user -- uvx --from https://github.com/ajaquin8/autocad-mcp/archive/refs/heads/main.zip autocad-mcp
```

Step by step, with the safety summary: **[INSTALL.md](INSTALL.md)**.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

Claude Code picks up `.mcp.json` (server name `autocad`) when it is started from this folder; it
runs `.venv\Scripts\python.exe -m autocad_mcp` relative to the project, so it works wherever the
repository is cloned. Start AutoCAD first, then ask Claude to call `acad_status`.

Build the Claude desktop bundle with `python scripts/build_mcpb.py` (writes `dist/autocad-mcp-<version>.mcpb`).

## Safety

- **Edit guard:** only drawings created through the server (`new_drawing`) are editable. An
  existing drawing must be unlocked with `allow_edit_document`, which happens only when you ask.
  If the server restarts, it takes back the drawings it created that are still open in the same
  AutoCAD; a drawing closed and opened again, or anything after AutoCAD restarts, stays locked.
- **Busy guard:** edits are refused while you are in a command, prompt or dialog (`CMDACTIVE`).
  When AutoCAD asks to be called again later (opening a drawing, loading an add-in), the server
  retries for up to 8 seconds (`AUTOCAD_MCP_BUSY_RETRY_SECONDS`, 0 switches it off).
- **`cancel_command`** cancels (two Ctrl+C) a prompt the server left open, and refuses unless the
  active drawing is one the server created.
- **One undo step per tool** (UNDO Begin/End marks). If a tool fails, what it created is deleted
  and what it changed is put back.
- **No silent overwrites or discarded changes.** `close_document` only closes the server's own drawings.
- **`send_command`** (raw command line, which bypasses the guard) is registered only with
  `AUTOCAD_MCP_ENABLE_COMMANDS=1`.

Details: [knowledge/Decisions/Edit guard and document safety.md](knowledge/Decisions/Edit%20guard%20and%20document%20safety.md).

## Tools

39 tools: drawings, layers, lines/polylines/arcs/circles/text, centre marks, linear and radial
dimensions, leaders, blocks and attributes, moving/re-layering/deleting by handle, sheets (layouts,
viewports at an exact scale, title blocks), queries, view capture, PDF plotting and clearing a stuck prompt. The full list is
generated from the code into
[knowledge/Projects/AutoCAD-MCP/Tool reference.md](knowledge/Projects/AutoCAD-MCP/Tool%20reference.md).
Coordinates are drawing units in WCS; angles are degrees.

## Checks

```powershell
.\scripts\check.ps1
```

This runs ruff, the offline pytest suite (no AutoCAD needed), the tool-reference freshness check,
the vault link check and a stdio handshake. Live tests go in `tests/live/` and run only by hand,
after you agree (see
[knowledge/Decisions/Live test protocol.md](knowledge/Decisions/Live%20test%20protocol.md)).

## Status

See [knowledge/Projects/AutoCAD-MCP/index.md](knowledge/Projects/AutoCAD-MCP/index.md).
In short (2026-11-03): drawing, layers, dimensions, view capture and PDF plotting are verified
against live AutoCAD 2027 and 2026; on 2026 also blocks and attributes, edits by handle, open/close,
one Ctrl+Z per tool, and edits being refused while you are in a command or dialog.

## Contributing

Bug reports, "works on my AutoCAD" reports and pull requests are welcome; see
[CONTRIBUTING.md](CONTRIBUTING.md). Please never attach drawings or company files.

## Credits

The design follows inventor-mcp. AutoCAD COM patterns (late-bound dispatch, VARIANT points,
PrintWindow capture, foreground PDF plotting) were learned from
[U-C4N/Autocad-MCP](https://github.com/U-C4N/Autocad-MCP) (MIT). See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Licence: [MIT](LICENSE).
