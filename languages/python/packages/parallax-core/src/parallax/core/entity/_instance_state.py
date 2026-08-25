"""The backing beneath a published value, and every question that reads it.

A published Entity or Value Object holds its declared members in one immutable
tuple on a dedicated slot instead of in Pydantic's instance dictionary. That is a
second backing, and without one Module owning it the compact-versus-ordinary
branch would appear at every descriptor, at edit, at row derivation, at pickle,
and inside Pydantic's own equality, repr, iteration, and compiled serializer. So
the representation lives here alone: the per-class publication plan, the slot,
the tuple and its presence bitmap, both Adapters, and the two Pydantic schema
seams. Delete this Module and the layout reappears at each of those sites.

Only a few questions vary by backing — what a declared member holds, whether the
read carried it, and, once a caller reads a published relationship tail, what a
relationship position holds. Everything else needs declared values and, at most,
presence, so it is written once over both.

The scope is sealed and granted one sibling: the sentinels a construction input
spells. It therefore reaches neither the declaration engine that builds a class
nor the writer that publishes one, which is what forces a publication plan to
arrive as plain data its owner computed. What it does read of a class is the
class's own Pydantic facts — collected fields, their defaults, their order —
because those are what a plan has to agree with.

Two index spaces run through everything below and must not be conflated::

    bit index      i                     presence, one bit per declared field
    tuple index    i + 1                 that field's position; the bitmap is 0
    tuple index    1 + members + j       relationship j, which carries no bit

A descriptor is handed the absolute tuple index and nothing else, so it knows how
to address the backing and nothing about how it is laid out.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, cast

from pydantic import BaseModel
from pydantic_core import PydanticUndefined
from pydantic_core import core_schema as cs

from parallax.core.entity._construction_input import UNLOADED

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from pydantic.annotated_handlers import GetJsonSchemaHandler
    from pydantic.json_schema import JsonSchemaValue

__all__ = [
    "COMPACT_STATE_SLOT",
    "PublicationPlan",
    "allocate",
    "declared",
    "equal",
    "fields_set",
    "hashed",
    "install",
    "is_present",
    "iterate",
    "json_schema_of",
    "plan_of",
    "publish",
    "repr_args",
    "serialization_schema",
]

COMPACT_STATE_SLOT: Final = "__parallax_compact__"
"""The one slot a published value's whole declared state occupies.

It holds a single immutable tuple — presence bitmap, then every declared member
in the class's own model-fixed order, then, on an Entity, one position per
declared broad relationship. A value that has never been published carries
nothing here at all, and that absence IS the Adapter selection: nothing branches
on a flag, because there is no flag to read.
"""

_PLAN_ATTRIBUTE: Final = "__parallax_plan__"
"""Where a class carries its own publication plan.

Stamped per exact declared class rather than resolved through the MRO, because a
descendant's occurrence and relationship positions sit after its own attribute
count and so are not its ancestor's.
"""

_EMPTY_FIELDS_SET: Final[set[str]] = set()
"""The one fields-set object every published value's slot points at.

pydantic-core reads that slot from Rust before any Parallax code runs and refuses
anything but a ``set``, so the slot cannot be left unset or filled with a frozen
value. Nothing ever hands this object out: :func:`fields_set` synthesizes a fresh
set per request, so mutating what a caller receives cannot reach it.
"""


@dataclass(frozen=True, slots=True)
class PublicationPlan:
    """One declared class's immutable publication facts.

    Derived once at class creation and never per instance, so a published value
    carries no layout pointer and composing a Domain Model neither builds nor
    mutates one. It has a single Implementation by design: it is data a deep
    module owns rather than a seam, and it must not acquire a Protocol.
    """

    template: tuple[object, ...]
    """A prebuilt row — bitmap zero, each member's declared default, an all-unloaded
    relationship tail — copied per published value, so an absent position costs the
    walk nothing."""
    required_mask: int
    """One comparison against the assembled bitmap rejects a row missing a required
    member, in place of a check on every read."""
    bits: Mapping[str, int]
    """Each declared member's presence bit."""
    indexes: Mapping[str, int]
    """Each declared member's absolute tuple index, handed to its descriptor."""
    py_names: tuple[str, ...]
    """Bit index to member name, in the model-fixed order a positional row is aligned
    to: attributes root-first, then Value Object occurrences."""
    fields: tuple[str, ...]
    """The same members in Pydantic's own field order, which is what repr,
    iteration, and serialization are stated over and which a class body's
    declaration order can make differ from :attr:`py_names`."""
    occurrences: Mapping[int, type]
    """Tuple index to the Value Object class that position takes."""
    relationships: Mapping[str, int]
    """Each declared broad relationship's absolute tuple index in the tail."""
    has_auxiliary: bool
    """Whether the class declares a ``cached_property`` or a ``PrivateAttr``, and so
    whether a published value can carry state outside its tuple at all."""


