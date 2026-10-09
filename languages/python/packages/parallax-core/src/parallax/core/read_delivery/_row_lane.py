from __future__ import annotations

from array import array
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from parallax.core import opt_lock, temporal_read
from parallax.core.db_port import DatabaseConnection
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.execution_lifecycle._activity import INERT, DatabaseCallScope
from parallax.core.metamodel import Metamodel
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery._convert import complete_occurrences
from parallax.core.read_delivery._fetch import execute_read
from parallax.core.read_delivery._page import (
    INERT_OBSERVER,
    EntityState,
    InvalidData,
    LogicalKey,
    MaterializationObserver,
    Page,
    PageRows,
    VersionAttributes,
    attribute_state,
    diagnosis,
    observed_edge,
    observed_object_key,
    observed_version,
    page_cadence,
    page_rows,
    release_page_rows,
    root_last_uses,
    state_for,
    stored_data_refusal,
)
from parallax.core.read_delivery._page_reader import FlatPageRequest, FlatPageResult, PageReader
from parallax.core.read_delivery._read_plan import UNCACHED_READ_PLANNER, ReadPlanner
from parallax.core.read_delivery._row_converter import RowPublisher
from parallax.core.temporal_read import resolved_query_pin
from parallax.core.unit_work import Concurrency

__all__ = [
    "PublishedRow",
    "RowsResult",
    "admitted_member_rows",
    "completed_member_row",
    "find_rows",
    "publishable_member_rows",
]


type PublishedRow = Mapping[str, object] | InvalidData[Mapping[str, object]]
"""One row-form result position: the transformed row itself, or the record a row
whose stored state contradicted the model publishes in its place.

The values lane's element type is the same union both public materializers
publish, one result position at a time — a row-form read has no graph, so its
own root IS the row."""


@dataclass(frozen=True, slots=True)
class RowsResult:
    """A row-form read's published rows.

    ``rows`` is every result position in result order, already eager, detached,
    and immutable, keyed as the read PROJECTED it — physical columns plus the
    synthetic ``familyVariant`` where the compiled read materializes one.
    ``edition`` is the Model Edition the read was served under, retained for
    later access exactly as the graph-form envelopes retain theirs.
    """

    rows: tuple[PublishedRow, ...]
    edition: str


