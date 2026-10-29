"""Each authored value is judged once, at its write's admission.

A public verb is driven over a scripted port while ``sys.monitoring`` counts
the starts of the scalar converters and of every general judgment, freeze, and
validating codec entry point. The verb, the node a Wire insert answers, and
the flush are observed apart, so an encoding that legitimately happens later
is never mistaken for repeated admission. Models, instances, and payloads are
built before the observed window opens.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections import Counter
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal as PyDecimal
from types import CodeType
from typing import Any, Final

import pytest

from parallax.core import Attr, DomainModel, Entity, ValueObject, attr
from parallax.core.base import (
    INFINITY,
    INT64,
    STRING,
    Decimal,
    Int32,
    NeutralType,
    coerce_neutral_input,
    matches_neutral_type,
    retain_document_value,
    typed_converter,
)
from parallax.core.base._neutral import _general_typed_converter  # pyright: ignore[reportPrivateUsage]
from parallax.core.db_port import JsonDocument
from parallax.core.entity import Document
from parallax.core.unit_work import UnitOfWork
from parallax.core.wire import decode_wire, encode_wire
from parallax.core.wire._codec import wire_converter
from parallax.snapshot import TxnContext, WireEntity
from parallax.snapshot._publication._wire import opened_wire_entity
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write, WriteCall
from tests.unit._transact_support import db_for
from tests.unit._where_position_model import WHERE_POSITION_META, WherePosition

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

_READ: Final = "read"
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
            if frame.f_code is _PREDICATE_EXECUTION_CODE:
                phase = _FLUSH
                break
            frame = frame.f_back
        self.counts[label, phase] += 1

    def count(self, label: str, phase: str) -> int:
        return self.counts[label, phase]


_NODE_CODE: Final = opened_wire_entity.__code__
# A predicate write executes at its verb: its statement's lowering is a flush.
_PREDICATE_EXECUTION_CODE: Final = UnitOfWork._execute_predicate.__code__  # pyright: ignore[reportPrivateUsage]


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


def _run(
    model: DomainModel,
    script: tuple[Read | Write, ...],
    write: Callable[[TxnContext, object], object],
    *,
    read: Callable[[TxnContext], object] | None = None,
) -> tuple[_Observation, list[WriteCall]]:
    """``write`` driven over ``script``, handed what ``read`` answers; the read
    is observed apart from the verb and the flush."""
    port = ScriptedAdapter(Transact(*script))
    database = db_for(model, port)

    def fn(tx: TxnContext) -> None:
        observation.phase = _READ
        source = None if read is None else read(tx)
        observation.phase = _VERB
        write(tx, source)
        observation.phase = _FLUSH

    with _observed() as observation:
        database.transact(fn, concurrency="optimistic")
    return observation, [call for call in port.calls if isinstance(call, WriteCall)]


def _write(
    entity: type[Entity], write: Callable[[TxnContext], object]
) -> tuple[_Observation, WriteCall]:
    observation, calls = _run(_MODEL, (Write(),), lambda tx, _source: write(tx))
    (call,) = calls
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


def _admitted_once(observation: _Observation, converted: int) -> None:
    """``converted`` values were each converted once by the verb, and no value
    again by anything after it."""
    assert observation.count(_CONVERT, _VERB) == converted
    assert observation.count(_GENERAL, _VERB) == 0
    assert observation.count(_CONVERT, _FLUSH) == 0


# A stored Shelf as its Columns read returns it.
_SHELF_ROW: Final[Mapping[str, object]] = {
    "id": 1,
    "price": PyDecimal("2.50"),
    "name": "N",
    "sizes": [1, 2],
    "spot": {"code": "A", "rank": 3},
}
_SHELF: Final = Shelf(
    id=1, price=PyDecimal("2.50"), name="M", sizes=(1, 2), spot=Spot(code="A", rank=3)
)
_DRAWER: Final = Drawer(
    id=1, price=PyDecimal("2.50"), name="M", sizes=(1, 2), spot=Spot(code="A", rank=3)
)
# A Wire replacement's document states every member but the key its source
# addresses.
_SHELF_STATE: Final[Mapping[str, object]] = {
    "price": "2.50",
    "name": "M",
    "sizes": [1, 2],
    "spot": {"code": "A", "rank": 3},
}
_RENAMED: Final = Shelf.name.set("M")
_SPOTTED_SHELVES: Final = Shelf.where(Shelf.spot.exists())
_SPOTTED_DRAWERS: Final = Drawer.where(Drawer.spot.exists())
_WIRE_SHELF_QUERY: Final[Mapping[str, object]] = {
    "target": f"{_NS}.Shelf",
    "predicate": {"eq": {"path": f"{_NS}.Shelf.id", "value": 1}},
}


def _shelf(tx: TxnContext) -> Shelf:
    return tx.find(Shelf.where(Shelf.id == 1)).result()


def _renamed_shelf(tx: TxnContext) -> Shelf:
    return _shelf(tx).edit(name="M")


def _wire_shelf(tx: TxnContext) -> WireEntity:
    return tx.wire.find(_WIRE_SHELF_QUERY).result()


def _typed_amend(tx: TxnContext, source: Any) -> None:
    tx.amend(source)


def _wire_amend(tx: TxnContext, source: Any) -> None:
    tx.wire.amend(source, {"name": "M"})


def _typed_replace(tx: TxnContext, source: Any) -> None:
    tx.replace(source)


def _wire_replace(tx: TxnContext, source: Any) -> None:
    tx.wire.replace(source, dict(_SHELF_STATE))


def _typed_delete(tx: TxnContext, source: Any) -> None:
    tx.delete(source)


def _wire_delete(tx: TxnContext, source: Any) -> None:
    tx.wire.delete(source)


# Each keyed verb's write off a read source, and the scalars it states: the
# key its source addresses, plus an amendment's one assigned member, or a
# replacement's every other member as an opening states them.
@pytest.mark.parametrize(
    ("read", "write", "converted"),
    [
        pytest.param(_renamed_shelf, _typed_amend, 2, id="typed-amend"),
        pytest.param(_wire_shelf, _wire_amend, 2, id="wire-amend"),
        pytest.param(_renamed_shelf, _typed_replace, _AUTHORED_SCALARS, id="typed-replace"),
        pytest.param(_wire_shelf, _wire_replace, _AUTHORED_SCALARS, id="wire-replace"),
        pytest.param(_shelf, _typed_delete, 1, id="typed-delete"),
        pytest.param(_wire_shelf, _wire_delete, 1, id="wire-delete"),
    ],
)
def test_a_keyed_write_converts_each_value_it_states_once(
    read: Callable[[TxnContext], object],
    write: Callable[[TxnContext, Any], object],
    converted: int,
) -> None:
    observation, calls = _run(_MODEL, (Read(rows=[_SHELF_ROW]), Write()), write, read=read)
    _admitted_once(observation, converted)
    assert len(calls) == 1


def _typed_amend_where(tx: TxnContext, _source: object) -> None:
    tx.amend_where(_SPOTTED_SHELVES, _RENAMED)


def _wire_amend_where(tx: TxnContext, _source: object) -> None:
    tx.wire.amend_where(_SPOTTED_SHELVES, {"name": "M"})


def _typed_replace_shelves(tx: TxnContext, _source: object) -> None:
    tx.replace_where(_SPOTTED_SHELVES, _SHELF)


def _typed_replace_drawers(tx: TxnContext, _source: object) -> None:
    tx.replace_where(_SPOTTED_DRAWERS, _DRAWER)


def _wire_replace_drawers(tx: TxnContext, _source: object) -> None:
    tx.wire.replace_where(_SPOTTED_DRAWERS, {"id": 1, **_SHELF_STATE})


@pytest.mark.parametrize(
    ("write", "converted"),
    [
        pytest.param(_typed_amend_where, 1, id="typed-amend-where"),
        pytest.param(_wire_amend_where, 1, id="wire-amend-where"),
        pytest.param(_typed_replace_shelves, _AUTHORED_SCALARS, id="typed-replace-where-columns"),
        pytest.param(_typed_replace_drawers, _AUTHORED_SCALARS, id="typed-replace-where-document"),
        pytest.param(_wire_replace_drawers, _AUTHORED_SCALARS, id="wire-replace-where-document"),
    ],
)
def test_a_predicate_write_converts_each_value_it_assigns_once(
    write: Callable[[TxnContext, object], object], converted: int
) -> None:
    # A Typed assignment's own `.set(...)` judged its value when it was built,
    # outside the observed verb, under its own contract. The statement executes
    # at the verb, and its lowering is observed as the flush.
    observation, calls = _run(_MODEL, (Write(),), write)
    _admitted_once(observation, converted)
    assert len(calls) == 1


class Crate(Entity, table="crate", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


_CRATES: Final = DomainModel(Crate)
_RENAMED_CRATE: Final = Crate.name.set("M")
_CRATE: Final = Crate(id=1, name="M")


def _typed_amend_if(tx: TxnContext, _source: object) -> None:
    tx.amend_if(Crate, _RENAMED_CRATE, key=1, version=3)


def _wire_amend_if(tx: TxnContext, _source: object) -> None:
    tx.wire.amend_if("Crate", {"id": 1, "name": "M"}, version=3)


def _typed_replace_if(tx: TxnContext, _source: object) -> None:
    tx.replace_if(_CRATE, version=3)


def _wire_replace_if(tx: TxnContext, _source: object) -> None:
    tx.wire.replace_if("Crate", {"id": 1, "name": "M"}, version=3)


def _typed_delete_if(tx: TxnContext, _source: object) -> None:
    tx.delete_if(Crate, key=1, version=3)


def _wire_delete_if(tx: TxnContext, _source: object) -> None:
    tx.wire.delete_if("Crate", {"id": 1}, version=3)


@pytest.mark.parametrize(
    ("write", "converted"),
    [
        pytest.param(_typed_amend_if, 2, id="typed-amend-if"),
        pytest.param(_wire_amend_if, 2, id="wire-amend-if"),
        pytest.param(_typed_replace_if, 2, id="typed-replace-if"),
        pytest.param(_wire_replace_if, 2, id="wire-replace-if"),
        pytest.param(_typed_delete_if, 1, id="typed-delete-if"),
        pytest.param(_wire_delete_if, 1, id="wire-delete-if"),
    ],
)
def test_a_target_write_converts_its_key_and_each_member_it_states_once(
    write: Callable[[TxnContext, object], object], converted: int
) -> None:
    observation, calls = _run(_CRATES, (Write(),), write)
    _admitted_once(observation, converted)
    assert len(calls) == 1


_VALID_FROM: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_UNTIL: Final = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)
_POSITION_ROW: Final[Mapping[str, object]] = {
    "id": 1,
    "acct_num": "A",
    "value": PyDecimal("100.00"),
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": INFINITY,
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": INFINITY,
}


def _position(tx: TxnContext) -> WherePosition:
    query = WherePosition.where(WherePosition.id == 1).as_of(valid_time=_VALID_FROM)
    return tx.find(query).result()


def _revalued(tx: TxnContext) -> WherePosition:
    return _position(tx).edit(value=PyDecimal("200.00"))


_WIRE_POSITION_QUERY: Final[Mapping[str, object]] = {
    "target": "parallax.compatibility.WherePosition",
    "predicate": {"eq": {"path": "parallax.compatibility.WherePosition.id", "value": 1}},
    "temporal": {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"asOf": "2024-06-01T00:00:00.000000Z"},
    },
}


def _wire_position(tx: TxnContext) -> WireEntity:
    return tx.wire.find(_WIRE_POSITION_QUERY).result()


def _amend_until(tx: TxnContext, source: Any) -> None:
    tx.amend(source, until=_UNTIL)


def _wire_revalue(tx: TxnContext, source: Any) -> None:
    tx.wire.amend(source, {"value": "200.00"})


def _wire_revalue_until(tx: TxnContext, source: Any) -> None:
    tx.wire.amend(source, {"value": "200.00"}, until=_UNTIL)


def _replace_until(tx: TxnContext, source: Any) -> None:
    tx.replace(source, until=_UNTIL)


_POSITION_STATE: Final[Mapping[str, object]] = {"acctNum": "A", "value": "200.00"}


def _wire_restate(tx: TxnContext, source: Any) -> None:
    tx.wire.replace(source, dict(_POSITION_STATE))


def _wire_restate_until(tx: TxnContext, source: Any) -> None:
    tx.wire.replace(source, dict(_POSITION_STATE), until=_UNTIL)


def _terminate(tx: TxnContext, source: Any) -> None:
    tx.terminate(source)


def _terminate_until(tx: TxnContext, source: Any) -> None:
    tx.terminate(source, until=_UNTIL)


def _wire_terminate(tx: TxnContext, source: Any) -> None:
    tx.wire.terminate(source)


def _wire_terminate_until(tx: TxnContext, source: Any) -> None:
    tx.wire.terminate(source, until=_UNTIL)


# A temporal write's scalars as the keyed matrix counts them: an amendment's
# key and revalued `value`, a replacement's key and both other members, and a
# termination's key.
@pytest.mark.parametrize(
    ("read", "write", "converted"),
    [
        pytest.param(_revalued, _typed_amend, 2, id="typed-amend"),
        pytest.param(_wire_position, _wire_revalue, 2, id="wire-amend"),
        pytest.param(_revalued, _amend_until, 2, id="typed-amend-until"),
        pytest.param(_wire_position, _wire_revalue_until, 2, id="wire-amend-until"),
        pytest.param(_revalued, _typed_replace, 3, id="typed-replace"),
        pytest.param(_wire_position, _wire_restate, 3, id="wire-replace"),
        pytest.param(_revalued, _replace_until, 3, id="typed-replace-until"),
        pytest.param(_wire_position, _wire_restate_until, 3, id="wire-replace-until"),
        pytest.param(_position, _terminate, 1, id="typed-terminate"),
        pytest.param(_wire_position, _wire_terminate, 1, id="wire-terminate"),
        pytest.param(_position, _terminate_until, 1, id="typed-terminate-until"),
        pytest.param(_wire_position, _wire_terminate_until, 1, id="wire-terminate-until"),
    ],
)
def test_a_temporal_write_admits_once_and_its_successors_carry_cells_unjudged(
    read: Callable[[TxnContext], object],
    write: Callable[[TxnContext, Any], object],
    converted: int,
) -> None:
    observation, calls = _run(
        WHERE_POSITION_META, (Read(rows=[_POSITION_ROW]), Write(times=2)), write, read=read
    )
    _admitted_once(observation, converted)
    # The close, then one milestone insert of every successor it opens.
    close, opening = calls
    assert close.sql.startswith("update where_position")
    assert opening.sql.startswith("insert into where_position(")


def _typed_insert_until(tx: TxnContext, _source: object) -> None:
    tx.insert(
        WherePosition(id=1, acct_num="A", value=PyDecimal("100.00")),
        valid_from=_VALID_FROM,
        until=_UNTIL,
    )


def _wire_insert_until(tx: TxnContext, _source: object) -> None:
    tx.wire.insert(
        "WherePosition",
        {"id": 1, "acctNum": "A", "value": "100.00"},
        valid_from=_VALID_FROM,
        until=_UNTIL,
    )


@pytest.mark.parametrize(
    "write",
    [
        pytest.param(_typed_insert_until, id="typed-insert-until"),
        pytest.param(_wire_insert_until, id="wire-insert-until"),
    ],
)
def test_a_bounded_opening_converts_each_member_it_states_once(
    write: Callable[[TxnContext, object], object],
) -> None:
    observation, calls = _run(WHERE_POSITION_META, (Write(),), write)
    # Its key and both other members; the bounds are no member it states.
    _admitted_once(observation, 3)
    assert observation.count(_CONVERT, _NODE) == 0
    (opening,) = calls
    assert opening.sql.startswith("insert into where_position(")
