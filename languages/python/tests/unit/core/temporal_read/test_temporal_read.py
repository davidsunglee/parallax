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
import gc
from collections.abc import Iterator
from typing import Any, cast

import pytest

from parallax.conformance import models
from parallax.core import Edge, Pin, UndeclaredAxisError, deep_fetch, inheritance
from parallax.core import object_query as oq
from parallax.core import predicate as oa
from parallax.core.base import INFINITY
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
    FACET_KEY,
    Bitemporal,
    TemporalReadError,
    TemporalShape,
    TimeInterval,
    inject_resolved_as_of,
    milestone_edge,
    scans_validated_axis,
    valid_time_coverage,
    validated_hop_as_of_terms,
    validated_query_pin,
)
from parallax.core.temporal_read import view as temporal_view
from parallax.core.write_plan import PredecessorRow
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


def test_hop_temporal_injection_rejects_axes_with_missing_members() -> None:
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

    facets: dict[object, object] = {
        inheritance.FACET_KEY: Family(),
        FACET_KEY: temporal_view(_ACCEPTED["Position"]),
    }

    class Model:
        @staticmethod
        def facet(key: object) -> object:
            return facets[key]

        @staticmethod
        def entity(_identity: object) -> EntityMetadata:
            return without_end

    malformed_model = cast("Any", Model())

    with pytest.raises(TemporalReadError, match="temporal axis member is undeclared"):
        validated_hop_as_of_terms(without_end, malformed_model, {})
    with pytest.raises(TemporalReadError, match="temporal axis member is undeclared"):
        validated_hop_as_of_terms(
            without_end,
            malformed_model,
            {axis.dimension: dt.datetime(2024, 1, 1, tzinfo=dt.UTC)},
        )


def _undeclared_axes(monkeypatch: pytest.MonkeyPatch, entity: EntityMetadata) -> None:
    """Fail any read of an Entity's declared As-Of Axes."""

    def refuse(declaration: EntityMetadata, *_dimension: object) -> object:
        raise AssertionError(f"{declaration.identity} was asked for its declared axes")

    monkeypatch.setattr(type(entity), "declared_as_of_axes", property(refuse))
    monkeypatch.setattr(type(entity), "as_of_axis", refuse)


