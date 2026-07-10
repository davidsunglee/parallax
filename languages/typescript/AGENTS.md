# AGENTS.md

Standing instructions for agents working inside `languages/typescript/`. Each
`languages/<lang>/` folder ships its own `AGENTS.md`; this is the TypeScript one.
The root `AGENTS.md` rules (spec/schema/corpus are the source of truth; reference-harness
internals are non-normative) apply here unchanged.

## TypeScript Implementation Work

- Follow the two-stage reading order in the root `AGENTS.md` and `IMPLEMENTING.md`. The completed TypeScript language spec at `languages/typescript/spec/01-implementation-spec.md` is the source of TypeScript design decisions; read it before writing runtime code.
- Use `languages/typescript/IMPLEMENTING.md` only for commands, database setup, milestones, current status, and operational blockers. If a language decision changes, update the completed TypeScript spec rather than copying the decision into the operational guide.
- The compatibility corpus is the primary behavioral surface: verify against `core/compatibility` cases first, and add TypeScript unit tests only for internal seams, diagnostics, and failure modes.
- Surface conformance through the `parallax-conformance` adapter defined by `core/spec/m-conformance-adapter.md`; do not invent a different language-specific conformance surface.
