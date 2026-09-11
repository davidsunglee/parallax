"""The read lanes: a case's ``when.objectQuery`` compiled to its statement, or
run through the production read seams and reported as the observation its
``then`` member grades.

``compile_read_case`` lowers the query purely, with no database. The five run
entry points route it through production's own reads — the values lane for
`then.rows`, the public Wire read for `then.graph` and `then.graphs`, and the
Wire stream for a case declaring a `when.stream` page size — so planning,
compilation, execution, conversion, classification, and materialization are
production's, and what is left here is the envelope: the emissions and round
trips read off the delivered lifecycle, the wire rendering of each published
row or root, the root key and milestone pin a graph is reported under, and the
stored-data records a classified root publishes in place of itself.

Every run lane builds its own Handle through :func:`case_database`, applies
the case's ``given.corrupt`` ahead of the read, and closes the Handle where
the case that needed it ends. Grading the observation against ``then`` is the
adapter's.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Literal, cast

from parallax.conformance import _case_ingress, case_format
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._database_control import CaseDatabase
from parallax.conformance._lifecycle_observation import (
    LifecycleObservation,
    LifecycleRun,
    lifecycle_run,
)
from parallax.conformance._mechanism import case_document, envelope
from parallax.conformance._mechanism.envelope import READ_ERRORS, Emission, EngineError
from parallax.conformance._mechanism.given_state import apply_given_corrupt
from parallax.conformance._mechanism.model_facts import (
    canonicalize_read,
    case_entity,
    case_serving_model,
    declaring_metadata,
    load_case_metamodel,
)
from parallax.conformance._mechanism.transaction_control import transact, underlying
from parallax.core.base import normalize_instant
from parallax.core.continuation import ContinuationError
from parallax.core.db_port import Row
from parallax.core.dialect import dialect_for
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    MemberIdentity,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.sql_gen._compile import CompiledRead, compile_read
from parallax.core.temporal_read import Pin, scans_an_axis
from parallax.core.unit_work import Clock, Concurrency
from parallax.snapshot import handle

__all__ = [
    "case_database",
    "compile_read_case",
    "run_graph_case",
    "run_graphs_case",
    "run_read_case",
    "run_stream_case",
    "run_streamed_graphs_case",
]


def case_database(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: ExecutionLifecycleProvider,
    *,
    clock: Clock | None = None,
) -> handle.Database:
    """A Handle connected from ``port`` serving ``case``'s model under its edition.

    The caller owns what comes back: a Handle opens a runtime of its own, so
    every lane below composes one inside a ``with`` and the runtime is closed
    where the case that needed it ends.
    """
    return handle.Database.connect(
        port, case_serving_model(case), clock=clock, lifecycle_provider=lifecycle
    )


def _read_query(case: case_format.Case, model: AcceptedMetamodel) -> ObjectQueryNode:
    when = case.document.get("when")
    if not isinstance(when, Mapping):
        raise EngineError(f"{case.path.name}: read case has no `when`")
    body = cast("Mapping[str, object]", when)
    if "objectQuery" not in body:
        raise EngineError(f"{case.path.name}: read case has no `objectQuery`")
    return _case_ingress.normalize_case_query(deserialize_query(body["objectQuery"]), model)


def _result_form(case: case_format.Case) -> Literal["row", "instance"]:
    """The read's result form from its asserted result member (m-case-format / m-sql).

    A top-level read case declares its consumption lane by which result member it
    asserts: ``then.graph`` / ``then.graphs`` materialize instances (instance-form,
    the object lane), so the read projects the value-object document columns (slot
    4); every other read (``then.rows``) is row-form (the values lane) and omits
    them.
    """
    then = case.document.get("then")
    if isinstance(then, Mapping) and ("graph" in then or "graphs" in then):
        return "instance"
    return "row"


def _read_case_concurrency(case: case_format.Case) -> Concurrency | None:
    """A read-shape case's own unit-of-work Concurrency Preference — the
    read-shape half of the `when.uow` threading.

    `when.uow.concurrency` when the case declares it; ``None`` otherwise, which
    is the plain, non-transactional `db.find` surface every other reachable read
    models and which takes no lock under any preference.

    Absent `when.uow` there is no participation to derive a strategy from at
    all, so this seam grants no module-scoped default: the `m-read-lock`
    witnesses whose goldens carry the shared-row-lock suffix declare the
    preference that produces it, exactly as `m-case-format` requires of any
    case whose SQL depends on the effective choice.
    """
    when = case.document.get("when")
    uow = cast("Mapping[str, object]", when).get("uow") if isinstance(when, Mapping) else None
    if isinstance(uow, Mapping):
        concurrency = cast("Mapping[str, object]", uow).get("concurrency")
        if concurrency in ("locking", "optimistic"):
            return concurrency
    return None


def _compile_statement(case: case_format.Case, dialect_name: str) -> CompiledRead:
    if case.shape != "read":
        raise EngineError(
            f"{case.path.name}: only `read`-shape compile is implemented (a write/rejected/"
            f"scenario case compiles through its own dedicated lane; shape={case.shape})"
        )
    model = load_case_metamodel(case)
    query = _read_query(case, model)
    dialect = dialect_for(dialect_name)
    try:
        metadata = case_entity(model, query.target.canonical)
        form: Literal["rows", "graph"] = "graph" if _result_form(case) == "instance" else "rows"
        entity_query = canonicalize_read(query, metadata, model, form=form)
        return compile_read(
            entity_query,
            model,
            dialect,
            result_form=_result_form(case),
            lock=handle.entity_read_lock(model, metadata.identity, _read_case_concurrency(case)),
        )
    except READ_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def compile_read_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a read case to its ordered emissions and round-trip count."""
    statement = _compile_statement(case, dialect_name).statement
    emission = Emission("/objectQuery", statement)
    return [emission], 1


