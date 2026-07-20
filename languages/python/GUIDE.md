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
                        complement from core/spec/modules.md, and parity-checks
                        its support-scope table against spec/python.md §7
    check_scope_ownership.py
                        proves every production source file belongs to exactly
                        one §7 enforcement scope or an exact exemption
    check_untracked_sources.py
                        fails on a Python source file that exists on disk but
                        not in git (the changed-line coverage gate reads git)
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
| Verify every production file has a scope owner | `cd languages/python && uv run python tools/check_scope_ownership.py` |

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
  wrapping (`parallax.snapshot.handle`), the `.include`/`.narrow`/`.any`/`.none`
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
  wrap-time identity bug (`parallax.snapshot.handle` now dedupes by logical
  identity, not python object identity). Counts: unit lane 1543, compile
  sweep unchanged at 164, combined Docker lane 271 passed / 10 skipped,
  rejected sweep 25 passed / 10 skipped. **Phase 7 (the snapshot branch) is
  COMPLETE.** **Next:** Phase 8 (writes and correctness).
- **Temporal root-ownership remediation round (core amendment).** Landed the
  binding uniform-family-temporality decision — design in
  [ADR 0026](../../docs/adr/0026-inheritance-family-temporal-axes-are-declared-only-by-the-root.md)
  and `core/spec/m-inheritance.md` ("Temporal axes are root-owned") /
  `core/spec/m-descriptor.md`; this entry is status only. Measured
  post-round: unit lane (`pytest -m unit`) 1583 passed / 77 skipped;
  compile-sweep module (`pytest -m compile_sweep`) 168 passed / 67 skipped;
  combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 312
  passed / 10 skipped; rejected sweep (`test_rejected_sweep.py`) 27 passed /
  10 skipped; API-suite partition exact over 303 active cases (47 exercised
  / 256 reasoned-skip); reference-harness `just oracle-test` 1421 passed
  dual-dialect; slice tag counts `slice-mvp-1`/`slice-snapshot-1`/
  `slice-managed-1` = 197 / 303 / 325 (`just core-dep-graph` profile gate).
- **Effective-temporality resolver + `m-inheritance-100`/`-101` story review
  remediation.** Closed a residual gap in the round above: four sites still
  classified from an inheritance participant's LOCAL `as_of_attributes`
  instead of the family-effective one (`meta().temporal`, the
  `optimisticLocking` composition check, `lower_write`'s temporal-write
  refusal, plus the completed `m-descriptor`-scope resolver
  `parallax.core.descriptor.declaring_entity` this round's records.py change
  started); `parallax.core.inheritance.declaring_entity`/`family_root` now
  compose with it instead of duplicating the ancestry walk; the class
  frontend (`EntityMeta.__new__`) gained the same family-effective
  `optimisticLocking` composition gate the descriptor-level validator did.
  `m-inheritance-100`'s graph story ran `.history()` instead of the case's own
  as-of point read (moved to a `ReadStory`, `parallax.conformance.read_stories`,
  graded by the generic runner; the history proof survives as a clearly-named
  supplemental, non-partition-affecting test). Measured post-round: unit lane
  (`pytest -m unit`) 1589 passed / 77 skipped; compile-sweep module
  (`pytest -m compile_sweep`) 168 passed / 67 skipped; combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 314
  passed / 10 skipped; API-suite partition unchanged at 303 active (47
  exercised / 256 reasoned-skip); `just python-static` / `just python-verify`
  exit 0 (diff-cover 100%, Pyright 0/0/0); `just lint` exit 0, including the
  new `m-case-format.md` <-> `compatibility-case.schema.json` `rejectedRule`
  vocabulary drift guard (`reference_harness.case_format_vocab_check`).
