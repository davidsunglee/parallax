"""The shared read-page and root-publication seam for every Snapshot lane."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol

from parallax.snapshot.materialize import Page

__all__ = ["INERT", "MaterializationObserver", "Materializer"]


class MaterializationObserver(Protocol):
    """Aggregate cadence events emitted by the shared materialization path."""

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


INERT: MaterializationObserver = _InertObserver()


@dataclass(frozen=True, slots=True)
class Materializer:
    """One delivery's two operations: build a Page, then publish its roots."""

    observer: MaterializationObserver = INERT

    def read_page[T](self, read: Callable[[MaterializationObserver], T]) -> T:
        """Run the one callback that reads and assembles this delivery's Page."""
        return read(self.observer)

    def roots(
        self,
        page: Page,
        publish: Callable[[], Iterator[object]],
        *,
        ordinal_offset: int = 0,
    ) -> Iterator[object]:
        """Publish ``page`` one root at a time and report completed roots."""
        for position, root in enumerate(publish()):
            self.observer.root_published(ordinal_offset + position)
            yield root
