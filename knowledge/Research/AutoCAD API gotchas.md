# AutoCAD API gotchas

What the AutoCAD 2027 ActiveX (COM) API really does. Add a dated entry for every lesson, with an evidence label. Until the first live test, almost everything here is **inferred** from other projects' code and comments.

## 2026-10-29: starting list (before any live test)
- **inferred (from U-C4N's comments, which say verified on 2026):** keep every object late-bound. With a makepy (gen_py) cache, `ModelSpace.Item(i)` comes back wrapped as `IAcadEntity` and loses the members of the real class (a line's `StartPoint`). `session._late_bound` uses `win32com.client.dynamic.Dispatch` for the application, and everything it returns stays dynamic.
- **inferred:** points and coordinate lists must be `VARIANT(VT_ARRAY | VT_R8, ...)`; a plain tuple is rejected. Helpers: `com.point()` and `com.doubles()`.
- **inferred:** AutoCAD collections are 0-based (`Documents.Item(0)`), unlike Inventor's 1-based ones.
- **inferred:** `PlotToFile` returns immediately and writes nothing yet while `BACKGROUNDPLOT` is 1 or 2; `plot_pdf` sets it to 0 for the plot and restores it.
- **inferred:** `Linetypes.Load` needs `acadiso.lin` in metric drawings (`MEASUREMENT=1`) and `acad.lin` in imperial ones.
- **inferred:** AutoCAD rejects COM calls (`RPC_E_CALL_REJECTED`) while a modal dialog or a command is active; pywin32 has no `CoRegisterMessageFilter`, so calls are not retried automatically. A rejected call never ran, so it is safe to ask the user and retry.
- **inferred:** the ActiveX API has no linear dimension method; horizontal and vertical dimensions are `AddDimRotated` at 0° and 90°.
- **reported by the research subagent, not re-verified:** `Documents.Count` is 0 when only the Start tab is open; `acad_status` handles this.
- **unresolved:** whether `StartUndoMark`/`EndUndoMark` called over COM group the changes into one Ctrl+Z step.
- **unresolved:** `GetBoundingBox` through dynamic dispatch (U-C4N calls it as `lo, hi = ent.GetBoundingBox()`).

## 2026-10-29: first live run ([[Sources/2026-10-29 First drawing]])
- **verified:** the proxy returned by `Documents.Add()` could not resolve `ReadOnly` (AttributeError), although `Name`, `FullName` and `Saved` worked; the same drawing from `Documents.Item(i)` works. Always re-fetch a new or opened drawing by name.
- **verified:** `GetBoundingBox` works through dynamic dispatch as `lo, hi = ent.GetBoundingBox()`. **superseded:** the "unresolved" item above.
- **verified:** `Linetypes.Load("HIDDEN", "acad.lin")` works in an inches drawing (MEASUREMENT 0).
- **verified:** `AddDimRotated` at 0° and 90° makes horizontal and vertical dimensions (`AcDbRotatedDimension`).
- **verified:** `PlotToFile` with `BACKGROUNDPLOT=0` writes the PDF before returning; afterwards the drawing reports unsaved changes.
- **verified:** `SaveAs` renames the open drawing (`Name` becomes the new file name).
- **verified:** with only the Start tab open, `Documents.Count` is 0. **superseded:** the "reported by the research subagent" item above.
- **unresolved:** undo grouping with `StartUndoMark`/`EndUndoMark` (still to try with Ctrl+Z).

## 2026-10-29: kitchen plan ([[Sources/2026-10-29 Kitchen plan]])
- **verified:** dimensions made with `AddDimRotated`/`AddDimAligned` ignore DIM* system variable overrides and follow the active dimension style. Copy the settings into the style with `ActiveDimStyle.CopyFrom(doc)`.
- **verified:** an existing dimension keeps its built picture after its style changes, even through `REGEN`, until `dim.Update()` is called on it.
- **verified:** a `PrintWindow` capture taken straight after `ZoomExtents` can be blank; AutoCAD needs a moment to redraw.
- **verified:** integer system variables (LUNITS, DIMLUNIT, BACKGROUNDPLOT) accept plain Python ints through `SetVariable`.

## 2026-10-29: kitchen elevations ([[Sources/2026-10-29 Kitchen elevations]])
- **verified:** DIMZIN in architectural units: 0 shows 14' (zero inches suppressed); 3 is needed for 14'-0" with zero feet still suppressed.
- **verified:** `HandleToObject(h).Delete()` removes a polyline found with a model space scan; the handle came from `query_entities`.

