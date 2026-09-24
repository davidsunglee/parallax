"""m-descriptor records: preserved local declarations and the declarations they
carry without composing any derived structure."""

from __future__ import annotations

from parallax.descriptor import _records
from parallax.descriptor._records import Attribute, Entity, Inheritance, ValueObject
from tests.unit._corpus_model_support import corpus_records

_MODELS = corpus_records()


def test_records_preserve_local_declarations_and_their_effective_columns() -> None:
    account = _MODELS["account"].entity("Account")
    assert tuple((a.name, a.column) for a in account.attributes) == (
        ("id", "id"),
        ("owner", "owner"),
        ("balance", "balance"),
        ("version", "version"),
    )
    customer = _MODELS["customer"].entity("Customer")
    assert tuple((a.name, a.column) for a in customer.attributes) == (
        ("id", "id"),
        ("name", "name"),
    )
    assert tuple((v.name, v.storage_column) for v in customer.value_objects) == (
        ("address", "address"),
    )


def test_records_retain_the_tag_declaration_without_composing_a_column_sequence() -> None:
    # The framework-owned tag is a declaration on the root's strategy, and these
    # records carry it as one. Where it sits among the table's columns — and where
    # a document column sits — is `m-storage-layout`'s answer, not a descriptor fact.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="name", type="string", column="name"),
        ),
        value_objects=(ValueObject(name="badge", column="badge"),),
    )
    assert root.inheritance is not None
    assert root.inheritance.tag_column == "kind"
    assert tuple(a.column for a in root.attributes) == ("id", "name")
    assert tuple(v.storage_column for v in root.value_objects) == ("badge",)
    assert not hasattr(_records, "column_order")
