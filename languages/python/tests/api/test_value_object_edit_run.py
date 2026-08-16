"""The public `ValueObject.edit` usage story, end to end against real Postgres.

Idiomatic use of the copy verb is one sentence — derive a changed occurrence from
the one a read published, assign it, write it — and the half that only a real
database can show is what the row then holds. Presence is the sharp edge: an
occurrence carries forward exactly the members its receiver populated, so a
member storage never held stays out of the stored document instead of arriving as
an explicit null, and an assignment replaces its subtree whole instead of merging
into it.

What the corpus cannot reach is why this lane exists for the verb at all: the
copy is an in-memory authoring door that issues no statement of its own, so no
case shape observes it (`docs/architecture/supplemental-interface-obligations.md`,
SIO-015 and SIO-021). `tests/unit/test_value_object_edit.py` holds the same
verb's internal seams and every refusal it raises; nothing here restates those.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.conformance import engine
from parallax.conformance.class_models import MODELS
from parallax.conformance.vo_models import (
    Customer,
    CustomerAddress,
    CustomerGeo,
    CustomerPhone,
    CustomerPoint,
)
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

_CUSTOMER = MODELS["customer"]

_SEEDED_ADDRESS = {
    "street": "Storgata 1",
    "city": "Oslo",
    "phones": [{"type": "home", "number": "1"}],
}
"""The document the seed stores. `geo` is declared and nullable and is left
unpopulated, so it is absent from the document rather than stored as null — the
state every assertion below weighs its own stored document against."""


def _connect_and_seed(provisioner: Any) -> Database:
    provisioner.reset(model_of(_CUSTOMER), {})
    db = connect(provisioner.port, _CUSTOMER)
    db.transact(
        lambda tx: tx.insert(
            Customer(
                id=1,
                name="Ada",
                address=CustomerAddress(
                    street="Storgata 1",
                    city="Oslo",
                    phones=(CustomerPhone(type="home", number="1"),),
                ),
            )
        )
    )
    return db


def _stored_address(provisioner: Any) -> object:
    state = engine.read_table_state(provisioner.port, model_of(_CUSTOMER), POSTGRES)
    (row,) = state["customer"]
    return row["address"]


def _address_of(customer: Customer) -> CustomerAddress:
    address = customer.address
    assert address is not None
    return address


def test_an_edited_occurrence_stores_what_it_names_and_carries_the_rest(
    provisioner: Any,
) -> None:
    db = _connect_and_seed(provisioner)

    def relocate(tx: Transaction) -> CustomerAddress:
        customer = tx.find(Customer.where(Customer.id == 1)).result()
        address = _address_of(customer)
        tx.update(customer.edit(address=address.edit(city="Bergen")))
        return address

    published = db.transact(relocate).value

    assert _stored_address(provisioner) == {
        "street": "Storgata 1",
        "city": "Bergen",
        "phones": [{"type": "home", "number": "1"}],
    }
    assert (published.street, published.city) == ("Storgata 1", "Oslo")


def test_an_edited_occurrence_replaces_a_nested_and_a_plural_member_whole(
    provisioner: Any,
) -> None:
    db = _connect_and_seed(provisioner)

    def replace(tx: Transaction) -> None:
        customer = tx.find(Customer.where(Customer.id == 1)).result()
        tx.update(
            customer.edit(
                address=_address_of(customer).edit(
                    geo=CustomerGeo(country="NO", point=CustomerPoint(lat=59.5, lon=10.75)),
                    phones=(CustomerPhone(type="work", number="2"),),
                )
            )
        )

    db.transact(replace)

    assert _stored_address(provisioner) == {
        "street": "Storgata 1",
        "city": "Oslo",
        "geo": {"country": "NO", "point": {"lat": 59.5, "lon": 10.75}},
        "phones": [{"type": "work", "number": "2"}],
    }


def test_edits_compose_and_leave_every_value_they_derive_from_untouched(
    provisioner: Any,
) -> None:
    db = _connect_and_seed(provisioner)

    def compose(tx: Transaction) -> tuple[CustomerAddress, CustomerAddress]:
        customer = tx.find(Customer.where(Customer.id == 1)).result()
        address = _address_of(customer)
        moved = address.edit(city="Bergen")
        renumbered = moved.edit(street="Nedre gate 2")
        tx.update(customer.edit(address=renumbered))
        return address, moved

    published, intermediate = db.transact(compose).value

    assert _stored_address(provisioner) == {
        "street": "Nedre gate 2",
        "city": "Bergen",
        "phones": [{"type": "home", "number": "1"}],
    }
    assert (published.street, published.city) == ("Storgata 1", "Oslo")
    assert (intermediate.street, intermediate.city) == ("Storgata 1", "Bergen")


def _change_free(address: CustomerAddress) -> CustomerAddress:
    return address.edit()


def _away_and_back(address: CustomerAddress) -> CustomerAddress:
    return address.edit(city="Bergen").edit(city="Oslo")


@pytest.mark.parametrize(
    "derive", [_change_free, _away_and_back], ids=["change-free", "away-and-back"]
)
def test_an_occurrence_carrying_no_net_change_writes_nothing(
    provisioner: Any, derive: Callable[[CustomerAddress], CustomerAddress]
) -> None:
    db = _connect_and_seed(provisioner)

    def rewrite(tx: Transaction) -> None:
        customer = tx.find(Customer.where(Customer.id == 1)).result()
        tx.update(customer.edit(address=derive(_address_of(customer))))

    result = db.transact(rewrite)

    assert [
        call
        for attempt in result.execution_log.attempts
        for call in attempt.calls
        if call.kind == "write"
    ] == []
    assert _stored_address(provisioner) == _SEEDED_ADDRESS
