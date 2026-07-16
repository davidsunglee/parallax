"""``validate_write`` unit tests (m-value-object write validation, COR-3 Phase
8 increment 2), over a hand-built multi-type synthetic model — the SAME
"synthetic Widget model" convention `test_op_algebra_validate.py` uses for
`_literal_matches_type`'s full neutral-type sweep, applied here to the write
side's own `_type_matches`. The 10 in-slice `when.write` rejected corpus
cases are exercised through the real corpus models in `test_transact.py`
(the developer-verb frontend) and `test_engine.py` (the rejected lane); this
module covers the declared-composite walk's OWN internal branches the ten
witnessed shapes do not reach on their own: depth-0 entity-attribute
required-ness (a corpus shape none of the ten witness — every witnessed case
happens to keep the entity's own scalar attributes complete), the declared
`default` / DB-computed-marker exemptions, sparse-mutation leniency at every
level, `cardinality: many` value-object array walking, and the full m-core
neutral-type vocabulary `_type_matches` accepts.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest

from parallax.core.descriptor import (
    AsOfAttribute,
    Attribute,
    Entity,
    Metamodel,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.core.unit_work import WriteRejectedError, validate_write

pytestmark = pytest.mark.unit

# A synthetic multi-type entity: every scalar neutral type as a NULLABLE
# top-level attribute (so a bare `{id, label, seeded}` row is a valid INSERT
# baseline regardless of which field a given test exercises), one required
# attribute with no default (`label`), one required attribute WITH a declared
# default (`seeded`), a `cardinality: one` nested value object (`spec`, itself
# nullable, with a required nested `detail` carrying a nullable leaf `hint` —
# the leaf-of-the-tree shape with no further nesting), and a `cardinality:
# many` value object (`tags`) for the array walk.
_WIDGET = Entity(
    name="Widget",
    table="widget",
    mutability="transactional",
    attributes=(
        Attribute(name="id", type="int64", column="id", primary_key=True),
        Attribute(name="label", type="string", column="label"),
        Attribute(name="seeded", type="string", column="seeded", default="fallback"),
        Attribute(name="marker", type="int64", column="marker", nullable=True),
        Attribute(name="flag", type="boolean", column="flag", nullable=True),
        Attribute(name="count", type="int32", column="count", nullable=True),
        Attribute(name="ratio", type="float64", column="ratio", nullable=True),
        Attribute(name="amount", type="decimal(18,2)", column="amount", nullable=True),
        Attribute(name="whenMade", type="date", column="when_made", nullable=True),
        Attribute(name="whenTouched", type="time", column="when_touched", nullable=True),
        Attribute(name="tstamp", type="timestamp", column="tstamp", nullable=True),
        Attribute(name="uid", type="uuid", column="uid", nullable=True),
        Attribute(name="blob", type="bytes", column="blob", nullable=True),
    ),
    value_objects=(
        ValueObject(
            name="spec",
            column="spec",
            nullable=True,
            attributes=(ValueObjectAttribute(name="note", type="string"),),
            value_objects=(
                NestedValueObject(
                    name="detail",
                    nullable=False,
                    attributes=(ValueObjectAttribute(name="hint", type="string", nullable=True),),
                ),
            ),
        ),
        ValueObject(
            name="tags",
            column="tags",
            cardinality="many",
            nullable=True,
            attributes=(ValueObjectAttribute(name="label", type="string"),),
        ),
    ),
)
_META = Metamodel(entities=(_WIDGET,))

_BASE_ROW: dict[str, object] = {"id": 1, "label": "L", "seeded": "S"}


def _row(**overrides: object) -> dict[str, object]:
    row = dict(_BASE_ROW)
    row.update(overrides)
    return row


def _rejects(row: dict[str, object], *, mutation: str = "insert") -> WriteRejectedError:
    with pytest.raises(WriteRejectedError) as exc_info:
        validate_write(_WIDGET, row, _META, mutation=mutation)
    return exc_info.value


# --------------------------------------------------------------------------- #
# Depth-0 entity attributes: required-ness, the declared `default` exemption, #
# the DB-computed-marker exemption, and sparse-mutation leniency.             #
# --------------------------------------------------------------------------- #
def test_valid_row_is_accepted_on_insert() -> None:
    validate_write(_WIDGET, _row(), _META, mutation="insert")  # no raise


def test_required_attribute_missing_at_depth_zero_on_insert() -> None:
    row: dict[str, object] = {"id": 1, "seeded": "S"}  # `label` omitted entirely
    assert _rejects(row).rule == "write-required-attribute-missing"


def test_required_attribute_null_at_depth_zero_on_insert() -> None:
    assert _rejects(_row(label=None)).rule == "write-required-attribute-missing"


def test_declared_default_exempts_absence_on_insert() -> None:
    row = {"id": 1, "label": "L"}  # `seeded` omitted, but it declares a default
    validate_write(_WIDGET, row, _META, mutation="insert")  # no raise


def test_entity_attribute_type_mismatch() -> None:
    assert _rejects(_row(flag="not-a-bool")).rule == "write-value-type-mismatch"


def test_scalar_write_marker_exempts_type_checking() -> None:
    # A DB-computed marker on a scalar attribute column binds verbatim
    # regardless of its declared neutral type (m-value-object "Writing").
    validate_write(_WIDGET, _row(marker={"computed": "maxPlusOne"}), _META, mutation="insert")
    validate_write(_WIDGET, _row(marker={"increment": 1}), _META, mutation="insert")


def test_sparse_update_does_not_require_an_absent_entity_attribute() -> None:
    row: dict[str, object] = {"id": 1}  # `label` / `seeded` untouched
    validate_write(_WIDGET, row, _META, mutation="update")  # no raise


def test_sparse_update_still_type_checks_a_present_attribute() -> None:
    assert (
        _rejects({"id": 1, "flag": "nope"}, mutation="update").rule == "write-value-type-mismatch"
    )


# --------------------------------------------------------------------------- #
# Value objects: top-level presence/nullability, nested required-ness, the    #
# leaf-of-the-tree shape (no further nesting), and non-document values.       #
# --------------------------------------------------------------------------- #
def test_nullable_value_object_absent_is_fine_on_insert() -> None:
    validate_write(_WIDGET, _row(), _META, mutation="insert")  # `spec` never set


def test_nullable_value_object_explicit_null_is_fine() -> None:
    validate_write(_WIDGET, _row(spec=None), _META, mutation="insert")


def test_sparse_update_does_not_require_an_absent_value_object() -> None:
    row: dict[str, object] = {"id": 1}
    validate_write(_WIDGET, row, _META, mutation="update")  # `spec` untouched, fine


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
    row = _row(spec={"note": "n", "detail": {}})
    validate_write(_WIDGET, row, _META, mutation="insert")  # no raise


def test_nested_leaf_attribute_type_mismatch() -> None:
    row = _row(spec={"note": "n", "detail": {"hint": 7}})
    assert _rejects(row).rule == "write-value-type-mismatch"


def test_value_object_document_must_be_a_mapping() -> None:
    assert _rejects(_row(spec="not-a-document")).rule == "write-value-type-mismatch"


# --------------------------------------------------------------------------- #
# `cardinality: many` value objects: the array walk.                          #
# --------------------------------------------------------------------------- #
def test_many_value_object_must_be_a_sequence() -> None:
    assert _rejects(_row(tags="not-a-list")).rule == "write-value-type-mismatch"


def test_many_value_object_empty_array_is_fine() -> None:
    # "emptiness is not a nullability violation" (m-value-object).
    validate_write(_WIDGET, _row(tags=[]), _META, mutation="insert")


def test_many_value_object_element_must_be_a_mapping() -> None:
    assert _rejects(_row(tags=[123])).rule == "write-value-type-mismatch"


def test_many_value_object_element_type_mismatch() -> None:
    assert _rejects(_row(tags=[{"label": "ok"}, {"label": 42}])).rule == "write-value-type-mismatch"


def test_many_value_object_valid_elements() -> None:
    row = _row(tags=[{"label": "a"}, {"label": "b"}])
    validate_write(_WIDGET, row, _META, mutation="insert")  # no raise


# --------------------------------------------------------------------------- #
# `_type_matches`: the full m-core neutral-type vocabulary, exercised through #
# `validate_write` over each depth-0 attribute (python.md §2).                #
# --------------------------------------------------------------------------- #
_TYPE_CASES: list[tuple[str, object, bool]] = [
    ("flag", True, True),
    ("flag", "x", False),
    ("count", 3, True),
    ("count", "3", False),
    ("count", True, False),  # a bool is never a numeric literal
    ("ratio", 1.5, True),
    ("ratio", 3, True),  # int accepted (lossless)
    ("ratio", "x", False),
    ("amount", Decimal("1.00"), True),
    ("amount", 3, True),
    ("amount", 1.5, True),
    ("amount", "x", False),
    ("whenMade", dt.date(2024, 1, 1), True),
    ("whenMade", "2024-01-01", True),
    ("whenMade", dt.datetime(2024, 1, 1, tzinfo=dt.UTC), False),  # not a bare date
    ("whenMade", 5, False),
    ("whenTouched", dt.time(12, 0), True),
    ("whenTouched", "12:00", True),
    ("whenTouched", 5, False),
    ("tstamp", dt.datetime(2024, 1, 1, tzinfo=dt.UTC), True),
    ("tstamp", "2024-01-01T00:00:00Z", True),
    ("tstamp", 5, False),
    ("uid", uuid.uuid4(), True),
    ("uid", "not-checked-for-format", True),
    ("uid", 5, False),
    ("blob", b"x", True),
    ("blob", "x", True),
    ("blob", 5, False),
]


@pytest.mark.parametrize("field,value,valid", _TYPE_CASES)
def test_type_matches_the_full_neutral_type_vocabulary(field: str, value: Any, valid: bool) -> None:
    row = _row(**{field: value})
    if valid:
        validate_write(_WIDGET, row, _META, mutation="insert")  # no raise
    else:
        assert _rejects(row).rule == "write-value-type-mismatch"


def test_type_matches_string_accepts_string_and_rejects_others() -> None:
    validate_write(_WIDGET, _row(label="x"), _META, mutation="insert")
    assert _rejects(_row(label=5)).rule == "write-value-type-mismatch"


# --------------------------------------------------------------------------- #
# Temporal axis columns (COR-3 Phase 8 increment 4): the milestone interval    #
# bounds a temporal write never authors — excluded from the required/type     #
# walk regardless of mutation kind, since they are Clock-supplied / axis-     #
# explicit instruction-level context, never a neutral write-row member        #
# (`m-unit-work` "the instant surface is axis-explicit"; ADR 0010).           #
# --------------------------------------------------------------------------- #
_GAUGE = Entity(
    name="Gauge",
    table="gauge",
    mutability="transactional",
    attributes=(
        Attribute(name="id", type="int64", column="id", primary_key=True),
        Attribute(name="reading", type="decimal(18,2)", column="reading"),
        Attribute(name="processingFrom", type="timestamp", column="in_z"),
        Attribute(name="processingTo", type="timestamp", column="out_z"),
    ),
    as_of_attributes=(
        AsOfAttribute(
            name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
        ),
    ),
)
_TEMPORAL_META = Metamodel(entities=(_GAUGE,))


def test_temporal_axis_columns_are_never_required_on_a_full_document_insert() -> None:
    # A full-document (insert) row omitting `processingFrom` / `processingTo`
    # entirely is still valid: the milestone bounds are Clock-supplied /
    # instruction-level, never authored on the neutral write row.
    row = {"id": 1, "reading": 20.00}
    validate_write(_GAUGE, row, _TEMPORAL_META, mutation="insert")  # no raise


def test_temporal_axis_columns_are_never_type_checked_even_when_present() -> None:
    # A stray, wrongly-typed axis column value is silently ignored (excluded
    # before the type walk ever sees it) — the lowering seam is what would
    # reject an actually-authored one, not this pre-SQL structural validator.
    row = {"id": 1, "reading": 20.00, "processingFrom": 12345}
    validate_write(_GAUGE, row, _TEMPORAL_META, mutation="insert")  # no raise
