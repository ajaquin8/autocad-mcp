# 2026-11-18 Improvement list live check

Report-ID: AMCP-LIVE-20261118-01
Writer: Claude Code, in the session that built the fixes. The user saved open work and gave the go ("Saved, go") after the batch was described.
Question: do the fixes and tools from the 2026-11-18 improvement list (T1, T2, T3, T5, B1, B2, B3, B6) work against AutoCAD?

## Setup
- AutoCAD 2027 on the home PC, with the user's own drawings open (not touched; the drawing active before was switched back to at the end, a tab switch only).
- `tests/live/improvements_check.py`, run with the repo's `.venv` from a local branch `live/2026-11-18` that merged `fix/activate-and-hangs`, `feat/block-library` and `feat/text-and-space`. Not through the installed Claude desktop extension.
- Three scratch drawings made by the script (a library drawing, a target drawing and one more for T1), closed without saving. The library was saved under `scratch/` for the import.

## Results (70 of 72 checks)
- **verified T1:** `run_command` in an inactive drawing pointed to `activate_document`; `activate_document` made it active, and REGEN then ran there. Switching back to the user's drawing at the end worked.
- **verified T2:** `define_block` made a block from a frame, two lines and a centred attribute (4 objects, MARK listed), and a tag block with `originals="replace"` (one reference left). **Failed check:** the result said `"objects": 2` for every block. **observed:** through late binding `CopyObjects` returned a pair (the copies and the IDPairs output). Fixed the same day: the count now comes from the definition.
- **verified T5:** an attribute and a TEXT with `justify="MC"` were centred on the given point (bounding box centre within 0.001); the TEXT used the new text style; an MTEXT with `attachment="MC"` kept its insertion point at the given point.
- **verified B6:** with a sheet tab active, `draw_line` reported model space with the note; `draw_circle(layout=...)` was owned by the sheet's paper space block.
- **verified B1:** in the Block Editor, a stretch with `multiplier=0.5` and its badge far off screen completed (view widened first), after a plain right-side stretch. The block then grew by exactly 12 at Width 72, left side fixed.
- **B2, failed check, safe outcome:** a model-space handle was not refused before BACTION started (the owner pre-check did not match inside the Block Editor). **verified:** `(handent)` of that handle found nothing inside the Block Editor; BACTION stopped at the selection, was put back, and AutoCAD stayed idle; no hang. Fixed the same day: the pre-check is gone, and the error now says the handles are not objects of the block being edited.
- **verified B3:** `DELAY 3000` with a 1 s timeout was cancelled by the server; the error listed the prompts and said AutoCAD answers again; AutoCAD was idle afterwards.
- **verified T3:** import without overwrite skipped the existing block. With overwrite, a plain old definition was replaced by the library's dynamic one, both references (model space and nested in a legend block) were switched, a new block came in, and the old definition was deleted. A second overwrite (dynamic over dynamic) kept the placed reference's Width 72 and also deleted the old definition. The imported block behaved (Width 72, 12 wider).

## Not covered
- The two fixes made after this run (T2 count, B2 message) are offline-tested only.
- Whether the expression's error handler ran after the B3 cancel: the error did not say the drawing was put back (no UNDO Back line in the transcript), though AutoCAD answered again.
- `define_block` with `redefine=True`, `originals="delete"`, `add_text` with every justification, `import_blocks` from a drawing open in AutoCAD, attribute references after an overwrite (ATTSYNC).
- The installed extension: everything here ran with the repo code.

## Follow-up
- [[Change log]] entry of 2026-11-18 (live check). API lessons in [[Research/AutoCAD API gotchas]].