## 2026-11-03: AutoCAD ProgIDs on a PC with DWG TrueView (work PC setup)
- **verified (registry, work PC):** with AutoCAD 2026 (R25.1, plus Architecture and Mechanical 2026) and DWG TrueView 2027 installed, `AutoCAD.Application.26` is registered by TrueView (`dwgviewr.exe /Automation`), while `AutoCAD.Application.25.1`, `.25` and the unversioned `AutoCAD.Application` start `AutoCAD 2026\acad.exe`. A versioned ProgID therefore does not prove that AutoCAD of that release is installed.
- **inferred:** with TrueView open, `GetActiveObject("AutoCAD.Application.26")` would return TrueView, and launching `.26` would start TrueView. `session.connect` now scans the registry for every `AutoCAD.Application.<release>` name (newest release first, then the unversioned one; about 0.04 s for 7,700 keys on the work PC), skips a running TrueView (exe `dwgviewr.exe` or "TrueView" in `Name`) and launches only a ProgID whose `LocalServer32` is `acad.exe`.
- **unresolved:** not yet run against the live AutoCAD 2026 on the work PC: which ProgID it registers in the running object table (`.25.1` is expected), whether TrueView answers `FullName`/`Name` as assumed, and whether the tools behave the same on 2026, or on releases older than 2025, as on 2027.

## 2026-11-03: first live connection to AutoCAD 2026 ([[Sources/2026-11-03 AutoCAD 2026 connection]])
- **verified:** with TrueView closed, the registry-based `session.connect` attached to AutoCAD 2026 (`acad.exe`, version "25.1s (LMS Tech)"), and `acad_status` worked unchanged on 2026. **superseded (in part):** the 2026-11-03 "unresolved" item above about running against the live AutoCAD 2026; still open are which ProgID 2026 registers in the running object table, how TrueView answers `FullName`/`Name`, and the drawing tools on 2026.

## 2026-11-03: drawing tools on AutoCAD 2026 ([[Sources/2026-11-03 AutoCAD 2026 drawing]])
- **verified:** `Documents.Add`, layers with a loaded linetype, `AddLightWeightPolyline` with bulges, lines, arcs, circles, TEXT, MTEXT, `AddDimRotated`, `ZoomExtents`, PrintWindow capture, `SaveAs` and `PlotToFile` behave on AutoCAD 2026 (R25.1) as on 2027: the same 33 steps passed with the same read-back values. **superseded (in part):** the "drawing tools on 2026" item left open above. Still open: which ProgID 2026 registers in the running object table, and how TrueView answers `FullName`/`Name`.

## 2026-11-03: Application.Version is a release number, not a year
- **verified 2026-11-03 (a reply Alex pasted from the Claude desktop app):** `acad_status` returned `"autocad": "25.1s (LMS Tech)"` and Claude called it "AutoCAD 2025"; release 25.1 is AutoCAD 2026 (consistent with the ProgID `.25.1` noted above). `acad_status` now names the product year from a table of release numbers (`session.RELEASE_YEARS`, 2013 to 2027) and keeps the raw string as `autocad_version`. A release missing from the table is reported as "release N.N", never guessed.

## 2026-11-03: a busy AutoCAD rejects late-bound lookups as AttributeError
- **verified (AMCP-LIVE-20261103-03, AutoCAD 2026):** while the user is inside LINE or has the OPTIONS dialog open, AutoCAD rejects COM calls immediately (no hang). With pywin32's late binding the first symptom is not a `com_error` but `AttributeError: <unknown>.Count`: each new dispatch object (here `app.Documents`) looks members up by name, the lookup is rejected, and pywin32 reports the name as unknown. A warmed-up process gets the same, because `Documents` is a new object on every access. So the server's `CMDACTIVE` check is not reached in these states; AutoCAD's rejection is what keeps the drawing safe. `describe_attribute_error` maps `<unknown>.` errors to the busy message.
- **verified:** after Esc / closing the dialog the next call works without reconnecting.

