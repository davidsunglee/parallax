from __future__ import annotations

from collections.abc import Container, Hashable, Mapping, Sequence
from typing import Final, cast

from parallax.core import storage_layout
from parallax.core.base import Json
from parallax.core.document_codec import (
    NULL,
    DocumentPatch,
    Present,
    SetLeaf,
    SetValue,
    apply_prepared_patches,
    persisted_document_equal,
    prepare_patches,
)
from parallax.core.document_codec._document import encode_managed_document, encode_managed_many
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.storage_layout import (
    ColumnTier,
    DocumentResidentSelection,
    EntityLayoutView,
    InheritanceDiscriminator,
    RelationalDocument,
)
from parallax.core.write_plan.payload import (
    AssignmentPayload,
    PatchedDocument,
    RowPayload,
)
from parallax.core.write_plan.planned_rows import WritePlanningError
from parallax.core.write_plan.steps import (
    MaxPlusOne,
    NewLineage,
    PlannedAssignments,
    SelfIncrement,
    WriteRow,
)

__all__ = ["LayoutPayloadPreparer"]

_UNSTATED: Final = object()


class LayoutPayloadPreparer:
    """The write payload preparer of one accepted Metamodel.

    Every member is placed where the model's Storage Layout puts it and encoded
    by the document codec, so lowering only renders and binds what this
    answers. Nothing here chooses authority, preservation, or topology.
    """

    __slots__ = ("_intervals", "_layouts", "_residences")

    def __init__(self, model: Metamodel) -> None:
        self._layouts = storage_layout.view(model)
        self._intervals: dict[EntityIdentity, frozenset[AttributeIdentity]] = {}
        self._residences: dict[EntityIdentity, _Residence | None] = {}

    def row(self, entity: EntityIdentity, write_row: WriteRow) -> RowPayload:
        view = self._view(entity)
        contributors, values = _row_cells(view, self._residence(entity, view), write_row)
        return RowPayload(
            entity=entity, row=write_row.row, contributors=contributors, values=values
        )

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        view = self._view(entity)
        contributors, values = _assignment_cells(view, self._residence(entity, view), assignments)
        return AssignmentPayload(
            entity=entity, assignments=assignments, contributors=contributors, values=values
        )

    def proven_unequal_non_interval(
        self, entity: EntityIdentity, left: WriteRow, right: WriteRow
    ) -> bool:
        """Whether some scalar member both rows state persists differently.

        Each Attribute both finalized rows hold a resolved value for is
        compared as stored: a managed value is exact at its Neutral Type, so
        values that differ are stored differently whether the member has a
        Column of its own or lives in the shared document. Interval members,
        generated values, members only one row states, and occurrences decide
        nothing here.
        """
        view = self._view(entity)
        intervals = self._interval_members(entity, view)
        right_attributes = right.row.attributes
        for identity, value in left.row.attributes.items():
            if identity in intervals:
                continue
            other = right_attributes.get(identity, _UNSTATED)
            if other is _UNSTATED or _generated(value) or _generated(other):
                continue
            if _scalar_differs(_attribute_type(view, identity), value, other):
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
        view = self._view(left.entity)
        columns = view.columns
        if len(left.values) != len(columns) or len(right.values) != len(columns):
            return False
        for slot, contributor, other_contributor, value, other in zip(
            columns,
            left.contributors,
            right.contributors,
            left.values,
            right.values,
            strict=True,
        ):
            if contributor != other_contributor or contributor != slot.contributor:
                return False
            if slot.tier is ColumnTier.TEMPORAL:
                continue
            if not _cell_equal(view, contributor, value, other):
                return False
        return True

    def _view(self, entity: EntityIdentity) -> EntityLayoutView:
        view = self._layouts.entity(entity)
        if view is None:
            raise WritePlanningError(f"{entity.name!r}: write target has no effective table")
        return view

    def _residence(self, entity: EntityIdentity, view: EntityLayoutView) -> _Residence | None:
        if entity in self._residences:
            return self._residences[entity]
        resident = view.document_residents
        residence = None if resident is None else _Residence(resident)
        self._residences[entity] = residence
        return residence

    def _interval_members(
        self, entity: EntityIdentity, view: EntityLayoutView
    ) -> frozenset[AttributeIdentity]:
        intervals = self._intervals.get(entity)
        if intervals is None:
            intervals = frozenset(
                slot.contributor
                for slot in view.columns
                if slot.tier is ColumnTier.TEMPORAL
                and isinstance(slot.contributor, AttributeIdentity)
            )
            self._intervals[entity] = intervals
        return intervals


type _Cells = tuple[tuple[Hashable, ...], tuple[object, ...]]


