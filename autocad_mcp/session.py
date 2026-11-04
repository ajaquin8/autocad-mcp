"""Connection to the running AutoCAD plus the edit and busy guards.

Edit guard: a drawing may only be changed if this server created it during the
current session, or if it was explicitly unlocked with allow_edit_document
(which the model should only call after the user asked for that drawing to be
changed). Everything in here runs on the COM worker thread.
"""

from __future__ import annotations

import contextlib
import os
import re
import time
import winreg
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

import pythoncom
import pywintypes
import win32com.client
import win32com.client.dynamic

from .com import RPC_BUSY_CODES, RPC_GONE_CODES, AcadError, enums

T = TypeVar("T")

# settle(): a new drawing counts as ready once it answers this many calls in a row, this far apart.
# Add-ins that load into every new drawing made AutoCAD reject calls for several seconds after the
# drawing first answered (verified 2026-11-04).
SETTLE_CALLS = 3
SETTLE_PAUSE = 0.5
SETTLE_TIMEOUT = 45.0


def is_busy_error(err: BaseException) -> bool:
    """A call AutoCAD rejected because it was busy (as a COM error, or as pywin32's failed lookup)."""
    if isinstance(err, pywintypes.com_error):
        return bool(err.args) and err.args[0] in RPC_BUSY_CODES
    return isinstance(err, AttributeError) and str(err).startswith("<unknown>.")

# Each AutoCAD release registers AutoCAD.Application.<release> (2027 is .26, 2026 is
# .25.1, 2025 is .25, 2024 is .24.3 ...); the unversioned name is the last resort (it
# names whichever AutoCAD registered last). DWG TrueView registers the same names: on a
# PC with AutoCAD 2026 and DWG TrueView 2027, AutoCAD.Application.26 is TrueView. So a
# running match is skipped if it is TrueView, and AutoCAD is only launched from a
# ProgID whose registered program is acad.exe.
PROGID = "AutoCAD.Application"

# Application.Version starts with the release number ("25.1s (LMS Tech)"), not the product year,
# and Claude has guessed the year wrong from it (25.1 read as 2025). Autodesk's release numbers:
RELEASE_YEARS = {
    "19.0": 2013, "19.1": 2014, "20.0": 2015, "20.1": 2016, "21.0": 2017, "22.0": 2018, "23.0": 2019,
    "23.1": 2020, "24.0": 2021, "24.1": 2022, "24.2": 2023, "24.3": 2024, "25.0": 2025, "25.1": 2026,
    "26.0": 2027,
}

INSUNITS = {0: "unitless", 1: "inches", 2: "feet", 3: "miles", 4: "millimeters", 5: "centimeters",
            6: "meters", 7: "kilometers", 8: "microinches", 9: "mils", 10: "yards", 11: "angstroms",
            12: "nanometers", 13: "microns", 14: "decimeters", 15: "dekameters", 16: "hectometers",
            17: "gigameters", 18: "astronomical units", 19: "light years", 20: "parsecs",
            21: "US survey feet"}


def product_name(version: str) -> str:
    """'AutoCAD 2026' from an Application.Version such as '25.1s (LMS Tech)'."""
    match = re.match(r"(\d+)\.(\d+)", version.strip())
    if not match:
        return f"AutoCAD (version {version})"
    release = f"{int(match[1])}.{int(match[2])}"
    year = RELEASE_YEARS.get(release)
    return f"AutoCAD {year}" if year else f"AutoCAD release {release} (newer or older than this server knows)"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _late_bound(dispatch: Any) -> Any:
    """Always a late-bound (dynamic) proxy. With a makepy cache, pywin32 would wrap
    objects in the class of their *declared* type (IAcadEntity), which hides the
    members of the real class (a line's StartPoint). Dynamic dispatch reads the
    object's own type info instead, and everything it returns stays dynamic."""
    return win32com.client.dynamic.Dispatch(dispatch)


def _is_trueview(app: Any) -> bool:
    """DWG TrueView answers to the AutoCAD ProgIDs but cannot be drawn in."""
    with contextlib.suppress(pywintypes.com_error, AttributeError):
        if os.path.basename(str(app.FullName)).lower() == "dwgviewr.exe":
            return True
    with contextlib.suppress(pywintypes.com_error, AttributeError):
        return "trueview" in str(app.Name).lower()
    return False


def _registered_progids() -> list[str]:
    """Every AutoCAD.Application.* name in the registry (about 0.05 s to scan)."""
    names, i = [], 0
    while True:
        try:
            name = winreg.EnumKey(winreg.HKEY_CLASSES_ROOT, i)
        except OSError:
            return names
        i += 1
        if name.lower().startswith(PROGID.lower() + "."):
            names.append(name)


def progids() -> list[str]:
    """The versioned AutoCAD ProgIDs on this PC, newest release first, then the unversioned one."""
    def release(name: str) -> tuple[int, ...] | None:
        parts = name[len(PROGID) + 1:].split(".")
        return tuple(map(int, parts)) if all(p.isdigit() for p in parts) else None

    versioned = [(r, n) for n in _registered_progids() if (r := release(n)) is not None]
    return [n for _, n in sorted(versioned, reverse=True)] + [PROGID]


def _server_exe(progid: str) -> str:
    """The command line COM would run to start this ProgID ('' if it is not registered)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID") as key:
            clsid = winreg.QueryValue(key, None)
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32") as key:
            return winreg.QueryValue(key, None)
    except OSError:
        return ""


def _launch_progid(candidates: list[str]) -> str | None:
    """The first ProgID that starts AutoCAD itself (acad.exe), not TrueView."""
    return next((p for p in candidates if "\\acad.exe" in _server_exe(p).lower()), None)


def doc_key(doc: Any) -> str:
    """Identity of an open drawing for the edit guard: its full path, or its name
    while it has never been saved (AutoCAD keeps open drawing names unique)."""
    full = str(doc.FullName or "")
    return os.path.normcase(full) if full else "unsaved:" + str(doc.Name).lower()


class Edit:
    """What one tool changed, so a failure can put it back."""

    def __init__(self, doc: Any) -> None:
        self.doc = doc
        self.created: list[Any] = []
        self.undo_actions: list[Callable[[], None]] = []

    def add(self, obj: Any) -> Any:
        """Record an object the tool created; it is deleted again if the tool fails.
        Recording the same object twice is harmless."""
        if not any(o is obj for o in self.created):
            self.created.append(obj)
        return obj

    def on_rollback(self, action: Callable[[], None]) -> None:
        """Record how to undo a change to an existing object (run in reverse order on failure)."""
        self.undo_actions.append(action)

    def rollback(self) -> list[str]:
        problems = []
        for action in reversed(self.undo_actions):
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - reported, never raised
                problems.append(f"restore failed: {exc}")
        for obj in reversed(self.created):
            try:
                obj.Delete()
            except Exception as exc:  # noqa: BLE001
                problems.append(f"could not delete a created object: {exc}")
        return problems


class Session:
    def __init__(self) -> None:
        self._app: Any = None
        self.owned: set[str] = set()
        self.unlocked: set[str] = set()
        self.allow_all_edits = _env_flag("AUTOCAD_MCP_ALLOW_ALL_EDITS")
        self.hwnd: int | None = None  # AutoCAD's main window, for cancel_command (which uses no COM)

    # ---------- connection ----------

    @property
    def app(self) -> Any:
        if self._app is not None:
            try:
                _ = self._app.Name
                return self._app
            except pywintypes.com_error as err:
                if err.args and err.args[0] in RPC_GONE_CODES:
                    self._app = None
                else:
                    raise
        return self.connect(start=False)

    def connect(self, start: bool = False) -> Any:
        app = None
        trueview_running = False
        candidates = progids()
        for progid in candidates:
            try:
                unknown = pythoncom.GetActiveObject(pywintypes.IID(progid))
                candidate = _late_bound(unknown.QueryInterface(pythoncom.IID_IDispatch))
            except pywintypes.com_error:
                continue
            if _is_trueview(candidate):
                trueview_running = True
                continue
            app = candidate
            break
        if app is None:
            if not start:
                note = " (DWG TrueView is open, but it is a viewer and cannot be drawn in)" if trueview_running else ""
                raise AcadError(
                    f"AutoCAD is not running{note}. Ask the user to start it, or call "
                    "acad_status(start_if_needed=True) to launch it.") from None
            progid = _launch_progid(candidates)
            if progid is None:
                raise AcadError("Found no installed AutoCAD to start (checked " + ", ".join(candidates) + ").")
            app = _late_bound(progid)
            app.Visible = True
        self._app = app
        with contextlib.suppress(pywintypes.com_error, AttributeError, TypeError, ValueError):
            self.hwnd = int(app.HWND)
        enums.load(app)
        return app

    @property
    def connected(self) -> bool:
        return self._app is not None

    # ---------- documents ----------

    def documents(self) -> list[Any]:
        docs = self.app.Documents
        return [docs.Item(i) for i in range(docs.Count)]

    def find_document(self, name: str) -> Any:
        """Find an open drawing by name, file name or full path. Also used to re-fetch the
        drawing that Documents.Add/Open returned: that proxy failed to resolve ReadOnly
        on AutoCAD 2027 (verified 2026-10-29), while the one from Documents.Item works."""
        wanted = name.strip().lower()
        for doc in self.documents():
            full = str(doc.FullName or "").lower()
            if wanted in (str(doc.Name).lower(), full, os.path.basename(full)):
                return doc
        raise AcadError(f"No open drawing named '{name}'. Use list_documents to see what is open.")

    def settle(self, fetch: Callable[[], T], what: str) -> T:
        """Call fetch() until it succeeds SETTLE_CALLS times in a row, and return its last result.
        Busy rejections start the count again; any other error is raised at once."""
        deadline = time.monotonic() + SETTLE_TIMEOUT
        ok, result = 0, None
        while True:
            try:
                result = fetch()
                ok += 1
                if ok >= SETTLE_CALLS:
                    return result
            except (pywintypes.com_error, AttributeError) as err:
                if not is_busy_error(err):
                    raise
                ok = 0
                if time.monotonic() > deadline:
                    raise AcadError(f"AutoCAD stayed busy for {SETTLE_TIMEOUT:.0f}s after {what}. Check "
                                    "acad_status before trying again.") from None
            time.sleep(SETTLE_PAUSE)

    def document(self, name: str = "") -> Any:
        if name:
            return self.find_document(name)
        if self.app.Documents.Count == 0:
            raise AcadError("No drawing is open in AutoCAD (only the Start tab).")
        return self.app.ActiveDocument

    # ---------- edit guard ----------

    def is_editable(self, doc: Any) -> bool:
        key = doc_key(doc)
        return self.allow_all_edits or key in self.owned or key in self.unlocked

    def require_editable(self, doc: Any) -> None:
        if not self.is_editable(doc):
            raise AcadError(
                f"'{doc.Name}' is locked: this server did not create it. Do not change existing "
                "user drawings unless the user explicitly asked for this one; if they did, call "
                "allow_edit_document first.")
        if bool(doc.ReadOnly):
            raise AcadError(f"'{doc.Name}' is open read-only.")

    def require_idle(self, doc: Any = None) -> None:
        """Refuse to act while the user is in the middle of a command, prompt or dialog.
        CMDACTIVE is 0 only when no command, script or dialog is running."""
        doc = doc if doc is not None else self.document()
        # If AutoCAD is too busy to answer, this call is rejected and describe_com_error says so.
        active = int(doc.GetVariable("CMDACTIVE"))
        if active:
            raise AcadError(
                f"The user is busy in AutoCAD (CMDACTIVE={active}: a command, script or dialog is "
                "active). Ask them to finish or press Esc, then retry. Never edit while a user "
                "command is running.")
        try:
            quiescent = bool(self.app.GetAcadState().IsQuiescent)
        except Exception:  # noqa: BLE001 - optional second opinion
            quiescent = True
        if not quiescent:
            raise AcadError("AutoCAD is not idle (it reports a command or operation in progress). "
                            "Ask the user to finish it, then retry.")

    def mark_owned(self, doc: Any) -> None:
        self.owned.add(doc_key(doc))

    def rekey(self, old_key: str, doc: Any) -> None:
        """A drawing was saved under a new path: keep its edit permission."""
        new_key = doc_key(doc)
        for keys in (self.owned, self.unlocked):
            if old_key in keys:
                keys.discard(old_key)
                keys.add(new_key)

    def forget(self, key: str) -> None:
        self.owned.discard(key)
        self.unlocked.discard(key)

    @contextlib.contextmanager
    def edit(self, doc: Any = None) -> Iterator[Edit]:
        """Guarded edit of a drawing, grouped as one undo step (UNDO Begin/End marks).
        On any exception the objects this edit created are deleted and recorded
        changes restored, so a failed tool leaves nothing half-done behind."""
        doc = doc if doc is not None else self.document()
        self.require_editable(doc)
        self.require_idle(doc)
        change = Edit(doc)
        doc.StartUndoMark()
        try:
            yield change
        except BaseException as err:
            problems = change.rollback()
            with contextlib.suppress(pywintypes.com_error):
                doc.EndUndoMark()
            if problems:
                raise AcadError(f"{err} (rollback was incomplete: {'; '.join(problems)})") from err
            raise
        else:
            doc.EndUndoMark()

    def describe(self, doc: Any) -> dict:
        return {
            "name": str(doc.Name),
            "path": str(doc.FullName) or None,
            "unsaved_changes": not bool(doc.Saved),
            "read_only": bool(doc.ReadOnly),
            "editable": self.is_editable(doc),
            "created_by_mcp": doc_key(doc) in self.owned,
        }

    def units(self, doc: Any) -> str:
        return INSUNITS.get(int(doc.GetVariable("INSUNITS")), "unknown")


session = Session()
