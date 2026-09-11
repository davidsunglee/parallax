"""The scenario, writeSequence, and conflict lanes: a case's units of work
compiled purely to the DML each would emit, or run through the shipped
``db.transact`` entry point and reported as the observations its ``then``
members grade.

A write step is one unit of work. Its buffered keyed writes are planned by the
SAME ``build_write_planner`` factory production uses (``m-unit-work``) and each
surviving :class:`~parallax.core.unit_work.PlannedWrite` is lowered to DML by
the shared ``snapshot.handle.stream_lowered`` seam, the deliberate ``m-sql``
write edge the conformance family may compose. A scenario is a sequence of
units of work: a write step commits (or, ``rollback: true``, aborts) its
coalesced DML, a ``find`` reads committed state through the public Wire read,
and a ``uow``-grouped span runs inside one transaction. A writeSequence lowers
each entry independently and runs each as its own transaction. A conflict case
is the optimistic-lock lane: every attempt takes a real source read and writes
against the version that read observed.

The compile entry points lower purely, with no database; that pure lowering is
also what the run lanes' emissions and round-trips observations grade against,
since both are the same deterministic computation over the same instructions,
observations, and instant. Every run lane builds its own Handle over the
caller's port, applies the case's ``given.apply`` ahead of the first step, and
closes the Handle where the case that needed it ends. The observation envelope
each returns — a :class:`~parallax.conformance._mechanism.envelope.ScenarioRun`,
or the emissions, round trips, and table state a writeSequence or conflict
reports — is graded against ``then`` by the adapter.

The two sub-lanes that share this write core — the snapshot action-step
scenario and the interleaved ``uow`` fork — consume the names exported here
beyond the entry points; a scenario carrying an action step is dispatched to
the snapshot lane by the façade before reaching this module's entry points.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, cast

from parallax.conformance import (
    _case_ingress,
    case_format,
    models,
    temporal_state,
)
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._database_control import (
    CaseDatabase,
    InterleavedExecution,
    InterleavedExecutionFactory,
    ModeledExecution,
)
from parallax.conformance._lanes.turnstile import Turnstile, await_workers
from parallax.conformance._lifecycle_observation import (
    LifecycleObservation,
    LifecycleRun,
    lifecycle_run,
)
from parallax.conformance._mechanism import case_document, envelope
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
    canonicalize_read,
    case_entity,
    case_serving_model,
    default_family_root,
    family_declarer,
    first_declared_entity,
    load_case_metamodel,
)
from parallax.conformance._mechanism.transaction_control import (
    absorbing_rollback,
    committed,
    transact,
    write_adapter,
    write_connection,
)
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import (
    batch_write,
    inheritance,
    opt_lock,
    storage_layout,
)
from parallax.core.base import (
    INFINITY_LITERAL,
    TIMESTAMP,
    ManagedValue,
    TemporalBound,
    matches_neutral_type,
    normalize_instant,
)
from parallax.core.db_port import (
    DatabaseAdapter,
    DatabaseConnection,
    IsolationLevel,
    Row,
)
from parallax.core.dialect import Dialect, dialect_for
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
from parallax.core.sql_gen._compile import CompiledRead, compile_read
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.temporal_read import TemporalReadError
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    CardinalityCorruptionError,
    ClaimedKeyedWrite,
    Concurrency,
    FixedClock,
    KeyedWrite,
    MissingTargetError,
    ObjectKey,
    OptimisticLockConflictError,
    PlanningRequest,
    PredicateWrite,
    RetainedObservation,
    StaleWriteError,
    SubjectIdentity,
    TemporalObservation,
    TransactionInstant,
    VersionObservation,
    WriteEffectError,
    WriteObservation,
    WritePlanningError,
    buffered_write,
    enforce_affected_rows,
    instructions,
    object_key,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
    WriteInstruction,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_wire, encode_wire
from parallax.snapshot import handle
from parallax.snapshot.handle import (
    ServingModel,
    TransactionTimePinReadOnlyError,
    build_write_planner,
    stream_lowered,
    validate_source_pin,
)
from parallax.snapshot.handle._transaction import (
    buffer_prepared_predicate_write,
    buffer_prepared_wire_keyed_write,
)
from parallax.snapshot.materialize import source_hint_of

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
    "graph_rows",
    "is_materializing_write_step",
    "is_predicate_write_step",
    "lower_writes",
    "read_step_graph",
    "read_table_state",
    "run_conflict_case",
    "run_group_step",
    "run_interleaved_scenario_case",
    "run_scenario_case",
    "run_standalone_find",
    "run_write_sequence_case",
    "scenario_group_step_indices",
    "step_query",
    "step_rows",
    "write_entries",
]


# --------------------------------------------------------------------------- #
# Scenario / writeSequence — the unit-of-work write lanes (m-unit-work).       #
# --------------------------------------------------------------------------- #
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
# unit), so a fixed, deterministic instant stands in (`m-txtime-write` / ADR 0010:
# "a non-temporal entry's clock value is inert, pick something deterministic").
INERT_CLOCK_INSTANT: Final[str] = "1970-01-01T00:00:00+00:00"

# The compile lane's own audit-neutral Subject Identity: this lane never opens
# a real Principal boundary, and a Planning Request requires one regardless
# (`m-unit-work`) — the harness proves the value is never inspected, so any
# nonempty constant serves every pure re-lowering call below identically.
_PLANNING_SUBJECT: Final[SubjectIdentity] = SubjectIdentity("conformance-compile-lane")


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
# write-row key in any shape: they are authored beside the write, at
# `when.observedTxStart` / `when.observedValidStart` — and, on a retry attempt,
# `observedTxStart` alone, since the edge form is single-attempt only
# (`m-case-format`) — so a row carrying one is refused rather than stripped.
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
    """

    instruction: PreparedWrite
    oracle_observation: WriteObservation | None


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
    (m-txtime-write / m-bitemp-write ``at``; ADR 0010: the Clock, never a
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
    is refused HERE, where the authoring diagnosis can name the entry. It is the
    SAME rule :func:`_conflict_close_row` applies to a temporal conflict attempt's
    multi-key ``write`` array; the shared case schema cannot express either,
    because the row count it may admit depends on whether the target entity is
    temporal, which only the model knows.

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


def _build_temporal_instruction(
    entry: Mapping[str, object],
    model: AcceptedMetamodel,
    shadow: TemporalShadow,
    unit_inserted: set[ObjectKey],
    source: ObservedNodes | None,
) -> _ResolvedWrite:
    """One TEMPORAL writeSequence/scenario entry -> its canonical keyed
    instruction plus the observation its close/chain consumes.

    Where the observation comes from is what ``source`` decides. Absent one, it is
    the milestone ``shadow`` tracks for this key (`m-txtime-write` /
    `m-bitemp-write` "the engine supplies observed rows from case state" — never
    an implicit resolving read), which is how every writeSequence entry and every
    ungrouped scenario write resolves; a milestone a materializing predicate write
    of this case already moved (:func:`_refuse_materialized_case_state`), and one
    whose tracked members can no longer account for the whole stored row
    (:func:`_refuse_unaccounted_document_milestone`), are both refused first.
    Given one, the entry's own
    step named a find of its `uow` group with ``on``, and the evidence is the
    Observed State Key the claim that node carries is addressed by
    (:func:`_settled_against_source`).

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
    (`m-unit-work` same-transaction coalescing, `m-txtime-write-008` /
    `m-bitemp-write-014`): a later entry targeting one of them is a
    same-buffer coalescing candidate whose OWN close/chain arithmetic never
    runs (the planner folds it into the pending insert before finalization
    ever sees it) — its observation is forced to `None`, and with no observation
    consumed there is no milestone for it to retire. What the ledger ends up
    holding for the key is the COALESCED row: :func:`_lower_resolved` tracks the
    surviving Planned Insert off the finished plan, so the tracked state is the
    milestone the flush actually writes rather than a stand-in for it.
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
    if not is_insert and not is_coalescing_candidate:
        if source is None:
            _refuse_materialized_case_state(model, entity_metadata, row, shadow)
            _refuse_unaccounted_document_milestone(model, entity_metadata, row, shadow)
            observation = shadow.resolve(model, entity_metadata, row)
        else:
            settled = _settled_against_source(entity_name, pk_key, source)
            # A temporal row's evidence is its whole predecessor milestone; a
            # versioned target's Version Observation can never answer a lookup
            # this branch reached, because the branch is chosen by temporality.
            assert isinstance(settled, TemporalObservation)
            observation = settled
    if observation is not None and not is_coalescing_candidate:
        shadow.retire(model, entity_metadata, observation)
    if is_insert and pk_key is not None:
        unit_inserted.add(pk_key)
    return _ResolvedWrite(prepared, observation)


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
      alone and every other key names an entity member, while a temporal close's
      observed coordinate rides beside the write, at ``when.observedTxStart`` /
      ``when.observedValidStart`` — and, on a retry attempt, ``observedTxStart``
      alone (`m-case-format`). Stripping one from a row — or projecting the row
      past it — would silently discard the very coordinate the author meant to
      observe.
    - a TEMPORAL target's write observes a whole predecessor MILESTONE, which no
      flat row cell can name. It resolves either from tracked case state
      (:class:`~parallax.conformance.temporal_state.TemporalShadow`) or, where the
      write's own step named the find it settles against, from the observations
      that `uow` group's reads filled (:func:`_settled_against_source`); a
      standalone close's gate is authored beside the write. Which of the two
      supplies it changes nothing here: neither is a cell the row may carry.
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
            f"a write row authors no `{key}` (m-case-format: an observed milestone's own edge "
            "coordinate rides beside the write, at `when.observedTxStart` / "
            "`when.observedValidStart`, or an attempt's own `observedTxStart`; a writeRow "
            "reserves `observedVersion` alone and every other key names an entity member)"
        )
    if _is_temporal_entity(model, entity_name):
        return (
            f"a temporal row authors no `{key}` (m-unit-work: a temporal write observes a whole "
            "predecessor milestone, which no flat row cell can name — the engine resolves one "
            "from tracked case state or from the find its own step settles against, and a "
            "standalone close's gate rides beside the write)"
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
    entry, :func:`_build_temporal_instruction` for a temporal one,
    :func:`_resolve_conflict_writes` for a non-temporal conflict attempt's
    ``write``, and :func:`_run_conflict_close` for a temporal attempt's close
    row. EVERY row of each reaches it, not merely the first: the two non-temporal
    producers resolve the whole authored sequence (:func:`_durable_rows`), and the
    two temporal ones admit a single row and refuse a plural entry outright
    (:func:`_temporal_entry_row`, :func:`_conflict_close_row`) rather than
    settling one row and discarding the rest.

    Refusal (:func:`_observation_refusal`) and stripping are one
    indivisible step here precisely because they were separable before: a
    producer that copied the row itself got a perfectly usable durable row while
    silently skipping the refusal, and each new write shape rediscovered the
    hole. There is now no way to obtain a durable row without being refused.

    The durable row never carries a control key: the write-instruction schema
    forbids every one of them (ADR 0013), which `instructions.deserialize`
    enforces for the lanes that reach it and which the lanes that bypass it — a
    standalone close settles straight through
    :func:`~parallax.snapshot.handle.plan_temporal_close` — depend on this seam
    for.
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
    (:func:`_lower_resolved`, `parallax.snapshot.handle.Database.transact`).
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
    shadow: TemporalShadow,
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
    which admits exactly ONE row: its authored ``statements`` count is the DML
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
    the group instead: from the find its step NAMED with ``on``
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
    if _is_temporal_entity(model, entity_name):
        return [_build_temporal_instruction(entry, model, shadow, unit_inserted, source)]
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
    source: ObservedNodes | None = None,
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
    this unit ran — never a store spanning the whole scenario.

    ``source`` is what the step's own ``on`` named (`m-case-format` *Settling
    against a grouped find*): the observed states ONE earlier find of this same
    group recorded, which every entry of this step settles against instead of
    against tracked case state — a milestone on a temporal target, a generation on
    a versioned Non-Temporal one. It defaults to absence, which is every lane but
    a grouped scenario write step naming a find."""
    resolved: list[_ResolvedWrite] = []
    unit_inserted: set[ObjectKey] = set()
    for entry in entries:
        resolved.extend(
            _build_instructions(entry, model, shadow, unit_inserted, group_observations, source)
        )
    return resolved


def _buffered(
    instruction: PreparedWrite, observation: WriteObservation | None, model: AcceptedMetamodel
) -> PreparedWrite | ClaimedKeyedWrite:
    """One resolved entry as the buffer item a unit of work would hold for it.

    What the entry settles against is the rule
    :func:`~parallax.core.opt_lock.instruction_evidence` states for every caller
    holding an instruction, which is the rule production's own write verbs read
    off a source value's hint: an entry whose case document (or this
    group's own prior find) supplied an observation settles against it as given,
    and an entry that supplied none reaches the claim-scope derivation over the
    same two declared facts a developer verb reads. Sharing the rule rather than
    restating it is what keeps this PURE re-lowering oracle answering the plan
    the real flush produces, coalescing included; the shared resolver reads
    nothing but the model, so the oracle stays readless. Whether an observation
    may exist at all is decided BEFORE this point, by :func:`_durable_row` — the
    one seam every producer's rows pass through — and by the carriers' own
    structural refusals; this function only forwards what they left.
    """
    assert isinstance(
        instruction, PreparedKeyedWrite
    )  # every producer of this seam resolves keyed writes
    return buffered_write(
        instruction, opt_lock.instruction_evidence(model, instruction, supplied=observation)
    )


def _lower_resolved(
    resolved: Sequence[_ResolvedWrite],
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
    shadow: TemporalShadow,
) -> tuple[LoweredStatement, ...]:
    """Plan one write buffer through the SAME ``build_write_planner`` factory
    the composition layer uses (`parallax.snapshot.handle.Database.transact`)
    and lower each survivor — PURE, no database. The planner is the ONE
    authority that merges a case entry's rows: every entry arrives as its own
    per-row instructions, and which of them share a statement is decided HERE,
    per physical shape, by the same `batch_write.collapses` eligibility answer
    production consults.

    ``entries`` are the case entries ``resolved`` was built from, carried only so
    their authored ``statements`` counts can be graded against the statements
    this ONE plan actually emits (:func:`_check_statement_count_consistency`) —
    the count is never derived from a second, reconstructed plan.

    The case-state ledger advances HERE, from THIS plan's own opened rows
    (:meth:`TemporalShadow.track_opened`) — the milestone a later choreography
    unit observes is the one this write actually plans, so there is no second
    expansion of the same topology to drift from it. The close's retirement
    happened at resolution, where the observation it consumed is known. Both
    advances belong to the boundary the caller stages them on
    (:meth:`TemporalShadow.staged`), so a doomed unit's are discarded with its
    rows.
    """
    buffer = [_buffered(write.instruction, write.oracle_observation, model) for write in resolved]
    instant = _pinned_instant(tx_instant)
    plan = (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                subject_identity=_PLANNING_SUBJECT,
                transaction_instant=instant,
                concurrency=concurrency,
                buffered_writes=buffer,
            )
        )
        .plan
    )
    statements = [statement for _step, statement in stream_lowered(plan, model, dialect)]
    _check_statement_count_consistency(entries, len(statements))
    shadow.track_opened(model, plan)
    return tuple(statements)


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
    :func:`eligibility` before the compile lane ever calls this — reaching
    this seam with one is therefore always a caller wiring defect, surfaced as
    planning's own defensive :class:`~parallax.core.unit_work.WritePlanningError`.
    """
    # A readless predicate write declares no Transaction-Time boundary, so the
    # inert instant it carries is never captured (ADR 0010).
    instant = _pinned_instant(INERT_CLOCK_INSTANT)
    plan = (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                subject_identity=_PLANNING_SUBJECT,
                transaction_instant=instant,
                concurrency=concurrency,
                buffered_writes=[prepared],
            )
        )
        .plan
    )
    statements = [statement for _step, statement in stream_lowered(plan, model, dialect)]
    assert len(statements) == 1  # a readless predicate write is always exactly one statement
    return statements[0]


def _compile_find(
    step: Mapping[str, object],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    *,
    result_form: Literal["row", "instance"] = "instance",
) -> CompiledRead:
    """Compile a scenario ``find`` step through the read path with the read-lock
    suffix — the COMPILE lane's own oracle, which reaches no database.

    Every RUN lane instead executes the step through the public Wire read
    (:func:`run_standalone_find`, :func:`_run_uow_group`) and reports the
    statement production actually ran, so this function answers the compile lane
    alone.

    A scenario find is an in-transaction object find, so ``concurrency`` is the
    scenario's RESOLVED Concurrency Preference
    (:func:`~parallax.conformance._mechanism.case_document.concurrency` —
    declared ``when.uow.concurrency`` or the `optimistic` default), never absent. It
    resolves against the step's own target Entity into the Effective
    Concurrency Strategy that decides the ``m-sql`` shared-row-lock suffix
    (``for share of t0``) — through
    :func:`~parallax.snapshot.handle.entity_read_lock`, the same seam the
    production `Transaction.find` derives every level's lock through. The
    Locking strategy renders the suffix after every clause; the Optimistic one
    renders none (the `m-txtime-write-008` / `m-bitemp-write-014` coalescing
    witnesses exercise that branch).

    ``result_form`` defaults to ``instance`` — an ORDINARY (managed) scenario
    find mirrors production ``Transaction.find`` (`m-sql` *Read projection*,
    slot 4 included); for a value-object-free entity row-form and instance-form
    are byte-identical, so the default only matters to VO-bearing targets.
    A materializing predicate write's OWN internal resolving read is ROW-form
    (`m-value-object-047` pins its need-driven Document projection) but is compiled by
    the materializing predicate-write resolve in `parallax.snapshot.handle`
    directly, never through this function — the RUN lane reports its ACTUAL
    executed SQL off what the transaction put on the wire
    (:func:`_run_materializing_pair`), not a separate pure re-lowering (its
    binds are query-result-dependent, so no pure oracle exists to compute them
    from).

    This composition — `compile_read` + `entity_read_lock`, mirroring
    `Transaction.find`'s own derivation — is IRREDUCIBLE adapter content, not
    a residual "mirrors production" gap to close. The case-driven engine has
    no typed Python entity classes at all (a scenario step is a raw,
    case-authored dict carrying a serialized Object Query), so
    there is no `LoweredStatement` to hand a production seam — `Transaction.find`
    itself REQUIRES one. Re-routing through a production API would mean
    inventing a new one solely to serve this untyped input, the opposite of
    engine-thinning; this function stays the adapter's own translation from
    "raw case step" to compiled read, composing production's `m-sql` /
    `m-read-lock` building blocks rather than duplicating their logic.
    """
    query = step_query(step, model)
    metadata = case_entity(model, query.target.canonical)
    entity_query = canonicalize_read(query, metadata, model)
    return compile_read(
        entity_query,
        model,
        dialect,
        result_form=result_form,
        lock=handle.entity_read_lock(model, metadata.identity, concurrency),
    )


def step_query(step: Mapping[str, object], model: AcceptedMetamodel) -> ObjectQueryNode:
    """A scenario or coherence read step's own canonical Object Query.

    The query travels as authored. Root as-of injection and per-hop navigation
    canonicalization are `deep_fetch.plan`'s own first step on every production
    read path, so applying them here would apply them twice; the compile lane's
    :func:`_compile_find` composes them itself precisely because it reaches no
    executor.
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

    A step carrying its scenario's Concurrency Preference runs inside a real
    ``db.transact`` so the read participates exactly as
    :func:`~parallax.conformance._lanes.reads.run_read_case` does and exactly
    as a developer's ``tx.find`` would: whether it takes the shared row lock is
    then the target Entity's own Effective Concurrency Strategy, never a
    property of the preference alone or of what the scenario goes on to write.
    """
    query = step_query(step, context.model)
    observed = lifecycle.observation()
    with handle.Database.connect(port, context.serving, lifecycle_provider=observed.provider) as db:
        return (
            transact(db, lambda tx: tx.wire.find(query), concurrency=context.concurrency),
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
    projection = ActualWireProjection(model)
    return [
        _projected_row(model, projection, columns, family, envelope.graph_root(root) or {})
        for root in roots
    ]


def _projected_row(
    model: AcceptedMetamodel,
    projection: ActualWireProjection,
    columns: Mapping[str, tuple[tuple[str, AttributeMetadata | ValueObjectMetadata], ...]],
    family: bool,
    node: Mapping[str, object],
) -> Mapping[str, object]:
    """One published node as its projection's row."""
    variant = node.get("familyVariant")
    selected: frozenset[MemberIdentity] | None = None
    if family and node:
        if not isinstance(variant, str):
            raise EngineError(
                "an abstract-position read publishes a concrete node carrying "
                f"`familyVariant`; this one published {sorted(node)}"
            )
        entity = case_entity(model, variant)
        view = inheritance.view(model).entity(entity.identity)
        if view is None:  # pragma: no cover - every accepted Entity has a view
            raise EngineError(f"{entity.identity.canonical}: no inheritance position")
        selected = frozenset(
            member.identity
            for member in (*view.applicable_attributes, *view.applicable_value_objects)
        )
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
    if not family or not node:
        return published
    return {
        **dict.fromkeys(column for options in columns.values() for column, _member in options),
        **published,
        "familyVariant": variant,
    }


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
        statement = _compile_find(step, context.model, dialect, context.concurrency).statement
        return LoweredStep(f"/scenario/{index}/objectQuery", (statement,), False, False)
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
        context.shadow,
        entry_instant(entries[0]),
        group_observations,
    )
    return LoweredStep(f"/scenario/{index}/write", statements, True, rollback)