def install(
    cls: type,
    *,
    members: tuple[str, ...],
    occurrences: Mapping[str, type],
    relationships: tuple[str, ...],
) -> PublicationPlan:
    """Derive ``cls``'s publication plan, stamp it, and hand it back.

    ``members`` is the model-fixed member order — attributes root-first over the
    inheritance chain, then Value Object occurrences the same way — which is the
    order a positional construction row is aligned to. Everything else about a
    member is read from the class's own collected Pydantic field, so the default
    an absent position reads is the one Pydantic itself would have supplied and
    cannot drift from it.

    The caller installs each member's descriptor from the returned plan, which is
    why this returns rather than only stamping.
    """
    fields = cast("dict[str, Any]", getattr(cls, "__pydantic_fields__", {}))
    if set(members) != set(fields):
        raise ValueError(
            f"{cls.__name__}: the publication plan's members and the class's collected "
            "Pydantic fields name different sets, so no row of it addresses the class"
        )
    bits = {py_name: bit for bit, py_name in enumerate(members)}
    indexes = {py_name: bit + 1 for py_name, bit in bits.items()}
    required_mask = 0
    row: list[object] = [0]
    for py_name in members:
        field = fields[py_name]
        if field.is_required():
            required_mask |= 1 << bits[py_name]
            row.append(None)
        else:
            row.append(field.get_default(call_default_factory=True))
    row.extend(UNLOADED for _ in relationships)
    plan = PublicationPlan(
        template=tuple(row),
        required_mask=required_mask,
        bits=MappingProxyType(bits),
        indexes=MappingProxyType(indexes),
        py_names=members,
        fields=tuple(fields),
        occurrences=MappingProxyType(
            {indexes[py_name]: vo_class for py_name, vo_class in occurrences.items()}
        ),
        relationships=MappingProxyType(
            {py_name: 1 + len(members) + position for position, py_name in enumerate(relationships)}
        ),
        has_auxiliary=_declares_auxiliary_state(cls),
    )
    setattr(cls, _PLAN_ATTRIBUTE, plan)
    return plan


def plan_of(cls: type) -> PublicationPlan:
    """``cls``'s own publication plan."""
    return cast("PublicationPlan", getattr(cls, _PLAN_ATTRIBUTE))


def _declares_auxiliary_state(cls: type) -> bool:
    """Whether ``cls`` can hold state outside its published tuple.

    A ``cached_property`` result and a ``PrivateAttr`` value are author-owned and
    stay in ordinary per-instance storage, so a class declaring neither has a
    published value whose whole state is the tuple — which is what lets an edit
    of one avoid touching the instance dictionary at all.
    """
    if getattr(cls, "__private_attributes__", None):
        return True
    return any(
        isinstance(bound, functools.cached_property)
        for ancestor in cls.__mro__
        for bound in vars(ancestor).values()
    )


# --------------------------------------------------------------------------- #
# The two Adapters, and the three questions that vary
# --------------------------------------------------------------------------- #


def _compact(value: BaseModel) -> tuple[object, ...] | None:
    """``value``'s published row, or ``None`` when it carries ordinary backing."""
    try:
        return cast("tuple[object, ...]", object.__getattribute__(value, COMPACT_STATE_SLOT))
    except AttributeError:
        return None


def declared(value: BaseModel) -> dict[str, object]:
    """Every declared member ``value`` holds, in Pydantic field order.

    An ordinary value's dictionary is read as its class answers for it, exactly
    as Pydantic's own equality, repr, and serialization read it: this is the
    class's own surface rather than the framework's private state. A member the
    dictionary does not carry — which validation-free construction can leave out
    — is omitted rather than invented, which is the shape Pydantic's own repr and
    iteration produce.
    """
    plan = plan_of(type(value))
    row = _compact(value)
    if row is None:
        state = value.__dict__
        return {py_name: state[py_name] for py_name in plan.fields if py_name in state}
    indexes = plan.indexes
    return {py_name: row[indexes[py_name]] for py_name in plan.fields}


