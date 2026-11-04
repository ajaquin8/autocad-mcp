# 2026-11-04 Ownership across restarts

Report-ID: AMCP-LIVE-20261104-05
Writer: Claude Code. The batch was described first and run after Alex's go ("Saved, go"); no user action was needed.
Question: does a restarted server take back its own still-open drawings, and nothing else, on AutoCAD 2026? See [[Decisions/Edit guard and document safety]].

## Setup
- AutoCAD 2026 on the work PC (process 32844, running since 2026-11-02). Script `tests/live/ownership_check.py`. Every phase is a new process, which stands in for a server restart.
- Only scratch drawings saved to `scratch/` were changed. The user's open drawing was only read.

## Results
- **make:** `new_drawing` (Drawing36) saved to `scratch/` (3/3). The record (`%LOCALAPPDATA%\autocad-mcp\owned.json`) held the AutoCAD identity and the drawing's path and document window.
- **restart:** in a new process the scratch drawing was editable again (`created_by_mcp` true), and the user's drawing stayed locked (3/3).
- **reopen, first try: failed.**
  - The close worked, and the record emptied as designed.
  - The lookup right after `Documents.Open` failed, although the drawing then opened. The scratch file was found open and **locked** afterwards.
  - Fix: `open_drawing` now uses the same settle wait as `new_drawing`.
- **A one-off check crashed its own Python process** (not AutoCAD). It created a message filter without keeping a reference, so COM called freed memory. Fix: `MessageFilter.register()` now keeps every registered filter alive.
- **Rerun with both fixes:** cleanup 2/2, make 3/3 (Drawing37), reopen 4/4, cleanup 2/2.
  - In the reopen phase, a new process could close its scratch drawing only because ownership was taken back.
  - After reopening, the file was locked.
  - The record ended empty.

## Not covered
- AutoCAD itself restarting: this is covered offline only (a different identity takes nothing back).
- Two server processes running at once (the known gap in the decision note).
