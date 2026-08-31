"""As-of temporal-read unit tests (m-temporal-read).

Exercises the injection templates (current-row / containment / range / scan), the
explicit per-dimension selection rule, the Valid-Time-first bitemporal
composition, the milestone edge-pin, and the ``Pin`` / ``Edge`` value model —
independently of the Docker-gated compile/run sweeps. Each injection assertion
compiles the rewritten predicate through ``m-sql`` so the fragment and bind order
are checked against the same canonical form the corpus goldens fix.
"""

from __future__ import annotations

import datetime as dt

import pytest
from _corpus_model_support import model as accepted_model
from _corpus_model_support import target

from parallax.conformance import models
from parallax.core import Edge, Pin, UndeclaredAxisError, deep_fetch
from parallax.core import object_query as oq
from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityMetadata, TemporalDimension
from parallax.core.object_query import LATEST
from parallax.core.predicate import ModelRejectedError
from parallax.core.sql_gen._compile import compile_read
from parallax.core.temporal_read import (
    TemporalReadError,
    inject_as_of,
    milestone_edge,
    milestone_edge_from_members,
    milestone_edge_of,
    query_pin,
    scans_an_axis,
)

_MODELS = models.load_models()
_ACCEPTED = {
    "Balance": accepted_model("balance"),
    "Position": accepted_model("position"),
    "Ledger": accepted_model("ledger"),
    "Order": accepted_model("orders"),
}
BALANCE = target(_ACCEPTED["Balance"], "Balance")
POSITION = target(_ACCEPTED["Position"], "Position")
LEDGER = target(_ACCEPTED["Ledger"], "Ledger")
ORDERS = target(_ACCEPTED["Order"], "Order")

_D = "2024-04-01T00:00:00.000000Z"
_B = "2024-03-01T00:00:00.000000Z"
_P = "2024-02-01T00:00:00.000000Z"


