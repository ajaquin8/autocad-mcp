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
- logs LASTPROMPT, the command line's last line, after each answer. AutoCAD prints a prompt only
  when the next input arrives, so the line read right after an answer is the prompt that answer
  replied to (with the answer echoed after it), unless AutoCAD printed a message after taking the
  answer ("1 found", "Specify selection set for action"); read_line tells these apart (E2,
  transcripts of AMCP-LIVE-20261118-03);
- cancels with (command) if the command is still waiting at the end, and goes back to an UNDO
  mark it set first if the command ended early or had to be cancelled;
- writes that transcript to a file the server reads, so nothing needs COM while it runs.
Running object snaps are off while it runs, and CMDECHO is on so the prompts are logged. If the
expression does not finish in time (a command stuck at a prompt it cannot be answered at), the
server cancels it with Ctrl+C, unless AutoCAD shows a dialog (cancel_unfinished).

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
from ..session import is_busy_error, session
from ..winui import describe_blockers, send_input, window_title
from .control import CANCEL_INPUT

# A folder both this server and AutoCAD see (see the module docstring); AMCP_RUN_DIR overrides it.
RUN_DIR = Path(os.environ.get("AMCP_RUN_DIR") or Path.home() / ".autocad-mcp" / "run")
START_WAIT = 3.0  # seconds for the expression to start (it first creates the transcript file)
CANCEL_WAIT = 5.0  # seconds for a cancelled expression to finish its transcript, and for AutoCAD to answer
# A second look after a command that left AutoCAD answering: once (SELECT in the Block Editor, live 2026-11-18,
# AMCP-LIVE-20261118-02) AutoCAD answered right after the command ended and was waiting at a prompt a moment later.
AFTER_WAIT = 0.75
MAX_MESSAGE = 900  # characters per WM_COPYDATA message; AutoCAD drops a message of 1000 or more
POLL = 0.05
MAX_INPUTS = 60
MAX_TEXT = 256
FAILED_STEPS = 8  # steps a compact result keeps when the command did not complete

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

FOUND = re.compile(r"^(.*?)\s+(\d+ found.*)$")
TYPED_POINT = re.compile(r"^(.*:)\s+(-?[\d.]+(?:,-?[\d.]+){1,2})$")
CANCEL_MARK = re.compile(r"\s*\*Cancel\*\s*$", re.IGNORECASE)


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


def lisp_types(value: Any) -> str:
    types = str(value).strip().upper()
    if not OBJECT_TYPES.match(types):
        raise ValueError(f"'{types}' is not a list of DXF object types such as LWPOLYLINE,DIMENSION.")
    return types


def lisp_handle(value: Any) -> str:
    handle = str(value).strip()
    if not HANDLE.match(handle):
        raise ValueError(f"'{handle}' is not an entity handle.")
    return f"(handent {lisp_string(handle.upper())})"


def lisp_selection(value: dict) -> str:
    """A selection set built in AutoCAD: {"crossing" | "window": [p1, p2]} selects in the current space
    and needs the window on screen (as a pick would); {"handles": [...]} takes those objects. "except":
    "TYPES" leaves objects of those DXF types out. Nothing selected gives nil (the command is stopped)."""
    keys = set(value)
    kind = next((k for k in ("crossing", "window", "handles") if k in keys), None)
    if kind is None or keys - {kind, "except"}:
        raise ValueError(f"Cannot read the selection {value!r}.")
    if kind == "handles":
        handles = value["handles"]
        if not isinstance(handles, (list, tuple)) or not handles or len(handles) > MAX_INPUTS:
            raise ValueError(f"handles takes a list of 1 to {MAX_INPUTS} entity handles.")
        ents = " ".join(lisp_handle(h) for h in handles)
        test = "e"
        if "except" in value:
            test = f'(and e (not (wcmatch (cdr (assoc 0 (entget e))) {lisp_string(lisp_types(value["except"]))})))'
        return (f"((lambda (ss) (foreach e (list {ents}) (if {test} (ssadd e ss)))"
                " (if (> (sslength ss) 0) ss)) (ssadd))")
    corners = value[kind]
    if not isinstance(corners, (list, tuple)) or len(corners) != 2:
        raise ValueError(f"{kind} takes two corners [[x1, y1], [x2, y2]].")
    mode = "_C" if kind == "crossing" else "_W"
    args = f'(ssget "{mode}" {lisp_point(corners[0])} {lisp_point(corners[1])}'
    if "except" in value:
        types = lisp_string(lisp_types(value["except"]))
        args += f' (list (cons -4 "<NOT") (cons 0 {types}) (cons -4 "NOT>"))'
    return args + ")"


