"""Live check that a server restart keeps the drawings the server created, and nothing else.
Run ONLY after the user has saved open work and said go, one phase at a time (each phase is a
new process, which is the "restart"):

    .venv\\Scripts\\python.exe tests\\live\\ownership_check.py make      # new scratch drawing, saved to scratch/
    .venv\\Scripts\\python.exe tests\\live\\ownership_check.py restart   # new process: scratch editable, user drawings locked
    .venv\\Scripts\\python.exe tests\\live\\ownership_check.py reopen    # close the scratch file, open it again: locked
    .venv\\Scripts\\python.exe tests\\live\\ownership_check.py cleanup   # close it (re-marked as the test's own)

The user's drawings are only read. Output and the scratch drawing go to scratch/.
"""

from __future__ import annotations

import os
import sys

import harness
import pythoncom
from harness import SCRATCH, check, step

from autocad_mcp.com import MessageFilter, retry_seconds
from autocad_mcp.session import doc_key, session
from autocad_mcp.tools import documents

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-OWNERSHIP")
PATH = os.path.join(SCRATCH, f"{REPORT}.dwg")


def main(phase: str) -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    MessageFilter(retry_seconds()).register()  # as the server's COM worker does
    session.connect()
    check("AutoCAD identity read", bool(session.identity), str(session.identity))
    if phase == "make":
        info = step("new_drawing", documents.new_drawing)
        if info:
            step("save it to scratch/", documents.save_document, PATH, overwrite=True, name=info["name"])
    elif phase == "restart":
        docs = {str(d.Name): session.describe(d) for d in session.documents()}
        mine = docs.get(os.path.basename(PATH))
        check("scratch drawing taken back after the restart", bool(mine and mine["editable"]), str(mine))
        others = [d for name, d in docs.items() if name != os.path.basename(PATH)]
        check("every other drawing still locked", all(not d["editable"] for d in others),
              ", ".join(f"{d['name']}={d['editable']}" for d in others))
    elif phase == "reopen":
        step("close the scratch drawing", documents.close_document, PATH)
        step("open it again", documents.open_drawing, PATH)
        doc = session.find_document(PATH)
        check("reopened file is locked", not session.is_editable(doc), str(session.describe(doc)))
    elif phase == "cleanup":
        doc = session.find_document(PATH)
        session.owned.add(doc_key(doc))  # the test's own scratch file; never done for a user drawing
        step("close the scratch drawing", documents.close_document, PATH)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
    sys.exit(harness.finish(REPORT))
