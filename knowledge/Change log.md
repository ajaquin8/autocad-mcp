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

## 2026-11-03: bundle tested in the Claude desktop app
Writer: Claude Code side session (Alex: "Yes, guide me", then installed the bundle and reported "Both worked").
- The v0.1.0 `.mcpb` installed by double-click; the desktop app used its own uv 0.9.7, so bundle users need no uv. `acad_status` worked in Chat and in Cowork. Details in [[Decisions/Distribution and install]].
- Changed: `INSTALL.md` (bundle first, for Chat and Cowork, without uv; uv only for Claude Code and the config-file fallback; updating per route), README install summary.
- Found: Claude misread version `25.1` as AutoCAD 2025; a separate change makes `acad_status` report the year. Drawing names and paths from the pasted reply are not recorded.
- Validation: `scripts/check.ps1` green.

## 2026-11-03: acad_status names the AutoCAD year (0.1.1)
Writer: Claude Code side session (Alex: "Yes, fix it", after Claude read version 25.1 as AutoCAD 2025 in the desktop test).
- `autocad_mcp/session.py`: `RELEASE_YEARS` and `product_name()`; `acad_status` returns `"autocad": "AutoCAD 2026"` plus the raw `autocad_version`, and its description tells Claude to use the first. `scripts/stdio_smoke.py` prints the new name.
- Version 0.1.1 in `pyproject.toml` and `autocad_mcp/app.py`, with a test that keeps them equal. Updated [[Research/AutoCAD API gotchas]] and the regenerated [[Projects/AutoCAD-MCP/Tool reference]].
- Validation: three new offline tests; `scripts/check.ps1` green. **Not run against a live AutoCAD** (the mapping is a lookup on the version string already returned live: 25.1 on 2026, 26.0 on 2027).

## 2026-11-03: v0.1.1 released and checked live
Writer: Claude Code side session (Alex: "Merged, publish", then installed 0.1.1 and pasted the Chat reply).
- Release v0.1.1 (`698d988`, bundle SHA-256 `26aab952…ded2d`); the public "latest" download matched the build and passed the handshake (32 tools). The v0.1.0 notes now point to 0.1.1.
- Live: the updated extension made Claude say "AutoCAD 2026". Recorded in [[Decisions/Distribution and install]].

## 2026-11-03: safety check (AMCP-LIVE-20261103-03) and the busy message (0.1.2)
Writer: Claude Code side session (Alex: "Okay lets start with 1", then "Saved, go" and the AutoCAD steps between phases).
- New: `tests/live/safety_check.py` (phased live batch) and [[Sources/2026-11-03 Safety check]]. Updated [[Sources/index]], [[Projects/AutoCAD-MCP/Roadmap]], [[Projects/AutoCAD-MCP/index]], [[Research/AutoCAD API gotchas]], README status.
- Result on AutoCAD 2026: 41/44. Edit guard, one Ctrl+Z per tool, blocks, edits by handle and open/close passed; nothing was drawn inside LINE or with OPTIONS open, but the refusal reached Claude as `AttributeError: <unknown>.Count`.
- Fix: `autocad_mcp/com.py` `describe_attribute_error` and `autocad_mcp/app.py` turn that into the busy message; offline test added; version 0.1.2. The fix was not rerun live.
- Validation: `scripts/check.ps1` green. Drawing names from Alex's PC are not recorded.

