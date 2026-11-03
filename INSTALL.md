# Install autocad-mcp (for AutoCAD users)

autocad-mcp lets Claude work in the AutoCAD that is already open on your PC: it can draw lines,
polylines, arcs, circles, text, dimensions and blocks, make layers, look up what is in a drawing,
take a picture of the view and plot to PDF. You don't need to know any programming. In the Claude desktop app it is
one click; Claude Code needs one extra helper (uv).

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

You also need Claude on that PC: the **Claude desktop app** (Chat or Cowork) or **Claude Code**.

## Step 1: add the server to Claude

### Claude desktop app (Chat and Cowork): one-click bundle

Nothing else to install: the Claude desktop app sets up Python and the server's parts by itself.

1. Download `autocad-mcp-<version>.mcpb` from the
   [Releases page](https://github.com/ajaquin8/autocad-mcp/releases) (it is under **Assets**, below
   the release notes).
2. Double-click it (or drag it onto Claude's **Settings → Extensions** page) and choose **Install**.
   Claude warns that the extension is not signed by a known publisher; that is expected for a
   hobby project.
3. *AutoCAD* now shows on the Extensions page. The first start can take a minute while it
   downloads the server's parts.

One install covers both Chat and Cowork. This needs a recent Claude desktop app (the bundle uses
the newer "uv" bundle format). If your Claude is managed by your company, the admin may have
switched off extensions; ask them, or use Claude Code.

### Claude Code

Claude Code needs a small helper called **uv**, which downloads the right Python and the server's
parts, so you don't need to install Python. Open **PowerShell** (Start menu, type `PowerShell`)
and paste:

```powershell
winget install --id=astral-sh.uv -e
```

If `winget` is not found, use uv's own installer instead:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close PowerShell, open a new one, and add the server for all your projects:

```powershell
claude mcp add autocad --scope user -- uvx --from https://github.com/ajaquin8/autocad-mcp/archive/refs/heads/main.zip autocad-mcp
```

The first start downloads Python and the server's parts and can take a minute. If Claude reports
that `autocad` failed to start, wait a moment and restart Claude.

### If the bundle won't install

Install uv as in the Claude Code part above, then in the Claude desktop app go to **Settings →
Developer → Edit Config** and put this in `claude_desktop_config.json` (merge it with anything
already there), then quit Claude completely (also from the system tray) and start it again:

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

## Step 2: try it

1. Start AutoCAD and open a drawing (or leave the blank start drawing).
2. In Claude (a Chat, a Cowork task or Claude Code), ask: **"Call acad_status and tell me what you see."**

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

- Claude desktop app: download the newest `.mcpb` from the Releases page and install it the same way.
- Claude Code: the server is downloaded once and then reused. To get the newest version, quit
  Claude, run `uv cache clean autocad-mcp` in PowerShell, and start Claude again.

## Removing it

- Claude desktop app: **Settings → Extensions**, remove *AutoCAD* (or delete the `autocad` entry from
  the config file).
- Claude Code: `claude mcp remove autocad --scope user`.
- Claude Code users, optional: `uv cache clean` frees the downloaded parts, and `winget uninstall astral-sh.uv` removes uv.

## Problems?

- **"AutoCAD is not running"**: start AutoCAD first. The server attaches to the AutoCAD that is open.
- **It finds DWG TrueView instead of AutoCAD**: start full AutoCAD; TrueView can't be drawn in.
- **`uvx` or `uv` is not recognized** (Claude Code or the config file): quit and restart Claude (and PowerShell) after installing uv.
- **Edits are refused as "busy"**: press Esc in AutoCAD to leave the current command, close any
  dialog box, then ask again.
- Anything else: open an issue on [GitHub](https://github.com/ajaquin8/autocad-mcp/issues) with what you
  asked and what Claude answered.
