from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from parallax.core.metamodel import AttributeIdentity
from parallax.core.write_plan.columns import ChunkedColumnBuilder, ColumnSlice, whole

if TYPE_CHECKING:
    from parallax.core.inheritance import EntityMemberSelection

__all__ = [
    "PredecessorRows",
    "PredecessorRowsBuilder",
]


@dataclass(frozen=True, slots=True)
class PredecessorRows:
    """Each selected row's complete Predecessor Row state, in resolution order.

    ``rows`` holds the resolving read's own judged positional member rows,
    aligned to ``selection``, and ``absent`` is the marker those rows carry at a
    member the row does not hold. ``key_position`` is the family key's position
    in ``selection``. ``documents`` aligns each row's raw Structured Column and
    is absent where the read projected none. Rows and documents are adopted by
    reference from the reader that exclusively owned them, and nothing reads
    them except to view or copy them.
    """

    selection: EntityMemberSelection
    key_position: int
    absent: object
    rows: ColumnSlice[tuple[object, ...]]
    documents: ColumnSlice[object] | None = None

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("Predecessor Rows carries at least one row")
        if self.documents is not None and len(self.documents) != len(self.rows):
            raise ValueError(
                "Predecessor Rows aligns one raw document with each row: "
                f"{len(self.rows)} rows, {len(self.documents)} documents"
            )
        if not 0 <= self.key_position < len(self.selection.bindings):
            raise ValueError("Predecessor Rows' key position lies within its selection")

    def __len__(self) -> int:
        return len(self.rows)

    def key(self, index: int) -> object:
        return self.rows[index][self.key_position]

    def document(self, index: int) -> object | None:
        documents = self.documents
        return None if documents is None else documents[index]

    def axis_start(self, at: int, attribute: AttributeIdentity, /) -> object:
        position = self.selection.index.get(attribute)
        return None if position is None else self.rows[at][position]

    def axis_end(self, at: int, attribute: AttributeIdentity, /) -> object:
        position = self.selection.index.get(attribute)
        return None if position is None else self.rows[at][position]


class PredecessorRowsBuilder:
    """Accumulates :class:`PredecessorRows` by reference from judged rows."""

    __slots__ = ("_absent", "_documents", "_key_position", "_rows", "_selection")

    def __init__(
        self,
        selection: EntityMemberSelection,
        *,
        key_position: int,
        absent: object,
        documents: bool,
    ) -> None:
        self._selection = selection
        self._key_position = key_position
        self._absent = absent
        self._rows: ChunkedColumnBuilder[tuple[object, ...]] = ChunkedColumnBuilder()
        self._documents: ChunkedColumnBuilder[object] | None = (
            ChunkedColumnBuilder() if documents else None
        )

    def append(self, row: tuple[object, ...], document: object | None = None) -> None:
        self._rows.append(row)
        documents = self._documents
        if documents is not None:
            documents.append(document)

    def seal(self) -> PredecessorRows | None:
        """The evidence appended so far, or ``None`` when nothing was."""
        if not self._rows:
            return None
        documents = self._documents
        return PredecessorRows(
            selection=self._selection,
            key_position=self._key_position,
            absent=self._absent,
            rows=whole(self._rows.build()),
            documents=None if documents is None else whole(documents.build()),
        )
