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
- **Phase 7 increment 2 COMPLETE — inheritance read lowering.** `compile_read`
  (`parallax.core.sql_gen`) lowers both inheritance strategies directly (the
  D-12 refusal is gone): table-per-hierarchy tag-predicate selection (whole
  family → no predicate; one concrete → `=`; several, or any `narrow` → `in`,
  canonical alphabetical order), the abstract-read superset projection
  (ancestry prefix, then each concrete's own block alphabetically, then the
  raw tag column — projected iff `targetEntity` itself is abstract, regardless
  of a narrow's resolved cardinality), grouped branch predicates for a narrow
  nested inside `and`/`or`/`not`/`group`, and table-per-concrete-subtype
  lowering (a single resolved concrete is an ordinary read; two or more lower
  to canonical `union all`, one branch per concrete, each restarting its own
  alias at `t0` and NULL-casting columns it does not own, plus its own
  `familyVariant` literal). `parallax.core.inheritance` gained the shared
  ancestry helpers (`ancestor_chain`, `family_attributes`, `family_root`) both
  `sql_gen` and provisioning reuse — the `m-sql → m-inheritance` edge is legal
  (`modules.md`'s "Notable directions": `m-sql` already reaches `m-inheritance`
  transitively through `m-op-algebra`), confirmed by `lint-imports`. The
  conformance engine (`run_read_case`) materializes `familyVariant` from the
  projected tag column via the family's tag→subtype-name map (table-per-
  hierarchy) or renames the projected literal column (table-per-concrete-
  subtype); a concrete-target (or single-resolved-position table-per-concrete-
  subtype) read carries neither. Provisioning (`provision.py`) now derives
  inheritance-aware DDL and fixture loading: one shared table per
  table-per-hierarchy family (root + every abstract-subtype's own columns,
  every concrete's own columns nullable, plus the tag column) created once,
  and one table per table-per-concrete-subtype concrete carrying its full
  ancestry-derived chain; fixture rows resolve inherited members by name and
  bind a table-per-hierarchy tag column from the concrete's own `tagValue`,
  never a fixture-authored field. The 17 in-slice inheritance reads
  (`m-inheritance-001–006/011–017` over payment.yaml/animal.yaml,
  `-050–053` over document.yaml) flip from reasoned-skip to byte-exact
  compile + row-graded run, and two temporal-composed abstract reads
  (`m-inheritance-092`/`-093`, corpus-commented "Phase 8 temporal composition")
  flip alongside them as an unplanned but verified-correct side effect of the
  lowering being strategy-shaped rather than temporal-aware — leaving them
  silently un-exercised once they answered `ok` would itself be a D-11-style
  gap. Updated counts: unit lane 1273, compile sweep 129 (+19), `pg-full` run
  sweep 114 passed (+19, real Postgres). **Next:** increments 3–4 (navigate
  lowering, to-many value-object array traversal — mutually independent), then
  increment 5 (deep fetch + materialization + graph observations), then
  increment 6 (developer surface + ledger closures).
- **Phase 7 increment 3 COMPLETE — navigate lowering.** `parallax.core.navigate`
  (new scope, filled in from its Phase-1 skeleton) owns per-hop as-of
  canonicalization: `canonicalize(op, meta, root_pins)` walks an already
  root-injected operation and, for every `navigate`/`exists`/`notExists` hop,
  resolves the relationship's target entity and — when it (or its inheritance
  family, resolved through the family root) is temporal — injects the child's
  own per-axis as-of predicate as plain `m-op-algebra` nodes, matched by axis,
  business-first, defaulting to latest whenever the root's own pin
  (`m-temporal-read.resolve_pinned_instants`, a new export alongside
  `inject_as_of`) carries no specific instant for that axis; a navigation-free
  operation is a strict identity. Composed at the engine (`_compile_statement`'s
  new `_canonicalize_read` helper, reused by the scenario-find lowering) and at
  `snapshot/handle.py`'s `Transaction.find`, immediately after `inject_as_of` —
  the M2 precedent. `compile_read` (`parallax.core.sql_gen`) lowers
  `navigate`/`exists`/`notExists` to a correlated `EXISTS`/`not exists`
  semi-join: correlation columns derived mechanically from the relationship's
  `join` predicate (never authored), continuing the single `t0, t1, …` alias
  sequence and bind list across arbitrarily nested hops via a new `_Ctx.
  next_alias`/`.child()` pair; a polymorphic hop reuses increment 2's
  tag-fragment machinery directly (table-per-hierarchy: one `EXISTS` + interior
  tag predicate; table-per-concrete-subtype: a grouped `OR` of one `EXISTS` per
  effective concrete, alphabetical, continuing the same alias sequence).
  `DeepFetch` keeps refusing, its message narrowed to name increment 5
  specifically rather than the whole snapshot branch. The 13 row-form navigate
  reads (`m-navigate-001–011/018/023`, orders/person/policy.yaml — to-many,
  to-one, one-to-one, multi-hop, boolean composition, and the temporal-hop
  propagation pair that must lower byte-identically defaulted vs explicit
  `asOf(..., now)`) and the 6 polymorphic-relationship reads
  (`m-inheritance-060–063` TPH over animal.yaml, `-070–071` TPCS over
  document.yaml) flip from reasoned-skip to byte-exact compile + row-graded
  run; the 11 deep-fetch-bearing navigate reads (`-012–017/019–022/024`) stay
  reasoned-refused (increment 5). `m-navigate` joining `IMPLEMENTED_MODULES`
  also flips 3 rejected cases the model-aware validator already classified in
  increment 1 (`m-inheritance-064/-072` `narrow-outside-relationship-target`,
  `m-value-object-036` `navigate-value-object-target`) — no engine change
  needed, just reachability. `languages/python/spec/python.md` §7 gained
  `m-navigate` in the handle scope's allowed dependencies (already legal
  transitively through `m-snapshot-read → m-deep-fetch → m-navigate`, so
  `check_dag_sync.py --write` produced no contract diff) and prose explaining
  the edge; `tools/check_dag_sync.py`'s `SUPPORT_SCOPE_DEPS` mirrors it.
  Updated counts (measured): unit lane 1326 passed / 70 skipped, compile sweep
  151 passed / 60 skipped (206 parametrized cases total), `pg-full` run sweep
  99 parametrized cases, rejected sweep 32 parametrized cases (22 passed + 10
  `when.write` skipped, +3 over increment 1's baseline), `just python-static`
  and `just python-verify` green (100% branch + 100% diff coverage). **Next:**
  increment 4 (to-many value-object array traversal), then increment 5 (deep
  fetch + materialization + graph observations), then increment 6 (developer
  surface + ledger closures).
- **Phase 7 increment 4 COMPLETE — to-many value-object array-traversal
  lowering.** `compile_read` (`parallax.core.sql_gen`) lowers `nestedExists` /
  `nestedNotExists` and every flat `nested*` predicate crossing a
  `cardinality: many` value-object member (the D-12 refusal is gone for this
  family): a correlated `EXISTS` over a guarded `jsonb_array_elements` unnest,
  continuing increment 3's single `_Ctx.next_alias` sequence. The array-type
  guard (new `Dialect.array_guard`, m-sql's `<arr>` fragment) keeps the strict
  `jsonb_array_elements` from erroring on a non-array `many` value — a NULL
  column, a missing key, a JSON `null`, a JSON scalar, or a JSON object all
  fold to zero elements (m-op-algebra absence collapse) — binding its path
  segments TWICE (the `jsonb_typeof` probe, then the re-extraction). A flat
  predicate crossing a `many` member is **any-element** and self-guards
  independently per predicate (two ANDed flat predicates open two independent
  `EXISTS` subqueries, aliases continuing `t1`, `t2`, …); a scoped
  `nestedExists`/`nestedNotExists` `where` is **same-element** — every element
  predicate in the compound lowers against the SAME unnested alias,
  element-relative (no `Class.valueObject` prefix), reusing the existing
  extraction machinery for the field within the element. Postgres `EXISTS` is
  never NULL, so the negated forms need no `coalesce` wrap (unlike the
  documented-but-unimplemented MariaDB containment form). The 8 in-slice
  corpus reads (`m-value-object-015..-022`, customer.yaml's `address.phones`)
  flip from reasoned-skip to byte-exact compile + row-graded run; no other
  reachable case was gated only on this refusal. Increments 2–4 are now all
  landed. Updated counts (measured): unit lane 1348 passed / 62 skipped,
  compile sweep 159 passed / 52 skipped (+8), `pg-full` run sweep 107
  parametrized read cases (+8, real Postgres), rejected sweep unchanged,
  `just python-static` green (Pyright 0 errors, 100% branch + 100% diff
  coverage) and the Docker `pg-full`/provider/API-conformance lanes green.
  **Next:** increment 5 (deep fetch + materialization + graph observations),
  then increment 6 (developer surface + ledger closures).
- **Phase 7 increment 5 COMPLETE — deep fetch, graph materialization, and the
  graph observation lane.** `parallax.core.deep_fetch` (new scope) is a pure
  planner: `plan(target, op, meta)` walks a `DeepFetch`'s declared paths into a
  trie, deduping on `(relationship hop, effective concrete set)` so a shared
  prefix and equivalent narrowings (`[Pet]` vs `[Cat, Dog]`) converge to one
  level while a broad vs. narrowed hop over the same relationship stay
  distinct; an ancestor-revisit hop is flagged `is_back_reference` (zero
  round trips, resolved by identity instead of a query) and a path may not
  continue past one. It never compiles or executes — `FetchLevel.
  child_operation` only composes the neutral `in`-membership + propagated
  as-of + declared relationship `orderBy` IR a level's own child read needs.
  `parallax.snapshot.materialize` is the one assembler: `decode_row`/
  `identity_key` (family-normalized, PK-keyed, coordinate-omitted — safe
  within one graph's single pin) and `Assembler.attach_level` fan rows back
  to parent nodes (to-many order-preserving, to-one, back-reference
  resolution via the identity map, empty-level short-circuit). Wire
  rendering stays per-view (a fresh `Node` per attach position, never
  cross-view field-sharing) per m-snapshot-read-012's own diamond-position
  contract; the identity map serves only back-reference resolution and
  `identityChecks`. `parallax.snapshot.handle.find`/`find_history` is the
  ONE production find executor (the per-level loop, `1 + L` round trips) —
  the conformance engine and the developer `find` surface both call it, no
  engine-local level loop anywhere. `compile_read` gained a
  `relationship_order` kwarg so a declared relationship `orderBy`'s
  NULLS-last rule applies only to nullable keys, never blanket-applied to
  ordinary reads. The engine wires `run_graph_case`/`run_graphs_case` (single
  and milestone-set snapshot reads), `identityChecks` evaluation by
  JSON-Pointer walk over the pre-truncation graph, cycle-stub truncation on
  the wire, and the scenario `mutate` action (in-memory field update, no
  write-back — `access` stays deferred to the API Conformance Suite, and its
  lane is dispatched out honestly by both compile and run). Twenty-four
  corpus cases (11 `m-navigate` deep-fetch reads, 10 `m-snapshot-read`,
  3 `m-inheritance` narrowed-view reads) are declared
  `compileEligibility: run-only` (query-result-dependent — a child level's
  own IN-list, or whether it executes at all, depends on the parent query's
  result), discovered by running the refusing compile lane first (D-10);
  `m-snapshot-read-009`'s scenario needs no declaration (structurally lane-
  dispatched instead). `m-deep-fetch`/`m-snapshot-read` joined
  `IMPLEMENTED_MODULES`. Updated counts (measured): unit lane 1437 passed / 77
  skipped, compile sweep 164 passed / 67 skipped (231 total), rejected sweep
  unchanged (25 passed / 10 skipped), `pg-full` run sweep 179 passed / 10
  skipped (real Postgres — this increment's core proof), the combined Docker
  database lane (`pg-full`/provider/adapter-smoke/API-conformance) 224 passed
  / 10 skipped, `just oracle-test` 1408 passed. `just python-static` green
  (Pyright 0 errors, every increment-5-owned file at 100% branch coverage,
  100% diff coverage against `origin/main`). **Next:** increment 6 (developer
  surface + ledger closures).
- **Phase 7 increment 6a COMPLETE — public developer surface, D-7 class
  spellings, D-16 verb graduation.** `parallax.snapshot.Snapshot[T]` (spec
  §3/§4): `result()`/`result_or_none()`/`results()`, `pin`, `execution`,
  `__repr__` — no iteration/`len`/truthiness/indexing/refresh/write/lazy
  behavior. `db.find(statement)` / `tx.find(statement)` both wrap the
  increment-5 find/find_history executors and return `Snapshot[Any]` (DQ6);
  `.history()`/`.as_of_range()` combined with `.include()` raises
  `UnsupportedFeatureError` naming `snapshot-history-includes`. Frozen-node
  wrapping (`parallax.snapshot.wrap`) turns a materialized graph into
  instances of the caller's registered entity classes via `model_construct` +
  the `object.__setattr__` backdoor: tuples for to-many/cardinality-many value
  objects, the `UNLOADED` sentinel translated to `UnloadedRelationshipError`
  by the `Rel[T]` data descriptor, polymorphic children as their CONCRETE
  classes, `parallax.core.is_loaded`/`narrowed` for closed-world load-state
  introspection, hashability conditional (never forced). The statement
  frontend gained `.include(*paths)` (chained `Rel[T]` class access,
  hop-level `.narrow(*subtypes)`), `.any()`/`.none()` quantifiers on `Rel`,
  and `Entity.narrow(*subtypes, where=...)` plus the statement-level
  `.narrow(...)` clause — all validated at build time via
  `validate_operation`, never deferred to execution. The D-7 `ValueObject`
  class spelling (frozen, metaclass-light, `Attr[VOClass]` /
  `Attr[tuple[VOClass, ...]]` fields, element-scoped `ElementAttributeExpr`
  expressions, instances-only input policy enforced by a `field_validator`)
  and the D-7 inheritance spelling (DQ2: `parent`/`role` derive from the
  Python class hierarchy, `strategy`/`tag`/`tagValue` thread through
  `EntityConfig(inheritance=FamilyRoot(...)/Concrete(...))`) both proved
  no-drift against their corpus models (customer.yaml; payment.yaml TPH,
  document.yaml TPCS) at the unit level. D-16 graduated to its FULL shape:
  a validating `Entity.model_copy` override builds a Change Record
  (touched field → earliest original across a copy chain, net-zero changes
  tracked but excluded from the effective set); `tx.insert(instance)` /
  `tx.update(edited_copy)` (sparse row, an empty effective change set is a
  true no-op — zero round trips) / `tx.delete(node_or_instance)` replace the
  neutral row-document verb signatures (the conformance engine's own
  `KeyedWrite` path is unaffected; `lower_write`'s Phase-8 refusal set stays
  byte-stable). The API-conformance write stories (`parallax.conformance.
  stories`) now execute the graduated verbs end to end; `tests/api_conformance`
  was touched only as needed to keep it green under the new signatures (a
  `_as_rows` helper renders a `Snapshot[T]`'s wrapped instances back to the
  suite's still-neutral `list[Row]` grading shape) — the full instance-native
  example rework is the next agent's job. Updated counts (measured): unit lane
  1541 passed / 77 skipped, compile sweep unchanged at 164 passed / 67
  skipped (no read-path regression), the combined Docker database lane
  (`pg-full`/provider/adapter-smoke/API-conformance) unchanged at 224 passed /
  10 skipped. `just python-static` green (Pyright 0 errors across production
  AND tests, 100% branch coverage on every file this increment touched, 100%
  diff coverage against `origin/main`); the public-API snapshot
  (`tests/api_surface/public_api.json`) and the usage guide
  (`docs/usage-guide.md`) both regenerated for the new exports. **Next:**
  increment 6b (the example build-out over the graduated instance-native
  surface), then increment 7 (remaining ledger closures).

## Blockers

- None. Docker is required for the database-backed lanes (`just python-verify` /
  the `python-database` CI job); the database-free lane (`just python-static`,
  which now includes `-m dialect` and `-m compile_sweep`) needs no Docker.
