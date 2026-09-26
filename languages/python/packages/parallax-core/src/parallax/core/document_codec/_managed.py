from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple, TypeIs, cast

from parallax.core.document_codec._document import reduce_declared_members
from parallax.core.document_codec._shape import (
    DocumentMember,
    Leaf,
    MemberShape,
    Occurrence,
)
from parallax.core.metamodel import Multiplicity

__all__ = [
    "PreparedEffectiveChange",
    "classify_effective_change",
    "prepare_effective_change",
]

_EXHAUSTED = object()


@dataclass(frozen=True, slots=True)
class EffectiveChangeSet:
    """How one write's authored members divide against the values they revise.

    The two sets are disjoint and together name exactly the declared members the
    assignment spelled; a key the shape does not declare takes no part in either.
    Neither carries a payload: a caller selects its own already-prepared values by
    these names, so nothing here rewrites what will be stored.
    """

    effective: frozenset[str]
    restored: frozenset[str]


def classify_effective_change(
    shape: MemberShape,
    authored: Mapping[str, object],
    originals: Mapping[str, object],
) -> EffectiveChangeSet:
    """Which of ``authored``'s members change the value they were authored
    against, and which restore it.

    ``authored`` carries the explicitly assigned members alone, never the
    identity: a member no assignment names is untouched rather than compared, so
    nothing here fills one. ``originals`` is read by those same names and by
    nothing else — it may carry the whole observed row, and a member ``authored``
    does not name is never read, compared, or normalized — and a name it does
    not carry is the observed null: an absent Document Path and a stored null
    are one logical value at this boundary, whatever the member's kind, which is
    the collapse the encoded operations deliberately leave to a consumer.

    Below that top level presence is the shape's: only declared members
    contribute, an omitted declared leaf or ``one`` inside an assigned occurrence
    differs from an explicit null and can therefore be an effective change, and
    an omitted, null, or empty ``many`` is one value, that occurrence's empty
    collection. Managed leaves compare as they are, so a value contradicting its
    declared shape is compared as itself rather than refused.
    """
    effective: set[str] = set()
    restored: set[str] = set()
    for name, value in authored.items():
        member = shape.member(name)
        if member is None:
            continue
        original = originals.get(name)
        if value == original or _structurally_equal(
            _canonical_member(member, value), _canonical_member(member, original)
        ):
            restored.add(name)
        else:
            effective.add(name)
    return EffectiveChangeSet(effective=frozenset(effective), restored=frozenset(restored))


class _Assigned(NamedTuple):
    position: int
    member: DocumentMember
    value: object


class PreparedEffectiveChange:
    """:func:`classify_effective_change`'s rule, prepared once for positional rows.

    A row is positional over the prepared shape: one cell per member, a ``one``
    occurrence a tuple positional over its own shape, a ``many`` a tuple of
    those, and the prepared absence marker at every position the row does not
    hold. Only the assigned positions are read, and a row is compared in place
    rather than through a view, copy, or member set.
    """

    __slots__ = ("_absent", "_assigned")

    def __init__(self, assigned: tuple[_Assigned, ...], absent: object) -> None:
        self._assigned = assigned
        self._absent = absent

    def any_effective(self, row: tuple[object, ...]) -> bool:
        """Whether any assignment changes ``row``, stopping at the first that does."""
        absent = self._absent
        for position, member, value in self._assigned:
            if not _restores(member, value, row[position], absent):
                return True
        return False

    def effective_positions(self, row: tuple[object, ...]) -> Iterator[int]:
        """The positions of ``row`` the assignments change, in authored order."""
        absent = self._absent
        for position, member, value in self._assigned:
            if not _restores(member, value, row[position], absent):
                yield position


def prepare_effective_change(
    shape: MemberShape, assigned: Mapping[str, object], *, absent: object
) -> PreparedEffectiveChange:
    """Prepare the effective-change comparison of ``assigned`` against rows of ``shape``.

    Each assigned occurrence is reduced once to the complete document the
    assignment would store, whether it arrives managed or in its encoded
    spelling, and canonicalized once; a name ``shape`` does not declare takes no
    part. A row position holding ``absent`` is always an effective change: the
    marker is a value the row holds, never the observed null a missing mapping
    key is to :func:`classify_effective_change`.
    """
    prepared: list[_Assigned] = []
    for name, value in assigned.items():
        position = shape.position(name)
        if position is None:
            continue
        member = shape.members[position]
        prepared.append(_Assigned(position, member, _prepared_value(member, value)))
    return PreparedEffectiveChange(tuple(prepared), absent)