def is_present(value: BaseModel, bit: int) -> bool:
    """Whether the read that produced ``value`` carried the member at ``bit``.

    Allocation-free, and the only presence question internal code has: row and
    document derivation iterate declared members anyway, so a per-member
    predicate is proportional and never synthesizes a set.
    """
    row = _compact(value)
    if row is None:
        return plan_of(type(value)).py_names[bit] in value.__pydantic_fields_set__
    return bool(cast("int", row[0]) >> bit & 1)


# --------------------------------------------------------------------------- #
# One implementation over both
# --------------------------------------------------------------------------- #


def fields_set(value: BaseModel) -> set[str]:
    """A fresh observational snapshot of what ``value``'s read carried.

    Named for its single legitimate caller, ``model_fields_set``. It allocates,
    so nothing internal reaches for it: the mutable result is the caller's own
    and changes neither compact presence nor a later ``exclude_unset`` dump.
    """
    row = _compact(value)
    if row is None:
        return set(value.__pydantic_fields_set__)
    bitmap = cast("int", row[0])
    return {
        py_name for bit, py_name in enumerate(plan_of(type(value)).py_names) if bitmap >> bit & 1
    }


def allocate(cls: type[Any]) -> Any:
    """An unpopulated publication shell of ``cls``.

    Neither the ordinary constructor nor ``model_construct`` is entered: a shell
    exists so a relationship can name it before it holds anything, and it holds
    nothing until :func:`publish` attaches its row. What it is given here is only
    the Pydantic storage a shell cannot be missing — the fields-set slot
    pydantic-core reads from Rust, the extra slot every read of the value
    consults, and the private state an author's own ``PrivateAttr`` declares,
    initialized to its declared defaults exactly as validation-free construction
    would have initialized it.
    """
    instance = cast("Any", cls).__new__(cls)
    object.__setattr__(instance, "__pydantic_fields_set__", _EMPTY_FIELDS_SET)
    object.__setattr__(instance, "__pydantic_extra__", None)
    object.__setattr__(instance, "__pydantic_private__", _private_state(cls))
    return instance


def _private_state(cls: type[Any]) -> dict[str, Any] | None:
    """The private-attribute state a fresh value of ``cls`` starts out holding."""
    declarations = cast("dict[str, Any]", getattr(cls, "__private_attributes__", {}) or {})
    if not declarations:
        return None
    state: dict[str, Any] = {}
    for py_name, private in declarations.items():
        default = private.get_default()
        if default is not PydanticUndefined:
            state[py_name] = default
    return state


def publish(
    instance: BaseModel,
    values: Mapping[str, object],
    relationships: Mapping[str, object] = MappingProxyType({}),
) -> None:
    """Assemble ``instance``'s complete compact row and attach it, once.

    Attachment is the atomic act of populating the value: the row is built in
    local state and every refusal happens before anything is written, so no
    partially published value exists at any point. A member ``values`` does not
    name keeps its declared default and leaves its presence bit clear; a required
    member it does not name is one mask comparison, not a check on every read.
    """
    plan = plan_of(type(instance))
    if _compact(instance) is not None:
        raise ValueError(
            f"{type(instance).__name__} is already published, and a published value's "
            "state is attached exactly once"
        )
    indexes = plan.indexes
    bits = plan.bits
    row = list(plan.template)
    bitmap = 0
    for py_name, member in values.items():
        index = indexes.get(py_name)
        if index is None:
            raise ValueError(f"{type(instance).__name__} declares no member {py_name!r}")
        row[index] = member
        bitmap |= 1 << bits[py_name]
    if bitmap & plan.required_mask != plan.required_mask:
        missing = sorted(
            py_name
            for py_name, bit in bits.items()
            if plan.required_mask >> bit & 1 and not bitmap >> bit & 1
        )
        raise ValueError(
            f"{type(instance).__name__}: publication carries no value for required "
            f"{', '.join(missing)}"
        )
    tail = plan.relationships
    for py_name, related in relationships.items():
        index = tail.get(py_name)
        if index is None:
            raise ValueError(f"{type(instance).__name__} declares no relationship {py_name!r}")
        row[index] = related
    row[0] = bitmap
    object.__setattr__(instance, COMPACT_STATE_SLOT, tuple(row))


