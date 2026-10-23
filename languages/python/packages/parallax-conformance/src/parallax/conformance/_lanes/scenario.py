from __future__ import annotations

import contextlib
import datetime as dt
import functools
import itertools
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, Literal, Never, cast

from parallax.conformance import (
    _case_ingress,
    case_format,
    models,
    simulated_temporal_store,
)
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._database_control import CaseDatabase
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
    seed_store_from_fixtures,
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
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.simulated_temporal_store import SimulatedTemporalStore
from parallax.core import (
    batch_write,
    inheritance,
    opt_lock,
    read_delivery,
    storage_layout,
    temporal_read,
)
from parallax.core._execution._keyed_writes import validate_source_pin
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    PreparedWrite,
    WriteInstruction,
)
from parallax.core.base import (
    normalize_instant,
)
from parallax.core.db_port import (
    DatabaseAdapter,
    DatabaseConnection,
    MappingRow,
)
from parallax.core.dialect import Dialect
from parallax.core.execution import (
    ServingModel,
    TransactionTimePinReadOnlyError,
    TxnOptions,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeMetadata,
    EntityMetadata,
    Leaf,
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
from parallax.core.temporal_read import TemporalReadError
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    AdmittedWrite,
    CardinalityCorruptionError,
    Concurrency,
    KeyedWriteInstruction,
    MissingTargetError,
    OptimisticLockConflictError,
    ParticipationToken,
    PredicateWriteInstruction,
    ReadEvidence,
    RetainedObservation,
    StaleWriteError,
    SubjectActor,
    TargetWriteInstruction,
    TransactionSettings,
    UnitOfWork,
    WriteEffectError,
    WriteEvidenceError,
    WritePreconditionError,
    buffered_write,
    object_key,
)
from parallax.core.wire import WireValue, decode_wire
from parallax.core.write_plan import (
    ObjectKey,
    ObjectStateKey,
    StateObservation,
    TemporalObservation,
    VersionObservation,
    WritePlanningError,
    object_state_key_from_observation,
)
from parallax.core.write_plan.steps import KeyTarget
from parallax.snapshot import Database, ScopedDatabase, Snapshot, TxnContext, WireEntity
from parallax.snapshot._publication._wire import authoring_of, read_evidence_of

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
    "is_predicate_write_step",
    "lower_writes",
    "read_step_graph",
    "read_table_state",
    "run_conflict_case",
    "run_group_step",
    "run_scenario_case",
    "run_standalone_find",
    "run_write_sequence_case",
    "scenario_group_step_indices",
    "step_affected_rows",
    "step_query",
    "step_rows",
    "write_entries",
]


# A write step is one transaction: its buffered keyed writes are admitted,
# composed, planned, and executed by an ordinary unit of work through the SAME
# ``build_write_planner`` factory production uses (``m-unit-work``). A
# **scenario** is a *sequence* of transactions: a write step commits (or,
# ``rollback: true``, aborts) its coalesced DML, a `uow` group shares one
# transaction across its steps, and a ``find`` reads through the read path. A
# **writeSequence** runs each entry independently — no cross-entry coalescing
# (an insert-then-delete pair across two entries is two Database Calls, not a
# cancellation) — and each entry is its OWN transaction (not "the whole
# sequence in one transaction").
#
# The RUN lane executes
# every write choreography unit — a writeSequence entry, a scenario write step, a
# conflict attempt — through the SHIPPED ``db.transact`` entry point (one
# transaction per unit, ``clock=FixedClock(<entry at>)``, ADR 0010), stated
# through the PUBLIC ``tx.wire`` verb each mutation names against the value the
# unit's own read published (never the typed instance verbs, which this engine's
# case-driven metamodel has no compiled classes for), and reports the DML its
# lifecycle delivered. The COMPILE lane opens no database: each of its
# transactions is a simulated one (:func:`_simulated_unit`), whose unit of work
# executes its steps through conformance support's simulated step execution,
# which records the statements they lower to. Only compile resolves temporal
# observations against a :class:`SimulatedTemporalStore` (`_resolve_entries`).

# The failures the write lanes convert to a neutral :class:`EngineError`, so
# the adapter reports a ``*-failed`` diagnostic rather than leaking a
# lower-layer exception type across the conformance seam.
# `opt_lock.UnobservedVersionError` / `.CallerAuthoredVersionError` are
# m-opt-lock's own forward-error posture;
# `simulated_temporal_store.SimulatedStoreError` is the refusal of a
# composition the simulated rows cannot name. A deferred witness (the
# auto-retry boundary forms) that reaches this engine-local write path without
# a recorded observation must degrade to a reasoned `EngineError`, never an
# uncaught crash of the sweep.
LOWERING_ERRORS: Final[tuple[type[Exception], ...]] = (
    instructions.WriteInstructionError,
    WritePlanningError,
    inheritance.InheritanceError,
    opt_lock.UnobservedVersionError,
    opt_lock.CallerAuthoredVersionError,
    simulated_temporal_store.SimulatedStoreError,
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

# The audit-neutral Subject Actor every simulated unit of work plans as: no
# simulated transaction opens a real Execution Scope, and a unit of work
# requires one regardless (`m-unit-work`) — the harness proves the value is
# never inspected, so any nonempty constant serves every one identically.
_PLANNING_ACTOR: Final[SubjectActor] = SubjectActor("conformance-compile-lane")


def _pinned_clock(tx_instant: str) -> FixedClock:
    """The Clock a simulated transaction runs at: the entry's own ``at``
    through the SAME ``FixedClock`` the run lane hands ``db.transact``, so the
    two lanes capture the identical literal, and a transaction needing no
    Transaction-Time boundary captures nothing at all."""
    return FixedClock(dt.datetime.fromisoformat(tx_instant))


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


# What ONE grouped find step retained, in the order production filed it. A later
# write step of the same group names that step with `on` and settles against the
# record of its OWN key (`m-case-format` "Settling against a grouped find").
RetainedObservations = tuple[RetainedObservation, ...]

# Compile receives no query-result observations; explicit named observations are
# retained only for compile composition tests.
GroupRetainedObservations = list[RetainedObservation]


@dataclass(frozen=True, slots=True)
class _ResolvedWrite:
    """A compile instruction and the observation its simulated unit retains."""

    instruction: PreparedWrite | PreparedTargetWrite
    supplied_observation: StateObservation | None


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
    store: SimulatedTemporalStore,
) -> None:
    """Compile cannot reconstruct unknown document keys from unmodeled setup SQL."""
    if store.has_complete_stored_row(model, entity, row):
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
    closes its own current milestone, settles against its own Temporal
    Observation, and opens its own successors, and a temporal entity never
    collapses into a set-based statement (`m-batch-write`), so several rows under
    one entry denote
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


def _compile_temporal_observation(
    model: AcceptedMetamodel,
    store: SimulatedTemporalStore,
    entity: EntityMetadata,
    key: ObjectKey | None,
    row: Mapping[str, object],
    source: RetainedObservations | None,
) -> TemporalObservation | None:
    if source is None:
        _refuse_unaccounted_document_milestone(model, entity, row, store)
        return store.predecessor_for(model, entity, row)
    observation = _observation_from_source(entity.identity.canonical, key, source)
    assert isinstance(observation, TemporalObservation)
    return observation


def _build_temporal_instruction(
    entry: Mapping[str, object],
    model: AcceptedMetamodel,
    store: SimulatedTemporalStore,
    unit_inserted: set[ObjectKey],
    source: RetainedObservations | None,
) -> _ResolvedWrite:
    """One TEMPORAL writeSequence/scenario entry -> its canonical keyed
    instruction plus the observation its close/chain settles against, which
    :func:`_compile_temporal_observation` answers.

    The corpus and canonical instruction share the same ``validFrom`` / ``until``
    spelling. Bounds are instruction-level fields; temporal row payloads never
    carry authoring aliases. A temporal entry carries exactly ONE row, which
    :func:`_temporal_entry_row` enforces rather than assumes.

    That row reaches the same :func:`_durable_row` seam every other producer's
    does, which entitles a temporal row to no observation control key at all —
    the observation this entry settles against is a whole predecessor
    milestone, never a cell the row carried.

    ``unit_inserted`` is the SAME choreography unit's own running set of
    (entity, pk) pairs a PRIOR entry in this SAME buffer already inserted
    (`m-unit-work` same-transaction coalescing, `m-temporal-write-008` /
    `m-temporal-write-030`): a later entry targeting one of them is a
    same-buffer coalescing candidate whose OWN close/chain arithmetic never
    runs (the planner folds it into the pending insert before finalization
    ever sees it) — its observation is forced to `None`, and the store is never
    asked. What the store ends up holding for the key is the COALESCED row:
    executing the flush stores the surviving Planned Insert's own row, so the
    stored state is the milestone the flush actually writes rather than a
    stand-in for it.
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
        observation = _compile_temporal_observation(
            model, store, entity_metadata, pk_key, row, source
        )
    if is_insert and pk_key is not None:
        unit_inserted.add(pk_key)
    return _ResolvedWrite(prepared, observation)


def _observation_from_source(
    entity_name: str, pk_key: ObjectKey | None, source: RetainedObservations
) -> StateObservation:
    """The observation a write is supplied with when its step named the find it
    came from (`m-case-format` *Settling against a grouped find*).

    The named find's own record for this key is what production retained onto the
    value the write is handed, so the simulated unit of work plans with the state
    the read actually saw rather than a coordinate this engine re-derived and
    hoped agreed. That is what makes a store keyed by identity alone observably wrong
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
    ``KeyError``; this shape routes to the readless predicate-write translation
    instead — see :func:`_lower_predicate_write_step` /
    :func:`_run_readless_predicate_write`.
    """
    return isinstance(raw_write, Mapping)


def write_entries(raw_write: object) -> Sequence[Mapping[str, object]]:
    """A scenario write step's own ``write`` field as its keyed-write entry
    LIST — callers check :func:`is_predicate_write_step` FIRST; this is never
    reached for a structured predicate-write instruction."""
    return cast("Sequence[Mapping[str, object]]", raw_write)


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
    - a TEMPORAL write observes a whole predecessor milestone, never a row cell.
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
    :class:`SimulatedTemporalStore`, or, where the step named the find it settles against,
    by that same group's observations).

    Observation legality and stripping share :func:`_without_observation_controls`
    with unprepared routing, which needs the durable row but no observation.
    """
    durable = _without_observation_controls(model, entity_name, mutation, row)
    version = row.get(_VERSION_OBSERVATION_KEY)
    if version is None:
        return durable, None
    return durable, VersionObservation(observed_version=cast("int", version))


