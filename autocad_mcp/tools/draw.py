"""2D geometry and text, in model space or on a sheet. Every tool is one undo step and returns the
new entity, with the space it went into."""

from __future__ import annotations

from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, describe_com_error, doubles, enums, point, rad, xyz
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
              attachment: str = "top_left", style: str = "", layout: str = "", name: str = "") -> dict:
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
        info = place(change, ent, layer, where)
        info["attachment"] = key
        return info


# ---------- many entities in one call (GAP-018) ----------

MAX_BATCH = 2000
# Fields each entity type takes: (required, optional). Anything else is refused, so a typo
# ("raduis") fails before AutoCAD is touched instead of being silently ignored.
BATCH_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "line": (("start", "end"), ("layer",)),
    "polyline": (("points",), ("closed", "bulges", "layer")),
    "circle": (("center", "radius"), ("layer",)),
    "arc": (("center", "radius", "start_angle", "end_angle"), ("layer",)),
    "text": (("text", "position", "height"), ("rotation", "justify", "style", "layer")),
    "mtext": (("text", "position", "width"), ("height", "attachment", "style", "layer")),
}


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number, got {value!r}")
    return float(value)


def check_batch_entity(spec: Any) -> dict:
    """One create_entities entry, checked without AutoCAD; ValueError says what is wrong."""
    if not isinstance(spec, dict):
        raise ValueError(f"each entity is an object with a \"type\", got {spec!r}")
    kind = str(spec.get("type", "")).strip().lower()
    if kind not in BATCH_FIELDS:
        raise ValueError(f"type is one of {', '.join(BATCH_FIELDS)}; got {spec.get('type')!r}")
    required, optional = BATCH_FIELDS[kind]
    missing = [f for f in required if f not in spec]
    unknown = [f for f in spec if f != "type" and f not in required + optional]
    if unknown:
        raise ValueError(f"unknown field(s) {', '.join(unknown)}; a {kind} takes {', '.join(required + optional)}")
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    out: dict[str, Any] = {**spec, "type": kind}
    for key in ("start", "end", "center", "position"):
        if key in out:
            out[key] = list(xyz(out[key]))
    if kind == "polyline":
        points = out["points"]
        if isinstance(points, str) or not isinstance(points, list) or len(points) < 2:
            raise ValueError("a polyline needs at least two points")
        out["points"] = [list(xyz(p)) for p in points]
        bulges = out.get("bulges")
        if bulges is not None:
            if not isinstance(bulges, list) or len(bulges) != len(points):
                raise ValueError("give one bulge per point (or none)")
            out["bulges"] = [_number(b, "a bulge") for b in bulges]
        out["closed"] = bool(out.get("closed", False))
    if "radius" in out and _number(out["radius"], "radius") <= 0:
        raise ValueError("radius must be positive")
    for key in ("start_angle", "end_angle", "rotation", "width"):
        if key in out:
            out[key] = _number(out[key], key)
    if kind == "text":
        if _number(out["height"], "height") <= 0:
            raise ValueError("height must be positive")
        out["justify"] = justification(out.get("justify", "left"), TEXT_JUSTIFY, "justify")
    if kind == "mtext":
        if out["width"] < 0:
            raise ValueError("width must be zero or more")
        out["height"] = _number(out.get("height", 0), "height")
        out["attachment"] = justification(out.get("attachment", "top_left"), MTEXT_ATTACH, "attachment")
    if kind in ("text", "mtext") and not isinstance(out["text"], str):
        raise ValueError("text must be a string")
    if "layer" in out and not isinstance(out["layer"], str):
        raise ValueError("layer must be a layer name")
    if "style" in out and not isinstance(out["style"], str):
        raise ValueError("style must be a text style name")
    return out


