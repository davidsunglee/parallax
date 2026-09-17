"""The portable document encoding, decoding, patching, and candidate contract.

The corpus witnesses the codec's decisions where a database can observe them —
the comparison split, the leaf spellings a predicate binds, the containment
candidate. What stays here is what no case can reach: the encode/decode inverse
over every value space, the float shortest-round-trip rule with its even-digit
tie-break, the presence table's four states, patching's unknown-key preservation,
and the refusals that keep a consumer from spelling a leaf of its own.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Iterable
from typing import cast

import pytest

from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    JSON,
    SQL_NULL,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Decimal,
    DocumentValue,
    NeutralType,
    PresentDocument,
)
from parallax.core.document_codec import (
    MISSING,
    NULL,
    UNAVAILABLE,
    DecodedMember,
    Leaf,
    LeafEncodingError,
    MemberShape,
    Occurrence,
    Present,
    SetLeaf,
    SetValue,
    apply_patches,
    comparison_text,
    decode_located_member_classified,
    decode_occurrence_classified,
    decode_path,
    decode_path_classified,
    encode_candidate,
    encode_document,
    encode_leaf,
    encode_many,
    entity_shape,
    is_text_compared,
    locate_raw_entity_member,
    occurrence_shape,
    prepared_raw_member_classifier,
    reduce_declared_members,
    reduce_declared_members_classified,
    shape_of_declaration,
)
from parallax.core.document_codec._document import encode_managed_document
from parallax.core.entity import Attr, DomainModel, Entity, ValueObject, attr
from parallax.core.metamodel import (
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    ValueObjectAttributeDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_wire, loads

_INSTANT = dt.datetime(2026, 1, 15, 9, 30, tzinfo=dt.UTC)
_TOKEN = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")

# One value per row of the encoding table, paired with the document spelling the
# table admits — the whole table in one place, so a row that loses its spelling
# fails here rather than in whichever consumer happens to store it first.
_TABLE: list[tuple[NeutralType, object, object]] = [
    (BOOLEAN, True, True),
    (INT32, -7, -7),
    (INT64, 2**40, 2**40),
    (FLOAT32, 1.5, 1.5),
    (FLOAT64, 2.25, 2.25),
    (STRING, "alpha", "alpha"),
    (Decimal(12, 2), decimal.Decimal("1.5"), "1.50"),
    (BYTES, b"\x0a\x1b", "0a1b"),
    (DATE, dt.date(2026, 1, 15), "2026-01-15"),
    (TIME, dt.time(9, 30), "09:30:00"),
    (TIMESTAMP, _INSTANT, "2026-01-15T09:30:00.000000Z"),
    (UUID, _TOKEN, "123e4567-e89b-12d3-a456-426614174000"),
    (JSON, {"free": [1, None]}, {"free": [1, None]}),
]


@pytest.mark.parametrize(
    ("neutral_type", "value", "document"), _TABLE, ids=[str(row[0]) for row in _TABLE]
)
def test_every_neutral_type_has_exactly_one_document_spelling(
    neutral_type: NeutralType, value: object, document: object
) -> None:
    assert encode_leaf(neutral_type, value) == document


@pytest.mark.parametrize(
    ("neutral_type", "value", "document"), _TABLE, ids=[str(row[0]) for row in _TABLE]
)
def test_decoding_an_encoding_yields_an_equal_value(
    neutral_type: NeutralType, value: object, document: object
) -> None:
    assert decode_path(_one_leaf(neutral_type), {"leaf": document}, ("leaf",)) == Present(value)


def test_a_value_outside_its_declared_space_has_no_spelling() -> None:
    # Refused rather than encoded: the table is total over the type algebra but says
    # nothing about a value outside a declared value space, and inventing a spelling
    # for one is what leaves two writers disagreeing.
    #
    # The `timestamp` row is the one where a carrier of the right Python type is
    # still outside the space: an aware `datetime` at the representational edge
    # names an instant this table's four-digit-year UTC spelling cannot write, so
    # it is refused HERE rather than overflowing inside the conversion.
    with pytest.raises(LeafEncodingError):
        encode_leaf(DATE, "2026-01-15")
    with pytest.raises(LeafEncodingError):
        encode_leaf(Decimal(4, 2), decimal.Decimal("1.005"))
    with pytest.raises(LeafEncodingError):
        encode_leaf(TIMESTAMP, dt.datetime.min.replace(tzinfo=dt.timezone(dt.timedelta(hours=14))))


def test_an_exact_decimal_pads_to_its_declared_scale_and_signs_only_below_zero() -> None:
    assert encode_leaf(Decimal(12, 2), decimal.Decimal("-0.5")) == "-0.50"
    assert encode_leaf(Decimal(12, 2), decimal.Decimal("-0.00")) == "0.00"
    assert encode_leaf(Decimal(12, 0), decimal.Decimal("7")) == "7"
    assert encode_leaf(Decimal(12, 2), decimal.Decimal("0.05")) == "0.05"
    # Exactness beyond any rounding context's default precision: 38 significant
    # digits, rescaled by construction rather than by `quantize`.
    wide = decimal.Decimal("0.12345678901234567890123456789012345678")
    assert encode_leaf(Decimal(38, 38), wide) == "0.12345678901234567890123456789012345678"


def test_a_float_encodes_as_the_shortest_number_that_decodes_back_to_it() -> None:
    assert encode_leaf(FLOAT64, 0.1) == 0.1
    assert encode_leaf(FLOAT64, 20.0) == 20.0
    assert encode_leaf(FLOAT64, 1e300) == 1e300


def test_equally_short_and_equally_near_floats_break_the_tie_to_an_even_last_digit() -> None:
    # Both witnesses the contract states. Binary64 562949953421312.25 is decoded from
    # 562949953421312.2 AND .3 — sixteen significant digits each, 0.05 from the value
    # each — so "fewest digits, then nearest" alone still admits two numbers, and two
    # numbers are two documents.
    assert encode_leaf(FLOAT64, 562949953421312.25) == 562949953421312.2
    assert encode_leaf(FLOAT32, 1048576.25) == 1048576.2


def test_a_float_encoding_decodes_back_at_the_width_that_chose_it() -> None:
    # The shortest number is the shortest one that decodes back to the value AT THE
    # DECLARED WIDTH, so the width has to be on both legs: 1048576.2 is a `float32`
    # encoding of 1048576.25 and a binary64 number in its own right, and reading it
    # back at binary64 would answer a value no `float32` holds.
    assert decode_wire(FLOAT32, cast("WireValue", encode_leaf(FLOAT32, 1048576.25))) == 1048576.25
    assert decode_wire(FLOAT64, 1048576.2) == 1048576.2
    for binary32_value in (1048576.25, 1.5, -2.5, 0.0, 3.4028234663852886e38):
        assert (
            decode_wire(FLOAT32, cast("WireValue", encode_leaf(FLOAT32, binary32_value)))
            == binary32_value
        )
    # A magnitude that rounds past binary32's finite range is refused by Wire
    # decoding instead of producing an infinite carrier.
    with pytest.raises(WireDecodingError):
        decode_wire(FLOAT32, 3.5e38)


def test_a_canonical_float32_number_need_not_be_exactly_a_binary32_value() -> None:
    # Why literal membership cannot be an exactness test (`m-document-codec`, "What
    # nearest-value decoding gives up"): the shortest number that decodes back to a
    # binary32 value is routinely not that value, so a rule refusing every inexact
    # number would refuse spellings this table itself produces.
    binary32_value = decode_wire(FLOAT32, 1e30)
    assert binary32_value == 1.0000000150474662e30
    assert encode_leaf(FLOAT32, binary32_value) == 1e30


def test_decode_reads_a_float32_leaf_at_its_declared_width() -> None:
    shape = MemberShape(members=(Leaf(name="ratio", type=FLOAT32, nullable=True),))
    stored = encode_document(shape, {"ratio": Present(1048576.25)})
    assert stored == {"ratio": 1048576.2}
    assert decode_path(shape, stored, ("ratio",)) == Present(1048576.25)


def test_a_stored_float_that_is_not_the_shortest_number_is_invalid_stored_data() -> None:
    # The refusal a float's canonicality needs the AUTHORED DIGITS to make: two
    # JSON numbers name one binary float, so a parse that discards the digits
    # leaves `0.1` and `0.10000000000000001` indistinguishable and the second
    # readable as the first. Strict Wire loading preserves the authored number
    # until the document codec resolves the declared leaf type.
    shape = MemberShape(members=(Leaf(name="ratio", type=FLOAT64, nullable=True),))
    assert decode_path(shape, {"ratio": loads("0.1")}, ("ratio",)) == Present(0.1)
    # The number, not its rendering: `20` and `20.0` are one JSON number.
    assert decode_path(shape, {"ratio": loads("20.0")}, ("ratio",)) == Present(20.0)
    with pytest.raises(ValueError, match="invalid stored data"):
        decode_path(shape, {"ratio": loads("0.10000000000000001")}, ("ratio",))
    # At `float32` the canonical number is the shortest one that decodes back AT
    # THAT WIDTH, so the exact binary32 value is itself a second spelling of it.
    narrow = MemberShape(members=(Leaf(name="ratio", type=FLOAT32, nullable=True),))
    assert decode_path(narrow, {"ratio": loads("1048576.2")}, ("ratio",)) == Present(1048576.25)
    with pytest.raises(ValueError, match="invalid stored data"):
        decode_path(narrow, {"ratio": loads("1048576.25")}, ("ratio",))


def test_a_float_carrier_with_no_authored_digits_is_the_number_it_names() -> None:
    # A runtime caller's own `float` is a carrier it chose rather than a spelling
    # some writer produced, so there is no second spelling to distinguish it
    # from: it reads back as the value it names.
    shape = MemberShape(members=(Leaf(name="ratio", type=FLOAT64, nullable=True),))
    assert decode_path(shape, {"ratio": 0.1}, ("ratio",)) == Present(0.1)


def test_an_integer_stored_leaf_spells_the_same_number_a_float_carrier_would() -> None:
    # A JSON number is a number, so the carrier a parser answered with settles
    # nothing: `1e30` is the canonical `float64` spelling, and the integer naming
    # that same number IS that spelling — though the binary float carrying either
    # holds 1000000000000000019884624838656 and equals neither rendering, which is
    # what host equality would compare and refuse the integer by.
    shape = MemberShape(members=(Leaf(name="ratio", type=FLOAT64, nullable=True),))
    assert decode_path(shape, {"ratio": 10**30}, ("ratio",)) == Present(1e30)
    # A number the width holds and the table does not spell stays refused: this one
    # rounds to the same binary64 and is still a second number.
    with pytest.raises(ValueError, match="invalid stored data"):
        decode_path(shape, {"ratio": 10**30 + 2**40}, ("ratio",))
    # At `float32` the canonical number is routinely not the value itself, so an
    # integer spelling one reads back as the binary32 value it names.
    narrow = MemberShape(members=(Leaf(name="ratio", type=FLOAT32, nullable=True),))
    assert decode_path(narrow, {"ratio": 10**30}, ("ratio",)) == Present(1.0000000150474662e30)


def _one_leaf(neutral_type: NeutralType) -> MemberShape:
    return MemberShape(members=(Leaf(name="leaf", type=neutral_type, nullable=True),))


def test_classified_member_variants_report_each_detection_without_inventing_values() -> None:
    nested = MemberShape(members=(Leaf("required", INT32, False),))
    shape = MemberShape(
        members=(
            Leaf("leaf", INT32, False),
            Occurrence("one", Multiplicity.ONE, False, nested),
            Occurrence("many", Multiplicity.MANY, False, nested),
        )
    )
    assert decode_located_member_classified(shape, SQL_NULL, "leaf").findings[0].code == (
        "required-member-absent"
    )
    assert (
        decode_located_member_classified(shape, PresentDocument(None), "leaf").findings[0].code
        == "required-member-null"
    )
    assert decode_path_classified(shape, {"one": []}, ("one",)).findings[0].code == (
        "one-wrong-kind"
    )
    assert decode_path_classified(shape, {"many": {}}, ("many",)).findings[0].code == (
        "many-wrong-kind"
    )
    undecodable = decode_path_classified(shape, {"leaf": "wrong"}, ("leaf",))
    assert undecodable.presence is UNAVAILABLE
    assert undecodable.findings[0].code == "leaf-undecodable"

    with pytest.raises(KeyError, match="names no member"):
        decode_located_member_classified(shape, SQL_NULL, "unknown")


def test_raw_member_location_preserves_missing_null_and_present_states() -> None:
    classify = prepared_raw_member_classifier(
        MemberShape(members=(Leaf("leaf", INT32, False),)), "leaf"
    )

    assert locate_raw_entity_member([], "leaf") is MISSING
    assert locate_raw_entity_member({}, "leaf") is MISSING
    assert classify(locate_raw_entity_member({"leaf": None}, "leaf"))[1][0].code == (
        "required-member-null"
    )
    assert classify(locate_raw_entity_member({"leaf": 7}, "leaf")) == (7, ())


def test_classified_paths_cover_non_object_and_nested_occurrence_states() -> None:
    nested = MemberShape(members=(Leaf("required", INT32, False),))
    shape = MemberShape(
        members=(
            Occurrence("one", Multiplicity.ONE, True, nested),
            Occurrence("many", Multiplicity.MANY, False, nested),
        )
    )

    non_object = decode_path_classified(shape, [], ("one",))
    assert non_object.presence is MISSING
    assert decode_path_classified(shape, {"one": None}, ("one", "required")).presence is NULL
    nested_value = decode_path_classified(shape, {"one": {"required": 7}}, ("one", "required"))
    assert nested_value == DecodedMember(Present(7))
    raw_element: dict[str, DocumentValue] = {"required": 7}
    tuple_document = cast("DocumentValue", {"many": (raw_element,)})
    isolated = decode_path_classified(shape, tuple_document, ("many",))
    raw_element["required"] = 8
    isolated_many = cast("tuple[dict[str, object], ...]", cast("Present", isolated.presence).value)
    assert isolated_many[0]["required"] == 7
    with pytest.raises(KeyError, match="array position"):
        decode_path_classified(shape, {"many": []}, ("many", "required"))

    reduced, findings = reduce_declared_members_classified(shape, "not-an-object")
    assert reduced is None
    assert findings[0].code == "one-wrong-kind"


def test_classified_reduction_preserves_member_names_and_integer_array_positions() -> None:
    shape = MemberShape(
        members=(
            Leaf("0", INT32, True),
            Occurrence(
                "many",
                Multiplicity.MANY,
                False,
                MemberShape(members=(Leaf("12", INT32, False),)),
            ),
        )
    )
    reduced, findings = reduce_declared_members_classified(
        shape, {"0": "wrong", "many": [{"12": "wrong"}]}
    )
    assert cast("dict[str, object]", reduced)["0"] is UNAVAILABLE
    assert [finding.path for finding in findings] == [("0",), ("many", 0, "12")]


def test_classified_decoding_constructs_positional_output_during_the_shared_walk() -> None:
    unavailable = object()
    element = MemberShape(members=(Leaf("required", INT32, False),))
    shape = MemberShape(
        members=(
            Leaf("omitted", INT32, True),
            Leaf("bad", INT32, True),
            Occurrence("one", Multiplicity.ONE, False, element),
            Occurrence("many", Multiplicity.MANY, False, element),
        )
    )
    stored: DocumentValue = {
        "bad": "wrong",
        "one": {},
        "many": [{"required": 7}, {}],
    }

    def positional_object(
        member_shape: MemberShape, values: Iterable[object]
    ) -> tuple[object, ...]:
        return tuple(
            unavailable if value is MISSING or value is UNAVAILABLE else value
            for _member, value in zip(member_shape.members, values, strict=True)
        )

    decoded = decode_occurrence_classified(
        shape,
        PresentDocument(stored),
        multiplicity=Multiplicity.ONE,
        nullable=False,
        build_object=positional_object,
        build_many=lambda values: tuple(values),
    )

    assert decoded.presence == Present(
        (unavailable, unavailable, (unavailable,), ((7,), (unavailable,)))
    )
    expected_paths = [
        ("bad",),
        ("one", "required"),
        ("many", 1, "required"),
    ]
    assert [finding.path for finding in decoded.findings] == expected_paths

    reduced, mapping_findings = reduce_declared_members_classified(shape, stored)
    assert reduced == {
        "bad": UNAVAILABLE,
        "one": {},
        "many": [{"required": 7}, {}],
    }
    assert [finding.path for finding in mapping_findings] == expected_paths


def test_top_level_occurrence_classification_uses_the_sql_null_aware_carrier() -> None:
    shape = MemberShape(members=(Leaf("required", INT32, False),))
    absent = decode_occurrence_classified(
        shape, SQL_NULL, multiplicity=Multiplicity.ONE, nullable=False
    )
    wrong_many = decode_occurrence_classified(
        shape,
        PresentDocument([{"required": 1}, "wrong"]),
        multiplicity=Multiplicity.MANY,
        nullable=False,
    )
    assert absent.findings[0].code == "required-member-absent"
    assert wrong_many.findings[0].code == "many-wrong-kind"
    assert cast("Present", wrong_many.presence).value == []


@pytest.mark.parametrize(
    ("neutral_type", "stored"),
    [
        (Decimal(12, 2), "1.5"),
        (Decimal(12, 2), 1.5),
        (Decimal(12, 2), "01.50"),
        (BYTES, "0A1B"),
        (DATE, "20260115"),
        (TIME, "09:30"),
        (TIMESTAMP, "2026-01-15T11:30:00+02:00"),
        (TIMESTAMP, "2026-01-15T09:30:00Z"),
        (TIMESTAMP, "0001-01-01T00:00:00.000000+14:00"),
        (UUID, "123E4567-E89B-12D3-A456-426614174000"),
        (UUID, "123e4567e89b12d3a456426614174000"),
        (FLOAT32, 1048576.3),
        (FLOAT32, 16777217),
    ],
    ids=lambda param: repr(param),
)
def test_a_stored_leaf_that_is_not_the_tables_own_spelling_is_refused(
    neutral_type: NeutralType, stored: object
) -> None:
    # Every type has exactly ONE document spelling, and it is what a predicate binds
    # and an ordering compares for the six text-compared types. Almost every row here
    # decodes cleanly into its declared value space and is still a DIFFERENT document
    # from the one a writer of the same value stores, so decoding it would answer with
    # a value whose own row no comparison against that member finds. The offset
    # `timestamp` at the range edge is the one row that is no spelling of any value:
    # its instant is outside what the table can write, and it earns the same
    # invalid-stored-data verdict rather than overflowing inside the decode.
    with pytest.raises(ValueError, match="invalid stored data"):
        decode_path(_one_leaf(neutral_type), {"leaf": stored}, ("leaf",))


def test_an_integral_float_number_answers_the_same_whichever_rendering_carries_it() -> None:
    # `20` and `20.0` are one JSON number, so validity cannot turn on which of them a
    # parser handed back as an `int` and which as a `float`. `2**24 + 1` names a value
    # binary32 does not hold in either rendering, so both are invalid stored data
    # rather than the silently rounded `16777216.0` a narrow-first reader answers.
    shape = _one_leaf(FLOAT32)
    for rendering in (2**24 + 1, float(2**24 + 1)):
        with pytest.raises(ValueError, match="invalid stored data"):
            decode_path(shape, {"leaf": rendering}, ("leaf",))
    assert decode_path(shape, {"leaf": 20}, ("leaf",)) == Present(20.0)
    assert decode_path(shape, {"leaf": 20.0}, ("leaf",)) == Present(20.0)


def test_only_the_six_text_compared_types_have_a_comparison_text() -> None:
    assert comparison_text(BYTES, b"\x0a\x1b") == "0a1b"
    assert comparison_text(UUID, _TOKEN) == "123e4567-e89b-12d3-a456-426614174000"
    assert comparison_text(TIMESTAMP, _INSTANT) == "2026-01-15T09:30:00.000000Z"
    for text_compared in (STRING, BYTES, DATE, TIME, TIMESTAMP, UUID):
        assert is_text_compared(text_compared)
    # `decimal(p, s)`'s document form is a JSON string too and it is deliberately
    # absent: the domain is fixed by how a type COMPARES, and a decimal casts.
    for cast_compared in (BOOLEAN, INT32, INT64, FLOAT32, FLOAT64, Decimal(12, 2)):
        assert not is_text_compared(cast_compared)
        with pytest.raises(ValueError, match="no comparison text"):
            comparison_text(cast_compared, 1)


# --------------------------------------------------------------------------- #
# Shapes, presence, and composition                                            #
# --------------------------------------------------------------------------- #

_ENTRY = ValueObjectShapeDeclaration(
    key=ValueObjectShapeKey(),
    attributes=(
        ValueObjectAttributeDeclaration(name="kind", type=STRING, nullable=True),
        ValueObjectAttributeDeclaration(name="price", type=Decimal(12, 2), nullable=True),
    ),
)
_ORIGIN = ValueObjectShapeDeclaration(
    key=ValueObjectShapeKey(),
    attributes=(ValueObjectAttributeDeclaration(name="city", type=STRING, nullable=True),),
)
_PROFILE = ValueObjectShapeDeclaration(
    key=ValueObjectShapeKey(),
    attributes=(
        ValueObjectAttributeDeclaration(name="flag", type=BOOLEAN, nullable=True),
        ValueObjectAttributeDeclaration(name="day", type=DATE, nullable=True),
    ),
    value_objects=(
        NestedValueObjectOccurrenceDeclaration(
            name="origin", shape=_ORIGIN, multiplicity=Multiplicity.ONE, nullable=True
        ),
        NestedValueObjectOccurrenceDeclaration(
            name="entries", shape=_ENTRY, multiplicity=Multiplicity.MANY
        ),
    ),
)
_SHAPE = shape_of_declaration(_PROFILE)

_NESTED_MANY_SHAPE = shape_of_declaration(
    ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        value_objects=(
            NestedValueObjectOccurrenceDeclaration(
                name="address",
                shape=ValueObjectShapeDeclaration(
                    key=ValueObjectShapeKey(),
                    attributes=(
                        ValueObjectAttributeDeclaration(name="city", type=STRING, nullable=True),
                    ),
                    value_objects=(
                        NestedValueObjectOccurrenceDeclaration(
                            name="phones", shape=_ENTRY, multiplicity=Multiplicity.MANY
                        ),
                    ),
                ),
                multiplicity=Multiplicity.ONE,
                nullable=True,
            ),
        ),
    )
)
"""A `many` under a nested `one`, which is where a reduction's own recursion
decides whether a member's presence rule holds at depth."""


