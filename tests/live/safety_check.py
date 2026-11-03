"""AMCP-LIVE-20261103-03: the safety promises in INSTALL.md, plus blocks, edits and open/close.
Run ONLY after the user has saved open work and said go, one phase at a time:

    .venv\\Scripts\\python.exe tests\\live\\safety_check.py tools        # no user action needed
    .venv\\Scripts\\python.exe tests\\live\\safety_check.py undo-prepare # then the user presses Ctrl+Z once
    .venv\\Scripts\\python.exe tests\\live\\safety_check.py undo-check   # then Ctrl+Z once more
    .venv\\Scripts\\python.exe tests\\live\\safety_check.py undo-check2
    .venv\\Scripts\\python.exe tests\\live\\safety_check.py busy         # while the user is inside LINE
    .venv\\Scripts\\python.exe tests\\live\\safety_check.py busy         # again with a modal dialog open
    .venv\\Scripts\\python.exe tests\\live\\safety_check.py idle         # after Esc / closing the dialog
    .venv\\Scripts\\python.exe tests\\live\\safety_check.py cleanup      # closes the scratch drawing

Calls the tool functions directly (no MCP client) and works only in new scratch drawings; the
user's own drawings are only read, and two edits on them are attempted to prove they are refused.
Each phase is its own process, so a later phase re-marks the scratch drawing it created earlier
(recorded in scratch/<report>-state.json) as created by this server. Output goes to scratch/.
"""

from __future__ import annotations

import json
import os
import sys

import harness
from harness import SCRATCH, check, step

from autocad_mcp.session import session
from autocad_mcp.tools import blocks, documents, draw, edit, layers, query

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-20261103-03")
STATE = os.path.join(SCRATCH, f"{REPORT}-state.json")


def load_state() -> dict:
    if not os.path.exists(STATE):
        return {}
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state: dict) -> None:
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)


def scratch_drawing(state: dict) -> str:
    """The undo/busy scratch drawing from undo-prepare, marked as ours again in this process."""
    name = state["undo_drawing"]
    session.mark_owned(session.find_document(name))
    return name


def user_drawings() -> list[dict]:
    status = documents.acad_status()
    return [d for d in status["open_drawings"] if not d["created_by_mcp"]]


def _exists(handle: str, name: str) -> dict | None:
    try:
        return query.get_entity(handle, name=name)
    except Exception:  # noqa: BLE001 - gone is a valid answer here
        return None


def need(value, what: str):
    """Stop the phase when a step it depends on failed (the failure is already recorded)."""
    if value is None:
        raise SystemExit(harness.finish(f"{REPORT}-stopped") or f"stopped: {what} failed")
    return value


def define_tag_block(name: str) -> str:
    """Test setup in our own scratch drawing: a block with two attributes (no tool defines blocks)."""
    from autocad_mcp.com import point

    doc = session.find_document(name)
    with session.edit(doc):
        block = doc.Blocks.Add(point([0, 0]), "AMCP-TAG")
        block.AddCircle(point([0, 0]), 1.0)
        block.AddAttribute(0.25, 0, "Mark", point([-0.5, 0.1]), "MARK", "W000")
        block.AddAttribute(0.2, 0, "Size", point([-0.5, -0.4]), "SIZE", "0x0")
    return "AMCP-TAG defined"


