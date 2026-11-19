"""Live check of the 2026-11-18 improvements (T1, T2, T3, T5, B1, B2, B3, B6), all in scratch drawings.
Run ONLY after the user has saved open work and said go (knowledge/Decisions/Live test protocol.md):

    .venv\\Scripts\\python.exe -u tests\\live\\improvements_check.py

Never touches the user's drawings: everything is drawn in new drawings this script creates. At the
very end it switches back to the drawing that was active before (a tab switch only, nothing changed).

 A. Library drawing (new):
    1. T2/T5: a 60 x 84 unit (frame, jamb, mullion, a centred MARK attribute) made into the block
       "AMCP lib unit" with define_block; a tag (circle and centred text in a new text style) made
       into "AMCP lib tag" with originals="replace". T5: the text's alignment point and the MTEXT
       attachment point read back where they were put.
    2. B6: with the first sheet tab active, draw_line must say it went into model space; draw_circle
       with layout= must land on the sheet. The Model tab is made active again.
    3. B2/B1: Block Editor on the unit: Width parameter, a stretch on the right; a stretch with a
       model-space handle (must be refused before BACTION starts); a centred stretch with
       multiplier 0.5 and its badge far off screen (must complete, view widened). Save, close,
       check_dynamic_block: Width 72 is 12 wider on the right.
    4. B3: run_command DELAY 3000 with a 1 s timeout: must be cancelled by the server, AutoCAD idle.
    5. Saved as scratch/<report>-library.dwg and closed.
 B. Target drawing (new):
    6. An old, plain "AMCP lib unit" (40 x 40) placed once in model space and once nested in "AMCP
       legend". T3: import without overwrite skips it; with overwrite it is replaced, both references
       switched, "AMCP lib tag" brought in. The placed unit is set to Width 72; a second overwrite
       must keep Width 72. check_dynamic_block on the imported unit.
    7. T1: a second new drawing becomes active; run_command in the first must point to
       activate_document; activate_document switches back; REGEN then runs there.
 C. Closes the scratch drawings without saving and switches back to the drawing that was active.
Output: scratch/<report>.json. Stops early, with a message, if AutoCAD is left busy.
"""

from __future__ import annotations

import os
import sys

import harness
import pythoncom
from harness import check, step

from autocad_mcp.com import MessageFilter, retry_seconds
from autocad_mcp.session import session
from autocad_mcp.tools import block_editor, block_library, blocks, commands, documents, draw, settings

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-20261118-01")
LIBRARY = os.path.join(harness.SCRATCH, f"{REPORT}-library.dwg")
UNIT, TAG, LEGEND = "AMCP lib unit", "AMCP lib tag", "AMCP legend"
STYLE = "AMCP-NOTES"
OPENED: list = []  # the scratch drawings this script created and still has open (closed at the end)


class Stop(Exception):
    """AutoCAD was left in a state the rest of the batch should not run in."""


def idle(doc, after: str) -> None:
    try:
        ok = int(doc.GetVariable("CMDACTIVE")) == 0
        detail = ""
    except Exception as err:  # noqa: BLE001
        ok, detail = False, str(err)
    check(f"AutoCAD idle after {after}", ok, detail)
    if not ok:
        raise Stop(f"AutoCAD is not idle after {after}. Call cancel_command (or press Esc in the scratch "
                   "drawing), then check acad_status.")


def handle_of(result) -> str:
    if not result:
        raise Stop("a step that later steps need failed")
    return result["handle"]


def width_of(name: str, handle: str):
    props = blocks.get_block_properties(handle, name=name)["properties"]
    return next((p["value"] for p in props if p["name"].lower() == "width"), None)


def first_sheet(doc):
    layouts = [doc.Layouts.Item(i) for i in range(doc.Layouts.Count)]
    sheets = sorted((lay for lay in layouts if not bool(lay.ModelType)), key=lambda lay: int(lay.TabOrder))
    model = next(lay for lay in layouts if bool(lay.ModelType))
    return sheets[0], model