## 2026-11-03: busy message verified live; repository settings
Writer: Claude Code side session (Alex pasted the Chat's busy reply, then "Lets do 1 next").
- [[Sources/2026-11-03 Safety check]]: addendum, the 0.1.2 busy message seen live through the Claude desktop app.
- GitHub: `compatibility` label; `main` protected (pull requests, `check` CI required, no force-push or deletion, admin override kept). Recorded in [[Decisions/Distribution and install]].
- Validation: settings read back from the GitHub API; `scripts/check.ps1` green.

## 2026-11-03: sheet tools (0.1.3)
Writer: Claude Code side session (Alex: "Fab part drawings", then chose the sketch sheet, the angle-stop benchmark and a private playbook; "Saved, go").
- New tools: `add_viewport`, `list_layouts` (new module `tools/sheets.py`), `add_leader`, `add_radial_dimension`, `draw_center_mark`, `set_current_styles`; `query_entities` takes a `layout`. Fakes and seven offline tests added. Version 0.1.3; README tool list.
- Live: [[Sources/2026-11-03 Sheet tools]] (39/39). Lessons in [[Research/AutoCAD API gotchas]]; updated [[Projects/AutoCAD-MCP/index]], [[Projects/AutoCAD-MCP/Roadmap]], [[Sources/index]].
- The company-specific playbook and the sheet template are private (outside this repository) by Alex's decision.
- Validation: `scripts/check.ps1` green.

## 2026-11-03: decimal separator and plot style re-plot
Writer: Claude Code side session (Alex: "Yes, install it", "Saved, go", "Yes, add to PR #7").
- Live: [[Sources/2026-11-03 Plot style re-plot]] (8/8) after the user's plot style table was installed outside this repository. Lessons in [[Research/AutoCAD API gotchas]]; [[Sources/index]] updated.
- Correction in [[Sources/2026-11-03 Sheet tools]]: the decimal dimensions printed with a comma, not `1.00`.
- `set_drawing_variables` accepts DIMDSEP ("." or ","), with an offline test. Not live-verified.
- Validation: `scripts/check.ps1` green.

## 2026-11-03: dynamic block authoring series
Writer: Claude Code side session (Alex: "Yes, record them", after the runs approved with "Saved, go").
- Live: [[Sources/2026-11-03 Dynamic block authoring]] (AMCP-LIVE-20261103-06 to -13). Lessons in [[Research/AutoCAD API gotchas]] (dynamic blocks; the console engine); [[Sources/index]] and [[Projects/AutoCAD-MCP/Roadmap]] updated.
- No code change. Open bug recorded: `new_drawing` can fail while AutoCAD is busy initialising the new drawing.
- The block, its data and the scripts that built it are the user's and stay outside this repository.
- Validation: `scripts/check.ps1` green.

## 2026-11-04: dynamic block rebuilt around one shared array
Writer: Claude Code side session (Alex: "One shared array", then "Saved, go" and "Yes, record them").
- Live: [[Sources/2026-11-04 Dynamic block shared array]] (AMCP-LIVE-20261104-01 to -03). Lessons in [[Research/AutoCAD API gotchas]]; [[Sources/index]] and [[Projects/AutoCAD-MCP/Roadmap]] updated.
- A dated section was added to [[Sources/2026-11-03 Dynamic block authoring]]: the fault found afterwards, and a corrected diagnosis of run 11 (inferred).
- No code change. The block and its scripts stay outside this repository.

## 2026-11-04: roadmap items to reduce desktop control
Writer: Claude Code side session (Alex: "In general what improvements can we make … to reduce the amount of computer use", then "Yes, add them").
- [[Projects/AutoCAD-MCP/Roadmap]]: new proposed section with five items, in order: busy handling (retry rejected calls, a cancel tool, settle after `new_drawing`); ownership across restarts; dynamic block place, test, inspect and Block Editor tools; experiments for dialog-only settings; an in-process .NET helper.
- No code change.

## 2026-11-04: busy handling (roadmap item 1)
Writer: Claude Code side session (Alex: "start on item 1 the busy handling").
- Code:
  - `com.py`: a ctypes message filter on the COM worker retries "retry later" rejections for up to 8 s (`AUTOCAD_MCP_BUSY_RETRY_SECONDS`).
  - `session.py`: `settle()`, and AutoCAD's window handle remembered at connect.
  - `new_drawing` waits for the new drawing to settle.
  - New tool `cancel_command` (`tools/control.py`): `^C^C` as command-line input through WM_COPYDATA, only while a server-created drawing is active.
  - Server instructions and README updated. [[Projects/AutoCAD-MCP/Tool reference]] regenerated (39 tools).
- Docs: dated sections in [[Decisions/Edit guard and document safety]] and [[Projects/AutoCAD-MCP/Roadmap]]; a lesson in [[Research/AutoCAD API gotchas]].
- Tests: 8 new offline tests (64 in total). Live: [[Sources/2026-11-04 Busy handling]] (AMCP-LIVE-20261104-04). The first cancel method, Esc window messages, failed live, and the tool was changed to WM_COPYDATA `^C^C`, which passed. The filter also counts rejections by type, for diagnosis.

## 2026-11-04: ownership across a server restart (roadmap item 2)
Writer: Claude Code side session (Alex: "Yes, start item 2").
- Code (`session.py`): a record of the server-created drawings, kept in `%LOCALAPPDATA%\autocad-mcp\owned.json`. A restarted server takes back only drawings still open in the same AutoCAD (same process and start time, same key, same `Document.HWND`). The record is updated on create, Save As and close.
- README Safety section and [[Decisions/Edit guard and document safety]] updated (dated section; the "resets on restart" rule is narrowed, not dropped); [[Projects/AutoCAD-MCP/Roadmap]] item 2 status.
- Tests: 6 new offline tests (70 in total). Live: [[Sources/2026-11-04 Ownership across restarts]] (AMCP-LIVE-20261104-05). It also fixed `open_drawing`, which now waits for the opened drawing to settle, and made `MessageFilter.register()` keep registered filters alive after a one-off script crashed.

## 2026-11-04: dynamic block tools, part 1 (roadmap item 3)
Writer: Claude Code side session (Alex: "Yes lets do that next").
- New tools (`tools/blocks.py`):
  - `get_block_properties` (read-only): shown dynamic properties with allowed values, plus attributes and whether each is invisible.
  - `set_block_properties`: by name, in order, with distances as numbers or inch fractions, checked against allowed values. It is one undo step and rolls back on refusal. Hidden helpers need `allow_hidden`. It regenerates so label fields update.
  - `measure_block`: explodes a temporary copy, reports the visible extents and counts (optionally the geometry), then deletes it. Server-created drawings only.
  - `insert_block` takes `dynamic_properties`.
- [[Projects/AutoCAD-MCP/Tool reference]] regenerated (42 tools); README and [[Projects/AutoCAD-MCP/Roadmap]] item 3 status updated.
- Tests: 7 new offline tests (77 in total). Live: [[Sources/2026-11-04 Dynamic block tools]] (AMCP-LIVE-20261104-06), 13/13. The first run's one miss was the script's own height check, now a tip check.

## 2026-11-04: block tools through the server
Writer: Claude Code (Alex: "Saved, go", then "Yes, close and record").
- New: [[Sources/2026-11-04 Block tools through the server]] (AMCP-LIVE-20261104-07), 8/8 through Claude's own MCP connection after the merge and a full restart of Claude.
- Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]] (a dynamic block's bounding box includes hidden sizes).
- No code changed.

## 2026-11-04: insert_block reports what a dynamic block shows
Writer: Claude Code (Alex: "Yes, fix it").
- `insert_block`: for a dynamic block, `bbox` is now measured from a temporary exploded copy (attribute text left out), because AutoCAD's box also counts hidden sizes ([[Sources/2026-11-04 Block tools through the server]]). `measure_block` shares the same helpers; it now forgets only its own exploded parts instead of clearing the whole rollback list.
- Updated: [[Research/AutoCAD API gotchas]], the regenerated [[Projects/AutoCAD-MCP/Tool reference]].
- Tests: 1 new offline test (78 in total). **Not live-verified.**

## 2026-11-06: command reliability, part 1 (cancel, dialogs, quick polls)
Writer: Claude Code side session, from the plan in the 2026-11-06 drafting-templates session's notes.
- Code:
  - `tools/control.py`: `cancel_command` reads `owned.json` again (without COM) before refusing, so it can cancel in drawings the server's own scripts created.
  - New `winui.py`: COM-free window helpers. Busy errors (and timeouts, and the busy guard's refusal) name the dialog AutoCAD shows, with its buttons.
  - `com.py`: `worker.quick_retries()`; `acad_status` retries rejected calls for 1 s instead of 8 s, so a stuck command shows up fast.
  - `session.py`: the busy refusal says what CMDACTIVE means (for example "a command and an AutoLISP expression").
- New: [[Sources/2026-11-06 Stretch grips by script]] (AMCP-LIVE-20261106-01), written from that session's notes. Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]], [[Decisions/Edit guard and document safety]], the regenerated [[Projects/AutoCAD-MCP/Tool reference]].
- Tests: 5 new offline tests (83 in total). **Not live-verified.**

## 2026-11-06: command reliability, part 2 (run_command)
Writer: Claude Code side session.
- New tool `run_command` (`tools/commands.py`): one command plus a list of answers, sent as one inline AutoLISP expression through WM_COPYDATA (no COM call while it runs, no `.lsp` file, so no SECURELOAD prompt). It feeds the answers one by one, logs LASTPROMPT after each, stops if the command ends early, cancels with `(command)` if it still waits, goes back to an UNDO mark on failure, and returns the transcript. Object snaps are off while it runs.
- `winui.py` now holds `send_input` (moved from `tools/control.py`) and `window_title`.
- Updated: README Safety and Tools, [[Decisions/Edit guard and document safety]], the regenerated [[Projects/AutoCAD-MCP/Tool reference]] (43 tools).
- Tests: 10 new offline tests (93 in total). **Not live-verified.**

## 2026-11-06: command reliability, part 3 (Block Editor tools)
Writer: Claude Code side session.
- New tools (`tools/block_editor.py`), built on `run_command`, with the prompt orders seen live on 2026-11-06 ([[Sources/2026-11-06 Stretch grips by script]]):
  - `open_block_editor` / `close_block_editor` (-BEDIT with the name as a LISP string; BSAVE then BCLOSE, answering a Save/Discard prompt if it comes);
  - `add_linear_parameter` (Label, points, label location, number of grips; returns a pick point on the parameter's line);
  - `add_stretch_action` (Stretch keyword T, parameter point Second by default, parameter picked by a computed point, crossing selection, polylines and dimensions removed for multiplier actions; BACTIONBARMODE 0 while it runs, then put back);
  - `lock_attribute_positions` (COM, one undo step, editor closed);
  - `check_dynamic_block` (temporary insert, properties case by case, measured change compared with what is expected, reference deleted).
- New live script `tests/live/command_check.py` (not run: it needs Alex's go).
- Updated: README, [[Projects/AutoCAD-MCP/Roadmap]] item 3, the regenerated [[Projects/AutoCAD-MCP/Tool reference]] (49 tools).
- Tests: 8 new offline tests (101 in total). **Not live-verified**; inferred: a linear parameter's line runs through the label location (the pick point relies on it).

## 2026-11-08: tiny house drawing (live)
Writer: Claude Code (Alex: "Want to draw a cool tiny house…", then "lets do it" and "Restarted, go").
- New: [[Sources/2026-11-08 Tiny house drawing]] (AMCP-LIVE-20261108-01). Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]].
- No code changed. The drawing is in `scratch/` (not in git).

## 2026-11-10: template tools without the command line
Writer: Claude, in a Claude desktop session building a steel-detailing drawing template (Alex: "please proceed with option 1"). Branch `feat/template-tools`, not pushed.
- Why: building a drawing template through the installed extension on AutoCAD 2027 (2026-11-09) needed text, dimension and multileader styles, a paper size, a non-plotting layer and a title block on a sheet. None of these had a tool, and `run_command` did not work there. That is **observed** in ordinary use, not a test batch: the expression never started, no transcript file appeared, and AutoCAD showed a Help dialog after the tool's fallback Enter. The cause is **unresolved**.
- New tools, all plain ActiveX inside `session.edit` (edit guard, busy guard, one undo step, rollback):
  - `tools/settings.py`: `add_text_style` (`TextStyles.Add`, `FontFile`, height, width factor, oblique angle); `add_dimension_style` (`DimStyles.Add`, then `CopyFrom` the document; takes DIM* variables, a text style and an arrowhead; the style becomes current); `add_multileader_style` (an `AcDbMLeaderStyle` in the `ACAD_MLEADERSTYLE` dictionary; `ScaleFactor`, text height, arrow size, text style).
  - `tools/sheets.py`: `set_page_setup` (plot device, paper size by the name Page Setup shows, plot style table; the layout is plotted 1:1 without rotation).
  - `tools/blocks.py`: `add_attribute_definition` (`ModelSpace.AddAttribute`, position locked by default).
- Changed tools:
  - `insert_block` takes `layout` and then inserts into that sheet's paper space; without it, model space as before.
  - `add_layer` takes `plot`, the layer's plot flag.
  - `set_drawing_variables` also takes DIMTAD, DIMTIH, DIMTOH, DIMFRAC, DIMEXO, DIMEXE and DIMGAP. Its validation and its dimension rebuild moved into `checked()` and `rebuild_dimensions()`, which `add_dimension_style` shares.
- Version 0.1.4. Updated: README Tools, the server instructions, [[Projects/AutoCAD-MCP/Roadmap]], [[Projects/AutoCAD-MCP/index]], the regenerated [[Projects/AutoCAD-MCP/Tool reference]] (54 tools).
- Sources: AutoCAD 2027 ActiveX Reference Guide (help.autodesk.com, read 2026-11-10) for `TextStyle.FontFile`, `DimStyle.CopyFrom`, the `MLeaderStyle` object, the `Layout` plot members and `AddAttribute`; the DIMBLK system variable page for the arrowhead names.
- Tests: 12 new offline tests (113 in total); `scripts\check.ps1` passes. **Not live-verified:** none of the new COM calls has run against AutoCAD. To check live:
  - a TrueType file name (`arial.ttf`) in `FontFile`;
  - DIMTIH and DIMTOH as 0/1 through `SetVariable`;
  - a `DIMBLK` name before that arrowhead block exists in the drawing;
  - an empty attribute default;
  - `InsertBlock` on the block of a layout that is not the current tab;
  - the paper names each plot device lists, and whether a new multileader style needs more than the four sizes copied from the current one.

## 2026-11-10: template tools, first live run and fixes
Writer: Claude, same session (Alex: "Lets go!" for the batch; after its first failure, "keep pushing and keep testing as we build"). Branch `feat/template-tools`, not pushed.
- New: [[Sources/2026-11-10 Template tools]] (AMCP-LIVE-20261110-01). The 0.1.4 bundle was installed in Claude desktop and the tools were called through Claude's MCP connection on AutoCAD 2027: 14 of 15 checks.
- Fixes from it:
  - `add_text_style`: a TrueType file given by name is looked up in the Windows Fonts folders and passed as a full path, because AutoCAD refused `arial.ttf` by name. A refused font now gets a plain message (the refusal is an `AttributeError`).
  - `add_attribute_definition`: the tool makes the tag upper case, because AutoCAD kept `title` as typed.
  - `add_dimension`: its description says where the text goes when it does not fit.
- Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]] (two new sections, one on `run_command` as observed through the extension), [[Projects/AutoCAD-MCP/index]], [[Projects/AutoCAD-MCP/Roadmap]].
- Tests: 2 new offline tests (115 in total); `scripts\check.ps1` passes. The fixes themselves are **not live-verified**, because the installed bundle predates them; the full-path font route they rely on is.
- Version 0.1.5, so the fixed bundle can be told apart from the 0.1.4 that was installed for the live run.
- Deviation from [[Decisions/Live test protocol]]: the batch's title-block drawing and its PDF went to the Windows Temp folder, not `scratch/`, and were deleted afterwards.

