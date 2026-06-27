# Conformance Adapter Contract

The conformance adapter is the seam between the language-neutral compatibility
corpus and a concrete language implementation. It gives an external runner a
small interface for asking an implementation what it supports, what SQL it
emits for a case, and what observations it produces when it runs a case.

This contract is M12-adjacent: the reference harness proves the core corpus is
internally coherent; a language implementation proves itself by satisfying this
adapter contract against that same corpus.

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
requested module, case shape, or dialect in `describe`.

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
    "modules": ["m0", "m1", "m2", "m3", "m11", "m12"],
    "dialects": ["postgres"],
    "caseShapes": ["read"],
    "commands": ["describe", "compile", "run"],
    "provisioning": "external-url"
  }
}
```

`provisioning` is one of:

- `external-url`: `run` and `benchmark` expect the caller to provide a database
  URL or equivalent language-specific connection configuration.
- `self-managed`: the adapter provisions its own clean database, for example
  with Testcontainers.

The target language spec records which mode the implementation uses.

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
  "case": "core/compatibility/cases/0002-eq.yaml",
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
  "case": "core/compatibility/cases/0002-eq.yaml",
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
- coherence cases report the final observed `rows`

## `benchmark`

`benchmark` runs one benchmark definition and reports measurements using the M13
methodology.

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
  "dialect": "postgres",
  "metrics": {
    "iterations": 100,
    "p50Ms": 2.8,
    "p95Ms": 4.7,
    "roundTrips": 1,
    "peakMemoryBytes": 12582912,
    "rowCount": 1
  }
}
```

Benchmarks are required only when a language implementation claims M13 support.

## Comparison Rules

A conformance runner compares adapter output to the compatibility case using the
same rules as M12:

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