@pytest.mark.parametrize("pinned", [False, True], ids=["latest", "pinned"])
def test_hop_terms_at_an_inherited_position_come_from_the_family_shape(
    monkeypatch: pytest.MonkeyPatch, pinned: bool
) -> None:
    model = accepted_model("rate")
    deposit_rate = target(model, "DepositRate")
    root = target(model, "Rate")
    shape = temporal_view(model).shape(deposit_rate.identity)
    assert isinstance(shape, Bitemporal)
    instant = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    pins = (
        {TemporalDimension.VALID_TIME: instant, TemporalDimension.TRANSACTION_TIME: instant}
        if pinned
        else {}
    )
    _undeclared_axes(monkeypatch, deposit_rate)

    terms = validated_hop_as_of_terms(deposit_rate, model, pins)

    members = [
        attribute
        for axis in (shape.valid_time, shape.transaction_time)
        for attribute in (
            (axis.start_attribute, axis.end_attribute) if pinned else (axis.end_attribute,)
        )
    ]
    assert [cast("oa.Comparison", term.authored).attr for term in terms] == [
        f"{root.identity.canonical}.{member.name}" for member in members
    ]
    assert all(
        term.member is root.attribute(member.name)
        for term, member in zip(terms, members, strict=True)
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
    assert explicit == ("t0.out_z = ?", (INFINITY,))


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
    assert binds == ("A", INFINITY)


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
    assert binds == (INFINITY, INFINITY)


def test_latest_terms_bind_managed_infinity_and_publish_its_canonical_literal() -> None:
    model = _ACCEPTED["Position"]
    query = _validated(POSITION, _bitemporal("latest", "latest"))
    injected = inject_resolved_as_of(query.predicate, query.temporal, POSITION)
    hop_terms = validated_hop_as_of_terms(POSITION, model, {})

    for term in (*injected.children, *hop_terms):
        assert cast("oa.Comparison", term.authored).value == "infinity"
        assert term.operands is not None
        assert term.operands.form == "framework"
        assert term.operands.values == (INFINITY,)

    root = deep_fetch.plan(
        query, model, projection=deep_fetch.ReadProjectionRequest("all", True)
    ).root
    statement = compile_read(root, model, POSTGRES).statement
    assert statement.binds == (INFINITY, INFINITY)
    assert statement.wire_binds() == ("infinity", "infinity")
    assert statement.typed_bind_spans == ()


def test_bitemporal_valid_time_past_tx_time_latest() -> None:
    where, binds = _where(POSITION, _bitemporal(_B, "latest"))
    assert where == "t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?"
    assert binds == (_instant(_B), _instant(_B), INFINITY)


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
class _AxisCells:
    """Axis starts and ends one carrier holds by Attribute Identity, answered by
    lookup.

    Every read is recorded, starts and ends apart, and enumeration is refused:
    an edge or a coverage names the axis members it needs rather than scanning
    a row for them.
    """

    def __init__(self, **values: object) -> None:
        self._values = values
        self.reads: list[tuple[str, AttributeIdentity]] = []
        self.end_reads: list[tuple[str, AttributeIdentity]] = []

    def axis_start(self, at: str, attribute: AttributeIdentity, /) -> object:
        self.reads.append((at, attribute))
        return self._values.get(attribute.name, _UNREAD)

    def axis_end(self, at: str, attribute: AttributeIdentity, /) -> object:
        self.end_reads.append((at, attribute))
        return self._values.get(attribute.name, _UNREAD)

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("a milestone edge reads its starts by lookup, never by enumeration")


_UNREAD = object()


def _shape(entity: EntityMetadata) -> TemporalShape:
    shape = temporal_view(_ACCEPTED[entity.identity.name]).shape(entity.identity)
    assert shape is not None
    return shape


def _start(entity: EntityMetadata, dimension: TemporalDimension) -> AttributeIdentity:
    axis = entity.as_of_axis(dimension)
    assert axis is not None
    return axis.start_attribute


def test_a_bitemporal_edge_reads_exactly_its_two_axis_starts() -> None:
    rows = _AxisCells(
        validStart=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        txStart=dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    )
    edge = milestone_edge(_shape(POSITION), rows, "milestone")
    assert edge.valid_time == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.tx_time == dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    assert sorted(rows.reads, key=lambda read: read[1].name) == [
        ("milestone", _start(POSITION, TemporalDimension.TRANSACTION_TIME)),
        ("milestone", _start(POSITION, TemporalDimension.VALID_TIME)),
    ]
    assert rows.end_reads == []


def test_a_transaction_time_edge_reads_one_start_and_declares_no_valid_time() -> None:
    rows = _AxisCells(txStart=dt.datetime(2024, 6, 1, tzinfo=dt.UTC), validStart="never read")
    edge = milestone_edge(_shape(BALANCE), rows, "milestone")
    assert rows.reads == [("milestone", _start(BALANCE, TemporalDimension.TRANSACTION_TIME))]
    assert rows.end_reads == []
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


def test_a_non_temporal_family_has_no_edge_and_reads_nothing() -> None:
    rows = _AxisCells(txStart=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
    with pytest.raises(TemporalReadError, match="Non-Temporal family"):
        milestone_edge(_shape(ORDERS), rows, "milestone")
    assert rows.reads == []


@pytest.mark.parametrize(
    "stored",
    [_UNREAD, None, "2024-06-01T00:00:00Z", dt.date(2024, 6, 1)],
    ids=["missing", "null", "string", "date"],
)
def test_a_start_that_is_not_an_instant_is_refused_under_the_family_roots_name(
    stored: object,
) -> None:
    starts = {} if stored is _UNREAD else {"txStart": stored}
    with pytest.raises(TemporalReadError, match=r"Balance\.txStart: .*not a timestamp instant"):
        milestone_edge(_shape(BALANCE), _AxisCells(**starts), "milestone")


def test_a_bitemporal_edge_refuses_a_missing_valid_time_start() -> None:
    rows = _AxisCells(txStart=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
    with pytest.raises(TemporalReadError, match=r"Position\.validStart"):
        milestone_edge(_shape(POSITION), rows, "milestone")


def test_a_predecessor_row_and_an_identity_keyed_carrier_derive_one_edge() -> None:
    # One milestone reaches two carriers on its way through the system: a
    # retained Predecessor Row holding members by declared name, and a
    # materialized row answering at Attribute Identities. Both name the SAME
    # milestone, so both must produce an EQUAL Edge — otherwise a write's
    # evidence could be filed under one coordinate and looked up under another.
    valid_start = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    tx_start = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    shape = _shape(POSITION)

    by_member = milestone_edge(
        shape,
        PredecessorRow({"validStart": valid_start, "txStart": tx_start, "value": "carried"}),
        None,
    )
    by_identity = milestone_edge(
        shape, _AxisCells(validStart=valid_start, txStart=tx_start), "milestone"
    )

    assert by_member == by_identity == Edge(tx_time=tx_start, valid_time=valid_start)


def test_a_predecessor_rows_edge_normalizes_an_offset_instant_to_utc() -> None:
    # The member-keyed payload carries what the driver returned, which need not be
    # spelled in UTC. Two spellings of one instant name one milestone, so the
    # derived edges are equal and the observation lands in one slot.
    offset = dt.timezone(dt.timedelta(hours=-4))
    shape = _shape(BALANCE)
    shifted = milestone_edge(
        shape, PredecessorRow({"txStart": dt.datetime(2024, 3, 31, 20, tzinfo=offset)}), None
    )
    assert shifted == milestone_edge(
        shape, PredecessorRow({"txStart": dt.datetime(2024, 4, 1, tzinfo=dt.UTC)}), None
    )
    assert shifted.tx_time.tzinfo is dt.UTC


def test_a_predecessor_row_missing_its_start_member_is_refused() -> None:
    with pytest.raises(TemporalReadError, match="not a timestamp instant"):
        milestone_edge(_shape(BALANCE), PredecessorRow({"id": 1}), None)


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


# --------------------------------------------------------------------------- #
# TimeInterval: one half-open value, its relationships, and its extents.       #
# --------------------------------------------------------------------------- #
def _month(month: int, year: int = 2024) -> dt.datetime:
    return dt.datetime(year, month, 1, tzinfo=dt.UTC)


JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG = (_month(month) for month in range(1, 9))


def _open(start: dt.datetime) -> TimeInterval:
    return TimeInterval(start, INFINITY)


def test_an_interval_keeps_the_endpoint_objects_its_owner_supplied() -> None:
    offset = dt.timezone(dt.timedelta(hours=-4))
    start = dt.datetime(2024, 1, 1, 20, tzinfo=offset)
    end = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)

    interval = TimeInterval(start, end)
    opened = _open(start)

    assert interval.start is start
    assert interval.end is end
    assert interval.start.tzinfo is offset
    assert opened.end is INFINITY


@pytest.mark.parametrize("end", [MAR, FEB], ids=["empty", "reversed"])
def test_an_empty_or_reversed_interval_is_refused_with_a_plain_value_error(
    end: dt.datetime,
) -> None:
    with pytest.raises(ValueError, match="start < end") as caught:
        TimeInterval(MAR, end)
    assert not isinstance(caught.value, TemporalReadError)


def test_intervals_are_immutable_values_equal_by_their_endpoints() -> None:
    interval = TimeInterval(JAN, MAR)
    twin = TimeInterval(_month(1), _month(3))

    assert interval == twin
    assert interval != TimeInterval(JAN, APR)
    assert interval != _open(JAN)
    assert _open(JAN) == _open(_month(1))
    assert len({interval, twin, _open(JAN), _open(_month(1))}) == 2
    assert not hasattr(interval, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        interval.end = APR  # type: ignore[misc] - frozen TimeInterval: reassigning an end must raise


_OVERLAPPING_PAIRS = [
    pytest.param(TimeInterval(JAN, MAR), TimeInterval(MAR, JUN), False, id="adjacent"),
    pytest.param(TimeInterval(JAN, MAR), TimeInterval(APR, JUN), False, id="separated"),
    pytest.param(TimeInterval(JAN, APR), TimeInterval(MAR, JUN), True, id="partial"),
    pytest.param(TimeInterval(JAN, JUN), TimeInterval(FEB, MAR), True, id="contained"),
    pytest.param(TimeInterval(JAN, MAR), TimeInterval(JAN, MAR), True, id="equal"),
    pytest.param(_open(JAN), _open(MAR), True, id="both-open"),
    pytest.param(_open(MAR), TimeInterval(JAN, MAR), False, id="open-adjacent"),
    pytest.param(_open(MAR), TimeInterval(JAN, APR), True, id="open-partial"),
]


@pytest.mark.parametrize(("first", "second", "overlapping"), _OVERLAPPING_PAIRS)
def test_overlap_and_disjointness_are_symmetric_complements(
    first: TimeInterval, second: TimeInterval, overlapping: bool
) -> None:
    assert first.overlaps(second) is second.overlaps(first) is overlapping
    assert first.disjoint(second) is second.disjoint(first) is (not overlapping)


def test_meeting_is_directional_adjacency_and_precedence_requires_a_gap() -> None:
    a = TimeInterval(JAN, MAR)
    b = TimeInterval(MAR, JUN)
    c = TimeInterval(APR, JUN)

    assert a.meets(b)
    assert not b.meets(a)
    assert not a.meets(c)
    assert not a.precedes(b)
    assert a.precedes(c)
    assert not c.precedes(a)
    for later in (b, c, _open(JUN), _open(AUG)):
        assert not _open(MAR).meets(later)
        assert not _open(MAR).precedes(later)


def test_point_containment_includes_the_start_and_excludes_the_end() -> None:
    window = TimeInterval(JAN, MAR)

    assert window.contains(JAN)
    assert window.contains(FEB)
    assert not window.contains(MAR)
    assert not window.contains(_month(12, 2023))
    assert _open(MAR).contains(dt.datetime(9999, 12, 31, tzinfo=dt.UTC))
    assert not _open(MAR).contains(FEB)


def test_interval_containment_includes_equal_intervals_and_equal_open_ends() -> None:
    outer = TimeInterval(JAN, JUN)
    inner = TimeInterval(FEB, MAR)

    assert outer.contains(outer)
    assert outer.contains(TimeInterval(_month(1), _month(6)))
    assert outer.contains(inner)
    assert not inner.contains(outer)
    assert not outer.contains(TimeInterval(MAR, JUL))
    assert _open(JAN).contains(_open(MAR))
    assert _open(JAN).contains(_open(_month(1)))
    assert _open(JAN).contains(outer)
    assert not outer.contains(_open(MAR))
    assert not _open(MAR).contains(_open(JAN))


def test_point_probes_are_strict_and_an_open_end_follows_every_instant() -> None:
    window = TimeInterval(MAR, JUN)

    assert window.starts_after(FEB)
    assert not window.starts_after(MAR)
    assert not window.starts_after(APR)
    assert window.ends_after(MAY)
    assert not window.ends_after(JUN)
    assert not window.ends_after(JUL)
    assert _open(MAR).ends_after(dt.datetime.max.replace(tzinfo=dt.UTC))


def test_intersection_shares_no_extent_across_adjacency_or_a_gap() -> None:
    for first, second in (
        (TimeInterval(JAN, MAR), TimeInterval(MAR, JUN)),
        (TimeInterval(JAN, MAR), TimeInterval(APR, JUN)),
        (TimeInterval(JAN, MAR), _open(MAR)),
    ):
        assert first.intersection(second) is None
        assert second.intersection(first) is None


def test_intersection_reuses_an_operand_that_already_is_the_shared_extent() -> None:
    outer = TimeInterval(JAN, JUN)
    inner = TimeInterval(MAR, MAY)
    later_open = _open(MAR)

    assert outer.intersection(inner) is inner
    assert inner.intersection(outer) is inner
    assert _open(JAN).intersection(later_open) is later_open
    assert later_open.intersection(_open(JAN)) is later_open
    assert outer.intersection(TimeInterval(_month(1), _month(6))) == outer


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param(TimeInterval(JAN, MAY), TimeInterval(MAR, JUN), id="finite"),
        pytest.param(_open(MAR), TimeInterval(JAN, MAY), id="open"),
    ],
)
def test_a_partial_intersection_spans_the_later_start_and_the_earlier_end(
    first: TimeInterval, second: TimeInterval
) -> None:
    shared = first.intersection(second)

    assert shared == TimeInterval(MAR, MAY) == second.intersection(first)
    assert shared is not None
    assert shared.start is (first if first.start > second.start else second).start
    assert shared.end is MAY


def test_clipping_narrows_to_its_limits_in_one_extent() -> None:
    window = TimeInterval(JAN, JUN)

    assert window.clipped(end=MAR) == TimeInterval(JAN, MAR)
    assert window.clipped(start=MAR) == TimeInterval(MAR, JUN)
    both = window.clipped(start=MAR, end=MAY)
    assert both == TimeInterval(MAR, MAY)
    assert both is not None
    assert both.start is MAR
    assert both.end is MAY
    assert _open(JAN).clipped(end=MAR) == TimeInterval(JAN, MAR)
    suffix = _open(JAN).clipped(start=MAR)
    assert suffix == _open(MAR)
    assert suffix is not None
    assert suffix.end is INFINITY


def test_clipping_never_extends_and_answers_an_unchanged_interval_itself() -> None:
    window = TimeInterval(JAN, JUN)

    assert window.clipped() is window
    assert window.clipped(start=_month(12, 2023), end=AUG) is window
    assert window.clipped(start=_month(1), end=_month(6)) is window
    opened = _open(JAN)
    assert opened.clipped(start=_month(1)) is opened
    narrowed = window.clipped(start=_month(12, 2023), end=MAR)
    assert narrowed is not None
    assert narrowed.start is JAN


@pytest.mark.parametrize(
    "limits",
    [
        pytest.param({"start": JUN}, id="start-at-end"),
        pytest.param({"start": AUG}, id="start-after-end"),
        pytest.param({"end": JAN}, id="end-at-start"),
        pytest.param({"end": _month(12, 2023)}, id="end-before-start"),
        pytest.param({"start": MAY, "end": MAR}, id="reversed-limits"),
        pytest.param({"start": MAR, "end": MAR}, id="empty-limits"),
    ],
)
def test_clipping_to_nothing_answers_none(limits: dict[str, dt.datetime]) -> None:
    assert TimeInterval(JAN, JUN).clipped(**limits) is None


@pytest.mark.parametrize(
    ("window", "coverage", "uncovered"),
    [
        pytest.param(
            TimeInterval(JAN, JUN),
            [TimeInterval(JAN, MAR), TimeInterval(MAR, JUN)],
            None,
            id="adjacent-cover",
        ),
        pytest.param(
            TimeInterval(JAN, JUN),
            [TimeInterval(JAN, MAR), TimeInterval(APR, JUN)],
            MAR,
            id="gap",
        ),
        pytest.param(TimeInterval(JAN, JUN), [TimeInterval(FEB, JUN)], JAN, id="late-start"),
        pytest.param(TimeInterval(JAN, JUN), [_open(JAN)], None, id="open-cover"),
        pytest.param(TimeInterval(JAN, JUN), [], JAN, id="no-coverage"),
        pytest.param(
            TimeInterval(JAN, JUN),
            [
                TimeInterval(JAN, APR),
                TimeInterval(JAN, APR),
                TimeInterval(FEB, MAR),
                TimeInterval(MAR, MAY),
            ],
            MAY,
            id="duplicate-contained-overlapping",
        ),
        pytest.param(
            TimeInterval(JAN, JUN),
            [TimeInterval(_month(11, 2023), _month(12, 2023)), TimeInterval(_month(12, 2023), JUN)],
            None,
            id="coverage-before-window",
        ),
        pytest.param(
            TimeInterval(JAN, JUN),
            [TimeInterval(JAN, MAR), TimeInterval(JUL, AUG)],
            MAR,
            id="coverage-after-window",
        ),
        pytest.param(
            _open(MAR),
            [TimeInterval(JAN, APR), TimeInterval(APR, JUN)],
            JUN,
            id="open-window-finite-cover",
        ),
        pytest.param(
            _open(MAR), [TimeInterval(JAN, APR), _open(APR)], None, id="open-window-open-cover"
        ),
    ],
)
def test_the_first_uncovered_instant_of_a_window(
    window: TimeInterval, coverage: list[TimeInterval], uncovered: dt.datetime | None
) -> None:
    assert window.first_uncovered(iter(coverage)) == uncovered


class _Consumed:
    """Start-ordered coverage yielded once, counting what was drawn from it."""

    def __init__(self, *coverage: TimeInterval) -> None:
        self._coverage = coverage
        self.drawn = 0
        self._started = False

    def __iter__(self) -> Iterator[TimeInterval]:
        assert not self._started, "coverage is traversed once"
        self._started = True
        for interval in self._coverage:
            self.drawn += 1
            yield interval


def test_the_first_uncovered_instant_is_answered_in_one_pass_that_stops_early() -> None:
    gap = _Consumed(TimeInterval(JAN, MAR), TimeInterval(APR, JUN), TimeInterval(JUN, AUG))
    covered = _Consumed(TimeInterval(JAN, JUL), TimeInterval(JUL, AUG))
    opened = _Consumed(_open(JAN), TimeInterval(MAR, APR))

    assert TimeInterval(JAN, JUN).first_uncovered(gap) == MAR
    assert TimeInterval(JAN, JUN).first_uncovered(covered) is None
    assert TimeInterval(FEB, JUN).first_uncovered(opened) is None
    assert (gap.drawn, covered.drawn, opened.drawn) == (2, 1, 1)


# --------------------------------------------------------------------------- #
# Valid-Time coverage: one checked interval over a carrier's own cells.         #
# --------------------------------------------------------------------------- #
def _end(entity: EntityMetadata, dimension: TemporalDimension) -> AttributeIdentity:
    axis = entity.as_of_axis(dimension)
    assert axis is not None
    return axis.end_attribute


@pytest.mark.parametrize("end", [MAY, INFINITY], ids=["finite", "open"])
def test_bitemporal_coverage_reads_one_valid_time_start_and_end_by_reference(
    end: object,
) -> None:
    start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    rows = _AxisCells(validStart=start, validEnd=end, txStart=JAN, txEnd=INFINITY)

    coverage = valid_time_coverage(_shape(POSITION), rows, "milestone")

    assert coverage is not None
    assert coverage.start is start
    assert coverage.end is end
    assert rows.reads == [("milestone", _start(POSITION, TemporalDimension.VALID_TIME))]
    assert rows.end_reads == [("milestone", _end(POSITION, TemporalDimension.VALID_TIME))]


@pytest.mark.parametrize("entity", [BALANCE, ORDERS], ids=["transaction-time", "non-temporal"])
def test_a_family_without_valid_time_has_no_coverage_and_reads_nothing(
    entity: EntityMetadata,
) -> None:
    rows = _AxisCells(txStart=JAN, txEnd=INFINITY, validStart=JAN, validEnd=INFINITY)

    assert valid_time_coverage(_shape(entity), rows, "milestone") is None
    assert (rows.reads, rows.end_reads) == ([], [])


def test_an_inherited_position_covers_through_its_family_roots_valid_time_axis() -> None:
    model = accepted_model("rate")
    shape = temporal_view(model).shape(target(model, "DepositRate").identity)
    assert isinstance(shape, Bitemporal)
    rows = _AxisCells(validStart=JAN, validEnd=INFINITY)

    assert valid_time_coverage(shape, rows, "milestone") == _open(JAN)
    root = target(model, "Rate").identity
    assert [read[1] for read in (*rows.reads, *rows.end_reads)] == [
        AttributeIdentity(root, "validStart"),
        AttributeIdentity(root, "validEnd"),
    ]


_NOT_ENDPOINTS = [
    pytest.param(_UNREAD, id="missing"),
    pytest.param(None, id="null"),
    pytest.param("2024-06-01T00:00:00.000000Z", id="string"),
    pytest.param(dt.date(2024, 6, 1), id="date"),
]


@pytest.mark.parametrize("stored", _NOT_ENDPOINTS)
def test_a_valid_time_start_that_is_not_an_instant_is_refused_by_name(stored: object) -> None:
    cells = {"validEnd": INFINITY} | ({} if stored is _UNREAD else {"validStart": stored})
    with pytest.raises(TemporalReadError, match=r"Position\.validStart: .*interval endpoint"):
        valid_time_coverage(_shape(POSITION), _AxisCells(**cells), "milestone")


@pytest.mark.parametrize(
    "stored", [*_NOT_ENDPOINTS, pytest.param("infinity", id="literal-infinity")]
)
def test_a_valid_time_end_that_is_neither_an_instant_nor_infinity_is_refused_by_name(
    stored: object,
) -> None:
    cells = {"validStart": JAN} | ({} if stored is _UNREAD else {"validEnd": stored})
    with pytest.raises(TemporalReadError, match=r"Position\.validEnd: .*interval endpoint"):
        valid_time_coverage(_shape(POSITION), _AxisCells(**cells), "milestone")


@pytest.mark.parametrize("end", [MAR, FEB], ids=["empty", "reversed"])
def test_an_empty_or_reversed_stored_coverage_is_refused_by_the_interval(
    end: dt.datetime,
) -> None:
    rows = _AxisCells(validStart=MAR, validEnd=end)
    with pytest.raises(ValueError, match="start < end") as caught:
        valid_time_coverage(_shape(POSITION), rows, "milestone")
    assert not isinstance(caught.value, TemporalReadError)


def test_coverage_is_computed_on_demand_and_retains_only_its_endpoints() -> None:
    rows = _AxisCells(validStart=JAN, validEnd=MAY)

    first = valid_time_coverage(_shape(POSITION), rows, "milestone")
    second = valid_time_coverage(_shape(POSITION), rows, "milestone")

    assert first == second
    assert first is not second
    assert first is not None
    held = [referent for referent in gc.get_referents(first) if referent is not TimeInterval]
    assert sorted(map(id, held)) == sorted((id(JAN), id(MAY)))
