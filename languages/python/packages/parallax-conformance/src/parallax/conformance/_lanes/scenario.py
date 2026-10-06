from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, cast

from parallax.conformance import (
    _case_ingress,
    case_format,
    models,
    temporal_state,
)
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._database_control import (
    CaseDatabase,
    ModeledExecution,
)
from parallax.conformance._lifecycle_observation import (
    LifecycleObservation,
    LifecycleRun,
    lifecycle_run,
)
from parallax.conformance._mechanism import case_document, envelope
from parallax.conformance._mechanism.dialects import dialect_for
from parallax.conformance._mechanism.envelope import (
    Emission,
    EngineError,
    ScenarioRun,
)
from parallax.conformance._mechanism.given_state import (
    apply_given_apply,
    seed_shadow_from_fixtures,
)
from parallax.conformance._mechanism.model_facts import (
    case_entity,
    case_serving_model,
    family_declarer,
    first_declared_entity,
    load_case_metamodel,
)
from parallax.conformance._mechanism.planned_reads import planned_read
from parallax.conformance._mechanism.transaction_control import (
    absorbing_rollback,
    committed,
    transact,
    write_adapter,
    write_connection,
)
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import (
    batch_write,
    inheritance,
    opt_lock,
    predicate,
    storage_layout,
)
from parallax.core.base import (
    INFINITY,
    normalize_instant,
)
from parallax.core.db_port import (
    DatabaseAdapter,
    DatabaseConnection,
    MappingRow,
)
from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeMetadata,
    EntityMetadata,
    MemberIdentity,
    PrimaryKey,
    TemporalDimension,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.predicate import (
    CanonicalDocumentError,
)
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.temporal_read import TemporalReadError, TimeInterval
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    BufferItem,
    CardinalityCorruptionError,
    Concurrency,
    KeyedWrite,
    MissingTargetError,
    OptimisticLockConflictError,
    PlanningRequest,
    PredicateWrite,
    RetainedObservation,
    SettledEvidence,
    StaleWriteError,
    SubjectActor,
    TransactionInstant,
    WriteEffectError,
    WritePreconditionError,
    buffered_write,
    instructions,
    object_key,
)
from parallax.core.unit_work.instructions import (
    ExpectedTxStart,
    ExpectedVersion,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    PreparedWrite,
    TargetWrite,
    WriteInstruction,
)
from parallax.core.unit_work.materialized import target_write
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import (
    ObjectKey,
    ObservedStateKey,
    TemporalObservation,
    VersionObservation,
    WriteObservation,
    WritePlan,
    WritePlanningError,
)
from parallax.core.write_plan.plan import NO_OWNERSHIP
from parallax.core.write_plan.steps import KeyTarget, PlannedWrite
from parallax.snapshot import DatabaseOptions, handle
from parallax.snapshot.handle import (
    ServingModel,
    TransactionTimePinReadOnlyError,
    build_write_planner,
    stream_lowered,
    validate_source_pin,
)
from parallax.snapshot.materialize._wire import authoring_of, read_origin_of

__all__ = [
    "INERT_CLOCK_INSTANT",
    "LOWERING_ERRORS",
    "CaseContext",
    "GroupState",
    "LoweredStep",
    "compile_scenario_case",
    "compile_write_sequence_case",
    "entry_instant",
    "execute_keyed_unit",
    "flush_failure",
    "graph_rows",
    "group_tx_instant",
    "is_materializing_write_step",
    "is_predicate_write_step",
    "lower_writes",
    "read_step_graph",
    "read_table_state",
    "refuse_a_conflict_retry_opt_in",
    "run_conflict_case",
    "run_group_step",
    "run_scenario_case",
    "run_standalone_find",
    "run_write_sequence_case",
    "scenario_group_step_indices",
    "step_query",
    "step_rows",
    "write_entries",
]


# A write step is one unit of work: its buffered keyed writes are planned by
# the SAME ``build_write_planner`` factory production uses (``m-unit-work``)
# and each surviving :class:`~parallax.core.unit_work.PlannedWrite` is lowered
# to DML by the shared ``snapshot.handle.stream_lowered`` seam — the deliberate
# ``m-sql`` write edge the conformance family may compose (the import-side DAG
# exemption). A **scenario** is a *sequence* of units of work: a write step
# commits (or, ``rollback: true``, aborts) its coalesced DML, then a ``find``
# reads committed state through the read path. A **writeSequence** lowers each
# entry independently — no cross-entry coalescing (an insert-then-delete pair
# across two entries is two round trips, not a cancellation) — and each entry
# is its OWN transaction (not "the whole sequence in one transaction").
#
# The RUN lane executes
# every write choreography unit — a writeSequence entry, a scenario write step, a
# conflict attempt — through the SHIPPED ``db.transact`` entry point (one
# transaction per unit, ``clock=FixedClock(<entry at>)``, ADR 0010), stated
# through the PUBLIC ``tx.wire`` verb each mutation names against the value the
# unit's own read published (never the typed instance verbs, which this engine's
# case-driven metamodel has no compiled classes for). The COMPILE lane still
# lowers PURELY (no database, ``build_write_planner(...).finalize(...).plan`` /
# ``stream_lowered``) — that pure lowering is ALSO what the RUN lane's
# emissions/round-trips observation grades against,
# since both are the SAME deterministic computation over the SAME
# instructions/observations/instant (`_resolve_entries` / `_lower_resolved`
# below are the shared core).

# The lowering failures the write lanes convert to a neutral :class:`EngineError`,
# so the adapter reports a ``*-failed`` diagnostic rather than leaking a lower-layer
# exception type across the conformance seam. `opt_lock.UnobservedVersionError` /
# `.CallerAuthoredVersionError` are m-opt-lock's own
# forward-error posture; `temporal_state.AmbiguousObservationError` /
# `.MilestoneEdgeError` are this engine's own (shapes no reachable case
# exercises). A deferred witness (the
# materializing / auto-retry-
# boundary forms) that reaches this engine-local write path without
# a recorded observation must degrade to a reasoned `EngineError`, never an
# uncaught crash of the sweep.
LOWERING_ERRORS: Final[tuple[type[Exception], ...]] = (
    instructions.WriteInstructionError,
    WritePlanningError,
    inheritance.InheritanceError,
    opt_lock.UnobservedVersionError,
    opt_lock.CallerAuthoredVersionError,
    temporal_state.AmbiguousObservationError,
    temporal_state.MilestoneEdgeError,
    CanonicalDocumentError,
    SqlGenError,
    TemporalReadError,
    KeyError,
    TypeError,
)

# A non-temporal writeSequence entry (e.g. a pk-gen sequence registry advance)
# names no `at` — its Clock value is inert (no temporal write consumes it this
# unit), so a fixed, deterministic instant stands in (`m-temporal-write` / ADR 0010:
# "a non-temporal entry's clock value is inert, pick something deterministic").
INERT_CLOCK_INSTANT: Final[str] = "1970-01-01T00:00:00+00:00"

# The compile lane's own audit-neutral Subject Actor: this lane never opens
# a real Execution Scope, and a Planning Request requires one regardless
# (`m-unit-work`) — the harness proves the value is never inspected, so any
# nonempty constant serves every pure re-lowering call below identically.
_PLANNING_ACTOR: Final[SubjectActor] = SubjectActor("conformance-compile-lane")


def _pinned_instant(tx_instant: str) -> TransactionInstant:
    """The lazy Transaction Instant a pure lowering runs at.

    The compile lane has no unit of work to own one, so it pins the entry's own
    ``at`` through the SAME ``FixedClock`` the run lane hands ``db.transact`` —
    the two lanes therefore capture the identical literal, and an entry whose
    lowering needs no Transaction-Time boundary captures nothing at all.
    """
    return TransactionInstant(FixedClock(dt.datetime.fromisoformat(tx_instant)))


@dataclass(frozen=True, slots=True)
class LoweredStep:
    """One lowered scenario step: its emission pointer and DML, and how to run it."""

    pointer: str
    statements: tuple[LoweredStatement, ...]
    is_write: bool
    rollback: bool


# The ONE reserved observation control key a case writeRow can author
# (`compatibility-case.schema.json` `$defs/writeRow`): the version the unit of
# work observed, stripped into a Version Observation before the durable
# instruction is built (the durable row forbids it, ADR 0013). Which write
# shapes are entitled to author it is `_observation_refusal`'s answer, not the
# schema's — one shared `writeRow` definition spans every shape.
_VERSION_OBSERVATION_KEY: Final[str] = "observedVersion"

# The two halves of an observed milestone's own EDGE coordinate. NEITHER is a
# write-row key in any shape (`compatibility-case.schema.json` `$defs/writeRow`):
# a temporal write observes a whole predecessor milestone, which no flat row cell
# can name, so a row carrying one is refused rather than stripped.
_TEMPORAL_GATE_KEY: Final[str] = "observedTxStart"
_TEMPORAL_VALID_START_KEY: Final[str] = "observedValidStart"

# Every reserved observation control key a case can spell on a write row. The
# durable instruction forbids all of them (ADR 0013); which one a given write is
# entitled to author BEFORE stripping is :func:`_observation_refusal`'s answer.
_ROW_OBSERVATION_KEYS: Final[tuple[str, ...]] = (
    _VERSION_OBSERVATION_KEY,
    _TEMPORAL_GATE_KEY,
    _TEMPORAL_VALID_START_KEY,
)


# What ONE grouped find step observed, in the order production filed it. A later
# write step of the same group names that step with `on` and settles against the
# record of its OWN key (`m-case-format` "Settling against a grouped find").
ObservedNodes = tuple[RetainedObservation, ...]

# Everything a `uow` group's find steps have observed so far, in step order — the
# store a grouped write with no `on` reference resolves its own evidence from.
# `_write_sequence_lowered` / `run_write_sequence_case` pass a permanently EMPTY
# sequence (a writeSequence carries no find steps at all): every keyed write's
# observation there comes solely from its own row's reserved `observedVersion`
# control key. The scenario RUN lane (`_run_uow_group`) builds one FRESH store per
# `uow` GROUP — never one spanning the whole scenario or crossing a group
# boundary; the scenario COMPILE lane (`_scenario_lowered`) never populates one at
# all, so no compile path ever consults a query result (`m-conformance-adapter`
# "Compile eligibility"). Reladomo prior art (semantics, not idioms): the
# transaction records the version at read time ("the shadow value read earlier")
# and threads it into the UPDATE bind
# (`docs/research/reladomo/09-transactions-locking.md:55-59`).
GroupObservations = list[RetainedObservation]


@dataclass(frozen=True, slots=True)
class _ResolvedWrite:
    """One case write entry's row, resolved against whatever evidence its lane
    supplies and ready for BOTH consumers of a write buffer.

    ``oracle_observation`` is the evidence as a VALUE, for the pure re-lowering
    (:func:`_lower_resolved`) that plans with no unit of work behind it. The real
    execution needs no peer of it: it states each write through the public verb
    its mutation names, against the value this unit's own read published, so what
    that write settles against is the claim the value already carries. An entry
    needing no evidence at all carries none.

    ``source_node`` is that value, where the lane's evidence already resolved it
    (:class:`GroupEvidence`), so the real write is addressed by the very node the
    oracle's evidence came from rather than by a second resolution of it.
    """

    instruction: PreparedWrite | PreparedTargetWrite
    oracle_observation: WriteObservation | None
    source_node: handle.WireEntity | None = None


def _versioned_non_temporal_version_attribute(
    model: AcceptedMetamodel, entity_name: str
) -> AttributeMetadata | None:
    """``entity_name``'s own optimistic-lock version ATTRIBUTE, when it is a
    VERSIONED, NON-TEMPORAL entity (`m-opt-lock`) — ``None`` otherwise, because a
    temporal entity observes a whole MILESTONE rather than a version, which is a
    different observation shape and not this attribute's
    (:func:`_milestone_observation`; `_build_temporal_instruction`). Resolved
    through the FAMILY-declaring entity
    (:func:`~parallax.conformance._mechanism.model_facts.family_declarer`): the
    version column is family-wide metadata declared only on the root
    (`m-opt-lock` "The version column")."""
    declaring = family_declarer(model, case_entity(model, entity_name))
    if declaring.declared_as_of_axes:
        return None
    return next((attr for attr in declaring.declared_attributes if attr.optimistic_locking), None)


def _refuse_unaccounted_document_milestone(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    row: Mapping[str, object],
    shadow: TemporalShadow,
) -> None:
    """Refuse a keyed temporal write over a Relational Document Layout target
    whose observation would be rebuilt from a tracked milestone the tracker can no
    longer account for whole.

    It governs the lanes that take their milestone from tracked case state rather
    than from a find — every writeSequence entry and every scenario write step
    not settling against a grouped find. A step that DOES settle against a
    grouped find needs no such refusal: its observation is the one production
    filed for the read, which retains the row's raw Structured Column, so nothing
    is rebuilt from declared members there.
    Under ``Columns`` the tracked members ARE the whole stored row.
    Under ``Document`` they are the whole stored document too, but only while
    every key in it came from this case's own fixtures and authored writes: a
    fixture row is authored member by member, and a successor this engine tracked
    was built from the plan that wrote it.

    Out-of-band statements are exactly what breaks that. They exist to store what
    no authored member can produce, this tracker never re-reads, and the framework
    issues no resolving read on behalf of a keyed write — so the successor such a
    write chains would be patched onto declared members alone and drop whatever
    those statements MAY have left in the document. Whether they touched this
    milestone at all is not knowable from a naive ``sql`` string, so the doubt
    alone refuses: naming the shape is the only answer that cannot be silently
    wrong.

    Which milestone the write addresses is what decides it
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.accounts_for`),
    never merely whether the case ran such statements somewhere: a milestone this
    case's own later write opened is a whole account of its row again, so an
    insert-then-update chain over a document-mapped target stays legal beside any
    out-of-band statement (`m-case-format`: a keyed write consumes the milestone
    the case's own fixtures and earlier entries left current).
    """
    if shadow.accounts_for(model, entity, row):
        return
    entity_name = entity.identity.canonical
    column = _shared_document_column(model, entity_name)
    if column is None:
        return
    raise EngineError(
        f"a keyed temporal write on {entity_name!r} addresses a milestone this case's own "
        f"out-of-band statements may have overtaken or stored, and its document-resident members "
        f"are stored in the shared Structured Column {column!r} — this lane observes the "
        "milestone from tracked case state, which never saw what those statements stored, so "
        "the successor it chains would lose whatever else that document holds"
    )


def _refuse_materialized_case_state(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    row: Mapping[str, object],
    shadow: TemporalShadow,
) -> None:
    """Refuse a keyed temporal write whose observation would come from case state
    a materializing predicate write of this same case already moved
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.moved_by_materialization`).

    That write resolved its own rows inside production, retired the milestone it
    found for each and opened a successor, and returned neither the plan nor the
    rows — so the milestone this lane still holds current for that key is one the
    database closed. A close addressed at it matches no row.

    The composition is refused rather than executed because the two would not even
    fail the same way. A real caller could not have issued this write at all
    without a Temporal Observation, which only a read supplies; their observation
    would name the milestone the predicate write opened, and gating a close on the
    retired one is what production reports as a stale write. This lane's
    observation comes from tracked case state instead — the whole reason the
    tracker exists — and would issue a well-formed statement that quietly affects
    zero rows. Naming the shape is the only answer that cannot be silently wrong.

    Scope is the milestone, not the case: a target the predicate write never named
    keeps its tracked state, and a milestone this case's own later write opens for
    the moved key is a current account of it again.
    """
    if not shadow.moved_by_materialization(model, entity, row):
        return
    raise EngineError(
        f"a keyed temporal write on {entity.identity.canonical!r} settles against case state "
        "that this case's own materializing predicate write already moved — that write closed "
        "the tracked milestone and opened a successor inside production, whose plan this lane "
        "never sees, so the close this write would address matches no row. A real caller could "
        "reach this step only by READING the row, and would gate on the milestone the predicate "
        "write opened; gating on the retired one is a stale write, not a zero-row success. "
        "Author the materializing write and the keyed write as separate cases"
    )


def _shared_document_column(model: AcceptedMetamodel, entity_name: str) -> str | None:
    """The name of the shared Structured Column ``entity_name``'s rows carry under
    Relational Document Layout, or ``None`` under ``Columns``, which has none."""
    entity = entity_by_name(model, entity_name)
    layout = None if entity is None else storage_layout.view(model).entity(entity.identity)
    if layout is None:  # pragma: no cover - an observed node names a row-owning Entity
        return None
    return next(
        (
            slot.column.name
            for slot in layout.columns
            if isinstance(slot.contributor, storage_layout.RelationalDocument)
        ),
        None,
    )


def entry_instant(entry: Mapping[str, object]) -> str:
    """The tx_instant an entry's OWN choreography unit (transaction) runs at
    (m-temporal-write ``at``; ADR 0010: the Clock, never a
    per-operation override). A non-temporal entry names none — its Clock
    value is inert, so :data:`INERT_CLOCK_INSTANT` stands in."""
    at = entry.get("at")
    return at if isinstance(at, str) else INERT_CLOCK_INSTANT


def _is_temporal_entity(model: AcceptedMetamodel, entity_name: str) -> bool:
    return bool(family_declarer(model, case_entity(model, entity_name)).declared_as_of_axes)


_TEMPORAL_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})


