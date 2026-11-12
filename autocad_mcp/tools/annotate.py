"""Dimensions and leaders."""

from __future__ import annotations

import math

from ..app import acad_tool
from ..com import AcadError, doubles, point, rad, xyz
from ..session import session
from .draw import Point, place

DIMENSION_KINDS = {"aligned": None, "horizontal": 0.0, "vertical": 90.0, "rotated": None}


@acad_tool()
def add_dimension(first: Point, second: Point, text_position: Point, kind: str = "aligned",
                  rotation: float = 0, text_override: str = "", layer: str = "", name: str = "") -> dict:
    """Add a linear dimension between two points, using the current dimension style.

    When the text does not fit between the extension lines, AutoCAD puts it outside, beyond
    the second point. For a short dimension in a chain, give the two points in the order that
    sends the text to free space.

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


@acad_tool()
def add_radial_dimension(center: Point, point_on_curve: Point, kind: str = "diameter", leader_length: float = 0,
                         text_override: str = "", layer: str = "", name: str = "") -> dict:
    """Dimension a circle or arc by its diameter (Ø) or radius (R), using the current dimension style.

    Args:
        center: centre of the circle or arc [x, y].
        point_on_curve: a point on the circle or arc where the dimension line meets it [x, y];
            for a diameter the line runs from here through the centre.
        kind: diameter or radius.
        leader_length: how far the text sits outside the curve, in drawing units (0 keeps it close).
        text_override: replace the measured text, e.g. "<> THRU, 4 PLACES" keeps the value and adds to it.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    kind = kind.lower()
    if kind not in ("diameter", "radius"):
        raise AcadError("kind must be diameter or radius.")
    cx, cy, cz = xyz(center)
    px, py, pz = xyz(point_on_curve)
    if math.isclose(cx, px) and math.isclose(cy, py):
        raise AcadError("point_on_curve must be on the curve, not at the centre.")
    doc = session.document(name)
    with session.edit(doc) as change:
        if kind == "radius":
            dim = doc.ModelSpace.AddDimRadial(point(center), point(point_on_curve), float(leader_length))
        else:
            far = [2 * cx - px, 2 * cy - py, 2 * cz - pz]
            dim = doc.ModelSpace.AddDimDiametric(point(point_on_curve), point(far), float(leader_length))
        change.add(dim)
        if text_override:
            dim.TextOverride = text_override
        return place(change, dim, layer)


@acad_tool()
def add_leader(points: list[Point], text: str, layer: str = "", name: str = "") -> dict:
    """Add a multileader (a callout): an arrow at the first point, a line through the next, and text
    at the last, using the current multileader style. Good for notes such as "1/4" DIA THRU, 4 PLACES".

    Args:
        points: two or three points [[x, y], ...]: the arrow tip first, the text end last.
        text: the note; use \\P for a new line.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    if not 2 <= len(points) <= 3:
        raise AcadError("Give two or three points: the arrow tip first, the text end last.")
    if not text.strip():
        raise AcadError("text cannot be empty.")
    doc = session.document(name)
    flat = [c for p in points for c in xyz(p)]
    with session.edit(doc) as change:
        result = doc.ModelSpace.AddMLeader(doubles(flat), 0)
        leader = result[0] if isinstance(result, tuple) else result  # late binding may also return the index
        change.add(leader)
        leader.TextString = text
        return place(change, leader, layer)
