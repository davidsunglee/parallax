from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from operator import itemgetter
from typing import Final, cast

from parallax.core import storage_layout
from parallax.core.base import JSON, STRING, Json, ManagedValue, NeutralType
from parallax.core.document_codec import (
    NULL,
    DocumentPatch,
    MemberShape,
    OccurrenceDefinition,
    Present,
    SetScalar,
    SetValueObject,
    apply_prepared_patches,
)
from parallax.core.document_codec._document import (
    encode_managed_document,
    encode_managed_many,
    prepare_managed_patches,
)
from parallax.core.document_codec._leaf import encode_managed_scalar_many
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    MemberIdentity,
    Metamodel,
    Multiplicity,
)
from parallax.core.storage_layout import (
    ColumnTier,
    DocumentResidentSelection,
    EntityLayoutView,
    InheritanceDiscriminator,
    RelationalDocument,
)
from parallax.core.write_plan.managed_row import occurrence_cells
from parallax.core.write_plan.planned_rows import WritePlanningError
from parallax.core.write_plan.steps import NewLineage, WriteRow

__all__ = [
    "ROW_SLOTS_PER_ENTITY",
    "AssignmentPlacement",
    "EntityStorage",
    "RowSlots",
    "StorageCatalog",
    "assigned_document",
    "occurrence_document",
]

ROW_SLOTS_PER_ENTITY: Final = 16
"""The most Row Slots one Entity's storage retains, one per presence first
seen, and likewise the most assignment placements. A row stating a further
combination of optional members is placed for its own statement and not
retained, so the members a writer chooses to state cannot grow what the model
holds."""

# How one Table slot's cell is gathered from a row: a member's own cell, a
# scalar collection's encoded array, an occurrence's encoded document, the
# shared Structured Column, or a value fixed by the slot itself.
_DIRECT, _COLLECTION, _OCCURRENCE, _SHARED, _CONSTANT = range(5)


class StorageCatalog:
    """Where one accepted model stores each member of every Entity owning rows.

    Each Entity's storage is compiled the first time a write of it asks and
    kept for the catalog's lifetime, so a catalog costs nothing per Entity the
    model declares but never writes.
    """

    __slots__ = ("_entities", "_layouts")

    def __init__(self, model: Metamodel) -> None:
        self._layouts = storage_layout.view(model)
        self._entities: dict[EntityIdentity, EntityStorage] = {}

    def entity(self, identity: EntityIdentity) -> EntityStorage:
        storage = self._entities.get(identity)
        if storage is None:
            view = self._layouts.entity(identity)
            if view is None:
                raise WritePlanningError(f"{identity.name!r}: write target has no effective table")
            storage = self._entities[identity] = EntityStorage(view)
        return storage


class _Slot:
    """One Table slot as a write stores it: its contributor, physical Column,
    gathering kind, the member position it gathers from where it gathers one,
    and the scalar type it binds at or the value it fixes."""

    __slots__ = ("column", "contributor", "document", "fact", "kind", "position")

    def __init__(
        self,
        contributor: Hashable,
        column: str,
        kind: int,
        position: int,
        fact: object,
        document: bool,
    ) -> None:
        self.contributor = contributor
        self.column = column
        self.kind = kind
        self.position = position
        self.fact = fact
        self.document = document


