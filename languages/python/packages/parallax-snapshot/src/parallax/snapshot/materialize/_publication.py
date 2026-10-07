from __future__ import annotations

from array import array
from collections.abc import Callable, Iterator, Sequence

from parallax.core import opt_lock
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery._page import (
    Page,
    StoredDataIssueInput,
    page_cadence,
    page_rows,
    release_page_rows,
    root_last_uses,
    stored_data_refusal,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize._root import RootView

__all__ = ["publication_issue", "publish_roots", "require_publishable"]


def publication_issue(root_view: RootView) -> StoredDataIssueInput | None:
    """The first issue reachable from a requested root, in deterministic Root View order."""
    if root_view.invalid_roots:
        return root_view.invalid_roots[0].issues[0]
    if not root_view.has_issues:
        return None
    # `invalid_roots` indexes every reachable issue; the walk is defensive for
    # implementations of RootView's structural protocol.
    for index in range(len(root_view.order)):  # pragma: no cover
        issues = root_view.issues(index)
        if issues:  # pragma: no cover
            return issues[0]
    raise AssertionError("an issue-bearing Root View has no reachable issue")  # pragma: no cover


def require_publishable(root_view: RootView) -> None:
    """Refuse an issue-bearing Root View before identity or object derivation."""
    issue = publication_issue(root_view)
    if issue is not None:
        raise stored_data_refusal(issue)


def publish_roots[T](
    page: Page,
    publish: Callable[[RootView, int], Iterator[T]],
    *,
    atomic: bool = False,
    model: Metamodel | None = None,
    ordinal_offset: int = 0,
    pins: Sequence[Pin | None] | None = None,
    prepare: Callable[[RootView], None] | None = None,
) -> Iterator[T]:
    """Form and publish one Root View per Page root, in result order.

    An ``atomic`` publication publishes nothing until every root has been, and
    defers judging every root's state when each root's family carries write
    evidence, which ``model``'s Optimistic Lock Facet answers; it is required
    exactly then. Each root's Page storage is released once no later root can
    reach it.
    """
    observer = page_cadence(page)
    if pins is not None and len(pins) != page.root_count:
        raise ValueError("root pin count must match the Page root count")
    if atomic:
        if model is None:
            raise ValueError("an atomic publication decides state deferral against its model")
        keys = opt_lock.view(model)
        rows = page_rows(page)
        deferred_states = all(
            isinstance(
                keys.key(rows.layouts[root].concrete),
                opt_lock.ExplicitVersion | opt_lock.TransactionTimeDerived,
            )
            for root in rows.roots
        )
        last_uses = (
            root_last_uses(page)
            if deferred_states or any(not isinstance(claim, int) for claim in rows.claims)
            else None
        )
        prepared: list[T] = []
        published_counts = array("I")
        for position in range(page.root_count):
            pin = None if pins is None else pins[position]
            root = RootView(page, position, pin=pin, defer_states=deferred_states)
            root.complete()
            if prepare is not None:
                prepare(root)
            if last_uses is None:
                root.release_raw_rows()
            else:
                root.release_finished_page_rows(position, last_uses)
            before = len(prepared)
            prepared.extend(publish(root, position))
            published_counts.append(len(prepared) - before)
        release_page_rows(page)
        prepared_position = 0
        for position, count in enumerate(published_counts):
            for root in prepared[prepared_position : prepared_position + count]:
                yield root
            prepared_position += count
            observer.root_published(ordinal_offset + position)
        return
    for position in range(page.root_count):
        pin = None if pins is None else pins[position]
        root = RootView(page, position, pin=pin)
        root.release_raw_rows()
        yield from publish(root, position)
        observer.root_published(ordinal_offset + position)
