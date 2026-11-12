"""Running one prompt-driven AutoCAD command with a list of answers, without ever leaving it waiting.

Why not SendCommand: on the command line a space is Enter, so names with spaces break, and a
command that runs out of answers waits for input while AutoCAD rejects every COM call, so the
server can neither answer nor cancel it (live 2026-11-06, [[Sources/2026-11-06 Stretch grips by
script]]). Instead, run_command builds ONE inline AutoLISP expression and hands it to AutoCAD's
command line through WM_COPYDATA (no COM call, no .lsp file, so no SECURELOAD prompt). The
expression:

- feeds the answers one by one with (command x), names with spaces as LISP strings, points
  converted from WCS to the current UCS;
- before each answer checks that the command is still active, and stops if it ended early;
- logs LASTPROMPT after each answer (it lags one answer: a prompt is printed only when the next
  input arrives);
- cancels with (command) if the command is still waiting at the end, and goes back to an UNDO
  mark it set first if the command ended early or had to be cancelled;
- writes that transcript to a file the server reads, so nothing needs COM while it runs.
Running object snaps are off while it runs, and CMDECHO is on so the prompts are logged.

How the expression is handed over (live 2026-11-11, AutoCAD 2027, scratch/AMCP-DIAG-20261111-*):
- AutoCAD does NOT evaluate input when the parentheses close. It sits on the command line as
  typed text, and AutoCAD rejects COM calls meanwhile, until an Enter arrives. So every message
  ends with its Enter.
- One WM_COPYDATA message carries at most 999 characters including the Enter (998 + Enter ran,
  999 + Enter did not). A longer message is dropped whole and nothing says so: this is why
  run_command never started before (the shortest expression is about 1,350 characters).
- Typing one expression across several messages is not reliable: of six tries cut between
  forms, one ran. So the expression is not typed in pieces. Each message is a complete, short
  expression of its own: the first ones store the big expression's text in a variable, piece
  by piece, and each writes an "S" line to the transcript so the server knows AutoCAD took it
  before sending the next; the last one evaluates the stored text.
- The transcript folder is under the user's home folder, not %LOCALAPPDATA%: the Microsoft Store
  build of Claude gives the server a private copy of %LOCALAPPDATA% that AutoCAD cannot see.
"""

from __future__ import annotations

import contextlib
import os
import re
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, worker, xyz
from ..session import doc_key, is_busy_error, session
from ..winui import describe_blockers, send_input, window_title
from .control import CANCEL_INPUT

# A folder both this server and AutoCAD see (see the module docstring); AMCP_RUN_DIR overrides it.
RUN_DIR = Path(os.environ.get("AMCP_RUN_DIR") or Path.home() / ".autocad-mcp" / "run")
START_WAIT = 3.0  # seconds for the expression to start (it first creates the transcript file)
MAX_MESSAGE = 900  # characters per WM_COPYDATA message; AutoCAD drops a message of 1000 or more
POLL = 0.05
MAX_INPUTS = 60
MAX_TEXT = 256

COMMAND_NAME = re.compile(r"^[_.]*-?[A-Za-z][A-Za-z0-9_-]{0,63}$")
HANDLE = re.compile(r"^[0-9A-Fa-f]{1,16}$")
OBJECT_TYPES = re.compile(r"^[A-Za-z0-9_*,]{1,200}$")

# Commands run_command refuses: they run code, change AutoCAD or its security, write or close files,
# or switch drawings. Dedicated tools save, plot and close; everything else should be asked for.
DENIED = {
    "SHELL", "SH", "START", "NETLOAD", "APPLOAD", "ARX", "LOAD", "SCRIPT", "SCRIPTCALL", "RSCRIPT",
    "QUIT", "EXIT", "NEW", "QNEW", "OPEN", "RECOVER", "PARTIALOPEN", "WBLOCK", "PLOT", "PUBLISH",
    "ETRANSMIT", "ARCHIVE", "OPTIONS", "SECURITYOPTIONS", "SETVAR", "MULTIPLE", "REDEFINE", "UNDEFINE",
    "TRUSTEDPATHS", "SECURELOAD", "LISPSYS", "PLUGINS", "DXFOUT", "PSOUT", "STLOUT", "ACISOUT", "BMPOUT",
    "JPGOUT", "PNGOUT", "TIFOUT", "WMFOUT", "MSLIDE", "ATTEXT", "DATAEXTRACTION", "LOGFILEON",
    "DWGCONVERT", "SYSVARMONITOR",
}
DENIED_PREFIXES = ("VBA", "VLISP", "VLIDE", "CUI", "MENU", "SAVE", "CLOSE", "EXPORT", "ACT", "PUBLISH")
# Commands that switch the Block Editor on or off: no UNDO mark around them (undoing across the
# editor's boundary is not something to do blind).
NO_UNDO = {"BEDIT", "BCLOSE", "BSAVE", "BSAVEAS"}