class EntityStorage:
    """One Entity's Table Layout, compiled for writing: each slot in Table
    Layout order, the document-resident members of its shared Structured
    Column, and the Row Slots of each presence first seen, at most
    :data:`ROW_SLOTS_PER_ENTITY` of them."""

    __slots__ = (
        "_assignments",
        "_rows",
        "entity",
        "interval_members",
        "residents",
        "scalars",
        "slots",
        "table",
        "view",
    )

    def __init__(self, view: EntityLayoutView) -> None:
        self.view = view
        self.entity = view.entity
        self.table = view.layout.table.name
        selection = view.member_selection
        bindings = selection.bindings
        members = selection.shape.members
        resident = view.document_residents
        self.residents = None if resident is None else _Residents(resident.shape, resident)
        slots: list[_Slot] = []
        intervals: set[AttributeIdentity] = set()
        for column_slot in view.columns:
            contributor = column_slot.contributor
            column = column_slot.column.name
            if isinstance(contributor, AttributeIdentity):
                position = selection.index[contributor]
                attribute = cast("AttributeMetadata", bindings[position])
                if column_slot.tier is ColumnTier.TEMPORAL:
                    intervals.add(contributor)
                if column_slot.tier is ColumnTier.DOCUMENT:
                    slots.append(
                        _Slot(contributor, column, _COLLECTION, position, attribute.type, True)
                    )
                else:
                    slots.append(
                        _Slot(contributor, column, _DIRECT, position, attribute.type, False)
                    )
            elif isinstance(contributor, InheritanceDiscriminator):
                discriminator = view.discriminator
                if discriminator is None:  # pragma: no cover - a discriminator slot owns its tag
                    raise ValueError(f"{view.entity.canonical}: discriminator slot has no tag")
                slots.append(_Slot(contributor, column, _CONSTANT, -1, discriminator.value, False))
            elif isinstance(contributor, RelationalDocument):
                if resident is None:  # pragma: no cover - a Relational Document slot owns residency
                    raise ValueError(
                        f"{view.entity.canonical}: Relational Document slot has no resident "
                        "selection"
                    )
                slots.append(_Slot(contributor, column, _SHARED, -1, None, True))
            else:
                position = selection.index[contributor]
                slots.append(
                    _Slot(contributor, column, _OCCURRENCE, position, members[position], True)
                )
        self.slots: tuple[_Slot, ...] = tuple(slots)
        self.interval_members: frozenset[AttributeIdentity] = frozenset(intervals)
        self.scalars: Mapping[AttributeIdentity, bool] = {
            binding.identity: isinstance(binding.type, Json)
            for binding in bindings
            if isinstance(binding, AttributeMetadata) and binding.identity not in intervals
        }
        self._rows: dict[int, RowSlots] = {}
        self._assignments: dict[int, AssignmentPlacement] = {}

    def row_slots(self, presence: int) -> RowSlots:
        """The Row Slots of every row stating exactly the members ``presence``
        names."""
        slots = self._rows.get(presence)
        if slots is None:
            slots = RowSlots(self, presence)
            if len(self._rows) < ROW_SLOTS_PER_ENTITY:
                self._rows[presence] = slots
        return slots

    def assignment_placement(self, slots: int) -> AssignmentPlacement:
        """The placement of the cells a revising statement assigns at the
        slots whose indexes the ``slots`` mask names."""
        placement = self._assignments.get(slots)
        if placement is None:
            placement = AssignmentPlacement(self, slots)
            if len(self._assignments) < ROW_SLOTS_PER_ENTITY:
                self._assignments[slots] = placement
        return placement


class _Residents:
    """The document-resident members of one shared Structured Column, in
    canonical logical placement order: each one's member position, identity,
    and path, aligned with ``shape``."""

    __slots__ = ("identities", "paths", "positions", "shape")

    def __init__(self, shape: MemberShape, resident: DocumentResidentSelection) -> None:
        identities = resident.member_selection.identities
        self.shape = shape
        self.positions: tuple[int, ...] = resident.positions
        self.identities: tuple[MemberIdentity, ...] = tuple(
            identities[position] for position in resident.positions
        )
        self.paths: tuple[tuple[str, ...], ...] = tuple(
            placement.path for placement in resident.placements
        )


def _part(slot: _Slot, presence: int) -> tuple[int, int, object] | None:
    """How a row stating ``presence`` stores ``slot``'s cell, ``None`` where it
    stores none there."""
    kind = slot.kind
    position = slot.position
    if kind in (_SHARED, _CONSTANT):
        return kind, 0, slot.fact
    if presence >> position & 1:
        return kind, _packed(presence, position), slot.fact
    if kind == _COLLECTION:
        return _CONSTANT, 0, ()
    if (
        kind == _OCCURRENCE
        and cast("OccurrenceDefinition", slot.fact).multiplicity is Multiplicity.MANY
    ):
        return _CONSTANT, 0, ()
    return None


def _element_type(slot: _Slot) -> NeutralType:
    """The Neutral Type every cell ``slot`` stores shares."""
    if slot.kind == _DIRECT:
        return cast("NeutralType", slot.fact)
    return JSON if slot.document else STRING


