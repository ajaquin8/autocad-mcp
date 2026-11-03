"""Install packaging: the Claude desktop bundle and the portable project config. No AutoCAD needed."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import tomllib
import zipfile

from autocad_mcp.server import mcp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("build_mcpb", os.path.join(ROOT, "scripts", "build_mcpb.py"))
build_mcpb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_mcpb)


def _project() -> dict:
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)["project"]


def test_bundle_manifest_matches_the_package():
    m = build_mcpb.manifest()
    assert m["manifest_version"] == "0.4"
    assert m["version"] == _project()["version"]
    assert m["license"] == "MIT"
    assert m["compatibility"]["platforms"] == ["win32"]
    assert m["server"]["type"] == "uv"
    assert m["server"]["mcp_config"]["args"] == ["run", "--directory", "${__dirname}", "autocad-mcp"]
    assert _project()["scripts"]["autocad-mcp"] == "autocad_mcp.server:main"  # what `uv run autocad-mcp` starts
    listed = [t["name"] for t in m["tools"]]
    assert listed == [t.name for t in asyncio.run(mcp.list_tools())]
    assert "send_command" not in listed  # the raw command line stays opt-in



def test_server_reports_the_package_version():
    with open(os.path.join(ROOT, "autocad_mcp", "app.py"), encoding="utf-8") as f:
        assert re.search(r'version="([^"]+)"', f.read())[1] == _project()["version"]


def test_bundle_carries_what_uv_needs_and_nothing_private():
    files = build_mcpb.bundle_files()
    for needed in ("pyproject.toml", "README.md", "LICENSE", "autocad_mcp/__main__.py", "autocad_mcp/server.py"):
        assert needed in files
    assert build_mcpb.manifest()["server"]["entry_point"] in files
    assert not [f for f in files if f.startswith(("knowledge/", "tests/", "scratch/", ".venv/"))]
    assert not [f for f in files if "__pycache__" in f]


def test_build_writes_a_zip_with_the_manifest_at_its_root():
    path = build_mcpb.build()
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert json.loads(z.read("manifest.json"))["name"] == "autocad-mcp"
    assert set(build_mcpb.bundle_files()) <= set(names)


def test_project_mcp_config_has_no_machine_specific_path():
    with open(os.path.join(ROOT, ".mcp.json"), encoding="utf-8") as f:
        server = json.load(f)["mcpServers"]["autocad"]
    assert server["command"].startswith("${CLAUDE_PROJECT_DIR:-.}/")
    assert ":\\" not in server["command"] and "Users" not in server["command"]
