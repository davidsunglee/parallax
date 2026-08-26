"""The backing beneath a published value, and every question that reads it.

A published Entity or Value Object holds its declared members in one immutable
tuple on a dedicated slot instead of in Pydantic's instance dictionary. That is a
second backing, and without one Module owning it the compact-versus-ordinary
branch would appear at every descriptor, at edit, at row derivation, at pickle,
and inside Pydantic's own equality, repr, iteration, and compiled serializer. So
the representation lives here alone: the per-class publication plan, the slot,
the tuple and its presence bitmap, both Adapters, and the framework root that
answers Pydantic for a value's instance state. Delete this Module and the layout
reappears at each of those sites.

**Pydantic reads instance state by name, never through the struct pointer.** Its
compiled serializer reaches ``__dict__``, ``__pydantic_fields_set__``, and
``__pydantic_extra__`` as interned attribute names, and so does its validator. So
a data descriptor bound under those names on a shared framework root decides what
Pydantic sees, and a published value can present its row as the instance
dictionary Pydantic believes it is reading — without the row ever becoming one.
Everything Pydantic implements over that dictionary is then correct again by
construction rather than by restatement: equality, hashing, repr, the compiled
serializer, and every documented serialization option, including the ones no
reimplementation of the model schema can reach.

**What the seam costs is part of what it offers.** A published value retains
roughly a fifth of what an ordinary one does — one tuple and two pointers
against a dictionary and a name-keyed set — and pays for that every time
Pydantic reads its state. The compiled serializer reaches ``__dict__`` twice per
instance per dump and each read builds a mapping, so serializing a published
value runs about twice an ordinary one and about three times a plain
``BaseModel`` of the same fields, and equality comparably. Ordinary values pay
none of it: their reads reach Pydantic's own slot descriptor and answer with the
storage itself, and an ordinary attribute read is a plain model's. That is a
settled trade rather than an unfinished one — :class:`_DeclaredState` states why
the cache that would flatten it is forbidden.

Only three questions vary by backing — what a declared member holds, whether the
read carried it (:func:`is_present`), and what a relationship position holds
(:func:`relationship`). Everything else needs declared values and, at most,
presence, so it is written once over both.

Which way a question is asked is part of that. A caller reading one member's
presence asks :func:`is_present`, which tests one bit and allocates nothing; the
populated-member set a published value has no room for is synthesized only where
a caller asks the value itself for it, and by :func:`carry_presence`, whose
product is ordinary backing and has nowhere else to keep presence. Deriving a
copy is likewise the backing's own question, because the answer is always the
same one (:func:`restated`): a copy built out of semantic state is ordinary,
whichever backing it came from.

The scope is sealed and granted two siblings: the sentinels a construction input
spells, and the seam that reaches a value's real storage past every name a class
body can bind. It therefore reaches neither the declaration engine that builds a
class nor the writer that publishes one, which is what forces a publication plan
to arrive as plain data its owner computed. What it does read of a class is the
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

import copy
import functools
import operator
from dataclasses import dataclass
from types import MappingProxyType, MemberDescriptorType
from typing import TYPE_CHECKING, Any, Final, cast

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from parallax.core.entity._construction_input import UNLOADED
from parallax.core.entity._pydantic_storage import (
    MODEL_PRESENCE,
    MODEL_STORAGE,
    instance_presence,
    instance_state,
    replace_instance_presence,
    replace_instance_state,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping

__all__ = [
    "AUXILIARY_STATE_SLOT",
    "COMPACT_STATE_SLOT",
    "BackedModel",
    "PublicationPlan",
    "allocate",
    "auxiliary",
    "carry_presence",
    "carry_slots_beside_state",
    "declared",
    "install",
    "is_present",
    "is_published",
    "iterate",
    "named_state",
    "plan_of",
    "publish",
    "relationship",
    "restated",
]

COMPACT_STATE_SLOT: Final = "__parallax_compact__"
"""The one slot a published value's whole declared state occupies.

It holds a single immutable tuple — presence bitmap, then every declared member
in the class's own model-fixed order, then, on an Entity, one position per
declared broad relationship. A value that has never been published carries
``None`` or nothing at all here, and that absence IS the Adapter selection:
nothing branches on a flag, because there is no flag to read.
"""

AUXILIARY_STATE_SLOT: Final = "__parallax_auxiliary__"
"""Where a published value's author-owned dynamic state goes instead.

