from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from parallax.core.read_delivery._page._rows import Page

__all__ = ["INERT_OBSERVER", "MaterializationObserver", "page_cadence"]


class MaterializationObserver(Protocol):
    """Aggregate cadence events emitted while a Page is read, judged, and published."""

    def prepared(self, levels: int) -> None: ...

    def statement_rendered(self, level: int) -> None: ...

    def statement_executed(self, level: int, rows: int) -> None: ...

    def occurrences_reached(self, count: int) -> None: ...

    def witnesses_compared(self, count: int) -> None: ...

    def states_decoded(self) -> None: ...

    def states_shared(self) -> None: ...

    def root_published(self, ordinal: int) -> None: ...


@dataclass(frozen=True, slots=True)
class _InertObserver:
    def prepared(self, levels: int) -> None:
        del levels

    def statement_rendered(self, level: int) -> None:
        del level

    def statement_executed(self, level: int, rows: int) -> None:
        del level, rows

    def occurrences_reached(self, count: int) -> None:
        del count

    def witnesses_compared(self, count: int) -> None:
        del count

    def states_decoded(self) -> None:
        pass

    def states_shared(self) -> None:
        pass

    def root_published(self, ordinal: int) -> None:
        del ordinal


INERT_OBSERVER: MaterializationObserver = _InertObserver()


def page_cadence(page: Page) -> MaterializationObserver:
    """The observer ``page`` was built under, or the inert one."""
    observer = page.observer
    return INERT_OBSERVER if observer is None else cast("MaterializationObserver", observer)
