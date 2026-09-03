"""Delivering one streamed read page by page, and proving the delivery ended.

Placement-neutral: an ordinary streamed read case and a Unit Work Scenario's
streamed read step are the same delivery over different authored lists, so both
reach :func:`deliver_stream` with the read they belong to and the name of the
list its pages were authored in.

A streamed ``statements`` list is the pages' own ``1 + L`` groups concatenated,
so the page partition is recovered as the delivery runs rather than sliced up
front: a page's Include levels consume only as much of the remaining list as that
page's own roots reach, and a level whose parents gathered no keys consumes
nothing at all. :mod:`.seek` owns what each page's SQL must say; what is owned
here is how far the list is walked and what proves it is exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..case import Case, Entity
from ..case_assertions import CaseFailure, coerce_identity_key, scalars_equal
from . import execute, graph, includes, materialize, seek
from .executor import ReadExecutor


@dataclass(frozen=True, slots=True)
class _StreamPage:
    """One page of a streamed delivery.

    ``root_rows`` is what the page KEEPS; ``returned`` is what its statement
    answered, which is one more wherever a further page follows. ``consumed``
    counts the CHILD-level statements the page took off the flat authored list,
    which is where the next page's root statement begins.
    """

    root_rows: list[materialize.PublishedRow]
    nodes: list[dict[str, Any] | None]
    coordinates: list[tuple[Any, ...]]
    consumed: int
    returned: int


def _stream_page(
    case: Case,
    reader: ReadExecutor,
    source: str,
    query: dict[str, Any],
    steps: list[includes.FetchStep],
    root_entity: Entity,
    terms: list[seek.ContinuationTerm],
    root_sql: str,
    root_binds: list[Any],
    levels: list[tuple[str, list[Any]]],
    aliases: list[str],
    requested: int,
    lookahead: bool,
) -> _StreamPage:
    """Execute one page of a streamed read and publish the roots it keeps.

    A page IS an eager read of a bounded root query (`m-snapshot-read` *Streamed
    delivery*), so it is graded by the graders an eager read of the same Object
    Query gets: the deep-fetch levels and their assembly where the query declares
    Include Paths, the single-statement instance-form materialization where it
    declares none. What the page adds is that it consumes a PREFIX of *levels* and
    reports how much, because the statements after it belong to later pages.

    A page asking for a lookahead root reads one MORE than it may deliver, so a
    full result is cut back to the batch before anything below it is fetched:
    the discarded root gathers no key, receives no child, and is read again by
    the page that delivers it.
    """
    raw = execute.query_rows(case, reader, root_sql, root_binds)
    returned = materialize.materialize_read(case, seek.without_captured_coordinates(raw, aliases))
    keep = requested - 1 if lookahead and len(returned) == requested else len(returned)
    root_rows = returned[:keep]
    coordinates = [
        seek.evaluated_coordinate(published, raw_row, terms, aliases)
        for published, raw_row in zip(root_rows, raw[:keep], strict=True)
    ]
    if not includes.query_has_includes(query):
        narrowed = materialize.narrow_to_variant_columns(case, root_rows)
        kept: list[dict[str, Any] | None] = [
            graph.graph_node(case, root_entity, row) for row in narrowed
        ]
        return _StreamPage(
            root_rows=root_rows,
            nodes=kept,
            coordinates=coordinates,
            consumed=0,
            returned=len(returned),
        )

    executed = includes.execute_fetch_levels(case, reader, source, query, steps, root_rows, levels)
    assembled = graph.assemble_graph(case, query, steps, root_rows, executed.children_by_hop)
    nodes: list[dict[str, Any] | None] = list(assembled.get(root_entity.name, []))
    return _StreamPage(
        root_rows=root_rows,
        nodes=nodes,
        coordinates=coordinates,
        consumed=executed.consumed,
        returned=len(returned),
    )


def _binds_equal(
    authored: list[Any],
    derived: list[Any],
    neutral_types: list[str | None],
) -> bool:
    """Compare structural binds exactly and typed coordinates under their declarations."""
    if len(authored) != len(derived) or len(derived) != len(neutral_types):
        return False
    return all(
        scalars_equal(left, right, None)
        if neutral_type is None
        else execute.coordinate_bind_equal(left, right, neutral_type)
        for left, right, neutral_type in zip(authored, derived, neutral_types, strict=True)
    )


@dataclass(frozen=True, slots=True)
class StreamDelivery:
    """What one streamed delivery published: its root rows, and the graph nodes
    assembled from them, concatenated across every page in delivery order."""

    root_rows: list[materialize.PublishedRow]
    nodes: list[dict[str, Any] | None]


def deliver_stream(case: Case, reader: ReadExecutor, source: str) -> StreamDelivery:
    """Execute a streamed delivery page by page and assert the pages it authored.

    A streamed statement list is the pages' own ``1 + L`` groups concatenated
    (`m-case-format` *Streamed reads*), so the page partition has to be recovered
    before anything can be graded against it: each page's root statement is
    executed, its child levels consume as much of the remaining list as the
    page's own roots reach, and the next page starts where that stopped.

    ``case`` is the READ this delivery belongs to, which in the member's second
    placement is a scenario step presented as one; ``source`` names where that
    read authored its pages — ``then.statements``, or the step's own
    ``statements`` — so one oracle grades both placements and a failure still
    points at the list it read.

    Four properties are then derived independently of the authored SQL, so a
    delivery that reached the right rows the wrong way fails rather than passing
    on its graph alone. The requested page size is `batchSize` plus the one
    LOOKAHEAD root a page reads past its batch, and a page returns at most that
    many roots and delivers at most the batch; where a declared ``limit`` leaves
    no more than a batch undelivered the page it caps asks for exactly that
    remainder and reads no lookahead root at all, an authored limit being a hard
    database-read boundary. A page after the first seeks past the Continuation
    Order coordinates of the root the page before it KEPT last — never the
    lookahead root it discarded — composed and lowered by :mod:`.seek` from the
    query's own ``orderBy``, the model's primary key, and a milestone-set read's
    own edge columns rather than read off the golden — its coordinates graded as
    binds and the direction it compares them in, which no bind carries, graded as
    the comparators it spells. And exhaustion is proven rather than assumed: a
    page that comes back short of what it asked for ends the delivery, so a
    result filling its final page exactly costs no terminal statement, and a page
    reading a full lookahead is followed by another.

    Every page also projects one hidden coordinate cell per Continuation Order
    term, which is what a delivery advances on, and both halves of that are
    derived: the cells' own expressions from the order, and the Document Paths
    they bind ahead of everything the page's `where` clause binds.

    The FIRST page's remaining binds are the baseline the later pages are measured
    against rather than an independently derived list: the harness executes
    authored goldens rather than compiling the query, so a predicate's binds have
    no second source here. What is derived is everything the pages after it must
    agree with — which is why a first page carrying a seek it should not have is
    caught by the levels its own too-narrow result no longer feeds, and a
    continuing page that stopped seeking by its SQL text rather than its binds.

    Two continuing pages carry the same statement text where their coordinates
    are null in the same places, and only there: a Sort Key over a nullable
    member seeks a null coordinate through a null check and a non-null one
    through a comparison, so the two spell different statements over the same
    ordering. Where they differ, the difference is graded rather than allowed —
    every continuing page is the first page's statement with one conjunct
    spliced in, spelling the seek its own coordinates compose.

    The published roots are the concatenation of the pages', which is what the
    caller compares to its own result oracle, because over the storage a case's
    model describes — the only storage a fixture can seed — a page size changes
    neither membership nor order nor what a root carries.
    """
    dialect = reader.dialect
    query = case.object_query
    batch_size = case.batch_size
    entries = [
        (sql, case.statement_binds(index, dialect))
        for index, sql in enumerate(case.golden_statements(dialect))
    ]
    steps = includes.fetch_steps(case.model, query) if includes.query_has_includes(query) else []
    root_entity = case.model.entity(query["target"])
    terms = seek.continuation_order(case, query, root_entity, dialect)
    aliases = seek.capture_aliases(case, terms)
    limit = query.get("limit")

    nodes: list[dict[str, Any] | None] = []
    root_rows: list[materialize.PublishedRow] = []
    carried_binds: list[Any] = []
    first_root_sql = ""
    seek_shapes: dict[tuple[bool, ...], str] = {}
    cursor: tuple[Any, ...] = ()
    index = 0
    page = 0
    while True:
        if index >= len(entries):
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) ends after {page} page(s), "
                f"but the delivery is not exhausted — the last page returned every root "
                f"it asked for, lookahead included, which proves another page follows. "
                f"Author that page's root statement, or a final page shorter than the "
                f"size it asked for."
            )
        root_sql, authored = entries[index]
        index += 1
        remaining = None if limit is None else limit - len(root_rows)
        lookahead = remaining is None or remaining > batch_size
        requested = batch_size + 1 if remaining is None or lookahead else remaining
        composed: seek.ComposedSeek | None = None
        if page == 0:
            first_root_sql = root_sql
            seek.refuse_an_uncaptured_page(case, dialect, source, root_sql, terms, aliases)
            cells = seek.capture_binds(terms)
            carried_binds = list(authored[:-1])
            expected_binds: list[Any] = [*cells, *carried_binds[len(cells) :], requested]
            expected_bind_types: list[str | None] = [None] * len(expected_binds)
        else:
            composed = seek.composed_seek(terms, cursor)
            spliced_at, _spliced_to = seek.seek_splice(first_root_sql, root_sql)
            seek_bind_position = root_sql[:spliced_at].count("?")
            expected_binds = [
                *carried_binds[:seek_bind_position],
                *composed.binds,
                *carried_binds[seek_bind_position:],
                requested,
            ]
            expected_bind_types = [
                *([None] * seek_bind_position),
                *composed.neutral_types,
                *([None] * (len(carried_binds) - seek_bind_position + 1)),
            ]
        if not _binds_equal(authored, expected_binds, expected_bind_types):
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) page {page + 1} root binds "
                f"{authored!r} != {expected_binds!r}. A page binds the query's own binds "
                f"and — after the first page — the seek past the Continuation Order "
                f"coordinates of the root the previous page delivered LAST, spliced in "
                f"where the two statements diverge, then the size it is asking for."
            )
        if composed is not None:
            seek.refuse_a_drifting_page(
                seek.PageText(case, dialect, source, page, first_root_sql, root_sql),
                composed,
                cursor,
                seek_shapes,
            )

        executed = _stream_page(
            case,
            reader,
            source,
            query,
            steps,
            root_entity,
            terms,
            root_sql,
            authored,
            entries[index:],
            aliases,
            requested,
            lookahead,
        )
        index += executed.consumed
        returned = executed.returned
        if returned > requested:
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) page {page + 1} returned "
                f"{returned} root(s) for a requested {requested}. A page's own `limit` "
                f"bounds what its statement may answer."
            )
        nodes.extend(executed.nodes)
        root_rows.extend(executed.root_rows)
        if executed.coordinates:
            cursor = tuple(coerce_identity_key(carrier) for carrier in executed.coordinates[-1])
        page += 1
        if not lookahead or returned < requested:
            break

    if index != len(entries):
        raise CaseFailure(
            f"{case.path.name}: {source} ({dialect}) lists {len(entries) - index} "
            f"statement(s) after the delivery ended. A stream stops at its first page "
            f"short of what it asked for, so nothing follows it."
        )

    return StreamDelivery(root_rows=root_rows, nodes=nodes)
