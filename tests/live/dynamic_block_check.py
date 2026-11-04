"""Live check of get_block_properties, set_block_properties, insert_block(dynamic_properties)
and measure_block on a real dynamic block. Run ONLY after the user has saved open work and said go:

    .venv\\Scripts\\python.exe tests\\live\\dynamic_block_check.py <block.dwg> <list property> <value A> <value B>
                                                                  <distance property> <distance 1> <distance 2>

e.g. ... screw.dwg Size "#8-18" "1/4-14" Length 1 2

Everything happens in a new scratch drawing, which is closed without saving at the end. The block
file is only inserted, never changed. Nothing about the block is hard-coded here: the checks are
that values read back as set, the width changes with the list value, the block grows by exactly the
distance change at its far end, measuring leaves nothing behind, and the attributes follow the change.
"""

from __future__ import annotations

import os
import sys

import harness
import pythoncom
from harness import check, step

from autocad_mcp.com import MessageFilter, retry_seconds
from autocad_mcp.session import session
from autocad_mcp.tools import blocks, documents

REPORT = os.environ.get("AMCP_REPORT", "AMCP-LIVE-DYNBLOCK")


def main(path: str, list_prop: str, a: str, b: str, dist_prop: str, d1: str, d2: str) -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    MessageFilter(retry_seconds()).register()
    session.connect()
    info = step("new scratch drawing", documents.new_drawing)
    if not info:
        return
    scratch = info["name"]
    try:
        placed = step("insert with dynamic properties", blocks.insert_block, path, [0, 0],
                      dynamic_properties={list_prop: a, dist_prop: d1}, name=scratch)
        if not placed:
            return
        handle = placed["handle"]
        read = step("get_block_properties", blocks.get_block_properties, handle, name=scratch)
        values = {p["name"].lower(): p["value"] for p in (read or {}).get("properties", [])}
        check("values read back as set", str(values.get(list_prop.lower())) == a
              and abs(float(values.get(dist_prop.lower(), -1)) - blocks.number(d1)) < 1e-6, str(values))
        doc = session.find_document(scratch)
        count = doc.ModelSpace.Count
        m1 = step(f"measure at {a}, {d1}", blocks.measure_block, handle, name=scratch)
        check("measuring left nothing behind", doc.ModelSpace.Count == count, f"{doc.ModelSpace.Count} vs {count}")
        labels_1 = (read or {}).get("attributes", {})
        step(f"set {list_prop}={b}, {dist_prop}={d2}", blocks.set_block_properties, handle,
             {list_prop: b, dist_prop: d2}, name=scratch)
        m2 = step(f"measure at {b}, {d2}", blocks.measure_block, handle, name=scratch)
        if m1 and m2:
            e1, e2 = m1["extents"], m2["extents"]
            print("extents:", e1, "->", e2)
            check("width changes with the list value", abs(e1["width"] - e2["width"]) > 1e-6,
                  f"{e1['width']} -> {e2['width']}")
            # The far end (lowest point from the insertion point) moves by the distance change; the overall
            # height also changes with the list value (a bigger head), so it is not the measure here.
            low1 = m1["extents_from_insertion_point"]["min"][1]
            low2 = m2["extents_from_insertion_point"]["min"][1]
            moved = round(low1 - low2, 6)
            check("far end moves by the distance change", abs(moved - (blocks.number(d2) - blocks.number(d1))) < 1e-4,
                  f"{low1} -> {low2}")
        labels_2 = blocks.get_block_properties(handle, name=scratch)["attributes"]
        print("attributes:", labels_1, "->", labels_2)
        check("attributes follow the change", labels_1 != labels_2 or not labels_1, "")
        step("a refused value is reported", blocks.set_block_properties, handle, {list_prop: "no such value"},
             name=scratch, expect_error="not an allowed")
    finally:
        step("close the scratch drawing", documents.close_document, scratch, discard_changes=True)


if __name__ == "__main__":
    if len(sys.argv) != 8:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
    sys.exit(harness.finish(REPORT))
