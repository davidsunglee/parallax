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
| `goldenSql` | yes | **keyed by dialect** (`postgres: …`); the optimized SQL an impl must emit |
| `binds` | no | ordered bind values for the `?` placeholders (default `[]`) |
| `referenceSql` | conditional | an independent naive oracle (see below) |
| `expectedRows` | yes | the rows the query must return, against the fixture data |
| `roundTrips` | no | declared statement count (default `1`); enforced from a later phase |

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
   (the `referenceSql` term is included only when present).
3. **Normalization determinism** — `normalize(goldenSql[dialect]) ==
   goldenSql[dialect]` via sqlglot, per the M3 rules (alias scheme `t0,t1,…`,
   sorted binds, whitespace-collapsed, deterministic clause order).
4. **Serde round-trip** — `serialize(deserialize(x)) == x` for **both** the
   `operation` encoding *and* the model descriptor (the descriptor **is** the
   serialized metamodel), in **both** JSON and YAML.

A later phase adds a fifth layer — **round-trip-count consistency** — for
relationship / deep-fetch / scenario cases (statement count equals the declared
`roundTrips`, and the assembled object graph equals the expected graph).

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