def _without_observation_controls(
    model: AcceptedMetamodel, entity_name: str, mutation: str, row: Mapping[str, object]
) -> dict[str, object]:
    for key in _ROW_OBSERVATION_KEYS:
        if key not in row:
            continue
        refusal = _observation_refusal(model, entity_name, mutation, key)
        if refusal is not None:
            raise EngineError(f"{entity_name!r} {mutation!r}: {refusal}")
    durable = dict(row)
    durable.pop(_VERSION_OBSERVATION_KEY, None)
    return durable


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
    `TxnContext.insert`/`.update`/`.delete` calls would buffer — rather than
    arriving as anonymous rows free to be merged back together.

    This decides OBSERVATION BINDING only, never statement count:
    :func:`_build_instructions` buffers one single-row instruction per row
    regardless, and leaves every merge to the planner's own collapse stage
    (a simulated unit of work's flush, an Attempt's flush execution).
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

    ``emitted_count`` is what the compile lane's simulated flush recorded
    (:func:`lower_writes`), or what the run lane's flush delivered, so the
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
    """Seed the derived version only for compile's prepared insert validation."""
    if mutation != "insert":
        return dict(row)
    version_attr = _versioned_non_temporal_version_attribute(model, entity_name)
    if version_attr is None or version_attr.identity.name in row:
        return dict(row)
    return {**row, version_attr.identity.name: opt_lock.INITIAL_VERSION}


def _build_instructions(
    entry: Mapping[str, object],
    model: AcceptedMetamodel,
    store: SimulatedTemporalStore,
    unit_inserted: set[ObjectKey],
    group_observations: GroupRetainedObservations,
    source: RetainedObservations | None,
) -> list[_ResolvedWrite]:
    """One case write entry -> one or more canonical keyed write instructions.

    A STRUCTURED PREDICATE-write entry (`target`/`predicate` shaped, no
    `entity` key at all) refuses loudly here too — defensive coverage for the
    writeSequence path, which shares this function with every scenario write
    entry (the scenario `write`-field-is-itself-a-mapping shape is caught one
    layer up, by :func:`is_predicate_write_step`, and routed to the readless
    predicate-write translation instead — a predicate
    write is never a legal writeSequence entry shape, `m-case-format`'s
    writeSequence vocabulary is keyed-only).

    A TEMPORAL entity's entry dispatches to :func:`_build_temporal_instruction`,
    settling against compile's explicit observation lookup, and admits exactly ONE row: its
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
    / ``databaseCalls`` / ``rollback``). ``rows`` MAY batch several logical
    per-object writes into one entry (the write-instruction schema's "one or
    more rows" vocabulary), and this seam ALWAYS buffers one single-row
    instruction per row, exactly as that many separate ``TxnContext`` calls
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
    (:func:`_observation_from_source`) where it named one, and otherwise from
    ``group_observations`` — a writeSequence's own permanently-empty sequence, or
    (the scenario RUN lane only) a `uow` GROUP's own prior find step(s), scanned
    from the end. A versioned target holds one ROW per primary key but a unit of
    work may hold several observed GENERATIONS of it, so the unnamed fallback
    answers the latest reading while the reference is what names any other.

    An entry's authored ``statements`` count is graded later, once the buffer
    these instructions join has actually been lowered or delivered
    (:func:`_check_statement_count_consistency`) — nothing here predicts what
    the flush will emit.
    """
    entity_name = _keyed_entry_entity(entry)
    if "row" in entry:
        return [_build_target_instruction(entry, model)]
    if _is_temporal_entity(model, entity_name):
        return [_build_temporal_instruction(entry, model, store, unit_inserted, source)]
    mutation = cast("str", entry["mutation"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    durable = _durable_rows(model, entity_name, mutation, raw_rows)
    binds_observations = _binds_row_observations(model, entity_name, mutation, raw_rows)
    out: list[_ResolvedWrite] = []
    opens_a_row = mutation in INSERT_MUTATIONS
    for clean_row, row_observation in durable:
        observation: StateObservation | None = row_observation
        clean_row = _seed_insert_version(model, entity_name, mutation, clean_row)
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity_name, "rows": [clean_row]}
        )
        assert isinstance(instruction, KeyedWriteInstruction)  # a `rows` document is a keyed write
        prepared = _case_ingress.prepare_case_write(instruction, model)
        if binds_observations and not opens_a_row:
            key = object_key(prepared, model)
            if observation is None and key is not None:
                if source is not None:
                    observation = _observation_from_source(entity_name, key, source)
                else:
                    observed = _observed_for(group_observations, key)
                    if observed is not None:
                        observation = observed.evidence
        else:
            observation = None
        out.append(_ResolvedWrite(prepared, observation))
    return out


def _keyed_entry_entity(entry: Mapping[str, object]) -> str:
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
    return cast("str", entry["entity"])


def _build_target_instruction(
    entry: Mapping[str, object], model: AcceptedMetamodel
) -> _ResolvedWrite:
    """A target entry as the target instruction it states, prepared by
    the one producer every ingress reaches. It carries its caller's revision
    and no evidence of any read."""
    instruction = instructions.deserialize(
        {
            name: value
            for name, value in entry.items()
            if name in ("mutation", "entity", "row", "ifVersion", "ifTxStart", "validFrom", "until")
        }
    )
    assert isinstance(instruction, TargetWriteInstruction)  # a `row` document is a target write
    return _ResolvedWrite(_case_ingress.prepare_case_write(instruction, model), None)


def _observed_for(
    observations: GroupRetainedObservations, key: ObjectKey
) -> RetainedObservation | None:
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
    store: SimulatedTemporalStore,
    group_observations: GroupRetainedObservations,
) -> list[_ResolvedWrite]:
    """Resolve a compile buffer against its explicit case-long simulated store."""
    resolved: list[_ResolvedWrite] = []
    unit_inserted: set[ObjectKey] = set()
    for entry in entries:
        resolved.extend(
            _build_instructions(entry, model, store, unit_inserted, group_observations, None)
        )
    return resolved


class _SimulatedUnit:
    """The unit of work one simulated transaction buffers its writes through:
    an ordinary :class:`~parallax.core.unit_work.UnitOfWork`, so what the lane
    buffers is admitted, composed, planned, and executed Write Group by Write
    Group exactly as an attempt's own writes are, every step sequence it
    executes changing the case's simulated rows (:func:`_simulated_unit`).

    Every write it buffers settles against authority of this unit's own, as
    an application's would against its source's: an observation is retained
    here, detached from any participation, so this unit's completions never
    invalidate what a real read retained; a write with no observation, of an
    object this unit's own insertion opened, is authorized by the identity this
    unit issued; and an
    observation-free write of an unversioned row carries Read Evidence of its
    own, stamped with a participation no unit of work issued. A write
    that unit of work refuses to admit is refused as the case's composition
    rather than leaked as the production refusal. A target write is
    buffered as the attempt's own is, through
    :meth:`~parallax.core.unit_work.UnitOfWork.buffer_target`: under Locking it
    is confirmed against the case state's stored row.

    ``inserted`` holds the keys temporal inserts opened in this unit's pending
    buffer: a later write of one, resolved into the same buffer, composes onto
    that insert (:func:`_build_temporal_instruction`). It spans every step a
    held group buffers before the unit's next flush, which empties it.
    """

    __slots__ = ("_model", "_participation", "_steps", "_uow", "inserted")

    def __init__(
        self, model: AcceptedMetamodel, uow: UnitOfWork, steps: SimulatedWriteSteps
    ) -> None:
        self._model = model
        self._uow = uow
        self._steps = steps
        self._participation = ParticipationToken()
        self.inserted: set[ObjectKey] = set()

    @property
    def statements(self) -> tuple[LoweredStatement, ...]:
        """Every statement this transaction's flushes recorded so far, in order."""
        return self._steps.statements

    def buffer(self, write: _ResolvedWrite) -> None:
        instruction = write.instruction
        if isinstance(instruction, PreparedTargetWrite):
            self._admit(instruction)
            return
        assert isinstance(instruction, PreparedKeyedWrite)  # predicate writes execute apart
        key = object_key(instruction, self._model)
        observation = write.supplied_observation
        if instruction.mutation in INSERT_MUTATIONS:
            self._admit(instruction)
        elif observation is None:
            self._authorized(instruction, key)
        else:
            assert key is not None  # an observation is bound only to a row naming its object
            shape = temporal_read.view(self._model).shape(instruction.target.identity)
            assert shape is not None  # the facet covers every accepted Entity
            retained = self._retained(
                object_state_key_from_observation(key, observation, shape), observation
            )
            self._settled(instruction, key, retained)

    def execute_predicate(self, prepared: PreparedPredicateWrite) -> int:
        """Execute ``prepared`` once everything buffered has flushed before it,
        as the attempt's own predicate-selected write runs."""
        affected = self._uow.execute_predicate(prepared)
        self.inserted.clear()
        return affected

    def read[T](self, read_fn: Callable[[], T]) -> T:
        """``read_fn``'s answer, run once everything buffered has flushed, as a
        read depending on the buffer flushes it first."""
        answer = self._uow.read(read_fn)
        self.inserted.clear()
        return answer

    def _retained(self, key: ObjectStateKey, evidence: StateObservation) -> RetainedObservation:
        return self._uow.retain(RetainedObservation(key, evidence, None))

    def _authorized(self, instruction: PreparedKeyedWrite, key: ObjectKey | None) -> None:
        identity = None if key is None else self._uow.insertion_identity(key)
        if identity is None:
            self._settled(instruction, key, None)
        else:
            self._admit(buffered_write(instruction, None, authority=identity))

    def _settled(
        self,
        instruction: PreparedKeyedWrite,
        key: ObjectKey | None,
        observation: RetainedObservation | None,
    ) -> None:
        evidence = opt_lock.settled_evidence(
            opt_lock.optimistic_key(self._model, instruction.target.identity),
            instruction.mutation,
            object_key=key,
            observation=observation,
        )
        if not isinstance(evidence, ObjectKey):
            self._admit(buffered_write(instruction, evidence))
            return
        source = ReadEvidence(instruction.target.identity, evidence, self._participation, None)
        self._admit(buffered_write(instruction, evidence, source=source))

    def _admit(self, item: AdmittedWrite | PreparedTargetWrite) -> None:
        try:
            if isinstance(item, PreparedTargetWrite):
                self._uow.buffer_target(item)
            else:
                self._uow.buffer(item)
        except WriteEvidenceError as refusal:
            raise EngineError(
                f"a simulated transaction cannot admit this write beside the ones it already "
                f"buffered — {refusal}"
            ) from refusal


