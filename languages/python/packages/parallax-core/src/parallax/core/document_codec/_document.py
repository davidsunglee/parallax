"""The document operations (m-document-codec, "Operations").

Every operation is a pure function of its arguments: none mutates its input document,
and a returned document shares no mutable state with one passed in.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import ClassVar, Final, Literal, Self, TypeGuard, cast

from parallax.core.base import (
    SQL_NULL,
    DocumentValue,
    FrozenMap,
    NeutralType,
    PresentDocument,
    SqlNull,
    adopt_frozen_map,
    detach_json_container,
    retain_document_value,
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
    ExplicitNull,
    Leaf,
    MemberShape,
    Missing,
    Occurrence,
    Presence,
    Present,
    resolve,
)
from parallax.core.metamodel import Multiplicity
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire

__all__ = [
    "UNAVAILABLE",
    "DecodedMember",
    "DocumentFinding",
    "DocumentFindingCode",
    "DocumentPatch",
    "DocumentPathSegment",
    "LocatedMemberInput",
    "RawLocatedMemberInput",
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
    "locate_raw_entity_member",
    "prepared_raw_member_classifier",
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
    """One stored-shape contradiction at a logical document member path.

    ``stored_value`` is the internal value the contradiction was judged about,
    captured before the classification collapses it: the codec's :data:`MISSING`
    marker where the member was genuinely absent from a traversable object, and
    the rejected value itself otherwise.
    """

    code: DocumentFindingCode
    path: tuple[DocumentPathSegment, ...]
    stored_value: object


class Unavailable:
    """A classified member for which hydration would require invention.

    Sameness is identity: :data:`UNAVAILABLE` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[Unavailable | None] = None

    def __new__(cls) -> Unavailable:
        if Unavailable._instance is None:
            Unavailable._instance = super().__new__(cls)
        return Unavailable._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("Unavailable admits one instance and therefore no subclass")

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


class _PresentJsonNull:
    __slots__ = ()


_PRESENT_JSON_NULL: Final = _PresentJsonNull()
type RawLocatedMemberInput = SqlNull | Missing | _PresentJsonNull | DocumentValue
"""An allocation-free direct-member witness that distinguishes present JSON null."""


def _is_document_object(value: object) -> TypeGuard[Mapping[str, object]]:
    return type(value) in (dict, FrozenMap)


def _is_document_array(value: object) -> TypeGuard[Sequence[object]]:
    return type(value) in (list, tuple)


def _isolated_document_container(value: object) -> object:
    if type(value) is FrozenMap:
        return cast("FrozenMap[object, object]", value)
    if type(value) is tuple:
        return retain_document_value(cast("tuple[object, ...]", value))
    return detach_json_container(value)


def _adopt_document_builder(value: object) -> object:
    if isinstance(value, dict):
        builder = cast("dict[str, object]", value)
        for key, nested in builder.items():
            builder[key] = _adopt_document_builder(nested)
        return adopt_frozen_map(builder)
    return retain_document_value(value)


type _ObjectOutput = Callable[[MemberShape, Iterable[object]], object]
type _ManyOutput = Callable[[Iterable[object]], object]


def _mapping_output(shape: MemberShape, values: Iterable[object]) -> dict[str, object]:
    output: dict[str, object] = {}
    for member, value in zip(shape.members, values, strict=True):
        if not isinstance(value, Missing):
            output[member.name] = value
    return output


def _list_output(values: Iterable[object]) -> list[object]:
    return list(values)


def locate_entity_member(document: DocumentValue, member: str) -> Missing | PresentDocument:
    """Locate one direct Entity member in a raw Entity document carrier."""
    if _is_document_object(document) and member in document:
        return PresentDocument(cast("DocumentValue", document[member]))
    return MISSING


def locate_raw_entity_member(document: DocumentValue, member: str) -> RawLocatedMemberInput:
    """Locate one direct member without allocating a presence wrapper."""
    if not _is_document_object(document):
        return MISSING
    value = document.get(member, MISSING)
    if isinstance(value, Missing):
        return MISSING
    return _PRESENT_JSON_NULL if value is None else cast("DocumentValue", value)


