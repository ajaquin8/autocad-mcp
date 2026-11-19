"""More Block Editor tools: list what is in the editor (T10), visibility parameters and states (T6),
flip and rotation parameters, and move, scale, flip and rotate actions (T8).

Built on run_command like tools/block_editor.py. The prompt orders were recorded live on 2026-11-18
(AMCP-LIVE-20261118-03, AutoCAD 2027, BACTIONBARMODE 0), except where a comment says "not seen yet".
"""

from __future__ import annotations

import math
from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import rounded, xyz
from ..session import session
from .block_editor import (
    PARAMETER_POINT,
    location_inputs,
    require_editor,
    run_action,
    run_checked,
    selection_input,
    value_set_inputs,
)
from .draw import Point

KINDS = ("geometry", "parameters", "actions", "grips")
NEW_STATE = {"current": "_C", "show_all": "_S", "hide_all": "_H"}  # [Hide all/Show all/Current visibility]
ACTIONS = ("move", "scale", "flip", "rotate")


def kind_of(object_name: str) -> str:
    """'parameters' for AcDbBlockLinearParameterEntity, 'actions', 'grips', else 'geometry'."""
    if object_name.startswith("AcDbBlock") and object_name.endswith("Entity"):
        for word, kind in (("Parameter", "parameters"), ("Action", "actions"), ("Grip", "grips")):
            if word in object_name:
                return kind
    return "geometry"


def short_type(object_name: str) -> str:
    """'LinearParameter' for AcDbBlockLinearParameterEntity, 'Circle' for AcDbCircle."""
    text = object_name.removeprefix("AcDb")
    if text.startswith("Block") and text.endswith("Entity"):
        text = text.removeprefix("Block").removesuffix("Entity")
    return text


@acad_tool(read_only=True)
def list_block_editor_objects(kinds: list[str] | None = None, name: str = "") -> dict:
    """List what is in the open Block Editor, with handles that work there: pass them as
    select={"handles": [...]} to add_stretch_action, add_action and set_object_visibility.
    Handles read in model space or before BEDIT do not work in the Block Editor (it gives a
    block's objects new handles), and these stop working once it is closed.

    Args:
        kinds: which to list, from "geometry", "parameters", "actions", "grips"
            (default: geometry, parameters and actions).
        name: which drawing; it must be the active one (default: active).
    """
    wanted = set(kinds or ("geometry", "parameters", "actions"))
    if wanted - set(KINDS):
        raise ValueError(f"kinds are {', '.join(KINDS)}.")
    doc = session.document(name)
    require_editor(doc, True)
    # Inside the Block Editor, COM's ModelSpace is the editor's space (live 2026-11-18, AMCP-LIVE-20261118-02/03).
    space = doc.ModelSpace
    found: dict[str, list] = {k: [] for k in KINDS if k in wanted}
    for i in range(space.Count):
        item = space.Item(i)
        object_name = str(item.ObjectName)
        kind = kind_of(object_name)
        if kind not in wanted:
            continue
        info: dict[str, Any] = {"handle": str(item.Handle), "type": short_type(object_name)}
        if kind == "geometry":
            info["layer"] = str(item.Layer)
            try:
                lo, hi = item.GetBoundingBox()
                info["bbox"] = [rounded(lo[:2]), rounded(hi[:2])]
            except (pywintypes.com_error, AttributeError, TypeError, ValueError):
                pass
        found[kind].append(info)
    return found


# ---------- visibility (T6) ----------


@acad_tool()
def add_visibility_parameter(location: Point, label: str = "Visibility", grips: int = 1, name: str = "") -> dict:
    """Add a visibility parameter in the open Block Editor (BPARAMETER Visibility): the drop-down
    users pick a visibility state from. AutoCAD starts it with one state, "VisibilityState0".
    Add states with visibility_state, and choose what each shows with set_object_visibility.
    Objects AND parameters added while a state is current exist only in that state.

    Args:
        location: where the parameter's grip goes [x, y].
        label: the property name users see (default "Visibility").
        grips: 0 or 1 (default 1).
        name: which drawing; it must be the active one (default: active).
    """
    if grips not in (0, 1):
        raise ValueError("grips is 0 or 1.")
    doc = session.document(name)
    require_editor(doc, True)
    result = run_checked(doc, f"Adding the visibility parameter '{label}'", "BPARAMETER",
                         ["_V", "_L", label, list(location), str(grips)])
    return {"label": label, "steps": result["steps"]}


