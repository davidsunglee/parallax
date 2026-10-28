"""Each authored value is judged once, at its write's admission.

A public verb is driven over a scripted port while ``sys.monitoring`` counts
the starts of the scalar converters and of every general judgment, freeze, and
validating codec entry point. The verb, the node a Wire insert answers, and
the flush are observed apart, so an encoding that legitimately happens later
is never mistaken for repeated admission. Models, instances, and payloads are
built before the observed window opens.
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal as PyDecimal
from types import CodeType
from typing import Final

import pytest

from parallax.core import Attr, DomainModel, Entity, ValueObject, attr
from parallax.core.base import (
    INT64,
    STRING,
    Decimal,
    NeutralType,
    coerce_neutral_input,
    matches_neutral_type,
    retain_document_value,
    typed_converter,
)
from parallax.core.base._neutral import _general_typed_converter  # pyright: ignore[reportPrivateUsage]
from parallax.core.db_port import JsonDocument
from parallax.core.entity import Document
from parallax.core.wire import decode_wire, encode_wire
from parallax.core.wire._codec import wire_converter
from parallax.snapshot import TxnContext
from parallax.snapshot._publication._wire import opened_wire_entity
from tests._support.db_port import ScriptedAdapter, Transact, Write, WriteCall
from tests.unit._transact_support import db_for

_NS = "judged.once"


class Spot(ValueObject):
    code: Attr[str]
    rank: Attr[int | None]


class Shelf(Entity, table="shelf", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    price: Attr[PyDecimal] = attr(precision=8, scale=2)
    name: Attr[str]
    sizes: Attr[tuple[int, ...]]
    spot: Attr[Spot | None]


class Drawer(Entity, table="drawer", namespace=_NS, layout=Document):
    id: Attr[int] = attr(primary_key=True)
    price: Attr[PyDecimal] = attr(precision=8, scale=2)
    name: Attr[str]
    sizes: Attr[tuple[int, ...]]
    spot: Attr[Spot | None]


_MODEL = DomainModel(Shelf, Drawer)
_DECLARED: Final[tuple[NeutralType, ...]] = (INT64, STRING, Decimal(precision=8, scale=2))

# id, price, name, both `sizes` elements, and both `spot` members.
_AUTHORED_SCALARS: Final = 7

_CONVERT: Final = "convert"
_GENERAL: Final = "general"
_LABELS: Final[Mapping[CodeType, str]] = {
    **{
        factory(declared).__code__: _CONVERT
        for factory in (typed_converter, wire_converter)
        for declared in _DECLARED
    },
    **{
        operation.__code__: _GENERAL
        for operation in (
            coerce_neutral_input,
            matches_neutral_type,
            retain_document_value,
            decode_wire,
            encode_wire,
        )
    },
    _general_typed_converter(INT64).__code__: _GENERAL,
}

_VERB: Final = "verb"
_NODE: Final = "returned-node"
_FLUSH: Final = "flush"


@dataclass(slots=True)
class _Observation:
    """Starts of each labelled code object, by the phase they happened in."""

    phase: str = _VERB
    counts: Counter[tuple[str, str]] = field(default_factory=Counter[tuple[str, str]])

    def started(self, code: CodeType, _offset: int) -> None:
        label = _LABELS.get(code)
        if label is None:
            return
        frame = sys._getframe(1)  # pyright: ignore[reportPrivateUsage]
        phase = self.phase
        while frame is not None:
            if frame.f_code is _NODE_CODE:
                phase = _NODE
                break
            frame = frame.f_back
        self.counts[label, phase] += 1

    def count(self, label: str, phase: str) -> int:
        return self.counts[label, phase]


_NODE_CODE: Final = opened_wire_entity.__code__


@contextmanager
def _observed() -> Generator[_Observation]:
    monitoring = sys.monitoring
    tool = next(
        (tool for tool in range(6) if monitoring.get_tool(tool) is None),
        None,
    )
    if tool is None:  # pragma: no cover - every tool slot is already claimed
        pytest.skip("no free sys.monitoring tool id")
    observation = _Observation()
    monitoring.use_tool_id(tool, "one-judgment-per-value")
    try:
        monitoring.register_callback(tool, monitoring.events.PY_START, observation.started)
        for code in _LABELS:
            monitoring.set_local_events(tool, code, monitoring.events.PY_START)
        yield observation
    finally:
        for code in _LABELS:
            monitoring.set_local_events(tool, code, monitoring.events.NO_EVENTS)
        monitoring.register_callback(tool, monitoring.events.PY_START, None)
        monitoring.free_tool_id(tool)


def _write(
    entity: type[Entity], write: Callable[[TxnContext], object]
) -> tuple[_Observation, WriteCall]:
    port = ScriptedAdapter(Transact(Write()))
    database = db_for(_MODEL, port)

    def fn(tx: TxnContext) -> None:
        write(tx)
        observation.phase = _FLUSH

    with _observed() as observation:
        database.transact(fn)
    (call,) = [call for call in port.calls if isinstance(call, WriteCall)]
    assert call.sql.startswith(f"insert into {entity.__name__.lower()}(")
    return observation, call


_TYPED: Final = "typed"
_WIRE: Final = "wire"


def _opening(entity: type[Entity], lane: str) -> Callable[[TxnContext], object]:
    if lane == _TYPED:
        instance = entity(
            id=1, price=PyDecimal("2.50"), name="N", sizes=(1, 2), spot=Spot(code="A", rank=3)
        )
        return lambda tx: tx.insert(instance)
    payload = {
        "id": 1,
        "price": "2.50",
        "name": "N",
        "sizes": [1, 2],
        "spot": {"code": "A", "rank": 3},
    }
    return lambda tx: tx.wire.insert(entity.__name__, payload)


def _stored(call: WriteCall) -> list[object]:
    """The binds of the one row ``call`` inserts, documents by their content."""
    return [bind.value if isinstance(bind, JsonDocument) else bind for bind in call.binds]


_SPOT: Final = {"code": "A", "rank": 3}
# Each layout's stored row: Columns binds every member in its own slot, and the
# Relational Document Layout gathers the non-key members into one document.
_STORED: Final[Mapping[type[Entity], list[object]]] = {
    Shelf: [1, PyDecimal("2.50"), "N", (1, 2), _SPOT],
    Drawer: [1, {"price": "2.50", "name": "N", "sizes": (1, 2), "spot": _SPOT}],
}


@pytest.mark.parametrize("lane", [_TYPED, _WIRE])
@pytest.mark.parametrize("entity", [Shelf, Drawer], ids=["columns", "document"])
def test_an_opening_converts_each_authored_scalar_once_and_judges_it_nowhere_else(
    entity: type[Entity], lane: str
) -> None:
    observation, call = _write(entity, _opening(entity, lane))
    assert observation.count(_CONVERT, _VERB) == _AUTHORED_SCALARS
    assert observation.count(_GENERAL, _VERB) == 0
    # Neither the Wire node the verb answers nor the flush admits a value
    # again. The flush's storage encoding and bind signature still consult
    # general membership.
    assert observation.count(_CONVERT, _NODE) == 0
    assert observation.count(_CONVERT, _FLUSH) == 0
    assert _stored(call) == _STORED[entity]


class _Key(int):
    pass


def test_the_observer_sees_a_judgment_a_verb_makes() -> None:
    # A Typed value outside the fast arms, an `int` subclass for an Int, is
    # converted through the general rule, which the observer reports.
    instance = Shelf.model_construct(None, id=_Key(1), price=PyDecimal("2.50"), name="N")
    observation, _call = _write(Shelf, lambda tx: tx.insert(instance))
    assert observation.count(_GENERAL, _VERB) > 0
