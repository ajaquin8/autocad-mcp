"""COM plumbing: a single STA worker thread that owns every AutoCAD COM call.

MCP tool handlers run on arbitrary threads. COM objects obtained in one
apartment must not be used from another, so every piece of AutoCAD work is
shipped to one dedicated thread and executed there in full.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import math
import os
import queue
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from ctypes import wintypes
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


class AcadStuck(AcadTimeout):
    """Refused at once: an earlier call timed out and is still running on the COM thread."""


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


def objects(items: Sequence[Any]) -> Any:
    """A VARIANT array of COM objects, the type CopyObjects expects for its Objects argument."""
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                                   [getattr(o, "_oleobj_", o) for o in items])


def rounded(values: Sequence[float], places: int = 6) -> list[float]:
    return [round(float(v), places) for v in values]


# ---------- errors ----------


BUSY_MESSAGE = ("AutoCAD is busy and rejected the call (a command, dialog or prompt is probably "
                "open; the server already waited a few seconds). Ask the user to finish it or press Esc, "
                "then retry.")


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


# ---------- retrying calls AutoCAD rejects ----------

# IMessageFilter (objidl.h). pywin32 cannot implement it, so the filter is a tiny COM object built
# with ctypes. COM asks the calling thread's filter what to do when a call is rejected; AutoCAD
# answers "retry later" while it is opening a drawing, loading an add-in or just closing a dialog.
SERVERCALL_RETRYLATER = 2
PENDINGMSG_WAITDEFPROCESS = 2
RETRY_PAUSE_MS = 250
_CANCEL = 0xFFFFFFFF  # -1 as a DWORD: give up, the caller gets RPC_E_CALL_REJECTED
_IID_IUNKNOWN = uuid.UUID("00000000-0000-0000-C000-000000000046").bytes_le
_IID_IMESSAGEFILTER = uuid.UUID("00000016-0000-0000-C000-000000000046").bytes_le
_S_OK, _E_NOINTERFACE = 0, 0x80004002 - 0x100000000

_QI = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_REF = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
_INCOMING = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.c_void_p)
_RETRY = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD)
_PENDING = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD)


class _Vtbl(ctypes.Structure):
    _fields_ = [("QueryInterface", _QI), ("AddRef", _REF), ("Release", _REF),
                ("HandleInComingCall", _INCOMING), ("RetryRejectedCall", _RETRY), ("MessagePending", _PENDING)]


class _Obj(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.POINTER(_Vtbl))]


_REGISTERED: list[MessageFilter] = []  # filters handed to COM; never freed while the process runs


# Status polls (acad_status, the checks run_command makes after a command) give up after this long
# instead of the full retry time: while a command waits for input AutoCAD rejects every call, and a
# poll that waits 8 s per call only makes a stuck command look like a hung server.
QUICK_RETRY_SECONDS = 1.0


def retry_seconds() -> float:
    """How long a rejected call is retried (AUTOCAD_MCP_BUSY_RETRY_SECONDS, default 8, 0 = never)."""
    try:
        return max(0.0, float(os.environ.get("AUTOCAD_MCP_BUSY_RETRY_SECONDS", "8")))
    except ValueError:
        return 8.0


class MessageFilter:
    """Retries a call AutoCAD rejected with "retry later", for a limited time.

    A rejected call never ran, so retrying it cannot repeat any work. A call AutoCAD
    refuses outright, or one still rejected after the limit, fails as before, so the
    busy guard (Session.require_idle) still refuses edits while the user is busy.
    The object lives as long as the worker thread; AddRef/Release are no-ops.
    """

    def __init__(self, seconds: float) -> None:
        self.limit_ms = int(seconds * 1000)
        self.retries = 0
        self.rejections: dict[int, int] = {}  # reject type -> times COM asked (1 = refused, 2 = retry later)
        self._vtbl = _Vtbl(_QI(self._query_interface), _REF(lambda this: 1), _REF(lambda this: 1),
                           _INCOMING(lambda this, kind, caller, ticks, info: 0),  # SERVERCALL_ISHANDLED
                           _RETRY(self._retry_rejected_call),
                           _PENDING(lambda this, callee, ticks, kind: PENDINGMSG_WAITDEFPROCESS))
        self._obj = _Obj(ctypes.pointer(self._vtbl))

    @property
    def address(self) -> int:
        return ctypes.addressof(self._obj)

    def delay(self, ticks: int, reject_type: int) -> int:
        """Milliseconds to wait before retrying, or _CANCEL to give up."""
        self.rejections[reject_type] = self.rejections.get(reject_type, 0) + 1
        if reject_type != SERVERCALL_RETRYLATER or ticks >= self.limit_ms:
            return _CANCEL
        self.retries += 1
        return RETRY_PAUSE_MS

    def _retry_rejected_call(self, this: int, callee: int, ticks: int, reject_type: int) -> int:
        return self.delay(ticks, reject_type)

    def _query_interface(self, this: int, riid: int, ppv: Any) -> int:
        if ctypes.string_at(riid, 16) in (_IID_IUNKNOWN, _IID_IMESSAGEFILTER):
            ppv[0] = this
            return _S_OK
        ppv[0] = None
        return _E_NOINTERFACE

    def register(self) -> None:
        """Install as the current (STA) thread's filter. COM keeps only a raw pointer, so the
        filter is also kept alive here; one that Python freed crashed the process (2026-11-04)."""
        previous = ctypes.c_void_p()
        hr = ctypes.windll.ole32.CoRegisterMessageFilter(ctypes.c_void_p(self.address), ctypes.byref(previous))
        if hr != _S_OK:
            raise OSError(f"CoRegisterMessageFilter failed (0x{hr & 0xFFFFFFFF:08X})")
        _REGISTERED.append(self)

    @staticmethod
    def unregister() -> None:
        ctypes.windll.ole32.CoRegisterMessageFilter(None, ctypes.byref(ctypes.c_void_p()))


# ---------- one AutoCAD client at a time, across processes ----------

# Inside one server every COM call already runs on one thread. Several server processes (two AI
# clients, or a Claude desktop extension next to a Hermes profile) still reached the same AutoCAD at
# the same time, and parallel COM clients are the suspected cause of AutoCAD's layout tabs crashing
# (GAP-017, user-reported 2026-11-23). A named Win32 mutex makes the servers on this Windows login
# take turns: each tool call holds it from start to end.
LOCK_NAME = "Local\\autocad-mcp-com"
LOCK_HOLDER = Path(os.environ.get("LOCALAPPDATA", ".")) / "autocad-mcp" / "com-lock.json"
_WAIT_OBJECT_0, _WAIT_ABANDONED, _WAIT_TIMEOUT = 0x0, 0x80, 0x102
_LOCK_POLL_MS = 100


def lock_wait_seconds() -> float:
    """How long a call waits for another server to finish (AUTOCAD_MCP_LOCK_WAIT_SECONDS, default 30)."""
    try:
        return max(0.0, float(os.environ.get("AUTOCAD_MCP_LOCK_WAIT_SECONDS", "30")))
    except ValueError:
        return 30.0


def lock_enabled() -> bool:
    """AUTOCAD_MCP_CROSS_PROCESS_LOCK=0 switches the lock off (escape hatch; default on)."""
    return os.environ.get("AUTOCAD_MCP_CROSS_PROCESS_LOCK", "1").strip().lower() not in ("0", "false", "no", "off")


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON through a temporary file and a rename, so a reader in another process never sees
    half a file. Raises OSError if the rename keeps failing (a reader holding the file open)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                with contextlib.suppress(OSError):
                    tmp.unlink()
                raise
            time.sleep(0.02)


class CrossProcessLock:
    """A named Win32 mutex shared by every autocad-mcp server on this Windows login.

    A Win32 mutex belongs to the thread that took it, so take and release it on the same thread
    (the STA worker). It is recursive. If the holder died while holding it, Windows hands it to the
    next waiter (WAIT_ABANDONED); that counts as taken, and `abandoned` says so.
    """

    def __init__(self, name: str | None = None, holder_file: Path | None = None) -> None:
        self.name = name
        self.holder_file = holder_file
        self._handle: int | None = None
        self.abandoned = 0  # times the lock was taken over from a server that died holding it

    def _resolved_name(self) -> str:
        return self.name or os.environ.get("AUTOCAD_MCP_LOCK_NAME") or LOCK_NAME

    def _mutex(self) -> int:
        if self._handle is None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            handle = kernel32.CreateMutexW(None, False, self._resolved_name())
            if not handle:
                raise OSError(f"CreateMutexW failed (error {ctypes.get_last_error()})")
            self._handle = handle
            return handle
        return self._handle

    def holder(self) -> dict:
        """The last recorded holder ({pid, tool, since}), or {} if unknown."""
        try:
            data = json.loads((self.holder_file or LOCK_HOLDER).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def acquire(self, tool: str, wait_seconds: float) -> None:
        """Take the lock, waiting up to `wait_seconds` for another server; AcadError if it never frees."""
        handle = self._mutex()
        kernel32 = ctypes.windll.kernel32
        deadline = time.monotonic() + wait_seconds
        while True:
            result = kernel32.WaitForSingleObject(wintypes.HANDLE(handle), _LOCK_POLL_MS)
            if result in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
                if result == _WAIT_ABANDONED:
                    self.abandoned += 1
                with contextlib.suppress(OSError):
                    write_json_atomic(self.holder_file or LOCK_HOLDER, {
                        "pid": os.getpid(), "tool": tool, "since": time.strftime("%Y-%m-%dT%H:%M:%S")})
                return
            if result != _WAIT_TIMEOUT:
                raise OSError(f"WaitForSingleObject failed (0x{result & 0xFFFFFFFF:08X})")
            if time.monotonic() >= deadline:
                raise AcadError(self.busy_message(wait_seconds))
            with contextlib.suppress(Exception):
                pythoncom.PumpWaitingMessages()  # an STA thread should keep its messages moving

    def release(self) -> None:
        if self._handle is not None:
            ctypes.windll.kernel32.ReleaseMutex(wintypes.HANDLE(self._handle))

    def busy_message(self, waited: float) -> str:
        h = self.holder()
        who = "another autocad-mcp server"
        if h.get("pid") and h.get("pid") != os.getpid():
            who += f" (process {h['pid']}, running {h.get('tool', '?')} since {h.get('since', '?')})"
        return (f"AutoCAD is in use by {who}; waited {waited:g}s for it to finish. Only one AI client "
                "should drive AutoCAD at a time (parallel COM clients can crash AutoCAD's layout tabs). "
                "Retry when the other client is done, or close it. Nothing was sent to AutoCAD.")


# ---------- the STA worker ----------


class ComWorker:
    """Runs callables on one STA thread, one at a time, in submission order.

    Each call also holds the cross-process lock, so servers in other processes wait their turn.

    A call that timed out or that the client cancelled before it started is dropped from the
    queue, so it can no longer run minutes later. One that had already started cannot be
    stopped (COM has no way to interrupt AutoCAD); while it is still running, new calls fail at
    once instead of queueing behind it (GAP-017 slice b).
    """

    def __init__(self, cross_process_lock: CrossProcessLock | None = None) -> None:
        self._queue: queue.Queue[tuple[Callable[[], Any], Future, float]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.busy_with: str | None = None
        self.busy_since: float | None = None
        self.message_filter: MessageFilter | None = None
        self.cross_process_lock = cross_process_lock or CrossProcessLock()
        self._stuck: Future | None = None  # a call that timed out after it had started
        self._stuck_tool = ""
        self.dropped = 0  # queued calls never run because they timed out or were cancelled first

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="autocad-sta", daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        seconds = retry_seconds()
        if seconds > 0:
            try:
                self.message_filter = MessageFilter(seconds)
                self.message_filter.register()
            except OSError:  # without it, a busy AutoCAD fails at once, as before
                self.message_filter = None
        while True:
            fn, fut, deadline = self._queue.get()
            if time.monotonic() >= deadline:
                fut.cancel()  # its caller already gave up: never start it late
            if not fut.set_running_or_notify_cancel():
                self.dropped += 1
                continue
            tool = str(getattr(fn, "__name__", "call"))
            self.busy_with = tool
            self.busy_since = time.monotonic()
            locked = False
            try:
                if lock_enabled():
                    try:
                        wait = min(lock_wait_seconds(), max(0.0, deadline - time.monotonic()))
                        self.cross_process_lock.acquire(tool, wait)
                        locked = True
                    except OSError:  # Windows refused the mutex itself: run as before, unlocked
                        locked = False
                fut.set_result(fn())
            except BaseException as exc:  # noqa: BLE001 - surfaced to caller
                fut.set_exception(exc)
            finally:
                if locked:
                    self.cross_process_lock.release()
                self.busy_with = None
                self.busy_since = None

    @contextlib.contextmanager
    def quick_retries(self, seconds: float = QUICK_RETRY_SECONDS) -> Iterator[None]:
        """Retry rejected calls for at most `seconds` inside this block (on the worker thread)."""
        f = self.message_filter
        if f is None:
            yield
            return
        previous = f.limit_ms
        f.limit_ms = min(previous, int(seconds * 1000))
        try:
            yield
        finally:
            f.limit_ms = previous

    def submit(self, fn: Callable[[], T], timeout: float = 180.0) -> Future:
        """Queue `fn` for the worker thread. It is dropped instead of run if it has not started
        within `timeout` seconds. AcadStuck if an earlier call timed out and is still running."""
        self._ensure_started()
        stuck = self._stuck
        if stuck is not None:
            if not stuck.done():
                raise AcadStuck(self.stuck_message())
            self._stuck = None
        fut: Future = Future()
        self._queue.put((fn, fut, time.monotonic() + timeout))
        return fut

    def wait(self, fut: Future, timeout: float = 180.0) -> Any:
        """The result of a submitted call. On timeout the call is dropped if it never started;
        if it had started, it is remembered as stuck so new calls fail fast until it ends."""
        try:
            return fut.result(timeout=timeout)
        except FutureTimeout:
            if fut.cancel():
                raise AcadTimeout(
                    f"AutoCAD did not get to this call within {timeout:.0f}s (an earlier call or another "
                    "autocad-mcp server kept it busy), so it was dropped. Nothing was sent to AutoCAD; "
                    "check acad_status, then retry.") from None
            if fut.done():  # it finished just now
                return fut.result()
            self._stuck, self._stuck_tool = fut, self.busy_with or "call"
            raise AcadTimeout(
                f"No answer from AutoCAD after {timeout:.0f}s. The operation may still be "
                "running inside AutoCAD; do NOT repeat it. Check acad_status first.") from None

    def stuck_message(self) -> str:
        since = self.busy_since
        running = f" for {time.monotonic() - since:.0f}s" if since is not None else ""
        return (f"An earlier call ({self._stuck_tool}) timed out and is still running inside AutoCAD{running}. "
                "Nothing was sent to AutoCAD. Ask the user to look at AutoCAD (a dialog, a prompt, or a long "
                "operation); retry once it has finished. Do NOT repeat the earlier call.")

    def call(self, fn: Callable[[], T], timeout: float = 180.0) -> T:
        self._ensure_started()
        if threading.current_thread() is self._thread:
            return fn()
        return self.wait(self.submit(fn, timeout), timeout)


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
