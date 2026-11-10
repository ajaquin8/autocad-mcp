"""Live check of run_command and the Block Editor tools, in ONE new scratch drawing.
Run ONLY after the user has saved open work and said go (knowledge/Decisions/Live test protocol.md):

    .venv\\Scripts\\python.exe -u tests\\live\\command_check.py

What it does, all in a scratch drawing it creates (never in the user's drawings):
 1. new_drawing; a 60 x 84 rectangle and a jamb line at x = 60.
 2. run_command -BLOCK with a name that has spaces ("AMCP test unit"), base 0,0, the two objects.
 3. run_command LINE with too few answers: must be cancelled and undone (no line left).
 4. run_command ERASE with one answer too many: must end early and be undone (rectangle kept).
 5. open_block_editor, add_linear_parameter Width (0,0 -> 60,0), add_stretch_action on the
    right side, close_block_editor (save).
 6. check_dynamic_block: Width 72 must make it 12 wider on the right (min_x unchanged).
 7. close the scratch drawing without saving.
Output: scratch/<report>.json. The script stops at the first step that leaves AutoCAD in an
unexpected state and prints what to do.
"""

from __future__ import annotations

import os
import sys

import harness
import pythoncom
from harness import check, step

from autocad_mcp.com import MessageFilter, point, retry_seconds
from autocad_mcp.session import session
from autocad_mcp.tools import block_editor, commands, documents, draw

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-COMMANDS")
BLOCK = "AMCP test unit"


def count_model_space(doc) -> int:
    return int(doc.ModelSpace.Count)


def main() -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    MessageFilter(retry_seconds()).register()
    session.connect()
    check("AutoCAD window found", bool(session.hwnd), str(session.hwnd))
    info = step("new scratch drawing", documents.new_drawing)
    if not info:
        return
    doc = session.find_document(info["name"])
    try:
        frame = step("rectangle 60 x 84", draw.draw_rectangle, [0, 0], [60, 84])
        jamb = step("jamb line", draw.draw_line, [60, 0], [60, 84])
        made = step("-BLOCK with spaces in the name", commands.run, doc, "-BLOCK",
                    [BLOCK, [0, 0], {"handle": frame["handle"]}, {"handle": jamb["handle"]}, ""])
        check("-BLOCK completed", bool(made and made["completed"]), str(made and made.get("problem")))
        if not (made and made["completed"]):
            return
        ref = step("insert the block back", lambda: str(doc.ModelSpace.InsertBlock(
            point([0, 0]), BLOCK, 1.0, 1.0, 1.0, 0.0).Handle))

        before = count_model_space(doc)
        line = step("LINE with too few answers", commands.run, doc, "LINE", [[100, 0], [110, 0]])
        check("LINE was cancelled", bool(line and line["cancelled"]), str(line and line.get("left_waiting_at")))
        check("nothing left behind", count_model_space(doc) == before, f"{before} -> {count_model_space(doc)}")
        check("AutoCAD idle again", int(doc.GetVariable("CMDACTIVE")) == 0)

        erase = step("ERASE with one answer too many", commands.run, doc, "ERASE", [{"handle": ref}, "", "_L"])
        check("ERASE ended early and was undone", bool(erase and erase["ended_early_before_input"] == 3
                                                        and erase["undone"]), str(erase and erase.get("problem")))
        check("block reference still there", count_model_space(doc) == before, f"{count_model_space(doc)}")

        if not step("open the Block Editor", block_editor.open_block_editor, BLOCK):
            return
        param = step("Width parameter", block_editor.add_linear_parameter, "Width", [0, 0], [60, 0], [30, -6])
        if param:
            step("stretch action on the right side", block_editor.add_stretch_action, param["pick_point"],
                 [[55, -10], [70, 94]], location=[65, -12])
        step("close the Block Editor (save)", block_editor.close_block_editor, True)
        result = step("check: Width 72 is 12 wider on the right", block_editor.check_dynamic_block, BLOCK,
                      [{"properties": {"Width": 72}, "expect": {"width": 12, "max_x": 12, "min_x": 0}}])
        check("dynamic block behaves", bool(result and result["passed"]), str(result and result["cases"]))
    finally:
        step("close the scratch drawing", documents.close_document, str(doc.Name), discard_changes=True)


if __name__ == "__main__":
    main()
    sys.exit(harness.finish(REPORT))
