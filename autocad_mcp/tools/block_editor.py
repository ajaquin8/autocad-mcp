"""Authoring dynamic blocks in the Block Editor: open and close it, add linear parameters and
stretch actions, lock attribute positions, and test the result.

The Block Editor commands only exist as prompts, so the editor tools are built on run_command
(tools/commands.py), which never leaves AutoCAD waiting. Prompt orders come from the live batch
of 2026-11-06 on AutoCAD 2026 with BACTIONBARMODE 0 ([[Sources/2026-11-06 Stretch grips by
script]]); the tools themselves are not live-verified yet.
"""

from __future__ import annotations

import math
from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, point, rounded, xyz
from ..session import session
from . import commands
from .blocks import apply_properties, exploded, shown_extents
from .draw import Point

STRETCH = "_T"  # BACTION: [Array/Move/Scale/sTretch]; Stretch is T, not S (live 2026-11-06)
PARAMETER_POINT = {"second": "_S", "start": "_T"}  # [sTart point/Second point]; Enter alone picks the nearest
CENTRE_EXCLUDE = "LWPOLYLINE,DIMENSION"  # moved instead of stretched by a centre action (live 2026-11-06)
EXPECT_KEYS = ("width", "height", "min_x", "min_y", "max_x", "max_y")


def editor_open(doc: Any) -> bool:
    return int(doc.GetVariable("BLOCKEDITOR")) == 1


def require_editor(doc: Any, wanted: bool) -> None:
    if editor_open(doc) != wanted:
        raise AcadError("The Block Editor is not open; call open_block_editor first." if wanted else
                        "The Block Editor is open; close it first (close_block_editor).")


def require_block(doc: Any, block: str) -> Any:
    try:
        return doc.Blocks.Item(block)
    except pywintypes.com_error:
        raise AcadError(f"No block named '{block}' in '{doc.Name}'. Use list_blocks.") from None


def failed(what: str, result: dict) -> AcadError:
    steps = "; ".join(f"{s['sent']} -> {s['lastprompt']!r}" for s in result.get("steps", []))
    back = " The drawing was put back to how it was." if result.get("undone") else ""
    return AcadError(f"{what} failed: {result.get('problem') or 'it did not complete'}{back} Steps: {steps}")


def run_checked(doc: Any, what: str, command: str, inputs: list, undo: bool = True) -> dict:
    result = commands.run(doc, command, inputs, undo_on_failure=undo)
    if not result["completed"]:
        raise failed(what, result)
    return result


def parameter_pick_point(start: Point, end: Point, label_location: Point) -> list[float]:
    """A point on a linear parameter's drawn line, a quarter of the way along: the line runs parallel
    to start-end through the label location. Picking there selects the parameter at BACTION's "Select
    parameter:" prompt (an ename is refused there, live 2026-11-06)."""
    (x1, y1, _), (x2, y2, _), (lx, ly, _) = xyz(start), xyz(end), xyz(label_location)
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        raise ValueError("A linear parameter needs two different points.")
    nx, ny = -dy / length, dx / length
    offset = (lx - x1) * nx + (ly - y1) * ny
    return rounded([x1 + 0.25 * dx + offset * nx, y1 + 0.25 * dy + offset * ny])


@acad_tool()
def open_block_editor(block: str, name: str = "") -> dict:
    """Open the Block Editor on a block of a drawing this server created (-BEDIT with the
    name as a LISP string, so names with spaces work). The other Block Editor tools need it
    open; close it with close_block_editor.

    Args:
        block: the block definition's name (see list_blocks).
        name: which drawing; it must be the active one (default: active).
    """
    doc = session.document(name)
    require_block(doc, block)
    require_editor(doc, False)
    result = commands.run(doc, "-BEDIT", [block], undo_on_failure=False)
    if not editor_open(doc):
        raise failed(f"Opening the Block Editor on '{block}'", result)
    return {"block": block, "block_editor_open": True, "steps": result["steps"]}


@acad_tool()
def close_block_editor(save: bool = True, name: str = "") -> dict:
    """Close the Block Editor, saving the block first (BSAVE, then BCLOSE) or discarding the
    changes. If BCLOSE still asks Save/Discard, it is answered. If AutoCAD shows a dialog
    instead (it once showed "Block - Changes Not Saved"), the error names it and the user
    has to answer it.

    Args:
        save: save the block definition (default True); False discards the changes.
        name: which drawing; it must be the active one (default: active).
    """
    doc = session.document(name)
    require_editor(doc, True)
    steps: list[dict] = []
    if save:
        steps += run_checked(doc, "BSAVE", "BSAVE", [], undo=False)["steps"]
    result = commands.run(doc, "BCLOSE", [], undo_on_failure=False)
    steps += result["steps"]
    if editor_open(doc) and result.get("cancelled"):
        # It asked [Save changes/Discard changes] (also seen right after BSAVE, live 2026-11-06).
        result = commands.run(doc, "BCLOSE", ["_S" if save else "_D"], undo_on_failure=False)
        steps += result["steps"]
    if editor_open(doc):
        raise failed("Closing the Block Editor", result)
    return {"saved": save, "block_editor_open": False, "steps": steps}


