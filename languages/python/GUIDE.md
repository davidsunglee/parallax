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
  D-11) with forward reasons — ledger D-12 (17 inheritance-family reads and 8
  to-many value-object array-traversal reads, both landing later in Phase 7;
  the read-side pre-SQL rejected-operation validation landed in Phase 7
  increment 1) and the write-path shapes (Phase 6/8). The operation no-drift
  guard exercises 10 idiomatic op-algebra read spellings.
- **Phase 6: transactions + temporal backbone — milestones 1–4 COMPLETE (backbone review closed).**
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
  - **M4 — COMPLETE (`4298e22..bf6f581`):** the write-DML → SQL lowering at the
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
    (ledger D-16). Also landed: the **error-shape `run` lane** — the four
    single-connection `m-db-error` uniqueViolation cases execute their authored
    trigger DML against a reset database and grade the classified
    `errorClass` / `nativeCode` (a small additive core amendment defined that
    observation pair in the adapter envelope schema + spec, and
    descriptor-derived DDL now enforces declared unique secondary indices); the
    five two-connection choreography cases are lane-classified to the provider
    contract proof, and boundary cases to the api-conformance lane — the
    error-shape compile skip is now a permanent lane classification, not a
    forward promise.
    Also landed: the **API-suite write surface** — eleven idiomatic examples
    (the nine keyed unit-of-work write cases through `db.transact`, the
    boundary withheld-value case, and the first temporal as-of read), proven
    by the new write no-drift guard (commit spellings emit the golden DML
    through the public surface; abort spellings prove the discard contract)
    and the operation no-drift guard; the **D-7 temporal class spelling**
    (`EntityConfig.as_of` declares axes in the descriptor's own
    `AsOfAttribute` vocabulary — the `Balance` mirror joins the descriptor
    no-drift guard); the coverage partition flipped (the `m-unit-work` skip
    entry narrowed to the two `m-batch-write` coalescing witnesses) and the
    usage guide regenerated.
    Closed by increment 6: the carry-in `case_runner.py` cleanup (the scenario
    find branch routes through the shared per-step read-entity helper) and the
    closing gates — `just python-verify` green (108 database-backed checks),
    the unit lane at 1069, `just oracle-test` at 1405 dual-dialect. The
    coalescing witnesses (`m-audit-write-008`, `m-bitemp-write-014`,
    `m-unit-work-010`) stay reasoned-skipped with forward reasons
    (`m-batch-write`, Phase 8). The Phase-6 backbone external review
    (checkpoint 3, M1–M4 + the two in-flight core deltas) is closed.
- **Phase 7: Snapshot branch — increment 1 COMPLETE (`6766fe0..972a0e2`).** The
  core-amendment bundle (DQ5: `m-navigate --> m-op-list` inverted to
  `m-navigate --> m-op-algebra`, `m-op-list --> m-deep-fetch` mirroring
  `m-snapshot-read --> m-deep-fetch`; DQ3/DQ8: the rejected-case run answer —
  `observations.rejectedRule`, `roundTrips: 0`, no provisioning — added to the
  adapter envelope + schema) and the Python rejected lane: `validate_operation`
  in `parallax.core.op_algebra` (narrow / subtype-attribute position tracking,
  value-object path grammar + typed-literal checks, including the scoped
  `nestedExists`/`nestedNotExists` `where`), the engine's `run_rejected_case`
  three-way `when.operation`/`when.model`/`when.write` dispatch (an
  exactly-one guard over the recognized `when` keys), and a Docker-free
  rejected sweep. Current counts: unit lane 1219, compile sweep 110, rejected
  sweep 21 passed + 10 skipped (the `when.write` cases, reasoned-skipped to
  Phase 8). Deferred: 4 rejected cases tagged `m-navigate`/`m-deep-fetch` stay
  unreachable until increments 3/5 land (their owning modules aren't in
  `IMPLEMENTED_MODULES` yet, though `validate_operation` already classifies
  them correctly).
- **Phase 7 increment 2 COMPLETE — inheritance read lowering (`8a0b506`).**
  Table-per-hierarchy tag-predicate/abstract-root reads and table-per-
  concrete-subtype union-all reads land in `compile_read`; provisioning
  derives inheritance-aware DDL and fixture loading. The 17 in-slice
  inheritance reads flip from reasoned-skip to byte-exact compile + row-graded
  run; `m-inheritance-092`/`-093` (temporal abstract reads) flip alongside
  them as a verified-correct side effect. Counts: unit lane 1273, compile
  sweep 129 (+19), `pg-full` run sweep 114 (+19, real Postgres).
