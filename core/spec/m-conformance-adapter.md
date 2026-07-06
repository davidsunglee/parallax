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
requested command, dialect, case shape, module tags, or case-tag slice in
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

Capability claims are deliberately **case-slice aware**. `modules`,
`dialects`, and `caseShapes` are broad filters; `caseTags` is an optional
fine-grained filter over the compatibility case's own `tags` array. This lets a
partial implementation honestly claim, for example, `m-op-algebra` predicate reads
while deferring aggregation (`m-agg`) reads, or `m-unit-work` transaction/write
cases while deferring the `m-process-cache` query-cache and identity-cache
scenarios.

The example above is intentionally minimal. For a worked, canonical
**include-driven** first slice, see the
[`slice-mvp-1`](slices.md#first-implementation-conformance-slice)
Conformance Slice in `slices.md`: its `describe` claim selects 123
Postgres-only cases by a single `caseTags.include: ["slice-mvp-1"]`
tag rather than by a fragile list of exclusions, and a consistency gate keeps the
tagged corpus aligned with that claim. A fresh implementer authoring a first build
ordinarily adopts that claim's `capabilities` verbatim (only the `adapter`
identity differs).

That canonical block is the general rule, not a one-off: a slice's
machine-readable form is a `describeOk` envelope validated against this schema,
and its name is its `caseTags.include` tag, which follows the slice-naming
convention `^slice-[a-z0-9][a-z0-9-]*$`. Both the rule and the convention are
stated with the slice in
[`slices.md`](slices.md#first-implementation-conformance-slice).

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
observations to `expectedRows`, `expectedGraph`, `expectedTableState`,
`expectedAffectedRows`, cache/identity expectations, and `roundTrips`.

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

- read cases report `rows` or `graph`
- write-sequence cases report `tableState`
- conflict cases report `affectedRows` and MAY report `tableState`
- scenario cases report `identityChecks` and `roundTrips`
- coherence cases report the final observed `rows`, and `identityChecks` for any step that declares `sameObjectAs`

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

- emitted SQL is normalized and compared to `goldenSql[dialect]`
- binds compare in authored order
- rows compare using the case's row comparison rules
- deep-fetch graphs compare to `expectedGraph`
- write table state compares to `expectedTableState`
- conflict affected rows compare to `expectedAffectedRows`
- round trips compare to the case's declared `roundTrips` or scenario step
  counts

The adapter output is not allowed to weaken the core corpus. If an
implementation disagrees with a case, fix the implementation or update the core
spec, schemas, fixtures, and cases together.
