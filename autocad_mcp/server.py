"""Entry point: registers all tool modules and serves MCP over stdio."""

from __future__ import annotations

import os

from .app import mcp
from .tools import (  # noqa: F401
    annotate,
    blocks,
    commands,
    control,
    documents,
    draw,
    edit,
    layers,
    plot,
    query,
    settings,
    sheets,
)

if os.environ.get("AUTOCAD_MCP_ENABLE_COMMANDS", "").strip().lower() in ("1", "true", "yes", "on"):
    from .tools import power  # noqa: F401


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
