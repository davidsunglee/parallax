"""``validate_write`` unit tests (m-value-object write validation), over a
hand-built multi-type synthetic model — the SAME
"synthetic Widget model" convention `test_op_algebra_validate.py` uses for
`_literal_matches_type`'s full neutral-type sweep, applied here to the write
side's own value conformance. The 10 in-slice `when.write` rejected corpus
cases are exercised through the real corpus models in
`test_transaction_writes.py` (the developer-verb frontend) and `test_engine.py`
(the rejected lane); this
module covers the declared-composite walk's OWN internal branches the ten
witnessed shapes do not reach on their own: depth-0 entity-attribute
required-ness (a corpus shape none of the ten witness — every witnessed case
happens to keep the entity's own scalar attributes complete), the DB-computed-
marker exemption, sparse-mutation leniency at every level, to-many value-object
array walking, and the full m-core neutral-type vocabulary — in both the native
carrier and the portable literal spelling a neutral write row may carry.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
from _metamodel_support import Declaration, attribute, identity, key, source

from parallax.core._formation_profile import form_metamodel
from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT64,
    INT32,
    INT64,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    NeutralType,
)
from parallax.core.base import Decimal as DecimalType
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    Column,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    Table,
    TemporalDimension,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.unit_work import WriteRejectedError, validate_write

pytestmark = pytest.mark.unit

# A synthetic multi-type entity: every scalar neutral type as a NULLABLE
# top-level attribute (so a bare `{id, label}` row is a valid INSERT baseline
# regardless of which field a given test exercises), one required attribute
# (`label`), a to-one nested value object (`spec`, itself nullable, with a
# required nested `detail` carrying a nullable leaf `hint` — the leaf-of-the-tree
# shape with no further nesting), and a to-many value object (`tags`) for the
# array walk.
_WIDGET = identity("Widget")
_MONEY = DecimalType(precision=18, scale=2)

_SCALARS: dict[str, NeutralType] = {
    "marker": INT64,
    "flag": BOOLEAN,
    "count": INT32,
    "ratio": FLOAT64,
    "amount": _MONEY,
    "whenMade": DATE,
    "whenTouched": TIME,
    "tstamp": TIMESTAMP,
    "uid": UUID,
    "blob": BYTES,
}


def _nullable(name: str, neutral: NeutralType) -> AttributeMetadata:
    return AttributeMetadata(
        identity=AttributeIdentity(_WIDGET, name),
        type=neutral,
        storage=Column(name),
        nullable=True,
    )


_DETAIL = NestedValueObjectOccurrenceDeclaration(
    name="detail",
    shape=ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration("hint", type=STRING, nullable=True),),
    ),
)

_SPEC = ValueObjectOccurrenceDeclaration(
    name="spec",
    storage=Column("spec"),
    nullable=True,
    shape=ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration("note", type=STRING),),
        value_objects=(_DETAIL,),
    ),
)

# A to-one occurrence carrying a to-many nested one, so an element violation
# reported from inside the nested occurrence keeps its bracket index attached to
# the nested member's own name.
_BOOK = ValueObjectOccurrenceDeclaration(
    name="book",
    storage=Column("book"),
    nullable=True,
    shape=ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        value_objects=(
            NestedValueObjectOccurrenceDeclaration(
                name="phones",
                multiplicity=Multiplicity.MANY,
                shape=ValueObjectShapeDeclaration(
                    key=ValueObjectShapeKey(),
                    attributes=(ValueObjectAttributeDeclaration("number", type=STRING),),
                ),
            ),
        ),
    ),
)

_TAGS = ValueObjectOccurrenceDeclaration(
    name="tags",
    storage=Column("tags"),
    multiplicity=Multiplicity.MANY,
    shape=ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration("label", type=STRING),),
    ),
)

_WIDGET_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_WIDGET,
            container=Table("widget"),
            attributes=(
                key(_WIDGET),
                attribute(_WIDGET, "label", type=STRING),
                *(_nullable(name, neutral) for name, neutral in _SCALARS.items()),
            ),
            value_objects=(_SPEC, _BOOK, _TAGS),
        )
    )
)


def _entity(model: Metamodel, name: str) -> EntityMetadata:
    metadata = model.entity(identity(name))
    assert metadata is not None
    return metadata


_WIDGET_METADATA = _entity(_WIDGET_MODEL, "Widget")

# `tags` is a to-many occurrence, so it may not also be nullable (only a to-one
# may) — an insert row therefore always carries it, even empty.
_BASE_ROW: dict[str, object] = {"id": 1, "label": "L", "tags": []}


def _row(**overrides: object) -> dict[str, object]:
    row = dict(_BASE_ROW)
    row.update(overrides)
    return row


def _accept(row: dict[str, object], *, mutation: str = "insert") -> None:
    validate_write(_WIDGET_METADATA, row, _WIDGET_MODEL, mutation=mutation)


def _rejects(row: dict[str, object], *, mutation: str = "insert") -> WriteRejectedError:
    with pytest.raises(WriteRejectedError) as exc_info:
        _accept(row, mutation=mutation)
    return exc_info.value


# --------------------------------------------------------------------------- #
# Depth-0 entity attributes: required-ness, the DB-computed-marker exemption, #
# and sparse-mutation leniency.                                               #
# --------------------------------------------------------------------------- #
def test_valid_row_is_accepted_on_insert() -> None:
    _accept(_row())


def test_required_attribute_missing_at_depth_zero_on_insert() -> None:
    row = _row()
    del row["label"]
    assert _rejects(row).rule == "write-required-attribute-missing"


def test_required_attribute_null_at_depth_zero_on_insert() -> None:
    assert _rejects(_row(label=None)).rule == "write-required-attribute-missing"


def test_entity_attribute_type_mismatch() -> None:
    assert _rejects(_row(flag="not-a-bool")).rule == "write-value-type-mismatch"


def test_scalar_write_marker_exempts_type_checking() -> None:
    # A DB-computed marker on a scalar attribute column binds verbatim
    # regardless of its declared neutral type (m-value-object "Writing").
    _accept(_row(marker={"computed": "maxPlusOne"}))
    _accept(_row(marker={"increment": 1}))


def test_sparse_update_does_not_require_an_absent_entity_attribute() -> None:
    _accept({"id": 1}, mutation="update")  # `label` untouched


def test_sparse_update_still_type_checks_a_present_attribute() -> None:
    assert (
        _rejects({"id": 1, "flag": "nope"}, mutation="update").rule == "write-value-type-mismatch"
    )


# --------------------------------------------------------------------------- #
# Value objects: top-level presence/nullability, nested required-ness, the    #
# leaf-of-the-tree shape (no further nesting), and non-document values.       #
# --------------------------------------------------------------------------- #
def test_nullable_value_object_absent_is_fine_on_insert() -> None:
    _accept(_row())  # `spec` never set


def test_nullable_value_object_explicit_null_is_fine() -> None:
    _accept(_row(spec=None))


def test_sparse_update_does_not_require_an_absent_value_object() -> None:
    _accept({"id": 1}, mutation="update")  # `spec` untouched, fine


def test_nested_value_object_required_missing_once_the_parent_is_present() -> None:
    # `detail` is required (`nullable: false`) the moment `spec` is present,
    # regardless of mutation kind -- there is no sparse write below a
    # value-object document boundary.
    row = _row(spec={"note": "n"})
    assert _rejects(row).rule == "write-required-value-object-missing"
    assert _rejects(row, mutation="update").rule == "write-required-value-object-missing"


def test_nested_leaf_nullable_attribute_absent_is_fine() -> None:
    # `detail` declares no further nested value objects (the leaf-of-the-tree
    # shape) and its own `hint` is nullable.
    _accept(_row(spec={"note": "n", "detail": {}}))


def test_nested_leaf_attribute_type_mismatch() -> None:
    assert _rejects(_row(spec={"note": "n", "detail": {"hint": 7}})).rule == (
        "write-value-type-mismatch"
    )


def test_value_object_document_must_be_a_mapping() -> None:
    assert _rejects(_row(spec="not-a-document")).rule == "write-value-type-mismatch"


# --------------------------------------------------------------------------- #
# To-many value objects: the array walk.                                      #
# --------------------------------------------------------------------------- #
def test_many_value_object_must_be_a_sequence() -> None:
    assert _rejects(_row(tags="not-a-list")).rule == "write-value-type-mismatch"


def test_many_value_object_empty_array_is_fine() -> None:
    # "emptiness is not a nullability violation" (m-value-object).
    _accept(_row(tags=[]))


def test_many_value_object_element_must_be_a_mapping() -> None:
    assert _rejects(_row(tags=[123])).rule == "write-value-type-mismatch"


def test_many_value_object_element_type_mismatch() -> None:
    assert _rejects(_row(tags=[{"label": "ok"}, {"label": 42}])).rule == "write-value-type-mismatch"


def test_many_value_object_valid_elements() -> None:
    _accept(_row(tags=[{"label": "a"}, {"label": "b"}]))


def test_a_nested_many_element_violation_keeps_its_index_on_the_nested_member() -> None:
    # The index attaches to `phones` with no separating dot, and the leaf name
    # dot-joins after it.
    error = _rejects(_row(book={"phones": [{"number": "1"}, {"number": 2}]}))
    assert error.rule == "write-value-type-mismatch"
    assert str(error).startswith("Widget.book.phones[1].number:")


# --------------------------------------------------------------------------- #
# Value conformance: the full m-core neutral-type vocabulary, exercised       #
# through `validate_write` over each depth-0 attribute — a native carrier and #
# the portable literal spelling a neutral write row may carry for it both     #
# conform, and neither a wrong carrier nor a malformed literal does.          #
# --------------------------------------------------------------------------- #
_TYPE_CASES: list[tuple[str, object, bool]] = [
    ("flag", True, True),
    ("flag", "x", False),
    ("count", 3, True),
    ("count", "3", False),
    ("count", True, False),  # a bool is never a numeric literal
    ("count", 2**31, False),  # outside the declared width
    ("ratio", 1.5, True),
    ("ratio", 3, True),  # an integer literal spells a float value
    ("ratio", "x", False),
    ("amount", Decimal("1.00"), True),
    ("amount", 3, True),
    ("amount", 1.5, True),
    ("amount", 1.005, False),  # more fractional digits than the declared scale
    ("amount", "x", False),
    ("whenMade", dt.date(2024, 1, 1), True),
    ("whenMade", "2024-01-01", True),
    ("whenMade", "not-a-date", False),
    ("whenMade", dt.datetime(2024, 1, 1, tzinfo=dt.UTC), False),  # not a bare date
    ("whenMade", 5, False),
    ("whenTouched", dt.time(12, 0), True),
    ("whenTouched", "12:00", True),
    ("whenTouched", 5, False),
    ("tstamp", dt.datetime(2024, 1, 1, tzinfo=dt.UTC), True),
    ("tstamp", "2024-01-01T00:00:00Z", True),
    ("tstamp", "2024-01-01T00:00:00", False),  # a naive instant carries no offset
    ("tstamp", 5, False),
    ("uid", uuid.UUID("123e4567-e89b-12d3-a456-426614174000"), True),
    ("uid", "123e4567-e89b-12d3-a456-426614174000", True),
    ("uid", "not-a-uuid", False),
    ("uid", 5, False),
    ("blob", b"\x01\x02", True),
    ("blob", "0102", True),
    ("blob", "not-hex", False),
    ("blob", 5, False),
]


@pytest.mark.parametrize(("field", "value", "valid"), _TYPE_CASES)
def test_value_conformance_over_the_full_neutral_type_vocabulary(
    field: str, value: Any, valid: bool
) -> None:
    row = _row(**{field: value})
    if valid:
        _accept(row)
    else:
        assert _rejects(row).rule == "write-value-type-mismatch"


def test_string_accepts_text_and_rejects_others() -> None:
    _accept(_row(label="x"))
    assert _rejects(_row(label=5)).rule == "write-value-type-mismatch"


# --------------------------------------------------------------------------- #
# Temporal axis attributes: the milestone interval                            #
# bounds a temporal write never authors — excluded from the required/type     #
# walk regardless of mutation kind, since they are Clock-supplied / axis-     #
# explicit instruction-level context, never a neutral write-row member        #
# (`m-unit-work` "the instant surface is axis-explicit"; ADR 0010).           #
# --------------------------------------------------------------------------- #
_GAUGE = identity("Gauge")
_GAUGE_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_GAUGE,
            container=Table("gauge"),
            attributes=(
                key(_GAUGE),
                attribute(_GAUGE, "reading", type=_MONEY),
                attribute(_GAUGE, "txStart", type=TIMESTAMP, column="in_z"),
                attribute(_GAUGE, "txEnd", type=TIMESTAMP, column="out_z"),
            ),
            as_of_axes=(
                AsOfAxisMetadata(
                    dimension=TemporalDimension.TRANSACTION_TIME,
                    start_attribute=AttributeIdentity(_GAUGE, "txStart"),
                    end_attribute=AttributeIdentity(_GAUGE, "txEnd"),
                ),
            ),
        )
    )
)
_GAUGE_METADATA = _entity(_GAUGE_MODEL, "Gauge")


def test_temporal_axis_attributes_are_never_required_on_a_full_document_insert() -> None:
    # A full-document (insert) row omitting `txStart` / `txEnd`
    # entirely is still valid: the milestone bounds are Clock-supplied /
    # instruction-level, never authored on the neutral write row.
    validate_write(_GAUGE_METADATA, {"id": 1, "reading": 20.00}, _GAUGE_MODEL, mutation="insert")


def test_temporal_axis_attributes_are_never_type_checked_even_when_present() -> None:
    # A stray, wrongly-typed axis value is silently ignored (excluded before the
    # type walk ever sees it) — the lowering seam is what would reject an
    # actually-authored one, not this pre-SQL structural validator.
    row = {"id": 1, "reading": 20.00, "txStart": 12345}
    validate_write(_GAUGE_METADATA, row, _GAUGE_MODEL, mutation="insert")
