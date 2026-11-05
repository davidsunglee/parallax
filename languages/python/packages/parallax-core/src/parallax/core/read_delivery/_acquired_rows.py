from __future__ import annotations

from collections.abc import Generator, Iterable

from parallax.core.entity._layout import EntityLayout
from parallax.core.read_delivery._convert import occurrence_completer
from parallax.core.read_delivery._page import (
    Page,
    PageSchedule,
    attribute_state,
    entity_state,
    page_rows,
    release_finished_rows,
    stored_data_refusal,
)

__all__ = [
    "admitted_member_rows",
    "completed_member_rows",
    "publishable_member_rows",
]


def publishable_member_rows(page: Page) -> Generator[tuple[object, ...]]:
    """Each flat root's judged positional member row, by reference and in result
    order, refusing the first root that holds invalid stored data.

    A read whose rows become write evidence has no channel for a stored-data
    verdict, so a root's findings refuse it before it contributes anything. Each
    root is judged only when the caller asks for it, and its raw row is released
    once judged.
    """
    rows = page_rows(page)
    raw_rows = PageSchedule(None, False)
    for position, root in enumerate(rows.roots):
        state = entity_state(rows, root)
        if state.findings:
            raise stored_data_refusal(state.findings[0])
        release_finished_rows(page, raw_rows, position, (root,))
        yield state.member_row


def admitted_member_rows(page: Page) -> Generator[tuple[object, ...]]:
    """Each flat root's positional member row with its Attributes judged, in
    result order, refusing the first root whose Attributes hold invalid stored
    data.

    The judgment :func:`publishable_member_rows` makes of a read projecting no
    Value Object, made of a read that projects them all: each occurrence its
    root carried stays the unexamined input its classification takes — its
    Column's value, or its location in the raw Structured Column, SQL null and
    a present JSON null kept apart — so the row outlives the Page and
    :func:`completed_member_rows` judges those inputs later, if at all. Each
    root is judged only when the caller asks for it, and its raw row is
    released once judged.
    """
    rows = page_rows(page)
    raw_rows = PageSchedule(None, False)
    for position, root in enumerate(rows.roots):
        state = attribute_state(rows, root)
        if state.findings:
            raise stored_data_refusal(state.findings[0])
        release_finished_rows(page, raw_rows, position, (root,))
        yield state.member_row


def completed_member_rows(
    layout: EntityLayout, rows: Iterable[tuple[object, ...]]
) -> Generator[tuple[object, ...]]:
    """Each of ``rows``, member rows :func:`admitted_member_rows` produced for
    ``layout``'s Entity, completed in order: its Value Object occurrences judged
    as an ordinary read judges them, refusing the first that holds invalid
    stored data. No statement runs and no Page is involved."""
    complete = occurrence_completer(layout)
    for row in rows:
        member_row, findings = complete(row)
        if findings:
            raise stored_data_refusal(findings[0])
        yield member_row
