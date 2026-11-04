"""Clearing a prompt this server left open in AutoCAD.

While AutoCAD waits at a prompt it rejects every COM call, so this tool sends
Windows messages to AutoCAD's main window instead. It makes no COM call, so it
does not run on the COM worker (which may itself be waiting on AutoCAD).
"""

from __future__ import annotations

import os

import win32con
import win32gui
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from ..app import mcp
from ..com import AcadError
from ..session import session


def owned_names() -> set[str]:
    """File names (lower case) of the drawings this server created, from the edit guard's keys."""
    return {key[len("unsaved:"):] if key.startswith("unsaved:") else os.path.basename(key)
            for key in list(session.owned)}


def owned_in_title(title: str, names: set[str]) -> str | None:
    """The server-created drawing AutoCAD's window title shows as active, if any. The title ends
    with the active drawing's file name ("<product>  Drawing3.dwg", older releases "- [Drawing3.dwg]")."""
    text = title.strip().rstrip("]").rstrip().lower()
    for name in names:
        if text.endswith(name) and (len(text) == len(name) or text[-len(name) - 1] in " \t[-"):
            return name
    return None


def cancel() -> str:
    hwnd = session.hwnd
    if not hwnd:
        raise AcadError("Not connected to AutoCAD yet; call acad_status first.")
    if not win32gui.IsWindow(hwnd):
        raise AcadError("AutoCAD's window is gone (was it closed?). Call acad_status.")
    title = win32gui.GetWindowText(hwnd)
    name = owned_in_title(title, owned_names())
    if name is None:
        raise AcadError(f"Refused: AutoCAD's active drawing (window title {title!r}) was not created by this "
                        "server. Esc there could cancel the user's own command; ask the user to press Esc "
                        "if they need to.")
    for _ in range(2):
        win32gui.PostMessage(hwnd, win32con.WM_CHAR, win32con.VK_ESCAPE, 0)
    return f"Sent Esc twice to AutoCAD while '{name}' was active. Call acad_status to check that it answers again."


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False),
          structured_output=False)
async def cancel_command() -> str:
    """Press Esc twice in AutoCAD to clear a command or prompt this server left open (for
    example a scripted command stopped at "Select objects:"), which makes AutoCAD reject
    every other call. Works even then: it uses window messages, not COM. Refuses unless
    AutoCAD's active drawing is one this server created, so it cannot cancel the user's
    work in their own drawings. Do not use it while the user is working in that drawing.
    """
    try:
        return cancel()
    except AcadError as err:
        raise ToolError(str(err)) from None
