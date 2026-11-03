"""Layers: list, add or update, set current."""

from __future__ import annotations

from typing import Any

import pywintypes

from ..app import acad_tool
from ..com import AcadError
from ..session import session
from .entities import color_name

# Lineweights AutoCAD accepts, in hundredths of a millimetre; -1 ByLayer, -2 ByBlock, -3 Default.
LINEWEIGHTS = {-3, -2, -1, 0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90,
               100, 106, 120, 140, 158, 200, 211}


def find_layer(doc: Any, name: str) -> Any | None:
    try:
        return doc.Layers.Item(name)
    except pywintypes.com_error:
        return None


def ensure_linetype(doc: Any, name: str) -> None:
    """Load a linetype from acadiso.lin (metric drawings) or acad.lin if it is not in the drawing yet."""
    try:
        doc.Linetypes.Item(name)
        return
    except pywintypes.com_error:
        pass
    lin = "acadiso.lin" if int(doc.GetVariable("MEASUREMENT")) == 1 else "acad.lin"
    try:
        doc.Linetypes.Load(name, lin)
    except pywintypes.com_error:
        raise AcadError(f"Linetype '{name}' is not in the drawing or in {lin}.") from None


def describe_layer(layer: Any, current: str) -> dict:
    return {
        "name": str(layer.Name),
        "color": color_name(layer.color),
        "linetype": str(layer.Linetype),
        "lineweight": int(layer.Lineweight),
        "on": bool(layer.LayerOn),
        "frozen": bool(layer.Freeze),
        "locked": bool(layer.Lock),
        "plottable": bool(layer.Plottable),
        "current": str(layer.Name).lower() == current.lower(),
    }


@acad_tool(read_only=True)
def list_layers(name: str = "") -> list:
    """List the drawing's layers with color, linetype, lineweight and on/frozen/locked state.

    Args:
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    current = str(doc.ActiveLayer.Name)
    layers = doc.Layers
    return [describe_layer(layers.Item(i), current) for i in range(layers.Count)]


@acad_tool()
def add_layer(layer: str, color: int = 7, linetype: str = "Continuous", lineweight: int = -3,
              description: str = "", name: str = "") -> dict:
    """Create a layer, or update the color/linetype/lineweight of an existing one.

    Args:
        layer: layer name.
        color: AutoCAD Color Index 1-255 (1 red, 2 yellow, 3 green, 4 cyan, 5 blue, 6 magenta, 7 white/black).
        linetype: e.g. Continuous, HIDDEN, CENTER, DASHED (loaded from acad(iso).lin if needed).
        lineweight: hundredths of a mm, e.g. 25 for 0.25 mm; -3 is Default.
        description: layer description.
        name: which open drawing (default: active).
    """
    if not 1 <= color <= 255:
        raise AcadError("color must be an AutoCAD Color Index from 1 to 255.")
    if lineweight not in LINEWEIGHTS:
        raise AcadError(f"lineweight must be one of {sorted(LINEWEIGHTS)}.")
    doc = session.document(name)
    with session.edit(doc) as change:
        existing = find_layer(doc, layer)
        if existing is None:
            target = change.add(doc.Layers.Add(layer))
        else:
            target = existing
            old = (target.color, str(target.Linetype), int(target.Lineweight), str(target.Description))

            def restore(t=target, o=old) -> None:
                t.color, t.Linetype, t.Lineweight, t.Description = o
            change.on_rollback(restore)
        ensure_linetype(doc, linetype)
        target.color = color
        target.Linetype = linetype
        target.Lineweight = lineweight
        if description:
            target.Description = description
        result = describe_layer(target, str(doc.ActiveLayer.Name))
    result["created"] = existing is None
    return result


@acad_tool()
def set_current_layer(layer: str, name: str = "") -> str:
    """Make a layer current, so new objects from the user land on it too.

    Args:
        layer: layer name (must exist, not frozen).
        name: which open drawing (default: active).
    """
    doc = session.document(name)
    with session.edit(doc) as change:
        target = find_layer(doc, layer)
        if target is None:
            raise AcadError(f"No layer named '{layer}'. Use add_layer first.")
        if bool(target.Freeze):
            raise AcadError(f"Layer '{layer}' is frozen and cannot be made current.")
        previous = doc.ActiveLayer
        change.on_rollback(lambda: setattr(doc, "ActiveLayer", previous))
        doc.ActiveLayer = target
    return f"Current layer is now '{target.Name}'."
