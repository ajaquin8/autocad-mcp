"""AMCP-LIVE-20261029-01: the first drawing. Run ONLY after the user has saved open work and said go.

    .venv\\Scripts\\python.exe tests\\live\\first_drawing.py

Calls the tool functions directly (no MCP client). Works in one new scratch drawing,
leaves it open for the user to look at, and writes output under scratch/.
Set AMCP_REPORT to rerun it under a new Report-ID (the output files are named after it).
"""

from __future__ import annotations

import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from autocad_mcp.com import AcadError  # noqa: E402
from autocad_mcp.session import session  # noqa: E402
from autocad_mcp.tools import annotate, documents, draw, layers, plot, query  # noqa: E402

SCRATCH = os.path.join(ROOT, "scratch")
REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-20261029-01")
results: list[dict] = []


def step(label: str, fn, *args, expect_error: str = "", **kwargs):
    try:
        value = fn(*args, **kwargs)
    except Exception as err:  # noqa: BLE001 - every outcome is recorded
        ok = bool(expect_error) and expect_error in str(err)
        results.append({"step": label, "ok": ok, "error": f"{type(err).__name__}: {err}"})
        print(("PASS" if ok else "FAIL"), label, "->", err)
        if not ok:
            traceback.print_exc()
        return None
    ok = not expect_error
    results.append({"step": label, "ok": ok})
    print(("PASS" if ok else "FAIL"), label, "->", _short(value))
    return value


def _short(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:300]


def main() -> int:
    os.makedirs(SCRATCH, exist_ok=True)
    status = step("acad_status (read-only)", documents.acad_status)
    if status is None:
        return 1
    theirs = {d["name"]: d["unsaved_changes"] for d in status["open_drawings"]}
    print("User's drawings (must all be locked):", [(d["name"], d["editable"]) for d in status["open_drawings"]])
    results.append({"step": "user drawings locked", "ok": not any(d["editable"] for d in status["open_drawings"])})

    new = step("new_drawing", documents.new_drawing)
    if new is None:
        return 1
    name = new["name"]
    s = 25.4 if new["units"] == "millimeters" else 1.0  # sizes below are inches
    print("units:", new["units"], "scale:", s)

    def p(x, y):
        return [x * s, y * s]

    for layer, color, linetype, weight in [("A-FRAME", 7, "Continuous", 50), ("A-GLASS", 4, "Continuous", 18),
                                           ("A-MUNTIN", 3, "Continuous", 25), ("A-SWING", 6, "HIDDEN", 18),
                                           ("A-TEXT", 2, "Continuous", -3), ("A-DIMS", 1, "Continuous", -3)]:
        step(f"add_layer {layer}", layers.add_layer, layer, color=color, linetype=linetype, lineweight=weight,
             name=name)

    step("frame outer", draw.draw_rectangle, p(0, 0), p(36, 48), layer="A-FRAME", name=name)
    step("frame inner", draw.draw_rectangle, p(2.5, 2.5), p(33.5, 45.5), layer="A-FRAME", name=name)
    step("glass", draw.draw_rectangle, p(4, 4), p(32, 44), layer="A-GLASS", name=name)
    step("muntin vertical", draw.draw_line, p(18, 4), p(18, 44), layer="A-MUNTIN", name=name)
    for y in (17.333, 30.667):
        step(f"muntin horizontal y={y}", draw.draw_line, p(4, y), p(32, y), layer="A-MUNTIN", name=name)
    step("arched head trim (arc)", draw.draw_arc, p(18, 48), 18 * s, 0, 180, layer="A-FRAME", name=name)
    step("sill with rounded nose (polyline + bulge)", draw.draw_polyline,
         [p(-1, 0), p(37, 0), p(37, -1.5), p(-1, -1.5)], closed=True, bulges=[0, 0, 0, -1],
         layer="A-FRAME", name=name)
    step("swing line 1", draw.draw_line, p(2.5, 2.5), p(33.5, 24), layer="A-SWING", name=name)
    step("swing line 2", draw.draw_line, p(2.5, 45.5), p(33.5, 24), layer="A-SWING", name=name)
    step("handle (circle)", draw.draw_circle, p(34.25, 24), 0.5 * s, layer="A-FRAME", name=name)
    step("mark (text)", draw.add_text, "W101", p(15, -6), 1.5 * s, layer="A-TEXT", name=name)
    step("note (mtext)", draw.add_mtext, "CASEMENT WINDOW\\P36 x 48\\PSDL 2W x 3H", p(44, 48), 20 * s,
         height=1 * s, layer="A-TEXT", name=name)
    step("width dimension (horizontal)", annotate.add_dimension, p(0, 0), p(36, 0), p(18, -10),
         kind="horizontal", layer="A-DIMS", name=name)
    step("height dimension (vertical)", annotate.add_dimension, p(36, 0), p(36, 48), p(42, 24),
         kind="vertical", layer="A-DIMS", name=name)

    before = query.drawing_info(name=name)["model_space_entities"]
    step("rollback: line on a missing layer is refused", draw.draw_line, p(0, 0), p(1, 1), layer="NOPE",
         name=name, expect_error="No layer named")
    after = query.drawing_info(name=name)["model_space_entities"]
    results.append({"step": "rollback left nothing behind", "ok": before == after,
                    "detail": f"{before} -> {after}"})
    print("rollback entity count:", before, "->", after)

    step("zoom_extents", query.zoom_extents, name=name)
    image = step("capture_view", query.capture_view)
    if image is not None:
        with open(os.path.join(SCRATCH, f"{REPORT}.png"), "wb") as fh:
            fh.write(image.data)
    step("drawing_info", query.drawing_info, name=name)
    step("query_entities A-MUNTIN", query.query_entities, layer="A-MUNTIN", name=name)
    saved = step("save_document", documents.save_document, os.path.join(SCRATCH, f"{REPORT}.dwg"),
                 overwrite=True, name=name)
    name = saved["name"] if saved else name  # Save As renames the drawing
    step("plot_pdf (Model)", plot.plot_pdf, os.path.join(SCRATCH, f"{REPORT}.pdf"), overwrite=True, name=name)

    after_status = documents.acad_status()
    untouched = {d["name"]: d["unsaved_changes"] for d in after_status["open_drawings"] if d["name"] in theirs}
    results.append({"step": "user drawings untouched", "ok": untouched == theirs, "detail": str(untouched)})

    with open(os.path.join(SCRATCH, f"{REPORT}.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed. Drawing left open: {session.document().Name}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AcadError as err:
        print("STOPPED:", err)
        sys.exit(1)
