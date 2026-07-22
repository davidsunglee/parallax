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
    "modules": ["m-api-conformance", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-detach", "m-dialect", "m-identity-map", "m-inheritance", "m-metamodel", "m-model-formation", "m-navigate", "m-op-algebra", "m-op-list", "m-opt-lock", "m-pk-gen", "m-read-lock", "m-relationship", "m-sql", "m-temporal-read", "m-txtime-write", "m-unit-work", "m-value-object"],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "error", "concurrencySuccess", "rejected"],
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
lists, mutation buffering, commit/abort, detach, and merge-back are explicit.

## 4. Result collections and materialization

### Managed-object results

Operation-backed collections resolve lazily and coalesce through the identity
map while preserving empty, null, unloaded, ordered, and shared states.

## 7. Source-enforcement topology

| Behavioral/support module | Source owner/path | Enforcement scope | Allowed direct dependencies | Enforcement rule/config |
|---|---|---|---|---|
| `m-api-conformance` | src/api-proof | api-proof | `m-case-format` | depcheck.toml |
| `m-txtime-write` | src/txtime-write | txtime-write | `m-temporal-read`, `m-unit-work` | depcheck.toml |
| `m-auto-retry` | src/auto-retry | auto-retry | `m-unit-work`, `m-db-error` | depcheck.toml |
| `m-batch-write` | src/batch-write | batch-write | `m-unit-work` | depcheck.toml |
| `m-bitemp-write` | src/bitemp-write | bitemp-write | `m-txtime-write` | depcheck.toml |
| `m-case-format` | src/case-format | case-format | `m-core` | depcheck.toml |
| `m-conformance-adapter` | src/conformance | conformance | `m-case-format` | depcheck.toml |
| `m-core` | src/core | core | none | depcheck.toml |
| `m-db-error` | src/db-error | db-error | `m-db-port`, `m-dialect` | depcheck.toml |
| `m-db-port` | src/db-port | db-port | `m-core` | depcheck.toml |
| `m-deep-fetch` | src/deep-fetch | deep-fetch | `m-navigate`, `m-op-list` | depcheck.toml |
| `m-descriptor` | src/descriptor | descriptor | `m-core`, `m-metamodel` | depcheck.toml |
| `m-detach` | src/detach | detach | `m-unit-work`, `m-identity-map` | depcheck.toml |
| `m-dialect` | src/dialect | dialect | `m-core` | depcheck.toml |
| `m-identity-map` | src/identity-map | identity-map | `m-unit-work`, `m-temporal-read` | depcheck.toml |
| `m-inheritance` | src/inheritance | inheritance | `m-descriptor`, `m-metamodel`, `m-model-formation` | depcheck.toml |
| `m-metamodel` | src/metamodel | metamodel | `m-core` | depcheck.toml |
| `m-model-formation` | src/model-formation | model-formation | `m-metamodel` | depcheck.toml |
| `m-navigate` | src/navigate | navigate | `m-op-algebra`, `m-unit-work`, `m-temporal-read`, `m-inheritance`, `m-relationship` | depcheck.toml |
| `m-op-algebra` | src/operation | operation | `m-descriptor`, `m-inheritance` | depcheck.toml |
| `m-op-list` | src/lists | lists | `m-op-algebra`, `m-unit-work` | depcheck.toml |
| `m-opt-lock` | src/opt-lock | opt-lock | `m-unit-work`, `m-temporal-read`, `m-metamodel`, `m-model-formation`, `m-inheritance` | depcheck.toml |
| `m-pk-gen` | src/pk-gen | pk-gen | `m-descriptor`, `m-metamodel` | depcheck.toml |
| `m-read-lock` | src/read-lock | read-lock | `m-unit-work`, `m-dialect` | depcheck.toml |
| `m-sql` | src/sql | sql | `m-op-algebra`, `m-dialect` | depcheck.toml |
| `m-relationship` | src/relationship | relationship | `m-metamodel`, `m-model-formation` | depcheck.toml |
| `m-temporal-read` | src/temporal-read | temporal-read | `m-op-algebra`, `m-metamodel`, `m-model-formation`, `m-inheritance` | depcheck.toml |
| `m-unit-work` | src/unit-work | unit-work | `m-op-algebra`, `m-db-port` | depcheck.toml |
| `m-value-object` | src/value-object | value-object | `m-descriptor`, `m-metamodel`, `m-model-formation` | depcheck.toml |
| adapter composition | tests/composition | composition | postgres adapter | depcheck.toml |

## 8. Deployable artifact topology

| Artifact/package | Production or development-only | Included source scopes | External runtime dependencies | Depends on artifacts | Public exports/entry points |
|---|---|---|---|---|---|
| example common runtime | production | shared scopes | yaml | none | runtime API |
| example managed lifecycle extension | production | identity-map, detach, lists | none | common runtime | managed API |
| example postgres adapter | production | db-port adapter | postgres-driver | common runtime | adapter API |
| example conformance tools | development-only | api-proof, conformance | pytest | common runtime, postgres adapter | conformance CLI |

## 9. Conditional capability decisions

No conditional capability is part of this claim.

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
| Clean-install production smoke tests | pip 26.x | tests/install | `pytest tests/install` | `ci install` | Selective installs exclude alternative lifecycles and drivers. |
| Supported language/runtime versions | Python 3.11-3.13 | ci/runtime.yml | `tox` | `ci runtime-matrix` | All supported versions block; EOL versions are removed deliberately. |
| Dependency and supply-chain audit | pip-audit 2.x | requirements.lock | `pip-audit` | `ci audit` | High severity blocks; owned exceptions expire in 30 days. |
| Compatibility Conformance Suite | pytest 9.x | tests/conformance | `pytest tests/conformance` | `ci conformance` | Selects active slice and capability tags; validates envelopes. |
| API Conformance Suite and Usage Guide | pytest 9.x | tests/api | `pytest tests/api` | `ci api` | Coverage partition, operation no-drift, real adapter, and guide drift block. |
| Database-backed verification | pytest 9.x | tests/database | `pytest tests/database` | `ci database` | Required profiles run; every skipped check is reported with its reason. |

**Static verification:** `just static` runs in blocking CI job `ci static`.

**Full verification:** `just verify` reports every run, failed, and skipped check
with a reason.