LAG_NOTE = ("LASTPROMPT lags one answer: the prompt logged after an answer is usually the one that "
            "answer replied to, or the one before; the prompt still open at the end is in 'left_waiting_at'.")


def title_shows(title: str, drawing: str) -> bool:
    """AutoCAD's window title names this drawing (anywhere: the Block Editor may add to the title;
    which drawing is active is checked over COM first, this is a second opinion before sending)."""
    return drawing.lower() in title.lower()


def bare_name(command: str) -> str:
    """'BEDIT' for '_.-BEDIT'."""
    return command.lstrip("_.").lstrip("-").upper()


def check_command(command: str) -> str:
    """The command as it is sent ('_.' added unless given), after refusing names that are not plain
    command names or are on the denied list."""
    name = command.strip()
    if not COMMAND_NAME.match(name):
        raise AcadError(f"'{command}' is not a command name (letters, digits, '-' and '_'; options go in inputs).")
    bare = bare_name(name)
    if bare in DENIED or bare.startswith(DENIED_PREFIXES):
        raise AcadError(f"run_command refuses {bare}: it runs code, changes AutoCAD's setup, writes or closes "
                        "files, or switches drawings. Use the dedicated tools (save_document, plot_pdf, "
                        "close_document, set_drawing_variables) or ask the user.")
    return name if name.startswith(("_", ".")) else "_." + name


