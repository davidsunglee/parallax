from __future__ import annotations

from parallax.core._execution._retention import (
    ReadEvidenceByProjection,
    ReadEvidenceContext,
    RecordedProjections,
    defer_read_evidence,
)
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery._page import Page, hydrates, judged_state, page_rows

__all__ = ["ReadEvidenceCollector"]


class ReadEvidenceCollector(RecordedProjections):
    """One writable Page operation's projection observer and origin source, in
    one object.

    Conversion reports each projection to it while the row is live, and the
    reader asks it for the sealed Page's origins once. ``evidence_context`` is
    what the participating attempt files the evidence into.
    """

    __slots__ = ("_evidence_context", "_meta")

    def __init__(self, meta: Metamodel, *, evidence_context: ReadEvidenceContext) -> None:
        super().__init__()
        self._meta = meta
        self._evidence_context = evidence_context

    def origins_for(self, page: Page, /) -> ReadEvidenceByProjection:
        """The lazy Read Evidence of each recorded projection of the sealed ``page``.

        Participation and read freshness are captured now, while the read that
        acquired the rows runs; each origin resolves from its Page-owned judged
        state when first read. The records pass to the origins and this
        collector keeps none, so the raw documents they reference live no longer
        than the origins that still need them, however long the request
        carrying this collector stays reachable.
        """
        rows = page_rows(page)

        def admitted(node: int) -> tuple[EntityLayout, tuple[object, ...]] | None:
            state = None if rows.keys[node] is None else judged_state(rows, node)
            # Invalid roots suppress their complete origin map before this callback.
            if state is None or not hydrates(state.findings):  # pragma: no cover
                return None
            return rows.layouts[node], state.member_row

        def primary_key(node: int) -> object | None:
            key = rows.keys[node]
            return None if key is None else key.primary_key

        origins = defer_read_evidence(
            self._meta,
            self,
            admitted,
            lambda node: rows.layouts[node].concrete,
            primary_key,
            evidence_context=self._evidence_context,
            pin=page.pin,
        )
        self._rows.clear()
        return origins