def _doomed_group_spans(case_name: str, steps: Sequence[Mapping[str, object]]) -> dict[int, int]:
    """Each DOOMED `uow` group's own step span, keyed ``start -> end`` inclusive.

    Only the doomed ones: a committing group's steps need no staging, so leaving
    them out lets the caller drive them as ordinary steps. The two spans this
    lane cannot represent answer emptily — an interleaved two-group race
    (:func:`_scenario_uow_spans` returns ``None``) needs two concurrent units a
    pure lowering has no way to model, and every case carrying that shape is
    `compileEligibility: run-only` for the same reason.
    """
    spans = _scenario_uow_spans(case_name, steps)
    if spans is None:
        return {}
    return {start: end for start, end in spans.values() if _group_is_doomed(steps, start, end)}


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
    short-circuits at :func:`eligibility` before this function ever runs
    (`adapter.compile_case`). The group observation store therefore stays
    permanently empty here: a keyed write's Version Observation comes from its
    OWN row's reserved ``observedVersion`` control key alone
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
    context = CaseContext(
        serving, model, concurrency, TemporalShadow(), case_format.uow_isolation(case)
    )
    seed_shadow_from_fixtures(case, model, context.shadow)
    group_observations: GroupObservations = []
    lowered: list[LoweredStep] = []
    try:
        steps = case_document.scenario_steps(case)
        doomed_spans = _doomed_group_spans(case.path.name, steps)
        index = 0
        while index < len(steps):
            end = doomed_spans.get(index)
            if end is not None:
                with context.shadow.staged(doomed=True):
                    for grouped in range(index, end + 1):
                        lowered.append(
                            _lower_scenario_step(
                                context, dialect, steps[grouped], grouped, group_observations
                            )
                        )
                index = end + 1
                continue
            step = steps[index]
            with context.shadow.staged(doomed=step.get("rollback") is True):
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
    instruction: WriteInstruction | PreparedWrite, model: AcceptedMetamodel
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

    Composed the way :func:`_run_conflict_close` composes a standalone close —
    the caller's own plan, executed on the port's own transaction — rather than
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
    model: AcceptedMetamodel, entity_name: str, keys: Sequence[ObjectKey]
) -> dict[str, object]:
    """The canonical Object Query resolving every row of ``entity_name`` — a
    CANONICAL Entity spelling — one choreography unit writes against existing
    state.

    Membership over the family-declared primary key, one read per target Entity
    however many rows the unit addresses, which is what a caller holding several
    writes of one Entity does: it reads them together and writes what the read
    returned. Reading per row instead would cost the corpus a round trip per row
    for no semantic gain, and reading between two writes would force-flush the
    first — destroying the very batch collapse the goldens pin.

    A temporal target selects ``latest`` on every dimension it declares, which is
    both what a canonical Object Query requires (one selection per declared
    dimension) and the only milestone a keyed write may address: the
    Transaction-Time past is read-only, so a source pinned anywhere else is a
    value no verb accepts.
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
    temporal = {
        _LATEST_SELECTION[axis.dimension]: {"asOf": "latest"}
        for axis in declaring.declared_as_of_axes
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
    needed: dict[str, dict[ObjectKey, None]] = {}
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
        needed.setdefault(canonical, {})[key] = None
    return [_unit_source_query(model, entity, tuple(keys)) for entity, keys in needed.items()]


def _execute_write_unit(
    port: CaseDatabase,
    serving: ServingModel,
    model: AcceptedMetamodel,
    concurrency: Concurrency,
    resolved: Sequence[_ResolvedWrite],
    statements: Sequence[LoweredStatement],
    tx_instant: str,
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """Execute one choreography unit's ALREADY-RESOLVED instructions through the
    production ``db.transact`` entry point — ONE transaction,
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
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as database:

        def body(tx: handle.Transaction) -> None:
            state = GroupState()
            with observed.resolving_reads():
                for query in _unit_source_reads(model, resolved):
                    state.published.extend(_published_nodes(tx.wire.find(query)))
            for write in resolved:
                _buffer_wire_write(tx, model, state, write, None)

        with absorbing_rollback():
            transact(database, body, concurrency=concurrency)
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
    with context.shadow.staged(doomed=rollback):
        resolved = _resolve_entries(entries, context.model, context.shadow, group_observations)
        statements = _lower_resolved(
            resolved,
            entries,
            context.model,
            port.dialect,
            context.concurrency,
            tx_instant,
            context.shadow,
        )
        ran, unit_trips = _execute_write_unit(
            port,
            context.serving,
            context.model,
            context.concurrency,
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
    instruction: PreparedPredicateWrite,
    statement: LoweredStatement,
    tx_instant: str,
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """Execute a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) through the SAME production ``db.transact`` entry point every
    other write path uses. The conformance adapter has already normalized the
    case-format carriers into a core-owned ``PreparedPredicateWrite``; the
    private execution bridge retains production ownership of dispatch,
    materialization, lifecycle, and buffering without producing another
    instruction.

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
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as database:

        def body(tx: handle.Transaction) -> None:
            buffer_prepared_predicate_write(tx, instruction)

        with absorbing_rollback():
            transact(database, body, concurrency=context.concurrency)
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
    shadow = context.shadow
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
    # directly; `canonicalize_read` would additionally inject interval
    # predicates and is therefore still not the apples-to-apples form.
    comparable_find = _case_ingress.prepare_case_write(
        PredicateWrite(
            "delete",
            instructions.PredicateSelection(write_target, find.predicate),
            (),
        ),
        model,
    )
    assert isinstance(comparable_find, PreparedPredicateWrite)
    if comparable_find.selection.predicate.authored != write_predicate:
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
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as database:

        def body(tx: handle.Transaction) -> None:
            buffer_prepared_predicate_write(tx, instruction)

        with shadow.staged(doomed=rollback):
            with absorbing_rollback():
                transact(database, body, concurrency=context.concurrency)
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
    the caller (:func:`_scenario_uow_spans` / :func:`run_interleaved_scenario_case`)
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
    SECOND, peer-backed session) — :func:`run_interleaved_scenario_case` is
    the entry point that can, on the cases its OWN guards admit. What this
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


def _group_tx_instant(steps: Sequence[Mapping[str, object]], start: int, end: int) -> str:
    """The Clock instant a `uow` group's own choreography unit runs at — its
    first write entry's own instant (m-txtime-write/m-bitemp-write `at`; ADR
    0010), or the inert default when the group carries no write (or every
    write entry names none, i.e. every group this round targets a
    non-temporal entity)."""
    for i in range(start, end + 1):
        step = steps[i]
        if "write" in step:
            entries = write_entries(step["write"])
            if entries:
                return entry_instant(entries[0])
    return INERT_CLOCK_INSTANT


def _group_is_doomed(steps: Sequence[Mapping[str, object]], start: int, end: int) -> bool:
    """Whether a `uow` group ROLLS BACK after its last step: at least one of
    its OWN write steps declares `rollback: true` — the WHOLE group is then
    the doomed unit of work (`m-case-format` scenario `uow` grouping), not
    just that one step."""
    return any(
        "write" in steps[i] and steps[i].get("rollback") is True for i in range(start, end + 1)
    )


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
    opened. The record is frozen because none of the four is ever REBOUND inside
    a case; the tracker's own contents advance, which is exactly the state a
    shared tracker exists to carry.

    The dialect is deliberately NOT one of them. It is fixed by the connection a
    unit executes through rather than by the case, and one case's steps do not
    all run through one connection — each interleaved group runs on a dedicated
    session of its own. Each lowering therefore reads it off the port about to execute the
    statement (:class:`_GroupSession` for a group, the unit's own port
    otherwise), so this record can travel beside any of them.

    The isolation is the case's own `when.uow.isolation`, carried beside the
    concurrency preference because both are `db.transact` arguments a held group
    opens at rather than anything a step's translation reads. It has no default:
    a level the case declared and no lane propagated is invisible, so every
    construction states it — ``None`` for a case declaring none.
    """

    serving: ServingModel
    model: AcceptedMetamodel
    concurrency: Concurrency
    shadow: TemporalShadow
    isolation: IsolationLevel | None


