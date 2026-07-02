# AGENTS.md

Standing instructions for agents working inside `languages/typescript/`. Each
`languages/<lang>/` folder ships its own `AGENTS.md`; this is the TypeScript one.

## TypeScript Implementation Work

- The reference harness's internals are non-normative and MUST NOT be used as design input for a language implementation; the binding inputs are the spec modules, `core/schemas/`, the compatibility corpus, and the conformance-adapter contract.
- Read the language spec `languages/typescript/spec/01-implementation-spec.md` alongside the core reading order in the root `AGENTS.md` and `IMPLEMENTING.md` before writing runtime code, and follow `languages/typescript/IMPLEMENTING.md` for the operational path.
- The compatibility corpus is the primary behavioral surface: verify against `core/compatibility` cases first, and add TypeScript unit tests only for internal seams, diagnostics, and failure modes.
- Surface conformance through the `parallax-conformance` adapter defined by `core/spec/conformance-adapter-contract.md`; do not invent a different language-specific conformance surface.
- Do not change `core/spec`, `core/schemas`, or `core/compatibility` only to make the TypeScript implementation pass; any change to them must update the spec, schema, fixtures, and cases consistently.
