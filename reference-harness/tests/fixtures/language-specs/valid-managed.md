# Example Managed-Object Language Specification

## 1. Scope and exact claim

The implementation selects `slice-managed-1` and the managed-object lifecycle.

```json
{
  "schemaVersion": "1",
  "command": "describe",
  "status": "ok",
  "adapter": {
    "language": "example-managed",
    "name": "example-managed-adapter",
    "version": "1.0.0"
  },
  "capabilities": {
    "modules": ["m-api-conformance", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-dialect", "m-document-codec", "m-edit", "m-identity-map", "m-inheritance", "m-metamodel", "m-model-formation", "m-navigate", "m-object-query", "m-op-list", "m-opt-lock", "m-pk-gen", "m-predicate", "m-read-lock", "m-relationship", "m-sql", "m-storage-layout", "m-temporal-read", "m-txtime-write", "m-unit-work", "m-value-object", "m-wire"],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "edit", "error", "concurrencySuccess", "rejected"],
    "caseTags": { "include": ["slice-managed-1"] },
    "commands": ["describe", "compile", "run"],
    "provisioning": "self-managed"
  }
}
```

The unclaimed implementation prerequisite is `m-db-port`. Deferred behavior is
recorded separately. Verification selects the active slice tag intersected with
the relevant capability tags.

## 3. Object lifecycle profile

### Managed-object lifecycle

Reads return managed objects interned by a transaction-scoped identity map;
lists, mutation buffering, and commit/abort are explicit.

## 4. Result collections and materialization

### Managed-object results

Query-backed collections resolve lazily and coalesce through the identity
map while preserving empty, null, unloaded, ordered, and shared states.

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
| `m-identity-map` | `identity-map` |
| `m-inheritance` | `inheritance` |
| `m-storage-layout` | `storage-layout` |
| `m-metamodel` | `metamodel` |
| `m-model-formation` | `model-formation` |
| `m-navigate` | `navigate` |
| `m-object-query` | `object-query` |
| `m-predicate` | `predicate` |
| `m-op-list` | `lists` |
| `m-opt-lock` | `opt-lock` |
| `m-pk-gen` | `pk-gen` |
| `m-read-lock` | `read-lock` |
| `m-sql` | `sql` |
| `m-relationship` | `relationship` |
| `m-temporal-read` | `temporal-read` |
| `m-unit-work` | `unit-work` |
| `m-value-object` | `value-object` |
| `m-wire` | `wire` |

| Enforcement scope | Allowed direct first-party dependencies |
|---|---|
| `lists.batching` | `m-op-list`, `m-unit-work` |
| `db-port.diagnostics` | (none) |
| `db-port` | `db-port.diagnostics` |

| Restricted external package | Granted enforcement scopes |
|---|---|
| `postgres_driver` | `postgres-adapter`, `conformance` |

| Child enforcement scope | Parent enforcement scope | Import policy |
|---|---|---|
| `lists.batching` | `lists` | ordinary |
| `db-port.diagnostics` | `db-port` | sealed |

The composition root is application or test code under `tests/composition`;
it is owned by no scope and imports `lists` and the `postgres-adapter`
scope directly. `api-proof` is a test collection boundary. `depcheck` reads
each table back and compares it with its own declaration of the same
relation, so neither side can be edited alone.

## 8. Deployable artifact topology

| Artifact/package | Production or development-only | Included source scopes | External runtime dependencies | Depends on artifacts | Public exports/entry points |
|---|---|---|---|---|---|
| example common runtime | production | shared scopes | yaml | none | runtime API |
| example managed lifecycle extension | production | identity-map, lists | none | common runtime | managed API |
| example postgres adapter | production | db-port adapter | postgres-driver | common runtime | adapter API |
| example conformance tools | development-only | api-proof, conformance | pytest | common runtime, postgres adapter | conformance CLI |

## 9. Conditional capability decisions

The claim contains `m-storage-layout`, so the Relational Document Layout
decision is recorded; no other conditional capability is part of this claim.

### Relational Document Layout

The implementation does not support the root-owned `Document` Storage Layout.
The capability is recorded as deferred in section 1, and formation refuses every
`Document` declaration rather than accepting a subset it cannot execute.

## 10. Mandatory quality toolchain

| Quality concern | Tool and version policy | Configuration path(s) | Local command | Blocking CI command/job | Threshold, exclusions, and enforcement policy |
|---|---|---|---|---|---|
| Dependency directions within and across artifacts | depcheck 1.x | depcheck.toml | `depcheck` | `ci depcheck` | Blocks DAG drift and illegal directions. |
| Unit tests | pytest 9.x | pyproject.toml | `pytest tests/unit` | `ci unit` | Unit failures block; database tests are separate. |
| Code coverage | coverage.py 7.x | pyproject.toml | `coverage run` | `ci coverage` | 90% line coverage; generated code excluded; no new uncovered code. |
| Linting | Ruff 0.x | pyproject.toml | `ruff check .` | `ci lint` | Selected rules block; suppressions require rationale. |
| Deterministic formatter check | Ruff 0.x | pyproject.toml | `ruff format --check .` | `ci format` | Check mode blocks; `ruff format .` writes. |
| Strict static typing | basedpyright 1.x strict | pyproject.toml | `basedpyright` | `ci types` | Strict mode covers production and tests with no exclusions. |
| Import-cycle detection | depcheck 1.x | depcheck.toml | `depcheck cycles` | `ci cycles` | All production scopes are checked. |
| Dead code and unused exports | vulture 2.x | pyproject.toml | `vulture src` | `ci dead-code` | Unused production symbols block unless allowlisted with rationale. |
| Built-artifact and public-export health | twine 6.x | pyproject.toml | `twine check dist/*` | `ci package` | Packed metadata and exports must be valid. |
| Clean-install production smoke tests | pip 26.x | tests/distribution | `pytest tests/distribution` | `ci install` | Selective installs exclude alternative lifecycles and drivers. |
| Supported language/runtime versions | Python 3.13-3.14 | ci/runtime.yml | `tox` | `ci runtime-matrix` | All supported versions block; EOL versions are removed deliberately. |
| Dependency and supply-chain audit | pip-audit 2.x | requirements.lock | `pip-audit` | `ci audit` | High severity blocks; owned exceptions expire in 30 days. |
| Compatibility Conformance Suite | pytest 9.x | tests/compatibility | `pytest tests/compatibility` | `ci conformance` | Selects active slice and capability tags; validates envelopes. |
| API Conformance Suite and Usage Guide | pytest 9.x | tests/api | `pytest tests/api` | `ci api` | Coverage partition, query no-drift, real adapter, and guide drift block. |
| Database-backed verification | pytest 9.x | pyproject.toml | `pytest -m db` | `ci database` | Required profiles run; every skipped check is reported with its reason. |

- **Scheduling classes.** `dbfree` and `db`, decided per item by whether the
  item's fixture closure reaches the provisioned database.
- **Aggregate `dbfree` command.** `example-check-dbfree` runs every
  database-free row above in blocking CI job `ci dbfree`.
- **Aggregate `db` command.** `example-check-db` runs every database-backed row
  above in blocking CI job `ci database`.
- **Complete verification command.** `example-check` composes both class
  aggregates and reports every run, failed, and skipped check with a reason.
