# Shared wiki protocol

Read this file before editing. Applies to humans and assistants in every app mode.

## Evidence and sources
- **verified**: directly supported by an inspected source or reproducible test. Name exactly what was verified, when, and within what limits.
- **user-reported**: stated by the user; preserve attribution and date without presenting it as independently tested.
- **inferred**: reasoned from cited evidence; state assumptions and alternatives.
- **unresolved**: missing, conflicting, or untested evidence; record the next useful check.

Give substantive claims a source link or original local path, title, source date if known, access/test date, and page/section or test method. Use YYYY-MM-DD dates. Unknown dates stay unknown. Separate source publication dates from access dates. Assistant summaries are not primary evidence.

## Preservation and corrections
Keep original source files where they are. Never move, overwrite, or alter project sources during ingestion. Copy only explicitly selected, authorized material into Sources when useful; otherwise record a reference. Do not bulk-import documents, private chats, session stores, or assistant internal notes. Do not store secrets, credentials, or customer data by default. Obtain specific authorization and minimize sensitive content if an exception is necessary.

Preserve the history of meaningful findings: label obsolete claims **superseded**, date the correction, explain why, and link the replacement. Do not silently erase conflicting evidence. Keep decisions distinct from hypotheses.

## One writer at a time
Before editing, agree which human or assistant owns the editing session. Other apps may read but must wait to write. Never assume a note is an atomic lock. Read current files before changing them and stop if another writer has changed them unexpectedly. Close the session by validating links, appending the change log, and releasing ownership explicitly.

## Session finish
Update relevant project, research, and decision notes. Record evidence labels and open questions; add source references. Append a dated entry to [[Change log]] describing files changed, sources used, validation, and remaining uncertainties. Never rewrite existing log entries; correct them with a new entry. This convention is append-only, not a filesystem enforcement mechanism.

AGENTS.md and CLAUDE.md point here, but not every app mode auto-loads them. In every new session explicitly ask the assistant to read wiki-protocol.md before editing. No plugin is required. Local storage is not an off-device backup or cloud sync.
## REA research save-back workflow — added 2026-10-19
These are workflow instructions, not enforcement or automatic transcript sync. They apply only to an already authorized, narrowly scoped research pass. They grant no authority to analyze arbitrary binaries, execute software, query live databases, or write beyond this vault. Preserve source programs and existing app settings.

### Start
Read this protocol, Home/index, Sources/index, the relevant topic/project pages and their cited reports before research. State the question, exact authorized targets, allowed method and stop conditions. Identify existing source/report IDs and unresolved or disproven hypotheses. Confirm sole writing ownership before any write. Do not assume an app auto-loads AGENTS.md or CLAUDE.md.

### Save a dated scoped source report
Every authorized pass, including a negative or inconclusive one, ends with a report under Sources containing:
- Stable Source-ID, distinct Report-ID, date/time and timezone, writer, and narrow question.
- Authorized targets/actions; tool/method and tool version if known; file/product version.
- Original source locations and relevant symbols, sections, pages or tool-call references.
- Observed facts separately from interpretations; evidence labels and precise citations.
- Unresolved or disproven hypotheses, contradictory evidence and the limits of negative results.
- What was not inspected/tested, failures and scope limits; the next useful question.

Record unknown versions or details as unknown. Do not store secrets, raw customer records, private transcripts or assistant internal notes. Report only selected, permitted evidence.

Use stable Source-IDs based on existing citation/message identifiers, commits, or exact artifact identity plus version (hash only if authorized and available). Keep the same ID across ingestions. Give each actual pass a distinct dated Report-ID, such as REA-20261019-topic-01. Search Sources/index and reports before creation; reuse the existing report for the same pass instead of duplicating it. Corrections and new passes receive new Report-IDs linking their predecessors.

### Integrate and preserve
Preserve source reports after ingestion. Update existing synthesis/topic pages and relevant project/index pages; register IDs and report links in Sources/index. Date and cite unresolved, disproven or superseded hypotheses, including the scope of the disproof. Never silently replace earlier findings or erase conflicting evidence. A research-task template may be used as an optional scaffold.

### One writer; missing access
Only one writer edits the vault at a time, including drafts. If another assistant is editing, retain proposed findings in the response labeled **not saved** until ownership transfers. After handoff, a staging draft may hold findings while synthesis awaits review. Never overwrite another task's draft. This note is not an atomic lock or permission for concurrent writing; no lock daemon is needed.

If access is absent, a write fails, or read-back cannot confirm it, say **not saved** and identify any partially saved paths. An intended tool call, chat response, config entry or another executor's access is not proof of persistence.

### Validate and finish
Read back each saved report and changed page, check evidence labels and IDs, and resolve added internal links. Append a concise dated Change log entry with the question/report ID, paths, outcome, validation and uncertainty; read back that entry too. Return a receipt listing saved paths, read-back/link results, unsaved findings and pending draft integration. Say "none" only when nothing remains unsaved. Release writing ownership. Do not mark another app's read/write connection verified from this executor's access.