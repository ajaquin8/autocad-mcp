"""AMCP-LIVE-20261029-03: check the dimension-style and screenshot fixes on the kitchen scratch drawing.
Run ONLY after the user said go.

    .venv\\Scripts\\python.exe tests\\live\\kitchen_dims_fix.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import SCRATCH, check, finish, step  # noqa: E402

from autocad_mcp.tools import documents, query, settings  # noqa: E402

REPORT = "AMCP-LIVE-20261029-03"
KITCHEN = "AMCP-LIVE-20261029-02.dwg"


def main() -> int:
    if step("unlock the kitchen scratch drawing", documents.allow_edit_document, KITCHEN) is None:
        return 1
    before = query.get_entity("DB", name=KITCHEN)  # the room depth dimension (A4 was rebuilt by hand)
    step("dimension settings into the style", settings.set_drawing_variables,
         {"DIMSCALE": 24, "DIMLUNIT": 4}, name=KITCHEN)
    after = query.get_entity("DB", name=KITCHEN)
    width = lambda e: e["bbox"][1][0] - e["bbox"][0][0]  # noqa: E731 - text sits beside a vertical dimension
    check("room depth dimension grew", width(after) > width(before) + 1,
          f"bbox width {width(before):.2f} -> {width(after):.2f}")
    image = step("capture_view (no zoom, waits for redraw)", query.capture_view)
    if image is not None:
        with open(os.path.join(SCRATCH, f"{REPORT}.png"), "wb") as fh:
            fh.write(image.data)
    step("save_document", documents.save_document, name=KITCHEN)
    return finish(REPORT)


if __name__ == "__main__":
    sys.exit(main())