def test_a_declared_shape_names_leaves_then_occurrences_in_declaration_order() -> None:
    assert [member.name for member in _SHAPE.members] == ["flag", "day", "origin", "entries"]
    assert _SHAPE.member("flag") == Leaf(name="flag", type=BOOLEAN, nullable=True)
    assert _SHAPE.member("absent") is None
    entries = _SHAPE.member("entries")
    assert isinstance(entries, Occurrence)
    assert entries.multiplicity is Multiplicity.MANY


def test_encode_emits_the_presence_table() -> None:
    document = encode_document(
        _SHAPE,
        {"flag": NULL, "day": Present(dt.date(2026, 1, 15))},
    )
    # A required member's encoding, an explicit null, an omitted key that is simply
    # absent, and a `many` given nothing at all — which still stores `[]`, its sole
    # zero-element representation.
    assert document == {"flag": None, "day": "2026-01-15", "entries": []}


def test_a_many_member_stores_the_empty_array_for_every_zero_state() -> None:
    for zero in (MISSING, NULL, Present([])):
        assert encode_document(_SHAPE, {"entries": zero})["entries"] == ()
    assert encode_many(shape_of_declaration(_ENTRY), []) == ()


def test_nesting_composes_from_the_leaves_up_through_these_two_operations() -> None:
    entry_shape = shape_of_declaration(_ENTRY)
    document = encode_document(
        _SHAPE,
        {
            "origin": Present(
                encode_document(shape_of_declaration(_ORIGIN), {"city": Present("Oslo")})
            ),
            "entries": Present(
                encode_many(
                    entry_shape,
                    [
                        {"kind": Present("home"), "price": Present(decimal.Decimal("19.99"))},
                        {"kind": Present("work")},
                    ],
                )
            ),
        },
    )
    assert document == {
        "origin": {"city": "Oslo"},
        "entries": [{"kind": "home", "price": "19.99"}, {"kind": "work"}],
    }


