"""Live check of the dynamic block tools (T6 to T10), in ONE new scratch drawing.
Run ONLY after the user has saved open work and said go (knowledge/Decisions/Live test protocol.md):

    .venv\\Scripts\\python.exe -u tests\\live\\dynamic_tools_check.py

 1. New drawing; a 60 x 84 frame, a mullion, a circle; the block "AMCP dyn"; Block Editor.
 2. T10: list_block_editor_objects finds the three objects; their handles are used below.
 3. T7: Width with a value list (48, 60, 72); Height with an increment (6, 72 to 96).
 4. Stretch on the right; T8 move (circle by handle, half the distance, 90 degree offset = T9) and
    scale (circle) on Width.
 5. T8: a flip parameter (vertical line through the middle) with a flip action on everything; a
    rotation parameter at the circle with a rotate action on the circle.
 6. T6: a visibility parameter, states "With circle" and "Plain", the circle hidden in "Plain".
 7. T10 again: the parameters and actions are listed.
 8. Save, close; a placed block must offer Width (48/60/72), the flip, the angle and the two states;
    Width 72 makes it 12 wider on the right; "Plain" shows one object fewer than "With circle".
 9. The scratch drawing is closed without saving; the drawing active before becomes active again.
Output: scratch/<report>.json. Every Block Editor tool restores BACTIONBARMODE itself.
"""

from __future__ import annotations

import os
import sys

import harness
import pythoncom
from harness import check, step

from autocad_mcp.com import MessageFilter, retry_seconds
from autocad_mcp.session import session
from autocad_mcp.tools import block_authoring, block_editor, block_library, blocks, documents, draw

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-20261118-04")
BLOCK = "AMCP dyn"


