@AGENTS.md

## Claude Code specifics

- When a session's context fills, update the ticket's handoff doc (`.humanlayer/tasks/<ticket>/*handoff*.md`) with state only — workflow policy lives here and in `AGENTS.md`, so do not restate it in handoffs.
- When dispatching research subagents, always include a Reladomo prior-art angle (see "Prior Art: Reladomo" in `AGENTS.md`) before fanning out.
