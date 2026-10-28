from __future__ import annotations

from array import array
from collections.abc import Callable, Iterator, Mapping
from types import MappingProxyType
from typing import Final

from parallax.core import opt_lock
from parallax.core._execution._unit_work.retain import ReadEvidence
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery._page import (
    Page,
    StoredDataIssueInput,
    page_cadence,
    page_edges,
    page_rows,
    page_schedule,
    release_finished_rows,
    release_page_rows,
    stored_data_refusal,
)
from parallax.core.temporal_read import Edge, Pin, TemporalShape
from parallax.snapshot._publication._root import RootView

__all__ = ["edge_pin", "publication_issue", "publish_roots", "require_publishable"]

_NO_ORIGINS: Final[Mapping[int, ReadEvidence]] = MappingProxyType({})


def publication_issue(root: RootView) -> StoredDataIssueInput | None:
    """The first stored-data finding ``root`` publishes, in node order after
    its own unreadable identity."""
    if not root.has_issues:
        return None
    invalid = root.invalid_root
    if invalid is not None:
        return invalid.issues[0]
    for node in range(len(root)):
        issues = root.issues(node)
        if issues:
            return issues[0]
    raise AssertionError("an issue-bearing Root View has no issue")  # pragma: no cover


def require_publishable(root: RootView) -> None:
    """Refuse an issue-bearing root before identity or object derivation."""
    issue = publication_issue(root)
    if issue is not None:
        raise stored_data_refusal(issue)


def edge_pin(edge: Edge) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (the Python binding: each
    milestone-set root is edge-pinned at its own milestone's from-instant).

    An axis the Entity does not declare answers absent on both sides, so the
    rendering needs no per-entity axis list of its own.
    """
    return Pin(tx_time=edge.tx_time_or_none, valid_time=edge.valid_time_or_none)


def publish_roots[T](
    page: Page,
    publish_root: Callable[[RootView, int], tuple[T, ...]],
    model: Metamodel,
    *,
    atomic: bool = False,
    ordinal_offset: int = 0,
    milestones: TemporalShape | None = None,
    origins: Mapping[int, ReadEvidence] = _NO_ORIGINS,
) -> Iterator[T]:
    """Publish ``page``'s roots in result order through one Root View the pass
    re-points at each root, handing it with the root's result ordinal to
    ``publish_root``.

    Each root is resolved, judged, and given its ``origins`` before the Page
    storage it finished with is released, and only then published. A root of a
    ``milestones`` read stands at its own milestone's edge. An ``atomic``
    publication publishes nothing until every root has been, and defers judging
    a root's states past its claim comparison when every root's family carries
    write evidence, which ``model``'s Optimistic Lock Facet answers.
    """
    rows = page_rows(page)
    observer = page_cadence(page)
    schedule = page_schedule(page, opt_lock.write_evidence(model), atomic=atomic)
    root = RootView(rows, schedule, origins=origins)
    resolve = root._resolve_root  # pyright: ignore[reportPrivateUsage] - the pass owns re-pointing
    edges = page_edges(page, milestones)
    if atomic:
        prepared: list[T] = []
        published_counts = array("I")
        for position, edge in enumerate(edges):
            resolve(position, rows.pin if edge is None else edge_pin(edge))
            release_finished_rows(page, schedule, position, root.reached)
            values = publish_root(root, ordinal_offset + position)
            prepared.extend(values)
            published_counts.append(len(values))
        release_page_rows(page)
        prepared_position = 0
        for position, count in enumerate(published_counts):
            yield from prepared[prepared_position : prepared_position + count]
            prepared_position += count
            observer.root_published(ordinal_offset + position)
        return
    for position, edge in enumerate(edges):
        resolve(position, rows.pin if edge is None else edge_pin(edge))
        release_finished_rows(page, schedule, position, root.reached)
        yield from publish_root(root, ordinal_offset + position)
        observer.root_published(ordinal_offset + position)
