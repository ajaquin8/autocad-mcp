"""More Block Editor tools: list what is in the editor (T10), visibility parameters and states (T6).

Built on run_command like tools/block_editor.py. The prompt orders were recorded live on 2026-11-18
(AMCP-LIVE-20261118-02/03, AutoCAD 2027).
"""

from __future__ import annotations

from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import rounded
from ..session import session
from .block_editor import require_editor, run_checked, selection_input
from .draw import Point

KINDS = ("geometry", "parameters", "actions", "grips")
NEW_STATE = {"current": "_C", "show_all": "_S", "hide_all": "_H"}  # [Hide all/Show all/Current visibility]


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
