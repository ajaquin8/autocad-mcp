"""2D geometry and text, in model space or on a sheet. Every tool is one undo step and returns the
new entity, with the space it went into."""

from __future__ import annotations

from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, doubles, enums, point, rad, xyz
from ..session import Edit, session
from .entities import details, find_layout
from .layers import find_layer

Point = list[float]

# Text justification: our names -> AutoCAD's AcAlignment constants (TEXT and ATTDEF).
TEXT_JUSTIFY = {
    "left": "acAlignmentLeft", "center": "acAlignmentCenter", "right": "acAlignmentRight",
    "middle": "acAlignmentMiddle", "top_left": "acAlignmentTopLeft", "top_center": "acAlignmentTopCenter",
    "top_right": "acAlignmentTopRight", "middle_left": "acAlignmentMiddleLeft",
    "middle_center": "acAlignmentMiddleCenter", "middle_right": "acAlignmentMiddleRight",
    "bottom_left": "acAlignmentBottomLeft", "bottom_center": "acAlignmentBottomCenter",
    "bottom_right": "acAlignmentBottomRight",
}
# MTEXT attachment points -> AcAttachmentPoint constants.
MTEXT_ATTACH = {key: "acAttachmentPoint" + "".join(w.title() for w in key.split("_"))
                for key in ("top_left", "top_center", "top_right", "middle_left", "middle_center", "middle_right",
                            "bottom_left", "bottom_center", "bottom_right")}
# AutoCAD's own short forms, as typed at the TEXT command's Justify prompt.
SHORT = {"l": "left", "c": "center", "r": "right", "m": "middle", "tl": "top_left", "tc": "top_center",
         "tr": "top_right", "ml": "middle_left", "mc": "middle_center", "mr": "middle_right", "bl": "bottom_left",
         "bc": "bottom_center", "br": "bottom_right"}


def justification(value: str, table: dict[str, str], what: str) -> str:
    """'Middle Center', 'middle-center' or 'MC' -> 'middle_center', checked against the table."""
    key = "_".join(str(value).strip().lower().replace("-", " ").split())
    key = SHORT.get(key, key)
    if key not in table:
        raise AcadError(f"{what} is one of {', '.join(table)} (or TL, MC, BR ...); got '{value}'.")
    return key


def text_style(doc: Any, wanted: str) -> str:
    """The text style's name as the drawing spells it, or an error listing the styles there are."""
    styles = doc.TextStyles
    names = [str(styles.Item(i).Name) for i in range(styles.Count)]
    for found in names:
        if found.lower() == wanted.strip().lower():
            return found
    raise AcadError(f"No text style named '{wanted}'. The drawing has: {', '.join(names)} (add_text_style makes one).")


def finish_text(doc: Any, ent: Any, position: Point, justify: str, style: str) -> dict:
    """Style and justification for a new TEXT or ATTDEF; with a justification other than left,
    position is the justification point (as at the TEXT command)."""
    info: dict = {}
    if style:
        ent.StyleName = text_style(doc, style)
    key = justification(justify, TEXT_JUSTIFY, "justify")
    if key != "left":
        ent.Alignment = getattr(enums, TEXT_JUSTIFY[key])
        ent.TextAlignmentPoint = point(position)  # after Alignment: setting it first has no effect
        info["justification_point"] = [round(v, 6) for v in xyz(position)]
    info["justify"] = key
    return info


def drawing_space(doc: Any, layout: str = "") -> tuple[Any, dict]:
    """Where a tool puts new objects, and how its result says so: model space by default, or the
    paper space of the sheet named by layout. Before 2026-11-18 the result did not say, and with a
    sheet tab active the objects still went into model space unnoticed: a following -BLOCK then
    found them "not in current space" (B6). Now the result carries a note in that case."""
    if layout:
        sheet = find_layout(doc, layout)
        if not bool(sheet.ModelType):
            return sheet.Block, {"space": "paper", "layout": str(sheet.Name)}
        return doc.ModelSpace, {"space": "model"}
    where: dict = {"space": "model"}
    try:
        active = doc.ActiveLayout
        on_sheet = not bool(active.ModelType) and not bool(doc.MSpace)
    except (pywintypes.com_error, AttributeError):
        on_sheet = False  # only a hint; never a reason to fail
    if on_sheet:
        sheet_name = str(active.Name)
        where["note"] = (f"The sheet '{sheet_name}' is the active tab, but this went into model space (shown "
                         f"through its viewports, if any). Pass layout='{sheet_name}' to draw on the sheet itself.")
    return doc.ModelSpace, where


