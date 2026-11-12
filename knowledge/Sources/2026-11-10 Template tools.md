# 2026-11-10 Template tools

Report-ID: AMCP-LIVE-20261110-01
Writer: Claude, in a Claude desktop session. The batch was described first and run after Alex's go ("Lets go!"). It stopped at its first failure, as agreed, and went on after Alex said "keep pushing and keep testing as we build".
Question: do the template tools of 0.1.4 work against AutoCAD: `add_text_style`, `add_dimension_style`, `add_multileader_style`, `set_page_setup`, `add_attribute_definition`, the `layout` argument of `insert_block` and the `plot` argument of `add_layer`?

## Setup
- AutoCAD 2027 (26.0s) on the home PC. Server 0.1.4, the bundle built from branch `feat/template-tools` at its second commit ("Document the template tools"), installed as a Claude desktop extension. Every call went through Claude's own MCP connection; no script.
- Two scratch drawings from AutoCAD's default template (Drawing6, Drawing7). Five other server-created drawings were open and were not touched.
- Drawing7 was saved as a title-block drawing in the Windows Temp folder so it could be inserted by path, and the sheet was plotted to a PDF there. Both were deleted afterwards. The PDF was rendered with pypdfium2 to look at it.

## Results (14 of 15 checks)
- **text style, AutoCAD font:** `add_text_style` with `romans.shx`, made current: created.
- **text style, TrueType by name: failed.** `arial.ttf` was refused: `AttributeError: Property 'Add.FontFile' can not be set`. The rollback worked: afterwards the drawing had only Standard, Annotative and the first test style.
- **text style, TrueType by full path** (run after the rest): `C:\Windows\Fonts\arial.ttf` with width factor 0.9 was accepted, and text in that style plotted as Arial.
- **dimension style:** `add_dimension_style` with 13 DIM variables, the new text style and the `tick` arrowhead: created and current. DIMTIH and DIMTOH were accepted as 0; DIMBLK read back as `ArchTick`.
- **dimensions in that style:** six linear dimensions showed tick marks, text above and along the dimension line, and unstacked fractions, on screen and in the PDF. The text of both 1 1/2" dimensions went outside, beyond the second point; one landed on the neighbouring 3" text, which was the test's own choice of point order.
- **multileader style:** `add_multileader_style` with scale 4, text and arrow 3/32, the new text style: created and current. An `add_leader` callout of 27 characters measured 10.3 wide, so about 0.375 high; the unscaled Standard style had given 0.18 on 2026-11-09.
- **layer plot flag:** `add_layer` with `plot=False` reported `plottable: false`, and the viewport frame drawn on that layer was absent from the PDF.
- **attribute definitions:** three `add_attribute_definition` calls worked, one with an empty default. The tag given as `title` stayed lower case.
- **page setup:** `set_page_setup` on Layout1 of the drawing that was not active, a layout never opened before: DWG To PDF.pc3, "ANSI full bleed B (17.00 x 11.00 Inches)", `monochrome.ctb`. The PDF page is 1224 x 792 points.
- **title block on the sheet:** `insert_block` with the saved drawing's path and `layout="Layout1"`, in that same non-active drawing: inserted, with all three attributes filled. Keys given in upper case matched the lower-case tag.
- **viewport and plot:** `add_viewport` at 1:4, then `plot_pdf`. The page shows the border, the filled title block and the detail, with no colour (0 non-grey colours in a 1592 x 1030 render) and no viewport frame.
- **cleanup:** both scratch drawings closed without saving; the Temp files deleted.

## Also seen
- Layout1 had only the paper-space viewport and the new one. On 2026-11-09 an empty layout had got an automatic viewport on first activation.
- A screenshot of the layout did not show text added to model space after the viewport was made; the next plot did.

## Changed after this run (offline-tested only)
- `add_text_style` looks a TrueType file name up in the Windows Fonts folders and passes the full path, and turns a refused font into a plain message.
- `add_attribute_definition` makes the tag upper case.

## Not covered
- Changing an existing text, dimension or multileader style, and the rebuild of dimensions already drawn in a changed style.
- Rollback of a page setup; the error that lists several matching papers; plot devices other than DWG To PDF.
- Attribute modes other than the default (invisible, constant, preset).
- AutoCAD 2026 and the work PC.
