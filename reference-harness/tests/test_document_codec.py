"""The harness's own reading of the portable document encoding (m-document-codec).

The corpus grades the two implementations against each other wherever a database
can observe the answer. These pin what a case cannot reach on its own: that this
twin encodes each wire literal to the one spelling the table admits, that a
containment candidate carries encodings rather than either comparison form, and
that a value the table does not cover is refused rather than passed through.
"""

from __future__ import annotations

from typing import Any

import pytest

from reference_harness.document_codec import (
    DocumentEncodingError,
    comparison_text,
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
