# Sources

Dated reports of AutoCAD-MCP's own live tests, plus the external references. Report-IDs are stable (`AMCP-LIVE-YYYYMMDD-NN`).

- [[Sources/External references]]: the projects and documents this one draws on.
- [[Sources/2026-10-29 First drawing]]: AMCP-LIVE-20261029-01, the first live run: a window elevation in a scratch drawing; 32/33 steps after one fix, the miss being a script bug.
- [[Sources/2026-10-29 Kitchen plan]]: AMCP-LIVE-20261029-02 and -03, an L-shaped kitchen with an island at 1/2"=1'-0" (55/55), then the fixes for unreadable dimensions and a blank screenshot (5/5).
- [[Sources/2026-10-29 Kitchen elevations]]: AMCP-LIVE-20261029-04, north and east cabinet elevations beside the plan, and the plan's uppers fixed by handle (87/87).
- [[Sources/2026-11-03 AutoCAD 2026 connection]]: AMCP-LIVE-20261103-01, read-only connection check on the work PC: attached to AutoCAD 2026 (not DWG TrueView 2027) and kept Alex's open drawing locked (4/4).
- [[Sources/2026-11-03 AutoCAD 2026 drawing]]: AMCP-LIVE-20261103-02, the window elevation rerun on AutoCAD 2026 on the work PC: 33/33, same results as on 2027, Alex's drawings left locked and unchanged.
- [[Sources/2026-11-03 Safety check]]: AMCP-LIVE-20261103-03, the safety promises on AutoCAD 2026: edit guard, one Ctrl+Z per tool, nothing drawn inside LINE or with a dialog open; blocks, edits by handle and open/close (41 of 44 steps; the 3 misses were the busy message's wording, fixed in the same change).
- [[Sources/2026-11-03 Sheet tools]]: AMCP-LIVE-20261103-04, the new sheet tools on a real title-block sheet: a small bent part in three views with centre marks, hidden edges, decimal dimensions, a callout, a 1:1 viewport and a filled title block, saved and plotted (39/39).
- [[Sources/2026-11-03 Plot style re-plot]]: AMCP-LIVE-20261103-05, the part sketch plotted again after the sheet's plot style table was installed: no plot-style warning, black PDF with lineweights (8/8); found the decimal-comma dimension text and short hidden lines plotting solid.
- [[Sources/2026-11-03 Dynamic block authoring]]: AMCP-LIVE-20261103-06 to -13, a 7-size dynamic screw block (visibility states, length grip, arrayed threads, callout fields) built partly by script and finished with desktop control; what can and cannot be scripted (98/98, 31/31, 16/16, 73/73, 16/16).
- [[Sources/2026-11-04 Dynamic block shared array]]: AMCP-LIVE-20261104-01 to -03. The screw block rebuilt around one shared thread array and a size lookup, after the user found stale threads on size change. Build faults found offline, then fixed; 169/169 from the released file.
- [[Sources/2026-11-04 Busy handling]]: AMCP-LIVE-20261104-04, retried calls, the settle wait in `new_drawing`, and `cancel_command` on AutoCAD 2026. Esc window messages did not cancel a prompt; `^C^C` via WM_COPYDATA did, and the tool now uses it.
- [[Sources/2026-11-04 Ownership across restarts]]: AMCP-LIVE-20261104-05. A restarted server took back its open scratch drawing; the user's drawing and a reopened file stayed locked. It also found and fixed `open_drawing` returning before the file finished opening.
- [[Sources/2026-11-04 Dynamic block tools]]: AMCP-LIVE-20261104-06, the new dynamic block tools on the user's screw block. Insert with properties, read, set (with refusal), and measure the visible geometry: 13/13 after fixing a check in the script.
- [[Sources/2026-11-04 Block tools through the server]]: AMCP-LIVE-20261104-07, the block tools after merge, called through Claude's own MCP connection on the released screw block: insert with properties, read, set, measure and refusal (8/8). Found that the reported bounding box of a dynamic block includes hidden sizes.
