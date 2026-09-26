"""Managed-document authoring and the one effective-change rule.

The opt-lock witnesses hold the outcomes a database can observe — `m-opt-lock-001`
that an empty effective change set emits no statement, `-014` that per-row
elimination is scalar equality, `-020` that an undeclared key inside a stored
occurrence takes no part. What stays here is what no case can reach: the rule
stated at the operation's own interface, over operands no write path has to
produce, and the prepared positional form of that rule held to the same verdict
over generated shapes.
"""

from __future__ import annotations

import datetime as dt
import decimal
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import pytest

import parallax.core.document_codec._authoring as authoring
from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    INT32,
    JSON,
    STRING,
    Decimal,
    FrozenMap,
    NeutralType,
    coerce_neutral_input,
    matches_neutral_type,
    retain_document_value,
)
from parallax.core.document_codec import (
    Leaf,
    MemberShape,
    Occurrence,
    classify_effective_change,
    prepare_effective_change,
    reduce_declared_members,
)
from parallax.core.document_codec import _managed as managed
from parallax.core.document_codec._authoring import (
    BORROWED_SOURCE_ACCESS,
    MAPPING_SOURCE_ACCESS,
    prepare_authoring,
    prepare_member_authoring,
    validate_authoring,
    validate_member_authoring,
)
from parallax.core.document_codec._managed import EffectiveChangeSet
from parallax.core.metamodel import DocumentMember, Multiplicity
from parallax.core.unit_work import EntityStateRow

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


# --------------------------------------------------------------------------- #
# The prepared positional comparison: the same rule over the positional row a  #
# read materializes, with the assignments normalized once rather than per row. #
# --------------------------------------------------------------------------- #
_ABSENT: Final = object()


@dataclass(frozen=True, slots=True)
class _Selected:
    shape: MemberShape


def _row(shape: MemberShape, members: Mapping[str, object]) -> tuple[object, ...]:
    """``members`` positional over ``shape``, a name it omits held as ``_ABSENT``."""
    return tuple(
        _cell(member, members[member.name]) if member.name in members else _ABSENT
        for member in shape.members
    )


def _cell(member: DocumentMember, value: object) -> object:
    if isinstance(member, Leaf) or value is None or value is _ABSENT:
        return value
    if member.multiplicity is Multiplicity.MANY:
        return tuple(
            _row(member.shape, cast("Mapping[str, object]", item))
            for item in cast("Sequence[object]", value)
        )
    return _row(member.shape, cast("Mapping[str, object]", value))


def _classified(
    shape: MemberShape, assigned: Mapping[str, object], row: tuple[object, ...]
) -> list[int]:
    """The positions the keyed rule answers effective, in authored order, after
    the one normalization a write applies to its assignments: each occurrence
    reduced, presence preserved, to the document it would store."""
    normalized: dict[str, object] = {}
    for name, value in assigned.items():
        member = shape.member(name)
        if not isinstance(member, Occurrence):
            normalized[name] = value
        elif member.multiplicity is Multiplicity.MANY:
            normalized[name] = [
                reduce_declared_members(member.shape, element, preserve_presence=True)
                for element in cast("Sequence[object]", value)
            ]
        else:
            normalized[name] = reduce_declared_members(member.shape, value, preserve_presence=True)
    view = EntityStateRow.over_declared_members(_Selected(shape), row, absent=_ABSENT)
    effective = classify_effective_change(shape, normalized, view).effective
    return [cast("int", shape.position(name)) for name in assigned if name in effective]


def _prepared(
    shape: MemberShape, assigned: Mapping[str, object], row: tuple[object, ...]
) -> list[int]:
    change = prepare_effective_change(shape, assigned, absent=_ABSENT)
    positions = list(change.effective_positions(row))
    assert change.any_effective(row) is bool(positions)
    return positions


_LEAF_VALUES: Final[Mapping[NeutralType, tuple[object, ...]]] = {
    STRING: ("a", "b"),
    INT32: (1, 2),
    BOOLEAN: (True, False),
    JSON: ({"k": 1}, {"k": [1, 2]}, [1, 2], "a"),
}


