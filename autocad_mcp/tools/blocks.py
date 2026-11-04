"""Blocks: list definitions, insert references, set attribute values and dynamic properties."""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, point, rad, rounded
from ..session import session
from .draw import Point, place
from .entities import attributes, by_handle

# Not real block properties: "Origin" is the base point AutoCAD lists for every dynamic block.
INTERNAL_PROPERTIES = {"origin"}
# Exploded attributes come back as text or attribute definitions; they are not geometry.
NOT_GEOMETRY = {"AcDbAttributeDefinition", "AcDbAttribute", "AcDbText", "AcDbMText"}
MAX_GEOMETRY = 400


def block_ref(doc: Any, handle: str) -> Any:
    ref = by_handle(doc, handle)
    if str(ref.ObjectName) != "AcDbBlockReference":
        raise AcadError(f"Handle {handle} is a {ref.ObjectName}, not a block reference.")
    return ref


def block_props(ref: Any) -> dict[str, Any]:
    """Name (lower case) -> property object, read fresh: the objects go stale once any property
    changes, e.g. after a visibility change (verified 2026-11-03)."""
    if not bool(getattr(ref, "IsDynamicBlock", False)):
        return {}
    props = {}
    for prop in ref.GetDynamicBlockProperties():
        name = str(prop.PropertyName)
        if name.lower() not in INTERNAL_PROPERTIES:
            props[name.lower()] = prop
    return props


def _plain(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (bool, int)):
        return value
    return str(value)


def property_info(prop: Any) -> dict:
    allowed = [_plain(v) for v in (prop.AllowedValues or ())]
    info = {"name": str(prop.PropertyName), "value": _plain(prop.Value), "shown": bool(prop.Show),
            "read_only": bool(prop.ReadOnly)}
    if allowed:
        info["allowed"] = allowed
    return info


def block_attributes(ref: Any) -> dict[str, dict]:
    if not bool(ref.HasAttributes):
        return {}
    return {str(a.TagString): {"value": str(a.TextString), "invisible": bool(a.Invisible)}
            for a in ref.GetAttributes()}


def number(value: Any) -> float:
    """12, 1.25, "1.25", "5/8", "1 1/4" or "1-1/4" (inches written as fractions) -> float."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip('"')
    match = re.fullmatch(r"(?:(\d+)[ -])?(\d+)/(\d+)", text)
    if match:
        whole, num, den = match.groups()
        return int(whole or 0) + int(num) / int(den)
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"'{value}' is not a number") from None


def _set(ref: Any, key: str, value: Any) -> None:
    block_props(ref)[key].Value = value


def apply_properties(ref: Any, values: dict[str, Any], change: Any, allow_hidden: bool = False) -> None:
    """Set dynamic properties by name, in the order given; each change is recorded for rollback."""
    for name, wanted in values.items():
        props = block_props(ref)
        key = str(name).lower()
        prop = props.get(key)
        if prop is None or (not bool(prop.Show) and not allow_hidden):
            shown = [str(p.PropertyName) for p in props.values() if bool(p.Show)]
            hidden = " (it is a hidden helper; pass allow_hidden only if you know why)" if prop is not None else ""
            raise AcadError(f"No property '{name}' to set{hidden}. This block shows: {', '.join(shown) or 'none'}.")
        if bool(prop.ReadOnly):
            raise AcadError(f"Property '{prop.PropertyName}' is read-only.")
        current, allowed = prop.Value, list(prop.AllowedValues or ())
        if isinstance(current, str):
            value: Any = str(wanted)
            if allowed:
                match = next((a for a in allowed if str(a).lower() == value.lower()), None)
                if match is None:
                    raise AcadError(f"'{wanted}' is not an allowed {prop.PropertyName}; choose from "
                                    f"{', '.join(map(str, allowed))}.")
                value = str(match)
        else:
            value = number(wanted)
            if allowed and not any(abs(float(a) - value) < 1e-6 for a in allowed):
                raise AcadError(f"{wanted} is not an allowed {prop.PropertyName}; choose from "
                                f"{', '.join(str(_plain(a)) for a in allowed)}.")
        change.on_rollback(lambda k=key, old=current: _set(ref, k, old))
        prop.Value = value


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
                 attribute_values: dict[str, str] | None = None, layer: str = "",
                 dynamic_properties: dict[str, str | float] | None = None, name: str = "") -> dict:
    """Insert a block reference, optionally filling in its attributes and dynamic properties.

    Args:
        block: a block defined in the drawing (see list_blocks), or the full path of a
            .dwg to insert as a block.
        position: insertion point [x, y].
        scale: uniform scale factor.
        rotation: degrees counter-clockwise.
        attribute_values: attribute values by tag, e.g. {"MARK": "W101", "SIZE": "36x48"}.
        layer: layer to put it on (default: current layer).
        dynamic_properties: for a dynamic block, values by property name, set in this order,
            e.g. {"Size": "#10-16", "Length": "1 1/4"} (see set_block_properties).
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
        if dynamic_properties:
            apply_properties(ref, dynamic_properties, change)
            doc.Regen(1)  # fields in attributes (labels) update on regen
        info = place(change, ref, layer)
        if dynamic_properties:
            info["dynamic_properties"] = {p["name"]: p["value"] for p in map(property_info, block_props(ref).values())
                                          if p["shown"]}
        return info


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


