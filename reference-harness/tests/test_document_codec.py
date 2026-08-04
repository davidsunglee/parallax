"""The harness's own reading of the portable document encoding (m-document-codec).

The corpus grades the two implementations against each other wherever a database
can observe the answer. These pin what a case cannot reach on its own: that this
twin encodes each wire literal to the one spelling the table admits, that a
containment candidate carries encodings rather than either comparison form, and
that a value the table does not cover is refused rather than passed through.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from reference_harness.document_codec import (
    DocumentEncodingError,
    comparison_text,
    decode_leaf,
    decode_stored,
    encode_candidate,
    encode_document,
    encode_leaf,
    is_document,
    is_text_compared,
)

# One wire literal per row of the encoding table, paired with the document spelling
# it encodes to. Four rows carry a literal that is NOT already its own spelling, and
# they are the rows an implementation gets wrong silently.
_TABLE: list[tuple[str, Any, Any]] = [
    ("boolean", True, True),
    ("int32", -7, -7),
    ("int64", 2**40, 2**40),
    ("float32", 1.5, 1.5),
    ("float64", 2.25, 2.25),
    ("string", "alpha", "alpha"),
    ("decimal(12,2)", 10.25, "10.25"),
    ("decimal(12,2)", 5, "5.00"),
    ("bytes", "0A1B", "0a1b"),
    ("bytes", b"\x0a\x1b", "0a1b"),
    ("date", "2026-01-15", "2026-01-15"),
    ("time", "09:30", "09:30:00"),
    ("timestamp", "2026-01-15T11:30:00+02:00", "2026-01-15T09:30:00.000000Z"),
    ("uuid", "123E4567-E89B-12D3-A456-426614174000", "123e4567-e89b-12d3-a456-426614174000"),
]


@pytest.mark.parametrize(
    ("type_spelling", "literal", "document"),
    _TABLE,
    ids=[f"{row[0]}-{row[1]!r}" for row in _TABLE],
)
def test_every_neutral_type_has_exactly_one_document_spelling(
    type_spelling: str, literal: Any, document: Any
) -> None:
    assert encode_leaf(type_spelling, literal) == document


def test_a_decimal_pads_to_its_declared_scale_and_signs_only_below_zero() -> None:
    assert encode_leaf("decimal(12,2)", -0.5) == "-0.50"
    assert encode_leaf("decimal(12,0)", 7) == "7"
    assert encode_leaf("decimal(38,20)", "0.12345678901234567890") == "0.12345678901234567890"


def test_a_value_the_table_cannot_spell_is_refused_rather_than_passed_through() -> None:
    with pytest.raises(DocumentEncodingError):
        encode_leaf("decimal(12,2)", 1.005)
    with pytest.raises(DocumentEncodingError):
        encode_leaf("bytes", "zz")
    with pytest.raises(DocumentEncodingError):
        encode_leaf("date", "2026-01-15T09:30:00Z")
    with pytest.raises(DocumentEncodingError):
        encode_leaf("timestamp", "2026-01-15T09:30:00")
    with pytest.raises(DocumentEncodingError):
        encode_leaf("uuid", "not-a-uuid")
    with pytest.raises(DocumentEncodingError):
        encode_leaf("time", "half past nine")
    with pytest.raises(DocumentEncodingError):
        encode_leaf("geography", "POINT(0 0)")


def test_an_authored_number_naming_no_float_of_the_width_is_refused_rather_than_rounded() -> None:
    # Nothing between a case's authored value and the document it stores asks whether
    # that value is a member of the declared space, so rendering `2**24 + 1` as the
    # nearest binary32 would put `16777216` into a fixture row and a golden bind under
    # a member the case wrote `16777217` for.
    for spelling, authored in (
        ("float32", 2**24 + 1),
        ("float64", 2**53 + 1),
        ("float32", 1e39),
        ("float64", float("inf")),
        ("float32", "1.5"),
    ):
        with pytest.raises(DocumentEncodingError, match="names no"):
            encode_leaf(spelling, authored)
    # A fractional number is a rendering, so it names the float of the width nearest
    # it and encodes to THAT value's shortest number — which is how every `float32`
    # the corpus authors is read.
    assert encode_leaf("float32", 1048576.2) == 1048576.2
    assert encode_leaf("float32", 1048576.3) == 1048576.2
    # An integer a float of the width holds exactly names that float, at either width.
    assert encode_leaf("float32", 20) == 20.0
    assert encode_leaf("float64", 2**24 + 1) == float(2**24 + 1)


def test_only_the_six_text_compared_types_have_a_comparison_text() -> None:
    for text_compared in ("string", "bytes", "date", "time", "timestamp", "uuid"):
        assert is_text_compared(text_compared)
    assert comparison_text("uuid", "123E4567-E89B-12D3-A456-426614174000") == (
        "123e4567-e89b-12d3-a456-426614174000"
    )
    # `decimal(p, s)`'s document form is a JSON string too and is deliberately absent:
    # the domain is fixed by how a type COMPARES, and a decimal casts.
    for cast_compared in ("boolean", "int32", "float64", "decimal(12,2)"):
        assert not is_text_compared(cast_compared)
        with pytest.raises(DocumentEncodingError, match="no comparison text"):
            comparison_text(cast_compared, 1)


_ENTRIES: dict[str, Any] = {
    "name": "entries",
    "multiplicity": "many",
    "attributes": [
        {"name": "kind", "type": "string"},
        {"name": "active", "type": "boolean"},
        {"name": "price", "type": "decimal(12,2)"},
    ],
}
_PROFILE: dict[str, Any] = {
    "name": "profile",
    "attributes": [{"name": "flag", "type": "boolean"}, {"name": "day", "type": "date"}],
    "valueObjects": [
        {"name": "origin", "attributes": [{"name": "city", "type": "string"}]},
        _ENTRIES,
    ],
}


def test_encode_emits_the_presence_table() -> None:
    # A supplied leaf's encoding, an explicit null, an omitted key that is simply
    # absent, and a `many` given nothing at all — which still stores `[]`, its sole
    # zero-element representation.
    assert encode_document(_PROFILE, {"day": "2026-01-15", "flag": None}) == {
        "flag": None,
        "day": "2026-01-15",
        "entries": [],
    }


def test_nesting_and_arrays_compose_element_by_element() -> None:
    assert encode_document(
        _PROFILE,
        {
            "origin": {"city": "Oslo"},
            "entries": [{"kind": "home", "active": True, "price": 19.99}, {"kind": "work"}],
        },
    ) == {
        "origin": {"city": "Oslo"},
        "entries": [{"kind": "home", "active": True, "price": "19.99"}, {"kind": "work"}],
    }


def test_a_null_occurrence_and_a_non_array_many_are_their_own_zero_states() -> None:
    assert encode_document(_PROFILE, None) is None
    assert encode_document(_ENTRIES, None) == []


def test_an_unknown_key_survives_unencoded() -> None:
    # Valid data written by some other version of an application: the shape says
    # nothing about how to spell it, so it is carried rather than dropped or guessed.
    assert encode_document(_PROFILE, {"unknown": {"deep": 1}})["unknown"] == {"deep": 1}


def test_a_candidate_carries_encodings_rather_than_either_comparison_form() -> None:
    # `json_contains` compares JSON values type-strictly, so the boolean's cast form
    # (MariaDB's `1`) and the decimal's managed value (a JSON number) each match no
    # element — silently, with the statement planning and executing.
    assert encode_candidate(
        _ENTRIES, {("kind",): "home", ("active",): True, ("price",): 19.99}
    ) == {"kind": "home", "active": True, "price": "19.99"}


def test_a_candidate_nests_and_leaves_unnamed_paths_unconstrained() -> None:
    assert encode_candidate(_PROFILE, {("origin", "city"): "Oslo"}) == {"origin": {"city": "Oslo"}}
    # No `entries: []`: an unnamed `many` is unconstrained, not absent.
    assert encode_candidate(_PROFILE, {("flag",): True}) == {"flag": True}


def test_a_candidate_names_at_least_one_declared_leaf_path() -> None:
    with pytest.raises(DocumentEncodingError, match="at least one"):
        encode_candidate(_PROFILE, {})
    with pytest.raises(DocumentEncodingError, match="declared leaf"):
        encode_candidate(_PROFILE, {("origin",): "Oslo"})
    with pytest.raises(DocumentEncodingError, match="no occurrence"):
        encode_candidate(_PROFILE, {("absent", "city"): "Oslo"})


def test_a_document_is_recognized_once_on_the_way_to_a_driver() -> None:
    assert is_document({"a": 1})
    assert is_document([{"a": 1}])
    # A JSON *string* argument a dialect spells — the array guard's `[]` — stays a
    # string, so the two never collide at the bind seam.
    assert not is_document("[]")
    assert not is_document(None)


def test_decode_stored_is_dialect_agnostic() -> None:
    assert decode_stored('{"a": 1}') == {"a": 1}  # MariaDB JSON text
    assert decode_stored(b'{"a": 1}') == {"a": 1}  # MariaDB JSON bytes
    assert decode_stored({"a": 1}) == {"a": 1}  # Postgres parsed jsonb
    assert decode_stored(None) is None  # SQL NULL column


def test_decode_leaf_is_the_identity_wherever_the_document_spelling_is_the_wire_one() -> None:
    # Eight of the twelve rows: a member the layout moved into a Structured Column
    # reaches a result row spelled exactly as a Column of its own would spell it, so
    # the layout is not observable through the value.
    for spelling, value in (
        ("boolean", True),
        ("int32", -7),
        ("int64", 7),
        ("string", "alpha"),
        ("date", "2026-01-15"),
        ("time", "09:30:00"),
        ("uuid", "123e4567-e89b-12d3-a456-426614174000"),
        ("bytes", "0a1b"),
    ):
        assert decode_leaf(spelling, value) == value


def test_decode_leaf_converts_the_three_rows_whose_spellings_differ_by_layout() -> None:
    # A `decimal` is stored as its exact digit STRING and read back from a Column as
    # a number; a `timestamp` is stored at UTC with a `Z` terminator and read back
    # from a Column with an explicit offset.
    assert decode_leaf("decimal(12,2)", "10.25") == Decimal("10.25")
    assert decode_leaf("timestamp", "2026-01-15T09:30:00.000000Z") == "2026-01-15T09:30:00+00:00"


def test_decode_leaf_reads_a_float32_at_its_declared_width() -> None:
    # `1048576.2` is the shortest number that decodes back to binary32 `1048576.25`,
    # so it is that value's encoding and not its own: reading it at binary64 would
    # answer a number no `float32` Column can hold, and the layout would be
    # observable through the value.
    assert decode_leaf("float32", 1048576.2) == 1048576.25
    # A value binary32 holds exactly is unchanged, and a binary64 member never
    # narrows.
    assert decode_leaf("float32", 1.5) == 1.5
    assert decode_leaf("float64", 1048576.2) == 1048576.2


def test_a_float_document_number_reads_as_a_float_of_its_declared_width() -> None:
    # `20` and `20.0` are one JSON number and either rendering may be written, so an
    # integer-rendered float carries the float value a Column of that width reads
    # back, not a Python `int`. An integer NO float of the width holds exactly names
    # no value of that space at all: `2**24 + 1` is invalid stored data for a
    # `float32` rather than the nearest binary32 to it.
    assert decode_leaf("float32", 20) == 20.0
    assert isinstance(decode_leaf("float32", 20), float)
    assert isinstance(decode_leaf("float64", 20), float)
    assert decode_leaf("float64", 2**24 + 1) == float(2**24 + 1)
    with pytest.raises(DocumentEncodingError, match="invalid stored data"):
        decode_leaf("float32", 2**24 + 1)


def test_an_integral_float_number_answers_the_same_whichever_rendering_carries_it() -> None:
    # `20` and `20.0` are one JSON number, so validity cannot depend on which of them
    # the parser handed back as an `int` and which as a `float`. `2**24 + 1` names a
    # value binary32 does not hold, in either rendering, so both are invalid stored
    # data — never the silently rounded `16777216.0` a narrow-first reader answers.
    for rendering in (2**24 + 1, float(2**24 + 1)):
        with pytest.raises(DocumentEncodingError, match="invalid stored data"):
            decode_leaf("float32", rendering)
    assert decode_leaf("float32", 20) == decode_leaf("float32", 20.0) == 20.0
    # The same law one width up: binary64 holds neither `2**53 + 1` nor any decimal
    # naming it, so that integer is a member of no float space either.
    with pytest.raises(DocumentEncodingError, match="invalid stored data"):
        decode_leaf("float64", 2**53 + 1)


def test_a_stored_leaf_that_is_not_the_tables_own_spelling_is_refused() -> None:
    # Every type has exactly ONE document spelling (m-document-codec), so a stored
    # leaf that parses into the declared value space is still invalid stored data
    # unless it IS that spelling. Each row below decodes cleanly and is a different
    # document from the one a writer of the same value stores — and the six
    # text-compared spellings are the characters SQL compares and orders by, so
    # reading one back would answer with a row no predicate over that member finds.
    for spelling, stored in (
        ("decimal(12,2)", "1.5"),  # short of the declared scale
        ("decimal(12,2)", 1.5),  # a JSON number, not the exact digit string
        ("decimal(12,2)", "01.50"),  # a leading zero
        ("bytes", "0A1B"),  # uppercase hexadecimal
        ("bytes", "0a 1b"),  # separated octets
        ("date", "20260115"),  # ISO basic format
        ("time", "09:30"),  # not zero-padded to seconds
        ("timestamp", "2026-01-15T11:30:00+02:00"),  # a non-UTC offset
        ("timestamp", "2026-01-15T09:30:00Z"),  # not at microsecond precision
        ("uuid", "123E4567-E89B-12D3-A456-426614174000"),  # uppercase
        ("uuid", "123e4567e89b12d3a456426614174000"),  # hyphenless
        ("float32", 1048576.3),  # binary32 1048576.25's encoding is `1048576.2`
    ):
        with pytest.raises(DocumentEncodingError, match="invalid stored data"):
            decode_leaf(spelling, stored)


def test_every_admitted_leaf_is_exactly_what_the_encoder_produces() -> None:
    # The inverse law, stated over the table itself: `decode_leaf`'s domain is
    # `encode_leaf`'s codomain and nothing wider, so re-encoding what a stored leaf
    # decodes to reproduces that leaf character for character.
    for spelling, literal in (
        ("boolean", True),
        ("int32", -7),
        ("int64", 2**40),
        ("float32", 1.5),
        ("float64", 2.25),
        ("string", "alpha"),
        ("decimal(12,2)", 10.25),
        ("bytes", "0A1B"),
        ("date", "2026-01-15"),
        ("time", "09:30"),
        ("timestamp", "2026-01-15T11:30:00+02:00"),
        ("uuid", "123E4567-E89B-12D3-A456-426614174000"),
    ):
        document = encode_leaf(spelling, literal)
        assert encode_leaf(spelling, decode_leaf(spelling, document)) == document


@pytest.mark.parametrize(
    ("spelling", "value"),
    (("boolean", 1), ("int32", 2**40), ("int64", 2**80), ("string", 7)),
)
def test_identity_encoded_leaf_must_belong_to_its_declared_type(
    spelling: str, value: object
) -> None:
    with pytest.raises(DocumentEncodingError, match=f"names no {spelling} value"):
        encode_leaf(spelling, value)


def test_a_stored_leaf_outside_its_declared_type_is_refused_rather_than_read() -> None:
    # The domain `decode_leaf` inverts is the encoding table's own codomain, so a
    # stored value outside it contradicts the shape that declares the member and is
    # invalid stored data (m-document-codec) rather than a value to hand back. Each
    # row below is a leaf the JSON kind, the declared width, or the spelling refuses.
    for spelling, stored in (
        ("decimal(12,2)", "bogus"),
        ("decimal(12,2)", "1.005"),
        ("boolean", 1),
        ("int32", "5"),
        ("int32", 2**31),
        ("int64", 2.5),
        ("string", False),
        ("bytes", "zz"),
        ("date", "2026-13-40"),
        ("time", "09:30:00+02:00"),
        ("timestamp", "2026-01-15T09:30:00"),
        ("uuid", "not-a-uuid"),
    ):
        with pytest.raises(DocumentEncodingError, match="invalid stored data"):
            decode_leaf(spelling, stored)


def test_decode_leaf_carries_absence_through_and_refuses_an_uncovered_type() -> None:
    assert decode_leaf("string", None) is None
    with pytest.raises(DocumentEncodingError, match="no neutral type"):
        decode_leaf("interval", "P1D")