@contextlib.contextmanager
def _simulated_unit(
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
    store: SimulatedTemporalStore | None,
    *,
    rollback: bool,
    record_statements: bool,
) -> Generator[_SimulatedUnit]:
    """One simulated transaction's unit of work, ending with the pre-commit
    flush its writes reach the store through.

    The unit of work is production's own, planned by the SAME
    ``build_write_planner`` factory, over the attempt's lifetime
    implementation, at ``tx_instant``. Its steps run through simulated step
    execution over ``store``, which records the statements they lower to where
    ``record_statements``; a deferred range or group reads its coverage, and a
    Locking target write its stored row, from ``store``. ``store``
    is the caller's to stage: a transaction's rows advance as its flushes
    execute and stand or fall with the caller's
    :meth:`~SimulatedTemporalStore.transaction`. The lifetime closes however
    the transaction ends, and a failure or ``rollback`` discards what the unit
    of work holds. With no store, SQL generation rejects every row acquisition.
    """
    planner = build_write_planner(model)
    steps = SimulatedWriteSteps(
        planner.payloads, model, dialect, store=store, record_statements=record_statements
    )
    lifetime = TxnAttemptLifetime()
    uow = UnitOfWork(
        settings=TransactionSettings(
            concurrency=concurrency, counts_unchanged_rows=dialect.counts_unchanged_rows
        ),
        lifetime=lifetime,
        clock=_pinned_clock(tx_instant),
        meta=model,
        execute_write_steps=steps,
        execute_counted_step=steps.counted,
        acquire_rows=_refuse_marker_rows if store is None else store.acquisition(model),
        planner=planner,
        actor_identity=_PLANNING_ACTOR,
        evidence_policy_for=opt_lock.view(model).required_key,
    )
    try:
        yield _SimulatedUnit(model, uow, steps)
        uow.flush(trigger="pre_commit")
    except BaseException:
        uow.discard()
        raise
    finally:
        lifetime.close()
    if rollback:
        uow.discard()


def _refuse_marker_rows(request: object, consumer: object, /) -> Never:
    raise EngineError("store-free framework marker lowering cannot acquire rows")


def _case_write_instructions(
    entries: Sequence[Mapping[str, object]], model: AcceptedMetamodel
) -> tuple[WriteInstruction, ...]:
    translated: list[WriteInstruction] = []
    for entry in entries:
        entity = _keyed_entry_entity(entry)
        mutation = cast("str", entry["mutation"])
        document = {
            name: entry[name]
            for name in (
                "mutation",
                "entity",
                "row",
                "ifVersion",
                "ifTxStart",
                "validFrom",
                "until",
            )
            if name in entry
        }
        if "row" in entry:
            translated.append(
                _case_ingress.normalize_case_write(instructions.deserialize(document), model)
            )
            continue
        rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
        if _is_temporal_entity(model, entity):
            _temporal_entry_row(entity, mutation, rows)
        for row in rows:
            document["rows"] = [_without_observation_controls(model, entity, mutation, row)]
            translated.append(
                _case_ingress.normalize_case_write(instructions.deserialize(document), model)
            )
    return tuple(translated)


def _lower_marker_unit(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
) -> tuple[LoweredStatement, ...]:
    prepared = instructions.prepare_wire_write(instruction, model)
    with _simulated_unit(
        model, dialect, concurrency, tx_instant, None, rollback=False, record_statements=True
    ) as unit:
        unit.buffer(_ResolvedWrite(prepared, None))
    return unit.statements


def lower_writes(
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    store: SimulatedTemporalStore,
    tx_instant: str,
    group_observations: GroupRetainedObservations,
    *,
    rollback: bool,
) -> tuple[LoweredStatement, ...]:
    """Resolve one write buffer and lower it as its own simulated transaction —
    the COMPILE lane's own lowering, with no database: the statements its
    pre-commit flush recorded, whose count the entries' authored ``statements``
    are graded against (:func:`_check_statement_count_consistency`). A
    ``rollback`` transaction still flushes, and then restores the rows it
    advanced."""
    translated = _case_write_instructions(entries, model)
    if _framework_unit(translated, model):
        statements = _lower_marker_unit(translated[0], model, dialect, concurrency, tx_instant)
        _check_statement_count_consistency(entries, len(statements))
        return statements
    with store.transaction(rollback=rollback):
        resolved = _resolve_entries(entries, model, store, group_observations)
        with _simulated_unit(
            model,
            dialect,
            concurrency,
            tx_instant,
            store,
            rollback=rollback,
            record_statements=True,
        ) as unit:
            for write in resolved:
                unit.buffer(write)
    statements = unit.statements
    _check_statement_count_consistency(entries, len(statements))
    return statements


def _prepared_case_predicate_write(
    raw_write: Mapping[str, object], model: AcceptedMetamodel
) -> PreparedPredicateWrite:
    instruction = instructions.deserialize(raw_write)
    assert isinstance(instruction, PredicateWriteInstruction)
    prepared = _case_ingress.prepare_case_write(instruction, model)
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


def _lower_predicate_write_step(
    prepared: PreparedPredicateWrite,
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    store: SimulatedTemporalStore,
    *,
    rollback: bool,
) -> tuple[LoweredStatement, ...]:
    """Lower an ungrouped READLESS scenario predicate-write step
    (`m-batch-write-005`/``-006``) to its statements as its own simulated
    transaction, with no database: the SAME ``build_write_planner`` planning
    and unit of work every other write path reaches. That is one statement,
    or none for the empty amendment the unit of work answers without one
    (`m-batch-write-050`).

    The case-format preparation seam normalizes only carrier differences before
    strict Wire preparation. The prepared product retains managed values, and
    its compiler metadata projects them back to canonical Wire for the emission
    the case grades.
    """
    # A readless predicate write declares no Transaction-Time boundary, so the
    # inert instant it carries is never captured (ADR 0010).
    with (
        store.transaction(rollback=rollback),
        _simulated_unit(
            model,
            dialect,
            concurrency,
            INERT_CLOCK_INSTANT,
            store,
            rollback=rollback,
            record_statements=True,
        ) as unit,
    ):
        unit.execute_predicate(prepared)
    statements = tuple(unit.statements)
    assert len(statements) <= 1  # a readless predicate write is at most one statement
    return statements


def _execute_wire_predicate_write(
    tx: TxnContext, model: AcceptedMetamodel, raw_write: Mapping[str, object]
) -> int:
    """Execute one scenario predicate write through its public Wire verb, which
    prepares the case's own authored target and changes or row, once, and
    answer the count the verb returned.

    Only a synthetic case's managed carrier values are spelled in Wire first
    (:func:`~parallax.conformance._case_ingress.normalize_case_write`). Dict
    insertion order preserves the authored assignment order; the Entity Layout
    still decides emitted SET order.
    """
    instruction = instructions.deserialize(raw_write)
    assert isinstance(instruction, PredicateWriteInstruction)
    authored = _case_ingress.normalize_case_write(instruction, model)
    target = cast("Mapping[str, object]", raw_write["target"])
    match authored.mutation:
        case "amend":
            return tx.wire.amend_where(
                target,
                {
                    assignment.attr.rpartition(".")[2]: assignment.value
                    for assignment in authored.assignments
                },
            )
        case "replace":
            assert authored.row is not None  # a replacement states its row
            return tx.wire.replace_where(target, authored.row)
        case "delete":
            return tx.wire.delete_where(target)


