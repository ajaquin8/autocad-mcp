"""Shared helpers for reading entities: summaries, details and handle lookup. No tools here."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pywintypes

from ..com import AcadError, deg, rounded

BYLAYER = 256


def by_handle(doc: Any, handle: str) -> Any:
    try:
        return doc.HandleToObject(str(handle).strip().upper())
    except pywintypes.com_error:
        raise AcadError(f"No object with handle '{handle}' in '{doc.Name}'.") from None


def handles(value: str | list[str]) -> list[str]:
    """'1A, 2B;3C' or ['1A', '2B'] -> ['1A', '2B', ...]."""
    items = value.replace(";", ",").split(",") if isinstance(value, str) else value
    return [str(h).strip().upper() for h in items if str(h).strip()]


def model_space(doc: Any) -> Iterator[Any]:
    space = doc.ModelSpace
    for i in range(space.Count):
        yield space.Item(i)


def color_name(index: int) -> str | int:
    return {0: "ByBlock", BYLAYER: "ByLayer"}.get(int(index), int(index))


def summary(ent: Any) -> dict:
    """Handle, type and layer, plus the bounding box when AutoCAD can give one."""
    info = {"handle": str(ent.Handle), "type": str(ent.ObjectName), "layer": str(ent.Layer)}
    try:
        lo, hi = ent.GetBoundingBox()
        info["bbox"] = [rounded(lo[:2]), rounded(hi[:2])]
    except (pywintypes.com_error, TypeError, ValueError):
        pass
    return info


def attributes(ref: Any) -> dict[str, str]:
    if not bool(ref.HasAttributes):
        return {}
    return {str(a.TagString): str(a.TextString) for a in ref.GetAttributes()}


def details(ent: Any) -> dict:
    """Summary plus the properties that matter for the entity's type."""
    info = summary(ent)
    kind = info["type"]
    info["color"] = color_name(ent.color)
    info["linetype"] = str(ent.Linetype)
    if kind == "AcDbLine":
        info.update(start=rounded(ent.StartPoint), end=rounded(ent.EndPoint), length=round(ent.Length, 6),
                    angle=round(deg(ent.Angle), 6))
    elif kind == "AcDbCircle":
        info.update(center=rounded(ent.Center), radius=round(ent.Radius, 6))
    elif kind == "AcDbArc":
        info.update(center=rounded(ent.Center), radius=round(ent.Radius, 6),
                    start_angle=round(deg(ent.StartAngle), 6), end_angle=round(deg(ent.EndAngle), 6),
                    arc_length=round(ent.ArcLength, 6))
    elif kind == "AcDbPolyline":
        flat = list(ent.Coordinates)
        vertices = [rounded(flat[i:i + 2]) for i in range(0, len(flat), 2)]
        bulges = [round(ent.GetBulge(i), 6) for i in range(len(vertices))]
        info.update(vertices=vertices, closed=bool(ent.Closed), length=round(ent.Length, 6))
        if any(bulges):
            info["bulges"] = bulges
        if info["closed"]:
            info["area"] = round(ent.Area, 6)
    elif kind == "AcDbText":
        info.update(text=str(ent.TextString), position=rounded(ent.InsertionPoint), height=ent.Height,
                    rotation=round(deg(ent.Rotation), 6), style=str(ent.StyleName))
    elif kind == "AcDbMText":
        info.update(text=str(ent.TextString), position=rounded(ent.InsertionPoint), width=ent.Width,
                    height=ent.Height, style=str(ent.StyleName))
    elif kind == "AcDbMLeader":
        info["text"] = str(ent.TextString)
    elif kind == "AcDbViewport":
        info.update(center=rounded(ent.Center), width=round(ent.Width, 6), height=round(ent.Height, 6),
                    scale=round(ent.CustomScale, 9), locked=bool(ent.DisplayLocked))
    elif kind == "AcDbBlockReference":
        info.update(name=str(ent.Name), effective_name=str(ent.EffectiveName),
                    position=rounded(ent.InsertionPoint), rotation=round(deg(ent.Rotation), 6),
                    scale=rounded([ent.XScaleFactor, ent.YScaleFactor, ent.ZScaleFactor]),
                    attributes=attributes(ent))
    elif "Dimension" in kind:
        info.update(measurement=round(ent.Measurement, 6), text_override=str(ent.TextOverride))
    return info


def find_layout(doc: Any, name: str) -> Any:
    """The layout with this name (case-insensitive), or an error that lists the ones there are."""
    layouts = [doc.Layouts.Item(i) for i in range(doc.Layouts.Count)]
    for layout in layouts:
        if str(layout.Name).lower() == name.strip().lower():
            return layout
    raise AcadError(f"No layout named '{name}' in '{doc.Name}'. Layouts: "
                    f"{', '.join(str(lay.Name) for lay in layouts)}.")


def layout_space(doc: Any, layout: str) -> Iterator[Any]:
    """The entities on one layout (its paper space), like model_space for model space."""
    block = find_layout(doc, layout).Block
    for i in range(block.Count):
        yield block.Item(i)
