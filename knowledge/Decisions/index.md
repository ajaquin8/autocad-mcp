# Decisions

- [[Decisions/Python COM server foundation]]: **adopted 2026-10-29.** Build our own Python COM server modelled on inventor-mcp instead of adopting an existing AutoCAD MCP. Alex chose to scaffold it.
- [[Decisions/Edit guard and document safety]]: **adopted 2026-10-29** (Claude design carried over from inventor-mcp, in code). Only drawings the server created can be edited, unless Alex asks otherwise.
- [[Decisions/Live test protocol]]: **adopted 2026-10-29**, carried over from inventor-mcp's user-directed rule. Every live batch is announced first and runs only after Alex saves open work and says go.
- [[Decisions/Distribution and install]]: **adopted 2026-11-03** (Alex chose MIT, a public repository and no PyPI for now). AutoCAD users install with uv: a one-click `.mcpb` bundle for the Claude desktop app, or `uvx` from the GitHub ZIP for Claude Code. Not public yet.

Use [[Templates/Decision note]] for future decisions.