def _temporal_entry_row(
    entity_name: str, mutation: str, raw_rows: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    """The ONE case-authored row a TEMPORAL write entry mutates.

    `m-unit-work` "A temporal keyed instruction carries exactly one row": each row
    closes its own current milestone, consumes its own Temporal Observation, and
    opens its own successors, and a temporal entity never collapses into a
    set-based statement (`m-batch-write`), so several rows under one entry denote
    several independent milestone chains rather than one wider write. That rule
    forbids reducing the entry to a first row the case did not single out, so it
    is refused HERE, where the authoring diagnosis can name the entry. The shared
    case schema cannot express it, because the row count it may admit depends on
    whether the target entity is temporal, which only the model knows.

    Refusing before :func:`_durable_row` is what makes "every case-authored row
    reaches the seam" true rather than approximately true: a row this function
    admits is the entry's only row, so none is left behind unrefused.
    """
    if len(raw_rows) != 1:
        raise EngineError(
            f"{entity_name!r} {mutation!r}: a temporal write entry carries ONE row "
            f"({len(raw_rows)} authored) — each row closes its own milestone and chains its "
            "own successors, and a temporal entity never collapses into a set-based statement "
            "(m-unit-work 'A temporal keyed instruction carries exactly one row'); author one "
            "entry per row"
        )
    return raw_rows[0]


class TemporalEvidence(Protocol):
    """Where a grouped or ungrouped temporal write's predecessor comes from — the
    one decision about a temporal write that differs by lane.

    ``settle`` answers the observation the write's close and chain consume, and
    the published value it came from where the answer was resolved from one.
    """

    def settle(
        self,
        entity: EntityMetadata,
        key: ObjectKey | None,
        row: Mapping[str, object],
        valid_from: dt.datetime | None,
    ) -> tuple[TemporalObservation | None, handle.WireEntity | None]: ...


@dataclass(frozen=True, slots=True)
class CaseStateEvidence:
    """Evidence for a lane that models case state: the milestone ``shadow``
    tracks for the key (`m-temporal-write` "the engine supplies
    observed rows from case state" — never an implicit resolving read), or, where
    the entry named a find of its `uow` group with ``on``, the claim that find
    retained (:func:`_settled_against_source`).

    A milestone a materializing predicate write of this case already moved
    (:func:`_refuse_materialized_case_state`), and one whose tracked members can
    no longer account for the whole stored row
    (:func:`_refuse_unaccounted_document_milestone`), are both refused before
    the tracker answers. Whichever answers, the milestone it names is retired
    from the tracker, because the write's close consumes it.
    """

    model: AcceptedMetamodel
    shadow: TemporalShadow
    named: ObservedNodes | None

    def settle(
        self,
        entity: EntityMetadata,
        key: ObjectKey | None,
        row: Mapping[str, object],
        valid_from: dt.datetime | None,
    ) -> tuple[TemporalObservation | None, handle.WireEntity | None]:
        observation: TemporalObservation | None
        if self.named is None:
            _refuse_materialized_case_state(self.model, entity, row, self.shadow)
            _refuse_unaccounted_document_milestone(self.model, entity, row, self.shadow)
            observation = self.shadow.resolve(self.model, entity, row)
        else:
            settled = _settled_against_source(entity.identity.canonical, key, self.named)
            # A temporal row's evidence is its whole predecessor milestone; a
            # versioned target's Version Observation can never answer a lookup
            # this branch reached, because the branch is chosen by temporality.
            assert isinstance(settled, TemporalObservation)
            observation = settled
        if observation is not None:
            self.shadow.retire(self.model, entity, observation)
        return observation, None


@dataclass(frozen=True, slots=True)
class GroupEvidence:
    """Evidence for a lane that models no case state: the claim production
    retained onto the value the write is handed, chosen as an application would
    choose it (:func:`_group_source_node` — the ``on``-named find, else the
    group's own insert, else its latest reading).

    Nothing here computes a predecessor, so the evidence is exactly what that
    group's own reads saw, whatever any other session has since committed. A
    write whose plan would need more than that is refused as unwitnessed rather
    than modeled: a key its group already settled would compose onto a buffered
    write, and a key its group opened carries no reading at all.
    """

    state: GroupState
    named: Sequence[handle.WireEntity] | None

    def settle(
        self,
        entity: EntityMetadata,
        key: ObjectKey | None,
        row: Mapping[str, object],
        valid_from: dt.datetime | None,
    ) -> tuple[TemporalObservation | None, handle.WireEntity | None]:
        name = entity.identity.canonical
        if key is not None and key in self.state.settled:
            raise EngineError(
                f"{name!r}: a second temporal write of {key!r} in one `uow` group composes "
                "onto the write its group already buffered — state no read of the group "
                "retained, which this lane does not model"
            )
        node = _group_source_node(name, key, self.state, self.named, valid_from)
        origin = read_origin_of(node)
        retained = None if origin is None else origin.observation
        if retained is None:
            raise EngineError(
                f"{name!r}: a temporal write of {key!r} composes onto the row its own `uow` "
                "group inserted — state no read of the group retained, which this lane does "
                "not model"
            )
        evidence = retained.evidence
        assert isinstance(evidence, TemporalObservation)  # chosen by temporality, as above
        if key is not None:
            self.state.settled.add(key)
        return evidence, node


def _build_temporal_instruction(
    entry: Mapping[str, object],
    model: AcceptedMetamodel,
    evidence: TemporalEvidence,
    unit_inserted: set[ObjectKey],
) -> _ResolvedWrite:
    """One TEMPORAL writeSequence/scenario entry -> its canonical keyed
    instruction plus the observation its close/chain consumes, which
    ``evidence`` answers (:class:`TemporalEvidence`).

    The corpus and canonical instruction share the same ``validFrom`` / ``until``
    spelling. Bounds are instruction-level fields; temporal row payloads never
    carry authoring aliases. A temporal entry carries exactly ONE row, which
    :func:`_temporal_entry_row` enforces rather than assumes.

    That row reaches the same :func:`_durable_row` seam every other producer's
    does, which entitles a temporal row to no observation control key at all —
    the observation this entry consumes is a whole predecessor milestone, never a
    cell the row carried.

    ``unit_inserted`` is the SAME choreography unit's own running set of
    (entity, pk) pairs a PRIOR entry in this SAME buffer already inserted
    (`m-unit-work` same-transaction coalescing, `m-temporal-write-008` /
    `m-temporal-write-030`): a later entry targeting one of them is a
    same-buffer coalescing candidate whose OWN close/chain arithmetic never
    runs (the planner folds it into the pending insert before finalization
    ever sees it) — its observation is forced to `None`, and ``evidence`` is never
    asked. What the ledger ends up holding for the key is the COALESCED row:
    :func:`_lower_resolved` tracks the surviving Planned Insert off the finished
    plan, so the tracked state is the milestone the flush actually writes rather
    than a stand-in for it.
    """
    mutation = cast("str", entry["mutation"])
    entity_name = cast("str", entry["entity"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    row, _authored_none = _durable_row(
        model, entity_name, mutation, _temporal_entry_row(entity_name, mutation, raw_rows)
    )
    valid_from = cast("str | None", entry.get("validFrom"))
    until = cast("str | None", entry.get("until"))
    doc: dict[str, object] = {"mutation": mutation, "entity": entity_name, "rows": [row]}
    if valid_from is not None:
        doc["validFrom"] = valid_from
    if until is not None:
        doc["until"] = until
    instruction = instructions.deserialize(doc)
    prepared = _case_ingress.prepare_case_write(instruction, model)
    assert isinstance(prepared, PreparedKeyedWrite)  # a temporal entry is always keyed
    entity_metadata = case_entity(model, entity_name)
    pk_key = object_key(prepared, model)
    is_insert = mutation in _TEMPORAL_INSERT_MUTATIONS
    is_coalescing_candidate = not is_insert and pk_key is not None and pk_key in unit_inserted
    observation: TemporalObservation | None = None
    source_node: handle.WireEntity | None = None
    if not is_insert and not is_coalescing_candidate:
        window = prepared.valid_time_window
        observation, source_node = evidence.settle(
            entity_metadata, pk_key, row, None if window is None else window.start
        )
    if is_insert and pk_key is not None:
        unit_inserted.add(pk_key)
    return _ResolvedWrite(prepared, observation, source_node)


def _settled_against_source(
    entity_name: str, pk_key: ObjectKey | None, source: ObservedNodes
) -> WriteObservation:
    """The observation the PURE re-lowering oracle plans a write with when its
    step named the find it came from (`m-case-format` *Settling against a grouped
    find*).

    The named find's own record for this key is what production retained onto the
    value the write is handed, so the oracle plans with the state the read
    actually saw rather than a coordinate this engine re-derived and hoped
    agreed. That is what makes a store keyed by identity alone observably wrong
    here: a key holding several current rectangles — or, on a versioned target,
    several observed generations of one row — has no single answer, while the
    retained record names exactly one.

    A named find that observed no row of this key — or several, which no single
    value could have come from — is an authoring defect, refused here where the
    diagnosis can name the step.
    """
    matched = [record for record in source if record.key.object == pk_key]
    if len(matched) != 1:
        raise EngineError(
            f"{entity_name!r}: the find step this write settles against observed "
            f"{len(matched)} rows of {pk_key!r} — a keyed write settles against the ONE "
            "observed state the value it was handed came from (m-case-format 'Settling "
            "against a grouped find')"
        )
    return matched[0].evidence


def is_predicate_write_step(raw_write: object) -> bool:
    """Whether a scenario write step's own ``write`` field is a single
    STRUCTURED PREDICATE-write instruction (`mutation` / `target` / optional
    `assignments` — `m-case-format`'s predicate-selected shape, e.g.
    ``m-batch-write-005``) rather than the keyed-write entry LIST
    (`m-case-format`'s buffered-keyed-write shape) this engine's keyed path
    lowers. A predicate write's `target` names its entity/predicate; a keyed
    write is a plain list of ``{mutation, entity, rows}`` entries — the SHAPE
    signal (a bare mapping vs. a list) is structural, never inferred from a
    ``KeyError``; this shape routes to the readless/materializing
    predicate-write
    translation instead — see :func:`_lower_predicate_write_step` /
    :func:`_run_materializing_pair`.
    """
    return isinstance(raw_write, Mapping)


def write_entries(raw_write: object) -> Sequence[Mapping[str, object]]:
    """A scenario write step's own ``write`` field as its keyed-write entry
    LIST — callers check :func:`is_predicate_write_step` FIRST; this is never
    reached for a structured predicate-write instruction."""
    return cast("Sequence[Mapping[str, object]]", raw_write)


def _is_versioned_entity(model: AcceptedMetamodel, entity_name: str) -> bool:
    declaring = family_declarer(model, case_entity(model, entity_name))
    return any(attr.optimistic_locking for attr in declaring.declared_attributes)


def _observation_refusal(
    model: AcceptedMetamodel, entity_name: str, mutation: str, key: str
) -> str | None:
    """Why a write row against ``entity_name`` under ``mutation`` may not author
    the reserved observation control key ``key`` — ``None`` when that pair is the
    ONE the corpus vocabulary entitles to author it.

    This is the whole licensing rule `m-unit-work`'s "Absence is structural"
    states, total over every (target, mutation) pair a case can write, so no
    producer decides any part of it locally. A VERSIONED, NON-TEMPORAL update or
    delete may author ``observedVersion``; nothing else may author anything:

    - neither half of an observed milestone's own EDGE coordinate
      (``observedTxStart`` / ``observedValidStart``) is entitled ANYWHERE. Neither
      is a write-row control key in any shape:
      `compatibility-case.schema.json`'s ``writeRow`` reserves ``observedVersion``
      alone and every other key names an entity member. Stripping one from a row
      — or projecting the row past it — would silently discard the very
      coordinate the author meant to observe.
    - a TEMPORAL target's write observes a whole predecessor MILESTONE, which no
      flat row cell can name. It resolves either from tracked case state
      (:class:`~parallax.conformance.temporal_state.TemporalShadow`) or, where the
      write's own step named the find it settles against, from the observations
      that `uow` group's reads filled (:func:`_settled_against_source`). Which of
      the two supplies it changes nothing here: neither is a cell the row may
      carry.
    - an INSERT opens a row rather than writing against one, so an observed
      version names a milestone that does not yet exist.
    - an UNVERSIONED non-temporal target has no version to observe, so an
      observed version on it is evidence about nothing. Wrapping such a row would
      still exclude it from batching, splitting a collapsible run into one
      statement per key on the strength of an observation the planner then
      ignores.

    The last two restate what `compatibility-case.schema.json`'s own prose
    already says — "absent on a versioned insert and on a non-versioned write" —
    and which its single shared ``writeRow`` definition cannot express. Deciding
    them here is what makes the carrier's own guarantee complete: the carrier can
    decide "is this an insert?" from the instruction alone, but "is this target
    versioned?" and "is it temporal?" need the model, which only this translation
    holds.
    """
    if key in {_TEMPORAL_GATE_KEY, _TEMPORAL_VALID_START_KEY}:
        return (
            f"a write row authors no `{key}` (m-case-format: a writeRow reserves "
            "`observedVersion` alone and every other key names an entity member — a temporal "
            "write observes a whole predecessor milestone, which no row cell can name)"
        )
    if _is_temporal_entity(model, entity_name):
        return (
            f"a temporal row authors no `{key}` (m-unit-work: a temporal write observes a whole "
            "predecessor milestone, which no flat row cell can name — the engine resolves one "
            "from tracked case state or from the find its own step settles against)"
        )
    if mutation in INSERT_MUTATIONS:
        return (
            f"an insert row authors no `{key}` (m-unit-work: inserts have no observation — an "
            "observed version names the milestone a write against an EXISTING row observed)"
        )
    if _versioned_non_temporal_version_attribute(model, entity_name) is None:
        return (
            f"an unversioned row authors no `{key}` (m-unit-work: unversioned Non-Temporal "
            "writes have no observation — there is no observed version for it to name)"
        )
    return None


def _durable_row(
    model: AcceptedMetamodel, entity_name: str, mutation: str, row: Mapping[str, object]
) -> tuple[dict[str, object], VersionObservation | None]:
    """One case-authored write row as the DURABLE row a write carries, plus the
    Version Observation that row described (``None`` when it described none — an
    unobserved write, one whose observation instead comes from this SAME `uow`
    group's own prior find step (:func:`_observed_nodes`), or a temporal
    write, whose observation is a whole milestone — held by
    :class:`TemporalShadow`, or, where the step named the find it settles against,
    by that same group's observations).

    THE seam a case row becomes a durable row through — the only one. Every
    producer of a case-authored row goes through it, whatever the row's shape or
    lane: :func:`_build_instructions` for a non-temporal writeSequence/scenario
    entry, :func:`_build_temporal_instruction` for a temporal one, and
    :func:`_resolve_conflict_writes` for a conflict attempt's ``write``. EVERY row
    of each reaches it, not merely the first: the two non-temporal producers
    resolve the whole authored sequence (:func:`_durable_rows`), and the temporal
    one admits a single row and refuses a plural entry outright
    (:func:`_temporal_entry_row`) rather than settling one row and discarding the
    rest.

    Refusal (:func:`_observation_refusal`) and stripping are one
    indivisible step here precisely because they were separable before: a
    producer that copied the row itself got a perfectly usable durable row while
    silently skipping the refusal, and each new write shape rediscovered the
    hole. There is now no way to obtain a durable row without being refused.

    The durable row never carries a control key: the write-instruction schema
    forbids every one of them (ADR 0013), which `instructions.deserialize`
    enforces as well.
    """
    for key in _ROW_OBSERVATION_KEYS:
        if key not in row:
            continue
        refusal = _observation_refusal(model, entity_name, mutation, key)
        if refusal is not None:
            raise EngineError(f"{entity_name!r} {mutation!r}: {refusal}")
    durable = dict(row)
    version = durable.pop(_VERSION_OBSERVATION_KEY, None)
    if version is None:
        return durable, None
    return durable, VersionObservation(observed_version=cast("int", version))


def _durable_rows(
    model: AcceptedMetamodel,
    entity_name: str,
    mutation: str,
    raw_rows: Sequence[Mapping[str, object]],
) -> list[tuple[dict[str, object], VersionObservation | None]]:
    """Every row of one multi-row write entry through :func:`_durable_row`,
    resolved EAGERLY so an entry is refused on any row it authors before its
    first row is planned — a partially translated entry is never observable."""
    return [_durable_row(model, entity_name, mutation, row) for row in raw_rows]


def _binds_row_observations(
    model: AcceptedMetamodel,
    entity_name: str,
    mutation: str,
    raw_rows: Sequence[Mapping[str, object]],
) -> bool:
    """Whether a non-temporal write entry's rows each carry their OWN object key
    and observation, mirroring what that many separate
    `Transaction.insert`/`.update`/`.delete` calls would buffer — rather than
    arriving as anonymous rows free to be merged back together.

    This decides OBSERVATION BINDING only, never statement count:
    :func:`_build_instructions` buffers one single-row instruction per row
    regardless, and leaves every merge to the planner's own collapse stage
    (:func:`_lower_resolved`, `parallax.snapshot.handle.ScopedDatabase.transact`).
    What a bound observation changes is that the planner refuses to merge that
    row at all, which is exactly the point — a merged multi-row instruction has
    nowhere to carry a per-row observed version. The question is answered with
    :func:`~parallax.core.batch_write.collapses`, the same injected
    `m-batch-write` collapse-eligibility vocabulary the planner consults, so
    binding an observation never contradicts the planner's own eligibility
    answer.

    Derived SEMANTICALLY from the instruction and model — mutation kind,
    versioned-ness, computed/allocated primary keys, and (for update) per-key
    value uniformity — never from the case's own authored ``statements`` count,
    which is a count-consistency ASSERTION only (`compatibility-case.schema.
    json`) verified separately by
    :func:`_check_statement_count_consistency`, never a semantics
    discriminator:

    - a single row always binds its own observation (nothing to merge it with,
      so nothing is given up);
    - `batch_write.insert_collapses` — an INSERT decomposes only when the
      target's primary key is pk-gen MANAGED (`m-pk-gen`'s `sequence`/`max`
      strategies, ``m-pk-gen-001``..`-012``); a VERSIONED insert still
      collapses (the initial version is a derived constant, never observed);
    - `batch_write.update_collapses` — a VERSIONED target's update always
      decomposes (the gate/advance binds a per-row observed version,
      `m-opt-lock`, ADR 0014); an unversioned target decomposes per distinct
      key only when its rows assign NON-uniform values (``m-batch-write-002``),
      collapsing into one `IN`-predicate statement when uniform
      (``m-batch-write-001``'s own update entry);
    - `batch_write.delete_collapses` — a VERSIONED target's delete always
      decomposes (``m-batch-write-004``'s versioned per-key delete
      materialize); an unversioned one collapses to one `IN`-list statement.
    """
    if len(raw_rows) == 1:
        return True
    entity = case_entity(model, entity_name)
    return not batch_write.collapses(model, entity, mutation, raw_rows)


def _check_statement_count_consistency(
    entries: Sequence[Mapping[str, object]], emitted_count: int
) -> None:
    """``statements`` is a count-CONSISTENCY assertion the schema intends
    (`compatibility-case.schema.json`), never a semantics discriminator — verify
    the authored count against the statements this buffer's flush ACTUALLY
    emitted and fail loudly on a mismatch (an authoring error), rather than
    silently trusting either number.

    ``emitted_count`` comes from the real plan (:func:`_lower_resolved`), so the
    assertion sees every stage the planner applies — coalescing, physical-shape
    collapse, and the ELISION that drops a keyed update whose effective change
    set is empty (`m-opt-lock`'s no-op write) — rather than a second,
    drift-prone reconstruction of them.

    Only a writeSequence entry authors ``statements`` (a buffered scenario write
    entry has no such key at all), and a writeSequence entry is planned ALONE,
    so the sum below spans exactly one entry in practice; summing is what
    `m-case-format` asserts either way ("the DML statement count MUST equal the
    sum of the steps' declared statement counts"). An entry that authors nothing
    grades nothing.
    """
    declared = [entry.get("statements") for entry in entries]
    if any(count is None for count in declared):
        return
    expected = sum(cast("int", count) for count in declared)
    if expected != emitted_count:
        described = ", ".join(
            f"{entry.get('entity')!r} {entry.get('mutation')!r}" for entry in entries
        )
        raise EngineError(
            f"{described}: authored `statements: {expected}` does not match the "
            f"{emitted_count} statement(s) this flush emits (m-case-format: `statements` is a "
            "count-consistency assertion, not a semantics discriminator)"
        )


def _seed_insert_version(
    model: AcceptedMetamodel, entity_name: str, mutation: str, row: Mapping[str, object]
) -> dict[str, object]:
    """A VERSIONED, non-temporal entity's INSERT row, with the derived initial
    version seeded when the case-authored row omits it
    (`opt_lock.INITIAL_VERSION`) — a no-op for every other mutation/entity/row
    shape.

    `parallax.snapshot.handle`'s own write finalization derives the INITIAL
    version at the version Attribute UNCONDITIONALLY, ignoring any row-carried
    value
    — every reachable insert witness already authors an explicit `version`
    matching this SAME constant (`m-unit-work-001`/`-008`), coincidentally
    satisfying `~parallax.core.unit_work.write_validate.validate_write`'s
    required-attribute check along the way, but a same-transaction coalescing
    pair whose insert never survives to ANY golden DML
    (`m-unit-work-010`'s insert-then-delete cancellation) has no golden bind
    to match and so may omit it. The RUN lane's own translation
    (`_execute_write_unit`, mirroring "as many separate `Transaction.insert`
    calls") states each insert through `tx.wire.insert`, whose Create Payload
    carries no framework-owned member at all (`_wire_insert_payload` drops the
    seeded version), and a case's own authored `version` is what a
    required-attribute check would have wanted; since the framework discards
    whatever the row carries at lowering regardless, seeding the identical
    constant here changes no compiled emission.
    """
    if mutation != "insert":
        return dict(row)
    version_attr = _versioned_non_temporal_version_attribute(model, entity_name)
    if version_attr is None or version_attr.identity.name in row:
        return dict(row)
    return {**row, version_attr.identity.name: opt_lock.INITIAL_VERSION}


def _build_instructions(
    entry: Mapping[str, object],
    model: AcceptedMetamodel,
    evidence: TemporalEvidence,
    unit_inserted: set[ObjectKey],
    group_observations: GroupObservations,
    source: ObservedNodes | None,
) -> list[_ResolvedWrite]:
    """One case write entry -> one or more canonical keyed write instructions.

    A STRUCTURED PREDICATE-write entry (`target`/`predicate` shaped, no
    `entity` key at all) refuses loudly here too — defensive coverage for the
    writeSequence path, which shares this function with every scenario write
    entry (the scenario `write`-field-is-itself-a-mapping shape is caught one
    layer up, by :func:`is_predicate_write_step`, and routed to the
    readless/materializing predicate-write translation instead — a predicate
    write is never a legal writeSequence entry shape, `m-case-format`'s
    writeSequence vocabulary is keyed-only).

    A TEMPORAL entity's entry dispatches to :func:`_build_temporal_instruction`,
    settling against what ``evidence`` answers, and admits exactly ONE row: its
    authored ``statements`` count is the DML
    STATEMENT count (a close plus zero-to-three chained opens), a DIFFERENT
    accounting from the row-decomposition below, which assumes non-temporal
    semantics and is never applied to a temporal entry's entry. Decomposition
    would answer no question there either — a temporal entity never collapses
    (`m-batch-write`), so there is no set-based statement for a decomposed row to
    be re-merged into, and several rows under one entry are several independent
    milestone chains the case must author as several entries.

    Otherwise, a write entry carries the instruction triple (``mutation`` /
    ``entity`` / ``rows``) beside case-authoring keys (``note`` / ``statements``
    / ``roundTrips`` / ``rollback``). ``rows`` MAY batch several logical
    per-object writes into one entry (the write-instruction schema's "one or
    more rows" vocabulary), and this seam ALWAYS buffers one single-row
    instruction per row, exactly as that many separate ``Transaction`` calls
    would. Nothing is ever pre-merged here: whether buffered rows share one
    statement is the planner's own collapse stage to decide.

    :func:`_durable_rows` resolves every row first, so an observation surviving
    from a row belongs to a versioned non-temporal write against an existing row
    — the only write shape `m-unit-work` gives an observation at all.

    What :func:`_binds_row_observations` derives SEMANTICALLY is whether each row
    binds its OWN object key and Version Observation (its reserved
    ``observedVersion`` stripped into one — `m-opt-lock`; ADR 0013), which in
    turn tells the planner to keep that row separately identifiable rather than
    merging it. A row that authors no observed version takes its evidence from
    the group instead: from the find the entry NAMED with ``on``
    (:func:`_settled_against_source`) where it named one, and otherwise from
    ``group_observations`` — a writeSequence's own permanently-empty sequence, or
    (the scenario RUN lane only) a `uow` GROUP's own prior find step(s), scanned
    from the end. A versioned target holds one ROW per primary key but a unit of
    work may hold several observed GENERATIONS of it, so the unnamed fallback
    answers the latest reading while the reference is what names any other.

    An entry's authored ``statements`` count is graded later, once
    :func:`_lower_resolved` has actually planned and lowered the buffer these
    instructions join (:func:`_check_statement_count_consistency`) — nothing
    here predicts what the flush will emit.
    """
    if "entity" not in entry:
        target = entry.get("target")
        target = (
            cast("Mapping[str, object]", target).get("entity")
            if isinstance(target, Mapping)
            else None
        )
        raise EngineError(
            f"a writeSequence entry must be a keyed mutation (`entity` + `rows`) — a "
            f"structured predicate-selected instruction ({entry.get('mutation')!r} on "
            f"{target!r}) is scenario-write-only (m-case-format: the writeSequence "
            "entry vocabulary is keyed-only)"
        )
    entity_name = cast("str", entry["entity"])
    if "row" in entry:
        return [_build_target_instruction(entry, model)]
    if _is_temporal_entity(model, entity_name):
        return [_build_temporal_instruction(entry, model, evidence, unit_inserted)]
    mutation = cast("str", entry["mutation"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    durable = _durable_rows(model, entity_name, mutation, raw_rows)
    binds_observations = _binds_row_observations(model, entity_name, mutation, raw_rows)
    out: list[_ResolvedWrite] = []
    opens_a_row = mutation in INSERT_MUTATIONS
    for clean_row, row_observation in durable:
        observation: WriteObservation | None = row_observation
        clean_row = _seed_insert_version(model, entity_name, mutation, clean_row)
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity_name, "rows": [clean_row]}
        )
        assert isinstance(instruction, KeyedWrite)  # a `rows` document is a keyed write
        prepared = _case_ingress.prepare_case_write(instruction, model)
        if binds_observations and not opens_a_row:
            key = object_key(prepared, model)
            if observation is None and key is not None:
                if source is not None:
                    observation = _settled_against_source(entity_name, key, source)
                else:
                    observed = _observed_for(group_observations, key)
                    if observed is not None:
                        observation = observed.evidence
        else:
            observation = None
        out.append(_ResolvedWrite(prepared, observation))
    return out


def _build_target_instruction(
    entry: Mapping[str, object], model: AcceptedMetamodel
) -> _ResolvedWrite:
    """A caller-addressed entry as the target instruction it states, prepared by
    the one producer every ingress reaches. It carries its caller's revision
    and no evidence of any read."""
    instruction = instructions.deserialize(
        {
            name: value
            for name, value in entry.items()
            if name in ("mutation", "entity", "row", "ifVersion", "ifTxStart", "validFrom", "until")
        }
    )
    assert isinstance(instruction, TargetWrite)  # a `row` document is a target write
    return _ResolvedWrite(_case_ingress.prepare_case_write(instruction, model), None)


def _observed_for(observations: GroupObservations, key: ObjectKey) -> RetainedObservation | None:
    """The LATEST claim this group's finds retained for ``key``, or ``None``.

    Latest rather than first: a versioned Non-Temporal target holds one row per
    primary key, so a second find of it reads whatever state the row now stands
    in, and a write this group authors next settles against that reading rather
    than against a stale one. Production keeps every observed state distinct and
    lets each source value name its own; an ordered store scanned from the end
    is how a lane holding instructions instead of values reaches the same one.
    """
    for record in reversed(observations):
        if record.key.object == key:
            return record
    return None


def _resolve_entries(
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    shadow: TemporalShadow,
    group_observations: GroupObservations,
) -> list[_ResolvedWrite]:
    """Every entry in one choreography unit's buffer -> its resolved
    instructions (retiring from ``shadow`` the milestone each close consumes) —
    the shared core both the PURE lowering (:func:`_lower_resolved`) and the
    RUN lane's real `db.transact` execution (:func:`_execute_write_unit`)
    consume, so a temporal write's observation is never resolved (or its
    milestone retired) twice for one unit. ``unit_inserted`` tracks this SAME
    buffer's own same-transaction coalescing candidates (see
    :func:`_build_temporal_instruction`) across the whole unit.
    ``group_observations`` is READ-ONLY here — an always-empty sequence for a
    writeSequence entry or an ungrouped scenario write step (neither ever
    consults a find-derived observation), or (the scenario RUN lane only) the
    nodes a `uow` GROUP's own find steps published (:func:`_run_uow_group`) before
    this unit ran — never a store spanning the whole scenario. A grouped write
    step resolves its submissions one at a time instead, each against the find
    its own ``on`` names (:func:`run_group_step`)."""
    resolved: list[_ResolvedWrite] = []
    unit_inserted: set[ObjectKey] = set()
    evidence = CaseStateEvidence(model, shadow, None)
    for entry in entries:
        resolved.extend(
            _build_instructions(entry, model, evidence, unit_inserted, group_observations, None)
        )
    return resolved


def instruction_evidence(
    model: AcceptedMetamodel,
    instruction: PreparedKeyedWrite,
    *,
    supplied: WriteObservation | RetainedObservation | None,
) -> SettledEvidence | None:
    """What a keyed write settles against, for an oracle holding the INSTRUCTION
    rather than the value it was derived from.

    Evidence the case supplied is what the write settles against, used as given:
    it is the one licensed way a keyed write settles against a row no read of the
    writing unit of work materialized, so a write that can hold none REFUSES it
    at its carrier rather than having it dropped here. An entry that supplied
    none reaches :func:`~parallax.core.opt_lock.settled_evidence` over the
    instruction's own target and mutation, exactly what a typed verb reads off a
    source value's hint, so this readless oracle settles each write as the verb
    the same write goes through would.
    """
    if supplied is not None:
        return supplied
    return opt_lock.settled_evidence(
        opt_lock.optimistic_key(model, instruction.target.identity),
        instruction.mutation,
        object_key=object_key(instruction, model),
        observation=None,
    )


def _buffered(
    instruction: PreparedWrite | PreparedTargetWrite,
    observation: WriteObservation | None,
    model: AcceptedMetamodel,
) -> BufferItem:
    """One resolved entry as the buffer item a unit of work would hold for it,
    settled against :func:`instruction_evidence`. Whether an observation may
    exist at all is decided BEFORE this point, by :func:`_durable_row` — the one
    seam every producer's rows pass through — and by the carriers' own structural
    refusals; this function only forwards what they left.
    """
    if isinstance(instruction, PreparedTargetWrite):
        return target_write(instruction, inheritance.view(model))
    assert isinstance(
        instruction, PreparedKeyedWrite
    )  # every other producer of this seam resolves keyed writes
    return buffered_write(
        instruction, instruction_evidence(model, instruction, supplied=observation)
    )


def _lower_resolved(
    resolved: Sequence[_ResolvedWrite],
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
    advances: TemporalShadow | None,
) -> tuple[LoweredStatement, ...]:
    """Plan one write buffer through the SAME ``build_write_planner`` factory
    the composition layer uses (`parallax.snapshot.handle.ScopedDatabase.transact`)
    and lower each survivor — PURE, no database. The planner is the ONE
    authority that merges a case entry's rows: every entry arrives as its own
    per-row instructions, and which of them share a statement is decided HERE,
    per physical shape, by the same `batch_write.collapses` eligibility answer
    production consults.

    ``entries`` are the case entries ``resolved`` was built from, carried only so
    their authored ``statements`` counts can be graded against the statements
    this ONE plan actually emits (:func:`_check_statement_count_consistency`) —
    the count is never derived from a second, reconstructed plan.

    The case-state ledger, ``advances``, moves HERE, from THIS plan's own opened rows
    (:meth:`TemporalShadow.track_opened`), and keeps every milestone a write left
    unchanged (:meth:`TemporalShadow.keep_unchanged`) — the milestone a later choreography
    unit observes is the one this write actually plans, so there is no second
    expansion of the same topology to drift from it. The close's retirement
    happened at resolution, where the observation it consumed is known. Both
    advances belong to the boundary the caller stages them on
    (:meth:`TemporalShadow.staged`), so a doomed unit's are discarded with its
    rows. A lane that models no case state passes ``None``: nothing advances, and
    a range whose coverage no observation holds is refused rather than bound.
    """
    buffer = [_buffered(write.instruction, write.oracle_observation, model) for write in resolved]
    plan, statements = _plan_and_lower(
        model, dialect, concurrency, tx_instant, buffer, coverage=advances
    )
    _check_statement_count_consistency(entries, len(statements))
    if advances is None:
        return statements
    advances.keep_unchanged(
        model,
        plan.steps,
        (
            (write.instruction.target, write.oracle_observation)
            for write in resolved
            if isinstance(write.instruction, PreparedKeyedWrite)
            and isinstance(write.oracle_observation, TemporalObservation)
        ),
    )
    advances.track_opened(model, plan.steps, retired=plan.changed)
    return statements


def _plan_and_lower(
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
    buffered_writes: Sequence[BufferItem],
    *,
    coverage: TemporalShadow | None = None,
) -> tuple[ExecutedPlan, tuple[LoweredStatement, ...]]:
    """Plan one write buffer through the SAME ``build_write_planner`` factory the
    composition layer uses and lower every surviving step PURELY, in execution
    order, beside the plan they came from.

    The buffer is composed first, as a unit of work composes each write it
    admits. A range whose requested window reaches coverage its observations do
    not hold is bound to the case state ``coverage`` tracks — the rows the
    execution's own coverage read returns — so its statements stand where the
    execution runs them; a lane tracking no case state has none to bind to.
    """
    planner = build_write_planner(model)
    instant = _pinned_instant(tx_instant)
    plan = planner.finalize(
        PlanningRequest(
            actor_identity=_PLANNING_ACTOR,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=compose_writes(model, buffered_writes),
            counts_unchanged_rows=dialect.counts_unchanged_rows,
        )
    ).plan
    executed = ExecutedPlan(plan)
    statements: list[LoweredStatement] = []
    units = iter(plan.units)
    unit = next(units, None)
    position = 0

    def bind_deferred() -> None:
        nonlocal unit
        while unit is not None and unit.end == position:
            deferred = unit.deferred
            if deferred is not None:
                if coverage is None:
                    raise EngineError(
                        "a range write reached coverage no observation of its unit holds, and "
                        "this lane tracks no case state to bind it to"
                    )
                bound = planner.bind_deferred(
                    deferred,
                    coverage.coverage(model, deferred.acquisition),
                    ownership=NO_OWNERSHIP,
                    actor_identity=_PLANNING_ACTOR,
                    transaction_instant=instant,
                )
                executed.steps.extend(bound.steps)
                executed.changed.extend(bound.changed)
                statements.extend(compile_write_step(step, model, dialect) for step in bound.steps)
            unit = next(units, None)

    for step, statement in stream_lowered(plan, model, dialect):
        bind_deferred()
        executed.steps.append(step)
        statements.append(statement)
        position += 1
    bind_deferred()
    return executed, tuple(statements)


@dataclass(slots=True)
class ExecutedPlan:
    """One write buffer's plan beside every step its execution runs, deferred
    ranges bound, and the observed states those bound ranges changed."""

    plan: WritePlan
    steps: list[PlannedWrite] = field(default_factory=list[PlannedWrite])
    changed: list[ObservedStateKey] = field(default_factory=list[ObservedStateKey])


def lower_writes(
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    shadow: TemporalShadow,
    tx_instant: str,
    group_observations: GroupObservations,
) -> tuple[LoweredStatement, ...]:
    """Resolve and PURE-lower one write buffer — the COMPILE lane's own
    lowering, and the RUN lane's emissions/round-trips oracle (`_execute_write_unit`
    resolves its own entries via :func:`_resolve_entries` and reuses
    :func:`_lower_resolved` directly, rather than calling this a second time, so
    each consumed observation is retired once and the buffer's one plan is
    tracked once)."""
    resolved = _resolve_entries(entries, model, shadow, group_observations)
    return _lower_resolved(resolved, entries, model, dialect, concurrency, tx_instant, shadow)


def _prepared_case_predicate_write(
    raw_write: Mapping[str, object], model: AcceptedMetamodel
) -> PreparedPredicateWrite:
    instruction = instructions.deserialize(case_document.canonical_predicate_doc(raw_write))
    assert isinstance(instruction, PredicateWrite)
    prepared = _case_ingress.prepare_case_write(instruction, model)
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


def _lower_predicate_write_step(
    prepared: PreparedPredicateWrite,
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
) -> LoweredStatement:
    """Lower a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) to its ONE statement — PURE, no database. Deserializes +
    validates the canonical instruction, then reuses the SAME
    ``build_write_planner`` -> ``stream_lowered`` seam every other write path
    does (batching is a structural no-op for a lone predicate write).

    The case-format preparation seam normalizes only carrier differences before
    strict Wire preparation. The prepared product retains managed values, and
    its compiler metadata projects them back to canonical Wire for the emission
    the case grades.

    A MATERIALIZING predicate write never reaches here: its case carries
    ``compileEligibility: run-only``, which short-circuits at
    :func:`~parallax.conformance._mechanism.case_document.eligibility` before
    the compile lane ever calls this — reaching this seam with one is therefore
    always a caller wiring defect, surfaced as planning's own defensive
    :class:`~parallax.core.write_plan.WritePlanningError`.
    """
    # A readless predicate write declares no Transaction-Time boundary, so the
    # inert instant it carries is never captured (ADR 0010).
    _plan, statements = _plan_and_lower(
        model, dialect, concurrency, INERT_CLOCK_INSTANT, [prepared]
    )
    assert len(statements) == 1  # a readless predicate write is always exactly one statement
    return statements[0]


def _buffer_wire_predicate_write(
    tx: handle.Transaction,
    model: AcceptedMetamodel,
    raw_write: Mapping[str, object],
    prepared: PreparedPredicateWrite,
) -> None:
    """Buffer one scenario predicate write through its public Wire verb.

    The case's target remains the independently authored corpus input. Managed
    assignment values come from the prepared product the pure lowering oracle
    uses, then cross back through the canonical Wire projection before the public
    verb prepares them again. Dict insertion order preserves the authored
    assignment order; the Entity Layout still decides emitted SET order.
    """
    authored = case_document.canonical_predicate_doc(raw_write)
    target = cast("Mapping[str, object]", authored["target"])
    managed_changes = {
        assignment.attr.rpartition(".")[2]: assignment.value
        for assignment in prepared.managed_assignments
    }
    changes = ActualWireProjection(model).entity_values(prepared.selection.target, managed_changes)
    valid_from, until = _authored_bounds(prepared.valid_time_window)
    match prepared.mutation:
        case "update":
            tx.wire.update_where(target, changes, valid_from=valid_from)
        case "delete":
            tx.wire.delete_where(target)
        case "terminate":
            tx.wire.terminate_where(target, valid_from=valid_from)
        case "updateUntil":
            tx.wire.update_where(
                target,
                changes,
                valid_from=_required(valid_from),
                until=_required(until),
            )
        case "terminateUntil":
            tx.wire.terminate_where(
                target, valid_from=_required(valid_from), until=_required(until)
            )


def _compile_find(
    step: Mapping[str, object], context: CaseContext, dialect: Dialect
) -> tuple[LoweredStatement, ...]:
    """The statements a scenario ``find`` step's read issues over a database
    holding no rows — the COMPILE lane's own oracle.

    The read runs as the RUN lanes run it (:func:`run_standalone_find`,
    :func:`_run_uow_group`): a Wire read inside ``db.transact`` with the
    scenario's authored keywords over a root connected with its configured
    options, so the shared-row-lock suffix is the one production resolves for
    the step's own target Entity. A materializing predicate write's own resolving
    read never reaches here: its case is `compileEligibility: run-only`.
    """
    return planned_read(
        context.serving,
        context.options,
        dialect,
        step_query(step, context.model),
        transaction=context.requests,
    )


def step_query(step: Mapping[str, object], model: AcceptedMetamodel) -> ObjectQueryNode:
    """A scenario or coherence read step's own canonical Object Query.

    The query travels as authored. Root as-of injection and per-hop navigation
    canonicalization are `deep_fetch.plan`'s own first step on every production
    read path, the compile lane's :func:`_compile_find` included, so applying
    them here would apply them twice.
    """
    query_doc = step.get("objectQuery")
    if query_doc is None:
        raise EngineError("a scenario read step needs `objectQuery`")
    return _case_ingress.normalize_case_query(deserialize_query(query_doc), model)


def run_standalone_find(
    port: CaseDatabase,
    context: CaseContext,
    step: Mapping[str, object],
    lifecycle: LifecycleRun,
) -> tuple[handle.Snapshot[handle.WireEntity], LifecycleObservation]:
    """Run one UNGROUPED scenario find step through the production Wire read.

    A step runs inside a real ``db.transact`` under exactly the options its
    scenario authored, so the read participates exactly as
    :func:`~parallax.conformance._lanes.reads.run_read_case` does and exactly
    as a developer's ``tx.find`` would: whether it takes the shared row lock is
    then the target Entity's own Effective Concurrency Strategy under the
    preference production resolves, never a property of the planning value
    alone or of what the scenario goes on to write.
    """
    query = step_query(step, context.model)
    observed = lifecycle.observation()
    with handle.Database.connect(
        port, context.serving, options=context.options, lifecycle_provider=observed.provider
    ) as _root_db:
        db = _root_db.using_database_login()
        return (
            transact(db, lambda tx: tx.wire.find(query), **context.requests),
            observed,
        )


def _names_one_entity(model: AcceptedMetamodel, left: str, right: str) -> bool:
    """Whether two authored Entity spellings denote ONE Entity the model declares.

    A case spells an Entity as the bare local name or as the canonical
    ``<namespace>.<Entity>``, and both resolve by model identity (`m-case-format`
    *How a case spells an Entity*), so the two legal spellings of one target must
    pair. Total: an unresolvable spelling denotes no Entity and pairs with nothing,
    leaving the refusal to the caller that owns the diagnostic.
    """
    resolved, other = entity_by_name(model, left), entity_by_name(model, right)
    return resolved is not None and other is not None and resolved.identity == other.identity


def graph_rows(
    model: AcceptedMetamodel, query: ObjectQueryNode, roots: Sequence[object]
) -> list[Mapping[str, object]]:
    """Published result positions as physically-keyed rows — what a read step's
    ``expectRows`` grades.

    The corpus states a find step's expectation in the projection's own physical
    spelling while a Wire root is keyed by declared member name, so each member's
    value is re-keyed by the slot it occupies. It is a rendering of what
    production published, never a second traversal, and it reads nothing about how
    the roots arrived: an eager result and a delivery's concatenated pages render
    identically.

    An ABSTRACT position publishes one CONCRETE node per row, so the read's own
    projection is the position's fixed superset rather than the addressed
    position's applicable members: each row carries every column the superset
    places, ``null`` where the row's own branch contributes none, plus the
    ``familyVariant`` the node itself publishes (`m-case-format` *Read
    targeting*). Rendering the branch's members alone would DROP what the read
    published; rendering the raw tag column would report a storage value no node
    carries, which is exactly why the format names the variant instead.
    """
    columns, family = _read_projection(model, query)
    superset = (
        dict.fromkeys(column for options in columns.values() for column, _member in options)
        if family
        else None
    )
    projection = ActualWireProjection(model)
    return [
        _projected_row(model, projection, columns, superset, envelope.graph_root(root) or {})
        for root in roots
    ]


def _projected_row(
    model: AcceptedMetamodel,
    projection: ActualWireProjection,
    columns: Mapping[str, tuple[tuple[str, AttributeMetadata | ValueObjectMetadata], ...]],
    superset: Mapping[str, None] | None,
    node: Mapping[str, object],
) -> Mapping[str, object]:
    """One published node as its projection's row.

    ``superset`` holds an abstract position's superset columns, each ``null``
    until the node fills it, and is ``None`` for a concrete read.
    """
    variant = node.get("familyVariant")
    selected = _variant_members(model, node) if superset is not None and node else None
    published: dict[str, object] = {}
    for name, value in node.items():
        options = columns.get(name, ())
        if not options:
            continue
        if len(options) == 1:
            column, member = options[0]
        else:
            matches = tuple(
                option
                for option in options
                if selected is not None and option[1].identity in selected
            )
            if len(matches) != 1:
                raise EngineError(
                    f"{variant!r} does not select one declaration for published member {name!r}"
                )
            column, member = matches[0]
        if value is None:
            published[column] = None
        elif isinstance(member, AttributeMetadata):
            published[column] = projection.published_scalar(member, value)
        else:
            published[column] = projection.published_value_object(member, value)
    if superset is None or not node:
        return published
    return {**superset, **published, "familyVariant": variant}


def _variant_members(
    model: AcceptedMetamodel, node: Mapping[str, object]
) -> frozenset[MemberIdentity]:
    variant = node.get("familyVariant")
    if not isinstance(variant, str):
        raise EngineError(
            "an abstract-position read publishes a concrete node carrying "
            f"`familyVariant`; this one published {sorted(node)}"
        )
    entity = case_entity(model, variant)
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - every accepted Entity has a view
        raise EngineError(f"{entity.identity.canonical}: no inheritance position")
    return frozenset(
        member.identity for member in (*view.applicable_attributes, *view.applicable_value_objects)
    )


def _read_projection(
    model: AcceptedMetamodel, query: ObjectQueryNode
) -> tuple[
    Mapping[str, tuple[tuple[str, AttributeMetadata | ValueObjectMetadata], ...]],
    bool,
]:
    """The columns ``query`` projects, and whether it reads an abstract position.

    Abstractness is the ADDRESSED position's own role, exactly as it is where
    production decides to project the discriminator, while the column set follows
    the query's resolved narrowing: narrowing an abstract read shrinks its
    superset without making the read concrete.
    """
    facet = inheritance.view(model)
    entity = case_entity(model, query.target.canonical)
    view = facet.entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return {}, False
    if not isinstance(entity.inheritance, (AbstractRoot, AbstractSubtype)):
        return _member_columns(view.applicable_attributes, view.applicable_value_objects), False
    position: inheritance.InheritancePositionView = view
    if query.narrow_to:
        narrowed = facet.position(
            [case_entity(model, spelling).identity for spelling in query.narrow_to]
        )
        if narrowed is None:  # pragma: no cover - a read whose roots exist resolved it
            raise EngineError(
                f"narrowing {query.target.canonical!r} to {list(query.narrow_to)} resolves "
                "no position of one inheritance family"
            )
        position = narrowed
    return _member_columns(position.superset_attributes, position.superset_value_objects), True


def step_rows(
    model: AcceptedMetamodel, index: int, query: ObjectQueryNode, roots: Sequence[object]
) -> dict[str, object]:
    """One read step's `stepRows` observation (`m-conformance-adapter`): the
    values that step published, at the step's own pointer, in wire space.

    A step's rows are what it HANDED OVER rather than what its statements
    returned — the distinction the observable exists to draw, and the reason this
    takes published roots rather than a result set.
    """
    return {
        "at": f"/scenario/{index}",
        "rows": [dict(row) for row in graph_rows(model, query, roots)],
    }


def _member_columns(
    attributes: Sequence[AttributeMetadata], value_objects: Sequence[ValueObjectMetadata]
) -> Mapping[str, tuple[tuple[str, AttributeMetadata | ValueObjectMetadata], ...]]:
    """Each member name paired with its own column, in projection order."""
    columns: dict[
        str, dict[MemberIdentity, tuple[str, AttributeMetadata | ValueObjectMetadata]]
    ] = {}
    for member in (*attributes, *value_objects):
        name = (
            member.identity.name
            if isinstance(member, AttributeMetadata)
            else member.identity.path[-1]
        )
        columns.setdefault(name, {})[member.identity] = (member.storage.name, member)
    return {name: tuple(options.values()) for name, options in columns.items()}


def _lower_scenario_step(
    context: CaseContext,
    dialect: Dialect,
    step: Mapping[str, object],
    index: int,
    group_observations: GroupObservations,
) -> LoweredStep:
    """One scenario step's pointer + DML, PURE — the compile lane's own per-step
    interpreter, the peer of the run lane's :func:`run_group_step`.

    Which boundary the step belongs to is deliberately NOT decided here: a
    doomed unit's case-state advances are staged by the caller
    (:func:`_scenario_lowered`), the one place a step's own transaction is
    known.
    """
    if "write" not in step:
        statements = _compile_find(step, context, dialect)
        return LoweredStep(f"/scenario/{index}/objectQuery", statements, False, False)
    raw_write = step["write"]
    rollback = step.get("rollback") is True
    if is_predicate_write_step(raw_write):
        # Readless only (`m-batch-write-005`/`-006`) — a materializing predicate
        # write never reaches the compile lane at all (its case's
        # `compileEligibility: run-only` short-circuits before
        # `_scenario_lowered` ever runs).
        statement = _lower_predicate_write_step(
            _prepared_case_predicate_write(cast("Mapping[str, object]", raw_write), context.model),
            context.model,
            dialect,
            context.concurrency,
        )
        return LoweredStep(f"/scenario/{index}/write", (statement,), True, rollback)
    entries = write_entries(raw_write)
    statements = lower_writes(
        entries,
        context.model,
        dialect,
        context.concurrency,
        context.case_state(),
        entry_instant(entries[0]),
        group_observations,
    )
    return LoweredStep(f"/scenario/{index}/write", statements, True, rollback)


def _doomed_group_spans(
    case: case_format.Case, steps: Sequence[Mapping[str, object]]
) -> dict[int, int]:
    """Each DOOMED `uow` group's own step span, keyed ``start -> end`` inclusive.

    Only the doomed ones: a committing group's steps need no staging, so leaving
    them out lets the caller drive them as ordinary steps. The two spans this
    lane cannot represent answer emptily — an interleaved two-group race
    (:func:`_scenario_uow_spans` returns ``None``) needs two concurrent units a
    pure lowering has no way to model, and every case carrying that shape is
    `compileEligibility: run-only` for the same reason.
    """
    spans = _scenario_uow_spans(case.path.name, steps)
    if spans is None:
        return {}
    return {start: end for label, (start, end) in spans.items() if _group_is_doomed(case, label)}


def _scenario_lowered(case: case_format.Case, dialect_name: str) -> list[LoweredStep]:
    """Lower every scenario step to its pointer + DML — pure (no database).

    One :class:`TemporalShadow` spans the whole scenario, seeded from the case's
    own fixture documents
    (:func:`~parallax.conformance._mechanism.given_state.seed_shadow_from_fixtures`)
    and then advanced by each step's plan: a write step's temporal close/chain
    observes the
    milestone persisted history declares or one an earlier step opened, and no
    query answers either — the seed reads the fixtures the run lane's database is
    provisioned FROM, which is what makes the two lanes the same computation
    while this one stays pure.

    The compile lane consults NO find-derived observation:
    a keyed write whose version bind is the framework-owned
    advance of a version this SAME scenario's own observing find returned is
    query-result-dependent (`m-conformance-adapter` "Compile eligibility") and
    is therefore declared `compileEligibility: run-only` in the corpus, so it
    short-circuits at :func:`~parallax.conformance._mechanism.case_document.eligibility`
    before this function ever runs (`adapter.compile_case`). The group
    observation store therefore stays permanently empty here: a keyed write's
    Version Observation comes from its OWN row's reserved ``observedVersion``
    control key alone
    (:func:`_durable_row`), exactly as a writeSequence entry's does, and a
    temporal write's whole-milestone observation from the tracker above.

    A DOOMED unit's advances are staged on that unit's own outcome, exactly as
    the run lane stages them
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.staged`): a
    doomed group's own later steps observe them and the group's last step
    restores them, and an ungrouped `rollback: true` write step restores them
    after itself. Both lanes must reach the same DML for the same case, and a
    step after an abort takes its milestone from the write the database kept.
    """
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    concurrency = case_document.concurrency(case)
    dialect = dialect_for(dialect_name)
    shadow = TemporalShadow()
    context = CaseContext(
        serving,
        model,
        concurrency,
        shadow,
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    seed_shadow_from_fixtures(case, model, shadow)
    group_observations: GroupObservations = []
    lowered: list[LoweredStep] = []
    try:
        steps = case_document.scenario_steps(case)
        doomed_spans = _doomed_group_spans(case, steps)
        index = 0
        while index < len(steps):
            end = doomed_spans.get(index)
            if end is not None:
                with shadow.staged(doomed=True):
                    for grouped in range(index, end + 1):
                        lowered.append(
                            _lower_scenario_step(
                                context, dialect, steps[grouped], grouped, group_observations
                            )
                        )
                index = end + 1
                continue
            step = steps[index]
            with shadow.staged(doomed=step.get("rollback") is True):
                lowered.append(
                    _lower_scenario_step(context, dialect, step, index, group_observations)
                )
            index += 1
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return lowered


def _write_sequence_lowered(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, tuple[LoweredStatement, ...]]]:
    """Lower each writeSequence entry independently to ``(pointer, statements)`` —
    pure. One :class:`TemporalShadow` spans the whole sequence, seeded from the
    case's own fixture documents where it opted in
    (:func:`~parallax.conformance._mechanism.given_state.seed_shadow_from_fixtures`):
    an entry's temporal close/chain observes the milestone that opt-in declares
    or one an earlier entry opened,
    and no query answers either. A writeSequence carries no find steps at all
    (`m-case-format`), so its own group observation store stays permanently
    empty — a keyed write's Version Observation still comes from its row's own
    ``observedVersion`` control key."""
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = case_document.concurrency(case)
    shadow = TemporalShadow()
    # The same seeding the RUN lane applies: a case opting into `given.fixtures`
    # starts from persisted history, and its first temporal close observes a
    # fixture milestone rather than one an earlier entry opened. Both lanes must
    # start from the same tracked state or they are not the same computation.
    seed_shadow_from_fixtures(case, model, shadow)
    group_observations: GroupObservations = []
    try:
        return [
            (
                f"/writeSequence/{index}",
                lower_writes(
                    [entry],
                    model,
                    dialect,
                    concurrency,
                    shadow,
                    entry_instant(entry),
                    group_observations,
                ),
            )
            for index, entry in enumerate(case_document.write_sequence_entries(case))
        ]
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def read_step_graph(
    case: case_format.Case,
    model: AcceptedMetamodel,
    index: int,
    step: Mapping[str, object],
    query: ObjectQueryNode,
    snapshot: handle.Snapshot[handle.WireEntity],
) -> dict[str, object] | None:
    """One find step's own graph observation, or ``None`` when it asserts none.

    The observable's other placement (`m-case-format` *Relationship contents at a
    step*), and the opposite claim to an `access` step's: what THIS read
    materialized — its roots and the relationships its own Include Paths
    populated — rather than what a view materialized earlier still holds. It is
    the whole-read `then.graph` value, reported per step because a scenario has
    many reads.

    Inside a `uow` group the read runs on the group's own transaction, so the
    contents are what that connection observes mid-flight: read-your-own-writes
    stated over a relationship. Ungrouped they are the committed database. Either
    way they come from the read's own published result, so nothing here can
    answer from a retained view — the confusion the access placement forbids from
    the other side.
    """
    if "expectGraph" not in step:
        return None
    if not query.includes:
        raise EngineError(
            f"{case.path.name}: a find step states relationship contents but declares no "
            "`includes` — the contents a read states are the relationships its own Include "
            "Paths materialized"
        )
    roots = snapshot.checked().results()
    graph: dict[str, object] = {
        envelope.graph_root_key(query.target.canonical, model): [
            envelope.graph_root(root) for root in roots
        ]
    }
    return {"at": f"/scenario/{index}", "graph": graph}


def compile_scenario_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a keyed unit-of-work scenario case to its ordered per-step
    emissions and round-trip count; a scenario carrying an action step is the
    snapshot lane's (:func:`~parallax.conformance._lanes.snapshot.compile_scenario`),
    which the façade dispatches to."""
    emissions = envelope.emissions(
        [(step.pointer, step.statements) for step in _scenario_lowered(case, dialect_name)]
    )
    return emissions, len(emissions)


def compile_write_sequence_case(
    case: case_format.Case, dialect_name: str
) -> tuple[list[Emission], int]:
    """Compile a writeSequence case to its ordered per-entry emissions and round trips."""
    emissions = envelope.emissions(_write_sequence_lowered(case, dialect_name))
    return emissions, len(emissions)


def _is_framework_write(
    instruction: WriteInstruction | PreparedWrite | PreparedTargetWrite, model: AcceptedMetamodel
) -> bool:
    """Whether ``instruction`` states the FRAMEWORK's own bookkeeping rather than
    a write a developer authors.

    The signal is a DB-computed write marker AT A SCALAR ATTRIBUTE — the
    ``{"increment": n}`` a `m-pk-gen` sequence-registry block reservation
    carries, and the ``{"computed": …}`` a `max` allocation carries beside it
    (`m-value-object` "Writing"). Such a value is the framework's to produce, so
    no public verb accepts it: the instruction-level validator exempts it at a
    scalar leaf, while the assignment judgement every verb reaches does not, and
    those two rules disagreeing is exactly what says the value is not developer
    input.

    The attribute's DECLARED ROLE is what decides, never the value's shape: a
    Value Object member binds its whole literal document even when that document
    is shaped like a marker, and only a scalar Attribute can carry the marker
    form at all (`m-case-format` "Write-sequence cases").
    """
    if not isinstance(instruction, (KeyedWrite, PreparedKeyedWrite)):
        return False
    entity = (
        instruction.target.identity.canonical
        if isinstance(instruction, PreparedKeyedWrite)
        else instruction.entity
    )
    scalars = _scalar_attribute_names(model, entity)
    return any(
        name in scalars
        and isinstance(value, Mapping)
        and frozenset(cast("Mapping[str, object]", value)) in _MARKER_KEYS
        for row in instruction.rows
        for name, value in row.items()
    )


def _scalar_attribute_names(model: AcceptedMetamodel, entity_name: str) -> frozenset[str]:
    """Every Attribute name applicable to ``entity_name``, its inherited ones
    included — the positions a DB-computed write marker may occupy, and the
    complement of the Value Object slots that never may."""
    view = inheritance.view(model).entity(case_entity(model, entity_name).identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return frozenset()
    return frozenset(attribute.identity.name for attribute in view.applicable_attributes)


_MARKER_KEYS: Final[frozenset[frozenset[str]]] = frozenset(
    {frozenset({"computed"}), frozenset({"increment"})}
)


def _framework_writes(
    resolved: Sequence[_ResolvedWrite], model: AcceptedMetamodel
) -> list[_ResolvedWrite]:
    """The entries of one buffer stating the FRAMEWORK's own bookkeeping.

    Every write lane asks this, because each one has to decide the same thing:
    such an entry has no public verb to be stated through, so it is a
    choreography unit of its own and every other composition of it is a form no
    case may author (`m-case-format` "Buffered keyed write instructions").
    """
    return [write for write in resolved if _is_framework_write(write.instruction, model)]


def _execute_framework_write_unit(
    port: DatabaseConnection,
    statements: Sequence[LoweredStatement],
    *,
    rollback: bool,
) -> int:
    """Execute the choreography unit ONE framework-marker entry is, and report the
    calls it cost.

    The caller's own plan, executed on the port's own transaction, rather than
    driven through a write verb, because there is no verb to drive: a
    ``{"increment": n}`` registry advance is the PK allocator's own statement,
    and admitting it at a public ingress would make a DB-computed write marker
    developer surface over the framework's bookkeeping.

    Executing the statements the caller reports is what keeps the two the same:
    this unit opens no Handle, so no lifecycle observes it, and a plan of its own
    would be a second derivation nothing could reconcile against the first. It is
    the one write lane whose round trips are STATED — it reaches its last
    statement only by having issued every one before it, the same reasoning
    `run_error_case` carries for authored trigger DML.

    A marker entry is a choreography unit of its own and the buffer's only entry
    (`m-case-format` "Buffered keyed write instructions"), which is why this
    takes one plan rather than a buffer: the unit is the entry. It honours the
    step's own abort contract like every other write path: a ``rollback: true``
    step runs on the aborting port, its statements reach the wire and count their
    round trips, and the provider then rolls them back.
    """

    def run(conn: DatabaseConnection) -> None:
        for statement in statements:
            conn.execute_write(
                conn.dialect.to_driver_sql(statement.sql), envelope.driver_binds(statement.binds)
            )

    with absorbing_rollback():
        committed(write_connection(port, rollback=rollback).transaction(run))
    return len(statements)


_LATEST_SELECTION: Final[Mapping[TemporalDimension, str]] = {
    TemporalDimension.VALID_TIME: "valid-time",
    TemporalDimension.TRANSACTION_TIME: "transaction-time",
}


def _unit_source_query(
    model: AcceptedMetamodel,
    entity_name: str,
    keys: Sequence[ObjectKey],
    valid_at: dt.datetime | None = None,
) -> dict[str, object]:
    """The canonical Object Query resolving every row of ``entity_name`` — a
    CANONICAL Entity spelling — one choreography unit writes against existing
    state, at the Valid-Time instant ``valid_at`` its Bitemporal writes start
    from.

    Membership over the family-declared primary key, one read per target Entity
    however many rows the unit addresses, which is what a caller holding several
    writes of one Entity does: it reads them together and writes what the read
    returned. Reading per row instead would cost the corpus a round trip per row
    for no semantic gain, and reading between two writes would force-flush the
    first — destroying the very batch collapse the goldens pin.

    A temporal target selects ``latest`` on Transaction Time, the only milestone
    a keyed write may address: the Transaction-Time past is read-only. A
    Bitemporal target is read at the instant its writes start from, because an
    observed write starts at its source's own Valid-Time pin; one read per
    distinct start, so writes starting apart read apart.
    """
    declaring = family_declarer(model, case_entity(model, entity_name))
    pk = [
        attr for attr in declaring.declared_attributes if isinstance(attr.primary_key, PrimaryKey)
    ]
    if len(pk) != 1:  # pragma: no cover - no witnessed write target is composite-keyed
        raise EngineError(
            f"{entity_name!r}: a unit's source read selects by a single-attribute primary key, "
            f"and this Entity declares {len(pk)}"
        )
    name = pk[0].identity.name
    query: dict[str, object] = {
        "target": entity_name,
        "predicate": {
            "in": {
                "attr": f"{declaring.identity.canonical}.{name}",
                "values": [dict(key.primary_key)[name] for key in keys],
            }
        },
    }
    temporal: dict[str, object] = {
        _LATEST_SELECTION[axis.dimension]: {"asOf": "latest"}
        for axis in declaring.declared_as_of_axes
    }
    if valid_at is not None:
        temporal[_LATEST_SELECTION[TemporalDimension.VALID_TIME]] = {
            "asOf": f"{valid_at:%Y-%m-%dT%H:%M:%S.%fZ}"
        }
    if temporal:
        query["temporal"] = temporal
    return query


def _unit_source_reads(
    model: AcceptedMetamodel, resolved: Sequence[_ResolvedWrite]
) -> list[dict[str, object]]:
    """Every resolving read one choreography unit owes, in target order.

    A keyed verb is stated against a value the caller holds, so each Entity this
    unit writes against EXISTING state needs one read to hold it by — except for
    a row this same unit opened, which read-your-own-writes covers and which no
    read could return anyway, since the insert has not flushed. Insert rows are
    therefore gathered first and the reads derived from what is left.

    The membership is over OBJECTS rather than over authored rows: two entries
    writing one row — an update the delete after it supersedes — address one
    object and contribute one key. A row naming no whole object is gathered for
    no read at all, because the write it states is addressed by nothing and is
    refused where the diagnosis can name the key.

    Both the object identity and the TARGET are canonical, never the spelling the
    case authored: a bare local name and its canonical form name one Entity
    (`m-case-format`), so two entries spelling one target differently owe one
    read between them rather than one each.
    """
    opened: set[ObjectKey] = set()
    for write in resolved:
        instruction = write.instruction
        if not isinstance(instruction, PreparedKeyedWrite):
            continue
        if instruction.mutation in INSERT_MUTATIONS:
            key = object_key(instruction, model)
            if key is not None:
                opened.add(key)
    needed: dict[tuple[str, dt.datetime | None], dict[ObjectKey, None]] = {}
    for write in resolved:
        instruction = write.instruction
        if not isinstance(instruction, PreparedKeyedWrite):
            continue
        if instruction.mutation in INSERT_MUTATIONS:
            continue
        key = object_key(instruction, model)
        if key is None or key in opened:
            continue
        canonical = instruction.target.identity.canonical
        window = instruction.valid_time_window
        needed.setdefault((canonical, None if window is None else window.start), {})[key] = None
    return [
        _unit_source_query(model, entity, tuple(keys), valid_at)
        for (entity, valid_at), keys in needed.items()
    ]


def _execute_write_unit(
    port: CaseDatabase,
    serving: ServingModel,
    model: AcceptedMetamodel,
    options: DatabaseOptions,
    requests: case_format.TransactionKeywords,
    resolved: Sequence[_ResolvedWrite],
    statements: Sequence[LoweredStatement],
    tx_instant: str,
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """Execute one choreography unit's ALREADY-RESOLVED instructions through the
    production ``db.transact`` entry point — ONE transaction over a root
    connected with ``options``, requesting exactly ``requests``,
    ``clock=FixedClock(tx_instant)``
    (ADR 0010: instants come from the Clock Strategy, never a per-operation
    override), and report the DML it ran beside the calls it cost.

    ``statements`` is the caller's plan for the same ``resolved`` instructions,
    reported back once the delivered lifecycle has confirmed the unit ran exactly
    it (:func:`~parallax.conformance._mechanism.envelope.delivered`).

    Every write against existing state is stated through the PUBLIC ``tx.wire``
    verb its mutation names, against the value this unit's own resolving reads
    published (:func:`_unit_source_reads`). Those reads ALL run before any write
    is buffered, and that order is load-bearing rather than tidy: a participating
    read force-flushes, so a read interleaved between two writes would put the
    first on the wire alone and destroy the batch collapse the goldens pin. They
    are charged to the observation's resolving reads
    (:meth:`~parallax.conformance._lifecycle_observation.LifecycleObservation.resolving_reads`):
    a case counts them in `then.roundTrips` and authors no golden for them, so
    they name no statement index in the lifecycle observation.

    A unit whose writes are the framework's own bookkeeping takes
    :func:`_execute_framework_write_unit` instead, which opens no unit of work
    at all — those statements have no verb to be stated through. A marker entry
    is a choreography unit of its own and therefore the buffer's ONLY entry
    (`m-case-format` "Buffered keyed write instructions"), so anything beside it
    states a form no case may author and is refused here rather than silently
    executed as one unit: a caller-authored entry would put half the DML through
    a public verb and half around it, and a second marker would fold two of the
    framework's own units into one flush, hiding whichever boundary the corpus
    meant to grade.

    A ``rollback: true`` step runs on the aborting port (`m-unit-work` abort
    contract): the boundary's own pre-commit flush still puts the buffered DML
    on the wire — and counts its round trips — before the provider rolls the
    transaction back.
    """
    framework = _framework_writes(resolved, model)
    if framework:
        if len(framework) != len(resolved):
            raise EngineError(
                "a choreography unit states either the framework's own bookkeeping or the writes "
                f"a caller authors, never both: this one holds {len(framework)} entry(s) carrying "
                f"a DB-computed write marker beside {len(resolved) - len(framework)} that a "
                "public verb states"
            )
        if len(resolved) != 1:
            raise EngineError(
                "an entry carrying a DB-computed write marker states the framework's own "
                "bookkeeping and is a choreography unit of its own, so it is the buffer's only "
                f"entry: this one holds {len(resolved)}"
            )
        return tuple(statements), _execute_framework_write_unit(port, statements, rollback=rollback)
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    observed = lifecycle.observation()
    with handle.Database.connect(
        write_adapter(port, rollback=rollback),
        serving,
        options=options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()

        def body(tx: handle.Transaction) -> None:
            state = GroupState()
            with observed.resolving_reads():
                for query in _unit_source_reads(model, resolved):
                    state.published.extend(_published_nodes(tx.wire.find(query)))
            for write in resolved:
                _buffer_wire_write(tx, model, state, write, None)

        with absorbing_rollback():
            transact(database, body, **requests)
        return envelope.delivered(
            statements, observed.writes, "a keyed write unit"
        ), observed.round_trips


def execute_keyed_unit(
    port: CaseDatabase,
    context: CaseContext,
    entries: Sequence[Mapping[str, object]],
    group_observations: GroupObservations,
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """One buffered-keyed-write choreography unit, whole: resolve its entries
    once, re-lower that ONE resolution purely, and execute it as its own
    ``db.transact`` — reporting the DML the plan holds beside the round trips
    the execution cost.

    Every producer of an ungrouped keyed unit drives this — a scenario's
    ungrouped write step on either scenario lane, and a writeSequence entry — so
    the order the three operations happen in, and the boundary they are staged
    on, are stated once. The staging is the unit's own outcome
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.staged`): a
    doomed unit's tracked advances are discarded with the rows its abort erases.

    Resolution happens ONCE and both consumers read it, so a temporal write's
    observation is consumed (and its milestone retired) a single time; the
    emission is therefore the PURE re-lowering of the very instructions the
    execution buffered, with binds observed through the lowered statement's
    canonical Wire projection. That plan is reported only where the
    delivered lifecycle confirms the unit ran it
    (:func:`~parallax.conformance._mechanism.envelope.delivered`), so being
    the plan and being what the database saw are one claim rather than two.
    """
    tx_instant = entry_instant(entries[0])
    shadow = context.case_state()
    with shadow.staged(doomed=rollback):
        resolved = _resolve_entries(entries, context.model, shadow, group_observations)
        statements = _lower_resolved(
            resolved,
            entries,
            context.model,
            port.dialect,
            context.concurrency,
            tx_instant,
            shadow,
        )
        ran, unit_trips = _execute_write_unit(
            port,
            context.serving,
            context.model,
            context.options,
            context.requests,
            resolved,
            statements,
            tx_instant,
            lifecycle,
            rollback=rollback,
        )
    return ran, unit_trips


def _run_readless_predicate_write(
    port: CaseDatabase,
    context: CaseContext,
    raw_write: Mapping[str, object],
    instruction: PreparedPredicateWrite,
    statement: LoweredStatement,
    tx_instant: str,
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """Execute a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) through the SAME production ``db.transact`` entry point every
    other write path uses. The public Wire verb prepares the case's authored
    target and canonically projected changes, while the separate prepared
    product remains the independent lowering oracle.

    The reported emission is ``statement`` — lowered from that same prepared
    product — and its compiler metadata renders the canonical Wire binds used
    for grading and delivery reconciliation. It is reported only where the
    delivered lifecycle confirms this transaction ran it
    (:func:`~parallax.conformance._mechanism.envelope.delivered`).
    """
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    observed = lifecycle.observation()
    with handle.Database.connect(
        write_adapter(port, rollback=rollback),
        context.serving,
        options=context.options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()

        def body(tx: handle.Transaction) -> None:
            _buffer_wire_predicate_write(tx, context.model, raw_write, instruction)

        with absorbing_rollback():
            transact(database, body, **context.requests)
        return (
            envelope.delivered((statement,), observed.writes, "a readless predicate write"),
            observed.round_trips,
        )


def is_materializing_write_step(
    step: Mapping[str, object] | None, model: AcceptedMetamodel
) -> PreparedPredicateWrite | None:
    """If ``step`` is a write step whose ``write`` field is a structured
    predicate instruction targeting a VERSIONED or TEMPORAL entity
    (MATERIALIZES, `m-opt-lock` "Predicate-selected writes materialize when
    observations are needed", ADR 0014), its core-produced
    :class:`~parallax.core.unit_work.PreparedPredicateWrite` — ``None`` for a keyed
    write step, a READLESS predicate write, a find step, or ``None`` itself
    (no such step, e.g. the scenario's last step).

    The returned prepared product holds producer-decoded managed assignment
    values. A materializing write has no
    separate PURE re-lowering oracle (its own golden bind is graded against
    the ACTUAL executed SQL, `_run_materializing_pair`'s own port observation),
    so there is nothing for a decoded value to drift away from here.
    """
    if step is None or "write" not in step:
        return None
    raw_write = step["write"]
    if not isinstance(raw_write, Mapping):
        return None
    instruction = instructions.deserialize(
        case_document.canonical_predicate_doc(cast("Mapping[str, object]", raw_write))
    )
    if not isinstance(instruction, PredicateWrite):
        return None
    prepared = _case_ingress.prepare_case_write(instruction, model)
    assert isinstance(prepared, PreparedPredicateWrite)
    target_name = prepared.selection.target.identity.canonical
    if _is_temporal_entity(model, target_name) or _is_versioned_entity(model, target_name):
        return prepared
    return None


def _run_materializing_pair(
    port: CaseDatabase,
    context: CaseContext,
    steps: Sequence[Mapping[str, object]],
    index: int,
    lifecycle: LifecycleRun,
) -> tuple[list[LoweredStep], int]:
    """Execute a MATERIALIZING predicate-write step (``index + 1``) whose
    IMMEDIATELY PRECEDING step (``index``) is the resolving find that shares
    its target entity — ONE transaction, `m-case-format` "Materializing
    cases": "a preceding scenario read resolves the same target predicate ...
    It is a real resolving read, not a cache hit". Production materialization
    (``tx.wire.update_where`` and its family) performs its OWN internal
    resolve using the SAME predicate; with no concurrent writer between the
    two steps, that resolve observes the IDENTICAL rows the corpus's own
    preceding find step documents, so pairing them here reproduces the
    corpus's own ``1 resolve + N per-row writes`` round-trip accounting
    exactly — the resolve's round trip is charged to the FIND step's pointer
    (the corpus's own authoring convention), never double-counted against the
    write step.

    Reports the ACTUAL executed SQL, read off the delivered lifecycle, never a
    separate pure re-lowering: a materializing write's per-row binds are
    QUERY-RESULT-DEPENDENT, so there is no pure oracle to derive them from
    independently of a real run. The resolve is the transaction's read
    (materialization always resolves before it writes) and the ``N`` per-row
    keyed writes are its DML, in resolved-row order — each in the canonical
    Lowered Statement form the Database Call borrowed, so nothing stands between
    what ran and what is reported.

    What this transaction did to a TEMPORAL target's milestones is recorded on
    ``shadow`` rather than tracked into it: the rows it closed and opened were
    resolved and planned inside production, so no later step can settle against
    them from case state, and one that tries is refused
    (:func:`_refuse_materialized_case_state`). The record is staged on this
    transaction's own outcome, exactly as every other unit's advances are — an
    aborted pair moved nothing.
    """
    model = context.model
    shadow = context.case_state()
    find_step = steps[index]
    write_step = steps[index + 1]
    instruction = is_materializing_write_step(write_step, model)
    assert instruction is not None  # the caller already established this via the same check
    find = step_query(find_step, model)
    target = find.target.canonical
    write_target = instruction.selection.target.identity.canonical
    write_predicate = instruction.selection.predicate.authored
    if not _names_one_entity(model, target, write_target):
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} is not preceded by "
            f"a resolving find over the SAME target entity (find targets {target!r}, write "
            f"targets {write_target!r} — m-case-format 'Materializing cases' "
            "requires the prior find to share the write's own target)"
        )
    # `m-case-format` "Materializing cases": for every versioned or temporal
    # target, model-aware validation MUST require that prior find to use the same
    # concrete target AND canonical predicate — same entity alone is not enough
    # (a resolving find over a DIFFERENT predicate would silently observe the
    # wrong rows). The read's own Temporal Selection is a sibling clause and the
    # write target remains the bare predicate, so the two predicates compare
    # directly; planning the read would additionally inject interval
    # predicates and is therefore still not the apples-to-apples form.
    comparable_find = predicate.validate_predicate(
        instruction.selection.target, find.predicate, model
    ).authored
    if comparable_find != write_predicate:
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} is not preceded by "
            "a resolving find over the SAME canonical predicate as the write's own target "
            f"predicate (find {find.predicate!r}, write {write_predicate!r} "
            "— m-case-format 'Materializing cases' requires the prior find to use the same "
            "concrete target and canonical predicate)"
        )
    tx_instant = entry_instant(cast("Mapping[str, object]", write_step["write"]))
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    rollback = write_step.get("rollback") is True
    observed = lifecycle.observation()
    with handle.Database.connect(
        write_adapter(port, rollback=rollback),
        context.serving,
        options=context.options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()

        def body(tx: handle.Transaction) -> None:
            _buffer_wire_predicate_write(
                tx,
                model,
                cast("Mapping[str, object]", write_step["write"]),
                instruction,
            )

        with shadow.staged(doomed=rollback):
            with absorbing_rollback():
                transact(database, body, **context.requests)
            shadow.note_materialized_write(case_entity(model, write_target))
        # The split is the port method each statement ran through rather than a
        # position in one flat list, so a resolve that issued more than one call, or
        # a batch the planner split, still lands where the corpus authors it: the
        # internal resolve against the FIND step's pointer, every DML statement
        # against the write step's.
        resolve = observed.reads
        if not resolve:  # pragma: no cover - zero resolved rows still resolves (1 statement)
            raise EngineError(
                f"materializing predicate write at scenario step {index + 1} executed no "
                "statements at all — even a zero-row resolve issues its own SELECT"
            )
        return [
            LoweredStep(f"/scenario/{index}/objectQuery", resolve, False, False),
            LoweredStep(f"/scenario/{index + 1}/write", observed.writes, True, rollback),
        ], observed.round_trips


def scenario_group_step_indices(steps: Sequence[Mapping[str, object]]) -> dict[str, list[int]]:
    """Every declared `uow` group label's OWN step indices, in authored order
    (`m-case-format` scenario `uow` grouping) — not necessarily contiguous;
    the caller (:func:`_scenario_uow_spans` /
    :func:`~parallax.conformance._lanes.interleaved.run_interleaved_scenario_case`)
    decides how to execute them."""
    groups: dict[str, list[int]] = {}
    for index, step in enumerate(steps):
        label = step.get("uow")
        if isinstance(label, str):
            groups.setdefault(label, []).append(index)
    return groups


def _scenario_uow_spans(
    case_name: str, steps: Sequence[Mapping[str, object]]
) -> dict[str, tuple[int, int]] | None:
    """Every declared `uow` group label's step-index span ``(start, end)``
    (inclusive) in this scenario (`m-case-format` scenario `uow` grouping).

    Every group whose OWN steps are CONTIGUOUS gets its ordinary span, and
    :func:`_run_uow_group` runs each on the MAIN connection. Exactly TWO
    groups whose steps INTERLEAVE (`m-case-format`'s own "two groups MAY
    interleave" — the optimistic-lock race and the Isolation Level scenarios
    alike) is signaled by returning ``None``: :func:`run_scenario_case`
    cannot execute that shape itself (no engine function here constructs a
    connection of its own, and an interleaved choreography genuinely needs a
    SECOND, peer-backed session) —
    :func:`~parallax.conformance._lanes.interleaved.run_interleaved_scenario_case`
    is the entry point that can, on the cases its OWN guards admit. What this
    function reports is the SHAPE; it admits no case. Anything BEYOND a clean
    TWO-group interleave — three or more interleaved groups, or a
    non-contiguous group that is not part of one — raises loudly rather than
    silently mis-executing it (scope honestly: support the interleaving the
    corpus witnesses, refuse the rest)."""
    groups = scenario_group_step_indices(steps)
    spans = {label: (indices[0], indices[-1]) for label, indices in groups.items()}
    noncontiguous = {
        label
        for label, indices in groups.items()
        if indices != list(range(spans[label][0], spans[label][1] + 1))
    }
    if not noncontiguous:
        return spans
    if len(groups) == 2:
        (label_a, label_b) = groups
        span_a, span_b = spans[label_a], spans[label_b]
        interleaved = span_a[1] >= span_b[0] and span_b[1] >= span_a[0]
        if interleaved:
            return None
    raise EngineError(
        f"{case_name}: uow group(s) {sorted(noncontiguous)} interleave beyond the "
        "witnessed TWO-group shape (run_interleaved_scenario_case) — the engine's "
        "scenario run lane supports exactly that interleaving, not an arbitrary one"
    )


def group_tx_instant(steps: Sequence[Mapping[str, object]], indices: Iterable[int]) -> str:
    """The Clock instant a `uow` group's own choreography unit runs at — its
    first write entry's own instant (m-temporal-write `at`; ADR
    0010), or the inert default when the group carries no write (or every
    write entry names none, i.e. every group this round targets a
    non-temporal entity). ``indices`` are the group's own steps, in authored
    order, whether or not they are contiguous."""
    for i in indices:
        step = steps[i]
        if "write" in step:
            raw_write = step["write"]
            if is_predicate_write_step(raw_write):
                return entry_instant(cast("Mapping[str, object]", raw_write))
            entries = write_entries(raw_write)
            if entries:
                return entry_instant(entries[0])
    return INERT_CLOCK_INSTANT


def _group_is_doomed(case: case_format.Case, label: str) -> bool:
    """Whether a `uow` group ROLLS BACK after its last step: its fate in
    ``then.units`` is `rolledBack` (`m-case-format` *Unit fates*)."""
    return case_document.unit_fate(case, label).get("outcome") == "rolledBack"


@dataclass(frozen=True, slots=True)
class CaseContext:
    """What ONE case's write translation is fixed by, for every step or entry of
    it — the run lane's `uow` groups (:func:`run_group_step`), an ungrouped
    write step on either scenario lane (:func:`execute_keyed_unit`), and the
    compile lane's pure lowering (:func:`_lower_scenario_step`) alike.

    The model is the case's own, in both forms one formation answers: the
    Serving Model a Snapshot connection adopts from — the case's Domain Model
    prepared once under the case's edition — and the accepted Metamodel every
    neutral lowering surface is stated over. The tracker is the ONE case-spanning
    :class:`TemporalShadow` every unit shares rather than a per-unit copy — a
    later unit's temporal close observes the milestone an earlier one's write
    opened. It is ``None`` on a lane that models no case state, and that alone
    selects how a grouped temporal write settles: against the tracker
    (:class:`CaseStateEvidence`) or against its own group's reads
    (:class:`GroupEvidence`). The record is frozen because none of the four is
    ever REBOUND inside a case; the tracker's own contents advance, which is
    exactly the state a shared tracker exists to carry.

    The dialect is deliberately NOT one of them. It is fixed by the connection a
    unit executes through rather than by the case, and one case's steps do not
    all run through one connection — each interleaved group runs on a dedicated
    session of its own. Each lowering therefore reads it off the port about to execute the
    statement (:class:`GroupSession` for a group, the unit's own port
    otherwise), so this record can travel beside any of them.

    The concurrency is the preference the case's writes are PLANNED under —
    the one its outer invocation resolves to, from the explicit request over
    the configured root — and is what every lowering here reads. The options
    are the root record the case CONFIGURES
    (:func:`~parallax.conformance.case_format.database_options`), handed to
    every ``connect`` a lane composes for the case's own units of work; the
    requests are the ``db.transact`` keywords the case AUTHORED
    (:func:`~parallax.conformance.case_format.transaction_keywords`), handed to
    every ``transact``. The two are carried separately from the planning value
    and from each other because an omitted field must reach production omitted
    rather than as the planning value restated: a held group, an ungrouped
    unit, and a standalone find all connect with exactly the record and forward
    exactly these keywords. Every construction states all three, so a field the
    case declared and no lane propagated cannot go invisible.
    """

    serving: ServingModel
    model: AcceptedMetamodel
    concurrency: Concurrency
    shadow: TemporalShadow | None
    requests: case_format.TransactionKeywords
    options: DatabaseOptions

    def case_state(self) -> TemporalShadow:
        """The tracker of a lane that models case state."""
        if self.shadow is None:
            raise EngineError(
                "this choreography unit settles against tracked case state, which a lane "
                "modeling none cannot supply"
            )
        return self.shadow


def _empty_published() -> list[handle.WireEntity]:
    return []


def _empty_group_finds() -> dict[int, tuple[handle.WireEntity, ...]]:
    return {}


def _empty_opened() -> dict[ObjectKey, handle.WireEntity]:
    return {}


def _empty_settled() -> set[ObjectKey]:
    return set()


@dataclass(frozen=True, slots=True)
class GroupState:
    """What ONE `uow` group accumulates as its own steps run, and nothing wider.

    Every field holds published VALUES rather than derived evidence, because a
    value is what a keyed Wire verb is addressed and licensed by, and its claim
    is one accessor away (:func:`_published_claims`). ``published`` is the flat
    run a write with no reference resolves against, ``finds`` keys the same nodes
    by the step that published them — what a write step naming a find with ``on``
    addresses (`m-case-format` *Settling against a grouped find*) — and
    ``opened`` holds what this group's own inserts answered, which is how
    read-your-own-writes reaches a row no find could have returned. ``settled``
    holds the keys whose temporal write already settled against this group's
    reads (:class:`GroupEvidence`). All four are built fresh per group, never a
    scenario-wide store, so no value crosses a transaction boundary.
    """

    published: list[handle.WireEntity] = field(default_factory=_empty_published)
    finds: dict[int, tuple[handle.WireEntity, ...]] = field(default_factory=_empty_group_finds)
    opened: dict[ObjectKey, handle.WireEntity] = field(default_factory=_empty_opened)
    settled: set[ObjectKey] = field(default_factory=_empty_settled)


def _published_nodes(snapshot: handle.Snapshot[handle.WireEntity]) -> tuple[handle.WireEntity, ...]:
    """Every Entity node ``snapshot`` published, each once, in walk order.

    The roots come from the CHECKED view, because invalid stored data is a fact
    about a root rather than a refusal of the read.
    """
    return _published_from(snapshot.checked().results())


def _published_from(roots: Iterable[object]) -> tuple[handle.WireEntity, ...]:
    """Every Entity node ``roots`` carry, each once, in walk order.

    Publication is what settles ownership: a value a caller was handed is the one
    a later keyed write may be addressed by, so the walk starts at the published
    roots and descends the values they carry rather than reading the read's own
    retained sources. A frozen Wire node is a ``dict`` and therefore unhashable,
    which is why the visited set is identity-keyed over objects the caller holds
    for the walk's whole duration.

    How the roots ARRIVED is not among the things this reads: a Snapshot's whole
    result and a Snapshot Stream's delivered roots walk identically, which is the
    claim `m-unit-work-030` states in the corpus — evidence belongs to the value
    rather than to the delivery that carried it. A HYDRATABLE record's collapse
    produced legal member values, so the node in its ``data`` is an ordinary
    observed source and enters the walk unwrapped, while a NON-HYDRATING record
    carries no value to publish and contributes none — which is what leaves the
    wrapper itself unwritable.
    """
    nodes: list[handle.WireEntity] = []
    visited: set[int] = set()
    frontier: list[object] = [
        cast("handle.InvalidData[object]", root).data
        if isinstance(root, handle.InvalidData)
        else root
        for root in roots
    ]
    cursor = 0
    while cursor < len(frontier):
        value = frontier[cursor]
        cursor += 1
        if isinstance(value, list):
            frontier.extend(cast("list[object]", value))
            continue
        if not isinstance(value, handle.WireEntity) or id(value) in visited:
            continue
        visited.add(id(value))
        nodes.append(value)
        frontier.extend(cast("Mapping[str, object]", value).values())
    return tuple(nodes)


def _published_claims(nodes: Sequence[handle.WireEntity]) -> GroupObservations:
    """The retained claims ``nodes`` carry, in order — what the PURE re-lowering
    oracle plans with, derived from the same values the real write settles
    against so the two can never name different states."""
    claims: list[RetainedObservation] = []
    for node in nodes:
        hint = read_origin_of(node)
        if hint is not None and hint.observation is not None:
            claims.append(hint.observation)
    return claims


def _node_object_key(node: handle.WireEntity) -> ObjectKey:
    """The object ``node`` names: the one its read observed, or the one the
    insert that answered it opened."""
    hint = read_origin_of(node)
    if hint is not None:
        return hint.object_key
    authority = authoring_of(node)
    assert authority is not None  # every node this lane holds a read or an insert published
    return authority.object_key


def _writable_source(node: handle.WireEntity) -> bool:
    """Whether a keyed write may be addressed by ``node`` at all.

    A group may publish SEVERAL milestones of one key — an audit read of the
    Transaction-Time past beside a read of the current row — and only the
    current one is writable, because the Transaction-Time past records what the
    system knew and is never rewritten. A caller holding both hands the verb the
    writable one, so an unreferenced scan skips what the verb would refuse
    rather than reaching for the refusal.
    """
    hint = read_origin_of(node)
    assert hint is not None
    try:
        validate_source_pin(hint.entity, hint.pin)
    except TransactionTimePinReadOnlyError:
        return False
    return True


def _group_source_node(
    entity_name: str,
    key: ObjectKey | None,
    state: GroupState,
    named: Sequence[handle.WireEntity] | None,
    valid_from: dt.datetime | None = None,
) -> handle.WireEntity:
    """The published value one keyed write is addressed by, from what its own
    choreography unit produced.

    Shared by both lanes that state keyed writes: a `uow` group's steps, where
    the values come from the group's own find steps, and an ungrouped unit,
    where they come from the resolving reads that unit issued for itself
    (:func:`_unit_source_reads`).

    ``named`` is what a grouped step's own ``on`` reference resolved to, and is
    the whole answer where it is present: a versioned target holds one row per
    key but a unit of work may observe several GENERATIONS of it, and the
    reference is how a case says which. With no reference, a row this unit's own
    insert opened wins over any find — that is read-your-own-writes, and no read
    could have returned it — and otherwise the published run is scanned from the
    END, so a write settles against the latest reading rather than a stale one.

    ``valid_from`` is a Bitemporal write's start, which an observed write takes
    from the Valid-Time pin of the value it is handed rather than as an argument
    of its own: a published value read anywhere else states a different write,
    so it is never the source, and a named one is refused.
    """
    if named is not None:
        matched = [node for node in named if _node_object_key(node) == key]
        if len(matched) != 1:
            raise EngineError(
                f"{entity_name!r}: the find step this write settles against published "
                f"{len(matched)} rows of {key!r} — a keyed write settles against the ONE "
                "observed state the value it was handed came from (m-case-format 'Settling "
                "against a grouped find')"
            )
        (node,) = matched
        if not _pinned_at(node, valid_from):
            raise EngineError(
                f"{entity_name!r}: the write starts at {valid_from!r}, but the find it settles "
                "against was read at another Valid-Time instant — an observed write starts at "
                "its source's own pin and states no start of its own (m-case-format 'Settling "
                "against a grouped find')"
            )
        return node
    opened = None if key is None else state.opened.get(key)
    if opened is not None:
        return opened
    for node in reversed(state.published):
        if (
            _node_object_key(node) == key
            and _writable_source(node)
            and _pinned_at(node, valid_from)
        ):
            return node
    raise EngineError(
        f"{entity_name!r}: a keyed write addresses {key!r}, which no read of its own "
        "choreography unit published and no write of it opened — every keyed write here is "
        "stated through the public verb its mutation names, against a value the caller holds, "
        "and a choreography unit comes to hold one only by reading the row or by opening it "
        "with its own insert (m-case-format 'Resolving reads a write owes')"
    )


def _pinned_at(node: handle.WireEntity, valid_from: dt.datetime | None) -> bool:
    """Whether ``node`` was read at the Valid-Time instant a write starting at
    ``valid_from`` takes from its source; a write with no Valid-Time start
    takes none."""
    if valid_from is None:
        return True
    hint = read_origin_of(node)
    assert hint is not None
    pin = hint.pin
    return pin is not None and pin.valid_time == valid_from


def _source_find_nodes(
    entry: Mapping[str, object],
    index: int,
    group_finds: Mapping[int, tuple[handle.WireEntity, ...]],
) -> tuple[handle.WireEntity, ...] | None:
    """What the find step a submission of the WRITE step at ``index`` names with
    ``on`` published (`m-case-format` *Settling against a grouped find*) —
    ``None`` when it names no find, which is every submission but one settling
    against its group's own read.

    ``group_finds`` holds one entry per find step of THIS group that has already
    run, so a reference it cannot satisfy names a step outside the group, a step
    that is not a find, or one that has not run yet. All three are the same
    authoring defect and all three are refused here, rather than resolved to an
    empty tuple that would read as "the find published nothing".
    """
    source = entry.get("on")
    if source is None or isinstance(source, str):
        return None
    if not isinstance(source, int) or isinstance(source, bool):
        raise EngineError(
            f"scenario[{index}]: a write settles against ONE find step, named by its "
            f"index — {source!r} is not one (m-case-format 'Settling against a grouped find')"
        )
    published = group_finds.get(source)
    if published is None:
        raise EngineError(
            f"scenario[{index}]: settles against step {source}, which is not an EARLIER find "
            "step of its own `uow` group — the evidence a write consumes is transaction-scoped "
            "(m-case-format 'Settling against a grouped find')"
        )
    return published


def _buffer_wire_write(
    tx: handle.Transaction,
    model: AcceptedMetamodel,
    state: GroupState,
    write: _ResolvedWrite,
    named: Sequence[handle.WireEntity] | None,
    source: handle.WireEntity | None = None,
) -> handle.WireEntity | None:
    """Buffer ONE resolved keyed write through the public ``tx.wire`` verb its
    mutation names.

    Driven off the SAME :class:`_ResolvedWrite` the pure oracle plans, so the
    real write and the reported emission read one resolution: the durable row,
    its Valid-Time bounds, and its mutation all come from the instruction, and
    what this adds is only which verb states them and which published value the
    write is addressed by.

    An insert opens a row no find can have returned, so the node the verb answers
    is recorded for the rest of the group — the read-your-own-writes source a
    later entry of the same unit resolves against — and returned. Every other
    mutation takes its source from ``source`` where the submission named the
    insert whose answered value it writes through, else from the node its
    evidence already resolved (``write.source_node``), else from what this group
    published, and its change set is the durable row less the identity that
    source already carries: a PK-only row therefore states the empty change set,
    which is the ordinary no-op.
    """
    instruction = write.instruction
    if isinstance(instruction, PreparedTargetWrite):
        _buffer_wire_target(tx, model, instruction)
        return None
    assert isinstance(
        instruction, PreparedKeyedWrite
    )  # every other resolved entry this lane buffers is keyed
    entity_name = instruction.target.identity.canonical
    entity_metadata = instruction.target
    row = dict(instruction.rows[0])
    valid_from, until = _authored_bounds(instruction.valid_time_window)
    if instruction.mutation in INSERT_MUTATIONS:
        payload = _wire_insert_payload(model, entity_metadata, row)
        opened = (
            tx.wire.insert(
                entity_name, payload, valid_from=_required(valid_from), until=_required(until)
            )
            if instruction.mutation == "insertUntil"
            else tx.wire.insert(entity_name, payload, valid_from=valid_from)
        )
        state.opened[_node_object_key(opened)] = opened
        return opened
    key = object_key(instruction, model)
    node = (
        source
        if source is not None
        else write.source_node
        if write.source_node is not None
        else _group_source_node(entity_name, key, state, named, valid_from)
    )
    identity = dict(key.primary_key) if key is not None else {}
    changes = ActualWireProjection(model).entity_values(
        entity_metadata,
        {name: value for name, value in row.items() if name not in identity},
    )
    match instruction.mutation:
        case "update":
            tx.wire.update(node, changes)
        case "updateUntil":
            tx.wire.update(node, changes, until=_required(until))
        case "delete":
            tx.wire.delete(node)
        case "terminate":
            tx.wire.terminate(node)
        case _:
            tx.wire.terminate(node, until=_required(until))
    return None


def _buffer_wire_target(
    tx: handle.Transaction, model: AcceptedMetamodel, instruction: PreparedTargetWrite
) -> None:
    """Buffer ONE caller-addressed write through the public ``tx.wire`` verb
    its mutation names, with the caller's own revision beside its document."""
    entity_name = instruction.target.identity.canonical
    document = ActualWireProjection(model).entity_values(instruction.target, dict(instruction.row))
    expectation = instruction.expectation
    valid_from, until = _authored_bounds(instruction.valid_time_window)
    version = expectation.version if isinstance(expectation, ExpectedVersion) else None
    tx_start = expectation.instant if isinstance(expectation, ExpectedTxStart) else None
    verb = tx.wire.replace if instruction.replaces else tx.wire.update
    if until is None:
        verb(
            entity_name,
            document,
            valid_from=valid_from,
            if_version=version,
            if_tx_start=tx_start,
        )
    else:
        verb(
            entity_name,
            document,
            valid_from=valid_from,
            until=until,
            if_tx_start=tx_start,
        )


def _wire_insert_payload(
    model: AcceptedMetamodel, entity: EntityMetadata, row: Mapping[str, object]
) -> dict[str, object]:
    """One insert entry's row as the Create Payload a public verb accepts.

    A case authors the framework-owned optimistic-lock version on an insert to
    satisfy the instruction lane's own required-attribute check
    (:func:`_seed_insert_version`), and the framework derives it at lowering
    whatever the row carries. A public verb refuses it outright — the Typed
    Entity constructor and the Wire insert alike — so the value the case states
    is dropped here rather than smuggled through a door built to close it.
    """
    return ActualWireProjection(model).entity_values(entity, row, omit_framework=True)


def _authored_bounds(
    window: TimeInterval | None,
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """The scalar bounds a public write verb authors a prepared ``window`` with:
    no ``valid_from`` without Valid Time, and no ``until`` for a window running
    to the open bound, which public authoring states by omission."""
    if window is None:
        return None, None
    end = window.end
    return window.start, None if end is INFINITY else end


def _required(instant: dt.datetime | None) -> dt.datetime:
    """A bound a bounded mutation always carries, narrowed for the verb that
    requires it — the instruction build already refused one that states none."""
    assert instant is not None
    return instant


@dataclass(frozen=True, slots=True)
class _StepRead:
    """What one scenario read step handed over.

    ``roots`` is the step's own result positions in the order it published them —
    a delivery's pages concatenated where the step streamed — which is what its
    `expectRows` states. ``graph`` is the eager Snapshot the step materialized,
    which only an `expectGraph` reads and which a streamed step has none of: a
    delivery assembles no whole result, and the format admits that oracle on no
    streamed step.
    """

    roots: tuple[object, ...]
    graph: handle.Snapshot[handle.WireEntity] | None


@dataclass(frozen=True, slots=True)
class _GroupRun:
    """One `uow` group's own report: its steps' lowered emissions in step order,
    the round trips its single transaction made, and the per-step observations its
    read steps filled, each in step order."""

    lowered: list[LoweredStep]
    round_trips: int
    step_rows: list[dict[str, object]]
    step_graphs: list[dict[str, object]]


@dataclass(frozen=True, slots=True, init=False)
class GroupSession:
    """The connection ONE `uow` group runs on: the port it executes through, and
    the Handle opened over that port.

    One value rather than two arguments because a group's SQL is spelled by the
    port that executes it (`m-dialect`), and one case's groups do not all run on
    one connection — each interleaved group runs on a dedicated session of its
    own. Handing
    a runner a Handle and a dialect apart admits a group lowering in one
    connection's spelling while executing in another's, so this takes the port
    alone and OPENS the Handle over it: no caller can hand it a Handle connected
    to some other port, and the pair it holds names one connection. The Handle
    is connected with the case's own root record, so the group's transaction
    resolves whatever it does not request against the root the case configured.
    """

    adapter: DatabaseAdapter
    root: handle.Database[object]
    database: handle.ScopedDatabase

    def __init__(
        self,
        adapter: DatabaseAdapter,
        context: CaseContext,
        instant: dt.datetime,
        observation: LifecycleObservation,
    ) -> None:
        object.__setattr__(self, "adapter", adapter)
        root = handle.Database.connect(
            adapter,
            context.serving,
            options=context.options,
            clock=FixedClock(instant),
            lifecycle_provider=observation.provider,
        )
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "database", root.using_database_login())

    @property
    def dialect(self) -> Dialect:
        return self.adapter.dialect

    def close(self) -> None:
        """Close the Handle this session opened, and the runtime under it."""
        self.root.close()


def run_group_step(
    tx: handle.Transaction,
    session: ModeledExecution,
    context: CaseContext,
    state: GroupState,
    step: Mapping[str, object],
    index: int,
    tx_instant: str,
    observation: LifecycleObservation,
) -> tuple[LoweredStep, _StepRead | None]:
    """One `uow` group step, inside the group's own open transaction — the ONE
    interpreter both group runners share, contiguous span and interleaved index
    list alike.

    A WRITE step resolves its entries against this group's own published values
    (never a scenario-wide store) — a temporal entry's predecessor through the
    evidence ``context`` selects (:class:`CaseStateEvidence` where the lane models
    case state, :class:`GroupEvidence` where it models none) — records the pure
    re-lowering every
    other write path uses (:func:`_lower_resolved`) BEFORE the group's flush
    executes anything — the runner reconciles the group's whole plan against what
    that flush delivered — and then buffers each resolved write through the PUBLIC
    ``tx.wire`` verb its mutation names, against the value this group published
    for its key. Every entry a group holds is therefore caller-authored: a
    DB-computed write marker is a choreography unit of its own and no group step
    may carry one (`m-case-format` "Buffered keyed write instructions"), which
    this refuses by name rather than leaving to the verb that would reject the
    value. A READLESS predicate-write step lowers and buffers exactly as an
    ungrouped one does (:func:`_run_readless_predicate_write`), but into the
    group's held transaction, so the flush that delivers it also orders the
    keyed writes buffered on either side of it. A FIND step runs through
    ``tx.wire.find`` — the participating
    Wire read, which force-flushes any pending buffered write, takes the read
    lock its target Entity's own Effective Concurrency Strategy calls for, and
    retains onto each published node what a later write settles against — and
    records the nodes it published into ``state``, which this function extends
    in place. A find step carrying `stream` (`m-case-format` *Streamed read
    steps*) runs through ``tx.wire.stream`` at its declared page size instead,
    and what it records is the same thing: the roots the DELIVERY published,
    walked identically, because a value's evidence is a property of the value
    rather than of how it arrived. ``observation`` is the group's own port
    observation, read across either call to recover the statements the step
    emits — for a delivery, every page's.

    ``session`` is the connection ``tx`` was opened over, and the spelling of
    every statement this step lowers is read off its port. A group runs on its
    own connection — an interleaved group's on the dedicated session opened for
    it — so the lowering
    a step reports is spelled by whatever is about to execute it rather than by
    the caller's own port.

    Returns the step's lowered emission pointer, and — for a read step — what it
    published beside it (:class:`_StepRead`), which is the step's own
    `expectRows` observable on either lane. A write step publishes nothing and
    answers ``None``.
    """
    model = context.model
    if "write" in step and is_predicate_write_step(step["write"]):
        raw_write = cast("Mapping[str, object]", step["write"])
        prepared = _prepared_case_predicate_write(raw_write, model)
        statement = _lower_predicate_write_step(
            prepared, model, session.dialect, context.concurrency
        )
        _buffer_wire_predicate_write(tx, model, raw_write, prepared)
        return (
            LoweredStep(
                f"/scenario/{index}/write", (statement,), True, step.get("rollback") is True
            ),
            None,
        )
    if "write" in step:
        entries = write_entries(step["write"])
        published = _published_claims(state.published)
        resolved: list[_ResolvedWrite] = []
        sources: list[Sequence[handle.WireEntity] | None] = []
        unit_inserted: set[ObjectKey] = set()
        for entry in entries:
            named = _source_find_nodes(entry, index, state.finds)
            source = None if named is None else tuple(_published_claims(named))
            evidence: TemporalEvidence = (
                GroupEvidence(state, named)
                if context.shadow is None
                else CaseStateEvidence(model, context.shadow, source)
            )
            written = _build_instructions(entry, model, evidence, unit_inserted, published, source)
            resolved.extend(written)
            sources.extend(named for _ in written)
        framework = _framework_writes(resolved, model)
        if framework:
            raise EngineError(
                f"/scenario/{index}/write: {len(framework)} entry(s) carry a DB-computed write "
                "marker, which states the framework's own bookkeeping and is a choreography unit "
                "of its own — a `uow` group's held transaction has no verb to buffer one through"
            )
        statements = _lower_resolved(
            resolved,
            entries,
            model,
            session.dialect,
            context.concurrency,
            tx_instant,
            context.shadow,
        )
        for write, named in zip(resolved, sources, strict=True):
            _buffer_wire_write(tx, model, state, write, named)
        return LoweredStep(f"/scenario/{index}/write", statements, True, False), None
    return _group_read(tx, context, state, step, index, observation)


def _group_read(
    tx: handle.Transaction,
    context: CaseContext,
    state: GroupState,
    step: Mapping[str, object],
    index: int,
    observation: LifecycleObservation,
) -> tuple[LoweredStep, _StepRead]:
    """One `uow` group's find step, through ``tx.wire.find`` or, for a step
    carrying `stream`, ``tx.wire.stream`` at its page size — recording into
    ``state`` the nodes it published, which a later write of the group is
    addressed by."""
    model = context.model
    mark = observation.round_trips
    batch_size = case_document.batch_size_of(step, f"/scenario/{index}/stream")
    if batch_size is None:
        snapshot = tx.wire.find(step_query(step, model))
        read = _StepRead(tuple(snapshot.checked().results()), snapshot)
    else:
        with tx.wire.stream(step_query(step, model), batch_size=batch_size) as delivery:
            read = _StepRead(tuple(delivery.checked()), None)
    nodes = _published_from(read.roots)
    state.finds[index] = nodes
    state.published.extend(nodes)
    return LoweredStep(
        f"/scenario/{index}/objectQuery", observation.since(mark, "read"), False, False
    ), read


def _run_uow_group(
    case: case_format.Case,
    port: CaseDatabase,
    context: CaseContext,
    steps: Sequence[Mapping[str, object]],
    start: int,
    end: int,
    lifecycle: LifecycleRun,
) -> _GroupRun:
    """Execute one CONTIGUOUS `uow` group's steps (index *start*..*end*
    inclusive) inside ONE ``db.transact``, in step order, each through the shared
    :func:`run_group_step` interpreter.

    What this runner owns beyond that interpreter is the group's own BOUNDARY:
    the single Transaction Instant every step in the span runs at
    (:func:`group_tx_instant`), and the doom decision — `rollback: true` on any
    of the group's own write steps dooms the WHOLE group, which then runs on the
    aborting port, so the boundary's pre-commit flush still puts the buffered
    DML on the wire before the provider rolls it back (the `m-unit-work` abort
    contract applied to the group rather than to one step). The group's case-state
    advances are staged on that same outcome
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.staged`): visible
    to the group's own later steps, discarded with the rows when it aborts.

    What each read step published is reported twice over, from the one value the
    step handed back: as its `stepRows` observation (:func:`step_rows`), and — for
    a step declaring `expectGraph` — as its graph observation
    (:func:`read_step_graph`). Both are what that read observed THROUGH this
    transaction, which is where read-your-own-writes becomes visible at all.
    """
    tx_instant = group_tx_instant(steps, range(start, end + 1))
    doomed = _group_is_doomed(case, cast("str", steps[start]["uow"]))
    state = GroupState()
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    observation = lifecycle.observation()
    session = GroupSession(write_adapter(port, rollback=doomed), context, instant, observation)
    try:
        lowered: list[LoweredStep] = []
        rows_observed: list[dict[str, object]] = []
        step_graphs: list[dict[str, object]] = []

        def body(tx: handle.Transaction) -> None:
            for index in range(start, end + 1):
                step, read = run_group_step(
                    tx, session, context, state, steps[index], index, tx_instant, observation
                )
                lowered.append(step)
                if read is None:
                    continue
                query = step_query(steps[index], context.model)
                rows_observed.append(step_rows(context.model, index, query, read.roots))
                if read.graph is None:
                    continue
                observed = read_step_graph(
                    case, context.model, index, steps[index], query, read.graph
                )
                if observed is not None:
                    step_graphs.append(observed)

        with context.case_state().staged(doomed=doomed), absorbing_rollback():
            transact(session.database, body, **context.requests)
        # The group's writes reach the wire in ONE flush at its boundary, so a step's
        # own plan is reconciled against the group's whole delivery rather than
        # against a flush of its own: what the transaction wrote is every write
        # step's DML, in the order those steps buffered it.
        envelope.delivered(
            [statement for step in lowered if step.is_write for statement in step.statements],
            observation.writes,
            "a held `uow` group",
        )
        # Every statement this ONE transaction put on the wire, which is where the
        # group's round trips come from rather than from a second count this lane
        # keeps.
        return _GroupRun(lowered, observation.round_trips, rows_observed, step_graphs)
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# State-graded groups: public verbs only, graded on what they leave.           #
# --------------------------------------------------------------------------- #


def _empty_answered() -> dict[str, handle.WireEntity]:
    return {}


def _empty_refusals() -> list[dict[str, object]]:
    return []


@dataclass(frozen=True, slots=True)
class _Submitted:
    """What a state-graded group's submissions left for the rest of the run:
    the value each accepted insert answered, by its pointer, and the refusal
    each refused submission raised."""

    opened: dict[str, handle.WireEntity] = field(default_factory=_empty_answered)
    refusals: list[dict[str, object]] = field(default_factory=_empty_refusals)


def _submission_writes(
    entry: Mapping[str, object], model: AcceptedMetamodel
) -> list[_ResolvedWrite]:
    """One keyed submission as the instructions its verb is handed, one per row.

    A state-graded group drives public verbs only, so nothing here resolves an
    observation: the value a verb is handed carries its own.
    """
    entity_name = cast("str", entry["entity"])
    mutation = cast("str", entry["mutation"])
    bounds = {name: entry[name] for name in ("validFrom", "until") if name in entry}
    writes: list[_ResolvedWrite] = []
    for raw_row in cast("Sequence[Mapping[str, object]]", entry["rows"]):
        row, _observation = _durable_row(model, entity_name, mutation, raw_row)
        row = _seed_insert_version(model, entity_name, mutation, row)
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity_name, "rows": [row], **bounds}
        )
        writes.append(_ResolvedWrite(_case_ingress.prepare_case_write(instruction, model), None))
    return writes


def _submit(
    tx: handle.Transaction,
    model: AcceptedMetamodel,
    state: GroupState,
    submitted: _Submitted,
    entry: Mapping[str, object],
    pointer: str,
    index: int,
) -> None:
    """Hand one submission to the public verb its form names, catching the one
    refusal it declares, as a caller that continues past it does."""
    refusal = entry.get("expectError")
    try:
        if "target" in entry:
            prepared = _prepared_case_predicate_write(entry, model)
            _buffer_wire_predicate_write(tx, model, entry, prepared)
        elif "row" in entry:
            target = _build_target_instruction(entry, model).instruction
            assert isinstance(target, PreparedTargetWrite)  # a `row` entry is caller-addressed
            _buffer_wire_target(tx, model, target)
        else:
            on = entry.get("on")
            source = submitted.opened.get(on) if isinstance(on, str) else None
            if isinstance(on, str) and source is None:
                raise EngineError(f"{pointer}: writes through {on!r}, which opened no value")
            named = _source_find_nodes(entry, index, state.finds)
            for write in _submission_writes(entry, model):
                opened = _buffer_wire_write(tx, model, state, write, named, source)
                if opened is not None:
                    submitted.opened[pointer] = opened
    except handle.WriteEvidenceError as exc:
        if exc.code != refusal:
            raise
        submitted.refusals.append({"at": pointer, "errorClass": exc.code})


_FLUSH_FAILURES = (
    MissingTargetError,
    StaleWriteError,
    OptimisticLockConflictError,
    WritePreconditionError,
)
_SHORTFALLS: Final[dict[type[WriteEffectError], str]] = {
    MissingTargetError: "missingTarget",
    StaleWriteError: "staleWrite",
    OptimisticLockConflictError: "optimisticConflict",
}


def flush_failure(
    model: AcceptedMetamodel,
    failure: WriteEffectError | WritePreconditionError,
    at: int | Literal["commit"],
) -> dict[str, object]:
    """The ``flushFailure`` a group reports: where its flush ran, and the object
    and Shortfall the failure names, in the case's own spelling."""
    if isinstance(failure, WritePreconditionError):
        entity, key, shortfall = failure.entity, dict(failure.key), "failedPrecondition"
    else:
        entity = failure.entity
        target = failure.target
        names = tuple(attribute.name for attribute in target.key_attributes)
        values = target.key_values[0] if isinstance(target, KeyTarget) else target.key_values
        key = dict(zip(names, values, strict=True))
        shortfall = _SHORTFALLS[type(failure)]
    metadata = case_entity(model, entity.canonical)
    return {
        "at": at,
        "entity": entity.canonical,
        "key": ActualWireProjection(model).entity_values(metadata, key),
        "shortfall": shortfall,
    }


@dataclass(frozen=True, slots=True)
class _StateGroupRun:
    """One state-graded group's report: its fate, the rows each of its finds
    published, the refusals its submissions raised, and its round trips."""

    fate: dict[str, object]
    step_rows: list[dict[str, object]]
    refusals: list[dict[str, object]]
    round_trips: int


def _run_state_graded_group(
    case: case_format.Case,
    port: CaseDatabase,
    context: CaseContext,
    steps: Sequence[Mapping[str, object]],
    start: int,
    end: int,
    lifecycle: LifecycleRun,
) -> _StateGroupRun:
    """Execute one state-graded `uow` group through public verbs alone.

    Each submission goes to the verb its form names; each find reads through the
    group's transaction. A group whose fate is a plain rollback abandons its unit
    of work once its last step ran; any other runs to commit, and a flush that
    fails ends it where it ran — at the find whose read flushed, or at commit —
    which is the fate it reports.
    """
    label = cast("str", steps[start]["uow"])
    fate = case_document.unit_fate(case, label)
    abandoned = fate.get("outcome") == "rolledBack" and "flushFailure" not in fate
    instant = normalize_instant(
        dt.datetime.fromisoformat(group_tx_instant(steps, range(start, end + 1)))
    )
    observation = lifecycle.observation()
    session = GroupSession(write_adapter(port, rollback=abandoned), context, instant, observation)
    state = GroupState()
    submitted = _Submitted()
    rows_observed: list[dict[str, object]] = []
    running: list[int] = []

    def body(tx: handle.Transaction) -> None:
        for index in range(start, end + 1):
            running.append(index)
            step = steps[index]
            if "write" in step:
                for position, entry in enumerate(write_entries(step["write"])):
                    pointer = f"/scenario/{index}/write/{position}"
                    _submit(tx, context.model, state, submitted, entry, pointer, index)
            else:
                _lowered, read = _group_read(tx, context, state, step, index, observation)
                query = step_query(step, context.model)
                rows_observed.append(step_rows(context.model, index, query, read.roots))
        running.clear()

    outcome: dict[str, object] = {"outcome": "rolledBack" if abandoned else "committed"}
    try:
        with absorbing_rollback():
            transact(session.database, body, **context.requests)
    except _FLUSH_FAILURES as failure:
        at: int | Literal["commit"] = running[-1] if running else "commit"
        reported = flush_failure(context.model, failure, at)
        outcome = {"outcome": "rolledBack", "flushFailure": reported}
    finally:
        session.close()
    return _StateGroupRun(outcome, rows_observed, submitted.refusals, observation.round_trips)


def _run_state_graded_case(
    case: case_format.Case, port: CaseDatabase, lifecycle: LifecycleRun
) -> ScenarioRun:
    """Run a state-graded scenario (`m-case-format` *State-graded scenarios*):
    every group through :func:`_run_state_graded_group`, every ungrouped find
    on committed state, then the tables read back. It reports no emissions:
    nothing here grades which statements a flush chose."""
    steps = case_document.scenario_steps(case)
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    spans = _scenario_uow_spans(case.path.name, steps)
    if spans is None:
        raise EngineError(f"{case.path.name}: a state-graded case runs its groups one at a time")
    starts = {start: (label, end) for label, (start, end) in spans.items()}
    context = CaseContext(
        serving,
        model,
        case_document.concurrency(case),
        TemporalShadow(),
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    units: dict[str, dict[str, object]] = {}
    refusals: list[dict[str, object]] = []
    rows_observed: list[dict[str, object]] = []
    round_trips = 0
    try:
        apply_given_apply(case, port, context.shadow)
        index = 0
        while index < len(steps):
            group = starts.get(index)
            if group is not None:
                label, end = group
                run = _run_state_graded_group(case, port, context, steps, index, end, lifecycle)
                units[label] = run.fate
                refusals.extend(run.refusals)
                rows_observed.extend(run.step_rows)
                round_trips += run.round_trips
                index = end + 1
                continue
            step = steps[index]
            if "write" in step:
                raise EngineError(
                    f"{case.path.name}: scenario[{index}] is an ungrouped write, which a "
                    "state-graded case states no fate for"
                )
            read, read_observed = run_standalone_find(port, context, step, lifecycle)
            round_trips += read_observed.round_trips
            query = step_query(step, model)
            rows_observed.append(step_rows(model, index, query, read.checked().results()))
            index += 1
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return ScenarioRun(
        [], round_trips, refusals, rows_observed, [], units, read_table_state(port, model)
    )


def run_scenario_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> ScenarioRun:
    """Run a scenario: an UNGROUPED write step commits (or aborts) as its OWN
    unit of work through ``db.transact``, and an ungrouped find reads
    committed state. A `uow`-GROUPED contiguous span of steps instead runs
    inside ONE ``db.transact`` (:func:`_run_uow_group`): the observing find
    and the versioned write it licenses execute in the SAME unit of work, so
    the write's version bind is a genuine transaction-scoped observation,
    never an oracle. A MATERIALIZING predicate-write step pairs with its
    IMMEDIATELY PRECEDING find step (:func:`_run_materializing_pair`) —
    detected by a one-step LOOK-AHEAD before that find is lowered as an
    ordinary standalone step, since `m-case-format`'s own "Materializing
    cases" convention makes the preceding find the resolve.

    Reports its observations as a :class:`ScenarioRun`. The `errors` channel is
    filled by the snapshot action-step lane alone, from its `expectError`
    grading (:func:`~parallax.conformance._lanes.snapshot.run_scenario`, which
    the façade dispatches a scenario carrying an action step to); a keyed
    unit-of-work scenario reports it empty. `stepGraphs` is filled on both
    lanes, from whichever placement of `expectGraph` the case authors: an
    `access` step's retained view there, and here a find step's own
    materialized graph (:func:`read_step_graph`) — grouped, the contents that
    read observed inside the group's transaction.
    `stepRows` is filled on both lanes too, by every read step this run drives —
    ungrouped, grouped, and streamed alike — and by every accepted `mutate`
    declaring `expectRows`. A MATERIALIZING pair's resolving find drives none:
    production performs that read internally while planning the write and hands
    its rows to no caller, so the step reports no entry (`m-conformance-adapter`
    *Per-step row observations*)."""
    lifecycle = lifecycle_run(lifecycle)
    if case.document.get("grading") == "state":
        return _run_state_graded_case(case, port, lifecycle)
    steps = case_document.scenario_steps(case)
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    dialect = port.dialect
    concurrency = case_document.concurrency(case)
    shadow = TemporalShadow()
    rows_observed: list[dict[str, object]] = []
    step_graphs: list[dict[str, object]] = []
    spans = _scenario_uow_spans(case.path.name, steps)
    if spans is None:
        raise EngineError(
            f"{case.path.name}: interleaved uow groups need a second, peer-backed "
            "connection this function does not construct — call "
            "run_interleaved_scenario_case instead"
        )
    span_start_labels = {start: label for label, (start, _end) in spans.items()}
    context = CaseContext(
        serving,
        model,
        concurrency,
        shadow,
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    lowered: list[LoweredStep] = []
    units: dict[str, dict[str, object]] = {}
    round_trips = 0
    try:
        seed_shadow_from_fixtures(case, model, shadow)
        # After the fixtures and before the first step, exactly where every other
        # lane applies it
        # (:func:`~parallax.conformance._mechanism.given_state.apply_given_apply`).
        # The tracker is deliberately
        # not re-seeded from it — it records which milestones the statements may
        # have overtaken instead. A predicate write resolves through a real read that
        # sees whatever they wrote; a keyed write's observation stays case state,
        # and where that state can no longer be the whole stored row the write is
        # refused rather than silently rebuilt
        # (:func:`_refuse_unaccounted_document_milestone`).
        apply_given_apply(case, port, shadow)
        index = 0
        while index < len(steps):
            label = span_start_labels.get(index)
            if label is not None:
                start, end = spans[label]
                group = _run_uow_group(case, port, context, steps, start, end, lifecycle)
                units[label] = {
                    "outcome": "rolledBack" if _group_is_doomed(case, label) else "committed"
                }
                lowered.extend(group.lowered)
                rows_observed.extend(group.step_rows)
                step_graphs.extend(group.step_graphs)
                round_trips += group.round_trips
                index = end + 1
                continue
            step = steps[index]
            if "write" not in step:
                next_step = steps[index + 1] if index + 1 < len(steps) else None
                pairing = is_materializing_write_step(next_step, model)
                if pairing is not None and _names_one_entity(
                    model,
                    step_query(step, model).target.canonical,
                    pairing.selection.target.identity.canonical,
                ):
                    pair_lowered, pair_trips = _run_materializing_pair(
                        port, context, steps, index, lifecycle
                    )
                    lowered.extend(pair_lowered)
                    round_trips += pair_trips
                    index += 2
                    continue
                read, read_observed = run_standalone_find(port, context, step, lifecycle)
                round_trips += read_observed.round_trips
                lowered.append(
                    LoweredStep(f"/scenario/{index}/objectQuery", read_observed.reads, False, False)
                )
                query = step_query(step, model)
                rows_observed.append(step_rows(model, index, query, read.checked().results()))
                observed = read_step_graph(case, model, index, step, query, read)
                if observed is not None:
                    step_graphs.append(observed)
                index += 1
                continue
            raw_write = step["write"]
            rollback = step.get("rollback") is True
            if is_predicate_write_step(raw_write):
                # A materializing write reaching HERE (rather than being
                # consumed by the look-ahead pairing above) was not preceded
                # by a matching find — a malformed corpus case per
                # `m-case-format`'s own validation requirement; finalization's
                # defensive refusal surfaces it loudly rather than silently
                # mishandling it. A READLESS write needs no pairing at all.
                raw_predicate_write = cast("Mapping[str, object]", raw_write)
                tx_instant = entry_instant(raw_predicate_write)
                instruction = _prepared_case_predicate_write(raw_predicate_write, model)
                statement = _lower_predicate_write_step(instruction, model, dialect, concurrency)
                ran, predicate_trips = _run_readless_predicate_write(
                    port,
                    context,
                    raw_predicate_write,
                    instruction,
                    statement,
                    tx_instant,
                    lifecycle,
                    rollback=rollback,
                )
                round_trips += predicate_trips
                lowered.append(LoweredStep(f"/scenario/{index}/write", ran, True, rollback))
            else:
                statements, unit_trips = execute_keyed_unit(
                    port, context, write_entries(raw_write), [], lifecycle, rollback=rollback
                )
                round_trips += unit_trips
                lowered.append(LoweredStep(f"/scenario/{index}/write", statements, True, rollback))
            index += 1
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = envelope.emissions([(step.pointer, step.statements) for step in lowered])
    then = case.document.get("then")
    table_state = (
        read_table_state(port, model)
        if isinstance(then, Mapping) and "tableState" in then
        else None
    )
    return ScenarioRun(emissions, round_trips, [], rows_observed, step_graphs, units, table_state)


def run_write_sequence_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], dict[str, list[MappingRow]], int]:
    """Run a writeSequence: each entry executes as its OWN unit of work through
    ``db.transact`` (one transaction per entry, never the whole sequence in
    one), then report the ordered per-entry
    emissions, the committed table state, and the total round trips.

    The table read-back is the `m-conformance-adapter` write-sequence observation
    ("write-sequence cases report ``tableState``"): the runner grades it against
    the case's ``then.tableState``. Observation reads are not case round trips.

    ``given.apply`` is applied after the case's own fixture provisioning and
    before the first entry (`m-case-format` admits it on a writeSequence): the
    state it stands for — a row a concurrent writer removed, a stored document
    key no authored member of this model can produce — is state the FIRST entry
    already writes against, so applying it later than that would grade the
    sequence against a table the case never described.
    """
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    lifecycle = lifecycle_run(lifecycle)
    shadow = TemporalShadow()
    context = CaseContext(
        serving,
        model,
        case_document.concurrency(case),
        shadow,
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    group_observations: GroupObservations = []
    lowered: list[tuple[str, tuple[LoweredStatement, ...]]] = []
    round_trips = 0
    try:
        seed_shadow_from_fixtures(case, model, shadow)
        apply_given_apply(case, port, shadow)
        for index, entry in enumerate(case_document.write_sequence_entries(case)):
            statements, unit_trips = execute_keyed_unit(
                port, context, [entry], group_observations, lifecycle, rollback=False
            )
            round_trips += unit_trips
            lowered.append((f"/writeSequence/{index}", statements))
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = envelope.emissions(lowered)
    table_state = read_table_state(port, model)
    return emissions, table_state, round_trips


def read_table_state(
    port: DatabaseConnection, model: AcceptedMetamodel
) -> dict[str, list[MappingRow]]:
    """The committed contents of every model table, in canonical wire form.

    Every compiled Table Layout is read back exactly once, projecting its
    complete slot sequence in canonical order, so the observation reports the
    whole physical row ``then.tableState`` asserts — including a slot that only
    a sibling table-per-hierarchy variant fills (e.g. `m-inheritance-007`'s
    inserted `CardPayment` row still reports the cash-only `tendered` column as
    `null`).
    """
    dialect = port.dialect
    state: dict[str, list[MappingRow]] = {}
    for layout in storage_layout.view(model).tables:
        columns = ", ".join(dialect.quote(slot.column.name) for slot in layout.columns)
        sql = f"select {columns} from {dialect.quote(layout.table.name)}"
        rows = port.execute(dialect.to_driver_sql(sql), [])
        projection = ActualWireProjection(model)
        keys = tuple(slot.column.name for slot in layout.columns)
        state[layout.table.name] = [
            projection.table_row(layout, dict(zip(keys, row, strict=True))) for row in rows
        ]
    return state


def _conflict_mutation(when: Mapping[str, object]) -> Literal["update", "delete"]:
    """A conflict case's written verb (`m-case-format` ``when.mutation``),
    defaulting to ``update``."""
    return "delete" if when.get("mutation") == "delete" else "update"


@dataclass(frozen=True, slots=True)
class _ConflictWrite:
    """One row of a NON-TEMPORAL conflict attempt's ``write``, resolved once for
    both the pure re-lowering and the real execution: the durable row, the
    single-row instruction a unit of work buffers for it, that instruction's
    coalescing identity, and the Version Observation the row's reserved
    ``observedVersion`` described.

    The observation is a DECLARED FACT the case states, never the evidence the
    write settles against: the real execution reads its own source and settles
    against what that read observed (:func:`_conflict_source_nodes`), and this
    value is what that observation is cross-checked against
    (:func:`_refuse_unobserved_conflict_version`). The pure oracle plans with it
    directly, having no read behind it.
    """

    row: dict[str, object]
    instruction: PreparedWrite
    key: ObjectKey | None
    observation: VersionObservation | None


def _resolve_conflict_writes(
    model: AcceptedMetamodel,
    target: str,
    mutation: Literal["update", "delete"],
    write_rows: Sequence[Mapping[str, object]],
) -> tuple[_ConflictWrite, ...]:
    """Resolve a NON-TEMPORAL conflict attempt's ``write`` rows: strip each row's
    reserved ``observedVersion`` into a Version Observation (`m-opt-lock`;
    ADR 0013) and validate the durable instruction it leaves. ``mutation`` is the
    case's own ``when.mutation`` verb — a keyed UPDATE or DELETE, the two
    non-temporal shapes whose gate the target Entity's Effective Concurrency
    Strategy decides uniformly.

    A conflict attempt authors its rows in the SAME ``writeRow`` vocabulary a
    writeSequence entry does, so they become durable rows through the SAME
    :func:`_durable_row` seam: an unversioned conflict target — a supported
    surface (``m-unit-work-013`` / ``-014``, ``m-batch-write-008``) — has no
    version to observe, and wrapping its rows anyway would exclude them from the
    collapse this lane exists to exercise.

    Every row becomes its OWN single-row instruction, exactly as a unit of work
    buffers it. Which of them end up sharing a statement is the planner's
    decision alone, so the MULTI-KEY ``write`` array reaches the collapse rule
    rather than a pre-merged instruction this function invented.
    """
    resolved: list[_ConflictWrite] = []
    for clean_row, observation in _durable_rows(model, target, mutation, write_rows):
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": target, "rows": [clean_row]}
        )
        assert isinstance(instruction, KeyedWrite)  # a `rows` document is a keyed write
        prepared = _case_ingress.prepare_case_write(instruction, model)
        resolved.append(
            _ConflictWrite(clean_row, prepared, object_key(prepared, model), observation)
        )
    return tuple(resolved)


def _landed_conflict_rows(resolved: Sequence[_ConflictWrite]) -> int:
    """The aggregate row count a conflict attempt affects when its write LANDS:
    one per DISTINCT addressed key, since same-key rows coalesce into a single
    addressed row before any target is built. A row whose identity does not
    resolve coalesces with nothing and stands for itself."""
    keyed = {write.key for write in resolved if write.key is not None}
    return len(keyed) + sum(1 for write in resolved if write.key is None)


def _lower_conflict_write(
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    resolved: Sequence[_ConflictWrite],
) -> tuple[LoweredStatement, ...]:
    """PURE-lower one NON-TEMPORAL conflict attempt's resolved ``write`` rows:
    plan the whole buffer through the SAME ``build_write_planner`` factory the
    composition layer uses (`parallax.snapshot.handle.ScopedDatabase.transact`) and
    lower every survivor, so a MULTI-KEY attempt reports the ONE set-based
    statement its real execution emits rather than the per-row statements an
    uncollapsed plan would have rendered.
    """
    _plan, statements = _plan_and_lower(
        model,
        dialect,
        concurrency,
        INERT_CLOCK_INSTANT,
        [_buffered(write.instruction, write.observation, model) for write in resolved],
    )
    return statements


def _implied_shortfall_error(
    observation_requiring: bool,
    concurrency: Concurrency,
    model: AcceptedMetamodel,
    target: str,
) -> type[WriteEffectError]:
    """The ONE shortfall class a conflict case's declared facts imply.

    Derived from the case, never from the plan the implementation settled, so a
    write whose policy was settled wrongly cannot also move the expectation it is
    graded against. An OBSERVATION-REQUIRING write — a versioned keyed UPDATE or
    DELETE — classifies by its gate, which the target's own
    Effective Concurrency Strategy decides: a GATED (Optimistic) shortfall is the
    retriable optimistic-lock conflict, an UNGATED (Locking) one the
    non-retriable stale write. Anything else is an observation-free keyed write,
    whose shortfall means the addressed rows are simply not there.
    """
    if not observation_requiring:
        return MissingTargetError
    strategy = opt_lock.effective_strategy(
        concurrency, opt_lock.view(model).key(case_entity(model, target).identity)
    )
    return OptimisticLockConflictError if strategy == "optimistic" else StaleWriteError


def _conflict_attempt_requests(case: case_format.Case) -> case_format.TransactionKeywords:
    """The options one authored conflict ATTEMPT's transaction requests: the
    case's `concurrency` and `isolation`, and neither retry field.

    A conflict case's `when.attempts` IS its retry loop, authored one attempt at
    a time and graded per attempt — `affectedRows: 0` on the stale attempt, the
    advance on the next — so each attempt runs as one transaction of its own.
    Forwarding an authored `retryOptimisticConflicts` would make production
    re-execute the stale attempt inside that transaction and report the
    advance where the case grades the shortfall; the opt-in that case authors
    describes the loop the attempts spell out, and the boundary lane is where
    production's own loop is driven from it. The root record a conflict case
    configures (`given.databaseOptions`) reaches the attempt's ``connect``
    unchanged, so a root preference or level governs the attempt exactly as an
    authored one does — and a root that opts into conflict retry under a
    positive bound is refused before any attempt runs
    (:func:`refuse_a_conflict_retry_opt_in`), because the lane carries no
    authored keyword that could stand over it.
    """
    authored = case_format.transaction_keywords(case)
    requests: case_format.TransactionKeywords = {}
    if "concurrency" in authored:
        requests["concurrency"] = authored["concurrency"]
    if "isolation" in authored:
        requests["isolation"] = authored["isolation"]
    return requests


def refuse_a_conflict_retry_opt_in(
    case: case_format.Case, resolved: DatabaseOptions, placement: str
) -> None:
    """Refuse a case whose transactions would resolve `retryOptimisticConflicts`
    to true under a positive `maxRetries` on a lane that authors each attempt
    itself.

    The conflict lane's `when.attempts` and the interleaved lane's two `uow`
    groups are the retry loop, spelled one attempt at a time and graded per
    attempt, so each attempt must be exactly one production attempt. An opt-in
    the transaction resolved — from ``resolved``, the record production would
    resolve to — would make production re-run a conflicting attempt inside the
    one transaction this lane opened for it: hidden SQL, a second observing
    read, and an advance reported where the case grades the shortfall. A
    retried loop is a `boundary` case's to prove; here it is refused by name
    rather than run as work the case never described. A bound of ``0`` disables
    re-execution (`m-auto-retry`), so an opt-in the bound makes inert is
    admitted: production classifies the conflict retriable and still surfaces
    it after the one attempt. ``placement`` names where the case spelled the
    opt-in.
    """
    if not (resolved.retry_optimistic_conflicts and resolved.max_retries > 0):
        return
    raise EngineError(
        f"{case.path.name}: {placement} opts into optimistic-conflict retry under a bound of "
        f"{resolved.max_retries}, so production could re-run a conflicting attempt inside the "
        "one transaction this lane opens for it; the attempts this shape authors are its retry "
        "loop, and a retried loop is a `boundary` case's to prove"
    )


def _conflict_attempt_affected(
    database: handle.ScopedDatabase,
    requests: case_format.TransactionKeywords,
    implied: type[WriteEffectError],
    body: Callable[[handle.Transaction], int],
) -> int:
    """One conflict attempt's affected-row observation: what ``body`` reports when
    the write lands, or the ``actual`` count carried by the ONE Write Effect Error
    the case's own declared facts admit.

    Every member of the family renders the same ``actual`` count, so a lane that
    caught the whole family would report an identical ``affectedRows`` observation
    whichever class the write raised, and the case would then assert nothing about
    the classification. Admitting only the implied class lets every other one
    propagate and fail the case instead.

    An EXCESS is invariant: whatever a shortfall would have classified as, more
    rows than the target addresses is always Cardinality Corruption, so the
    direction the raised error itself reports — not the declared mode — selects
    that arm.
    """
    try:
        return transact(database, body, **requests)
    except WriteEffectError as exc:
        admitted = CardinalityCorruptionError if exc.actual > exc.expected else implied
        if type(exc) is not admitted:
            raise
        return exc.actual


def _conflict_key_predicate(
    model: AcceptedMetamodel, target: str, resolved: Sequence[_ConflictWrite]
) -> dict[str, object]:
    """A predicate selecting exactly the rows one conflict attempt addresses.

    Membership over the family-declared primary key, whatever the attempt's row
    count, so one read resolves the whole attempt and a single-key attempt takes
    no different path from a multi-key one. The key is family-declared for the
    reason every write-side key resolution is: a concrete subtype inherits it.
    """
    declaring = family_declarer(model, case_entity(model, target))
    keys = [
        attr for attr in declaring.declared_attributes if isinstance(attr.primary_key, PrimaryKey)
    ]
    if len(keys) != 1:  # pragma: no cover - no witnessed conflict target is composite-keyed
        raise EngineError(
            f"{target!r}: a conflict attempt's source read selects by a single-attribute "
            f"primary key, and this Entity declares {len(keys)}"
        )
    name = keys[0].identity.name
    return {
        "in": {
            "attr": f"{declaring.identity.canonical}.{name}",
            "values": [write.row[name] for write in resolved],
        }
    }


def _conflict_source_nodes(
    port: CaseDatabase,
    serving: ServingModel,
    model: AcceptedMetamodel,
    options: DatabaseOptions,
    target: str,
    resolved: Sequence[_ConflictWrite],
    lifecycle: LifecycleRun,
) -> tuple[dict[ObjectKey, handle.WireEntity], int]:
    """The published rows one NON-TEMPORAL conflict attempt's keyed writes are
    addressed and licensed by, read through a real ``db.wire.find``, beside the
    round trips that read cost.

    STANDALONE rather than participating, because the read has to happen where
    the case says it does: a conflict case's ``given.apply`` is a concurrent
    writer that commits BETWEEN the read and the write it invalidates, and a
    read inside the attempt's own transaction could only observe the state that
    writer already left. An effective-Optimistic target licenses exactly this —
    the retained observation IS the evidence, and a standalone source carries it
    as a participating read's does (`m-opt-lock`), which is also why every
    conflict shape reachable through public verbs is an optimistic one.

    A row the read does not answer is absent from the mapping; the write that
    wanted it is refused where its diagnosis can name the key
    (:func:`_conflict_source_node`).

    It observes like every other Handle this engine builds. The read is one
    outermost public operation, so it opens a Root Execution of its own, that
    root belongs to the run's delivered stream, and the calls it makes are round
    trips the case counts like any other — a keyed write's resolving read is
    work the framework genuinely does, whether it stands inside the transaction
    it licenses or, as here, outside it (`m-case-format` "Resolving reads a
    write owes"). What it authors no golden for is the SQL, so the read is
    charged to the observation's resolving reads and names no statement index.
    """
    instant = normalize_instant(dt.datetime.fromisoformat(INERT_CLOCK_INSTANT))
    observed = lifecycle.observation()
    with handle.Database.connect(
        port,
        serving,
        options=options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()
        nodes: dict[ObjectKey, handle.WireEntity] = {}
        with observed.resolving_reads():
            snapshot = database.wire.find(
                {"target": target, "predicate": _conflict_key_predicate(model, target, resolved)}
            )
            for root in snapshot.results():
                hint = read_origin_of(root)
                assert hint is not None  # a Wire read files a hint on every published Entity node
                nodes[hint.object_key] = root
        return nodes, observed.round_trips


def _conflict_source_node(
    target: str, write: _ConflictWrite, nodes: Mapping[ObjectKey, handle.WireEntity]
) -> handle.WireEntity:
    """The published node ``write`` settles against, or the authoring refusal.

    A conflict case describes a write a caller could actually issue, so the row
    it addresses has to be one the case's own state holds when the source read
    runs. A key the read answered nothing for describes a write no verb can
    author — the state the evidence model exists to make unreachable — and is
    refused here rather than executed as a blind statement.
    """
    node = None if write.key is None else nodes.get(write.key)
    if node is None:
        raise EngineError(
            f"{target!r}: a conflict attempt writes {write.row!r}, which its own source read "
            "found no row for — the attempt is stated against the value that read published, "
            "so a case whose target is already gone describes a write no verb can author "
            "(m-case-format 'Conflict cases')"
        )
    return node


def _refuse_unobserved_conflict_version(
    target: str, write: _ConflictWrite, node: handle.WireEntity
) -> None:
    """Refuse an attempt whose declared ``observedVersion`` is not the version its
    own source read observed.

    The declared fact and the real observation are two spellings of one state,
    and the case's golden gate bind is derived from the declared one while the
    write settles against the observed one. Letting them differ would grade a
    statement against a version no read of this lane ever saw.
    """
    declared = None if write.observation is None else write.observation.observed_version
    hint = read_origin_of(node)
    assert hint is not None  # the node came from :func:`_conflict_source_nodes`
    retained = None if hint.observation is None else hint.observation.evidence
    observed = retained.observed_version if isinstance(retained, VersionObservation) else None
    if declared != observed:
        raise EngineError(
            f"{target!r}: a conflict attempt declares `observedVersion: {declared!r}` and its "
            f"own source read observed {observed!r} — the gate this case grades binds the "
            "declared version, so the two must name one state"
        )


def _run_conflict_write(
    port: CaseDatabase,
    serving: ServingModel,
    model: AcceptedMetamodel,
    options: DatabaseOptions,
    target: str,
    concurrency: Concurrency,
    requests: case_format.TransactionKeywords,
    write_rows: Sequence[Mapping[str, object]],
    mutation: Literal["update", "delete"],
    nodes: Mapping[ObjectKey, handle.WireEntity],
    lifecycle: LifecycleRun,
) -> tuple[tuple[LoweredStatement, ...], int, int]:
    """Lower and execute one NON-TEMPORAL conflict attempt's write through
    ``db.transact`` — ONE transaction over a root connected with ``options``,
    an inert Clock (never consumed by a non-temporal write), and exactly the
    options the attempt requests (``requests``); ``concurrency`` is the
    planning value the emission is lowered and the implied shortfall classified
    under.

    Every row is written through the PUBLIC keyed Wire verb its mutation names,
    against the node ``nodes`` published for its key, so a MULTI-KEY attempt
    reaches the flush exactly as that many developer calls would and the batching
    rule — not this function — decides how many statements they become. The
    PRODUCTION flush executor's OWN affected-row enforcer raises on a violation,
    and this lane admits only the class the case's own declared facts imply
    (:func:`_implied_shortfall_error`), rendering it as the ``affectedRows``
    observation the case asserts. A failure classified any other way — a gated
    shortfall surfacing as a stale write, or the reverse — propagates and fails
    the case.

    ``statements`` (the reported golden-comparable emission) is
    :func:`_lower_conflict_write`'s own PURE re-lowering of the original rows.
    Its Lowered Statement carries the metadata that projects native execution
    carriers and planned carriers into one canonical Wire observation. It is
    reported only where the delivered lifecycle confirms the attempt ran it
    (:func:`~parallax.conformance._mechanism.envelope.delivered`).
    """
    resolved = _resolve_conflict_writes(model, target, mutation, write_rows)
    statements = _lower_conflict_write(model, port.dialect, concurrency, resolved)
    instant = normalize_instant(dt.datetime.fromisoformat(INERT_CLOCK_INSTANT))
    observed = lifecycle.observation()
    with handle.Database.connect(
        port,
        serving,
        options=options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()
        landed = _landed_conflict_rows(resolved)
        sources = [_conflict_source_node(target, write, nodes) for write in resolved]
        for write, node in zip(resolved, sources, strict=True):
            _refuse_unobserved_conflict_version(target, write, node)

        def body(tx: handle.Transaction) -> int:
            for write, node in zip(resolved, sources, strict=True):
                if mutation == "delete":
                    tx.wire.delete(node)
                else:
                    tx.wire.update(node, _conflict_changes(model, write))
            return landed  # the expectation machinery already verified this on success

        observation_requiring = _versioned_non_temporal_version_attribute(model, target) is not None
        implied = _implied_shortfall_error(observation_requiring, concurrency, model, target)
        affected = _conflict_attempt_affected(database, requests, implied, body)
        ran = envelope.delivered(statements, observed.writes, "a conflict attempt")
        return ran, affected, observed.round_trips


def _conflict_changes(model: AcceptedMetamodel, write: _ConflictWrite) -> dict[str, object]:
    """One conflict attempt row's authored assignments — its durable row less the
    identity the source node already carries, in authored order.

    The mapping preserves authored assignment order through the public call;
    Entity Layout remains the owner of emitted SET order.
    """
    instruction = write.instruction
    assert isinstance(instruction, PreparedKeyedWrite)
    identity = dict(write.key.primary_key) if write.key is not None else {}
    managed = {name: value for name, value in instruction.rows[0].items() if name not in identity}
    return ActualWireProjection(model).entity_values(instruction.target, managed)


def _conflict_write_rows(attempt: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """One conflict attempt's authored ``write`` as the ordered row sequence both
    forms denote: a lone object is the one-element case of the multi-key array
    (`m-case-format`), so the single seam here spares every lane downstream from
    knowing which spelling the case chose."""
    raw = attempt["write"]
    if isinstance(raw, list):
        return tuple(cast("list[Mapping[str, object]]", raw))
    return (cast("Mapping[str, object]", raw),)


def run_conflict_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], int, dict[str, list[MappingRow]] | None, int]:
    """Run a `conflict` case (`m-opt-lock`): the single-attempt form
    (`when.write`), or the `when.attempts` retry sequence — each attempt its OWN
    `db.transact` unit, in order, each with its own statements / affected-row
    count (the case's own `0`-then-`1` retry-contract witness). The keyed UPDATE
    or DELETE `when.mutation` names writes every row of its `write` — one row, or
    the multi-key array whose rows the batching rule may collapse into a single
    set-based statement — through the public keyed Wire verb. A temporal target
    is refused: the conflict shape is non-temporal (`m-case-format`).

    Loads no fixtures itself (the caller's own lifecycle does, per
    `m-case-format`'s conflict-shape default). `given.apply`'s concurrent writer
    commits BETWEEN the FIRST attempt's source read and the write that read
    licenses (:func:`~parallax.conformance._mechanism.given_state.apply_given_apply`),
    which is the ordering a conflict case describes: the state its write settles
    against is one a real read of this lane observed, and the writer that
    invalidated it committed afterwards. A retry attempt reads again, after the
    attempt before it ran, so it observes the state that writer left.

    Returns the ordered emissions, the FINAL (single-attempt or last-retry)
    affected-row count — the schema's one `affectedRows` slot,
    `m-conformance-adapter` — and the resulting table state when the case
    authors `then.tableState`.
    """
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    lifecycle = lifecycle_run(lifecycle)
    when = case_document.when(case)
    concurrency = case_document.concurrency(case)
    options = case_format.database_options(case)
    refuse_a_conflict_retry_opt_in(case, options, "`given.databaseOptions`")
    requests = _conflict_attempt_requests(case)
    target = first_declared_entity(case)
    if _is_temporal_entity(model, target):
        raise EngineError(
            f"{case.path.name}: {target!r} is temporal, and a conflict case's write targets a "
            "non-temporal Entity — a temporal write's race is an interleaved scenario "
            "(m-case-format 'Conflict cases')"
        )
    mutation = _conflict_mutation(when)
    emissions: list[Emission] = []
    affected = 0
    round_trips = 0
    try:
        raw_attempts = when.get("attempts")
        attempts: list[tuple[str, Mapping[str, object]]] = (
            [
                (f"/when/attempts/{index}/write", attempt)
                for index, attempt in enumerate(cast("list[Mapping[str, object]]", raw_attempts))
            ]
            if isinstance(raw_attempts, list)
            else [("/when/write", when)]
        )

        def sources_for(attempt: Mapping[str, object]) -> dict[ObjectKey, handle.WireEntity]:
            nonlocal round_trips
            nodes, source_trips = _conflict_source_nodes(
                port,
                serving,
                model,
                options,
                target,
                _resolve_conflict_writes(model, target, mutation, _conflict_write_rows(attempt)),
                lifecycle,
            )
            round_trips += source_trips
            return nodes

        # Taken before the concurrent writer commits, and spent by the first
        # attempt; every later attempt reads again, after the one before it ran.
        sources: dict[ObjectKey, handle.WireEntity] | None = sources_for(attempts[0][1])
        apply_given_apply(case, port, None)
        for pointer, attempt in attempts:
            statements, affected, attempt_trips = _run_conflict_write(
                port,
                serving,
                model,
                options,
                target,
                concurrency,
                requests,
                _conflict_write_rows(attempt),
                mutation,
                sources_for(attempt) if sources is None else sources,
                lifecycle,
            )
            sources = None
            emissions.extend(Emission(pointer, statement) for statement in statements)
            round_trips += attempt_trips
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    then = case.document.get("then")
    table_state = (
        read_table_state(port, model)
        if isinstance(then, Mapping) and "tableState" in then
        else None
    )
    # The round trips are every call this case put on the wire: each attempt's
    # own DML, summed across all of them rather than the last one's alone, and
    # the resolving read each attempt's write is licensed by. The read reaches
    # the database, so it counts exactly as the DML does (`m-case-format`
    # `then.roundTrips`), and the lifecycle stream this count must agree with
    # holds it too.
    return emissions, affected, table_state, round_trips
