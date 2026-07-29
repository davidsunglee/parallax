# Reference Harness Instructions

- The reference harness is executable compatibility tooling, not an ORM or a normative design source for language implementations.
- It carries a second responsibility: the repository's own verification-gate tooling — the resolver over the orchestrator's command graph and the commands built on it. That code answers to `core/spec/language-testing.md`; the compatibility corpus is not its subject. Keep it in modules of its own rather than mixing it into corpus tooling.
- Treat the core specs, schemas, compatibility corpus, and conformance-adapter contract as authoritative.
- Follow `reference-harness/README.md#running`; prefer maintained root `just` recipes where available and report skipped Docker-backed checks.