@acad_tool()
def visibility_state(action: str, state: str, new_state_shows: str = "current", name: str = "") -> dict:
    """Make, switch to or delete a visibility state in the open Block Editor (-BVSTATE). Needs a
    visibility parameter first (add_visibility_parameter). A new state becomes the current one.

    Args:
        action: "new", "set" (make it current) or "delete".
        state: the state's name, e.g. "36 in".
        new_state_shows: for "new": "current" (what the current state shows, default),
            "show_all" or "hide_all".
        name: which drawing; it must be the active one (default: active).
    """
    if action not in ("new", "set", "delete"):
        raise ValueError('action is "new", "set" or "delete".')
    if not state.strip():
        raise ValueError("Give the state's name.")
    if action == "new":
        if new_state_shows not in NEW_STATE:
            raise ValueError(f"new_state_shows is one of {', '.join(NEW_STATE)}.")
        inputs = ["_N", state, NEW_STATE[new_state_shows]]
    else:
        inputs = ["_S" if action == "set" else "_D", state]
    doc = session.document(name)
    require_editor(doc, True)
    result = run_checked(doc, f"Visibility state {action} '{state}'", "-BVSTATE", inputs)
    return {"action": action, "state": state, "steps": result["steps"]}


@acad_tool()
def set_object_visibility(select: dict, visible: bool, all_states: bool = False, name: str = "") -> dict:
    """Show or hide objects in the current visibility state, or in all of them, in the open
    Block Editor (BVSHOW / BVHIDE). Switch states with visibility_state.

    Args:
        select: {"crossing": [p1, p2]}, {"window": [p1, p2]} or {"handles": [...]} (handles
            from list_block_editor_objects).
        visible: True to show, False to hide.
        all_states: apply to every visibility state, not only the current one (default False).
        name: which drawing; it must be the active one (default: active).
    """
    answer = selection_input(select, [], "")
    doc = session.document(name)
    require_editor(doc, True)
    command = "BVSHOW" if visible else "BVHIDE"
    result = run_checked(doc, f"{'Showing' if visible else 'Hiding'} objects", command,
                         [answer, "", "_A" if all_states else "_C"])
    return {"visible": visible, "all_states": all_states, "steps": result["steps"]}


# ---------- flip and rotation parameters, actions (T8) ----------


@acad_tool()
def add_flip_parameter(label: str, base: Point, end: Point, label_location: Point, unflipped: str = "Not flipped",
                       flipped: str = "Flipped", name: str = "") -> dict:
    """Add a flip parameter in the open Block Editor (BPARAMETER Flip): a reflection line from
    base to end that objects flip about, with a property users see as `label`. Its grip sits at
    base. Returns "pick_point", a point on the line, for add_action(kind="flip").

    Args:
        label: property name, e.g. "Hinge side".
        base, end: the reflection line [x, y].
        label_location: where the label goes [x, y].
        unflipped, flipped: the property's two values (default "Not flipped" / "Flipped").
        name: which drawing; it must be the active one (default: active).
    """
    (x1, y1, _), (x2, y2, _) = xyz(base), xyz(end)
    if math.isclose(x1, x2) and math.isclose(y1, y2):
        raise ValueError("base and end must differ.")
    doc = session.document(name)
    require_editor(doc, True)
    # Label asks for the label, then the unflipped and flipped values (live 2026-11-18); then the line and the
    # label location (documented; not seen to the end yet).
    result = run_checked(doc, f"Adding the flip parameter '{label}'", "BPARAMETER",
                         ["_F", "_L", label, unflipped, flipped, list(base), list(end), list(label_location)])
    pick = rounded([x1 + 0.25 * (x2 - x1), y1 + 0.25 * (y2 - y1)])
    return {"label": label, "pick_point": pick, "steps": result["steps"]}