class _Residence:
    """One Table's document-resident members, resolved once per preparer: each
    member's binding and path in canonical logical placement order, and the
    identities the shared Structured Column accounts for."""

    __slots__ = ("members", "placements", "selection")

    def __init__(self, selection: DocumentResidentSelection) -> None:
        bindings = selection.member_selection.bindings
        self.selection = selection
        self.placements: tuple[
            tuple[AttributeMetadata | ValueObjectMetadata, tuple[str, ...]], ...
        ] = tuple(
            (bindings[position], placement.path)
            for position, placement in zip(selection.positions, selection.placements, strict=True)
        )
        self.members: frozenset[AttributeIdentity | ValueObjectIdentity] = frozenset(
            binding.identity for binding, _ in self.placements
        )

    def named(
        self,
        attributes: Mapping[AttributeIdentity, object],
        value_objects: Mapping[ValueObjectIdentity, object],
    ) -> int:
        """How many of the named members the Structured Column accounts for."""
        members = self.members
        return len(members.intersection(attributes)) + len(members.intersection(value_objects))


# One arm per Column contributor kind, in Table Layout slot order. It runs per written row
# and visits every slot, so the arms stay inline rather than behind a per-slot call.
def _row_cells(view: EntityLayoutView, residence: _Residence | None, write_row: WriteRow) -> _Cells:
    """``write_row``'s complete persisted cells, in Table Layout slot order.

    Every member a row names occupies its slot. A Value Object occurrence with
    a Column of its own stores its whole encoded document there, and an unnamed
    `many` stores ``[]``, because absence and the empty array are one logical
    zero state (`m-value-object`). Every document-resident member collapses into
    the Table's one shared Structured Column, which every row stores, the empty
    object included (`m-storage-layout`). The table-per-hierarchy discriminator
    stores the concrete subtype's own tag.
    """
    row = write_row.row
    attributes = row.attributes
    value_objects = row.value_objects
    discriminator = view.discriminator
    contributors: list[Hashable] = []
    values: list[object] = []
    matched = 0
    for slot in view.columns:
        contributor = slot.contributor
        if isinstance(contributor, AttributeIdentity):
            if contributor not in attributes:
                continue
            value: object = attributes[contributor]
            matched += 1
        elif isinstance(contributor, InheritanceDiscriminator):
            if discriminator is None:  # pragma: no cover - a discriminator slot owns its tag
                raise ValueError(f"{view.entity.canonical}: discriminator slot has no tag")
            value = discriminator.value
        elif isinstance(contributor, RelationalDocument):
            resident = _residents(view, residence)
            value = _row_document(resident, write_row)
            matched += resident.named(attributes, value_objects)
        else:
            occurrence = _occurrence_binding(view, contributor)
            if contributor in value_objects:
                stated = value_objects[contributor]
                value = None if stated is None else _occurrence_document(occurrence, stated)
                matched += 1
            elif occurrence.multiplicity is Multiplicity.MANY:
                value = _occurrence_document(occurrence, ())
            else:
                continue
        contributors.append(contributor)
        values.append(value)
    _require_placed(view, matched, len(attributes) + len(value_objects))
    return tuple(contributors), tuple(values)


def _assignment_cells(
    view: EntityLayoutView, residence: _Residence | None, assignments: PlannedAssignments
) -> _Cells:
    """The persisted values ``assignments`` writes, in Table Layout slot order.

    A revising statement writes only what it assigns: the shared Structured
    Column takes the ordered prepared patches of its assigned paths, so every key
    it does not name survives, and an assigned occurrence replaces its whole
    subtree at its own path whatever its cardinality.
    """
    attributes = assignments.attributes
    value_objects = assignments.value_objects
    contributors: list[Hashable] = []
    values: list[object] = []
    matched = 0
    for slot in view.columns:
        contributor = slot.contributor
        if isinstance(contributor, AttributeIdentity):
            if contributor not in attributes:
                continue
            value: object = attributes[contributor]
            matched += 1
        elif isinstance(contributor, RelationalDocument):
            resident = _residents(view, residence)
            named = resident.named(attributes, value_objects)
            if not named:
                continue
            matched += named
            value = PatchedDocument(
                prepare_patches(
                    resident.selection.shape,
                    _resident_patches(resident, attributes, value_objects),
                )
            )
        elif isinstance(contributor, ValueObjectIdentity) and contributor in value_objects:
            stated = value_objects[contributor]
            occurrence = _occurrence_binding(view, contributor)
            value = None if stated is None else _occurrence_document(occurrence, stated)
            matched += 1
        else:
            continue
        contributors.append(contributor)
        values.append(value)
    _require_placed(view, matched, len(attributes) + len(value_objects))
    return tuple(contributors), tuple(values)


def _row_document(resident: _Residence, write_row: WriteRow) -> object:
    """One row's Structured Column, given where its state came from.

    A row that succeeds a milestone whose observation retained the predecessor's
    raw document is that document patched at the members the row executes
    alone, so every key it carries outside them survives the close-and-insert —
    a key a newer application version wrote included (`m-document-codec`,
    `m-write-plan`). Settlement already made that document recursively
    immutable (`m-db-port`). An executed member is written whatever it assigns,
    so an executed occurrence replaces its stored subtree whole even where its
    declared members equal the stored ones.

    Without a retained document there is nothing to preserve, so the row's own
    complete member set composes the document.
    """
    row = write_row.row
    origin = write_row.origin
    if isinstance(origin, NewLineage) or origin.predecessor.document is None:
        return _complete_document(resident, row.attributes, row.value_objects)
    document = origin.predecessor.document
    executed = write_row.executed
    if not executed:
        return document
    patches = _resident_patches(
        resident,
        row.attributes,
        row.value_objects,
        executed,
    )
    if not patches:
        return document
    return apply_prepared_patches(document, prepare_patches(resident.selection.shape, patches))


