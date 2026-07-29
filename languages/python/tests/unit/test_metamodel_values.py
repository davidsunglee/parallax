"""m-core / m-metamodel: the structured value layer and its construction constraints."""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Callable

import pytest

from parallax.core import base
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    NOT_PRIMARY_KEY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    ApplicationAssigned,
    AttributeIdentity,
    AttributeMetadata,
    AttributeReference,
    Cardinality,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    IndexIdentity,
    Max,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    NotPrimaryKey,
    PersistenceMode,
    PrimaryKey,
    RelationshipIdentity,
    RelationshipReference,
    RelativeEntityReference,
    Sequence,
    SortDirection,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedRelationshipOrder,
    ValueObjectAttributeDeclaration,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    resolve_entity_reference,
)

_ORDERS = EntityIdentity("parallax.test", "Order")
_OWNERLESS = EntityIdentity(None, "Order")


def test_entity_identity_spells_its_canonical_name_and_sort_key() -> None:
    assert _ORDERS.canonical == "parallax.test.Order"
    assert _OWNERLESS.canonical == "Order"
    assert _ORDERS.sort_key == ("parallax.test", "Order")
    assert _OWNERLESS.sort_key == ("", "Order")


def test_an_empty_namespace_is_unconstructible() -> None:
    with pytest.raises(ValueError, match="namespace"):
        EntityIdentity("", "Order")


def test_an_ill_formed_entity_name_stays_constructible_so_it_can_locate_its_issue() -> None:
    assert EntityIdentity(None, "a.b").name == "a.b"
    assert EntityIdentity(None, "").name == ""


