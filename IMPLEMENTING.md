# Implementing Parallax

Use this guide to find the contract owners for a change. It is not a second
specification or a required reading sequence for every task.

## Changing an existing implementation

1. Identify the affected public surface or internal module. Read its binding
   page and owning core contract only as needed.
2. For a portable behavior change, update the owning core rule and relevant
   schemas and conformance expectations. Keep independent expected results;
   never derive an oracle from the implementation being graded.
3. For a language-specific public change, update the relevant binding contract
   only where types and executable examples do not express the decision.
4. For an internal change, update code and appropriate tests. No specification
   or ADR is required unless an actual contract or enforced boundary changes.
5. Verify using [TESTING.md](TESTING.md).

Keep the core graph and language source/artifact topology enforcement intact.
Dependency changes follow [modules.md](core/spec/modules.md) and the target's
declared topology; changes to the enforcement mechanism require design review.

## Adding a language target

Select a lifecycle-complete claim from [slices.md](core/spec/slices.md).
Start a binding entrypoint at `languages/<target>/spec/<target>.md` using
[the template](core/spec/language-spec-template.md). Reference the canonical
claim instead of copying its envelope. Record unresolved public decisions before
implementing the affected surface; unrelated decisions need not block progress.

Read the [core overview](core/spec/00-overview.md), the
[module graph](core/spec/modules.md), and the
[conformance-adapter contract](core/spec/m-conformance-adapter.md). Implement
prerequisites in graph order, using the selected lifecycle. The reference
harness and sibling language implementations are not implementation design inputs.

A useful first vertical slice parses a corpus descriptor and query, compiles
SQL, executes it through the shipped adapter, and compares the observations.
Then expand by intersecting the canonical slice's tags and capability tags.
Filename prefixes are navigation aids, not capability selection.

Maintain the template's required source and deployable topology declarations
and enforce them against the implementation. Package manifests, tool
configuration, and the command graph own their executable settings.

## Proof and user documentation

The compatibility adapter proves the portable claim. The
[API Conformance Suite](core/spec/m-api-conformance.md) proves that developers
can reach that behavior through the public API; its coverage partition and
query drift checks remain required.

Generate the usage guide from a curated set of executed examples. A guide
teaches common operations; it need not publish every case or repeat the core
specification. Keep the full conformance suite regardless of guide selection.

The [language testing contract](core/spec/language-testing.md) owns test
organization and command composition. Each target's `TESTING.md` explains its
test placement and fixtures. Resolve the actual verification graph through
`just show-gates <command>`.

## Decisions and records

A consequential new contract may need an ADR explaining its rationale and
alternatives. Ordinary refactors do not. Once a decision is incorporated into
its contract owner, the ADR is historical evidence rather than another document
to keep synchronized. Research and task records have the same non-normative role.
