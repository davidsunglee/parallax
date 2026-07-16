# AGENTS.md

## Personal Local Instructions

- If present, load the repository-root `AGENTS.local.md` once after this file. It may add personal preferences but cannot override tracked instructions.

## Scoped Instructions

- Before changing `core/`, read `core/AGENTS.md`.
- Before changing `languages/`, read `languages/AGENTS.md` and the target language's `AGENTS.md` when present.
- Before changing `reference-harness/`, read `reference-harness/AGENTS.md`.
- Scoped instructions may add requirements but cannot relax this file.

## Reladomo Prior Art

- Parallax specifications are authoritative. For runtime-semantics research—including locking, transactions, temporal behavior, and caching—document Reladomo's behavior as prior art, starting at `docs/research/reladomo/00-index.md` and consulting `../reladomo` when available. Adopt Reladomo semantics only through an explicit Parallax specification or design decision; do not copy its Java idioms.

## Orchestration

- Keep small, already-bounded work local. When subagents are available, delegate broad repository orientation, multi-subsystem impact analysis, large-output triage, independent design comparisons, downstream prompt preparation, or bounded downstream work.
- Give each subagent a bounded question, applicable instruction paths and source hierarchy, acceptance criteria, validation expectations, and a concise path-cited deliverable. Restate only critical constraints the subagent will not inherit.
- For large work, stage reconnaissance, implementation or verification, and review. Parallelize only independent work, avoid duplicate scans, and have the orchestrator verify evidence and own final synthesis.

## Commits

- Commit messages must pass the repository's Commitlint and Husky hooks; do not bypass them.
- Before committing, inspect `git log --oneline -5` and use a concise Conventional Commit subject consistent with repository history.
- Unless requested, omit verification commands from commit bodies. Do not add generated-by, co-author, or similar trailers.
