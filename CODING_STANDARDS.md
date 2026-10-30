# Coding Standards

## Design Principles

Hold every change to these principles:

- **Deep modules.** Judge module shape with the `codebase-design` skill: its vocabulary and principles, not its design-it-twice exercise.
- **Canonical data.** Work from the canonical structures the data owner already builds at the right point in the framework lifecycle. When access must be faster, the owner presents a view and manages its lifetime there, rather than a caller building a structure for one piece of work.
- **End-to-end processing.** Each step runs once, close to the data owner, at a point with a coherent reason, across every flow: keyed, target, and predicate writes; eager and streamed reads; Typed and Wire APIs; `Columns` and `Document` Storage Layouts. Optimize the whole flow: a step convenient locally but reversed downstream, such as encoding that a later stage decodes, is duplicate processing.
- **Production-only code.** Tests and conformance reach production through existing seams. When no seam exists and no other approach can test the behavior, escalate to the maintainer to choose between a minimal seam and a different testing approach.
- **Least surprise.** The API surface behaves as its intended user expects, both per operation and as a set whose operations work harmoniously together.

## Review

- Judge behavior against its current contract owner and changes against applicable repository instructions and standards, including [`AGENTS.md`](AGENTS.md) and scoped instruction files for the reviewed paths.
- Missing repetition in a secondary document is not a defect. When duplicated prose conflicts, prefer removing the duplicate or linking to its owner; preserve any unique public contract before deleting it.
- Review generated documentation through its authored inputs and generation checks.