## 2026-11-11: template tools, second live run and fixes
Writer: Claude, same session (Alex, after installing 0.1.5: "want to test it now and then I will merge after"). Branch `feat/template-tools`.
- New: [[Sources/2026-11-11 Template tools second run]] (AMCP-LIVE-20261111-01), on AutoCAD 2027 through Claude's MCP connection: 11 of 13 checks. The three 0.1.5 fixes work live, and so does changing existing styles.
- Fixes from it:
  - `add_multileader_style`: a new style now gets a text style (the current multileader style's, else the current text style). Made without one, it had none at all and the tool failed reading it back.
  - `set_page_setup`: a failed call on a layout never set up no longer reports an incomplete rollback; the empty paper name is not put back, because AutoCAD refuses it.
- Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]], [[Projects/AutoCAD-MCP/index]], [[Projects/AutoCAD-MCP/Roadmap]].
- Tests: 2 new offline tests (117 in total); `scripts\check.ps1` passes. Version 0.1.6. These two fixes are **not live-verified**.
- One step used a short COM script instead of the server, on the scratch drawing only, to find which layout property could not be put back.

## 2026-11-11: the 0.1.6 fixes, checked live
Writer: Claude, same session (Alex installed the 0.1.6 bundle: "Okay its installed"). Branch `feat/template-tools`.
- New: [[Sources/2026-11-11 Template tools third run]] (AMCP-LIVE-20261111-02), on AutoCAD 2027 through Claude's MCP connection: 3 of 3 checks. Both 0.1.6 fixes work live. This **supersedes** "not live-verified" in the entry above.
- Updated: [[Sources/index]], [[Sources/2026-11-11 Template tools second run]], [[Research/AutoCAD API gotchas]], [[Projects/AutoCAD-MCP/index]], [[Projects/AutoCAD-MCP/Roadmap]].
- No code change.