## 2026-11-03: sheets, viewports and leaders over COM
- **verified (AMCP-LIVE-20261103-04):** a paper-space viewport at an exact scale: make the layout active, `PaperSpace.AddPViewport(center, width, height)`, `Display(True)`, `MSpace = True`, `ActivePViewport = vp`, `Application.ZoomWindow` on the model rectangle the viewport should show, then `StandardScale = acVpCustomScale` and `CustomScale = scale`, and `MSpace = False`. The scale read back exactly. (Order from the ActiveX guide "About Creating Paper Space Viewports".)
- **verified:** `ModelSpace.AddMLeader(points, 0)` plus `TextString` gives a multileader in the current multileader style; the current style is the `CMLEADERSTYLE` variable, and the styles themselves live in the `ACAD_MLEADERSTYLE` dictionary (no collection object).
- **verified:** a template's current dimension style can name a style that is not in the file (here a metric `ISO-25`); AutoCAD then uses Standard. Set the intended style current before dimensioning.
- **verified:** title blocks in paper space are found through the layout's `Block`, and `HandleToObject` reaches them like model-space objects.
- **verified (AMCP-LIVE-20261103-05):** a plot with a missing plot style table still writes the PDF (in layer colours); the only trace is AutoCAD's `PlotandPublishLog.CSV` ("WARNING: Incompatible or missing plot style", "Plotted with Warning(s)"). Read that log to check a plot, not just the PDF's existence.
- **verified:** DIMLUNIT 2 shows the dimension style's own decimal separator (DIMDSEP); a style set up for metric work prints `1,00`. Look at the printed text, not the measured value, when checking decimal dimensions.
- **verified:** in a live script, every COM call and tool function must run on the thread that connected; connecting on the STA worker and then calling from the main thread fails with "interface marshalled for a different thread" (RPC_E_WRONG_THREAD).

## 2026-11-03: dynamic blocks from outside AutoCAD
Source: [[Sources/2026-11-03 Dynamic block authoring]] (AMCP-LIVE-20261103-06 to -13).
- **verified:** scriptable through `SendCommand` + `(command ...)` in the Block Editor: `BEDIT` by name, `BPARAMETER` (visibility, linear with label, value list, chain actions, grip count), `-BVSTATE` New/Set/Delete, `BVSHOW`/`BVHIDE`, `BACTION` stretch and array, `CHPROP`, `BSAVE`, `BCLOSE`. Picking a parameter by a point on its dimension line works; `(entlast)` does not.
- **verified:** `BACTION` keywords are Array/Move/Scale/sTretch: stretch is `T`; `S` makes a Scale action. Neither action asks for a location. An array on a linear parameter asks only "distance between columns".
- **verified:** not scriptable: the contents of a Block Properties Table or lookup table, and fields (Insert Field is a dialog). These need a person or desktop control.
- **verified:** objects *and parameters* added while a visibility state is current exist only in that state. Hidden parameters cannot be picked and their grips do not show on an insert. Use `BVSHOW` … All; turn `BVMODE` 1 to select objects of other states for an action.
- **verified:** `SendCommand` rejects text containing control characters ("Invalid input"); cancel inside AutoLISP instead: a bare `(command)` acts as Esc. When a command waits for input, AutoCAD rejects all COM calls, so a scripted prompt sequence that goes wrong can only be cleared by a person (Esc).
- **verified:** after AutoCAD closes a dialog (BEDIT, Save As, block close), it can keep rejecting COM calls and ignore clicks until one Esc in the drawing area.
- **verified:** dynamic property objects from `GetDynamicBlockProperties` go stale after the visibility state changes; read them again before setting the next property.
- **verified:** `GetBoundingBox` on a dynamic block reference includes geometry hidden by visibility states; `Explode` returns only what is visible (attribute text included).
- **verified:** an array spacing typed rounded up (0.0416667 for 1/24) loses the last item when the length is an exact multiple of the spacing; round down.
- **verified:** a BlockPlaceholder field reads a dynamic property: `%<\AcObjProp.16.2 Object(?BlockRefId).Parameter(n).VisibilityState>%` or `.UpdatedDistance \f "%lu5">%` (fractional). An attribute default can hold several fields with text between them; values update on regen.
- **verified (bug, open):** `new_drawing` can fail with `AttributeError: <unknown>.Count` when AutoCAD is still busy initialising the drawing it just created; the drawing exists but is not marked as server-created.

