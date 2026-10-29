from __future__ import annotations

from collections.abc import Hashable, Iterator, Mapping
from itertools import chain
from typing import cast

from parallax.core.base import Json, ManagedValue, NeutralType
from parallax.core.document_codec import (
    NULL,
    DocumentPatch,
    OccurrenceDefinition,
    Present,
    SetScalar,
    SetValueObject,
    persisted_document_equal,
)
from parallax.core.document_codec._document import prepare_managed_patches
from parallax.core.document_codec._leaf import encode_managed_scalar_many
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.storage_layout import ColumnTier, EntityLayoutView, RelationalDocument
from parallax.core.write_payload._storage import (
    EffectShape,
    EntityStorage,
    StorageCatalog,
    assigned_document,
)
from parallax.core.write_plan.managed_row import ManagedRow
from parallax.core.write_plan.payload import (
    AssignmentPayload,
    EffectSlots,
    PatchedDocument,
    RowPayload,
    RowSlots,
)
from parallax.core.write_plan.planned_rows import WritePlanningError
from parallax.core.write_plan.steps import (
    MaxPlusOne,
    PlannedAssignments,
    PlannedStep,
    SelfIncrement,
    WriteRow,
)

__all__ = ["LayoutPayloadPreparer"]


class LayoutPayloadPreparer:
    """The write payload preparer of one accepted Metamodel.

    Every member is placed where the model's Storage Layout puts it and encoded
    by the document codec, so lowering only renders and binds what this
    answers. Nothing here chooses authority, preservation, or topology.
    """

    __slots__ = ("_comparisons", "_storage")

    def __init__(self, model: Metamodel) -> None:
        self._storage = StorageCatalog(model)
        self._comparisons: dict[EntityIdentity, _Comparison] = {}

    def row_slots(self, entity: EntityIdentity, presence: int) -> RowSlots:
        return self._storage.entity(entity).row_slots(presence)

    def row(self, entity: EntityIdentity, write_row: WriteRow) -> RowPayload:
        slots = self.row_slots(entity, write_row.row.presence)
        return RowPayload(slots=slots, source=write_row, values=slots.cells(write_row))

    def effect_shape(self, step: PlannedStep) -> EffectShape | None:
        return self._storage.entity(step.entity).effect_shape(step)

    def effect_slots(self, entity: EntityIdentity, shape: Hashable) -> EffectSlots:
        if not isinstance(shape, EffectShape) or shape.entity != entity:
            raise WritePlanningError(
                f"{entity.canonical}: an effect shape names the Effect Slots of its own Entity"
            )
        return self._storage.entity(entity).effect_slots(shape)

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        storage = self._storage.entity(entity)
        slots, values = _assignment_cells(storage, assignments)
        return AssignmentPayload(
            entity=entity,
            assignments=assignments,
            placement=storage.assignment_placement(slots),
            values=values,
        )

    def proven_unequal_non_interval(
        self, entity: EntityIdentity, left: WriteRow, right: WriteRow
    ) -> bool:
        """Whether some scalar member both rows state persists differently.

        Each Attribute both finalized rows hold a resolved value for is
        compared as stored: a managed value is exact at its Neutral Type, so
        values that differ are stored differently whether the member has a
        Column of its own or lives in the shared document. A scalar
        collection's managed tuple is exact element by element in order, so
        the same holds for it. Interval members, generated values, members only
        one row states, and occurrences decide nothing here.
        """
        # A member either row executes is where neighbours usually differ, so it
        # is compared before the rest; an executed occurrence is no scalar and
        # its lookups miss.
        documented = cast("Mapping[Hashable, bool]", self._storage.entity(entity).scalars)
        left_row, right_row = left.row, right.row
        for identity in chain(left.executed, right.executed, _stated_attributes(left_row)):
            json = documented.get(identity)
            if json is None:  # an interval member or an occurrence
                continue
            value = left_row.cell(cast("AttributeIdentity", identity))
            other = right_row.cell(cast("AttributeIdentity", identity))
            if (
                value is left_row.selection.absent
                or other is right_row.selection.absent
                or _generated(value)
                or _generated(other)
            ):
                continue
            if _scalar_differs(json, value, other):
                return True
        return False

    def equal_non_interval(self, left: RowPayload, right: RowPayload) -> bool:
        """Whether both complete prepared rows persist identical cells outside
        their temporal interval.

        A row that leaves some Column to the database's default, or holds a
        generated value, establishes no known state and so equals nothing.
        """
        if left.entity != right.entity:
            return False
        cells = self._comparison(left.entity).cells
        if len(left.values) != len(cells) or len(right.values) != len(cells):
            return False
        for (slot, kind), contributor, other_contributor, value, other in zip(
            cells,
            left.contributors,
            right.contributors,
            left.values,
            right.values,
            strict=True,
        ):
            if (
                contributor != other_contributor
                or contributor != slot
                or not _cell_equal(kind, value, other)
            ):
                return False
        return True

    def rebound(self, payload: RowPayload, write_row: WriteRow) -> RowPayload:
        source = payload.source
        entity = payload.entity
        intervals = self._storage.entity(entity).interval_members
        row = write_row.row
        before = source.row
        index = row.selection.members.index
        if (
            write_row.origin is not source.origin
            or write_row.executed is not source.executed
            or row.selection is not before.selection
            or row.presence != before.presence
            or any(
                cell is not other and before.selection.members.identities[position] not in intervals
                for (position, cell), other in zip(before.stated_cells(), row.cells, strict=True)
            )
        ):
            raise WritePlanningError(
                f"{entity.name!r}: prepared cells rebind only to a row stating what they were "
                "prepared from outside its temporal interval"
            )
        return RowPayload(
            slots=payload.slots,
            source=write_row,
            values=tuple(
                row.at(index[contributor])
                if isinstance(contributor, AttributeIdentity) and contributor in intervals
                else value
                for contributor, value in zip(payload.contributors, payload.values, strict=True)
            ),
        )

    def _comparison(self, entity: EntityIdentity) -> _Comparison:
        comparison = self._comparisons.get(entity)
        if comparison is None:
            comparison = self._comparisons[entity] = _Comparison(self._storage.entity(entity).view)
        return comparison


