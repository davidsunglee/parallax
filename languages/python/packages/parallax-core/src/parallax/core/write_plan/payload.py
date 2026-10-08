from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Protocol

from parallax.core.document_codec import PreparedPatch
from parallax.core.metamodel import EntityIdentity
from parallax.core.write_plan.steps import PlannedAssignments, WriteRow

__all__ = [
    "AssignmentPayload",
    "PatchedDocument",
    "RowPayload",
    "WritePayloadPreparer",
]


@dataclass(frozen=True, slots=True)
class PatchedDocument:
    """The paths one revising step assigns inside a shared Structured Column,
    as the ordered prepared patches a path-patching statement applies."""

    patches: tuple[PreparedPatch, ...]


@dataclass(frozen=True, slots=True)
class RowPayload:
    """The persisted cells one Write Row stores, in Table Layout slot order:
    each cell's contributor and the value stored there, aligned.

    A contributor is a member identity, or the tagged identity of the shared
    Structured Column or the table-per-hierarchy discriminator, never a physical
    column. A value is a planned scalar or generated-value expression, a
    complete encoded document (``None`` for JSON null), or the discriminator's
    tag. ``source`` is the Write Row the cells were prepared from, held by
    identity so a consumer can refuse a payload prepared from other inputs
    without comparing documents.
    """

    entity: EntityIdentity
    source: WriteRow
    contributors: tuple[Hashable, ...]
    values: tuple[object, ...]

    def __post_init__(self) -> None:
        if len(self.contributors) != len(self.values):
            raise ValueError("a payload aligns one value with each contributor")

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
class AssignmentPayload:
    """The persisted values one revising step assigns, in Table Layout slot
    order, aligned with their contributors as in :class:`RowPayload`.

    ``assignments`` is the semantic assignment set the cells were prepared from,
    held by identity. The shared Structured Column's value is a
    :class:`PatchedDocument` rather than a whole document, so unassigned content
    stays as stored.
    """

    entity: EntityIdentity
    assignments: PlannedAssignments
    contributors: tuple[Hashable, ...]
    values: tuple[object, ...]

    def __post_init__(self) -> None:
        if len(self.contributors) != len(self.values):
            raise ValueError("a payload aligns one value with each contributor")


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