## 2026-11-03: AutoCAD's console engine (accoreconsole) on copies
- **verified:** `accoreconsole.exe /i copy.dwg /s script.scr` runs AUDIT, DXFOUT, -PURGE and -PLOT in a separate windowless process without touching the open AutoCAD session; good for reading or cleaning copies of large drawings.
- **verified:** SECURELOAD blocks `(load ...)` from an untrusted folder; type the routine into the script instead of changing trusted paths (a user setting).
- **verified:** the console engine has no `(layoutlist)`; read layout names from the `ACAD_LAYOUT` dictionary.
- **verified:** `-PLOT` with "Detailed plot configuration? No" plots a layout with its own page setup to PDF from the console; plots of the same drawing before and after a purge compared pixel-identical.
- **verified:** a console run stopped silently after a second `AUDIT` with fix and never reached `QSAVE`; saving to a new file with `SAVEAS` worked. Check the file time after a console save.
## 2026-11-04: dynamic blocks, second round ([[Sources/2026-11-04 Dynamic block shared array]])
- **inferred:** arrayed copies are made when a dynamic block is worked out and are not in the visibility lists. An array whose source objects are hidden per visibility state keeps stale copies when only the visibility changes. Keep arrayed objects visible in every state, and let a lookup change a linear parameter, so that every choice re-works the block.
- **verified:** at BACTION's "parameter point … [sTart point/Second point] <Second>" prompt, an empty answer takes the point *nearest the pick*, not the default shown. Answer `_S` or `_T`.
- **verified:** picking a parameter by a point only works if the point is on screen and on a drawn part of it: a line, an arrow or the label text. A short dimension with its arrows outside has no line between them. A missed pick leaves BACTION waiting at "Select parameter:", and only Esc clears it.
- **verified:** in the Block Editor, attribute definitions whose position is not locked are filtered out of visibility and action selections ("2 unlocked AttDefs filtered from selection"). Set `LockPosition` first. Definitions added over COM start unlocked.
- **verified:** a stretch action *moves* selected objects that have no point inside its frame. Select only the objects whose points the frame takes.
- **verified:** if action A moves a parameter whose chain setting is on, that parameter's own actions run with A's displacement. When both act on the same point, the point moves twice.
- **verified:** a BlockPlaceholder field written into an attribute definition over COM (`TextString` with the field code) becomes a field object, but placed blocks show `####`. Made in the Field dialog with the same expression, it works. The dialog lists only parameters with *Show properties = Yes*; a field made while the parameter was shown keeps working after it is hidden.
- **verified:** a lookup parameter added while a visibility state is current is visible only in that state, like other parameters. The default visibility state is the top of the list, and the drawn helper values must match that row of the lookup, or the lookup property shows "Custom".
- **verified:** WBLOCK of a dynamic block (block → own file) keeps the parameters, actions, lookup table and attribute fields. Inserting the file gives a block named after the file. This was tested in the console engine and live.
- **verified:** the console engine has no `getpropertyvalue`, `setpropertyvalue` or `dumpallproperties`, so it cannot set dynamic properties; structural checks go through DXFOUT. `QUIT` on a never-saved drawing asks "Really want to discard all changes?", and the answer is `Y`.
- **verified:** a third-party add-in that loads into each new drawing can make AutoCAD reject COM calls ("Call was rejected by callee") for several seconds after `new_drawing`. Wait until a few calls in a row succeed.
- **verified:** Windows PowerShell 5.1 strips embedded double quotes from arguments passed to native programs, so AutoLISP passed as an argument arrives broken. Pass it from a file or another shell.

## 2026-11-04: a COM message filter from Python
- **verified (offline):** pywin32 cannot implement `IMessageFilter`: it has no `CoRegisterMessageFilter` and no gateway for the interface. A filter built with `ctypes` (a six-entry vtable, registered with `ole32.CoRegisterMessageFilter` on the STA thread) works without a new dependency. Keep the Python object alive as long as the thread, and make AddRef/Release no-ops.
- **inferred:** a filter is per thread. Live scripts that call tool functions on their own thread need their own filter, which the server's COM worker does not give them.

## 2026-11-04: cancelling a prompt without COM ([[Sources/2026-11-04 Busy handling]])
- **verified:** while a command waits at a prompt, AutoCAD rejects COM calls with "retry later" (SERVERCALL_RETRYLATER), not an outright refusal, so a message filter can wait them out.
- **verified:** WM_CHAR or WM_KEYDOWN Esc posted to AutoCAD's main window does not cancel a prompt. Command-line input sent with WM_COPYDATA (COPYDATASTRUCT, dwData 1, a Unicode string) does: `""` (^C^C) cleared LINE at its first prompt.
- **verified:** `Session.connect()` fails while a prompt is open, because loading the enum cache reads `app.Version`. Keep the window handle from an earlier connection.