def _empty_published() -> list[handle.WireEntity]:
    return []


def _empty_group_finds() -> dict[int, tuple[handle.WireEntity, ...]]:
    return {}


def _empty_opened() -> dict[ObjectKey, handle.WireEntity]:
    return {}


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
    read-your-own-writes reaches a row no find could have returned. All three are
    built fresh per group, never a scenario-wide store, so no value crosses a
    transaction boundary.
    """

    published: list[handle.WireEntity] = field(default_factory=_empty_published)
    finds: dict[int, tuple[handle.WireEntity, ...]] = field(default_factory=_empty_group_finds)
    opened: dict[ObjectKey, handle.WireEntity] = field(default_factory=_empty_opened)


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
        hint = source_hint_of(node)
        if hint is not None and hint.observation is not None:
            claims.append(hint.observation)
    return claims


def _node_object_key(node: handle.WireEntity) -> ObjectKey:
    hint = source_hint_of(node)
    assert hint is not None  # every node in this state came from a read or an insert
    return hint.object_key


def _writable_source(node: handle.WireEntity) -> bool:
    """Whether a keyed write may be addressed by ``node`` at all.

    A group may publish SEVERAL milestones of one key — an audit read of the
    Transaction-Time past beside a read of the current row — and only the
    current one is writable, because the Transaction-Time past records what the
    system knew and is never rewritten. A caller holding both hands the verb the
    writable one, so an unreferenced scan skips what the verb would refuse
    rather than reaching for the refusal.
    """
    hint = source_hint_of(node)
    assert hint is not None  # as above
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
        return matched[0]
    opened = None if key is None else state.opened.get(key)
    if opened is not None:
        return opened
    for node in reversed(state.published):
        if _node_object_key(node) == key and _writable_source(node):
            return node
    raise EngineError(
        f"{entity_name!r}: a keyed write addresses {key!r}, which no read of its own "
        "choreography unit published and no write of it opened — every keyed write here is "
        "stated through the public verb its mutation names, against a value the caller holds, "
        "and a choreography unit comes to hold one only by reading the row or by opening it "
        "with its own insert (m-case-format 'Resolving reads a write owes')"
    )


def _source_find_nodes(
    step: Mapping[str, object], index: int, group_finds: Mapping[int, tuple[handle.WireEntity, ...]]
) -> tuple[handle.WireEntity, ...] | None:
    """What the find step this WRITE step names with ``on`` published
    (`m-case-format` *Settling against a grouped find*) — ``None`` when it names
    no source, which is every write step but one settling against its group's own
    read.

    ``group_finds`` holds one entry per find step of THIS group that has already
    run, so a reference it cannot satisfy names a step outside the group, a step
    that is not a find, or one that has not run yet. All three are the same
    authoring defect and all three are refused here, rather than resolved to an
    empty tuple that would read as "the find published nothing".
    """
    source = step.get("on")
    if source is None:
        return None
    if not isinstance(source, int) or isinstance(source, bool):
        raise EngineError(
            f"scenario[{index}]: a write step settles against ONE find step, named by its "
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
) -> None:
    """Buffer ONE resolved keyed write through the public ``tx.wire`` verb its
    mutation names.

    Driven off the SAME :class:`_ResolvedWrite` the pure oracle plans, so the
    real write and the reported emission read one resolution: the durable row,
    its Valid-Time bounds, and its mutation all come from the instruction, and
    what this adds is only which verb states them and which published value the
    write is addressed by.

    An insert opens a row no find can have returned, so the node the verb answers
    is recorded for the rest of the group — the read-your-own-writes source a
    later entry of the same unit resolves against. Every other mutation takes its
    source from what this group published, and its change set is the durable row
    less the identity that source already carries: a PK-only row therefore states
    the empty change set, which is the ordinary no-op.
    """
    instruction = write.instruction
    assert isinstance(
        instruction, PreparedKeyedWrite
    )  # every resolved entry this lane buffers is keyed
    entity_name = instruction.target.identity.canonical
    entity_metadata = instruction.target
    row = dict(instruction.rows[0])
    valid_from = _bound_instant(instruction.bounds.valid_from)
    until = _bound_instant(instruction.bounds.until)
    if instruction.mutation in INSERT_MUTATIONS:
        payload = _wire_insert_payload(model, entity_metadata, row)
        opened = (
            tx.wire.insert_until(
                entity_name,
                payload,
                valid_from=_required(valid_from),
                until=_required(until),
            )
            if instruction.mutation == "insertUntil"
            else tx.wire.insert(entity_name, payload, valid_from=valid_from)
        )
        state.opened[_node_object_key(opened)] = opened
        return
    key = object_key(instruction, model)
    node = _group_source_node(entity_name, key, state, named)
    identity = dict(key.primary_key) if key is not None else {}
    changes = ActualWireProjection(model).entity_values(
        entity_metadata,
        {name: value for name, value in row.items() if name not in identity},
    )
    match instruction.mutation:
        case "update":
            tx.wire.update(node, changes, valid_from=valid_from)
        case "updateUntil":
            tx.wire.update_until(
                node, changes, valid_from=_required(valid_from), until=_required(until)
            )
        case "delete":
            tx.wire.delete(node)
        case "terminate":
            tx.wire.terminate(node, valid_from=valid_from)
        case _:
            tx.wire.terminate_until(node, valid_from=_required(valid_from), until=_required(until))


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


def _bound_instant(literal: str | dt.datetime | None) -> dt.datetime | None:
    """One instruction-level Valid-Time bound as the instant a verb takes."""
    if literal is None:
        return None
    instant = dt.datetime.fromisoformat(literal) if isinstance(literal, str) else literal
    return normalize_instant(instant)


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
class _GroupSession:
    """The connection ONE `uow` group runs on: the port it executes through, and
    the Handle opened over that port.

    One value rather than two arguments because a group's SQL is spelled by the
    port that executes it (`m-dialect`), and one case's groups do not all run on
    one connection — each interleaved group runs on a dedicated session of its
    own. Handing
    a runner a Handle and a dialect apart admits a group lowering in one
    connection's spelling while executing in another's, so this takes the port
    alone and OPENS the Handle over it: no caller can hand it a Handle connected
    to some other port, and the pair it holds names one connection.
    """

    adapter: DatabaseAdapter
    database: handle.Database

    def __init__(
        self,
        adapter: DatabaseAdapter,
        context: CaseContext,
        instant: dt.datetime,
        observation: LifecycleObservation,
    ) -> None:
        object.__setattr__(self, "adapter", adapter)
        object.__setattr__(
            self,
            "database",
            handle.Database.connect(
                adapter,
                context.serving,
                clock=FixedClock(instant),
                lifecycle_provider=observation.provider,
            ),
        )

    @property
    def dialect(self) -> Dialect:
        return self.adapter.dialect

    def close(self) -> None:
        """Close the Handle this session opened, and the runtime under it."""
        self.database.close()


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
    (never a scenario-wide store), records the pure re-lowering every
    other write path uses (:func:`_lower_resolved`) BEFORE the group's flush
    executes anything — the runner reconciles the group's whole plan against what
    that flush delivered — and then buffers each resolved write through the PUBLIC
    ``tx.wire`` verb its mutation names, against the value this group published
    for its key. Every entry a group holds is therefore caller-authored: a
    DB-computed write marker is a choreography unit of its own and no group step
    may carry one (`m-case-format` "Buffered keyed write instructions"), which
    this refuses by name rather than leaving to the verb that would reject the
    value. A FIND step runs through ``tx.wire.find`` — the participating
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
    if "write" in step:
        entries = write_entries(step["write"])
        named = _source_find_nodes(step, index, state.finds)
        source = None if named is None else tuple(_published_claims(named))
        resolved = _resolve_entries(
            entries, model, context.shadow, _published_claims(state.published), source
        )
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
        for write in resolved:
            _buffer_wire_write(tx, model, state, write, named)
        return (
            LoweredStep(f"/scenario/{index}/write", statements, True, step.get("rollback") is True),
            None,
        )
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
    (:func:`_group_tx_instant`), and the doom decision — `rollback: true` on any
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
    tx_instant = _group_tx_instant(steps, start, end)
    doomed = _group_is_doomed(steps, start, end)
    state = GroupState()
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    observation = lifecycle.observation()
    session = _GroupSession(write_adapter(port, rollback=doomed), context, instant, observation)
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

        with context.shadow.staged(doomed=doomed), absorbing_rollback():
            transact(
                session.database, body, concurrency=context.concurrency, isolation=context.isolation
            )
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
# Interleaved `uow` groups — the two-group shapes: the optimistic-lock race    #
# (`m-opt-lock-012`) and the Isolation Level scenarios alike, admitted by ONE  #
# guard on ORACLE SHAPE: a step stating `expectGraph` is REFUSED below for     #
# lack of a `stepGraphs` channel to answer it, so read oracles here are        #
# row-valued only — a write step, stating no oracle of its own, is asked for   #
# nothing. Which of the rest a sweep routes here is its own to say             #
# (`test_run_sweep._INTERLEAVED_RUNNER_CASES`) — a choreography needing a      #
# peer's DML on the wire BEFORE that peer's own flush edge is left out, not    #
# for want of a channel here: this lane would run it, reconcile its delivered  #
# statements, and report its emissions, round trips and rows for the sweep to  #
# grade. A real unit of work buffers to its boundary, so that window never     #
# opens and those oracles hold at EVERY level — a pass asserting nothing about #
# isolation. `_run_uow_group` above runs                                       #
# ONE contiguous group on the main connection; a genuinely interleaved case    #
# needs TWO groups held open CONCURRENTLY over TWO real sessions (the scoped   #
# `ProvisionedRun.interleaved_execution` seam) — a DIFFERENT scoped-control    #
# consumer than the                                                           #
# `when.concurrency` rounds runner (`parallax.conformance.concurrency_runner`, #
# real `db.transact` calls, production routing, not verbatim                   #
# authored statements). :class:`Turnstile` sequences the two groups' own      #
# steps in AUTHORED order across two worker threads — deterministic (never a   #
# genuine race at the Python level) because optimistic mode's own reads take   #
# no lock and the choreography hands off control explicitly at each step, so   #
# there is nothing to race. A step hands off only once it is WHOLE: a streamed #
# read step's every page is drained before the turnstile advances, so a peer's #
# commit lands BETWEEN two deliveries and never inside one.                    #
# --------------------------------------------------------------------------- #
def _empty_group_rows() -> dict[int, list[Mapping[str, object]]]:
    return {}


@dataclass(slots=True)
class _InterleavedGroupResult:
    """One interleaved group's own report: its lowered steps (keyed by
    scenario step index), the conflict's own `actual` affected-row count
    when its LAST write step doomed the group via a genuine optimistic-lock
    conflict (`None` for a group that committed, or that never conflicts),
    any OTHER exception the worker thread raised (re-raised on the main
    thread once both join — never silently swallowed), and every OWN find
    step's own observed rows (keyed by scenario step index) — the group's own
    oracle for `expectRows`, the
    SAME grade the ordinary scenario run lane gives every OTHER find step through
    its `stepRows` observation; without this the caller has no way to grade a
    grouped find at all, only its DML shape."""

    lowered: dict[int, LoweredStep]
    conflict_actual: int | None = None
    failure: BaseException | None = None
    rows: dict[int, list[Mapping[str, object]]] = field(default_factory=_empty_group_rows)
    round_trips: int = 0


def _run_interleaved_group(
    session: ModeledExecution,
    observation: LifecycleObservation,
    context: CaseContext,
    steps: Sequence[Mapping[str, object]],
    indices: Sequence[int],
    turnstile: Turnstile,
    result: _InterleavedGroupResult,
) -> None:
    """Run one interleaved group's OWN steps (``indices``, in authored order,
    possibly non-contiguous across the WHOLE scenario) inside ONE real
    ``db.transact`` call on ``session``'s own Handle — the SAME :func:`run_group_step`
    interpreter :func:`_run_uow_group` drives over a contiguous span,
    generalized to an explicit index list and gated by ``turnstile`` at every
    step. A write step's lowering is therefore recorded BEFORE the group's own
    flush executes it, so a step that later CONFLICTS still reports its own
    well-formed golden DML (`m-opt-lock` "Conflict detection" — the SQL is
    correct, the row count is not).

    The group's own boundary flushes what its last step buffered, and that
    flush may itself raise
    :class:`~parallax.core.unit_work.OptimisticLockConflictError` (the SAME
    signal a caller-driven retry catches, `_run_conflict_write`'s own
    precedent) — caught HERE, its ``actual`` recorded, and the transaction
    aborts (never retried: `m-opt-lock-012`'s own `when.uow` sets no
    ``retryOptimisticConflicts`` opt-in, so :func:`~parallax.core.auto_retry.
    run_with_retry` surfaces it after exactly one attempt). Unlike
    :func:`_run_uow_group`'s own OWN ``doomed``/``rollback: true`` convention
    (an authored, EXPLICIT abort signal independent of any real conflict),
    this lane's ONE conflicting witness (`m-opt-lock-012`) authors
    ``rollback: true``
    ONLY on the step whose OWN flush already conflicts — the CONFLICT itself
    is what dooms the group, so no separate explicit-rollback trigger exists
    here; a genuinely non-conflict-driven interleaved abort is unwitnessed
    and out of scope (pinned semantics #10, "unwitnessed surfaces stay
    honest"). The turnstile only ADVANCES past the group's own last step once
    ``session.database.transact`` itself RETURNS (a REAL commit — the underlying
    port's transaction context manager has committed, not merely that this
    callback's own Python code finished): the OTHER group's next step must
    observe that commit for real, never a same-process illusion of one.

    ``session`` is passed beside the shared ``context`` rather than read out of
    it because the two groups run on two connections: each group's steps execute
    on, and lower in the spelling of, the dedicated session opened for it.

    ``context`` carries the SAME single :class:`TemporalShadow` every group
    shares (`_run_uow_group`'s own convention) — safe here ONLY because every
    model this lane witnesses is entirely NON-temporal (the
    tracker is never mutated for these instructions, so two threads never
    contend on it, and this group's own abort has nothing to discard). A
    genuinely temporal interleaved case would need its own per-group tracking
    discipline — the contiguous runner's whole-tracker staging cannot serve two
    groups advancing at once — unwitnessed and out of scope.

    Every OWN find step's observed rows land in ``result.rows`` (keyed by
    scenario step index): the caller's own
    oracle for that step's authored ``expectRows`` — without this, a grouped
    find's own DML is graded but its OBSERVATION never is, so a broken abort
    that left a doomed group's writes durable, or a group opened at the wrong
    Isolation Level, would report well-formed SQL and still pass. Keeping them
    is the one thing this runner does with a step's
    result that the contiguous runner does not.
    """
    lowered: dict[int, LoweredStep] = {}
    state = GroupState()

    def body(tx: handle.Transaction) -> None:
        for position, index in enumerate(indices):
            turnstile.wait_for(index)
            is_last = position == len(indices) - 1
            lowered[index], read = run_group_step(
                tx, session, context, state, steps[index], index, INERT_CLOCK_INSTANT, observation
            )
            if read is not None:
                result.rows[index] = graph_rows(
                    context.model, step_query(steps[index], context.model), read.roots
                )
            if not is_last:
                turnstile.advance()

    committed = False
    try:
        transact(
            session.database, body, concurrency=context.concurrency, isolation=context.isolation
        )
        committed = True
    except OptimisticLockConflictError as exc:
        result.conflict_actual = exc.actual
    except BaseException as exc:  # re-raised on the main thread below
        result.failure = exc
        turnstile.release_all()  # never leave a partner thread hanging on this thread's own defect
    result.lowered = lowered
    result.round_trips = observation.round_trips
    if committed:
        turnstile.advance()


def _refuse_untrusted_terminations(
    executions: Mapping[str, InterleavedExecution], case_name: str
) -> None:
    """Refuse the choreography unless every execution grants termination trust.

    The lane's post-termination join is deliberately unbounded, so a worker it
    cannot unstick hangs there rather than racing the harness. What makes that
    trade sound is a DECLARED contract rather than an inspected shape: a
    structural check — that a session's own close and its transport's are
    callable — passes an implementation whose every rung raises, and that
    implementation hangs the same join anyway. So the refusal happens BEFORE
    either worker thread is constructed, naming EVERY execution that failed to
    declare it rather than stopping at the first, and nothing here calls into an
    execution at all.

    Past this gate, a hang at that join can only mean a grant was untruthful — a
    defect in the declaring type, diagnosable at that exact line.
    """
    defects = [
        f"{label} declares no trusted termination contract "
        f"(`termination_ladder_trusted`), so nothing promises the termination "
        f"ladder can unblock its own I/O"
        for label, execution in executions.items()
        if execution.termination_ladder_trusted is not True
    ]
    if not defects:
        return
    raise EngineError(
        f"{case_name}: the interleaved-group choreography refuses to start — {'; '.join(defects)}"
    )


def run_interleaved_scenario_case(
    case: case_format.Case,
    port: CaseDatabase,
    execution_factory: InterleavedExecutionFactory,
) -> tuple[list[Emission], int, int | None, list[list[Mapping[str, object]]]]:
    """Run a two-group interleaved-`uow`-group scenario — the optimistic-lock
    race (`m-opt-lock-012`) and the Isolation Level scenarios alike, whose ONE
    admission guard is on ORACLE SHAPE (a step stating `expectGraph` is REFUSED
    here: this entry point carries no `stepGraphs` channel, so that oracle would
    go unasserted — read oracles are row-valued only, and a write step, stating
    no oracle of its own, is asked for nothing):
    each
    declared group on a DEDICATED session of its own (``execution_factory`` —
    this function constructs no connection itself), each a REAL ``db.transact``
    (production routing) whose steps lower in the dialect its OWN connection
    declares, steps sequenced across the two in AUTHORED order
    (:class:`Turnstile`). Neither group runs on the caller's ``port``: a stuck
    worker is unstuck by destroying the session it is parked in, and what this
    lane may destroy is only a session it opened for this one choreography. The
    caller's ``port`` therefore serves the case's out-of-band `given.apply`
    statements and any ungrouped step (each witnessed case's own trailing verify
    find), which runs AFTER both groups have resolved.

    Reports the ordered emissions, total round trips, and — when a group's
    own last write step conflicted — the conflict's ``actual`` affected-row
    count (`then.affectedRows`, the scenario shape's own EXTRA top-level
    assertion only the optimistic-lock race authors; ``None`` when no group
    conflicted), and
    EVERY find step's own observed rows (grouped or ungrouped, in scenario
    step order): the caller's own oracle for
    every authored `expectRows`, the SAME observable the ordinary scenario
    run lane grades for every OTHER find step. Routed to explicitly by the
    run sweep (`test_run_sweep.py`) rather than through `run_scenario_case`/
    `adapter.run_case` — this shape's own peer requirement has no seat in the
    ordinary shape-dispatched entry points, the SAME reasoning the rounds
    runner's own dispatch follows.

    Before either worker thread starts, every execution must DECLARE a trusted
    deterministic-termination contract (:func:`_refuse_untrusted_terminations`):
    an execution that declares none is refused loudly here, rather than
    surfacing only much later as an indefinite hang at
    :func:`~parallax.conformance._lanes.turnstile.await_workers`'s own
    unbounded post-ladder join.
    """
    steps = case_document.scenario_steps(case)
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    concurrency = case_document.concurrency(case)
    if any("expectGraph" in step for step in steps):
        raise EngineError(
            f"{case.path.name}: this entry point reports emissions, round trips and find "
            "rows, and carries no `stepGraphs` channel — a step stating relationship "
            "contents is an oracle nothing here would answer, so it is refused rather "
            "than silently unasserted"
        )
    groups = scenario_group_step_indices(steps)
    if len(groups) != 2:
        raise EngineError(  # pragma: no cover - defensive: every case reaching this entry has two
            f"{case.path.name}: run_interleaved_scenario_case supports exactly the "
            f"TWO-group interleaved shape, not {len(groups)} uow groups"
        )
    ungrouped = [i for i in range(len(steps)) if i not in {j for js in groups.values() for j in js}]
    (label_a, indices_a), (label_b, indices_b) = groups.items()
    shadow = TemporalShadow()
    seed_shadow_from_fixtures(case, model, shadow)
    apply_given_apply(case, port, shadow)
    instant = normalize_instant(dt.datetime.fromisoformat(INERT_CLOCK_INSTANT))
    # This lane reports no lifecycle oracle, and could not: two connections
    # driven at once have no single root order to state. The run is here so the
    # trailing ungrouped verify find has one to open its own Handle through.
    lifecycle = LifecycleRun()
    observed_a = lifecycle.observation()
    observed_b = lifecycle.observation()
    context = CaseContext(serving, model, concurrency, shadow, case_format.uow_isolation(case))
    turnstile = Turnstile()
    result_a = _InterleavedGroupResult(lowered={})
    result_b = _InterleavedGroupResult(lowered={})
    # Incremental protection: each execution is registered for release the
    # moment it opens, so a second-session failure — or the trust refusal below
    # — releases the first rather than leaking it, and the ordinary exit
    # releases both whatever the choreography did.
    plans = (
        (f"uow-{label_a}", observed_a, indices_a, result_a),
        (f"uow-{label_b}", observed_b, indices_b, result_b),
    )
    with contextlib.ExitStack() as stack:
        executions: dict[str, InterleavedExecution] = {}
        for name, observed, _indices, _result in plans:
            execution = execution_factory(
                serving, clock=FixedClock(instant), lifecycle_provider=observed.provider
            )
            stack.callback(execution.close)
            executions[name] = execution
        _refuse_untrusted_terminations(executions, case.path.name)
        workers = {
            name: (
                threading.Thread(
                    target=_run_interleaved_group,
                    args=(executions[name], observed, context, steps, indices, turnstile, result),
                    name=name,
                ),
                executions[name],
            )
            for name, observed, indices, result in plans
        }
        for thread, _execution in workers.values():
            thread.start()
        await_workers(workers, turnstile, case.path.name)
    for result in (result_a, result_b):
        if result.failure is not None:
            raise result.failure
    # Each group's writes reach the wire in its own boundary flush — a
    # conflicting flush included, whose gated statement reached the database and
    # reported zero rows — so a group's own steps are reconciled against its own
    # connection's delivery. Reconciled on this thread rather than inside the
    # worker, so a disagreement surfaces where every other failure of this lane
    # does.
    for result, observed in ((result_a, observed_a), (result_b, observed_b)):
        envelope.delivered(
            [
                statement
                for step in result.lowered.values()
                if step.is_write
                for statement in step.statements
            ],
            observed.writes,
            "an interleaved `uow` group",
        )

    lowered: dict[int, LoweredStep] = {**result_a.lowered, **result_b.lowered}
    rows_by_index: dict[int, list[Mapping[str, object]]] = {**result_a.rows, **result_b.rows}
    # Each group's own transaction counted its own calls; the trailing ungrouped
    # verify finds add theirs below.
    round_trips = sum(result.round_trips for result in (result_a, result_b))
    for index in ungrouped:
        step = steps[index]
        if "write" in step:  # pragma: no cover - no witnessed ungrouped write is doomed-adjacent
            raise EngineError(
                f"{case.path.name}: an ungrouped write step ({index}) beside an "
                "interleaved uow race is unsupported — every witnessed case's own "
                "ungrouped step is a trailing verify find only"
            )
        read, read_observed = run_standalone_find(port, context, step, lifecycle)
        rows_by_index[index] = graph_rows(model, step_query(step, model), read.checked().results())
        round_trips += read_observed.round_trips
        lowered[index] = LoweredStep(
            f"/scenario/{index}/objectQuery", read_observed.reads, False, False
        )

    ordered = [lowered[index] for index in sorted(lowered)]
    emissions = envelope.emissions([(step.pointer, step.statements) for step in ordered])
    conflict_actual = result_a.conflict_actual
    if conflict_actual is None:
        conflict_actual = result_b.conflict_actual
    find_rows = [rows_by_index[index] for index in sorted(rows_by_index)]
    return emissions, round_trips, conflict_actual, find_rows


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
    steps = case_document.scenario_steps(case)
    lifecycle = lifecycle_run(lifecycle)
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
    context = CaseContext(serving, model, concurrency, shadow, case_format.uow_isolation(case))
    lowered: list[LoweredStep] = []
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
    return ScenarioRun(emissions, round_trips, [], rows_observed, step_graphs)


def run_write_sequence_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], dict[str, list[Row]], int]:
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
    context = CaseContext(
        serving,
        model,
        case_document.concurrency(case),
        TemporalShadow(),
        case_format.uow_isolation(case),
    )
    group_observations: GroupObservations = []
    lowered: list[tuple[str, tuple[LoweredStatement, ...]]] = []
    round_trips = 0
    try:
        seed_shadow_from_fixtures(case, model, context.shadow)
        apply_given_apply(case, port, context.shadow)
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


def read_table_state(port: DatabaseConnection, model: AcceptedMetamodel) -> dict[str, list[Row]]:
    """The committed contents of every model table, in canonical wire form.

    Every compiled Table Layout is read back exactly once, projecting its
    complete slot sequence in canonical order, so the observation reports the
    whole physical row ``then.tableState`` asserts — including a slot that only
    a sibling table-per-hierarchy variant fills (e.g. `m-inheritance-007`'s
    inserted `CardPayment` row still reports the cash-only `tendered` column as
    `null`).
    """
    dialect = port.dialect
    state: dict[str, list[Row]] = {}
    for layout in storage_layout.view(model).tables:
        columns = ", ".join(dialect.quote(slot.column.name) for slot in layout.columns)
        sql = f"select {columns} from {dialect.quote(layout.table.name)}"
        rows = port.execute(dialect.to_driver_sql(sql), [])
        projection = ActualWireProjection(model)
        state[layout.table.name] = [projection.table_row(layout, row) for row in rows]
    return state


# --------------------------------------------------------------------------- #
# Conflict — the write-effect run lane (m-opt-lock / m-unit-work).             #
# Single-attempt (`when.write`) and retry                                      #
# (`when.attempts`) forms both drive ONE `db.transact` call per attempt.       #
# A non-temporal attempt (a keyed UPDATE or DELETE over one row or the         #
# multi-key array) is stated through `tx.wire.update` / `tx.wire.delete`       #
# exactly like any other keyed write; a TEMPORAL attempt (`m-txtime-write` /   #
# `m-bitemp-write`) composes `handle.plan_temporal_close` directly — a         #
# conflict case tests ONLY the close, under an address and a gate the case     #
# names EXPLICITLY rather than derives from an observation.                    #
# --------------------------------------------------------------------------- #
def _conflict_target(case: case_format.Case, model: AcceptedMetamodel) -> str:
    """The entity a conflict case's write targets, when ``when.write`` carries no
    explicit reference (`m-case-format`: a conflict case's write names no
    entity of its own). For a plain model this is its SOLE entity — the same
    convention :func:`_rejected_target` uses. For an inheritance family
    (`m-inheritance-105`'s TPH composed conflict) writes are concrete-subtype
    only (`m-inheritance` "Concrete-subtype writes"), never the abstract root
    :func:`_rejected_target` resolves to for the REJECTED lane's DIFFERENT
    default-target convention — this resolves to the family's SOLE concrete
    subtype (every reachable temporal-inheritance conflict model declares
    exactly one).

    Reported by CANONICAL spelling, like every default this lane resolves: the
    subtype is selected by Identity here, so reducing it to a bare local name
    would hand a resolved selection back to the ambiguity rule that adjudicates
    an authored reference."""
    root = default_family_root(model)
    if root is None:
        return first_declared_entity(case)
    view = inheritance.view(model).entity(root.identity)
    concretes = sorted(
        identity.canonical for identity in (() if view is None else view.concrete_subtypes)
    )
    if len(concretes) != 1:
        raise EngineError(  # pragma: no cover - no witnessed conflict model is ambiguous
            f"a conflict case's model declares {len(concretes)} concrete subtypes "
            f"{concretes!r}; the target is ambiguous without an explicit reference"
        )
    return concretes[0]


def _conflict_mutation(when: Mapping[str, object]) -> Literal["update", "delete"]:
    """A NON-TEMPORAL conflict case's written verb (`m-case-format`
    ``when.mutation``), defaulting to ``update``. A temporal target ignores it:
    its conflict write is always the milestone close."""
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
    Strategy decides uniformly; a
    temporal close's own conflict form (`handle.plan_temporal_close`) is a
    distinct shape.

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
    composition layer uses (`parallax.snapshot.handle.Database.transact`) and
    lower every survivor, so a MULTI-KEY attempt reports the ONE set-based
    statement its real execution emits rather than the per-row statements an
    uncollapsed plan would have rendered.
    """
    instant = _pinned_instant(INERT_CLOCK_INSTANT)
    plan = (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                subject_identity=_PLANNING_SUBJECT,
                transaction_instant=instant,
                concurrency=concurrency,
                buffered_writes=[
                    _buffered(write.instruction, write.observation, model) for write in resolved
                ],
            )
        )
        .plan
    )
    return tuple(statement for _step, statement in stream_lowered(plan, model, dialect))


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
    DELETE, or a temporal close — classifies by its gate, which the target's own
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


