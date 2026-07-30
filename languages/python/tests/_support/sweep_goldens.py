"""The corpus cases the compile and run sweeps grade against authored goldens.

Membership of a set here is the claim that the named cases' emitted SQL and binds
equal the case's own ``postgres`` golden byte for byte; the two readers below are
how both sweeps read that golden. Both sweeps grade the same claim, so the sets
and the readers are surface-neutral rather than owned by either.
"""

from __future__ import annotations

from typing import Any, Final, cast

from _support.corpus import case_document
from parallax.conformance import case_format, engine

# Reachable read cases whose golden projection and predicate are supported by
# the current compiler.
#
# Scalar round-trip + quoted-reserved-identifier reads.
_SCALAR_READS: Final[frozenset[str]] = frozenset({"m-core-001", "m-descriptor-001"})
# Value-object nested-predicate reads (row-form — the values lane; slot 4 omitted).
_VALUE_OBJECT_PREDICATE_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 48, 49, 54, 55)
)
# To-many value-object array-traversal reads (`m-sql`, "To-many — exists /
# notExists and any-element predicates"): guarded-unnest correlated `EXISTS`/`NOT EXISTS`
# (bare non-empty/empty-or-absent, and same-element scoped `where`) and the flat
# any-element `nested*` forms crossing customer.yaml's `address.phones` — row-form,
# compiled and run below.
_VALUE_OBJECT_TO_MANY_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (*range(15, 23), *range(50, 54), *range(56, 66))
)
# Orders op-algebra reads use the full declared scalar projection emitted by
# the default find projection. Case 028 is intentionally absent from the corpus.
_ORDERS_OP_ALGEBRA_READS: Final[frozenset[str]] = frozenset(
    f"m-op-algebra-{n:03d}" for n in (*range(1, 28), *range(29, 39))
)
# Value-object instance-form materialization reads (the object lane): the slot-4
# document splice projects the `address` column (m-sql *Read projection*). Their graph
# *observation* requires materialization, so these cases compile here and execute
# in the run sweep.
_VALUE_OBJECT_MATERIALIZATION_READS: Final[frozenset[str]] = frozenset(
    {"m-value-object-023", "m-value-object-024"}
)
# Temporal reads (`m-temporal-read`): the as-of predicate is
# auto-injected by m-temporal-read (default-latest on omitted axes) and m-sql projects
# each axis's interval columns (Valid Time before Transaction Time) from the corpus.
# Audit-only + boundary (001-008) and bitemporal (013-017) are row-form — compiled and
# run below.
_TEMPORAL_READ_ROW_FORM: Final[frozenset[str]] = frozenset(
    f"m-temporal-read-{n:03d}" for n in (*range(1, 9), 13, 14, 15, 16, 17)
)
# Temporal value-object reads: the document rides the owner's milestone (m-value-object
# "Inherited temporality"). Instance-form (assert `then.graph`), so — like the non-
# temporal 023/024 — compile-exercised (slot-4 `address` + injected as-of predicate) but
# executed by the snapshot run sweep rather than this compile-only lane.
_TEMPORAL_VALUE_OBJECT_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (28, 29, 30, 31)
)
# Inheritance-family reads:
# table-per-hierarchy tag-predicate / abstract-superset / narrow / grouped-branch-OR
# reads over payment.yaml and animal.yaml (001-006, 011-017), and table-per-concrete-
# subtype single-concrete + union-all reads over document.yaml (050-053). All row-form
# — compiled and run below.
_INHERITANCE_READS: Final[frozenset[str]] = frozenset(
    f"m-inheritance-{n:03d}" for n in (*range(1, 7), *range(11, 18), 50, 51, 52, 53)
)
# The temporal-composed abstract reads (`m-inheritance-092`/`-093`, tagged both
# `m-inheritance` and `m-temporal-read`) compile and run byte-exact
# (092 degenerates to the plain "abstract root, no tag" case; 093's per-branch as-of
# is just `inner` applied identically to every union-all branch, `m-sql`
# "Temporal abstract reads").
_INHERITANCE_TEMPORAL_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-092", "m-inheritance-093"}
)
# Concrete-target temporal reads over a family whose as-of axes are declared ONLY on
# the root. Temporality is family-wide: `m-inheritance-100` pins `DepositRate`
# Transaction Time
# through the TPCS concrete position, `m-inheritance-101` pins `Bond` Valid Time
# through the TPH concrete position, tag predicate included). Both resolve the
# inherited axis through the family root (the descriptor's declaring entity) exactly as
# `_INHERITANCE_TEMPORAL_READS`'s abstract-root reads do — a strategy/position
# sibling, not a new lowering mechanism — so both compile byte-exact and join here.
_INHERITANCE_CONCRETE_TARGET_TEMPORAL_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-100", "m-inheritance-101"}
)
# Relationship-navigation reads (`m-navigate` / `m-sql`,
# "Joins by navigation"): the 13 row-form correlated-EXISTS/anti-join reads over
# orders.yaml/person.yaml/policy.yaml (to-many, to-one, one-to-one, multi-hop,
# boolean composition, and the temporal-hop propagation pair 018/023, which MUST
# lower byte-identically since m-temporal-read's default-injection rule makes a
# defaulted root indistinguishable from an explicit `asOf(..., now)` one) — all
# row-form, compiled and run below. The 11 deep-fetch-bearing navigate reads
# (012-017/019-022/024) stay out because they declare
# `compileEligibility: run-only` (query-result-dependent), so `compile` answers
# the defined `run-only` envelope, never `ok` — asserted by
# `test_run_only_cases_are_never_compiled`, not this exercised set.
_NAVIGATE_READS: Final[frozenset[str]] = frozenset(
    {f"m-navigate-{n:03d}" for n in (*range(1, 12), 18, 23)}
)
# Polymorphic relationship-navigation reads (m-navigate x m-inheritance): the TPH
# abstract-root/abstract-subtype/narrowed-to-concrete/narrowed-to-abstract-subtype
# hops over animal.yaml (060-063) and the TPCS grouped-OR abstract-root/narrowed
# hops over document.yaml (070-071) — all row-form. The 4 narrowed-deep-fetch
# inheritance reads (065-068) and the 5 path-root-guarded ones (073-077) stay OUT
# of this set for the same declared-run-only reason as the navigate deep-fetch
# reads above; the guarded five are graded end to end by the API suite's own
# executable graph stories (`graph_stories.py`), except -073 and -077, whose
# multi-subtype guards have no idiomatic spelling (`api_suite.CASE_SKIP_REASONS`).
# -110 is -062's bind-order sibling: the same narrowed-to-concrete hop, but with a
# REAL branch predicate, so the subquery carries a user bind AND the injected tag
# guard and their order is observable (m-sql "Grouped branch predicates"). It is
# row-form and compile-eligible exactly as -062 is.
_NAVIGATE_INHERITANCE_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-060", "m-inheritance-061", "m-inheritance-062", "m-inheritance-063"}
    | {"m-inheritance-070", "m-inheritance-071", "m-inheritance-110"}
)
# Milestone-set snapshot reads (`m-snapshot-read`,
# "Milestone-set graphs"): `history` / `asOfRange` compile to a single, pure
# statement — no deep-fetch levels, so no query-result-dependent child binds —
# and stay UNDECLARED (compile-eligible), unlike every other graph-bearing case
# reachable here because only deep-fetch-bearing cases are query-result-dependent.
# Run grades the `then.graphs` observation (per-
# milestone edge-pinned graphs), not `then.rows`, but compile only cares about
# the one golden statement.
_SNAPSHOT_READ_MILESTONE_SET_READS: Final[frozenset[str]] = frozenset(
    {"m-snapshot-read-013", "m-snapshot-read-014"}
)
# Multi-concrete polymorphic instance-form reads:
# the `then.graph` siblings of the row-form abstract-multi-concrete reads above
# (m-inheritance-003/-013/-015/-052), pinning the per-variant node shape
# (own-branch members only, no null sibling padding, plus `familyVariant`)
# `db.find` on an abstract multi-concrete position must eventually produce.
# Every one of the four compiles BYTE-IDENTICAL to its row-form sibling
# (animal.yaml/payment.yaml/document.yaml declare no value objects, so the
# instance-form slot-4 delta is empty): table-per-hierarchy (106-108) always
# does; table-per-concrete-subtype case 109 supports the witnessed VO-free shape.
# A VO-bearing TPCS multi-concrete family retains a narrower refusal because no
# case witnesses it. Runtime graph materialization is covered by the run sweep.
_INHERITANCE_INSTANCE_FORM_GRAPH_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-106", "m-inheritance-107", "m-inheritance-108", "m-inheritance-109"}
)
# The read-lock matrix's four in-slice read cases (`m-read-lock`):
# `m-read-lock-001` is the harness-lane single-
# connection golden — the module's OWN witness for "the default (locking)
# in-transaction object find" (`m-read-lock.md`), so its `when.uow`-free read
# still compiles the locked golden through `engine._read_case_concurrency`'s
# module-scoped default. `m-read-lock-002`/`-003`/`-005` are the
# `api-conformance`-lane runtime matrix (an explicit `when.uow.concurrency`
# locking object-find lock / locking-mode projection-omits-lock / optimistic-
# mode omits-lock): compile-eligible (no `compileEligibility` declared), so
# the compile sweep grades their golden SQL byte-exact here — the SAME lane
# routing precedent `m-snapshot-read-011` already sets (an `api-conformance`-
# lane read whose wire-level SQL the ordinary compile/run lanes still grade,
# the API Conformance Suite proving only the ADDITIONAL runtime-observable
# half no wire comparison can see). `m-read-lock-004` (deep-fetch, tagged
# `m-op-list`) and `m-read-lock-009` (MariaDB) stay OUT of slice
# (`slices.md`), never reaching `_REACHABLE` at all.
_READ_LOCK_READS: Final[frozenset[str]] = frozenset(
    {"m-read-lock-001", "m-read-lock-002", "m-read-lock-003", "m-read-lock-005"}
)
# The descriptor default-column witness is a compile-eligible instance-form read:
# descriptor ingestion resolves every omitted scalar/document column before SQL
# lowering, which must project the derived physical names byte-exactly.
_DESCRIPTOR_DEFAULT_COLUMN_READS: Final[frozenset[str]] = frozenset({"m-descriptor-002"})
_MATERIALIZATION_KEY_COMPATIBILITY_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-119", "m-inheritance-120"}
)
# The Storage Layout read witnesses: canonical semantic tier order over a shared
# table whose declarations interleave the tiers, and the cross-table position
# branch mapping whose two contributors legally reuse one physical Column
# spelling. Both grade projection ORDER byte-exactly, which is the whole point.
_STORAGE_LAYOUT_READS: Final[frozenset[str]] = frozenset(
    {"m-storage-layout-009", "m-storage-layout-010"}
)
COMPILE_EXERCISED: Final[frozenset[str]] = (
    _SCALAR_READS
    | _VALUE_OBJECT_PREDICATE_READS
    | _VALUE_OBJECT_TO_MANY_READS
    | _ORDERS_OP_ALGEBRA_READS
    | _VALUE_OBJECT_MATERIALIZATION_READS
    | _TEMPORAL_READ_ROW_FORM
    | _TEMPORAL_VALUE_OBJECT_READS
    | _INHERITANCE_READS
    | _INHERITANCE_TEMPORAL_READS
    | _INHERITANCE_CONCRETE_TARGET_TEMPORAL_READS
    | _NAVIGATE_READS
    | _NAVIGATE_INHERITANCE_READS
    | _SNAPSHOT_READ_MILESTONE_SET_READS
    | _INHERITANCE_INSTANCE_FORM_GRAPH_READS
    | _READ_LOCK_READS
    | _DESCRIPTOR_DEFAULT_COLUMN_READS
    | _MATERIALIZATION_KEY_COMPATIBILITY_READS
    | _STORAGE_LAYOUT_READS
)