def library_drawing() -> None:
    info = step("new library drawing", documents.new_drawing)
    if not info:
        raise Stop("no library drawing")
    lib = info["name"]
    doc = session.find_document(lib)
    OPENED.append(doc)
    try:
        # 1. T2 and T5
        frame = handle_of(step("frame 60 x 84", draw.draw_rectangle, [0, 0], [60, 84], name=lib))
        jamb = handle_of(step("jamb", draw.draw_line, [60, 0], [60, 84], name=lib))
        mullion = handle_of(step("mullion", draw.draw_line, [30, 0], [30, 84], name=lib))
        mark = step("T5: MARK attribute centred", blocks.add_attribute_definition, "MARK", [30, 42], 3,
                    justify="MC", name=lib)
        check("T5: attribute justified middle_center", bool(mark and mark.get("justify") == "middle_center"))
        made = step("T2: define_block unit", block_library.define_block, UNIT,
                    [frame, jamb, mullion, handle_of(mark)], [0, 0], name=lib)
        check("T2: four objects in the unit", bool(made and made["objects"] == 4), str(made))
        listed = {b["name"]: b for b in blocks.list_blocks(name=lib)}
        check("T2: unit listed with its MARK attribute", listed.get(UNIT, {}).get("attribute_tags") == ["MARK"],
              str(listed.get(UNIT)))
        step("text style for the tag", settings.add_text_style, STYLE, font="romans.shx", name=lib)
        circle = handle_of(step("tag circle", draw.draw_circle, [100, 0], 5, name=lib))
        text = step("T5: tag text centred, in the new style", draw.add_text, "T1", [100, 0], 4, justify="MC",
                    style=STYLE, name=lib)
        ent = doc.HandleToObject(handle_of(text))
        lo, hi = ent.GetBoundingBox()
        centre = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
        check("T5: text centred on [100, 0]", abs(centre[0] - 100) < 1.0 and abs(centre[1]) < 1.0, str(centre))
        check("T5: text in the new style", str(ent.StyleName).upper() == STYLE, str(ent.StyleName))
        mtext = step("T5: MTEXT attached middle-centre", draw.add_mtext, "LIVING", [100, 30], 20,
                     attachment="MC", name=lib)
        point = tuple(doc.HandleToObject(handle_of(mtext)).InsertionPoint)[:2]
        check("T5: MTEXT attachment point stayed at [100, 30]", abs(point[0] - 100) < 1e-6
              and abs(point[1] - 30) < 1e-6, str(point))
        tag = step("T2: define_block tag, originals replaced", block_library.define_block, TAG,
                   [circle, handle_of(text)], [100, 0], originals="replace", name=lib)
        check("T2: tag replaced by one reference", bool(tag and tag.get("reference")), str(tag))
        idle(doc, "part 1")

        # 2. B6
        sheet, model = first_sheet(doc)
        doc.ActiveLayout = sheet
        line = step("B6: draw_line with a sheet tab active", draw.draw_line, [0, -20], [10, -20], name=lib)
        check("B6: result says model space, with a note", bool(line and line.get("space") == "model"
                                                               and "note" in line), str(line and line.get("note")))
        on_sheet = step("B6: draw_circle on the sheet", draw.draw_circle, [2, 2], 0.5, layout=str(sheet.Name),
                        name=lib)
        owner_ok = bool(on_sheet) and int(doc.HandleToObject(on_sheet["handle"]).OwnerID) == int(sheet.Block.ObjectID)
        check("B6: circle is on the sheet's paper space", owner_ok and on_sheet.get("space") == "paper")
        doc.ActiveLayout = model
        idle(doc, "part 2")

        # 3. B2 and B1 in the Block Editor
        step("lock attribute positions", block_editor.lock_attribute_positions, UNIT, name=lib)
        if not step("open the Block Editor", block_editor.open_block_editor, UNIT, name=lib):
            raise Stop("the Block Editor did not open")
        param = step("Width parameter", block_editor.add_linear_parameter, "Width", [0, 0], [60, 0], [30, -6],
                     name=lib)
        if not param:
            raise Stop("no Width parameter")
        pick = param["pick_point"]
        step("stretch on the right", block_editor.add_stretch_action, pick, [[55, -10], [70, 94]],
             location=[65, -12], name=lib)
        idle(doc, "the right stretch")
        step("B2: model-space handle refused", block_editor.add_stretch_action, pick, [[25, -10], [35, 94]],
             select={"handles": [frame]}, name=lib, expect_error="not in the block being edited")
        idle(doc, "the refused handle (B2)")
        centred = step("B1: centred stretch, multiplier 0.5, badge off screen", block_editor.add_stretch_action,
                       pick, [[25, -10], [35, 94]], multiplier=0.5, location=[400, -300], name=lib)
        check("B1: view widened for the badge", bool(centred and centred["zoom"].startswith("extents, widened")),
              str(centred and centred.get("zoom")))
        idle(doc, "the centred stretch (B1)")
        step("close the Block Editor (save)", block_editor.close_block_editor, True, name=lib)
        result = step("check: Width 72 is 12 wider on the right", block_editor.check_dynamic_block, UNIT,
                      [{"properties": {"Width": 72}, "expect": {"width": 12, "max_x": 12, "min_x": 0}}], name=lib)
        check("unit behaves", bool(result and result["passed"]), str(result and result["cases"]))
        idle(doc, "part 3")

        # 4. B3
        step("B3: DELAY 3000 with a 1 s timeout is cancelled", commands.run, doc, "DELAY", [3000],
             timeout_seconds=1, expect_error="cancelled it")
        idle(doc, "the cancelled DELAY (B3)")

        # 5. save the library
        step("save the library", documents.save_document, LIBRARY, overwrite=True, name=lib)
    finally:
        OPENED.remove(doc)
        step("close the library drawing", documents.close_document, str(doc.Name), discard_changes=True)


