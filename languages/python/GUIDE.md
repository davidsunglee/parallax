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
  green: `just python-static` (unit coverage 99.97%, diff-cover 100%) and the
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
- **Reachable intersection this phase:** 122 corpus cases (75 read, 18
  writeSequence, 29 rejected). After the Phase-5b read-projection amendment closed
  ledger D-11, **50 reads compile-match** the corpus and **48 run end-to-end**
  against real Postgres: the 33 orders `m-op-algebra` reads (incl. the tracer
  `m-op-algebra-002-eq`), the 13 value-object nested-predicate reads,
  `m-descriptor-001` (quoted identifier), and `m-core-001` (scalar round-trip); the
  2 value-object materialization reads (`m-value-object-023/024`) compile-match via
  the instance-form slot-4 document projection but are run-deferred to the snapshot
  branch (their graph observation lands with materialization, Phase 7). The
  remaining reachable cases are reasoned-skipped in the sweep (no silent gaps, zero
  D-11) with forward reasons — ledger D-12 (17 inheritance-family reads, 8 to-many
  value-object array-traversal reads, and pre-SQL rejected-operation validation) and
  the write-path shapes (Phase 6/8). The operation no-drift guard exercises 10
  idiomatic op-algebra read spellings.
- **Phase 6 in progress (transactions + temporal backbone; milestones 1–3 landed).**
  - **M1 — `m-db-error`:** the neutral category set + call-site predicates
    (`is_retriable` / `violates_unique_index` / `is_timed_out`) in
    `parallax.core.db_error`, and the port-boundary re-raise in `parallax.postgres`
    (every driver exception becomes a `DatabaseError` carrying category + preserved
    SQLSTATE + driver message). Proven by the dialect contract suite, the
    `m-db-error` unit tests, and the provider deadlock proof (a genuine
    two-connection `40P01` via `peer`).
  - **M2 — `m-temporal-read` (`ca64903`):** as-of predicate templates,
    default-latest injection on omitted axes, the milestone edge-pin, and the
    `Pin` / `Edge` value model, expressed as a rewrite of the temporal wrapper
    nodes into plain `m-op-algebra` predicates (the DAG forbids
    `m-sql -> m-temporal-read`, so the SQL composition happens one layer up).
  - **M3 — `m-unit-work` core:** the `UnitOfWork` shell (frame join,
    rollback-only, abort-and-withhold, write buffer, observations, and the
    read-your-own-writes force-flush), the write-instruction IR (`KeyedWrite` /
    `PredicateWrite`, serde against `write-instruction.schema.json`, and
    member-name honesty), the Clock Strategy, and the pure planner
    (coalesce → FK-order → elide) producing a neutral `FlushPlan`. The DAG pins
    `m-unit-work → m-op-algebra` and `m-unit-work → m-db-port` only (no
    `m-sql` / `m-dialect` edge), so the planner emits no SQL; the write-DML → SQL
    lowering is deferred to the composition surface (M4). Docker-free unit tests
    only; no write case runs yet.
  - **M4 (in progress):** landed — the write-DML → SQL lowering at the
    composition surface (`snapshot.handle.lower_write`); the conformance
    case-instruction translation (writeSequence + scenario, the D-3 string
    labels retired for the snapshot slice); and the developer transaction
    **plumbing** — `Database.connect` / `db.transact` with sentinel options,
    join / option-conflict, rollback-only foreclosure, the `m-auto-retry`
    bounded loop (`parallax.core.auto_retry`; exhaustion re-raises the failure
    with the attempt count as an exception note), and the injected flush
    executor, with the neutral `Transaction` verbs (`insert`/`update`/`delete`
    rows + a participating `find` returning rows). The object-model-dependent
    ergonomic I/O (participating `find` → instances and the instance→write-input
    derivation an `update` effective change set needs) is staged to the
    snapshot branch (Phase 7), which brings up the instance model both rest on
    (ledger D-16).
  - **Remaining (M4):** error/boundary-shape `run`; the API-suite write
    examples + no-drift guard + D-7 class spellings + the coverage-partition
    flip + usage-guide regen; the carry-in `case_runner.py` cleanup. The nine
    `error`-shape `m-db-error` cases and the coalescing witnesses
    (`m-audit-write-008`, `m-bitemp-write-014`, `m-unit-work-010`) stay
    reasoned-skipped with forward reasons until then.

## Blockers

- None. Docker is required for the database-backed lanes (`just python-verify` /
  the `python-database` CI job); the database-free lane (`just python-static`,
  which now includes `-m dialect` and `-m compile_sweep`) needs no Docker.