def test_managed_encoding_builds_the_same_immutable_document_without_presence_maps() -> None:
    managed = {
        "origin": {"city": "Oslo"},
        "entries": ({"kind": "home", "price": decimal.Decimal("19.99")},),
    }
    encoded = encode_managed_document(_SHAPE, managed)

    assert encoded == {
        "origin": {"city": "Oslo"},
        "entries": [{"kind": "home", "price": "19.99"}],
    }
    with pytest.raises(TypeError):
        cast("dict[str, object]", encoded["origin"])["city"] = "Bergen"

    zero_many = encode_managed_document(_SHAPE, {"origin": None})
    assert zero_many == {"origin": None, "entries": ()}


def test_decode_answers_by_declared_type_and_never_by_inspecting_the_value() -> None:
    document = {
        "flag": True,
        "day": "2026-01-15",
        "origin": {"city": "Oslo"},
        "entries": [{"price": "19.99"}],
    }
    assert decode_path(_SHAPE, document, ("day",)) == Present(dt.date(2026, 1, 15))
    # The declared type comes from the member the path reaches, at any depth.
    assert decode_path(_SHAPE, document, ("origin", "city")) == Present("Oslo")
    # The occurrence arm answers with the stored subtree as it is, so an element is
    # decoded by handing it back with that occurrence's own shape — which is what
    # makes a `many` traversable without an element index.
    entries = decode_path(_SHAPE, document, ("entries",))
    assert isinstance(entries, Present)
    elements = cast("list[object]", entries.value)
    assert decode_path(shape_of_declaration(_ENTRY), elements[0], ("price",)) == Present(
        decimal.Decimal("19.99")
    )