def prepared_raw_member_classifier(
    shape: MemberShape,
    member_name: str,
    *,
    build_object: _ObjectOutput = _mapping_output,
    build_many: _ManyOutput = _list_output,
) -> Callable[[RawLocatedMemberInput], tuple[object, tuple[DocumentFinding, ...]]]:
    """Prepare classification and final-output construction for one raw witness."""
    member = shape.member(member_name)
    if member is None:  # pragma: no cover - compiled callers resolve declared members
        raise KeyError(f"{member_name!r} names no member of the shape")
    path = (member_name,)
    if isinstance(member, Leaf):
        return _PreparedRawLeafClassifier(member, path)

    def classify_occurrence(
        located: RawLocatedMemberInput,
    ) -> tuple[object, tuple[DocumentFinding, ...]]:
        carrier = (
            SQL_NULL
            if isinstance(located, (SqlNull, Missing))
            else PresentDocument(
                None if located is _PRESENT_JSON_NULL else cast("DocumentValue", located)
            )
        )
        classified = decode_occurrence_classified(
            member.shape,
            carrier,
            multiplicity=member.multiplicity,
            nullable=member.nullable,
            build_object=build_object,
            build_many=build_many,
        )
        value = classified.presence.value if isinstance(classified.presence, Present) else None
        return value, tuple(
            replace(finding, path=(member_name, *finding.path)) for finding in classified.findings
        )

    return classify_occurrence