@pytest.mark.parametrize(
    "construct",
    [
        pytest.param(lambda: AttributeIdentity(_ORDERS, ""), id="attribute"),
        pytest.param(lambda: RelationshipIdentity(_ORDERS, ""), id="relationship"),
        pytest.param(lambda: IndexIdentity(_ORDERS, ""), id="index"),
        pytest.param(lambda: ValueObjectIdentity(_ORDERS, ()), id="empty-path"),
        pytest.param(lambda: ValueObjectIdentity(_ORDERS, ("a", "")), id="empty-path-segment"),
        pytest.param(
            lambda: ValueObjectAttributeIdentity(ValueObjectIdentity(_ORDERS, ("a",)), ""),
            id="value-object-attribute",
        ),
        pytest.param(lambda: RelativeEntityReference(""), id="relative-reference"),
        pytest.param(
            lambda: AttributeReference(ExactEntityReference(_ORDERS), ""), id="attribute-reference"
        ),
        pytest.param(
            lambda: RelationshipReference(ExactEntityReference(_ORDERS), ""),
            id="relationship-reference",
        ),
        pytest.param(lambda: Table(""), id="table"),
        pytest.param(lambda: Column(""), id="column"),
        pytest.param(lambda: Sequence(""), id="sequence-name"),
        pytest.param(lambda: Sequence("s", batch_size=0), id="sequence-batch-size"),
        pytest.param(lambda: Sequence("s", increment_size=0), id="sequence-increment-size"),
        pytest.param(lambda: TablePerHierarchy(""), id="tag-column"),
        pytest.param(lambda: ConcreteSubtype(_ORDERS, ""), id="tag-value"),
        pytest.param(
            lambda: AttributeMetadata(
                AttributeIdentity(_ORDERS, "sku"), base.STRING, Column("sku"), max_length=0
            ),
            id="max-length",
        ),
        pytest.param(
            lambda: AttributeMetadata(
                AttributeIdentity(_ORDERS, "quantity"), base.INT64, Column("quantity"), max_length=8
            ),
            id="max-length-on-a-non-text-type",
        ),
        pytest.param(lambda: UnresolvedRelationshipOrder(""), id="order-term"),
        pytest.param(
            lambda: ValueObjectAttributeDeclaration("", base.STRING), id="value-object-attribute"
        ),
        pytest.param(
            lambda: NestedValueObjectOccurrenceDeclaration(
                "", ValueObjectShapeDeclaration(ValueObjectShapeKey())
            ),
            id="nested-occurrence",
        ),
        pytest.param(
            lambda: ValueObjectOccurrenceDeclaration(
                "", Column("c"), ValueObjectShapeDeclaration(ValueObjectShapeKey())
            ),
            id="top-level-occurrence",
        ),
    ],
)
def test_invalid_payloads_are_unconstructible(construct: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        construct()


def test_a_relative_reference_adopts_its_owners_namespace() -> None:
    assert resolve_entity_reference(_ORDERS, RelativeEntityReference("Item")) == EntityIdentity(
        "parallax.test", "Item"
    )


def test_an_ownerless_owner_resolves_a_relative_reference_without_a_namespace() -> None:
    assert resolve_entity_reference(_OWNERLESS, RelativeEntityReference("Item")) == EntityIdentity(
        None, "Item"
    )


def test_an_exact_reference_ignores_its_owner() -> None:
    target = EntityIdentity("other", "Item")
    assert resolve_entity_reference(_ORDERS, ExactEntityReference(target)) == target


def test_cardinality_carries_structured_side_multiplicities() -> None:
    assert Cardinality.ONE_TO_ONE.source is Multiplicity.ONE
    assert Cardinality.ONE_TO_ONE.target is Multiplicity.ONE
    assert Cardinality.MANY_TO_ONE.source is Multiplicity.MANY
    assert Cardinality.MANY_TO_ONE.target is Multiplicity.ONE
    assert Cardinality.ONE_TO_MANY.source is Multiplicity.ONE
    assert Cardinality.ONE_TO_MANY.target is Multiplicity.MANY


def test_nullary_union_members_have_shared_singletons() -> None:
    assert ApplicationAssigned() == APPLICATION_ASSIGNED
    assert Max() == MAX
    assert MAX != APPLICATION_ASSIGNED
    assert NotPrimaryKey() == NOT_PRIMARY_KEY
    assert TablePerConcreteSubtype() == TABLE_PER_CONCRETE_SUBTYPE


def test_a_generation_is_reachable_only_through_the_primary_key_branch() -> None:
    assert PrimaryKey().generation == APPLICATION_ASSIGNED
    assert PrimaryKey(Sequence("order_seq")).generation == Sequence(
        "order_seq", batch_size=1, initial_value=1, increment_size=1
    )
    assert not hasattr(NOT_PRIMARY_KEY, "generation")


def test_the_ordering_and_axis_vocabularies_are_closed() -> None:
    assert [direction.name for direction in SortDirection] == ["ASCENDING", "DESCENDING"]
    assert [mode.name for mode in PersistenceMode] == ["READ_WRITE", "READ_ONLY"]
    assert [dimension.name for dimension in TemporalDimension] == [
        "VALID_TIME",
        "TRANSACTION_TIME",
    ]
    assert TemporalDimension.VALID_TIME.value < TemporalDimension.TRANSACTION_TIME.value


def test_inheritance_variants_carry_the_role_without_a_parallel_field() -> None:
    root = AbstractRoot(TablePerHierarchy("kind"))
    assert root.strategy == TablePerHierarchy("kind")
    assert AbstractSubtype(_ORDERS).parent == _ORDERS
    assert ConcreteSubtype(_ORDERS).tag_value is None
    assert ConcreteSubtype(_ORDERS, "order").tag_value == "order"
    assert not hasattr(AbstractSubtype(_ORDERS), "strategy")


def test_a_many_value_object_occurrence_stays_nullable_at_construction() -> None:
    """A Many occurrence that is also nullable is a representable declaration.

    Null and empty would then both denote no contained values, which is
    invalid — but that invariant spans an occurrence's two members against a
    model-wide rule, so a semantic Rule Set rejects it with its own coded,
    located Issue. Making the state unconstructible here would put the defect
    beyond that Rule Set's reach and beyond a model author's diagnostics.
    """
    shape = ValueObjectShapeDeclaration(ValueObjectShapeKey())
    top_level = ValueObjectOccurrenceDeclaration(
        "addresses", Column("addresses"), shape, multiplicity=Multiplicity.MANY, nullable=True
    )
    nested = NestedValueObjectOccurrenceDeclaration(
        "lines", shape, multiplicity=Multiplicity.MANY, nullable=True
    )
    assert (top_level.multiplicity, top_level.nullable) == (Multiplicity.MANY, True)
    assert (nested.multiplicity, nested.nullable) == (Multiplicity.MANY, True)


def test_a_shape_key_compares_by_reference_not_structure() -> None:
    one = ValueObjectShapeKey()
    another = ValueObjectShapeKey()
    assert one == one
    assert one != another
    assert len({one, another, one}) == 2


def test_a_decimal_type_requires_serializable_bounds() -> None:
    assert base.Decimal(18, 2) == base.Decimal(precision=18, scale=2)
    with pytest.raises(ValueError, match="precision"):
        base.Decimal(0, 9)
    with pytest.raises(ValueError, match="scale"):
        base.Decimal(2, 5)
    with pytest.raises(ValueError, match="scale"):
        base.Decimal(2, -1)


@pytest.mark.parametrize(
    ("value", "declared", "expected"),
    [
        (True, base.BOOLEAN, True),
        (True, base.INT64, False),
        (1, base.BOOLEAN, False),
        (1, base.INT32, True),
        (2**31 - 1, base.INT32, True),
        (-(2**31), base.INT32, True),
        (2**31, base.INT32, False),
        (-(2**31) - 1, base.INT32, False),
        (2**31, base.INT64, True),
        (2**63 - 1, base.INT64, True),
        (2**63, base.INT64, False),
        ("1", base.INT64, False),
        (1.5, base.FLOAT32, True),
        (3.5e38, base.FLOAT32, False),
        (float("inf"), base.FLOAT32, False),
        (1e300, base.FLOAT64, True),
        (float("nan"), base.FLOAT64, False),
        (float("-inf"), base.FLOAT64, False),
        (2, base.FLOAT64, False),
        ("x", base.FLOAT64, False),
        (decimal.Decimal("1.5"), base.Decimal(18, 2), True),
        (decimal.Decimal("1.500"), base.Decimal(18, 2), True),
        (decimal.Decimal("-1.5"), base.Decimal(18, 2), True),
        (decimal.Decimal("0.000"), base.Decimal(18, 2), True),
        (decimal.Decimal("1.234"), base.Decimal(18, 2), False),
        (decimal.Decimal("1234567890123456.78"), base.Decimal(18, 2), True),
        (decimal.Decimal("12345678901234567.89"), base.Decimal(18, 2), False),
        (decimal.Decimal("100"), base.Decimal(3, 0), True),
        (decimal.Decimal("1E+2"), base.Decimal(2, 0), False),
        (decimal.Decimal("NaN"), base.Decimal(18, 2), False),
        (decimal.Decimal("Infinity"), base.Decimal(18, 2), False),
        (1.5, base.Decimal(18, 2), False),
        (2, base.Decimal(18, 2), False),
        (object(), base.Decimal(18, 2), False),
        ("text", base.STRING, True),
        ("\ud800", base.STRING, False),
        (1, base.STRING, False),
        (b"raw", base.BYTES, True),
        ("raw", base.BYTES, False),
        (1, base.BYTES, False),
        (dt.date(2026, 1, 1), base.DATE, True),
        (dt.datetime(2026, 1, 1, tzinfo=dt.UTC), base.DATE, False),
        ("2026-01-01", base.DATE, False),
        (dt.time(12, 0), base.TIME, True),
        (dt.time(12, 0, tzinfo=dt.UTC), base.TIME, False),
        ("12:00:00", base.TIME, False),
        (dt.datetime(2026, 1, 1, tzinfo=dt.UTC), base.TIMESTAMP, True),
        (dt.datetime(2026, 1, 1), base.TIMESTAMP, False),
        ("2026-01-01T00:00:00Z", base.TIMESTAMP, False),
        (uuid.uuid4(), base.UUID, True),
        ("6ba7b810-9dad-11d1-80b4-00c04fd430c8", base.UUID, False),
        ({"a": 1}, base.JSON, True),
        ([1, {"b": None}, "t", True, 1.5], base.JSON, True),
        (None, base.JSON, False),
        (float("nan"), base.JSON, False),
        ({1: "a"}, base.JSON, False),
        ({"a": "\ud800"}, base.JSON, False),
        ([object()], base.JSON, False),
    ],
)
def test_neutral_value_conformance_is_exact_logical_membership(
    value: object, declared: base.NeutralType, expected: bool
) -> None:
    assert base.matches_neutral_type(value, declared) is expected


# A runtime write validator asks membership of a value that may still carry its
# portable literal spelling, so it decodes first and then checks membership. That
# composite must be exact (no value the space cannot represent is admitted),
# lossless (an integer literal spells a float value only when some float of the
# target width carries it exactly), and total (a value outside the space
# classifies as a non-member, never raises).
def _runtime_member(value: object, declared: base.NeutralType) -> bool:
    return base.matches_neutral_type(base.decode_neutral_literal(value, declared), declared)


@pytest.mark.parametrize(
    ("value", "declared", "expected"),
    [
        (3, base.FLOAT64, True),
        (2**53, base.FLOAT64, True),
        (2**53 + 1, base.FLOAT64, False),
        (10**1000, base.FLOAT64, False),
        (-(10**1000), base.FLOAT64, False),
        (3, base.FLOAT32, True),
        (2**24, base.FLOAT32, True),
        (2**24 + 1, base.FLOAT32, False),
        (2**64, base.FLOAT32, True),
        (10**40, base.FLOAT32, False),
        (10**1000, base.FLOAT32, False),
        ("123e4567-e89b-12d3-a456-426614174000", base.UUID, True),
        ("not-a-uuid", base.UUID, False),
        ("deadbeef", base.BYTES, True),
        ("not-hex", base.BYTES, False),
        ("2026-01-01", base.DATE, True),
        ("2026-01-01T00:00:00+00:00", base.TIMESTAMP, True),
        ("2026-01-01T00:00:00.123456+00:00", base.TIMESTAMP, True),
        ("2026-01-01T00:00:00.1234560+00:00", base.TIMESTAMP, True),
        ("2026-01-01T00:00:00.1234567+00:00", base.TIMESTAMP, False),
        ("2026-01-01T00:00:00.12345678+00:00", base.TIMESTAMP, False),
        ("2026-01-01T00:00:00,1234567+00:00", base.TIMESTAMP, False),
        # A '.' date-time separator introduces the hour, so the fractional
        # second is a later run, and a fractional timezone offset is another;
        # sub-microsecond precision in any fractional field is rejected.
        ("2026-01-01.00:00:00.1234567+00:00", base.TIMESTAMP, False),
        ("2026-01-01.00:00:00,1234567+00:00", base.TIMESTAMP, False),
        ("2026-01-01.00:00:00.1234560+00:00", base.TIMESTAMP, True),
        ("2026-01-01T00:00:00.123456+01:02:03.1234567", base.TIMESTAMP, False),
        ("2026-01-01T00:00:00.123456+01:02:03.1234560", base.TIMESTAMP, True),
        ("00:00:00", base.TIME, True),
        ("00:00:00.123456", base.TIME, True),
        ("00:00:00.1234560", base.TIME, True),
        ("00:00:00.1234567", base.TIME, False),
        ("00:00:00,1234567", base.TIME, False),
        ("00:00:00.123456+01:02:03.1234567", base.TIME, False),
    ],
)
def test_runtime_neutral_membership_is_exact_lossless_and_total(
    value: object, declared: base.NeutralType, expected: bool
) -> None:
    assert _runtime_member(value, declared) is expected


@pytest.mark.parametrize("declared", [base.FLOAT32, base.FLOAT64])
def test_decoding_a_huge_integer_literal_does_not_raise(declared: base.NeutralType) -> None:
    # A magnitude no float can carry must not overflow; it decodes to itself and
    # fails membership, never crashing the validator that called it.
    decoded = base.decode_neutral_literal(10**1000, declared)
    assert decoded == 10**1000
    assert base.matches_neutral_type(decoded, declared) is False


# The DEVELOPER-facing write validators call `coerce_neutral_input` rather than
# the full wire decode above: only the input policy's own narrow,
# exact/lossless widenings apply (`python.md` "Neutral scalar type mapping"),
# so a `float` for a `decimal` is NEVER coerced (membership then rejects it),
# while an `int` for a `decimal`/`float` and a canonical UUID string still
# widen -- and there is no ISO date/time/timestamp or hex-`bytes` decode at
# all, since those are wire spellings the case-format ingestion seam decodes,
# never a form the input policy itself admits.
def _coerced_member(value: object, declared: base.NeutralType) -> bool:
    return base.matches_neutral_type(base.coerce_neutral_input(value, declared), declared)


@pytest.mark.parametrize(
    ("value", "declared", "expected"),
    [
        (3, base.Decimal(18, 2), True),
        (1.5, base.Decimal(18, 2), False),
        (3, base.FLOAT64, True),
        (2**53 + 1, base.FLOAT64, False),
        (3, base.FLOAT32, True),
        (10**40, base.FLOAT32, False),
        ("123e4567-e89b-12d3-a456-426614174000", base.UUID, True),
        ("not-a-uuid", base.UUID, False),
        (5, base.UUID, False),
        ("123E4567-E89B-12D3-A456-426614174000", base.UUID, False),
        ("123e4567e89b12d3a456426614174000", base.UUID, False),
        ("{123e4567-e89b-12d3-a456-426614174000}", base.UUID, False),
        ("urn:uuid:123e4567-e89b-12d3-a456-426614174000", base.UUID, False),
        ("deadbeef", base.BYTES, False),
        ("2026-01-01", base.DATE, False),
        ("2026-01-01T00:00:00+00:00", base.TIMESTAMP, False),
    ],
)
def test_coerce_neutral_input_applies_only_the_narrow_input_policy_widenings(
    value: object, declared: base.NeutralType, expected: bool
) -> None:
    assert _coerced_member(value, declared) is expected


def test_coerce_neutral_input_leaves_an_already_native_value_unchanged() -> None:
    native = decimal.Decimal("1.50")
    assert base.coerce_neutral_input(native, base.Decimal(18, 2)) is native
    stamp = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    assert base.coerce_neutral_input(stamp, base.TIMESTAMP) is stamp


def test_coerce_neutral_input_is_total_and_nonthrowing_on_a_huge_integer() -> None:
    # Mirrors `decode_neutral_literal`'s own overflow-safety proof above: a
    # magnitude no float can carry is left unchanged rather than raising.
    coerced = base.coerce_neutral_input(10**1000, base.FLOAT64)
    assert coerced == 10**1000
    assert base.matches_neutral_type(coerced, base.FLOAT64) is False
