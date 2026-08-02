"""The document operations (m-document-codec, "Operations").

Every operation is a pure function of its arguments: none mutates its input document,
and a returned document shares no mutable state with one passed in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core.base import NeutralType, decode_neutral_literal, matches_neutral_type
from parallax.core.document_codec._leaf import encode_leaf, is_text_compared
from parallax.core.document_codec._shape import (
    MISSING,
    NULL,
    DocumentShape,
    ExplicitNull,
    Leaf,
    Missing,
    Occurrence,
    Presence,
    Present,
    resolve,
)
from parallax.core.metamodel import Multiplicity

__all__ = [
    "DocumentPatch",
    "SetLeaf",
    "SetOccurrence",
    "apply_patches",
    "comparison_text",
    "decode_path",
    "encode_candidate",
    "encode_document",
    "encode_many",
]


@dataclass(frozen=True, slots=True)
class SetLeaf:
    """Write one leaf path and leave every other key untouched.

    ``value`` is a leaf presence carrying a ``NeutralValue``: writing a
    :class:`~parallax.core.document_codec.Present` stores that value's encoding,
    :data:`~parallax.core.document_codec.NULL` stores JSON null, and
    :data:`~parallax.core.document_codec.MISSING` removes the key. The encoding is
    this module's to spell, which is why :func:`apply_patches` resolves the path
    against a shape rather than taking an already-spelled document value.
    """

    path: tuple[str, ...]
    value: Presence


@dataclass(frozen=True, slots=True)
class SetOccurrence:
    """Replace the subtree at ``path`` in place.

    ``document`` is that occurrence's own document — an :func:`encode_document` object
    for a ``ONE``, an :func:`encode_many` array for a ``MANY`` — or ``None``, and it is
    the same value a subtree-replacing ``UPDATE`` binds. Every key outside the subtree
    survives; unknown keys **inside** the replaced subtree do not.
    """

    path: tuple[str, ...]
    document: object


type DocumentPatch = SetLeaf | SetOccurrence
"""The closed patch algebra: a whole occurrence is replaced through
:class:`SetOccurrence`, never through :class:`SetLeaf`."""


def encode_document(shape: DocumentShape, values: Mapping[str, Presence]) -> dict[str, object]:
    """One complete document, from ``shape`` and one presence per applicable member.

    The whole bind a consumer stores: an insert, a fresh Value Object column value, and
    a fixture document all come from here. Members are emitted in the shape's own
    order, so one set of values always produces one document. An occurrence member's
    value is written in place as the occurrence's own document, which this function
    (for a ``ONE``) or :func:`encode_many` (for a ``MANY``) produced from that
    occurrence's shape, so one complete document composes from the leaves up.

    A ``MANY`` member is never null: ``MISSING``, ``NULL``, and an empty array all
    write ``[]``, the sole zero-element representation.
    """
    document: dict[str, object] = {}
    for member in shape.members:
        presence = values.get(member.name, MISSING)
        if isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY:
            document[member.name] = presence.value if isinstance(presence, Present) else []
            continue
        if isinstance(presence, Missing):
            continue
        if isinstance(presence, ExplicitNull):
            document[member.name] = None
            continue
        document[member.name] = (
            encode_leaf(member.type, presence.value) if isinstance(member, Leaf) else presence.value
        )
    return document


def encode_many(shape: DocumentShape, elements: Sequence[Mapping[str, Presence]]) -> list[object]:
    """The one document a ``MANY`` occurrence stores: the ordered array whose elements
    are, in the sequence's own order, the :func:`encode_document` of each element's
    values against that occurrence's shape.

    It exists because :func:`encode_document` builds one object from one value mapping
    while a ``MANY`` is a *sequence* of them — without it, a ``many`` occurrence would
    have exactly one construction route, a consumer assembling the array itself, which
    is the one JSON structure this module would then not own. An empty sequence yields
    ``[]``.
    """
    return [encode_document(shape, element) for element in elements]


def decode_path(shape: DocumentShape, document: object, path: Sequence[str]) -> Presence:
    """One known path's presence, resolved against ``shape``.

    The declared Neutral Type comes from the model rather than from the caller: a leaf
    path answers with that leaf's value decoded by its declared type rather than by the
    JSON value's own shape, and an occurrence path answers with that occurrence's own
    document exactly as stored, unknown keys included. A path naming no member of
    ``shape`` is a caller error, not an absence.

    For a ``MANY`` the returned document is the array, and each of its elements is
    itself a document over that same shape — the elements are decoded one at a time by
    passing an element back here with the occurrence's own shape, which is what makes a
    ``many`` traversable without an element index.
    """
    member = resolve(shape, path)
    raw = _walk(document, path)
    if isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY:
        elements = cast("list[object]", raw) if isinstance(raw, list) else []
        return Present(elements)
    if isinstance(raw, Missing):
        return MISSING
    if raw is None:
        return NULL
    if isinstance(member, Occurrence):
        return Present(raw)
    decoded = decode_neutral_literal(raw, member.type)
    if not matches_neutral_type(decoded, member.type):
        raise ValueError(
            f"{'.'.join(path)!r} holds {raw!r}, which does not decode into its declared "
            f"type {member.type!r} — invalid stored data"
        )
    return Present(decoded)


def _walk(document: object, path: Sequence[str]) -> object | Missing:
    """The raw JSON value at ``path``, or :data:`MISSING` where the walk stops.

    A non-object intermediate blocks descent exactly as an absent key does, so every
    not-present state the stored document can hold arrives here as one answer.
    """
    current = document
    for name in path:
        if not isinstance(current, dict):
            return MISSING
        members = cast("dict[str, object]", current)
        if name not in members:
            return MISSING
        current = members[name]
    return current


def comparison_text(neutral_type: NeutralType, value: object) -> str:
    """The exact characters a dialect's text extraction returns for ``value``'s
    encoding — the literal SQL binds where the member's declared type compares as
    extracted text rather than through a cast (`m-dialect`, `m-sql`).

    Defined for exactly the six text-compared types — ``string``, ``bytes``, ``date``,
    ``time``, ``timestamp``, and ``uuid`` — and for each it is that string's own
    characters, unquoted and unescaped, so a consumer binds ``0a1b`` rather than the
    JSON text ``"0a1b"`` that carries it. The domain is fixed by how a type
    **compares**, not by its document form: ``decimal(p, s)``'s document form is a JSON
    string too and is deliberately not here, because it casts.
    """
    if not is_text_compared(neutral_type):
        raise ValueError(
            f"{neutral_type!r} has no comparison text: it is compared inside the engine's "
            "own type system through a dialect cast, which binds the managed value"
        )
    return cast("str", encode_leaf(neutral_type, value))


def encode_candidate(
    shape: DocumentShape, constraints: Mapping[tuple[str, ...], object]
) -> dict[str, object]:
    """The containment candidate a to-many equality binds: the object carrying exactly
    the constrained paths, each at its declared position under ``shape`` and spelled by
    the encoding table, and no other key.

    Containment compares JSON **values**, so neither comparison form is what it binds:
    a ``boolean`` in the form its cast comparison binds is MariaDB's ``1``, and a
    candidate ``{"flag": 1}`` matches no element storing a JSON boolean, while a
    ``decimal(p, s)`` in that form is a JSON number and ``{"amt": 1.50}`` matches no
    element storing the exact digit string ``"1.50"``.

    A candidate is a probe, never a document a row holds. A path the constraints do not
    name is left **unconstrained** rather than absent, so it contributes no key at all —
    including a ``MANY`` member, which therefore contributes no ``[]``. Each named path
    MUST reach a leaf, and a path descending through a ``ONE`` occurrence nests exactly
    as the stored document nests.

    One constrained path is one candidate key, and that is a precondition on the
    caller: a consumer holding two constraints on one path either collapses them when
    the values are equal or refuses the predicate before it reaches here, because a
    dropped constraint yields a probe that matches elements the predicate excludes,
    silently.
    """
    if not constraints:
        raise ValueError("a containment candidate carries at least one constrained path")
    candidate: dict[str, object] = {}
    for path, value in constraints.items():
        member = resolve(shape, path)
        if not isinstance(member, Leaf):
            raise ValueError(f"{'.'.join(path)!r} does not reach a leaf of the shape")
        nest = candidate
        for name in path[:-1]:
            nest = cast("dict[str, object]", nest.setdefault(name, {}))
        nest[path[-1]] = encode_leaf(member.type, value)
    return candidate


def apply_patches(
    shape: DocumentShape, document: object, patches: Sequence[DocumentPatch]
) -> object:
    """``patches`` applied in order, left to right, each over the result of the last.

    Every key a patch is not told to change survives, unknown keys included. That is
    the whole point of patching rather than re-encoding: an application that rebuilt a
    document from the members it knows would silently drop the rest. A
    :class:`SetOccurrence` replaces its subtree whole, so unknown keys **inside** it do
    not survive — the one case where patching loses data a newer writer stored, and
    deliberate, because an author who assigns a whole occurrence has stated what that
    occurrence now is.

    ``shape`` is what makes a :class:`SetLeaf`'s ``NeutralValue`` spellable here rather
    than by its caller; it also refuses a path the model does not declare, so a patch
    can never introduce a key no member names.
    """
    if not patches:
        raise ValueError("a patch sequence is nonempty")
    current = document
    for patch in patches:
        current = _apply(shape, current, patch)
    return current


def _apply(shape: DocumentShape, document: object, patch: DocumentPatch) -> object:
    member = resolve(shape, patch.path)
    root = dict(cast("dict[str, object]", document)) if isinstance(document, dict) else {}
    target = root
    for name in patch.path[:-1]:
        child = target.get(name)
        replacement = dict(cast("dict[str, object]", child)) if isinstance(child, dict) else {}
        target[name] = replacement
        target = replacement
    name = patch.path[-1]
    if isinstance(patch, SetOccurrence):
        target[name] = patch.document
    elif isinstance(patch.value, Missing):
        target.pop(name, None)
    elif isinstance(patch.value, ExplicitNull):
        target[name] = None
    elif isinstance(member, Leaf):
        target[name] = encode_leaf(member.type, patch.value.value)
    else:
        raise ValueError(f"{'.'.join(patch.path)!r} names an occurrence; use SetOccurrence")
    return root