def _conflict_attempt_affected(
    database: handle.Database,
    concurrency: Concurrency,
    implied: type[WriteEffectError],
    body: Callable[[handle.Transaction], int],
) -> int:
    """One conflict attempt's affected-row observation: what ``body`` reports when
    the write lands, or the ``actual`` count carried by the ONE Write Effect Error
    the case's own declared facts admit.

    Both conflict lanes — the non-temporal keyed write and the temporal close —
    make this exact guard, so it lives here once rather than beside each ``body``.
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
        return transact(database, body, concurrency=concurrency)
    except WriteEffectError as exc:
        admitted = CardinalityCorruptionError if exc.actual > exc.expected else implied
        if type(exc) is not admitted:
            raise
        return exc.actual


def _admitted_affected(implied: type[WriteEffectError], run: Callable[[], int]) -> int:
    """``run``'s own affected-row count, or the ``actual`` the ONE admitted Write
    Effect Error carries — :func:`_conflict_attempt_affected`'s guard, for the
    close lane, which opens no ``db.transact`` at all."""
    try:
        return run()
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
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as database:
        nodes: dict[ObjectKey, handle.WireEntity] = {}
        with observed.resolving_reads():
            snapshot = database.wire.find(
                {"target": target, "predicate": _conflict_key_predicate(model, target, resolved)}
            )
            for root in snapshot.results():
                hint = source_hint_of(root)
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
    hint = source_hint_of(node)
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
    target: str,
    concurrency: Concurrency,
    write_rows: Sequence[Mapping[str, object]],
    mutation: Literal["update", "delete"],
    nodes: Mapping[ObjectKey, handle.WireEntity],
    lifecycle: LifecycleRun,
) -> tuple[tuple[LoweredStatement, ...], int, int]:
    """Lower and execute one NON-TEMPORAL conflict attempt's write through
    ``db.transact`` — ONE
    transaction, an inert Clock (never consumed by a non-temporal write).

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
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as database:
        landed = _landed_conflict_rows(resolved)
        sources = [_conflict_source_node(target, write, nodes) for write in resolved]
        for write, node in zip(resolved, sources, strict=True):
            _refuse_unobserved_conflict_version(target, write, node)

        def body(tx: handle.Transaction) -> int:
            for write, node in zip(resolved, sources, strict=True):
                if mutation == "delete":
                    assert isinstance(write.instruction, PreparedKeyedWrite)
                    buffer_prepared_wire_keyed_write(tx, write.instruction, node, frozenset())
                else:
                    assert isinstance(write.instruction, PreparedKeyedWrite)
                    buffer_prepared_wire_keyed_write(
                        tx,
                        write.instruction,
                        node,
                        frozenset(_conflict_changes(write)),
                    )
            return landed  # the expectation machinery already verified this on success

        observation_requiring = _versioned_non_temporal_version_attribute(model, target) is not None
        implied = _implied_shortfall_error(observation_requiring, concurrency, model, target)
        affected = _conflict_attempt_affected(database, concurrency, implied, body)
        ran = envelope.delivered(statements, observed.writes, "a conflict attempt")
        return ran, affected, observed.round_trips


