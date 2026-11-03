"""Dimensions."""

from __future__ import annotations

from ..app import acad_tool
from ..com import AcadError, point, rad
from ..session import session
from .draw import Point, place

DIMENSION_KINDS = {"aligned": None, "horizontal": 0.0, "vertical": 90.0, "rotated": None}


@acad_tool()
def add_dimension(first: Point, second: Point, text_position: Point, kind: str = "aligned",
                  rotation: float = 0, text_override: str = "", layer: str = "", name: str = "") -> dict:
    """Add a linear dimension between two points, using the current dimension style.

    Args:
        first, second: the two points being measured [x, y].
        text_position: a point on the dimension line, where the text goes [x, y].
        kind: aligned (parallel to the points), horizontal, vertical, or rotated (uses rotation).
        rotation: degrees, only for kind=rotated.
        text_override: replace the measured text, e.g. "<> TYP" keeps the value and adds TYP.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    kind = kind.lower()
    if kind not in DIMENSION_KINDS:
        raise AcadError(f"kind must be one of {', '.join(DIMENSION_KINDS)}.")
    doc = session.document(name)
    space = doc.ModelSpace
    with session.edit(doc) as change:
        if kind == "aligned":
            dim = space.AddDimAligned(point(first), point(second), point(text_position))
        else:
            angle = rotation if kind == "rotated" else DIMENSION_KINDS[kind]
            dim = space.AddDimRotated(point(first), point(second), point(text_position), rad(angle))
        change.add(dim)
        if text_override:
            dim.TextOverride = text_override
        return place(change, dim, layer)
