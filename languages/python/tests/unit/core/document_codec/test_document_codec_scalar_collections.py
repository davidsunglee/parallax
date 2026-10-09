"""Scalar collections through the document codec's own seams.

A ``many`` leaf is one scalar member holding an ordered array of its declared
type's canonical spellings. These tests hold the codec to that at its interface:
authoring in both modes, encoding, patching, reduction, the effective-change
rule, and the one stored-collection interpretation every read entry point shares.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Iterable, Mapping
from typing import cast

import pytest

from parallax.core.base import (
    FLOAT32,
    INT32,
    SQL_NULL,
    STRING,
    TIMESTAMP,
    Decimal,
    DocumentValue,
    FrozenMap,
    PresentDocument,
    coerce_neutral_input,
    matches_neutral_type,
    retain_document_value,
)
from parallax.core.document_codec import (
    MISSING,
    NULL,
    UNAVAILABLE,
    DocumentFinding,
    Leaf,
    MemberShape,
    Occurrence,
    OccurrenceCarrier,
    Present,
    SetScalar,
    apply_prepared_patches,
    classify_effective_change,
    decode_occurrence_classified,
    decode_scalar_many_classified,
    encode_occurrence,
    encode_scalar_many,
    locate_raw_entity_member,
    prepare_effective_change,
    prepare_patches,
    prepared_raw_member_classifier,
    reduce_declared_members,
)
from parallax.core.document_codec._authoring import (
    BORROWED_SOURCE_ACCESS,
    MAPPING_SOURCE_ACCESS,
    prepare_authoring,
    prepare_member_authoring,
    validate_member_authoring,
)
from parallax.core.document_codec._document import encode_managed_document
from parallax.core.document_codec._leaf import LeafEncodingError
from parallax.core.metamodel import AuthoringViolation, Multiplicity

_MANY = Multiplicity.MANY
_TAGS = Leaf("tags", STRING, False, _MANY)
_AMOUNTS = Leaf("amounts", Decimal(6, 2), False, _MANY)
_MARKS = Leaf("marks", INT32, False, _MANY)
_LINE = MemberShape(members=(Leaf("sku", STRING, False), _MARKS))
_DETAIL = MemberShape(members=(Leaf("labels", STRING, False, _MANY),))
_SHAPE = MemberShape(
    members=(
        Leaf("label", STRING, True),
        _TAGS,
        _AMOUNTS,
        Occurrence("detail", Multiplicity.ONE, True, _DETAIL),
        Occurrence("lines", _MANY, False, _LINE),
    )
)


def _normalize(leaf: Leaf, value: object, _path: str) -> tuple[object, bool]:
    managed = coerce_neutral_input(value, leaf.type)
    return retain_document_value(managed), matches_neutral_type(managed, leaf.type)


class _CountingNormalizer:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def __call__(self, leaf: Leaf, value: object, path: str) -> tuple[object, bool]:
        self.paths.append(path)
        return _normalize(leaf, value, path)


# --------------------------------------------------------------------------- #
# Authoring                                                                    #
# --------------------------------------------------------------------------- #


def test_a_produced_collection_is_one_ordered_tuple_keeping_normalized_duplicates() -> None:
    prepared = prepare_member_authoring(
        _AMOUNTS,
        (decimal.Decimal("1.5"), 7, decimal.Decimal("1.50")),
        source_access=BORROWED_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )

    assert prepared.failure is None
    assert prepared.value == (decimal.Decimal("1.5"), decimal.Decimal(7), decimal.Decimal("1.50"))
    assert type(prepared.value) is tuple


def test_validation_alone_normalizes_every_element_and_builds_no_collection() -> None:
    normalizer = _CountingNormalizer()

    failure = validate_member_authoring(
        _TAGS,
        ["a", "b"],
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=normalizer,
        path="Order.tags",
    )

    assert failure is None
    assert normalizer.paths == ["Order.tags[0]", "Order.tags[1]"]


@pytest.mark.parametrize(
    ("source", "violation"),
    [
        ("ab", AuthoringViolation("", "not-a-list", "ab")),
        ({"a": 1}, AuthoringViolation("", "not-a-list", {"a": 1})),
        (("a", 2, None), AuthoringViolation("[1]", "type-mismatch", 2, STRING)),
        (("a", None), AuthoringViolation("[1]", "type-mismatch", None, STRING)),
    ],
    ids=["string", "mapping", "first-invalid-element", "null-element"],
)
def test_a_collection_reports_its_first_shape_or_element_violation(
    source: object, violation: AuthoringViolation
) -> None:
    for produce in (True, False):
        failure = (
            prepare_member_authoring(
                _TAGS, source, source_access=MAPPING_SOURCE_ACCESS, normalize_leaf=_normalize
            ).failure
            if produce
            else validate_member_authoring(
                _TAGS, source, source_access=MAPPING_SOURCE_ACCESS, normalize_leaf=_normalize
            )
        )
        assert failure == violation


def test_a_null_collection_is_left_to_the_callers_nullability_judgement() -> None:
    assert (
        validate_member_authoring(
            _TAGS, None, source_access=MAPPING_SOURCE_ACCESS, normalize_leaf=_normalize
        )
        is None
    )


def test_document_authoring_fills_an_unnamed_collection_and_refuses_a_null_one() -> None:
    prepared = prepare_authoring(
        _SHAPE,
        {"tags": ["b", "a", "b"], "detail": {}, "lines": [{"sku": "x"}]},
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )

    assert prepared.failures == {}
    assert prepared.value == {
        "tags": ("b", "a", "b"),
        "detail": {"labels": ()},
        "lines": ({"sku": "x", "marks": ()},),
        "amounts": (),
    }
    nested = prepare_authoring(
        _SHAPE,
        {"detail": {"labels": None}, "lines": [{"sku": "x", "marks": [1, "2"]}]},
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )
    assert dict(nested.failures) == {
        3: AuthoringViolation("labels", "attribute-missing"),
        4: AuthoringViolation("[0].marks[1]", "type-mismatch", "2", INT32),
    }


# --------------------------------------------------------------------------- #
# Encoding and patching                                                        #
# --------------------------------------------------------------------------- #


def test_a_collection_encodes_as_its_ordered_canonical_array() -> None:
    assert encode_scalar_many(Decimal(6, 2), (decimal.Decimal("1.5"), decimal.Decimal(7))) == (
        "1.50",
        "7.00",
    )
    assert encode_scalar_many(FLOAT32, (1.2000000476837158, 0.0)) == (1.2, 0.0)
    assert encode_scalar_many(TIMESTAMP, (dt.datetime(2024, 6, 1, 10, tzinfo=dt.UTC),)) == (
        "2024-06-01T10:00:00.000000Z",
    )
    assert encode_scalar_many(STRING, ()) == ()


def test_an_element_outside_the_value_space_names_its_position() -> None:
    with pytest.raises(LeafEncodingError, match="element 1"):
        encode_scalar_many(INT32, (1, 2**40))


def test_a_managed_document_encodes_every_collection_omitted_or_null_as_empty() -> None:
    document = encode_managed_document(
        _SHAPE,
        {"tags": ("b", "a", "b"), "amounts": None, "lines": ({"sku": "x", "marks": (2, 2)},)},
    )

    assert document == {
        "tags": ("b", "a", "b"),
        "amounts": (),
        "lines": ({"sku": "x", "marks": (2, 2)},),
    }
    assert type(cast("object", document)) is FrozenMap


def test_a_scalar_patch_replaces_a_whole_collection_and_keeps_unknown_keys() -> None:
    prepared = prepare_patches(
        _SHAPE,
        [SetScalar(("tags",), Present(("z", "z"))), SetScalar(("amounts",), NULL)],
    )

    assert [(patch.path, patch.value, patch.leaf) for patch in prepared] == [
        (("tags",), ("z", "z"), None),
        (("amounts",), (), None),
    ]
    assert apply_prepared_patches(
        {"tags": ["a"], "amounts": ["1.00"], "future": [1, "x"]}, prepared
    ) == {"tags": ("z", "z"), "amounts": (), "future": (1, "x")}


def test_an_occurrence_encodes_a_nested_collection_through_its_carrier() -> None:
    carrier = OccurrenceCarrier(
        absent=MISSING,
        values=lambda record, shape: (
            cast("Mapping[str, object]", record).get(member.name, MISSING)
            for member in shape.members
        ),
        elements=lambda value: cast("Iterable[object]", value),
    )

    encoded = encode_occurrence(
        [{"sku": "a", "marks": (2, 1, 2)}, {"sku": "b"}],
        _LINE,
        _MANY,
        carrier,
        encode_leaf=lambda neutral_type, value: f"{neutral_type}:{value}",
        build_object=dict,
        build_array=list,
    )

    assert encoded == [
        {"sku": "String():a", "marks": ["Int32():2", "Int32():1", "Int32():2"]},
        {"sku": "String():b", "marks": []},
    ]


# --------------------------------------------------------------------------- #
# Reading stored collections                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "document",
    [{}, {"tags": None}, {"tags": []}, "not-an-object"],
    ids=["missing-key", "json-null", "empty-array", "non-object-carrier"],
)
def test_every_empty_alias_reads_as_the_empty_collection(document: object) -> None:
    classify = prepared_raw_member_classifier(_SHAPE, "tags")

    assert classify(locate_raw_entity_member(cast("DocumentValue", document), "tags")) == (
        (),
        (),
    )


def test_a_direct_column_reads_sql_null_and_json_null_as_empty() -> None:
    assert decode_scalar_many_classified(_TAGS, SQL_NULL) == ((), ())
    assert decode_scalar_many_classified(_TAGS, PresentDocument(None)) == ((), ())


def test_a_canonical_array_reads_as_its_ordered_managed_tuple() -> None:
    value, findings = decode_scalar_many_classified(
        _AMOUNTS, PresentDocument(["1.50", "1.50", "7.00"])
    )

    assert findings == ()
    assert value == (decimal.Decimal("1.50"), decimal.Decimal("1.50"), decimal.Decimal("7.00"))


def test_a_non_array_carrier_leaves_the_whole_collection_unavailable() -> None:
    classify = prepared_raw_member_classifier(_SHAPE, "tags")

    assert classify(locate_raw_entity_member(cast("DocumentValue", {"tags": "a,b"}), "tags")) == (
        UNAVAILABLE,
        (DocumentFinding("leaf-undecodable", ("tags",), "a,b"),),
    )
    assert decode_scalar_many_classified(_TAGS, PresentDocument({"a": 1})) == (
        UNAVAILABLE,
        (DocumentFinding("leaf-undecodable", (), {"a": 1}),),
    )


def test_every_invalid_element_is_found_in_order_and_nothing_is_shortened() -> None:
    value, findings = decode_scalar_many_classified(
        _AMOUNTS, PresentDocument(["1.50", "1.5", None, "7.00", 3])
    )

    assert value is UNAVAILABLE
    assert findings == (
        DocumentFinding("leaf-undecodable", (1,), "1.5"),
        DocumentFinding("leaf-undecodable", (2,), None),
        DocumentFinding("leaf-undecodable", (4,), 3),
    )


def test_nested_collections_keep_every_enclosing_name_and_index() -> None:
    decoded = decode_occurrence_classified(
        _LINE,
        PresentDocument(
            [{"sku": "a", "marks": [1]}, {"sku": "b", "marks": [2, "x"]}, {"sku": "c"}]
        ),
        multiplicity=_MANY,
        nullable=False,
    )

    assert decoded.findings == (DocumentFinding("leaf-undecodable", (1, "marks", 1), "x"),)
    assert isinstance(decoded.presence, Present)
    elements = cast("list[dict[str, object]]", decoded.presence.value)
    assert elements[0]["marks"] == (1,)
    assert elements[1]["marks"] is UNAVAILABLE
    assert elements[2]["marks"] == ()


def test_an_absent_enclosing_occurrence_invents_no_collection() -> None:
    decoded = decode_occurrence_classified(
        _DETAIL, PresentDocument(None), multiplicity=Multiplicity.ONE, nullable=True
    )

    assert decoded.presence is NULL
    assert decoded.findings == ()


def test_reduction_decodes_a_collection_element_wise_and_refuses_a_non_array() -> None:
    assert reduce_declared_members(_DETAIL, {"labels": ["x", "x"]}) == {"labels": ["x", "x"]}
    assert reduce_declared_members(_DETAIL, {}, preserve_presence=True) == {"labels": []}
    with pytest.raises(LeafEncodingError, match="labels"):
        reduce_declared_members(_DETAIL, {"labels": "x"})


# --------------------------------------------------------------------------- #
# Effective change                                                             #
# --------------------------------------------------------------------------- #


def test_collections_compare_ordered_element_wise_with_null_as_empty() -> None:
    changes = classify_effective_change(
        _SHAPE,
        {"tags": ("a", "b"), "amounts": ()},
        {"tags": ["b", "a"]},
    )

    assert changes.effective == frozenset({"tags"})
    assert changes.restored == frozenset({"amounts"})


def test_the_prepared_rule_reads_a_null_cell_as_the_empty_collection() -> None:
    absent = object()
    prepared = prepare_effective_change(_SHAPE, {"tags": ()}, absent=absent)
    row = (None, None, (), None, ())

    assert not prepared.any_effective(row)
    assert prepared.any_effective((None, ("a",), (), None, ()))
    assert not prepared.any_effective_in({})