def place(change: Edit, ent: Any, layer: str, where: dict | None = None) -> dict:
    """Record a new entity for rollback, put it on its layer and describe it (and where it went)."""
    change.add(ent)
    if layer:
        if find_layer(change.doc, layer) is None:
            raise AcadError(f"No layer named '{layer}'. Create it with add_layer first.")
        ent.Layer = layer
    ent.Update()
    info = details(ent)
    info.update(where or {})
    return info


def flat_xy(points: list[Point]) -> list[float]:
    """[[x, y], ...] -> [x1, y1, x2, y2, ...] for a lightweight polyline (z is ignored)."""
    flat: list[float] = []
    for p in points:
        x, y, _ = xyz(p)
        flat += [x, y]
    return flat


@acad_tool()
def draw_line(start: Point, end: Point, layer: str = "", layout: str = "", name: str = "") -> dict:
    """Draw a line.

    Args:
        start, end: [x, y] or [x, y, z].
        layer: layer to put it on (default: current layer).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        return place(change, space.AddLine(point(start), point(end)), layer, where)


@acad_tool()
def draw_polyline(points: list[Point], closed: bool = False, bulges: list[float] | None = None,
                  layer: str = "", layout: str = "", name: str = "") -> dict:
    """Draw a 2D polyline (LWPOLYLINE) through points.

    Args:
        points: [[x, y], ...], at least two.
        closed: join the last point back to the first.
        bulges: optional arc bulge per vertex (0 straight, 1 semicircle, negative clockwise);
            the segment from vertex i to i+1 uses bulges[i].
        layer: layer to put it on (default: current layer).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    if len(points) < 2:
        raise AcadError("A polyline needs at least two points.")
    if bulges is not None and len(bulges) != len(points):
        raise AcadError("Give one bulge per point (or none).")
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        pline = space.AddLightWeightPolyline(doubles(flat_xy(points)))
        change.add(pline)
        for i, bulge in enumerate(bulges or []):
            if bulge:
                pline.SetBulge(i, float(bulge))
        pline.Closed = closed
        return place(change, pline, layer, where)


@acad_tool()
def draw_rectangle(corner: Point, opposite_corner: Point, layer: str = "", layout: str = "",
                   name: str = "") -> dict:
    """Draw an axis-aligned rectangle as a closed polyline.

    Args:
        corner, opposite_corner: two opposite corners [x, y].
        layer: layer to put it on (default: current layer).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    (x1, y1, _), (x2, y2, _) = xyz(corner), xyz(opposite_corner)
    if x1 == x2 or y1 == y2:
        raise AcadError("The corners must differ in both x and y.")
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        pline = space.AddLightWeightPolyline(doubles([x1, y1, x2, y1, x2, y2, x1, y2]))
        change.add(pline)
        pline.Closed = True
        return place(change, pline, layer, where)


@acad_tool()
def draw_circle(center: Point, radius: float, layer: str = "", layout: str = "", name: str = "") -> dict:
    """Draw a circle.

    Args:
        center: [x, y] or [x, y, z].
        radius: radius in drawing units.
        layer: layer to put it on (default: current layer).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    if radius <= 0:
        raise AcadError("radius must be positive.")
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        return place(change, space.AddCircle(point(center), float(radius)), layer, where)


