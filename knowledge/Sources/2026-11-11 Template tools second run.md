# 2026-11-11 Template tools, second run

Report-ID: AMCP-LIVE-20261111-01
Writer: Claude, in a Claude desktop session. Alex installed the 0.1.5 bundle and said "want to test it now and then I will merge after". Follows [[Sources/2026-11-10 Template tools]].
Question: do the 0.1.5 fixes work against AutoCAD, and do the paths the first run left out: changing existing styles, attribute modes, and a paper name that fits several papers?

## Setup
- AutoCAD 2027 (26.0s) on the home PC, with no drawing open at the start. Server 0.1.5 from branch `feat/template-tools`, installed as a Claude desktop extension. Calls went through Claude's own MCP connection.
- One scratch drawing from AutoCAD's default template (Drawing1), closed without saving at the end. Nothing was written to disk.
- One step used a short COM script instead of the server, on that scratch drawing's Layout2 only: it changed the layout's plot device and paper, then put each old value back one at a time to see which one AutoCAD refused.

## Results (11 of 13 checks)
- **TrueType by name (0.1.5 fix):** `add_text_style` with `arial.ttf` created the style with the full path in the Windows Fonts folder.
- **missing TrueType file:** `nope.ttf` gave "No font file 'nope.ttf' in the Windows Fonts folders", before AutoCAD was touched.
- **unknown AutoCAD font (0.1.5 fix):** `doesnotexist.shx` gave "AutoCAD did not accept the font file", and no style was left behind.
- **attribute tag case (0.1.5 fix):** the tag given as `title` came back as `TITLE`.
- **changing a text style:** the style's font changed from Arial to `romans.shx`; text already drawn in it followed (its width went from 6.93 to 10.71).
- **new dimension style, then a dimension in it:** as in the first run.
- **changing a dimension style that was not current:** it became current, took DIMSCALE 8 and tick arrowheads, and its one dimension was rebuilt (reported, and its box grew).
- **new multileader style without a text style: failed.** `AutoCAD COM error 0x80020009 ... Null object ID` at the line that reads the style's text style back. Nothing was left behind.
- **new multileader style with a text style, then a leader:** worked, as in the first run.
- **changing a multileader style:** scale 4 to 8; the leader already drawn in it grew (its box went from 18.3 to 24.7 wide).
- **paper name that fits several: half failed.** The message was right ("'17.00 x 11.00' matches several paper sizes: ANSI B ...; ANSI expand B ...; ANSI full bleed B ..."), but it ended "rollback was incomplete: restore failed: ... Invalid input".
- **attribute modes:** definitions with `invisible`, `constant` and `preset` were created. The modes were not read back.
- **page setup:** DWG To PDF, ANSI full bleed B, `monochrome.ctb` on Layout1: set.

## What the COM script showed
- The scratch drawing's layouts had the PC's default Windows printer as plot device. Layout2, never opened, had an empty paper name.
- After changing device and paper, every old value went back except the paper name: AutoCAD refuses the empty string ("Invalid input"), with or without `RefreshPlotDeviceInfo`. The layout then showed the restored device's default paper.

## Changed after this run (verified live in [[Sources/2026-11-11 Template tools third run]])
- `add_multileader_style` gives a new style a text style: the current multileader style's, else the current text style.
- `set_page_setup` does not try to put an empty paper name back.

## Not covered
- A block inserted from a drawing with invisible, constant or preset attributes.
- Plot devices other than DWG To PDF; AutoCAD 2026 and the work PC.