def _conflict_changes(write: _ConflictWrite) -> dict[str, object]:
    """One conflict attempt row's authored assignments — its durable row less the
    identity the source node already carries, in authored order.

    Order is what the golden's SET clause is rendered in, so it is the case's own
    rather than the model's declaration order.
    """
    identity = dict(write.key.primary_key) if write.key is not None else {}
    return {name: value for name, value in write.row.items() if name not in identity}


# A temporal conflict attempt's verb. The case names none (`when.mutation` is
# the NON-temporal lane's keyed UPDATE/DELETE) because a temporal target's
# conflict write is always the milestone close — so the close names itself, for
# the row diagnostics that report which write refused an authored key.
_CLOSE_MUTATION: Final[str] = "close"


def _run_conflict_close(
    port: DatabaseConnection,
    model: AcceptedMetamodel,
    target: str,
    concurrency: Concurrency,
    write_row: Mapping[str, object],
    at: str,
    observed_tx_start: str | None,
    observed_valid_start: str | None,
    shadow: TemporalShadow,
) -> tuple[tuple[LoweredStatement, ...], int, int]:
    """Lower and execute one TEMPORAL conflict attempt's close — ONE
    transaction opened on the port itself, ``clock=FixedClock(at)``. Composes the SAME two halves
    production does — :func:`~parallax.snapshot.handle.plan_temporal_close`
    settles the step, :func:`~parallax.core.sql_gen._write.compile_write_step` renders it —
    for a conflict case's own close-only probe, never a REAL chaining mutation,
    and executes it on the port's own transaction; a standalone close has
    nothing to coalesce or FK-order with, so it bypasses the buffer/flush
    pipeline entirely.

    A case names its close's coordinates one of two ways, and never both:

    * the ADDRESS directly — the write row's own ``validEnd`` completes a
      bitemporal close's address and ``observed_tx_start`` supplies its gate
      candidate, both the case's EXPLICIT authored fields
      (`when.write.validEnd` / `when.observedTxStart`). This is how a case tests
      a KNOWN stale-or-fresh gate, whose whole point is that it matches no
      milestone;
    * the OBSERVED MILESTONE — ``observed_valid_start`` with
      ``observed_tx_start`` is that milestone's own edge coordinate
      (`when.observedValidStart` / `when.observedTxStart`), which resolves
      against the case's tracked state and supplies BOTH the address's
      Valid-Time end and the gate from the ONE milestone it names. A key holding
      several disjoint current rectangles is then addressable, and the address
      and the gate provably come from one observation rather than from two
      independently authored coordinates.

    Its ``write_row`` is a case-authored row like any other, so it becomes a
    durable row through :func:`_durable_row`, which entitles a temporal row to no
    observation control key: the coordinates this close binds are the SEPARATE
    arguments, and a row that spelled its own would otherwise be projected away
    to the address's primary-key cells and the author's coordinate silently
    replaced by the one beside the write.

    A zero-row close is caught only as the class the case's own mode implies
    (:func:`_implied_shortfall_error`); every other class propagates, so the
    ``affectedRows`` observation can never absorb a misclassified failure.
    """
    row, _authored_none = _durable_row(model, target, _CLOSE_MUTATION, write_row)
    authored_valid_end = row.pop("validEnd", None)
    inputs = _conflict_close_inputs(
        model,
        target,
        row,
        at,
        observed_tx_start,
        observed_valid_start,
        authored_valid_end,
    )
    observed_valid_end = inputs.authored_valid_end
    managed_observed_tx_start = inputs.observed_tx_start
    if inputs.observed_valid_start is not None:
        observed_valid_end, managed_observed_tx_start = _observed_milestone_coordinates(
            model,
            target,
            dict(inputs.identity),
            observed_valid_end,
            inputs.observed_valid_start,
            managed_observed_tx_start,
            shadow,
        )
        metadata = _conflict_close_metadata(model, target)
        observed_valid_end = _decode_observed_conflict_bound(
            metadata.valid_end, observed_valid_end, position="observed valid end"
        )
        managed_observed_tx_start = _decode_conflict_optional_instant(
            metadata.tx_start,
            managed_observed_tx_start,
            position="observed transaction start",
        )
    # The standalone close is settled outside any unit of work, so it is handed
    # its own Transaction Instant over the SAME clock the transaction below runs
    # on — the two can never derive different instants from one `at`.
    clock = FixedClock(inputs.instant)
    step = handle.plan_temporal_close(
        dict(inputs.identity),
        target,
        model,
        concurrency,
        TransactionInstant(clock),
        managed_observed_tx_start,
        observed_valid_end,
    )
    statement = compile_write_step(step, model, port.dialect)

    # A standalone close is no keyed mutation and no unit of work buffers it, so
    # it runs on the port's own transaction — public `m-db-port`, the same
    # boundary ``db.transact`` opens. That opens no Handle, so nothing observes
    # this statement: it is exactly one, and its round trip is stated rather than
    # read off a lifecycle, the same account `run_error_case` gives for authored
    # trigger DML.
    #
    # A Bitemporal close is unreachable through a keyed verb: every
    # closure-bearing entry in `bitemp_write._TOPOLOGIES` chains at least the
    # head rectangle, and the goldens author the close alone. A
    # Transaction-Time-Only `terminate` does close without chaining
    # (`txtime_write.MILESTONE_CHAIN.topology`), but it derives its address and
    # gate from the milestone its observation names, while a conflict case
    # authors both directly — including the deliberately stale gate whose whole
    # point is that it matches no milestone.
    def run_close(conn: DatabaseConnection) -> int:
        affected = conn.execute_write(
            conn.dialect.to_driver_sql(statement.sql), list(statement.binds)
        )
        # The SAME authoritative interpreter `parallax.snapshot.handle`'s own
        # flush executor asks, so the two callers can never disagree on what a
        # count means.
        enforce_affected_rows(step, affected)
        return affected

    implied = _implied_shortfall_error(True, concurrency, model, target)
    affected = _admitted_affected(implied, lambda: committed(port.transaction(run_close)))
    return (statement,), affected, 1