@acad_tool()
def draw_center_mark(center: Point, radius: float, extension: float = 0.0625, layer: str = "",
                     layout: str = "", name: str = "") -> dict:
    """Draw a centre mark: two crossing lines through the centre of a hole or arc, reaching a
    little past the curve. Both lines are one undo step. Use a centre-line layer.

    Args:
        center: centre of the hole or arc [x, y].
        radius: radius of the hole or arc being marked.
        extension: how far the lines reach past the curve, in drawing units.
        layer: layer to put it on (default: current layer).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    if radius <= 0 or extension < 0:
        raise AcadError("radius must be positive and extension zero or more.")
    x, y, z = xyz(center)
    half = radius + extension
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        across = place(change, space.AddLine(point([x - half, y, z]), point([x + half, y, z])), layer, where)
        upright = place(change, space.AddLine(point([x, y - half, z]), point([x, y + half, z])), layer, where)
        return {"handles": [across["handle"], upright["handle"]], "center": [x, y, z], "half_length": half,
                "layer": across["layer"], **where}


@acad_tool()
def draw_arc(center: Point, radius: float, start_angle: float, end_angle: float,
             layer: str = "", layout: str = "", name: str = "") -> dict:
    """Draw an arc counter-clockwise from start_angle to end_angle.

    Args:
        center: [x, y] or [x, y, z].
        radius: radius in drawing units.
        start_angle, end_angle: degrees from +X, counter-clockwise.
        layer: layer to put it on (default: current layer).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    if radius <= 0:
        raise AcadError("radius must be positive.")
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        arc = space.AddArc(point(center), float(radius), rad(start_angle), rad(end_angle))
        return place(change, arc, layer, where)


@acad_tool()
def add_text(text: str, position: Point, height: float, rotation: float = 0, layer: str = "",
             justify: str = "left", style: str = "", layout: str = "", name: str = "") -> dict:
    """Add single-line text (TEXT). position is where the justification point goes: the
    left end of the baseline by default, the centre of the text with justify="middle_center",
    so a centred label is one call.

    Args:
        text: the text.
        position: the justification point [x, y].
        height: text height in drawing units (a style with a fixed height overrides it).
        rotation: degrees counter-clockwise.
        layer: layer to put it on (default: current layer).
        justify: left (default), center, right, middle, top_left, top_center, top_right,
            middle_left, middle_center, middle_right, bottom_left, bottom_center or
            bottom_right; AutoCAD's short forms (TL, MC, BR ...) work too. center and right
            sit on the baseline; middle is the middle of the text's height and width.
        style: text style to use, e.g. one made with add_text_style (default: the current one).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    if height <= 0:
        raise AcadError("height must be positive.")
    justification(justify, TEXT_JUSTIFY, "justify")
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        ent = space.AddText(text, point(position), float(height))
        change.add(ent)
        extra = finish_text(doc, ent, position, justify, style)
        if rotation:
            ent.Rotation = rad(rotation)
        info = place(change, ent, layer, where)
        info.update(extra)
        return info


@acad_tool()
def add_mtext(text: str, position: Point, width: float, height: float = 0, layer: str = "",
              attachment: str = "top_left", style: str = "", mask: bool = False, layout: str = "",
              name: str = "") -> dict:
    """Add multiline text (MTEXT). position is its attachment point: the top-left corner by
    default, the centre with attachment="middle_center".

    Args:
        text: the text; use \\P for a new paragraph.
        position: the attachment point [x, y].
        width: wrapping width in drawing units (0 for no wrapping).
        height: text height (0 keeps the style's height).
        layer: layer to put it on (default: current layer).
        attachment: top_left (default), top_center, top_right, middle_left, middle_center,
            middle_right, bottom_left, bottom_center or bottom_right (or TL, MC, BR ...).
        style: text style to use (default: the current one).
        mask: True to give the text a background mask, so it stays legible over hatches and
            lines (AutoCAD's default mask: drawing background colour, border offset 1.5).
            set_text_mask turns it on or off later.
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    key = justification(attachment, MTEXT_ATTACH, "attachment")
    doc = session.document(name)
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        ent = space.AddMText(point(position), float(width), text)
        change.add(ent)
        if style:
            ent.StyleName = text_style(doc, style)
        if height > 0:
            ent.Height = float(height)
        if key != "top_left":
            ent.AttachmentPoint = getattr(enums, MTEXT_ATTACH[key])
            ent.InsertionPoint = point(position)  # the attachment point stays at position
        if mask:
            ent.BackgroundFill = True
        info = place(change, ent, layer, where)
        info["attachment"] = key
        return info
