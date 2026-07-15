"""As-of temporal-read unit tests (m-temporal-read).

Exercises the injection templates (current-row / containment / range / scan), the
default-latest rule on omitted axes, the business-axis-first bitemporal
composition, the milestone edge-pin, and the ``Pin`` / ``Edge`` value model —
independently of the Docker-gated compile/run sweeps. Each injection assertion
compiles the rewritten predicate through ``m-sql`` so the fragment and bind order
are checked against the same canonical form the corpus goldens fix.
"""

from __future__ import annotations

import datetime as dt

import pytest

from parallax.conformance import models
from parallax.core import Edge, Pin, UndeclaredAxisError, edge_of, pin_of
from parallax.core import op_algebra as oa
from parallax.core.descriptor import Entity
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import compile_read
from parallax.core.temporal_read import (
    LATEST,
    TemporalReadError,
    inject_as_of,
    milestone_edge,
    statement_pin,
)

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
_META = {
    "Balance": _MODELS["balance"],
    "Position": _MODELS["position"],
    "Ledger": _MODELS["ledger"],
    "Reservation": _MODELS["reservation"],
    "Order": _MODELS["orders"],
}
BALANCE = _META["Balance"].entity("Balance")
POSITION = _META["Position"].entity("Position")
LEDGER = _META["Ledger"].entity("Ledger")
RESERVATION = _META["Reservation"].entity("Reservation")
ORDERS = _META["Order"].entity("Order")

_D = "2024-04-01T00:00:00+00:00"
_B = "2024-03-01T00:00:00+00:00"
_P = "2024-02-01T00:00:00+00:00"


def _where(op: oa.Operation, entity: Entity) -> tuple[str, tuple[object, ...]]:
    """Inject the as-of predicate, compile through m-sql, return the WHERE + binds."""
    injected = inject_as_of(op, entity)
    statement = compile_read(injected, _META[entity.name], POSTGRES, entity.name)
    _, _, where = statement.sql.partition(" where ")
    return where, statement.binds


# --------------------------------------------------------------------------- #
# Single-axis (audit-only / business-only) templates + default injection.      #
# --------------------------------------------------------------------------- #
def test_default_latest_injection_equals_explicit_now() -> None:
    # Omitting the axis defaults it to the current milestone (out_z = infinity), and
    # an explicit `asOf(..., now)` lowers to the IDENTICAL injected predicate.
    defaulted = _where(oa.All(), BALANCE)
    explicit = _where(
        oa.AsOf(operand=oa.All(), as_of_attr="Balance.processingDate", date="now"), BALANCE
    )
    assert defaulted == ("t0.out_z = ?", ("infinity",))
    assert explicit == defaulted


def test_past_instant_is_half_open_containment() -> None:
    where, binds = _where(
        oa.AsOf(operand=oa.All(), as_of_attr="Balance.processingDate", date=_D), BALANCE
    )
    assert where == "t0.in_z <= ? and t0.out_z > ?"
    assert binds == (_D, _D)


def test_inclusive_upper_bound_uses_gte() -> None:
    # Ledger declares toIsInclusive: true, so the closed interval injects `>=`.
    where, _ = _where(
        oa.AsOf(
            operand=oa.All(), as_of_attr="Ledger.processingDate", date="2024-06-01T00:00:00+00:00"
        ),
        LEDGER,
    )
    assert where == "t0.in_z <= ? and t0.out_z >= ?"


def test_as_of_range_overlap_predicate_binds_window_end_first() -> None:
    where, binds = _where(
        oa.AsOfRange(
            operand=oa.All(),
            as_of_attr="Balance.processingDate",
            from_="2024-06-15T00:00:00+00:00",
            to="2024-07-01T00:00:00+00:00",
        ),
        BALANCE,
    )
    assert where == "t0.in_z < ? and t0.out_z > ?"
    assert binds == ("2024-07-01T00:00:00+00:00", "2024-06-15T00:00:00+00:00")


def test_history_injects_no_term() -> None:
    where, binds = _where(
        oa.History(
            operand=oa.Comparison(op="eq", attr="Balance.id", value=1),
            as_of_attr="Balance.processingDate",
        ),
        BALANCE,
    )
    assert where == "t0.bal_id = ?"
    assert binds == (1,)


