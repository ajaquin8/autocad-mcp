"""Opt-in raw command line access. Registered only with AUTOCAD_MCP_ENABLE_COMMANDS=1.

This bypasses the edit guard and the rollback, so it is off by default.
"""

from __future__ import annotations

from ..app import acad_tool
from ..session import session


@acad_tool(destructive=True)
def send_command(command: str, name: str = "") -> str:
    """Send text to the AutoCAD command line, exactly as if typed (SendCommand).
    BYPASSES the edit guard and rollback. Use only when no other tool can do the job
    and the user agreed. End the command with a space or "\\n" so it runs, e.g.
    "_.ZOOM _E ". AutoCAD queues it; check the result with the query tools.

    Args:
        command: command line text.
        name: which open drawing; it must be the active one.
    """
    doc = session.document(name)
    session.require_idle(doc)
    doc.SendCommand(command)
    return f"Sent to '{doc.Name}': {command!r}"