def _compile_find(
    step: Mapping[str, object], context: CaseContext, dialect: Dialect
) -> tuple[LoweredStatement, ...]:
    """The statements a scenario ``find`` step's read issues over a database
    holding no rows — the COMPILE lane's own oracle.

    The read runs as the RUN lanes run it (:func:`run_standalone_find`,
    :func:`_run_uow_group`): a Wire read inside ``db.transact`` with the
    scenario's authored keywords over a root connected with its configured
    options, so the shared-row-lock suffix is the one production resolves for
    the step's own target Entity.
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

    The query travels as authored. Root as-of injection and per-hop temporal
    propagation are `deep_fetch.plan`'s own first step on every production
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
) -> tuple[Snapshot[WireEntity], LifecycleObservation]:
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
    with Database.connect(
        port, context.serving, options=context.options, lifecycle_provider=observed.provider
    ) as _root_db:
        db = _root_db.using_database_login()
        return (
            transact(db, lambda tx: tx.wire.find(query), **context.requests),
            observed,
        )


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
    store: SimulatedTemporalStore,
    dialect: Dialect,
    step: Mapping[str, object],
    index: int,
) -> LoweredStep:
    """One UNGROUPED scenario step's pointer + DML, with no database — a write
    step as its own simulated transaction, which a ``rollback: true`` step
    restores after itself. A `uow` group's steps share one transaction instead
    (:func:`_lower_group`)."""
    if "write" not in step:
        statements = _compile_find(step, context, dialect)
        return LoweredStep(f"/scenario/{index}/objectQuery", statements, False, False)
    raw_write = step["write"]
    rollback = step.get("rollback") is True
    if is_predicate_write_step(raw_write):
        statements = _lower_predicate_write_step(
            _prepared_case_predicate_write(cast("Mapping[str, object]", raw_write), context.model),
            context.model,
            dialect,
            context.concurrency,
            store,
            rollback=rollback,
        )
        return LoweredStep(f"/scenario/{index}/write", statements, True, rollback)
    entries = write_entries(raw_write)
    statements = lower_writes(
        entries,
        context.model,
        dialect,
        context.concurrency,
        store,
        entry_instant(entries[0]),
        [],
        rollback=rollback,
    )
    return LoweredStep(f"/scenario/{index}/write", statements, True, rollback)


def _lower_group(
    context: CaseContext,
    store: SimulatedTemporalStore,
    dialect: Dialect,
    steps: Sequence[Mapping[str, object]],
    start: int,
    end: int,
    *,
    doomed: bool,
) -> list[LoweredStep]:
    """One CONTIGUOUS `uow` group's steps (index *start*..*end* inclusive) as
    ONE simulated transaction, with no database — the compile peer of the run
    lane's :func:`_run_uow_group`.

    Every write step buffers into the group's one unit of work, at the group's
    one Transaction Instant (:func:`group_tx_instant`); a find step's read
    flushes what is buffered before it is compiled, and the group's end runs
    the pre-commit flush. A DOOMED group still flushes, and its transaction
    then restores every row it advanced. What a flush emitted is attributed as
    the run lane attributes a held group's delivered writes
    (:func:`group_writes`): a read's flush to the last write step buffered
    before it, and a predicate write's flush to the predicate's own step.
    """
    model = context.model
    state = GroupState()
    lowered: list[LoweredStep] = []
    with (
        store.transaction(rollback=doomed),
        _simulated_unit(
            model,
            dialect,
            context.concurrency,
            group_tx_instant(steps, range(start, end + 1)),
            store,
            rollback=doomed,
            record_statements=True,
        ) as unit,
    ):
        for index in range(start, end + 1):
            step = steps[index]
            if "write" not in step:
                statements = unit.read(functools.partial(_compile_find, step, context, dialect))
                lowered.append(
                    LoweredStep(f"/scenario/{index}/objectQuery", statements, False, False)
                )
                continue
            raw_write = step["write"]
            if is_predicate_write_step(raw_write):
                state.buffered.append((index, len(unit.statements)))
                unit.execute_predicate(
                    _prepared_case_predicate_write(cast("Mapping[str, object]", raw_write), model)
                )
            else:
                entries = write_entries(raw_write)
                _refuse_group_markers(entries, model)
                for write in _resolve_entries(entries, model, store, []):
                    unit.buffer(write)
                state.buffered.append((index, len(unit.statements)))
            lowered.append(
                LoweredStep(f"/scenario/{index}/write", (), True, step.get("rollback") is True)
            )
    shares = group_writes(state, unit.statements, "a simulated `uow` group")
    return [
        replace(step, statements=shares[index]) if step.is_write else step
        for index, step in zip(range(start, end + 1), lowered, strict=True)
    ]


def _compiled_groups(
    case: case_format.Case, steps: Sequence[Mapping[str, object]]
) -> dict[int, tuple[int, bool]]:
    """Each `uow` group's own step span, keyed ``start -> (end, doomed)``.

    An interleaved two-group race (:func:`_scenario_uow_spans` returns
    ``None``) answers emptily: it needs two concurrent units a simulated
    transaction has no way to model, and every case carrying that shape is
    `compileEligibility: run-only` for the same reason, so its steps lower one
    by one.
    """
    spans = _scenario_uow_spans(case.path.name, steps)
    if spans is None:
        return {}
    return {start: (end, _group_is_doomed(case, label)) for label, (start, end) in spans.items()}


def _scenario_lowered(case: case_format.Case, dialect_name: str) -> list[LoweredStep]:
    """Lower every scenario step to its pointer + DML, with no database.

    One :class:`SimulatedTemporalStore` spans the whole scenario, seeded from the case's
    own fixture documents
    (:func:`~parallax.conformance._mechanism.given_state.seed_store_from_fixtures`)
    and then advanced by each transaction's flushes: a write step's temporal
    close/chain observes the milestone persisted history declares or one an
    earlier transaction stored, and no query answers either — the seed reads
    the fixtures the run lane's database is provisioned FROM, which is what
    makes the two lanes the same computation while this one reads nothing.

    The compile lane consults NO find-derived observation:
    a keyed write whose version bind is the framework-owned
    advance of a version this SAME scenario's own observing find returned is
    query-result-dependent (`m-conformance-adapter` "Compile eligibility") and
    is therefore declared `compileEligibility: run-only` in the corpus, so it
    short-circuits at :func:`~parallax.conformance._mechanism.case_document.eligibility`
    before this function ever runs (`adapter.compile_case`). A keyed write's
    Version Observation therefore comes from its OWN row's reserved
    ``observedVersion`` control key alone
    (:func:`_durable_row`), exactly as a writeSequence entry's does, and a
    temporal write's whole-milestone observation from the store above.

    Each ungrouped write step is its own transaction and each `uow` group one
    transaction across its steps (:func:`_lower_group`), exactly as the run
    lane executes them. A transaction that rolls back — a doomed group, or an
    ungrouped `rollback: true` write step — restores the rows it advanced once
    it ends, so a step after an abort takes its milestone from the write the
    database kept. Both lanes must reach the same DML for the same case.
    """
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    concurrency = case_document.concurrency(case)
    dialect = dialect_for(dialect_name)
    store = SimulatedTemporalStore()
    context = CaseContext(
        serving,
        model,
        concurrency,
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    seed_store_from_fixtures(case, model, store)
    lowered: list[LoweredStep] = []
    try:
        steps = case_document.scenario_steps(case)
        groups = _compiled_groups(case, steps)
        index = 0
        while index < len(steps):
            group = groups.get(index)
            if group is not None:
                end, doomed = group
                lowered.extend(
                    _lower_group(context, store, dialect, steps, index, end, doomed=doomed)
                )
                index = end + 1
                continue
            lowered.append(_lower_scenario_step(context, store, dialect, steps[index], index))
            index += 1
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return lowered


def _write_sequence_lowered(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, tuple[LoweredStatement, ...]]]:
    """Lower each writeSequence entry independently to ``(pointer, statements)``,
    each as its own simulated transaction. One :class:`SimulatedTemporalStore`
    spans the whole sequence, seeded from the case's own fixture documents
    where it opted in
    (:func:`~parallax.conformance._mechanism.given_state.seed_store_from_fixtures`):
    an entry's temporal close/chain observes the milestone that opt-in declares
    or one an earlier entry stored,
    and no query answers either. A writeSequence carries no find steps at all
    (`m-case-format`), so its own group observation store stays permanently
    empty — a keyed write's Version Observation still comes from its row's own
    ``observedVersion`` control key."""
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = case_document.concurrency(case)
    store = SimulatedTemporalStore()
    seed_store_from_fixtures(case, model, store)
    group_observations: GroupRetainedObservations = []
    try:
        return [
            (
                f"/writeSequence/{index}",
                lower_writes(
                    [entry],
                    model,
                    dialect,
                    concurrency,
                    store,
                    entry_instant(entry),
                    group_observations,
                    rollback=False,
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
    snapshot: Snapshot[WireEntity],
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
    emissions and Database Call count; a scenario carrying an action step is the
    snapshot lane's (:func:`~parallax.conformance._lanes.snapshot.compile_scenario`),
    which the façade dispatches to."""
    emissions = envelope.emissions(
        [(step.pointer, step.statements) for step in _scenario_lowered(case, dialect_name)]
    )
    return emissions, len(emissions)


def compile_write_sequence_case(
    case: case_format.Case, dialect_name: str
) -> tuple[list[Emission], int]:
    """Compile a writeSequence case to its ordered per-entry emissions and Database Calls."""
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
    if not isinstance(instruction, (KeyedWriteInstruction, PreparedKeyedWrite)):
        return False
    entity = (
        instruction.target.identity.canonical
        if isinstance(instruction, PreparedKeyedWrite)
        else instruction.entity
    )
    position = inheritance.view(model).entity(case_entity(model, entity).identity)
    if position is None:  # pragma: no cover - accepted entities have an inheritance position
        return False
    shape = position.member_selection.shape
    return any(
        isinstance(shape.member(name), Leaf)
        and isinstance(value, Mapping)
        and frozenset(cast("Mapping[str, object]", value)) in _MARKER_KEYS
        for row in instruction.rows
        for name, value in row.items()
    )


_MARKER_KEYS: Final[frozenset[frozenset[str]]] = frozenset(
    {frozenset({"computed"}), frozenset({"increment"})}
)


def _refuse_group_markers(
    entries: Sequence[Mapping[str, object]], model: AcceptedMetamodel
) -> None:
    if any(_is_framework_write(write, model) for write in _case_write_instructions(entries, model)):
        raise EngineError(
            "a DB-computed write marker is a choreography unit of its own; "
            "a `uow` group's held transaction has no verb to buffer one through"
        )