def phase_tools(state: dict) -> None:
    theirs = user_drawings()
    check("user drawings are all locked", not any(d["editable"] for d in theirs), f"{len(theirs)} open")
    before = {d["name"]: d["unsaved_changes"] for d in theirs}

    # -- the edit guard, on a real user drawing (both refused before anything changes)
    if theirs:
        target = theirs[0]["name"]
        step("draw on a user drawing is refused", draw.draw_line, [0, 0], [1, 1], name=target,
             expect_error="is locked")
        step("close a user drawing is refused", documents.close_document, target,
             expect_error="not created by this server")
    else:
        check("edit guard on a user drawing", True, "skipped: no user drawing open")

    # -- blocks and attributes
    a = need(step("new_drawing (blocks/edits)", documents.new_drawing), "new_drawing")["name"]
    need(step("define block AMCP-TAG (test setup, direct COM)", define_tag_block, a), "block setup")
    names = [b["name"] for b in step("list_blocks", blocks.list_blocks, name=a) or []]
    check("list_blocks shows AMCP-TAG", "AMCP-TAG" in names, str(names))
    ref = need(step("insert_block with attributes", blocks.insert_block, "AMCP-TAG", [10, 10],
                    attribute_values={"MARK": "W101", "SIZE": "36x48"}, name=a), "insert_block")
    got = query.get_entity(ref["handle"], name=a)
    check("attributes read back", got.get("attributes") == {"MARK": "W101", "SIZE": "36x48"},
          str(got.get("attributes")))
    step("set_block_attributes MARK=W102", blocks.set_block_attributes, ref["handle"], {"MARK": "W102"}, name=a)
    got = query.get_entity(ref["handle"], name=a)
    check("changed attribute read back", got.get("attributes", {}).get("MARK") == "W102", str(got.get("attributes")))
    count = query.query_entities(name=a)["matches"]
    step("insert_block with an unknown tag is refused", blocks.insert_block, "AMCP-TAG", [20, 10],
         attribute_values={"NOPE": "x"}, name=a, expect_error="has no attribute")
    check("refused insert left nothing behind", query.query_entities(name=a)["matches"] == count)

    # -- move, change, delete
    line = need(step("draw_line", draw.draw_line, [0, 0], [4, 0], name=a), "draw_line")
    circle = need(step("draw_circle", draw.draw_circle, [10, 0], 2, name=a), "draw_circle")
    step("move_entities line +5,+1", edit.move_entities, line["handle"], [5, 1], name=a)
    got = query.get_entity(line["handle"], name=a)
    check("line moved", got["start"][:2] == [5, 1] and got["end"][:2] == [9, 1], f"{got['start']} {got['end']}")
    step("add_layer A-TEST", layers.add_layer, "A-TEST", color=3, name=a)
    step("change_properties circle -> A-TEST, red", edit.change_properties, circle["handle"], layer="A-TEST",
         color=1, name=a)
    got = query.get_entity(circle["handle"], name=a)
    check("circle layer and color changed", got["layer"] == "A-TEST" and got["color"] == 1, f"{got['layer']} {got['color']}")
    step("change_properties to a missing layer is refused", edit.change_properties,
         [line["handle"], circle["handle"]], layer="NOPE", name=a, expect_error="No layer named")
    got_line, got_circle = query.get_entity(line["handle"], name=a), query.get_entity(circle["handle"], name=a)
    check("refused change left both as they were", got_line["layer"] == "0" and got_circle["layer"] == "A-TEST",
          f"{got_line['layer']} {got_circle['layer']}")
    step("delete_entities circle", edit.delete_entities, circle["handle"], name=a)
    check("deleted circle is gone", _exists(circle["handle"], a) is None)
    check("entity count after delete", query.query_entities(name=a)["matches"] == count + 1)

    # -- save, close, open again (opened files are locked), unsaved-close protection
    path = os.path.join(SCRATCH, f"{REPORT}-a.dwg")
    saved = step("save_document", documents.save_document, path, overwrite=True, name=a)
    a = saved["name"] if saved else a
    step("close_document (saved, ours)", documents.close_document, a)
    opened = step("open_drawing the saved file", documents.open_drawing, path)
    check("an opened file is locked", opened is not None and not opened["editable"], str(opened))
    if opened:
        step("draw on the opened file is refused", draw.draw_line, [0, 0], [1, 1], name=opened["name"],
             expect_error="is locked")
    b = need(step("new_drawing (unsaved close)", documents.new_drawing), "new_drawing")["name"]
    step("draw_line in it", draw.draw_line, [0, 0], [1, 1], name=b)
    step("close with unsaved changes is refused", documents.close_document, b, expect_error="unsaved changes")
    step("close with discard_changes=True", documents.close_document, b, discard_changes=True)

    after = {d["name"]: d["unsaved_changes"] for d in user_drawings() if d["name"] in before}
    check("user drawings unchanged (unsaved-changes flags)", after == before)
    state["opened_file"] = opened["name"] if opened else None


def phase_undo_prepare(state: dict) -> None:
    c = need(step("new_drawing (undo/busy)", documents.new_drawing), "new_drawing")["name"]
    line = need(step("tool 1: draw_line", draw.draw_line, [0, 0], [6, 0], name=c), "draw_line")
    circle = need(step("tool 2: draw_circle", draw.draw_circle, [3, 3], 1.5, name=c), "draw_circle")
    step("tool 3: change_properties both -> red", edit.change_properties, [line["handle"], circle["handle"]],
         color=1, name=c)
    step("zoom_extents (convenience)", query.zoom_extents, name=c)
    state.update(undo_drawing=c, line=line["handle"], circle=circle["handle"])
    print(f"\nNOW: in AutoCAD, click into '{c}' and press Ctrl+Z ONCE. Expected: both turn back to ByLayer.")


