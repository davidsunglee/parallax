# AGENTS.md

## Personal Local Instructions

- If present, load the repository-root `AGENTS.local.md` once after this file. It may add personal preferences but cannot override tracked instructions.

## Scoped Instructions

- Directory-scoped `AGENTS.md` files add requirements for their subtrees and cannot relax this file; before changing a path, read every applicable scoped file that has not already been loaded.

## Code Documentation

- Prefer clear names, types, and structure over comments.
- Document declarations intentionally exported from their defining module, focusing on contracts; re-export lists do not need to repeat the source documentation.
- Otherwise, document only non-obvious behavior, constraints, or rationale.
- Keep comments and docstrings timeless and code-local. Never narrate straightforward code. Never reference planning or execution artifacts like issues, plans, or reviews.
- Update or remove affected comments and docstrings when behavior changes; stale documentation is a defect.
- Compatibility cases: start each case with one detailed header comment that explains the scenario, expected observable behavior, and semantic distinction it pins down. The case body must contain no comments.

## Reladomo Prior Art

- Parallax specifications are authoritative.
- For runtime semantics research—including locking, transactions, temporal behavior, and caching—document Reladomo's behavior as prior art. Start at `docs/research/reladomo/00-index.md` and consult `../reladomo` when available.
- Adopt Reladomo semantics only through an explicit Parallax specification or design decision; do not copy its Java idioms.

## Verification

- Resolve what an aggregate command already runs before listing or running verification — `just show-gates <command>` prints its execution owners — and never list a focused command beside an aggregate that contains it.
- Invoke an authoritative aggregate — `just check` for a merge-ready run — directly rather than piping it through an output filter, and trust the status the execution tool reports.
- `just check` is the merge gate and the only aggregate to run locally. It omits the `cost` class, whose memory measurements CI owns and gates on every change: `just check-all` and `just check-cost` are CI's, not a local step. Report a green `just check` as a green merge gate, never as every blocking check having passed.
- While iterating on what the `cost` class grades — the memory instruments, or a suite reading a whole interpreter — `just python-check-cost` is the one command owning that gate, and running it is focused iteration rather than a completeness run.
- If another agent reports that an exact verification command passed, do not rerun it unless relevant repository state changed afterward.
- [`TESTING.md`](TESTING.md) is the operational map: which command owns which gate, and the workflow from focused iteration with the `<scope>-test-<surface>` selectors to one merge-ready run.

## Commits

- Commit messages must pass the repository's Commitlint and Husky hooks; do not bypass them.
- Before committing, inspect `git log --oneline -5` and use a concise Conventional Commit subject consistent with repository history.
- Unless requested, omit verification commands from commit bodies. Do not add generated-by, co-author, or similar trailers.