def test_decode_distinguishes_absent_from_explicitly_null_and_collapses_a_many() -> None:
    assert decode_path(_SHAPE, {}, ("day",)) is MISSING
    assert decode_path(_SHAPE, {"day": None}, ("day",)) is NULL
    # An absent nullable occurrence carries its whole subtree with it, so a path
    # below one is not present rather than invalid — including a REQUIRED leaf
    # there, whose requiredness says nothing about a subtree the row never wrote.
    assert decode_path(_SHAPE, {}, ("origin", "city")) is MISSING
    assert decode_path(_SHAPE, {"origin": None}, ("origin", "city")) is MISSING
    zero_states: list[dict[str, object]] = [{}, {"entries": None}, {"entries": []}]
    for zero in zero_states:
        assert decode_path(_SHAPE, zero, ("entries",)) == Present([])


def test_a_path_naming_no_member_is_a_caller_error_rather_than_an_absence() -> None:
    with pytest.raises(KeyError):
        decode_path(_SHAPE, {}, ("absent",))
    with pytest.raises(KeyError):
        decode_path(_SHAPE, {}, ())
    with pytest.raises(KeyError, match="continues past"):
        decode_path(_SHAPE, {}, ("day", "deeper"))


def test_stored_data_that_contradicts_its_shape_fails_the_decode() -> None:
    # Every arm of "invalid stored data": a value that does not decode into its
    # declared type, a nested structure that is not the declared kind, and a
    # required path that is absent or JSON null. None of them may answer with a
    # presence, because inventing one turns corrupt storage into a plausible row.
    required = MemberShape(
        members=(
            Leaf(name="label", type=STRING, nullable=False),
            Occurrence(
                name="entries",
                multiplicity=Multiplicity.MANY,
                nullable=False,
                shape=shape_of_declaration(_ENTRY),
            ),
        )
    )
    for document, path in (
        ({"day": "not-a-date"}, ("day",)),
        ({"origin": "unknown"}, ("origin",)),
        ({"origin": "unknown"}, ("origin", "city")),
        ({"entries": 7}, ("entries",)),
    ):
        with pytest.raises(ValueError, match="invalid stored data"):
            decode_path(_SHAPE, document, path)
    for document, path in (({}, ("label",)), ({"label": None}, ("label",))):
        with pytest.raises(ValueError, match="invalid stored data"):
            decode_path(required, document, path)
    # A document that is not an object at all carries no member, and answering
    # "absent" for one would report a corrupt cell as an ordinary empty row.
    with pytest.raises(ValueError, match="invalid stored data"):
        decode_path(_SHAPE, "not-a-document", ("day",))