def main() -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    MessageFilter(retry_seconds()).register()
    session.connect()
    os.makedirs(harness.SCRATCH, exist_ok=True)
    before = str(session.app.ActiveDocument.Name) if session.documents() else ""
    info = step("new scratch drawing", documents.new_drawing)
    if not info:
        return
    name = info["name"]
    doc = session.find_document(name)
    try:
        frame = step("frame 60 x 84", draw.draw_rectangle, [0, 0], [60, 84], name=name)
        mullion = step("mullion", draw.draw_line, [30, 0], [30, 84], name=name)
        circle = step("circle", draw.draw_circle, [30, 42], 5, name=name)
        if not (frame and mullion and circle):
            return
        if not step("define the block", block_library.define_block, BLOCK,
                    [frame["handle"], mullion["handle"], circle["handle"]], [0, 0], name=name):
            return
        if not step("open the Block Editor", block_editor.open_block_editor, BLOCK, name=name):
            return

        # 2. T10
        listed = step("T10: list the editor's objects", block_authoring.list_block_editor_objects, name=name)
        geometry = (listed or {}).get("geometry", [])
        check("T10: three objects listed", len(geometry) == 3, str(geometry))
        ring = next((g["handle"] for g in geometry if g["type"] == "Circle"), None)
        check("T10: the circle is among them", ring is not None)

        # 3. T7
        width = step("T7: Width with a value list", block_editor.add_linear_parameter, "Width", [0, 0], [60, 0],
                     [30, -6], value_list=[48, 60, 72], name=name)
        step("T7: Height with an increment", block_editor.add_linear_parameter, "Height", [0, 0], [0, 84],
             [-6, 42], increment={"step": 6, "min": 72, "max": 96}, name=name)
        if not width:
            return
        pick = width["pick_point"]

        # 4. stretch, move (with offset), scale
        step("stretch on the right", block_editor.add_stretch_action, pick, [[55, -10], [70, 94]],
             location=[65, -12], name=name)
        if ring:
            step("T8/T9: move the circle by half, 90 degree offset", block_authoring.add_action, "move", pick,
                 {"handles": [ring]}, multiplier=0.5, offset=90, location=[25, -20], name=name)
            step("T8: scale the circle with Width", block_authoring.add_action, "scale", pick,
                 {"handles": [ring]}, location=[20, -24], name=name)

        # 5. flip and rotation
        flip = step("T8: flip parameter", block_authoring.add_flip_parameter, "Hand", [30, -12], [30, 96],
                    [36, 100], unflipped="Left", flipped="Right", name=name)
        if flip:
            step("T8: flip action on everything", block_authoring.add_action, "flip", flip["pick_point"],
                 {"crossing": [[-1, -1], [61, 85]]}, location=[40, 100], name=name)
        turn = step("T8: rotation parameter", block_authoring.add_rotation_parameter, "Angle", [30, 42], 8,
                    [30, 56], name=name)
        if turn and ring:
            step("T8: rotate action on the circle", block_authoring.add_action, "rotate", turn["pick_point"],
                 {"handles": [ring]}, location=[45, 54], name=name)

        # 6. T6
        if step("T6: visibility parameter", block_authoring.add_visibility_parameter, [80, 90], "Style", name=name):
            step("T6: state 'With circle'", block_authoring.visibility_state, "new", "With circle", name=name)
            step("T6: state 'Plain'", block_authoring.visibility_state, "new", "Plain", name=name)
            if ring:
                step("T6: hide the circle in 'Plain'", block_authoring.set_object_visibility, {"handles": [ring]},
                     False, name=name)

        # 7. T10 again
        listed = step("T10: list parameters and actions", block_authoring.list_block_editor_objects,
                      ["parameters", "actions"], name=name)
        kinds = {p["type"] for p in (listed or {}).get("parameters", [])}
        check("T10: the parameters are listed", {"LinearParameter", "FlipParameter", "RotationParameter",
                                                 "VisibilityParameter"} <= kinds, str(sorted(kinds)))
        check("T10: the actions are listed", len((listed or {}).get("actions", [])) >= 5,
              str([a["type"] for a in (listed or {}).get("actions", [])]))

        # 8. save, place, check
        step("close the Block Editor (save)", block_editor.close_block_editor, True, name=name)
        placed = step("place the block", blocks.insert_block, BLOCK, [200, 0], name=name)
        if placed:
            props = step("its properties", blocks.get_block_properties, placed["handle"], name=name)
            offered = {p["name"]: p for p in (props or {}).get("properties", [])}
            check("T7: Width offers 48, 60, 72", offered.get("Width", {}).get("allowed") == [48.0, 60.0, 72.0],
                  str(offered.get("Width")))
            check("T8: the flip is offered", "Hand" in offered, str(sorted(offered)))
            check("T8: the angle is offered", "Angle" in offered, str(offered.get("Angle")))
            states = offered.get("Style", {}).get("allowed", [])
            check("T6: both states offered", {"With circle", "Plain"} <= set(states), str(states))
            counts = {}
            for state in ("With circle", "Plain"):
                if step(f"T6: show '{state}'", blocks.set_block_properties, placed["handle"], {"Style": state},
                        name=name):
                    measured = step(f"T6: measure '{state}'", blocks.measure_block, placed["handle"], name=name)
                    counts[state] = sum((measured or {}).get("counts", {}).values())
            check("T6: 'Plain' shows the circle hidden", bool(counts) and counts.get("Plain") != counts.get(
                "With circle"), str(counts))
        result = step("check: Width 72 is 12 wider on the right", block_editor.check_dynamic_block, BLOCK,
                      [{"properties": {"Width": 72}, "expect": {"width": 12, "max_x": 12, "min_x": 0}}],
                      position=[0, -200], name=name)
        check("the block behaves", bool(result and result["passed"]), str(result and result["cases"]))
    finally:
        try:
            editor_open = int(doc.GetVariable("BLOCKEDITOR")) == 1
        except Exception:  # noqa: BLE001
            editor_open = False
        if editor_open:
            step("close the Block Editor (discard)", block_editor.close_block_editor, False, name=name)
        step("close the scratch drawing", documents.close_document, str(doc.Name), discard_changes=True)
        if before and any(str(d.Name) == before for d in session.documents()):
            step("switch back to the drawing that was active", documents.activate_document, before)


if __name__ == "__main__":
    try:
        main()
    finally:  # the results are written even if a step crashed
        code = harness.finish(REPORT)
    sys.exit(code)
