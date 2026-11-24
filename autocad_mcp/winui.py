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


# ---------- health: crash reports, a hung AutoCAD, other autocad-mcp servers (GAP-017 c) ----------

# Window titles of AutoCAD's fatal-error box ("AutoCAD Error Aborting", text "FATAL ERROR: ...") and of
# the Autodesk crash reporter, which runs as its own process (senddmp.exe), so blocking_dialogs, which
# only looks at acad.exe's windows, never saw it. Lower case, matched as parts of the title (inferred
# from Autodesk support articles; not yet seen live through this server).
CRASH_TITLES = ("fatal error", "error aborting", "error report", "crash report")
CRASH_PROCESSES = ("senddmp.exe", "adskerrorreporting.exe", "cer.exe")


def process_image(pid: int) -> str:
    """File name of a process's program, lower case ('acad.exe'), or '' if it cannot be read."""
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(handle)


def crash_dialogs() -> list[dict]:
    """Visible top-level windows of any process that look like an AutoCAD fatal error or the
    Autodesk crash reporter: [{title, program}]."""
    found: list[dict] = []

    def visit(hwnd: int, _: Any) -> bool:
        with contextlib.suppress(Exception):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd).strip()
            pid = window_pid(hwnd)
            program = process_image(pid) if pid else ""
            if (title and any(t in title.lower() for t in CRASH_TITLES)) or program in CRASH_PROCESSES:
                found.append({"title": title, "program": program})
        return True

    with contextlib.suppress(Exception):
        win32gui.EnumWindows(visit, None)
    return found


def is_hung(hwnd: int | None) -> bool:
    """True if Windows considers the window not responding (no messages handled for about 5 s)."""
    if not hwnd:
        return False
    try:
        return bool(ctypes.windll.user32.IsHungAppWindow(wintypes.HWND(hwnd)))
    except Exception:  # noqa: BLE001
        return False


def describe_crash() -> str:
    """' Windows shows "AutoCAD Error Aborting" (acad.exe): AutoCAD has probably crashed ...' or ''."""
    try:
        dialogs = crash_dialogs()
    except Exception:  # noqa: BLE001 - only ever an extra hint
        return ""
    if not dialogs:
        return ""
    names = "; ".join(f"\"{d['title'] or '(untitled)'}\"" + (f" ({d['program']})" if d["program"] else "")
                      for d in dialogs[:3])
    return (f" Windows shows {names}: AutoCAD has probably crashed or is writing a crash report. Do not "
            "retry; tell the user (unsaved work may need recovery when AutoCAD restarts).")
