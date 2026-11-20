"""Live check of B4 (flip states set by set_block_properties) and T11 (order_visibility_states), in ONE
new scratch drawing. Run ONLY after the user has saved open work and said go
(knowledge/Decisions/Live test protocol.md):

    .venv\\Scripts\\python.exe -u tests\\live\\flip_and_state_order_check.py

 1. New drawing; a 60 x 84 frame and a circle; the block "AMCP order"; Block Editor.
 2. A flip parameter "Hand" with a flip action on everything; a visibility parameter "Style" with
    the states "With circle" and "Plain" (circle hidden in "Plain") after "VisibilityState0".
 3. Save; a placed block lists VisibilityState0, With circle, Plain, and shows VisibilityState0.
 4. B4: set Hand to 1, then to "not flipped"; each reads back; a refused value puts Hand back.
 5. T11: default "Plain", then the full order back; a new copy shows "Plain" first; "Plain" still
    hides the circle and "With circle" still shows it (the rebuilt states kept their objects).
 6. The scratch drawing is closed without saving; the drawing active before becomes active again.
Output: scratch/<report>.json.
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

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-YYYYMMDD-NN")
BLOCK = "AMCP order"


def shown(handle: str, name: str) -> int:
    measured = step("measure", blocks.measure_block, handle, name=name)
    return sum((measured or {}).get("counts", {}).values())


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
        circle = step("circle", draw.draw_circle, [30, 42], 5, name=name)
        if not (frame and circle):
            return
        if not step("define the block", block_library.define_block, BLOCK, [frame["handle"], circle["handle"]],
                    [0, 0], name=name):
            return
        if not step("open the Block Editor", block_editor.open_block_editor, BLOCK, name=name):
            return
        listed = step("list the editor's objects", block_authoring.list_block_editor_objects, name=name)
        ring = next((g["handle"] for g in (listed or {}).get("geometry", []) if g["type"] == "Circle"), None)
        flip = step("flip parameter", block_authoring.add_flip_parameter, "Hand", [30, -12], [30, 96], [36, 100],
                    name=name)
        if flip:
            step("flip action on everything", block_authoring.add_action, "flip", flip["pick_point"],
                 {"crossing": [[-1, -1], [61, 85]]}, location=[40, 100], name=name)
        if step("visibility parameter", block_authoring.add_visibility_parameter, [80, 90], "Style", name=name):
            step("state 'With circle'", block_authoring.visibility_state, "new", "With circle", name=name)
            step("state 'Plain'", block_authoring.visibility_state, "new", "Plain", name=name)
            if ring:
                step("hide the circle in 'Plain'", block_authoring.set_object_visibility, {"handles": [ring]},
                     False, name=name)
        step("close the Block Editor (save)", block_editor.close_block_editor, True, name=name)

        placed = step("place the block", blocks.insert_block, BLOCK, [200, 0], name=name)
        if not placed:
            return
        handle = placed["handle"]
        props = {p["name"]: p for p in (step("its properties", blocks.get_block_properties, handle, name=name)
                                        or {}).get("properties", [])}
        check("states listed in creation order", props.get("Style", {}).get("allowed") ==
              ["VisibilityState0", "With circle", "Plain"], str(props.get("Style")))
        check("the first state is the default", props.get("Style", {}).get("value") == "VisibilityState0",
              str(props.get("Style")))

        # 4. B4
        check("Hand is offered", "Hand" in props, str(sorted(props)))
        out = step("B4: Hand = 1", blocks.set_block_properties, handle, {"Hand": 1}, name=name)
        value = {p["name"]: p["value"] for p in (out or {}).get("properties", [])}.get("Hand")
        check("B4: Hand reads back 1", value == 1, str(value))
        out = step("B4: Hand = 'not flipped'", blocks.set_block_properties, handle, {"Hand": "not flipped"},
                   name=name)
        value = {p["name"]: p["value"] for p in (out or {}).get("properties", [])}.get("Hand")
        check("B4: Hand reads back 0", value == 0, str(value))
        try:
            blocks.set_block_properties(handle, {"Hand": 1, "Style": "No such state"}, name=name)
            check("B4: a refused value is reported", False)
        except Exception as err:  # noqa: BLE001
            check("B4: a refused value is reported", "not an allowed" in str(err), str(err)[:200])
        props = {p["name"]: p for p in blocks.get_block_properties(handle, name=name)["properties"]}
        check("B4: the rollback put Hand back to 0", props["Hand"]["value"] == 0, str(props["Hand"]))

        counts = {}
        for state in ("With circle", "Plain"):
            if step(f"show '{state}' (before)", blocks.set_block_properties, handle, {"Style": state}, name=name):
                counts[state] = shown(handle, name)

        # 5. T11
        out = step("T11: default 'Plain'", block_authoring.order_visibility_states, BLOCK, default="Plain",
                   name=name)
        check("T11: Plain is first", bool(out) and out["states"] == ["Plain", "VisibilityState0", "With circle"]
              and "problem" not in out, str(out and out.get("states")))
        fresh = step("place a new copy", blocks.insert_block, BLOCK, [300, 0], name=name)
        if fresh:
            props = {p["name"]: p for p in blocks.get_block_properties(fresh["handle"], name=name)["properties"]}
            check("T11: a new copy shows 'Plain'", props.get("Style", {}).get("value") == "Plain",
                  str(props.get("Style")))
            for state in ("With circle", "Plain"):
                if step(f"show '{state}' (after)", blocks.set_block_properties, fresh["handle"], {"Style": state},
                        name=name):
                    now = shown(fresh["handle"], name)
                    check(f"T11: '{state}' shows what it showed before", now == counts.get(state),
                          f"before {counts.get(state)}, after {now}")
        out = step("T11: the old order back", block_authoring.order_visibility_states, BLOCK,
                   ["VisibilityState0", "With circle", "Plain"], name=name)
        check("T11: the old order is back", bool(out) and out["default"] == "VisibilityState0",
              str(out and out.get("states")))
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
