# 2026-11-04 Busy handling

Report-ID: AMCP-LIVE-20261104-04
Writer: Claude Code. The batch was described first and run after Alex's go ("Saved, go"). Alex switched tabs and started LINE when asked.
Question: do the new busy-handling parts work on AutoCAD 2026? They are the message filter, the settle wait in `new_drawing`, and `cancel_command` ([[Decisions/Edit guard and document safety]]).

## Setup
- AutoCAD 2026 on the work PC, with a third-party add-in that loads into every new drawing. Script `tests/live/busy_check.py`, one process per phase. The script installs the same message filter on its own thread.
- Only a new scratch drawing (Drawing35) was changed. The user's drawing was only read: its title, for the refusal check.

## Results
- **new:** `new_drawing` created and settled Drawing35 in 11.6 s and marked it as server-created (2/2). The filter logged no rejections in this run.
- **refused:** with the user's drawing active, `cancel_command` refused (2/2). AutoCAD's real title format here is `<product> - [<drawing>.dwg]`.
- **cancel, first try:** the tool's first method, WM_CHAR Esc posted twice to AutoCAD's main window, did **not** clear LINE.
  - The script also first looked the drawing up over COM while the prompt was open. That was rejected, so the script was changed to mark the drawing from its saved name and look it up only after cancelling.
  - During this phase the filter saw 63 "retry later" rejections and retried 61 of them.
- **Trying other methods by hand** (Drawing35 only, title checked before each send):
  - WM_KEYDOWN/WM_CHAR/WM_KEYUP Esc did nothing; no AutoCAD window had keyboard focus while the user was in another app.
  - Two Ctrl+C handed to AutoCAD as command-line input with WM_COPYDATA (dwData 1, the same channel external programs use to send commands) cleared LINE at once: CMDACTIVE 0.
- **cancel, with the tool changed to WM_COPYDATA `^C^C`:** 3/3. LINE was cancelled and CMDACTIVE read 0.
- **cleanup:** Drawing35 closed (2/2).

## Not covered
- A prompt left open by a scripted command (`send_command`) rather than typed. A modal dialog: `^C^C` is command-line input and will not close a dialog.
- How long the retry window should be. 8 s covered every rejection seen here.