# Keyed, non-temporal unit-of-work writes graded byte-exact across `m-unit-work`,
# `m-opt-lock`, `m-inheritance`, and `m-pk-gen`: read-your-own-writes, rollback, mixed-op
# flushes, and the FK-ordered writeSequence cases. Each emits its per-step golden DML
# (a scenario find carries the `for share of t0` read-lock suffix). `m-unit-work-008`/
# `-010` (the same-transaction insert-then-update / insert-then-delete coalescing
# witnesses) are compile-exercised through the coalescing machinery. The remaining
# `m-pk-gen` sequence-strategy writeSequence cases (query-result-dependent,
# run-only) stay reasoned-skipped; the optimistic-lock conflict-abort scenario
# (m-opt-lock-012) is `uow`-grouped AND INTERLEAVED (two genuinely concurrent
# sessions) — it is `compileEligibility: run-only` regardless (its version binds
# are query-result-dependent, `_skip_reason`'s own run-only branch classifies
# it, shape-agnostically, before this set is even consulted). Its run-lane entry
# point uses the `Provisioner.peer` seam; see
# `test_run_sweep.py::test_interleaved_uow_group_run_sweep`
# (`engine.run_interleaved_scenario_case`), routed to explicitly rather than
# through this set or `adapter.run_case`.
#
# `m-unit-work-002/005/006/009/012` are excluded because each authors observing
# finds grouped with its
# versioned keyed write(s) into ONE `uow` (m-case-format scenario grouping), so
# the write's version bind is the group's own transaction-scoped observation —
# a QUERY RESULT the compile lane cannot derive (`m-conformance-adapter`
# "Compile eligibility"). All five are declared `compileEligibility: run-only`
# (`query-result-dependent`) and fall through to the shape-agnostic run-only
# skip (`_skip_reason`) instead; `run` (never `compile`) is the only lane that
# grades them (`test_run_sweep.py`'s selector mirrors the read lane's own
# run-only inclusion for write shapes). `-001`/`-011` stay here: both are
# insert-only, so neither ever needed an observation.
_WRITE_SCENARIOS: Final[frozenset[str]] = frozenset(f"m-unit-work-{n:03d}" for n in (1, 8, 10, 11))
# Readless predicate-write scenarios (`m-batch-write`, "Predicate-selected
# readless forms"; ADR 0014's
# unversioned/non-temporal exception): an unversioned, non-temporal target's
# predicate delete/update lowers to exactly ONE statement — no materializing
# read, no equality-elimination pass. `m-batch-write-006` additionally pins
# descriptor-declared column order (SET columns/binds) independent of the
# authored assignment order.
# `m-batch-write-007` widens this set to the valueObject write lane, which was
# in the value-object write lane. It has the same terms as its siblings: one
# statement, no materializing read, and a fully authored golden.
# and it is the only case that grades the DML spelling of a document extraction:
# a readless predicate write must render `jsonb_extract_path_text(address, ?)`, not
# the read lane's `t0.address` (m-sql rule 1's unaliased DML shape). Nothing else in
# the corpus compiles a valueObject predicate through the WRITE lane, so leaving it
# out would leave that rendering ungraded.
_READLESS_PREDICATE_WRITE_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-batch-write-005", "m-batch-write-006", "m-batch-write-007"}
)
# Compile-eligible non-temporal optimistic-locking and key-generation writes:
# versioned advance (m-opt-lock-002), the inheritance-family keyed write family
# (table-per-hierarchy tag derivation/guard, table-per-concrete-subtype own-table
# routing, the deep-chain and sibling-branch create witnesses, the opt-lock x
# inheritance composition pair), the pk-gen `max` strategy (folded into the INSERT),
# and the versioned batched-delete per-key materialize.
_OPT_LOCK_AND_PK_GEN_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-opt-lock-002",
        "m-inheritance-007",
        "m-inheritance-008",
        "m-inheritance-009",
        "m-inheritance-010",
        "m-inheritance-080",
        "m-inheritance-081",
        "m-inheritance-082",
        "m-inheritance-083",
        "m-inheritance-084",
        "m-inheritance-085",
        "m-inheritance-104",
        "m-pk-gen-001",
        "m-pk-gen-002",
        "m-pk-gen-003",
        "m-pk-gen-013",
        "m-batch-write-004",
    }
)
# `m-batch-write-002` is an unversioned Wallet update whose two rows assign non-uniform per-key
# values (`m-batch-write` "Set-based flush": non-uniform values decompose into
# one UPDATE per distinct key, `batch_write.update_collapses`'s own
# uniform-value check). It compiles as two
# independent single-row keyed updates, neither versioned nor pk-gen-managed,
# so neither needs `lower_write`'s multi-row refusal.
#
# Batch-collapse write sequences (`m-batch-write`, "Set-based flush") cover the
# multi-row INSERT and uniform-value
# `IN`-list UPDATE (`m-batch-write-001`), the non-versioned `IN`-list DELETE
# collapse (`m-batch-write-003`, the delete analogue of the multi-row INSERT),
# and the value-object multi-row INSERT collapse (`m-value-object-045`, each
# row's whole `address` document carried as one atomic document bind).
_BATCH_COLLAPSE_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {"m-batch-write-001", "m-batch-write-003", "m-value-object-045"}
)
# `m-core-007` witnesses the decimal(p,s) write BOUNDARY itself (m-core "Decimal
# precision/scale WRITE boundary"): a single-row insert authoring a decimal(18,4)
# value at all four fractional digits (9999.9999). The case YAML necessarily
# authors that value as a wire-spelled Python float; it decodes to a native
# `Decimal` at the case-format ingestion seam before the (coercion-only)
# developer-facing write validator ever sees it. Compile-exercised byte-identical
# here regardless — a keyed write's compile-time lowering never runs value-type
# validation at all (member-name honesty only) — and the SAME case joins the
# Docker run sweep through `WRITE_EXERCISED`, proving end to end that the decode
# keeps this authored decimal write intact against real Postgres.
_DECIMAL_PRECISION_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset({"m-core-007"})
# The physical-composition witnesses (`m-storage-layout`): both concrete variants
# of one shared table (each binding only its own applicable slots while the
# sibling's required column stays null), the two table-per-concrete-subtype
# tables whose distinct members reuse one column spelling, the top-level
# document slot that follows every scalar tier, and the milestone chain proving
# the physical key selects the model key then the Transaction-Time start while
# every domain slot still precedes the temporal slots. Each carries fully
# authored goldens, so compile grades the emitted column list and binds and run
# additionally grades the committed physical rows.
_STORAGE_LAYOUT_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-storage-layout-006",
        "m-storage-layout-007",
        "m-storage-layout-008",
        "m-storage-layout-011",
    }
)
_WRITE_SEQUENCES: Final[frozenset[str]] = (
    frozenset({"m-unit-work-003", "m-unit-work-007", "m-batch-write-002"})
    | _OPT_LOCK_AND_PK_GEN_WRITE_SEQUENCES
    | _BATCH_COLLAPSE_WRITE_SEQUENCES
    | _DECIMAL_PRECISION_WRITE_SEQUENCES
    | _STORAGE_LAYOUT_WRITE_SEQUENCES
)
# The `m-snapshot-read-010` mutate scenario emits no write DML. Its two `find`
# steps' emissions and round trips grade byte-
# exact through the SAME per-step emission machinery `_assert_write_emissions`
# already applies to a keyed scenario's steps (the `mutate` action step
# contributes an empty statement group, `write_golden_statements` above); its
# find-step wire rows equal `expectRows` through `test_write_run_sweep`'s
# existing port-capture grading, proving the mutate step's own zero round trips
# left the re-read observing the UNCHANGED original row (no write-back).
_SNAPSHOT_MUTATE_SCENARIOS: Final[frozenset[str]] = frozenset({"m-snapshot-read-010"})
# Compile-eligible temporal keyed writes (`m-txtime-write` / `m-bitemp-write`): audit-only
# insert/close-and-chain-update/terminate (001-005), the full-bitemporal rectangle
# split and its plain/bounded-insert degenerates (001-003/006-009), the TPH/TPCS
# txtime and bitemporal composition (090/091/094-097), and the value-object
# carry-through witnesses (m-value-object-032/033). The materializing predicate
# forms (m-txtime-write-007/009, m-bitemp-write-010-013), the conflict-shape
# close-only witnesses (run-only, graded by `test_run_sweep.py`), and
# `m-value-object-047` stays skipped here because each such case is
# `compileEligibility: run-only`
# (query-result-dependent, materializing), so `compile` structurally never
# grades them. The run lane exercises all of them, including
# `m-value-object-047`, whose trailing verification is an `asOf` read,
# the same lane every other `asOf` case already lowers) are EXERCISED in the
# RUN lane instead (`test_run_sweep.py`'s own
# `_MATERIALIZING_PREDICATE_WRITE_SCENARIOS_EXERCISED`).
_TEMPORAL_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-txtime-write-001",
        "m-txtime-write-002",
        "m-txtime-write-003",
        "m-txtime-write-004",
        "m-txtime-write-005",
        "m-bitemp-write-001",
        "m-bitemp-write-002",
        "m-bitemp-write-003",
        "m-bitemp-write-006",
        "m-bitemp-write-007",
        "m-bitemp-write-008",
        "m-bitemp-write-009",
        "m-inheritance-090",
        "m-inheritance-091",
        "m-inheritance-094",
        "m-inheritance-095",
        "m-inheritance-096",
        "m-inheritance-097",
        "m-value-object-032",
        "m-value-object-033",
    }
)
# The two same-transaction coalescing SCENARIO witnesses (m-unit-work-008's
# temporal siblings): an insert+update buffer of one new object folds to a
# single final-value INSERT, no close/chain — proven byte-exact the SAME way
# `_WRITE_SCENARIOS` proves the non-temporal coalescing case.
_TEMPORAL_COALESCING_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-txtime-write-008", "m-bitemp-write-014"}
)
# The finite-pin mutation contrast pair (m-bitemp-write / m-temporal-read's
# finite-pin mutation row): `expectError`-bearing api-conformance-lane mutate
# scenarios the engine's own lanes grade — compile emits the find step's golden
# (the mutate contributes nothing, `_SNAPSHOT_MUTATE_SCENARIOS`' own precedent),
# and run additionally grades the `errors` observation (the raised
# `transaction-time-pin-read-only` for `-016`; none for the writable Valid-Time
# pin, `-015`) in `test_run_sweep.test_write_run_sweep`.
_PIN_CONTRAST_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-bitemp-write-015", "m-bitemp-write-016"}
)
WRITE_EXERCISED: Final[frozenset[str]] = (
    _WRITE_SCENARIOS
    | _WRITE_SEQUENCES
    | _SNAPSHOT_MUTATE_SCENARIOS
    | _TEMPORAL_WRITE_SEQUENCES
    | _TEMPORAL_COALESCING_SCENARIOS
    | _READLESS_PREDICATE_WRITE_SCENARIOS
    | _PIN_CONTRAST_SCENARIOS
)