- **Phase 8 increment 1 COMPLETE — core-amendment bundle (D-25 root-owned
  optimistic locking, the DQ2 spec-gap riders, DQ7b's instance-form corpus
  support; core commits `83649ad`/`f62e7d1`).** Design in
  [ADR 0027](../../docs/adr/0027-inheritance-family-optimistic-locking-is-declared-only-by-the-root.md)
  and `core/spec/m-inheritance.md` ("Optimistic locking is root-owned",
  "Abstract-position reads"); this entry is status only.
  `validate_optimistic_locking_root_owned` (generalizing the retired
  `validate_temporal_optimistic_locking`) and the class frontend
  (`EntityMeta.__new__`) both reject a family descendant's own
  `optimisticLocking` attribute regardless of root versioning;
  `parallax.core.inheritance.validate` gained the matching
  `inheritance-optimistic-locking-not-root-owned` invariant so
  `m-inheritance-102`/`-103` grade through the existing rejected lane.
  Eight new corpus cases join the reachable sweep: `m-inheritance-102`/`-103`
  (rejected), `-104` (TPCS opt-lock composition, unreachable — `m-opt-lock`
  not yet implemented), `-105` (composed temporal x inheritance x opt-lock
  conflict, unreachable, same reason), `-106`/`-107`/`-108` (TPH instance-form
  `then.graph` siblings — compile byte-identical to their row-form originals,
  reasoned-skipped from the RUN sweep and the API-suite partition pending
  increment 7's per-variant graph narrowing), `-109` (the TPCS sibling,
  reasoned-skipped at compile too — `SqlGenError`, a pre-existing engine gap
  increment 7 also closes). Measured post-round: unit lane (`pytest -m unit`)
  1611 passed / 78 skipped; compile-sweep module (`pytest -m compile_sweep`)
  171 passed / 68 skipped; combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 314
  passed / 10 skipped; rejected sweep (`test_rejected_sweep.py`) 27 passed /
  10 skipped; API-suite partition exact over 311 active cases (47 exercised /
  264 reasoned-skip); `just python-static` / `just python-verify` exit 0
  (diff-cover 100%, Pyright/coverage clean); `just lint` exit 0; reference-harness
  `just oracle-test` 1447 passed dual-dialect; slice tag counts
  `slice-mvp-1`/`slice-snapshot-1`/`slice-managed-1` = 197 / 311 / 333
  (`just core-dep-graph` profile gate). No `validate_write`, version-gate
  lowering, instance-form Python lowering, or boundary runner in this
  increment (increments 2+).
- **Phase 8 increment 2 COMPLETE — write validation + the rejected lane.**
  The model-aware `validate_write` (`parallax.core.unit_work.write_validate`):
  the declared-composite walk (required-attribute / required-value-object /
  value-type-mismatch, any depth, mutation-aware sparse-update leniency, the
  DB-computed-marker and declared-`default` exemptions) plus
  `parallax.core.inheritance.validate_subtype_write` (the payload-shape
  pipeline: keyless → metadata → sibling → abstract-target) — one validator,
  two callers, shared verbatim by `engine.run_rejected_case`'s new `write`
  branch and `Transaction._buffer` (which now runs it before
  `validate_instruction`). All 10 `when.write` rejected cases flip; the
  sweep's hard-skip is gone. `m-inheritance-088` (abstract-write-target) gets
  an idiomatic buffer-time proof through `tx.insert` (`Payment`/`CardPayment`/
  `CashPayment` already have a production-reachable mirror); the other nine
  stay honest, case-scoped reasoned skips — three m-inheritance shapes
  (sibling/metadata/keyless) have no idiomatic spelling through the typed
  verb surface today (each empirically verified: Pydantic's `extra='ignore'`
  silently drops a sibling field, `tagValue` is never a per-instance field,
  and the keyless shape's honest developer trigger is the unbuilt `_where`
  verb family, increment 5), and the six m-value-object shapes need a
  `Contact`/`Shipment` mirror that does not exist yet (ledger D-21, increment
  7). No core change. Measured post-round: unit lane (`pytest -m unit`) 1682
  passed / 68 skipped; compile-sweep module (`pytest -m compile_sweep`) 171
  passed / 68 skipped (byte-identical, unchanged); combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 325
  passed / 0 skipped; rejected sweep (`test_rejected_sweep.py`) 37 passed / 0
  skipped; API-suite partition exact over 311 active cases (48 exercised /
  263 reasoned-skip); `just python-static` exit 0 (diff-cover 100%,
  Pyright/coverage clean); `gen-usage-guide --check` exit 0; `just lint` /
  `just core-dep-graph` unchanged-green (slice tag counts
  `slice-mvp-1`/`slice-snapshot-1`/`slice-managed-1` = 197 / 311 / 333). No
  version-gate lowering, temporal writes, `_where` verbs, or `lower_write`
  changes in this increment (increments 3+).
