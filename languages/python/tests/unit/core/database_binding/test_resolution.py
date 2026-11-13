"""m-database-binding: resolving a binding against one model."""

from __future__ import annotations

from typing import Final

import pytest

from parallax.core.internal.database_binding import (
    BindingError,
    BindingIssue,
    PhysicalSequence,
    PhysicalTable,
    ResolvedBinding,
    SequenceRelocated,
    TableRelocated,
    relocations_between,
)
from parallax.core.internal.entity import model_of
from parallax.core.internal.metamodel import EntityIdentity, Metamodel
from parallax.descriptor import domain_model_from_yaml
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresSequence, PostgresTable

_MODEL_YAML: Final = """
entities:
  - name: Customer
    namespace: commerce
    table: customer
    attributes:
      - name: id
        type: int64
        primaryKey: true
        pkGeneration: { strategy: sequence, name: customerIds }
  - name: Order
    namespace: commerce
    table: orders
    attributes:
      - name: id
        type: int64
        primaryKey: true
        pkGeneration: { strategy: sequence, name: orderIds }
  - name: Event
    namespace: audit
    table: event
    attributes:
      - { name: id, type: int64, primaryKey: true }
  - name: Note
    table: note
    attributes:
      - { name: id, type: int64, primaryKey: true }
  - name: Payment
    namespace: billing
    table: payment
    inheritance: { role: root, strategy: table-per-hierarchy, tag: { column: kind } }
    attributes:
      - { name: id, type: int64, primaryKey: true }
  - name: CardPayment
    namespace: billing
    inheritance: { role: concrete-subtype, parent: billing.Payment, tagValue: card }
    attributes:
      - { name: network, type: string, maxLength: 16 }
"""

_MODEL: Final[Metamodel] = model_of(domain_model_from_yaml(_MODEL_YAML))
_CUSTOMER: Final = EntityIdentity("commerce", "Customer")
_ORDER: Final = EntityIdentity("commerce", "Order")
_EVENT: Final = EntityIdentity("audit", "Event")
_NOTE: Final = EntityIdentity(None, "Note")
_PAYMENT: Final = EntityIdentity("billing", "Payment")
_APP: Final = PostgresLocation(schema="app")


def _refused(binding: PostgresBinding) -> tuple[BindingIssue, ...]:
    with pytest.raises(BindingError) as raised:
        ResolvedBinding(_MODEL, binding)
    assert raised.value.code == "binding-resolution-rejected"
    return raised.value.issues


def test_each_owner_takes_its_entry_then_its_exact_namespace_then_the_default() -> None:
    resolved = ResolvedBinding(
        _MODEL,
        PostgresBinding(
            default=_APP,
            namespaces={
                "audit": PostgresLocation(schema="audit"),
                "commerce": PostgresLocation(schema="shop"),
            },
            entities={
                "commerce.Customer": PostgresTable(schema="crm", name="customer_master"),
                "commerce.Order": PostgresTable(name="order_book"),
            },
        ),
    )
    assert resolved.table(_CUSTOMER).physical == PhysicalTable(("crm",), "customer_master")
    assert resolved.table(_ORDER).physical == PhysicalTable(("shop",), "order_book")
    assert resolved.table(_EVENT).physical == PhysicalTable(("audit",), "event")
    assert resolved.table(_NOTE).physical == PhysicalTable(("app",), "note")
    assert resolved.table(_PAYMENT).physical == PhysicalTable(("app",), "payment")


def test_a_namespace_default_never_covers_a_longer_namespace() -> None:
    issues = _refused(
        PostgresBinding(
            namespaces={
                "commerce": PostgresLocation(schema="shop"),
                "audit": PostgresLocation(schema="audit"),
                "billing": PostgresLocation(schema="billing"),
            }
        )
    )
    assert [(issue.code, issue.path) for issue in issues] == [
        ("binding-table-unresolved", ("entities", "Note")),
        ("binding-sequence-unresolved", ("sequences", "customerIds")),
        ("binding-sequence-unresolved", ("sequences", "orderIds")),
    ]


def test_an_allocator_ignores_namespace_and_table_placement() -> None:
    resolved = ResolvedBinding(
        _MODEL,
        PostgresBinding(
            default=_APP,
            namespaces={"commerce": PostgresLocation(schema="shop")},
            entities={"commerce.Customer": PostgresTable(schema="crm")},
            sequences={"orderIds": PostgresSequence(schema="keys", name="order_numbers")},
        ),
    )
    assert resolved.sequence("customerIds") == PhysicalSequence(("app",), "customerIds")
    assert resolved.sequence("orderIds") == PhysicalSequence(("keys",), "order_numbers")


def test_every_key_must_name_something_the_model_declares() -> None:
    issues = _refused(
        PostgresBinding(
            default=_APP,
            namespaces={"shipping": _APP},
            entities={"commerce.Basket": PostgresTable(), "billing.CardPayment": PostgresTable()},
            sequences={"basketIds": PostgresSequence()},
        )
    )
    assert {(issue.code, issue.path) for issue in issues} == {
        ("binding-entity-owns-no-table", ("entities", "billing.CardPayment")),
        ("binding-entity-unknown", ("entities", "commerce.Basket")),
        ("binding-namespace-unknown", ("namespaces", "shipping")),
        ("binding-sequence-unknown", ("sequences", "basketIds")),
    }


