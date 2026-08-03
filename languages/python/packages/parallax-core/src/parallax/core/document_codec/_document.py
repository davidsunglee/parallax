"""The document operations (m-document-codec, "Operations").

Every operation is a pure function of its arguments: none mutates its input document,
and a returned document shares no mutable state with one passed in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core.base import NeutralType
from parallax.core.document_codec._leaf import (
    LeafEncodingError,
    decode_leaf,
    encode_leaf,
    is_text_compared,
)
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
"""The closed patch algebra, and the pairing is exclusive both ways: a whole
occurrence is replaced through :class:`SetOccurrence` and never through
:class:`SetLeaf`, and a leaf is written through :class:`SetLeaf` and never through
:class:`SetOccurrence`. Either mismatch is refused rather than applied, because
applying one produces a document whose own shape would read it back as invalid
stored data."""


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
            document[member.name] = (
                _detached(presence.value) if isinstance(presence, Present) else []
            )
            continue
        if isinstance(presence, Missing):
            continue
        if isinstance(presence, ExplicitNull):
            document[member.name] = None
            continue
        document[member.name] = (
            encode_leaf(member.type, presence.value)
            if isinstance(member, Leaf)
            else _detached(presence.value)
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

    Stored content that contradicts the shape — a required path that is absent or JSON
    null, an occurrence holding something other than the object or array its
    multiplicity stores, a leaf that is no declared-type value's document encoding
    (:func:`~parallax.core.document_codec.encode_leaf`'s own codomain) — is **invalid
    stored data** and raises. This module defines no repair and no defaulting, so a
    not-present answer here always means the row is genuinely not carrying that member
    rather than that the codec chose a value for it.
    """
    member = resolve(shape, path)
    many = isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY
    holder = _holder(shape, document, path)
    raw: object | Missing = MISSING if holder is None else holder.get(path[-1], MISSING)
    if many:
        if isinstance(raw, Missing) or raw is None:
            return Present([])
        if not isinstance(raw, list):
            raise _invalid(
                path, f"holds {raw!r}, which is not the array a `many` occurrence stores"
            )
        return Present(_detached(cast("list[object]", raw)))
    if isinstance(raw, Missing):
        if holder is not None and not member.nullable:
            raise _invalid(path, "is required and its key is absent")
        return MISSING
    if raw is None:
        if not member.nullable:
            raise _invalid(path, "is required and its key holds JSON null")
        return NULL
    if isinstance(member, Occurrence):
        if not isinstance(raw, dict):
            raise _invalid(
                path, f"holds {raw!r}, which is not the object a `one` occurrence stores"
            )
        return Present(_detached(cast("dict[str, object]", raw)))
    try:
        return Present(decode_leaf(member.type, raw))
    except LeafEncodingError as exc:
        raise _invalid(
            path, f"holds {raw!r}, which is no {member.type!r} value's document encoding"
        ) from exc


def _invalid(path: Sequence[str], detail: str) -> ValueError:
    return ValueError(f"{'.'.join(path)!r} {detail} — invalid stored data")


def _holder(
    shape: DocumentShape, document: object, path: Sequence[str]
) -> dict[str, object] | None:
    """The object that would carry ``path``'s last key, or ``None`` when an ancestor
    occurrence is not present.

    Descent stops with ``None`` only where the ancestor's own declaration admits its
    absence: a **nullable** ``ONE`` occurrence whose key is absent or holds JSON null
    is a presence state the shape names, so a path below one names nothing rather than
    contradicting the shape — and a required member below such an ancestor is not a
    missing required path, because the whole subtree is legitimately absent. A
    **required** occurrence absent or null is itself the missing required path and
    raises, named at its own depth rather than at the leaf below it. A key present
    with a value of the wrong kind raises too, because answering "not present" there
    would invent an absence the row does not hold.

    A path descending through a ``MANY`` is a caller error rather than stored data: an
    element is decoded by passing it back with the occurrence's own shape, so a path
    never addresses an array position.
    """
    if not isinstance(document, dict):
        raise _invalid(path, f"is read out of {document!r}, which is not a document object")
    current = cast("dict[str, object]", document)
    scope = shape
    for depth, name in enumerate(path[:-1]):
        occurrence = scope.member(name)
        if not isinstance(occurrence, Occurrence):  # pragma: no cover - resolve() proved it
            raise KeyError(f"{'.'.join(path)!r}: the path continues past the leaf {name!r}")
        if occurrence.multiplicity is Multiplicity.MANY:
            raise KeyError(
                f"{'.'.join(path)!r}: {name!r} is a `many` occurrence, and a path never "
                "addresses an array position — decode an element against its own shape"
            )
        held = current.get(name, MISSING)
        if isinstance(held, Missing) or held is None:
            if not occurrence.nullable:
                raise _invalid(
                    path[: depth + 1],
                    "is required and its key is absent"
                    if isinstance(held, Missing)
                    else "is required and its key holds JSON null",
                )
            return None
        if not isinstance(held, dict):
            raise _invalid(
                path[: depth + 1],
                f"holds {held!r}, which is not the object a `one` occurrence stores",
            )
        current = cast("dict[str, object]", held)
        scope = occurrence.shape
    return current


def _detached(document: object) -> object:
    """A copy of ``document`` that shares no mutable state with it.

    Every operation here returns a document a caller may keep while the one it was
    built from stays reachable elsewhere — a row's stored subtree, a retained raw
    predecessor, an occurrence document a caller still holds — so a JSON object or
    array crossing this interface is copied rather than aliased. Scalars are immutable
    and are returned as they are.
    """
    if isinstance(document, dict):
        return {key: _detached(value) for key, value in cast("dict[str, object]", document).items()}
    if isinstance(document, list):
        return [_detached(item) for item in cast("list[object]", document)]
    return document


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
    can never introduce a key no member names, and it refuses a patch whose kind
    contradicts the member it names, so no patch writes an object into a leaf or a
    leaf's encoded value into an occurrence. What a patch *carries* stays the
    caller's: removing a required member's key, writing JSON null over it, or
    assigning an occurrence a document of some other shape all produce a document
    this same shape then reads back as invalid stored data, and nothing here refuses
    them.

    The input document is copied before the first patch, so the result shares no
    mutable state with it: an in-memory successor never aliases the retained
    predecessor it was patched from.
    """
    if not patches:
        raise ValueError("a patch sequence is nonempty")
    current = _detached(document)
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
        if not isinstance(member, Occurrence):
            raise ValueError(f"{'.'.join(patch.path)!r} names a leaf; use SetLeaf")
        target[name] = _detached(patch.document)
    elif isinstance(patch.value, Missing):
        target.pop(name, None)
    elif isinstance(patch.value, ExplicitNull):
        target[name] = None
    elif isinstance(member, Leaf):
        target[name] = encode_leaf(member.type, patch.value.value)
    else:
        raise ValueError(f"{'.'.join(patch.path)!r} names an occurrence; use SetOccurrence")
    return root