def _execute_framework_write_unit(
    port: DatabaseConnection,
    statements: Sequence[LoweredStatement],
    *,
    rollback: bool,
) -> int:
    """Execute the choreography unit ONE framework-marker entry is, and report the
    calls it cost.

    The statements the caller's simulated transaction recorded, executed on the
    port's own transaction, rather than driven through a write verb, because
    there is no verb to drive: a
    ``{"increment": n}`` registry advance is the PK allocator's own statement,
    and admitting it at a public ingress would make a DB-computed write marker
    developer surface over the framework's bookkeeping.

    Executing the statements the caller reports is what keeps the two the same:
    this unit opens no Handle, so no lifecycle observes it, and a plan of its own
    would be a second derivation nothing could reconcile against the first. It is
    the one write lane whose Database Calls are STATED — it reaches its last
    statement only by having issued every one before it, the same reasoning
    `run_error_case` carries for authored trigger DML.

    A marker entry is a choreography unit of its own and the buffer's only entry
    (`m-case-format` "Buffered keyed write instructions"), which is why this
    takes one entry's statements rather than a buffer: the unit is the entry. It honours the
    step's own abort contract like every other write path: a ``rollback: true``
    step runs on the aborting port, its statements reach the wire and count their
    Database Calls, and the provider then rolls them back.
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
    returned. Reading per row instead would cost the corpus a Database Call per row
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
                "path": f"{declaring.identity.canonical}.{name}",
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
    model: AcceptedMetamodel, translated: Sequence[WriteInstruction]
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
    for instruction in translated:
        if not isinstance(instruction, KeyedWriteInstruction):
            continue
        if instruction.mutation in INSERT_MUTATIONS:
            key = _instruction_key(instruction, model)
            if key is not None:
                opened.add(key)
    needed: dict[tuple[str, dt.datetime | None], dict[ObjectKey, None]] = {}
    for instruction in translated:
        if not isinstance(instruction, KeyedWriteInstruction):
            continue
        if instruction.mutation in INSERT_MUTATIONS:
            continue
        key = _instruction_key(instruction, model)
        if key is None or key in opened:
            continue
        canonical = case_entity(model, instruction.entity).identity.canonical
        needed.setdefault((canonical, instruction.valid_from), {})[key] = None
    return [
        _unit_source_query(model, entity, tuple(keys), valid_at)
        for (entity, valid_at), keys in needed.items()
    ]


def _execute_write_unit(
    port: CaseDatabase,
    context: CaseContext,
    translated: Sequence[WriteInstruction],
    tx_instant: str,
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """Execute unprepared writes through production, resolving all sources before buffering."""
    model = context.model
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    observed = lifecycle.observation()
    with Database.connect(
        write_adapter(port, rollback=rollback),
        context.serving,
        options=context.options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()

        def body(tx: TxnContext) -> None:
            state = GroupState()
            with observed.resolving_reads():
                for query in _unit_source_reads(model, translated):
                    state.published.extend(_published_nodes(tx.wire.find(query)))
            for instruction in translated:
                _buffer_wire_write(tx, model, state, instruction, None)

        with absorbing_rollback():
            transact(database, body, **context.requests)
        return observed.writes, observed.database_calls


def _framework_unit(translated: Sequence[WriteInstruction], model: AcceptedMetamodel) -> bool:
    """Whether one choreography unit states the framework's own bookkeeping,
    which :func:`_execute_framework_write_unit` executes because no public verb
    states it.

    A marker entry is a choreography unit of its own and therefore the buffer's
    ONLY entry (`m-case-format` "Buffered keyed write instructions"), so anything
    beside it states a form no case may author and is refused here rather than
    silently executed as one unit: a caller-authored entry would put half the DML
    through a public verb and half around it, and a second marker would fold two
    of the framework's own units into one flush, hiding whichever boundary the
    corpus meant to grade.
    """
    framework = [write for write in translated if _is_framework_write(write, model)]
    if not framework:
        return False
    if len(framework) != len(translated):
        raise EngineError(
            "a choreography unit states either the framework's own bookkeeping or the writes "
            f"a caller authors, never both: this one holds {len(framework)} entry(s) carrying "
            f"a DB-computed write marker beside {len(translated) - len(framework)} that a "
            "public verb states"
        )
    if len(translated) != 1:
        raise EngineError(
            "an entry carrying a DB-computed write marker states the framework's own "
            "bookkeeping and is a choreography unit of its own, so it is the buffer's only "
            f"entry: this one holds {len(translated)}"
        )
    return True


def execute_keyed_unit(
    port: CaseDatabase,
    context: CaseContext,
    entries: Sequence[Mapping[str, object]],
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int]:
    """Execute one keyed choreography unit and report the lifecycle-delivered DML.

    Only isolated framework markers use store-free lowering instead of public verbs."""
    tx_instant = entry_instant(entries[0])
    translated = _case_write_instructions(entries, context.model)
    if _framework_unit(translated, context.model):
        statements = _lower_marker_unit(
            translated[0], context.model, port.dialect, context.concurrency, tx_instant
        )
        _check_statement_count_consistency(entries, len(statements))
        return statements, _execute_framework_write_unit(port, statements, rollback=rollback)
    ran, unit_calls = _execute_write_unit(
        port, context, translated, tx_instant, lifecycle, rollback=rollback
    )
    _check_statement_count_consistency(entries, len(ran))
    return ran, unit_calls


def _run_readless_predicate_write(
    port: CaseDatabase,
    context: CaseContext,
    raw_write: Mapping[str, object],
    tx_instant: str,
    lifecycle: LifecycleRun,
    *,
    rollback: bool,
) -> tuple[tuple[LoweredStatement, ...], int, int]:
    """Execute a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) through the SAME production ``db.transact`` entry point every
    other write path uses. The public Wire verb prepares the case's authored
    target and changes.

    The reported emission is the DML the lifecycle delivered, whose compiler
    metadata renders the canonical Wire binds used for grading, beside the
    Database Calls it made and the count the verb returned.
    """
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    observed = lifecycle.observation()
    with Database.connect(
        write_adapter(port, rollback=rollback),
        context.serving,
        options=context.options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()
        affected: list[int] = []

        def body(tx: TxnContext) -> None:
            affected[:] = [_execute_wire_predicate_write(tx, context.model, raw_write)]

        with absorbing_rollback():
            transact(database, body, **context.requests)
        (count,) = affected
        return observed.writes, observed.database_calls, count


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
    """Fixed case model, planning preference, root options, and authored transaction keywords.

    Simulated state is passed explicitly only to compile helpers. The dialect comes
    from each executing connection, which may differ across interleaved groups."""

    serving: ServingModel
    model: AcceptedMetamodel
    concurrency: Concurrency
    requests: case_format.TransactionKeywords
    options: TxnOptions


def _empty_published() -> list[WireEntity]:
    return []


def _empty_group_finds() -> dict[int, tuple[WireEntity, ...]]:
    return {}


def _empty_opened() -> dict[ObjectKey, WireEntity]:
    return {}


def _empty_answered() -> dict[str, list[WireEntity]]:
    return {}


def _empty_buffered() -> list[tuple[int, int]]:
    return []


def _empty_affected() -> dict[int, int]:
    return {}


@dataclass(frozen=True, slots=True)
class GroupState:
    """What ONE `uow` group accumulates as its own steps run, and nothing wider.

    Every field holds published VALUES rather than derived evidence, because a
    value is what a keyed Wire verb is addressed and licensed by, and its claim
    is one accessor away. ``published`` is the flat
    run a write with no reference resolves against, ``finds`` keys the same nodes
    by the step that published them — what a write step naming a find with ``on``
    addresses (`m-case-format` *Settling against a grouped find*) — and
    ``opened`` and ``insertions`` hold the same accepted insert results by object
    key and submission pointer. Explicit references never fall back to another value.
    ``buffered`` holds each write step's index,
    in step order, beside how many writes the group had delivered once that step
    finished buffering, or, for a predicate write, before it executed
    (:func:`group_writes`). ``affected`` holds the count each predicate-write
    step's verb returned, by step index. All are built fresh per attempt,
    never a scenario-wide store, so no value crosses a transaction boundary.
    """

    published: list[WireEntity] = field(default_factory=_empty_published)
    finds: dict[int, tuple[WireEntity, ...]] = field(default_factory=_empty_group_finds)
    opened: dict[ObjectKey, WireEntity] = field(default_factory=_empty_opened)
    insertions: dict[str, list[WireEntity]] = field(default_factory=_empty_answered)
    buffered: list[tuple[int, int]] = field(default_factory=_empty_buffered)
    affected: dict[int, int] = field(default_factory=_empty_affected)


def group_writes(
    state: GroupState, delivered: Sequence[LoweredStatement], where: str
) -> dict[int, tuple[LoweredStatement, ...]]:
    """Each write step's share of the writes one held group's flushes delivered,
    keyed by step index.

    A held group's buffered writes reach the wire when a later read or
    predicate write forces a flush, or at its boundary, so the step a delivered
    write belongs to is read off when it was delivered: each write step owns
    what was delivered after its mark and before the next write step's, and the
    last owns everything after. A keyed write step's mark is where it finished
    buffering, so write steps buffered before a read's flush report that
    flush's statements under the last of them, because what one flush delivers
    carries no trace of the step that buffered each write. A predicate write's
    mark is where it was called, so it reports the whole flush it executed in:
    everything buffered before it, then its own statement.
    """
    shares: dict[int, tuple[LoweredStatement, ...]] = {}
    buffered = state.buffered
    first = buffered[0][1] if buffered else len(delivered)
    if first:
        raise EngineError(
            f"{where}: the lifecycle delivered {first} write(s) before any write step had "
            "buffered one"
        )
    for position, (index, start) in enumerate(buffered):
        stop = buffered[position + 1][1] if position + 1 < len(buffered) else len(delivered)
        shares[index] = (*shares.get(index, ()), *delivered[start:stop])
    return shares


def _published_nodes(snapshot: Snapshot[WireEntity]) -> tuple[WireEntity, ...]:
    """Every Entity node ``snapshot`` published, each once, in walk order.

    The roots come from the CHECKED view, because invalid stored data is a fact
    about a root rather than a refusal of the read.
    """
    return _published_from(snapshot.checked().results())


def _published_from(roots: Iterable[object]) -> tuple[WireEntity, ...]:
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
    nodes: list[WireEntity] = []
    visited: set[int] = set()
    frontier: list[object] = [
        cast("read_delivery.InvalidData[object]", root).data
        if isinstance(root, read_delivery.InvalidData)
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
        if not isinstance(value, WireEntity) or id(value) in visited:
            continue
        visited.add(id(value))
        nodes.append(value)
        frontier.extend(cast("Mapping[str, object]", value).values())
    return tuple(nodes)


def _node_object_key(node: WireEntity) -> ObjectKey:
    """The object ``node`` names: the one its read observed, or the one the
    insert that answered it opened."""
    hint = read_evidence_of(node)
    if hint is not None:
        return hint.object_key
    authority = authoring_of(node)
    assert authority is not None  # every node this lane holds a read or an insert published
    return authority.object_key


def _writable_source(node: WireEntity) -> bool:
    """Whether a keyed write may be addressed by ``node`` at all.

    A group may publish SEVERAL milestones of one key — an audit read of the
    Transaction-Time past beside a read of the current row — and only the
    current one is writable, because the Transaction-Time past records what the
    system knew and is never rewritten. A caller holding both hands the verb the
    writable one, so an unreferenced scan skips what the verb would refuse
    rather than reaching for the refusal.
    """
    hint = read_evidence_of(node)
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
    named: Sequence[WireEntity] | None,
    valid_from: dt.datetime | None = None,
) -> WireEntity:
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
        if read_evidence_of(node) is not None and not _pinned_at(node, valid_from):
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


def _pinned_at(node: WireEntity, valid_from: dt.datetime | None) -> bool:
    """Whether ``node`` was read at the Valid-Time instant a write starting at
    ``valid_from`` takes from its source; a write with no Valid-Time start
    takes none."""
    if valid_from is None:
        return True
    hint = read_evidence_of(node)
    assert hint is not None
    pin = hint.pin
    return pin is not None and pin.valid_time == valid_from


def _source_find_nodes(
    entry: Mapping[str, object],
    index: int,
    group_finds: Mapping[int, tuple[WireEntity, ...]],
) -> tuple[WireEntity, ...] | None:
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
            "step of its own `uow` group — the evidence a write settles against is "
            "transaction-scoped (m-case-format 'Settling against a grouped find')"
        )
    return published


def _source_nodes(
    entry: Mapping[str, object], index: int, state: GroupState
) -> Sequence[WireEntity] | None:
    source = entry.get("on")
    if isinstance(source, str):
        opened = state.insertions.get(source)
        if opened is None:
            raise EngineError(
                f"scenario[{index}]: writes through {source!r}, which opened no value "
                "in this attempt of its own `uow` group"
            )
        return opened
    return _source_find_nodes(entry, index, state.finds)


def _buffer_wire_write(
    tx: TxnContext,
    model: AcceptedMetamodel,
    state: GroupState,
    instruction: WriteInstruction,
    named: Sequence[WireEntity] | None,
    *,
    pointer: str | None = None,
) -> None:
    """Submit an unprepared instruction through its public Wire verb."""
    if isinstance(instruction, TargetWriteInstruction):
        _buffer_wire_target(tx, model, instruction)
        return
    assert isinstance(instruction, KeyedWriteInstruction)
    if instruction.mutation in INSERT_MUTATIONS:
        _buffer_wire_insert(tx, model, state, instruction, pointer)
        return
    _buffer_wire_keyed(
        tx,
        model,
        instruction,
        _group_source_node(
            case_entity(model, instruction.entity).identity.canonical,
            _instruction_key(instruction, model),
            state,
            named,
            instruction.valid_from,
        ),
    )


def _instruction_key(
    instruction: KeyedWriteInstruction, model: AcceptedMetamodel
) -> ObjectKey | None:
    entity = case_entity(model, instruction.entity)
    declaring = family_declarer(model, entity)
    attributes = [
        attr for attr in declaring.declared_attributes if isinstance(attr.primary_key, PrimaryKey)
    ]
    row = instruction.rows[0]
    if not attributes or any(row.get(attr.identity.name) is None for attr in attributes):
        return None
    return ObjectKey(
        entity.identity,
        tuple(
            (attr.identity.name, decode_wire(attr.type, cast("WireValue", row[attr.identity.name])))
            for attr in attributes
        ),
    )


def _buffer_wire_insert(
    tx: TxnContext,
    model: AcceptedMetamodel,
    state: GroupState,
    instruction: KeyedWriteInstruction,
    pointer: str | None,
) -> WireEntity:
    """Buffer ONE insert through ``tx.wire.insert`` and record the value it
    answered: a row no find can have returned, which a later write of the
    same unit is addressed by — read-your-own-writes."""
    valid_from, until = instruction.valid_from, instruction.until
    entity = case_entity(model, instruction.entity)
    version = _versioned_non_temporal_version_attribute(model, instruction.entity)
    payload = {
        name: value
        for name, value in instruction.rows[0].items()
        if version is None or name != version.identity.name
    }
    opened = (
        tx.wire.insert(
            entity.identity.canonical,
            payload,
            valid_from=_required(valid_from),
            until=_required(until),
        )
        if instruction.mutation == "insertUntil"
        else tx.wire.insert(entity.identity.canonical, payload, **_stated_start(valid_from))
    )
    state.opened[_node_object_key(opened)] = opened
    if pointer is not None:
        state.insertions.setdefault(pointer, []).append(opened)
    return opened


def _buffer_wire_keyed(
    tx: TxnContext, model: AcceptedMetamodel, instruction: KeyedWriteInstruction, node: WireEntity
) -> None:
    """Submit authored changes against the published source, leaving admission to production."""
    key = _instruction_key(instruction, model)
    identity = dict(key.primary_key) if key is not None else {}
    changes = {name: value for name, value in instruction.rows[0].items() if name not in identity}
    until = instruction.until
    match instruction.mutation:
        case "amend":
            tx.wire.amend(node, changes)
        case "amendUntil":
            tx.wire.amend(node, changes, until=_required(until))
        case "replace" | "replaceUntil":
            tx.wire.replace(node, changes, **({} if until is None else {"until": until}))
        case "delete":
            tx.wire.delete(node)
        case "terminate":
            tx.wire.terminate(node)
        case _:
            tx.wire.terminate(node, until=_required(until))


def _buffer_wire_target(
    tx: TxnContext, model: AcceptedMetamodel, instruction: TargetWriteInstruction
) -> None:
    """Buffer ONE target write through the public ``tx.wire`` verb
    its mutation names, with the caller's own revision beside its document."""
    entity_name = case_entity(model, instruction.entity).identity.canonical
    document = dict(instruction.row)
    valid_from, until = instruction.valid_from, instruction.until
    condition: dict[str, Any] = (
        {"version": instruction.if_version}
        if instruction.if_version is not None
        else {"tx_start": instruction.if_tx_start}
    )
    bounds: dict[str, Any] = {**_stated_start(valid_from)}
    if until is not None:
        bounds["until"] = until
    match instruction.mutation:
        case "amend" | "amendUntil":
            tx.wire.amend_if(entity_name, document, **condition, **bounds)
        case "replace" | "replaceUntil":
            tx.wire.replace_if(entity_name, document, **condition, **bounds)
        case "delete":
            tx.wire.delete_if(entity_name, document, **condition)
        case _:
            tx.wire.terminate_if(entity_name, document, **condition, **bounds)


