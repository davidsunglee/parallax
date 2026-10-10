"""Writes refuse a malformed scalar collection before any statement.

A collection is a whole sequence of non-null elements. A row or an assignment
that binds anything else is refused by the existing write vocabulary, at the
collection or at the failing element's position: a non-sequence or a null
element is a value-type mismatch, a null collection a missing required value,
and an element its type cannot decode the Wire literal rule. A Typed write
accepts only a tuple, even where no ``.set(...)`` judged the assignment first. The scripted port
is given no statement to answer, so a refusal that reached the database would
fail the script instead.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest

from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core.entity import AttributeAssignment
from parallax.core.entity._expressions import AttributeRef
from parallax.core.execution import ExecutionFailure
from parallax.snapshot import Transaction, connect
from tests._support.db_port import ScriptedAdapter, Transact
from tests._support.root_ownership import own_root

_NS = "scalar.collection.refusal"


class Order(Entity, table="orders", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()


_MODEL = DomainModel(Order)
_ORDER = f"{_NS}.Order"


def _refusal(work: Callable[[Transaction], object]) -> BaseException:
    port = ScriptedAdapter(Transact())
    database = own_root(connect(port, _MODEL)).using_database_login()
    with pytest.raises(ExecutionFailure) as caught:
        database.transact(work)
    return caught.value.__cause__ or caught.value


@pytest.mark.parametrize(
    ("tags", "rule", "message"),
    [
        ("urgent", "write-value-type-mismatch", "must bind a list of scalar values"),
        (["urgent", None], "write-value-type-mismatch", r"tags\[1\]: value None"),
        (None, "write-required-attribute-missing", "never null"),
        (["urgent", 3], "neutral-literal-type-mismatch", r"tags\[1\]: 3"),
    ],
    ids=["non-sequence", "null-element", "null-collection", "undecodable-element"],
)
def test_an_insert_refuses_a_malformed_collection_at_its_position(
    tags: object, rule: str, message: str
) -> None:
    refusal = _refusal(lambda tx: tx.wire.insert(_ORDER, {"id": 1, "tags": tags}))

    assert getattr(refusal, "rule", None) == rule
    assert re.search(message, str(refusal))


@pytest.mark.parametrize(
    ("tags", "message"),
    [
        ("urgent", "a `many` attribute must bind a sequence of scalar values"),
        (["urgent", None], "tags[1]: value None does not match the declared type"),
        (None, "required attribute is absent"),
    ],
    ids=["non-sequence", "null-element", "null-collection"],
)
def test_a_predicate_assignment_refuses_a_malformed_collection(tags: object, message: str) -> None:
    refusal = _refusal(
        lambda tx: tx.wire.amend_where(
            {"entity": _ORDER, "predicate": {"true": {}}}, {"tags": tags}
        )
    )

    assert message in str(refusal)


@pytest.mark.parametrize("tags", [["urgent"], range(1)], ids=["list", "range"])
def test_a_typed_assignment_no_set_judged_refuses_any_carrier_but_a_tuple(tags: object) -> None:
    unjudged: AttributeAssignment[Any] = AttributeAssignment(AttributeRef(_ORDER, "tags"), tags)
    refusal = _refusal(lambda tx: tx.amend_where(Order.where(Order.id == 1), unjudged))

    assert "tags: value" in str(refusal)
    assert "a `many` attribute must bind" in str(refusal)
