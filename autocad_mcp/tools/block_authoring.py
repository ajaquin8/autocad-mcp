"""More Block Editor tools: list what is in the editor (T10).

Recorded live on 2026-11-18 (AMCP-LIVE-20261118-02/03, AutoCAD 2027).
"""

from __future__ import annotations

from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import rounded
from ..session import session
from .block_editor import require_editor

KINDS = ("geometry", "parameters", "actions", "grips")


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
