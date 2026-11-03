"""AMCP-LIVE-20261029-02: an L-shaped kitchen with an island, in plan. Run ONLY after the user said go.

    .venv\\Scripts\\python.exe tests\\live\\kitchen_plan.py

Room 14'-0" x 15'-0" inside (168" x 180"), 4 1/2" walls, inches drawing at 1/2"=1'-0".
Origin at the inside south-west corner. Works in one new scratch drawing and leaves it open.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import SCRATCH, check, finish, step  # noqa: E402

from autocad_mcp.tools import annotate, documents, draw, layers, plot, query, settings  # noqa: E402

REPORT = "AMCP-LIVE-20261029-02"
W, D, T = 168.0, 180.0, 4.5  # inside width, inside depth, wall thickness
DOOR = (20.0, 52.0)  # 2'-8" door in the south wall
WINDOW = (42.0, 78.0)  # 3'-0" window in the north wall, centred on the sink


def main() -> int:
    os.makedirs(SCRATCH, exist_ok=True)
    status = step("acad_status (read-only)", documents.acad_status)
    if status is None:
        return 1
    theirs = {d["name"]: d["unsaved_changes"] for d in status["open_drawings"]}
    check("open drawings locked", not any(d["editable"] for d in status["open_drawings"]), str(list(theirs)))

    new = step("new_drawing", documents.new_drawing)
    if new is None:
        return 1
    name = new["name"]
    if new["units"] != "inches":
        print("STOPPED: the default template is not inches; this plan is drawn in inches.")
        return 1

    step("architectural units, 1/2\"=1'-0\"", settings.set_drawing_variables,
         {"LUNITS": 4, "LUPREC": 4, "DIMLUNIT": 4, "DIMSCALE": 24, "LTSCALE": 12}, name=name)

    for layer, color, linetype, weight in [
        ("A-WALL", 7, "Continuous", 50), ("A-DOOR", 4, "Continuous", 25), ("A-GLAZ", 5, "Continuous", 18),
        ("A-CASE", 3, "Continuous", 25), ("A-CASE-UPPR", 8, "HIDDEN", 18), ("A-FLOR-APPL", 6, "Continuous", 25),
        ("A-ANNO-TEXT", 2, "Continuous", -3), ("A-ANNO-DIMS", 1, "Continuous", -3)]:
        step(f"add_layer {layer}", layers.add_layer, layer, color=color, linetype=linetype, lineweight=weight,
             name=name)

    def line(a, b, layer, label):
        return step(label, draw.draw_line, list(a), list(b), layer=layer, name=name)

    def pline(points, layer, label, closed=False):
        return step(label, draw.draw_polyline, [list(p) for p in points], closed=closed, layer=layer, name=name)

    def rect(a, b, layer, label):
        return step(label, draw.draw_rectangle, list(a), list(b), layer=layer, name=name)

    # Walls: two continuous runs each side of the door and window openings, plus jambs.
    d0, d1 = DOOR
    w0, w1 = WINDOW
    pline([(d1, 0), (W, 0), (W, D), (w1, D)], "A-WALL", "wall inside, east run")
    pline([(d1, -T), (W + T, -T), (W + T, D + T), (w1, D + T)], "A-WALL", "wall outside, east run")
    pline([(w0, D), (0, D), (0, 0), (d0, 0)], "A-WALL", "wall inside, west run")
    pline([(w0, D + T), (-T, D + T), (-T, -T), (d0, -T)], "A-WALL", "wall outside, west run")
    for x in (d0, d1):
        line((x, 0), (x, -T), "A-WALL", f"door jamb x={x}")
    for x in (w0, w1):
        line((x, D), (x, D + T), "A-WALL", f"window jamb x={x}")
    for y in (D + T / 3, D + 2 * T / 3):
        line((w0, y), (w1, y), "A-GLAZ", f"window glass y={y}")

    # Door: leaf open 90 degrees into the room, hinge at the west jamb, and its swing.
    line((d0, 0), (d0, d1 - d0), "A-DOOR", "door leaf")
    step("door swing (arc)", draw.draw_arc, [d0, 0], d1 - d0, 0, 90, layer="A-DOOR", name=name)

    # Base cabinets, 24" deep: the north run full width, the east run from the fridge to it.
    rect((0, D - 24), (W, D), "A-CASE", "base cabinets, north run")
    rect((W - 24, 36), (W, D - 24), "A-CASE", "base cabinets, east run")
    # Upper cabinets, 12" deep, dashed; none over the window.
    rect((0, D - 12), (w0, D), "A-CASE-UPPR", "uppers, north-west")
    rect((w1, D - 12), (W, D), "A-CASE-UPPR", "uppers, north-east")
    rect((W - 12, 36), (W, D - 24), "A-CASE-UPPR", "uppers, east")

    # Sink under the window, dishwasher beside it, range on the east run, fridge in the corner.
    sx = (w0 + w1) / 2
    rect((sx - 16.5, D - 22), (sx + 16.5, D - 2), "A-FLOR-APPL", "sink, outline")
    rect((sx - 14.5, D - 20), (sx - 1, D - 4), "A-FLOR-APPL", "sink, left bowl")
    rect((sx + 1, D - 20), (sx + 14.5, D - 4), "A-FLOR-APPL", "sink, right bowl")
    step("DW label", draw.add_text, "DW", [w1 + 8, D - 15], 4, layer="A-ANNO-TEXT", name=name)
    rect((W - 24, 84), (W, 114), "A-FLOR-APPL", "range")
    for x in (W - 18, W - 6):
        for y in (91, 107):
            step(f"burner {x},{y}", draw.draw_circle, [x, y], 3.5, layer="A-FLOR-APPL", name=name)
    rect((W - 30, 0), (W, 36), "A-FLOR-APPL", "refrigerator")
    step("REF label", draw.add_text, "REF", [W - 22, 15], 4, layer="A-ANNO-TEXT", name=name)

    # Island 60" x 36", 42" clear of the north and east counters.
    ix1, iy1 = W - 24 - 42, D - 24 - 42
    ix0, iy0 = ix1 - 60, iy1 - 36
    rect((ix0, iy0), (ix1, iy1), "A-CASE", "island")

    # Labels and dimensions.
    step("room name", draw.add_text, "KITCHEN", [30, 40], 6, layer="A-ANNO-TEXT", name=name)
    step("title", draw.add_mtext, "KITCHEN PLAN\\PSCALE: 1/2\" = 1'-0\"", [0, -30], 120, height=5,
         layer="A-ANNO-TEXT", name=name)
    dims = [
        ("room width", (0, D + T), (W, D + T), (W / 2, D + 30), "horizontal"),
        ("room depth", (W + T, 0), (W + T, D), (W + 30, D / 2), "vertical"),
        ("island width", (ix0, iy0), (ix1, iy0), ((ix0 + ix1) / 2, iy0 - 14), "horizontal"),
        ("island depth", (ix0, iy0), (ix0, iy1), (ix0 - 14, (iy0 + iy1) / 2), "vertical"),
        ("aisle to north counter", (ix0 + 20, iy1), (ix0 + 20, D - 24), (ix0 + 20, (iy1 + D - 24) / 2), "vertical"),
        ("aisle to east counter", (ix1, iy0 + 18), (W - 24, iy0 + 18), ((ix1 + W - 24) / 2, iy0 + 18), "horizontal"),
    ]
    for label, a, b, at, kind in dims:
        step(f"dimension: {label}", annotate.add_dimension, list(a), list(b), list(at), kind=kind,
             layer="A-ANNO-DIMS", name=name)

    step("zoom_extents", query.zoom_extents, name=name)
    image = step("capture_view", query.capture_view)
    if image is not None:
        with open(os.path.join(SCRATCH, f"{REPORT}.png"), "wb") as fh:
            fh.write(image.data)
    info = step("drawing_info", query.drawing_info, name=name)
    if info:
        print("by layer:", info["by_layer"])
    saved = step("save_document", documents.save_document, os.path.join(SCRATCH, f"{REPORT}.dwg"),
                 overwrite=True, name=name)
    name = saved["name"] if saved else name
    step("plot_pdf (Model)", plot.plot_pdf, os.path.join(SCRATCH, f"{REPORT}.pdf"), overwrite=True, name=name)

    after = {d["name"]: d["unsaved_changes"] for d in documents.acad_status()["open_drawings"] if d["name"] in theirs}
    check("other open drawings untouched", after == theirs, str(after))
    return finish(REPORT)


if __name__ == "__main__":
    sys.exit(main())