def _complete_document(
    resident: _Residence,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> object:
    """One row's complete Structured Column document from its own members.

    Composed through the codec against the shape of every applicable
    document-resident member rather than only the named ones, so presence
    classification stays the codec's: a member the row omits is absent, one the
    row sets to ``None`` is JSON null, and a `many` occurrence always contributes
    its array even where the row never mentions it (`m-document-codec`).
    """
    values: dict[str, object] = {}
    for binding, _ in resident.placements:
        if isinstance(binding, AttributeMetadata):
            if binding.identity in attributes:
                values[binding.identity.name] = attributes[binding.identity]
        elif binding.identity in value_objects:
            values[binding.identity.path[-1]] = value_objects[binding.identity]
    return encode_managed_document(resident.selection.shape, values)


def _resident_patches(
    resident: _Residence,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
    selected: Container[AttributeIdentity | ValueObjectIdentity] | None = None,
) -> tuple[DocumentPatch, ...]:
    """The patches writing each named document-resident member at its path, in
    canonical logical placement order — the order the in-memory patch and the
    equivalent path-patched statement both apply left to right
    (`m-storage-layout`).

    An assigned ``None`` writes JSON null rather than removing the key, which is
    the one not-present state a NULL Column also has. ``selected``, where given,
    narrows the named members to the ones it holds.
    """
    patches: list[DocumentPatch] = []
    for binding, path in resident.placements:
        if selected is not None and binding.identity not in selected:
            continue
        if isinstance(binding, AttributeMetadata):
            if binding.identity in attributes:
                raw = attributes[binding.identity]
                patches.append(SetLeaf(path, NULL if raw is None else Present(raw)))
        elif binding.identity in value_objects:
            raw = value_objects[binding.identity]
            patches.append(
                SetValue(path, None if raw is None else _occurrence_document(binding, raw))
            )
    return tuple(patches)


def _occurrence_document(occurrence: ValueObjectMetadata, value: object) -> object:
    """One Value Object occurrence's document, spelled by the codec.

    The write input carries each leaf in whatever portable spelling it was
    authored or built in; the codec owns the ONE spelling stored, so the value
    stored is composed here rather than handed to a serializer as it arrived.
    That is what gives a ``decimal``, ``bytes``, ``date``, ``time``,
    ``timestamp``, or ``uuid`` leaf inside an occurrence its storage form, and it
    is idempotent over an already-encoded document because every decode leg is
    the encode leg's inverse (`m-document-codec`).
    """
    shape = occurrence.document_shape
    if occurrence.multiplicity is Multiplicity.MANY:
        return encode_managed_many(shape, cast("Sequence[Mapping[str, object]]", value))
    return encode_managed_document(shape, cast("Mapping[str, object]", value))


def _residents(view: EntityLayoutView, resident: _Residence | None) -> _Residence:
    if resident is None:  # pragma: no cover - a Relational Document slot owns residency
        raise ValueError(
            f"{view.entity.canonical}: Relational Document slot has no resident selection"
        )
    return resident


def _occurrence_binding(
    view: EntityLayoutView, identity: ValueObjectIdentity
) -> ValueObjectMetadata:
    binding = view.member_selection.bindings[view.member_selection.position(identity)]
    if isinstance(binding, AttributeMetadata):  # pragma: no cover - identities are disjoint
        raise ValueError(f"{identity.path[-1]!r}: the Column contributor is not an occurrence")
    return binding


def _attribute_type(view: EntityLayoutView, identity: AttributeIdentity) -> object:
    binding = view.member_selection.bindings[view.member_selection.position(identity)]
    assert isinstance(binding, AttributeMetadata)  # identities are disjoint
    return binding.type


def _require_placed(view: EntityLayoutView, matched: int, named: int) -> None:
    if matched != named:  # pragma: no cover - finalization resolves against this view
        raise ValueError(
            f"{view.entity.canonical}: a planned member occupies no Column of the target's "
            "Table Layout"
        )


def _generated(value: object) -> bool:
    return isinstance(value, MaxPlusOne | SelfIncrement)


def _scalar_differs(neutral_type: object, value: object, other: object) -> bool:
    if value is None or other is None:
        return value is not other
    if isinstance(neutral_type, Json):
        return not persisted_document_equal(value, other)
    return value != other


def _cell_equal(view: EntityLayoutView, contributor: object, value: object, other: object) -> bool:
    if _generated(value) or _generated(other):
        return False
    if isinstance(contributor, RelationalDocument | ValueObjectIdentity):
        return persisted_document_equal(value, other)
    if isinstance(contributor, AttributeIdentity):
        return not _scalar_differs(_attribute_type(view, contributor), value, other)
    return value == other
