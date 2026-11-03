"""AMCP-LIVE-20261103-01: connect to whichever AutoCAD is running. Read only. Run ONLY after
the user has saved open work and said go.

    .venv\\Scripts\\python.exe tests\\live\\connect_check.py

Creates, opens and changes nothing: it lists the AutoCAD ProgIDs in the registry, calls
acad_status, and checks that the server attached to acad.exe (not DWG TrueView) and that
every open drawing is still locked by the edit guard.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import SCRATCH, check, finish, step  # noqa: E402

from autocad_mcp import session as session_module  # noqa: E402
from autocad_mcp.session import session  # noqa: E402
from autocad_mcp.tools import documents  # noqa: E402

REPORT = "AMCP-LIVE-20261103-01"


def main() -> int:
    os.makedirs(SCRATCH, exist_ok=True)
    step("registered AutoCAD ProgIDs, newest first", session_module.progids)
    status = step("acad_status", documents.acad_status)
    if status is None:
        return finish(REPORT)
    app = session.app
    full_name = str(app.FullName)
    check("attached to acad.exe, not TrueView", os.path.basename(full_name).lower() == "acad.exe",
          f"{app.Name} at {full_name}, version {app.Version}")
    locked = [d["name"] for d in status["open_drawings"] if not d.get("editable")]
    check("every open drawing is locked by the edit guard",
          len(locked) == len(status["open_drawings"]), f"locked: {locked}")
    return finish(REPORT)


if __name__ == "__main__":
    sys.exit(main())