A ``functools.cached_property`` memoizes by writing into what it was handed as
the instance dictionary, and what a published value hands it is a presentation
rather than its storage — so the write would evaporate and the property would
recompute forever with no signal. The presentation forwards that write here and
is seeded from here, which is what makes the memoization correct while leaving
the value's real storage empty. Allocated on the first such write and never
before, so a published value of a class that declares no auxiliary state carries
one null pointer and nothing else.
"""

_PLAN_ATTRIBUTE: Final = "__parallax_plan__"
"""Where a class carries its own publication plan.

Stamped per exact declared class rather than resolved through the MRO, because a
descendant's occurrence and relationship positions sit after its own attribute
count and so are not its ancestor's.
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
    walk nothing.

    A member the class declares required has no declared default to hold, and its
    position holds ``None``. That is not a value the member admits; it is what a
    position a read did not carry reads back as, with its presence bit clear, so
    ``model_fields_set`` and ``exclude_unset`` still tell the two apart. A read is
    entitled to carry no value there — a required position the stored data left
    absent is a recorded finding on the projection rather than a refusal — so
    publication invents nothing for it and refuses nothing over it."""
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
    field_values: Callable[[tuple[object, ...]], tuple[object, ...]]
    """One row's declared members, permuted into :attr:`fields` order in a single
    call.

    Key order is a contract rather than an implementation note: Pydantic emits a
    model's keys in the order the mapping it read them from was built, not in
    schema order. The row is in model-fixed order, which a class declaring an
    occurrence between two attributes makes differ from field order, so the
    permutation is prebuilt here rather than walked per value."""
    occurrences: Mapping[int, type]
    """Tuple index to the Value Object class that position takes."""
    relationships: Mapping[str, int]
    """Each declared broad relationship's absolute tuple index in the tail."""
    has_auxiliary: bool
    """Whether the class declares a ``cached_property`` or a ``PrivateAttr``, and so
    whether a published value can carry state outside its tuple at all.

    A presentation is seeded from the auxiliary slot only where this holds, which
    is what keeps every other class's presentation one row read and one mapping —
    so it decides a write as well as a read: author-owned state written through a
    published value of a class declaring none is refused, because the slot it
    would land in is one no presentation of that class ever consults."""


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
    row: list[object] = [0]
    for py_name in members:
        field = fields[py_name]
        row.append(None if field.is_required() else field.get_default(call_default_factory=True))
    row.extend(UNLOADED for _ in relationships)
    plan = PublicationPlan(
        template=tuple(row),
        bits=MappingProxyType(bits),
        indexes=MappingProxyType(indexes),
        py_names=members,
        fields=tuple(fields),
        field_values=_permutation(tuple(indexes[py_name] for py_name in fields)),
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


def _permutation(indexes: tuple[int, ...]) -> Callable[[tuple[object, ...]], tuple[object, ...]]:
    """One C call that reads ``indexes`` out of a row, in that order.

    ``operator.itemgetter`` answers a bare value rather than a one-tuple for a
    single index and refuses to be built with none at all, so the two degenerate
    widths are spelled out instead of special-cased at every call site.
    """
    if not indexes:
        return lambda _row: ()
    if len(indexes) == 1:
        only = indexes[0]
        return lambda row: (row[only],)
    return cast("Callable[[tuple[object, ...]], tuple[object, ...]]", operator.itemgetter(*indexes))


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
# The instance state Pydantic reads, and the root that answers for it
# --------------------------------------------------------------------------- #


class _PresentedState(dict[str, Any]):
    """One published value's row, presented as the mapping Pydantic reads.

    Built per read and discarded with it: nothing here is the value's storage,
    and the row it was derived from is never reached through it. A mutation is
    the one thing that has to outlive the mapping — ``functools.cached_property``
    memoizes by assigning into what it was handed — so EVERY mutating operation
    ``dict`` defines is answered here rather than only item assignment. Left
    inherited, ``update``, ``setdefault``, ``|=``, ``pop``, ``popitem``,
    ``clear``, and ``__init__`` — which ``dict`` defines as the update of an
    existing mapping — would each write the temporary at C speed and vanish with
    it, which is the one outcome this seam may not have.

    Each ends one of three ways. A key the row holds — a declared member, or a
    relationship position the presentation does not even carry — is part of a row
    attached once, which no mapping operation can shadow or remove without
    splitting the value between what an attribute read answers and what a dump
    emits, so those refuse. Any other key is author-owned state, and it lands in
    the value's auxiliary slot, which the next presentation is seeded from — on a
    class that declares such state. On a class that declares none, no presentation
    is ever seeded from that slot, so a write there would be exactly the
    disappearance this seam may not have, and it refuses too.

    The initializer is answered as the update it is, and :class:`_DeclaredState`
    builds a presentation without entering it: every read of a published value's
    state builds one of these, so what a build costs is ``dict``'s own
    initializer and one slot write rather than a Python frame. That bypass is
    what leaves the initializer free to answer a caller rather than a build.

    Every parameter answered here is positional-only, because the C methods these
    stand in for have no other kind: a keyword reaching one of them is a data key
    or an error, never a parameter name. Spelling one keyword-bindable would make
    the presentation refuse ``state.__init__(self=7)``, which ``dict`` stores, or
    accept ``state |= ...`` spelled with a keyword, which ``dict`` rejects — a
    different mapping either way rather than a stricter one.
    """

    __slots__ = ("_value",)

    def __init__(self, /, *state: Any, **members: Any) -> None:
        self.update(*state, **members)

    def __setitem__(self, key: str, item: Any, /) -> None:
        if self._row_holds(key):
            raise TypeError(self._row_position(key))
        if not plan_of(type(self._value)).has_auxiliary:
            raise TypeError(self._undeclared_state(key))
        auxiliary(self._value)[key] = item
        super().__setitem__(key, item)

    def setdefault(self, key: str, default: Any = None, /) -> Any:
        if key in self:
            return self[key]
        self[key] = default
        return default

    def update(self, /, *state: Any, **members: Any) -> None:
        for key, item in dict(*state, **members).items():
            self[key] = item

    def __ior__(self, state: Any, /) -> _PresentedState:
        self.update(state)
        return self

    def __delitem__(self, key: str, /) -> None:
        del self._warmed(key)[key]
        super().__delitem__(key)

    def pop(self, key: str, /, *default: Any) -> Any:
        if len(default) > 1:
            raise TypeError(f"pop expected at most 2 arguments, got {1 + len(default)}")
        if default and key not in self:
            return default[0]
        item = self[key]
        del self[key]
        return item

    def popitem(self, /) -> tuple[str, Any]:
        if not self:
            return super().popitem()
        key = next(reversed(self))
        item = self[key]
        del self[key]
        return key, item

    def clear(self, /) -> None:
        for key in self:
            self._warmed(key)
        warmed = _auxiliary(self._value)
        if warmed is not None:
            warmed.clear()
        super().clear()

    def _warmed(self, key: str) -> dict[str, Any]:
        """The auxiliary state holding ``key``, for an operation about to drop it."""
        warmed = _auxiliary(self._value)
        if warmed is not None and key in warmed:
            return warmed
        if self._row_holds(key):
            raise TypeError(self._row_position(key))
        raise KeyError(key)

    def _row_holds(self, key: str) -> bool:
        """Whether ``key`` names a position the value's row itself carries.

        A declared member is one and so is a relationship, which the presentation
        does not carry at all — so this asks the plan rather than the mapping,
        which is what reaches the tail a presented key set would miss.
        """
        plan = plan_of(type(self._value))
        return key in plan.indexes or key in plan.relationships

    def _row_position(self, key: str) -> str:
        return (
            f"{type(self._value).__name__}.{key} is a position in a published row, "
            "which is attached once and cannot be rewritten or dropped through the mapping "
            "presenting it; derive a value that differs with edit(...)"
        )

    def _undeclared_state(self, key: str) -> str:
        return (
            f"{type(self._value).__name__}.{key} is dynamic state a published value of this "
            "class carries nowhere: the class declares no `functools.cached_property` and no "
            "`PrivateAttr`, so nothing seeds a presentation of it from the auxiliary slot and "
            "the write would vanish with the mapping it landed in; declare the slot on the "
            "class as a `functools.cached_property`, which a presentation is seeded from"
        )

    def __reduce__(self) -> tuple[Any, ...]:
        """Copied and pickled as the plain mapping it presents.

        Whatever reaches a value's state through ``__dict__`` and carries it
        somewhere — ``BaseModel.__getstate__`` is the one that does — is carrying
        declared values, not a presentation of a value it will no longer be
        beside. Reducing as ``dict`` says exactly that, and keeps the default
        reduction of a ``dict`` subclass, which rebuilds by item assignment,
        from writing into an auxiliary slot on the way out.
        """
        return (dict, (dict(self),))


class _DeclaredState:
    """What a value answers for ``__dict__``, under either backing.

    Pydantic reaches instance state by this name and not through the struct
    pointer, so binding here is what lets a published value present its row as
    the instance dictionary every Pydantic implementation over that dictionary
    believes it is reading. Ordinary backing answers with the storage ITSELF
    rather than a copy of it, because a caller that writes through it — a
    relationship an ordinary read loaded, a Change Record, a ``cached_property``
    — has to reach the value.

    A published value's presentation is built per read and MUST NOT be memoized
    on the value. Caching it is the obvious way to pay the build once rather than
    twice per dump, and it is forbidden: a mapping held from the first dump
    onward is a per-node retained dictionary, which is the whole of what this
    backing exists to remove, reintroduced on exactly the values that removed it.
    What may be optimized is the build — it is spelled here rather than behind a
    function of its own, it enters no Python frame of the presentation's, the
    auxiliary read is gated on a class fact, and the ordinary branch reaches the
    slot descriptor rather than a function over it.

    Assignment is where a published value stops being one. Every write Pydantic
    makes to a model's state is a wholesale assignment of this name, and the
    paths that make it — validation, ``model_construct``, ``__setstate__`` — are
    each producing an ordinary value out of semantic state. Landing that write in
    the real storage and clearing the row is what makes them do exactly that,
    rather than split the value between a row nothing wrote and storage nothing
    reads.

    Class access is never answered here and no branch spells one: ``Cls.__dict__``
    resolves the name through the METAtype, where ``type``'s own descriptor for a
    class namespace wins, so this one is reached with an instance or not at all.
    """

    __slots__ = ()

    def __get__(self, value: BaseModel, owner: type | None = None) -> Any:
        try:
            row = _CompactState.__get__(value)
        except AttributeError:
            row = None
        if row is None:
            return MODEL_STORAGE.__get__(value)
        plan = plan_of(type(value))
        members: Any = zip(plan.fields, plan.field_values(row), strict=True)
        if plan.has_auxiliary:
            warmed = _auxiliary(value)
            if warmed:
                members = [*members, *warmed.items()]
        presented = _PresentedState.__new__(_PresentedState)
        _PresentedOwner.__set__(presented, value)
        _PresentedRow(presented, members)
        return presented

    def __set__(self, value: BaseModel, state: dict[str, Any]) -> None:
        _CompactState.__set__(value, None)
        replace_instance_state(value, state)


class _PopulatedMembers:
    """What a value answers for ``__pydantic_fields_set__``, under either backing.

    A published value keeps no ``set[str]``: the same bitmap ``exclude_unset``
    reads answers this one, synthesized fresh per request and never memoized, so
    the mutable result a caller receives changes neither compact presence nor a
    later dump. Ordinary backing answers with the set it holds, as Pydantic's own
    slot always did.

    Assignment writes the value's own set and deliberately does NOT clear the
    row: the two writes always arrive together, and it is the ``__dict__`` half
    that decides which backing a value ends up with.

    Class access IS reachable here, unlike its sibling above: no metatype answers
    for this name, and Pydantic's own ``__getattr__`` asks ``hasattr`` of the
    class before it re-raises. Answering with the descriptor is what makes that
    question true and lets the instance read raise on its own terms.
    """

    __slots__ = ()

    def __get__(self, value: BaseModel | None, owner: type | None = None) -> Any:
        if value is None:
            return self
        try:
            row = _CompactState.__get__(value)
        except AttributeError:
            row = None
        if row is None:
            return MODEL_PRESENCE.__get__(value)
        bitmap = cast("int", row[0])
        return {
            py_name
            for bit, py_name in enumerate(plan_of(type(value)).py_names)
            if bitmap >> bit & 1
        }

    def __set__(self, value: BaseModel, populated: set[str]) -> None:
        replace_instance_presence(value, populated)


if TYPE_CHECKING:
    BackedModel = BaseModel
    """What a type checker sees of the root below: the Pydantic base it adds
    nothing typed to.

    The root exists to bind two names whose declared types no descriptor can
    satisfy — a ``__dict__`` is a final ``MappingProxyType`` and a
    populated-member set is a ``set[str]``, and what is bound answers with
    exactly those at runtime while being neither — and to declare two slots,
    which carry no type at all. What it overrides beyond them, Pydantic's own
    base already declares with the same signature.

    It is aliased rather than merely narrowed because a Pydantic model class
    standing between ``BaseModel`` and a class with a metaclass of its own stops
    Pyright synthesizing the constructor its ``@dataclass_transform`` promises,
    for every declared class in the repository. Hiding a root that adds no typed
    surface costs nothing and is the whole of the workaround.
    """
else:

    class BackedModel(BaseModel):
        """The Pydantic root beneath both framework roots, and the whole of the seam.

        An Entity Class and a Value Object Class each extend a framework root
        that extends this, so one pair of descriptors decides what Pydantic reads
        of every declared value — and one pair of slots gives both kinds the same
        backing, so no read has to ask what shape a value is. A framework root
        below this one may add a slot of its own for state only its kind can hold
        (``Entity`` does, for lifecycle state); what this root fixes is the
        backing every declared value shares, not the whole object layout.

        Nothing else belongs here. What a declared class IS remains its own
        root's; this is the one place a value's physical state is answered for.
        """

        __slots__ = (AUXILIARY_STATE_SLOT, COMPACT_STATE_SLOT)

        __dict__ = _DeclaredState()
        __pydantic_fields_set__ = _PopulatedMembers()

        def __iter__(self):
            """Declared members alone, which is the whole of what ``dict(value)`` is.

            Pydantic's inherited iteration walks instance state and filters only
            underscored names, so an Entity's relationship positions and unloaded
            sentinels would ride along with it. Its own signature is the one
            declared on ``BaseModel``.
            """
            return iterate(self)


_PresentedOwner: Final = _PresentedState.__dict__["_value"]
"""The presentation's own owner slot, written without a Python frame."""

_PresentedRow: Final = cast("Callable[[_PresentedState, Any], None]", dict.__dict__["__init__"])
"""``dict``'s own initializer, which fills a presentation without entering the
override that answers a caller re-initializing one as the write it is."""


_CompactState: Final = cast("Any", BackedModel).__dict__[COMPACT_STATE_SLOT]
"""The compact slot's own descriptor, reached without a name lookup."""

_AuxiliaryState: Final = cast("Any", BackedModel).__dict__[AUXILIARY_STATE_SLOT]
"""The auxiliary slot's own descriptor, likewise."""

_PopulatedState: Final = cast("Any", BackedModel).__dict__["__pydantic_fields_set__"]
"""The populated-member descriptor itself, so a framework read of a value's
presence reaches the same answer Pydantic does without resolving the name through
a class that may answer for it."""


# --------------------------------------------------------------------------- #
# The two Adapters, and the three questions that vary
# --------------------------------------------------------------------------- #


def _compact(value: BaseModel) -> tuple[object, ...] | None:
    """``value``'s published row, or ``None`` when it carries ordinary backing.

    The slot is unset on a value no construction path ever assigned state to and
    ``None`` on one that de-published, and neither is a row — which is the whole
    of the Adapter selection. There is no flag, because there is nothing a flag
    would say that the row does not.
    """
    try:
        return cast("tuple[object, ...] | None", _CompactState.__get__(value))
    except AttributeError:
        return None


def _auxiliary(value: BaseModel) -> dict[str, Any] | None:
    """``value``'s warmed author-owned state, or ``None`` while it has none.

    Read only where the class declares state that could be there
    (:attr:`PublicationPlan.has_auxiliary`), which is what keeps the presentation
    of every other class one row read and one mapping.
    """
    try:
        return cast("dict[str, Any] | None", _AuxiliaryState.__get__(value))
    except AttributeError:
        return None


def auxiliary(value: BaseModel) -> dict[str, Any]:
    """``value``'s warmed author-owned state, allocated if this is the first."""
    warmed = _auxiliary(value)
    if warmed is None:
        warmed = {}
        _AuxiliaryState.__set__(value, warmed)
    return warmed


def is_published(value: object) -> bool:
    """Whether ``value``'s declared state is a published row."""
    return isinstance(value, BackedModel) and _compact(value) is not None


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
        state = instance_state(value)
        return {py_name: state[py_name] for py_name in plan.fields if py_name in state}
    return dict(zip(plan.fields, plan.field_values(row), strict=True))


def named_state(value: BaseModel) -> Mapping[str, object]:
    """Everything ``value`` holds under a name, reached without creating storage.

    An ordinary value keeps its declared members and every framework name beside
    them in one instance dictionary, and that dictionary itself is the answer: a
    caller partitioning it, or reading one name out of it, is reading the value.
    State a framework root holds in a real slot is not under a name and so is not
    here — the lifecycle slot is carried by its own owner, not by a caller of
    this. A published value keeps its declared members in its row and holds no instance
    dictionary at all, so the answer is derived from the row — asking the storage
    would CREATE the dictionary publication exists to do without, permanently,
    on a path that only meant to read. A relationship the read loaded is named
    here too, under the name ordinary backing files it in storage under, so a
    copy derived from either backing carries the same loaded tails forward; an
    unloaded position names nothing, exactly as a dictionary that was never
    written names nothing. The value's author-owned state is named last and for
    the same reason: a published value holds it in the auxiliary slot rather than
    beside its declared members, and a caller preserving everything it did not
    replace has to see it there or drop what ordinary backing would have kept.

    So this is what a framework read of a value's whole name-keyed state goes
    through, and :func:`~parallax.core.entity._pydantic_storage.instance_state`
    is left to the callers that mean the storage itself.
    """
    row = _compact(value)
    if row is None:
        return instance_state(value)
    plan = plan_of(type(value))
    state: dict[str, object] = dict(zip(plan.fields, plan.field_values(row), strict=True))
    state.update(
        (py_name, related)
        for py_name, index in plan.relationships.items()
        if (related := row[index]) is not UNLOADED
    )
    warmed = _auxiliary(value)
    if warmed:
        state.update(warmed)
    return state


def is_present(value: BaseModel, bit: int) -> bool:
    """Whether the read that produced ``value`` carried the member at ``bit``.

    Allocation-free, and the only presence question internal code has: row and
    document derivation iterate declared members anyway, so a per-member
    predicate is proportional and never synthesizes a set.
    """
    row = _compact(value)
    if row is None:
        return plan_of(type(value)).py_names[bit] in instance_presence(value)
    return bool(cast("int", row[0]) >> bit & 1)


# --------------------------------------------------------------------------- #
# One implementation over both
# --------------------------------------------------------------------------- #


def allocate(cls: type[Any]) -> Any:
    """An unpopulated publication shell of ``cls``.

    Neither the ordinary constructor nor ``model_construct`` is entered: a shell
    exists so a relationship can name it before it holds anything, and it holds
    nothing until :func:`publish` attaches its row. What it is given here is only
    the Pydantic storage a shell cannot be missing — the extra slot every read of
    the value consults, and the private state an author's own ``PrivateAttr``
    declares, initialized to its declared defaults exactly as validation-free
    construction would have initialized it. It is given no populated-member set
    at all: the bitmap answers that question, so a published value retains no
    name-keyed presence state of any kind.
    """
    instance = cast("Any", cls).__new__(cls)
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


_REBUILT_STATE_SLOTS: Final = frozenset(
    {"__dict__", "__pydantic_fields_set__", COMPACT_STATE_SLOT, AUXILIARY_STATE_SLOT}
)
"""The four slots a copy derived from semantic state rebuilds instead of carrying.

They are not the slots that hold a value's state — the private-attribute mapping
holds state too. They are the four whose content a copy derives rather than
takes.

Two are Pydantic's own, and a copy fills them with the declared members and the
populated-member set it was derived from. Two are this Module's, and a copy fills
neither: it is built ordinary, so the compact row a published source holds is not
its to inherit — carrying it would leave a value claiming both backings at once —
and the author-owned state that source keeps in the auxiliary slot has already
been read out under its own names by :func:`named_state` and lands in the copy's
instance dictionary beside everything else it carries.
"""

_CARRIED_SLOTS: Final[tuple[MemberDescriptorType, ...]] = tuple(
    descriptor
    for ancestor in BackedModel.__mro__
    for name, descriptor in vars(ancestor).items()
    if isinstance(descriptor, MemberDescriptorType) and name not in _REBUILT_STATE_SLOTS
)
"""Every other slot of a declared value's layout, which a copy carries.

Today that is ``__pydantic_extra__`` and ``__pydantic_private__``: the two
name-keyed mappings Pydantic lays out beside the instance dictionary, both of
which stay live once a copy exists. Assigning a private attribute or an extra
field on the copy writes into whichever mapping the copy's slot points at, so a
copy sharing the source's mapping would write the source's state — each is
therefore carried as the copy's own shallow copy, exactly as Pydantic's own copy
of a model gives it one, while what a container holds under a key stays shared.

Resolved once off the shared backing root rather than per concrete class, and so
it reaches exactly the slots that root's own layout declares. A declaration may
not extend a foreign base (``entity-base-invalid``) and may not declare
``__slots__`` of its own (``entity-reserved-member-name``), so no CONCRETE class
adds a slot; what can is a framework root between a concrete class and this one.
``Entity`` does, for its lifecycle state, which is why that slot is carried by
``_entity.carry_lifecycle_state`` rather than here — its payload is opaque and
would be wrong to shallow-copy, so it is classified rather than swept up.

This is therefore a complement over a FIXED root layout rather than over the
layout a value really has, and a framework slot added below this root would go
uncarried. What holds the classification exact is graded rather than argued:
``test_a_declared_class_lays_out_no_slot_of_its_own`` and
``test_an_edit_carries_every_slot_of_the_layout_it_does_not_rebuild`` walk a
concrete class's whole MRO and fail on a slot neither bucket names.

It is a complement rather than those two names so that a slot a Pydantic release
adds is carried rather than silently dropped. Such a release would take the
shallow copy above without having said it wants one;
``test_the_framework_lays_out_exactly_the_slots_the_carry_classifies`` fails
there, where the classification is stated.
"""


def carry_slots_beside_state(source: BaseModel, target: BaseModel) -> None:
    """Give ``target`` its own of every container the shared backing root holds.

    A copy derived from a value rebuilds the four slots above out of semantic
    state, and :data:`_CARRIED_SLOTS` is the rest of that root's layout — not the
    rest of the layout a concrete value has, which a framework root below it may
    have added to. Private
    attributes are the state that reaches: Pydantic keeps a ``PrivateAttr`` in a
    slot of its own rather than in the instance dictionary, so a copy assembled
    out of a name-keyed mapping alone silently resets every one of them to the
    declared defaults a fresh instance starts with.

    The copy's mapping is its own and is shallow, so rebinding a private
    attribute through either value leaves the other's binding alone while
    everything inside that mapping stays shared — appending to a list a
    ``PrivateAttr`` holds is visible through both.
    """
    for slot in _CARRIED_SLOTS:
        slot.__set__(target, copy.copy(slot.__get__(source)))


def carry_presence(source: BaseModel, target: BaseModel, authored: Iterable[str] = ()) -> None:
    """Give ``target`` the members ``source`` reports populated, plus ``authored``.

    A value derived from another carries the source's presence forward exactly —
    a member the source never populated stays unpopulated on the copy, which is
    what keeps it absent from a document and out of a narrow insert rather than
    becoming an explicit null. Where the source keeps that fact differs by
    backing, and both answers are read here: an ordinary value holds a
    ``set[str]``, a published one holds the bitmap the set is synthesized from.

    This is the ONE caller that needs the whole set, and it needs it because what
    it builds is ordinary backing, which has nowhere else to keep presence. Every
    internal question about whether a member was carried is :func:`is_present`,
    one member at a time and allocation-free, so no read path synthesizes a set
    to answer one.
    """
    replace_instance_presence(target, set(_PopulatedState.__get__(source)) | set(authored))


def restated[M: BaseModel](value: M, state: dict[str, object]) -> M:
    """A fresh ordinary value of ``value``'s class holding exactly ``state``.

    A copy derived from semantic state rather than from a backing, which is why
    it lives here: it is the one operation that decides what backing a derived
    value ends up with, and the answer is always ordinary. A published source's
    row is not the copy's to inherit — carrying it would leave a value claiming
    both backings at once — and ``state`` already carries everything that row and
    the source's auxiliary slot named, so the copy holds neither of this Module's
    two slots.

    It builds through the validation-free construction path, which is what an
    edit that authored nothing has to use: nothing was authored, so there is
    nothing to validate, and every inherited copy door is refused. ``state``
    lands in the copy's own storage through Pydantic's own slot descriptor, so no
    name a class body binds decides what the copy ends up holding.
    :func:`carry_presence` gives it the source's presence and
    :func:`carry_slots_beside_state` the rest of the shared backing root's
    layout, without which every ``PrivateAttr`` would silently reset to a fresh
    instance's default. A slot a framework root below that one declares is its
    owner's to carry: the caller pairs this with
    :func:`~parallax.core.entity._entity.carry_lifecycle_state`.
    """
    copied = cast("M", cast("Any", type(value)).model_construct())
    replace_instance_state(copied, state)
    carry_presence(value, copied)
    carry_slots_beside_state(value, copied)
    return copied


def relationship(value: BaseModel, py_name: str) -> object:
    """``value``'s raw position for the relationship ``py_name``, sentinel included.

    The one read that distinguishes unloaded from loaded-null without raising,
    and one of the three questions the two backings answer differently: a
    published value holds every declared direction in its row's tail, and an
    ordinary one holds only the loaded ones under their own names in storage, so
    a name that was never written is unloaded there exactly as the sentinel is
    here. A reader arriving with only an instance resolves the position off the
    class's plan, as every such reader does.
    """
    row = _compact(value)
    if row is None:
        return instance_state(value).get(py_name, UNLOADED)
    return row[plan_of(type(value)).relationships[py_name]]


def publish(
    instance: BaseModel,
    values: Mapping[str, object],
    relationships: Mapping[str, object] = MappingProxyType({}),
    *,
    shared_bitmaps: dict[int, int] | None = None,
) -> None:
    """Assemble ``instance``'s complete compact row and attach it, once.

    Attachment is the atomic act of populating the value: the row is built in
    local state and every refusal happens before anything is written, so no
    partially published value exists at any point. A member ``values`` does not
    name keeps whatever :attr:`PublicationPlan.template` holds at its position
    and leaves its presence bit clear.

    ``shared_bitmaps`` is one caller's own memo of the presence masks it has
    already assembled, and its life is that caller's. CPython interns small
    integers, so a mask through ``0b11111111`` is a shared singleton already and
    a wider one allocates; every node of one class in one materialization comes
    from one projection and so repeats one pattern, which the memo turns into one
    shared integer per distinct pattern. Nothing process-wide holds it, so no
    mask outlives the graph whose publication assembled it.
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
    tail = plan.relationships
    for py_name, related in relationships.items():
        index = tail.get(py_name)
        if index is None:
            raise ValueError(f"{type(instance).__name__} declares no relationship {py_name!r}")
        row[index] = related
    row[0] = bitmap if shared_bitmaps is None else shared_bitmaps.setdefault(bitmap, bitmap)
    _CompactState.__set__(instance, tuple(row))


def iterate(value: BaseModel) -> Generator[tuple[str, object]]:
    """``value``'s declared members, which is the whole of what ``dict(value)`` is.

    Pydantic's inherited iteration walks the instance dictionary and filters only
    underscored names, so an Entity's relationship positions and unloaded
    sentinels ride along with it by accident. Both backings answer with declared
    members alone, so what a conversion exposes is the same fact the model
    declares rather than whatever the backing happened to hold.
    """
    yield from declared(value).items()
