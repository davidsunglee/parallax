# m-conformance-adapter — Conformance Adapter Contract

The conformance adapter is the seam between the language-neutral compatibility
corpus and a concrete language implementation. It gives an external runner a
small interface for asking an implementation what it supports, what SQL it
emits for a case, and what observations it produces when it runs a case.

This contract is adjacent to `m-case-format`: the reference harness proves the
core corpus is internally coherent; a language implementation proves itself by
satisfying this adapter contract against that same corpus.

## Purpose

The adapter exists so a conformance runner can validate a TypeScript, Java,
Python, Rust, or other implementation without knowing that implementation's
internal modules or public developer API.

The adapter MUST NOT expose internal classes, finder builders, cache objects, or
language-specific query surfaces. It accepts compatibility corpus files and
returns JSON observations.

The adapter SHOULD be implemented as a CLI because a CLI is portable across
language ecosystems. A language MAY also expose the same interface as an
in-process test helper, but the CLI is the shared contract.

## Commands

An adapter binary SHOULD be named `parallax-conformance` or exposed through a
language-native wrapper that accepts the same commands.

```text
parallax-conformance describe
parallax-conformance compile --case <case.yaml> --dialect <dialect>
parallax-conformance run --case <case.yaml> --dialect <dialect>
parallax-conformance benchmark --benchmark <benchmark.yaml> --dialect <dialect>
```

Each command writes exactly one JSON document to stdout. That JSON document MUST
validate against
[`core/schemas/conformance-adapter.schema.json`](../schemas/conformance-adapter.schema.json).
Human-readable logs MAY be written to stderr.

### Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Command completed and stdout contains `status: "ok"` |
| `10` | Requested capability is intentionally unsupported and stdout contains `status: "unsupported"` |
| `1` | Command failed and stdout contains `status: "error"` |
| `2` | CLI usage error, such as a missing flag or unreadable file |

The `unsupported` result is only valid when the adapter has not claimed the
requested command, dialect, case shape, module tags, or case-tag selection in
`describe`.

## Common Output Envelope

Every JSON output document has these common fields:

```json
{
  "schemaVersion": "1",
  "command": "compile",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  }
}
```

`status` is one of:

- `ok`: the command completed and command-specific fields are present.
- `unsupported`: the request is outside the adapter's claimed capability set.
- `error`: the adapter attempted the request and failed.

`unsupported` and `error` outputs MUST include at least one diagnostic:

```json
{
  "schemaVersion": "1",
  "command": "compile",
  "status": "unsupported",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "diagnostics": [
    {
      "code": "unsupported-dialect",
      "message": "mariadb is not claimed by this adapter"
    }
  ]
}
```

## `describe`

`describe` reports the adapter's claimed capability set. It does not read cases
or connect to a database.

Example:

```json
{
  "schemaVersion": "1",
  "command": "describe",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "capabilities": {
    "modules": ["m-core", "m-descriptor", "m-op-algebra", "m-sql", "m-dialect", "m-case-format"],
    "dialects": ["postgres"],
    "caseShapes": ["read"],
    "caseTags": {
      "exclude": ["groupBy", "having"]
    },
    "commands": ["describe", "compile", "run"],
    "provisioning": "external-url"
  }
}
```

Capability claims are deliberately **case-tag aware**. `modules`,
`dialects`, and `caseShapes` are broad filters; `caseTags` is an optional
fine-grained filter over the compatibility case's own `tags` array. This lets a
partial implementation honestly claim, for example, `m-op-algebra` predicate reads
while deferring aggregation (`m-agg`) reads, or `m-unit-work` transaction/write
cases while deferring the `m-process-cache` query-cache and identity-cache
scenarios.

Inheritance capability follows this same shape and needs **no**
inheritance-specific adapter surface. An adapter claims it by listing
`m-inheritance` in `modules` and, where a claim defers part of the module, by the
ordinary `caseTags` filter; abstract-target reads, subtype `narrow`, polymorphic
navigation, narrowed deep fetch, and concrete-subtype writes are all ordinary case
commands under the existing `describe` / `compile` / `run` contract, with no new
command, dialect, case shape, or observation field.

The example above is intentionally minimal. An include-driven claim selects an
exact case subset with `caseTags.include`, avoiding a fragile list of
exclusions. A completed language spec ordinarily adopts its selected canonical
`capabilities` block verbatim; only the `adapter` identity differs.

A case command is claimed only when **all** of these are true:

- the command is listed in `commands`
- the requested dialect is listed in `dialects`
- the case shape is listed in `caseShapes`
- every module-like tag on the case (`m-core`, `m-op-algebra`, …) is
  listed in `modules`