class _Generated:
    """Shapes, positional rows, and assignments drawn so that a large share of
    assignments restore the row they are compared against."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def shape(self, depth: int = 0) -> MemberShape:
        draw = self._random
        members: list[DocumentMember] = []
        members.extend(
            Leaf(f"leaf{index}", draw.choice(tuple(_LEAF_VALUES)), True)
            for index in range(draw.randint(1, 3))
        )
        if depth < 2:
            members.extend(
                Occurrence(
                    f"occurrence{index}",
                    draw.choice((Multiplicity.ONE, Multiplicity.MANY)),
                    True,
                    self.shape(depth + 1),
                )
                for index in range(draw.randint(0, 2))
            )
        return MemberShape(members=tuple(members))

    def document(self, shape: MemberShape) -> dict[str, object]:
        return {
            member.name: self.value(member)
            for member in shape.members
            if self._random.random() > 0.2
        }

    def value(self, member: DocumentMember) -> object:
        draw = self._random
        if draw.random() < 0.15:
            return None
        if isinstance(member, Leaf):
            return draw.choice(_LEAF_VALUES[member.type])
        if member.multiplicity is Multiplicity.MANY:
            return [self.document(member.shape) for _ in range(draw.randint(0, 2))]
        return self.document(member.shape)

    def stored(self, shape: MemberShape) -> dict[str, object]:
        """A row's members; a name left out is the absent marker."""
        return self.document(shape)

    def assigned(self, shape: MemberShape, stored: Mapping[str, object]) -> dict[str, object]:
        draw = self._random
        assigned: dict[str, object] = {}
        for member in shape.members:
            if draw.random() < 0.4:
                continue
            restoring = member.name in stored and draw.random() < 0.6
            value = stored[member.name] if restoring else self.value(member)
            if value is None and _is_many(member):
                if draw.random() < 0.5:
                    continue
                value = cast("object", [])
            assigned[member.name] = self.perturbed(member, value)
        if draw.random() < 0.1:
            assigned["undeclared"] = "a"
        return assigned

    def perturbed(self, member: DocumentMember, value: object) -> object:
        """``value`` or, now and then, one member of it changed or omitted, or
        a JSON array in the other carrier a caller may hand over."""
        draw = self._random
        if isinstance(value, list) and isinstance(member, Leaf):
            items = cast("list[object]", value)
            return tuple(items) if draw.random() < 0.5 else items
        if not isinstance(value, dict) or draw.random() < 0.7:
            return cast("object", value)
        document = dict(cast("dict[str, object]", value))
        if document and draw.random() < 0.5:
            del document[draw.choice(tuple(document))]
        elif isinstance(member, Occurrence):
            nested = draw.choice(member.shape.members)
            document[nested.name] = self.value(nested)
        return document


def test_the_prepared_comparison_answers_the_keyed_rule_over_generated_positional_rows() -> None:
    generated = _Generated(20260925)
    restored = effective = 0
    for _ in range(3000):
        shape = generated.shape()
        stored = generated.stored(shape)
        assigned = generated.assigned(shape, stored)
        row = _row(shape, stored)
        expected = _classified(shape, assigned, row)
        assert _prepared(shape, assigned, row) == expected, (shape, assigned, stored)
        declared = sum(1 for name in assigned if shape.member(name) is not None)
        effective += len(expected)
        restored += declared - len(expected)
    assert restored > 1000 and effective > 1000


def test_a_top_level_absent_position_is_a_change_never_the_observed_null() -> None:
    # A row a read materialized holds every position; one the read left absent
    # holds the marker as a value, so even a null assignment changes it.
    for member in _SHAPE.members:
        row = _row(_SHAPE, {})
        assert _prepared(
            _SHAPE, {member.name: None} if not _is_many(member) else {member.name: []}, row
        ) == [_SHAPE.members.index(member)]
    assert _prepared(_SHAPE, {"flag": None}, _row(_SHAPE, {"flag": None})) == []


def _is_many(member: DocumentMember) -> bool:
    return isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY


def test_the_prepared_comparison_reads_only_assigned_positions_and_stops_at_the_first_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[int] = []

    class _Row(tuple[object, ...]):
        def __getitem__(self, index: object) -> object:  # pyright: ignore[reportIncompatibleMethodOverride] - an index-reading probe
            reads.append(cast("int", index))
            return super().__getitem__(cast("int", index))

    stored = _row(_SHAPE, {"flag": True, "amount": decimal.Decimal("1.00"), "day": None})
    row = _Row(stored)
    change = prepare_effective_change(
        _SHAPE, {"day": dt.date(2026, 1, 1), "amount": decimal.Decimal("1.00")}, absent=_ABSENT
    )

    assert change.any_effective(row)
    assert reads == [2]
    reads.clear()
    assert list(change.effective_positions(row)) == [2]
    assert reads == [2, 1]

    reductions: list[object] = []
    reduce = reduce_declared_members

    def counting(shape: MemberShape, document: object, **options: bool) -> object:
        reductions.append(document)
        return reduce(shape, document, **options)

    monkeypatch.setattr(managed, "reduce_declared_members", counting)
    authored = {"origin": {"city": "Oslo"}, "entries": [{"kind": "home"}, {"kind": "work"}]}
    prepared = prepare_effective_change(_SHAPE, authored, absent=_ABSENT)
    for _ in range(5):
        prepared.any_effective(_row(_SHAPE, {"origin": {"city": "Oslo"}}))
    assert len(reductions) == 3


def test_an_assignment_naming_only_undeclared_members_changes_nothing() -> None:
    change = prepare_effective_change(_SHAPE, {"unknown": 1}, absent=_ABSENT)
    assert not change.any_effective(_row(_SHAPE, {}))
    assert list(change.effective_positions(_row(_SHAPE, {}))) == []


def test_an_encoded_occurrence_is_compared_as_the_managed_document_it_decodes_to() -> None:
    # A nested leaf may arrive in its encoded spelling; preparation decodes it
    # once, so the row's managed Decimal is the value it is weighed against.
    stored = {"entries": [{"kind": "home", "price": decimal.Decimal("1.50")}]}
    row = _row(_SHAPE, stored)
    assert _prepared(_SHAPE, {"entries": [{"kind": "home", "price": "1.50"}]}, row) == []
    assert _prepared(_SHAPE, {"entries": [{"kind": "home", "price": "1.51"}]}, row) == [5]
