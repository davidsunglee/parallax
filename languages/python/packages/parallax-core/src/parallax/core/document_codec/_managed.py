from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeIs

from parallax.core.document_codec._shape import (
    DocumentMember,
    Leaf,
    MemberShape,
    Occurrence,
)
from parallax.core.metamodel import Multiplicity

__all__ = [
    "classify_effective_change",
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