- if `caseTags.include` is present, the case has at least one listed tag
- if `caseTags.exclude` is present, the case has none of the listed tags

`caseTags.include` and `caseTags.exclude` use exact tag strings from case files,
including tags that contain spaces such as `identity cache`. The filters are
evaluated after the broad module/dialect/shape filters. If `caseTags` is omitted,
then the module, dialect, and shape claims are all-or-nothing for matching cases.

For a claimed case command, returning `unsupported` is invalid: the adapter MUST
return `ok` or `error`. For an unclaimed case command, returning `unsupported`
is valid and SHOULD include a diagnostic naming the first failed filter, such as
`unsupported-case-tag` or `unsupported-case-shape`.

`provisioning` is one of:

- `external-url`: `run` and `benchmark` expect the caller to provide a database
  URL or equivalent language-specific connection configuration.
- `self-managed`: the adapter provisions its own clean database, for example
  with Testcontainers. The adapter owns the reset lifecycle needed to make each
  database-backed case isolated: reset to an empty state, apply the case model's
  derived DDL, and load fixtures according to the core case lifecycle. The
  contract does not assume any generic container snapshot API; language specs
  that use snapshot/restore optimizations MUST name the concrete provider API
  and fallback reset path.

The target language spec records which mode the implementation uses.
The reusable provider-test obligations for `reset`, `applyDdl`, fixture loading,
query/write execution, rollback execution, peer connections, and declared
full/partial database matrix profiles are recorded in
[`database-provider-test-contract.md`](database-provider-test-contract.md). That
document guides implementation suites; this adapter contract remains the
normative wire surface.

## `compile`

`compile` reads one compatibility case and emits the SQL statements and binds
the implementation would execute for the requested dialect. It MUST NOT execute
SQL.

The command is valid for any case shape whose behavior can be represented as
SQL emissions. Cache-hit scenario steps that perform no database work simply
produce no emission for that step and still contribute `0` round trips.

Example:

```json
{
  "schemaVersion": "1",
  "command": "compile",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "case": "core/compatibility/cases/m-op-algebra-002-eq.yaml",
  "dialect": "postgres",
  "caseShape": "read",
  "emissions": [
    {
      "casePointer": "/operation",
      "sql": "select t0.id, t0.name from account t0 where t0.id = ?",
      "binds": [1]
    }
  ],
  "roundTrips": 1
}
```

`casePointer` is a JSON Pointer into the compatibility case. Common values are:

- `/operation`
- `/writeSequence/0`
- `/scenario/0/find`
- `/coherence/1/find`

For deep-fetch and write-sequence cases, `emissions` contains one item per
statement in execution order.

## `run`

`run` executes a compatibility case through the language implementation and
returns the observations required to compare against the case.

The adapter is responsible for using a clean database according to its declared
provisioning mode, applying schema and fixtures, executing the implementation's
public behavior, and reporting observations. A runner may compare those
observations to `then.rows`, `then.graph`, `then.graphs`, `then.tableState`,
`then.affectedRows`, cache/identity expectations, and `then.roundTrips`.

When a language implementation routes case execution through its `m-db-port`
runtime database port, read/result statements and DML outcome statements remain
separate: row-returning reads use the port's row execution method, while
write-sequence and conflict affected counts come from the port's affected-row
write method (`executeWrite` in the TypeScript port). An adapter MUST NOT weaken
the emitted SQL by adding dialect-specific row-returning clauses solely to compute
affected rows.

Example:

```json
{
  "schemaVersion": "1",
  "command": "run",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "case": "core/compatibility/cases/m-op-algebra-002-eq.yaml",
  "dialect": "postgres",
  "caseShape": "read",
  "emissions": [
    {
      "casePointer": "/operation",
      "sql": "select t0.id, t0.name from account t0 where t0.id = ?",
      "binds": [1]
    }
  ],
  "observations": {
    "rows": [
      {
        "id": 1,
        "name": "Alice"
      }
    ],
    "roundTrips": 1
  }
}
```

The observations object is intentionally shape-flexible because case shapes
assert different things:

- read cases report `rows`, `graph`, or `graphs`; `graphs` is the ordered
  per-milestone `{pin, graph}` observation for a milestone-set snapshot read
- write-sequence cases report `tableState`
- conflict cases report `affectedRows` and MAY report `tableState`
- scenario cases report `identityChecks` and `roundTrips`, plus `stateChecks` for
  any step declaring `expectState` and `errors` for any step declaring `expectError`
- coherence cases report the final observed `rows`, and `identityChecks` for any step that declares `sameObjectAs`

### Lifecycle observations (`stateChecks`, `errors`)

