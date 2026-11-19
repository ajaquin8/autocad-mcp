"""Discovery batch for the dynamic block tools (T6 to T10): records AutoCAD's real Block Editor prompts
and where the Block Editor's objects can be read from, in ONE new scratch drawing.
Run ONLY after the user has saved open work and said go (knowledge/Decisions/Live test protocol.md):

    .venv\\Scripts\\python.exe -u tests\\live\\block_editor_probe.py

Nothing here is a pass/fail test of a tool: each probe is one run_command call whose transcript (every
prompt AutoCAD showed) is saved. A probe whose answers do not fit is cancelled and put back by
run_command, so a wrong guess costs nothing. Steps:
 1. New drawing; a 60 x 84 frame, a mullion, a circle; made into the block "AMCP probe"; Block Editor.
 2. T10 (answered by AMCP-LIVE-20261118-02: COM's ModelSpace holds the Block Editor's objects, with
    new handles): what COM sees, read again at the end. No SELECT probe: in -02 a SELECT left AutoCAD
    waiting at a prompt right after it ended.
 3. T7: linear parameters with a value list and with an increment.
 4. T6: a visibility parameter, -BVSTATE New/Set, BVHIDE and BVSHOW.
 5. T8: a flip parameter and flip action; a rotation parameter and rotate action; scale and move actions.
 6. T9: a move action and a stretch action with an angle offset.
 7. BSAVE/BCLOSE, then the block's dynamic properties as a placed reference shows them.
 8. The scratch drawing is closed without saving; the drawing active before becomes active again.
Output: scratch/<report>.json (results) and scratch/<report>-transcripts.json (every probe's prompts).
"""

from __future__ import annotations

import json
import os
import sys

import harness
import pythoncom
from harness import check, step

from autocad_mcp.com import MessageFilter, point, retry_seconds
from autocad_mcp.session import session
from autocad_mcp.tools import block_editor, block_library, blocks, commands, documents, draw

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-20261118-03")
BLOCK = "AMCP probe"
TRANSCRIPTS: dict[str, dict] = {}


def probe(doc, label: str, command: str, inputs: list) -> dict | None:
    """One command; the whole result (prompts, where it stopped) is kept whatever happened."""
    try:
        result = commands.run(doc, command, inputs)
    except Exception as err:  # noqa: BLE001 - recorded, the batch goes on
        TRANSCRIPTS[label] = {"command": command, "inputs": inputs, "error": f"{type(err).__name__}: {err}"}
        check(f"probe {label}", False, str(err)[:300])
        return None
    TRANSCRIPTS[label] = {"command": command, "inputs": inputs, **result}
    check(f"probe {label}", bool(result["completed"]),
          result.get("problem") or f"{len(result['steps'])} prompts")
    return result


