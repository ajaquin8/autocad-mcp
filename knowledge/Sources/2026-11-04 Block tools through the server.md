# 2026-11-04 Block tools through the server

Report-ID: AMCP-LIVE-20261104-07
Writer: Claude Code. The batch was described first and run after Alex's go ("Saved, go"); no user action was needed. Alex then asked to close the scratch drawing and record the run ("Yes, close and record").
Question: after the merge of the dynamic block tools and a restart of Claude, do they work through Claude's own MCP connection (not a test script), on the released screw block?

## Setup
- AutoCAD 2026 on the work PC. One user drawing was open, saved and locked (`editable: false`); it was only listed.
- The server process started after the merge (checked from its start time). An earlier "restart" had only closed the Claude window, which keeps the app and its MCP servers running in the system tray; quitting from the tray icon restarted them.
- The released screw block from [[Sources/2026-11-04 Dynamic block shared array]], inserted from its library file into a new scratch drawing. The library file was only read. The scratch drawing was closed without saving.
- Every step was a single MCP tool call from Claude Code.

## Results
1. **`insert_block` with `dynamic_properties`** `{Size: "#10-16", Length: 1}`: placed in one call; the result reported the values and CALLOUT `#10-16 x 1" HWH TEK`. Claude's cached copy of the tool's schema still lacked the new parameter, but the call went through.
2. **`get_block_properties`:** only Size and Length shown, with the 7 sizes and 14 stock lengths; CALLOUT and SPEC listed as invisible.
3. **`measure_block` at #10-16 × 1":** width 0.414, tip at −1.000 from the insertion point, 15 lines, 29 polylines, 2 attribute definitions.
4. **`set_block_properties`** `{Size: "1/4-14", Length: "1 1/2"}` (a fraction string): read back as 1/4-14 and 1.5, CALLOUT `1/4-14 x 1 1/2" HWH TEK`.
5. **`measure_block` at 1/4-14 × 1-1/2":** width 0.520, tip at −1.500 (moved exactly 0.500), 22 lines and 43 polylines (the thread array refilled).
6. **Hidden helpers** (`include_hidden`): Pilot 0.21, Major 0.246, Minor 0.192, Thread 1.29 (= 1.5 − 0.21), Visibility1 `1/4-14`: all match the lookup row.
7. **Refused value** `5/16-12`: an error listing the 7 allowed sizes; a read-back showed the block unchanged.
8. **Picture** (`capture_view`, not kept: it shows the user's drawing tab): a 1/4-14 screw with the thread at full width down to the drill point.
- **Result: 8/8 steps as expected.**

## Finding
- **verified (this run):** the bounding box `insert_block` reports for a dynamic block is not what is shown. At #10-16 it reported x ±0.26 and top 0.19, which are the 1/4-14 numbers; `measure_block` gave ±0.207 and 0.12. The bottom (−1.0) did follow the length. **inferred:** AutoCAD's `GetBoundingBox` on a block reference includes objects hidden by the visibility state. Use `measure_block` when the shown size matters. Recorded in [[Research/AutoCAD API gotchas]].

## Not covered
- Rotated or scaled inserts, and blocks other than this one (as in [[Sources/2026-11-04 Dynamic block tools]]).
