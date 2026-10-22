"""Bitemporal objects whose deferred writes share coverage reads.

``frag(k, m)`` is object ``k`` storing ``2m`` rectangles ``R_i = [d_i,
d_{i+1})``, the last one open, each at amount ``i`` and label ``k{k}``, known
from ``T0``. Its writes observe every even rectangle and amend each pair
``[d_{2p}, d_{2p+2})`` to amount ``1000 + p``, so they compose into one write
whose ``m`` uncovered parts ``[d_{2p+1}, d_{2p+2})`` each reach the odd
rectangle ``R_{2p+1}`` alone.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import replace
from typing import Final, cast

from parallax.core import Attr, Bitemporal, Document, DomainModel, Entity, attr, temporal_read
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedTargetWrite,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.ranges import DeferredTemporalRange
from parallax.core._execution._unit_work.retain import RetainedTargetState
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    TargetKeyedWrite,
    target_write,
)
from parallax.core.base import INFINITY, DocumentValue, PresentDocument
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._model import model_of
from parallax.core.inheritance import view as inheritance_view
from parallax.core.unit_work import (
    Concurrency,
    KeyedWriteInstruction,
    RetainedObservation,
    TargetWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
    buffered_write,
)
from parallax.core.write_plan import ObjectKey, PredecessorRow, TemporalObservation, WritePlan
from parallax.core.write_plan.keys import TemporalObjectStateKey
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admitted_writes
from tests.unit._positional_row_support import positional_row

__all__ = [
    "AT",
    "DOMAIN",
    "MODEL",
    "T0",
    "ShareCols",
    "ShareDoc",
    "ShareTag",
    "covered_target",
    "day",
    "frag",
    "frag_rows",
    "observation",
    "physical_row",
    "plan",
    "ranges_of",
    "rectangle",
]


class ShareCols(Bitemporal, table="share_cols", namespace="parallax.execution.shared"):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str] = attr(max_length=16)


class ShareDoc(
    Bitemporal, table="share_doc", namespace="parallax.execution.shared", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str] = attr(max_length=16)


class ShareTag(Entity, table="share_tag", namespace="parallax.execution.shared"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


DOMAIN: Final = DomainModel(ShareCols, ShareDoc, ShareTag)
MODEL: Final = model_of(DOMAIN)
T0: Final = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
AT: Final = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_D0: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def day(index: int) -> dt.datetime:
    """``d_index``: 2024-01-01 plus ``index`` days."""
    return _D0 + dt.timedelta(days=index)


def _documented(entity: type[Bitemporal]) -> bool:
    return entity is ShareDoc


def rectangle(
    entity: type[Bitemporal], key: int, start: int, end: int | None, amount: int
) -> PredecessorRow:
    """Object ``key``'s current rectangle ``[d_start, d_end)`` — open where
    ``end`` is ``None`` — at ``amount``, known from ``T0``."""
    label = f"k{key}"
    return PredecessorRow(
        members={
            "id": key,
            "amount": amount,
            "label": label,
            "validStart": day(start),
            "validEnd": INFINITY if end is None else day(end),
            "txStart": T0,
            "txEnd": INFINITY,
        },
        document={"amount": amount, "label": label} if _documented(entity) else None,
    )


def frag_rows(entity: type[Bitemporal], key: int, parts: int) -> list[PredecessorRow]:
    """Every rectangle ``frag(key, parts)`` stores, in Valid-Time order."""
    last = 2 * parts - 1
    return [
        rectangle(entity, key, index, None if index == last else index + 1, index)
        for index in range(2 * parts)
    ]


def physical_row(entity: type[Bitemporal], row: PredecessorRow) -> dict[str, object]:
    """``row`` as the database answers it, by physical column."""
    members = row.members
    axes = {
        "from_z": members["validStart"],
        "thru_z": members["validEnd"],
        "in_z": members["txStart"],
        "out_z": members["txEnd"],
    }
    if _documented(entity):
        document: dict[str, DocumentValue] = {
            "amount": cast("int", members["amount"]),
            "label": cast("str", members["label"]),
        }
        return {"id": members["id"], **axes, "payload": PresentDocument(document)}
    return {"id": members["id"], "amount": members["amount"], "label": members["label"], **axes}


def _state(entity: type[Bitemporal], row: PredecessorRow) -> TemporalObjectStateKey:
    shape = temporal_read.view(MODEL).shape(entity.identity)
    assert shape is not None
    key = ObjectKey(entity.identity, (("id", row.members["id"]),))
    return TemporalObjectStateKey(key, temporal_read.milestone_edge(shape, row, None))


def observation(entity: type[Bitemporal], row: PredecessorRow) -> RetainedObservation:
    """``row`` observed by a read of the writing attempt."""
    return RetainedObservation(_state(entity, row), TemporalObservation(predecessor=row), None)


def frag(entity: type[Bitemporal], key: int, parts: int) -> list[AdmittedWrite]:
    """``frag(key, parts)``'s writes, each through its observation of an even
    rectangle, in Valid-Time order."""
    rows = frag_rows(entity, key, parts)
    writes: list[AdmittedWrite] = []
    for pair in range(parts):
        prepared = prepare_wire_write(
            KeyedWriteInstruction(
                "amendUntil",
                entity.identity.canonical,
                ({"id": key, "amount": 1000 + pair},),
                day(2 * pair),
                day(2 * pair + 2),
            ),
            MODEL,
        )
        assert isinstance(prepared, PreparedKeyedWrite)
        writes.append(buffered_write(prepared, observation(entity, rows[2 * pair])))
    return writes


def covered_target(entity: type[Bitemporal], key: int) -> tuple[TargetKeyedWrite, PredecessorRow]:
    """A Locking target write of object ``key`` over ``[d_0, d_1)`` beside the
    one stored rectangle ``[d_0, ∞)`` its acquisition retained, which covers
    its whole window."""
    stored = rectangle(entity, key, 0, None, 0)
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amendUntil",
            entity.identity.canonical,
            {"id": key, "amount": 7},
            if_tx_start=T0,
            valid_from=day(0),
            until=day(1),
        ),
        MODEL,
    )
    assert isinstance(prepared, PreparedTargetWrite)
    view = inheritance_view(MODEL).entity(entity.identity)
    assert view is not None
    retained = RetainedTargetState(
        _state(entity, stored),
        0,
        positional_row(view.member_selection.shape, stored.members, absent=ABSENT),
        stored.document,
    )
    return replace(target_write(prepared, inheritance_view(MODEL)), retained=retained), stored


def plan(
    writes: Sequence[AdmittedWrite],
    *,
    concurrency: Concurrency = "optimistic",
    instant: TransactionInstant | None = None,
) -> WritePlan:
    """``writes`` admitted in order and planned as one flush."""
    return build_write_planner(MODEL).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant or instant_at(AT.isoformat()),
            concurrency=concurrency,
            buffered_writes=admitted_writes(MODEL, list(writes)),
        )
    )


def ranges_of(written: WritePlan) -> tuple[DeferredTemporalRange, ...]:
    """The deferred range of each of ``written``'s groups, in order."""
    ranges: list[DeferredTemporalRange] = []
    for group in written.groups:
        (write,) = group.writes
        assert isinstance(write.deferred, DeferredTemporalRange)
        ranges.append(write.deferred)
    return tuple(ranges)