def describe_block(ref: Any, include_hidden: bool = False) -> dict:
    props = [property_info(p) for p in block_props(ref).values()]
    return {
        "handle": str(ref.Handle),
        "block": str(getattr(ref, "EffectiveName", ref.Name)),
        "dynamic": bool(getattr(ref, "IsDynamicBlock", False)),
        "properties": [p for p in props if p["shown"] or include_hidden],
        "attributes": block_attributes(ref),
    }


@acad_tool(read_only=True)
def get_block_properties(handle: str, include_hidden: bool = False, name: str = "") -> dict:
    """Read a block reference's dynamic properties (value, allowed values) and attributes
    (value, invisible). Works on any open drawing.

    Args:
        handle: the block reference's handle (from query_entities or insert_block).
        include_hidden: also list helper properties the block's author hid from users.
        name: which open drawing (default: active).
    """
    return describe_block(block_ref(session.document(name), handle), include_hidden)


@acad_tool()
def set_block_properties(handle: str, properties: dict[str, str | float], regen: bool = True,
                         allow_hidden: bool = False, name: str = "") -> dict:
    """Set dynamic block properties by name, in the order given, as one undo step; if any
    value is refused, all are put back. Distances take numbers or inch fractions ("1 1/4").
    Lists (e.g. Size) must use one of the allowed values (see get_block_properties).

    Args:
        handle: the block reference's handle.
        properties: values by property name, e.g. {"Size": "#10-16", "Length": 1.25}.
        regen: regenerate afterwards so fields in attributes (labels) show the new values.
        allow_hidden: also allow helper properties the author hid (normally driven by
            another property; setting them directly can break the block's lookup).
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    with session.edit(doc) as change:
        ref = block_ref(doc, handle)
        if not bool(getattr(ref, "IsDynamicBlock", False)):
            raise AcadError(f"Handle {handle} is not a dynamic block; it has no properties to set.")
        apply_properties(ref, properties, change, allow_hidden)
        if regen:
            doc.Regen(1)  # fields in attributes update on regen
        return describe_block(ref)


def _geometry(part: Any) -> dict:
    kind = str(part.ObjectName)
    info: dict = {"type": kind}
    if kind == "AcDbLine":
        info["start"], info["end"] = rounded(part.StartPoint[:2]), rounded(part.EndPoint[:2])
    elif kind == "AcDbPolyline":
        info["points"] = rounded(part.Coordinates)
        info["closed"] = bool(part.Closed)
    elif kind in ("AcDbCircle", "AcDbArc"):
        info["center"], info["radius"] = rounded(part.Center[:2]), round(float(part.Radius), 6)
    return info


@acad_tool()
def measure_block(handle: str, include_geometry: bool = False, name: str = "") -> dict:
    """Measure what a block reference actually shows (after its visibility state, stretches
    and arrays): extents and object counts, and optionally each visible line, polyline, arc
    and circle. Works by exploding a temporary copy, which is deleted again, so it only
    runs on drawings this server may edit. Attribute text is counted but not measured.

    Args:
        handle: the block reference's handle.
        include_geometry: also list the visible objects (lines with start/end, polylines with
            their points, arcs and circles with centre/radius; at most 400).
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    with session.edit(doc) as change:
        ref = block_ref(doc, handle)
        parts = [change.add(p) for p in ref.Explode()]
        try:
            geometry = [p for p in parts if str(p.ObjectName) not in NOT_GEOMETRY]
            counts = Counter(str(p.ObjectName) for p in parts)
            result: dict = {"handle": str(ref.Handle), "block": str(getattr(ref, "EffectiveName", ref.Name)),
                            "counts": dict(sorted(counts.items()))}
            boxes = [p.GetBoundingBox() for p in geometry]
            if boxes:
                lo = [min(b[0][0] for b in boxes), min(b[0][1] for b in boxes)]
                hi = [max(b[1][0] for b in boxes), max(b[1][1] for b in boxes)]
                base = list(ref.InsertionPoint)[:2]
                result["extents"] = {"min": rounded(lo), "max": rounded(hi), "width": round(hi[0] - lo[0], 6),
                                     "height": round(hi[1] - lo[1], 6)}
                result["extents_from_insertion_point"] = {
                    "min": rounded([lo[0] - base[0], lo[1] - base[1]]),
                    "max": rounded([hi[0] - base[0], hi[1] - base[1]])}
            if include_geometry:
                result["geometry"] = [_geometry(p) for p in geometry[:MAX_GEOMETRY]]
                if len(geometry) > MAX_GEOMETRY:
                    result["geometry_truncated"] = len(geometry)
            return result
        finally:
            for p in parts:
                p.Delete()
            change.created.clear()