def lisp_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lisp_number(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    text = f"{float(value):.10f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def lisp_point(value: Sequence[float]) -> str:
    """A WCS point as the current UCS point (command) expects."""
    x, y, z = xyz(value)
    return f"(trans (list {lisp_number(x)} {lisp_number(y)} {lisp_number(z)}) 0 1)"


def lisp_input(value: Any) -> str:
    """One answer to a prompt as an AutoLISP expression.

    Text is sent as typed ("" is Enter), numbers as numbers, [x, y] or [x, y, z] as a WCS point.
    {"handle": h} is that object, {"handle": h, "point": p} picks it at that point (as entsel
    would), {"last": true} is the newest object, and {"select_all": "LWPOLYLINE,DIMENSION"} is
    every object of those types in the current space (for "Select objects" / Remove).
    """
    if isinstance(value, bool):
        raise ValueError(f"An answer cannot be true/false: {value!r}. Send text such as \"Yes\".")
    if isinstance(value, str):
        if len(value) > MAX_TEXT or any(c in value for c in "\r\n\t\x03"):
            raise ValueError(f"Answer {value!r} is too long or contains a line break, tab or Ctrl+C.")
        if value.lstrip().startswith(("(", "!", "'")):
            raise ValueError(f"Answer {value!r} would run AutoLISP or a transparent command; that is refused.")
        return lisp_string(value)
    if isinstance(value, (int, float)):
        return lisp_number(value)
    if isinstance(value, (list, tuple)):
        return lisp_point(value)
    if isinstance(value, dict):
        keys = set(value)
        if keys == {"point"}:
            return lisp_point(value["point"])
        if keys in ({"handle"}, {"handle", "point"}):
            handle = str(value["handle"]).strip()
            if not HANDLE.match(handle):
                raise ValueError(f"'{handle}' is not an entity handle.")
            ent = f"(handent {lisp_string(handle.upper())})"
            return f"(list {ent} {lisp_point(value['point'])})" if "point" in keys else ent
        if keys == {"last"} and value["last"] is True:
            return "(entlast)"
        if keys == {"select_all"}:
            types = str(value["select_all"]).strip().upper()
            if not OBJECT_TYPES.match(types):
                raise ValueError(f"'{types}' is not a list of DXF object types such as LWPOLYLINE,DIMENSION.")
            return f'(ssget "_X" (list (cons 0 {lisp_string(types)})))'
    raise ValueError(f"Cannot send {value!r} as an answer: use text, a number, [x, y], or "
                     '{"handle": ...}, {"handle": ..., "point": [x, y]}, {"last": true}, {"select_all": "TYPES"}.')


SAVED_VARS = ("OSMODE", "CMDECHO", "CMDDIA", "ATTDIA")


def check_inputs(inputs: Sequence[Any]) -> list[str]:
    """Every answer as AutoLISP, refusing bad ones before AutoCAD is touched."""
    if len(inputs) > MAX_INPUTS:
        raise ValueError(f"At most {MAX_INPUTS} answers per command, got {len(inputs)}.")
    return [lisp_input(v) for v in inputs]


def build_lisp(command: str, inputs: Sequence[Any], transcript: str, undo: bool) -> str:
    """The single expression that runs the command (no trailing space or line break). It appends to
    the transcript, which the messages that carried it to AutoCAD have already started."""
    answers = check_inputs(inputs)
    names = "'(" + " ".join(lisp_string(v) for v in SAVED_VARS) + ")"
    path = lisp_string(transcript.replace("\\", "/"))
    parts = [
        "(progn",
        f"(setq amcp:f (open {path} \"a\"))",
        f"(setq amcp:sv (mapcar 'getvar {names}) amcp:olderr *error* amcp:ok T amcp:early nil amcp:act nil"
        " amcp:mark nil)",
        "(defun amcp:log (tag text) (if amcp:f (write-line (strcat tag \"\\t\" text) amcp:f)))",
        "(defun amcp:on () (= 1 (logand 1 (getvar \"CMDACTIVE\"))))",
        "(defun amcp:in (i x) (if amcp:ok (cond ((not (amcp:on)) (setq amcp:ok nil amcp:early i))"
        " ((null x) (setq amcp:ok nil) (amcp:log \"N\" (itoa i)))"
        " (T (command x) (amcp:log \"P\" (getvar \"LASTPROMPT\"))))))",
        f"(defun amcp:restore () (mapcar 'setvar {names} amcp:sv) (setq *error* amcp:olderr))",
        "(defun *error* (msg) (amcp:restore) (amcp:log \"X\" msg)"
        " (if (and amcp:mark (not (amcp:on))) (progn (command-s \"_.UNDO\" \"_Back\") (amcp:log \"U\" \"\")))"
        " (amcp:log \"D\" (itoa (getvar \"CMDACTIVE\"))) (if amcp:f (close amcp:f)) (setq amcp:f nil) (princ))",
        "(amcp:log \"B\" \"\")",
        "(setvar \"OSMODE\" 0) (setvar \"CMDECHO\" 1) (setvar \"CMDDIA\" 0) (setvar \"ATTDIA\" 0)",
    ]
    if undo:
        parts.append("(command \"_.UNDO\" \"_Mark\") (setq amcp:mark T)")
    parts += [f"(command {lisp_string(command)})", "(amcp:log \"C\" (getvar \"LASTPROMPT\"))"]
    parts += [f"(amcp:in {i} {answer})" for i, answer in enumerate(answers, start=1)]
    parts += [
        "(if (amcp:on) (progn (setq amcp:act T amcp:ok nil) (amcp:log \"A\" (getvar \"LASTPROMPT\")) (command)))",
        "(if amcp:early (amcp:log \"E\" (itoa amcp:early)))",
    ]
    if undo:
        parts.append("(if (not amcp:ok) (progn (command \"_.UNDO\" \"_Back\") (amcp:log \"U\" \"\")))")
    parts += [
        "(amcp:restore)",
        "(amcp:log \"D\" (itoa (getvar \"CMDACTIVE\")))",
        "(close amcp:f) (setq amcp:f nil)",
        "(princ))",
    ]
    return " ".join(parts)


def staged_messages(lisp: str, transcript: str, limit: int = MAX_MESSAGE) -> list[tuple[str, str]]:
    """What is sent to AutoCAD, in order, as (message, the transcript line that shows AutoCAD ran it).

    Every message is a complete expression ending with Enter, and at most `limit` characters. The
    first ones store `lisp` as text in amcp:src, a piece each, and write "S<tab>n" to the transcript;
    the last evaluates the stored text, whose own first line is "B". See the module docstring for why.
    """
    path = lisp_string(transcript.replace("\\", "/"))

    def wrap(index: int, piece: str) -> str:
        store = f"(setq amcp:src (strcat amcp:src {piece}))" if index else f"(setq amcp:src {piece})"
        mode = "a" if index else "w"
        return (f"(progn {store} (setq amcp:h (open {path} \"{mode}\")) (write-line \"S\\t{index}\" amcp:h) "
                "(close amcp:h) (princ))\n")

    room = limit - len(wrap(999, '""'))
    if room < 100:
        raise AcadError(f"The transcript path is too long to hand the command to AutoCAD: {transcript}")
    messages: list[tuple[str, str]] = []
    piece = ""
    for char in lisp:
        if len(lisp_string(piece + char)) - 2 > room:
            messages.append((wrap(len(messages), lisp_string(piece)), f"S\t{len(messages)}"))
            piece = ""
        piece += char
    messages.append((wrap(len(messages), lisp_string(piece)), f"S\t{len(messages)}"))
    messages.append(("(eval (read amcp:src))\n", "B\t"))
    return messages


def describe_input(value: Any) -> str:
    return "Enter" if value == "" else (value if isinstance(value, str) else repr(value))


def parse_transcript(text: str, command: str, inputs: Sequence[Any]) -> dict:
    """The transcript lines (tag, tab, text) as the result run_command returns."""
    steps: list[dict] = []
    result: dict[str, Any] = {"command": command, "completed": False, "steps": steps,
                              "ended_early_before_input": None, "left_waiting_at": None,
                              "cancelled": False, "undone": False, "lisp_error": None, "missing_object": None}
    answered = 0
    finished = False
    for line in text.splitlines():
        tag, _, rest = line.partition("\t")
        if tag == "C":
            steps.append({"sent": command, "lastprompt": rest})
        elif tag == "P":
            value = inputs[answered] if answered < len(inputs) else "?"
            answered += 1
            steps.append({"sent": describe_input(value), "lastprompt": rest})
        elif tag == "A":
            result["left_waiting_at"], result["cancelled"] = rest, True
        elif tag == "E":
            result["ended_early_before_input"] = int(rest)
        elif tag == "U":
            result["undone"] = True
        elif tag == "N":
            result["missing_object"] = int(rest)
        elif tag == "X":
            result["lisp_error"] = rest
        elif tag == "D":
            finished = True
    result["inputs_used"] = answered
    result["inputs_given"] = len(inputs)
    result["completed"] = (finished and answered == len(inputs) and not result["cancelled"]
                           and result["ended_early_before_input"] is None and result["lisp_error"] is None
                           and result["missing_object"] is None)
    return result


def problem(result: dict) -> str | None:
    """What went wrong, in one sentence, or None."""
    if result["lisp_error"]:
        return f"AutoLISP stopped with an error: {result['lisp_error']}."
    if result["missing_object"] is not None:
        return (f"Answer {result['missing_object']} found nothing (no object with that handle, or nothing of "
                "those types), so the command was stopped there.")
    if result["ended_early_before_input"] is not None:
        return (f"The command ended before answer {result['ended_early_before_input']} of "
                f"{result['inputs_given']}; the rest were not sent. Check the prompts in 'steps'.")
    if result["cancelled"]:
        return ("The command still wanted input after the last answer and was cancelled. "
                f"It was waiting at: {result['left_waiting_at']!r}.")
    return None


def is_system_variable(doc: Any, name: str) -> bool:
    """True if AutoCAD knows `name` as a system variable (typing one changes it: refused here)."""
    try:
        return doc.GetVariable(name) is not None
    except (pywintypes.com_error, AttributeError) as err:
        if is_busy_error(err):
            raise
        return False


def _read(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("mbcs", errors="replace")


def _wait_line(path: Path, prefix: str, seconds: float) -> bool:
    """Wait until the transcript has a line that starts with `prefix`."""
    deadline = time.monotonic() + seconds
    while True:
        if path.exists():
            with contextlib.suppress(OSError):
                if any(line.startswith(prefix) for line in _read(path).splitlines()):
                    return True
        if time.monotonic() > deadline:
            return False
        time.sleep(POLL)


def run(doc: Any, command: str, inputs: Sequence[Any] = (), undo_on_failure: bool = True,
        timeout_seconds: float = 30.0) -> dict:
    """Run one command with its answers in a drawing this server may edit (see the module docstring)."""
    inputs = list(inputs or [])
    sent = check_command(command)
    check_inputs(inputs)
    session.require_editable(doc)
    session.require_idle(doc)
    app = session.app
    if doc_key(app.ActiveDocument) != doc_key(doc):
        raise AcadError(f"'{doc.Name}' is not the active drawing. Commands run in the active drawing only; "
                        "ask the user to switch to it (the server does not switch tabs under the user).")
    bare = bare_name(sent)
    if is_system_variable(doc, bare):
        raise AcadError(f"'{bare}' is a system variable, not a command; use set_drawing_variables.")
    undo = undo_on_failure and bare not in NO_UNDO
    if undo:
        undoctl = int(doc.GetVariable("UNDOCTL"))
        if not undoctl & 1 or undoctl & 2:
            raise AcadError(f"UNDO is off or limited to one step (UNDOCTL={undoctl}), so a failed command could "
                            "not be put back. Pass undo_on_failure=False to run it anyway.")
    hwnd = session.hwnd
    if not hwnd:
        raise AcadError("AutoCAD's main window is unknown; call acad_status first.")
    name = str(doc.Name).lower()
    title = window_title(hwnd)
    if not title_shows(title, name):
        raise AcadError(f"AutoCAD's window title ({title!r}) does not show '{doc.Name}' as active; not sending.")

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    path = RUN_DIR / f"run-{uuid.uuid4().hex}.txt"
    messages = staged_messages(build_lisp(sent, inputs, str(path), undo), str(path))
    timeout_seconds = max(1.0, min(float(timeout_seconds), 150.0))
    try:
        for i, (message, shows) in enumerate(messages, start=1):
            send_input(hwnd, message)  # a False may only mean AutoCAD is busy evaluating: the transcript tells
            if not _wait_line(path, shows, START_WAIT):
                send_input(hwnd, CANCEL_INPUT)  # never leave anything typed on the command line
                raise AcadError(f"AutoCAD did not run the command expression: it did not take message {i} of "
                                f"{len(messages)} ({len(message)} characters) within {START_WAIT:.0f}s. Nothing "
                                f"of the command ran; what was typed was cancelled. Transcript folder: {RUN_DIR}."
                                + describe_blockers(hwnd))
        if not _wait_line(path, "D\t", timeout_seconds):
            raise AcadError(f"'{sent}' did not finish within {timeout_seconds:.0f}s. It may be waiting in a dialog "
                            "or still working; do NOT repeat it. Check acad_status." + describe_blockers(hwnd))
        result = parse_transcript(_read(path), sent, inputs)
    finally:
        with contextlib.suppress(OSError):
            path.unlink()
    result["drawing"] = str(doc.Name)
    result["messages"] = len(messages)
    result["undo_mark"] = undo
    # Safety net: the expression should never leave a command waiting; if one is, cancel it.
    with worker.quick_retries():
        try:
            still = int(doc.GetVariable("CMDACTIVE")) & 1
        except (pywintypes.com_error, AttributeError) as err:
            if not is_busy_error(err):
                raise
            still = 1
    if still and title_shows(window_title(hwnd), name):
        send_input(hwnd, CANCEL_INPUT)
        result["cancelled_afterwards"] = True
    result["problem"] = problem(result)
    result["note"] = LAG_NOTE
    return result


@acad_tool(destructive=True)
def run_command(command: str, inputs: list[Any] | None = None, name: str = "",
                undo_on_failure: bool = True, timeout_seconds: float = 30) -> dict:
    """Run one AutoCAD command with a list of answers to its prompts, in a drawing this
    server created (the edit guard and busy check apply). Use it for prompt-driven
    commands no other tool covers, e.g. Block Editor commands (BPARAMETER, BACTION) or
    -PURGE. AutoCAD is never left waiting: if the command still wants input after the
    last answer it is cancelled, and if it ended early or was cancelled the drawing goes
    back to how it was (UNDO mark). The result has a transcript of the prompts.

    Answers: text as typed ("" is Enter; names with spaces are fine; options such as
    "_L" or "T"), numbers, [x, y] or [x, y, z] points in WCS drawing units,
    {"handle": "1A2"} for an object, {"handle": "1A2", "point": [x, y]} to pick it at a
    point, {"last": true} for the newest object, {"select_all": "LWPOLYLINE,DIMENSION"}
    for every object of those types. Running object snaps are off while it runs.
    Text starting with "(", "!" or "'" is refused, and so are commands that run code,
    change AutoCAD's setup, write or close files, or switch drawings.

    Read the result's "steps": LASTPROMPT lags one answer, and "left_waiting_at" is the
    prompt that was still open. "completed" is true only when every answer was used and
    the command ended with the last one.

    Args:
        command: command name, e.g. "BPARAMETER" or "-PURGE" (sent as "_.<name>").
        inputs: answers in order.
        name: which drawing; it must be the active one (default: the active drawing).
        undo_on_failure: go back to the UNDO mark if the command fails (default True;
            not used around BEDIT/BCLOSE/BSAVE).
        timeout_seconds: how long to wait for the command to finish (default 30, max 150).
    """
    return run(session.document(name), command, inputs or [], undo_on_failure, timeout_seconds)