def run_read_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], list[Row], int]:
    """Run a row-form read case through the production values lane.

    The whole lane is ``db.read_rows`` / ``tx.read_rows``: canonicalization,
    compilation, the read-lock suffix, the Database Call, `familyVariant`
    materialization, and the round-trip count are all production's, and what is
    left here is wire rendering and the case's own routing. A row this adapter
    reports is the row production materialized, not a row this adapter
    re-derived from the query a second time.

    A case declaring a `when.uow` Concurrency Preference is RUN in a transaction
    (`m-read-lock` "an in-transaction object find that intends to write acquires
    a shared row lock"): the lock suffix is derived inside production from that
    preference and the read target's own Optimistic Lock Facet, exactly as it is
    for a developer's ``tx.find``, rather than from a lock this lane asked a
    compiler for while executing outside any boundary. Begin and commit reach the
    database but are no Database Call, so the round trips a locking case reports
    are the read's alone.

    The adapter returns **managed** Python values (``Decimal``, ``datetime``,
    ``UUID``, ``bytes``, …); the conformance harness grades in **wire space**, so
    each observed row is rendered to canonical wire form here — the grader-side
    serialization the ``m-db-port`` boundary fixes, keeping the adapter free of any
    wire/grading logic and the observation envelope JSON-serializable.

    Wire rendering FOLLOWS production's own row transform, because that transform
    may itself produce a managed value: a Relational Document Layout read projects
    one Structured Column and fans it out into members decoded by their declared
    Neutral Type (`m-sql`), so a `timestamp` member arrives here as a `datetime`
    exactly as the same member does when it is a column of its own. Rendering
    first would hand the wire that member's document spelling instead, making one
    logical value observably different under the two layouts.
    """
    model = load_case_metamodel(case)
    query = _read_query(case, model)
    observed = lifecycle_run(lifecycle).observation()
    apply_given_corrupt(case, model, port)
    with case_database(case, port, observed.provider) as db:
        concurrency = _read_case_concurrency(case)
        try:
            result = (
                underlying(lambda: db.read_rows(query))
                if concurrency is None
                else transact(db, lambda tx: tx.read_rows(query), concurrency=concurrency)
            )
        except READ_ERRORS as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        return (
            _read_emissions(observed),
            [
                ActualWireProjection(model).published_row(query, _conforming_row(case, row))
                for row in result.rows
            ],
            observed.round_trips,
        )


def _conforming_row(case: case_format.Case, row: handle.PublishedRow) -> Mapping[str, object]:
    """One published row-form element as the row a `then.rows` case grades.

    A row whose stored state contradicted the model publishes its record instead
    of itself, and the row-form observation has no place to carry one, so this
    lane names the shape rather than grading a record as though it were a row.
    Graph-form cases grade `InvalidData` through `then.storedDataIssues`.
    """
    if isinstance(row, handle.InvalidData):
        raise EngineError(
            f"{case.path.name}: a row-form read published an InvalidData record — stored data "
            "that contradicts the model is graded through a `then.graph` case's own "
            "`storedDataIssues`, never as a row"
        )
    return row


# --------------------------------------------------------------------------- #
# Graph reads (m-deep-fetch / m-snapshot-read): the lane runs the PUBLIC Wire   #
# read, so every level's compile, execute, convert, merge, classify, and unwind #
# is production's and a `then.graph` observation IS a Wire result. What is left #
# here is the envelope around it — the root key, the milestone pin, and the     #
# stored-data records a classified root publishes in place of itself.           #
# --------------------------------------------------------------------------- #
def _wire_read(
    case: case_format.Case,
    query: ObjectQueryNode,
    model: AcceptedMetamodel,
    port: CaseDatabase,
    lifecycle: LifecycleRun,
) -> tuple[handle.Snapshot[handle.WireEntity], LifecycleObservation]:
    """One graph-form Wire read of the case's own Object Query, and what it ran.

    The whole lane is ``db.wire.find``: target resolution, validation, deep-fetch
    planning, per-level compilation and execution, row conversion, projection
    merging, root classification, and the finite include-tree unwind are
    production's, and a scanning read answers the milestone-set form from the
    same call, exactly as ``db.find`` does. The statements and the round-trip
    count come back beside the result rather than on it, because a Snapshot
    retains nothing about the execution that produced it.
    """
    observed = lifecycle.observation()
    apply_given_corrupt(case, model, port)
    with case_database(case, port, observed.provider) as db:
        try:
            return underlying(lambda: db.wire.find(query)), observed
        except READ_ERRORS as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc


def run_graph_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], dict[str, list[Row | None]], int, list[dict[str, object]] | None]:
    """Run a single-graph deep-fetch / snapshot read, reporting the Wire result
    production published as the wire `then.graph` shape (root-class-keyed) and,
    for a root whose stored state contradicted the model, the record it published
    in place of itself.
    """
    model = load_case_metamodel(case)
    query = _read_query(case, model)
    snapshot, observed = _wire_read(case, query, model, port, lifecycle_run(lifecycle))
    if not _is_single_graph(query):
        raise EngineError(
            f"{case.path.name}: a `then.graph` case read a milestone SET — "
            "a milestone-set read asserts `then.graphs`"
        )
    roots = snapshot.checked().results()
    return (
        _read_emissions(observed),
        {
            envelope.graph_root_key(query.target.canonical, model): [
                envelope.graph_root(root) for root in roots
            ]
        },
        observed.round_trips,
        _stored_data_records(roots, model),
    )


_STREAM_ERRORS = (*READ_ERRORS, ContinuationError, handle.SnapshotStreamStateError)


def _stream_batch_size(case: case_format.Case) -> int:
    when = case.document.get("when")
    size = (
        case_document.batch_size_of(
            cast("Mapping[str, object]", when), f"{case.path.name}: when.stream"
        )
        if isinstance(when, Mapping)
        else None
    )
    if size is None:
        raise EngineError(f"{case.path.name}: a streamed case declares `when.stream.batchSize`")
    return size


def run_stream_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], dict[str, list[Row | None]], int, list[dict[str, object]] | None]:
    """Run a streamed read through ``db.wire.stream`` and report what it delivered.

    The whole lane is production's streamed read at the case's own declared page
    size: the page plan, each page's `1 + L` execution, per-root publication, and
    the exhaustion verdict. Running the EAGER read and reporting its result would
    match `then.graph` and none of the page partition the case actually states,
    so the streamed entry point is the only one this dispatches to.

    Delivery is the verb and representation is not, so there is one entry point
    rather than a Typed and a Wire one: no corpus model composes Entity Classes,
    which puts the Typed lane out of reach for `find` and `stream` alike — the
    same reason :func:`run_graph_case` drives the Wire read. The Typed/Wire
    equivalence is stated where it can be executed, in each language's API
    Conformance Suite.

    Its statements and round trips come off the delivered lifecycle exactly as
    every other lane's do: a Snapshot Stream publishes one Stream Batch per page
    and every page's Database Calls under it, and each of those carries the
    canonical Lowered Statement it borrowed. Nothing here observes at the
    database port, which carries the driver's own text.
    """
    model = load_case_metamodel(case)
    query = _read_query(case, model)
    if not _is_single_graph(query):
        raise EngineError(
            f"{case.path.name}: a streamed `then.graph` case read a milestone SET — "
            "a milestone-set delivery asserts `then.graphs`"
        )
    roots, observed = _wire_delivery(case, query, model, port, lifecycle)
    return (
        _read_emissions(observed),
        {
            envelope.graph_root_key(query.target.canonical, model): [
                envelope.graph_root(root) for root in roots
            ]
        },
        observed.round_trips,
        _stored_data_records(roots, model),
    )


def run_streamed_graphs_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], list[dict[str, object]], int]:
    """Run a streamed milestone-set read and report its per-milestone graphs.

    :func:`run_stream_case`'s milestone peer, standing to it exactly as
    :func:`run_graphs_case` stands to :func:`run_graph_case`. The delivery is the
    same one — production's streamed read at the case's declared page size — and
    what differs is the observation it is reported as: a milestone-set delivery
    publishes one root per milestone, each standing at its own edge pin, so the
    `{pin, graph}` entries are recovered from those pins rather than from a second
    read per milestone.
    """
    model = load_case_metamodel(case)
    query = _read_query(case, model)
    if _is_single_graph(query):
        raise EngineError(
            f"{case.path.name}: a streamed `then.graphs` case read a single instant — "
            "a single-instant delivery asserts `then.graph`"
        )
    roots, observed = _wire_delivery(case, query, model, port, lifecycle)
    root_key = envelope.graph_root_key(query.target.canonical, model)
    entity = declaring_metadata(model, query.target.canonical)
    graphs_wire: list[dict[str, object]] = [
        {"pin": ActualWireProjection(model).pin(pin), "graph": {root_key: milestone_roots}}
        for pin, milestone_roots in _milestone_groups(entity, roots)
    ]
    return _read_emissions(observed), graphs_wire, observed.round_trips


def _wire_delivery(
    case: case_format.Case,
    query: ObjectQueryNode,
    model: AcceptedMetamodel,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None,
) -> tuple[list[object], LifecycleObservation]:
    """One streamed Wire delivery of ``query``, drained, and what it ran.

    The roots are accumulated for reporting, which is the harness's memory rather
    than a claim about production's: what the caller grades is the roots the
    delivery published, and that needs the whole delivery in hand.
    """
    observed = lifecycle_run(lifecycle).observation()
    apply_given_corrupt(case, model, port)
    with case_database(case, port, observed.provider) as db:
        roots: list[object] = []

        def drained() -> None:
            with db.wire.stream(query, batch_size=_stream_batch_size(case)) as delivery:
                roots.extend(delivery.checked())

        try:
            underlying(drained)
        except _STREAM_ERRORS as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        return roots, observed


def run_graphs_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], list[dict[str, object]], int]:
    """Run a milestone-set (`history` / `asOfRange`) snapshot read, reporting
    production's ordered per-milestone roots as the wire `then.graphs` shape: an
    array of `{pin, graph}` entries, each pin keyed by declared as-of dimension
    spelling.

    A milestone-set Wire Snapshot publishes every milestone's roots in ONE
    ordered result (`m-snapshot-read`), so the per-milestone partition is
    recovered from each root's own edge — the coordinate the pin states — rather
    than from a second read per milestone.
    """
    model = load_case_metamodel(case)
    query = _read_query(case, model)
    snapshot, observed = _wire_read(case, query, model, port, lifecycle_run(lifecycle))
    if _is_single_graph(query):
        raise EngineError(
            f"{case.path.name}: a `then.graphs` case read a single instant — "
            "a single-instant read asserts `then.graph`"
        )
    root_key = envelope.graph_root_key(query.target.canonical, model)
    entity = declaring_metadata(model, query.target.canonical)
    graphs_wire: list[dict[str, object]] = [
        {"pin": ActualWireProjection(model).pin(pin), "graph": {root_key: roots}}
        for pin, roots in _milestone_partition(entity, snapshot.checked().results())
    ]
    return _read_emissions(observed), graphs_wire, observed.round_trips


def _is_single_graph(query: ObjectQueryNode) -> bool:
    """Whether the read answers one graph rather than a milestone SET.

    The dispatch is the query's own — a scanned axis is what makes a read
    milestone-set (`m-temporal-read`) — read here rather than inferred from the
    result, because both forms now publish one ordered Snapshot.
    """
    return not scans_an_axis(query)


def _milestone_partition(
    entity: EntityMetadata, roots: Sequence[object]
) -> list[tuple[Pin, list[Row | None]]]:
    """One ordered milestone-set result partitioned back into its own graphs.

    Roots arrive in the executor's chronological milestone order, so a partition
    closes as soon as the edge changes: grouping by first appearance would fold
    two milestones a scan legitimately answers twice.
    """
    partitions: list[tuple[Pin, list[Row | None]]] = []
    for root in roots:
        pin = _root_pin(entity, root)
        if not partitions or partitions[-1][0] != pin:
            partitions.append((pin, []))
        partitions[-1][1].append(envelope.graph_root(root))
    return partitions


def _milestone_groups(
    entity: EntityMetadata, roots: Sequence[object]
) -> list[tuple[Pin, list[Row | None]]]:
    """One streamed milestone-set delivery grouped back into its own graphs.

    Deliberately NOT :func:`_milestone_partition`'s adjacency rule. A delivery
    arrives in the Continuation Order — the key, then the edge — so two roots of
    one milestone are adjacent only when they share a key, and a milestone
    several objects stand at reaches the caller in as many runs as there are
    objects. Grouping globally is what a whole-result read's own executor does,
    which is why the same `then.graphs` states both.

    The entries are ordered by edge rank, Valid Time before Transaction Time, for
    the same reason: what a milestone-set result states is which milestones the
    read reached, and ordering the entries by an order the delivery happens to
    have visited them in would make the observation depend on the page size the
    member exists to say nothing about.
    """
    groups: dict[Pin, list[Row | None]] = {}
    for root in roots:
        groups.setdefault(_root_pin(entity, root), []).append(envelope.graph_root(root))
    return sorted(groups.items(), key=lambda entry: _edge_rank(entity, entry[0]))


def _edge_rank(entity: EntityMetadata, pin: Pin) -> tuple[object, ...]:
    """One milestone's chronological rank: its coordinates in canonical axis order."""
    coordinates = {
        TemporalDimension.VALID_TIME: pin.valid_time,
        TemporalDimension.TRANSACTION_TIME: pin.tx_time,
    }
    axes = sorted(entity.declared_as_of_axes, key=lambda axis: axis.dimension.value)
    return tuple(coordinates[axis.dimension] for axis in axes)


