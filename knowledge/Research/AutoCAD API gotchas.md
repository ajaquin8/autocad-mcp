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
