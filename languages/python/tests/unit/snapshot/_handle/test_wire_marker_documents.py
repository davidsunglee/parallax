"""No public Wire verb reads a one-key `{increment: n}` or `{computed: ...}`
document at a scalar member as anything but the document it is: each verb's
codec refuses it before anything is buffered or written."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.core import Attr, DomainModel, Entity, Int32, attr
from parallax.core.internal.base import ParallaxError
from parallax.snapshot import TxnContext
from tests._support.db_port import ScriptedAdapter, Transact, WriteCall
from tests.unit._transact_support import db_for

_NS = "wire.marker.documents"


class Counter(Entity, table="counter", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    level: Attr[int] = attr(type=Int32)


class Gauge(Entity, table="gauge", namespace=_NS):
    """A versioned Entity, whose target writes state the version they hold."""

    id: Attr[int] = attr(primary_key=True)
    level: Attr[int] = attr(type=Int32)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


_MODEL = DomainModel(Counter, Gauge)
_TARGET = {"entity": "Counter", "predicate": {"eq": {"path": "Counter.id", "value": 1}}}

_DOCUMENTS = {
    "increment": {"increment": 1},
    "increment-text": {"increment": "x"},
    "increment-boolean": {"increment": True},
    "increment-fraction": {"increment": 1.5},
    "increment-null": {"increment": None},
    "increment-list": {"increment": [1]},
    "computed": {"computed": "maxPlusOne"},
}


def _insert(tx: TxnContext, document: object) -> None:
    tx.wire.insert("Counter", {"id": 1, "level": document})


def _amend(tx: TxnContext, document: object) -> None:
    tx.wire.amend(tx.wire.insert("Counter", {"id": 1, "level": 0}), {"level": document})


def _replace(tx: TxnContext, document: object) -> None:
    tx.wire.replace(tx.wire.insert("Counter", {"id": 1, "level": 0}), {"id": 1, "level": document})


def _amend_if(tx: TxnContext, document: object) -> None:
    tx.wire.amend_if("Gauge", {"id": 1, "level": document}, version=1)


def _replace_if(tx: TxnContext, document: object) -> None:
    tx.wire.replace_if("Gauge", {"id": 1, "level": document}, version=1)


def _amend_where(tx: TxnContext, document: object) -> None:
    tx.wire.amend_where(_TARGET, {"level": document})


def _replace_where(tx: TxnContext, document: object) -> None:
    tx.wire.replace_where(_TARGET, {"level": document})


_VERBS: dict[str, Callable[[TxnContext, object], None]] = {
    "insert": _insert,
    "amend": _amend,
    "replace": _replace,
    "amend_if": _amend_if,
    "replace_if": _replace_if,
    "amend_where": _amend_where,
    "replace_where": _replace_where,
}


class _Abandoned(Exception):
    """Ends the attempt once the refusal is seen, so nothing it buffered flushes."""


@pytest.mark.parametrize("verb", sorted(_VERBS))
@pytest.mark.parametrize("label", sorted(_DOCUMENTS))
def test_a_one_key_document_at_a_scalar_member_is_a_type_mismatch(verb: str, label: str) -> None:
    port = ScriptedAdapter(Transact())
    refused: list[ParallaxError] = []

    def fn(tx: TxnContext) -> None:
        with pytest.raises(ParallaxError) as raised:
            _VERBS[verb](tx, _DOCUMENTS[label])
        refused.append(raised.value)
        raise _Abandoned

    with pytest.raises(_Abandoned):
        db_for(_MODEL, port).transact(fn)
    (error,) = refused
    assert error.code == "neutral-literal-type-mismatch", error
    assert ".level" in str(error)
    assert not [call for call in port.calls if isinstance(call, WriteCall)]