- **Phase 8 increment 3 COMPLETE — the `m-opt-lock` version gate, inheritance
  keyed writes, and pk-gen write-side allocation.** `parallax.core.opt_lock`
  (the observation-required prior-read rule, the runtime-computed advance,
  the optimistic-only gate, the `OptimisticLockConflictError`/
  `HistoricalObservationError` vocabulary) composed at the
  `parallax.snapshot.handle.lower_write` seam: every non-temporal keyed
  UPDATE now advances a versioned row's version in both concurrency modes and
  gates on it (optimistic only); a keyed DELETE binds the observed version
  when one was recorded (`m-batch-write-004`'s own witness). Inheritance-family
  keyed writes (table-per-hierarchy tag derivation/guard, table-per-concrete-
  subtype own-table routing, deep-chain and sibling-branch creates, the
  opt-lock × inheritance composition pair) and pk-gen write-side allocation
  (`max` folded into the INSERT, `sequence` registry advance) land in the same
  seam. The reachability set flips 30 cases. `Transaction.update`/`.delete`
  gained the observation-required developer idiom (fetch inside the writing
  transaction first); the API-suite write examples that predate this rule
  (`m-unit-work-005`/`-009`) keep their pre-existing (then-undetected)
  round-trip mismatch — closed by a later review remediation, below. Measured
  post-round: unit lane (`pytest -m unit`) 1748 passed / 78 skipped;
  compile-sweep module (`pytest -m compile_sweep`) 190 passed / 78 skipped;
  combined Docker lane (`conformance`/`provider_contract`/`adapter_smoke`/
  `api_conformance`) 357 passed / 0 skipped; rejected sweep
  (`test_rejected_sweep.py`) 39 passed / 0 skipped; API-suite partition exact
  over 311 active cases (48 exercised / 263 reasoned-skip — increment 3's own
  new cases are conformance-lane-covered reasoned skips, no new idiomatic
  examples yet); `just python-static` exit 0. Known debt carried forward: the
  M4-era literal-version passthrough (`lower_update` recognizes an explicit
  row-carried `version` field and skips the observation rule entirely,
  `m-unit-work-005`/`-009`'s own authoring shape) is core corpus debt, not
  fixed here.
- **Phase 8 increment 4 COMPLETE — temporal writes: audit-only close-and-chain
  and full-bitemporal rectangle splits.** `parallax.core.audit_write` /
  `.bitemp_write` (pure milestone planning: `MilestoneClose`/`MilestoneOpen`
  steps) composed at the SAME `lower_write` seam with the `m-opt-lock` gate
  policy: `insert`/`update`/`terminate` and the bounded `insertUntil`/
  `updateUntil`/`terminateUntil` trio all lower, TPH/TPCS inheritance
  composition included. The conformance engine's write lanes re-route through
  the shipped `db.transact` entry point (DQ4, ledger D-18) instead of a
  bespoke execution path, and gain a case-local `TemporalShadow` translation
  layer (never production code) standing in for "the observation a real
  `tx.find` would have supplied." The reachability set flips 32 more cases.
  Measured post-round: unit lane (`pytest -m unit`) 1803 passed / 90 skipped;
  compile-sweep module (`pytest -m compile_sweep`) 212 passed / 90 skipped;
  combined Docker lane (`conformance`/`provider_contract`/`adapter_smoke`/
  `api_conformance`) 389 passed / 0 skipped; rejected sweep
  (`test_rejected_sweep.py`) 39 passed / 0 skipped; API-suite partition exact
  over 311 active cases (48 exercised / 263 reasoned-skip); `just
  python-static` exit 0. Known debt/gaps carried forward, closed by the
  Phase-8 mid-phase review remediation below: `lower_delete` let an
  unobserved versioned DELETE through ungated instead of raising (the
  `m-opt-lock` rule this increment's own UPDATE gate already enforced);
  `Transaction.find`'s observation recording covered only VERSION
  observations, so a locking-mode temporal write's historical-observation
  license (`check_locking_license`) was wired but permanently a no-op; the
  engine's row-decomposition discriminator read the case's own authored
  `statements` count instead of deriving it semantically; and two structured
  predicate-write cases (`m-batch-write-005`/`-006`) crashed with a bare
  `KeyError` instead of refusing loudly. `m-bitemp-write-008` (the sole
  writeSequence case needing optimistic concurrency with no
  `when.uow.concurrency` field to declare it) is accommodated by a narrow,
  documented, engine-local override (`_CONCURRENCY_OVERRIDES`) standing in for
  a corpus amendment — core debt, not fixed here.
- **Phase 8 mid-phase review remediation (increments 2–4).** Closed the four
  gaps increment 4's own entry named above: `lower_delete` now requires the
  SAME prior observation a keyed UPDATE does for a versioned row, in either
  concurrency mode (`m-unit-work-006`/`-009`/`-012`'s own corpus authoring
  predates the rule and no longer round-trips through the compile/run
  sweeps — a corpus conflict reported upstream, not resolved by editing
  `core/compatibility`); `Transaction.find` now records a TEMPORAL
  observation (observed `in_z` plus pin provenance, and — for a bitemporal
  entity — the business bounds/payload temporal lowering already consumes),
  so a locking-mode write after a historical/edge-pinned find genuinely
  raises `HistoricalObservationError` instead of a permanent no-op; the
  conformance engine's row-decomposition discriminator is now derived
  SEMANTICALLY (mutation kind, versioned-ness, per-row observation keys,
  pk-gen management, update-value uniformity) with `statements` demoted to
  the count-consistency assertion the schema intends; and a structured
  predicate-write instruction refused loudly at this round, naming
  increment 5 — a stand-in retired once increment 5 landed real
  predicate-write execution (below); its own `handle.predicate_write_refusal`
  source (named in that later entry) no longer exists. `m-batch-write-002`
  (an unversioned per-key update with non-uniform values) turned out to
  already lower correctly and joined the exercised set. Known debt this round
  intentionally left untouched (all pre-existing, all core-side or corpus-side):
  the `m-bitemp-write-008` engine override above; the M4-era literal-version
  UPDATE passthrough above; and the `m-unit-work-005`/`-009` API-suite
  round-trip conflict — plus a THIRD instance the delete fix surfaced,
  `m-unit-work-006` — all three now render as guide-only Usage-Guide examples
  (`api_suite.GUIDE_ONLY_WRITE_STORY_IDS`) with a case-scoped reasoned skip
  rather than a claimed exercised round trip; resolution for all three is a
  corpus amendment or the D-23 instance-native rework (increment 7). Measured
  post-round: unit lane (`pytest -m unit`) 1822 passed / 92 skipped;
  compile-sweep module (`pytest -m compile_sweep`) 211 passed / 92 skipped;
  combined Docker lane (`conformance`/`provider_contract`/`adapter_smoke`/
  `api_conformance`) 387 passed / 0 skipped; rejected sweep
  (`test_rejected_sweep.py`) 39 passed / 0 skipped (unchanged); API-suite
  partition exact over 311 active cases (45 exercised / 266 reasoned-skip —
  down 3 exercised, up 3 reasoned-skip: the three guide-only stories above);
  `just python-static` exit 0 (diff-cover 100%, Pyright/coverage clean);
  `gen-usage-guide --check` exit 0.
- **Confirmation-pass residual remediation.** Closed the two residuals the
  Phase-8 mid-phase review's confirmation pass surfaced. `m-unit-work-012`'s
  story constructed its delete's provenance outside the transaction and raised
  its own deliberate abort before ever flushing, so it coincidentally passed
  while no longer mirroring the corpus's own force-flushed-then-rolled-back
  DELETE choreography (`lower_delete`'s prior-observation gate, per the round
  above); the corrected idiom (observe, force-flush the delete for real, then
  let the deliberate abort roll it back) joins the guide-only set
  (`api_suite.GUIDE_ONLY_WRITE_STORY_IDS`) with the same case-scoped reasoned
  skip treatment as `m-unit-work-005`/`-006`/`-009`. The predicate-write
  refusal wording duplicated between `parallax.snapshot.handle.lower_write`
  and `parallax.conformance.engine`'s structural pre-check now shared one
  source, `handle.predicate_write_refusal` (the same move as
  `opt_lock.classify_mismatch`, increment above) — that refusal, and its
  named source, no longer exist: increment 5 (below) replaced the refusal
  with real predicate-write execution. Measured post-round: unit
  lane (`pytest -m unit`) 1822 passed / 92 skipped (unchanged); compile-sweep
  module (`pytest -m compile_sweep`) 211 passed / 92 skipped (unchanged);
  combined Docker lane (`conformance`/`provider_contract`/`adapter_smoke`/
  `api_conformance`) 387 passed / 0 skipped (unchanged — `m-unit-work-012`
  keeps running under `test_story_run.py`); rejected sweep
  (`test_rejected_sweep.py`) 39 passed / 0 skipped (unchanged); API-suite
  partition exact over 311 active cases (44 exercised / 267 reasoned-skip —
  down 1 exercised, up 1 reasoned-skip: `m-unit-work-012` joining the
  guide-only set); `just python-static` exit 0 (diff-cover 100%,
  Pyright/coverage clean); `gen-usage-guide --check` exit 0.
- **Core amendment bundle (corpus) + Python re-enablement.** Landed the
  corpus/spec conflict fix the mid-phase review's confirmation pass named:
  `m-bitemp-write-008` gained its `when.uow.concurrency: optimistic`
  declaration; `m-unit-work-005`/`-006`/`-009`/`-012` gained the observing
  find(s) `m-opt-lock`'s prior-observation rule requires. Two commits
  (`fix(core):` corpus, `fix(python):` engine re-enablement). Measured
  post-round: unit lane (`pytest -m unit`) 1830 passed / 89 skipped;
  compile-sweep module (`pytest -m compile_sweep`) 214 passed / 89 skipped;
  combined Docker lane (`conformance`/`provider_contract`/`adapter_smoke`/
  `api_conformance`) 390 passed / 0 skipped; rejected sweep
  (`test_rejected_sweep.py`) 39 passed / 0 skipped; API-suite partition exact
  over 311 active cases (48 exercised / 263 reasoned-skip); `just
  python-static` exit 0 (diff-cover 100%, Pyright/coverage clean);
  `gen-usage-guide --check` exit 0. External review of this series returned
  REWORK (2 blockers, 3 should-fix) — closed by the remediation below.
- **Amendment-bundle review remediation.** Closed the external review's
  findings via its own mandated resolution: scenario `uow` step grouping
  (`core/schemas`, `core/spec`, the reference harness) plus
  `compileEligibility: run-only` declarations on the five observation-
  dependent `m-unit-work` cases and the re-authored `m-opt-lock-012`. Three
  commits (`fix(core):` schema/spec/harness, `fix(core):` corpus,
  `fix(python):` engine). Measured post-round: unit lane (`pytest -m unit`)
  1834 passed / 94 skipped; compile-sweep module (`pytest -m compile_sweep`)
  209 passed / 94 skipped; combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 390
  passed / 0 skipped (the five `m-unit-work` cases graded via the run-only
  selector; `m-opt-lock-012` stays out — its green gate is `just
  oracle-test`); rejected sweep (`test_rejected_sweep.py`) 39 passed / 0
  skipped; API-suite partition exact over 311 active cases (48 exercised /
  263 reasoned-skip, unchanged); `just python-static` exit 0 (diff-cover
  100%, Pyright/coverage clean); `gen-usage-guide --check` exit 0; `just
  oracle-test` 1455 passed (real Postgres + MariaDB, +7 new harness unit
  tests pinning the `uow` grouping semantics). Confirmation-pass residuals
  closed (two commits: `fix(core):` harness/schema/prose/corpus,
  `fix(python):` docstring). Re-measured: `just oracle-test` 1456 passed
  (+1); unit lane 1834 passed / 94 skipped; compile-sweep 209 passed / 94
  skipped (unchanged); combined Docker lane 390 passed / 0 skipped
  (unchanged); rejected sweep 39 passed / 0 skipped (unchanged); API-suite
  partition unchanged (48 exercised / 263 reasoned-skip); `just
  python-static` exit 0; `gen-usage-guide --check` exit 0.
- **Phase 8 increment 5 (predicate-selected set-based writes) + corpus
  fixes.** Landed the `.set(...)` typed assignment DSL and the `_where` verb
  family (`update_where` / `delete_where` / `terminate_where` /
  `update_until_where` / `terminate_until_where`, python.md §5): a bare
  `m-op-algebra` predicate, readless for an unversioned non-temporal target
  (one statement, `m-batch-write` "Predicate-selected readless forms") and
  MATERIALIZING otherwise (resolve + per-row observation + gated/no-op-eliminated
  per-object writes, an atomic planned unit, `m-opt-lock` ADR 0014). The
  earlier `handle.predicate_write_refusal` stand-in (mid-phase-review-remediation
  entry above) retired entirely — predicate writes execute for real now, no
  refusal wording left anywhere in the seam. `m-value-object-047` and
  `m-opt-lock-001` were re-authored as reachable golden shapes and flipped
  into the run sweep.
- **Increment-5 review remediation.** Closed an external review's findings (1
  blocking, 4 should-fix, 1 nit, 1 confirmation-partial). An OPTIMISTIC
  audit-only materializing `terminate` was lowering ungated: the resolving
  read now records every resolved row's observed `in_z` through the same
  `uow.observe` seam every other materializing verb uses (observations are
  mode-independent; only the gate is mode-dependent), so the existing
  gated-close lowering emits `and in_z = ?` under optimistic concurrency and
  stays ungated under locking — `m-value-object-047`'s own step-2 close golden
  was re-authored gated to match (`core/compatibility`). The materializing
  resolving read's projection is now need-sensitive: terminate/delete still
  omit the value-object document (`m-value-object-047`'s own row-form
  witness, unchanged), while an assignment-bearing audit-only `update`
  carries the document forward for its chain. `.set(...)` and a case-authored
  predicate-write assignment now share one classification
  (`inheritance.validate_write_assignment`): a primary-key or framework-owned
  (version) target is rejected, and a scalar value must conform to its
  declared neutral type, identically on both the typed and engine/serialized
  paths. The conformance engine's materializing-pair check now compares the
  preceding find's canonical operation against the write's own target
  predicate, not just the entity. Stale prose (a "predicate writes await
  increment 5" framing, and the now-removed `handle.predicate_write_refusal`
  name) was freshened in `GUIDE.md` itself, `conformance/sweep.py`, and
  `test_compile_sweep.py`. Round-6 pins strengthened: the bare-statement
  guard now has a behavioral (not just `is_bare()`) pin, and the
  materializing-terminate pin covers multiple resolved rows, in order, under
  both concurrency modes. Measured post-round: `just oracle-test` 1456
  passed (real Postgres + MariaDB, `m-value-object-047` green); unit lane
  1928 passed / 87 skipped (+11 new pins); compile-sweep 217 passed / 87
  skipped (unchanged — the 047 close is run-only, no compile emission
  changed); combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 409
  passed / 0 skipped (`m-value-object-047` and `m-opt-lock-001` exercised and
  green); rejected sweep 39 passed / 0 skipped (unchanged); API-suite
  partition exact over 311 active cases (48 exercised / 263 reasoned-skip,
  unchanged); `just python-static` exit 0 (diff-cover 100%,
  Pyright/coverage clean); `gen-usage-guide --check` exit 0; `just lint`
  exit 0; `just core-dep-graph` 311/333/197 (unchanged).
- **Phase 8 increments 6–7, the increment-7 completion round, and the
  checkpoint-4 remediation.** Increment 6 (the case-driven
  `when.concurrency` rounds runner, interleaved `uow` groups, the D-17
  boundary runner) and increment 7 part 1 (D-20 scoped entity registries;
  the Supplier/Branch/Contact/Shipment, Person/Passport, and animal-owner
  mirrors; D-22 typed per-variant instances through `db.find`; the typed
  temporal window verbs) landed through their own externally-reviewed
  cycles. The completion round landed: per-story clock control for
  `WriteStory` (ledger D-29); the audit-only chain-update observed-payload
  fix (D-30); axis-attribute construction optionality plus
  `tx.insert_until` (D-31); the typed-verb story build-out with
  instance-native physical-column grading, `_as_rows` retired (D-23;
  `WRITE_STORIES` 10 → 23); the spec §3 stale-web-edit recipe, both
  variants, with public-verb negative pins, Docker-free unit halves, and
  Usage-Guide recipe rendering; the Customer/Location/Depot mirror family
  (descriptor no-drift over 12 families; 10 of its 13 cases flipped —
  `m-value-object-025/-026/-027` stay reasoned-skipped on the
  value-object write-serialization gap, ledger D-33); the five
  `m-db-error` two-session concurrency cases flipped case-driven through
  the rounds runner (D-28); the 15 branch-introduced Pyright suppressions
  removed by restructuring (110 → 95). The checkpoint-4 review's findings
  were remediated in-cycle: keyed temporal update/terminate now require a
  transaction-scoped observation (`UnobservedMilestoneError`, with a
  same-transaction-insert exemption) and the `m-audit-write-003` story
  observes before closing; every corpus verification read routes through
  the YAML 1.2 loader; the Customer graph-story runners are parameterized;
  the recipes render in the guide. Measured post-remediation: unit lane
  2188 passed / 97 skipped; compile sweep 222 passed / 97 skipped
  byte-identical; rejected sweep 39 / 0; combined Docker lane 549 passed /
  0 skipped; API-suite partition exact over 311 active cases (94
  exercised / 217 reasoned-skip); suppressions 95; `just python-static`
  exit 0 (Pyright 0/0/0, diff-cover 100%); `gen-usage-guide --check`
  exit 0.
- **Phase-9 ledger sweep, chunk 1: the D-33 value-object write-serializer
  fix.** `to_document` now omits a value object's unset OPTIONAL inner
  members (`full_row`'s own `model_fields_set` filtering, mirrored
  recursively into nested value objects and `tuple[VOClass, ...]`
  elements); `m-value-object-025/-026/-027` flip from reasoned-skip to
  exercised (three new `CUSTOMER_REGISTRY`-scoped Customer write stories),
  closing the Customer family at 13 of 13. Measured post-fix: unit lane
  2196 passed / 97 skipped (+8: 5 `to_document` pins, 3 new write-no-drift
  stories); compile sweep 222 passed / 97 skipped, byte-identical (the
  three flips exercise no case in the compile sweep's own reviewed set);
  rejected sweep 39 / 0 (unchanged); API-suite partition exact over 311
  active cases (97 exercised / 214 reasoned-skip, `stale_skip_reasons`
  empty); suppressions 95; `just python-static` steps green individually
  (Pyright 0/0/0, ruff clean, diff-cover 100%); `gen-usage-guide --check`
  exit 0 (regenerated: the three new stories render); combined Docker
  lane (`conformance`/`provider_contract`/`adapter_smoke`/
  `api_conformance`) 555 passed / 0 skipped (+6: the three new stories
  through both the real-Postgres `test_story_run.py` runner and the
  fake-port `test_write_no_drift.py` no-drift guard).
- **D-33 review remediation.** External review of the D-33 fix returned one
  should-fix: `to_document`'s docstring claimed a required member always
  renders because construction cannot succeed without the caller setting it —
  false under `parallax.conformance.vo_models`'s own deliberate design
  (descriptor-required inner members stay Python-optional so `validate_write`,
  never Pydantic, refuses an incomplete instance). The docstring is corrected
  to state the resolved contract (filtering is by `model_fields_set` alone,
  regardless of descriptor nullability; `validate_write` classifies an omitted
  required member, naming `write-required-attribute-missing` /
  `write-required-value-object-missing`), and three regression pins joined the
  existing five D-33 pins: `to_document(ContactGeo())`/`CustomerGeo()` both
  `== {}` as INTENDED, an explicitly-set required member at its own default
  value still rendering, and the `to_document` → `validate_write` pipeline
  classifying a structurally-incomplete `Contact` instance to the
  `m-value-object-039` corpus-pinned rule. No emission change. Measured
  post-fix: unit lane 2199 passed / 97 skipped (+3); compile sweep 222 passed
  / 97 skipped, byte-identical; rejected sweep 39 / 0 (unchanged); all 26
  write stories green; API-suite partition exact over 311 active cases (97
  exercised / 214 reasoned-skip, `stale_skip_reasons` empty); suppressions 95;
  `just python-static` steps green individually (Pyright 0/0/0, ruff clean,
  diff-cover 100%); `gen-usage-guide --check` exit 0 (unchanged — no new
  public-surface renders); combined Docker lane
  (`conformance`/`provider_contract`/`adapter_smoke`/`api_conformance`) 555
  passed / 0 skipped (unchanged).

## Blockers

- Docker is required for the database-backed lanes (`just python-verify` /
  the `python-database` CI job); the database-free lane (`just python-static`,
  which now includes `-m dialect` and `-m compile_sweep`) needs no Docker.