@pytest.mark.parametrize(
    ("binding", "path"),
    [
        (PostgresBinding(default=PostgresLocation(schema="a\x00b")), ("default",)),
        (
            PostgresBinding(default=_APP, entities={"Note": PostgresTable(name="n" * 64)}),
            ("entities", "Note", "table"),
        ),
        (
            PostgresBinding(default=_APP, namespaces={"audit": PostgresLocation(schema="é" * 32)}),
            ("namespaces", "audit"),
        ),
        (
            PostgresBinding(default=_APP, sequences={"orderIds": PostgresSequence(name="s\x00")}),
            ("sequences", "orderIds", "sequence"),
        ),
    ],
    ids=["nul-qualifier", "over-budget-name", "over-budget-bytes", "nul-sequence"],
)
def test_a_resolved_component_the_dialect_cannot_name_is_refused_where_it_was_supplied(
    binding: PostgresBinding, path: tuple[str, ...]
) -> None:
    assert [(issue.code, issue.path) for issue in _refused(binding)] == [
        ("binding-identifier-invalid", path)
    ]


def test_a_component_at_the_byte_budget_is_accepted() -> None:
    resolved = ResolvedBinding(
        _MODEL, PostgresBinding(default=_APP, entities={"Note": PostgresTable(name="n" * 63)})
    )
    assert resolved.table(_NOTE).physical.name == "n" * 63


def test_a_collision_names_the_later_owner_and_relates_the_earlier_one() -> None:
    (issue,) = _refused(
        PostgresBinding(
            default=_APP,
            entities={
                "commerce.Order": PostgresTable(name="customer"),
                "commerce.Customer": PostgresTable(),
            },
        )
    )
    assert issue == BindingIssue(
        "binding-table-collision",
        ("entities", "commerce.Order"),
        (("entities", "commerce.Customer"),),
    )


def test_equal_names_in_two_locations_do_not_collide_and_components_compare_exactly() -> None:
    resolved = ResolvedBinding(
        _MODEL,
        PostgresBinding(
            default=_APP,
            entities={
                "commerce.Customer": PostgresTable(name="ledger"),
                "commerce.Order": PostgresTable(schema="App", name="ledger"),
                "Note": PostgresTable(name="Ledger"),
            },
        ),
    )
    assert {table.physical for table in resolved.tables} >= {
        PhysicalTable(("app",), "ledger"),
        PhysicalTable(("App",), "ledger"),
        PhysicalTable(("app",), "Ledger"),
    }


def test_two_allocators_on_one_sequence_and_a_sequence_on_a_table_are_refused() -> None:
    issues = _refused(
        PostgresBinding(
            default=_APP,
            sequences={
                "customerIds": PostgresSequence(name="note"),
                "orderIds": PostgresSequence(name="note"),
            },
        )
    )
    assert issues == (
        BindingIssue(
            "binding-sequence-table-collision",
            ("sequences", "customerIds"),
            (("entities", "Note"),),
        ),
        BindingIssue(
            "binding-sequence-collision", ("sequences", "orderIds"), (("sequences", "customerIds"),)
        ),
        BindingIssue(
            "binding-sequence-table-collision", ("sequences", "orderIds"), (("entities", "Note"),)
        ),
    )


def test_a_dotted_name_is_one_component_and_each_component_is_quoted_alone() -> None:
    resolved = ResolvedBinding(
        _MODEL,
        PostgresBinding(
            default=PostgresLocation(schema='te"nant'),
            entities={"Note": PostgresTable(name="a.b")},
        ),
    )
    table = resolved.table(_NOTE)
    assert table.physical == PhysicalTable(('te"nant',), "a.b")
    assert table.sql == '"te""nant"."a.b"'


def test_only_a_mapping_owner_has_a_resolved_table() -> None:
    resolved = ResolvedBinding(_MODEL, PostgresBinding(default=_APP))
    with pytest.raises(LookupError):
        resolved.table(EntityIdentity("billing", "CardPayment"))
    with pytest.raises(LookupError):
        resolved.sequence("noSuchAllocator")


def test_relocations_name_surviving_tables_in_owner_order_then_surviving_sequences() -> None:
    earlier = ResolvedBinding(_MODEL, PostgresBinding(default=_APP))
    later = ResolvedBinding(
        _MODEL,
        PostgresBinding(
            default=_APP,
            namespaces={"audit": PostgresLocation(schema="audit")},
            entities={"Note": PostgresTable(name="notes")},
            sequences={"customerIds": PostgresSequence(schema="keys")},
        ),
    )
    assert relocations_between(earlier, later) == (
        TableRelocated(_NOTE, PhysicalTable(("app",), "note"), PhysicalTable(("app",), "notes")),
        TableRelocated(
            _EVENT, PhysicalTable(("app",), "event"), PhysicalTable(("audit",), "event")
        ),
        SequenceRelocated(
            "customerIds",
            PhysicalSequence(("app",), "customerIds"),
            PhysicalSequence(("keys",), "customerIds"),
        ),
    )
    assert relocations_between(later, later) == ()


def test_an_owner_only_one_side_holds_is_never_a_relocation() -> None:
    grown = model_of(
        domain_model_from_yaml(
            _MODEL_YAML
            + """
  - name: Refund
    namespace: billing
    table: refund
    attributes:
      - { name: id, type: int64, primaryKey: true }
"""
        )
    )
    earlier = ResolvedBinding(_MODEL, PostgresBinding(default=_APP))
    later = ResolvedBinding(
        grown,
        PostgresBinding(
            default=PostgresLocation(schema="next"),
            entities={
                "commerce.Customer": PostgresTable(schema="app"),
                "commerce.Order": PostgresTable(schema="app"),
                "audit.Event": PostgresTable(schema="app"),
                "Note": PostgresTable(schema="app"),
                "billing.Payment": PostgresTable(schema="app"),
            },
            sequences={
                "customerIds": PostgresSequence(schema="app"),
                "orderIds": PostgresSequence(schema="app"),
            },
        ),
    )
    assert relocations_between(earlier, later) == ()
    assert later.table(EntityIdentity("billing", "Refund")).physical == PhysicalTable(
        ("next",), "refund"
    )