def com_view(doc) -> dict:
    """What COM reports inside the Block Editor."""
    view: dict = {}
    for label, read in [
        ("BLOCKEDITOR", lambda: doc.GetVariable("BLOCKEDITOR")),
        ("ActiveSpace", lambda: doc.ActiveSpace),
        ("ModelSpace.Name", lambda: doc.ModelSpace.Name),
        ("ModelSpace.ObjectID", lambda: doc.ModelSpace.ObjectID),
        ("ModelSpace.Count", lambda: doc.ModelSpace.Count),
        ("Block.ObjectID", lambda: doc.Blocks.Item(BLOCK).ObjectID),
        ("Block.Count", lambda: doc.Blocks.Item(BLOCK).Count),
        ("ActiveLayout.Name", lambda: doc.ActiveLayout.Name),
        ("ActiveLayout.Block.Name", lambda: doc.ActiveLayout.Block.Name),
        ("ActiveLayout.Block.ObjectID", lambda: doc.ActiveLayout.Block.ObjectID),
    ]:
        try:
            view[label] = str(read())
        except Exception as err:  # noqa: BLE001
            view[label] = f"error: {err}"
    try:
        sets = doc.SelectionSets
        for i in range(sets.Count):
            if str(sets.Item(i).Name) == "AMCPPROBE":
                sets.Item(i).Delete()
                break
        ss = sets.Add("AMCPPROBE")
        try:
            ss.Select(5)  # acSelectionSetAll
            view["select_all"] = [{"handle": str(ss.Item(i).Handle), "type": str(ss.Item(i).ObjectName),
                                   "owner": str(ss.Item(i).OwnerID)} for i in range(ss.Count)]
        finally:
            ss.Delete()
    except Exception as err:  # noqa: BLE001
        view["select_all"] = f"error: {err}"
    return view


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
    old_mode = None
    try:
        # 1. the block
        frame = step("frame 60 x 84", draw.draw_rectangle, [0, 0], [60, 84], name=name)
        mullion = step("mullion", draw.draw_line, [30, 0], [30, 84], name=name)
        circle = step("circle", draw.draw_circle, [30, 42], 5, name=name)
        if not (frame and mullion and circle):
            return
        made = step("define the block", block_library.define_block, BLOCK,
                    [frame["handle"], mullion["handle"], circle["handle"]], [0, 0], name=name)
        if not made:
            return
        TRANSCRIPTS["model_space_handles"] = {"frame": frame["handle"], "circle": circle["handle"]}
        if not step("open the Block Editor", block_editor.open_block_editor, BLOCK, name=name):
            return
        old_mode = doc.GetVariable("BACTIONBARMODE")
        TRANSCRIPTS["BACTIONBARMODE_before"] = str(old_mode)
        doc.SetVariable("BACTIONBARMODE", 0)
        session.app.ZoomWindow(point([-40, -40]), point([140, 120]))

        # 2. T10: the editor's objects as COM lists them (the circle's handle is used by BVSHOW below)
        view = com_view(doc)
        TRANSCRIPTS["com_in_editor_before"] = view
        listed = view.get("select_all") if isinstance(view.get("select_all"), list) else []
        circles = [i["handle"] for i in listed if i["type"] == "AcDbCircle"]

        # 3. T7 value sets (documented options: Value set -> List / Increment)
        probe(doc, "linear with value list", "BPARAMETER",
              ["_L", "_L", "Width", "_V", "_L", "48,60,72", [0, 0], [60, 0], [30, -6], "1"])
        probe(doc, "linear with increment", "BPARAMETER",
              ["_L", "_L", "Height", "_V", "_I", 6, 72, 96, [0, 0], [0, 84], [-6, 42], "1"])

        # 4. T6 visibility
        probe(doc, "visibility parameter", "BPARAMETER", ["_V", "_L", "Size", [80, 90], "1"])
        probe(doc, "-BVSTATE New current", "-BVSTATE", ["_N", "Small", "_C"])
        probe(doc, "-BVSTATE New show all", "-BVSTATE", ["_N", "Large", "_S"])
        probe(doc, "-BVSTATE Set", "-BVSTATE", ["_S", "Small"])
        probe(doc, "BVHIDE crossing current", "BVHIDE", [{"crossing": [[24, 36], [36, 48]]}, "", "_C"])
        if circles:
            probe(doc, "BVSHOW by handle all states", "BVSHOW", [{"handles": [circles[0]]}, "", "_A"])
        probe(doc, "-BVSTATE Delete", "-BVSTATE", ["_D", "Large"])

        # 5. T8 flip, rotation, scale, move
        probe(doc, "flip parameter", "BPARAMETER", ["_F", "_L", "Mirror", [0, -12], [60, -12], [30, -16]])
        probe(doc, "flip action", "BACTION", [[15, -12], {"crossing": [[-1, -1], [61, 85]]}, "", [70, -12]])
        probe(doc, "rotation parameter", "BPARAMETER", ["_R", "_L", "Angle", [30, 42], 10, 0, [30, 56]])
        probe(doc, "rotate action", "BACTION", [[40, 42], {"crossing": [[24, 36], [36, 48]]}, "", [45, 50]])
        probe(doc, "scale action", "BACTION", [[15, -6], "_S", {"crossing": [[24, 36], [36, 48]]}, "", [20, -20]])
        probe(doc, "move action", "BACTION",
              [[15, -6], "_M", "_S", {"crossing": [[24, 36], [36, 48]]}, "", [25, -20]])

        # 6. T9 angle offset
        probe(doc, "move action with offset", "BACTION",
              [[15, -6], "_M", "_S", {"crossing": [[24, 36], [36, 48]]}, "", "_O", 90, [35, -20]])
        probe(doc, "stretch action with offset", "BACTION",
              [[15, -6], "_T", "_S", [55, -10], [70, 94], {"crossing": [[55, -10], [70, 94]]}, "", "_O", 90,
               [65, -20]])
        TRANSCRIPTS["com_in_editor_end"] = com_view(doc)

        # 7. save and look at what a placed reference offers
        step("close the Block Editor (save)", block_editor.close_block_editor, True, name=name)
        placed = step("place the block", blocks.insert_block, BLOCK, [200, 0], name=name)
        if placed:
            props = step("its dynamic properties", blocks.get_block_properties, placed["handle"],
                         include_hidden=True, name=name)
            TRANSCRIPTS["placed_properties"] = props
    finally:
        if old_mode is not None:
            try:
                doc.SetVariable("BACTIONBARMODE", old_mode)
            except Exception:  # noqa: BLE001
                pass
        with open(os.path.join(harness.SCRATCH, f"{REPORT}-transcripts.json"), "w", encoding="utf-8") as fh:
            json.dump(TRANSCRIPTS, fh, indent=1, default=str)
        try:
            editor_open = int(doc.GetVariable("BLOCKEDITOR")) == 1
        except Exception:  # noqa: BLE001
            editor_open = False
        if editor_open:  # leave it without saving first, so closing the drawing raises no dialog
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
