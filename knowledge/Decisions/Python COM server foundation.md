# Python COM server foundation

Date: 2026-10-29
Status: adopted (Alex: "Yes, scaffold it", after Claude recommended building an inventor-mcp-style server)
Owner: Alex

## Decision
Build the server in Python, the same way as inventor-mcp. It attaches to the running AutoCAD over COM (`pythoncom.GetActiveObject` on `AutoCAD.Application.26`, falling back to `AutoCAD.Application`) and speaks MCP over stdio with the official `mcp` SDK (2.3). Nothing is installed into AutoCAD. Every COM call runs on one STA worker thread, and every object is late-bound (dynamic dispatch).

## Evidence and citations
- **verified 2026-10-29:** AutoCAD 2027 on this PC is release 26.0.60.0, product key ACAD-A101 (plain AutoCAD), from `HKLM\SOFTWARE\Autodesk\AutoCAD\R26.0\ACAD-A101:409`.
- **verified 2026-10-29 (offline only):** the scaffold passes ruff, the offline tests and a stdio handshake. Not yet run against AutoCAD.
- **inferred:** the alternatives are summarised in [[Research/AutoCAD MCP landscape]]. None combines an edit guard on the user's drawings, a busy guard, rollback and a small tool set.
- **reported by U-C4N, not re-verified:** with a makepy cache, pywin32 wraps entities in their declared interface class and hides members of the real class; dynamic dispatch avoids it (U-C4N says verified on AutoCAD 2026). See [[Research/AutoCAD API gotchas]].

## Alternatives and rationale
- **U-C4N/Autocad-MCP (adopt as is):** widest coverage, but 248 tools (about 89k tokens idle), no edit guard on the user's drawings, and live-tested on 2026 only. Kept as a reference for COM behaviour.
- **In-process .NET add-in (ed-fos style):** the most robust connection (no rejected calls, real transactions), but needs the .NET 10 SDK, a bundle install and an AutoCAD restart, and is harder for Alex to change. Revisit if COM speed or rollback becomes a problem.
- **Autodesk's built-in MCP server:** read-only on plain AutoCAD (5 tools). Useful alongside this one for questions about drawings, not for drafting.

## Consequences and follow-up
- Out-of-process COM is slower per call, and AutoCAD rejects calls while busy; the busy guard and error messages handle that, but there is no automatic retry.
- ActiveX has no transaction abort. Rollback deletes what the tool created and restores recorded property changes; it does not cover everything (see [[Decisions/Edit guard and document safety]]).
- First live check: `acad_status`, then a scratch drawing exercising each tool, under [[Decisions/Live test protocol]].

## Supersedes / superseded by
None.

## 2026-11-03: AutoCAD 2026 and DWG TrueView
- **verified (registry, work PC):** on Alex's work PC `AutoCAD.Application.26` belongs to DWG TrueView 2027 and the installed AutoCAD is 2026. The server now tries every `AutoCAD.Application.<release>` ProgID found in the registry, newest first, then the unversioned name; a running TrueView is skipped and AutoCAD is only launched from a ProgID that starts `acad.exe`. See [[Research/AutoCAD API gotchas]]. **superseded:** the "`AutoCAD.Application.26`, falling back to `AutoCAD.Application`" wording in the Decision above.
