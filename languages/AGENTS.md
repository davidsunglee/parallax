# Language Target Instructions

- For language-spec work, follow the Spec-Authoring Journey in the root `IMPLEMENTING.md`. Select a canonical Conformance Slice and complete the target language spec before writing runtime code.
- Before runtime work, confirm that the target language spec has no unresolved decisions and follow the Implementation Journey in the root `IMPLEMENTING.md`.
- Binding inputs are the completed target spec, core module specs, schemas, compatibility corpus, and conformance-adapter contract. Reference-harness internals and sibling language implementations are non-normative and must not be inspected or used as design input.
- Keep target operational guides limited to commands, database setup, dependency-respecting milestones, status, and blockers.
- Do not alter core contracts to accommodate an implementation defect. If a core contract is wrong or incomplete, update the affected spec, schema, fixtures, and cases together.
- Implement in the legal dependency order from `core/spec/modules.md`. Use the compatibility corpus as the primary behavioral verification and `core/spec/m-conformance-adapter.md` as the only conformance surface; reserve language unit tests for internal seams, diagnostics, and failure modes.
- Run the narrowest active Conformance Slice and capability-tag intersection, then the applicable root gates named by the target operational guide. Report every skipped database-backed check and why it was skipped.
