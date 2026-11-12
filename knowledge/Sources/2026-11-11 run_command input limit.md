# 2026-11-11 run_command: why it never started, and the fix

Report-ID: AMCP-LIVE-20261111-03 (diagnosis) and AMCP-LIVE-20261111-04 (the fix)
Writer: Claude, in a Claude desktop session building title blocks through the installed 0.1.6 extension. Alex gave the go for a live test in a scratch drawing ("Yes") after `run_command` failed seven times in that session.
Question: why does AutoCAD not run the expression `run_command` sends, and what does?

## Setup
- AutoCAD 2027 (26.0s) on the home PC; AutoCAD was not the foreground window. Alex's own drawings open at the time were server-created title block drawings and two read-only examples; none was touched.
- Scripts under `scratch/` (`diag_copydata*.py`, `live_run_command_fix.py`), run with the repo's `.venv` from a shell started by Desktop Commander, not through the installed extension. Scratch drawings Drawing15 to Drawing18, all closed without saving. Each diagnostic expression set `USERI1` in the scratch drawing and the script read it back over COM.

## Results: diagnosis (AMCP-LIVE-20261111-03)
- **verified:** an expression sent without Enter is not evaluated. It sits on the command line as typed text (LASTPROMPT showed it) and AutoCAD rejects COM calls until Enter or a cancel. An Enter sent later as its own message evaluates it.
- **verified:** an expression with `\n` or `\r` at its end, in the same message, is evaluated within 0.2 s. A trailing space works too.
- **verified:** the length limit. A message of 998 characters plus `\n` ran; 999 plus `\n` did not (bisected between 500 and 1000). Longer messages (1000, 2000, 4000 characters, and the real `run_command` expression at 1351 and 1469) are dropped whole: nothing appears on the command line, `SendMessageTimeout` still reports success, and LASTPROMPT does not change.
- **verified:** input sent right after `Documents.Add` (0, 2, 4 and 8 s later) is evaluated in the new drawing.
- **observed:** typing one long expression across several messages is unreliable. Cut every 400 characters (4 messages, 0.05 s apart) the real expression ran and wrote a full transcript. Cut every 200 characters (8 messages) AutoCAD answered "Unknown command" for its tail. Cut between top-level forms with no pause, 1 of 6 commands ran. **unresolved:** why.
- **verified:** from that shell, `%LOCALAPPDATA%\autocad-mcp\run` was the real folder, visible to AutoCAD, and held no leftover transcripts. So the earlier expressions never ran at all; the private-copy problem ([[Research/AutoCAD API gotchas]], 2026-11-10) was not what stopped them.
- **observed:** the first diagnostic sent three short expressions with no usable result before the pattern was understood (one without Enter, two cancelled 2 s later by the script). It also left AutoCAD waiting twice with text on the command line; `cancel_command` through the extension cleared it both times.

## Results: the fix (AMCP-LIVE-20261111-04, 22 of 22 checks)
Branch `fix/run-command-input-limit`. `run_command` now sends short complete expressions, each with its Enter: the first ones store the big expression's text in `amcp:src` a piece at a time and write an `S` line to the transcript, the server waits for each `S` line, and the last message is `(eval (read amcp:src))`.
- **REGEN:** completed, 4 messages.
- **-HATCH** (solid, select objects, two nested rectangles): one hatch, area 7.0, so the inner rectangle was treated as an island.
- **CHPROP** on `{"last": true}` with Color, Truecolor, `0,194,184`: the hatch's `TrueColor` read back 0,194,184.
- **-LAYER** with 25 answers (12 new layers with 50-character names): completed in 5 messages; all 12 layers exist.
- **-LAYOUT** New "GD TEST SHEET": the layout exists.
- **LINE with one answer:** cancelled at "Specify first point:" and undone; no line left; CMDACTIVE 0 at the end.

## Not covered
- The fix through the installed extension (it needs a new bundle), where the server may see a private `%LOCALAPPDATA%`. The transcript folder moved to `%USERPROFILE%\.autocad-mcp\run` for that reason; **not verified** from inside the Store build.
- The Block Editor tools built on `run_command` (`tests/live/command_check.py` has still not run).
- AutoCAD 2026, and AutoCAD as the foreground window.
- Whether the 999-character limit is the same on other versions.
