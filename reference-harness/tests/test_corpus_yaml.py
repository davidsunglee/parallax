"""The corpus YAML schema (m-case-format "The corpus YAML schema")."""

from __future__ import annotations

import datetime

import pytest

from reference_harness.corpus_yaml import load_corpus_yaml
from reference_harness.portable_literal import AuthoredNumber, decode_number


# `m-case-format` fixes the corpus's YAML schema at YAML 1.2 core, so a plain
# scalar resolves to null / boolean / integer / float in the core schema's own
# spellings and to a string otherwise. Each case below is a scalar a host
# library's default YAML 1.1 resolvers read as a DIFFERENT value, which is how two
# readers of one corpus file come to grade two different documents.
@pytest.mark.parametrize(
    ("scalar", "value"),
    [
        ("on", "on"),
        ("off", "off"),
        ("yes", "yes"),
        ("no", "no"),
        ("NO", "NO"),
        ("True", True),
        ("false", False),
        ("1_000", "1_000"),
        ("1:30", "1:30"),
        ("017", 17),
        ("0o17", 15),
        ("0x1f", 31),
        ("2024-01-01", "2024-01-01"),
        ("2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        ("09:30:00", "09:30:00"),
        ("~", None),
        ("null", None),
        ("42", 42),
        ("4.5", 4.5),
        (".inf", float("inf")),
    ],
)
def test_a_plain_scalar_resolves_under_the_core_schema(scalar: str, value: object) -> None:
    loaded = load_corpus_yaml(f"key: {scalar}\n")
    assert loaded == {"key": value} or (value != value and loaded["key"] != loaded["key"])


def test_a_temporal_scalar_stays_its_portable_literal() -> None:
    # The corollary that matters most: a corpus temporal value reaches a grader as
    # the ISO text `m-document-codec` defines, never as a host date object some
    # loader constructed. A grader that received the object would compare it against
    # a value space whose literal form is text, and answer differently from one that
    # received the text.
    loaded = load_corpus_yaml("orderedOn: 2024-01-05\noccurredAt: 2024-01-05T09:30:00Z\n")
    assert loaded == {"orderedOn": "2024-01-05", "occurredAt": "2024-01-05T09:30:00Z"}
    assert not isinstance(loaded["orderedOn"], datetime.date)


def test_quoting_an_ambiguous_scalar_changes_nothing() -> None:
    assert load_corpus_yaml("country: NO\n") == load_corpus_yaml('country: "NO"\n')


def test_an_empty_plain_scalar_is_null() -> None:
    # The core schema's null vocabulary is `null` / `Null` / `NULL` / `~` / the EMPTY
    # scalar, and the empty one is the alternative a resolver table keyed by first
    # character cannot express: an empty scalar has no first character, so a table
    # that spells the entry as one registers a bucket nothing reaches and `key:`
    # silently becomes the empty STRING — a different document, and one that reads as
    # a present value where the corpus wrote an absent one.
    assert load_corpus_yaml("key:\n") == {"key": None}
    assert load_corpus_yaml("key:\n") == load_corpus_yaml("key: null\n")
    assert load_corpus_yaml("outer:\n  inner:\n") == {"outer": {"inner": None}}


def test_a_number_carries_the_digits_it_was_authored_with() -> None:
    # Which float a number names depends on the DECLARED width, which no parser sees,
    # so the literal travels with the carrier for the seam that does. The carrier
    # itself is the binary64 nearest the literal, so an ordinary consumer reads a
    # number.
    loaded = load_corpus_yaml("ratio: 1.0000000596046448\n")
    assert isinstance(loaded["ratio"], AuthoredNumber)
    assert loaded["ratio"].literal == "1.0000000596046448"
    assert loaded["ratio"] == float("1.0000000596046448")
    assert not isinstance(load_corpus_yaml("count: 7\n")["count"], float)


def test_a_float32_rounds_from_the_authored_digits_not_from_the_carrier() -> None:
    # `1.0000000596046448` lies ABOVE the midpoint between binary32 `1.0` and its
    # successor, so one rounding at binary32 names the successor. Its nearest binary64
    # IS that midpoint, so a consumer that narrows the carrier ties to even and answers
    # `1.0` — two roundings, both round-to-nearest-even, and a different value.
    authored = load_corpus_yaml("ratio: 1.0000000596046448\n")["ratio"]
    successor = 1.0 + 2.0**-23
    assert decode_number(authored, binary32=True) == successor
    assert decode_number(float(authored), binary32=True) == 1.0
    assert decode_number(authored, binary32=False) == float("1.0000000596046448")


def test_a_number_exactly_between_two_floats_names_the_one_with_the_even_mantissa() -> None:
    # `1 + 3 * 2**-24` is exactly halfway between the binary32 successors of `1.0`,
    # and the LOWER of the pair has the odd mantissa, so round-to-nearest-EVEN picks
    # the upper. A rule that broke the tie by proximity alone, or toward the search's
    # own starting point, would answer the lower one.
    halfway = load_corpus_yaml("ratio: 1.000000178813934326171875\n")["ratio"]
    assert decode_number(halfway, binary32=True) == 1.0 + 2.0**-22


def test_the_float32_overflow_boundary_is_the_magnitude_that_rounds_to_an_infinity() -> None:
    # `2**128 - 2**103` is half an ulp above the largest finite binary32, so it is the
    # first magnitude that rounds to an infinity — a member of no float space. One
    # below it still names the largest finite value, even though the binary64 a host
    # parser would put THAT number in has already overflowed the width.
    largest_finite = float(2**128 - 2**104)
    below = load_corpus_yaml(f"ratio: {2**128 - 2**103 - 1}\n")["ratio"]
    assert decode_number(below, binary32=True) == largest_finite
    assert decode_number(2**128 - 2**103 - 1, binary32=True) == largest_finite
    assert (
        decode_number(load_corpus_yaml(f"ratio: {2**128 - 2**103}\n")["ratio"], binary32=True)
        is None
    )