def decode_located_member_classified(
    shape: MemberShape,
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


@dataclass(frozen=True, slots=True)
class _PreparedRawLeafClassifier:
    member: Leaf
    path: tuple[str]

    def __call__(
        self, located: RawLocatedMemberInput
    ) -> tuple[object, tuple[DocumentFinding, ...]]:
        raw = (
            MISSING
            if isinstance(located, (SqlNull, Missing))
            else None
            if located is _PRESENT_JSON_NULL
            else located
        )
        if isinstance(raw, Missing):
            findings = (
                (DocumentFinding("required-member-absent", self.path, raw),)
                if not self.member.nullable
                else ()
            )
            return None, findings
        if raw is None:
            findings = (
                (DocumentFinding("required-member-null", self.path, raw),)
                if not self.member.nullable
                else ()
            )
            return None, findings
        try:
            return decode_canonical_wire(self.member.type, cast("WireValue", raw)), ()
        except WireDecodingError:
            return UNAVAILABLE, (DocumentFinding("leaf-undecodable", self.path, raw),)


def decode_occurrence_classified(
    shape: MemberShape,
    located: SqlNull | PresentDocument,
    *,
    multiplicity: Multiplicity,
    nullable: bool,
    build_object: _ObjectOutput = _mapping_output,
    build_many: _ManyOutput = _list_output,
) -> DecodedMember:
    """Classify one occurrence and construct its caller-selected final output.

    The two construction operations synchronously consume interpreted values in
    canonical shape order. They choose only the output carrier; classification,
    recursive decoding, and finding paths remain this module's one traversal.
    """
    member = Occurrence("", multiplicity, nullable, shape)
    raw = MISSING if isinstance(located, SqlNull) else located.document
    classified = _classify_member(member, raw, (), isolate=False)
    if not isinstance(classified.presence, Present):
        return classified
    output, findings = _decoded_occurrence_output(
        shape,
        classified.presence.value,
        multiplicity,
        build_object,
        build_many,
    )
    return DecodedMember(Present(output), (*classified.findings, *findings))


def decode_path_classified(
    shape: MemberShape, document: DocumentValue, path: Sequence[str]
) -> DecodedMember:
    """Classify one requested path without raising for contradictory stored state."""
    resolve(shape, path)
    if not _is_document_object(document):
        first = shape.member(path[0])
        if first is None:  # pragma: no cover - resolve proved the first segment
            raise KeyError(f"{path[0]!r} names no member of the shape")
        return _classify_member(first, MISSING, (path[0],))
    current = cast("Mapping[str, DocumentValue]", document)
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
        if not _is_document_object(value):  # pragma: no cover - a present One is an object
            return DecodedMember(UNAVAILABLE, classified.findings)
        current = cast("Mapping[str, DocumentValue]", value)
        scope = member.shape
    raise AssertionError("a classified document path is nonempty")  # pragma: no cover


def _classify_member(
    member: Leaf | Occurrence,
    raw: object | Missing,
    path: tuple[DocumentPathSegment, ...],
    *,
    isolate: bool = True,
) -> DecodedMember:
    if isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY:
        if isinstance(raw, Missing) or raw is None:
            return DecodedMember(Present([]))
        if not _is_document_array(raw) or not all(_is_document_object(item) for item in raw):
            return DecodedMember(Present([]), (DocumentFinding("many-wrong-kind", path, raw),))
        return DecodedMember(Present(_isolated_document_container(raw) if isolate else raw))
    if isinstance(raw, Missing):
        findings = (
            (DocumentFinding("required-member-absent", path, raw),) if not member.nullable else ()
        )
        return DecodedMember(MISSING, findings)
    if raw is None:
        findings = (
            (DocumentFinding("required-member-null", path, raw),) if not member.nullable else ()
        )
        return DecodedMember(NULL, findings)
    if isinstance(member, Occurrence):
        if not _is_document_object(raw):
            return DecodedMember(MISSING, (DocumentFinding("one-wrong-kind", path, raw),))
        return DecodedMember(Present(_isolated_document_container(raw) if isolate else raw))
    try:
        return DecodedMember(Present(decode_leaf(member.type, raw)))
    except LeafEncodingError:
        return DecodedMember(UNAVAILABLE, (DocumentFinding("leaf-undecodable", path, raw),))


def reduce_declared_members_classified(
    shape: MemberShape,
    document: object,
    *,
    build_object: _ObjectOutput = _mapping_output,
    build_many: _ManyOutput = _list_output,
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """Interpret one requested occurrence into caller-selected final containers.

    With the default builders this is the dictionary reduction a READ applies, so
    which members it keys is the read
    contract (`m-snapshot-read` *What a materialized value carries*) rather than an
    option: a member the document holds contributes its decoded value, a member it
    omits contributes nothing unless it is a ``many`` — whose omitted and JSON-null
    spellings are one zero value keyed as ``[]`` — and a classified position
    contributes what its verdict collapses to. The one entry that is not a value is
    an undecodable leaf, keyed as `UNAVAILABLE` so a materializing caller can tell it
    from a decoded one and leave that member out. Presence preservation belongs to
    the plain reduction, whose consumer is the mutation comparison's authored side.
    """
    return _decoded_object_output(shape, document, build_object, build_many)


def _decoded_occurrence_output(
    shape: MemberShape,
    raw: object,
    multiplicity: Multiplicity,
    build_object: _ObjectOutput,
    build_many: _ManyOutput,
) -> tuple[object, tuple[DocumentFinding, ...]]:
    if multiplicity is not Multiplicity.MANY:
        return _decoded_object_output(shape, raw, build_object, build_many)
    findings: list[DocumentFinding] = []
    documents = cast("Sequence[object]", raw)

    def elements() -> Iterable[object]:
        for index, document in enumerate(documents):
            value, nested = _decoded_object_output(shape, document, build_object, build_many)
            findings.extend(replace(finding, path=(index, *finding.path)) for finding in nested)
            yield value

    output = build_many(elements())
    return output, tuple(findings)


def _decoded_object_output(
    shape: MemberShape,
    document: object,
    build_object: _ObjectOutput,
    build_many: _ManyOutput,
) -> tuple[object, tuple[DocumentFinding, ...]]:
    if document is None:
        return None, ()
    if not _is_document_object(document):
        return None, (DocumentFinding("one-wrong-kind", (), document),)
    findings: list[DocumentFinding] = []
    output = build_object(
        shape,
        _interpreted_members(
            shape, cast("Mapping[str, WireValue]", document), findings, build_object, build_many
        ),
    )
    return output, tuple(findings)


def _interpreted_members(
    shape: MemberShape,
    source: Mapping[str, WireValue],
    findings: list[DocumentFinding],
    build_object: _ObjectOutput,
    build_many: _ManyOutput,
) -> Iterator[object]:
    # Paid once per declared member of every decoded object whether or not the
    # document holds it, so a leaf is decided in place rather than per call.
    for member in shape.members:
        name = member.name
        raw = source.get(name, MISSING)
        if isinstance(member, Leaf):
            if isinstance(raw, Missing):
                if not member.nullable:
                    findings.append(DocumentFinding("required-member-absent", (name,), raw))
                yield MISSING
            elif raw is None:
                if not member.nullable:
                    findings.append(DocumentFinding("required-member-null", (name,), raw))
                yield None
            else:
                try:
                    value = decode_canonical_wire(member.type, raw)
                except WireDecodingError:
                    findings.append(DocumentFinding("leaf-undecodable", (name,), raw))
                    value = UNAVAILABLE
                yield value
        else:
            yield _interpreted_occurrence(member, raw, source, findings, build_object, build_many)


def _interpreted_occurrence(
    member: Occurrence,
    raw: object | Missing,
    source: Mapping[str, object],
    findings: list[DocumentFinding],
    build_object: _ObjectOutput,
    build_many: _ManyOutput,
) -> object:
    name = member.name
    classified = _classify_member(member, raw, (name,), isolate=False)
    findings.extend(classified.findings)
    if member.multiplicity is Multiplicity.MANY:
        documents: object = (
            classified.presence.value if isinstance(classified.presence, Present) else ()
        )
        output, nested_findings = _decoded_occurrence_output(
            member.shape,
            documents,
            member.multiplicity,
            build_object,
            build_many,
        )
        findings.extend(replace(finding, path=(name, *finding.path)) for finding in nested_findings)
        return output
    if isinstance(classified.presence, Present):
        output, nested_findings = _decoded_object_output(
            member.shape,
            classified.presence.value,
            build_object,
            build_many,
        )
        findings.extend(replace(finding, path=(name, *finding.path)) for finding in nested_findings)
        return output
    return None if classified.findings or name in source else MISSING


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


def encode_document(shape: MemberShape, values: Mapping[str, Presence]) -> FrozenMap[str, object]:
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
                retain_document_value(presence.value) if isinstance(presence, Present) else ()
            )
            continue
        if isinstance(presence, Missing):
            continue
        if isinstance(presence, ExplicitNull):
            document[member.name] = None
            continue
        document[member.name] = (
            retain_document_value(encode_leaf(member.type, presence.value))
            if isinstance(member, Leaf)
            else retain_document_value(presence.value)
        )
    return adopt_frozen_map(document)


def encode_many(
    shape: MemberShape, elements: Sequence[Mapping[str, Presence]]
) -> tuple[FrozenMap[str, object], ...]:
    """The one document a ``MANY`` occurrence stores: the ordered array whose elements
    are, in the sequence's own order, the :func:`encode_document` of each element's
    values against that occurrence's shape.

    It exists because :func:`encode_document` builds one object from one value mapping
    while a ``MANY`` is a *sequence* of them — without it, a ``many`` occurrence would
    have exactly one construction route, a consumer assembling the array itself, which
    is the one JSON structure this module would then not own. An empty sequence yields
    ``[]``.
    """
    return tuple(encode_document(shape, element) for element in elements)


def encode_managed_document(
    shape: MemberShape, values: Mapping[str, object]
) -> FrozenMap[str, object]:
    """Encode one managed occurrence directly into recursively immutable storage."""
    document: dict[str, object] = {}
    for member in shape.members:
        if member.name not in values:
            if isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY:
                document[member.name] = ()
            continue
        value = values[member.name]
        if value is None:
            document[member.name] = () if _is_many(member) else None
        elif isinstance(member, Leaf):
            document[member.name] = retain_document_value(encode_leaf(member.type, value))
        elif member.multiplicity is Multiplicity.MANY:
            document[member.name] = encode_managed_many(
                member.shape, cast("Sequence[Mapping[str, object]]", value)
            )
        else:
            document[member.name] = encode_managed_document(
                member.shape, cast("Mapping[str, object]", value)
            )
    return adopt_frozen_map(document)


def encode_managed_many(
    shape: MemberShape, elements: Sequence[Mapping[str, object]]
) -> tuple[FrozenMap[str, object], ...]:
    """Encode managed Many elements once, preserving their semantic order."""
    return tuple(encode_managed_document(shape, element) for element in elements)


def decode_path(shape: MemberShape, document: object, path: Sequence[str]) -> Presence:
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
        if not _is_document_array(raw):
            raise _invalid(
                path, f"holds {raw!r}, which is not the array a `many` occurrence stores"
            )
        return Present(_isolated_document_container(raw))
    if isinstance(raw, Missing):
        if holder is not None and not member.nullable:
            raise _invalid(path, "is required and its key is absent")
        return MISSING
    if raw is None:
        if not member.nullable:
            raise _invalid(path, "is required and its key holds JSON null")
        return NULL
    if isinstance(member, Occurrence):
        if not _is_document_object(raw):
            raise _invalid(
                path, f"holds {raw!r}, which is not the object a `one` occurrence stores"
            )
        return Present(_isolated_document_container(raw))
    try:
        return Present(decode_leaf(member.type, raw))
    except LeafEncodingError as exc:
        raise _invalid(
            path, f"holds {raw!r}, which is no {member.type!r} value's document encoding"
        ) from exc


def _invalid(path: Sequence[str], detail: str) -> ValueError:
    return ValueError(f"{'.'.join(path)!r} {detail} — invalid stored data")


def _holder(
    shape: MemberShape, document: object, path: Sequence[str]
) -> Mapping[str, object] | None:
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
    if not _is_document_object(document):
        raise _invalid(path, f"is read out of {document!r}, which is not a document object")
    current = document
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
        if not _is_document_object(held):
            raise _invalid(
                path[: depth + 1],
                f"holds {held!r}, which is not the object a `one` occurrence stores",
            )
        current = held
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
    shape: MemberShape, constraints: Mapping[tuple[str, ...], object]
) -> FrozenMap[str, object]:
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
        nest[path[-1]] = retain_document_value(encode_leaf(member.type, value))
    return cast("FrozenMap[str, object]", _adopt_document_builder(candidate))


