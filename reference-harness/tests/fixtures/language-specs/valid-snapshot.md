# Example Snapshot Language Specification

## 1. Scope and exact claim

The implementation selects `slice-snapshot-1` and the snapshot lifecycle.

```language-binding
{"slice":"slice-snapshot-1"}
```

## 7. Source-enforcement topology

| Behavioral module | Enforcement scope |
|---|---|
| `m-api-conformance` | `api-proof` |
| `m-txtime-write` | `txtime-write` |
| `m-auto-retry` | `auto-retry` |
| `m-batch-write` | `batch-write` |
| `m-bitemp-write` | `bitemp-write` |
| `m-case-format` | `case-format` |
| `m-conformance-adapter` | `conformance` |
| `m-core` | `core` |
| `m-db-error` | `db-error` |
| `m-db-port` | `db-port` |
| `m-deep-fetch` | `deep-fetch` |
| `m-descriptor` | `descriptor` |
| `m-dialect` | `dialect` |
| `m-document-codec` | `document-codec` |
| `m-edit` | `edit` |
| `m-execution-authority` | `execution-authority` |
| `m-execution-lifecycle` | `execution-lifecycle` |
| `m-inheritance` | `inheritance` |
| `m-storage-layout` | `storage-layout` |
| `m-metamodel` | `metamodel` |
| `m-model-formation` | `model-formation` |
| `m-model-evolution` | `model-evolution` |
| `m-schema-delta` | `schema-delta` |
| `m-navigate` | `navigate` |
| `m-object-query` | `object-query` |
| `m-predicate` | `predicate` |
| `m-opt-lock` | `opt-lock` |
| `m-pk-gen` | `pk-gen` |
| `m-read-lock` | `read-lock` |
| `m-snapshot-read` | `snapshot` |
| `m-sql` | `sql` |
| `m-relationship` | `relationship` |
| `m-temporal-read` | `temporal-read` |
| `m-unit-work` | `unit-work` |
| `m-value-object` | `value-object` |
| `m-wire` | `wire` |

| Enforcement scope | Allowed direct first-party dependencies |
|---|---|
| `snapshot.materialize` | `m-metamodel`, `m-inheritance`, `m-relationship`, `m-wire` |
| `snapshot` | `snapshot.materialize`, `m-snapshot-read`, `m-execution-lifecycle` |
| `db-port.diagnostics` | (none) |
| `db-port` | `db-port.diagnostics` |

| Restricted external package | Granted enforcement scopes |
|---|---|
| `postgres_driver` | `postgres-adapter`, `conformance` |

| Child enforcement scope | Parent enforcement scope | Import policy |
|---|---|---|
| `snapshot.materialize` | `snapshot` | ordinary |
| `db-port.diagnostics` | `db-port` | sealed |

The composition root is application or test code under `tests/composition`;
it is owned by no scope and imports `snapshot` and the `postgres-adapter`
scope directly. `api-proof` is a test collection boundary. `depcheck` reads
each table back and compares it with its own declaration of the same
relation, so neither side can be edited alone.

## 8. Deployable artifact topology

| Artifact/package | Production or development-only | Included source scopes | External runtime dependencies | Depends on artifacts | Public exports/entry points |
|---|---|---|---|---|---|
| example common runtime | production | shared scopes | yaml | none | runtime API |
| example snapshot lifecycle extension | production | snapshot | none | common runtime | snapshot API |
| example postgres adapter | production | db-port adapter | postgres-driver | common runtime | adapter API |
| example conformance tools | development-only | api-proof, conformance | pytest | common runtime, postgres adapter | conformance CLI |