def equal(value: BaseModel, other: object) -> bool | Any:
    """Pydantic's own value equality, over declared members from either backing.

    Backing kind, presence bookkeeping, relationship positions, and lifecycle
    state do not participate, so a published value equals the ordinary one
    carrying the same members. Private attribute state does, because Pydantic's
    own equality counts it and this replaces that implementation rather than
    redefining it. Extra state is not read at all: the declaration engine fixes
    the model configuration and leaves ``extra`` at Pydantic's own default, so a
    declared value never carries any.
    """
    if not isinstance(other, BaseModel):
        return NotImplemented
    if type(other) is not type(value):
        return False
    if getattr(value, "__pydantic_private__", None) != getattr(other, "__pydantic_private__", None):
        return False
    return declared(value) == declared(other)


def hashed(value: BaseModel) -> int:
    """``value``'s hash over its declared members, in Pydantic field order.

    Both backings reach the same tuple, which is what keeps a published value and
    its ordinary twin — equal by :func:`equal` — hashing alike.
    """
    return hash(tuple(declared(value).values()))


def repr_args(value: BaseModel) -> Generator[tuple[str, object]]:
    """``value``'s repr arguments: declared members, then computed fields.

    Answering Pydantic's own ``__repr_args__`` seam rather than ``__repr__``
    leaves ``repr``, ``str``, and the pretty and rich renderings built on it in
    one place and identical across backings. Computed fields are rendered first
    so a ``cached_property`` among them cannot resize the instance dictionary
    while the declared half is being read, which is the ordering Pydantic's own
    implementation adopts for the same reason.
    """
    computed = [
        (py_name, getattr(value, py_name))
        for py_name, field in value.__pydantic_computed_fields__.items()
        if field.repr
    ]
    fields = value.__pydantic_fields__
    for py_name, member in declared(value).items():
        field = fields.get(py_name)
        if field is not None and field.repr:
            yield py_name, (value.__repr_recursion__(member) if member is value else member)
    yield from computed


def iterate(value: BaseModel) -> Generator[tuple[str, object]]:
    """``value``'s declared members, which is the whole of what ``dict(value)`` is.

    Pydantic's inherited iteration walks the instance dictionary and filters only
    underscored names, so an Entity's relationship positions and unloaded
    sentinels ride along with it by accident. Both backings answer with declared
    members alone, so what a conversion exposes is the same fact the model
    declares rather than whatever the backing happened to hold.
    """
    yield from declared(value).items()


# --------------------------------------------------------------------------- #
# The two Pydantic schema seams
# --------------------------------------------------------------------------- #


def serialization_schema(source: type, schema: cs.CoreSchema) -> cs.CoreSchema:
    """``schema`` with a serialization that reads members as attributes.

    Pydantic's compiled model serializer sources declared fields from the
    instance dictionary and computed fields by attribute, so the fields are
    restated as computed ones and pydantic-core reaches each value through its
    descriptor — which answers from the published tuple, or is shadowed by the
    instance dictionary on an ordinary value. One schema then serves both
    backings, so serialization never branches and a caller who never holds a
    published value sees the same output it always did.

    An authored model serializer is composed with rather than fought: a plain one
    already receives the value itself and is left alone, a wrap one has its inner
    schema retargeted so the handler it delegates to reads attributes too, and a
    class authoring neither gets this as its serialization.

    Two documented options answer with an empty mapping under this schema, on
    either backing: ``round_trip`` and ``exclude_computed_fields``, both of which
    pydantic-core skips computed fields for on the ground that a computed field
    cannot be validated back. What that costs and what the alternatives cost is
    recorded at :func:`_by_attribute`.
    """
    model = cast("dict[str, Any]", schema)
    if model.get("type") != "model":
        return schema
    authored = cast("dict[str, Any] | None", model.get("serialization"))
    if authored is not None and authored.get("type") != "function-wrap":
        return schema
    by_attribute = _by_attribute(source, cast("dict[str, Any]", model["schema"]))
    if authored is None:
        model["serialization"] = by_attribute
    else:
        authored["schema"] = by_attribute
    return schema


