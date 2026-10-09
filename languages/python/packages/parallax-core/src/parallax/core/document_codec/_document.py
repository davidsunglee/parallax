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
    frozen_map_json_backing,
    retain_document_value,
)
from parallax.core.document_codec._leaf import (
    LeafEncodingError,
    decode_leaf,
    encode_leaf,
    encode_scalar_many,
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
from parallax.core.wire._json import same_json_number

__all__ = [
    "UNAVAILABLE",
    "DecodedMember",
    "DocumentFinding",
    "DocumentFindingCode",
    "DocumentPatch",
    "DocumentPathSegment",
    "PreparedPatch",
    "SetScalar",
    "SetValueObject",
    "apply_prepared_patches",
    "comparison_text",
    "decode_occurrence_classified",
    "decode_scalar_many_classified",
    "encode_managed_document",
    "encode_managed_many",
    "locate_raw_entity_member",
    "located_occurrence",
    "persisted_document_equal",
    "prepare_patches",
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


def located_occurrence(located: object) -> SqlNull | PresentDocument:
    """The input :func:`decode_occurrence_classified` takes for an occurrence
    :func:`locate_raw_entity_member` ``located``: SQL null where the member or
    its whole document is missing, the present document otherwise — a present
    JSON null included — whose contents are not examined here."""
    if isinstance(located, (SqlNull, Missing)):
        return SQL_NULL
    return PresentDocument(
        None if located is _PRESENT_JSON_NULL else cast("DocumentValue", located)
    )


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
        if member.multiplicity is Multiplicity.MANY:
            return _PreparedRawScalarManyClassifier(member, path)
        return _PreparedRawLeafClassifier(member, path)

    def classify_occurrence(
        located: RawLocatedMemberInput,
    ) -> tuple[object, tuple[DocumentFinding, ...]]:
        classified = decode_occurrence_classified(
            member.shape,
            located_occurrence(located),
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


@dataclass(frozen=True, slots=True)
class _PreparedRawScalarManyClassifier:
    member: Leaf
    path: tuple[str]

    def __call__(
        self, located: RawLocatedMemberInput
    ) -> tuple[object, tuple[DocumentFinding, ...]]:
        raw = (
            None
            if isinstance(located, (SqlNull, Missing)) or located is _PRESENT_JSON_NULL
            else located
        )
        return _interpreted_scalar_many(self.member, raw, self.path)


def decode_scalar_many_classified(
    member: Leaf, located: SqlNull | PresentDocument
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """Classify one scalar collection stored in a Structured Column of its own.

    The answer is the ordered managed tuple, or :data:`UNAVAILABLE` with the
    findings that make the whole collection unavailable; finding paths are
    relative to the collection, so its own carrier is located at ``()`` and an
    element at its index.
    """
    raw = None if isinstance(located, SqlNull) else located.document
    return _interpreted_scalar_many(member, raw, ())


def _interpreted_scalar_many(
    member: Leaf, raw: object, path: tuple[DocumentPathSegment, ...]
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """The one interpretation of a reachable stored scalar collection.

    An absent carrier and JSON null are the empty collection. Any other
    non-array carrier, and any element that is not the canonical encoding of the
    declared element type, leaves the whole collection unavailable: every
    failing element is reported in element order, and no shortened collection is
    ever answered.
    """
    if raw is None or isinstance(raw, Missing):
        return (), ()
    if not _is_document_array(raw):
        return UNAVAILABLE, (DocumentFinding("leaf-undecodable", path, raw),)
    element_type = member.type
    values: list[object] = []
    findings: list[DocumentFinding] | None = None
    for index, element in enumerate(raw):
        try:
            values.append(decode_canonical_wire(element_type, cast("WireValue", element)))
        except WireDecodingError:
            if findings is None:
                findings = []
            findings.append(DocumentFinding("leaf-undecodable", (*path, index), element))
    if findings is not None:
        return UNAVAILABLE, tuple(findings)
    return tuple(values), ()


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
            if member.multiplicity is Multiplicity.MANY:
                value, many_findings = _interpreted_scalar_many(member, raw, (name,))
                findings.extend(many_findings)
                yield value
            elif isinstance(raw, Missing):
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
class SetScalar:
    """Write one scalar member's path and leave every other key untouched.

    ``value`` is the member's managed presence: a single scalar's
    ``NeutralValue``, or a scalar collection's whole ordered tuple. Writing a
    :class:`~parallax.core.document_codec.Present` stores that value's encoding,
    :data:`~parallax.core.document_codec.NULL` stores JSON null — the empty
    array for a collection, which has no null — and
    :data:`~parallax.core.document_codec.MISSING` removes the key. The encoding is
    this module's to spell, which is why :func:`prepare_patches` resolves the path
    against a shape rather than taking an already-spelled document value.
    """

    path: tuple[str, ...]
    value: Presence


@dataclass(frozen=True, slots=True)
class SetValueObject:
    """Replace the Value Object occurrence at ``path`` with ``document``, whole.

    ``document`` is that occurrence's complete stored document — the object a ``one``
    holds, the ordered array a ``many`` holds — or ``None``, which stores JSON null.
    Nothing inside the replaced subtree survives: an omitted declared member is absent
    afterwards and an undeclared key is gone. Cardinality selects no arm here, because
    an author who states an occurrence has stated a complete value either way.
    """

    path: tuple[str, ...]
    document: object


type DocumentPatch = SetScalar | SetValueObject
"""The closed patch algebra, named by member kind rather than multiplicity, and
the pairing is exclusive both ways: an occurrence is replaced through
:class:`SetValueObject` and never written through :class:`SetScalar`, and a
scalar leaf of either multiplicity is written through :class:`SetScalar` and
never through :class:`SetValueObject`. Either mismatch is refused rather than
applied, because applying one produces a document whose own shape would read it
back as invalid stored data."""


def encode_managed_document(
    shape: MemberShape, values: Mapping[str, object]
) -> FrozenMap[str, object]:
    """Encode one managed occurrence directly into recursively immutable storage."""
    document: dict[str, object] = {}
    for member in shape.members:
        if member.name not in values:
            if member.multiplicity is Multiplicity.MANY:
                document[member.name] = ()
            continue
        value = values[member.name]
        if value is None:
            document[member.name] = () if _is_many(member) else None
        elif isinstance(member, Leaf):
            document[member.name] = (
                encode_scalar_many(member.type, cast("Iterable[object]", value))
                if member.multiplicity is Multiplicity.MANY
                else retain_document_value(encode_leaf(member.type, value))
            )
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


@dataclass(frozen=True, slots=True)
class PreparedPatch:
    """One patch resolved against its shape and encoded, ready to apply anywhere.

    ``value`` is the recursively immutable encoded content the path receives: a
    single scalar's spelling or JSON null when ``leaf`` names its type, and
    composite content — an occurrence's complete document or JSON null, or a
    scalar collection's encoded array — when ``leaf`` is ``None``. ``removes``
    marks a scalar patch that deletes the key instead, which no SQL assignment
    expresses.
    """

    path: tuple[str, ...]
    value: object
    leaf: NeutralType | None
    removes: bool = False


def prepare_patches(
    shape: MemberShape, patches: Sequence[DocumentPatch]
) -> tuple[PreparedPatch, ...]:
    """``patches`` resolved against ``shape`` and encoded once, in order.

    The preparation is independent of any predecessor document, so one prepared
    sequence applies to every document of that shape
    (:func:`apply_prepared_patches`) and supplies the same encoded values to a
    path-patching statement. A path the shape does not declare is refused, and so
    is a patch whose kind contradicts the member it names — a :class:`SetScalar` at
    an occurrence, whatever presence it carries, or a :class:`SetValueObject` at a
    leaf. What a patch *carries* stays the caller's: removing a required member's
    key, writing JSON null over it, or assigning an occurrence a document of some
    other shape all produce a document this same shape then reads back as invalid
    stored data, and nothing here refuses them.
    """
    if not patches:
        raise ValueError("a patch sequence is nonempty")
    prepared: list[PreparedPatch] = []
    for patch in patches:
        member = resolve(shape, patch.path)
        dotted = ".".join(patch.path)
        if isinstance(patch, SetValueObject):
            if not isinstance(member, Occurrence):
                raise ValueError(f"{dotted!r} names a leaf; use SetScalar")
            prepared.append(PreparedPatch(patch.path, retain_document_value(patch.document), None))
            continue
        if not isinstance(member, Leaf):
            raise ValueError(f"{dotted!r} names an occurrence; use SetValueObject")
        presence = patch.value
        if isinstance(presence, Missing):
            prepared.append(PreparedPatch(patch.path, None, member.type, removes=True))
        elif member.multiplicity is Multiplicity.MANY:
            elements = (
                ()
                if isinstance(presence, ExplicitNull) or presence.value is None
                else cast("Iterable[object]", presence.value)
            )
            prepared.append(
                PreparedPatch(patch.path, encode_scalar_many(member.type, elements), None)
            )
        elif isinstance(presence, ExplicitNull):
            prepared.append(PreparedPatch(patch.path, None, member.type))
        else:
            encoded = retain_document_value(encode_leaf(member.type, presence.value))
            prepared.append(PreparedPatch(patch.path, encoded, member.type))
    return tuple(prepared)


def apply_prepared_patches(
    document: object, prepared: Sequence[PreparedPatch]
) -> FrozenMap[str, object]:
    """``prepared`` applied to ``document`` in order, left to right, each over the
    result of the last.

    Every key a patch is not told to change survives, unknown keys included. That is
    the whole point of patching rather than re-encoding: an application that rebuilt a
    document from the members it knows would silently drop the rest. The unit a patch
    does change is the position it names: an occurrence patch replaces its subtree
    whole, so the keys inside one it names do NOT survive, at any depth and whatever
    the occurrence's cardinality.

    The result is recursively immutable and holds each prepared value itself, so
    every document a sequence is applied to shares its encoded content. Mutable
    inputs are retained before sharing, while already-owned subtrees may be
    reused.
    """
    if not prepared:
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
    for patch in prepared:
        target = current
        for name in patch.path[:-1]:
            child = target.get(name)
            if isinstance(child, dict):
                target = cast("dict[str, object]", child)
                continue
            replacement = (
                dict(cast("FrozenMap[str, object]", child).items())
                if type(child) is FrozenMap
                else {}
            )
            target[name] = replacement
            target = replacement
        if patch.removes:
            target.pop(patch.path[-1], None)
        else:
            target[patch.path[-1]] = patch.value
    return cast("FrozenMap[str, object]", _adopt_document_builder(current))


# Strings and object members are compared inline in the per-node loop the
# predicate-flush window's merging rows time; a helper per node would add a call
# to every one.
def persisted_document_equal(left: object, right: object) -> bool:  # noqa: C901
    """Whether two stored documents hold the same persisted content.

    Every member participates, keys no shape declares included, and so does key
    presence: an absent key and a JSON null differ. Object-member order does not
    matter and array order does. JSON kinds stay distinct — ``true`` is not
    ``1`` — and numbers compare by the exact meaning ``m-wire`` stores them
    with, so ``1`` equals ``1.0`` while a retained ``0.10000000000000001`` is not
    ``0.1``. Nothing is decoded against a shape, reduced to declared members, or
    serialized.
    """
    pending: list[tuple[object, object]] = [(left, right)]
    pop = pending.pop
    queue = pending.append
    while pending:
        first, second = pop()
        if first is second:
            continue
        kind = type(first)
        if kind is str:
            if not isinstance(second, str) or first != second:
                return False
        elif kind is FrozenMap or kind is dict:
            other_kind = type(second)
            if other_kind is not FrozenMap and other_kind is not dict:
                return False
            members = (
                frozen_map_json_backing(cast("FrozenMap[str, object]", first))
                if kind is FrozenMap
                else cast("dict[str, object]", first)
            )
            others = (
                frozen_map_json_backing(cast("FrozenMap[str, object]", second))
                if other_kind is FrozenMap
                else cast("dict[str, object]", second)
            )
            if len(members) != len(others):
                return False
            for name, value in members.items():
                other = others.get(name, _MISSING_MEMBER)
                if value is other:
                    continue
                if other is _MISSING_MEMBER:
                    return False
                if type(value) is str:
                    if not isinstance(other, str) or value != other:
                        return False
                else:
                    queue((value, other))
        elif not _alike(first, second, pending):
            return False
    return True


_MISSING_MEMBER: Final = object()
"""What :func:`persisted_document_equal` reads for a key one object lacks."""


def _alike(first: object, second: object, pending: list[tuple[object, object]]) -> bool:
    """Whether ``first``, which is neither a string nor an object, and
    ``second`` may still be equal, queuing the item pairs that decide it."""
    kind = _json_kind(first)
    if kind != _json_kind(second):
        return False
    if kind == "array":
        first_items = cast("Sequence[object]", first)
        second_items = cast("Sequence[object]", second)
        if len(first_items) != len(second_items):
            return False
        pending.extend(zip(first_items, second_items, strict=True))
        return True
    if kind == "number":
        return same_json_number(cast("int | float", first), cast("int | float", second))
    return first == second


def _json_kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if type(value) in (dict, FrozenMap):
        return "object"
    if type(value) in (list, tuple):
        return "array"
    raise TypeError(f"{type(value).__name__} is not a stored document value")


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
        try:
            reduced[member.name] = _reduced_member(
                member, source.get(member.name), preserve_presence=preserve_presence
            )
        except LeafEncodingError as exc:
            raise exc.under(member.name) from exc
    return reduced


def _reduced_member(member: Leaf | Occurrence, raw: object, *, preserve_presence: bool) -> object:
    """``raw`` reduced as ``member`` declares it, failing relative to the member."""
    if isinstance(member, Leaf) and member.multiplicity is not Multiplicity.MANY:
        return None if raw is None else decode_leaf(member.type, raw)
    if member.multiplicity is not Multiplicity.MANY:
        return reduce_declared_members(
            cast("Occurrence", member).shape, raw, preserve_presence=preserve_presence
        )
    if raw is None:
        values: Sequence[object] = ()
    elif isinstance(raw, (list, tuple)):
        values = cast("Sequence[object]", raw)
    else:
        raise LeafEncodingError(f"expected array, got {type(raw).__name__}")
    if isinstance(member, Leaf):
        return [decode_leaf(member.type, value) for value in values]
    return [
        reduce_declared_members(member.shape, value, preserve_presence=preserve_presence)
        for value in values
    ]


def _is_many(member: Leaf | Occurrence) -> bool:
    return member.multiplicity is Multiplicity.MANY
