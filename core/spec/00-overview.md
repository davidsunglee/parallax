# Core Specification — Overview

This is the **language-neutral core specification** for a bitemporal
object-relational mapping framework. It locks down the common feature set every
language implementation must satisfy, while deliberately leaving the
developer-facing surface (API shape, configuration ergonomics, codegen vs.
metaprogramming) to a separate **per-language spec** authored before each
implementation.

The spec is paired with a **compatibility suite** (`core/compatibility/`) — the
primary behavioral surface. Handed the core spec, a language spec, and this
suite, an agent can build an implementation and prove parity by running the
suite against real databases.

## How to read this spec

The spec is a set of **capability modules** (`M0`–`M13` plus cross-process
coherence). Each module is one file defining its protocol surface, its
observable behavior, and the compatibility cases that pin it down. Modules
depend on one another only in the directions permitted by the **normative
module-dependency graph** ([`dependency-graph.md`](dependency-graph.md)).

| Module | File | Title |
|---|---|---|
| M0 | [`m0-core-conventions.md`](m0-core-conventions.md) | Core conventions — neutral types, timezone, infinity |
| M1 | [`m1-metamodel.md`](m1-metamodel.md) | Domain model & metamodel |
| M2 | [`m2-operation-algebra.md`](m2-operation-algebra.md) | Query, operation & aggregation algebra |
| M3 | [`m3-sql-contract.md`](m3-sql-contract.md) | SQL generation & equivalence contract |
| M11 | [`m11-dialect-seam.md`](m11-dialect-seam.md) | Database seam & portability |
| M12 | [`m12-compatibility-harness.md`](m12-compatibility-harness.md) | Compatibility harness & test-double integration |

Modules `M4`, `M5`, `M7`, `M8`, `M9`, `M10`, `M13`, and cross-process coherence
are introduced in later authoring phases; the dependency graph already names
them so the layering is fixed from the start.

## Normative vs. non-normative boundary (DQ3)

This spec separates **what an implementation must do** from **how it might do
it**. The distinction is load-bearing: it is what allows each language an
idiomatic developer experience while still guaranteeing parity.

**Normative** (an implementation MUST conform):

- **Observable behavior** — query results, the SQL emitted (per dialect, after
  normalization), deep-fetch round-trip counts, temporal semantics, transaction
  / identity-cache / optimistic-lock rules.
- **Protocol seams** — the metamodel (introspection **and** serde), the
  operation algebra (**and** its serde), the canonical model-descriptor schema,
  and the database-dialect interface.
- **The module-dependency graph** — the *direction* of allowed dependencies
  between modules (not the internal class layout within a module).

**Non-normative** (guidance only; a language MAY diverge):

- Internal class/package decomposition *within* a module. A "portal", a
  "manager", or any specific class need not exist.
- The developer-facing API surface, configuration ergonomics, and whether the
  implementation uses codegen, dynamic proxies, or metaprogramming.
- The suggested reference architecture mirroring Reladomo's decomposition.

## Requirement levels (RFC 2119)

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this
specification are to be interpreted as described in
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) — that is, the key words have
their RFC meaning **only** when in ALL CAPS. The same words in lower case carry
their ordinary English meaning and impose no requirement.

## How to read a compatibility case

A compatibility case is a YAML file under `core/compatibility/cases/`. It binds
a model descriptor, a canonical **operation** (an instance of the M2 algebra),
and the expected outcome. It carries **three independent things** the harness
cross-checks against a freshly-provisioned real database:

- **`goldenSql`** — the *optimized* SQL an implementation is **expected to
  emit** for the operation. This is the normative SQL contract a real ORM is
  graded against, and it is **keyed by dialect** (`postgres:`, with more behind
  the M11 seam over time).
- **`expectedRows`** — the result the query must return, authored against the
  small fixture dataset.
- **`referenceSql`** — a deliberately *naive, obviously-correct* second
  formulation of the same query, written so it is unlikely to share a bug with
  `goldenSql`. It is an **independent oracle**. It is **REQUIRED for non-trivial
  cases** (joins, deep fetch, aggregation, temporal predicates) and **OPTIONAL
  for trivial single-table predicate cases** where `expectedRows` is obviously
  verifiable by eye.

The harness asserts, per case:
`rows(goldenSql[dialect]) == rows(referenceSql) == expectedRows`,
that the golden SQL is already in canonical normalized form, and that both the
operation and the model descriptor survive a serde round-trip. See
[`m12-compatibility-harness.md`](m12-compatibility-harness.md) for the full
contract and the case-envelope schema.

> **Self-consistency proves correctness, not quality.** The harness can prove a
> case is internally consistent and that its golden SQL returns the right rows.
> Whether the golden SQL *reads* as idiomatic, well-optimized SQL is a
> human-judgment spot check, reserved for manual review.