def json_schema_of(schema: cs.CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
    """JSON Schema generated from ``schema`` with its serialization set aside.

    A serialization-mode JSON Schema is derived from whatever the core schema
    says serialization is, so the computed-field restatement above would widen
    every declared member to required and read-only. Dropping the key before
    delegating leaves both modes generated from the untouched validation schema,
    which is what keeps the published output identical to an unhooked class's.
    """
    if schema.get("type") == "model" and "serialization" in schema:
        schema = cast(
            "cs.CoreSchema",
            {key: item for key, item in schema.items() if key != "serialization"},
        )
    return handler(schema)


def _by_attribute(source: type, fields_schema: dict[str, Any]) -> cs.SerSchema:
    """The serialization schema that reads ``source``'s members as attributes.

    Every declared field is restated as a computed field, because computed fields
    are what pydantic-core reaches by attribute, and the field half is emptied so
    nothing reads the instance dictionary. One schema then serves both backings:
    on an ordinary value each descriptor is shadowed by the dictionary and answers
    the same value it always did, and on a published one it answers from the row.

    Leaving the field half populated as well was measured and rejected. It would
    answer ``round_trip`` and ``exclude_computed_fields`` — the two options
    pydantic-core skips computed fields for — from the instance dictionary, and so
    keep those two working on ordinary backing. What it costs is worse than what
    it buys: it makes those two options the one place compact and ordinary
    backing disagree, and it makes a published value warn
    ``PydanticSerializationUnexpectedValue`` inside a union serializer, which
    reads the field count against an empty instance dictionary. It also emits
    every key twice, which a Python mapping collapses and a JSON writer does not,
    so it depends on a wrap serializer standing between the two — and confining
    that wrap to JSON with ``when_used`` is not available either: pydantic-core
    falls back to INFERENCE in Python mode when a ``when_used`` function does not
    apply, which loses ``include``, ``exclude``, and ``serialize_as_any``
    outright.
    """
    fields = cast("dict[str, dict[str, Any]]", fields_schema["fields"])
    computed: list[cs.ComputedField] = []
    filtered: list[tuple[str, object]] = []
    for py_name, field in fields.items():
        computed.append(cs.computed_field(py_name, cast("cs.CoreSchema", field["schema"])))
        filtered.append((py_name, _excludable_default(field)))
    computed.extend(cast("list[cs.ComputedField]", fields_schema.get("computed_fields") or ()))
    by_attribute: cs.SerSchema = cs.model_ser_schema(
        source,
        cs.model_fields_schema(
            {},
            model_name=cast("str | None", fields_schema.get("model_name")),
            computed_fields=computed,
        ),
    )
    return cs.wrap_serializer_function_ser_schema(
        _presence_filter(tuple(filtered)),
        schema=cast("cs.CoreSchema", by_attribute),
        info_arg=True,
    )


_NO_DEFAULT: Final = object()
"""Marks a field ``exclude_defaults`` never drops, whatever its value.

A required field has no default to match. A field carrying its own serialization —
an authored ``@field_serializer`` — is not dropped either, because what
pydantic-core compares against the default is what that serializer produced, which
is not the default however the raw value compares.
"""


def _excludable_default(field: dict[str, Any]) -> object:
    """The default ``exclude_defaults`` measures ``field`` against, or :data:`_NO_DEFAULT`."""
    schema = cast("dict[str, Any]", field["schema"])
    if schema.get("type") != "default" or "serialization" in schema:
        return _NO_DEFAULT
    return schema.get("default", _NO_DEFAULT)


def _presence_filter(
    fields: tuple[tuple[str, object], ...],
) -> cs.WrapSerializerFunction:
    """Apply ``exclude_unset`` and ``exclude_defaults``, which a computed field has
    no notion of.

    The plan is resolved from the value when the filter runs rather than captured
    when the schema is built, and that is required rather than stylistic: with
    polymorphic serialization off, a subtype dumped through a base's
    ``TypeAdapter`` is serialized by the BASE's schema, so a filter holding the
    base's bits would test them against the subtype's row — while its BITS are
    always there to test, because ancestry contributes attributes root-first. The
    field list and the defaults ARE captured, because they are the ones the schema
    doing the serializing declared, which is what decides the keys in the result.

    The keys are member names rather than aliases, and every declared member has
    one: the declaration grammar produces a plain Pydantic field per member and
    spells no serialization alias, no ``Field(exclude=...)``, and no conditional
    exclusion, so the schema above restates exactly the members it was given.

    It is installed on every class rather than only on one with a defaulted field.
    A class whose members are all required can still be handed a fields-set a
    caller built, and one rule over every class is what keeps what a dump answers
    a property of the value rather than of which members its class happens to
    declare optional.
    """

    def presence(value: object, handler: Any, info: Any) -> Any:
        result = handler(value)
        if not (info.exclude_unset or info.exclude_defaults):
            return result
        bits = plan_of(type(value)).bits
        for py_name, default in fields:
            if py_name not in result:
                continue
            if (info.exclude_unset and not is_present(cast("BaseModel", value), bits[py_name])) or (
                info.exclude_defaults
                and default is not _NO_DEFAULT
                and getattr(value, py_name) == default
            ):
                del result[py_name]
        return result

    return cast("cs.WrapSerializerFunction", presence)
