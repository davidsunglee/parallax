from __future__ import annotations

from array import array
from collections.abc import Callable, Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Final, NamedTuple

from parallax.core._execution._unit_work.evidence import ReadEvidence
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
from parallax.snapshot._publication._graph_view import GraphView

__all__ = [
    "SharedGraph",
    "milestone_pin",
    "publication_issue",
    "publish_roots",
    "publish_shared_roots",
    "require_publishable",
]

_NO_READ_EVIDENCE: Final[Mapping[int, ReadEvidence]] = MappingProxyType({})


class SharedGraph[T](NamedTuple):
    """One Page's published Shared Graph: its ``view``, the value of each valid
    root in result order, and the positions that publish alone."""

    view: GraphView
    roots: tuple[T, ...]
    invalid: frozenset[int]


def publication_issue(root: GraphView) -> StoredDataIssueInput | None:
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


def require_publishable(root: GraphView) -> None:
    """Refuse an issue-bearing root before identity or object derivation."""
    issue = publication_issue(root)
    if issue is not None:
        raise stored_data_refusal(issue)


def milestone_pin(edge: Edge) -> Pin:
    """One milestone's own edge, rendered as the :class:`Pin` a milestone-set root
    stands at.

    An axis the Entity does not declare answers absent on both sides, so the
    rendering needs no per-entity axis list of its own.
    """
    return Pin(tx_time=edge.tx_time_or_none, valid_time=edge.valid_time_or_none)


def publish_roots[T](
    page: Page,
    publish_root: Callable[[GraphView, int], tuple[T, ...]],
    model: Metamodel,
    *,
    atomic: bool = False,
    ordinal_offset: int = 0,
    milestones: TemporalShape | None = None,
    read_evidence: Mapping[int, ReadEvidence] = _NO_READ_EVIDENCE,
) -> Iterator[T]:
    """Publish ``page``'s roots in result order through one Root View the pass
    re-points at each root, handing it with the root's result ordinal to
    ``publish_root``.

    Each root is resolved, judged, and given its ``read_evidence`` before the Page
    storage it finished with is released, and only then published. A root of a
    ``milestones`` read stands at its own milestone's edge. An ``atomic``
    publication publishes nothing until every root has been, and defers judging
    a root's states past its stored-values comparison when every root's family
    settles a write against its observation, which ``model``'s Concurrency
    Facet answers; a
    proved level's states were judged as its rows were recorded and are not
    deferred.
    """
    rows = page_rows(page)
    observer = page_cadence(page)
    schedule = page_schedule(page, model, atomic=atomic)
    root = GraphView(rows, schedule, read_evidence=read_evidence)
    resolve = root.resolve_root
    edges = page_edges(page, milestones)
    if atomic:
        prepared: list[T] = []
        published_counts = array("I")
        for position, edge in enumerate(edges):
            resolve(position, rows.pin if edge is None else milestone_pin(edge))
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
        resolve(position, rows.pin if edge is None else milestone_pin(edge))
        release_finished_rows(page, schedule, position, root.reached)
        yield from publish_root(root, ordinal_offset + position)
        observer.root_published(ordinal_offset + position)


def publish_shared_roots[T](
    page: Page,
    publish_root: Callable[[GraphView, int], tuple[T, ...]],
    publish_shared_graph: Callable[[GraphView, Sequence[int]], tuple[T, ...]],
    model: Metamodel,
    *,
    atomic: bool = False,
    ordinal_offset: int = 0,
    milestones: TemporalShape | None = None,
    read_evidence: Mapping[int, ReadEvidence] = _NO_READ_EVIDENCE,
) -> Iterator[T]:
    """Publish ``page``'s valid roots as one Shared Graph through
    ``publish_shared_graph`` and each invalid root alone through ``publish_root``,
    or every root through :func:`publish_roots` when the Page has nothing to
    share, cannot share, or fails in the attempt.

    A ``milestones`` read skips the attempt, because each of its roots stands at
    its own pin.
    """
    shared = (
        None
        if milestones is not None
        else _attempt_shared_graph(page, publish_shared_graph, model, read_evidence)
    )
    if shared is None:
        yield from publish_roots(
            page,
            publish_root,
            model,
            atomic=atomic,
            ordinal_offset=ordinal_offset,
            milestones=milestones,
            read_evidence=read_evidence,
        )
        return
    yield from _deliver_in_result_order(page, shared, publish_root, ordinal_offset)


def _attempt_shared_graph[T](
    page: Page,
    publish_shared_graph: Callable[[GraphView, Sequence[int]], tuple[T, ...]],
    model: Metamodel,
    read_evidence: Mapping[int, ReadEvidence],
) -> SharedGraph[T] | None:
    """``page``'s Shared Graph, or ``None`` for the per-root pass.

    The schedule is the one without last uses: the Page stays whole until the
    publish, and computing last uses walks every root's reach, which is the cost
    sharing removes. A failure here releases nothing, so it resurfaces at the same
    root when the per-root pass meets it.
    """
    rows = page_rows(page)
    view = GraphView(rows, page_schedule(page, model, atomic=False), read_evidence=read_evidence)
    try:
        invalid = view.resolve_shared_roots()
        if invalid is None:
            return None
        positions = [position for position in range(len(rows.roots)) if position not in invalid]
        return SharedGraph(view, publish_shared_graph(view, positions), invalid)
    except Exception:
        return None


def _deliver_in_result_order[T](
    page: Page,
    shared: SharedGraph[T],
    publish_root: Callable[[GraphView, int], tuple[T, ...]],
    ordinal_offset: int,
) -> Iterator[T]:
    """Publish each invalid root through ``shared``'s view, whose Shared Graph is
    published and done with, then release ``page`` and hand over every root in
    result order."""
    rows = page_rows(page)
    observer = page_cadence(page)
    view = shared.view
    published_alone: dict[int, tuple[T, ...]] = {}
    for position in sorted(shared.invalid):
        view.resolve_root(position, rows.pin)
        published_alone[position] = publish_root(view, ordinal_offset + position)
    positions = range(len(rows.roots))
    release_page_rows(page)
    shared_roots = iter(shared.roots)
    for position in positions:
        if position in published_alone:
            yield from published_alone[position]
        else:
            yield next(shared_roots)
        observer.root_published(ordinal_offset + position)
