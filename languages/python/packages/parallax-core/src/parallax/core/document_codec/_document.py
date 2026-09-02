"""The document operations (m-document-codec, "Operations").

Every operation is a pure function of its arguments: none mutates its input document,
and a returned document shares no mutable state with one passed in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Self, cast

from parallax.core.base import (
    DocumentValue,
    NeutralType,
    PresentDocument,
    SqlNull,
    detach_json_container,
)
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
    "UNAVAILABLE",
    "DecodedMember",
    "DocumentFinding",
    "DocumentFindingCode",
    "DocumentPatch",
    "DocumentPathSegment",
    "LocatedMemberInput",
    "SetLeaf",
    "SetValue",
    "Unavailable",
    "apply_patches",
    "comparison_text",
    "decode_located_member_classified",
    "decode_occurrence_classified",
    "decode_path",
    "decode_path_classified",
    "encode_candidate",
    "encode_document",
    "encode_many",
    "locate_entity_member",
    "reduce_declared_members",
    "reduce_declared_members_classified",
]


type DocumentFindingCode = Literal[
    "required-member-absent",
    "required-member-null",
    "one-wrong-kind",
    "many-wrong-kind",
    "leaf-undecodable",
]
"""The closed document-codec-local stored-shape finding vocabulary."""

type DocumentPathSegment = str | int
"""A declared member name or an array position in a classified document path."""


@dataclass(frozen=True, slots=True)
class DocumentFinding:
    """One stored-shape contradiction at a logical document member path."""

    code: DocumentFindingCode
    path: tuple[DocumentPathSegment, ...]


class Unavailable:
    """A classified member for which hydration would require invention.

    Sameness is identity: :data:`UNAVAILABLE` is the one instance, and it stays
    that one instance through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNAVAILABLE"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "UNAVAILABLE"


UNAVAILABLE: Final[Unavailable] = Unavailable()


@dataclass(frozen=True, slots=True)
class DecodedMember:
    """One classified member presence and its codec-local findings."""

    presence: Presence | Unavailable
    findings: tuple[DocumentFinding, ...] = ()


type LocatedMemberInput = SqlNull | Missing | PresentDocument
"""A direct member carrier after physical location but before classification."""


def locate_entity_member(document: DocumentValue, member: str) -> Missing | PresentDocument:
    """Locate one direct Entity member in a raw Entity document carrier."""
    if isinstance(document, dict) and member in document:
        return PresentDocument(document[member])
    return MISSING


def decode_located_member_classified(
    shape: DocumentShape,
    located: LocatedMemberInput,
    member_name: str,
) -> DecodedMember:
    """Classify one direct member independently of its physical carrier."""
    member = shape.member(member_name)
    if member is None:
        raise KeyError(f"{member_name!r} names no member of the shape")
    if isinstance(located, (SqlNull, Missing)):
        return _classify_member(member, MISSING, (member_name,))
    return _classify_member(member, located.document, (member_name,))


def decode_occurrence_classified(
    shape: DocumentShape,
    located: SqlNull | PresentDocument,
    *,
    multiplicity: Multiplicity,
    nullable: bool,
) -> DecodedMember:
    """Classify one top-level occurrence from its SQL-null-aware carrier."""
    member = Occurrence("", multiplicity, nullable, shape)
    raw = MISSING if isinstance(located, SqlNull) else located.document
    return _classify_member(member, raw, ())


def decode_path_classified(
    shape: DocumentShape, document: DocumentValue, path: Sequence[str]
) -> DecodedMember:
    """Classify one requested path without raising for contradictory stored state."""
    resolve(shape, path)
    if not isinstance(document, dict):
        first = shape.member(path[0])
        if first is None:  # pragma: no cover - resolve proved the first segment
            raise KeyError(f"{path[0]!r} names no member of the shape")
        return _classify_member(first, MISSING, (path[0],))
    current: dict[str, DocumentValue] = document
    scope = shape
    for depth, name in enumerate(path):
        member = scope.member(name)
        if member is None:  # pragma: no cover - resolve proved every segment
            raise KeyError(f"{'.'.join(path)!r}: {name!r} names no member of the shape")
        classified = _classify_member(member, current.get(name, MISSING), tuple(path[: depth + 1]))
        if depth == len(path) - 1:
            return classified
        if not isinstance(member, Occurrence):  # pragma: no cover - resolve proved the path
            raise KeyError(f"{'.'.join(path)!r}: the path continues past the leaf {name!r}")
        if member.multiplicity is Multiplicity.MANY:
            raise KeyError(
                f"{'.'.join(path)!r}: {name!r} is a `many` occurrence, and a path never "
                "addresses an array position — decode an element against its own shape"
            )
        if not isinstance(classified.presence, Present):
            return DecodedMember(classified.presence, classified.findings)
        value = classified.presence.value
        if not isinstance(value, dict):  # pragma: no cover - a present One is an object
            return DecodedMember(UNAVAILABLE, classified.findings)
        current = cast("dict[str, DocumentValue]", value)
        scope = member.shape
    raise AssertionError("a classified document path is nonempty")  # pragma: no cover


