"""Looking at AutoCAD's windows without COM.

While AutoCAD shows a modal dialog or waits at a prompt it rejects COM calls, so these helpers use
plain Win32 window functions only. They make no COM call and may run on any thread.
"""

from __future__ import annotations

import contextlib
import ctypes
from ctypes import wintypes
from typing import Any

import win32api
import win32gui
import win32process

DIALOG_CLASS = "#32770"  # standard Windows dialogs, message boxes and task dialogs
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_BUTTONS = 8
WM_COPYDATA = 0x004A
SMTO_ABORTIFHUNG = 0x0002


class _CopyData(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD), ("lpData", ctypes.c_void_p)]


def send_input(hwnd: int, text: str) -> bool:
    """Hand text to AutoCAD's command line through WM_COPYDATA (dwData 1, the channel external programs
    use to send commands); False if AutoCAD did not take it within 5 s."""
    buf = ctypes.create_unicode_buffer(text)
    data = _CopyData(1, ctypes.sizeof(buf), ctypes.cast(buf, ctypes.c_void_p))
    result = ctypes.c_size_t()
    sent = ctypes.windll.user32.SendMessageTimeoutW(wintypes.HWND(hwnd), WM_COPYDATA, None, ctypes.byref(data),
                                                    SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
    return bool(sent)


def window_title(hwnd: int) -> str:
    """The window's title ('' if it is gone)."""
    try:
        return win32gui.GetWindowText(hwnd)
    except Exception:  # noqa: BLE001
        return ""


def window_pid(hwnd: int) -> int | None:
    """Process id of the window's owner, or None if the window is gone."""
    try:
        if not win32gui.IsWindow(hwnd):
            return None
        return int(win32process.GetWindowThreadProcessId(hwnd)[1])
    except Exception:  # noqa: BLE001 - a vanished window is simply not there
        return None


def process_identity(hwnd: int) -> str | None:
    """'<process id>@<start time>' of the process that owns the window, or None."""
    pid = window_pid(hwnd)
    if pid is None:
        return None
    try:
        handle = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            started = win32process.GetProcessTimes(handle)["CreationTime"]
        finally:
            win32api.CloseHandle(handle)
        return f"{pid}@{started.isoformat()}"
    except Exception:  # noqa: BLE001
        return None


def _buttons(hwnd: int) -> list[str]:
    """Captions of the push buttons inside a dialog ("&Save" -> "Save")."""
    found: list[str] = []

    def visit(child: int, _: Any) -> bool:
        with contextlib.suppress(Exception):
            if win32gui.GetClassName(child) == "Button" and win32gui.IsWindowVisible(child):
                text = win32gui.GetWindowText(child).replace("&", "").strip()
                if text and text not in found:
                    found.append(text)
        return len(found) < MAX_BUTTONS

    with contextlib.suppress(Exception):  # EnumChildWindows raises when the callback stops it early
        win32gui.EnumChildWindows(hwnd, visit, None)
    return found


def blocking_dialogs(main: int) -> list[dict]:
    """Dialogs AutoCAD shows on top of its main window: title, buttons and window class.

    Counted: visible, enabled top-level windows of AutoCAD's process other than the main window
    that are standard dialogs (#32770, which includes message boxes and task dialogs), plus any
    other titled window while the main window is disabled (a modal WPF or MFC dialog). Floating
    palettes stay out while AutoCAD's main window is enabled. Task dialogs draw their buttons
    themselves, so their buttons may be missing from the list.
    """
    pid = window_pid(main)
    if pid is None:
        return []
    try:
        main_enabled = bool(win32gui.IsWindowEnabled(main))
    except Exception:  # noqa: BLE001
        main_enabled = True
    found: list[dict] = []

    def visit(hwnd: int, _: Any) -> bool:
        with contextlib.suppress(Exception):
            if hwnd == main or window_pid(hwnd) != pid:
                return True
            if not (win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd)):
                return True
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd).strip()
            if cls == DIALOG_CLASS or (not main_enabled and title):
                found.append({"title": title, "buttons": _buttons(hwnd), "window_class": cls})
        return True

    with contextlib.suppress(Exception):
        win32gui.EnumWindows(visit, None)
    return found


def describe_blockers(main: int | None) -> str:
    """' AutoCAD shows dialog "Block - Changes Not Saved" (buttons: Save, Discard). ...' or ''."""
    if not main:
        return ""
    try:
        dialogs = blocking_dialogs(main)
    except Exception:  # noqa: BLE001 - only ever an extra hint
        return ""
    if not dialogs:
        return ""
    parts = []
    for d in dialogs[:3]:
        text = f"\"{d['title']}\"" if d["title"] else "(untitled)"
        if d["buttons"]:
            text += f" (buttons: {', '.join(d['buttons'])})"
        parts.append(text)
    return (f" AutoCAD shows the dialog {'; '.join(parts)}. It blocks every call until it is answered; "
            "ask the user to answer it (cancel_command cannot close dialogs).")
