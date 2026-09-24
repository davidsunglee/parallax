# AGENTS.md

## Personal Local Instructions

- If present, load the repository-root `AGENTS.local.md` once after this file. It may add personal preferences but cannot override tracked instructions.

## Scoped Instructions

- Directory-scoped `AGENTS.md` files add requirements for their subtrees and cannot relax this file; before changing a path, read every applicable scoped file that has not already been loaded.

## Code Documentation

- Prefer clear names, types, and structure over comments.
- Document declarations intentionally exported from their defining module only when their signatures and types do not fully express their contracts; re-export lists do not need to repeat the source documentation.
- Otherwise, document only constraints or rationale that are critical and cannot be expressed in code.
- Keep comments and docstrings timeless and code-local. Never narrate straightforward code. Never reference planning or execution artifacts like issues, plans, or reviews.
- Update or remove affected comments and docstrings when behavior changes; stale documentation is a defect.
- Compatibility cases need no header commentary. Use descriptive names and executable inputs and expectations; add a short local explanation only for a distinction they cannot make clear.

## Contract Ownership

- Read instructions and contracts relevant to the change. Use `README.md`, `IMPLEMENTING.md`, and the language binding entrypoint as navigation; do not load every specification before an internal change.
- Portable semantics belong to their owning `core/spec` module, serialized structure to schemas, and concrete expected observations to compatibility cases. Resolve disagreements explicitly rather than changing an oracle to match production.
- Language bindings inherit core semantics and own additional public language decisions that signatures, types, and executable examples cannot express. Private structure belongs to code; package metadata, quality thresholds, and commands belong to executable configuration.
- Dependency declarations are an intentional exception to single authorship: preserve the core graph, language topology declarations, and independent implementation mappings and checks. Changes to this enforcement mechanism require explicit design review.
- Otherwise, author a fact once. Link to its owner or generate another view; do not maintain prose inventories of code, cases, or CI jobs. An internal refactor normally needs no specification edit.
- `CONTEXT.md` files are terminology/navigation aids. ADRs record decisions and rationale at the time they were made; supersede them when a decision changes rather than keeping historical prose synchronized. Research, measurements, and task artifacts are evidence, not additional current product contracts.

## Review

- Judge behavior against its current contract owner and changes against these instructions. A finding must identify observable harm or a material contract violation with a credible trigger and evidence.
- Missing repetition in a secondary document is not a defect. When duplicated prose conflicts, prefer removing the duplicate or linking to its owner; preserve any unique public contract before deleting it.
- Generated documentation is reviewed through its authored inputs and generation checks. Tests verify exports, types, behavior, and enforced boundaries, not explanatory prose that repeats them.
- Keep private task records out of product documentation. A bounded change needs no separate design document; a large change needs only a short execution outline unless an unresolved product decision requires design work.

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
