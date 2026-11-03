"""Build dist/autocad-mcp-<version>.mcpb, the one-click Claude Desktop extension.

    python scripts/build_mcpb.py

The bundle uses the MCPB "uv" server type: it carries only the source and pyproject.toml, and the
host installs Python and the dependencies (pywin32, mcp, Pillow) with uv on the user's PC.
A .mcpb file is a zip with manifest.json at its root.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tomllib
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REPO = "https://github.com/ajaquin8/autocad-mcp"
# Files the uv runtime needs to build the package (pyproject.toml names README.md as the readme).
TOP_FILES = ["pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"]


def manifest() -> dict:
    from autocad_mcp.server import mcp

    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        project = tomllib.load(f)["project"]
    tools = asyncio.run(mcp.list_tools())
    return {
        "manifest_version": "0.4",
        "name": "autocad-mcp",
        "display_name": "AutoCAD",
        "version": project["version"],
        "description": "Lets Claude draw in and inspect the AutoCAD session running on this PC.",
        "long_description": (
            "Attaches to a running full AutoCAD (or a vertical such as AutoCAD Architecture, Mechanical or "
            "Civil 3D) over ActiveX/COM. Windows only; AutoCAD LT is not supported. Only drawings Claude "
            "creates are editable unless you ask otherwise, edits wait while you are in a command, and every "
            "tool is one undo step."
        ),
        "author": {"name": "ajaquin8", "url": "https://github.com/ajaquin8"},
        "repository": {"type": "git", "url": REPO},
        "homepage": REPO,
        "documentation": f"{REPO}/blob/main/INSTALL.md",
        "license": project["license"],
        "keywords": ["autocad", "cad", "drafting", "autodesk"],
        "server": {
            "type": "uv",
            "entry_point": "autocad_mcp/__main__.py",
            "mcp_config": {"command": "uv", "args": ["run", "--directory", "${__dirname}", "autocad-mcp"]},
        },
        "tools": [{"name": t.name, "description": " ".join((t.description or "").split("\n\n")[0].split())}
                  for t in tools],
        "compatibility": {"platforms": ["win32"], "runtimes": {"python": project["requires-python"]}},
    }


def bundle_files() -> list[str]:
    files = list(TOP_FILES)
    for folder, dirs, names in os.walk(os.path.join(ROOT, "autocad_mcp")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        files += [os.path.relpath(os.path.join(folder, n), ROOT) for n in names if n.endswith(".py")]
    return sorted(f.replace(os.sep, "/") for f in files)


def build() -> str:
    data = manifest()
    out = os.path.join(ROOT, "dist", f"autocad-mcp-{data['version']}.mcpb")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(data, indent=2) + "\n")
        for name in bundle_files():
            z.write(os.path.join(ROOT, name), name)
    return out


if __name__ == "__main__":
    path = build()
    print(f"{path} ({os.path.getsize(path) // 1024} KB)")
