"""2D geometry and text in model space. Every tool is one undo step and returns the new entity."""

from __future__ import annotations

from typing import Any

from ..app import acad_tool
from ..com import AcadError, doubles, point, rad, xyz
from ..session import Edit, session
from .entities import details
from .layers import find_layer

Point = list[float]


def place(change: Edit, ent: Any, layer: str) -> dict:
    """Record a new entity for rollback, put it on its layer and describe it."""
    change.add(ent)
    if layer:
        if find_layer(change.doc, layer) is None:
            raise AcadError(f"No layer named '{layer}'. Create it with add_layer first.")
        ent.Layer = layer
    ent.Update()
    return details(ent)


def flat_xy(points: list[Point]) -> list[float]:
    """[[x, y], ...] -> [x1, y1, x2, y2, ...] for a lightweight polyline (z is ignored)."""
    flat: list[float] = []
    for p in points:
        x, y, _ = xyz(p)
        flat += [x, y]
    return flat


@acad_tool()
def draw_line(start: Point, end: Point, layer: str = "", name: str = "") -> dict:
    """Draw a line.

    Args:
        start, end: [x, y] or [x, y, z].
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    with session.edit(doc) as change:
        return place(change, doc.ModelSpace.AddLine(point(start), point(end)), layer)


@acad_tool()
def draw_polyline(points: list[Point], closed: bool = False, bulges: list[float] | None = None,
                  layer: str = "", name: str = "") -> dict:
    """Draw a 2D polyline (LWPOLYLINE) through points.

    Args:
        points: [[x, y], ...], at least two.
        closed: join the last point back to the first.
        bulges: optional arc bulge per vertex (0 straight, 1 semicircle, negative clockwise);
            the segment from vertex i to i+1 uses bulges[i].
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    if len(points) < 2:
        raise AcadError("A polyline needs at least two points.")
    if bulges is not None and len(bulges) != len(points):
        raise AcadError("Give one bulge per point (or none).")
    doc = session.document(name)
    with session.edit(doc) as change:
        pline = doc.ModelSpace.AddLightWeightPolyline(doubles(flat_xy(points)))
        change.add(pline)
        for i, bulge in enumerate(bulges or []):
            if bulge:
                pline.SetBulge(i, float(bulge))
        pline.Closed = closed
        return place(change, pline, layer)


@acad_tool()
def draw_rectangle(corner: Point, opposite_corner: Point, layer: str = "", name: str = "") -> dict:
    """Draw an axis-aligned rectangle as a closed polyline.

    Args:
        corner, opposite_corner: two opposite corners [x, y].
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    (x1, y1, _), (x2, y2, _) = xyz(corner), xyz(opposite_corner)
    if x1 == x2 or y1 == y2:
        raise AcadError("The corners must differ in both x and y.")
    doc = session.document(name)
    with session.edit(doc) as change:
        pline = doc.ModelSpace.AddLightWeightPolyline(doubles([x1, y1, x2, y1, x2, y2, x1, y2]))
        change.add(pline)
        pline.Closed = True
        return place(change, pline, layer)


@acad_tool()
def draw_circle(center: Point, radius: float, layer: str = "", name: str = "") -> dict:
    """Draw a circle.

    Args:
        center: [x, y] or [x, y, z].
        radius: radius in drawing units.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    if radius <= 0:
        raise AcadError("radius must be positive.")
    doc = session.document(name)
    with session.edit(doc) as change:
        return place(change, doc.ModelSpace.AddCircle(point(center), float(radius)), layer)


@acad_tool()
def draw_center_mark(center: Point, radius: float, extension: float = 0.0625, layer: str = "",
                     name: str = "") -> dict:
    """Draw a centre mark: two crossing lines through the centre of a hole or arc, reaching a
    little past the curve. Both lines are one undo step. Use a centre-line layer.

    Args:
        center: centre of the hole or arc [x, y].
        radius: radius of the hole or arc being marked.
        extension: how far the lines reach past the curve, in drawing units.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    if radius <= 0 or extension < 0:
        raise AcadError("radius must be positive and extension zero or more.")
    x, y, z = xyz(center)
    half = radius + extension
    doc = session.document(name)
    with session.edit(doc) as change:
        across = place(change, doc.ModelSpace.AddLine(point([x - half, y, z]), point([x + half, y, z])), layer)
        upright = place(change, doc.ModelSpace.AddLine(point([x, y - half, z]), point([x, y + half, z])), layer)
        return {"handles": [across["handle"], upright["handle"]], "center": [x, y, z], "half_length": half,
                "layer": across["layer"]}


@acad_tool()
def draw_arc(center: Point, radius: float, start_angle: float, end_angle: float,
             layer: str = "", name: str = "") -> dict:
    """Draw an arc counter-clockwise from start_angle to end_angle.

    Args:
        center: [x, y] or [x, y, z].
        radius: radius in drawing units.
        start_angle, end_angle: degrees from +X, counter-clockwise.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    if radius <= 0:
        raise AcadError("radius must be positive.")
    doc = session.document(name)
    with session.edit(doc) as change:
        arc = doc.ModelSpace.AddArc(point(center), float(radius), rad(start_angle), rad(end_angle))
        return place(change, arc, layer)


@acad_tool()
def add_text(text: str, position: Point, height: float, rotation: float = 0, layer: str = "",
             name: str = "") -> dict:
    """Add single-line text (TEXT) with its insertion point at position.

    Args:
        text: the text.
        position: insertion point [x, y].
        height: text height in drawing units.
        rotation: degrees counter-clockwise.
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    if height <= 0:
        raise AcadError("height must be positive.")
    doc = session.document(name)
    with session.edit(doc) as change:
        ent = doc.ModelSpace.AddText(text, point(position), float(height))
        change.add(ent)
        if rotation:
            ent.Rotation = rad(rotation)
        return place(change, ent, layer)


@acad_tool()
def add_mtext(text: str, position: Point, width: float, height: float = 0, layer: str = "",
              name: str = "") -> dict:
    """Add multiline text (MTEXT). Its top-left corner is at position.

    Args:
        text: the text; use \\P for a new paragraph.
        position: top-left corner [x, y].
        width: wrapping width in drawing units (0 for no wrapping).
        height: text height (0 keeps the style's height).
        layer: layer to put it on (default: current layer).
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    with session.edit(doc) as change:
        ent = doc.ModelSpace.AddMText(point(position), float(width), text)
        change.add(ent)
        if height > 0:
            ent.Height = float(height)
        return place(change, ent, layer)
