"""Docker-free compile sweep (m-conformance-adapter `compile`, m-sql).

Parametrized from the corpus at runtime over the reachable intersection of the
active slice and implemented module tags. Every case's compile envelope is
schema-validated; the exercised set must emit SQL and binds equal to the case's
``postgres`` golden after normalization, and every other reachable case has an
explicit skip reason. Because read compilation is pure, the refusing port never
sees a row request.

Marked ``unit`` as well as ``compile_sweep``: it is pure, Docker-free, in-process
behaviour, so it contributes to the unit-lane branch-coverage gate and also runs
under ``pytest -m compile_sweep`` in ``python-static``.
"""

from __future__ import annotations

import re
from typing import Any, Final, cast

import jsonschema
import pytest

from conftest import adapter_schema, case_document
from parallax.conformance import adapter, case_format, engine, sweep

pytestmark = [pytest.mark.unit, pytest.mark.compile_sweep]

# Reachable read cases whose golden projection and predicate are supported by
# the current compiler.
#
# Scalar round-trip + quoted-reserved-identifier reads.
_SCALAR_READS: Final[frozenset[str]] = frozenset({"m-core-001", "m-descriptor-001"})
# Value-object nested-predicate reads (row-form — the values lane; slot 4 omitted).
_VALUE_OBJECT_PREDICATE_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
)
# To-many value-object array-traversal reads (`m-sql`, "To-many — exists /
# notExists and any-element predicates"): guarded-unnest correlated `EXISTS`/`NOT EXISTS`
# (bare non-empty/empty-or-absent, and same-element scoped `where`) and the flat
# any-element `nested*` forms crossing customer.yaml's `address.phones` — row-form,
# compiled and run below.
_VALUE_OBJECT_TO_MANY_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in range(15, 23)
)
# Orders op-algebra reads use the full declared scalar projection emitted by
# the default find projection. Case 028 is intentionally absent from the corpus.
_ORDERS_OP_ALGEBRA_READS: Final[frozenset[str]] = frozenset(
    f"m-op-algebra-{n:03d}" for n in (*range(1, 28), 29, 30, 31, 32, 33, 34)
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
# inherited axis through `inheritance.declaring_entity` (the family root) exactly as
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
# hops over document.yaml (070-071) — all row-form. The 3 narrowed-deep-fetch
# inheritance reads (065-067) stay OUT of this set for the same declared-run-only
# reason as the navigate deep-fetch reads above.
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
# one UPDATE per distinct key, `_decomposes_per_row`'s own uniform-value
# check). It compiles as two
# independent single-row keyed updates, neither versioned nor pk-gen-managed,
# so neither needs `lower_write`'s multi-row refusal.
#
# Batch-collapse write sequences (`m-batch-write`, "Set-based flush") cover the
# multi-row INSERT and uniform-value
# `IN`-list UPDATE (`m-batch-write-001`), the non-versioned `IN`-list DELETE
# collapse (`m-batch-write-003`, the delete analogue of the multi-row INSERT),
# and the value-object multi-row INSERT collapse (`m-value-object-045`, each
# row's whole `address` document binding atomically in columnOrder position).
_BATCH_COLLAPSE_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {"m-batch-write-001", "m-batch-write-003", "m-value-object-045"}
)
_WRITE_SEQUENCES: Final[frozenset[str]] = (
    frozenset({"m-unit-work-003", "m-unit-work-007", "m-batch-write-002"})
    | _OPT_LOCK_AND_PK_GEN_WRITE_SEQUENCES
    | _BATCH_COLLAPSE_WRITE_SEQUENCES
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

_REACHABLE = sweep.reachable_cases()
_SCHEMA = adapter_schema()


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


def golden(case: case_format.Case) -> tuple[str, list[object]]:
    then = cast("dict[str, Any]", case_document(case).get("then", {}))
    statements = cast("list[dict[str, Any]]", then.get("statements", []))
    assert len(statements) == 1, case.case_id
    entry = statements[0]
    sql: Any = entry["sql"]
    text: str = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
    binds: Any = entry.get("binds", [])
    if isinstance(binds, dict):
        binds = cast("dict[str, list[object]]", binds)["postgres"]
    return text, list(cast("list[object]", binds))


def _skip_reason(case: case_format.Case, envelope: dict[str, Any]) -> str:
    """The reason a reachable case is not in the compile-exercised set.

    Run-only cases are classified first, independent of shape. Error cases are
    divided between the single-connection run lane and the provider's
    two-connection proof. Remaining non-read shapes receive their write-path
    classification, while unsupported reads report the compiler diagnostic.
    """
    if envelope.get("status") == "run-only":
        # Declared `compileEligibility: run-only` covers query-result-dependent
        # reads, pk-gen sequence reservations, and materializing predicate writes:
        # m-txtime-write-007/009, m-bitemp-write-010..-013, m-opt-lock-014/015,
        # m-value-object-047): `run` (never `compile`) is the ONLY lane that ever
        # grades these — the m-conformance-adapter envelope already answers
        # `run-only` without attempting any lowering at all, so this is classified
        # first, shape-agnostically, before any shape-specific fallback text.
        # `test_run_only_cases_are_never_compiled` asserts the envelope.
        reason = envelope.get("diagnostics", [{}])[0].get("message", "")
        return (
            f"declared compile-run-only ({reason}); graded by run instead (m-conformance-adapter)"
        )
    if case.shape == "error":
        # An error case's trigger DML is authored, not compiled (m-case-format), so
        # neither sub-shape ever joins the compile-exercised set: this is a lane
        # classification. The single-connection statement trigger is graded by the
        # error run lane; the two-connection choreography is
        # run-only and driven by the provider contract proof's barrier-synchronized
        # sessions, which the single-connection adapter lanes cannot hold.
        if engine.eligibility(case) is not None:
            return (
                "two-connection m-db-error choreography (deadlock / lock-wait / "
                "serialization): run-only; the provider contract proof "
                "(test_provider_contract) drives the barrier-synchronized sessions, "
                "not the single-connection adapter lanes"
            )
        return (
            "error-shape trigger DML is authored, not compiled (m-case-format); graded "
            "end-to-end by the error run lane (test_run_sweep.test_error_run_sweep)"
        )
    if case.shape == "boundary":
        # Every boundary case (m-auto-retry / m-opt-lock bounded automatic
        # retry — an injected-fault or loop-configuration loop-mechanics
        # branch) is a
        # declared `api-conformance`-lane assertion the wire golden SQL
        # cannot see (it carries no golden DML at all, m-case-format); the
        # API Conformance Suite verifies it, not `run`.
        return (
            "boundary loop-mechanics case (m-auto-retry/m-opt-lock, api-conformance lane): "
            "verified by the API Conformance Suite's case-driven boundary runner, not by `run`"
        )
    if case.shape in ("scenario", "writeSequence"):
        # The reachable keyed unit-of-work cases are graded above (WRITE_EXERCISED);
        # every run-only case is classified above too. The rest are either REFUSED
        # by the keyed-write lowering (inheritance-family / temporal / opt-lock-
        # unobserved writes, whose forward-error diagnostic names its own deferral
        # or corpus conflict) or lowerable but outside the exercised set.
        if envelope.get("status") == "error":
            message = envelope.get("diagnostics", [{}])[0].get("message", "")
            return f"{case.shape} write refused by the keyed-write lowering: {message}"
        return (
            f"{case.shape} `{case.primary_module}` write outside the reviewed keyed "
            "unit-of-work set (the 9 account/orders cases plus the COR-3 Phase 8 "
            "increment 5 batch/predicate-write flips); not yet a reviewed exercised case"
        )
    if case.shape != "read":
        return f"compile of {case.shape}-shape cases lands with the write path (COR-3 Phase 6/8)"
    message = envelope.get("diagnostics", [{}])[0].get("message", "")
    return f"read lowering deferred past the Phase-5 read path (ledger D-12): {message}"


def _pointer_ok(shape: str, pointer: str) -> bool:
    """Whether an emission ``casePointer`` is well-formed for a write case's shape."""
    if shape == "writeSequence":
        return re.fullmatch(r"/writeSequence/\d+", pointer) is not None
    return re.fullmatch(r"/scenario/\d+/(write|find)", pointer) is not None


def _assert_write_emissions(case: case_format.Case, envelope: dict[str, Any]) -> None:
    """Grade a keyed unit-of-work write case: per-step emissions == the golden DML,
    round trips == ``then.roundTrips``, and every casePointer well-formed for the shape."""
    assert envelope["status"] == "ok", envelope
    golden_statements = write_golden_statements(case)
    assert envelope["roundTrips"] == case_document(case)["then"]["roundTrips"], case.case_id
    emissions = envelope["emissions"]
    assert len(emissions) == len(golden_statements), (case.case_id, emissions, golden_statements)
    for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        assert wire_binds(emission["binds"]) == wire_binds(golden_binds), (case.case_id, emission)
        assert _pointer_ok(case.shape, emission["casePointer"]), (case.case_id, emission)


@pytest.mark.parametrize("case", _REACHABLE, ids=[c.case_id for c in _REACHABLE])
def test_compile_sweep(case: case_format.Case) -> None:
    envelope = adapter.compile_case(case.path, "postgres")
    jsonschema.validate(envelope, _SCHEMA)

    if case.shape == "rejected":
        # A rejected case carries no golden SQL by construction (m-case-format);
        # its run-only status is shape-intrinsic, not authored per-case
        # (`m-conformance-adapter`) — every reachable rejected
        # case answers it, never a silent skip.
        assert envelope["status"] == "run-only", envelope
        assert envelope["diagnostics"][0]["code"] == "compile-run-only", envelope
        return

    if case.case_id in WRITE_EXERCISED:
        _assert_write_emissions(case, envelope)
        return
    if case.case_id not in COMPILE_EXERCISED:
        pytest.skip(_skip_reason(case, envelope))

    assert envelope["status"] == "ok", envelope
    assert envelope["roundTrips"] == 1
    emissions = envelope["emissions"]
    assert len(emissions) == 1
    emission = emissions[0]
    assert emission["casePointer"] == "/operation"
    golden_sql, golden_binds = golden(case)
    assert emission["sql"] == golden_sql
    assert emission["binds"] == golden_binds


def test_exercised_set_is_a_subset_of_the_reachable_reads() -> None:
    reachable_reads = {c.case_id for c in _REACHABLE if c.shape == "read"}
    stale = COMPILE_EXERCISED - reachable_reads
    assert not stale, f"exercised ids outside the reachable read intersection: {sorted(stale)}"


def test_write_exercised_set_is_reachable() -> None:
    reachable = {c.case_id for c in _REACHABLE}
    stale = WRITE_EXERCISED - reachable
    assert not stale, f"write-exercised ids outside the reachable intersection: {sorted(stale)}"


def test_every_unexercised_reachable_read_is_refused() -> None:
    """Every compile-eligible read outside the exercised set is refused.

    A declared run-only read is exempt: its envelope is the defined ``run-only``
    answer, not ``error`` — asserted instead by
    `test_run_only_cases_are_never_compiled`, which every such case must join.
    """
    for case in _REACHABLE:
        if case.shape != "read" or case.case_id in COMPILE_EXERCISED:
            continue
        if engine.eligibility(case) is not None:
            continue
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "error", (case.case_id, envelope)


def test_run_only_cases_are_never_compiled() -> None:
    """A compile on a run-only case returns the defined ``run-only`` answer.

    The reachable set includes run-only `m-db-error` deadlock and lock-wait
    cases, each of which returns ``run-only`` rather than an emitted golden.
    """
    run_only = [c for c in _REACHABLE if engine.eligibility(c) is not None]
    assert run_only, "the reachable intersection now includes run-only m-db-error cases"
    for case in run_only:
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "run-only"
        assert envelope["diagnostics"][0]["code"] == "compile-run-only"


def test_error_and_boundary_lane_partition() -> None:
    """The error and boundary run-lane classification is exact.

    Every reachable error-shape case is EITHER a single-connection statement
    trigger (graded by the error run lane) XOR a two-connection choreography
    (corpus-declared run-only; the provider contract proof drives it) — the
    trigger marker and the run-only declaration must agree, so no error case
    can fall between the lanes. Every reachable boundary case is a declared
    api-conformance-lane case (the API Conformance Suite verifies it) with a
    run-only declaration, so neither adapter lane ever grades one.
    """
    errors = [c for c in _REACHABLE if c.shape == "error"]
    assert errors, "the reachable intersection lost its m-db-error cases"
    for case in errors:
        doc = case_document(case)
        has_choreography = "concurrency" in (doc.get("when") or {})
        declared_run_only = engine.eligibility(case) is not None
        assert has_choreography == declared_run_only, case.case_id
        if not has_choreography:
            assert doc["then"]["statements"], case.case_id
    boundaries = [c for c in _REACHABLE if c.shape == "boundary"]
    assert boundaries, "the reachable intersection lost its boundary case"
    for case in boundaries:
        assert case_document(case).get("lane") == "api-conformance", case.case_id
        assert engine.eligibility(case) is not None, case.case_id


def _actions_all_mutate(case: case_format.Case) -> bool:
    steps = cast("list[dict[str, Any]]", case_document(case).get("when", {}).get("scenario", []))
    actions = [step["action"] for step in steps if "action" in step]
    return bool(actions) and all(action == "mutate" for action in actions)


def test_scenario_lane_dispatch_is_honest() -> None:
    """Every reachable scenario-shape case whose top-level `lane` is
    `api-conformance` and is NOT a mutate-action-only scenario
    (m-snapshot-read-009's `action: access` closed-world witness) answers a
    lane-honest `error` from
    `compile` — the SAME `_boundary_lane_error` precedent, extended to a second
    shape (m-case-format "Case lanes"). It carries NO `compileEligibility`
    declaration (neither closed reason — `single-connection` /
    `query-result-dependent` — honestly describes why; the lane dispatch alone
    is the compile-time refusal), unlike a boundary case's mechanical
    run-only backstop. A MUTATE-action-only one is the exception: the engine
    grades the mutate verb itself — including an `expectError` step through
    the `errors` observation (`m-conformance-adapter`) — so it stays in the
    compile/run lanes as a member of `WRITE_EXERCISED`
    (`_PIN_CONTRAST_SCENARIOS`), graded like every other exercised scenario
    rather than refused.
    """
    lane_dispatched = [
        c
        for c in _REACHABLE
        if c.shape == "scenario" and case_document(c).get("lane") == "api-conformance"
    ]
    refused = [c for c in lane_dispatched if not _actions_all_mutate(c)]
    engine_graded = [c for c in lane_dispatched if _actions_all_mutate(c)]
    assert refused, "the reachable intersection lost its scenario api-conformance-lane case"
    assert engine_graded, "the reachable intersection lost its finite-pin contrast pair"
    for case in refused:
        assert engine.eligibility(case) is None, case.case_id
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "error", (case.case_id, envelope)
        # `run` answers the SAME lane-honest error, never touching a port at all
        # (a `None` port would raise loudly on any attempted use — it never is).
        run_envelope = adapter.run_case(case.path, "postgres", cast("Any", None))
        assert run_envelope["status"] == "error", (case.case_id, run_envelope)
    for case in engine_graded:
        assert case.case_id in WRITE_EXERCISED, case.case_id


def _skip_text(case_id: str) -> str:
    (case,) = [c for c in _REACHABLE if c.case_id == case_id]
    envelope = adapter.compile_case(case.path, "postgres")
    return _skip_reason(case, envelope)


def test_displayed_skip_text_stays_honest_for_a_representative_set() -> None:
    """Pin displayed skip text for representative classification cases.

    This catches vague forward promises and bare diagnostic fragments.
    """
    # `m-batch-write-005` and `-006` compile successfully and belong to
    # `WRITE_EXERCISED` (graded by `_assert_write_emissions` in the
    # main sweep, never by `_skip_text` — a case's exercised-status membership
    # is asserted directly there, not re-derived from skip text here).
    assert {"m-batch-write-005", "m-batch-write-006"} <= WRITE_EXERCISED
    # A materializing predicate-write scenario (query-result-dependent,
    # run-only) is classified BEFORE the shape fallback — never the stale
    # generic scheduling promise.
    materializing_text = _skip_text("m-txtime-write-007")
    assert materializing_text.startswith("declared compile-run-only"), materializing_text
    assert "graded by run instead" in materializing_text, materializing_text
    assert "land with a later write increment" not in materializing_text, materializing_text
    # A write that lowers successfully but sits outside the keyed set names its
    # current classification and does not mention unrelated pk-gen behavior.
    bucket_text = _skip_text("m-core-002")
    assert "outside the reviewed keyed" in bucket_text, bucket_text
    assert "m-pk-gen" not in bucket_text, bucket_text
    assert "land with a later write increment" not in bucket_text, bucket_text


def test_m_opt_lock_001_is_query_result_dependent_run_only() -> None:
    """`m-opt-lock-001` is a query-result-dependent run-only scenario.

    Its observing find, no-op versioned update, and dependent find share one
    unit of work and lock lifetime. The update's license comes from the query
    result, so compile returns the declared run-only envelope and the run lane
    grades the scenario.
    """
    (case,) = [c for c in _REACHABLE if c.case_id == "m-opt-lock-001"]
    assert case.case_id not in WRITE_EXERCISED
    assert engine.eligibility(case) is not None
    envelope = adapter.compile_case(case.path, "postgres")
    assert envelope["status"] == "run-only", envelope
    assert envelope["diagnostics"][0]["code"] == "compile-run-only", envelope