def _packed(presence: int, position: int) -> int:
    """The index of member ``position``'s cell in a row stating ``presence``."""
    return (presence & ((1 << position) - 1)).bit_count()


def _gather(indexes: Sequence[int]) -> Callable[[tuple[object, ...]], tuple[object, ...]]:
    """A gather answering a tuple of the cells at ``indexes``, whatever their
    number: ``itemgetter`` answers one cell bare and takes no empty index."""
    match len(indexes):
        case 0:
            return _nothing
        case 1:
            (index,) = indexes
            return lambda cells: (cells[index],)
        case _:
            return cast("Callable[[tuple[object, ...]], tuple[object, ...]]", itemgetter(*indexes))


def _nothing(_cells: tuple[object, ...]) -> tuple[object, ...]:
    return ()


class RowSlots:
    """The cells every row of one Entity stating exactly ``presence`` stores,
    in Table Layout slot order, and how each is gathered from such a row.

    An unstated nullable Column is left out rather than bound null; an unstated
    `many` stores ``[]``, and the shared Structured Column is stored by every
    row (`m-write-payload` *Row assembly*).
    """

    __slots__ = (
        "_document",
        "_gather",
        "_parts",
        "_residents",
        "columns",
        "contributors",
        "documents",
        "element_types",
        "entity",
        "presence",
        "shared_document",
        "table",
        "types",
    )

    def __init__(self, storage: EntityStorage, presence: int) -> None:
        self.entity = storage.entity
        self.presence = presence
        self.table = storage.table
        contributors: list[Hashable] = []
        columns: list[str] = []
        types: list[NeutralType | None] = []
        documents: list[bool] = []
        element_types: list[NeutralType] = []
        parts: list[tuple[int, int, object]] = []
        placed = 0
        self.shared_document: int | None = None
        self._residents = residents = storage.residents
        self._document: tuple[int, ...] = ()
        for slot in storage.slots:
            part = _part(slot, presence)
            if part is None:
                continue
            if part[0] == _SHARED:
                self.shared_document = len(parts)
                resident = cast("_Residents", residents)
                self._document = tuple(
                    _packed(presence, member) if presence >> member & 1 else -1
                    for member in resident.positions
                )
                placed += sum(1 for index in self._document if index >= 0)
            elif slot.position >= 0 and presence >> slot.position & 1:
                placed += 1
            parts.append(part)
            contributors.append(slot.contributor)
            columns.append(slot.column)
            types.append(cast("NeutralType", slot.fact) if slot.kind == _DIRECT else None)
            documents.append(slot.document)
            element_types.append(_element_type(slot))
        if placed != presence.bit_count():
            raise WritePlanningError(
                f"{storage.entity.canonical}: a planned member occupies no Column of the "
                "target's Table Layout"
            )
        self.contributors: tuple[Hashable, ...] = tuple(contributors)
        self.columns: tuple[str, ...] = tuple(columns)
        self.types: tuple[NeutralType | None, ...] = tuple(types)
        self.documents: tuple[bool, ...] = tuple(documents)
        self.element_types: tuple[NeutralType, ...] = tuple(element_types)
        direct = all(kind == _DIRECT for kind, _, _ in parts)
        self._gather = _gather([index for _, index, _ in parts]) if direct else None
        self._parts: tuple[tuple[int, int, object], ...] = tuple(parts)

    def cells(self, write_row: WriteRow) -> tuple[object, ...]:
        """``write_row``'s persisted cells, aligned with :attr:`contributors`.

        ``write_row`` states exactly :attr:`presence`, and every ordinary cell
        it holds was already admitted, so its cells are gathered as they are
        and its documents encoded unchecked.
        """
        row = write_row.row
        cells = row.cells
        gather = self._gather
        if gather is not None:
            return gather(cells)
        absent = row.selection.absent
        stored: list[object] = []
        for kind, index, fact in self._parts:
            if kind == _DIRECT:
                stored.append(cells[index])
            elif kind == _CONSTANT:
                stored.append(fact)
            elif kind == _COLLECTION:
                value = cells[index]
                stored.append(
                    encode_managed_scalar_many(
                        cast("NeutralType", fact),
                        () if value is None else cast("Iterable[ManagedValue]", value),
                    )
                )
            elif kind == _OCCURRENCE:
                value = cells[index]
                stored.append(
                    None
                    if value is None
                    else occurrence_document(cast("OccurrenceDefinition", fact), value, absent)
                )
            else:
                stored.append(self._shared_document(write_row, cells, absent))
        return tuple(stored)

    def column_cells(self, rows: Sequence[tuple[object, ...]]) -> tuple[list[object], ...]:
        """``rows``' cells as one new list per slot, in row order.

        Each row holds the cells :meth:`cells` gathered, its documents already
        encoded, so a column is read straight out of the rows and a value the
        slot fixes is repeated rather than read.
        """
        count = len(rows)
        return tuple(
            [
                [fact] * count if kind == _CONSTANT else list(map(itemgetter(index), rows))
                for index, (kind, _, fact) in enumerate(self._parts)
            ]
        )

    def _shared_document(
        self, write_row: WriteRow, cells: tuple[object, ...], absent: object
    ) -> object:
        """One row's shared Structured Column, given where its state came from.

        A row succeeding a milestone whose observation retained the
        predecessor's raw document is that document patched at the members the
        row executes alone, so every key it carries outside them survives the
        close-and-insert, a key a newer application version wrote included
        (`m-document-codec`, `m-write-plan`). An executed member is written
        whatever it assigns, so an executed occurrence replaces its stored
        subtree whole. Without a retained document the row's own complete
        member set composes the document, a member it omits absent there.
        """
        residents = cast("_Residents", self._residents)
        origin = write_row.origin
        if isinstance(origin, NewLineage) or origin.predecessor.document is None:
            return encode_managed_document(
                residents.shape,
                tuple(absent if index < 0 else cells[index] for index in self._document),
                absent,
            )
        document = origin.predecessor.document
        executed = write_row.executed
        if not executed:
            return document
        patches: list[DocumentPatch] = []
        for member, index, identity, path in zip(
            residents.shape.members,
            self._document,
            residents.identities,
            residents.paths,
            strict=True,
        ):
            if index < 0 or identity not in executed:
                continue
            value = cells[index]
            if isinstance(member, OccurrenceDefinition):
                patches.append(
                    SetValueObject(
                        path, None if value is None else occurrence_document(member, value, absent)
                    )
                )
            else:
                patches.append(SetScalar(path, NULL if value is None else Present(value)))
        if not patches:
            return document
        return apply_prepared_patches(document, prepare_managed_patches(residents.shape, patches))