def find_rows(
    query: ResolvedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    edition: str,
    versions: VersionAttributes,
    preference: Concurrency | None = None,
    read: DatabaseCallScope = INERT,
    observer: MaterializationObserver = INERT_OBSERVER,
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> RowsResult:
    """The row-form read: one statement and one Page of transformed roots.

    The transformed row is the returned representation, so the values lane builds
    no object graph. It does build a Page, whose judged states are what each
    row is classified by: a row whose own stored state contradicted the model
    publishes its :class:`InvalidData` record in place of itself, carrying the
    transformed row wherever its identity decoded. ``versions`` names the
    explicit version Attribute such a record publishes its observed version
    from, and ``edition`` is the Model Edition ``model`` was selected under,
    which the result retains.

    A row-form read materializes no relationships; the read gate refuses a
    request that asks this lane for one before any I/O, so the plan reaching
    here carries no level to drop.
    """
    meta = model.meta
    plan = planner.plan(
        edition=edition,
        model=model,
        dialect=port.dialect,
        query=query,
        result_form="row",
        preference=preference,
    )
    compiled, converter = plan.root_read()

    stage = PageReader(observer).read_page(
        FlatPageRequest(
            model,
            compiled,
            lambda: execute_read(port, compiled, read),
            resolved_query_pin(query.temporal),
            converter,
        )
    )
    return RowsResult(
        rows=_published_rows(stage, meta, versions, converter.row_publisher()), edition=edition
    )


def _published_rows(
    stage: FlatPageResult,
    meta: Metamodel,
    versions: VersionAttributes,
    publisher: RowPublisher,
) -> tuple[PublishedRow, ...]:
    """One published element per flat root, in result order, published atomically.

    Every root's state is judged and its row published before any is returned,
    and Page storage is released as roots finish with it: a root's raw row once
    it is judged, and everything a later root cannot reach once the last root
    reaching it has published. Families whose roots all carry write evidence
    take the same last-use release a graph root gets.
    """
    page = stage.page
    rows = page_rows(page)
    observer = page_cadence(page)
    keys = opt_lock.view(meta)
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
    temporal = temporal_read.view(meta)
    published: list[PublishedRow] = []
    for position, root in enumerate(rows.roots):
        if _keyless(rows, root):
            observer.occurrences_reached(0)
            state = state_for(rows, root)
            published.append(
                cast(
                    "InvalidData[Mapping[str, object]]",
                    InvalidData(
                        issues=frozenset(diagnosis(issue, None) for issue in state.findings),
                        data=None,
                        object_key=None,
                        version=None,
                        edge=None,
                        ordinal=position,
                    ),
                )
            )
            continue
        if deferred_states:
            observer.occurrences_reached(1)
            state = state_for(rows, root)
        else:
            state = state_for(rows, root)
            observer.occurrences_reached(1)
        layout = rows.layouts[root]
        if last_uses is None:
            _release_raw_row(rows, root)
        else:
            _release_finished_root(rows, position, root, last_uses)
        detached = MappingProxyType(
            publisher.publish(layout.concrete, state.member_row, stage.variants[position])
        )
        if not state.findings:
            published.append(detached)
            continue
        published.append(
            cast(
                "InvalidData[Mapping[str, object]]",
                _invalid_root(meta, versions, temporal, layout, state, position, detached),
            )
        )
    release_page_rows(page)
    for position in range(len(published)):
        observer.root_published(position)
    return tuple(published)


def publishable_member_rows(page: Page) -> Generator[tuple[object, ...]]:
    """Each flat root's judged positional member row, by reference and in result
    order, refusing the first root that holds invalid stored data.

    The acquisition peer of the values lane's in-band classification: a read
    whose rows become write evidence has no channel for a stored-data verdict,
    so a root's findings refuse it before it contributes anything. Each root is
    judged only when the caller asks for it, and its raw row is released once
    judged.
    """
    rows = page_rows(page)
    for root in rows.roots:
        state = state_for(rows, root)
        if state.findings:
            raise stored_data_refusal(state.findings[0])
        _release_raw_row(rows, root)
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
    :func:`completed_member_row` judges those inputs later, if at all. Each
    root is judged only when the caller asks for it, and its raw row is
    released once judged.
    """
    rows = page_rows(page)
    for root in rows.roots:
        state = attribute_state(rows, root)
        if state.findings:
            raise stored_data_refusal(state.findings[0])
        _release_raw_row(rows, root)
        yield state.member_row


def completed_member_row(layout: EntityLayout, row: tuple[object, ...]) -> tuple[object, ...]:
    """A member row :func:`admitted_member_rows` produced for ``layout``'s
    Entity, its Value Object occurrences judged as an ordinary read judges
    them, refusing the first that holds invalid stored data. No statement runs
    and no Page is involved."""
    member_row, findings = complete_occurrences(layout, row)
    if findings:
        raise stored_data_refusal(findings[0])
    return member_row


def _invalid_root(
    meta: Metamodel,
    versions: VersionAttributes,
    temporal: temporal_read.TemporalFacet,
    layout: EntityLayout,
    state: EntityState,
    position: int,
    detached: Mapping[str, object],
) -> InvalidData[object]:
    """A keyed root's record: the transformed row it still publishes, beside the
    diagnosis attributed to the identity, version, and edge it observed."""
    key = observed_object_key(layout, state.member_row, state.findings)
    return InvalidData(
        issues=frozenset(diagnosis(issue, key) for issue in state.findings),
        data=detached,
        object_key=key,
        version=observed_version(meta, versions, layout, state.member_row),
        edge=observed_edge(temporal, layout, state.member_row),
        ordinal=position,
    )


def _keyless(rows: PageRows, root: int) -> bool:
    """Whether ``root``'s own stored primary key could not be read, which leaves
    it a result position with no identity behind it."""
    return rows.keys[root] is None and any(
        issue.code.startswith("stored-data-primary-key-") for issue in rows.issues[root]
    )


def _release_raw_row(rows: PageRows, root: int) -> None:
    """Release ``root``'s raw member row once judged, except a keyless claim's
    still-pending one."""
    if not isinstance(rows.member_rows, list):  # pragma: no cover - a sealed Page holds lists
        return
    if rows.keys[root] is not None or not rows.decoders.pending(root):
        rows.member_rows[root] = ()


def _release_finished_root(
    rows: PageRows, position: int, root: int, last_uses: tuple[array[int], array[int]]
) -> None:
    """Release ``root``'s Page storage once no later root can reach it, and its
    logical state once the last root sharing it has been judged."""
    if not isinstance(rows.member_rows, list):  # pragma: no cover - a sealed Page holds lists
        return
    projection_last, logical_last = last_uses
    member_rows = rows.member_rows
    if projection_last[root] != position:  # pragma: no cover - a flat root is its own reach
        if rows.keys[root] is not None or not rows.decoders.pending(root):
            member_rows[root] = ()
        return
    keys = cast("list[LogicalKey | None]", rows.keys)
    logical_ids = cast("list[int]", rows.logical_ids)
    member_rows[root] = ()
    logical = logical_ids[root]
    rows.issues.release(root)
    keys[root] = None
    cast("list[object]", rows.view_rows)[root] = ()
    rows.overwritten_edges.release(root)
    cast("list[object]", rows.witnesses)[root] = None
    rows.decoders.release(root)
    logical_ids[root] = 0
    if logical_last[logical] == position:
        rows.judged_states.release_logical(logical)
        logical_last[logical] = -1
