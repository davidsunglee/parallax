"""How an unbroken run of deferred writes forms acquisition spans
(`m-unit-work` *Shared coverage acquisition*), over ranges real settlement
deferred: each span reads alike, names each object once, and holds at most
the span bound."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import replace

import pytest

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import acquisition_spans as spans_module
from parallax.core._execution._unit_work import write_settlement as settlement
from parallax.core._execution._unit_work.acquisition_spans import form_spans
from parallax.core._execution._unit_work.instructions import prepare_wire_write
from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.row_acquisition import CoverageReadKey
from parallax.core._execution._unit_work.write_items import target_write
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.inheritance import inheritance_facet_of
from parallax.core.internal.metamodel import AttributeIdentity
from parallax.core.internal.unit_work import TargetWriteInstruction, WritePlanningRequest
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admitted_writes, deferred_ranges
from tests._support.write_preparation import write_preparation_of
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit.core._shared_coverage_support import ShareCols, ShareDoc, frag, plan

_BALANCE = corpus_model("balance")
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _bitemporal(
    *keys: int,
    entity: type[ShareCols | ShareDoc] = ShareCols,
    concurrency: ConcurrencyPreference = "optimistic",
) -> tuple[DeferredRange, ...]:
    """The deferred range of one Bitemporal write of each object ``keys``
    names, settled in one compilation."""
    writes = [write for key in keys for write in frag(entity, key, 1)]
    return deferred_ranges(plan(writes, concurrency=concurrency))


def _transaction_time_only(*keys: int) -> tuple[DeferredRange, ...]:
    """The deferred range of one Optimistic Transaction-Time-Only target
    amendment of each object ``keys`` names, settled in one compilation."""
    targets = [
        target_write(
            prepare_wire_write(
                TargetWriteInstruction(
                    "amend", "Balance", {"id": key, "value": "9.00"}, if_tx_start=_JAN
                ),
                write_preparation_of(_BALANCE),
            ),
            inheritance_facet_of(_BALANCE),
        )
        for key in keys
    ]
    planned = build_write_planner(bound_model(_BALANCE)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            preference="optimistic",
            composed_writes=admitted_writes(_BALANCE, targets),
        )
    )
    return deferred_ranges(planned)


_SHAPES = pytest.mark.parametrize(
    "settled", [_bitemporal, _transaction_time_only], ids=["bitemporal", "transaction-time-only"]
)


def _formed(ranges: Sequence[DeferredRange]) -> list[tuple[object, ...]]:
    """The objects of each span ``ranges`` form, in order."""
    return [tuple(deferred.key_value for deferred in span.ranges) for span in form_spans(ranges)]


@_SHAPES
@pytest.mark.parametrize(
    ("objects", "sizes"),
    [(1, [1]), (31, [31]), (32, [32]), (33, [32, 1]), (65, [32, 32, 1])],
)
def test_a_run_forms_spans_of_at_most_the_bound(
    settled: Callable[..., tuple[DeferredRange, ...]], objects: int, sizes: list[int]
) -> None:
    ranges = settled(*range(1, objects + 1))
    formed = _formed(ranges)
    assert [len(span) for span in formed] == sizes
    assert [key for span in formed for key in span] == list(range(1, objects + 1))


def test_no_range_forms_no_span() -> None:
    assert _formed(()) == []


@_SHAPES
def test_a_range_of_an_object_the_open_span_holds_starts_the_next_span(
    settled: Callable[..., tuple[DeferredRange, ...]],
) -> None:
    # One compilation settles one range per object, so the repeat is another's.
    first, second = settled(1, 2)
    (repeated,) = settled(2)
    (third,) = settled(3)
    assert _formed((first, second, repeated, third)) == [(1, 2), (2, 3)]


def _keyed_by_label(deferred: DeferredRange) -> DeferredRange:
    """``deferred`` as though its Entity's family were keyed by ``label``."""
    key = deferred.read_key
    label = AttributeIdentity(key.entity.identity, "label")
    read_key = CoverageReadKey(key.entity, label, key.shared_lock)
    return replace(deferred, meaning=replace(deferred.meaning, read_key=read_key))


@pytest.mark.parametrize(
    "different",
    [
        lambda: _bitemporal(3, entity=ShareDoc)[0],
        lambda: _bitemporal(3, concurrency="locking")[0],
        lambda: _keyed_by_label(_bitemporal(3)[0]),
    ],
    ids=["another-entity", "another-lock", "another-key-attribute"],
)
def test_a_range_reading_differently_ends_the_open_span(
    different: Callable[[], DeferredRange],
) -> None:
    first, second = _bitemporal(1, 2)
    later = different()
    assert later.read_key != first.read_key
    (fourth,) = _bitemporal(4)
    assert _formed((first, second, later, fourth)) == [(1, 2), (3,), (4,)]


def test_ranges_reading_alike_share_a_span_whether_or_not_one_read_key_serves_them() -> None:
    (first,) = _bitemporal(1)
    (second,) = _bitemporal(2)
    assert first.read_key == second.read_key
    assert first.read_key is not second.read_key
    assert _formed((first, second)) == [(1, 2)]


def test_a_span_reads_by_its_first_ranges_read_key() -> None:
    (first,) = _bitemporal(1)
    (second,) = _bitemporal(2)
    (span,) = form_spans((first, second))
    assert span.read_key is first.read_key


def test_the_ready_writes_of_a_full_span_fit_one_write_group() -> None:
    # A span's ready writes execute as one group, which no span can overfill.
    ranges = spans_module._WRITES_PER_SPAN  # pyright: ignore[reportPrivateUsage] - the span bound
    writes = settlement._WRITES_PER_GROUP  # pyright: ignore[reportPrivateUsage] - the group bound
    assert ranges <= writes