def _add_batch_entity(change: Edit, space: Any, spec: dict, styles: dict[str, str]) -> Any:
    """Create one checked entry in space and record it for rollback at once (before any property
    is set); the layer is set by the caller. Returns the new entity."""
    kind = spec["type"]
    if kind == "line":
        return change.add(space.AddLine(point(spec["start"]), point(spec["end"])))
    if kind == "polyline":
        pline = change.add(space.AddLightWeightPolyline(doubles(flat_xy(spec["points"]))))
        for i, bulge in enumerate(spec.get("bulges") or []):
            if bulge:
                pline.SetBulge(i, bulge)
        if spec["closed"]:
            pline.Closed = True
        return pline
    if kind == "circle":
        return change.add(space.AddCircle(point(spec["center"]), float(spec["radius"])))
    if kind == "arc":
        return change.add(space.AddArc(point(spec["center"]), float(spec["radius"]), rad(spec["start_angle"]),
                                       rad(spec["end_angle"])))
    style = styles.get(spec.get("style", "").strip().lower(), "")
    if kind == "text":
        ent = change.add(space.AddText(spec["text"], point(spec["position"]), float(spec["height"])))
        if style:
            ent.StyleName = style
        if spec["justify"] != "left":
            ent.Alignment = getattr(enums, TEXT_JUSTIFY[spec["justify"]])
            ent.TextAlignmentPoint = point(spec["position"])  # after Alignment, as in finish_text
        if spec.get("rotation"):
            ent.Rotation = rad(spec["rotation"])
        return ent
    ent = change.add(space.AddMText(point(spec["position"]), float(spec["width"]), spec["text"]))
    if style:
        ent.StyleName = style
    if spec["height"] > 0:
        ent.Height = spec["height"]
    if spec["attachment"] != "top_left":
        ent.AttachmentPoint = getattr(enums, MTEXT_ATTACH[spec["attachment"]])
        ent.InsertionPoint = point(spec["position"])
    return ent


@acad_tool(timeout=600)
def create_entities(entities: list[dict], layer: str = "", layout: str = "", name: str = "") -> dict:
    """Create many lines, polylines, circles, arcs, texts and mtexts in one call and one undo
    step. Every entry is checked before AutoCAD is touched, and if AutoCAD refuses any of them
    the whole batch is rolled back: all or nothing. Use it instead of hundreds of draw_* calls.

    Args:
        entities: up to 2000 objects, each with a "type" and that type's fields (same meaning
            as in the single draw tools; unknown fields are refused):
            {"type": "line", "start": [x, y], "end": [x, y]};
            {"type": "polyline", "points": [[x, y], ...], "closed": false, "bulges": [b, ...]};
            {"type": "circle", "center": [x, y], "radius": r};
            {"type": "arc", "center": [x, y], "radius": r, "start_angle": deg, "end_angle": deg};
            {"type": "text", "text": "...", "position": [x, y], "height": h, "rotation": deg,
            "justify": "middle_center", "style": "..."};
            {"type": "mtext", "text": "...", "position": [x, y], "width": w, "height": h,
            "attachment": "top_left", "style": "..."}.
            Any entry may give "layer" to override the batch layer.
        layer: layer for entries without their own (default: current layer).
        layout: a sheet's layout name to draw on its paper space (default: model space).
        name: which open drawing (default: active).

    Returns how many were created, their handles in the order given, a count per type and
    the space used. Hatches, block inserts and drawing into a block definition are not offered.
    """
    if not isinstance(entities, list) or not entities:
        raise AcadError("entities is a non-empty list of objects, each with a \"type\".")
    if len(entities) > MAX_BATCH:
        raise AcadError(f"At most {MAX_BATCH} entities per call; got {len(entities)}. Split the batch.")
    checked = []
    for i, spec in enumerate(entities):
        try:
            checked.append(check_batch_entity(spec))
        except ValueError as err:
            kind = spec.get("type", "?") if isinstance(spec, dict) else "?"
            raise AcadError(f"entities[{i}] ({kind}): {err}. Nothing was drawn.") from None
    doc = session.document(name)
    for wanted in sorted({s.get("layer") or layer for s in checked} - {""}):
        if find_layer(doc, wanted) is None:
            raise AcadError(f"No layer named '{wanted}'. Create it with add_layer first. Nothing was drawn.")
    styles = {s["style"].strip().lower(): text_style(doc, s["style"])
              for s in checked if s.get("style", "").strip()}
    space, where = drawing_space(doc, layout)
    created: list[str] = []
    counts: dict[str, int] = {}
    with session.edit(doc) as change:
        for i, spec in enumerate(checked):
            try:
                ent = _add_batch_entity(change, space, spec, styles)
                if spec.get("layer") or layer:
                    ent.Layer = spec.get("layer") or layer
                if spec["type"] == "text" and spec["justify"] != "left":
                    ent.Update()  # as add_text does after setting the alignment point
            except pywintypes.com_error as err:
                raise AcadError(f"entities[{i}] ({spec['type']}): AutoCAD refused it "
                                f"({describe_com_error(err)}). The whole batch was rolled back; "
                                "nothing was drawn.") from err
            created.append(str(ent.Handle))
            counts[spec["type"]] = counts.get(spec["type"], 0) + 1
    return {"created": len(created), "handles": created, "counts": counts, **where}