Two optional `observations` keys carry the object-lifecycle assertions a wire
golden SQL cannot see, mirroring the explicit-verdict shape of `identityCheck`:

- **`stateChecks`** — one entry per scenario step declaring `expectState`, each
  `{ at, expected, observed, pass }`: `at` is a JSON Pointer into the case (the
  step), `expected` the case's `expectState` (the `m-detach` five-state machine),
  `observed` the state the implementation saw, and `pass` the verdict.
- **`errors`** — one entry per scenario step declaring `expectError`, each
  `{ at, errorClass, native? }`: `at` the step pointer, `errorClass` the neutral
  application-lifecycle error the verb raised (`detached-relationship-load` /
  `processing-pin-read-only` — `m-detach` / `m-identity-map`, **distinct** from the
  `m-db-error` taxonomy), and an optional `native` witness carrying the raw
  implementation error.

Both are additive and optional: an adapter that observes no lifecycle state or
raised error simply omits them, so an existing `run` output (`roundTrips` plus
`rows` / `graph` / `identityChecks`) stays valid unchanged.

An **`identityCheck`'s semantics are the claiming module's identity contract**, not
a single fixed rule. For a **wire-level** scenario check (the PK-value one-object-
per-PK rule the harness itself grades) `same` means **primary-key-value equality**.
For a **managed-slice lifecycle** check (`differentObjectFrom`, and identity checks
on managed objects generally) `same` means **reference identity** — value equality
is insufficient, because two finite coordinates in one milestone have identical row
values yet are distinct pinned views (`m-identity-map`). An adapter grading a
managed-slice case therefore compares object references, not sorted PK values.

An **abstract-target read** — an abstract `targetEntity`, or an abstract position
`narrow`ed with `m-op-algebra`'s `narrow` node — materializes complete concrete
instances, so each observed row (and each `graph` leaf) additionally carries a
**`familyVariant`** key: the concrete subtype name of that instance (`Dog`, `Cat`,
…). `familyVariant` is a materialized observation, **never projected as SQL** —
under `table-per-hierarchy` the emitted SQL projects the raw tag column and the
implementation materializes `familyVariant` from the tag metadata map, and under
`table-per-concrete-subtype` it is a per-branch subtype-name literal
(`m-inheritance` / `m-sql`). It rides inside the already-open `rows` / `graph`
observation objects, so the adapter output gains no field for it. A
concrete-target read carries no `familyVariant`.

## `benchmark`

`benchmark` runs one benchmark fixture and reports measurements using the
`m-perf-bench` methodology. The command returns the same report shape
`m-perf-bench` calls `report.json`, wrapped in the standard adapter envelope. For a
single `--benchmark <b.yaml>` invocation, `report.benchmarks` contains one entry
for that requested fixture. Adapters MAY also write the same `report` object to a
local `report.json` artifact for CI collection, but stdout is the normative adapter
output.

Example:

```json
{
  "schemaVersion": "1",
  "command": "benchmark",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "benchmark": "core/compatibility/benchmarks/read-mix.yaml",
  "report": {
    "generatedAt": "2026-06-27T00:00:00+00:00",
    "dialect": "postgres",
    "benchmarks": [
      {
        "fixture": "read-mix.yaml",
        "model": "models/account.yaml",
        "datasetRows": 1000,
        "workloads": [
          {
            "name": "point-read",
            "iterations": 200,
            "wallTimeMs": {
              "p50": 2.8,
              "p95": 4.7
            },
            "roundTrips": 1,
            "expectRoundTrips": 1,
            "roundTripsOk": true
          }
        ]
      }
    ],
    "memory": {
      "peakBytes": 12582912,
      "steadyBytes": 10485760
    }
  }
}
```

Benchmarks are required only when a language implementation claims `m-perf-bench`
support. The benchmark envelope MUST NOT use the legacy single-workload `metrics`
object; the report object is the machine-readable performance artifact.

## Comparison Rules

A conformance runner compares adapter output to the compatibility case using the
same rules as `m-case-format`:

- emitted SQL is normalized and compared to each `then.statements` entry's
  `sql[dialect]`
- binds compare in authored order (each statement entry's own `binds`)
- rows compare using the case's row comparison rules
- deep-fetch graphs compare to `then.graph`
- milestone-set snapshot graphs compare in authored order to `then.graphs`, with
  each observation's `pin` and `graph` compared to the corresponding oracle entry
- write table state compares to `then.tableState`
- conflict affected rows compare to `then.affectedRows`
- round trips compare to the case's declared `then.roundTrips` or scenario step
  counts

The adapter output is not allowed to weaken the core corpus. If an
implementation disagrees with a case, fix the implementation or update the core
spec, schemas, fixtures, and cases together.