def phase_undo_check(state: dict) -> None:
    c = scratch_drawing(state)
    line, circle = _exists(state["line"], c), _exists(state["circle"], c)
    check("one Ctrl+Z undid all of tool 3 (both ByLayer again)",
          bool(line and circle) and line["color"] == "ByLayer" and circle["color"] == "ByLayer",
          f"line={line and line['color']} circle={circle and circle['color']}")
    print(f"\nNOW: press Ctrl+Z ONCE more in '{c}'. Expected: the circle disappears, the line stays.")


def phase_undo_check2(state: dict) -> None:
    c = scratch_drawing(state)
    line, circle = _exists(state["line"], c), _exists(state["circle"], c)
    check("second Ctrl+Z undid only tool 2 (circle gone, line kept)", line is not None and circle is None,
          f"line={'kept' if line else 'gone'} circle={'kept' if circle else 'gone'}")


def phase_busy(state: dict) -> None:
    c = scratch_drawing(state)
    count = query.query_entities(name=c)["matches"]
    step("draw while the user is busy is refused", draw.draw_circle, [10, 10], 1, name=c, expect_error="busy")
    check("nothing was drawn while busy", query.query_entities(name=c)["matches"] == count)


def phase_busy_armed(state: dict) -> None:
    """Like the real server: connect and warm up while AutoCAD is idle, then wait for
    scratch/<report>-go (created when the user is inside a command or dialog) and try to draw."""
    import time

    c = scratch_drawing(state)
    count = query.query_entities(name=c)["matches"]
    documents.acad_status()
    go = os.path.join(SCRATCH, f"{REPORT}-go")
    if os.path.exists(go):
        os.remove(go)
    print("ARMED: waiting for", go, flush=True)
    deadline = time.time() + 600
    while not os.path.exists(go):
        if time.time() > deadline:
            check("busy-armed: go signal", False, "timed out waiting")
            return
        time.sleep(0.5)
    os.remove(go)
    step("draw while the user is busy is refused (warm session)", draw.draw_circle, [10, 10], 1, name=c,
         expect_error="busy")
    try:
        after = query.query_entities(name=c)["matches"]
        check("nothing was drawn while busy (warm session)", after == count, f"{count} -> {after}")
    except Exception as err:  # noqa: BLE001 - a rejected read is also an answer; checked again in 'idle'
        check("count read while busy", True, f"read rejected too ({type(err).__name__}); checked in idle")
    state["busy_count"] = count


def phase_idle(state: dict) -> None:
    c = scratch_drawing(state)
    if "busy_count" in state:
        now = query.query_entities(name=c)["matches"]
        check("nothing was drawn during the busy attempts", now == state["busy_count"], f"{state['busy_count']} -> {now}")
    step("draw after the user is done works again", draw.draw_circle, [10, 10], 1, name=c)


def phase_cleanup(state: dict) -> None:
    c = scratch_drawing(state)
    step("close the undo/busy scratch drawing (ours, discard)", documents.close_document, c, discard_changes=True)
    if state.get("opened_file"):
        print(f"\nLeft open on purpose: '{state['opened_file']}', a scratch file the server opened. It is locked,"
              " so the server can't close it. Close it in AutoCAD; it has no changes.")


PHASES = {"tools": phase_tools, "undo-prepare": phase_undo_prepare, "undo-check": phase_undo_check,
          "undo-check2": phase_undo_check2, "busy": phase_busy, "busy-armed": phase_busy_armed,
          "idle": phase_idle, "cleanup": phase_cleanup}


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase not in PHASES:
        print("phase must be one of:", ", ".join(PHASES))
        return 2
    os.makedirs(SCRATCH, exist_ok=True)
    state = load_state()
    PHASES[phase](state)
    save_state(state)
    runs = len([k for k in state if k.startswith("run_")])
    state[f"run_{runs + 1}"] = phase
    save_state(state)
    return harness.finish(f"{REPORT}-{phase}-{runs + 1}")


if __name__ == "__main__":
    sys.exit(main())
