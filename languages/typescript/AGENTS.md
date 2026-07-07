# AGENTS.md

Standing instructions for agents working inside `languages/typescript/`. Each
`languages/<lang>/` folder ships its own `AGENTS.md`; this is the TypeScript one.
The root `AGENTS.md` rules (spec/schema/corpus are the source of truth; reference-harness
internals are non-normative) apply here unchanged.

## TypeScript Implementation Work

- Read the language spec `languages/typescript/spec/01-implementation-spec.md` alongside the core reading order in the root `AGENTS.md` and `IMPLEMENTING.md` before writing runtime code, and follow `languages/typescript/IMPLEMENTING.md` for the operational path.
- The compatibility corpus is the primary behavioral surface: verify against `core/compatibility` cases first, and add TypeScript unit tests only for internal seams, diagnostics, and failure modes.
- Surface conformance through the `parallax-conformance` adapter defined by `core/spec/m-conformance-adapter.md`; do not invent a different language-specific conformance surface.