@acad_tool()
def add_rotation_parameter(label: str, base: Point, radius: float, label_location: Point, default_angle: float = 0,
                           grips: int = 1, value_list: list[float] | None = None, name: str = "") -> dict:
    """Add a rotation parameter in the open Block Editor (BPARAMETER Rotation): an angle property
    users see as `label`, turning about base. It is drawn as a circle of the given radius.
    Returns "pick_point", a point on that circle, for add_action(kind="rotate").

    Args:
        label: property name, e.g. "Angle".
        base: the point objects rotate about [x, y].
        radius: the circle's radius (where the grip sits).
        label_location: where the label goes [x, y].
        default_angle: degrees where the grip starts (default 0).
        grips: 0 or 1 (default 1).
        value_list: allowed angles in degrees, e.g. [0, 90, 180, 270] (default: any).
        name: which drawing; it must be the active one (default: active).
    """
    if radius <= 0:
        raise ValueError("radius must be positive.")
    if grips not in (0, 1):
        raise ValueError("grips is 0 or 1.")
    values = value_set_inputs(value_list, None)
    doc = session.document(name)
    require_editor(doc, True)
    # Label, base point, radius, default angle, label location (live 2026-11-18); the answer after the label
    # location (the number of grips) and the angle value set are not seen yet.
    result = run_checked(doc, f"Adding the rotation parameter '{label}'", "BPARAMETER",
                         ["_R", "_L", label, *values, list(base), float(radius), float(default_angle),
                          list(label_location), str(grips)])
    bx, by, _ = xyz(base)
    angle = math.radians(default_angle + 135)  # away from the grip
    pick = rounded([bx + radius * math.cos(angle), by + radius * math.sin(angle)])
    return {"label": label, "pick_point": pick, "steps": result["steps"]}


def action_inputs(kind: str, parameter_pick: Point, select: dict, end: str, multiplier: float | None,
                  offset: float | None, location: Point | None) -> list:
    """BACTION answers per action (live 2026-11-18 for move and scale; flip and rotate not seen yet:
    their parameters allow one action each, so no action type is asked)."""
    if kind not in ACTIONS:
        raise ValueError(f"kind is one of {', '.join(ACTIONS)}.")
    if (multiplier not in (None, 1) or offset) and kind != "move":
        raise ValueError("multiplier and offset are for move actions (stretches take them in add_stretch_action).")
    pick = list(parameter_pick)
    where = list(location if location is not None else parameter_pick)
    chosen = [selection_input(select, [], ""), ""]
    if kind == "move":
        if end not in PARAMETER_POINT:
            raise ValueError('end is "second" or "start".')
        return [pick, "_M", PARAMETER_POINT[end], *chosen, *location_inputs(multiplier, offset, where)]
    if kind == "scale":
        return [pick, "_S", *chosen, where]
    return [pick, *chosen, where]


@acad_tool()
def add_action(kind: str, parameter_pick: Point, select: dict, end: str = "second", multiplier: float | None = None,
               offset: float | None = None, location: Point | None = None, name: str = "") -> dict:
    """Add a move, scale, flip or rotate action in the open Block Editor (BACTION) to the parameter
    drawn through parameter_pick (pick_point from the parameter tools). Stretches have their own
    tool (add_stretch_action). The view is widened first so every pick is on screen.

    move: with a linear, polar, XY or point parameter; `end` picks the parameter point that drives
    it, and multiplier / offset (degrees) work as for stretches. scale: with a linear, polar or XY
    parameter. flip: with a flip parameter. rotate: with a rotation parameter.

    Args:
        kind: "move", "scale", "flip" or "rotate".
        parameter_pick: [x, y] on the parameter.
        select: the objects: {"crossing": [p1, p2]}, {"window": [p1, p2]} or {"handles": [...]}
            (from list_block_editor_objects).
        end: for move: "second" (default) or "start".
        multiplier: for move: distance multiplier, e.g. 0.5 (default 1).
        offset: for move: angle offset in degrees (default 0).
        location: where the action's badge goes (default: parameter_pick).
        name: which drawing; it must be the active one (default: active).
    """
    inputs = action_inputs(kind, parameter_pick, select, end, multiplier, offset, location)
    result = run_action(session.document(name), f"Adding the {kind} action", inputs, select)
    return {"kind": kind, **result}
