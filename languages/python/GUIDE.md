# Parallax Python — operational guide

Operational reference for building and verifying the Parallax Python target
(`slice-snapshot-1`). Milestones, commands, database setup, status, blockers
only — design decisions live in `spec/python.md` and `docs/adr/`.

## Layout

```text
languages/python/
  pyproject.toml        uv workspace root (virtual): toolchain + tool config;
                        hosts the generated [tool.importlinter] complement
  pyrightconfig.json    Pyright strict configuration
  uv.lock               committed lockfile (one per workspace)
  tools/
    check_dag_sync.py   generates/checks the import-linter forbidden-edge
                        complement from core/spec/modules.md (§7)
  packages/
    parallax-core/        the class-free engine spine (production)
    parallax-snapshot/     snapshot lifecycle + handle (production)
    parallax-postgres/     concrete psycopg adapter (production)
    parallax-conformance/  corpus/case loading + describe/compile/run CLI (dev-only)
  tests/                unit / dialect / compile_sweep / conformance / provider /
                        adapter_smoke / api_conformance / artifact / clean_install /
                        api_surface lanes (pytest markers, §6/§10)
  docs/adr/             per-language ADRs
```

The four distributions share the PEP 420 `parallax.*` namespace: there is no
`parallax/__init__.py` at the namespace root, and each distribution ships
`py.typed` at its own package root.

## Dependency-respecting milestones

Built in dependency-graph order (`core/spec/modules.md`, `IMPLEMENTING.md`); a
dependency is always implemented before anything that names it. The nine COR-3
phases (structure outline
`.humanlayer/tasks/cor-3-build-python-slice/06-structure-outline-python-snapshot-target.md`):

1. Workspace, toolchain, and verification wiring. **(this milestone)**
2. Conformance spine — `m-core`, `m-case-format`, `describe` end-to-end.
3. Metamodel hub and Pydantic class frontend.
4. Core amendment bundle (compile-eligibility, write-instruction schema, coalescing).
5. SQL walking skeleton — tracer compiles and runs end-to-end.
6. Transactions and temporal backbone.
7. Snapshot branch.
8. Writes and correctness.
9. Claim closure.

## Commands

Run from the repo root (via `just`) or from `languages/python` (via `uv`).

| Purpose | Command |
|---|---|
| Install dev environment | `cd languages/python && uv sync` |
| All database-free gates (§10) | `just python-static` |
| Static + Docker database lanes | `just python-verify` |
| Unit tests | `cd languages/python && uv run pytest -m unit` |
| Regenerate import-linter complement | `cd languages/python && uv run python tools/check_dag_sync.py --write` |
| Verify the complement is in sync | `cd languages/python && uv run python tools/check_dag_sync.py` |

Pytest markers (§6): `unit`, `dialect`, `compile_sweep`, `adapter_smoke`,
`provider_contract`, `conformance`, `api_conformance`, `artifact`,
`clean_install`, `api_surface`.

## Database setup

Database-backed lanes (`conformance`/`pg-full`, `provider_contract`,
`adapter_smoke`) use testcontainers-python with a `self-managed` Postgres
container pinned to an exact version **and** sha256 digest in
`parallax.conformance.constants`. **Docker must be running.** One container per
test session; per-case isolation is `DROP SCHEMA … CASCADE` → descriptor-derived
DDL → fixtures in descriptor column order. A session summary reports every
skipped database-backed check (never silently); set `PARALLAX_REQUIRE_DB=1` to
turn any such skip into a failure (the CI database lane does this). The
production `parallax-postgres` declares `psycopg[binary]`, so the adapter installs
self-contained without a system `libpq`.

## Current status

- **Phases 1–5 complete.** The uv workspace, the four distributions, the
  conformance spine + `describe`, the metamodel hub + Pydantic class frontend,
  the Phase-4 core amendment bundle, and the Phase-5 read path are landed and
  green: `just python-static` (unit coverage 99.89%, diff-cover 100%) and the
  Docker database lanes both pass.
- **Phase 5 (SQL walking skeleton — read path):** `m-op-algebra` nodes + serde,
  the pure `m-dialect` Postgres strategy, the abstract `m-db-port`, the `m-sql`
  three-stage read compiler (`compile_read` = canonicalize → lower → normalize),
  the statement half (`Entity.where`, comparison/string/null/membership
  operators, `&`/`|`/`~` + canonical grouping, value-object nested access,
  `order_by`/`limit`/`distinct`), the concrete psycopg adapter, and the
  conformance `compile`/`run` commands with self-managed Testcontainers
  provisioning. The compile sweep and `pg-full` run lane exercise the reachable
  read intersection; the operation no-drift guard is live.
- **Reachable intersection this phase:** 124 corpus cases (77 read, 18
  writeSequence, 29 rejected). 15 reads are compiled **and** run end-to-end
  against real Postgres (13 value-object nested-predicate reads, `m-descriptor-001`
  quoted identifier, `m-core-001` scalar round-trip); the remaining reachable
  cases are reasoned-skipped in the sweep (no silent gaps) per ledger D-11 (the
  stale-orders read projection) and D-12 (inheritance reads, to-many value-object
  array traversal, and pre-SQL rejected-operation validation — all deferred to
  later phases). The operation no-drift guard exercises 10 idiomatic op-algebra
  read spellings.
- **Phase 6 next:** transactions and the temporal backbone (`db.transact`, the
  write-instruction IR + keyed writes, temporal reads, SQLSTATE classification).

## Blockers

- None. Docker is required for the database-backed lanes (`just python-verify` /
  the `python-database` CI job); the database-free lane (`just python-static`,
  which now includes `-m dialect` and `-m compile_sweep`) needs no Docker.