def test_a_required_intermediate_occurrence_is_a_missing_required_path() -> None:
    # The tolerance above belongs to a NULLABLE ancestor: its absence is a state the
    # shape names, so the subtree under it is legitimately not there. A required
    # occurrence has no such state, so its absence or JSON null IS the missing
    # required path, reported at the ancestor's own depth rather than as the leaf
    # below it being absent.
    shape = MemberShape(
        members=(
            Occurrence(
                name="origin",
                multiplicity=Multiplicity.ONE,
                nullable=False,
                shape=shape_of_declaration(_ORIGIN),
            ),
        )
    )
    for document in ({}, {"origin": None}):
        with pytest.raises(ValueError, match="'origin' is required"):
            decode_path(shape, document, ("origin", "city"))


def test_a_path_never_addresses_an_array_position() -> None:
    # A `many`'s elements are decoded one at a time against the occurrence's own
    # shape, so descending THROUGH one names no member — a caller error, never a
    # verdict about what the row stores.
    with pytest.raises(KeyError, match="array position"):
        decode_path(_SHAPE, {"entries": [{"kind": "home"}]}, ("entries", "kind"))


def test_an_unknown_key_never_becomes_a_member_value() -> None:
    document = {"unknown": 1, "origin": {"city": "Oslo", "unknown": 2}}
    with pytest.raises(KeyError):
        decode_path(_SHAPE, document, ("unknown",))
    # An occurrence answers with the subtree AS STORED, unknown keys included: its two
    # consumers ask what the row holds rather than what the model declares.
    assert decode_path(_SHAPE, document, ("origin",)) == Present({"city": "Oslo", "unknown": 2})


