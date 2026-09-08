"""The managed-document operations (m-document-codec, "Operations").

A managed document is one whose leaves are already the host carriers of their
declared Neutral Types — what a caller assigns and what a read decodes — rather
than the encoded spellings :mod:`parallax.core.document_codec._document` reads and
writes. These operations therefore decode nothing and refuse nothing: of everything the
shape states they read composition alone — which members are declared, and whether
each is a leaf, a ``one``, or a ``many`` — over a document whose leaves are
somebody else's answer, so a stored value that violates a current authoring
constraint stays correctable.

This file imports the shape algebra and nothing else of the codec, which is what
makes "takes managed leaves, decodes nothing, never refuses" checkable rather than
asserted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeIs

from parallax.core.document_codec._shape import (
    DocumentMember,
    DocumentShape,
    Leaf,
    Occurrence,
)
from parallax.core.metamodel import Multiplicity

__all__ = [
    "EffectiveChangeSet",
    "canonical_managed_document",
    "classify_effective_change",
]


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


def canonical_managed_document(
    shape: DocumentShape, document: Mapping[str, object] | None
) -> Mapping[str, object] | None:
    """``document`` reduced to the one form its shape gives its logical value.

    Only declared members contribute; an undeclared key is dropped. Presence is
    preserved at every containment depth — a member the document omits stays
    omitted and one it holds as ``None`` stays ``None`` — so the distinction an
    assignment makes between removing a member and storing a null survives.

    A ``many`` is the one member with no absent state to preserve: an omitted key,
    a ``None``, and an empty collection are three spellings of one zero value, and
    all three canonicalize to the empty collection at every depth. A ``one`` is
    canonicalized recursively and a ``many`` element-wise in stored order.

    Unlike :func:`~parallax.core.document_codec.reduce_declared_members`, which
    reads encoded leaves and refuses a shape it cannot decode against, this reads
    managed leaves, passes each through untouched, and refuses nothing: a value
    contradicting its declared shape passes through as itself and compares
    unequal to any well-formed one.

    The answer is ``document`` itself when the document is already canonical, and
    shares every nested container the canonical form did not have to rebuild.
    Container type is not a criterion: a tuple and a list are both canonical
    sequence carriers, and a mapping proxy and a dict both canonical mapping ones,
    so a frozen carrier is answered as itself. A root that is no mapping at all is
    the same contradiction one nested position deep and is answered the same way,
    as itself, rather than reduced to a document it never was.
    """
    if not _is_document(document):
        return document
    return _canonical_document(shape, document)


def classify_effective_change(
    shape: DocumentShape,
    authored: Mapping[str, object],
    originals: Mapping[str, object],
) -> EffectiveChangeSet:
    """Which of ``authored``'s members change the value they were authored
    against, and which restore it.

    ``authored`` carries the explicitly assigned members alone, never the
    identity: a member no assignment names is untouched rather than compared, so
    nothing here fills one. ``originals`` is keyed by those same names, and a name
    it does not carry is the observed null — an absent Document Path and a stored
    null are one logical value at this boundary, whatever the member's kind, which
    is the collapse the encoded operations deliberately leave to a consumer.

    Below that top level presence is the shape's, through
    :func:`canonical_managed_document`: an omitted declared leaf or ``one`` inside
    an assigned occurrence differs from an explicit null and can therefore be an
    effective change, while an omitted ``many`` is that occurrence's empty
    collection.
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


def _canonical_document(
    shape: DocumentShape, document: Mapping[str, object]
) -> Mapping[str, object]:
    rebuilt: dict[str, object] = {}
    declared = {member.name for member in shape.members}
    changed = any(key not in declared for key in document)
    for member in shape.members:
        if member.name not in document:
            if _is_many(member):
                rebuilt[member.name] = []
                changed = True
            continue
        value = document[member.name]
        canonical = _canonical_member(member, value)
        rebuilt[member.name] = canonical
        changed = changed or canonical is not value
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
