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
    "RawLocatedMemberInput",
    "SetLeaf",
    "SetValue",
    "Unavailable",
    "apply_patches",
    "comparison_text",
    "decode_occurrence_classified",
    "locate_raw_entity_member",
    "prepared_raw_member_classifier",
    "reduce_declared_members",
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
