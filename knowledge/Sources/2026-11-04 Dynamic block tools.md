# 2026-11-04 Dynamic block tools

Report-ID: AMCP-LIVE-20261104-06
Writer: Claude Code. The batch was described first and run after Alex's go ("Saved, go"); no user action was needed.
Question: do `insert_block(dynamic_properties=…)`, `get_block_properties`, `set_block_properties` and `measure_block` work on a real dynamic block in AutoCAD 2026?

## Setup
- The user's dynamic screw block from [[Sources/2026-11-04 Dynamic block shared array]]: a size lookup with 7 rows, a Length with stock values, invisible CALLOUT and SPEC attributes, and hidden helper parameters. It was inserted from its library file into a new scratch drawing, which was closed without saving. The library file was only read.
- Script `tests/live/dynamic_block_check.py`, with the block file and values on the command line: Size `#8-18` → `1/4-14`, Length `1` → `2`.

## Results
- **Insert:** placed with Size `#8-18` and Length 1 in one call. `get_block_properties` listed only Size and Length, with their allowed values. The helpers stayed hidden, and the values read back as set.
- **measure_block at #8-18 × 1":**
  - extents width 0.348 (the washer) and tip at −1.0 from the insertion point;
  - 16 lines, 31 polylines and 2 attribute definitions visible;
  - nothing left behind (model space count unchanged).
- **set_block_properties** to `1/4-14` and 2 in one call. Then:
  - width 0.52, tip at −2.0;
  - 30 lines and 59 polylines: the thread array refilled;
  - CALLOUT changed from `#8-18 x 1" HWH TEK` to `1/4-14 x 2" HWH TEK` after the tool's regen.
- **A refused value** (`no such value`) was reported with the 7 allowed sizes.
- **Result: 13/13.** The first run was 12/13 because of a flaw in the script's own check. It compared overall heights, but the head also grows with the size (0.11 → 0.19). The check now compares the tip's position from the insertion point, which moved by exactly the length change.

## Not covered
- Rotated or scaled inserts (`extents_from_insertion_point` is plain subtraction, meaningful at rotation 0).
- Blocks without a lookup, or with XY, polar or flip parameters.
