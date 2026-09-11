"""The managed-document canonicalization and the one effective-change rule.

The opt-lock witnesses hold the outcomes a database can observe — `m-opt-lock-001`
that an empty effective change set emits no statement, `-014` that per-row
elimination is scalar equality, `-020` that an undeclared key inside a stored
occurrence takes no part. What stays here is what no case can reach: the rule
stated at the operation's own interface, over operands no write path has to
produce, and the copy-on-write identity a caller depends on for memory without
ever seeing it.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Mapping
from typing import cast

from parallax.core.base import BOOLEAN, BYTES, DATE, STRING, Decimal
from parallax.core.document_codec import (
    DocumentShape,
    EffectiveChangeSet,
    Leaf,
    Occurrence,
    canonical_managed_document,
    classify_effective_change,
)
from parallax.core.metamodel import Multiplicity

_GEO = DocumentShape(members=(Leaf("lat", STRING, True),))
_ZONE = DocumentShape(members=(Leaf("label", STRING, True),))
_ORIGIN = DocumentShape(
    members=(
        Leaf("city", STRING, True),
        Occurrence("geo", Multiplicity.ONE, True, _GEO),
        Occurrence("zones", Multiplicity.MANY, False, _ZONE),
    )
)
_ENTRY = DocumentShape(members=(Leaf("kind", STRING, True), Leaf("price", Decimal(12, 2), True)))
_SHAPE = DocumentShape(
    members=(
        Leaf("flag", BOOLEAN, True),
        Leaf("amount", Decimal(12, 2), True),
        Leaf("day", DATE, True),
        Leaf("payload", BYTES, True),
        Occurrence("origin", Multiplicity.ONE, True, _ORIGIN),
        Occurrence("entries", Multiplicity.MANY, False, _ENTRY),
    )
)


def _classify(authored: dict[str, object], originals: dict[str, object]) -> EffectiveChangeSet:
    return classify_effective_change(_SHAPE, authored, originals)


def test_an_absent_original_and_a_null_one_are_the_same_observed_null() -> None:
    # The collapse the encoded operations leave to their consumer, applied here at
    # the top level and only there: a stored NULL Column and an absent Document
    # Path are two spellings of one observed value, for a member of any kind, so
    # assigning null over either states nothing.
    assert _classify({"flag": None}, {}).restored == frozenset({"flag"})
    assert _classify({"flag": None}, {"flag": None}).restored == frozenset({"flag"})
    assert _classify({"flag": None}, {"flag": True}).effective == frozenset({"flag"})
    assert _classify({"origin": None}, {}).restored == frozenset({"origin"})
    assert _classify({"origin": {"city": "Oslo"}}, {}).effective == frozenset({"origin"})


def test_a_key_no_member_declares_takes_no_part_on_either_side() -> None:
    # At the top level an undeclared name is neither effective nor restored — the
    # answer partitions the DECLARED members alone. Inside an occurrence the same
    # exclusion makes a stored subtree that differs only in unknown keys equal, so
    # the write is eliminated and the key survives where issuing it would have
    # replaced the subtree and removed it.
    change = _classify({"flag": True, "unknown": 1}, {"flag": True, "unknown": 2})
    assert change == EffectiveChangeSet(effective=frozenset(), restored=frozenset({"flag"}))
    subtree = _classify(
        {"origin": {"city": "Oslo", "zones": []}},
        {"origin": {"city": "Oslo", "zones": [], "future": 7}},
    )
    assert subtree.restored == frozenset({"origin"})


def test_a_one_occurrence_compares_recursively_with_presence_preserved() -> None:
    # An assignment states a complete value, so below the top level an omitted
    # declared leaf or `one` is the member the write REMOVES and stays distinct
    # from an explicit null — the opposite of the top-level collapse above, and
    # the distinction holds at every depth.
    assert _classify({"origin": {"city": None}}, {"origin": {}}).effective == frozenset({"origin"})
    assert _classify({"origin": {}}, {"origin": {"city": None}}).effective == frozenset({"origin"})
    assert _classify({"origin": {"geo": None}}, {"origin": {}}).effective == frozenset({"origin"})
    assert _classify(
        {"origin": {"geo": {"lat": "59.9"}}}, {"origin": {"geo": {"lat": "59.9"}}}
    ).restored == frozenset({"origin"})
    assert _classify(
        {"origin": {"geo": {"lat": None}}}, {"origin": {"geo": {}}}
    ).effective == frozenset({"origin"})


def test_a_many_compares_element_wise_in_stored_order() -> None:
    elements = [{"kind": "home", "price": decimal.Decimal("1.50")}, {"kind": "work", "price": None}]
    assert _classify({"entries": elements}, {"entries": list(elements)}).restored == frozenset(
        {"entries"}
    )
    assert _classify({"entries": elements}, {"entries": elements[::-1]}).effective == frozenset(
        {"entries"}
    )


def test_every_zero_spelling_of_a_many_is_one_value_at_every_depth() -> None:
    # A `many` has no absent state to preserve: omission, null, and the empty
    # collection are three spellings of the one zero the write would store, so
    # none of the three is a change against either of the others.
    assert _classify({"entries": []}, {}).restored == frozenset({"entries"})
    assert _classify({"entries": []}, {"entries": None}).restored == frozenset({"entries"})
    assert _classify({"entries": ()}, {"entries": []}).restored == frozenset({"entries"})
    assert _classify(
        {"origin": {"city": "Oslo"}}, {"origin": {"city": "Oslo", "zones": []}}
    ).restored == frozenset({"origin"})


def test_a_top_level_member_no_assignment_names_is_never_compared_or_filled() -> None:
    # The `many` zero fill is a rule about the document an ASSIGNMENT states, so
    # an occurrence the write assigns has its omitted nested `many` filled while a
    # top-level collection the write never names is untouched: it appears in
    # neither set, whatever the originals carry for it.
    change = _classify({"flag": True}, {"flag": True, "entries": [{"kind": "home"}]})
    assert change == EffectiveChangeSet(effective=frozenset(), restored=frozenset({"flag"}))
    assert _classify(
        {"flag": True, "origin": {"city": "Oslo"}},
        {"flag": True, "origin": {"city": "Oslo", "zones": []}},
    ).restored == frozenset({"flag", "origin"})


def test_the_two_sets_partition_the_declared_authored_names_and_carry_no_payload() -> None:
    authored: dict[str, object] = {
        "flag": True,
        "amount": decimal.Decimal("3.00"),
        "origin": {"city": "Bergen", "zones": []},
        "unknown": object(),
    }
    originals: dict[str, object] = {
        "flag": True,
        "amount": decimal.Decimal("4.00"),
        "origin": {"city": "Oslo", "zones": []},
    }
    change = classify_effective_change(_SHAPE, authored, originals)
    assert change.effective == frozenset({"amount", "origin"})
    assert change.restored == frozenset({"flag"})
    assert not change.effective & change.restored
    assert change.effective | change.restored == frozenset({"flag", "amount", "origin"})
    assert authored == {
        "flag": True,
        "amount": decimal.Decimal("3.00"),
        "origin": authored["origin"],
        "unknown": authored["unknown"],
    }
    assert authored["origin"] == {"city": "Bergen", "zones": []}


def test_managed_leaves_compare_without_an_encode_decode_round_trip() -> None:
    # Every operand is already a host carrier of its declared type, so leaf
    # equality is Python's own: a Decimal's exponent, a bytes-like's carrier type,
    # and a date's calendar value answer exactly as they do everywhere else, and
    # nothing is rescaled or respelled to reach the comparison.
    assert _classify(
        {"amount": decimal.Decimal("1.0")}, {"amount": decimal.Decimal("1.00")}
    ).restored == frozenset({"amount"})
    assert _classify(
        {"amount": decimal.Decimal("1.0")}, {"amount": decimal.Decimal("1.01")}
    ).effective == frozenset({"amount"})
    assert _classify(
        {"day": dt.date(2026, 1, 15)}, {"day": dt.date(2026, 1, 15)}
    ).restored == frozenset({"day"})
    assert _classify({"payload": b"\x0a\x1b"}, {"payload": bytearray(b"\x0a\x1b")}).restored == (
        frozenset({"payload"})
    )


def test_a_value_contradicting_its_declared_shape_is_effective_rather_than_refused() -> None:
    # Stored state a current authoring constraint would reject is still readable
    # state, and a correction written against it has to reach the store. So a
    # contradiction passes through canonicalization as itself and compares unequal
    # to any well-formed value, on either side.
    assert _classify({"origin": {"city": "Oslo"}}, {"origin": "Oslo"}).effective == frozenset(
        {"origin"}
    )
    assert _classify({"entries": [{"kind": "home"}]}, {"entries": {"kind": "home"}}).effective == (
        frozenset({"entries"})
    )
    assert _classify({"origin": "Oslo"}, {"origin": "Oslo"}).restored == frozenset({"origin"})


def test_a_bytes_leaf_is_one_value_rather_than_the_array_of_its_byte_values() -> None:
    # A provider hands a stored `bytes` value back as a bytearray or a memoryview,
    # each of which Python also reads as a sequence of integers. The leaf reading
    # is the one that holds, so a correction written over a stored array of those
    # byte values is an effective change rather than a restoration of the value
    # already there.
    assert _classify({"payload": bytearray(b"ab")}, {"payload": [97, 98]}).effective == frozenset(
        {"payload"}
    )
    assert _classify({"payload": memoryview(b"ab")}, {"payload": (97, 98)}).effective == frozenset(
        {"payload"}
    )
    assert _classify({"payload": b"ab"}, {"payload": memoryview(b"ab")}).restored == frozenset(
        {"payload"}
    )


def test_a_root_that_is_no_document_passes_through_canonicalization_as_itself() -> None:
    # Totality reaches the root and not only the positions inside it. Reading a
    # non-document against the shape would invent one: an empty sequence would
    # answer a mapping carrying every `many`'s zero, and a value that is not even
    # iterable would refuse — the two failures a total operation may not have.
    empty: object = []
    assert canonical_managed_document(_SHAPE, cast("Mapping[str, object]", empty)) is empty
    scalar: object = 7
    assert canonical_managed_document(_SHAPE, cast("Mapping[str, object]", scalar)) is scalar


def test_canonicalization_keeps_declared_members_and_fills_every_many_zero() -> None:
    assert canonical_managed_document(
        _SHAPE, {"flag": True, "future": 7, "origin": {"city": "Oslo", "extra": 1}}
    ) == {
        "flag": True,
        "origin": {"city": "Oslo", "zones": []},
        "entries": [],
    }
    assert canonical_managed_document(_SHAPE, {"entries": None}) == {"entries": []}
    assert canonical_managed_document(_SHAPE, None) is None


def test_an_already_canonical_document_is_answered_as_itself() -> None:
    # Every producer feeding the comparison already emits canonical documents, so
    # the common path must allocate nothing: the answer is the input object, and a
    # rebuild shares every nested container it did not have to change.
    origin: dict[str, object] = {"city": "Oslo", "geo": None, "zones": []}
    document: dict[str, object] = {"flag": True, "origin": origin, "entries": []}
    assert canonical_managed_document(_SHAPE, document) is document

    filled = canonical_managed_document(_SHAPE, {"origin": origin})
    assert filled == {"origin": origin, "entries": []}
    assert filled is not None
    assert filled["origin"] is origin


def test_a_tuple_and_a_list_are_both_canonical_carriers_of_one_value() -> None:
    # Container type is not a canonicality criterion, so a frozen prepared carrier
    # is answered as itself; and because the two sides may therefore arrive in
    # different containers, the comparison ends in a structural equality rather
    # than in the containers' own.
    elements = ({"kind": "home", "price": None},)
    document: dict[str, object] = {"entries": elements}
    assert canonical_managed_document(_SHAPE, document) is document
    assert _classify({"entries": elements}, {"entries": list(elements)}).restored == frozenset(
        {"entries"}
    )
