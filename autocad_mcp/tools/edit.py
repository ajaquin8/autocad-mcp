"""Change existing entities by handle: move, change properties, delete."""

from __future__ import annotations

from ..app import acad_tool
from ..com import AcadError, point, xyz
from ..session import session
from .draw import Point
from .entities import BYLAYER, by_handle, handles, summary
from .layers import ensure_linetype, find_layer

MAX_HANDLES = 500


def _targets(doc, value: str | list[str]) -> list:
    keys = handles(value)
    if not keys:
        raise AcadError("Give at least one handle.")
    if len(keys) > MAX_HANDLES:
        raise AcadError(f"At most {MAX_HANDLES} handles per call.")
    return [by_handle(doc, h) for h in keys]


@acad_tool()
def move_entities(entity_handles: str | list[str], offset: Point, name: str = "") -> dict:
    """Move entities by an offset.

    Args:
        entity_handles: handles, as a list or "1A, 2B".
        offset: [dx, dy] or [dx, dy, dz] in drawing units.
        name: which open drawing (default: active).
    """
    dx, dy, dz = xyz(offset)
    doc = session.document(name)
    with session.edit(doc) as change:
        origin, target = point([0, 0, 0]), point([dx, dy, dz])
        for ent in _targets(doc, entity_handles):
            ent.Move(origin, target)
            change.on_rollback(lambda e=ent: e.Move(target, origin))
        return {"moved": len(handles(entity_handles)), "offset": [dx, dy, dz]}


@acad_tool()
def change_properties(entity_handles: str | list[str], layer: str = "", color: int | None = None,
                      linetype: str = "", name: str = "") -> list:
    """Change the layer, color or linetype of entities.

    Args:
        entity_handles: handles, as a list or "1A, 2B".
        layer: move them to this existing layer.
        color: AutoCAD Color Index 1-255, or 256 for ByLayer.
        linetype: a linetype name, or ByLayer.
        name: which open drawing (default: active).
    """
    if not (layer or color is not None or linetype):
        raise AcadError("Nothing to change: give layer, color and/or linetype.")
    if color is not None and not 1 <= color <= BYLAYER:
        raise AcadError("color must be 1-255, or 256 for ByLayer.")
    doc = session.document(name)
    with session.edit(doc) as change:
        if layer and find_layer(doc, layer) is None:
            raise AcadError(f"No layer named '{layer}'. Create it with add_layer first.")
        if linetype and linetype.lower() != "bylayer":
            ensure_linetype(doc, linetype)
        result = []
        for ent in _targets(doc, entity_handles):
            old = (str(ent.Layer), int(ent.color), str(ent.Linetype))

            def restore(e=ent, o=old) -> None:
                e.Layer, e.color, e.Linetype = o
            change.on_rollback(restore)
            if layer:
                ent.Layer = layer
            if color is not None:
                ent.color = color
            if linetype:
                ent.Linetype = linetype
            result.append(summary(ent))
        return result


@acad_tool(destructive=True)
def delete_entities(entity_handles: str | list[str], name: str = "") -> str:
    """Delete entities. All handles are checked before anything is deleted; the user
    can bring them back with one Ctrl+Z (U), but this server cannot.

    Args:
        entity_handles: handles, as a list or "1A, 2B".
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    with session.edit(doc):
        targets = _targets(doc, entity_handles)
        for ent in targets:
            ent.Delete()
    return f"Deleted {len(targets)} entities (one undo step)."