@acad_tool()
def add_linear_parameter(label: str, start: Point, end: Point, label_location: Point, grips: int = 1,
                         name: str = "") -> dict:
    """Add a linear parameter in the open Block Editor (BPARAMETER Linear): the distance
    property users see as `label` (e.g. "Width"), measured from start to end, with its
    line through label_location. One grip (the default) sits at the end point.
    Returns "pick_point", a point on the parameter's line for add_stretch_action.

    Args:
        label: property name shown to users, e.g. "Width" or "Height".
        start, end: [x, y] in the block's coordinates (the Block Editor's WCS).
        label_location: where the parameter's line and label go (like a dimension line).
        grips: number of grips, 0, 1 or 2 (default 1, at the end point).
        name: which drawing; it must be the active one (default: active).
    """
    if grips not in (0, 1, 2):
        raise ValueError("grips is 0, 1 or 2.")
    pick = parameter_pick_point(start, end, label_location)
    doc = session.document(name)
    require_editor(doc, True)
    # [Name/Label/...]: Label sets the property name; the number of grips comes last (live 2026-11-06).
    result = run_checked(doc, f"Adding the linear parameter '{label}'", "BPARAMETER",
                         ["_L", "_L", label, list(start), list(end), list(label_location), str(grips)])
    return {"label": label, "pick_point": pick, "steps": result["steps"]}


def selection_inputs(select: dict | None, frame: list[Point]) -> list:
    """Answers for "Select objects:" from {"crossing": [p1, p2]}, {"window": [p1, p2]} or
    {"handles": [...]}; default: a crossing window the size of the stretch frame."""
    select = select or {"crossing": frame}
    if set(select) == {"crossing"} or set(select) == {"window"}:
        kind = next(iter(select))
        corners = select[kind]
        if len(corners) != 2:
            raise ValueError(f"{kind} takes two corners [[x1, y1], [x2, y2]].")
        return ["_C" if kind == "crossing" else "_W", list(corners[0]), list(corners[1])]
    if set(select) == {"handles"} and select["handles"]:
        return [{"handle": h} for h in select["handles"]]
    raise ValueError('select is {"crossing": [p1, p2]}, {"window": [p1, p2]} or {"handles": [...]}.')


def stretch_inputs(parameter_pick: Point, frame: list[Point], select: dict | None, end: str,
                   multiplier: float | None, exclude_types: str | None, location: Point | None) -> list:
    if end not in PARAMETER_POINT:
        raise ValueError('end is "second" or "start".')
    if len(frame) != 2:
        raise ValueError("frame takes two corners [[x1, y1], [x2, y2]].")
    if exclude_types is None:
        exclude_types = CENTRE_EXCLUDE if multiplier not in (None, 1) else ""
    inputs: list = [list(parameter_pick), STRETCH, PARAMETER_POINT[end], list(frame[0]), list(frame[1])]
    inputs += selection_inputs(select, frame)
    if exclude_types:
        inputs += ["_R", {"select_all": exclude_types}]
    inputs.append("")  # end the selection
    if multiplier not in (None, 1):
        inputs += ["_M", float(multiplier)]
    inputs.append(list(location if location is not None else parameter_pick))
    return inputs


@acad_tool()
def add_stretch_action(parameter_pick: Point, frame: list[Point], select: dict | None = None,
                       end: str = "second", multiplier: float | None = None, exclude_types: str | None = None,
                       location: Point | None = None, name: str = "") -> dict:
    """Add a stretch action in the open Block Editor (BACTION Stretch) to the parameter
    drawn through parameter_pick (use pick_point from add_linear_parameter; it must be on
    screen, so the view is zoomed to extents first). Objects with points inside `frame` are
    stretched; other selected objects are MOVED, so select only what should follow.

    For a centred item that moves half the distance, pass multiplier 0.5: polylines and
    dimensions are then removed from the selection by default (they would move by half).
    Lock attribute positions first (lock_attribute_positions), or attribute definitions
    are left out of the selection.

    Args:
        parameter_pick: [x, y] on the parameter's line.
        frame: stretch frame corners [[x1, y1], [x2, y2]].
        select: {"crossing": [p1, p2]} (default: crossing the frame), {"window": [p1, p2]},
            or {"handles": [...]}.
        end: which parameter point drives it, "second" (the grip end, default) or "start".
        multiplier: distance multiplier, e.g. 0.5 for centred items (default 1).
        exclude_types: DXF types removed from the selection, e.g. "LWPOLYLINE,DIMENSION";
            "" for none (default: those two when multiplier is not 1, else none).
        location: where the action's badge goes (default: parameter_pick).
        name: which drawing; it must be the active one (default: active).
    """
    inputs = stretch_inputs(parameter_pick, frame, select, end, multiplier, exclude_types, location)
    doc = session.document(name)
    require_editor(doc, True)
    session.app.ZoomExtents()  # a pick only selects what is on screen
    old_mode = doc.GetVariable("BACTIONBARMODE")
    doc.SetVariable("BACTIONBARMODE", 0)  # the prompt order above; put back afterwards
    try:
        result = run_checked(doc, "Adding the stretch action", "BACTION", inputs)
    finally:
        doc.SetVariable("BACTIONBARMODE", old_mode)
    return {"steps": result["steps"], "inputs_used": result["inputs_used"]}


