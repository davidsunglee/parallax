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
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Decimal,
    NeutralType,
    decode_neutral_literal,
)
from parallax.core.document_codec import (
    MISSING,
    NULL,
    DocumentShape,
    Leaf,
    LeafEncodingError,
    Occurrence,
    Present,
    SetLeaf,
    SetOccurrence,
    apply_patches,
    comparison_text,
    decode_path,
    encode_candidate,
    encode_document,
    encode_leaf,
    encode_many,
    is_text_compared,
    occurrence_shape,
    shape_of_declaration,
)
from parallax.core.entity import Attr, DomainModel, Entity, ValueObject, attr
from parallax.core.metamodel import (
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    ValueObjectAttributeDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)

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
    # The inverse leg is m-core's own portable-literal decode, not a second table
    # here: stating it twice is exactly the drift the module exists to prevent.
    assert decode_neutral_literal(document, neutral_type) == value


def test_a_value_outside_its_declared_space_has_no_spelling() -> None:
    # Refused rather than encoded: the table is total over the type algebra but says
    # nothing about a value outside a declared value space, and inventing a spelling
    # for one is what leaves two writers disagreeing.
    with pytest.raises(LeafEncodingError):
        encode_leaf(DATE, "2026-01-15")
    with pytest.raises(LeafEncodingError):
        encode_leaf(Decimal(4, 2), decimal.Decimal("1.005"))


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
        assert encode_document(_SHAPE, {"entries": zero})["entries"] == []
    assert encode_many(shape_of_declaration(_ENTRY), []) == []


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


def test_decode_answers_by_declared_type_and_never_by_inspecting_the_value() -> None:
    document = {"flag": True, "day": "2026-01-15", "entries": [{"price": "19.99"}]}
    assert decode_path(_SHAPE, document, ("day",)) == Present(dt.date(2026, 1, 15))
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
    # A non-object intermediate blocks descent exactly as an absent key does.
    assert decode_path(_SHAPE, {"origin": "unknown"}, ("origin", "city")) is MISSING
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
    with pytest.raises(ValueError, match="invalid stored data"):
        decode_path(_SHAPE, {"day": "not-a-date"}, ("day",))


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


def test_a_subtree_replacement_drops_unknown_keys_inside_it_and_nowhere_else() -> None:
    stored = {"unknown": 1, "origin": {"city": "Oslo", "unknown": 2}}
    replaced = apply_patches(
        _SHAPE,
        stored,
        [SetOccurrence(("origin",), encode_document(shape_of_declaration(_ORIGIN), {}))],
    )
    assert replaced == {"unknown": 1, "origin": {}}


def test_patches_apply_left_to_right_each_over_the_result_of_the_last() -> None:
    patched = apply_patches(
        _SHAPE,
        {},
        [SetLeaf(("flag",), Present(True)), SetLeaf(("flag",), Present(False))],
    )
    assert patched == {"flag": False}
    with pytest.raises(ValueError, match="nonempty"):
        apply_patches(_SHAPE, {}, [])
    with pytest.raises(ValueError, match="SetOccurrence"):
        apply_patches(_SHAPE, {}, [SetLeaf(("origin",), Present("Oslo"))])


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
    assert occurrence_shape(occurrence) == DocumentShape(
        members=(
            Leaf(name="flag", type=BOOLEAN, nullable=True),
            Occurrence(
                name="origin",
                multiplicity=Multiplicity.ONE,
                nullable=True,
                shape=DocumentShape(members=(Leaf(name="city", type=STRING, nullable=True),)),
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
