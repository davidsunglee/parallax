from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Final, Literal, Self, TypeGuard, cast

from parallax.core.base import (
    SQL_NULL,
    DocumentValue,
    FrozenMap,
    ManagedValue,
    NeutralType,
    PresentDocument,
    SqlNull,
    adopt_frozen_map,
    frozen_map_json_backing,
    retain_document_value,
)
from parallax.core.document_codec._leaf import (
    LeafEncodingError,
    decode_leaf,
    encode_leaf,
    encode_managed_leaf,
    encode_managed_scalar_many,
    encode_scalar_many,
    is_text_compared,
)
from parallax.core.document_codec._shape import (
    MISSING,
    NULL,
    ExplicitNull,
    MemberDefinition,
    MemberShape,
    Missing,
    OccurrenceDefinition,
    Presence,
    Present,
    ScalarDefinition,
    resolve,
)
from parallax.core.metamodel import Multiplicity
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire
from parallax.core.wire._json import same_json_number

__all__ = [
    "MAPPING_OUTPUT",
    "UNAVAILABLE",
    "DecodeOutput",
    "DecodedMember",
    "DocumentFinding",
    "DocumentFindingCode",
    "DocumentPatch",
    "DocumentPathSegment",
    "MemberDecodePlan",
    "PreparedPatch",
    "SetScalar",
    "SetValueObject",
    "apply_prepared_patches",
    "comparison_text",
    "decode_scalar_many_classified",
    "encode_managed_document",
    "encode_managed_many",
    "entity_member_plan",
    "locate_raw_entity_member",
    "located_occurrence",
    "persisted_document_equal",
    "prepare_managed_patches",
    "prepare_patches",
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

type StoredMember = RawLocatedMemberInput | PresentDocument
"""What a :class:`MemberDecodePlan` classifies: a direct member located in its
Entity's document, or the Document Read of a Structured Column of its own."""


def _is_document_object(value: object) -> TypeGuard[Mapping[str, object]]:
    return type(value) in (dict, FrozenMap)


def _is_document_array(value: object) -> TypeGuard[Sequence[object]]:
    return type(value) in (list, tuple)


def _adopt_document_builder(value: object) -> object:
    if isinstance(value, dict):
        builder = cast("dict[str, object]", value)
        for key, nested in builder.items():
            builder[key] = _adopt_document_builder(nested)
        return adopt_frozen_map(builder)
    return retain_document_value(value)


def _mapping_output(shape: MemberShape, values: list[object]) -> dict[str, object]:
    output: dict[str, object] = {}
    for member, value in zip(shape.members, values, strict=True):
        if value is not MISSING:
            output[member.name] = value
    return output


@dataclass(frozen=True, slots=True, eq=False)
class DecodeOutput:
    """The carrier a :class:`MemberDecodePlan` builds each occurrence value in.

    ``build_object`` receives one stored object's member values in canonical
    shape order, ``missing`` standing for a member the object does not hold and
    ``unavailable`` for one no value of its declared type can be read from;
    ``build_many`` receives a Many's built elements in stored order. Each is
    called once per object or Many, innermost first, while the one traversal
    runs. A carrier chooses only the output: classification, decoding, and
    finding paths are the plan's.
    """

    build_object: Callable[[MemberShape, list[object]], object]
    build_many: Callable[[list[object]], object]
    missing: object = MISSING
    unavailable: object = UNAVAILABLE


MAPPING_OUTPUT: Final = DecodeOutput(_mapping_output, list)
"""Each object a ``dict`` of the members it holds, each Many a ``list``."""


def locate_raw_entity_member(document: DocumentValue, member: str) -> RawLocatedMemberInput:
    """Locate one direct member without allocating a presence wrapper."""
    if not _is_document_object(document):
        return MISSING
    value = document.get(member, MISSING)
    if isinstance(value, Missing):
        return MISSING
    return _PRESENT_JSON_NULL if value is None else cast("DocumentValue", value)


def located_occurrence(located: object) -> SqlNull | PresentDocument:
    """The Document Read an occurrence :func:`locate_raw_entity_member`
    ``located`` is classified from as though stored in a Column of its own: SQL
    null where the member or its whole document is missing, the present
    document otherwise — a present JSON null included — whose contents are not
    examined here."""
    if isinstance(located, (SqlNull, Missing)):
        return SQL_NULL
    return PresentDocument(
        None if located is _PRESENT_JSON_NULL else cast("DocumentValue", located)
    )


def decode_scalar_many_classified(
    member: ScalarDefinition, located: SqlNull | PresentDocument
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """Classify one scalar collection stored in a Structured Column of its own.

    The answer is the ordered managed tuple, or :data:`UNAVAILABLE` with the
    findings that make the whole collection unavailable; finding paths are
    relative to the collection, so its own carrier is located at ``()`` and an
    element at its index.
    """
    return _interpreted_scalar_many(member, _stored_raw(located), ())


_LEAF: Final = 0
_ONE: Final = 1
_MANY: Final = 2
_LEAF_MANY: Final = 3


def _kind(member: MemberDefinition) -> int:
    many = member.multiplicity is Multiplicity.MANY
    if isinstance(member, ScalarDefinition):
        return _LEAF_MANY if many else _LEAF
    return _MANY if many else _ONE


class MemberDecodePlan:
    """One member's stored-shape classification, compiled once for its
    definition, an output carrier, and the path its findings are located at.

    The plan is this module's one read-side traversal. An occurrence's object
    plan fixes each member's kind and recurses through the plans of its nested
    occurrences, and is compiled once, so classifying a conforming document
    resolves nothing and wraps nothing. A finding is built only where stored
    data contradicts the shape, at the path of the nested occurrence, ``Many``
    element, or scalar collection it was found in: the traversal extends that
    path on entering each, so no finding is relocated afterwards.

    A ``One`` occurrence classifies as absent, explicit null, a present object,
    or ``one-wrong-kind``; a ``Many`` as empty, a present array of objects, or
    ``many-wrong-kind``, which also refuses any non-object element; a single
    scalar as absent, explicit null, its decoded value, or ``leaf-undecodable``.
    A scalar collection is the empty collection when absent or null, and is
    otherwise unavailable unless it is an array every element of which decodes.
    """

    __slots__ = ("_kind", "_member", "_output", "_path", "_plan")

    def __init__(
        self,
        member: MemberDefinition,
        output: DecodeOutput = MAPPING_OUTPUT,
        *,
        path: tuple[DocumentPathSegment, ...] = (),
    ) -> None:
        self._member: Any = member
        self._kind = _kind(member)
        self._output = output
        self._plan: _ObjectPlan | None = None
        self._path = path

    def value(self, stored: StoredMember) -> tuple[object, tuple[DocumentFinding, ...]]:
        """``stored``'s value and the findings classifying it: ``None`` for a
        member that is absent, null, or a ``One`` stored as something other
        than an object, and :data:`UNAVAILABLE` for a scalar that does not
        decode."""
        findings: list[DocumentFinding] = []
        presence = self._classified(stored, findings)
        value = None if presence is MISSING or presence is NULL else presence
        return value, tuple(findings) if findings else ()

    def classified(self, stored: StoredMember) -> DecodedMember:
        """``stored``'s presence and the findings classifying it."""
        findings: list[DocumentFinding] = []
        presence = self._classified(stored, findings)
        found = tuple(findings) if findings else ()
        if presence is MISSING or presence is NULL or presence is UNAVAILABLE:
            return DecodedMember(cast("Missing | ExplicitNull | Unavailable", presence), found)
        return DecodedMember(Present(presence), found)

    def _classified(self, stored: StoredMember, findings: list[DocumentFinding]) -> object:
        """The member's presence — :data:`MISSING`, :data:`NULL`,
        :data:`UNAVAILABLE`, or its present value unwrapped."""
        raw: Any = _stored_raw(stored)
        kind = self._kind
        path = self._path
        if kind == _MANY:
            return self._object_plan().many(raw, path, findings)
        if kind == _LEAF_MANY:
            value, found = _interpreted_scalar_many(self._member, raw, path)
            findings.extend(found)
            return value
        if raw is MISSING or raw is None:
            if not self._member.nullable:
                findings.append(_not_present(raw, path))
            return MISSING if raw is MISSING else NULL
        if kind == _ONE:
            if _is_document_object(raw):
                return self._object_plan().object(raw, path, findings)
            findings.append(DocumentFinding("one-wrong-kind", path, raw))
            return MISSING
        try:
            return decode_canonical_wire(self._member.type, raw)
        except WireDecodingError:
            findings.append(DocumentFinding("leaf-undecodable", path, raw))
            return UNAVAILABLE

    def _object_plan(self) -> _ObjectPlan:
        """The occurrence's object plan, compiled on first request: a read binds
        a plan for every occurrence it may classify, and compiling each tree
        then would retain it for every compiled read, decoded or not."""
        plan = self._plan
        if plan is None:
            plan = self._plan = _ObjectPlan(self._member.shape, self._output)
        return plan


def entity_member_plan(
    shape: MemberShape, member_name: str, output: DecodeOutput = MAPPING_OUTPUT
) -> MemberDecodePlan:
    """The plan classifying the direct member ``member_name`` of an Entity
    document of ``shape``, its findings located under that name.

    A name the shape does not declare is a caller error rather than an absence.
    """
    member = shape.member(member_name)
    if member is None:
        raise KeyError(f"{member_name!r} names no member of the shape")
    return MemberDecodePlan(member, output, path=(member_name,))


class _ObjectPlan:
    """One occurrence shape's members, walked over each stored object of it.

    The plan reads each member's name, type, and nullability from the shape's
    own definitions and adds one kind byte per member and the plans of its
    nested occurrences in member order, so what it retains beside the shape
    grows with the occurrences it nests rather than with its width.
    """

    __slots__ = (
        "_build_many",
        "_build_object",
        "_kinds",
        "_members",
        "_missing",
        "_nested",
        "_unavailable",
        "shape",
    )

    def __init__(self, shape: MemberShape, output: DecodeOutput) -> None:
        self.shape = shape
        self._members: tuple[Any, ...] = shape.members
        self._kinds = bytes(_kind(member) for member in shape.members)
        self._nested = tuple(
            _ObjectPlan(member.shape, output)
            for member in shape.members
            if isinstance(member, OccurrenceDefinition)
        )
        self._build_object = output.build_object
        self._build_many = output.build_many
        self._missing = output.missing
        self._unavailable = output.unavailable

    # One loop per stored object is the whole traversal: a call per member would
    # be paid by every member of every decoded object. Members and stored values
    # are typed ``Any`` so it calls no ``cast`` per member either.
    def object(  # noqa: C901
        self,
        document: Mapping[str, Any],
        path: tuple[DocumentPathSegment, ...],
        findings: list[DocumentFinding],
    ) -> object:
        """One stored object's value, each declared member classified in shape
        order and each finding appended at its path below ``path``."""
        missing = self._missing
        nested = self._nested
        occurrence = 0
        values: list[object] = []
        append = values.append
        for member, kind in zip(self._members, self._kinds, strict=True):
            name = member.name
            raw = document.get(name, MISSING)
            if kind == _LEAF:
                if raw is MISSING or raw is None:
                    if not member.nullable:
                        findings.append(_not_present(raw, (*path, name)))
                    append(missing if raw is MISSING else None)
                    continue
                try:
                    append(decode_canonical_wire(member.type, raw))
                except WireDecodingError:
                    findings.append(DocumentFinding("leaf-undecodable", (*path, name), raw))
                    append(self._unavailable)
            elif kind == _ONE:
                plan = nested[occurrence]
                occurrence += 1
                if raw is MISSING or raw is None:
                    if member.nullable:
                        append(missing if raw is MISSING else None)
                        continue
                    findings.append(_not_present(raw, (*path, name)))
                    append(None)
                    continue
                if _is_document_object(raw):
                    append(plan.object(raw, (*path, name), findings))
                else:
                    findings.append(DocumentFinding("one-wrong-kind", (*path, name), raw))
                    append(None)
            elif kind == _MANY:
                append(nested[occurrence].many(raw, (*path, name), findings))
                occurrence += 1
            else:
                value, found = _interpreted_scalar_many(member, raw, (*path, name))
                if found:
                    findings.extend(found)
                    value = self._unavailable
                append(value)
        return self._build_object(self.shape, values)

    def many(
        self, raw: object, path: tuple[DocumentPathSegment, ...], findings: list[DocumentFinding]
    ) -> object:
        """A Many's value: its stored objects built in stored order, or no
        element where it is absent, null, or anything but an array of objects."""
        if raw is MISSING or raw is None:
            return self._build_many([])
        carrier = type(raw)
        if carrier is list or carrier is tuple:
            documents = cast("Sequence[object]", raw)
            for document in documents:
                if type(document) is not dict and type(document) is not FrozenMap:
                    break
            else:
                objects = cast("Sequence[Mapping[str, object]]", documents)
                return self._build_many(
                    [
                        self.object(document, (*path, index), findings)
                        for index, document in enumerate(objects)
                    ]
                )
        findings.append(DocumentFinding("many-wrong-kind", path, raw))
        return self._build_many([])


def _stored_raw(stored: object) -> object:
    """The stored value a member's classification reads: :data:`MISSING` for
    SQL null and an absent member alike, ``None`` for a present JSON null."""
    if isinstance(stored, PresentDocument):
        return stored.document
    if stored is SQL_NULL or stored is MISSING:
        return MISSING
    if stored is _PRESENT_JSON_NULL:
        return None
    return stored


def _not_present(raw: object, path: tuple[DocumentPathSegment, ...]) -> DocumentFinding:
    """The finding a required member earns for being absent or null."""
    if raw is MISSING:
        return DocumentFinding("required-member-absent", path, raw)
    return DocumentFinding("required-member-null", path, raw)


def _interpreted_scalar_many(
    member: ScalarDefinition, raw: object, path: tuple[DocumentPathSegment, ...]
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """The one interpretation of a reachable stored scalar collection.

    An absent carrier and JSON null are the empty collection. Any other
    non-array carrier, and any element that is not the canonical encoding of the
    declared element type, leaves the whole collection unavailable: every
    failing element is reported in element order, and no shortened collection is
    ever answered.
    """
    if raw is None or raw is MISSING:
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
    afterwards and an undeclared key is gone. Cardinality selects no case here, because
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
    shape: MemberShape, cells: Sequence[object], absent: object
) -> FrozenMap[str, object]:
    """Encode one managed occurrence's positional cells directly into
    recursively immutable storage.

    ``cells`` aligns with ``shape``'s members, ``absent`` marking an omitted
    one, and every nested occurrence keeps the same positional form. Every
    value was already admitted under its declared type, so nothing here judges
    one again.
    """
    document: dict[str, object] = {}
    for member, value in zip(shape.members, cells, strict=True):
        if value is absent:
            if member.multiplicity is Multiplicity.MANY:
                document[member.name] = ()
            continue
        if value is None:
            document[member.name] = () if _is_many(member) else None
        elif isinstance(member, ScalarDefinition):
            document[member.name] = (
                encode_managed_scalar_many(member.type, cast("Iterable[ManagedValue]", value))
                if member.multiplicity is Multiplicity.MANY
                else encode_managed_leaf(member.type, value)
            )
        elif member.multiplicity is Multiplicity.MANY:
            document[member.name] = encode_managed_many(
                member.shape, cast("Sequence[Sequence[object]]", value), absent
            )
        else:
            document[member.name] = encode_managed_document(
                member.shape, cast("Sequence[object]", value), absent
            )
    return adopt_frozen_map(document)


def encode_managed_many(
    shape: MemberShape, elements: Sequence[Sequence[object]], absent: object
) -> tuple[FrozenMap[str, object], ...]:
    """Encode managed Many elements once, preserving their semantic order."""
    return tuple(encode_managed_document(shape, element, absent) for element in elements)


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
    return _prepared_patches(
        shape, patches, _validated_leaf, encode_scalar_many, retain_document_value
    )


def prepare_managed_patches(
    shape: MemberShape, patches: Sequence[DocumentPatch]
) -> tuple[PreparedPatch, ...]:
    """:func:`prepare_patches` for patches whose every value was already
    admitted under its declared type, which nothing here judges again, and
    whose every occurrence document is already encoded and owned."""
    return _prepared_patches(
        shape,
        patches,
        encode_managed_leaf,
        cast("_ManyEncoder", encode_managed_scalar_many),
        _owned,
    )


def _validated_leaf(neutral_type: NeutralType, value: object) -> object:
    return retain_document_value(encode_leaf(neutral_type, value))


def _owned(document: object) -> object:
    return document


type _ManyEncoder = Callable[[NeutralType, Iterable[object]], tuple[object, ...]]


def _prepared_patches(
    shape: MemberShape,
    patches: Sequence[DocumentPatch],
    leaf: Callable[[NeutralType, object], object],
    many: _ManyEncoder,
    document: Callable[[object], object],
) -> tuple[PreparedPatch, ...]:
    if not patches:
        raise ValueError("a patch sequence is nonempty")
    prepared: list[PreparedPatch] = []
    for patch in patches:
        member = resolve(shape, patch.path)
        dotted = ".".join(patch.path)
        if isinstance(patch, SetValueObject):
            if not isinstance(member, OccurrenceDefinition):
                raise ValueError(f"{dotted!r} names a leaf; use SetScalar")
            prepared.append(PreparedPatch(patch.path, document(patch.document), None))
            continue
        if not isinstance(member, ScalarDefinition):
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
            prepared.append(PreparedPatch(patch.path, many(member.type, elements), None))
        elif isinstance(presence, ExplicitNull):
            prepared.append(PreparedPatch(patch.path, None, member.type))
        else:
            encoded = leaf(member.type, presence.value)
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


# Strings and object members are compared inline in the per-node loop that judges
# whether adjacent temporal rows merge; a helper per node would add a call to
# every one.
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


def _reduced_member(
    member: ScalarDefinition | OccurrenceDefinition, raw: object, *, preserve_presence: bool
) -> object:
    """``raw`` reduced as ``member`` declares it, failing relative to the member."""
    if isinstance(member, ScalarDefinition) and member.multiplicity is not Multiplicity.MANY:
        return None if raw is None else decode_leaf(member.type, raw)
    if member.multiplicity is not Multiplicity.MANY:
        return reduce_declared_members(
            cast("OccurrenceDefinition", member).shape, raw, preserve_presence=preserve_presence
        )
    if raw is None:
        values: Sequence[object] = ()
    elif isinstance(raw, (list, tuple)):
        values = cast("Sequence[object]", raw)
    else:
        raise LeafEncodingError(f"expected array, got {type(raw).__name__}")
    if isinstance(member, ScalarDefinition):
        return [decode_leaf(member.type, value) for value in values]
    return [
        reduce_declared_members(member.shape, value, preserve_presence=preserve_presence)
        for value in values
    ]


def _is_many(member: ScalarDefinition | OccurrenceDefinition) -> bool:
    return member.multiplicity is Multiplicity.MANY