def _stated_start(valid_from: dt.datetime | None) -> dict[str, dt.datetime]:
    """``valid_from`` as the keyword a public verb takes, omitted where the
    instruction states no start."""
    return {} if valid_from is None else {"valid_from": valid_from}


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
    graph: Snapshot[WireEntity] | None


@dataclass(frozen=True, slots=True)
class _GroupRun:
    """One `uow` group's own report: its steps' lowered emissions in step order,
    the Database Calls its single transaction made, the per-step observations
    its read steps filled, each in step order, and the count each of its
    predicate-write steps returned, by step index."""

    lowered: list[LoweredStep]
    database_calls: int
    step_rows: list[dict[str, object]]
    step_graphs: list[dict[str, object]]
    affected: dict[int, int]


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
    root: Database[object]
    database: ScopedDatabase

    def __init__(
        self,
        adapter: DatabaseAdapter,
        context: CaseContext,
        instant: dt.datetime,
        observation: LifecycleObservation,
    ) -> None:
        object.__setattr__(self, "adapter", adapter)
        root = Database.connect(
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
    tx: TxnContext,
    context: CaseContext,
    state: GroupState,
    step: Mapping[str, object],
    index: int,
    observation: LifecycleObservation,
) -> tuple[LoweredStep, _StepRead | None]:
    """Interpret a held group step through public verbs using this attempt's values.

    Reads publish sources and flush pending writes through production. Predicate writes
    record their returned count; buffered writes record a lifecycle attribution mark."""
    model = context.model
    if "write" in step and is_predicate_write_step(step["write"]):
        raw_write = cast("Mapping[str, object]", step["write"])
        state.buffered.append((index, len(observation.writes)))
        state.affected[index] = _execute_wire_predicate_write(tx, model, raw_write)
        return (
            LoweredStep(f"/scenario/{index}/write", (), True, step.get("rollback") is True),
            None,
        )
    if "write" in step:
        entries = write_entries(step["write"])
        _refuse_group_markers(entries, model)
        for position, entry in enumerate(entries):
            named = _source_nodes(entry, index, state)
            for write in _case_write_instructions([entry], model):
                _buffer_wire_write(
                    tx, model, state, write, named, pointer=f"/scenario/{index}/write/{position}"
                )
        state.buffered.append((index, len(observation.writes)))
        return LoweredStep(f"/scenario/{index}/write", (), True, False), None
    return _group_read(tx, context, state, step, index, observation)


