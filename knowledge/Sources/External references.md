# External references

Accessed 2026-10-29 unless noted.

- **ajaquin8/inventor-mcp** (private, Alex's own): https://github.com/ajaquin8/inventor-mcp. The architecture, scripts, tests and vault layout this project copies.
- **U-C4N/Autocad-MCP** (MIT): https://github.com/U-C4N/Autocad-MCP, commit of 2026-10-26. Read `backends/com_backend.py` for COM patterns (late binding, VARIANT points, PrintWindow capture, plotting, linetype files, CMDACTIVE).
- **ed-fos/autocad-mcp** (Apache-2.0): https://github.com/ed-fos/autocad-mcp. In-process .NET 10 design; notes on main-thread marshalling and undo honesty.
- **puran-water/autocad-mcp** (MIT): https://github.com/puran-water/autocad-mcp. AutoCAD LT via AutoLISP and file IPC.
- **LokmenoWer/best-cad-mcp** (MIT): https://github.com/LokmenoWer/best-cad-mcp. Not read in detail; reported by the research subagent.
- **Autodesk AutoCAD MCP Server**: installed bundle `C:\Program Files\Autodesk\ApplicationPlugins\AutoCAD-MCP-Server-2027.bundle` (26.0.460.2523); help at https://help.autodesk.com/view/ADSKMCP/ENU/ (reported by the research subagent).
- **AutoCAD 2027 ActiveX reference**: help.autodesk.com, "AutoCAD ActiveX Reference Guide". Check unfamiliar members there.