def _classify_member(
    member: Leaf | Occurrence,
    raw: object | Missing,
    path: tuple[DocumentPathSegment, ...],
) -> DecodedMember:
    if isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY:
        if isinstance(raw, Missing) or raw is None:
            return DecodedMember(Present([]))
        if not isinstance(raw, list) or not all(
            isinstance(item, dict) for item in cast("list[object]", raw)
        ):
            return DecodedMember(Present([]), (DocumentFinding("many-wrong-kind", path),))
        return DecodedMember(Present(detach_json_container(cast("list[DocumentValue]", raw))))
    if isinstance(raw, Missing):
        findings = (DocumentFinding("required-member-absent", path),) if not member.nullable else ()
        return DecodedMember(MISSING, findings)
    if raw is None:
        findings = (DocumentFinding("required-member-null", path),) if not member.nullable else ()
        return DecodedMember(NULL, findings)
    if isinstance(member, Occurrence):
        if not isinstance(raw, dict):
            return DecodedMember(MISSING, (DocumentFinding("one-wrong-kind", path),))
        return DecodedMember(Present(detach_json_container(cast("dict[str, DocumentValue]", raw))))
    try:
        return DecodedMember(Present(decode_leaf(member.type, raw)))
    except LeafEncodingError:
        return DecodedMember(UNAVAILABLE, (DocumentFinding("leaf-undecodable", path),))


