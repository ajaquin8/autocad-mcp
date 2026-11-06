# 2026-11-06 Stretch grips by script

Report-ID: AMCP-LIVE-20261106-01
Writer: Claude Code, written up on 2026-11-06 from the notes of the session that ran the batch (a drafting-templates session). That session had Alex's go before each step. This writer did not watch the batch, so the items below are **reported**: that session's notes call them verified, meaning seen in its log, on screen or in AutoCAD's command history.
Question: can Width and Height stretch grips be added to an existing window-unit block through this server, and where does scripted Block Editor work stall?

## Setup
- AutoCAD 2026 on the work PC (a vendor-branded AutoCAD 2026). Only drawings the session's script created were changed: a scratch drawing, then a new seed drawing holding the block.
- `send_command` was off in the running server (it is opt-in, `AUTOCAD_MCP_ENABLE_COMMANDS=1`). So the Block Editor steps ran in a Python script that imported the package (session, block and document helpers, `control`) instead of through MCP tools.
- Goal: two linear parameters (Width, Height) and four stretch actions on the block.

## Results (reported)
- **Spaces in a block name:** `SendCommand('_.-BEDIT "<name with spaces>"')` hung. On the command line a space is Enter, and quotes do not help. `(command "_.-BEDIT" "<name>")` worked, because a LISP string keeps its spaces.
- **A command left waiting:** `(command "_.BPARAMETER" "_L" "_L" "Width" p1 p2 plab)` left BPARAMETER waiting for the number of grips. The script's `GetVariable` polls were then refused (COM is refused while LISP or a command waits), so it could neither answer nor cancel. A retry with `"1"` added completed it.
- **A wrapper that never leaves AutoCAD waiting:** `(progn (command ...) (if (> (getvar "CMDACTIVE") 0) (progn (setvar "USERS1" (getvar "LASTPROMPT")) (command))))` returned AutoCAD to an empty command line. `(command)` with no arguments acts as Esc.
- **LASTPROMPT lags one input:** a prompt is printed only when the next input arrives, so a driver cannot read the prompt it is about to answer. With `CMDECHO 0` it holds the echo of the typed expression.
- **Selections block COM:** while BACTION waits at "Select parameter:", every COM call is refused, so outside polling freezes.
- **BACTION prompt order** (BACTIONBARMODE 0): Select parameter, then `Enter action type [Array/Move/Scale/sTretch]` (Stretch is **T**, not S), then `parameter point [sTart point/Second point] <Second>`, then the stretch frame's first and opposite corners (or CPolygon), then `Select objects` (crossing) and Enter, then `Specify action location or [Multiplier/Offset]` (M asks for the distance multiplier before the location).
- **Picking a parameter by ename fails:** "*Invalid selection* Expects a single object." A pick on screen worked. An entsel-style `(list ename point)` was not tried.
- **Unlocked attribute definitions** were filtered out of the stretch selection ("N unlocked AttDefs filtered from selection") until their position was locked (`LockPosition`).
- **Closing the Block Editor:** `BCLOSE` after `BSAVE` still asked `[Save/Discard changes]` once. Later it showed a modal task dialog "Block - Changes Not Saved", which blocks COM completely.
- **`cancel_command` refused** in the script's drawing. The drawing was in the ownership record (`owned.json`), but the server reads that record only when it connects. The same check (record plus window title) run by a helper process worked. Fixed on 2026-11-06: `cancel_command` now reads the record again, without COM.
- **SECURELOAD:** loading a `.lsp` file from the templates folder raised AutoCAD's trust prompt (Alex approved it). An inline expression avoids it.
- **Typing at the command line** through desktop control was reliable. Prompts were visible, Stretch = T was found this way, and absolute coordinates were typed as `x,y` (`#x,y` was rejected with dynamic input off). The first click after typing into the floating command line only focused the drawing area; the pick needed a second click.
- **Log lost:** Python output piped and then killed by a timeout lost the whole log. Run with `-u` or line buffering.
- **Stretch moves what it does not stretch:** objects in an action's selection with no point inside the stretch frame are moved. Two half-distance "centre" actions first picked their objects with a crossing window. That also caught the frame outlines and glass strips crossing the band, which then moved by half (12" and 18" off). The fix was a crossing window, then removing `(ssget "_X" '((0 . "LWPOLYLINE,DIMENSION")))`. A plain window misses wide text (attribute definitions, MTEXT) that sticks out of a narrow band.
- **Redefining the block in a drawing that already has it:** `-PURGE` reported "No unreferenced blocks" right after the stretched reference was deleted. Its anonymous `*U` copy still counts until save and reopen. The workaround in an unsaved test drawing: `-RENAME` the old block, then insert the source drawing again.
- **Result:** the Width and Height grips with four stretch actions work. A test insert at 48 x 72 moved the right jamb, head, dimensions, tags and glass strips; centred items stayed centred. After the centre fix, a 60 x 84 unit grew by exactly 24 x 36 with everything in place. The seed drawing was saved.

## Not covered
- Any of this through MCP tools: there was no tool for prompt-driven commands. The planned tools (`run_command`, Block Editor tools) were built after this batch and are **not live-verified** yet.
- An entsel-style `(list ename point)` answer at "Select parameter:".
- Why `BCLOSE` asked on the command line once and showed a task dialog another time.

## Follow-up
- 2026-11-06: `cancel_command` reads the ownership record again; busy errors name the AutoCAD dialog that blocks; status polls retry only briefly ([[Change log]]).
- Lessons copied to [[Research/AutoCAD API gotchas]].
