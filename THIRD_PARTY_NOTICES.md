# Third-party notices

## Runtime dependencies (installed from PyPI, not bundled)
- **mcp** (Model Context Protocol Python SDK), MIT. https://github.com/modelcontextprotocol/python-sdk
- **pywin32**, PSF-2.0. https://github.com/mhammond/pywin32
- **Pillow**, MIT-CMU (HPND). https://github.com/python-pillow/Pillow — used to encode the view capture as PNG.
- Transitive dependencies of `mcp` (anyio, pydantic, httpx, starlette and others) are MIT, BSD or Apache-2.0.

## Install tool (used on the user's PC, not bundled)
- **uv** (Astral), MIT or Apache-2.0. https://github.com/astral-sh/uv — installs Python and the runtime dependencies for `uvx` and the `.mcpb` bundle.

## Development dependencies
- **pytest**, MIT. **ruff**, MIT.

## Prior art (ideas, no code copied verbatim)
- **ajaquin8/inventor-mcp** (the same author's project): the whole architecture, the scripts and the vault layout.
- **U-C4N/Autocad-MCP**, MIT. https://github.com/U-C4N/Autocad-MCP. AutoCAD COM lessons: late-bound dispatch instead of makepy wrappers, VARIANT double arrays for points, `PrintWindow` window capture, foreground plotting (`BACKGROUNDPLOT=0`) so `PlotToFile` writes the file before returning, and `acadiso.lin` vs `acad.lin` by `MEASUREMENT`.

## Not redistributed
Autodesk AutoCAD, its type library and its help files are not part of this repository.
