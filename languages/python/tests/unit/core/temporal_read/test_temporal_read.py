"""As-of temporal-read unit tests (m-temporal-read).

Exercises the injection templates (current-row / containment / range / scan), the
explicit per-dimension selection rule, the Valid-Time-first bitemporal
composition, the milestone edge-pin, and the ``Pin`` / ``Edge`` value model —
independently of the Docker-gated compile/run sweeps. Each injection assertion
compiles the rewritten predicate through ``m-sql`` so the fragment and bind order
are checked against the same canonical form the corpus goldens fix.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any, cast

import pytest

from parallax.conformance import models
from parallax.core import Edge, Pin, UndeclaredAxisError, deep_fetch
from parallax.core import object_query as oq
from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeIdentity, EntityMetadata, TemporalDimension
from parallax.core.object_query import LATEST
from parallax.core.object_query._nodes import TemporalDimension as QueryTemporalDimension
from parallax.core.object_query._validated import (
    ValidatedAsOfSelection,
    ValidatedLatestSelection,
    ValidatedObjectQuery,
)
from parallax.core.predicate import ModelRejectedError
from parallax.core.predicate._validated import ValidatedPredicate
from parallax.core.sql_gen._compile import compile_read
from parallax.core.temporal_read import (
    TemporalReadError,
    inject_resolved_as_of,
    milestone_edge_from_members,
    milestone_edge_of,
    scans_validated_axis,
    validated_hop_as_of_terms,
    validated_query_pin,
)
from tests.unit._corpus_model_support import model as accepted_model
from tests.unit._corpus_model_support import target

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
    temporal: dict[QueryTemporalDimension, oq.TemporalSelection] | None = None,
    predicate: oa.PredicateNode | None = None,
    **clauses: object,
) -> oq.ObjectQueryNode:
    return oq.object_query(
        entity.identity,
        predicate if predicate is not None else oa.All(),
        temporal=temporal,
        **clauses,  # pyright: ignore[reportArgumentType] - the caller names real clauses
    )


def _validated(
    entity: EntityMetadata,
    temporal: dict[QueryTemporalDimension, oq.TemporalSelection] | None = None,
    predicate: oa.PredicateNode | None = None,
    **clauses: object,
) -> ValidatedObjectQuery:
    return oq.validate_object_query(
        entity,
        _query(entity, temporal, predicate, **clauses),
        _ACCEPTED[entity.identity.name],
    )


def _where(
    entity: EntityMetadata,
    temporal: dict[QueryTemporalDimension, oq.TemporalSelection] | None = None,
    predicate: oa.PredicateNode | None = None,
) -> tuple[str, tuple[object, ...]]:
    """Inject the as-of predicate, compile through m-sql, return the WHERE + binds."""
    model = _ACCEPTED[entity.identity.name]
    query = _validated(entity, temporal, predicate)
    root = deep_fetch.plan(
        query, model, projection=deep_fetch.ReadProjectionRequest("all", True)
    ).root
    statement = compile_read(root, model, POSTGRES).statement
    _, _, where = statement.sql.partition(" where ")
    return where, statement.binds


def test_temporal_injection_rejects_incomplete_resolved_products() -> None:
    axis = POSITION.declared_as_of_axes[0]
    without_end = cast(
        "EntityMetadata",
        dataclasses.replace(
            cast("Any", POSITION),
            declared_attributes=tuple(
                member
                for member in POSITION.declared_attributes
                if member.identity.name != axis.end_attribute.name
            ),
        ),
    )

    with pytest.raises(TemporalReadError, match="temporal axis member is undeclared"):
        inject_resolved_as_of(
            ValidatedPredicate(oa.All()),
            (ValidatedLatestSelection(axis),),
            without_end,
        )
    with pytest.raises(TemporalReadError, match="not a managed datetime"):
        validated_query_pin((ValidatedAsOfSelection(axis, 1),))
    with pytest.raises(AssertionError):
        inject_resolved_as_of(
            ValidatedPredicate(oa.All()),
            (cast("Any", type("UnknownSelection", (), {"axis": axis})()),),
            POSITION,
        )


def test_hop_temporal_injection_rejects_axes_with_missing_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    axis = POSITION.declared_as_of_axes[0]
    without_end = cast(
        "EntityMetadata",
        dataclasses.replace(
            cast("Any", POSITION),
            declared_attributes=tuple(
                member
                for member in POSITION.declared_attributes
                if member.identity.name != axis.end_attribute.name
            ),
        ),
    )

    class Family:
        @staticmethod
        def entity(_identity: object) -> Any:
            return type("Position", (), {"root": without_end.identity})()

    class Model:
        @staticmethod
        def entity(_identity: object) -> EntityMetadata:
            return without_end

    import parallax.core.inheritance as inheritance_module

    monkeypatch.setattr(
        inheritance_module,
        "view",
        lambda _model: Family(),  # pyright: ignore[reportUnknownArgumentType,reportUnknownLambdaType]
    )
    malformed_model = cast("Any", Model())

    with pytest.raises(TemporalReadError, match="temporal axis member is undeclared"):
        validated_hop_as_of_terms(without_end, malformed_model, {})
    with pytest.raises(TemporalReadError, match="temporal axis member is undeclared"):
        validated_hop_as_of_terms(
            without_end,
            malformed_model,
            {axis.dimension: dt.datetime(2024, 1, 1, tzinfo=dt.UTC)},
        )


def test_temporal_query_validation_reports_an_invalid_wire_coordinate() -> None:
    with pytest.raises(ModelRejectedError) as caught:
        oq.validate_object_query(
            POSITION,
            _query(
                POSITION,
                {
                    "transaction-time": oq.AsOf("not-an-instant"),
                    "valid-time": oq.AsOf("latest"),
                },
            ),
            _ACCEPTED["Position"],
        )

    assert caught.value.rule == "neutral-literal-type-mismatch"


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
    plan = deep_fetch.plan(query, model, projection=deep_fetch.ReadProjectionRequest("all", True))
    assert plan.root.narrow_to == (BALANCE.identity,)
    assert plan.root.validated_predicate.authored == oa.Comparison(
        op="eq", attr="parallax.compatibility.Balance.txEnd", value="infinity"
    )


def test_past_instant_is_half_open_containment() -> None:
    where, binds = _where(BALANCE, {"transaction-time": oq.AsOf(_D)})
    assert where == "t0.in_z <= ? and t0.out_z > ?"
    assert binds == (_instant(_D), _instant(_D))


def test_temporal_upper_bound_is_exclusive() -> None:
    # AsOfAxis intervals are uniformly half-open: start inclusive, end exclusive.
    where, _ = _where(LEDGER, {"transaction-time": oq.AsOf("2024-06-01T00:00:00.000000Z")})
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


@pytest.mark.parametrize("end", [_B, _P], ids=["equal", "reversed"])
def test_serialized_as_of_range_requires_decoded_start_before_end(end: str) -> None:
    query = _query(
        BALANCE,
        {"transaction-time": oq.AsOfRange(start=_B, end=end)},
    )
    with pytest.raises(ModelRejectedError, match="start < end") as caught:
        oq.validate_object_query(BALANCE, query, _ACCEPTED["Balance"])
    assert caught.value.rule == "query-clause-invalid"


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
) -> dict[QueryTemporalDimension, oq.TemporalSelection]:
    selections: dict[QueryTemporalDimension, oq.TemporalSelection] = {}
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
    query = _validated(ORDERS, predicate=op)
    assert inject_resolved_as_of(query.predicate, query.temporal, ORDERS) is query.predicate


def test_result_directives_survive_injection() -> None:
    query = _query(
        BALANCE,
        {"transaction-time": oq.AsOf("latest")},
        order_by=(oq.OrderKey(attr="Balance.id"),),
        limit=2,
    )
    model = _ACCEPTED["Balance"]
    root = deep_fetch.plan(
        oq.validate_object_query(BALANCE, query, model),
        model,
        projection=deep_fetch.ReadProjectionRequest("all", True),
    ).root
    assert root.limit == 2
    assert root.order_by[0].member.identity.name == "id"
    assert root.validated_predicate.authored == oa.Comparison(
        op="eq", attr="parallax.compatibility.Balance.txEnd", value="infinity"
    )


def test_a_user_predicate_conjoins_with_the_injected_as_of_terms() -> None:
    # The flattening rule the as-of injection and `m-navigate`'s hop composition
    # share: `all` contributes no conjunct, an `and` flattens into the enclosing
    # conjunction, and an `or` is grouped first so the injected term cannot
    # silently re-associate into its weaker binding.
    predicate = oa.Comparison(op="eq", attr="Balance.id", value=1)
    conjunction = oa.And(
        operands=(predicate, oa.Comparison(op="eq", attr="Balance.acctNum", value="A"))
    )
    disjunction = oa.Or(operands=(predicate, oa.Comparison(op="eq", attr="Balance.id", value=2)))
    pin: dict[QueryTemporalDimension, oq.TemporalSelection] = {
        "transaction-time": oq.AsOf("latest")
    }
    as_of = oa.Comparison(op="eq", attr="parallax.compatibility.Balance.txEnd", value="infinity")

    def injected(authored: oa.PredicateNode) -> oa.PredicateNode:
        query = _validated(BALANCE, pin, authored)
        return inject_resolved_as_of(query.predicate, query.temporal, BALANCE).authored

    assert injected(oa.All()) == as_of
    assert injected(predicate) == oa.And(operands=(predicate, as_of))
    assert injected(conjunction) == oa.And(operands=(*conjunction.operands, as_of))
    assert injected(disjunction) == oa.And(operands=(oa.Group(operand=disjunction), as_of))


# --------------------------------------------------------------------------- #
# Edge-pin + Pin / Edge value model.                                           #
# --------------------------------------------------------------------------- #
def _starts(entity: EntityMetadata, **values: object) -> dict[AttributeIdentity, object]:
    """``values`` keyed by the start Attribute Identity of each named axis."""
    return {
        axis.start_attribute: values[axis.start_attribute.name]
        for axis in entity.declared_as_of_axes
        if axis.start_attribute.name in values
    }


def test_milestone_edge_reads_each_axis_from_its_start_member() -> None:
    edge = milestone_edge_of(
        POSITION,
        _starts(
            POSITION,
            validStart=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            txStart=dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        ),
    )
    assert edge.valid_time == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.tx_time == dt.datetime(2024, 4, 1, tzinfo=dt.UTC)


def test_edge_strict_accessor_raises_on_undeclared_axis() -> None:
    edge = milestone_edge_of(
        BALANCE, _starts(BALANCE, txStart=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
    )
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
        milestone_edge_of(ORDERS, {})


def test_milestone_edge_rejects_a_non_instant_start_member() -> None:
    with pytest.raises(TemporalReadError, match="not a timestamp instant"):
        milestone_edge_of(BALANCE, _starts(BALANCE, txStart="not-a-datetime"))


def test_the_two_keying_schemes_derive_one_milestones_edge_identically() -> None:
    # One milestone reaches two keying schemes on its way through the system:
    # declared member names as a retained row payload holds them, and Attribute
    # Identities as a materialized node answers in. Both name the SAME
    # milestone, so both must produce an EQUAL Edge — otherwise a write's
    # evidence could be filed under one coordinate and looked up under another.
    # Equality holds by shared derivation rather than by coincidence: each
    # scheme resolves the axis start values and hands them to one computation.
    valid_start = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    tx_start = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    axes = {axis.dimension: axis for axis in POSITION.declared_as_of_axes}
    starts = {
        axes[TemporalDimension.VALID_TIME].start_attribute: valid_start,
        axes[TemporalDimension.TRANSACTION_TIME].start_attribute: tx_start,
    }

    by_member = milestone_edge_from_members(
        POSITION, {"validStart": valid_start, "txStart": tx_start, "value": "carried"}
    )
    by_identity = milestone_edge_of(POSITION, starts)

    assert by_member == by_identity


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


def test_query_pin_reads_both_bitemporal_axes() -> None:
    pin = validated_query_pin(_validated(POSITION, _bitemporal(_B, "latest")).temporal)
    assert pin.tx_time is LATEST
    assert pin.valid_time == dt.datetime.fromisoformat(_B)


def test_the_temporal_readers_are_unaffected_by_result_narrowing() -> None:
    query = _validated(
        POSITION,
        {"transaction-time": oq.History(), "valid-time": oq.AsOf(_B)},
        narrow_to=("Position",),
    )
    assert validated_query_pin(query.temporal).valid_time == dt.datetime.fromisoformat(_B)
    assert scans_validated_axis(query.temporal)


def test_query_pin_is_absent_for_a_scanned_asof_range_or_history_axis() -> None:
    # A scan is not a pin: `asOfRange` / `history` never set a coordinate, even
    # though the pin is still read off them (ahead of the milestone-set /
    # pinned-read branch decision).
    ranged = _validated(BALANCE, {"transaction-time": oq.AsOfRange(start=_P, end=_D)})
    assert validated_query_pin(ranged.temporal) == Pin()

    scanned = _validated(BALANCE, {"transaction-time": oq.History()})
    assert validated_query_pin(scanned.temporal) == Pin()


def test_a_scan_is_seen_beside_a_pinned_dimension() -> None:
    # Each dimension carries its own selection, so the WHOLE clause decides:
    # pinning Valid Time beside a Transaction-Time scan still answers a
    # milestone set.
    pinned_over_history = _validated(
        POSITION, {"transaction-time": oq.History(), "valid-time": oq.AsOf(_B)}
    )
    assert scans_validated_axis(pinned_over_history.temporal)

    pinned_over_range = _validated(
        POSITION,
        {"transaction-time": oq.AsOfRange(start=_P, end=_D), "valid-time": oq.AsOf("latest")},
    )
    assert scans_validated_axis(pinned_over_range.temporal)

    both_pinned = _validated(POSITION, _bitemporal(_B, "latest"))
    assert not scans_validated_axis(both_pinned.temporal)
    assert not scans_validated_axis(_validated(ORDERS).temporal)


def test_result_directives_never_hide_a_scan() -> None:
    # Ordering and a cap are siblings of the Temporal Selection clause, so
    # neither can stand between the reader and a scanned dimension.
    query = _validated(
        POSITION,
        {"transaction-time": oq.History(), "valid-time": oq.AsOf(_B)},
        order_by=(oq.OrderKey(attr="Position.id"),),
        limit=5,
    )
    assert scans_validated_axis(query.temporal)


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