@dataclass(frozen=True, slots=True)
class _ConflictCloseMetadata:
    primary_key: tuple[AttributeMetadata, ...]
    tx_start: AttributeMetadata
    valid_start: AttributeMetadata | None
    valid_end: AttributeMetadata | None


@dataclass(frozen=True, slots=True)
class _ConflictCloseInputs:
    """Managed inputs for compatibility's standalone temporal-close probe."""

    identity: tuple[tuple[str, ManagedValue], ...]
    instant: dt.datetime
    observed_tx_start: dt.datetime | None
    observed_valid_start: dt.datetime | None
    authored_valid_end: dt.datetime | TemporalBound | None


def _conflict_close_inputs(
    model: AcceptedMetamodel,
    target: str,
    row: Mapping[str, object],
    at: object,
    observed_tx_start: object | None,
    observed_valid_start: object | None,
    authored_valid_end: object | None,
) -> _ConflictCloseInputs:
    metadata = _conflict_close_metadata(model, target)
    primary_key_names = tuple(attribute.identity.name for attribute in metadata.primary_key)
    if set(row) != set(primary_key_names):
        raise EngineError(
            f"{target!r}: a standalone temporal close must carry exactly its primary-key "
            f"members; expected {list(primary_key_names)!r}, got {list(row)!r}"
        )
    return _ConflictCloseInputs(
        identity=tuple(
            (
                attribute.identity.name,
                _decode_conflict_literal(
                    attribute,
                    row[attribute.identity.name],
                    position=f"primary key `{attribute.identity.name}`",
                ),
            )
            for attribute in metadata.primary_key
        ),
        instant=_decode_conflict_instant(metadata.tx_start, at, position="at"),
        observed_tx_start=_decode_conflict_optional_instant(
            metadata.tx_start,
            observed_tx_start,
            position="observedTxStart",
        ),
        observed_valid_start=_decode_conflict_optional_instant(
            metadata.valid_start,
            observed_valid_start,
            position="observedValidStart",
        ),
        authored_valid_end=_decode_conflict_bound(
            metadata.valid_end,
            authored_valid_end,
            position="validEnd",
        ),
    )