# --------------------------------------------------------------------------- #
# Patching                                                                     #
# --------------------------------------------------------------------------- #


def test_patch_preserves_every_key_it_is_not_told_to_change() -> None:
    stored = {"flag": True, "unknown": "from a newer writer", "entries": [{"kind": "home"}]}
    patched = apply_patches(_SHAPE, stored, [SetLeaf(("day",), Present(dt.date(2026, 1, 15)))])
    assert patched == {
        "flag": True,
        "unknown": "from a newer writer",
        "entries": [{"kind": "home"}],
        "day": "2026-01-15",
    }
    assert stored == {"flag": True, "unknown": "from a newer writer", "entries": [{"kind": "home"}]}


def test_a_leaf_patch_spells_its_value_through_the_encoding_table() -> None:
    assert apply_patches(_SHAPE, {}, [SetLeaf(("origin", "city"), Present("Oslo"))]) == {
        "origin": {"city": "Oslo"}
    }
    assert apply_patches(_SHAPE, {"flag": True}, [SetLeaf(("flag",), NULL)]) == {"flag": None}
    assert apply_patches(_SHAPE, {"flag": True}, [SetLeaf(("flag",), MISSING)]) == {}


def test_an_occurrence_patch_replaces_the_whole_subtree_it_names() -> None:
    stored = {"unknown": 1, "origin": {"city": "Oslo", "unknown": 2}}
    replaced = apply_patches(
        _SHAPE,
        stored,
        [SetValue(("origin",), encode_document(shape_of_declaration(_ORIGIN), {}))],
    )
    assert replaced == {"unknown": 1, "origin": {}}


def test_both_cardinalities_replace_their_subtree_and_null_stores_json_null() -> None:
    stored = {
        "origin": {"city": "Oslo", "unknown": 2},
        "entries": [{"kind": "old", "unknown": 3}],
    }
    patched = apply_patches(
        _SHAPE,
        stored,
        [
            SetValue(("origin",), {"city": "Bergen"}),
            SetValue(("entries",), [{"kind": "new"}]),
        ],
    )
    assert patched == {
        "origin": {"city": "Bergen"},
        "entries": [{"kind": "new"}],
    }
    assert apply_patches(_SHAPE, stored, [SetValue(("origin",), None)]) == {
        "origin": None,
        "entries": [{"kind": "old", "unknown": 3}],
    }


def test_replacement_reaches_every_depth_of_the_subtree_it_names() -> None:
    wrapper = MemberShape(
        (
            Occurrence(
                name="profile",
                shape=_SHAPE,
                multiplicity=Multiplicity.ONE,
                nullable=False,
            ),
        )
    )
    patched = apply_patches(
        wrapper,
        {
            "profile": {
                "origin": {"city": "Oslo", "unknown": 1},
                "entries": [{"kind": "old", "unknown": 2}],
            }
        },
        [
            SetValue(
                ("profile",),
                {"origin": {"city": "Bergen"}, "entries": [{"kind": "new"}]},
            )
        ],
    )
    assert patched == {
        "profile": {
            "origin": {"city": "Bergen"},
            "entries": [{"kind": "new"}],
        }
    }


def test_declared_member_reduction_is_recursive_and_drops_undeclared_keys() -> None:
    stored = {
        "flag": True,
        "day": "2026-01-15",
        "origin": {"city": "Oslo", "unknown": 1},
        "entries": [{"kind": "home", "unknown": 2}],
        "unknown": 3,
    }
    reduced = cast("dict[str, object]", reduce_declared_members(_SHAPE, stored))
    assert "unknown" not in reduced
    assert reduced["origin"] == {"city": "Oslo"}
    assert reduced["entries"] == [{"kind": "home", "price": None}]
    with pytest.raises(LeafEncodingError, match=r"origin\.city"):
        reduce_declared_members(_SHAPE, {"origin": {"city": 7}})
    with pytest.raises(LeafEncodingError, match=r"entries\.kind"):
        reduce_declared_members(_SHAPE, {"entries": [{"kind": 7}]})


def test_declared_member_reduction_can_take_its_presence_from_the_source_document() -> None:
    # Presence preservation lets the document answer for itself, at every depth —
    # `entries`' element omits `price`, and the preserved reduction omits it too
    # rather than fabricating the null a re-serialization would then store. The
    # unpreserved reduction answers the declared composite instead — one entry per
    # declared position — which is what a consumer needing that shape asks for.
    stored: dict[str, object] = {
        "flag": None,
        "origin": {},
        "entries": [{"kind": "home"}],
        "unknown": 3,
    }
    assert reduce_declared_members(_SHAPE, stored, preserve_presence=True) == {
        "flag": None,
        "origin": {},
        "entries": [{"kind": "home"}],
    }
    assert reduce_declared_members(_SHAPE, stored) == {
        "flag": None,
        "day": None,
        "origin": {"city": None},
        "entries": [{"kind": "home", "price": None}],
    }