def _group_read(
    tx: TxnContext,
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
    mark = observation.database_calls
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
        f"/scenario/{index}/objectQuery", observation.own_reads_since(mark), False, False
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
    """Run one contiguous group in production.

    Reports and source references are attempt-local; delivered lifecycle calls, including
    failed attempts, remain cumulative."""
    tx_instant = group_tx_instant(steps, range(start, end + 1))
    doomed = _group_is_doomed(case, cast("str", steps[start]["uow"]))
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    observation = lifecycle.observation()
    session = GroupSession(write_adapter(port, rollback=doomed), context, instant, observation)
    try:
        lowered: list[LoweredStep] = []
        rows_observed: list[dict[str, object]] = []
        step_graphs: list[dict[str, object]] = []
        state = GroupState()
        prior_buffered: list[tuple[int, int]] = []

        def body(tx: TxnContext) -> None:
            nonlocal state, lowered, rows_observed, step_graphs
            prior_buffered.extend(state.buffered)
            state = GroupState()
            lowered, rows_observed, step_graphs = [], [], []
            for index in range(start, end + 1):
                step, read = run_group_step(tx, context, state, steps[index], index, observation)
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

        with absorbing_rollback():
            transact(session.database, body, **context.requests)
        state.buffered[:0] = prior_buffered
        shares = group_writes(state, observation.writes, "a held `uow` group")
        reported = [
            replace(step, statements=shares[index]) if step.is_write else step
            for index, step in zip(range(start, end + 1), lowered, strict=True)
        ]
        # Every statement this ONE transaction put on the wire, which is where the
        # group's Database Calls come from rather than from a second count this lane
        # keeps.
        return _GroupRun(
            reported, observation.database_calls, rows_observed, step_graphs, state.affected
        )
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# State-graded groups: public verbs only, graded on what they leave.           #
# --------------------------------------------------------------------------- #


def _empty_refusals() -> list[dict[str, object]]:
    return []


@dataclass(frozen=True, slots=True)
class _Submitted:
    refusals: list[dict[str, object]] = field(default_factory=_empty_refusals)


def _submission_writes(
    entry: Mapping[str, object], model: AcceptedMetamodel
) -> tuple[WriteInstruction, ...]:
    """One keyed submission as the instructions its verb is handed, one per row.

    A state-graded group drives public verbs only, so nothing here resolves an
    observation: the value a verb is handed carries its own.
    """
    _refuse_group_markers([entry], model)
    return _case_write_instructions([entry], model)


def _submit(
    tx: TxnContext,
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
            _execute_wire_predicate_write(tx, model, entry)
        elif "row" in entry:
            (target,) = _case_write_instructions([entry], model)
            assert isinstance(target, TargetWriteInstruction)
            _buffer_wire_target(tx, model, target)
        else:
            named = _source_nodes(entry, index, state)
            for write in _submission_writes(entry, model):
                _buffer_wire_write(tx, model, state, write, named, pointer=pointer)
    except WriteEvidenceError as exc:
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
    published, the refusals its submissions raised, and its Database Calls."""

    fate: dict[str, object]
    step_rows: list[dict[str, object]]
    refusals: list[dict[str, object]]
    database_calls: int


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
    fails ends it where it ran — at the find whose read flushed, at the write
    step whose predicate submission flushed, or at commit — which is the fate it
    reports.
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

    def body(tx: TxnContext) -> None:
        nonlocal state, submitted, rows_observed, running
        state = GroupState()
        submitted = _Submitted()
        rows_observed, running = [], []
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
    return _StateGroupRun(outcome, rows_observed, submitted.refusals, observation.database_calls)


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
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    units: dict[str, dict[str, object]] = {}
    refusals: list[dict[str, object]] = []
    rows_observed: list[dict[str, object]] = []
    database_calls = 0
    try:
        apply_given_apply(case, port)
        index = 0
        while index < len(steps):
            group = starts.get(index)
            if group is not None:
                label, end = group
                run = _run_state_graded_group(case, port, context, steps, index, end, lifecycle)
                units[label] = run.fate
                refusals.extend(run.refusals)
                rows_observed.extend(run.step_rows)
                database_calls += run.database_calls
                index = end + 1
                continue
            step = steps[index]
            if "write" in step:
                raise EngineError(
                    f"{case.path.name}: scenario[{index}] is an ungrouped write, which a "
                    "state-graded case states no fate for"
                )
            read, read_observed = run_standalone_find(port, context, step, lifecycle)
            database_calls += read_observed.database_calls
            query = step_query(step, model)
            rows_observed.append(step_rows(model, index, query, read.checked().results()))
            index += 1
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return ScenarioRun(
        [], database_calls, refusals, rows_observed, [], units, read_table_state(port, model)
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
    never an oracle.

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
    declaring `expectRows`. `stepAffectedRows` holds the count each direct
    predicate-write step's verb returned, grouped or not."""
    lifecycle = lifecycle_run(lifecycle)
    if case.document.get("grading") == "state":
        return _run_state_graded_case(case, port, lifecycle)
    steps = case_document.scenario_steps(case)
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    concurrency = case_document.concurrency(case)
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
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    lowered: list[LoweredStep] = []
    units: dict[str, dict[str, object]] = {}
    affected: dict[int, int] = {}
    database_calls = 0
    try:
        apply_given_apply(case, port)
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
                affected.update(group.affected)
                database_calls += group.database_calls
                index = end + 1
                continue
            step = steps[index]
            if "write" not in step:
                read, read_observed = run_standalone_find(port, context, step, lifecycle)
                database_calls += read_observed.database_calls
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
                raw_predicate_write = cast("Mapping[str, object]", raw_write)
                tx_instant = entry_instant(raw_predicate_write)
                ran, predicate_calls, affected[index] = _run_readless_predicate_write(
                    port,
                    context,
                    raw_predicate_write,
                    tx_instant,
                    lifecycle,
                    rollback=rollback,
                )
                database_calls += predicate_calls
                lowered.append(LoweredStep(f"/scenario/{index}/write", ran, True, rollback))
            else:
                statements, unit_calls = execute_keyed_unit(
                    port, context, write_entries(raw_write), lifecycle, rollback=rollback
                )
                database_calls += unit_calls
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
    return ScenarioRun(
        emissions,
        database_calls,
        [],
        rows_observed,
        step_graphs,
        units,
        table_state,
        step_affected_rows(affected),
    )


def step_affected_rows(affected: Mapping[int, int]) -> list[dict[str, object]]:
    """The `stepAffectedRows` observation (`m-conformance-adapter`): each
    predicate-write step's pointer and the count its verb returned, in step
    order."""
    return [
        {"at": f"/scenario/{index}", "affectedRows": count}
        for index, count in sorted(affected.items())
    ]


def run_write_sequence_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> tuple[list[Emission], dict[str, list[MappingRow]], int]:
    """Run a writeSequence: each entry executes as its OWN unit of work through
    ``db.transact`` (one transaction per entry, never the whole sequence in
    one), then report the ordered per-entry
    emissions, the committed table state, and the total Database Calls.

    The table read-back is the `m-conformance-adapter` write-sequence observation
    ("write-sequence cases report ``tableState``"): the runner grades it against
    the case's ``then.tableState``. Observation reads are not case Database Calls.

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
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    lowered: list[tuple[str, tuple[LoweredStatement, ...]]] = []
    database_calls = 0
    try:
        apply_given_apply(case, port)
        for index, entry in enumerate(case_document.write_sequence_entries(case)):
            statements, unit_calls = execute_keyed_unit(
                port, context, [entry], lifecycle, rollback=False
            )
            database_calls += unit_calls
            lowered.append((f"/writeSequence/{index}", statements))
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = envelope.emissions(lowered)
    table_state = read_table_state(port, model)
    return emissions, table_state, database_calls


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


def _conflict_mutation(when: Mapping[str, object]) -> Literal["amend", "delete"]:
    """A conflict case's written verb (`m-case-format` ``when.mutation``),
    defaulting to ``amend``."""
    return "delete" if when.get("mutation") == "delete" else "amend"


@dataclass(frozen=True, slots=True)
class _ConflictWrite:
    """One row of a NON-TEMPORAL conflict attempt's ``write``, resolved once for
    the real execution: the durable row, the single-row instruction a unit of
    work buffers for it, that instruction's coalescing identity, and the Version
    Observation the row's reserved ``observedVersion`` described.

    The observation is a DECLARED FACT the case states, never the evidence the
    write settles against: the real execution reads its own source and settles
    against what that read observed (:func:`_conflict_source_nodes`), and this
    value is what that observation is cross-checked against
    (:func:`_refuse_unobserved_conflict_version`).
    """

    row: dict[str, object]
    instruction: PreparedWrite
    key: ObjectKey | None
    observation: VersionObservation | None


def _resolve_conflict_writes(
    model: AcceptedMetamodel,
    target: str,
    mutation: Literal["amend", "delete"],
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
        assert isinstance(instruction, KeyedWriteInstruction)  # a `rows` document is a keyed write
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


def _refuse_a_bound_short_of_the_authored_attempts(case: case_format.Case, authored: int) -> None:
    """Refuse a conflict case whose resolved retry bound admits fewer
    production attempts than it authors.

    The case's attempts are production's own: one ``db.transact`` call runs
    them, and each replay the bounded retry loop makes is the next authored
    attempt. A bound of ``N`` admits ``N + 1`` attempts, so a sequence longer
    than that describes replays production would never make.
    """
    bound = case_format.effective_options(case).max_retries
    if bound + 1 >= authored:
        return
    raise EngineError(
        f"{case.path.name}: the case authors {authored} attempts and its transaction resolves "
        f"`maxRetries: {bound}`, which admits {bound + 1} — every authored attempt is one "
        "production attempt of a single invocation (m-case-format 'Conflict cases')"
    )


def _conflict_attempt_affected(
    database: ScopedDatabase,
    requests: case_format.TransactionKeywords,
    implied: type[WriteEffectError],
    body: Callable[[TxnContext], int],
) -> int:
    """The final conflict attempt's affected-row observation: what ``body``
    reports when the write lands, or the ``actual`` count carried by the ONE
    Write Effect Error the case's own declared facts admit, once production's
    bound left that failure unreplayed.

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
            "path": f"{declaring.identity.canonical}.{name}",
            "values": [write.row[name] for write in resolved],
        }
    }


def _conflict_source_nodes(
    tx: TxnContext,
    model: AcceptedMetamodel,
    target: str,
    resolved: Sequence[_ConflictWrite],
    observed: LifecycleObservation,
) -> dict[ObjectKey, WireEntity]:
    """The published rows one NON-TEMPORAL conflict attempt's keyed writes are
    addressed and licensed by, read through a real ``tx.wire.find`` inside the
    attempt whose writes they license — the only read a source write can be
    licensed by (`m-unit-work` *Current-attempt source admission*).

    A row the read does not answer is absent from the mapping; the write that
    wanted it is refused where its diagnosis can name the key
    (:func:`_conflict_source_node`).

    The read is charged to the observation's resolving reads: a case counts it in
    `then.databaseCalls` and authors no golden for it, so it names no statement
    index (`m-case-format` "Resolving reads a write owes").
    """
    nodes: dict[ObjectKey, WireEntity] = {}
    with observed.resolving_reads():
        snapshot = tx.wire.find(
            {"target": target, "predicate": _conflict_key_predicate(model, target, resolved)}
        )
        for root in snapshot.results():
            hint = read_evidence_of(root)
            assert hint is not None  # a Wire read files a hint on every published Entity node
            nodes[hint.object_key] = root
    return nodes


def _conflict_source_node(
    target: str, write: _ConflictWrite, nodes: Mapping[ObjectKey, WireEntity]
) -> WireEntity:
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
    target: str, write: _ConflictWrite, node: WireEntity
) -> None:
    """Refuse an attempt whose declared ``observedVersion`` is not the version its
    own source read observed.

    The declared fact and the real observation are two spellings of one state,
    and the case's golden gate bind is derived from the declared one while the
    write settles against the observed one. Letting them differ would grade a
    statement against a version no read of this lane ever saw.
    """
    declared = None if write.observation is None else write.observation.observed_version
    hint = read_evidence_of(node)
    assert hint is not None  # the node came from :func:`_conflict_source_nodes`
    retained = None if hint.observation is None else hint.observation.evidence
    observed = retained.observed_version if isinstance(retained, VersionObservation) else None
    if declared != observed:
        raise EngineError(
            f"{target!r}: a conflict attempt declares `observedVersion: {declared!r}` and its "
            f"own source read observed {observed!r} — the gate this case grades binds the "
            "declared version, so the two must name one state"
        )