def _conflict_close_metadata(model: AcceptedMetamodel, target: str) -> _ConflictCloseMetadata:
    entity = case_entity(model, target)
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - every accepted Entity has a facet position
        raise EngineError(f"{entity.identity.canonical}: target is absent from inheritance view")
    primary_key = tuple(
        attribute
        for attribute in position.applicable_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )
    declarer = family_declarer(model, entity)
    tx_start, _tx_end = _axis_attributes(declarer, TemporalDimension.TRANSACTION_TIME)
    valid_axis = (
        _axis_attributes(declarer, TemporalDimension.VALID_TIME)
        if declarer.as_of_axis(TemporalDimension.VALID_TIME) is not None
        else None
    )
    return _ConflictCloseMetadata(
        primary_key,
        tx_start,
        None if valid_axis is None else valid_axis[0],
        None if valid_axis is None else valid_axis[1],
    )


def _axis_attributes(
    declarer: EntityMetadata,
    dimension: TemporalDimension,
) -> tuple[AttributeMetadata, AttributeMetadata]:
    axis = declarer.as_of_axis(dimension)
    if axis is None:  # pragma: no cover - the caller establishes the accepted temporal shape
        raise EngineError(
            f"{declarer.identity.canonical}: temporal close has no {dimension.value} axis"
        )
    start = declarer.attribute(axis.start_attribute.name)
    end = declarer.attribute(axis.end_attribute.name)
    if start is None or end is None:  # pragma: no cover - accepted axes resolve both endpoints
        raise EngineError(
            f"{declarer.identity.canonical}: {dimension.value} axis endpoints are unresolved"
        )
    return start, end


def _decode_conflict_optional_instant(
    attribute: AttributeMetadata | None,
    value: object | None,
    *,
    position: str,
) -> dt.datetime | None:
    if value is None:
        return None
    if attribute is None:
        raise EngineError(f"a temporal close {position} names an axis the target does not declare")
    return _decode_conflict_instant(attribute, value, position=position)


def _decode_conflict_bound(
    attribute: AttributeMetadata | None,
    value: object | None,
    *,
    position: str,
) -> dt.datetime | TemporalBound | None:
    if value is None:
        return None
    if isinstance(value, str) and str.__str__(value) == INFINITY_LITERAL:
        if attribute is None:
            raise EngineError(
                f"a temporal close {position} names an axis the target does not declare"
            )
        return TemporalBound.INFINITY
    if attribute is None:
        raise EngineError(f"a temporal close {position} names an axis the target does not declare")
    return _decode_conflict_instant(attribute, value, position=position)


def _decode_observed_conflict_bound(
    attribute: AttributeMetadata | None,
    value: object | None,
    *,
    position: str,
) -> dt.datetime | TemporalBound | None:
    if isinstance(value, TemporalBound):
        return value
    return _decode_conflict_bound(attribute, value, position=position)


def _decode_conflict_instant(
    attribute: AttributeMetadata,
    value: object,
    *,
    position: str,
) -> dt.datetime:
    normalized = value
    if isinstance(value, str):
        try:
            candidate = dt.datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if matches_neutral_type(candidate, TIMESTAMP):
                normalized = encode_wire(TIMESTAMP, candidate)
    elif isinstance(value, dt.datetime) and matches_neutral_type(value, TIMESTAMP):
        normalized = encode_wire(TIMESTAMP, value)
    decoded = _decode_conflict_literal(attribute, normalized, position=position)
    if not isinstance(decoded, dt.datetime):  # pragma: no cover - accepted axes are Timestamp
        raise EngineError(
            f"{attribute.identity.entity.canonical}.{attribute.identity.name}: "
            f"temporal close {position} did not decode to an instant"
        )
    return decoded


