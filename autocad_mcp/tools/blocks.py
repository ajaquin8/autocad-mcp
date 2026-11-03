"""Blocks: list definitions, insert references, set attribute values."""

from __future__ import annotations

import os

import pywintypes

from ..app import acad_tool
from ..com import AcadError, point, rad
from ..session import session
from .draw import Point, place
from .entities import attributes, by_handle


def set_attributes(ref, values: dict[str, str], change) -> list[str]:
    """Set attribute values by tag (case-insensitive); returns the tags that were not found."""
    wanted = {str(k).upper(): str(v) for k, v in values.items()}
    for att in (ref.GetAttributes() if bool(ref.HasAttributes) else []):
        tag = str(att.TagString).upper()
        if tag in wanted:
            old = str(att.TextString)
            change.on_rollback(lambda a=att, o=old: setattr(a, "TextString", o))
            att.TextString = wanted.pop(tag)
            att.Update()
    return sorted(wanted)


@acad_tool(read_only=True)
def list_blocks(include_anonymous: bool = False, name: str = "") -> list:
    """List block definitions in the drawing (not layouts or xrefs), with their attribute tags.

    Args:
        include_anonymous: also list *U/*D anonymous blocks (dynamic block copies, dimensions).
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    blocks = doc.Blocks
    result = []
    for i in range(blocks.Count):
        block = blocks.Item(i)
        block_name = str(block.Name)
        if bool(block.IsLayout) or bool(block.IsXRef):
            continue
        if block_name.startswith("*") and not include_anonymous:
            continue
        tags = []
        for j in range(block.Count):
            item = block.Item(j)
            if str(item.ObjectName) == "AcDbAttributeDefinition":
                tags.append(str(item.TagString))
        result.append({"name": block_name, "entities": int(block.Count), "attribute_tags": tags,
                       "dynamic": bool(block.IsDynamicBlock)})
    return result


@acad_tool()
def insert_block(block: str, position: Point, scale: float = 1, rotation: float = 0,
                 attribute_values: dict[str, str] | None = None, layer: str = "", name: str = "") -> dict:
    """Insert a block reference, optionally filling in its attributes.

    Args:
        block: a block defined in the drawing (see list_blocks), or the full path of a
            .dwg to insert as a block.
        position: insertion point [x, y].
        scale: uniform scale factor.
        rotation: degrees counter-clockwise.
        attribute_values: attribute values by tag, e.g. {"MARK": "W101", "SIZE": "36x48"}.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    if scale == 0:
        raise AcadError("scale cannot be 0.")
    doc = session.document(name)
    if block.lower().endswith(".dwg"):
        if not os.path.exists(block):
            raise AcadError(f"File not found: {block}")
    else:
        try:
            doc.Blocks.Item(block)
        except pywintypes.com_error:
            raise AcadError(f"No block named '{block}' in '{doc.Name}'. Use list_blocks.") from None
    with session.edit(doc) as change:
        ref = doc.ModelSpace.InsertBlock(point(position), block, float(scale), float(scale), float(scale),
                                         rad(rotation))
        change.add(ref)
        missing = set_attributes(ref, attribute_values or {}, change)
        if missing:
            raise AcadError(f"The block has no attribute(s) {', '.join(missing)}; it has "
                            f"{', '.join(attributes(ref)) or 'none'}. Nothing was inserted.")
        return place(change, ref, layer)


@acad_tool()
def set_block_attributes(handle: str, values: dict[str, str], name: str = "") -> dict:
    """Change attribute values of an existing block reference.

    Args:
        handle: the block reference's handle (from query_entities or insert_block).
        values: new values by tag, e.g. {"MARK": "W102"}.
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    with session.edit(doc) as change:
        ref = by_handle(doc, handle)
        if str(ref.ObjectName) != "AcDbBlockReference":
            raise AcadError(f"Handle {handle} is a {ref.ObjectName}, not a block reference.")
        missing = set_attributes(ref, values, change)
        if missing:
            raise AcadError(f"No attribute(s) {', '.join(missing)} on this block; it has "
                            f"{', '.join(attributes(ref)) or 'none'}. Nothing was changed.")
        return {"handle": str(ref.Handle), "attributes": attributes(ref)}
