"""Clearing a prompt this server left open in AutoCAD.

While AutoCAD waits at a prompt it rejects every COM call, so this tool hands
AutoCAD's main window command-line input with a WM_COPYDATA message instead. It
makes no COM call, so it does not run on the COM worker (which may itself be
waiting on AutoCAD).
"""

from __future__ import annotations

import os

import win32gui
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from ..app import mcp
from ..com import AcadError
from ..session import recorded_owned_keys, session
from ..winui import describe_blockers, send_input

# Two Ctrl+C, the "^C^C" of menu macros: cancels a command and its prompt. Handed to AutoCAD as
# command-line input (WM_COPYDATA, dwData 1). Verified live 2026-11-04: it cleared LINE waiting at
# its first prompt, where WM_CHAR/WM_KEYDOWN Esc to the main window did nothing.
CANCEL_INPUT = "\x03\x03"


def owned_names(keys: set[str] | None = None) -> set[str]:
    """File names (lower case) of drawings from edit-guard keys (default: the ones this server owns)."""
    keys = set(session.owned) if keys is None else keys
    return {key[len("unsaved:"):] if key.startswith("unsaved:") else os.path.basename(key) for key in keys}


def owned_in_title(title: str, names: set[str]) -> str | None:
    """The server-created drawing AutoCAD's window title shows as active, if any. The title ends
    with the active drawing's file name ("<product> - [Drawing3.dwg]", or without the brackets)."""
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
        # Not in memory: drawings created by the server's own scripts (or before a restart that has not
        # reconnected yet) are only in the ownership record. Read it again, without COM.
        name = owned_in_title(title, owned_names(recorded_owned_keys(hwnd)))
    if name is None:
        raise AcadError(f"Refused: AutoCAD's active drawing (window title {title!r}) was not created by this "
                        "server. A cancel there could stop the user's own command; ask the user to press Esc "
                        "if they need to." + describe_blockers(hwnd))
    if not send_input(hwnd, CANCEL_INPUT):
        raise AcadError("AutoCAD did not accept the cancel within 5 s (it may be hung). Ask the user to check it.")
    note = describe_blockers(hwnd)
    return (f"Cancelled the command in '{name}'. Call acad_status to check that AutoCAD answers again."
            + (f" Note:{note}" if note else ""))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False),
          structured_output=False)
async def cancel_command() -> str:
    """Cancel a command or prompt this server left open in AutoCAD (for example a scripted
    command stopped at "Select objects:"), which makes AutoCAD reject every other call.
    Works even then: it hands AutoCAD two Ctrl+C through a window message, not COM.
    Refuses unless AutoCAD's active drawing is one this server created (also one its
    scripts created: the ownership record is read again), so it cannot cancel the
    user's work in their own drawings. It cannot close a dialog; when one is open it
    names it. Do not use it while the user is working in that drawing.
    """
    try:
        return cancel()
    except AcadError as err:
        raise ToolError(str(err)) from None
