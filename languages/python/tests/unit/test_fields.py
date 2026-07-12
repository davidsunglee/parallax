"""Field / Relationship declaration helpers."""

from __future__ import annotations

import pytest

from parallax.core.descriptor import OrderByTerm
from parallax.core.entity import (
    EntityDefinitionError,
    Field,
    FieldSpec,
    Relationship,
    RelationshipSpec,
)

pytestmark = pytest.mark.unit


def test_field_records_declared_metadata() -> None:
    spec = Field(primary_key=True, column="acct", type="int64", max_length=8, pk_generator="none")
    assert isinstance(spec, FieldSpec)
    assert spec.primary_key is True
    assert spec.column == "acct"
    assert spec.type == "int64"
    assert spec.max_length == 8
    assert spec.pk_generator is not None
    assert spec.pk_generator.strategy == "none"


def test_field_accepts_a_sequence_pk_generator_mapping() -> None:
    spec = Field(
        primary_key=True,
        pk_generator={
            "strategy": "sequence",
            "sequenceName": "s",
            "batchSize": 3,
            "initialValue": 100,
            "incrementSize": 10,
        },
    )
    pk = spec.pk_generator
    assert pk is not None
    assert (pk.strategy, pk.sequence_name, pk.batch_size, pk.initial_value, pk.increment_size) == (
        "sequence",
        "s",
        3,
        100,
        10,
    )


def test_field_accepts_a_partial_pk_generator_mapping() -> None:
    # An object form may omit every optional field; the extras stay unset (not
    # coerced to a value) and the strategy alone survives.
    spec = Field(pk_generator={"strategy": "max"})
    pk = spec.pk_generator
    assert pk is not None
    assert (pk.strategy, pk.sequence_name, pk.batch_size) == ("max", None, None)
    assert (pk.initial_value, pk.increment_size) == (None, None)


@pytest.mark.parametrize(
    "mapping",
    [
        {"strategy": "sequence", "batchSize": "not-an-int"},
        {"strategy": "sequence", "batchSize": True},  # bool is not an integer
        {"strategy": "sequence", "initialValue": 1.5},
        {"strategy": "sequence", "incrementSize": "x"},
        {"strategy": "sequence", "sequenceName": 7},
    ],
)
def test_field_rejects_wrong_typed_pk_generator_fields(mapping: dict[str, object]) -> None:
    # A present-but-wrong-typed field is a definition error, never silently
    # dropped/coerced to None (the schema types each pkGenerator field).
    with pytest.raises(EntityDefinitionError, match="pk generator"):
        Field(pk_generator=mapping)


@pytest.mark.parametrize(
    ("mapping", "field_name"),
    [
        ({"strategy": "sequence", "batchSize": None}, "batchSize"),
        ({"strategy": "sequence", "initialValue": None}, "initialValue"),
        ({"strategy": "sequence", "incrementSize": None}, "incrementSize"),
        ({"strategy": "sequence", "sequenceName": None}, "sequenceName"),
    ],
)
def test_field_rejects_explicit_none_pk_generator_fields(
    mapping: dict[str, object], field_name: str
) -> None:
    # A present key carrying `None` is a malformed declaration (the schema types
    # every optional field and admits no `null`); it must raise, not be silently
    # dropped as if the key were omitted.
    with pytest.raises(EntityDefinitionError, match=rf"`{field_name}`.*NoneType"):
        Field(pk_generator=mapping)


def test_field_pk_generator_omitted_optional_key_is_not_none_rejected() -> None:
    # Absence is legitimate: an omitted optional key leaves the field unset
    # rather than triggering the present-but-None rejection.
    spec = Field(pk_generator={"strategy": "sequence"})
    pk = spec.pk_generator
    assert pk is not None
    assert (pk.strategy, pk.sequence_name, pk.batch_size) == ("sequence", None, None)
    assert (pk.initial_value, pk.increment_size) == (None, None)


def test_field_rejects_unknown_pk_generator_fields() -> None:
    # The pkGenerator object is closed (`additionalProperties: false`).
    with pytest.raises(EntityDefinitionError, match="unknown field"):
        Field(pk_generator={"strategy": "sequence", "bogus": 1})


def test_field_rejects_unknown_pk_strategies() -> None:
    with pytest.raises(EntityDefinitionError, match="pk generator"):
        Field(pk_generator="wild")
    with pytest.raises(EntityDefinitionError, match="pk generator"):
        Field(pk_generator={"strategy": "wild"})
    with pytest.raises(EntityDefinitionError, match="pk generator"):
        Field(pk_generator={})  # object form requires a strategy


def test_field_without_a_pk_generator_leaves_it_unset() -> None:
    assert Field().pk_generator is None


def test_relationship_records_declared_metadata() -> None:
    spec = Relationship(
        cardinality="one-to-many",
        join="this.id = Item.orderId",
        related_entity="Item",
        reverse_name="order",
        dependent=True,
        foreign_key="order_id",
        order_by=[OrderByTerm(attr="id", direction="desc")],
    )
    assert isinstance(spec, RelationshipSpec)
    assert spec.related_entity == "Item"
    assert spec.order_by == (OrderByTerm(attr="id", direction="desc"),)


def test_relationship_order_by_defaults_to_empty() -> None:
    spec = Relationship(cardinality="many-to-one", join="x", related_entity="Y")
    assert spec.order_by == ()