def target_drawing() -> None:
    info = step("new target drawing", documents.new_drawing)
    if not info:
        raise Stop("no target drawing")
    target = info["name"]
    doc = session.find_document(target)
    OPENED.append(doc)
    # 6. T3
    old = handle_of(step("old plain unit 40 x 40", draw.draw_rectangle, [0, 0], [40, 40], name=target))
    placed = step("old unit as a block, placed", block_library.define_block, UNIT, [old], [0, 0],
                  originals="replace", name=target)
    unit_ref = placed["reference"] if placed else None
    nested = handle_of(step("a second old unit", blocks.insert_block, UNIT, [200, 0], name=target))
    step("legend block holding it", block_library.define_block, LEGEND, [nested], [200, 0], originals="replace",
         name=target)
    skipped = step("T3: import without overwrite", block_library.import_blocks, LIBRARY, [UNIT], name=target)
    check("T3: existing unit skipped", bool(skipped and skipped["skipped_existing"] == [UNIT]), str(skipped))
    first = step("T3: import with overwrite", block_library.import_blocks, LIBRARY, [UNIT, TAG], overwrite=True,
                 name=target)
    check("T3: unit replaced, tag imported, two references switched",
          bool(first and first["replaced"] == [UNIT] and first["imported"] == [TAG]
               and first["references_switched"] == 2), str(first))
    check("T3: old definition deleted", bool(first) and "old_definitions_left" not in first,
          str(first and first.get("old_definitions_left")))
    listed = {b["name"]: b for b in blocks.list_blocks(name=target)}
    check("T3: unit is dynamic now", bool(listed.get(UNIT, {}).get("dynamic")), str(listed.get(UNIT)))
    idle(doc, "the first import")
    if unit_ref:
        step("placed unit set to Width 72", blocks.set_block_properties, unit_ref, {"Width": 72}, name=target)
        second = step("T3: overwrite again (dynamic over dynamic)", block_library.import_blocks, LIBRARY, [UNIT],
                      overwrite=True, name=target)
        check("T3: second overwrite switched the references", bool(second and second["references_switched"] == 2),
              str(second))
        check("T3: Width 72 kept", width_of(target, unit_ref) == 72, str(width_of(target, unit_ref)))
        check("T3: old dynamic definition deleted", bool(second) and "old_definitions_left" not in second,
              str(second and second.get("old_definitions_left")))
    result = step("check the imported unit", block_editor.check_dynamic_block, UNIT,
                  [{"properties": {"Width": 72}, "expect": {"width": 12, "max_x": 12, "min_x": 0}}],
                  position=[0, -200], name=target)
    check("imported unit behaves", bool(result and result["passed"]), str(result and result["cases"]))
    idle(doc, "part 6")

    # 7. T1
    other = step("another new drawing (becomes active)", documents.new_drawing)
    if other:
        OPENED.append(session.find_document(other["name"]))
        step("T1: run_command in the inactive drawing points to activate_document", commands.run, doc, "REGEN",
             expect_error="activate_document")
        switched = step("T1: activate_document", documents.activate_document, target)
        check("T1: the target is the active drawing", str(session.app.ActiveDocument.Name) == target,
              str(switched))
        regen = step("T1: REGEN runs there now", commands.run, doc, "REGEN")
        check("T1: REGEN completed", bool(regen and regen["completed"]), str(regen and regen.get("problem")))


def main() -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    MessageFilter(retry_seconds()).register()
    session.connect()
    os.makedirs(harness.SCRATCH, exist_ok=True)
    before = str(session.app.ActiveDocument.Name) if session.documents() else ""
    check("AutoCAD window found", bool(session.hwnd), f"active before: {before!r}")
    try:
        library_drawing()
        target_drawing()
    except Stop as stop:
        check("batch stopped early", False, str(stop))
        print("\nSTOPPED:", stop)
    finally:
        for doc in list(OPENED):
            step(f"close {doc.Name}", documents.close_document, str(doc.Name), discard_changes=True)
        if before and any(str(d.Name) == before for d in session.documents()):
            step("switch back to the drawing that was active", documents.activate_document, before)


if __name__ == "__main__":
    main()
    sys.exit(harness.finish(REPORT))
