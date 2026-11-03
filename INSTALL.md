# Install autocad-mcp (for AutoCAD users)

autocad-mcp lets Claude work in the AutoCAD that is already open on your PC: it can draw lines,
polylines, arcs, circles, text, dimensions and blocks, make layers, look up what is in a drawing,
take a picture of the view and plot to PDF. You don't need to know any programming. You do
two things: install a small helper called **uv**, and tell Claude about the server.

## Will it work on my PC?

| You have | Works? |
|---|---|
| Windows 10 or 11 with **full AutoCAD** | Yes |
| An AutoCAD vertical (Architecture, Mechanical, Electrical, MEP, Map 3D, Plant 3D, Civil 3D) | Yes; it uses the AutoCAD underneath |
| **AutoCAD LT** | **No.** LT has no automation interface (ActiveX/COM) |
| AutoCAD for **Mac**, or AutoCAD Web/mobile | **No.** The server needs Windows COM |
| DWG TrueView only | No. It is a viewer and can't draw; the server ignores it |

**Tested live:** AutoCAD 2027 (2026-10-29) and AutoCAD 2026 (2026-11-03), both on Windows 11.
The server finds whichever AutoCAD release is installed, so older releases (2025, 2024 ...) should
work too but have not been tried. If you try another version, please report it with the "Works on my AutoCAD" issue form.

You also need Claude: the **Claude desktop app** or **Claude Code**.

## Step 1: install uv (once)

uv downloads the right Python and the server's parts for you, so you don't need to install Python.
Open **PowerShell** (Start menu, type `PowerShell`) and paste:

```powershell
winget install --id=astral-sh.uv -e
```

If `winget` is not found, use uv's own installer instead:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then **close PowerShell and quit Claude completely** (also from the system tray), so both pick up the
new `uv` command.

## Step 2: add the server to Claude

### Claude desktop app: one-click bundle

1. Download `autocad-mcp-<version>.mcpb` from the
   [Releases page](https://github.com/ajaquin8/autocad-mcp/releases).
2. Double-click it (or drag it onto Claude's **Settings → Extensions** page) and choose **Install**.
   Claude warns that the extension is not signed by a known publisher; that is expected for a
   hobby project.
3. The first start downloads Python and the server's parts (about 60 MB) and can take a minute.

This needs a recent Claude desktop app: the bundle uses the newer "uv" bundle format.

If the bundle won't install, use the manual way: in Claude go to **Settings → Developer → Edit
Config**, and put this in `claude_desktop_config.json` (merge it with anything already there), then
restart Claude:

```json
{
  "mcpServers": {
    "autocad": {
      "command": "uvx",
      "args": ["--from", "https://github.com/ajaquin8/autocad-mcp/archive/refs/heads/main.zip", "autocad-mcp"]
    }
  }
}
```

### Claude Code

Run this once in PowerShell. It adds the server for all your projects:

```powershell
claude mcp add autocad --scope user -- uvx --from https://github.com/ajaquin8/autocad-mcp/archive/refs/heads/main.zip autocad-mcp
```

The first start downloads Python and the server's parts and can take a minute. If Claude reports
that `autocad` failed to start, wait a moment and restart Claude.

## Step 3: try it

1. Start AutoCAD and open a drawing (or leave the blank start drawing).
2. In Claude, ask: **"Call acad_status and tell me what you see."**

Claude should report your AutoCAD version, the open drawings (all shown as locked) and the drawing
units. Then try something small: *"Make a new drawing and draw a 1000 x 600 rectangle with a
circle in the middle, then show me a screenshot."*

## What keeps your drawings safe

- **Your drawings are locked.** Claude can only change drawings it created itself in this session
  (with `new_drawing`). It can read any open drawing, but to change one of yours you must ask for
  that specific drawing, and Claude unlocks only that one.
- **It waits for you.** If you are in the middle of a command, a prompt or a dialog box, Claude's
  edits are refused until you are done, so it never types into your command.
- **One undo per action.** Each thing Claude does is one step you can undo with Ctrl+Z. If an
  action fails halfway, whatever it had drawn is removed again and anything it changed is put back.
- **No surprise overwrites or closes.** Saving or plotting refuses to replace an existing file
  unless you agreed, and Claude only closes drawings it created.
- **No raw commands.** Typing arbitrary commands into AutoCAD's command line is switched off.
- Good habit anyway: save your own work before you let Claude loose in AutoCAD.

## Updating

The server is downloaded once and then reused. To get the newest version, quit Claude, run

```powershell
uv cache clean autocad-mcp
```

and start Claude again (desktop bundle users: install the new `.mcpb` from the Releases page instead).

## Removing it

- Claude desktop app: **Settings → Extensions**, remove *AutoCAD* (or delete the `autocad` entry from
  the config file).
- Claude Code: `claude mcp remove autocad --scope user`.
- Optional: `uv cache clean` frees the downloaded parts, and `winget uninstall astral-sh.uv` removes uv.

## Problems?

- **"AutoCAD is not running"**: start AutoCAD first. The server attaches to the AutoCAD that is open.
- **It finds DWG TrueView instead of AutoCAD**: start full AutoCAD; TrueView can't be drawn in.
- **`uvx` or `uv` is not recognized**: quit and restart Claude (and PowerShell) after installing uv.
- **Edits are refused as "busy"**: press Esc in AutoCAD to leave the current command, close any
  dialog box, then ask again.
- Anything else: open an issue on [GitHub](https://github.com/ajaquin8/autocad-mcp/issues) with what you
  asked and what Claude answered.