def test_presence_preservation_still_answers_an_omitted_many_with_its_empty_collection() -> None:
    # A `many` has no absent state to preserve: an omitted key, a JSON null, and
    # `[]` are three spellings of one zero value, and the document a write composes
    # from this reduction stores `[]` for all three. Dropping the key would make two
    # documents of one logical value compare unequal, so the preserved reduction
    # answers `[]` exactly as the unpreserved one does, at every depth.
    assert reduce_declared_members(_SHAPE, {"flag": True}, preserve_presence=True) == {
        "flag": True,
        "entries": [],
    }
    assert reduce_declared_members(_SHAPE, {"entries": None}, preserve_presence=True) == {
        "entries": []
    }
    assert reduce_declared_members(
        _NESTED_MANY_SHAPE, {"address": {"city": "Oslo"}}, preserve_presence=True
    ) == {"address": {"city": "Oslo", "phones": []}}


def test_declared_member_reduction_refuses_wrong_occurrence_kinds() -> None:
    # Invalid storage can never compare equal to a replacement value, so the
    # reduction refuses a wrong-kind occurrence instead of collapsing it —
    # under presence preservation too, where the member IS held by the document.
    with pytest.raises(LeafEncodingError, match="expected object"):
        reduce_declared_members(_SHAPE, {"origin": "Oslo"})
    with pytest.raises(LeafEncodingError, match="expected array"):
        reduce_declared_members(_SHAPE, {"entries": {"kind": "home"}})
    with pytest.raises(LeafEncodingError, match="expected object"):
        reduce_declared_members(_SHAPE, {"origin": "Oslo"}, preserve_presence=True)


def test_patches_apply_left_to_right_each_over_the_result_of_the_last() -> None:
    patched = apply_patches(
        _SHAPE,
        {},
        [SetLeaf(("flag",), Present(True)), SetLeaf(("flag",), Present(False))],
    )
    assert patched == {"flag": False}
    with pytest.raises(ValueError, match="nonempty"):
        apply_patches(_SHAPE, {}, [])


def test_nested_and_overlapping_patches_reuse_the_latest_changed_ancestor() -> None:
    patched = apply_patches(
        _SHAPE,
        {"origin": {"city": "Oslo", "unknown": 1}},
        [
            SetValue(("origin",), {"city": "Bergen", "replacement": True}),
            SetLeaf(("origin", "city"), Present("Tromso")),
        ],
    )
    assert patched == {"origin": {"city": "Tromso", "replacement": True}}

    replaced_last = apply_patches(
        _SHAPE,
        {"origin": {"city": "Oslo"}},
        [
            SetLeaf(("origin", "city"), Present("Tromso")),
            SetValue(("origin",), {"city": "Alta"}),
        ],
    )
    assert replaced_last == {"origin": {"city": "Alta"}}

    built_in_order = apply_patches(
        _SHAPE,
        {},
        [
            SetLeaf(("origin", "city"), Present("Oslo")),
            SetLeaf(("origin", "city"), Present("Bergen")),
        ],
    )
    assert built_in_order == {"origin": {"city": "Bergen"}}


def test_patch_reuses_safe_untouched_subtrees_and_owns_aliased_replacements() -> None:
    predecessor = encode_managed_document(
        _SHAPE, {"origin": {"city": "Oslo"}, "entries": ({"kind": "home"},)}
    )
    replacement = {"city": "Bergen"}
    changed = apply_patches(_SHAPE, predecessor, [SetValue(("origin",), replacement)])

    replacement["city"] = "Alta"

    assert changed["entries"] is predecessor["entries"]
    assert changed["origin"] == {"city": "Bergen"}
    assert predecessor["origin"] == {"city": "Oslo"}


def test_patch_treats_a_non_object_root_or_intermediate_as_an_empty_object() -> None:
    assert apply_patches(_SHAPE, 7, [SetLeaf(("flag",), Present(True))]) == {"flag": True}
    assert apply_patches(
        _SHAPE,
        {"origin": "not-an-object"},
        [SetLeaf(("origin", "city"), Present("Oslo"))],
    ) == {"origin": {"city": "Oslo"}}


def test_a_patch_whose_kind_contradicts_its_member_is_refused_both_ways() -> None:
    # The pairing is exclusive both ways. Applying either mismatch would build a
    # document the same shape reads back as invalid stored data — a leaf holding an
    # object, or an occurrence holding a scalar.
    with pytest.raises(ValueError, match="SetValue"):
        apply_patches(_SHAPE, {}, [SetLeaf(("origin",), Present("Oslo"))])
    with pytest.raises(ValueError, match="SetLeaf"):
        apply_patches(_SHAPE, {}, [SetValue(("day",), {})])


def test_a_returned_document_is_immutable_and_shares_no_mutable_input_state() -> None:
    stored: dict[str, object] = {"origin": {"city": "Oslo"}, "entries": [{"kind": "home"}]}
    patched = apply_patches(_SHAPE, stored, [SetLeaf(("flag",), NULL)])
    cast("dict[str, object]", stored["origin"])["city"] = "Bergen"
    cast("list[dict[str, object]]", stored["entries"])[0]["kind"] = "work"
    assert patched == {"origin": {"city": "Oslo"}, "entries": [{"kind": "home"}], "flag": None}
    with pytest.raises(TypeError):
        cast("dict[str, object]", patched)["flag"] = True
    with pytest.raises(TypeError):
        cast("dict[str, object]", patched["origin"])["city"] = "Tromso"

    origin = {"city": "Oslo"}
    encoded = encode_document(_SHAPE, {"origin": Present(origin)})
    with pytest.raises(TypeError):
        cast("dict[str, object]", encoded["origin"])["city"] = "Bergen"
    assert origin == {"city": "Oslo"}
    answered = decode_path(_SHAPE, {"origin": origin}, ("origin",))
    assert isinstance(answered, Present)
    cast("dict[str, object]", answered.value)["city"] = "Tromso"
    assert origin == {"city": "Oslo"}
    replaced = apply_patches(_SHAPE, {}, [SetValue(("origin",), origin)])
    origin["city"] = "Alta"
    assert replaced["origin"] == {"city": "Oslo"}
    assert origin == {"city": "Alta"}

    payload: list[object] = [{"value": 1}]
    encoded_payload = encode_document(_one_leaf(JSON), {"leaf": Present(payload)})
    cast("dict[str, object]", payload[0])["value"] = 2
    assert encoded_payload == {"leaf": ({"value": 1},)}