class AssignmentPlacement:
    """Where the cells one revising statement assigns land, for one set of the
    Entity's slots, in Table Layout slot order."""

    __slots__ = ("columns", "contributors", "documents", "types")

    def __init__(self, storage: EntityStorage, slots: int) -> None:
        placed = [slot for index, slot in enumerate(storage.slots) if slots >> index & 1]
        self.contributors: tuple[Hashable, ...] = tuple(slot.contributor for slot in placed)
        self.columns: tuple[str, ...] = tuple(slot.column for slot in placed)
        self.types: tuple[NeutralType | None, ...] = tuple(
            cast("NeutralType", slot.fact) if slot.kind == _DIRECT else None for slot in placed
        )
        self.documents: tuple[bool, ...] = tuple(slot.document for slot in placed)


def occurrence_document(definition: OccurrenceDefinition, value: object, absent: object) -> object:
    """One stated Value Object occurrence's positional cell as its stored
    document, encoded unchecked."""
    if definition.multiplicity is Multiplicity.MANY:
        return encode_managed_many(
            definition.shape, cast("Sequence[Sequence[object]]", value), absent
        )
    return encode_managed_document(definition.shape, cast("Sequence[object]", value), absent)


def assigned_document(definition: OccurrenceDefinition, value: object) -> object:
    """One assigned Value Object member's value as its stored document,
    encoded unchecked; ``None`` for a null one, which its own Column stores as
    SQL NULL and a shared Structured Column as JSON null at its path."""
    if value is None:
        return None
    cells, absent = occurrence_cells(value, definition)
    return occurrence_document(definition, cells, absent)