def apply_patches(
    shape: MemberShape, document: object, patches: Sequence[DocumentPatch]
) -> FrozenMap[str, object]:
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

    The result is recursively immutable. Mutable inputs and replacement payloads
    are retained before sharing, while already-owned subtrees may be reused.
    """
    if not patches:
        raise ValueError("a patch sequence is nonempty")
    if type(document) is FrozenMap:
        current = dict(cast("FrozenMap[str, object]", document).items())
    elif isinstance(document, Mapping):
        current = {
            key: retain_document_value(nested)
            for key, nested in cast("Mapping[str, object]", document).items()
        }
    else:
        current = {}
    for patch in patches:
        _apply(shape, current, patch)
    return cast("FrozenMap[str, object]", _adopt_document_builder(current))


def _apply(shape: MemberShape, root: dict[str, object], patch: DocumentPatch) -> None:
    member = resolve(shape, patch.path)
    target = root
    for name in patch.path[:-1]:
        child = target.get(name)
        if isinstance(child, dict):
            target = cast("dict[str, object]", child)
            continue
        replacement = (
            dict(cast("FrozenMap[str, object]", child).items()) if type(child) is FrozenMap else {}
        )
        target[name] = replacement
        target = replacement
    name = patch.path[-1]
    if isinstance(patch, SetValue):
        if not isinstance(member, Occurrence):
            raise ValueError(f"{'.'.join(patch.path)!r} names a leaf; use SetLeaf")
        target[name] = retain_document_value(patch.document)
    elif isinstance(patch.value, Missing):
        target.pop(name, None)
    elif isinstance(patch.value, ExplicitNull):
        target[name] = None
    elif isinstance(member, Leaf):
        target[name] = retain_document_value(encode_leaf(member.type, patch.value.value))
    else:
        raise ValueError(f"{'.'.join(patch.path)!r} names an occurrence; use SetValue")


def reduce_declared_members(
    shape: MemberShape,
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
            elif isinstance(raw, (list, tuple)):
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
