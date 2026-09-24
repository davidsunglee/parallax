# Language Target Instructions

- Start with the target's binding entrypoint at `spec/<language>.md`, then read only the core contracts relevant to the change. `IMPLEMENTING.md` describes adding a target and changing its claim.
- Binding documents record language-specific public decisions, not a second account of core semantics or private implementation structure. Preserve the required source and artifact topology declarations and their independent enforcement.
- Core specs, schemas, compatibility cases, and the conformance-adapter contract are the portable inputs. Reference-harness internals and sibling implementations are non-normative and must not be used as implementation design input.
- Do not alter an oracle to accommodate an implementation defect. Change the affected portable contract and executable evidence together only when intended behavior changes.
- Use compatibility cases for portable behavior and unit tests for internal seams, diagnostics, and failure modes.
- Read the target's `TESTING.md` before changing tests. Follow root verification policy and report any database-backed checks that could not run.
