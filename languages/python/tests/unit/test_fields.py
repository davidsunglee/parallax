"""Field / Relationship declaration helpers."""

from __future__ import annotations

import pytest

from parallax.core.descriptor import OrderByTerm
from parallax.core.entity import Field, FieldSpec, Relationship, RelationshipSpec

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


def test_field_ignores_non_scalar_sequence_fields() -> None:
    # Malformed extra fields are coerced to None rather than mis-typed.
    spec = Field(pk_generator={"strategy": "max", "sequenceName": 7, "batchSize": "x"})
    pk = spec.pk_generator
    assert pk is not None
    assert pk.strategy == "max"
    assert pk.sequence_name is None
    assert pk.batch_size is None


def test_field_rejects_unknown_pk_strategies() -> None:
    with pytest.raises(ValueError, match="pk generator"):
        Field(pk_generator="wild")
    with pytest.raises(ValueError, match="pk generator"):
        Field(pk_generator={"strategy": "wild"})


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
