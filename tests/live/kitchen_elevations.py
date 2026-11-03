"""AMCP-LIVE-20261029-04: north and east elevations beside the kitchen plan. Run ONLY after the user said go.

    .venv\\Scripts\\python.exe tests\\live\\kitchen_elevations.py

Works in the kitchen scratch drawing (AMCP-LIVE-20261029-02.dwg). Heights: floor 0, toe kick 4",
counter 34 1/2" + 1 1/2" top = 36", uppers 54" to 96", ceiling 8'-0". Elevation x runs left to
right as the viewer sees the wall.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import SCRATCH, check, finish, step  # noqa: E402

from autocad_mcp.tools import annotate, documents, draw, edit, layers, plot, query, settings  # noqa: E402

REPORT = "AMCP-LIVE-20261029-04"
KITCHEN = "AMCP-LIVE-20261029-02.dwg"
CEILING, TOE, BOX, TOP, UPPER = 96.0, 4.0, 34.5, 36.0, 54.0
NORTH_X, EAST_X = 260.0, 540.0  # where each elevation starts, right of the plan


class Elevation:
    """Draws one elevation from its own left floor corner at (x0, 0)."""

    def __init__(self, title: str, x0: float, width: float) -> None:
        self.title, self.x0, self.width = title, x0, width

    def p(self, x: float, y: float) -> list[float]:
        return [self.x0 + x, y]

    def rect(self, x0, y0, x1, y1, layer, label):
        step(f"{self.title}: {label}", draw.draw_rectangle, self.p(x0, y0), self.p(x1, y1), layer=layer,
             name=KITCHEN)

    def line(self, x0, y0, x1, y1, layer, label):
        step(f"{self.title}: {label}", draw.draw_line, self.p(x0, y0), self.p(x1, y1), layer=layer, name=KITCHEN)

    def text(self, value, x, y, height, label):
        step(f"{self.title}: {label}", draw.add_text, value, self.p(x, y), height, layer="A-ANNO-TEXT",
             name=KITCHEN)

    def dim(self, a, b, at, kind, label):
        step(f"{self.title}: dimension {label}", annotate.add_dimension, self.p(*a), self.p(*b), self.p(*at),
             kind=kind, layer="A-ANNO-DIMS", name=KITCHEN)

    def base(self, x0, x1, kind, label):
        """A base cabinet box on the toe kick: doors, a drawer stack or a plain panel."""
        self.rect(x0, TOE, x1, BOX, "A-ELEV-CASE", f"base {label}")
        if kind in ("doors", "door"):
            self.line(x0, BOX - 6, x1, BOX - 6, "A-ELEV-CASE", f"base {label} top drawer")
        if kind == "doors":
            self.line((x0 + x1) / 2, TOE, (x0 + x1) / 2, BOX - 6, "A-ELEV-CASE", f"base {label} door split")
        if kind == "drawers":
            for y in (BOX - 6, BOX - 16):
                self.line(x0, y, x1, y, "A-ELEV-CASE", f"base {label} drawer y={y}")

    def upper(self, x0, x1, y0, label, doors=1):
        self.rect(x0, y0, x1, CEILING, "A-ELEV-CASE", f"upper {label}")
        if doors == 2:
            self.line((x0 + x1) / 2, y0, (x0 + x1) / 2, CEILING, "A-ELEV-CASE", f"upper {label} door split")

    def frame(self) -> None:
        self.rect(0, 0, self.width, CEILING, "A-ELEV-OTLN", "wall outline (floor to ceiling)")

    def heights(self, x) -> None:
        for y0, y1 in ((0, TOP), (TOP, UPPER), (UPPER, CEILING)):
            self.dim((x, y0), (x, y1), (x + (18 if x > 0 else -18), (y0 + y1) / 2), "vertical", f"{y0}-{y1}")


def north() -> None:
    """The sink wall, seen from the room: west on the left, plan x = elevation x."""
    e = Elevation("north", NORTH_X, 168)
    e.frame()
    e.line(0, TOE, 168, TOE, "A-ELEV-CASE", "toe kick line")
    e.base(0, 42, "doors", "0-42")
    e.base(42, 78, "doors", "sink 42-78")
    e.rect(78, TOE, 102, BOX, "A-ELEV-APPL", "dishwasher")
    e.text("DW", 86, 18, 4, "DW label")
    e.base(102, 144, "drawers", "102-144")
    e.base(144, 168, "door", "corner 144-168")
    e.rect(0, BOX, 168, TOP, "A-ELEV-CASE", "countertop")
    e.rect(42, 42, 78, 80, "A-ELEV-GLAZ", "window frame")
    e.rect(44, 44, 76, 78, "A-ELEV-GLAZ", "window glass")
    e.upper(0, 42, UPPER, "0-42", doors=2)
    e.upper(78, 102, UPPER, "78-102")
    e.upper(102, 144, UPPER, "102-144", doors=2)
    e.upper(144, 168, UPPER, "144-168")
    e.dim((0, 0), (168, 0), (84, -14), "horizontal", "width")
    e.heights(168)
    e.text("NORTH ELEVATION - SINK WALL", 0, -34, 5, "title")


def east() -> None:
    """The range wall, seen from the room: north on the left, elevation x = 180 - plan y."""
    e = Elevation("east", EAST_X, 180)
    e.frame()
    e.line(0, TOE, 66, TOE, "A-ELEV-CASE", "toe kick line, left")
    e.line(96, TOE, 144, TOE, "A-ELEV-CASE", "toe kick line, right")
    e.base(0, 24, "door", "corner 0-24")
    e.base(24, 66, "drawers", "24-66")
    e.rect(66, 0, 96, TOP, "A-ELEV-APPL", "range")
    e.rect(68, 6, 94, 28, "A-ELEV-APPL", "range oven door")
    e.line(66, 31, 96, 31, "A-ELEV-APPL", "range control panel")
    e.base(96, 120, "door", "96-120")
    e.base(120, 144, "door", "120-144")
    e.rect(0, BOX, 66, TOP, "A-ELEV-CASE", "countertop, left")
    e.rect(96, BOX, 144, TOP, "A-ELEV-CASE", "countertop, right")
    e.rect(144, 0, 180, 70, "A-ELEV-APPL", "refrigerator")
    e.line(162, 36, 162, 70, "A-ELEV-APPL", "refrigerator doors")
    e.line(144, 36, 180, 36, "A-ELEV-APPL", "refrigerator freezer drawer")
    e.text("REF", 155, 50, 4, "REF label")
    e.rect(66, 66, 96, 78, "A-ELEV-APPL", "hood")
    e.rect(75, 78, 87, CEILING, "A-ELEV-APPL", "hood chimney")
    e.upper(0, 24, UPPER, "corner 0-24")
    e.upper(24, 66, UPPER, "24-66", doors=2)
    e.upper(96, 120, UPPER, "96-120")
    e.upper(120, 144, UPPER, "120-144")
    e.upper(144, 180, 72, "over refrigerator", doors=2)
    for label, a, b in (("corner+drawers", 0, 66), ("range", 66, 96), ("bases", 96, 144), ("ref", 144, 180)):
        e.dim((a, 0), (b, 0), ((a + b) / 2, -14), "horizontal", label)
    e.dim((0, 0), (180, 0), (90, -30), "horizontal", "width")
    e.heights(0)
    e.text("EAST ELEVATION - RANGE WALL", 0, -50, 5, "title")


def fix_plan_uppers() -> None:
    """The plan drew the east uppers over the range; split them round it and add one over the fridge."""
    found = step("find plan uppers", query.query_entities, layer="A-CASE-UPPR", name=KITCHEN)
    east_run = [e for e in (found or {}).get("entities", []) if e["bbox"][0][0] >= 155 and e["bbox"][1][1] > 150]
    check("one east upper run found", len(east_run) == 1, str(east_run))
    if len(east_run) != 1:
        return
    step("delete the east upper run", edit.delete_entities, [east_run[0]["handle"]], name=KITCHEN)
    for label, a, b in (("north of range", (156, 114), (168, 156)), ("south of range", (156, 36), (168, 84)),
                        ("over refrigerator", (138, 0), (168, 36))):
        step(f"plan upper {label}", draw.draw_rectangle, list(a), list(b), layer="A-CASE-UPPR", name=KITCHEN)
    step("plan hood outline", draw.draw_rectangle, [146, 84], [168, 114], layer="A-CASE-UPPR", name=KITCHEN)


def main() -> int:
    os.makedirs(SCRATCH, exist_ok=True)
    status = step("acad_status (read-only)", documents.acad_status)
    if status is None:
        return 1
    theirs = {d["name"]: d["unsaved_changes"] for d in status["open_drawings"] if d["name"] != KITCHEN}
    if step("unlock the kitchen scratch drawing", documents.allow_edit_document, KITCHEN) is None:
        return 1
    step("show 14'-0\" in dimensions", settings.set_drawing_variables, {"DIMZIN": 0}, name=KITCHEN)
    for layer, color, weight in (("A-ELEV-OTLN", 7, 50), ("A-ELEV-CASE", 3, 25), ("A-ELEV-APPL", 6, 25),
                                 ("A-ELEV-GLAZ", 5, 18)):
        step(f"add_layer {layer}", layers.add_layer, layer, color=color, lineweight=weight, name=KITCHEN)
    fix_plan_uppers()
    north()
    east()
    step("zoom_extents", query.zoom_extents, name=KITCHEN)
    image = step("capture_view right after the zoom", query.capture_view)
    if image is not None:
        with open(os.path.join(SCRATCH, f"{REPORT}.png"), "wb") as fh:
            fh.write(image.data)
    step("save_document", documents.save_document, name=KITCHEN)
    step("plot_pdf (Model)", plot.plot_pdf, os.path.join(SCRATCH, f"{REPORT}.pdf"), overwrite=True, name=KITCHEN)
    after = {d["name"]: d["unsaved_changes"] for d in documents.acad_status()["open_drawings"] if d["name"] in theirs}
    check("other open drawings untouched", after == theirs, str(after))
    return finish(REPORT)


if __name__ == "__main__":
    sys.exit(main())