def reduce_declared_members_classified(
    shape: DocumentShape,
    document: object,
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """Reduce one requested occurrence while returning every shape finding as data.

    This is the reduction a READ applies, so which members it keys is the read
    contract (`m-snapshot-read` *What a materialized value carries*) rather than an
    option: a member the document holds contributes its decoded value, a member it
    omits contributes nothing unless it is a ``many`` — whose omitted and JSON-null
    spellings are one zero value keyed as ``[]`` — and a classified position
    contributes what its verdict collapses to. The one entry that is not a value is
    an undecodable leaf, keyed as `UNAVAILABLE` so a materializing caller can tell it
    from a decoded one and leave that member out. Presence preservation belongs to
    the plain reduction, whose consumer is the mutation comparison's authored side.
    """
    if document is None:
        return None, ()
    if not isinstance(document, Mapping):
        return None, (DocumentFinding("one-wrong-kind", ()),)
    source = cast("Mapping[str, object]", document)
    reduced: dict[str, object] = {}
    findings: list[DocumentFinding] = []
    for member in shape.members:
        held = member.name in source
        classified = _classify_member(member, source.get(member.name, MISSING), (member.name,))
        findings.extend(classified.findings)
        if isinstance(classified.presence, Unavailable):
            reduced[member.name] = UNAVAILABLE
            continue
        if isinstance(member, Leaf):
            if isinstance(classified.presence, Present):
                reduced[member.name] = classified.presence.value
            elif isinstance(classified.presence, ExplicitNull):
                reduced[member.name] = None
            continue
        if member.multiplicity is Multiplicity.MANY:
            documents = (
                cast("list[object]", classified.presence.value)
                if isinstance(classified.presence, Present)
                else []
            )
            elements: list[object] = []
            for index, item in enumerate(documents):
                nested, nested_findings = reduce_declared_members_classified(member.shape, item)
                elements.append(nested)
                findings.extend(
                    DocumentFinding(finding.code, (member.name, index, *finding.path))
                    for finding in nested_findings
                )
            reduced[member.name] = elements
            continue
        if isinstance(classified.presence, Present):
            nested, nested_findings = reduce_declared_members_classified(
                member.shape, classified.presence.value
            )
            reduced[member.name] = nested
            findings.extend(
                DocumentFinding(finding.code, (member.name, *finding.path))
                for finding in nested_findings
            )
        elif held or classified.findings:
            reduced[member.name] = None
    return reduced, tuple(findings)


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
class SetValue:
    """Replace the occurrence at ``path`` with ``document``, whole.

    ``document`` is that occurrence's complete stored document — the object a ``one``
    holds, the ordered array a ``many`` holds — or ``None``, which stores JSON null.
    Nothing inside the replaced subtree survives: an omitted declared member is absent
    afterwards and an undeclared key is gone. Cardinality selects no arm here, because
    an author who states an occurrence has stated a complete value either way.
    """

    path: tuple[str, ...]
    document: object


type DocumentPatch = SetLeaf | SetValue
"""The closed patch algebra, and the pairing is exclusive both ways: an occurrence
is replaced through :class:`SetValue` and never written through :class:`SetLeaf`,
and a leaf is written through :class:`SetLeaf` and never through
:class:`SetValue`. Either mismatch is refused rather than applied, because
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
                detach_json_container(presence.value) if isinstance(presence, Present) else []
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
            else detach_json_container(presence.value)
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
        return Present(detach_json_container(cast("list[object]", raw)))
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
        return Present(detach_json_container(cast("dict[str, object]", raw)))
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
    document from the members it knows would silently drop the rest. The unit a patch
    does change is the position it names: a :class:`SetValue` replaces its occurrence's
    subtree whole, so the keys inside one it names do NOT survive, at any depth and
    whatever the occurrence's cardinality.

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
    current = detach_json_container(document)
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
    if isinstance(patch, SetValue):
        if not isinstance(member, Occurrence):
            raise ValueError(f"{'.'.join(patch.path)!r} names a leaf; use SetLeaf")
        target[name] = detach_json_container(patch.document)
    elif isinstance(patch.value, Missing):
        target.pop(name, None)
    elif isinstance(patch.value, ExplicitNull):
        target[name] = None
    elif isinstance(member, Leaf):
        target[name] = encode_leaf(member.type, patch.value.value)
    else:
        raise ValueError(f"{'.'.join(patch.path)!r} names an occurrence; use SetValue")
    return root


def reduce_declared_members(
    shape: DocumentShape,
    document: object,
    *,
    preserve_presence: bool = False,
) -> object:
    """Reduce stored content to one codec-owned view of the shape's declared members.

    A ``one`` is reduced recursively, a ``many`` element-wise in stored order, and
    absent or JSON-null members reduce to ``None``. Undeclared keys never contribute.

    ``preserve_presence`` asks which members **this document** holds, which the
    source answers by itself: a member the source omits contributes no key at all,
    at every containment depth, including inside a ``many`` element. A member the
    source holds as JSON null still contributes ``None``, so the
    omitted-versus-explicit-null distinction survives the reduction rather than
    collapsing into it. It is what a mutation comparison uses on BOTH sides,
    because an assignment states the complete value its occurrence will hold:
    narrowing the stored side to the members the assignment happens to name would
    call a write that removes a member no change at all.

    A ``many`` is the one member presence preservation cannot narrow, because it
    has no absent state to preserve: an omitted key, a JSON null, and ``[]`` are
    three spellings of one zero value, and the document a write composes from this
    reduction stores ``[]`` for all three. Preserving that omission would make two
    documents of one logical value compare unequal and turn a no-op write into
    DML, so an omitted ``many`` contributes its empty collection under either
    mode.
    """
    if document is None:
        return None
    if not isinstance(document, Mapping):
        raise LeafEncodingError(f"expected object, got {type(document).__name__}")
    source = cast("Mapping[str, object]", document)
    reduced: dict[str, object] = {}
    for member in shape.members:
        if preserve_presence and member.name not in source and not _is_many(member):
            continue
        raw = source.get(member.name)
        if isinstance(member, Leaf):
            if raw is None:
                reduced[member.name] = None
            else:
                try:
                    reduced[member.name] = decode_leaf(member.type, raw)
                except LeafEncodingError as exc:
                    raise exc.under(member.name) from exc
        elif member.multiplicity is Multiplicity.MANY:
            if raw is None:
                values: Sequence[object] = ()
            elif isinstance(raw, list) or (preserve_presence and isinstance(raw, tuple)):
                values = cast("Sequence[object]", raw)
            else:
                raise LeafEncodingError(
                    f"expected array, got {type(raw).__name__}", path=(member.name,)
                )
            try:
                reduced[member.name] = [
                    reduce_declared_members(
                        member.shape, value, preserve_presence=preserve_presence
                    )
                    for value in values
                ]
            except LeafEncodingError as exc:
                raise exc.under(member.name) from exc
        else:
            try:
                reduced[member.name] = reduce_declared_members(
                    member.shape,
                    cast("object", raw),
                    preserve_presence=preserve_presence,
                )
            except LeafEncodingError as exc:
                raise exc.under(member.name) from exc
    return reduced


def _is_many(member: Leaf | Occurrence) -> bool:
    return isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY
