# Change log

Newest entries at the bottom. Each entry: date, writer, what changed, and links.

## 2026-10-29: project scaffolded
Writer: Claude Code (Alex's request: "Yes, scaffold it", after reviewing AutoCAD MCP options and inventor-mcp).
- Created the `autocad-mcp` repository layout from inventor-mcp: the server package, offline tests, scripts, CI workflow and this vault ([[wiki-protocol]] and the Templates copied unchanged).
- New pages: [[Projects/AutoCAD-MCP/index]], [[Projects/AutoCAD-MCP/Roadmap]], [[Projects/AutoCAD-MCP/Tool reference]] (generated), [[Decisions/index]] with three decisions, [[Research/index]] with [[Research/AutoCAD MCP landscape]] and [[Research/AutoCAD API gotchas]], [[Sources/index]] with [[Sources/External references]].
- Sources: the cloned repositories listed in [[Sources/External references]], strings read from Autodesk's MCP DLLs, and a research subagent's web survey (labelled as such).
- Validation: ruff clean, offline pytest green, tool reference generated, vault links checked, stdio handshake passed. **Nothing has been run against a live AutoCAD.** Not committed to git yet; not on GitHub.

## 2026-10-29: first live run
Writer: Claude Code (Alex: "Saved, go").
- Ran `tests/live/first_drawing.py` (AMCP-LIVE-20261029-01). Fixed `new_drawing`/`open_drawing` to re-fetch the drawing by name, the script's post-Save-As name, and `plot_pdf`'s description.
- New: [[Sources/2026-10-29 First drawing]]. Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]], [[Projects/AutoCAD-MCP/index]], [[Projects/AutoCAD-MCP/Roadmap]].
- Validation: offline checks green (33 tests); vault links checked.

## 2026-10-29: kitchen plan and dimension fixes
Writer: Claude Code (Alex: "Want to try creating kitchen plans?", then "Saved, go" and "Go").
- Added `set_drawing_variables` / `get_drawing_variables` (tools/settings.py), the live harness and the kitchen scripts. Fixed unreadable dimensions (style copy and rebuild) and the blank screenshot after a zoom.
- New: [[Sources/2026-10-29 Kitchen plan]]. Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]], [[Projects/AutoCAD-MCP/index]], [[Projects/AutoCAD-MCP/Roadmap]], the regenerated [[Projects/AutoCAD-MCP/Tool reference]].
- Validation: offline checks green; vault links checked.

## 2026-10-29: kitchen elevations
Writer: Claude Code (Alex: "Want to try doing elevations for your kitchen design as well?", then "Saved, go").
- Added DIMZIN to `set_drawing_variables` (its description corrected after the run) and `tests/live/kitchen_elevations.py`.
- New: [[Sources/2026-10-29 Kitchen elevations]]. Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]], [[Projects/AutoCAD-MCP/index]], the regenerated [[Projects/AutoCAD-MCP/Tool reference]].
- Validation: offline checks green; vault links checked.

## 2026-10-29: DIMZIN 3 on the kitchen drawing
Writer: Claude Code (Alex: "Go, then commit").
- Set DIMZIN 3 on `AMCP-LIVE-20261029-02.dwg`; dimensions read 14'-0" etc. Updated [[Sources/2026-10-29 Kitchen elevations]] and [[Projects/AutoCAD-MCP/index]].

## 2026-11-03: repository on GitHub
Writer: Claude Code (Alex: "Can you work on getting our new AutoCAD MCP on my github?").
- Created the private repository `github.com/ajaquin8/autocad-mcp` with `gh repo create --private` and pushed `main` (4 commits, `b0894cf`). Verified: GitHub's `main` equals the local `HEAD`.
- Before pushing: no tracked drawings, PDFs or images, and no secrets found in tracked files. `.mcp.json` (with this PC's path to the Python environment) is included.
- Updated [[Projects/AutoCAD-MCP/index]]. The CI result was checked separately (see the next entry if any).

## 2026-11-03: work PC setup and AutoCAD 2026 detection
Writer: Claude Code (Alex: "help me set it up on my work computer", then "Yes, fix it").
- Cloned to the work PC, created `.venv`, pointed `.mcp.json` at it (local, uncommitted: the path differs per PC).
- `autocad_mcp/session.py`: tries every `AutoCAD.Application.<release>` ProgID in the registry (newest first, so any AutoCAD version is found), skips a running DWG TrueView, and launches only a ProgID registered to `acad.exe`. Five offline tests added.
- Updated [[Research/AutoCAD API gotchas]] and [[Decisions/Python COM server foundation]].
- Validation: offline checks green; the launch choice was checked against the work PC registry (picks `.25.1`). **Not run against a live AutoCAD 2026.**

## 2026-11-03: first live connection on the work PC
Writer: Claude Code (Alex: "Okay I have AutoCAD 2026 open", then "Saved, go").
- Added `tests/live/connect_check.py` (read only) and ran it as AMCP-LIVE-20261103-01: 4/4 passed. The server attached to AutoCAD 2026, not TrueView, and Alex's open drawing stayed locked and untouched.
- New: [[Sources/2026-11-03 AutoCAD 2026 connection]]. Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]].
- Validation: offline checks green; vault links checked. Drawing tools on 2026 not yet tried.