def _instant(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def _query(
    entity: EntityMetadata,
    temporal: dict[oq.TemporalDimension, oq.TemporalSelection] | None = None,
    predicate: oa.PredicateNode | None = None,
    **clauses: object,
) -> oq.ObjectQueryNode:
    return oq.object_query(
        entity.identity,
        predicate if predicate is not None else oa.All(),
        temporal=temporal,
        **clauses,  # pyright: ignore[reportArgumentType] - the caller names real clauses
    )


def _where(
    entity: EntityMetadata,
    temporal: dict[oq.TemporalDimension, oq.TemporalSelection] | None = None,
    predicate: oa.PredicateNode | None = None,
) -> tuple[str, tuple[object, ...]]:
    """Inject the as-of predicate, compile through m-sql, return the WHERE + binds."""
    model = _ACCEPTED[entity.identity.name]
    query = oq.validate_object_query(entity, _query(entity, temporal, predicate), model)
    root = deep_fetch.plan(query, model).root
    statement = compile_read(root, model, POSTGRES).statement
    _, _, where = statement.sql.partition(" where ")
    return where, statement.binds


# --------------------------------------------------------------------------- #
# Single-dimension Transaction-Time-only templates.                            #
# --------------------------------------------------------------------------- #
def test_explicit_latest_injects_the_current_row_predicate() -> None:
    explicit = _where(BALANCE, {"transaction-time": oq.AsOf("latest")})
    assert explicit == ("t0.out_z = ?", ("infinity",))


def test_result_narrowing_survives_temporal_selection_lowering() -> None:
    # Result narrowing is a sibling clause of Temporal Selection, so injection
    # can neither reorder nor demote it into a conjunctive predicate term.
    model = _ACCEPTED["Balance"]
    query = oq.validate_object_query(
        BALANCE,
        _query(BALANCE, {"transaction-time": oq.AsOf("latest")}, narrow_to=("Balance",)),
        model,
    )
    plan = deep_fetch.plan(query, model)
    assert plan.root.narrow_to == (BALANCE.identity,)
    assert plan.root.predicate == oa.Comparison(
        op="eq", attr="parallax.compatibility.Balance.txEnd", value="infinity"
    )


def test_past_instant_is_half_open_containment() -> None:
    where, binds = _where(BALANCE, {"transaction-time": oq.AsOf(_D)})
    assert where == "t0.in_z <= ? and t0.out_z > ?"
    assert binds == (_instant(_D), _instant(_D))


def test_temporal_upper_bound_is_exclusive() -> None:
    # AsOfAxis intervals are uniformly half-open: start inclusive, end exclusive.
    where, _ = _where(
        LEDGER, {"transaction-time": oq.AsOf("2024-06-01T00:00:00.000000Z")}
    )
    assert where == "t0.in_z <= ? and t0.out_z > ?"


def test_as_of_range_overlap_predicate_binds_window_end_first() -> None:
    where, binds = _where(
        BALANCE,
        {
            "transaction-time": oq.AsOfRange(
                start="2024-06-15T00:00:00.000000Z",
                end="2024-07-01T00:00:00.000000Z",
            )
        },
    )
    assert where == "t0.in_z < ? and t0.out_z > ?"
    assert binds == (
        dt.datetime(2024, 7, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 6, 15, tzinfo=dt.UTC),
    )


def test_history_injects_no_term() -> None:
    where, binds = _where(
        BALANCE,
        {"transaction-time": oq.History()},
        oa.Comparison(op="eq", attr="Balance.id", value=1),
    )
    assert where == "t0.bal_id = ?"
    assert binds == (1,)


def test_as_of_composes_after_a_user_predicate() -> None:
    where, binds = _where(
        BALANCE,
        {"transaction-time": oq.AsOf("latest")},
        oa.Comparison(op="eq", attr="Balance.acctNum", value="A"),
    )
    assert where == "t0.acct_num = ? and t0.out_z = ?"
    assert binds == ("A", "infinity")


# --------------------------------------------------------------------------- #
# Bitemporal composition (Valid-Time first, Transaction-Time inner).           #
# --------------------------------------------------------------------------- #
def _bitemporal(
    valid_time: str | None, tx_time: str | None
) -> dict[oq.TemporalDimension, oq.TemporalSelection]:
    selections: dict[oq.TemporalDimension, oq.TemporalSelection] = {}
    if tx_time is not None:
        selections["transaction-time"] = oq.AsOf(tx_time)
    if valid_time is not None:
        selections["valid-time"] = oq.AsOf(valid_time)
    return selections


def test_bitemporal_both_latest() -> None:
    where, binds = _where(POSITION, _bitemporal("latest", "latest"))
    assert where == "t0.thru_z = ? and t0.out_z = ?"
    assert binds == ("infinity", "infinity")


def test_bitemporal_valid_time_past_tx_time_latest() -> None:
    where, binds = _where(POSITION, _bitemporal(_B, "latest"))
    assert where == "t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?"
    assert binds == (_instant(_B), _instant(_B), "infinity")


def test_bitemporal_both_past_reads_valid_time_first() -> None:
    where, binds = _where(POSITION, _bitemporal(_B, _P))
    assert where == "t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?"
    assert binds == (_instant(_B), _instant(_B), _instant(_P), _instant(_P))


def test_preflight_rejects_a_missing_declared_selection_before_injection() -> None:
    with pytest.raises(ModelRejectedError) as excinfo:
        _where(POSITION, _bitemporal(_B, None))
    assert excinfo.value.rule == "temporal-read-dimension-selection-cardinality"


def test_bitemporal_history_scans_both_axes() -> None:
    where, binds = _where(
        POSITION,
        {"transaction-time": oq.History(), "valid-time": oq.History()},
        oa.Comparison(op="eq", attr="Position.id", value=1),
    )
    assert where == "t0.pos_id = ?"
    assert binds == (1,)


# --------------------------------------------------------------------------- #
# Non-temporal identity + validation.                                          #
# --------------------------------------------------------------------------- #
def test_non_temporal_read_is_identity() -> None:
    op = oa.Or(
        operands=(
            oa.Comparison(op="lessThan", attr="Order.qty", value=10),
            oa.Comparison(op="greaterThan", attr="Order.qty", value=25),
        )
    )
    assert inject_as_of(op, {}, ORDERS) is op


def test_result_directives_survive_injection() -> None:
    query = _query(
        BALANCE,
        {"transaction-time": oq.AsOf("latest")},
        order_by=(oq.OrderKey(attr="Balance.id"),),
        limit=2,
    )
    model = _ACCEPTED["Balance"]
    root = deep_fetch.plan(oq.validate_object_query(BALANCE, query, model), model).root
    assert root.limit == 2
    assert root.order_by == (oq.OrderKey(attr="Balance.id"),)
    assert root.predicate == oa.Comparison(
        op="eq", attr="parallax.compatibility.Balance.txEnd", value="infinity"
    )


def test_a_user_predicate_conjoins_with_the_injected_as_of_terms() -> None:
    # The flattening rule the as-of injection and `m-navigate`'s hop composition
    # share: `all` contributes no conjunct, an `and` flattens into the enclosing
    # conjunction, and an `or` is grouped first so the injected term cannot
    # silently re-associate into its weaker binding.
    predicate = oa.Comparison(op="eq", attr="Balance.id", value=1)
    conjunction = oa.And(
        operands=(predicate, oa.Comparison(op="eq", attr="Balance.owner", value="Ada"))
    )
    disjunction = oa.Or(operands=(predicate, oa.Comparison(op="eq", attr="Balance.id", value=2)))
    pin: dict[oq.TemporalDimension, oq.TemporalSelection] = {"transaction-time": oq.AsOf("latest")}
    as_of = oa.Comparison(op="eq", attr="parallax.compatibility.Balance.txEnd", value="infinity")
    assert inject_as_of(oa.All(), pin, BALANCE) == as_of
    assert inject_as_of(predicate, pin, BALANCE) == oa.And(operands=(predicate, as_of))
    assert inject_as_of(conjunction, pin, BALANCE) == oa.And(
        operands=(*conjunction.operands, as_of)
    )
    assert inject_as_of(disjunction, pin, BALANCE) == oa.And(
        operands=(oa.Group(operand=disjunction), as_of)
    )


def test_undeclared_axis_is_rejected() -> None:
    with pytest.raises(TemporalReadError, match="undeclared dimension"):
        inject_as_of(oa.All(), {"valid-time": oq.AsOf("latest")}, BALANCE)


def test_temporal_clause_on_non_temporal_entity_is_rejected() -> None:
    with pytest.raises(TemporalReadError, match="non-temporal entity"):
        inject_as_of(oa.All(), {"transaction-time": oq.AsOf("latest")}, ORDERS)


# --------------------------------------------------------------------------- #
# Edge-pin + Pin / Edge value model.                                           #
# --------------------------------------------------------------------------- #
def test_milestone_edge_reads_each_axis_from_column() -> None:
    row = {
        "from_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    }
    edge = milestone_edge(POSITION, row)
    assert edge.valid_time == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.tx_time == dt.datetime(2024, 4, 1, tzinfo=dt.UTC)


def test_edge_strict_accessor_raises_on_undeclared_axis() -> None:
    edge = milestone_edge(BALANCE, {"in_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC)})
    assert edge.tx_time == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.tx_time_or_none == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.valid_time_or_none is None
    with pytest.raises(UndeclaredAxisError, match="valid_time"):
        _ = edge.valid_time


def test_edge_tx_time_accessor_raises_when_undeclared() -> None:
    edge = Edge(valid_time=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
    with pytest.raises(UndeclaredAxisError, match="tx_time"):
        _ = edge.tx_time


def test_edge_equality_and_hashing() -> None:
    a = Edge(tx_time=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    b = Edge(tx_time=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    c = Edge(tx_time=dt.datetime(2024, 5, 1, tzinfo=dt.UTC))
    assert a == b
    assert a != c
    assert a != "not an edge"
    assert len({a, b, c}) == 2


def test_milestone_edge_on_non_temporal_entity_raises() -> None:
    with pytest.raises(TemporalReadError, match="not a temporal entity"):
        milestone_edge(ORDERS, {})


def test_milestone_edge_rejects_a_non_instant_from_column() -> None:
    with pytest.raises(TemporalReadError, match="not a timestamp instant"):
        milestone_edge(BALANCE, {"in_z": "not-a-datetime"})


def test_the_three_keying_schemes_derive_one_milestones_edge_identically() -> None:
    # One milestone reaches three keying schemes on its way through the system:
    # physical columns as a driver returns them, declared member names as a
    # retained row payload holds them, and Attribute Identities as a materialized
    # node answers in. All three name the SAME milestone, so all three must
    # produce an EQUAL Edge — otherwise a write's evidence could be filed under
    # one coordinate and looked up under another. Equality holds by shared
    # derivation rather than by coincidence: every scheme resolves the axis start
    # values and hands them to one computation.
    valid_start = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    tx_start = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    axes = {axis.dimension: axis for axis in POSITION.declared_as_of_axes}
    starts = {
        axes[TemporalDimension.VALID_TIME].start_attribute: valid_start,
        axes[TemporalDimension.TRANSACTION_TIME].start_attribute: tx_start,
    }

    by_column = milestone_edge(POSITION, {"from_z": valid_start, "in_z": tx_start})
    by_member = milestone_edge_from_members(
        POSITION, {"validStart": valid_start, "txStart": tx_start, "value": "carried"}
    )
    by_identity = milestone_edge_of(POSITION, starts)

    assert by_member == by_column == by_identity


def test_a_member_keyed_edge_normalizes_an_offset_instant_to_utc() -> None:
    # The member-keyed payload carries what the driver returned, which need not be
    # spelled in UTC. Two spellings of one instant name one milestone, so the
    # derived edges are equal and the observation lands in one slot.
    offset = dt.timezone(dt.timedelta(hours=-4))
    shifted = milestone_edge_from_members(
        BALANCE, {"txStart": dt.datetime(2024, 3, 31, 20, tzinfo=offset)}
    )
    assert shifted == milestone_edge_from_members(
        BALANCE, {"txStart": dt.datetime(2024, 4, 1, tzinfo=dt.UTC)}
    )


def test_member_keyed_edge_on_non_temporal_entity_raises() -> None:
    with pytest.raises(TemporalReadError, match="not a temporal entity"):
        milestone_edge_from_members(ORDERS, {"id": 1})


def test_member_keyed_edge_rejects_a_non_instant_member() -> None:
    with pytest.raises(TemporalReadError, match="not a timestamp instant"):
        milestone_edge_from_members(BALANCE, {"txStart": "not-a-datetime"})


def test_pin_reports_only_pinned_axes() -> None:
    pin = Pin(tx_time=LATEST)
    assert pin.tx_time is LATEST
    assert pin.valid_time is None
    assert not pin.is_empty
    assert Pin().is_empty


def test_query_pin_reads_both_bitemporal_axes() -> None:
    pin = query_pin(_query(POSITION, _bitemporal(_B, "latest")), POSITION)
    assert pin.tx_time is LATEST
    assert pin.valid_time == dt.datetime.fromisoformat(_B)


def test_the_temporal_readers_are_unaffected_by_result_narrowing() -> None:
    query = _query(
        POSITION,
        {"transaction-time": oq.History(), "valid-time": oq.AsOf(_B)},
        narrow_to=("Position",),
    )
    assert query_pin(query, POSITION).valid_time == dt.datetime.fromisoformat(_B)
    assert scans_an_axis(query)


def test_query_pin_is_absent_for_a_scanned_asof_range_or_history_axis() -> None:
    # A scan is not a pin (spec §3): `asOfRange` / `history` never set a
    # coordinate, even though `query_pin` still reads them (called
    # unconditionally ahead of the milestone-set/pinned-read branch decision).
    ranged = _query(POSITION, {"transaction-time": oq.AsOfRange(start=_P, end="infinity")})
    assert query_pin(ranged, POSITION) == Pin()

    scanned = _query(POSITION, {"transaction-time": oq.History()})
    assert query_pin(scanned, POSITION) == Pin()


def test_scans_an_axis_sees_a_scan_beside_a_pinned_dimension() -> None:
    # Each dimension carries its own selection, so the WHOLE clause decides:
    # pinning Valid Time beside a Transaction-Time scan still answers a
    # milestone set.
    pinned_over_history = _query(
        POSITION, {"transaction-time": oq.History(), "valid-time": oq.AsOf(_B)}
    )
    assert scans_an_axis(pinned_over_history)

    pinned_over_range = _query(
        POSITION,
        {"transaction-time": oq.AsOfRange(start=_P, end=_D), "valid-time": oq.AsOf("latest")},
    )
    assert scans_an_axis(pinned_over_range)

    both_pinned = _query(POSITION, _bitemporal(_B, "latest"))
    assert not scans_an_axis(both_pinned)
    assert not scans_an_axis(_query(ORDERS))


def test_result_directives_never_hide_a_scan() -> None:
    # Ordering and a cap are siblings of the Temporal Selection clause, so
    # neither can stand between the reader and a scanned dimension.
    query = _query(
        POSITION,
        {"transaction-time": oq.History(), "valid-time": oq.AsOf(_B)},
        order_by=(oq.OrderKey(attr="Position.qty"),),
        limit=5,
    )
    assert scans_an_axis(query)


# Reading a `Pin` or an `Edge` OFF a materialized node is the producing
# lifecycle's question, so `parallax.snapshot.pin_of` / `edge_of` and their
# refusals are pinned by `test_snapshot_inspection.py`. What stays here is the
# lifecycle-neutral value model itself.
def test_edge_is_frozen() -> None:
    # An Edge is hashable, so it must be immutable: reassigning or deleting an
    # axis after construction would silently invalidate any dict/set holding it.
    edge = Edge(tx_time=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
    with pytest.raises(AttributeError, match="frozen"):
        edge._tx_time = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)  # type: ignore[misc] - frozen Edge: reassigning an axis must raise
    with pytest.raises(AttributeError, match="frozen"):
        del edge._valid_time  # type: ignore[misc] - frozen Edge: deleting an axis must raise
