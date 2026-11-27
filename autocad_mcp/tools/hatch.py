"""Hatches with holes and text islands, in model space or on a sheet. One undo step per call."""

from __future__ import annotations

from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError, doubles, enums, objects, rad, rounded
from ..session import session
from .draw import drawing_space, flat_xy, place
from .entities import by_handle, handles
from .layers import find_layer

Point = list[float]

MAX_LOOPS = 500


def _predefined() -> int:
    """AcPatternType for a pattern from acad.pat. The help spells it acHatchPatternTypePredefined,
    older type libraries acHatchPatternTypePreDefined; the value is 1 in both (inferred, not read live)."""
    for name in ("acHatchPatternTypePreDefined", "acHatchPatternTypePredefined"):
        try:
            return getattr(enums, name)
        except AttributeError:
            continue
    return 1


def _polygon(points: list[Point], what: str) -> list[float]:
    """[[x, y], ...] -> flat x, y list for a closed lightweight polyline, checked."""
    if not isinstance(points, list) or len(points) < 3:
        raise AcadError(f"{what} needs at least three points [[x, y], ...].")
    try:
        flat = flat_xy(points)
    except ValueError as exc:
        raise AcadError(f"{what}: {exc}") from None
    xs, ys = flat[0::2], flat[1::2]
    if abs(sum(xs[i] * ys[i - 1] - xs[i - 1] * ys[i] for i in range(len(xs)))) < 1e-12:
        raise AcadError(f"{what} has no area (all points on one line).")
    return flat


def _island_box(doc: Any, handle: str, margin: float) -> list[float]:
    """The axis-aligned bounding box of an object, grown by margin, as a closed rectangle."""
    ent = by_handle(doc, handle)
    try:
        lo, hi = ent.GetBoundingBox()
    except pywintypes.com_error:
        raise AcadError(f"AutoCAD gives no bounding box for '{handle}' ({ent.ObjectName}); "
                        f"it cannot be a text island.") from None
    x1, y1, x2, y2 = lo[0] - margin, lo[1] - margin, hi[0] + margin, hi[1] + margin
    return [x1, y1, x2, y1, x2, y2, x1, y2]


@acad_tool()
def add_hatch(outer: list[Point], holes: list[list[Point]] | None = None, pattern: str = "SOLID",
              scale: float = 1.0, angle: float = 0.0, text_islands: str | list[str] = "",
              island_margin: float = 0.0, keep_boundaries: bool = False, layer: str = "",
              layout: str = "", name: str = "") -> dict:
    """Hatch a closed area, leaving holes and text unhatched, as one undo step (AddHatch with
    an outer loop and inner loops). Use it for solid fills or patterns behind notes on shop
    drawings: pass the notes as text_islands and the hatch stops short of them.

    Args:
        outer: the boundary [[x, y], ...], at least three points; it is closed for you.
        holes: optional inner boundaries, each [[x, y], ...]; they stay unhatched (islands).
        pattern: a pattern from acad.pat (acadiso.pat in metric drawings), e.g. SOLID
            (default), ANSI31, AR-CONC, AR-SAND. Patterns from other .pat files are not supported.
        scale: pattern scale (ignored for SOLID).
        angle: pattern angle in degrees (ignored for SOLID).
        text_islands: handles of texts, multileaders or other objects to keep clear: each
            object's axis-aligned bounding box (plus island_margin) becomes a hole. Boxes must
            lie inside outer and not overlap each other or the holes.
        island_margin: how far the cleared box reaches past each text_islands object,
            in drawing units.
        keep_boundaries: keep the boundary polylines (on the same layer) and make the hatch
            associative to them. By default they are deleted and the hatch stands alone.
        layer: layer for the hatch (default: current layer).
        layout: a sheet's layout name to hatch on its paper space (default: model space).
        name: which open drawing (default: active).
    """
    loops = [_polygon(outer, "outer")]
    for i, hole in enumerate(holes or []):
        loops.append(_polygon(hole, f"holes[{i}]"))
    island_handles = handles(text_islands) if text_islands else []
    if len(loops) + len(island_handles) > MAX_LOOPS:
        raise AcadError(f"At most {MAX_LOOPS} loops (outer, holes and text islands together) per hatch.")
    pattern = str(pattern).strip().upper()
    if not pattern or any(c in pattern for c in ' ,;"'):
        raise AcadError(f"pattern is a pattern name such as SOLID or ANSI31; got '{pattern}'.")
    if scale <= 0:
        raise AcadError("scale must be positive.")
    if island_margin < 0:
        raise AcadError("island_margin must be zero or more.")
    doc = session.document(name)
    if layer and find_layer(doc, layer) is None:
        raise AcadError(f"No layer named '{layer}'. Create it with add_layer first.")
    loops += [_island_box(doc, h, float(island_margin)) for h in island_handles]
    space, where = drawing_space(doc, layout)
    with session.edit(doc) as change:
        boundaries = []
        for flat in loops:
            pline = change.add(space.AddLightWeightPolyline(doubles(flat)))
            pline.Closed = True
            if layer:
                pline.Layer = layer
            boundaries.append(pline)
        hatch = change.add(space.AddHatch(_predefined(), pattern, bool(keep_boundaries)))
        # AutoCAD help (AddHatch): touch nothing on a new hatch before AppendOuterLoop, or AutoCAD
        # "will enter an unpredictable state". So the loops go first, then scale and angle, then Evaluate.
        hatch.AppendOuterLoop(objects(boundaries[:1]))
        for pline in boundaries[1:]:
            hatch.AppendInnerLoop(objects([pline]))
        if pattern != "SOLID":
            hatch.PatternScale = float(scale)
            hatch.PatternAngle = rad(angle)
        hatch.Evaluate()
        info = place(change, hatch, layer, where)
        info.update(pattern=pattern, loops=len(boundaries), holes=len(holes or []), text_islands=island_handles)
        if pattern != "SOLID":
            info.update(scale=float(scale), angle=float(angle))
        try:
            info["area"] = round(float(hatch.Area), 6)
        except (pywintypes.com_error, AttributeError, TypeError, ValueError):
            pass  # only a report; the hatch is made
        if keep_boundaries:
            info["boundary_handles"] = [str(p.Handle) for p in boundaries]
        else:
            # Last step, so a failure above still rolls the boundaries back with the hatch.
            for pline in boundaries:
                pline.Delete()
                change.created = [o for o in change.created if o is not pline]
        info["associative"] = bool(keep_boundaries)
        if island_handles:
            info["island_boxes"] = [[rounded(flat[0:2]), rounded(flat[4:6])] for flat in loops[-len(island_handles):]]
        return info