def _prepared_value(member: DocumentMember, value: object) -> object:
    if isinstance(member, Leaf):
        return value
    if member.multiplicity is Multiplicity.MANY:
        reduced: object = [
            reduce_declared_members(member.shape, element, preserve_presence=True)
            for element in cast("Sequence[object]", value)
        ]
    else:
        reduced = reduce_declared_members(member.shape, value, preserve_presence=True)
    return _canonical_member(member, reduced)


def _restores(member: DocumentMember, value: object, cell: object, absent: object) -> bool:
    if cell is absent:
        return False
    if isinstance(member, Leaf):
        return value == cell or _structurally_equal(value, cell)
    return _occurrence_restores(member, value, cell, absent)


def _occurrence_restores(member: Occurrence, value: object, cell: object, absent: object) -> bool:
    """Whether canonical ``value`` equals the canonical form of positional ``cell``.

    A null ``many`` cell is that occurrence's empty collection, as an omitted
    one is inside a document.
    """
    if member.multiplicity is Multiplicity.MANY:
        items = () if cell is None else cast("tuple[tuple[object, ...], ...]", cell)
        if not _is_array(value) or len(value) != len(items):
            return False
        shape = member.shape
        for element, item in zip(value, items, strict=True):
            if not (_is_document(element) and _document_restores(shape, element, item, absent)):
                return False
        return True
    if not isinstance(cell, tuple):
        return _structurally_equal(value, cell)
    return _is_document(value) and _document_restores(
        member.shape, value, cast("tuple[object, ...]", cell), absent
    )


def _document_restores(
    shape: MemberShape, value: Mapping[str, object], cell: tuple[object, ...], absent: object
) -> bool:
    held = 0
    for member, stored in zip(shape.members, cell, strict=True):
        if stored is absent:
            if not _is_many(member):
                continue
            stored = None
        if member.name not in value:
            return False
        held += 1
        assigned = value[member.name]
        if isinstance(member, Leaf):
            if not _structurally_equal(assigned, stored):
                return False
        elif not _occurrence_restores(member, assigned, stored, absent):
            return False
    return held == len(value)


def _canonical_document(shape: MemberShape, document: Mapping[str, object]) -> Mapping[str, object]:
    rebuilt: dict[str, object] = {}
    document_names = iter(document)
    document_name: object = next(document_names, _EXHAUSTED)
    changed = False
    for member in shape.members:
        if member.name not in document:
            if _is_many(member):
                rebuilt[member.name] = []
                changed = True
            continue
        changed = changed or document_name != member.name
        document_name = next(document_names, _EXHAUSTED)
        value = document[member.name]
        canonical = _canonical_member(member, value)
        rebuilt[member.name] = canonical
        changed = changed or canonical is not value
    changed = changed or document_name is not _EXHAUSTED
    return rebuilt if changed else document


def _canonical_member(member: DocumentMember, value: object) -> object:
    if isinstance(member, Leaf):
        return value
    if member.multiplicity is not Multiplicity.MANY:
        if not _is_document(value):
            return value
        return _canonical_document(member.shape, value)
    if value is None:
        return []
    if not _is_array(value):
        return value
    elements = [
        _canonical_document(member.shape, element) if _is_document(element) else element
        for element in value
    ]
    unchanged = all(
        canonical is original for canonical, original in zip(elements, value, strict=True)
    )
    return value if unchanged else elements


def _structurally_equal(left: object, right: object) -> bool:
    """``left`` and ``right`` as the same logical value, shape-blind.

    Canonicalization answers its input carrier when nothing changed, so the two
    sides reach here in whatever containers their producers used — a frozen tuple
    beside a decoded list, a mapping proxy beside a dict. Containers therefore
    compare by content and leaves by Python's own equality, which is what every
    write path already relies on for Decimal scale, bytes-likes, and NaN.
    """
    if _is_document(left) and _is_document(right):
        return left.keys() == right.keys() and all(
            _structurally_equal(value, right[key]) for key, value in left.items()
        )
    if _is_array(left) and _is_array(right):
        return len(left) == len(right) and all(
            _structurally_equal(one, other) for one, other in zip(left, right, strict=True)
        )
    return left == right


def _is_document(value: object) -> TypeIs[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_array(value: object) -> TypeIs[Sequence[object]]:
    """Whether ``value`` carries a document array rather than a leaf.

    Every bytes-like carrier is excluded, not just ``bytes``: a provider hands a
    ``bytearray`` or a ``memoryview`` back for a stored ``bytes`` value, and each
    is a Sequence of integers to Python while being one leaf to a caller. Reading
    one as an array would make it equal to an array of its byte values, which is a
    different logical value.
    """
    return isinstance(value, Sequence) and not isinstance(
        value, str | bytes | bytearray | memoryview
    )


def _is_many(member: DocumentMember) -> bool:
    return isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY
