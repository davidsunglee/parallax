"""The snapshot action-step lane: a scenario whose steps carry a `mutate` or
`access` action over the graph a find step materialized, compiled to its find
and write steps' DML or run and reported as the observations its ``then``
members grade.

A find step reads through the same public Wire read every graph read uses;
`mutate` runs the production write seam's finite-Transaction-Time-pin refusal
against the named view's own pin and, when that verdict accepts, derives an
Edited Copy carrying the step's `set` as this step's own result — zero round
trips, nothing at the port, because a snapshot node is never enrolled in a unit
of work (`m-snapshot-read` closed world); `access` navigates a relationship on
the view an earlier step holds, likewise touching the port not at all. A
`write:` step commits as its own unit of work through the write core this lane
consumes from :mod:`~parallax.conformance._lanes.scenario`, and the views
earlier find steps materialized stand untouched across it.

The run lane builds its own Handle over the caller's port, applies the case's
``given.apply`` ahead of the first step, and closes the Handle where the case
ends; the compile lane lowers purely, with no database. Both are reached from
the façade, which dispatches a scenario here by the presence of an action
step. The :class:`~parallax.conformance._mechanism.envelope.ScenarioRun` the
run lane returns — its `errors` channel filled from `expectError` grading, its
`stepRows` and `stepGraphs` from each step's own placement — is graded against
``then`` by the adapter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Final, Literal, cast

from parallax.conformance import (
    _case_ingress,
    case_format,
    models,
)
from parallax.conformance._database_control import (
    CaseDatabase,
)
from parallax.conformance._lanes.scenario import (
    LOWERING_ERRORS,
    CaseContext,
    entry_instant,
    execute_keyed_unit,
    is_materializing_write_step,
    is_predicate_write_step,
    lower_writes,
    read_step_graph,
    step_query,
    step_rows,
    write_entries,
)
from parallax.conformance._lifecycle_observation import LifecycleRun
from parallax.conformance._mechanism import case_document, envelope
from parallax.conformance._mechanism.envelope import (
    READ_ERRORS,
    Emission,
    EngineError,
    ScenarioRun,
)
from parallax.conformance._mechanism.given_state import (
    apply_given_apply,
    seed_shadow_from_fixtures,
)
from parallax.conformance._mechanism.model_facts import (
    canonicalize_read,
    case_entity,
    case_serving_model,
    declaring_metadata,
    load_case_metamodel,
)
from parallax.conformance._mechanism.transaction_control import (
    underlying,
)
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import (
    inheritance,
    relationship,
)
from parallax.core.dialect import dialect_for
from parallax.core.metamodel import (
    EntityIdentity,
    Multiplicity,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.sql_gen import LoweredStatement
from parallax.core.sql_gen._compile import compile_read
from parallax.core.temporal_read import Pin, query_pin
from parallax.core.unit_work import (
    KeyedWrite,
    WriteRejectedError,
    instructions,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
)
from parallax.snapshot import handle
from parallax.snapshot.handle import (
    TransactionTimePinReadOnlyError,
    validate_source_pin,
)
from parallax.snapshot.materialize import FAMILY_VARIANT_KEY

__all__ = ["compile_scenario", "run_scenario"]


_GRADED_ACTION_VERBS: Final[frozenset[str]] = frozenset({"mutate", "access"})
"""The lifecycle action verbs this lane grades over a snapshot graph.

`mutate` is the authored edit and `access` a relationship read over a view a
find step already materialized — both are things this lane holds the state for.
Every other verb (`load`, `flush`, `commit`, `abort`) is a managed-object
lifecycle surfacing only the API Conformance Suite
can verify, and a case built on one is dispatched to the api-conformance lane
before reaching here at all."""


def _check_action_step(case: case_format.Case, step: Mapping[str, object]) -> None:
    """Refuse an action verb this lane does not grade (:data:`_GRADED_ACTION_VERBS`)."""
    action = step.get("action")
    if action not in _GRADED_ACTION_VERBS:
        raise EngineError(
            f"{case.path.name}: scenario action {action!r} is graded by the API "
            "Conformance Suite (api-conformance lane), not compile/run"
        )


def _snapshot_write_entries(
    case: case_format.Case, model: AcceptedMetamodel, step: Mapping[str, object]
) -> Sequence[Mapping[str, object]]:
    """One snapshot-read scenario write step's own keyed instruction buffer.

    This lane admits the buffered KEYED form alone, and the three shapes it
    refuses are refused for three different reasons, so the mapping-shaped ones
    are CLASSIFIED before the diagnosis is written rather than sharing one:

    - a legacy string label states no instruction to lower at all;
    - a MATERIALIZING predicate write
      (:func:`~parallax.conformance._lanes.scenario.is_materializing_write_step`)
      resolves through the find step that precedes it, which the keyed
      unit-of-work lane runs as one materializing pair, and a find HERE
      materializes the snapshot whose view a later `access` states rather than
      the rows a write settles against — the two step roles genuinely conflict,
      so this refusal is permanent;
    - a READLESS predicate write owes no resolving read at all, so nothing about
      it conflicts with this lane; it is refused because the lane has not wired
      it, never because the shape is wrong here.
    """
    raw_write = step["write"]
    if isinstance(raw_write, list):
        return write_entries(cast("list[object]", raw_write))
    if not is_predicate_write_step(raw_write):
        raise EngineError(
            f"{case.path.name}: a snapshot-read scenario's write step states the BUFFERED "
            f"KEYED instruction list; {type(raw_write).__name__!r} is a legacy label, which "
            "states no instruction to lower at all"
        )
    if is_materializing_write_step(step, model) is not None:
        raise EngineError(
            f"{case.path.name}: a MATERIALIZING predicate write resolves through the find "
            "step before it, and a find HERE materializes the view a later `access` states "
            "rather than the rows the write settles against — pairing the two would answer "
            "a survival question with a resolve"
        )
    raise EngineError(
        f"{case.path.name}: a READLESS predicate write owes no resolving find, so nothing "
        "about it conflicts with this lane — the lane simply does not wire the "
        "predicate-write translation yet, so the shape is unsupported rather than "
        "mis-authored"
    )


_SnapshotStepKind = Literal["action", "write", "find"]


def _snapshot_step_kind(step: Mapping[str, object]) -> _SnapshotStepKind:
    """Which kind a snapshot-read scenario step is, decided ONCE for both of the
    lane's interpreters (:func:`compile_scenario` and
    :func:`run_scenario`).

    The three are mutually exclusive and a step carrying neither an `action` nor
    a `write` is a find (`m-case-format` "Scenario steps"), which is what makes
    the cascade a classification rather than each interpreter's own ordered
    guesses — a kind admitted here is a kind both of them must answer for."""
    if "action" in step:
        return "action"
    if "write" in step:
        return "write"
    return "find"


def compile_scenario(
    case: case_format.Case, dialect_name: str, steps: Sequence[Mapping[str, object]]
) -> tuple[list[Emission], int]:
    """Compile a snapshot-read scenario's own find steps (instance-form,
    unlocked — a snapshot materialization is not a locking object find) and its
    write steps (each its own choreography unit, lowered through the SAME
    planner the unit-of-work lane's ungrouped write step uses, staged on that
    unit's own outcome so a `rollback: true` step's advances are restored after
    it); `mutate` and `access` contribute no emissions and no round trips at all
    (m-snapshot-read: an in-memory-only change and a closed-world navigation,
    never SQL)."""
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = case_document.concurrency(case)
    shadow = TemporalShadow()
    # The same seeding the RUN lane applies: this lane's cases load their model's
    # fixtures, so a temporal close observes the milestone that persisted history
    # holds rather than none at all. Both lanes must start from the same tracked
    # state or they are not the same computation.
    seed_shadow_from_fixtures(case, model, shadow)
    emissions: list[Emission] = []
    try:
        for index, step in enumerate(steps):
            match _snapshot_step_kind(step):
                case "action":
                    _check_action_step(case, step)
                case "write":
                    entries = _snapshot_write_entries(case, model, step)
                    with shadow.staged(doomed=step.get("rollback") is True):
                        statements = lower_writes(
                            entries,
                            model,
                            dialect,
                            concurrency,
                            shadow,
                            entry_instant(entries[0]),
                            [],
                        )
                    emissions.extend(
                        Emission(f"/scenario/{index}/write", statement) for statement in statements
                    )
                case "find":
                    query = step_query(step, model)
                    metadata = case_entity(model, query.target.canonical)
                    entity_query = canonicalize_read(query, metadata, model)
                    statement = compile_read(
                        entity_query, model, dialect, result_form="instance"
                    ).statement
                    emissions.append(Emission(f"/scenario/{index}/objectQuery", statement))
    except (*READ_ERRORS, *LOWERING_ERRORS) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return emissions, len(emissions)


@dataclass(frozen=True, slots=True)
class _ScenarioStepResult:
    """What one snapshot-scenario step left behind for a later step to name.

    Its facts are produced together and named together by every step that reaches
    back to them — a `mutate` grades its assignment against ``pin`` and
    ``identity`` and derives a copy of ``roots`` (:func:`_grade_mutate_step`), an
    `access` navigates ``roots`` under the same ``identity``
    (:func:`_access_step_graph`) — so they travel as one value rather than as
    index-aligned sequences a caller could fall out of step.

    ``roots`` is the in-memory member state of each root the step holds, keyed by
    member name — the plain detached value an `access` navigates from
    (`m-snapshot-read` closed world). Its length is what a `mutate` step's
    single-node requirement is checked against. A relationship a find step's own
    read included rides ON that state as the nested nodes the Wire result
    published, so the view a later step reaches is the one THAT read materialized
    and no re-read can stand in for it — which is exactly what an `access` step's
    `expectGraph` asks about. ``pin`` and ``identity`` are the coordinates the
    production finite-pin validator is handed.

    Two step kinds fill one: a find, with what it materialized, and an ACCEPTED
    `mutate`, with the Edited Copy it derived (:func:`_edited_copy`) — a copy
    carries its source's views and pin, so a later `mutate` naming it answers
    exactly as one naming the read does (`m-snapshot-read` *Closed world*,
    composition). ``identity`` is the one fact they state at different
    precisions: a find records the Object Query's own TARGET, which spans a whole
    family when that target is abstract, while a copy holds exactly one node and
    records the CONCRETE Entity that node is
    (:func:`_edited_node_identity`). ``materialized`` is what separates them: a
    find's own read fetched the contents, a copy only carries them, and an
    `access` stating relationship contents names the read that materialized them
    (`m-case-format` *Relationship contents at a step*) — a distinction every
    executor draws alike, so the flag is the one place this lane draws it. A
    write step, an `access`, and a `mutate` the pin rule refused carry the empty
    result instead — their slot exists so a later step's `on` index still names
    the step it means.
    """

    roots: tuple[dict[str, object], ...]
    pin: Pin | None
    identity: EntityIdentity | None
    materialized: bool = False


_NO_SCENARIO_RESULT: Final[_ScenarioStepResult] = _ScenarioStepResult((), None, None)


def run_scenario(
    case: case_format.Case,
    port: CaseDatabase,
    steps: Sequence[Mapping[str, object]],
    lifecycle: LifecycleRun,
) -> ScenarioRun:
    """Run a snapshot-read scenario: each find step reads through the SAME
    public Wire read every graph read uses (``db.wire.find``); `mutate` runs the
    production write seam's
    finite-Transaction-Time-pin refusal against the named view's own pin and,
    when that verdict accepts, derives an Edited Copy carrying the step's `set`
    and publishes it as this step's own result (:func:`_grade_mutate_step`) —
    zero round trips, nothing at the port (m-snapshot-read closed world: a
    snapshot node is never enrolled in a unit of work, so editing it can never
    write back); and `access` navigates a relationship on the view a named
    earlier step holds, likewise touching the port not at all
    (:func:`_access_step_graph`).

    A `write:` step is the composition the closed-world clause is about: it
    commits as its OWN unit of work through ``db.transact``
    (:func:`_run_snapshot_write_step`), exactly as an ungrouped write step of the
    keyed unit-of-work lane does, and the views earlier find steps materialized
    stand untouched across it — a later `access` still answers what its own read
    fetched, whatever the write did to the rows behind it. Its step slot is
    parked empty so a later step's `on` index still names the step it means.

    Reports its observations as a :class:`ScenarioRun`; this lane opens no `uow`
    group."""
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    context = CaseContext(
        serving,
        model,
        case_document.concurrency(case),
        TemporalShadow(),
        case_format.uow_isolation(case),
    )
    # Seeded from the case's own fixtures and then advanced by each write step's
    # plan, so a temporal close observes the milestone the persisted history (or
    # an earlier step) actually holds — the SAME order every other lane applies:
    # fixtures, then `given.apply`, then the first step.
    seed_shadow_from_fixtures(case, model, context.shadow)
    apply_given_apply(case, port, context.shadow)
    observation = lifecycle.observation()
    with handle.Database.connect(port, serving, lifecycle_provider=observation.provider) as db:
        emissions: list[Emission] = []
        round_trips = 0
        results: list[_ScenarioStepResult] = []
        errors: list[dict[str, object]] = []
        rows_observed: list[dict[str, object]] = []
        step_graphs: list[dict[str, object]] = []
        for index, step in enumerate(steps):
            match _snapshot_step_kind(step):
                case "action":
                    _check_action_step(case, step)
                    if step.get("action") == "access":
                        observed = _access_step_graph(case, model, index, step, results)
                        if observed is not None:
                            step_graphs.append(observed)
                        results.append(_NO_SCENARIO_RESULT)
                    else:
                        error_class, edited = _grade_mutate_step(case, model, step, results)
                        if error_class is not None:
                            errors.append({"at": f"/scenario/{index}", "errorClass": error_class})
                        elif "expectRows" in step:
                            rows_observed.append(
                                {
                                    "at": f"/scenario/{index}",
                                    "rows": [dict(root) for root in edited.roots],
                                }
                            )
                        results.append(edited)
                case "write":
                    statements, unit_trips = _run_snapshot_write_step(
                        case, context, port, step, lifecycle
                    )
                    emissions.extend(
                        Emission(f"/scenario/{index}/write", statement) for statement in statements
                    )
                    round_trips += unit_trips
                    results.append(_NO_SCENARIO_RESULT)
                case "find":
                    query = step_query(step, model)
                    mark = observation.round_trips
                    try:
                        # The case document's own spelling is resolved HERE, where the
                        # document is read, so no later step carries a spelling into a
                        # production seam that takes an Entity Identity.
                        identity = case_entity(model, query.target.canonical).identity
                        snapshot = underlying(partial(db.wire.find, query))
                        pin = _find_step_pin(model, query)
                    except READ_ERRORS as exc:
                        raise EngineError(f"{case.path.name}: {exc}") from exc
                    emissions.extend(
                        Emission(f"/scenario/{index}/objectQuery", statement)
                        for statement in observation.since(mark, "read")
                    )
                    round_trips += observation.round_trips - mark
                    rows_observed.append(
                        step_rows(model, index, query, snapshot.checked().results())
                    )
                    observed = read_step_graph(case, model, index, step, query, snapshot)
                    if observed is not None:
                        step_graphs.append(observed)
                    results.append(
                        _ScenarioStepResult(
                            _root_members(snapshot), pin, identity, materialized=True
                        )
                    )
        return ScenarioRun(emissions, round_trips, errors, rows_observed, step_graphs)


def _root_members(
    snapshot: handle.Snapshot[handle.WireEntity],
) -> tuple[dict[str, object], ...]:
    """Each root the step materialized, as its own detached member state.

    Member NAME keyed, because that is the vocabulary a case's `set` is authored
    in — the Wire result's own keying — and detached into a plain mapping so
    what a later step names is a value of this lane's own rather than the frozen
    result production published. The relationship arms ride along by reference:
    a copy derived from this state answers the SAME materialized children, which
    is the composition rule itself (`m-snapshot-read` *Closed world*).
    """
    return tuple(dict(envelope.graph_root(root) or {}) for root in snapshot.checked().results())


def _run_snapshot_write_step(
    case: case_format.Case,
    context: CaseContext,
    port: CaseDatabase,
    step: Mapping[str, object],
    lifecycle: LifecycleRun,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """Execute one `write:` step of a snapshot-read scenario and report the DML
    it emitted beside the round trips it cost.

    The step is its OWN choreography unit, driven through the SAME
    :func:`~parallax.conformance._lanes.scenario.execute_keyed_unit` an
    ungrouped write step of the keyed unit-of-work lane is, which is the
    ungrouped semantics `m-case-format` gives a write step carrying no `uow`
    label. Nothing about it reaches the views this scenario's find steps
    materialized: those are values taken at their own pin (`m-snapshot-read`
    closed world), so the write persists and the graph stands.

    What this lane adds is its own admitted write form
    (:func:`_snapshot_write_entries`) and the case-named diagnosis every failure
    inside the unit carries out of it.
    """
    try:
        entries = _snapshot_write_entries(case, context.model, step)
        return execute_keyed_unit(
            port, context, entries, [], lifecycle, rollback=step.get("rollback") is True
        )
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def _access_step_graph(
    case: case_format.Case,
    model: AcceptedMetamodel,
    index: int,
    step: Mapping[str, object],
    results: Sequence[_ScenarioStepResult],
) -> dict[str, object] | None:
    """One `access` step's own graph observation, or ``None`` when it asserts none.

    An access over an already-materialized relationship issues nothing at the
    port (`m-snapshot-read` closed world), so what it observes is read off the
    state the named step holds — the view a find materialized, untouched by any
    edit derived from it since. Reporting a re-read here would answer that the
    database is right where the case asks whether the view survived, which is the
    whole point of the observable (`m-conformance-adapter`).

    The step names ONE materializing READ (`m-case-format`), and both halves of
    that bind here. One, because the multi-source `on` form spans views at
    different lowered coordinates and no single view holds contents gathered
    across them. A read, because an Edited Copy carries contents it never
    fetched: naming one would state a graph whose provenance is a step that
    issued no query, which the executor holding no copy at all cannot express —
    so a case authored that way would grade in one lane and be refused in
    another, where the observable's whole worth is that one authored
    `expectGraph` grades alike in every lane.
    """
    if "expectGraph" not in step:
        return None
    on = step.get("on")
    if not isinstance(on, int):
        raise EngineError(
            f"{case.path.name}: `access` states relationship contents on {on!r} — such a "
            "step names ONE materializing read, never a set of sources"
        )
    source = results[on] if 0 <= on < len(results) else None
    if source is None or source.identity is None:
        raise EngineError(
            f"{case.path.name}: `access` names {on!r}, which holds no view to navigate"
        )
    if not source.materialized:
        raise EngineError(
            f"{case.path.name}: `access` states relationship contents on step {on}, which "
            "derived its view rather than materializing it — such a step names the read "
            "whose `includes` fetched the contents"
        )
    path = step.get("path")
    if not isinstance(path, str):
        raise EngineError(f"{case.path.name}: an `access` asserting a graph needs a `path`")
    entity_name, nodes = _navigate_step_view(case, model, source, path)
    return {"at": f"/scenario/{index}", "graph": {entity_name: nodes}}


def _navigate_step_view(
    case: case_format.Case,
    model: AcceptedMetamodel,
    source: _ScenarioStepResult,
    path: str,
) -> tuple[str, list[object]]:
    """The nodes ``path`` reaches on a retained view, and their Entity's local name.

    Each hop reads the loaded arm the Wire result published on the node — a
    frozen sequence for a to-many, a nested node or ``None`` for a to-one — so
    the traversal is a walk over what the read materialized rather than a second
    materialization of it. A key the node does not carry is the unloaded state
    itself (`m-snapshot-read`), which an access asserting contents cannot be
    authored over; a key carrying ``None`` is the LOADED-null branch instead,
    whose deeper levels see an empty parent set (`m-deep-fetch`) rather than an
    unloaded view.

    A null or empty branch therefore contributes no terminal value once any hop
    fans out: such a path answers its non-null terminal nodes in traversal order.
    An all-to-one path fans out nowhere and answers one terminal per root
    instead, ``None`` where its branch reached no row. Those contents are the
    observable's own (`m-case-format` *Relationship contents at a step*), which
    every adapter reports alike; the Python inspection API's traversal rule
    (`python.md`) agrees with it rather than defining it.
    """
    identity = source.identity
    assert identity is not None, "the caller resolves the source step's Entity Identity"
    names = path.split(".")
    fans_out = False
    for name in names:
        direction = _related_direction(case, model, identity, name)
        identity = direction.join.target.entity
        fans_out = fans_out or direction.cardinality.target is Multiplicity.MANY
    nodes: list[object] = list(source.roots)
    for name in names:
        reached: list[object] = []
        for node in nodes:
            if node is None:
                reached.append(None)
                continue
            if not isinstance(node, Mapping) or name not in node:
                raise EngineError(
                    f"{case.path.name}: `access` navigates {path!r}, but the view its "
                    f"find step materialized carries no loaded {name!r} — an access "
                    "asserting relationship contents names a read whose `includes` "
                    "materialized them"
                )
            arm = cast("Mapping[str, object]", node)[name]
            if isinstance(arm, list | tuple):
                reached.extend(cast("Sequence[object]", arm))
            elif arm is not None or not fans_out:
                reached.append(arm)
        nodes = reached
    return identity.name, nodes


def _relationship_declaration(
    model: AcceptedMetamodel, identity: EntityIdentity, name: str
) -> relationship.RelationshipMetadata | None:
    """The relationship ``name`` names one hop from ``identity`` — declared on it
    or on an ancestor (`m-inheritance`) — or ``None``.

    The one place a member name is asked whether it is a relationship at all, so
    the navigating caller (:func:`_related_direction`) and the refusing one
    (:func:`_edited_copy`) reach the same answer.
    """
    position = inheritance.view(model).entity(identity)
    declared = None if position is None else position.applicable_relationship(name)
    return None if declared is None else relationship.view(model).relationship(declared.identity)


def _applicable_member_names(model: AcceptedMetamodel, identity: EntityIdentity) -> frozenset[str]:
    """Every member name APPLICABLE to ``identity``: the attributes and Value
    Object occurrences it declares and the ones it inherits alike, whatever each
    one's own assignability.

    Membership alone, which is the question a `mutate` step's `set`
    (:func:`_edited_copy`) asks before the prepared-write producer judges its
    values. Inheritance is part of
    that question and not a later one: `Dog` has `Pet`'s `licenseId` as plainly as
    its own `barkVolume`, so both are here. Whether a member may then be ASSIGNED
    is the later and separate verdict (:func:`_judged_assignments`), which is what
    refuses a primary-key or read-only target; a name absent from this set is
    refused earlier and for the different reason that it names no member at all. A
    key a read publishes BESIDE the members is absent by construction — an
    inheritance participant's synthetic `familyVariant` names no member of any
    ancestor, so it is no more assignable than a name the model never heard of,
    however plainly the materialized node carries it.
    """
    position = inheritance.view(model).entity(identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return frozenset()
    return frozenset(
        {attribute.identity.name for attribute in position.applicable_attributes}
        | {occurrence.identity.path[-1] for occurrence in position.applicable_value_objects}
    )


def _prepared_row_member_names(
    model: AcceptedMetamodel, identity: EntityIdentity
) -> frozenset[str]:
    position = inheritance.view(model).entity(identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return frozenset()
    return frozenset(
        {
            attribute.identity.name
            for attribute in position.applicable_attributes
            if not attribute.framework_owned
        }
        | {occurrence.identity.path[-1] for occurrence in position.applicable_value_objects}
    )


def _edited_node_identity(
    case: case_format.Case,
    model: AcceptedMetamodel,
    target: EntityIdentity,
    node: Mapping[str, object],
) -> EntityIdentity:
    """The Entity one retained node IS, which its find step's ``target`` names
    only where the read cannot be polymorphic.

    An abstract-target read materializes COMPLETE CONCRETE instances
    (`m-case-format`), so a node published under an abstract `Animal` carries
    `Dog`'s own members and the `familyVariant` spelling saying which concrete it
    is. An edit is judged against THAT Entity: its applicable members — the ones
    it declares and the ones it inherits alike — are the vocabulary an authored
    name resolves in (:func:`_applicable_member_names`), and their declared types
    are what a value is judged against, where the abstract target has neither and
    would wave both through. Whether a member of that vocabulary may then be
    ASSIGNED is the separate later verdict (:func:`_judged_assignments`), which is
    what refuses the primary-key, read-only and framework-owned members applicable
    membership deliberately includes. The resolution belongs here rather than at
    the read because one read answers many concretes at once; only a step holding
    exactly one node has a concrete to name.

    ``familyVariant`` is read as PROVENANCE only where the target position
    participates in a family, because that is the only place the name is reserved
    for one: `m-inheritance` reserves the synthetic key from declared members "on
    an inheritance participant", so a STANDALONE Entity may declare an ordinary
    member spelled exactly that way and a read then publishes its domain value
    under that key. The participation test is the position's own strategy — the
    same test the read makes before publishing a synthetic variant at all — so
    one node's key means metadata to both sides or domain state to both.

    A variant spelling naming no concrete subtype of a PARTICIPANT ``target`` is
    refused rather than fallen back on: falling back would judge a subtype member
    against the abstract position again, which is the hole this resolution exists
    to close.
    """
    facet = inheritance.view(model)
    position = facet.entity(target)
    if position is None or position.strategy is None:
        return target
    variant = node.get(FAMILY_VARIANT_KEY)
    if not isinstance(variant, str):
        return target
    for concrete in position.concrete_subtypes:
        if inheritance.family_variant_name(facet, concrete) == variant:
            return concrete
    raise EngineError(
        f"{case.path.name}: the view holds a {variant!r} node, which is no concrete subtype "
        f"of {target.name} — an edit is judged against the Entity its node IS"
    )


def _related_direction(
    case: case_format.Case, model: AcceptedMetamodel, identity: EntityIdentity, name: str
) -> relationship.RelationshipMetadata:
    """The relationship direction one hop from ``identity``, by its local name."""
    direction = _relationship_declaration(model, identity, name)
    if direction is None:
        raise EngineError(
            f"{case.path.name}: {identity.name} declares no relationship {name!r} to navigate"
        )
    return direction


def _find_step_pin(model: AcceptedMetamodel, query: ObjectQueryNode) -> Pin:
    """A scenario read step's own query pin — the whole-graph as-of coordinates
    the materialized view carries (`m-snapshot-read`), read from the SAME
    Object Query the find executor consumes. This is the pin
    :func:`_grade_mutate_step` hands the production write seam's finite-pin
    rule, resolved through the family-declaring entity exactly as the read
    path resolves it."""
    return query_pin(query, declaring_metadata(model, query.target.canonical))


def _grade_mutate_step(
    case: case_format.Case,
    model: AcceptedMetamodel,
    step: Mapping[str, object],
    results: Sequence[_ScenarioStepResult],
) -> tuple[str | None, _ScenarioStepResult]:
    """Grade one scenario `mutate` action step, answering both of its channels:
    the neutral error the verb raised, and the Edited Copy it derived.

    The verdict is the SAME production validator the keyed developer verbs run
    (:func:`~parallax.snapshot.handle.validate_source_pin`): a mutation through a
    view pinned at a finite Transaction-Time instant raises the neutral
    `transaction-time-pin-read-only` error and derives nothing, while a Latest or
    finite-Valid-Time pin is accepted and the step's `set` reaches a copy
    (:func:`_edited_copy`). The error channel carries the raised error's
    `errorClass` when the step's own declared `expectError` matched it, else
    ``None`` for an accepted mutation; a mismatch in either direction — an
    undeclared refusal, or a declared expectation the verb never raised — is a
    loud :class:`EngineError`, never a silently dropped observation. The result
    channel carries the copy on acceptance and the empty result on refusal,
    which is what a later step's `on` index resolves against.

    ``on`` names any step holding a view: a find, or an earlier `mutate` whose
    own copy this one derives from. A chain of edits therefore re-asks the pin
    question at every hop, because a copy carries its source's pin — which is
    what makes a view pinned in the Transaction-Time past read-only through an
    edit as well as directly.
    """
    on = step.get("on")
    source = results[on] if isinstance(on, int) and 0 <= on < len(results) else None
    identity = None if source is None else source.identity
    if not isinstance(on, int) or source is None or identity is None:
        raise EngineError(f"{case.path.name}: `mutate` names {on!r}, which holds no view to edit")
    expected = step.get("expectError")
    try:
        validate_source_pin(identity, source.pin)
    except TransactionTimePinReadOnlyError as exc:
        if expected != exc.code:
            declared = f"expectError {expected!r}" if expected is not None else "no expectError"
            raise EngineError(
                f"{case.path.name}: the `mutate` verb raised {exc.code!r} but the step "
                f"declares {declared}"
            ) from exc
        return exc.code, _NO_SCENARIO_RESULT
    if expected is not None:
        raise EngineError(
            f"{case.path.name}: the step declares expectError {expected!r} but the "
            "mutation was accepted"
        )
    return None, _edited_copy(case, model, step, on, source)


def _edited_copy(
    case: case_format.Case,
    model: AcceptedMetamodel,
    step: Mapping[str, object],
    on: int,
    source: _ScenarioStepResult,
) -> _ScenarioStepResult:
    """The Edited Copy an ACCEPTED `mutate` derives from the view step ``on`` holds.

    `m-case-format` defines `mutate` as assigning the attributes in `set` in
    memory, and `m-snapshot-read` *Closed world* fixes what deriving leaves
    alone: the result is a NEW value carrying the source's own relationship
    views, and the source itself is untouched — an edit answers with a copy
    rather than rewriting the node it derives from, which is why a scenario can
    hold both and ask each what it answers. It carries the source's pin too, so a
    later `mutate` naming the copy resolves exactly as one naming the read does;
    what it does NOT carry is a read of its own, which is why an `access` stating
    contents still names the find (:func:`_access_step_graph`). No DML follows
    either way: no unit of work holds the view (`m-snapshot-read`).

    Every verdict below is reached against the Entity the retained node IS
    (:func:`_edited_node_identity`), never against the query target that
    published it: an abstract-target read answers concrete instances, so it is
    the concrete subtype that fixes which names are assignable — its own members
    and its ancestors' alike — and what type each holds. That resolved Identity
    rides on the copy, so a chain of edits keeps judging the same Entity.

    Three verdicts stand between a `set` and the copy, in this order. A
    RELATIONSHIP name is refused outright — no edit changes a relationship
    member, so a carried view can only ever describe what a read observed, and a
    copy whose `items` the author replaced would describe a fetch that never
    happened. A name that is no APPLICABLE member of the node's Entity — neither
    one it declares nor one it inherits — is refused as an assignment with
    nowhere to land: a case the verb cannot perform, not a mutation it silently
    drops. The MODEL is what that gate asks, rather than the materialized
    mapping's own keys: an inheritance participant's node publishes the synthetic
    `familyVariant` beside its members, and that key is read-time provenance no
    edit authors — while on a standalone Entity the same spelling is an ordinary
    declared member the gate admits. What survives both is judged as any edited
    value is (:func:`~parallax.core.inheritance.validate_write_assignment`), so a
    primary-key, read-only or framework-owned target and an ill-typed value are
    refused by the SAME verdict the typed `edit(**changes)` reaches. The
    conformance preparation seam first normalizes every authored value through
    the canonical prepared-write producer, so this lane owns no second recursive
    conversion; the edit-only assignment judgment receives the managed frozen
    values that producer returned.

    Every verdict is reached over the WHOLE `set` before any member is copied, so
    a refused mutation derives nothing at all: `set` is an unordered mapping, and
    applying its accepted names up to the first refused one would make the result
    depend on authoring order.

    A `mutate` carrying NO `set` is the change-free edit, which is legal and
    derives a copy of the source's own state — the branch an implementation that
    short-circuits a change-free edit, or rebuilds a copy from its declared
    members, must still answer for.
    """
    if len(source.roots) != 1:
        raise EngineError(
            f"{case.path.name}: `mutate` targets step {on}, which holds "
            f"{len(source.roots)} nodes (expected exactly one to edit)"
        )
    raw = step.get("set", {})
    if not isinstance(raw, Mapping):
        raise EngineError(f"{case.path.name}: a `mutate` action's `set` is a mapping")
    assignments = cast("Mapping[str, object]", raw)
    members = source.roots[0]
    assert source.identity is not None, "the caller resolves the source step's Entity Identity"
    identity = _edited_node_identity(case, model, source.identity, members)
    related = sorted(
        name for name in assignments if _relationship_declaration(model, identity, name) is not None
    )
    if related:
        raise EngineError(
            f"{case.path.name}: `mutate` assigns {related!r}, which name relationship members — "
            "an edit carries the views its source read materialized and authors none"
        )
    applicable = _applicable_member_names(model, identity)
    unassignable = sorted(name for name in assignments if name not in applicable)
    if unassignable:
        raise EngineError(
            f"{case.path.name}: `mutate` on step {on} assigns {unassignable!r}, which "
            f"{identity.name} has no assignable member of"
        )
    edited = _judged_assignments(case, model, identity, assignments, members)
    return _ScenarioStepResult(({**members, **edited},), source.pin, identity)


def _judged_assignments(
    case: case_format.Case,
    model: AcceptedMetamodel,
    identity: EntityIdentity,
    assignments: Mapping[str, object],
    current: Mapping[str, object],
) -> dict[str, object]:
    """One `mutate` step's `set`, decoded against ``identity``'s applicable members
    and judged assignable, or a loud refusal naming the case.

    An unassignable target or an ill-typed value is a case-AUTHORING defect
    rather than a graded observation: `m-case-format` says in so many words that
    such a `set` is a case-authoring failure and deliberately not an `expectError`,
    so a case cannot declare the refusal and no executor owes a graded one. The
    corpus refuses such a case before either executor runs it, which is what makes
    the outcome portable; this verdict is the same rule reached again at run time,
    where it also guards the shapes a case never carries — a hand-built step, or a
    node whose concrete Entity only the read knows. The conformance preparation
    seam normalizes case carriers before the canonical producer judges them.
    """
    prepared_members = _prepared_row_member_names(model, identity)
    row = {name: value for name, value in current.items() if name in prepared_members}
    row.update(assignments)
    instruction = KeyedWrite("update", identity.canonical, (row,))
    try:
        prepared = _case_ingress.prepare_case_write(instruction, model)
    except instructions.InstructionRejectedError as exc:
        raise EngineError(
            f"{case.path.name}: `mutate` carries a value that does not match the declared type "
            f"— {exc}"
        ) from exc
    except (instructions.WriteInstructionError, WriteRejectedError) as exc:
        raise EngineError(
            f"{case.path.name}: `mutate` carries an invalid assignment — {exc}"
        ) from exc
    assert isinstance(prepared, PreparedKeyedWrite)
    managed = prepared.rows[0]
    entity = case_entity(model, identity.canonical)
    for name in assignments:
        try:
            inheritance.validate_write_assignment(model, entity, name, managed[name])
        except inheritance.WriteAssignmentError as exc:
            raise EngineError(
                f"{case.path.name}: `mutate` assigns {name!r}, which an edit refuses — {exc}"
            ) from exc
    return dict(managed)