def _decode_conflict_literal(
    attribute: AttributeMetadata,
    value: object,
    *,
    position: str,
) -> ManagedValue:
    try:
        return decode_wire(attribute.type, cast("WireValue", value))
    except WireDecodingError as exc:
        raise EngineError(
            f"{attribute.identity.entity.canonical}.{attribute.identity.name}: "
            f"temporal close {position} is "
            f"neutral-literal-{exc.reason}: {exc}"
        ) from exc


def _observed_milestone_coordinates(
    model: AcceptedMetamodel,
    target: str,
    row: Mapping[str, object],
    authored_valid_end: dt.datetime | TemporalBound | None,
    observed_valid_start: dt.datetime,
    observed_tx_start: dt.datetime | None,
    shadow: TemporalShadow,
) -> tuple[object | None, object]:
    """The close coordinates the ONE milestone a case named the edge of supplies:
    that milestone's own Valid-Time end (the address's exclusive upper bound) and
    its own Transaction-Time start (the gate candidate).

    Both come from one resolved observation, so an implementation that resolved
    the observation by primary key alone — picking whichever of a key's current
    rectangles it happened to hold — cannot render the address this returns.
    That is the whole reason a case names an edge instead of an address.

    An authored ``validEnd`` alongside is refused rather than cross-checked: the
    two spellings answer the same question, and a case that agrees with itself
    proves nothing the derivation does not already, while a case that disagrees
    would have to pick a winner.
    """
    if authored_valid_end is not None:
        raise EngineError(
            f"{target!r} {_CLOSE_MUTATION!r}: a close names its observed milestone's edge "
            "(`observedValidStart`) or its address (`write.validEnd`), never both — the "
            "address of an edge-named close is DERIVED from the milestone the edge selects"
        )
    entity_metadata = case_entity(model, target)
    edge = temporal_state.observed_edge(
        model, entity_metadata, valid_start=observed_valid_start, tx_start=observed_tx_start
    )
    observation = shadow.resolve(model, entity_metadata, row, edge)
    if observation is None:
        raise EngineError(
            f"{target!r} {_CLOSE_MUTATION!r}: no current milestone of this key carries the "
            f"observed edge {edge!r} — a close observes a milestone the case's own state holds"
        )
    valid_end, tx_start = temporal_state.observed_close_coordinates(
        model, entity_metadata, observation
    )
    return valid_end, tx_start


def _conflict_write_rows(attempt: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """One conflict attempt's authored ``write`` as the ordered row sequence both
    forms denote: a lone object is the one-element case of the multi-key array
    (`m-case-format`), so the single seam here spares every lane downstream from
    knowing which spelling the case chose."""
    raw = attempt["write"]
    if isinstance(raw, list):
        return tuple(cast("list[Mapping[str, object]]", raw))
    return (cast("Mapping[str, object]", raw),)


def _conflict_close_row(
    case: case_format.Case, attempt: Mapping[str, object]
) -> Mapping[str, object]:
    """The ONE milestone row a temporal conflict attempt closes.

    The multi-key ``write`` array is a keyed, NON-temporal form — a temporal
    target's write expands into a close plus its successors per key and never
    collapses into one set-based statement — so an array reaching a close is
    refused rather than silently reduced to a row the case did not single out.
    """
    raw = attempt["write"]
    if isinstance(raw, list):
        raise EngineError(
            f"{case.path.name}: a temporal conflict attempt closes one milestone row, and "
            "the multi-key `write` array form is keyed and non-temporal"
        )
    return cast("Mapping[str, object]", raw)


# The observed milestone's own edge, authored beside a temporal conflict write.
_MILESTONE_EDGE_KEYS: Final[frozenset[str]] = frozenset({"observedTxStart", "observedValidStart"})


def _refuse_unentitled_observed_edge(
    case: case_format.Case, when: Mapping[str, object], *, is_temporal: bool
) -> None:
    """Refuse an observation coordinate the conflict target, mode, or attempt
    form cannot consume.

    Four entitlements, all decided here because all are properties of the CASE
    rather than of any one attempt's arithmetic (`m-case-format`, *Naming the
    observed milestone*):

    * a NON-temporal target has no milestones and no edge to name one with, so
      the coordinates would be read by nothing — the versioned conflict path
      never looks at them. That holds wherever they are spelled, so the root
      ``when`` and every attempt are checked alike;
    * a RETRY attempt re-reads state the concurrent writer left behind, while an
      edge selects among the milestones the case's own loaded fixtures hold. The
      two cannot be reconciled without a resolving read no lane performs, so the
      OBSERVATION form is single-attempt only and a retry names its address
      directly;
    * a retry sequence reads each attempt's own coordinates and never the root
      ``when``'s, so a root coordinate beside ``attempts`` is consumed by nothing.
      The two authoring locations are alternatives, not a default and an
      override;
    * ``observedTxStart`` standing ALONE is the address form's gate candidate,
      and a close under the Locking strategy renders no gate, so it is entitled
      only where the preference resolves to ``optimistic`` — which a temporal
      target's Transaction-Time-derived key then carries into the Optimistic
      strategy. Beside ``observedValidStart`` it is instead the edge's
      Transaction-Time half, which selects the milestone under either strategy.
      The preference defaults to ``optimistic``, so only an explicitly
      ``locking`` case is refused.

    The Transaction-Time-Only arm of the first entitlement lives where the edge
    is built (:func:`temporal_state.observed_edge`), which refuses a coordinate
    on an axis the target does not declare.
    """
    raw_attempts = when.get("attempts")
    attempts = (
        cast("list[Mapping[str, object]]", raw_attempts) if isinstance(raw_attempts, list) else []
    )
    if not is_temporal:
        for pointer, source in [
            ("`when`", when),
            *((f"attempt {index}", attempt) for index, attempt in enumerate(attempts)),
        ]:
            if any(key in source for key in _MILESTONE_EDGE_KEYS):
                raise EngineError(
                    f"{case.path.name}: a NON-temporal conflict target has no milestone to "
                    f"observe, so it may author neither of {sorted(_MILESTONE_EDGE_KEYS)} "
                    f"({pointer})"
                )
    for index, attempt in enumerate(attempts):
        if "observedValidStart" in attempt:
            raise EngineError(
                f"{case.path.name}: attempt {index} names its observed milestone's edge "
                "(`observedValidStart`), which selects among the case's own fixtures — a "
                "retry re-reads what the concurrent writer left, so a retry attempt names "
                "its address (`write.validEnd`) directly"
            )
    if raw_attempts is not None:
        for key in sorted(_MILESTONE_EDGE_KEYS):
            if key in when:
                raise EngineError(
                    f"{case.path.name}: the root `when` authors {key!r} beside `attempts` — "
                    "a retry sequence reads each attempt's own coordinates, so a root one is "
                    "consumed by no attempt"
                )
    if case_document.concurrency(case) == "optimistic":
        return
    for pointer, source in [
        ("`when`", when),
        *((f"attempt {index}", attempt) for index, attempt in enumerate(attempts)),
    ]:
        if "observedTxStart" in source and "observedValidStart" not in source:
            raise EngineError(
                f"{case.path.name}: `locking` mode renders no gate, so a lone "
                f"`observedTxStart` is consumed by nothing ({pointer}) — it is entitled "
                "under `optimistic`, or beside `observedValidStart` as the observed "
                "milestone's edge"
            )


def run_conflict_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], int, dict[str, list[Row]] | None, int]:
    """Run a `conflict` case (`m-opt-lock` / `m-txtime-write` / `m-bitemp-write`):
    the single-attempt form (`when.write`), or the `when.attempts` retry
    sequence — each attempt its OWN `db.transact` unit,
    in order, each with its own statements /
    affected-row count (the case's own `0`-then-`1` retry-contract witness). A
    NON-temporal target (a keyed UPDATE or DELETE, named by `when.mutation`)
    writes every row of its `write` — one row, or the multi-key array whose
    rows the batching rule may collapse into a single set-based statement —
    through the public keyed Wire verb; a TEMPORAL target composes
    `handle.plan_temporal_close` directly, one milestone row at a time.

    Loads no fixtures itself (the caller's own lifecycle does, per
    `m-case-format`'s conflict-shape default). `given.apply`'s concurrent writer
    commits BETWEEN the FIRST attempt's source read and the write that read
    licenses (:func:`~parallax.conformance._mechanism.given_state.apply_given_apply`),
    which is the ordering a non-temporal
    conflict case describes: the state its write settles against is one a real
    read of this lane observed, and the writer that invalidated it committed
    afterwards. A retry attempt reads again, after the attempt before it ran, so
    it observes the state that writer left. A TEMPORAL attempt needs no source —
    its close settles against a coordinate the case names — so for it the writer
    still commits first.

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
    target = _conflict_target(case, model)
    mutation = _conflict_mutation(when)
    is_temporal = _is_temporal_entity(model, target)
    # The state an edge-named close resolves its observed milestone against — the
    # case's own loaded fixtures, which are exactly the milestones its address
    # can select. Seeded before `given.apply`, whose out-of-band writer is a
    # CONCURRENT transaction this one never observed.
    shadow = TemporalShadow()
    _refuse_unentitled_observed_edge(case, when, is_temporal=is_temporal)
    if is_temporal:
        seed_shadow_from_fixtures(case, model, shadow)
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
                target,
                _resolve_conflict_writes(model, target, mutation, _conflict_write_rows(attempt)),
                lifecycle,
            )
            round_trips += source_trips
            return nodes

        # Taken before the concurrent writer commits, and spent by the first
        # attempt; every later attempt reads again, after the one before it ran.
        sources = None if is_temporal else sources_for(attempts[0][1])
        apply_given_apply(case, port, shadow)
        for pointer, attempt in attempts:
            if is_temporal:
                statements, affected, attempt_trips = _run_conflict_close(
                    port,
                    model,
                    target,
                    concurrency,
                    _conflict_close_row(case, attempt),
                    cast("str", attempt["at"]),
                    cast("str | None", attempt.get("observedTxStart")),
                    cast("str | None", attempt.get("observedValidStart")),
                    shadow,
                )
            else:
                statements, affected, attempt_trips = _run_conflict_write(
                    port,
                    serving,
                    model,
                    target,
                    concurrency,
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
