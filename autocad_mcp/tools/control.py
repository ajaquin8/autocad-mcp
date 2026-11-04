"""Clearing a prompt this server left open in AutoCAD.

While AutoCAD waits at a prompt it rejects every COM call, so this tool hands
AutoCAD's main window command-line input with a WM_COPYDATA message instead. It
makes no COM call, so it does not run on the COM worker (which may itself be
waiting on AutoCAD).
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

import win32gui
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from ..app import mcp
from ..com import AcadError
from ..session import session

WM_COPYDATA = 0x004A
SMTO_ABORTIFHUNG = 0x0002
# Two Ctrl+C, the "^C^C" of menu macros: cancels a command and its prompt. Handed to AutoCAD as
# command-line input (WM_COPYDATA, dwData 1). Verified live 2026-11-04: it cleared LINE waiting at
# its first prompt, where WM_CHAR/WM_KEYDOWN Esc to the main window did nothing.
CANCEL_INPUT = "\x03\x03"


class _CopyData(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD), ("lpData", ctypes.c_void_p)]


def owned_names() -> set[str]:
    """File names (lower case) of the drawings this server created, from the edit guard's keys."""
    return {key[len("unsaved:"):] if key.startswith("unsaved:") else os.path.basename(key)
            for key in list(session.owned)}


def owned_in_title(title: str, names: set[str]) -> str | None:
    """The server-created drawing AutoCAD's window title shows as active, if any. The title ends
    with the active drawing's file name ("<product> - [Drawing3.dwg]", or without the brackets)."""
    text = title.strip().rstrip("]").rstrip().lower()
    for name in names:
        if text.endswith(name) and (len(text) == len(name) or text[-len(name) - 1] in " \t[-"):
            return name
    return None


def send_input(hwnd: int, text: str) -> bool:
    """Hand text to AutoCAD's command line through WM_COPYDATA; False if AutoCAD did not take it in 5 s."""
    buf = ctypes.create_unicode_buffer(text)
    data = _CopyData(1, ctypes.sizeof(buf), ctypes.cast(buf, ctypes.c_void_p))
    result = ctypes.c_size_t()
    sent = ctypes.windll.user32.SendMessageTimeoutW(wintypes.HWND(hwnd), WM_COPYDATA, None, ctypes.byref(data),
                                                    SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
    return bool(sent)


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
                        "server. A cancel there could stop the user's own command; ask the user to press Esc "
                        "if they need to.")
    if not send_input(hwnd, CANCEL_INPUT):
        raise AcadError("AutoCAD did not accept the cancel within 5 s (it may be hung). Ask the user to check it.")
    return f"Cancelled the command in '{name}'. Call acad_status to check that AutoCAD answers again."


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False),
          structured_output=False)
async def cancel_command() -> str:
    """Cancel a command or prompt this server left open in AutoCAD (for example a scripted
    command stopped at "Select objects:"), which makes AutoCAD reject every other call.
    Works even then: it hands AutoCAD two Ctrl+C through a window message, not COM.
    Refuses unless AutoCAD's active drawing is one this server created, so it cannot
    cancel the user's work in their own drawings. Do not use it while the user is
    working in that drawing.
    """
    try:
        return cancel()
    except AcadError as err:
        raise ToolError(str(err)) from None