## 2026-11-03: drawing tools on AutoCAD 2026
Writer: Claude Code (Alex: "Okay lets do the next two things", then "Saved, go").
- `tests/live/first_drawing.py` takes its Report-ID from `AMCP_REPORT`, so the same batch can be rerun. Ran it as AMCP-LIVE-20261103-02 on AutoCAD 2026: 33/33 passed; Alex's drawings stayed locked and unchanged.
- New: [[Sources/2026-11-03 AutoCAD 2026 drawing]]. Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]].
- Validation: offline checks green; vault links checked; the screenshot was looked at. The PDF's content was not.

## 2026-11-03: installable for AutoCAD users (branch feat/friend-install)
Writer: Claude Code side session (task from the work-PC session: make autocad-mcp installable for Alex's non-coder friends; Alex chose MIT, "Make GitHub repo public" and PyPI "Not now").
- New: `LICENSE` (MIT), `INSTALL.md` (friend guide), `scripts/build_mcpb.py` (Claude desktop bundle), `tests/test_packaging.py`, [[Decisions/Distribution and install]].
- Changed: `.mcp.json` now `${CLAUDE_PROJECT_DIR:-.}/.venv/Scripts/python.exe` (no per-PC path); `scripts/stdio_smoke.py` can test any install command after `--`; `pyproject.toml` licence and URLs; README install section, licence and status; `THIRD_PARTY_NOTICES.md` (uv); `.gitignore` (`dist/`); updated [[Decisions/index]] and [[Projects/AutoCAD-MCP/index]].
- Sources: MCPB spec, schemas and `hello-world-uv` example (github.com/modelcontextprotocol/mcpb), Claude Code MCP docs, accessed 2026-11-03.
- Validation: `uvx` from a git URL and from a GitHub-style ZIP (git hidden), and the extracted `.mcpb`'s own command, all passed the stdio handshake (32 tools); manifest valid against the v0.4 schema; Claude Code headless reported the portable `.mcp.json` server connected; `scripts/check.ps1` green. **AutoCAD was not contacted. Nothing pushed or published; the repository is still private; the bundle was not installed in the Claude desktop app.**

## 2026-11-03: contributor setup (branch chore/contributor-setup)
Writer: Claude Code side session (Alex: keep the project on the personal ajaquin8 account with the noreply address, and let coworkers try it and contribute; then "Contributor setup").
- New: `CONTRIBUTING.md` (no drawings or company files anywhere, issue forms for non-coders, fork and pull request flow, rules the code keeps, live tests only on your own PC, noreply email, MIT inbound = outbound), `.github/ISSUE_TEMPLATE/` (bug report, "Works on my AutoCAD", idea, install-help link; blank issues off), `.github/pull_request_template.md`.
- Changed: `CLAUDE.md` now speaks of "the user" instead of Alex, and drops the personal profile and the company-specific folder and vault references (same protections, written for any contributor's Claude); `tests/live/README.md` likewise; README links CONTRIBUTING.
- Validation: issue forms parsed with PyYAML (unique ids, string options); `scripts/check.ps1` green. The forms have not been seen rendered on GitHub yet. The `compatibility` label does not exist in the repository yet (GitHub skips labels that don't exist).
- Not changed here: the other personal and work references in the vault, the live scripts' docstrings, and the two commits authored with the work address (the separate "clean-up for public" step).

## 2026-11-03: clean-up before going public (branch chore/public-cleanup)
Writer: Claude Code side session (Alex: "Yes, clean up", after reviewing the list of personal and work references).
- **Redaction, not a history change:** this entry and two earlier ones were edited on purpose to take out company-identifying details before the repository goes public. Replaced: the company name and its vault, the company's network drive letter, the work PC's user folder path and user name, and the speaker profile. Earlier entries keep their meaning; the replaced words are described here instead of repeated.
- Changed: [[Change log]] (2026-11-03 work PC setup and contributor setup entries), [[Research/AutoCAD API gotchas]], [[Projects/AutoCAD-MCP/Roadmap]] ("Office drawing workflows"), the vault [[README]], [[wiki-protocol]] (two template references), `.gitignore`, `THIRD_PARTY_NOTICES.md`, `autocad_mcp/tools/settings.py` (comment), `tests/live/*.py` docstrings ("the user" instead of Alex), `INSTALL.md` (version reports go to the issue form).
- Kept on purpose: attribution of Alex's go-aheads and requests in the vault (evidence labels need it), and the generic words "work PC", which already appear in commit messages and pull request texts.
- Validation: re-scan of tracked text files finds no company name, drive letter, work email, user folder or speaker profile; `scripts/check.ps1` green.
- Not changed here: git history. Older versions of files and two commit authors (`1af1c23`, `2df6359`, a work email address) still contain the old details; rewriting them needs a force-push and Alex's separate go.

## 2026-11-03: public repository
Writer: Claude Code side session (Alex: "Fresh public repo", then "Merged, go").
- GitHub: the private repository was renamed `ajaquin8/autocad-mcp-dev` (full history, PRs #1–#6, still private). A new public `ajaquin8/autocad-mcp` holds one commit with the same content (`1d08497`, noreply author). The old local clone's `origin` now points to the archive, so its history can't be pushed here by accident; new work is cloned from the public repository.
- Updated [[Decisions/Distribution and install]] and [[Projects/AutoCAD-MCP/index]].
- Validation: the INSTALL.md route from the public `main.zip` passed the handshake (32 tools, git not on PATH); CI green on the first push; `scripts/check.ps1` green.
- Not done: GitHub Release with the `.mcpb`, the `compatibility` label, protection of `main`, email privacy setting.