## 2026-11-11: run_command starts (input limit found, expression sent in short messages)
Writer: Claude, in a Claude desktop session, on Alex's go ("Yes"). Branch `fix/run-command-input-limit` (from `feat/template-tools`). Version 0.1.7.
- New: [[Sources/2026-11-11 run_command input limit]] (AMCP-LIVE-20261111-03 and -04). AutoCAD drops a WM_COPYDATA message of 1000 characters or more without a word, and evaluates nothing until Enter. `run_command` sent about 1,350 characters and no Enter, so it never started.
- Code (`tools/commands.py`):
  - The expression goes to AutoCAD as short complete expressions, each with its Enter (`staged_messages`): pieces of its text stored in `amcp:src`, each acknowledged by an `S` line in the transcript, then `(eval (read amcp:src))`.
  - No fallback Enter any more. If a message is not taken within 3 s, the server cancels what was typed and says which message it was.
  - The transcript folder is `%USERPROFILE%\.autocad-mcp\run` (`AMCP_RUN_DIR` overrides it), because the Store build of Claude gives the server a private `%LOCALAPPDATA%`.
  - The result has `messages` (how many were sent) in place of `needed_enter`.
- Tests: the fake command line follows the new protocol; 2 tests replaced, 1 added. `ruff` and the offline tests pass.
- Live: 22 of 22 checks with the repo code (hatch with an island, true colour, 25 answers, new layout, cancel and undo). **Not verified** through the installed extension, which is still 0.1.6.
- Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]], [[Projects/AutoCAD-MCP/Roadmap]].

