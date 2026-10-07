"""The inert cadence observer a Page read without an installed observer reports to."""

from __future__ import annotations

from parallax.core.read_delivery._page import INERT_OBSERVER, PageBuilder, ViewSchema
from parallax.core.read_delivery._page._cadence import page_cadence
from parallax.core.temporal_read import Pin


def test_a_page_built_without_an_observer_reports_to_the_inert_one() -> None:
    page = PageBuilder(ViewSchema.of()).finish((), Pin())
    assert page_cadence(page) is INERT_OBSERVER


def test_the_inert_observer_accepts_every_cadence_event() -> None:
    observer = INERT_OBSERVER
    observer.prepared(2)
    observer.statement_rendered(0)
    observer.statement_executed(0, 3)
    observer.occurrences_reached(3)
    observer.witnesses_compared(1)
    observer.states_decoded()
    observer.states_shared()
    observer.root_published(0)
