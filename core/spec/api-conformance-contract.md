# API Conformance Suite Contract

The **API Conformance Suite** proves that a language implementation's idiomatic
developer surface reproduces the compatibility corpus. It is the developer-surface
sibling of the conformance adapter: the
[conformance adapter](conformance-adapter-contract.md) grades wire-level
conformance through a narrow CLI envelope, while the suite proves that the *code an
application developer actually writes* — run through the shipped adapter against a
real database — produces the corpus's results.

"API" here means the public developer surface a language spec pins down in its
**API surface** section: the finders, predicates, transaction blocks, and result
types a developer programs against. It is **not** the adapter's CLI envelope. The
adapter's `describe` / `compile` / `run` commands are a conformance transport, not
an API a developer uses; the suite tests the latter.

The suite is **additive proof that sits beside the adapter grade — never a
substitute for it, and it never touches the grader**. The official conformance
grade stays contract-driven over the conformance adapter, comparing wire values to
the corpus oracles. The suite exists because a wire grade deliberately ignores
developer-facing guarantees — that a returned row is a managed object, that the
idiomatic query canonicalizes to the corpus operation — and those guarantees need
their own proof.

## Two proof paths

| | Conformance adapter grade | API Conformance Suite |
| --- | --- | --- |
| Subject under test | the CLI envelope (`describe` / `compile` / `run`) | the idiomatic public developer API |
| Execution surface | corpus `operation` YAML, compiled and run through the adapter | the developer DSL, run through the shipped adapter |
| Compared against | the corpus oracles at wire level | the corpus oracles, plus developer-surface guarantees |
| Golden SQL text | compared (compile lane) | out of scope |
| Role | the official conformance grade | additive proof beside the grade |

The two paths share the corpus, the compilers, and the comparison rules; they
differ in what they exercise and what they additionally check. The suite does not
weaken or replace the grade — an implementation that passes the suite but fails the
adapter grade is not conformant.

## Required properties

A language implementation that claims a Conformance Slice MUST ship an API
Conformance Suite with all of the following properties. They are stated as
portable requirements; the mechanism that satisfies each is language-local.

1. **Idiomatic public API only.** The suite MUST exercise the same public surface
   an application developer uses — the finders, predicate builders, transaction
   blocks, and write operations described in the language spec's API surface
   section. It MUST NOT reach into internal compilers, runtime seams, or the
   conformance adapter's CLI.
2. **Shipped adapter, real database.** The suite MUST run through the shipped
   database adapter against a real database of a claimed dialect (not a mock, an
   in-memory fake, or the conformance grader's provisioning path used as a
   shortcut around the developer surface).
3. **Coverage partition over the claimed slice.** The suite MUST mechanically
   assert that the cases it exercises and the cases it explicitly skips partition
   the claimed slice exactly: exercised ∪ skipped equals the slice, the two sets
   are disjoint, no exercised or skipped id is stale (every id is a real in-slice
   case), and every skip records a non-empty reason. A silent gap — an in-slice
   case that is neither exercised nor reasoned-skipped — MUST fail the build.
4. **Expected results match the corpus oracles.** For every exercised case the
   suite MUST assert the developer surface produces the corpus's expected results
   (`expectedRows`, `expectedGraph`, `expectedTableState`, `expectedAffectedRows`,
   round-trip counts, and identity/cache expectations as applicable), using the
   same comparison rules the conformance grade uses.
5. **No-drift guard.** For cases whose behavior is a query, the suite MUST assert
   that the operation the idiomatic API builds canonically equals the corpus
   operation for that case. This ties the developer-facing snippet to the graded
   behavior: a snippet that stops matching its case fails the build rather than
   silently drifting into a different query that happens to return the same rows.
6. **Golden SQL text is out of scope.** The suite MUST NOT assert emitted SQL
   text. SQL text is not a developer-facing surface; it is graded in the adapter's
   compile lane. The suite proves developer-observable behavior and shape.

## Optional properties

- The suite SHOULD assert language-specific **value shapes** the wire grade
  deliberately ignores — for example that a returned scalar is its managed carrier
  type (a big integer, a decimal, a temporal instant) rather than a bare wire
  value, and that no physical column name leaks through the managed object. What
  counts as a managed shape is language-local, so this is a SHOULD/MAY rather than
  a portable MUST.

## Usage Guide

A language implementation MUST also ship a **Usage Guide**: a rendered document
that demonstrates idiomatic usage of the developer surface. The Usage Guide is the
genuinely demonstrative artifact — human-readable prose and examples — and it MUST
be generated from the API Conformance Suite's own source, with a CI drift check
that fails when the rendered guide falls out of lockstep with the suite. This keeps
the documented examples identical to executed, passing tests: prose and proof
cannot diverge. The rendering and drift-check mechanism is language-local; core
requires only the property.

## Worked example

The TypeScript implementation is the worked example of this contract, not a
mandate on other languages:

- the suite lives at
  `languages/typescript/packages/typescript/test/api-conformance/`, running the
  idiomatic `px.*` / `px.transaction` surface over the shipped `@parallax/db-postgres`
  adapter against a Testcontainers `postgres:17`;
- `coverage.test.ts` is the Docker-free partition assertion (exercised ∪ skipped ==
  the 101-case `slice-mvp-1` slice, no strays, every skip reasoned), with the
  exercised map in `covered.ts` and the reasoned skips in `skip-manifest.ts`;
- the no-drift guard is `assertSameOperation` in `_harness.ts`;
- the value-shape assertion is `assertManagedShape` in `_harness.ts`;
- the Usage Guide is `languages/typescript/docs/guide/*.md`, rendered from the
  suite source by `scripts/render-guide.mjs` and re-checked in CI with
  `render-guide.mjs --check`.

Nothing above mandates the TypeScript mechanism. Another language satisfies this
contract with its own test framework, its own partition assertion, and its own
guide renderer, as long as the required properties hold.