@acad_tool()
def lock_attribute_positions(block: str, name: str = "") -> dict:
    """Lock the position of every attribute definition in a block definition, so the Block
    Editor's actions can select them (unlocked ones are filtered out). Call it with the
    Block Editor closed, before adding actions. One undo step; drawings this server may
    edit only.

    Args:
        block: the block definition's name.
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    require_editor(doc, False)
    definition = require_block(doc, block)
    locked, already = [], []
    with session.edit(doc) as change:
        for i in range(definition.Count):
            item = definition.Item(i)
            if str(item.ObjectName) != "AcDbAttributeDefinition":
                continue
            if bool(item.LockPosition):
                already.append(str(item.TagString))
                continue
            change.on_rollback(lambda a=item: setattr(a, "LockPosition", False))
            item.LockPosition = True
            locked.append(str(item.TagString))
    return {"block": block, "locked": locked, "already_locked": already}


def _extents(ref: Any, change: Any) -> dict:
    with exploded(ref, change) as parts:
        box = shown_extents(parts)
    if box is None:
        raise AcadError("The block shows no geometry to measure.")
    (x1, y1), (x2, y2) = box
    return {"min_x": x1, "min_y": y1, "max_x": x2, "max_y": y2, "width": x2 - x1, "height": y2 - y1}


@acad_tool()
def check_dynamic_block(block: str, cases: list[dict], base_properties: dict[str, Any] | None = None,
                        position: Point = (0, 0), tolerance: float = 1e-4, name: str = "") -> dict:
    """Test a dynamic block: insert a temporary reference, set its properties case by case,
    measure what it shows (exploded copy, attribute text left out) and compare the change
    from the base state with what each case expects. The reference is deleted again.
    Run it with the Block Editor closed, after saving the block.

    Args:
        block: the block definition's name.
        cases: e.g. [{"properties": {"Width": 72}, "expect": {"width": 24, "max_x": 24, "min_x": 0}}].
            Expected values are changes from the base state; keys: width, height, min_x,
            min_y, max_x, max_y (leave out what you do not want checked).
        base_properties: properties set before the base measurement (default: as inserted).
        position: where the temporary reference goes [x, y] (default [0, 0]).
        tolerance: allowed difference in drawing units (default 0.0001).
        name: which drawing (default: active).
    """
    if not cases:
        raise ValueError("Give at least one case.")
    for case in cases:
        if not isinstance(case.get("properties"), dict) or set(case.get("expect", {})) - set(EXPECT_KEYS):
            raise ValueError(f'Each case is {{"properties": {{...}}, "expect": {{...}}}} with expect keys from '
                             f"{', '.join(EXPECT_KEYS)}; got {case!r}.")
    doc = session.document(name)
    require_editor(doc, False)
    require_block(doc, block)
    results = []
    with session.edit(doc) as change:
        ref = change.add(doc.ModelSpace.InsertBlock(point(position), block, 1.0, 1.0, 1.0, 0.0))
        if not bool(getattr(ref, "IsDynamicBlock", False)):
            raise AcadError(f"'{block}' is not a dynamic block.")
        try:
            if base_properties:
                apply_properties(ref, base_properties, change)
            base = _extents(ref, change)
            for case in cases:
                apply_properties(ref, case["properties"], change)
                now = _extents(ref, change)
                delta = {k: round(now[k] - base[k], 6) for k in EXPECT_KEYS}
                expect = case.get("expect", {})
                misses = {k: {"expected": v, "measured": delta[k]} for k, v in expect.items()
                          if abs(delta[k] - float(v)) > tolerance}
                results.append({"properties": case["properties"], "change": delta, "passed": not misses,
                                "misses": misses, "extents": {k: round(v, 6) for k, v in now.items()}})
        finally:
            ref.Delete()
            change.created[:] = [o for o in change.created if o is not ref]
    return {"block": block, "passed": all(r["passed"] for r in results),
            "base": {k: round(v, 6) for k, v in base.items()}, "cases": results}