def wire_binds(binds: list[object]) -> list[object]:
    """The bind list in canonical wire form (m-db-port), reconciling an authored `date`
    golden bind with the write-input date *string* the keyed lowering carries verbatim."""
    return [engine.wire_value(b) for b in binds]


def write_golden_statements(case: case_format.Case) -> list[tuple[str, list[object]]]:
    """The ordered golden DML for a write case: a writeSequence's flat `then.statements`,
    or a scenario's per-step `when.scenario[i].statements` flattened in step order.

    A lifecycle **action** step (m-case-format) carries no `statements` key at
    all when it emits no SQL (a snapshot-read `mutate`'s in-memory-only change);
    it contributes an empty group rather than a missing-key error.
    """
    doc = case_document(case)
    if case.shape == "writeSequence":
        groups = [cast("list[dict[str, Any]]", doc["then"]["statements"])]
    else:
        steps = cast("list[dict[str, Any]]", doc["when"]["scenario"])
        groups = [cast("list[dict[str, Any]]", step.get("statements", [])) for step in steps]
    out: list[tuple[str, list[object]]] = []
    for group in groups:
        for entry in group:
            sql: Any = entry["sql"]
            text = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
            out.append((cast("str", text), list(cast("list[object]", entry.get("binds", [])))))
    return out
