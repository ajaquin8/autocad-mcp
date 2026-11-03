# Distribution and install for AutoCAD users

Date: 2026-11-03
Status: **adopted** (Alex chose licence, visibility and PyPI on 2026-11-03; public since 2026-11-03, see the dated section)
Owner: Alex

## Decision
- **Licence: MIT** (user-reported 2026-11-03, Alex chose "MIT" when asked). `LICENSE` added; `pyproject.toml` declares `license = "MIT"`.
- **Repository: to be made public** on GitHub (Alex chose "Make GitHub repo public"). Not done yet: Alex first reviews the list of personal and work references in tracked files, and then changes the visibility on GitHub or gives Claude an explicit go.
- **PyPI: not now** (Alex chose "Not now"). The package builds as a normal wheel, so `uvx autocad-mcp` can follow later.
- **Install routes**, both needing only [uv](https://docs.astral.sh/uv/) on the user's PC (no git, no Python, no venv):
  - Claude desktop app: a one-click **MCPB bundle** (`.mcpb`, manifest 0.4, server type `uv`), built by `scripts/build_mcpb.py` and meant for GitHub Releases.
  - Claude Code (or the desktop app's config file): `uvx --from https://github.com/ajaquin8/autocad-mcp/archive/refs/heads/main.zip autocad-mcp`.
- **Project `.mcp.json`** (for people who clone the repository) uses `${CLAUDE_PROJECT_DIR:-.}/.venv/Scripts/python.exe` instead of a per-PC absolute path.
- The friend-facing guide is `INSTALL.md` in the repository root.

## Evidence and citations
- **verified 2026-11-03, this PC (Windows 11, uv 0.13.7 in a scratch venv, sandboxed uv cache, `UV_PYTHON_PREFERENCE=only-managed` so uv downloaded its own CPython 3.15.2):**
  - `uvx --from git+file:///…@feat/friend-install autocad-mcp`: initialize + tools/list answered, 32 tools; 20 s on first run, 6 s cached (`scripts/stdio_smoke.py -- <command>`).
  - `uvx --from file:///…/main.zip autocad-mcp` (a GitHub-style archive with an `autocad-mcp-main/` prefix) **with git removed from PATH**: handshake passed, 32 tools.
  - `uvx --from git+https://… ` with git removed from PATH fails ("Git operation failed"), so the git form is not suitable for non-coders.
  - In the uv environment `pythoncom`, `pywintypes`, `win32com.client` and `win32gui` import and `CoInitialize` works (pywin32 wheel; no post-install step needed).
  - The built `.mcpb` (32 KB, 23 files), extracted to a folder named like a Claude extension folder, started with its own `mcp_config` (`uv run --directory <dir> autocad-mcp`): handshake passed, 32 tools.
  - The manifest validates against the official `mcpb-manifest-v0.4.schema.json` with 0 errors (jsonschema). It fails `mcpb-manifest-latest.schema.json`, which is still 0.3 and does not know the `uv` type.
  - Claude Code 2.1.309 headless (`--mcp-config .mcp.json --strict-mcp-config`, started in the worktree) reported the `autocad` server **connected** with the new portable command. No tools were called.
- **Source:** MCPB manifest spec and the `hello-world-uv` example, https://github.com/modelcontextprotocol/mcpb (MANIFEST.md, examples/hello-world-uv, schemas/), accessed 2026-11-03. Claude Code MCP docs on `${VAR:-default}` and `CLAUDE_PROJECT_DIR`, https://code.claude.com/docs/en/mcp, accessed 2026-11-03.
- **unresolved:** whether the Claude desktop app supplies `uv` itself for `uv` bundles or needs it on PATH (the spec says the host manages it; the example's `mcp_config` calls `uv`). INSTALL.md therefore asks users to install uv first. **Installing the `.mcpb` in the Claude desktop app has not been tried** (it would change Alex's Claude settings; needs Alex's go).
- **verified (other sessions, 2026-11-03):** the server attaches to and draws in AutoCAD 2026 ([[Sources/2026-11-03 AutoCAD 2026 connection]], [[Sources/2026-11-03 AutoCAD 2026 drawing]]), so INSTALL.md lists 2026 and 2027 as tested.
- **inferred:** first start of either route downloads about 60 MB (CPython plus wheels); on a slow line it may exceed a client's start-up timeout once, so INSTALL.md says to restart Claude if the first start fails.

## Alternatives and rationale
- `uvx --from git+https://…`: needs git installed; rejected for friends (verified above).
- MCPB `python` server type with bundled dependencies: pywin32 and pydantic-core are compiled, so the bundle would be large and tied to one Python build; the `uv` type avoids that.
- PyPI (`uvx autocad-mcp`): shortest command, but publishing is public and permanent; Alex chose not now.
- Inviting friends to the private repository: each friend would need a GitHub account and git credentials; rejected by Alex.

## Consequences and follow-up
- Updates: `uvx` reuses its cache; INSTALL.md tells users to run `uv cache clean autocad-mcp`. Bundle users install a newer `.mcpb`.
- Windows path length: a uv cache under a very deep folder failed to build the package (WinError 206 inside setuptools' `bdist_wheel`). The default cache (`%LOCALAPPDATA%\uv\cache`) and a Claude extension folder are short enough (verified with an equivalent-length folder).
- uv picks the newest CPython that satisfies `requires-python >=3.12` (3.15.2 today). The server's handshake works on it; live AutoCAD use on 3.15 is not tested.
- Before going public: Alex reviews the personal/work reference list (2026-11-03 hand-over), then the repository is made public and a GitHub Release with the `.mcpb` is created, each only on Alex's go.

## 2026-11-03: public
- **verified 2026-11-03:** on Alex's go ("Fresh public repo", then "Merged, go"), the private repository with the full history was renamed to `ajaquin8/autocad-mcp-dev` (still private), and a new **public** `ajaquin8/autocad-mcp` was created with one commit (`1d08497`, author and committer `ajaquin8` with the GitHub noreply address). Its content is identical to the archive's `main` after PRs #5 and #6 (same tree hash). A fresh repository was chosen because older commits and two commit authors held company details, and GitHub keeps old commits reachable through closed pull requests.
- **verified:** installing from the public `main.zip` exactly as INSTALL.md says (uv with its own CPython 3.15.2, fresh cache, git not on PATH) passed the MCP handshake with 32 tools. CI passed on the first push. GitHub recognises the MIT licence, CONTRIBUTING.md, the PR template and the install-help link; the issue-form file views show no template errors.
- **unresolved:** the New issue page was not viewed signed in. No GitHub Release (and so no `.mcpb` download) yet; INSTALL.md's Releases link is empty until there is one.

## 2026-11-03: bundle installed in the Claude desktop app
- **verified 2026-11-03 (Alex's PC, Claude desktop app 4.4212, Windows 11):** Alex installed `autocad-mcp-0.1.0.mcpb` from the v0.1.0 Release by double-click. It appeared under Settings → Extensions, enabled. **The app brought its own uv** (`%APPDATA%\Claude\uv-runtime\uv-0.9.7-win32-x64\uv.exe`) and ran `uv run --directory <extension folder> autocad-mcp`, although uv was not installed on the PC; the extension's `.venv` used the installed CPython 3.12.10. This **supersedes** the earlier **unresolved** point above: bundle users don't need to install uv.
- **user-reported 2026-11-03:** `acad_status` worked from a Chat conversation and from a Cowork task (Alex: "Both worked"). The open drawings were reported locked, as designed.
- **verified (from the reply Alex pasted):** Claude read `"autocad": "25.1s …"` as "AutoCAD 2025"; 25.1 is AutoCAD 2026. `acad_status` should state the product year itself (follow-up fix).
- **inferred:** on a PC without Python, the app's uv downloads a managed CPython (uv's default); not tested.
- INSTALL.md now leads with the bundle for the desktop app (Chat and Cowork, no uv) and keeps uv for Claude Code and the config-file fallback.

## 2026-11-03: v0.1.1 checked live in the desktop app
- **verified 2026-11-03 (live, reply Alex pasted from a Chat):** after installing `autocad-mcp-0.1.1.mcpb` from the v0.1.1 Release over 0.1.0, `acad_status` was answered as **"AutoCAD 2026 is running"**, with the open drawing reported locked (edit guard on). This closes the year mix-up found in the 0.1.0 test. Updating by installing the new bundle over the old one worked.

## 2026-11-03: repository settings for contributors
- **verified 2026-11-03 (GitHub API, on Alex's go "Lets do 1 next"):** label `compatibility` created (used by the "Works on my AutoCAD" form). `main` is protected: changes only through pull requests (0 approvals required, so Alex merges his own), the `check` CI job must pass, no force-pushes, no deletion; `enforce_admins` is off, so Alex can override in an emergency. "Branch must be up to date" is off on purpose, because PRs often touch the change log at the same place.
- **user-reported 2026-11-03:** Alex turned on GitHub email privacy himself.

## Supersedes / superseded by
- Supersedes the per-PC `.mcp.json` path noted in [[Change log]] (2026-11-03, work PC setup).
