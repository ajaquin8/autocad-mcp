"""COM plumbing: a single STA worker thread that owns every AutoCAD COM call.

MCP tool handlers run on arbitrary threads. COM objects obtained in one
apartment must not be used from another, so every piece of AutoCAD work is
shipped to one dedicated thread and executed there in full.
"""

from __future__ import annotations

import json
import math
import os
import queue
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any, TypeVar

import pythoncom
import pywintypes
import win32com.client

T = TypeVar("T")

RPC_BUSY_CODES = {
    -2147418111,  # RPC_E_CALL_REJECTED
    -2147417846,  # RPC_E_SERVERCALL_RETRYLATER
}
RPC_GONE_CODES = {
    -2147023174,  # RPC_S_SERVER_UNAVAILABLE
    -2147023170,  # RPC_S_CALL_FAILED
    -2147417848,  # RPC_E_DISCONNECTED
    -2147221021,  # MK_E_UNAVAILABLE (GetActiveObject: not running)
}


class AcadError(Exception):
    """An error with a message meant for the model/user (no traceback needed)."""


class AcadTimeout(AcadError):
    pass


# ---------- coordinates and angles ----------


def rad(degrees: float) -> float:
    return math.radians(float(degrees))


def deg(radians: float) -> float:
    return math.degrees(float(radians))


def xyz(value: Sequence[float]) -> tuple[float, float, float]:
    """[x, y] or [x, y, z] in drawing units -> (x, y, z)."""
    if isinstance(value, str) or not isinstance(value, Sequence) or len(value) not in (2, 3):
        raise ValueError(f"A point is [x, y] or [x, y, z], got {value!r}.")
    x, y, *rest = (float(v) for v in value)
    return x, y, (rest[0] if rest else 0.0)


def doubles(values: Sequence[float]) -> Any:
    """A VARIANT array of doubles, the type AutoCAD expects for points and coordinate lists."""
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])


def point(value: Sequence[float]) -> Any:
    return doubles(xyz(value))


def rounded(values: Sequence[float], places: int = 6) -> list[float]:
    return [round(float(v), places) for v in values]


# ---------- errors ----------


BUSY_MESSAGE = ("AutoCAD is busy and rejected the call (a command, dialog or prompt is probably "
                "open). Ask the user to finish it or press Esc, then retry.")


def describe_attribute_error(err: AttributeError) -> str:
    """pywin32's late binding looks each member up by name, and AutoCAD rejects that lookup
    while the user is in a command or dialog; pywin32 then raises AttributeError('<unknown>.Count')
    instead of a COM error (verified live 2026-11-03, inside LINE and with OPTIONS open)."""
    if str(err).startswith("<unknown>."):
        return f"{BUSY_MESSAGE} (AutoCAD did not answer the lookup of {str(err)[len('<unknown>.'):]})"
    return f"AttributeError: {err}"


def describe_com_error(err: pywintypes.com_error) -> str:
    hresult = err.args[0] if err.args else None
    detail = ""
    if len(err.args) > 2 and err.args[2]:
        excepinfo = err.args[2]
        detail = excepinfo[2] or ""
        if excepinfo[5]:
            scode = excepinfo[5] & 0xFFFFFFFF
            known = {0x80070057: "invalid argument", 0x80004005: "operation failed",
                     0x80004001: "not implemented", 0x8000FFFF: "unexpected failure"}
            detail = (detail + " " if detail else "") + f"(0x{scode:08X} {known.get(scode, '')})".replace(" )", ")")
    if hresult in RPC_BUSY_CODES:
        return BUSY_MESSAGE
    if hresult in RPC_GONE_CODES:
        return "Lost the connection to AutoCAD (was it closed?). Call acad_status to reconnect."
    msg = err.args[1] if len(err.args) > 1 else str(err)
    return f"AutoCAD COM error 0x{(hresult or 0) & 0xFFFFFFFF:08X}: {msg}{(' - ' + detail) if detail else ''}"


# ---------- the STA worker ----------


class ComWorker:
    """Runs callables on one STA thread, one at a time, in submission order."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[Callable[[], Any], Future]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.busy_with: str | None = None

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="autocad-sta", daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        while True:
            fn, fut = self._queue.get()
            if not fut.set_running_or_notify_cancel():
                continue
            self.busy_with = getattr(fn, "__name__", "call")
            try:
                fut.set_result(fn())
            except BaseException as exc:  # noqa: BLE001 - surfaced to caller
                fut.set_exception(exc)
            finally:
                self.busy_with = None

    def call(self, fn: Callable[[], T], timeout: float = 180.0) -> T:
        self._ensure_started()
        if threading.current_thread() is self._thread:
            return fn()
        fut: Future = Future()
        self._queue.put((fn, fut))
        try:
            return fut.result(timeout=timeout)
        except FutureTimeout:
            raise AcadTimeout(
                f"No answer from AutoCAD after {timeout:.0f}s. The operation may still be "
                "running inside AutoCAD; do NOT repeat it. Check acad_status first.") from None


worker = ComWorker()


class Enums:
    """Every enum constant in AutoCAD's own type library, by name (acRed, acAttachmentPointTopLeft...).

    Read once from the running AutoCAD (so values always match the installed
    version) and cached per version under %LOCALAPPDATA%/autocad-mcp.
    """

    def __init__(self) -> None:
        self._values: dict[str, int] | None = None

    def load(self, app: Any) -> None:
        if self._values is not None:
            return
        version = "".join(c if c.isalnum() or c in ".-" else "_" for c in str(app.Version))
        cache = Path(os.environ.get("LOCALAPPDATA", ".")) / "autocad-mcp" / f"enums-{version}.json"
        if cache.exists():
            self._values = json.loads(cache.read_text(encoding="utf-8"))
            return
        typelib, _ = app._oleobj_.GetTypeInfo().GetContainingTypeLib()
        values: dict[str, int] = {}
        for i in range(typelib.GetTypeInfoCount()):
            if typelib.GetTypeInfoType(i) != pythoncom.TKIND_ENUM:
                continue
            info = typelib.GetTypeInfo(i)
            for j in range(info.GetTypeAttr().cVars):
                var = info.GetVarDesc(j)
                values[info.GetNames(var.memid)[0]] = int(var.value)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(values), encoding="utf-8")
        self._values = values

    def __getattr__(self, name: str) -> int:
        if name.startswith("_"):
            raise AttributeError(name)
        if self._values is None:
            raise AcadError("AutoCAD enums not loaded yet (not connected).")
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(f"Unknown AutoCAD enum constant {name}") from None


enums = Enums()