## 2026-11-04: ownership and opening ([[Sources/2026-11-04 Ownership across restarts]])
- **verified:** `Document.HWND` gives each open drawing its own window handle, and a file closed and opened again gets a new one. Together with the AutoCAD process id and start time, that identifies "the same open drawing" across a server restart.
- **verified:** like `Documents.Add`, `Documents.Open` can return before AutoCAD answers calls about the new drawing. Wait until it answers several calls in a row.
- **verified:** COM holds only a raw pointer to a message filter. If Python frees the ctypes object, the next rejected call crashes the process, so keep registered filters referenced for the life of the process.

## 2026-11-04: bounding box of a dynamic block ([[Sources/2026-11-04 Block tools through the server]])
- **verified:** `GetBoundingBox` on a dynamic block reference reported the extents of a larger, hidden size (x ±0.26, top 0.19 at a size that shows ±0.207, top 0.12). The stretched end did follow the current length.
- **inferred:** the box includes objects hidden by the visibility state. To get what is shown, explode a copy and measure it (`measure_block`).
- **2026-11-04, later:** `insert_block` now reports a dynamic block's `bbox` from an exploded copy (what it shows), not from `GetBoundingBox`. `query_entities` and `get_entity` still report AutoCAD's box.

## 2026-11-06: prompt-driven commands from a script ([[Sources/2026-11-06 Stretch grips by script]])
All **reported** from the notes of the session that ran the batch (seen there in its log, on screen or in the command history); not re-checked by this writer.
- **reported:** `SendCommand` text treats a space as Enter, and quotes do not keep a name with spaces together. Pass names through LISP strings: `(command "_.-BEDIT" "<name with spaces>")`.
- **reported:** a `(command ...)` call that runs out of inputs leaves the command waiting, and every COM call is then refused, including `GetVariable` polls. Check `CMDACTIVE` inside the same LISP expression and cancel with `(command)` (no arguments acts as Esc), so AutoCAD is never left waiting.
- **reported:** `LASTPROMPT` lags one input. A prompt is printed only when the next input arrives, so a driver cannot read the prompt it is about to answer. With `CMDECHO 0` it holds the echo of the typed expression.
- **reported:** `BPARAMETER` Linear asks for the number of grips after the label location; answer `1`.
- **reported:** BACTION (BACTIONBARMODE 0) asks: parameter, action type (`[Array/Move/Scale/sTretch]`, Stretch is **T**), parameter point (`<Second>`), stretch frame corners, objects (crossing), Enter, then action location or `[Multiplier/Offset]`.
- **reported:** "Select parameter:" does not take the parameter's ename ("Expects a single object"); a pick on screen works. Untried: an entsel-style `(list ename point)`.
- **reported:** `BCLOSE` right after `BSAVE` can still ask `[Save/Discard changes]`, and once showed a modal task dialog "Block - Changes Not Saved" that blocks COM completely.
- **reported:** loading a `.lsp` file from a folder outside the trusted paths raises the SECURELOAD prompt. An inline expression sent as command-line input does not load a file.
- **reported:** a plain window selection misses wide text (attribute definitions, MTEXT) that sticks out of a narrow band. For a centre action, select with a crossing window, then remove polylines and dimensions (`(ssget "_X" '((0 . "LWPOLYLINE,DIMENSION")))`), or they move by half.
- **reported:** right after the last reference to a dynamic block is deleted, `-PURGE` still finds no unreferenced blocks: its anonymous `*U` copy counts until save and reopen.
- **inferred (offline, 2026-11-06):** while a modal dialog is open, AutoCAD's main window is disabled and the dialog is a visible, enabled top-level window of the same process (class `#32770` for message boxes and task dialogs). Busy errors now list such windows. Task dialogs draw their own buttons, so their buttons may not be listed. **unresolved:** not yet seen live.

## 2026-11-06: open questions for run_command (to check in the first live run)
- **unresolved:** whether AutoCAD evaluates an AutoLISP expression handed over by WM_COPYDATA as soon as its parentheses close, or wants Enter. `run_command` sends no Enter, and sends one only if the expression has not started (no transcript file) after 3 s; the result says so in `needed_enter`.
- **unresolved:** how long a line AutoCAD's command line takes. A Block Editor action with 14 answers is about 1.7 KB of AutoLISP.
- **unresolved:** whether the window title changes in the Block Editor. `run_command` only checks that the title names the drawing.
- **unresolved:** whether UNDO Mark / Back inside the Block Editor goes back only to the mark.