def test_as_of_composes_after_a_user_predicate() -> None:
    where, binds = _where(
        oa.AsOf(
            operand=oa.Comparison(op="eq", attr="Balance.acctNum", value="A"),
            as_of_attr="Balance.processingDate",
            date="now",
        ),
        BALANCE,
    )
    assert where == "t0.acct_num = ? and t0.out_z = ?"
    assert binds == ("A", "infinity")


def test_business_only_default_now() -> None:
    where, binds = _where(oa.All(), RESERVATION)
    assert where == "t0.thru_z = ?"
    assert binds == ("infinity",)


# --------------------------------------------------------------------------- #
# Bitemporal composition (business-axis-first, processing inner).              #
# --------------------------------------------------------------------------- #
def _bitemporal(business: str | None, processing: str | None) -> oa.Operation:
    op: oa.Operation = oa.All()
    if processing is not None:
        op = oa.AsOf(operand=op, as_of_attr="Position.processingDate", date=processing)
    if business is not None:
        op = oa.AsOf(operand=op, as_of_attr="Position.businessDate", date=business)
    return op


def test_bitemporal_both_now() -> None:
    where, binds = _where(_bitemporal("now", "now"), POSITION)
    assert where == "t0.thru_z = ? and t0.out_z = ?"
    assert binds == ("infinity", "infinity")


def test_bitemporal_business_past_processing_now() -> None:
    where, binds = _where(_bitemporal(_B, "now"), POSITION)
    assert where == "t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?"
    assert binds == (_B, _B, "infinity")


def test_bitemporal_both_past_reads_business_axis_first() -> None:
    where, binds = _where(_bitemporal(_B, _P), POSITION)
    assert where == "t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?"
    assert binds == (_B, _B, _P, _P)


def test_bitemporal_omitted_processing_defaults_to_now() -> None:
    where, binds = _where(_bitemporal(_B, None), POSITION)
    assert where == "t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?"
    assert binds == (_B, _B, "infinity")


def test_bitemporal_history_scans_both_axes() -> None:
    op = oa.History(
        operand=oa.History(
            operand=oa.Comparison(op="eq", attr="Position.id", value=1),
            as_of_attr="Position.processingDate",
        ),
        as_of_attr="Position.businessDate",
    )
    where, binds = _where(op, POSITION)
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
    assert inject_as_of(op, ORDERS) is op


def test_directives_survive_injection() -> None:
    op = oa.Limit(
        operand=oa.OrderBy(operand=oa.All(), keys=(oa.OrderKey(attr="Balance.id"),)), count=2
    )
    injected = inject_as_of(op, BALANCE)
    assert isinstance(injected, oa.Limit)
    assert isinstance(injected.operand, oa.OrderBy)
    # The as-of predicate is injected UNDER the peeled directives.
    assert injected.operand.operand == oa.Comparison(
        op="eq", attr="Balance.processingTo", value="infinity"
    )


def test_double_pin_is_rejected() -> None:
    op = oa.AsOf(
        operand=oa.AsOf(operand=oa.All(), as_of_attr="Balance.processingDate", date="now"),
        as_of_attr="Balance.processingDate",
        date=_D,
    )
    with pytest.raises(TemporalReadError, match="pinned or scanned twice"):
        inject_as_of(op, BALANCE)


def test_undeclared_axis_is_rejected() -> None:
    op = oa.AsOf(operand=oa.All(), as_of_attr="Balance.businessDate", date="now")
    with pytest.raises(TemporalReadError, match="undeclared axis"):
        inject_as_of(op, BALANCE)


def test_temporal_clause_on_non_temporal_entity_is_rejected() -> None:
    op = oa.AsOf(operand=oa.All(), as_of_attr="Order.processingDate", date="now")
    with pytest.raises(TemporalReadError, match="non-temporal entity"):
        inject_as_of(op, ORDERS)