def _run_conflict_attempts(
    port: CaseDatabase,
    serving: ServingModel,
    model: AcceptedMetamodel,
    options: TxnOptions,
    target: str,
    concurrency: Concurrency,
    requests: case_format.TransactionKeywords,
    attempts: Sequence[Sequence[Mapping[str, object]]],
    mutation: Literal["amend", "delete"],
    interfere: Callable[[], None],
    lifecycle: LifecycleRun,
) -> tuple[tuple[tuple[LoweredStatement, ...], ...], int, int]:
    """Execute a NON-TEMPORAL conflict case's attempts through ONE ``db.transact``
    call — over a root connected with ``options``, an inert Clock (never
    consumed by a non-temporal write), and exactly the options the case requests
    (``requests``) — whose physical attempts are the authored ones, in order:
    each replay production's bounded retry loop makes runs the next authored
    attempt. ``attempts`` holds each authored attempt's ``write`` rows;
    ``concurrency`` is the planning value the implied shortfall is classified
    under.

    Inside each attempt the callback reads its sources
    (:func:`_conflict_source_nodes`), lets ``interfere`` commit whatever
    concurrent writer the case stages between that read and the write it
    invalidates, and then writes every row through the PUBLIC keyed Wire verb its
    mutation names, against the node the read published for its key. A MULTI-KEY
    attempt therefore reaches the flush exactly as that many developer calls
    would, and the batching rule — not this function — decides how many
    statements they become. The PRODUCTION flush executor's OWN affected-row
    enforcer raises on a violation, and this lane admits only the class the
    case's own declared facts imply (:func:`_implied_shortfall_error`),
    rendering it as the final ``affectedRows`` observation the case asserts. A
    failure classified any other way — a gated shortfall surfacing as a stale
    write, or the reverse — propagates and fails the case.

    Production deciding on a different number of attempts than the case
    authors fails the case: a replay past the last authored attempt is refused
    inside the callback, and an invocation that ended early is refused once it
    returns.

    Answers each attempt's DML as the lifecycle delivered it, each statement in
    the canonical Lowered Statement form its Database Call borrowed, whose
    metadata projects native execution carriers into one canonical Wire
    observation; the final affected-row count; and the Database Calls.
    """
    resolved_attempts = [
        _resolve_conflict_writes(model, target, mutation, rows) for rows in attempts
    ]
    _refuse_a_locking_conflict_target(model, target, concurrency)
    instant = normalize_instant(dt.datetime.fromisoformat(INERT_CLOCK_INSTANT))
    observed = lifecycle.observation()
    starts: list[int] = []
    with Database.connect(
        port,
        serving,
        options=options,
        clock=FixedClock(instant),
        lifecycle_provider=observed.provider,
    ) as _root_database:
        database = _root_database.using_database_login()

        def body(tx: TxnContext) -> int:
            if len(starts) == len(resolved_attempts):
                raise EngineError(
                    f"{target!r}: production replayed the conflict case's last authored attempt "
                    f"again — attempt {len(starts) + 1} of a case authoring "
                    f"{len(resolved_attempts)}; a case whose final attempt fails states the "
                    "bound that leaves it unreplayed (m-case-format 'Conflict cases')"
                )
            starts.append(observed.database_calls)
            resolved = resolved_attempts[len(starts) - 1]
            nodes = _conflict_source_nodes(tx, model, target, resolved, observed)
            sources = [_conflict_source_node(target, write, nodes) for write in resolved]
            for write, node in zip(resolved, sources, strict=True):
                _refuse_unobserved_conflict_version(target, write, node)
            interfere()
            for write, node in zip(resolved, sources, strict=True):
                if mutation == "delete":
                    tx.wire.delete(node)
                else:
                    tx.wire.amend(node, _conflict_changes(model, write))
            return _landed_conflict_rows(resolved)  # the expectation machinery verified it

        observation_requiring = _versioned_non_temporal_version_attribute(model, target) is not None
        implied = _implied_shortfall_error(observation_requiring, concurrency, model, target)
        affected = _conflict_attempt_affected(database, requests, implied, body)
    if len(starts) != len(resolved_attempts):
        raise EngineError(
            f"{target!r}: production ended the conflict case's invocation after {len(starts)} "
            f"attempt(s), and the case authors {len(resolved_attempts)} (m-case-format "
            "'Conflict cases')"
        )
    calls = observed.calls
    writes = tuple(
        tuple(call.statement for call in calls[start:end] if call.kind == "write")
        for start, end in itertools.pairwise([*starts, len(calls)])
    )
    return writes, affected, len(calls)


def _refuse_a_locking_conflict_target(
    model: AcceptedMetamodel, target: str, concurrency: Concurrency
) -> None:
    """Refuse a conflict case whose target's Effective Concurrency Strategy is
    Locking, before any read.

    Its source read would take the shared row lock, so the concurrent writer the
    case stages could not commit between that read and the write: the case
    describes interference no client can meet (`m-case-format` "Conflict cases").
    """
    key = opt_lock.view(model).key(case_entity(model, target).identity)
    if opt_lock.effective_strategy(concurrency, key) == "locking":
        raise EngineError(
            f"{target!r}: a conflict case stages a writer that commits between the attempt's "
            "source read and its write, which only the Optimistic strategy leaves room for — "
            "under Locking that read holds the shared row lock the writer would wait on "
            "(m-case-format 'Conflict cases')"
        )


def _refuse_a_snapshot_level_under_a_staged_writer(case: case_format.Case) -> None:
    """Refuse a conflict case that stages a `given.apply` writer while its
    attempts resolve to a level stronger than Read Committed.

    The staged writer commits between the attempt's source read and its write.
    Above Read Committed that read fixes the attempt's snapshot, so the write
    meets the changed row as a serialization failure, or the writer waits on the
    read's shared lock, rather than leaving the zero-row shortfall the case
    grades (`m-case-format` "Conflict cases").
    """
    given = case.document.get("given")
    if not isinstance(given, Mapping) or "apply" not in cast("Mapping[str, object]", given):
        return
    level = case_format.effective_options(case).isolation
    if level == "read_committed":
        return
    raise EngineError(
        f"{case.path.name}: a conflict case stages a writer that commits between the "
        f"attempt's source read and its write, and at `{level.replace('_', '-')}` that read "
        "fixes the snapshot the write then conflicts with — only Read Committed leaves the "
        "zero-row shortfall the case grades (m-case-format 'Conflict cases')"
    )


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
    (`when.write`), or the `when.attempts` sequence production's own bounded
    retry loop replays — every attempt one physical attempt of ONE
    `db.transact` invocation, in order, each with its own statements (the
    case's own `0`-then-`1` retry-contract witness). The keyed UPDATE or DELETE
    `when.mutation` names writes every row of its `write` — one row, or the
    multi-key array whose rows the batching rule may collapse into a single
    set-based statement — through the public keyed Wire verb. A temporal target
    is refused: the conflict shape is non-temporal (`m-case-format`).

    Loads no fixtures itself (the caller's own lifecycle does, per
    `m-case-format`'s conflict-shape default). Each attempt reads its source
    inside itself, and `given.apply`'s concurrent writer commits BETWEEN the
    FIRST attempt's source read and the write that read licenses
    (:func:`~parallax.conformance._mechanism.given_state.apply_given_apply`),
    which is the ordering a conflict case describes: the state its write settles
    against is one a real read of that attempt observed, and the writer that
    invalidated it committed afterwards. A replay reads again, after the attempt
    before it rolled back, so it observes the state that writer left.

    Returns the ordered emissions, the FINAL attempt's affected-row count — the
    schema's one `affectedRows` slot, `m-conformance-adapter` — the resulting
    table state when the case authors `then.tableState`, and the Database Calls.
    """
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    lifecycle = lifecycle_run(lifecycle)
    when = case_document.when(case)
    concurrency = case_document.concurrency(case)
    _refuse_a_snapshot_level_under_a_staged_writer(case)
    target = first_declared_entity(case)
    if _is_temporal_entity(model, target):
        raise EngineError(
            f"{case.path.name}: {target!r} is temporal, and a conflict case's write targets a "
            "non-temporal Entity — a temporal write's race is an interleaved scenario "
            "(m-case-format 'Conflict cases')"
        )
    raw_attempts = when.get("attempts")
    attempts: list[tuple[str, Mapping[str, object]]] = (
        [
            (f"/when/attempts/{index}/write", attempt)
            for index, attempt in enumerate(cast("list[Mapping[str, object]]", raw_attempts))
        ]
        if isinstance(raw_attempts, list)
        else [("/when/write", when)]
    )
    _refuse_a_bound_short_of_the_authored_attempts(case, len(attempts))
    interfered = False

    def interfere() -> None:
        # The concurrent writer commits once, between the FIRST attempt's source
        # read and its write; every replay reads the state that writer left.
        nonlocal interfered
        if not interfered:
            interfered = True
            apply_given_apply(case, port)

    try:
        writes, affected, database_calls = _run_conflict_attempts(
            port,
            serving,
            model,
            case_format.database_options(case),
            target,
            concurrency,
            case_format.transaction_keywords(case),
            [_conflict_write_rows(attempt) for _pointer, attempt in attempts],
            _conflict_mutation(when),
            interfere,
            lifecycle,
        )
    except LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = [
        Emission(pointer, statement)
        for (pointer, _attempt), statements in zip(attempts, writes, strict=True)
        for statement in statements
    ]
    then = case.document.get("then")
    table_state = (
        read_table_state(port, model)
        if isinstance(then, Mapping) and "tableState" in then
        else None
    )
    # The Database Calls are every call this case put on the wire: each attempt's
    # own DML, summed across all of them rather than the last one's alone, and
    # the resolving read each attempt's write is licensed by. The read reaches
    # the database, so it counts exactly as the DML does (`m-case-format`
    # `then.databaseCalls`), and the lifecycle stream this count must agree with
    # holds it too.
    return emissions, affected, table_state, database_calls
