from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.internal import inheritance
from parallax.core.internal.base import UsageError, typed_converter
from parallax.core.internal.document_codec._plan import (
    BORROWED_DOCUMENTS,
    MAPPING_DOCUMENTS,
    AuthoringCatalog,
    AuthoringLane,
    AuthoringPlan,
)
from parallax.core.internal.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    KeySequence,
    Metamodel,
    Multiplicity,
    PrimaryKey,
    judge_assignment,
)
from parallax.core.internal.planned_step.managed_row import RowSelection
from parallax.core.internal.wire._codec import wire_converter

__all__ = [
    "TYPED",
    "TYPED_LANE",
    "UNSTATED",
    "WIRE",
    "WIRE_LANE",
    "WRITE_INSTRUCTION_INVALID",
    "CompletePayload",
    "EntityPreparation",
    "KeyAllocation",
    "PartialPayload",
    "StatedMember",
    "TargetRevisionArguments",
    "Unstated",
    "WritePreparation",
    "WriteRepresentation",
    "refuse_observation_keys",
]

WRITE_INSTRUCTION_INVALID: Final = "write-instruction-invalid"

# The framework-owned transaction observation is NOT durable instruction state, so
# these control keys are forbidden on a write row. All THREE that
# `write-instruction.schema.json`'s own `writeRow` forbids: the observed version,
# and BOTH halves of the observed milestone's own edge coordinate. Omitting either
# half would let a row carry a coordinate the instruction cannot mean — the
# milestone a temporal write observes is resolved at flush, never authored.
_FORBIDDEN_ROW_KEYS: Final[frozenset[str]] = frozenset(
    {"observedVersion", "observedTxStart", "observedValidStart"}
)


def refuse_observation_keys(names: Iterable[str]) -> None:
    """Refuse a write row naming a transaction observation control key."""
    forbidden = sorted(_FORBIDDEN_ROW_KEYS.intersection(names))
    if forbidden:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"write row carries forbidden observation control key(s) {forbidden} "
            "(the transaction observation is attached at flush, never on the instruction)",
        )


class Unstated:
    """The type of the marker an optional key argument defaults to when its
    caller states none, so ``None`` stays a stated key."""

    __slots__ = ()


UNSTATED: Final[Unstated] = Unstated()

type StatedMember = tuple[int, object]
"""One member a partial payload states: its position beside its value."""


@dataclass(frozen=True, slots=True)
class CompletePayload:
    """An opening's or a replacement's payload: one value per member, in
    member order, the preparation's ``absent`` where it states none.

    ``values`` is read once, so a one-shot iterator goes in uncopied.
    ``unlisted_names`` are the names its caller stated that the target lists no
    member for, kept so a sibling-branch or derived member is refused as such.
    """

    values: Iterable[object]
    unlisted_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PartialPayload:
    """An amendment's members or a destructive write's identity, in the order
    its caller stated them, the key anywhere among them.

    ``judged_at_edit`` marks members an edit chain already judged as
    assignments; only a Typed edit chain sets it.
    """

    stated: tuple[StatedMember, ...]
    unlisted_names: tuple[str, ...] = ()
    judged_at_edit: bool = False


@dataclass(frozen=True, slots=True)
class WriteRepresentation:
    """Which caller's values a write carries: how they convert, and whether a
    complete payload's framework-owned and replacement-excluded cells are
    ``"carried"`` state the caller never authored or ``"authored"`` by it.

    ``lane`` and ``authoring_lane`` are the codec lane the representation
    converts through; nothing outside preparation names them.
    """

    complete_payload_cells: Literal["carried", "authored"]
    lane: int
    authoring_lane: AuthoringLane


TYPED_LANE: Final = 0
"""The authoring lane of a developer's native carriers."""
WIRE_LANE: Final = 1
"""The authoring lane of serialized Wire literals."""
TYPED: Final = WriteRepresentation(
    "carried", TYPED_LANE, AuthoringLane(typed_converter, BORROWED_DOCUMENTS)
)
WIRE: Final = WriteRepresentation(
    "authored", WIRE_LANE, AuthoringLane(wire_converter, MAPPING_DOCUMENTS)
)
# Each representation's lane index is its position here.
_LANES: Final = (TYPED.authoring_lane, WIRE.authoring_lane)


@dataclass(frozen=True, slots=True)
class TargetRevisionArguments:
    """The revision keywords a caller-conditioned write was handed, unjudged,
    beside the names its caller stated, so preparation can judge presence apart
    from value in its fixed order."""

    if_version: int | None
    if_tx_start: dt.datetime | None
    stated: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KeyAllocation:
    """Where an opening row's omitted key comes from: the key's member
    ``position`` and the logical ``allocator`` its family root declares."""

    position: int
    allocator: str


