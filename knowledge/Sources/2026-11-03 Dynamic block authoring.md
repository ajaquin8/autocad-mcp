# 2026-11-03 Dynamic block authoring

Report-IDs: AMCP-LIVE-20261103-06 to AMCP-LIVE-20261103-13 (one series)
Writer: Claude Code. Each batch was described first and run after Alex's go ("Saved, go"); Alex was at the machine for every Block Editor step.
Question: can a dynamic block (visibility states, parameters, actions, attributes with fields) be authored from outside AutoCAD, and which steps still need a person or the desktop?

## Setup
- AutoCAD 2026 ("25.1s"). Python scripts calling the server's tool functions directly, plus `Document.SendCommand` with `(command ...)` expressions for Block Editor commands (the same mechanism as the opt-in `send_command` tool). Steps that only exist in dialogs were done with Claude's desktop control (computer use) in Alex's AutoCAD.
- The subject: a self-drilling screw in side view, 7 sizes, drawn from published standard head and thread tables and a manufacturer's drilling-capacity data, with simplified threads. All work in new drawings the server created, or in the user's own library drawing at the user's request. Output files live outside this repository.

## Results
- **06 probe (placeholder geometry):** **verified** scripted: `BEDIT` by name, a visibility parameter, named states with `-BVSTATE` (New/Set/Delete), `BVSHOW` per state, a linear parameter with a label and a value list. **Failed:** `BACTION` given `(entlast)` as the parameter stalled at "Select parameter:", and AutoCAD then refused every automation call until a person pressed Esc.
- **07 geometry, 7 sizes:** 98/98. Each size drawn from the table at the default length and read back: width = washer diameter, top = head height, tip at −L.
- **08 thread styles:** 31/31. Plain schematic lines, zigzag edges, and zigzag plus slanted crest lines, each checked for extents; the user chose zigzag plus crests (18–26 objects per size, against 1,700–4,700 in the hand-drawn blocks it replaces).
- **09 one-size threaded prototype by script:** parameters (Length with a value list; a hidden "Thread" length parameter with chain actions) **verified**; the actions failed. First attempt: control characters appended to `SendCommand` text made AutoCAD reject every command ("Invalid input"). Second attempt: the action keyword `S` created a **Scale** action, not a stretch.
- **10 prototype finished and tested:** the wrong action deleted; stretch (`T`) and array added through computer use with typed coordinates. Inserted from its saved file into a new drawing: 16/16. At 3/4", 1", 1-1/2", 2" the tip lands at −L and the thread count is exactly floor((L − pilot)/pitch), threads ending above the pilot.
- **11 all 7 sizes by script:** one block with 7 visibility states, 1 Length, 7 Thread parameters, 1 stretch, 7 arrays; per-size temporary layers let the script select each size's objects inside the Block Editor and were removed afterwards. Test: visibility and thread counts right at the default length, but **the length grip moved nothing**.
- **12 diagnosis and fix (computer use):** with `BVMODE` 1 every parameter showed greyed: parameters created while a state was current were hidden in the states, so the scripted stretch had nothing to pick. Fixed with `BVSHOW` … All on the parameters, the stretch re-added with `BVMODE` 1 so all 7 pilots were selectable, and two array spacings rounded down. Retest 73/73 (every size at 1" and 2": width, tip, thread count, threads above pilot).
- **13 callout, default size, hidden helpers (computer use):** an invisible attribute whose default is two BlockPlaceholder fields plus text (size and fractional length, e.g. `#10-16 x 1 1/4" HWH TEK`), a second invisible attribute typed per job, the default state moved to the top of the list, and *Show properties = No* on the seven helper parameters. Tests 16/16 (label text after size/length changes and a regen; default state; both attributes present in every state) and 73/73 geometry; a placed block exposes only the size and Length.

## Not covered
- A plan/head view, scales other than full size, other fastener families, and a reliable scripted path for actions (the corrected keywords and point picks are recorded but the full scripted build was finished by hand).

## Process notes
- Computer use: `open_application` started a second AutoCAD instance instead of fronting the running one (closed again within a minute, nothing open in it); typing that goes through the clipboard into the drawing area becomes a `PASTECLIP` (cancelled); the desktop tool will not type into AutoCAD's file dialogs, so the user typed the one file name.
