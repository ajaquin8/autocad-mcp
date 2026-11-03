# AutoCAD MCP landscape

Date: 2026-10-29
Writer: Claude Code. Question (Alex): what are the existing AutoCAD MCP servers, and which is best for AutoCAD 2027 on this PC?

## Method
- **verified 2026-10-29:** cloned and read U-C4N/Autocad-MCP, ed-fos/autocad-mcp and puran-water/autocad-mcp (README and key code), and Alex's inventor-mcp.
- **verified 2026-10-29:** found Autodesk's own server installed at `C:\Program Files\Autodesk\ApplicationPlugins\AutoCAD-MCP-Server-2027.bundle` (version 26.0.460.2523) and read the tool descriptions embedded in its DLLs.
- **reported by a research subagent, not re-verified:** the wider survey (GitHub, PyPI, MCP registry, Autodesk help). Star counts and dates came from the GitHub API on 2026-10-29; tool counts are from READMEs.

## Findings
| Server | Connection | Scope | Notes |
|---|---|---|---|
| U-C4N/Autocad-MCP | Python COM + ezdxf | 248 tools | MIT, 204 stars, very active. Live COM tests on 2026 only. Retries rejected read-only calls and checks `CMDACTIVE` (verified in its code). Copies exist under other names. |
| LokmenoWer/best-cad-mcp | Python COM, one COM thread | 116/213/324 tools by profile | MIT, 34 stars. Handle targeting, dry-run before apply. Beta. |
| AUTOM8LABS MCP Connector | Closed-source plug-in | 201 tools | Officially 2022–2027; read-only tier free, edits paid. Not verified. |
| ed-fos/autocad-mcp | In-process .NET 10 | 151 tools, 77 need AutoCAD Architecture | Apache-2.0, alpha, built for 2027. Runs arbitrary code by design. |
| Autodesk AutoCAD MCP Server | In-process, HTTP localhost 5001–5050 | 5 read/query/navigation tools on plain AutoCAD | Supported client is Autodesk Assistant. `updateAutoCADObjects` lives in the Civil 3D DLL. Commands `MCPHTTPSTART`, `MCPHTTPSTOP`, `MCPCONFIG` (reported by the subagent from Autodesk help). |
| puran-water/autocad-mcp | AutoLISP via keystrokes + file IPC | 8 tools | Built for AutoCAD LT; fragile on full AutoCAD. |

## Interpretation (inferred)
- No existing server combines Alex's inventor-mcp safety model (edit guard on the user's own drawings, busy guard, rollback, small tool set, live-test protocol).
- COM from Python is the easiest to change but the most fragile connection; an in-process .NET add-in is the most robust. See [[Decisions/Python COM server foundation]].
- Autodesk's server is a good companion for questions about drawings (query, count, compare with a template) but cannot draft.

## Open questions
- **unresolved:** whether Autodesk's HTTP server can be used from Claude Code without the workarounds reported (NETLOAD, adding a missing DLL).
- **unresolved:** whether AUTOM8LABS or best-cad-mcp are worth a closer look for specific features.
