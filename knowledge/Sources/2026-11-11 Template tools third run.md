# 2026-11-11 Template tools, third run

Report-ID: AMCP-LIVE-20261111-02
Writer: Claude, in a Claude desktop session. Alex installed the 0.1.6 bundle and said "Okay its installed". Follows [[Sources/2026-11-11 Template tools second run]].
Question: do the two 0.1.6 fixes work against AutoCAD?

## Setup
- AutoCAD 2027 (26.0s) on the home PC, with no drawing open at the start. Server 0.1.6 from branch `feat/template-tools`, installed as a Claude desktop extension. Calls went through Claude's own MCP connection.
- One scratch drawing from AutoCAD's default template (Drawing2), closed without saving at the end. Nothing was written to disk.

## Results (3 of 3 checks)
- **new multileader style without a text style (0.1.6 fix):** `add_multileader_style` with only a name and scale 2 created the style and reported text style "Standard", the current multileader style's. In 0.1.5 this call failed.
- **paper name that fits several, on a layout never set up (0.1.6 fix):** `set_page_setup` on Layout2 with "17.00 x 11.00" gave the message listing the three ANSI B papers and nothing after it. In 0.1.5 it ended "rollback was incomplete".
- **the same layout afterwards:** `set_page_setup` with the full paper name and `monochrome.ctb` then worked, so the failed call left the layout usable.

## Not covered
- What plot device and paper Layout2 had after the failed call was not read back.
- A drawing whose current multileader style itself has no text style (the tool then uses the current text style; offline-tested only).