def lisp_input(value: Any) -> str:
    """One answer to a prompt as an AutoLISP expression.

    Text is sent as typed ("" is Enter), numbers as numbers, [x, y] or [x, y, z] as a WCS point.
    {"handle": h} is that object, {"handle": h, "point": p} picks it at that point (as entsel
    would), {"last": true} is the newest object. For "Select objects": {"crossing": [p1, p2]} or
    {"window": [p1, p2]} (current space, on screen) and {"handles": [...]}, each optionally with
    "except": "LWPOLYLINE,DIMENSION"; {"select_all": "TYPES"} is every object of those types in the
    whole drawing (ssget "_X": model space and every layout, not just the current space).
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
            ent = lisp_handle(value["handle"])
            return f"(list {ent} {lisp_point(value['point'])})" if "point" in keys else ent
        if keys == {"last"} and value["last"] is True:
            return "(entlast)"
        if keys == {"select_all"}:
            return f'(ssget "_X" (list (cons 0 {lisp_string(lisp_types(value["select_all"]))})))'
        if keys & {"crossing", "window", "handles"}:
            return lisp_selection(value)
    raise ValueError(f"Cannot send {value!r} as an answer: use text, a number, [x, y], or "
                     '{"handle": ...}, {"handle": ..., "point": [x, y]}, {"last": true}, {"crossing": [p1, p2]}, '
                     '{"window": [p1, p2]}, {"handles": [...]} (optionally with "except": "TYPES"), '
                     '{"select_all": "TYPES"}.')


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
        "(if (amcp:on) (progn (setq amcp:act T amcp:ok nil) (amcp:log \"A\" (getvar \"LASTPROMPT\")) (command)"
        " (amcp:log \"K\" (getvar \"LASTPROMPT\"))))",
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


def echo_of(value: Any) -> str | None:
    """What AutoCAD prints after the prompt for this answer, when that is known: typed text and numbers
    are echoed; points, objects, selections and Enter are not (a point given at a text prompt is,
    as "x,y", which TYPED_POINT catches)."""
    if isinstance(value, str):
        return value or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return lisp_number(value)
    return None


def same_number(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def read_line(value: Any, line: str) -> dict:
    """The command-line line read right after one answer, split into the prompt it replied to and
    what AutoCAD printed after it (E2). See the module docstring for why that line is the answer's prompt.

    {"prompt": p}: the answer's prompt, its echo removed.
    {"prompt": p, "message": "1 found"}: AutoCAD added a message to the prompt's line.
    {"prompt": p, "answered_as": "0,-12"}: a point was taken as typed text (a text prompt got a point).
    {"prompt": None, "message": m}: text that AutoCAD should have echoed is missing, so the line is a
    message printed after the answer and the answer's own prompt was not kept.
    """
    text = line.rstrip()
    found = FOUND.match(text)
    if found:
        return {"prompt": found[1].rstrip(), "message": found[2]}
    echo = echo_of(value)
    if echo is not None:
        head, sep, tail = text.rpartition(": ")
        if sep and (tail.strip().lower() == echo.lower() or same_number(tail, echo)):
            return {"prompt": head + ":"}
        if text.lower().endswith(echo.lower()) and text[:-len(echo)].rstrip().endswith(":"):
            return {"prompt": text[:-len(echo)].rstrip()}
        return {"prompt": None, "message": text}
    if isinstance(value, (list, tuple)):
        typed = TYPED_POINT.match(text)
        if typed:
            return {"prompt": typed[1], "answered_as": typed[2]}
    return {"prompt": text}


def step_text(step: dict) -> str:
    """One step for an error message: answer -> prompt (or message)."""
    shown = step.get("prompt") or step.get("message") or ""
    extra = f" [{step['message']}]" if step.get("prompt") and step.get("message") else ""
    return f"{step['sent']} -> {shown!r}{extra}"


def parse_transcript(text: str, command: str, inputs: Sequence[Any]) -> dict:
    """The transcript lines (tag, tab, text) as the result run_command returns."""
    steps: list[dict] = []
    result: dict[str, Any] = {"command": command, "completed": False, "steps": steps,
                              "ended_early_before_input": None, "left_waiting_at": None,
                              "cancelled": False, "undone": False, "lisp_error": None, "missing_object": None}
    answered = 0
    finished = False
    last_line, waiting, after_cancel = None, None, None
    for line in text.splitlines():
        tag, _, rest = line.partition("\t")
        if tag == "C":
            step = {"sent": command}
            if rest.strip() and not rest.lstrip().lower().startswith("command:"):
                step["message"] = rest.strip()  # e.g. "Current visibility state: ..."
            steps.append(step)
            last_line = rest
        elif tag == "P":
            value = inputs[answered] if answered < len(inputs) else "?"
            answered += 1
            steps.append({"sent": describe_input(value), **read_line(value, rest)})
            last_line = rest
        elif tag == "A":
            waiting, result["cancelled"] = rest, True
        elif tag == "K":
            after_cancel = CANCEL_MARK.sub("", rest).strip()
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
    # The prompt still open when the command was cancelled has usually not been printed yet (it is printed
    # when the next input arrives), so the line before the cancel repeats the last answer's prompt. The line
    # after the cancel may show it (not verified live); otherwise it is only known if AutoCAD printed it.
    for seen in (after_cancel, waiting):
        if seen and seen.strip() != (last_line or "").strip():
            result["left_waiting_at"] = seen.strip()
            break
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
        waiting = (f"It was waiting at: {result['left_waiting_at']!r}." if result["left_waiting_at"] else
                   "AutoCAD had not printed the prompt it was waiting at; the last answer replied to the last "
                   "step's prompt.")
        return f"The command still wanted input after the last answer and was cancelled. {waiting}"
    if result.get("cancelled_afterwards"):
        return ("The command ended, but AutoCAD was waiting at a prompt again right afterwards; the server "
                "cancelled that. Check the drawing before going on.")
    return None


def compact_result(result: dict) -> dict:
    """The short form of a result (E1): whether it completed, what went wrong, the last prompt, and only
    the lines AutoCAD printed besides prompts ("1 found"). The steps are kept, the last few, only when the
    command did not complete."""
    steps = result["steps"]
    out: dict[str, Any] = {"command": result["command"], "drawing": result.get("drawing"),
                           "completed": result["completed"]}
    if result.get("problem"):
        out["problem"] = result["problem"]
    out["inputs_used"], out["inputs_given"] = result["inputs_used"], result["inputs_given"]
    if steps:
        out["last_prompt"] = steps[-1].get("prompt") or steps[-1].get("message")
    said = []
    for i, step in enumerate(steps):
        where = f"answer {i}" if i else "command"
        if step.get("message"):
            said.append(f"{where}: {step['message']}")
        if step.get("answered_as"):
            said.append(f"{where}: the point was taken as text {step['answered_as']!r} (answers out of step?)")
    if said:
        out["messages"] = said
    for key in ("left_waiting_at", "cancelled", "cancelled_afterwards", "undone", "missing_object",
                "ended_early_before_input", "lisp_error"):
        if result.get(key) not in (None, False):
            out[key] = result[key]
    if not result["completed"] and steps:
        out["steps"] = steps[-FAILED_STEPS:]
        if len(steps) > FAILED_STEPS:
            out["steps_shown"] = f"the last {FAILED_STEPS} of {len(steps)}"
    return out


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


def autocad_answers(doc: Any, wait: float = 0.0) -> bool:
    """True once the drawing answers COM with no command active, trying for up to `wait` seconds."""
    deadline = time.monotonic() + wait
    while True:
        with worker.quick_retries():
            try:
                if not int(doc.GetVariable("CMDACTIVE")) & 1:
                    return True
            except (pywintypes.com_error, AttributeError) as err:
                if not is_busy_error(err):
                    raise
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL)


def cancel_unfinished(doc: Any, path: Path, sent: str, inputs: Sequence[Any], hwnd: int, name: str,
                      timeout_seconds: float) -> str:
    """The error for a command that did not finish in time, after cancelling it (B3, 2026-11-18: a Block
    Editor action that never finished left AutoCAD refusing every call until cancel_command).

    Not cancelled while AutoCAD shows a dialog (Ctrl+C cannot close it, and only the user should answer
    it) or when another drawing has become active. Ctrl+C also stops the expression, whose error handler
    puts the variables back, goes back to the UNDO mark and finishes the transcript, so the error can
    say how far the command got."""
    head = f"'{sent}' did not finish within {timeout_seconds:.0f}s."
    blockers = describe_blockers(hwnd)
    if blockers:
        return head + " It is waiting in a dialog, so it was not cancelled; do NOT repeat it." + blockers
    if not title_shows(window_title(hwnd), name):
        return (head + f" '{doc.Name}' is no longer the active drawing, so it was not cancelled; do NOT repeat "
                "it. Check acad_status.")
    send_input(hwnd, CANCEL_INPUT)
    _wait_line(path, "D\t", CANCEL_WAIT)
    text = head + " The server cancelled it (Ctrl+C)"
    partial = None
    with contextlib.suppress(OSError):
        partial = parse_transcript(_read(path), sent, inputs)
    if partial and partial["undone"]:
        text += " and the drawing was put back to how it was"
    text += "."
    if partial and partial["steps"]:
        shown = partial["steps"][-8:]
        steps = "; ".join(step_text(s) for s in shown)
        more = f" (last {len(shown)} of {len(partial['steps'])})" if len(partial["steps"]) > len(shown) else ""
        text += f" Prompts so far{more}: {steps}."
    if autocad_answers(doc, CANCEL_WAIT):
        text += " AutoCAD answers again. Do not repeat the command unchanged."
    else:
        text += (" AutoCAD still does not answer: call cancel_command, then acad_status. Do not repeat the command."
                 + describe_blockers(hwnd))
    return text


def run(doc: Any, command: str, inputs: Sequence[Any] = (), undo_on_failure: bool = True,
        timeout_seconds: float = 30.0) -> dict:
    """Run one command with its answers in a drawing this server may edit (see the module docstring)."""
    inputs = list(inputs or [])
    sent = check_command(command)
    check_inputs(inputs)
    session.require_editable(doc)
    session.require_idle(doc)
    session.require_active(doc, "commands run in the active drawing only")
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
            raise AcadError(cancel_unfinished(doc, path, sent, inputs, hwnd, name, timeout_seconds))
        result = parse_transcript(_read(path), sent, inputs)
    finally:
        with contextlib.suppress(OSError):
            path.unlink()
    result["drawing"] = str(doc.Name)
    result["pieces_sent"] = len(messages)
    result["undo_mark"] = undo
    # Safety net: the expression should never leave a command waiting; if one is, cancel it. Looked at twice.
    waiting = not autocad_answers(doc)
    if not waiting:
        time.sleep(AFTER_WAIT)
        waiting = not autocad_answers(doc)
    if waiting and title_shows(window_title(hwnd), name):
        send_input(hwnd, CANCEL_INPUT)
        result["answers_after_cancel"] = autocad_answers(doc, CANCEL_WAIT)
        result["cancelled_afterwards"] = True
    result["problem"] = problem(result)
    return result


@acad_tool(destructive=True)
def run_command(command: str, inputs: list[Any] | None = None, name: str = "",
                undo_on_failure: bool = True, timeout_seconds: float = 30, compact: bool = False) -> dict:
    """Run one AutoCAD command with a list of answers to its prompts, in a drawing this
    server created (the edit guard and busy check apply). Use it for prompt-driven
    commands no other tool covers, e.g. Block Editor commands (BPARAMETER, BACTION) or
    -PURGE. AutoCAD is never left waiting: if the command still wants input after the
    last answer, or has not finished within timeout_seconds, it is cancelled, and if it
    ended early or was cancelled the drawing goes back to how it was (UNDO mark). The
    result (or the error) has a transcript of the prompts. Only an AutoCAD dialog is left
    for the user to answer.

    Answers: text as typed ("" is Enter; names with spaces are fine; options such as
    "_L" or "T"), numbers, [x, y] or [x, y, z] points in WCS drawing units,
    {"handle": "1A2"} for an object, {"handle": "1A2", "point": [x, y]} to pick it at a
    point, {"last": true} for the newest object. At "Select objects": {"crossing": [p1, p2]}
    or {"window": [p1, p2]} (current space; the window must be on screen) or
    {"handles": [...]}, each optionally with "except": "LWPOLYLINE,DIMENSION" to leave those
    types out; {"select_all": "TYPES"} is every object of those types in the whole drawing
    (all spaces). Running object snaps are off while it runs.
    Text starting with "(", "!" or "'" is refused, and so are commands that run code,
    change AutoCAD's setup, write or close files, or switch drawings.

    Each of the result's "steps" pairs an answer with the prompt it replied to ("prompt",
    the echoed answer removed) and anything AutoCAD printed after it ("message", e.g.
    "1 found"). "prompt" is null when AutoCAD printed a message instead of echoing the
    answer; "answered_as" means a point was taken as typed text (the prompt wanted text:
    the answers are out of step). "left_waiting_at" is the prompt still open when the
    command was cancelled, if AutoCAD had printed it. "completed" is true only when every
    answer was used and the command ended with the last one.

    compact=True returns a short result for long builds: completed, problem, the last
    prompt and AutoCAD's other lines ("1 found"); the steps only if it did not complete.

    Args:
        command: command name, e.g. "BPARAMETER" or "-PURGE" (sent as "_.<name>").
        inputs: answers in order.
        name: which drawing; it must be the active one (default: the active drawing).
        undo_on_failure: go back to the UNDO mark if the command fails (default True;
            not used around BEDIT/BCLOSE/BSAVE).
        timeout_seconds: how long to wait for the command to finish before cancelling it
            (default 30, max 150).
        compact: return the short result (default False: every step).
    """
    result = run(session.document(name), command, inputs or [], undo_on_failure, timeout_seconds)
    return compact_result(result) if compact else result
