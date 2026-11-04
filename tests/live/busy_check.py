"""Live check of the busy handling: retried calls, new_drawing settling, cancel_command.
Run ONLY after the user has saved open work and said go, one phase at a time:

    .venv\\Scripts\\python.exe tests\\live\\busy_check.py new      # new scratch drawing (watch for retries)
    .venv\\Scripts\\python.exe tests\\live\\busy_check.py refused  # with one of the user's drawings active
    .venv\\Scripts\\python.exe tests\\live\\busy_check.py cancel   # scratch drawing active, user inside LINE
    .venv\\Scripts\\python.exe tests\\live\\busy_check.py cleanup  # closes the scratch drawing

The script calls the tool functions directly on its own thread, so it installs the same
message filter the server's COM worker uses. Each phase is its own process; the scratch
drawing's name is kept in scratch/<report>-state.json and re-marked as server-created.
"""

from __future__ import annotations

import json
import os
import sys
import time

import harness
import pythoncom
from harness import SCRATCH, check, step

from autocad_mcp.com import MessageFilter, retry_seconds
from autocad_mcp.session import session
from autocad_mcp.tools import control, documents

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-BUSY")
STATE = os.path.join(SCRATCH, f"{REPORT}-state.json")


def scratch_doc():
    with open(STATE, encoding="utf-8") as fh:
        name = json.load(fh)["scratch"]
    doc = session.find_document(name)
    session.mark_owned(doc)
    return doc


def main(phase: str) -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    message_filter = MessageFilter(retry_seconds())
    message_filter.register()
    session.connect()
    check("AutoCAD window found", bool(session.hwnd), str(session.hwnd))
    if phase == "new":
        start = time.monotonic()
        info = step("new_drawing settles", documents.new_drawing)
        print(f"took {time.monotonic() - start:.1f}s, rejected calls retried: {message_filter.retries}")
        if info:
            os.makedirs(SCRATCH, exist_ok=True)
            with open(STATE, "w", encoding="utf-8") as fh:
                json.dump({"scratch": info["name"]}, fh)
    elif phase == "refused":
        scratch_doc()
        step("cancel refuses in the user's drawing", control.cancel, expect_error="Refused")
    elif phase == "cancel":
        doc = scratch_doc()
        step("cancel_command", control.cancel)
        deadline, active = time.monotonic() + 5, None
        while time.monotonic() < deadline:
            try:
                active = int(doc.GetVariable("CMDACTIVE"))
                if active == 0:
                    break
            except Exception:  # noqa: BLE001 - still rejected
                pass
            time.sleep(0.3)
        check("the prompt is gone (CMDACTIVE 0)", active == 0, str(active))
    elif phase == "cleanup":
        doc = scratch_doc()
        step("close the scratch drawing", documents.close_document, str(doc.Name), discard_changes=True)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
    sys.exit(harness.finish(REPORT))
