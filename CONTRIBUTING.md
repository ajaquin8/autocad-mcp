# Contributing to autocad-mcp

Thanks for helping. autocad-mcp is a personal project by [ajaquin8](https://github.com/ajaquin8),
shared with other AutoCAD users. You don't have to write code to help.

## Never share drawings or company files

This comes before everything else. Do **not** attach drawings (`.dwg`, `.dxf`, `.dwt`), PDFs,
screenshots of client work, file paths or names from your company's projects, or any customer
information to an issue, a pull request or a commit. Describe the problem with a small drawing you
made yourself (a few lines and a dimension are usually enough), or just in words. The repository's
`.gitignore` blocks CAD files and PDFs, but it can't stop an attachment in an issue.

## Help without writing code

Open an [issue](https://github.com/ajaquin8/autocad-mcp/issues/new/choose) and pick a form:

- **Bug report:** what you asked Claude, what happened, and what you expected.
- **Works on my AutoCAD:** tell us which AutoCAD version or vertical you tried (Civil 3D 2025,
  Architecture 2024 ...) and whether `acad_status` and a simple drawing worked. So far it has only
  been tested on AutoCAD 2026 and 2027, so these reports are very useful.
- **Idea:** a tool or behaviour you'd like, and the drafting task it would help with.

## Change the code

You don't need write access. The usual GitHub flow:

1. **Fork** the repository (button at the top right on GitHub), then clone your fork.
2. Set up and check (Windows, Python 3.12 or newer):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e .[dev]
   .\scripts\check.ps1
   ```
3. Make your change on a branch: one topic per branch, small commits with plain-language messages.
4. Run `.\scripts\check.ps1` again (lint, offline tests, tool reference, vault links, MCP handshake).
   If you added or changed a tool, run `python scripts\gen_tool_docs.py` to regenerate the tool
   reference.
5. Push to your fork and open a **pull request** against `main`. GitHub runs the same checks.
   The maintainer reviews it and merges it; nothing reaches `main` without that.

If you work with Claude Code, it reads [CLAUDE.md](CLAUDE.md), which holds the same rules.

### Rules the code must keep

- **Safety stays on.** Only drawings the server created are editable; the busy check and the
  rollback stay. Pull requests that weaken them to make something work are not merged.
- Every AutoCAD call runs on the single COM worker thread (register tools with `@acad_tool`).
- Tools take points as `[x, y]` or `[x, y, z]` in drawing units and angles in degrees.
- New tools need a docstring (it becomes the description Claude sees) and an offline test where
  the logic allows one (`tests/test_offline.py`, using the fakes in `tests/conftest.py`).
- New runtime dependencies must have a permissive licence (MIT, BSD, Apache-2.0, PSF ...) and be
  listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Testing against a live AutoCAD

The scripts in `tests/live/` drive a real AutoCAD. Only run them on your own PC, **after saving and
closing your own work**, and never with client drawings open. They work in new scratch drawings and
write output to `scratch/`, which git ignores. Say in your pull request what you tested live and on
which AutoCAD version, and what you only tested offline.

## Your name in the history

Your commits show the name and email set in your git config. To keep your email private, use the
address GitHub gives you under **Settings → Emails** ("Keep my email addresses private"):

```powershell
git config user.name "your-github-name"
git config user.email "12345678+your-github-name@users.noreply.github.com"
```

## Licence of contributions

The project is [MIT-licensed](LICENSE). By opening a pull request you agree that your contribution is
licensed under the same MIT licence, as GitHub's terms of service describe for public repositories.
Only contribute code you wrote yourself or that is under a compatible licence (say where it came from).