_INTERVAL, _DOCUMENT, _JSON, _SCALAR, _EXACT = range(5)


class _Comparison:
    """How one Table's persisted cells compare, resolved once per preparer:
    each slot's contributor and how its cell compares."""

    __slots__ = ("cells",)

    def __init__(self, view: EntityLayoutView) -> None:
        cells: list[tuple[Hashable, int]] = []
        for slot in view.columns:
            contributor = slot.contributor
            if slot.tier is ColumnTier.TEMPORAL:
                kind = _INTERVAL
            elif slot.tier is ColumnTier.DOCUMENT:
                kind = _DOCUMENT
            elif isinstance(contributor, AttributeIdentity):
                kind = _JSON if isinstance(_attribute_type(view, contributor), Json) else _SCALAR
            else:
                kind = _EXACT
            cells.append((contributor, kind))
        self.cells = tuple(cells)


def _assignment_cells(
    storage: EntityStorage, assignments: PlannedAssignments
) -> tuple[int, tuple[object, ...]]:
    """The slots ``assignments`` writes, as a mask of their indexes, and the
    persisted value each stores there, in Table Layout slot order.

    A revising statement writes only what it assigns: the shared Structured
    Column takes the ordered prepared patches of its assigned paths, so every key
    it does not name survives, and an assigned occurrence replaces its whole
    subtree at its own path whatever its cardinality. Every assigned value was
    admitted before planning placed it here, so its encoding judges nothing.
    """
    attributes = assignments.attributes
    value_objects = assignments.value_objects
    values: list[object] = []
    slots = 0
    matched = 0
    for index, slot in enumerate(storage.slots):
        contributor = slot.contributor
        if isinstance(contributor, AttributeIdentity):
            if contributor not in attributes:
                continue
            value: object = attributes[contributor]
            if slot.document:
                value = _collection_cell(cast("NeutralType", slot.fact), value)
        elif isinstance(contributor, ValueObjectIdentity):
            if contributor not in value_objects:
                continue
            value = assigned_document(
                cast("OccurrenceDefinition", slot.fact), value_objects[contributor]
            )
        elif isinstance(contributor, RelationalDocument) and storage.residents is not None:
            patches = _resident_patches(storage, attributes, value_objects)
            if not patches:
                continue
            matched += len(patches) - 1
            value = PatchedDocument(prepare_managed_patches(storage.residents.shape, patches))
        else:
            continue
        matched += 1
        slots |= 1 << index
        values.append(value)
    if matched != len(attributes) + len(value_objects):  # pragma: no cover - planning places it
        raise WritePlanningError(
            f"{storage.entity.canonical}: a planned member occupies no Column of the target's "
            "Table Layout"
        )
    return slots, tuple(values)


def _resident_patches(
    storage: EntityStorage,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> list[DocumentPatch]:
    """The patches writing each assigned document-resident member at its path,
    in canonical logical placement order — the order the in-memory patch and the
    equivalent path-patched statement both apply left to right
    (`m-storage-layout`).

    An assigned ``None`` writes JSON null rather than removing the key, which is
    the one not-present state a NULL Column also has.
    """
    residents = storage.residents
    assert residents is not None  # a shared Structured Column owns residency
    patches: list[DocumentPatch] = []
    for member, identity, path in zip(
        residents.shape.members, residents.identities, residents.paths, strict=True
    ):
        if isinstance(member, OccurrenceDefinition):
            if identity in value_objects:
                patches.append(
                    SetValueObject(
                        path,
                        assigned_document(
                            member, value_objects[cast("ValueObjectIdentity", identity)]
                        ),
                    )
                )
        elif identity in attributes:
            raw = attributes[cast("AttributeIdentity", identity)]
            patches.append(SetScalar(path, NULL if raw is None else Present(raw)))
    return patches


def _collection_cell(element_type: NeutralType, value: object) -> object:
    """A scalar collection's own structured Column: its encoded array, with the
    null a stored row may carry read as the empty collection it denotes."""
    elements = () if value is None else cast("tuple[ManagedValue, ...]", value)
    return encode_managed_scalar_many(element_type, elements)


def _attribute_type(view: EntityLayoutView, identity: AttributeIdentity) -> object:
    binding = view.member_selection.bindings[view.member_selection.position(identity)]
    assert isinstance(binding, AttributeMetadata)  # identities are disjoint
    return binding.type


def _stated_attributes(row: ManagedRow) -> Iterator[AttributeIdentity]:
    """The scalar members ``row`` states, in member order."""
    members = row.selection.members
    identities = members.identities
    for position in row.positions():
        if position >= members.attribute_count:
            return
        yield cast("AttributeIdentity", identities[position])


def _generated(value: object) -> bool:
    return isinstance(value, MaxPlusOne | SelfIncrement)


def _cell_equal(kind: int, value: object, other: object) -> bool:
    if kind == _INTERVAL:
        return True
    if _generated(value) or _generated(other):
        return False
    if kind == _DOCUMENT:
        return persisted_document_equal(value, other)
    if kind == _EXACT:
        return value == other
    return not _scalar_differs(kind == _JSON, value, other)


def _scalar_differs(json: bool, value: object, other: object) -> bool:
    if value is None or other is None:
        return value is not other
    if json:
        return not persisted_document_equal(value, other)
    return value != other
