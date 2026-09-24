"""Managed-document authoring and the one effective-change rule.

The opt-lock witnesses hold the outcomes a database can observe — `m-opt-lock-001`
that an empty effective change set emits no statement, `-014` that per-row
elimination is scalar equality, `-020` that an undeclared key inside a stored
occurrence takes no part. What stays here is what no case can reach: the rule
stated at the operation's own interface, over operands no write path has to
produce.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Iterable, Mapping, Sequence
from typing import cast

import pytest

import parallax.core.document_codec._authoring as authoring
from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    STRING,
    Decimal,
    FrozenMap,
    NeutralType,
    coerce_neutral_input,
    matches_neutral_type,
    retain_document_value,
)
from parallax.core.document_codec import Leaf, MemberShape, Occurrence, classify_effective_change
from parallax.core.document_codec._authoring import (
    BORROWED_SOURCE_ACCESS,
    MAPPING_SOURCE_ACCESS,
    prepare_authoring,
    prepare_member_authoring,
    validate_authoring,
    validate_member_authoring,
)
from parallax.core.document_codec._managed import EffectiveChangeSet
from parallax.core.metamodel import Multiplicity

_GEO = MemberShape(members=(Leaf("lat", STRING, True),))
_ZONE = MemberShape(members=(Leaf("label", STRING, True),))
_ORIGIN = MemberShape(
    members=(
        Leaf("city", STRING, True),
        Occurrence("geo", Multiplicity.ONE, True, _GEO),
        Occurrence("zones", Multiplicity.MANY, False, _ZONE),
    )
)
_ENTRY = MemberShape(members=(Leaf("kind", STRING, True), Leaf("price", Decimal(12, 2), True)))
_SHAPE = MemberShape(
    members=(
        Leaf("flag", BOOLEAN, True),
        Leaf("amount", Decimal(12, 2), True),
        Leaf("day", DATE, True),
        Leaf("payload", BYTES, True),
        Occurrence("origin", Multiplicity.ONE, True, _ORIGIN),
        Occurrence("entries", Multiplicity.MANY, False, _ENTRY),
    )
)


def _normalize(neutral_type: NeutralType, value: object, _path: str) -> tuple[object, bool]:
    managed = coerce_neutral_input(value, neutral_type)
    return retain_document_value(managed), matches_neutral_type(managed, neutral_type)


class _Borrowed:
    def __init__(self, values: Mapping[str, object]) -> None:
        self.values = values
        self.name_reads = 0

    def __parallax_authoring_names__(self) -> Iterable[str]:
        self.name_reads += 1
        return self.values.keys()

    def __parallax_authoring_member__(self, name: str, /) -> object:
        return self.values[name]


def test_authoring_prepares_borrowed_and_mapping_sources_into_one_owned_tree() -> None:
    origin = _Borrowed({"city": "Oslo", "geo": None})
    entries = [{"kind": "home", "price": decimal.Decimal("1.20")}]

    prepared = prepare_authoring(
        _SHAPE,
        {"flag": True, "origin": origin, "entries": entries},
        source_access=BORROWED_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )

    assert prepared.failures == {}
    value = prepared.value
    assert type(cast("object", value)) is FrozenMap
    assert value == {
        "flag": True,
        "origin": {"city": "Oslo", "geo": None, "zones": ()},
        "entries": ({"kind": "home", "price": decimal.Decimal("1.20")},),
    }
    assert origin.name_reads == 1
    entries[0]["kind"] = "changed"
    assert cast("Sequence[Mapping[str, object]]", value["entries"])[0]["kind"] == "home"


def test_validation_only_reports_sparse_canonical_failures_without_output_construction() -> None:
    failures = validate_authoring(
        _SHAPE,
        {
            "flag": "not-bool",
            "origin": {"city": "Oslo", "zones": None},
            "entries": [],
        },
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )

    assert tuple(failures) == (0, 4)
    assert failures[0].reason == "type-mismatch"
    assert failures[4].reason == "value-object-missing"
    assert failures[4].path == "zones"


def test_validation_only_never_adopts_a_success_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_adoption(_values: object) -> object:
        raise AssertionError("validation-only traversal constructed output")

    monkeypatch.setattr(authoring, "adopt_frozen_map", reject_adoption)

    failures = validate_authoring(
        _SHAPE,
        {"flag": True, "origin": {"city": "Oslo"}, "entries": []},
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )

    assert failures == {}


def test_member_validation_covers_null_marker_valid_and_invalid_leaves() -> None:
    flag = cast("Leaf", _SHAPE.members[0])
    marker = {"computed": "server"}

    assert (
        prepare_member_authoring(
            flag,
            marker,
            source_access=MAPPING_SOURCE_ACCESS,
            normalize_leaf=_normalize,
            allow_marker=True,
        ).value
        == marker
    )
    assert (
        validate_member_authoring(
            flag,
            None,
            source_access=MAPPING_SOURCE_ACCESS,
            normalize_leaf=_normalize,
        )
        is None
    )
    assert (
        validate_member_authoring(
            flag,
            marker,
            source_access=MAPPING_SOURCE_ACCESS,
            normalize_leaf=_normalize,
            allow_marker=True,
        )
        is None
    )
    assert (
        validate_member_authoring(
            flag,
            True,
            source_access=MAPPING_SOURCE_ACCESS,
            normalize_leaf=_normalize,
        )
        is None
    )
    failure = validate_member_authoring(
        flag,
        "not-boolean",
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )
    assert failure is not None
    assert failure.reason == "type-mismatch"


def test_preparation_rejects_a_root_without_named_member_access() -> None:
    with pytest.raises(TypeError, match="must expose named members"):
        prepare_authoring(
            _SHAPE,
            object(),
            source_access=MAPPING_SOURCE_ACCESS,
            normalize_leaf=_normalize,
        )


def test_preparation_records_root_leaf_and_explicit_nested_null_failures() -> None:
    prepared = prepare_authoring(
        _SHAPE,
        {
            "flag": "not-boolean",
            "origin": {"city": "Oslo"},
            "entries": [],
        },
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )
    required_child = MemberShape(members=(Leaf("required", STRING, False),))
    nested = prepare_authoring(
        MemberShape(members=(Occurrence("child", Multiplicity.ONE, False, required_child),)),
        {"child": {"required": None}},
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )

    assert prepared.failures[0].reason == "type-mismatch"
    assert nested.failures[0].path == "required"


def test_authoring_preserves_explicit_null_many_until_policy_rejects_it() -> None:
    prepared = prepare_authoring(
        _SHAPE,
        {"entries": None},
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_normalize,
    )

    assert prepared.value["entries"] is None
    assert prepared.failures == {}


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
    # An empty sequence is no document either, so it is not read as one carrying
    # every `many`'s zero.
    assert _classify({"origin": {}}, {"origin": []}).effective == frozenset({"origin"})


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


def test_a_tuple_and_a_list_are_both_carriers_of_one_value() -> None:
    # A frozen prepared carrier and a decoded one may arrive on the two sides, so
    # the comparison ends in a structural equality rather than in the containers'
    # own.
    elements = ({"kind": "home", "price": None},)
    assert _classify({"entries": elements}, {"entries": list(elements)}).restored == frozenset(
        {"entries"}
    )
