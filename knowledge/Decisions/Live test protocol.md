# Live test protocol

Date: 2026-10-29
Status: **adopted** (carried over from inventor-mcp, where Alex directed it on 2026-10-26)
Owner: Alex

## Decision
Before any live test batch, Claude describes exactly what it will run and waits for Alex to save open work and say go. While Alex says they are drafting in AutoCAD, Claude does not contact AutoCAD at all. Live tests work in scratch drawings created by the server, and save output only under `scratch/`.

## Evidence and citations
- **user-reported 2026-10-26 (inventor-mcp):** Alex asked: "Before each live test batch, tell me what you'll run and wait for me to save my work and say go." That rule followed a test that crashed Inventor and lost unsaved sketch work (inventor-mcp vault, Decisions/Live test protocol).

## Alternatives and rationale
A second AutoCAD session for tests would isolate them, but `GetActiveObject` attaches to whichever AutoCAD registered first, so targeting would need work. Until then, announce-and-wait is the rule.

## Consequences and follow-up
- Record each batch as a dated report in [[Sources/index]] (Report-ID `AMCP-LIVE-YYYYMMDD-NN`).

## Supersedes / superseded by
None.