# --------------------------------------------------------------------------- #
# Edge-pin + Pin / Edge value model.                                           #
# --------------------------------------------------------------------------- #
def test_milestone_edge_reads_each_axis_from_column() -> None:
    row = {
        "from_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    }
    edge = milestone_edge(POSITION, row)
    assert edge.business == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.processing == dt.datetime(2024, 4, 1, tzinfo=dt.UTC)


def test_edge_strict_accessor_raises_on_undeclared_axis() -> None:
    edge = milestone_edge(BALANCE, {"in_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC)})
    assert edge.processing == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.processing_or_none == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert edge.business_or_none is None
    with pytest.raises(UndeclaredAxisError, match="business"):
        _ = edge.business


def test_edge_business_only_axis_leaves_processing_undeclared() -> None:
    edge = milestone_edge(RESERVATION, {"from_z": dt.datetime(2024, 3, 1, tzinfo=dt.UTC)})
    assert edge.business == dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    assert edge.processing_or_none is None
    with pytest.raises(UndeclaredAxisError, match="processing"):
        _ = edge.processing


def test_edge_equality_and_hashing() -> None:
    a = Edge(processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    b = Edge(processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    c = Edge(processing=dt.datetime(2024, 5, 1, tzinfo=dt.UTC))
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


def test_directive_distinct_survives_injection() -> None:
    injected = inject_as_of(oa.Distinct(operand=oa.All()), BALANCE)
    assert isinstance(injected, oa.Distinct)
    assert injected.operand == oa.Comparison(op="eq", attr="Balance.processingTo", value="infinity")


def test_pin_reports_only_pinned_axes() -> None:
    pin = Pin(processing=LATEST)
    assert pin.processing is LATEST
    assert pin.business is None
    assert not pin.is_empty
    assert Pin().is_empty


def test_statement_pin_reads_both_bitemporal_axes() -> None:
    op = oa.AsOf(
        operand=oa.AsOf(operand=oa.All(), as_of_attr="Position.businessDate", date=_B),
        as_of_attr="Position.processingDate",
        date="now",
    )
    pin = statement_pin(op, POSITION)
    assert pin.processing is LATEST
    assert pin.business == dt.datetime.fromisoformat(_B)


def test_statement_pin_is_absent_for_a_scanned_asof_range_or_history_axis() -> None:
    # A scan is not a pin (spec §3): `AsOfRange` / `History` never set a
    # coordinate, even though `statement_pin` still walks through them (called
    # unconditionally ahead of the milestone-set/pinned-read branch decision).
    ranged = oa.AsOfRange(
        operand=oa.All(), as_of_attr="Position.processingDate", from_=_P, to="infinity"
    )
    assert statement_pin(ranged, POSITION) == Pin()

    scanned = oa.History(operand=oa.All(), as_of_attr="Position.processingDate")
    assert statement_pin(scanned, POSITION) == Pin()


class _TemporalNode:
    """A stand-in for a Phase-7 materialized node carrying its attached coordinates."""

    __parallax_edge__: Edge
    __parallax_pin__: Pin

    def __init__(self, edge: Edge, pin: Pin) -> None:
        self.__parallax_edge__ = edge
        self.__parallax_pin__ = pin


class _PlainNode:
    """A node with no temporal coordinates (non-temporal / unmaterialized)."""


def test_edge_of_and_pin_of_read_materialized_coordinates() -> None:
    edge = Edge(processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    pin = Pin(processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    node = _TemporalNode(edge, pin)
    assert edge_of(node) is edge
    assert pin_of(node) is pin

    with pytest.raises(TemporalReadError, match="materialized temporal node"):
        edge_of(_PlainNode())
    with pytest.raises(TemporalReadError, match="no temporal pin"):
        pin_of(_PlainNode())


def test_edge_is_frozen() -> None:
    # An Edge is hashable, so it must be immutable: reassigning or deleting an
    # axis after construction would silently invalidate any dict/set holding it.
    edge = Edge(processing=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
    with pytest.raises(AttributeError, match="frozen"):
        edge._processing = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)  # type: ignore[misc]
    with pytest.raises(AttributeError, match="frozen"):
        del edge._business  # type: ignore[misc]