## 2026-11-11: run_command checked through the installed 0.1.7 bundle
Writer: Claude, same session (Alex installed the bundle and restarted Claude). Branch `fix/run-command-input-limit`.
- [[Sources/2026-11-11 run_command input limit]] gained a section: 9 of 9 checks through Claude's own MCP connection (hatch, true colour, explode, layout rename and new, cancel and undo). This **supersedes** "not verified through the installed extension" in the entry above.
- Found: `get_entity` reports a true colour as its nearest index colour; EXPLODE takes one object and no closing Enter.
- No code change.

## 2026-11-12: sheets plot with their own PDF driver; the best one is the default
Writer: Claude, in a Claude desktop session, on Alex's go ("Lets do it"). Branch `feat/plot-device` (from `main` after PR #22).
- New: [[Sources/2026-11-12 PDF plot device]] (AMCP-LIVE-20261112-01): the legacy driver writes 600 dpi vectors, High Quality Print 2400; `plot_pdf` ignored the sheet's driver; solid fills are written as hairline-stroked triangles, which is why they look rough on screen whatever the resolution.
- Code:
  - `plot_pdf` plots with the driver in the sheet's page setup when that is one of AutoCAD's PDF drivers, else `DWG To PDF.pc3`. New argument `plot_device` for one plot; the result names the `device` used.
  - `set_page_setup` takes `plot_device`; with none named it picks `AutoCAD PDF (High Quality Print).pc3` if AutoCAD has it, else `DWG To PDF.pc3`. `device` still works as the older name.
- Tests: 1 new offline test (119 in total); `scripts\check.ps1` passes. Live: 28 of 28 with the repo code. **Not verified** through an installed bundle.
- Updated: [[Sources/index]], [[Research/AutoCAD API gotchas]], Tool reference.
- 2026-11-13: version 0.1.8 in `pyproject.toml` and `app.py`, on Alex's go ("Okay lets push it"), so a bundle with this change can be told apart from the installed 0.1.7. Still **not verified** through an installed bundle.
