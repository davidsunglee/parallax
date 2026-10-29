from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Protocol

from parallax.core.base import NeutralType
from parallax.core.document_codec import PreparedPatch
from parallax.core.metamodel import EntityIdentity
from parallax.core.write_plan.steps import PlannedAssignments, WriteRow

__all__ = [
    "AssignmentPayload",
    "ColumnPlacement",
    "InsertPayload",
    "PatchedDocument",
    "RowPayload",
    "RowSlots",
    "WritePayloadPreparer",
]


@dataclass(frozen=True, slots=True)
class PatchedDocument:
    """The paths one revising step assigns inside a shared Structured Column,
    as the ordered prepared patches a path-patching statement applies."""

    patches: tuple[PreparedPatch, ...]


class ColumnPlacement(Protocol):
    """Where each of a statement's persisted cells lands, in Table Layout slot
    order, all aligned.

    ``contributors`` names each cell by model identity — a member, the shared
    Structured Column's tag, or the table-per-hierarchy discriminator's — and
    ``columns`` the physical Column it occupies, unquoted. ``types`` holds the
    Neutral Type a scalar cell binds at, ``None`` for any other cell, and
    ``documents`` whether a cell stores one whole encoded document.
    """

    @property
    def contributors(self) -> tuple[Hashable, ...]: ...
    @property
    def columns(self) -> tuple[str, ...]: ...
    @property
    def types(self) -> tuple[NeutralType | None, ...]: ...
    @property
    def documents(self) -> tuple[bool, ...]: ...


class RowSlots(ColumnPlacement, Protocol):
    """The cells every row of one Entity stating exactly the members
    ``presence`` names stores, and how each is gathered from such a row.

    Fixed by the Entity and ``presence`` alone, so every row of one insert
    statement shares one. ``shared_document`` is the index of the Table's
    shared Structured Column among the cells, ``None`` where it has none.
    ``element_types`` holds the Neutral Type every cell of a slot shares: its
    scalar type, ``json`` for a stored document, and ``string`` for the
    table-per-hierarchy discriminator's tag.
    """

    @property
    def entity(self) -> EntityIdentity: ...
    @property
    def presence(self) -> int: ...
    @property
    def table(self) -> str: ...
    @property
    def shared_document(self) -> int | None: ...
    @property
    def element_types(self) -> tuple[NeutralType, ...]: ...

    def cells(self, write_row: WriteRow) -> tuple[object, ...]:
        """``write_row``'s persisted cells, aligned with :attr:`contributors`.

        ``write_row`` states exactly the members :attr:`presence` names, and
        every ordinary cell it holds was already admitted, so nothing here
        judges a value again.
        """
        ...

    def column_cells(self, rows: Sequence[tuple[object, ...]]) -> tuple[list[object], ...]:
        """``rows``' cells as one new list per slot, in row order, aligned with
        :attr:`contributors`.

        Each row holds the cells :meth:`cells` gathered for one row stating
        :attr:`presence`, so every row is as wide as the slots.
        """
        ...


@dataclass(frozen=True, slots=True)
class RowPayload:
    """The persisted cells one Write Row stores under the Row Slots its
    presence selects, aligned with their contributors.

    A value is a planned scalar or generated-value expression, a complete
    encoded document (``None`` for a null Value Object, which binds SQL NULL),
    or the discriminator's tag.
    ``source`` is the Write Row the cells were prepared from, held by identity
    so a consumer can refuse a payload prepared from other inputs without
    comparing documents.
    """

    slots: RowSlots
    source: WriteRow
    values: tuple[object, ...]

    def __post_init__(self) -> None:
        if len(self.slots.contributors) != len(self.values):
            raise ValueError("a payload aligns one value with each contributor")

    @property
    def entity(self) -> EntityIdentity:
        return self.slots.entity

    @property
    def contributors(self) -> tuple[Hashable, ...]:
        return self.slots.contributors

    def prepared_from(self, write_row: WriteRow) -> bool:
        """Whether these cells were prepared from ``write_row``'s own row,
        origin, and executed members, whichever carrier holds them."""
        source = self.source
        return (
            source.row is write_row.row
            and source.origin is write_row.origin
            and source.executed is write_row.executed
        )


@dataclass(frozen=True, slots=True)
class InsertPayload:
    """What one insert statement stores: each entry's cells, in entry order,
    under the one Row Slots every entry's presence selects."""

    slots: RowSlots
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class AssignmentPayload:
    """The persisted values one revising step assigns, in Table Layout slot
    order, aligned with the placement of the cells they occupy.

    ``assignments`` is the semantic assignment set the cells were prepared from,
    held by identity. The shared Structured Column's value is a
    :class:`PatchedDocument` rather than a whole document, so unassigned content
    stays as stored.
    """

    entity: EntityIdentity
    assignments: PlannedAssignments
    placement: ColumnPlacement
    values: tuple[object, ...]

    def __post_init__(self) -> None:
        if len(self.placement.contributors) != len(self.values):
            raise ValueError("a payload aligns one value with each contributor")

    @property
    def contributors(self) -> tuple[Hashable, ...]:
        return self.placement.contributors


class WritePayloadPreparer(Protocol):
    """Model-scoped preparation of the values a write persists.

    Settlement and lowering share one configured preparer; neither encodes a
    payload of its own. Preparation is pure and demand-driven: a narrow update
    demands its assignments alone, and nothing prepares a complete row it does
    not need.
    """

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        """The persisted values ``assignments`` writes to an existing row."""
        ...

    def row_slots(self, entity: EntityIdentity, presence: int) -> RowSlots:
        """The Row Slots of every row of ``entity`` stating exactly the
        members ``presence`` names."""
        ...

    def row(self, entity: EntityIdentity, write_row: WriteRow) -> RowPayload:
        """The complete persisted cells ``write_row`` stores."""
        ...

    def proven_unequal_non_interval(
        self, entity: EntityIdentity, left: WriteRow, right: WriteRow
    ) -> bool:
        """Whether the two rows' persisted non-interval state is known to differ
        from what is already available, without preparing structured payload.
        ``False`` proves nothing."""
        ...

    def equal_non_interval(self, left: RowPayload, right: RowPayload) -> bool:
        """Whether the two prepared rows persist the same state outside their
        temporal interval cells."""
        ...

    def rebound(self, payload: RowPayload, write_row: WriteRow) -> RowPayload:
        """``payload``'s cells for ``write_row``, which states exactly what
        ``payload`` was prepared from outside its temporal interval: the same
        prepared values, with ``write_row``'s own interval cells. A row stating
        anything else outside its interval is refused rather than given cells
        prepared from other inputs."""
        ...