def _root_pin(entity: EntityMetadata, root: object) -> Pin:
    """One milestone-set root's own edge pin, read off the values it published.

    A milestone-set graph is edge-pinned at its own milestone's from-instant
    (`m-snapshot-read`), and the root carries those axis starts as declared
    members, so the coordinate is the row's own rather than a second reading of
    the query.
    """
    values = envelope.graph_root(root)
    if values is None:  # pragma: no cover - a non-hydrating milestone root pins nothing
        raise EngineError("a milestone-set root published no value to pin")
    coordinates: dict[TemporalDimension, object] = {
        axis.dimension: values.get(axis.start_attribute.name) for axis in entity.declared_as_of_axes
    }
    return Pin(
        tx_time=_pin_instant(coordinates.get(TemporalDimension.TRANSACTION_TIME)),
        valid_time=_pin_instant(coordinates.get(TemporalDimension.VALID_TIME)),
    )


def _pin_instant(value: object) -> dt.datetime | None:
    """One published axis start as the instant a :class:`Pin` carries."""
    if not isinstance(value, str):
        return None
    return normalize_instant(dt.datetime.fromisoformat(value))


def _read_emissions(observed: LifecycleObservation) -> list[Emission]:
    """The read's own emissions: the statements production actually ran, in order."""
    return [Emission("/objectQuery", statement) for statement in observed.statements]


def _stored_data_records(
    roots: Sequence[object], model: AcceptedMetamodel
) -> list[dict[str, object]] | None:
    """The `then.storedDataIssues` observation, or ``None`` for a clean read.

    One entry per INVALID result position, in result order: the position itself,
    whether hydration completed, and the closed diagnosis set the root carries.
    A conforming read reports nothing at all, so a case that authors no
    expectation is never handed an empty array to explain.
    """
    records = [
        _stored_data_record(cast("handle.InvalidData[object]", root), model)
        for root in roots
        if isinstance(root, handle.InvalidData)
    ]
    return records or None


def _stored_data_record(
    record: handle.InvalidData[object], model: AcceptedMetamodel
) -> dict[str, object]:
    """One published :class:`~parallax.snapshot.InvalidData` on the wire.

    ``hydrated`` states the one thing the graph position cannot: whether the
    ``null`` at that position means "no value could be produced without inventing
    one" or is the node's own collapsed value.
    """
    return {
        "ordinal": record.ordinal,
        "hydrated": record.data is not None,
        "issues": sorted(
            (_stored_data_issue(issue, model) for issue in record.issues),
            key=lambda issue: (
                cast("str", issue["code"]),
                cast("str", issue.get("member") or ""),
                cast("str", issue["entity"]),
            ),
        ),
    }


def _stored_data_issue(
    issue: handle.StoredDataIssue, model: AcceptedMetamodel
) -> dict[str, object]:
    """One diagnosis as its cross-language record (`m-snapshot-read`).

    ``member`` is absent for an unresolved family tag alone — its discriminator
    names no declared member — and ``objectKey`` is absent wherever the affected
    object's own identity did not decode.
    """
    rendered: dict[str, object] = {"code": issue.code, "entity": issue.entity.canonical}
    if issue.member is not None:
        rendered["member"] = _member_path(issue.member)
    if issue.object_key is not None:
        rendered["objectKey"] = ActualWireProjection(model).object_key(issue.object_key)
    return rendered


def _member_path(member: MemberIdentity) -> str:
    """One member identity as the dotted path the corpus addresses members by.

    The same spelling a nested predicate authors
    (``parallax.compatibility.Customer.address.geo.country``), so a diagnosis
    names a member exactly as a case already names one.
    """
    match member:
        case AttributeIdentity():
            return f"{member.entity.canonical}.{member.name}"
        case ValueObjectIdentity():
            return ".".join((member.entity.canonical, *member.path))
        case ValueObjectAttributeIdentity():
            occurrence = member.value_object
            return ".".join((occurrence.entity.canonical, *occurrence.path, member.name))
