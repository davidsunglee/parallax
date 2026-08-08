"""The corpus YAML schema (m-case-format "The corpus YAML schema")."""

from __future__ import annotations

import datetime

import pytest

from reference_harness.corpus_yaml import load_corpus_yaml


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