@dataclass(frozen=True, slots=True)
class EntityPreparation:
    """What every write of one Entity is prepared against.

    ``plan`` walks the Entity's member shape against each lane's converters,
    and ``key_position`` is its primary key's position there. ``insert_required`` marks
    the members an opening row must state with a value, ``framework_owned`` the
    members the framework supplies, which a Typed row never authors, and
    ``read_only`` the members outside the key that are immutable once inserted.
    A replacement must state each member in ``replace_required``, and writes
    one in ``replace_nulled`` it leaves unstated as null.
    ``typed_class`` is the Entity Class whose instances hold their members in
    ``selection``'s order, proven so when the model was prepared, or ``None``
    where no class was. ``key_allocation`` is present exactly for an Entity
    whose family key a :class:`~parallax.core.internal.metamodel.KeySequence`
    generates, whose opening row may therefore omit its key.
    """

    selection: RowSelection
    plan: AuthoringPlan
    key_position: int
    insert_required: int
    framework_owned: int
    read_only: int
    replace_required: int
    replace_nulled: int
    typed_class: type | None
    key_allocation: KeyAllocation | None = None

    def assignment_rules(self, position: int, raw: object) -> None:
        """Judge stating ``raw`` at ``position`` beside the key by the
        assignment rules the member's designation and nullability fix, before
        its value is converted; the key addresses its object and assigns
        nothing.

        Raises the assignment judgement's
        :class:`~parallax.core.internal.base.UsageError`.
        """
        if position != self.key_position:
            judge_assignment(
                self.selection.members.bindings[position],
                raw,
                known_violation=None,
                known_value_valid=True,
            )

    @property
    def key_name(self) -> str:
        return self.selection.members.shape.members[self.key_position].name

    def complete_payload_from_names(
        self, members: Mapping[str, object], *, key: object = UNSTATED
    ) -> CompletePayload:
        """``members``, a name mapping stating a whole state, as a complete
        payload, ``key`` standing for any key ``members`` names where it is
        stated. Judges no value."""
        shape = self.selection.members.shape
        values = [self.selection.absent] * len(shape.members)
        unlisted: list[str] = []
        for name, value in _named_members(members):
            position = shape.position(name)
            if position is None:
                unlisted.append(name)
            else:
                values[position] = value
        if not isinstance(key, Unstated):
            values[self.key_position] = key
        return CompletePayload(tuple(values), tuple(unlisted))

    def partial_payload_from_names(
        self, members: Mapping[str, object], *, key: object = UNSTATED
    ) -> PartialPayload:
        """``members``, a name mapping stating some members, as a partial
        payload in the order ``members`` states them, ``key`` standing for any
        key ``members`` names where it is stated. Judges no value."""
        shape = self.selection.members.shape
        stated: list[StatedMember] = []
        unlisted: list[str] = []
        overriding = not isinstance(key, Unstated)
        if overriding:
            stated.append((self.key_position, key))
        for name, value in _named_members(members):
            position = shape.position(name)
            if position is None:
                unlisted.append(name)
            elif not (overriding and position == self.key_position):
                stated.append((position, value))
        return PartialPayload(tuple(stated), tuple(unlisted))


def _named_members(members: Mapping[str, object]) -> Iterable[tuple[str, object]]:
    refuse_observation_keys(members)
    return members.items()


class WritePreparation:
    """One model's write preparation products, every Entity's derived at
    construction.

    ``absent`` is the marker the model's accepted Entity State spells an
    omitted member with; every row selection and nested occurrence cell the
    plans author carries that same object. ``positional`` names, by Entity,
    the class each one's instances are proven to hold their members in member
    order.
    """

    __slots__ = ("_entities", "absent", "meta")

    def __init__(
        self,
        meta: Metamodel,
        *,
        absent: object,
        positional: Mapping[EntityIdentity, type] | None = None,
    ) -> None:
        self.meta = meta
        self.absent = absent
        families = inheritance.inheritance_facet_of(meta)
        catalog = AuthoringCatalog(_LANES, absent=absent)
        entities: dict[EntityIdentity, EntityPreparation] = {}
        for entity in meta.entities:
            view = families.entity(entity.identity)
            if view is None:  # pragma: no cover - the facet covers every accepted Entity
                raise ValueError(f"{entity.identity.canonical}: no Inheritance Facet view")
            entities[entity.identity] = _entity_preparation(
                view,
                catalog,
                absent,
                None if positional is None else positional.get(entity.identity),
            )
        self._entities: Mapping[EntityIdentity, EntityPreparation] = entities

    def entity(self, identity: EntityIdentity) -> EntityPreparation:
        return self._entities[identity]


def _entity_preparation(
    view: inheritance.InheritanceEntityView,
    catalog: AuthoringCatalog,
    absent: object,
    typed_class: type | None,
) -> EntityPreparation:
    selection = view.member_selection
    key = selection.index[view.primary_key.identity]
    generation = view.primary_key.primary_key
    allocation = (
        KeyAllocation(key, generation.generation.name)
        if isinstance(generation, PrimaryKey) and isinstance(generation.generation, KeySequence)
        else None
    )
    required = 0
    framework_owned = 0
    read_only = 0
    replaced = 0
    for position, member in enumerate(selection.bindings):
        bit = 1 << position
        attribute = member if isinstance(member, AttributeMetadata) else None
        if attribute is not None and attribute.framework_owned:
            framework_owned |= bit
        elif not member.nullable and member.multiplicity is Multiplicity.ONE:
            required |= bit
        if attribute is not None and attribute.read_only and position != key:
            read_only |= bit
        if (
            member.multiplicity is Multiplicity.ONE
            and position != key
            and (attribute is None or attribute.write_capability.caller_update)
        ):
            replaced |= bit
    return EntityPreparation(
        selection=RowSelection(selection, absent),
        plan=catalog.plan(selection.shape),
        key_position=key,
        insert_required=required if allocation is None else required & ~(1 << key),
        framework_owned=framework_owned,
        read_only=read_only,
        replace_required=replaced & required,
        replace_nulled=replaced & ~required,
        typed_class=typed_class,
        key_allocation=allocation,
    )