def test_immutable_codec_outputs_compose_through_decode_compare_and_patch() -> None:
    encoded = encode_managed_document(
        _SHAPE,
        {"origin": {"city": "Oslo"}, "entries": ({"kind": "home"},)},
    )

    assert decode_path(_SHAPE, encoded, ("origin",)) == Present({"city": "Oslo"})
    assert reduce_declared_members(_SHAPE, encoded, preserve_presence=True) == {
        "origin": {"city": "Oslo"},
        "entries": [{"kind": "home"}],
    }
    classified, findings = reduce_declared_members_classified(_SHAPE, encoded)
    assert classified == {
        "origin": {"city": "Oslo"},
        "entries": [{"kind": "home"}],
    }
    assert findings == ()
    assert apply_patches(_SHAPE, encoded, [SetLeaf(("flag",), Present(True))]) == {
        "flag": True,
        "origin": {"city": "Oslo"},
        "entries": [{"kind": "home"}],
    }


# --------------------------------------------------------------------------- #
# The containment candidate                                                    #
# --------------------------------------------------------------------------- #


def test_a_candidate_carries_each_constrained_leafs_document_encoding() -> None:
    # Neither comparison form is what containment binds, and both fail SILENTLY: a
    # boolean bound the way its cast comparison binds it is MariaDB's `1`, and a
    # decimal bound as its managed value is a JSON number.
    assert encode_candidate(
        _SHAPE,
        {("flag",): True, ("day",): dt.date(2026, 1, 15)},
    ) == {"flag": True, "day": "2026-01-15"}
    entry_shape = shape_of_declaration(_ENTRY)
    assert encode_candidate(entry_shape, {("price",): decimal.Decimal("19.99")}) == {
        "price": "19.99"
    }


def test_a_candidate_nests_exactly_as_the_stored_document_nests() -> None:
    assert encode_candidate(_SHAPE, {("origin", "city"): "Oslo"}) == {"origin": {"city": "Oslo"}}


def test_a_candidate_owns_a_mutable_composite_json_leaf() -> None:
    payload: list[object] = [{"value": 1}]
    candidate = encode_candidate(_one_leaf(JSON), {("leaf",): payload})

    cast("dict[str, object]", payload[0])["value"] = 2

    assert candidate == {"leaf": ({"value": 1},)}


def test_an_unnamed_path_is_unconstrained_rather_than_absent() -> None:
    # A candidate is a probe, never a document a row holds: a `many` member the
    # constraints do not name contributes NO key, where `encode` would write `[]`.
    assert encode_candidate(_SHAPE, {("flag",): True}) == {"flag": True}


def test_a_candidate_names_at_least_one_path_and_each_reaches_a_leaf() -> None:
    with pytest.raises(ValueError, match="at least one"):
        encode_candidate(_SHAPE, {})
    with pytest.raises(ValueError, match="does not reach a leaf"):
        encode_candidate(_SHAPE, {("origin",): "Oslo"})


# --------------------------------------------------------------------------- #
# The Metadata-side shape                                                      #
# --------------------------------------------------------------------------- #


class Origin(ValueObject):
    city: Attr[str | None]


class Profile(ValueObject):
    flag: Attr[bool | None]
    origin: Attr[Origin | None]


class Holder(Entity, table="holder", namespace="parallax.test"):
    id: Attr[int] = attr(primary_key=True)
    profile: Attr[Profile | None]


def test_a_compiled_occurrence_yields_the_same_shape_as_its_declaration() -> None:
    # The two builders read the same declared facts through different vocabularies —
    # plain names on a declaration, identities on accepted Metadata — so the one place
    # that difference is unwound has to answer identically for both.
    (entity,) = DomainModel(Holder).entities
    (occurrence,) = entity.declared_value_objects
    assert occurrence_shape(occurrence) is occurrence.document_shape
    assert occurrence_shape(occurrence) == MemberShape(
        members=(
            Leaf(name="flag", type=BOOLEAN, nullable=True),
            Occurrence(
                name="origin",
                multiplicity=Multiplicity.ONE,
                nullable=True,
                shape=MemberShape(members=(Leaf(name="city", type=STRING, nullable=True),)),
            ),
        )
    )
    assert occurrence_shape(occurrence) == shape_of_declaration(
        ValueObjectShapeDeclaration(
            key=ValueObjectShapeKey(),
            attributes=(ValueObjectAttributeDeclaration(name="flag", type=BOOLEAN, nullable=True),),
            value_objects=(
                NestedValueObjectOccurrenceDeclaration(
                    name="origin",
                    shape=ValueObjectShapeDeclaration(
                        key=ValueObjectShapeKey(),
                        attributes=(
                            ValueObjectAttributeDeclaration(
                                name="city", type=STRING, nullable=True
                            ),
                        ),
                    ),
                    nullable=True,
                ),
            ),
        )
    )


def test_an_entity_shape_holds_its_document_resident_members_leaves_first() -> None:
    # The Entity-document counterpart of `occurrence_shape`: one root object over
    # the members that live inside a Relational Document Layout's shared
    # Structured Column. Residency is the CALLER's answer, so this takes the
    # already-filtered members — which is what lets the codec own the Entity
    # document without reading a layout it may not depend on.
    (entity,) = DomainModel(Holder).entities
    shape = entity_shape(entity.declared_attributes, entity.declared_value_objects)
    assert shape.members == (
        Leaf(name="id", type=INT64, nullable=False),
        Occurrence(
            name="profile",
            multiplicity=Multiplicity.ONE,
            nullable=True,
            shape=occurrence_shape(entity.declared_value_objects[0]),
        ),
    )


def test_an_entity_shape_over_no_members_encodes_the_empty_document() -> None:
    # An Entity declaring the layout but no document-resident member still
    # carries a document: the Structured Column is NOT NULL and the empty object
    # is what a row with nothing inside it holds (m-storage-layout).
    assert encode_document(entity_shape((), ()), {}) == {}
