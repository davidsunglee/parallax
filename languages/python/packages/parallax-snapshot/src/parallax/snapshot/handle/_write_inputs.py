"""``parallax.snapshot.handle._write_inputs`` — verb-input preparation and evidence.

Everything a write verb needs BEFORE an instruction reaches the unit of work,
plus the write evidence a read leaves on the values it publishes:

* build-time window validation every keyed AND ``_where`` temporal verb shares
  (:func:`validate_valid_from`, :func:`validate_until`), the
  finite-Transaction-Time-pin refusal every keyed verb runs on its source
  instance (:class:`TransactionTimePinReadOnlyError`,
  :func:`validate_source_pin`, :func:`source_pin`), and the provenance refusal
  the value-taking keyed verbs run before any row is derived
  (:class:`KeyedWriteValueError`, :data:`KEYED_WRITE_VALUE_CODES`,
  :func:`validate_write_value`);
* instance -> accepted-Metadata resolution (:func:`metadata_of_instance`), the
  object a written value addresses (:func:`written_object_key`), and the
  codec-free reading of which object a value names (:func:`written_object`) that
  a decision taken BEFORE any row derivation has to use;
* the observation record a read leaves behind (:class:`ReadObservations`), its
  retention onto the source values that observed it (:func:`retain_evidence`,
  :data:`ReadSources`), the resolution a keyed verb runs over one such source
  (:func:`source_hint_of`, :func:`resolve_write_evidence`,
  :class:`WriteEvidenceError`,
  :data:`WRITE_EVIDENCE_CODES`), plus the per-row column contributions a
  materializing predicate-write resolve streams into its
  :class:`~parallax.core.unit_work.MaterializedWriteGroup`
  (:func:`is_no_op_assignment`, :func:`key_column_values`,
  :func:`predecessor_payload`), which share their payload extraction with
  :func:`retain_evidence` through the module-local ``_row_payload``.

Semantic family facts come from the accepted Metamodel and its facets, resolved
through :mod:`parallax.snapshot.handle._family` (the declaring root,
family-effective axes and primary key, version attribute). Every PHYSICAL column
instead comes from the row-owning Entity's Storage Layout view, which each entry
point resolves once and carries into the helpers that read or write a row's
columns. The read executor drives :class:`ReadObservations` and
:func:`retain_evidence` while its rows are live; the dependency goes that way and
only that way, so nothing here names :mod:`parallax.snapshot.handle._read`. The
participating unit of work reaches this module as the structural
:class:`ObservationLedger` — the two answers retention needs from a transaction,
rather than the whole scope.

Names crossing a module boundary (read from ``_transaction`` / ``_predicate_writes``)
are spelled bare; a helper whose every caller lives here keeps its underscore.
Privacy is carried by this MODULE's leading underscore and by the package's
frozen ``__all__``, never by per-name underscores —
:class:`TransactionTimePinReadOnlyError` and :func:`validate_source_pin` are
additionally re-exported through that ``__all__`` (the conformance engine's
scenario grading shares the exact validator the developer verbs run), as are
:class:`KeyedWriteValueError` and :data:`KEYED_WRITE_VALUE_CODES`, which a
developer catches from ``parallax.snapshot`` itself.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol, cast

from parallax.core import opt_lock
from parallax.core.base import normalize_instant
from parallax.core.db_port import Row
from parallax.core.document_codec import (
    mask_managed_members,
    occurrence_shape,
    reduce_declared_members,
)
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import lifecycle_state_of
from parallax.core.entity._declaration import declaration_of
from parallax.core.entity._entity import wire_names_of
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    PrimaryKey,
    TemporalDimension,
    ValueObjectMetadata,
)
from parallax.core.object_query import Latest
from parallax.core.storage_layout import EntityLayoutView
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    Concurrency,
    KeyedMutation,
    ObjectKey,
    ObservedStateKey,
    ParticipationToken,
    PredecessorRow,
    RetainedObservation,
    SourceHint,
    TemporalObservation,
    VersionObservation,
    WriteObservation,
    instant_literal,
    observed_state_key,
)
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle._family import (
    axis_columns,
    declaring,
    entity_layout,
    members,
    placed_members,
    slot_column,
    tx_time_axis,
    version_attribute,
)

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "WRITE_EVIDENCE_CODES",
    "KeyedWriteValueError",
    "ObservationLedger",
    "ReadObservations",
    "ReadSources",
    "TransactionTimePinReadOnlyError",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
    "WrittenObject",
    "is_no_op_assignment",
    "key_column_values",
    "metadata_of_instance",
    "normalize_assignment_values",
    "predecessor_payload",
    "resolve_write_evidence",
    "retain_evidence",
    "source_hint_of",
    "source_pin",
    "validate_source_pin",
    "validate_until",
    "validate_valid_from",
    "validate_write_value",
    "written_object",
    "written_object_key",
]

_UPDATE_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})
"""The keyed mutations that write against an existing row from a value's own
effective changes — the family a value no managed read produced is refused for.
:data:`~parallax.core.unit_work.INSERT_MUTATIONS` is the complementary family;
every other keyed mutation derives an identity row alone."""

KEYED_WRITE_VALUE_CODES: Final[frozenset[str]] = frozenset(
    {
        "write-value-not-stored",
        "write-value-already-stored",
        "write-value-foreign-lifecycle",
    }
)
"""The complete keyed-write value refusal vocabulary (`m-unit-work` "Write value
provenance"). The three name the three answers provenance has for a verb — no
managed read produced this value, this verb's own source produced it, another
managed source did — so a refused value carries exactly one of them."""


class KeyedWriteValueError(ValueError):
    """A keyed write verb was handed a value whose PROVENANCE it does not accept.

    A ``ValueError`` for :class:`TransactionTimePinReadOnlyError`'s reason, which
    is the sibling this shares a vocabulary with: both report a neutral
    application-lifecycle refusal of an argument a caller supplied, so a caller
    catching one kind of refused write value catches the other the same way.

    ``code`` is the neutral `m-unit-work` refusal and ``identity`` the Entity
    Identity the write addressed. The value itself is never retained: what the
    refusal is about is which source produced it, and the message names the verb
    that does accept it.
    """

    def __init__(self, *, code: str, message: str, identity: EntityIdentity) -> None:
        if code not in KEYED_WRITE_VALUE_CODES:
            raise ValueError(f"{code!r} is not a keyed write value code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.identity = identity


class TransactionTimePinReadOnlyError(ValueError):
    """A mutation verb's source view is pinned at a finite Transaction-Time
    instant (`m-temporal-read`'s finite-pin mutation row; `m-identity-map`):
    the Transaction-Time past records what the system knew and is never
    rewritten, so the verb refuses at the call — before any buffering — and
    emits no DML. This is the neutral application-lifecycle error the
    conformance contract reports as ``errorClass:
    transaction-time-pin-read-only`` (`m-conformance-adapter`), distinct from
    the `m-db-error` database taxonomy. A ``LATEST`` Transaction-Time pin and
    a finite Valid-Time pin stay writable — the Valid-Time case is the
    retroactive correction that lowers to the `m-bitemp-write` rectangle
    split."""

    code: Final[str] = "transaction-time-pin-read-only"


def _declared_primary_key(entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    """``entity``'s OWN declared primary key — used where ``entity`` is already
    the declaring root, so its local declaration IS the family key."""
    return tuple(
        attribute
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def _is_temporal(declaring_entity: EntityMetadata) -> bool:
    return bool(declaring_entity.declared_as_of_axes)


def _is_bitemporal(declaring_entity: EntityMetadata) -> bool:
    return declaring_entity.as_of_axis(TemporalDimension.VALID_TIME) is not None


def written_object_key(
    record: EntityMetadata, declaring_entity: EntityMetadata, row: Mapping[str, object]
) -> ObjectKey:
    """The object a WRITTEN instance addresses — the same
    :class:`~parallax.core.unit_work.ObjectKey`
    :func:`retain_evidence` names its hints by (the instance's OWN Entity
    Identity, never family-normalized; pk pairs by canonical attribute name, in
    the declaring entity's primary-key order) and `unit_work.object_key`
    computes at flush, so a verb-time refusal and the flush-time settle can
    never name the object two different ways.

    ``row`` is that instance's identity row as the Entity Row Codec derived it,
    passed in rather than derived here: this module owns the semantic family
    facts the key's ORDER comes from, and the codec owns what an Entity value's
    canonical primary key IS."""
    return ObjectKey(
        record.identity,
        tuple(
            (attr.identity.name, row[attr.identity.name])
            for attr in _declared_primary_key(declaring_entity)
        ),
    )


type WrittenObject = tuple[EntityIdentity, tuple[tuple[str, object], ...]]
"""Which object a written value names, as :func:`written_object` reads it — the
equivalence a same-transaction insert is recognized by, never a row and never an
:class:`~parallax.core.unit_work.ObjectKey`."""


def written_object(
    record: EntityMetadata, declaring_entity: EntityMetadata, value: EntityBase
) -> WrittenObject | None:
    """Which object ``value`` names, read straight off its primary-key members —
    or ``None`` when its own class carries no attribute for one of them.

    The counterpart of :func:`written_object_key` for the one question that must
    be answerable BEFORE a row exists: whether a value is one this transaction
    already buffered an insert of, which is what exempts it from the NotStored
    provenance refusal (`m-unit-work` *Write value provenance*). That refusal is
    decided before any row is derived, so the question may not be asked through
    the Entity Row Codec: a cross-model value whose class keys the same Entity by
    other members has no identity row to derive, and deriving one would answer
    the developer's mistaken provenance with an ``EntityRowError``. Such a value
    is no object this transaction inserted, which is exactly what ``None`` says
    and exactly what leaves the provenance refusal standing.

    Both sides of every comparison are read here, so members are compared as the
    value carries them rather than as a row would serialize them; nothing derived
    here addresses a row or reaches a codec.
    """
    names = wire_names_of(type(value))
    pairs: list[tuple[str, object]] = []
    for attribute in _declared_primary_key(declaring_entity):
        py_name = names.name_to_py.get(attribute.identity.name)
        if py_name is None:
            return None
        pairs.append((attribute.identity.name, getattr(value, py_name)))
    return (record.identity, tuple(pairs))


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    """One materialized row's observable state, keyed by PHYSICAL column.

    ``node`` is the graph-input projection this row converted into, which is how
    the evidence built from it reaches the value that projection becomes.
    ``entity`` is the row's own resolved concrete Entity. ``columns`` is every
    value the row materialized — the primary key, the version column, the axis
    bounds, and every other applicable member — which is what makes a
    Predecessor Row complete. ``document`` is the raw Structured Column under
    Relational Document Layout.

    It holds neither a raw driver row nor a materialized node, so an observation
    outlives the read that produced it without pinning either.
    """

    node: int
    entity: EntityIdentity
    columns: Mapping[str, object]
    document: object | None


class ReadObservations:
    """What one :func:`~parallax.snapshot.handle.find` collects for the write
    side while its rows are still live.

    Rows accumulate in the order the executor materializes them (root first,
    then each level in plan order), and :func:`retain_evidence` is the only
    consumer. Every graph-form read collects: a value's write evidence belongs
    to the value, so a standalone read produces sources exactly as a
    participating one does and differs only in the participation it can stamp.
    """

    __slots__ = ("_rows",)

    def __init__(self) -> None:
        self._rows: list[_ObservedRow] = []

    def observe_row(
        self,
        node: int,
        entity: EntityIdentity,
        columns: Mapping[str, object],
        document: object | None,
    ) -> None:
        """Snapshot one materialized row's observable state. ``columns`` stays the
        caller's, so a later edit to it cannot reach the recorded observation."""
        self._rows.append(_ObservedRow(node, entity, dict(columns), document))

    @property
    def rows(self) -> Sequence[_ObservedRow]:
        """Every row observed so far, in materialization order."""
        return self._rows


type ReadSources = Mapping[int, SourceHint]
"""The Source Hint each observed projection's value carries, keyed by that
projection's own index in the read's Snapshot Graph Input.

Only the executor can build this pairing: it alone holds the row and the
projection it converted into at the same time, and by the time a materializer
builds the value the row is gone."""


class ObservationLedger(Protocol):
    """The unit of work an observing read files into, satisfied structurally.

    ``find`` needs exactly two things from a transaction — the participation its
    reads stamp, and the chance to answer evidence it already holds for a state
    this read saw again — so it names those two rather than the whole scope. A
    standalone read passes none of it.
    """

    @property
    def participation(self) -> ParticipationToken: ...

    def retain(self, observation: RetainedObservation, /) -> RetainedObservation: ...


def retain_evidence(
    meta: Metamodel, observations: ReadObservations, *, ledger: ObservationLedger | None
) -> ReadSources:
    """Retain the observed version/temporal-milestone of every VERSIONED or
    TEMPORAL row :func:`find` materialized, onto the values that observed them
    (`m-opt-lock`; ADR 0013; `m-unit-work` "Observation lifetime").

    Evidence is addressed by the exact state it is about
    (:func:`~parallax.core.unit_work.observed_state_key`), so a second read of
    one primary key that resolves to a DIFFERENT version or milestone is
    evidence about the row it actually saw rather than an overwrite of the first
    read's, and a live value keeps the state IT observed however often the row
    is read again. The identity half is the SAME
    :class:`~parallax.core.unit_work.ObjectKey` a subsequent keyed write's own
    :func:`~parallax.core.unit_work.object_key` computes — the Entity here is the
    row's OWN resolved concrete Entity (never family-normalized to the root),
    which is what a developer's later ``tx.update(copy)`` resolves its instance's
    own class to; the coordinate half is derived from the observation itself.

    Every observed row also yields a Source Hint, including an UNVERSIONED
    Non-Temporal row, which observes no state: what its hint carries is the
    object it denotes and the participation its read licensed, which is the whole
    of what an effective-Locking write asks of it. A row whose (family-effective)
    primary key, version column, or Transaction-Time interval is absent from its
    own observed columns is defensively skipped — never reachable for a
    well-formed corpus model, but this seam takes no data on faith. A versioned
    entity is never also temporal (`m-opt-lock`/`m-descriptor`: the two are
    mutually exclusive), so each row takes exactly one branch.

    The statement's own as-of coordinates are deliberately NOT recorded. What a
    write settles against is the state its value came from, and that state is
    what the key names; the pin that selected it is a property of the read, so
    two pins selecting one milestone retain one indistinguishable piece of
    evidence.

    ``find`` is always INSTANCE-form, which projects every applicable Column, so
    an observed row's columns are the COMPLETE persisted row a Predecessor Row
    requires. Under Relational Document Layout the read ALSO carried the row's raw
    Structured Column past the fan-out that decoded those members, and a temporal
    observation retains it (`m-unit-work`) so a successor is patched from what the
    row held rather than rebuilt from the members this model declares — at no
    extra query, because the predecessor read already materialized it.

    ``ledger`` is the participating unit of work, absent for a standalone read.
    Its two answers are the participation each hint carries and the evidence it
    already holds for a state this read saw again; a standalone read stamps no
    participation and shares nothing beyond this one pass.
    """
    participation = None if ledger is None else ledger.participation
    hints: dict[int, SourceHint] = {}
    # One observed state, one retained observation within this pass, so two
    # projections of one row answer one claim exactly as graph aliases do.
    pass_states: dict[ObservedStateKey, RetainedObservation] = {}
    for observed in observations.rows:
        resolved = _observed_object(meta, observed)
        if resolved is None:  # pragma: no cover - defends a malformed model/projection
            continue
        object_key, declaring_entity, observation = resolved
        if observation is None:
            hints[observed.node] = SourceHint(observed.entity, object_key, participation, None)
            continue
        key = observed_state_key(object_key, observation, declaring_entity)
        held = pass_states.get(key)
        if held is None:
            held = RetainedObservation(key, observation, participation)
            if ledger is not None:
                held = ledger.retain(held)
            pass_states[key] = held
        hints[observed.node] = SourceHint(observed.entity, object_key, participation, held)
    return MappingProxyType(hints)


def _observed_object(
    meta: Metamodel, observed: _ObservedRow
) -> tuple[ObjectKey, EntityMetadata, WriteObservation | None] | None:
    """One observed row's object, its declaring root, and the evidence it
    observed — or ``None`` where the row cannot be read as an object at all.

    The evidence is absent for an unversioned Non-Temporal row, which observes
    no state; the object and the declaring root are answered either way, because
    a hint names the object whether or not a state stands behind it.
    """
    observed_fields = observed.columns
    entity = meta.entity(observed.entity)
    if entity is None:  # pragma: no cover - a materialized row resolved within this model
        return None
    declaring_entity = declaring(meta, entity)
    layout = entity_layout(meta, entity)
    if layout is None:  # pragma: no cover - a materialized node always owns rows
        return None
    pk_attrs = _declared_primary_key(declaring_entity)
    pk_columns = [slot_column(layout, attr.identity) for attr in pk_attrs]
    if not pk_attrs or any(  # pragma: no cover - defends a malformed model/projection
        column not in observed_fields for column in pk_columns
    ):
        return None
    object_key = ObjectKey(
        observed.entity,
        tuple(
            (attr.identity.name, observed_fields[column])
            for attr, column in zip(pk_attrs, pk_columns, strict=True)
        ),
    )
    version_attr = version_attribute(meta, declaring_entity)
    if version_attr is not None:
        version_column = slot_column(layout, version_attr.identity)
        if version_column not in observed_fields:  # pragma: no cover - malformed projection
            return object_key, declaring_entity, None
        return (
            object_key,
            declaring_entity,
            VersionObservation(observed_version=cast("int", observed_fields[version_column])),
        )
    if not _is_temporal(declaring_entity):
        return object_key, declaring_entity, None
    tx_axis = tx_time_axis(declaring_entity)
    tx_start_column, _tx_end_column = axis_columns(layout, tx_axis)
    if tx_start_column not in observed_fields:  # pragma: no cover - malformed model/projection
        return object_key, declaring_entity, None
    return (
        object_key,
        declaring_entity,
        _temporal_observation(
            members(placed_members(meta, entity, layout)), observed_fields, observed.document
        ),
    )


type WriteEvidenceErrorCode = Literal["write-evidence-unavailable", "write-evidence-consumed"]
"""The write-evidence refusals a keyed verb raises.

The two partition what can be wrong with a source's evidence at the verb: there
is none the target Entity's Effective Concurrency Strategy can use, or the
evidence there is has been spent. A conflict the database discovers later is a
different thing entirely and keeps its own flush-time classification.
"""

WRITE_EVIDENCE_CODES: Final[frozenset[str]] = frozenset(
    {"write-evidence-unavailable", "write-evidence-consumed"}
)
"""The complete set of codes :class:`WriteEvidenceError` currently carries."""


class WriteEvidenceError(LookupError):
    """A keyed write verb was handed a source whose write evidence it cannot use.

    A ``LookupError`` because every code reports that the evidence the write
    needs is not there to be found: never recorded for this source, or recorded
    and already spent. ``object_key`` is the object the write addressed, always
    visible so a caller can say WHICH write was refused; the Source Hint and the
    Observed State Key behind it stay implementation state.

    Raised synchronously at the verb, before any buffering and before any
    database access. A conflict the database discovers later is a different
    thing entirely and keeps its own flush-time classification.
    """

    def __init__(
        self, *, code: WriteEvidenceErrorCode, message: str, object_key: ObjectKey
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code: Final = code
        self.message: Final = message
        self.object_key: Final = object_key


def source_hint_of(instance: object) -> SourceHint | None:
    """The private :class:`~parallax.core.unit_work.SourceHint` ``instance``
    carries, or ``None`` for a value no Parallax read produced.

    An edited copy answers the node's own hint, because an edit preserves every
    kind of instance state outside the declared members (``Entity.edit``) — which
    is what lets a developer read a row, change what they read, and write back
    against the state they read. A value another framework-managed source
    produced answers ``None`` here: its lifecycle state is that source's own, so
    this lifecycle recognizes no hint on it.
    """
    state = snapshot_state_of(instance)
    return None if state is None else state.source


def resolve_write_evidence(
    meta: Metamodel,
    record: EntityMetadata,
    declaring_entity: EntityMetadata,
    hint: SourceHint | None,
    *,
    object_key: ObjectKey,
    preference: Concurrency,
    participation: ParticipationToken,
) -> RetainedObservation | None:
    """The evidence a keyed write against existing state settles against, read
    off the source value's own hint.

    One resolution serves the address, the gate, and the version advance, which
    is what makes it impossible for them to disagree. It follows the target
    Entity's Effective Concurrency Strategy (`m-opt-lock`), not the transaction's
    preference:

    * **Locking** — the license is the shared row lock, so the source read must
      have run in THIS transaction. A source from another scope, or none at all,
      proves no held lock.
    * **Optimistic** — the license is the database gate, so the retained
      observation IS the evidence and a standalone ``db.find`` source carries it
      exactly as a participating read's does.

    Evidence a successful flush already spent is refused under BOTH strategies
    (:func:`_refuse_consumed`).

    Absence stays structural: a target that observes no state resolves to
    ``None`` and buffers bare.
    """
    strategy = opt_lock.effective_strategy(preference, opt_lock.view(meta).key(record.identity))
    observation = None if hint is None else hint.observation
    if strategy == "locking":
        if _observes_a_state(meta, declaring_entity) and (
            hint is None or hint.participation is not participation
        ):
            raise WriteEvidenceError(
                code="write-evidence-unavailable",
                message=(
                    f"{record.identity.canonical}: the Locking strategy licenses this write "
                    "through the shared row lock a read of THIS transaction holds, and the "
                    "value handed to the verb came from no such read; read the row through "
                    "this transaction and write what that read returned"
                ),
                object_key=object_key,
            )
        _refuse_consumed(record, observation, object_key)
        return observation
    if observation is None:
        raise WriteEvidenceError(
            code="write-evidence-unavailable",
            message=(
                f"{record.identity.canonical}: the Optimistic strategy gates this write on the "
                "state its source observed, and the value handed to the verb carries no "
                "retained observation; read the row through a `find` and write what it returned"
            ),
            object_key=object_key,
        )
    _refuse_consumed(record, observation, object_key)
    return observation


def _refuse_consumed(
    record: EntityMetadata, observation: RetainedObservation | None, object_key: ObjectKey
) -> None:
    """Refuse evidence a successful flush already spent (`m-unit-work` "A
    successful flush consumes").

    Strategy-independent, because what consumption says is that the state the
    value observed is no longer the stored state: this unit of work's own write
    moved the row on. A held shared row lock does not restore it — the Locking
    source's own write is what retired it — so a second write off the same
    source is refused under Locking exactly as under Optimistic, and the caller
    reads again.
    """
    if observation is None or not observation.consumed:
        return
    raise WriteEvidenceError(
        code="write-evidence-consumed",
        message=(
            f"{record.identity.canonical}: the state this value observed was already "
            "written by a flush of this unit of work, so its evidence is spent; read the "
            "row again and write what that read returns"
        ),
        object_key=object_key,
    )


def _observes_a_state(meta: Metamodel, declaring_entity: EntityMetadata) -> bool:
    """Whether a read of this family observes a state at all — a versioned or
    temporal target, never an unversioned Non-Temporal one."""
    return version_attribute(meta, declaring_entity) is not None or _is_temporal(declaring_entity)


def _temporal_observation(
    member_columns: Mapping[str, tuple[str, bool]],
    fields: Mapping[str, object],
    document: object | None = None,
) -> TemporalObservation:
    """The :class:`TemporalObservation` a materialized TEMPORAL row licenses: its
    complete Predecessor Row.

    The Predecessor Row retains EVERY applicable member ``fields`` carries —
    scalars, value-object documents, the primary key, and both axis intervals —
    because temporal expansion carries members the authored mutation never
    mentioned, and because the close's own address and gate are read off the same
    observed row rather than from separate per-axis fields. The bounds are the
    only members every consumer names; the rest ride through as the payload a
    chained or split successor carries forward (`m-bitemp-write` "head/tail old
    values"; `m-value-object` "the document rides every chained/split row
    whole").

    ``fields`` is a plain column-keyed mapping — one materialized row's own
    observable columns, documents decoded
    (:func:`~parallax.snapshot.materialize.observable_columns`, a real
    ``Transaction.find``), or one resolved row of a materializing predicate-write
    resolve (:func:`predecessor_payload`) — so both callers share the SAME
    extraction rather than duplicating it. Extraction renders nothing of its own:
    every value passes through EXACTLY as ``fields`` carries it, which for a
    scalar or interval column is exactly what the port returned (a real
    ``timestamptz`` column may be a driver-native ``datetime.datetime`` or the
    native-infinity sentinel, never pre-rendered to a wire string here) — the
    SAME driver-native-passthrough contract every other temporal bind in this
    seam already carries; wire-rendering for REPORTING is the conformance ADAPTER's
    own boundary concern (`parallax.conformance.engine._json_bind`), never this
    seam's.

    ``document`` is the row's raw Structured Column under Relational Document
    Layout, which the Predecessor Row retains beside — never among — those
    members, so a successor built from it keeps keys no member declares. It is
    absent under `Columns` layout, where the row has no such column.
    """
    return TemporalObservation(
        predecessor=PredecessorRow(
            _row_payload(member_columns, fields, include_value_objects=True), document=document
        )
    )


def _row_payload(
    member_columns: Mapping[str, tuple[str, bool]],
    fields: Mapping[str, object],
    excluded: frozenset[str] = frozenset(),
    *,
    include_value_objects: bool = False,
) -> dict[str, object]:
    """``fields``'s own payload (every applicable member besides ``excluded``
    columns) — the extraction a real TEMPORAL find's Predecessor Row
    (`_temporal_observation`, above) and a materializing resolve's own
    Predecessor Row (:func:`predecessor_payload`) share. A Predecessor Row
    excludes nothing; a caller excluding the axis bounds its own milestone plan
    stamps afresh names them.

    Value-object members are OMITTED by default (a plain row-form read projects
    no `Document` slot, `m-sql` *Read projection*). ``include_value_objects``
    opts in, and both callers are observation-side: `_temporal_observation`
    (every real ``Transaction.find``, always INSTANCE-form, and every
    materializing resolve on a temporal target, whose own projection carries
    every declared document so the Predecessor Row is complete) and
    `predecessor_payload` (that same resolve). ``column in fields`` still gates
    every member exactly as it does for scalars; a VO-free entity's empty
    value-object half makes this flag a no-op either way.
    """
    return {
        name: fields[column]
        for name, (column, is_value_object) in member_columns.items()
        if (include_value_objects or not is_value_object)
        and column in fields
        and column not in excluded
    }


# --------------------------------------------------------------------------- #
# Predicate-write materialization (m-opt-lock                                 #
# "Predicate-selected writes materialize when observations are needed";       #
# ADR 0014) — plus the build-time window/no-op validators every keyed AND     #
# `_where` temporal verb shares (`validate_valid_from` / `validate_until`).   #
# `is_no_op_assignment` / `key_column_values` / `predecessor_payload` below   #
# are pure per-row functions the SOLE caller                                  #
# (`_predicate_writes._materialize_predicate_write`) drives against its OWN   #
# resolved rows while streaming them into column builders — never an         #
# implicit read of their own, and never a merged per-row dict of their own.   #
# --------------------------------------------------------------------------- #
def source_pin(instance: object) -> Pin | None:
    """The whole-graph as-of :class:`Pin` a materialized snapshot node carries,
    or ``None`` for anything else — a plainly constructed instance, or an edit
    of one.

    An edited copy of a NODE answers the node's own pin: an edit preserves every
    kind of instance state outside the declared members, lifecycle state among
    them (``Entity.edit``), so the write a developer derives from a pinned view
    is refused exactly as a write of the view itself is. What a value answers
    here is therefore its provenance, not its editedness."""
    state = snapshot_state_of(instance)
    return None if state is None else state.pin


def validate_source_pin(identity: EntityIdentity, pin: Pin | None) -> None:
    """Reject a mutation sourced from a view pinned at a FINITE Transaction-Time
    instant (`m-temporal-read`'s finite-pin mutation row): raise
    :class:`TransactionTimePinReadOnlyError` at the verb call, before any
    buffering, so no DML is ever emitted. An absent pin, a ``LATEST``
    Transaction-Time pin, and a finite Valid-Time pin all pass — the finite
    Valid-Time pin is the writable retroactive correction (`m-bitemp-write`).
    Shared by every keyed developer verb (`_prepare_keyed_write` / ``delete``)
    and the conformance engine's scenario ``mutate`` grading, so the two
    callers can never drift. The predicate-selected ``_where`` family needs no
    counterpart: a set-based write target must be a bare statement, so it can
    never carry an as-of pin at all.

    Takes the written Entity's structured ``identity`` rather than a spelling:
    no layer of the keyed-write path holds an Entity spelling, and the message
    reports the canonical one the identity renders."""
    if pin is None:
        return
    tx_time = pin.tx_time
    if tx_time is None or isinstance(tx_time, Latest):
        return
    raise TransactionTimePinReadOnlyError(
        f"{identity.canonical}: the write's source view is pinned at the finite "
        f"Transaction-Time instant {tx_time.isoformat()} and is read-only — the "
        "Transaction-Time past records what the system knew and is never rewritten "
        "(transaction-time-pin-read-only); read the current milestone "
        "(Transaction Time Latest) to mutate it"
    )


def validate_write_value(
    identity: EntityIdentity,
    value: EntityBase,
    mutation: KeyedMutation,
    *,
    inserted_here: Callable[[], bool],
) -> None:
    """Refuse a value whose PROVENANCE ``mutation``'s verb does not accept
    (`m-unit-work` "Write value provenance"), before any row is derived from it.

    Provenance is which framework-managed source, if any, produced the value from
    a read — never whether an author has since changed it, which decides what a
    write CONTAINS rather than which verb accepts it. The three answers partition
    the values a verb can be handed, so a refused value earns exactly one code and
    the message names the verb that does accept it.

    An unedited value this source produced is NOT refused for an `update`: it
    carries no change, so it buffers nothing, issues no statement, and raises
    nothing — the same outcome as an edit whose net change is empty.
    ``delete`` / ``terminate`` / ``terminateUntil`` derive an identity row alone
    and fall through, exactly as they already do for ``valid_from``.

    ``inserted_here`` answers whether the writing unit of work has ALREADY
    buffered an insert of this object, and its ``True`` exempts a value from the
    NotStored refusal: a row this transaction inserted is a row it stores, so the
    update that follows carries the final value the flush writes rather than
    addressing nothing (`m-unit-work` "Insert-then-update coalesces in place").
    It is consulted only on the branch that would otherwise refuse, so an
    accepted value never pays for it, and it answers from what the value itself
    names (:func:`written_object`) rather than from a row, so a value whose class
    can key no row still reaches THIS refusal rather than an
    :class:`~parallax.core.entity.EntityRowError` raised on its behalf.

    Provenance is read through :func:`~parallax.snapshot._inspection.
    snapshot_state_of` and the un-narrowed
    :func:`~parallax.core.entity.lifecycle_state_of`, never through a value's
    private state: the narrowed answer says this Snapshot lifecycle produced the
    value, and the un-narrowed one is what distinguishes ANOTHER framework-managed
    source's value from one no managed read produced at all.
    """
    if mutation not in _UPDATE_MUTATIONS and mutation not in INSERT_MUTATIONS:
        return
    state = lifecycle_state_of(value)
    if state is None:
        if mutation in INSERT_MUTATIONS or inserted_here():
            return
        raise KeyedWriteValueError(
            code="write-value-not-stored",
            message=(
                f"{identity.canonical}: {mutation!r} was handed a value no read of this "
                "store produced, so it addresses no stored row; write it with "
                "`tx.insert(...)`, or update a value a `find` returned"
            ),
            identity=identity,
        )
    if snapshot_state_of(value) is None:
        raise KeyedWriteValueError(
            code="write-value-foreign-lifecycle",
            message=(
                f"{identity.canonical}: {mutation!r} was handed a value another "
                "framework-managed source produced, and no verb writes another source's "
                "value through this one; read the row through this transaction and write "
                "what that read returns"
            ),
            identity=identity,
        )
    if mutation in INSERT_MUTATIONS:
        raise KeyedWriteValueError(
            code="write-value-already-stored",
            message=(
                f"{identity.canonical}: {mutation!r} was handed a value this store's own read "
                "produced, so the row it names is already stored; change it with "
                "`value.edit(...)` and write it with `tx.update(...)`"
            ),
            identity=identity,
        )


def validate_valid_from(
    declaring_entity: EntityMetadata, mutation: KeyedMutation, valid_from: dt.datetime | None
) -> str | None:
    """Validate and render a write verb's ``valid_from`` (`python.md` §5):
    a Bitemporal target requires it (the mutation's own Valid-Time instant
    ``B``, `m-bitemp-write` "Plain (unbounded) bitemporal writes"); a
    non-temporal or Transaction-Time-Only target takes none."""
    name = declaring_entity.identity.name
    if _is_bitemporal(declaring_entity):
        if valid_from is None:
            raise ValueError(
                f"{name}: a bitemporal {mutation!r} requires valid_from "
                "(the mutation's own Valid-Time instant)"
            )
        return instant_literal(valid_from)
    if valid_from is not None:
        shape = "a Transaction-Time-Only" if _is_temporal(declaring_entity) else "a non-temporal"
        raise ValueError(
            f"{name}: {shape} {mutation!r} takes no valid_from "
            f"({name!r} declares no Valid-Time dimension to bound)"
        )
    return None


def validate_until(
    declaring_entity: EntityMetadata,
    mutation: KeyedMutation,
    valid_from: dt.datetime,
    until: dt.datetime,
) -> str:
    """Validate + render a ``*Until`` verb's window bound (`python.md` §5:
    "both aware-UTC-microsecond datetimes, all validated at build" ... "the
    `*_until` trio additionally requires `until`, with `valid_from <
    until` ... all validated at build"): reject an equal or reversed window
    — ``until`` must be strictly later than ``valid_from`` — at the verb
    call, before any buffering (never at flush time). Shared by every keyed
    AND ``_where`` ``*Until`` verb (``update_until`` / ``terminate_until`` /
    ``update_until_where`` / ``terminate_until_where``) — one validator,
    so none of the four can drift
    from the others.

    NORMALIZES both bounds BEFORE comparing them: comparing raw,
    un-normalized datetimes let a naive ``until``
    (compared against an already-aware ``valid_from``, since
    ``validate_valid_from`` — this verb's own sibling, called first —
    already normalizes/rejects a naive ``valid_from``) leak a bare
    ``TypeError`` from the ``<=`` comparison itself, rather than the proper
    ``ValueError`` :func:`~parallax.core.base.normalize_instant` raises for
    any naive datetime (mirroring ``validate_valid_from``'s own
    ``instant_literal``-based handling exactly)."""
    valid_from_normalized = normalize_instant(valid_from)
    until_normalized = normalize_instant(until)
    if until_normalized <= valid_from_normalized:
        raise ValueError(
            f"{declaring_entity.identity.name}: {mutation!r} requires valid_from < until "
            f"(python.md §5) — got valid_from={valid_from!r}, until={until!r}"
        )
    return until_normalized.isoformat()


def normalize_assignment_values(
    assignments: Mapping[str, object],
    occurrences: Mapping[str, ValueObjectMetadata] | None = None,
) -> dict[str, object]:
    """Decode each encoded occurrence assignment once into its managed value.

    Scalar assignments already carry managed values. A ``one`` keeps the caller's
    authored-member mask, while a ``many`` decodes every replacement element whole.
    The returned mapping is reusable across every row resolved by one predicate write.
    """
    occurrence_index: Mapping[str, ValueObjectMetadata] = (
        cast("Mapping[str, ValueObjectMetadata]", {}) if occurrences is None else occurrences
    )
    normalized: dict[str, object] = {}
    for member, value in assignments.items():
        occurrence = occurrence_index.get(member)
        if occurrence is None:
            normalized[member] = value
            continue
        shape = occurrence_shape(occurrence)
        if occurrence.multiplicity is Multiplicity.MANY:
            encoded = list(cast("tuple[object, ...]", value)) if isinstance(value, tuple) else value
            normalized[member] = [
                reduce_declared_members(shape, element, named_by=element)
                for element in cast("Sequence[object]", encoded)
            ]
        else:
            normalized[member] = reduce_declared_members(shape, value, named_by=value)
    return normalized


def is_no_op_assignment(
    member_columns: Mapping[str, tuple[str, bool]],
    assignments: Mapping[str, object],
    row: Row,
    occurrences: Mapping[str, ValueObjectMetadata] | None = None,
) -> bool:
    """Whether EVERY assigned member's new value already equals ``row``'s own
    (`m-opt-lock` per-row no-op elimination — structural equality, the SAME
    comparison a keyed no-op's effective-change-set test uses).

    ``row`` is one resolved row of the write's own resolving read, after that
    read's row transform: a document-mapped member is compared against the value
    the fan-out decoded, in its declared Neutral Type, rather than against a
    fragment of the raw Structured Column. An absent Document Path and an
    explicit JSON null both decode to ``None``, which is the one logical
    not-present state a NULL Column also carries, so a member assigned ``None``
    is a no-op in either spelling.

    ``assignments`` has already crossed :func:`normalize_assignment_values` once
    for the whole predicate write. A ``one`` comparison applies that codec-owned
    authored-member mask to the managed row; a ``many`` compares its whole ordered
    replacement without decoding either side again.

    This is the ONE narrow result-dependent normalization a materializing
    resolve performs while streaming: a resolved row an assignment-bearing
    verb would leave unchanged never joins its Materialized Write Group.
    ``delete`` / ``terminate`` / ``terminateUntil`` have no assignments to
    compare and therefore never call this — every resolved row is retained.
    """
    occurrence_index: Mapping[str, ValueObjectMetadata] = (
        cast("Mapping[str, ValueObjectMetadata]", {}) if occurrences is None else occurrences
    )
    for member, value in assignments.items():
        stored = row.get(member_columns[member][0])
        occurrence = occurrence_index.get(member)
        if occurrence is None:
            compared = stored
        elif occurrence.multiplicity is Multiplicity.MANY:
            compared = (
                list(cast("tuple[object, ...]", stored)) if isinstance(stored, tuple) else stored
            )
        else:
            compared = mask_managed_members(stored, value)
        if value != compared:
            return False
    return True


def key_column_values(
    pk_attrs: Sequence[AttributeMetadata], layout: EntityLayoutView, row: Row
) -> tuple[object, ...]:
    """One resolved row's aligned primary-key value tuple, in ``pk_attrs``
    order — a Materialized Write Group's own per-row key-column contribution.
    """
    return tuple(row[slot_column(layout, attr.identity)] for attr in pk_attrs)


def predecessor_payload(
    member_columns: Mapping[str, tuple[str, bool]], row: Row
) -> dict[str, object]:
    """One resolved row's COMPLETE Predecessor Row payload — every applicable
    member, value-object documents included — the SAME complete extraction
    :func:`retain_evidence` retains for a real find (`m-unit-work` "A
    Predecessor Row is the complete, immutable persisted state"), applied to a
    materializing resolve's own row-form row. A materializing resolve reads
    the CURRENT milestone by construction, so every predecessor it retains is
    latest-pinned.
    """
    return _row_payload(member_columns, row, include_value_objects=True)


def metadata_of_instance(meta: Metamodel, instance: EntityBase) -> EntityMetadata:
    """``instance``'s accepted Entity Metadata within ``meta``, or a loud
    ``TypeError`` when the connected model declares no such Entity.

    Membership is decided by the Entity Identity the instance's class declares:
    one class participates in any number of models, so belonging is a question
    about this model rather than about the class. What a shared identity cannot
    settle — whether a foreign class's MEMBERS are this model's — is settled one
    layer down and unchanged: every keyed write still routes ``deserialize`` ->
    ``validate_write`` -> ``validate_instruction`` against the connected model,
    where member-name honesty and the declared-type walk reject a foreign
    instance's row.
    """
    cls = type(instance)
    metadata = meta.entity(declaration_of(cls).identity)
    if metadata is None:
        raise TypeError(f"{cls.__name__} is not an Entity Class of this model")
    return metadata