- **Phase 7 increment 3 COMPLETE — navigate lowering (`2fb36d7`).**
  Relationship navigation lowers to correlated EXISTS/anti-join semi-joins in
  `parallax.core.navigate` + `compile_read`, with per-hop as-of propagation
  and polymorphic hop resolution. The 13 row-form navigate reads and 6
  polymorphic-relationship reads flip; 3 already-classified rejected cases
  become reachable. Counts: unit lane 1326, compile sweep 151 (+22), rejected
  sweep 22 passed / 10 skipped.
- **Phase 7 increment 4 COMPLETE — to-many value-object array traversal
  (`9802456`).** `nestedExists`/`nestedNotExists` and flat `nested*`
  predicates over `cardinality: many` value-object members lower to a guarded
  `jsonb_array_elements` unnest. The 8 in-slice value-object traversal reads
  flip. Counts: unit lane 1348, compile sweep 159 (+8), `pg-full` run sweep
  107 (+8, real Postgres).
- **Phase 7 increment 5 COMPLETE — deep fetch, materialization, graph
  observations (`22248e7`).** The pure deep-fetch planner
  (`parallax.core.deep_fetch`), the snapshot assembler
  (`parallax.snapshot.materialize`), and the one production find executor
  (`parallax.snapshot.handle.find`/`find_history`) land; the engine grades
  `then.graph`/`then.graphs`/`identityChecks`. 24 query-result-dependent graph
  cases are declared `compileEligibility: run-only` (ledger D-10). Counts:
  unit lane 1437, compile sweep 164 (+5, 231 total), `pg-full` run sweep 179
  (real Postgres), combined Docker lane 224 passed / 10 skipped.
- **Phase 7 increment 6a COMPLETE — developer surface, D-7 spellings, D-16
  graduation (`5386081`).** `Snapshot[T]`, `db.find`/`tx.find`, frozen-node
  wrapping (`parallax.snapshot.wrap`), the `.include`/`.narrow`/`.any`/`.none`
  statement spellings, the D-7 value-object and inheritance class spellings,
  and D-16's full write-verb graduation (`tx.insert`/`tx.update`/`tx.delete`
  over entity instances/edited copies) all land. Counts: unit lane 1541,
  compile sweep unchanged at 164, combined Docker lane unchanged at 224
  passed / 10 skipped.
- **Phase 7 increment 6b COMPLETE — API-suite build-out, coverage partition
  flip. PHASE 7 COMPLETE (`d192226`).** Every Phase-7 module's active cases
  are now either an idiomatic example or a reasoned, case-scoped skip (57
  exercised, 242 case-scoped skips, partition exact over 299 cases). Seven
  executable graph stories prove developer-facing guarantees (diamond
  identity, back-reference cycles, closed-world access, pin/edge) against
  real Postgres; fixing the diamond-identity story surfaced and fixed a
  wrap-time identity bug (`parallax.snapshot.wrap` now dedupes by logical
  identity, not python object identity). Counts: unit lane 1543, compile
  sweep unchanged at 164, combined Docker lane 271 passed / 10 skipped,
  rejected sweep 25 passed / 10 skipped. **Phase 7 (the snapshot branch) is
  COMPLETE.** **Next:** Phase 8 (writes and correctness).
- **Temporal root-ownership remediation round (core amendment, ADR 0026).**
  Corrected a latent core-spec ambiguity: temporality is now normatively a
  FAMILY-WIDE property — only the family root may declare `asOfAttributes`;
  a descendant that redeclares, adds, or shadows an axis is rejected pre-SQL
  (`inheritance-temporal-axes-not-root-owned`), regardless of the root's own
  temporal state. `parallax.core.inheritance.validate` and the D-7 class
  frontend (`EntityConfig(as_of=...)` on a family subclass) both enforce it;
  every temporal consumer (as-of injection, pin/edge, history/range,
  identity, propagation, TPH/TPCS DDL) resolves through the family root
  uniformly. Four corpus cases added (two `when.model` rejected witnesses,
  two concrete-target temporal reads); the `rate.yaml` fixture gained a
  second processing milestone sharing one business key, exercising the
  `(id, from_z, in_z)` temporal physical PK. Measured post-round: unit lane
  (`pytest -m unit`) 1583 passed / 77 skipped; compile-sweep module
  (`pytest -m compile_sweep`) 168 passed / 67 skipped; combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 312
  passed / 10 skipped; rejected sweep (`test_rejected_sweep.py`) 27 passed /
  10 skipped; API-suite partition exact over 303 active cases (47 exercised
  / 256 reasoned-skip); reference-harness `just oracle-test` 1421 passed
  dual-dialect; slice tag counts `slice-mvp-1`/`slice-snapshot-1`/
  `slice-managed-1` = 197 / 303 / 325 (`just core-dep-graph` profile gate).

## Blockers

- None. Docker is required for the database-backed lanes (`just python-verify` /
  the `python-database` CI job); the database-free lane (`just python-static`,
  which now includes `-m dialect` and `-m compile_sweep`) needs no Docker.
