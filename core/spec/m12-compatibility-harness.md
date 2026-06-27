# M12 — Compatibility Harness & Test-Double Integration

`M12` is the **compatibility-case contract** and the no-mock, real-database
harness that proves it. It is **tooling, not an ORM**: it **never compiles
operations to SQL** — that is exactly what a real implementation must do and
prove against the golden SQL. The harness only proves the *suite itself* is
internally consistent and that the golden SQL is correct for the data, across
every database behind the provider seam. `M12` depends on `M2`, `M3`, and (in
later phases) `M4`, `M7`, `M9`, `M10`.

The canonical reference implementation is `reference-harness/` (Python + uv +
sqlglot). Its *contract* is language-neutral; another ecosystem can re-implement
the runner.

## The compatibility case

A case is a YAML document under `core/compatibility/cases/`, validated against
[`core/schemas/compatibility-case.schema.json`](../schemas/compatibility-case.schema.json).
Its fields:

| Field | Required | Meaning |
|---|---|---|
| `model` | yes | path (relative to `core/compatibility/`) to the model descriptor |
| `tags` | yes | module/feature tags (e.g. `["m2", "eq"]`); drive coverage + test selection |
| `operation` | yes | a canonical M2 algebra node, validated against the operation schema |
| `equivalentEncodings` | no | alternate surface encodings of `operation` (e.g. a prefix vs a fluent spelling); each MUST canonicalize to `operation` |
| `goldenSql` | yes | **keyed by dialect** (`postgres: …`); the optimized SQL an impl must emit — a single statement, or an **ordered list** of statements (one per deep-fetch level) |
| `binds` | no | bind values for the `?` placeholders (default `[]`): a flat list for a single statement, or a list-of-lists for a multi-statement case |
| `referenceSql` | conditional | an independent naive oracle (see below); for a deep fetch it is the naive single-statement oracle for the **root** row set |
| `expectedRows` | conditional | the rows the query must return (single-statement / flat-result cases) |
| `expectedGraph` | conditional | the assembled object graph a deep fetch must produce (one of `expectedRows` / `expectedGraph` is REQUIRED) |
| `roundTrips` | no | declared statement count (default `1`); for a multi-statement case it MUST equal the goldenSql statement count and is asserted |
| `tolerance` | no | absolute numeric comparison tolerance; omit for exact comparison (the default). Declare ONLY for inherently inexact results (stddev/variance, repeating-decimal avg) |

### goldenSql, referenceSql, expectedRows (the oracle question)

Each case carries **three independent things**, and the harness cross-checks all
three:

- **`goldenSql`** — the *optimized* SQL an implementation is **expected to
  emit**. This is the normative, per-dialect SQL contract a real ORM is graded
  against.
- **`expectedRows`** — the result the query must return, authored against the
  small fixture dataset.
- **`referenceSql`** — a deliberately *naive, obviously-correct* second
  formulation of the same query (e.g. a plain `IN (subquery)` instead of an
  optimized `EXISTS` join). An **independent oracle**.

Why the oracle matters: if a human hand-authors `goldenSql` and `expectedRows`,
both can be wrong *in the same way*, and a harness that only runs `goldenSql` and
compares to `expectedRows` would still pass — self-consistent but incorrect. The
independent `referenceSql`, written naively, is unlikely to share the bug; if
both return identical rows against real data, we have high confidence the golden
SQL is correct. (This is Reladomo's own `validateMithraResult(op, rawSql)`
discipline, made portable.)

**Policy.** `referenceSql` is **REQUIRED for non-trivial cases** (joins, deep
fetch, aggregation, temporal predicates) and **OPTIONAL for trivial single-table
predicate cases** where `expectedRows` is obviously verifiable by eye.

## The layered assertion model

Per case, against a freshly-provisioned database selected via the provider seam,
the harness asserts:

1. **Schema conformance** — the model descriptor validates against the metamodel
   schema; the `operation` against the operation schema; the case against the
   compatibility-case schema.
2. **Triple equivalence** — load the database from the descriptor + fixture data,
   then assert `exec(goldenSql[dialect]) == exec(referenceSql) == expectedRows`
   (the `referenceSql` term is included only when present). Row comparison is
   order-insensitive, and **numerics compare exactly in decimal space** (never
   through binary `float`), so a `decimal(p,s)` money column matches to the cent
   and a value's type never depends on whether it is whole. A case whose result
   is inherently inexact (stddev/variance, a repeating-decimal avg) — and so
   cannot be authored exactly and differs in scale across dialects — MAY declare
   a `tolerance`, making the numeric comparison `abs(actual - expected) <=
   tolerance`. Booleans compare only to booleans (`true` is never `1`).
3. **Normalization determinism** — `normalize(goldenSql[dialect]) ==
   goldenSql[dialect]` via sqlglot, per the M3 rules (alias scheme `t0,t1,…`,
   sorted binds, whitespace-collapsed, deterministic clause order).
4. **Serde round-trip** — `serialize(deserialize(x)) == x` for **both** the
   `operation` encoding *and* the model descriptor (the descriptor **is** the
   serialized metamodel), in **both** JSON and YAML. When a case declares
   `equivalentEncodings`, each alternate encoding MUST canonicalize (via the same
   serde seam) to the case's `operation` — a dialect-agnostic check that proves
   precedence / serialization fidelity (a prefix and a fluent surface of the same
   grouped predicate denote one canonical node) in the fixture itself.

A fifth layer — **round-trip-count consistency** — applies to relationship /
deep-fetch cases: the number of golden SQL statements equals the declared
`roundTrips`, each level executes (a deep-fetch child level keyed by the distinct
parent keys gathered from the previous level), and the in-memory-assembled object
graph equals the case's `expectedGraph`. This is what proves N+1 elimination
automatically (a 1 → N → N deep fetch must run in exactly 3 statements, not
1 + N + N). For these cases a dialect's `goldenSql` is an **ordered list** of
statements (one per level) rather than a single string, and `expectedGraph`
replaces (or accompanies) `expectedRows`.

## Provisioning ↔ runner seam (DQ15)

The harness splits into two clearly-separated sub-parts joined by an explicit
seam so provisioning can be swapped without touching the assertion layer:

- **Provisioning — the `DatabaseProvider` seam.** Each provider yields a clean,
  migrated, isolated database for a single dialect, exposing `reset`,
  `apply_ddl`, `load`, `exec`, and a `dialect` identifier. **Testcontainers** is
  the default mechanism, pinned at the latest stable Postgres major; a language
  **MAY** substitute an embedded binary that satisfies the same reset/isolation
  contract.
- **Runner + assertions.** The case runner applies the four (later five) layers
  above against whatever provider it is handed.

This seam is also the **database-provider seam** that grows the matrix: adding a
dialect is a new provider behind the same protocol, and the
**compatibility-matrix report** (implementations × databases) is produced by
running the suite across every available provider.

## Test-double integration

Per DQ8, most tests **SHOULD** live at this compatibility-suite level — the suite
is the primary behavioral surface across all languages — rather than buried in
per-language unit tests. Each per-language spec specifies how its test runner
(pytest / JUnit / `cargo test`) wires to the database provider.
