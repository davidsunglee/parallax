# AGENTS.md

## Personal Local Instructions

- If present, load the repository-root `AGENTS.local.md` once after this file. It may add personal preferences but cannot override tracked instructions.

## Scoped Instructions

- Directory-scoped `AGENTS.md` files add requirements for their subtrees and cannot relax this file; before changing a path, read every applicable scoped file that has not already been loaded.

## Code Documentation

- Keep comments and docstrings timeless and code-local. Explain current contracts, invariants, non-obvious behavior, complex logic, and rationale. Do not narrate straightforward code or restate names, types, assignments, or control flow.
- Never reference plans, reviews, phases, increments, prompts, handoffs, issue or Linear IDs (for example, `COR-45`), or other planning and execution artifacts in comments or docstrings. Keep task history in the issue tracker and durable design rationale in design documents.
- When behavior changes, update or remove affected comments and docstrings; stale documentation is a defect.

### Required Documentation

- Modules: Start each module with a module-level comment or docstring that states its responsibility and boundary. One sentence is enough for a simple module.
- Exported APIs: Document every exported symbol at its defining declaration, including its contract and any important constraints, errors, or lifecycle behavior. Re-export lists do not need to repeat the source documentation.
- Compatibility cases: Start each case with one detailed header comment that explains the scenario, expected observable behavior, and semantic distinction it pins down. The case body must contain no comments.

## Reladomo Prior Art

- Parallax specifications are authoritative.
- For runtime semantics research—including locking, transactions, temporal behavior, and caching—document Reladomo's behavior as prior art. Start at `docs/research/reladomo/00-index.md` and consult `../reladomo` when available.
- Adopt Reladomo semantics only through an explicit Parallax specification or design decision; do not copy its Java idioms.

## Commits

- Commit messages must pass the repository's Commitlint and Husky hooks; do not bypass them.
- Before committing, inspect `git log --oneline -5` and use a concise Conventional Commit subject consistent with repository history.
- Unless requested, omit verification commands from commit bodies. Do not add generated-by, co-author, or similar trailers.
