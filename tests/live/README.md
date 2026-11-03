# Live tests

Scripts here talk to a running AutoCAD. They are never collected by pytest and run **only after
the person whose AutoCAD it is has agreed** (see `knowledge/Decisions/Live test protocol.md`):
describe the batch, wait for open work to be saved and a "go", then run it. Never run them with
client drawings open. Work only in scratch drawings the server creates; write output under
`scratch/` (ignored by git). Record each run in `knowledge/Sources/`.

`first_drawing.py` is the general smoke batch (window elevation, all draw tools, dimensions,
capture, PDF); `connect_check.py` only reads `acad_status`. The kitchen scripts are larger examples.
