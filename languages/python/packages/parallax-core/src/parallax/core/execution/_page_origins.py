from __future__ import annotations

from types import MappingProxyType

from parallax.core.entity._layout import EntityLayout
from parallax.core.execution._retention import (
    ObservationLedger,
    ReadOrigins,
    RecordedProjections,
    deferred_read_origins,
)
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery._page import Page, hydrates, judged_state, page_rows

__all__ = ["ObservedPageProjections"]


class ObservedPageProjections(RecordedProjections):
    """One Page operation's projection observer and origin source, in one object.

    Conversion reports each projection to it while the row is live, and the
    reader asks it for the sealed Page's origins once. ``ledger`` is the
    participating unit of work, absent for a standalone read; ``scanned`` marks a
    read that scans an As-Of Axis, whose roots stand at no single observed state
    and therefore carry no origin.
    """

    __slots__ = ("_ledger", "_meta", "_scanned")

    def __init__(self, meta: Metamodel, *, ledger: ObservationLedger | None, scanned: bool) -> None:
        super().__init__()
        self._meta = meta
        self._ledger = ledger
        self._scanned = scanned

    def origins_for(self, page: Page, /) -> ReadOrigins:
        """The lazy Read Origin of each recorded projection of the sealed ``page``.

        Participation and read freshness are captured now, while the read that
        acquired the rows runs; each origin resolves from its Page-owned judged
        state when first read. The records pass to the origins and this
        collector keeps none, so the raw documents they reference live no longer
        than the origins that still need them, however long the request
        carrying this collector stays reachable.
        """
        if self._scanned:
            self._rows.clear()
            return MappingProxyType({})
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

        origins = deferred_read_origins(
            self._meta,
            self,
            admitted,
            lambda node: rows.layouts[node].concrete,
            primary_key,
            ledger=self._ledger,
            pin=page.pin,
        )
        self._rows.clear()
        return origins
