"""``parallax.snapshot.handle._write_inputs`` — verb-input preparation and evidence.

Everything a keyed write needs from the moment a verb is called to the moment
the buffer holds it, plus the write evidence a read leaves on the values it
publishes. Both keyed ingresses — the Typed verbs and ``tx.wire``'s — reach the
whole of it, which is what keeps one judgement and one buffer behind two
representations:

* build-time window validation every keyed AND ``_where`` temporal verb shares
  (:func:`validate_window`), the
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
  :data:`WRITE_EVIDENCE_CODES`), the claim that verb then takes at the scope it
  settles against (:func:`admit_write_claim`, :class:`ClaimLedger`), plus the
  per-row column contributions a
  materializing predicate-write resolve streams into its
  :class:`~parallax.core.unit_work.MaterializedWriteGroup`
  (:func:`is_no_op_assignment`, :func:`key_column_values`,
  :func:`predecessor_payload`), which share their payload extraction with
  :func:`retain_evidence` through the module-local ``_row_payload``;
* the keyed seam itself, in the order every ingress runs it: the canonical
  single-row instruction a verb holding a value builds
  (:func:`keyed_instruction`), the whole judgement it is then measured by
  (:func:`validate_keyed_instruction`), the claim-then-buffer step that ends it
  (:func:`admit_and_buffer`, :func:`instruction_identity`), the question a
  wholly restoring edit asks before it decides whether it cancels anything
  (:func:`cancels_a_pending_assignment`), and the read-your-own-writes ledger
  both ingresses record into and read (:class:`BufferedInserts`,
  :func:`written_object_of_row`).

Semantic family facts come from the accepted Metamodel and its facets, resolved
through :mod:`parallax.snapshot.handle._family` (the declaring root,
family-effective axes and primary key, version attribute). Every PHYSICAL column
instead comes from the row-owning Entity's Storage Layout view, which each entry
point resolves once and carries into the helpers that read or write a row's
columns. The read executor drives :class:`ReadObservations` and
:func:`retain_evidence` while its rows are live; the dependency goes that way and
only that way, so nothing here names :mod:`parallax.snapshot.handle._read`. The
participating unit of work reaches this module as two structural protocols —
:class:`ObservationLedger`, the two answers retention needs from a transaction,
and :class:`ClaimLedger`, the three a keyed write needs — rather than as the
whole scope.

Names crossing a module boundary (read from ``_transaction``, ``_wire_writes``,
or ``_predicate_writes``) are spelled bare; a helper whose every caller lives
here keeps its underscore.
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
from parallax.core.base import TIMESTAMP, InstantError, normalize_instant
from parallax.core.db_port import Row
from parallax.core.document_codec import occurrence_shape, reduce_declared_members
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
    entity_by_name,
)
from parallax.core.object_query import Latest
from parallax.core.storage_layout import EntityLayoutView
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    BOUNDED_MUTATIONS,
    INSERT_MUTATIONS,
    BufferItem,
    ClaimScope,
    ClaimVerdict,
    Concurrency,
    KeyedMutation,
    KeyedWrite,
    ObjectKey,
    ObservedStateKey,
    ParticipationToken,
    PredecessorRow,
    PreparedKeyedWrite,
    RetainedObservation,
    SettledEvidence,
    SourceHint,
    TemporalObservation,
    VersionObservation,
    WriteIntent,
    WriteObservation,
    buffered_write,
    claim_scope,
    claimed_object,
    instructions,
    keyed_intent,
    observed_state_key,
    validate_write,
)
from parallax.core.wire import encode_wire
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
    "BufferedInserts",
    "ClaimLedger",
    "KeyedWriteValueError",
    "ObservationLedger",
    "ReadObservations",
    "ReadSources",
    "TransactionTimePinReadOnlyError",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
    "WrittenObject",
    "admit_and_buffer",
    "admit_write_claim",
    "cancels_a_pending_assignment",
    "instruction_identity",
    "is_no_op_assignment",
    "key_column_values",
    "keyed_instruction",
    "metadata_of_instance",
    "normalize_assignment_values",
    "predecessor_payload",
    "resolve_write_evidence",
    "retain_evidence",
    "source_hint_of",
    "source_pin",
    "validate_keyed_instruction",
    "validate_source_pin",
    "validate_window",
    "validate_write_value",
    "written_object",
    "written_object_key",
    "written_object_of_row",
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


def written_object_of_row(
    record: EntityMetadata, declaring_entity: EntityMetadata, row: Mapping[str, object]
) -> WrittenObject | None:
    """Which object a written ROW names — :func:`written_object`'s peer for an
    ingress holding a row rather than an Entity value.

    A Wire verb never holds an instance, so the read-your-own-writes exemption
    has to be answerable from the canonical row an insert buffers. Both readings
    key by the SAME declared primary-key members in the SAME declaring-entity
    order and carry the values as the caller supplied them, so a Typed insert and
    a Wire update of one object name one member of
    :class:`BufferedInserts` — which is what makes the exemption span both
    representations rather than one each.

    ``None`` for a row short of a primary-key member, which names no object at
    all. Defensive rather than reachable: an insert's row is judged complete
    before this is asked, and a keyed write's identity row comes from the object
    key its source's own read filed.
    """
    pairs: list[tuple[str, object]] = []
    for attribute in _declared_primary_key(declaring_entity):
        name = attribute.identity.name
        if name not in row:  # pragma: no cover - both callers hold a complete key already
            return None
        pairs.append((name, row[name]))
    return (record.identity, tuple(pairs))


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    """One materialized row's observable state, keyed by PHYSICAL column.

    ``node`` is the graph projection this row converted into, which is how
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
projection's own index in the read's sealed graph.

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


class ClaimLedger(Protocol):
    """The unit of work a keyed write settles into, satisfied structurally.

    Three answers, and nothing wider: what a new intent becomes against whatever
    the buffer already claimed at that exact scope, what it already claims there
    (which is what a restoring edit asks before it decides whether it has
    anything to cancel), and the buffer itself. Naming them rather than the whole
    scope is what lets both keyed ingresses share one seam without either
    reaching into a transaction.
    """

    def claim(self, key: ClaimScope, intent: WriteIntent, /) -> ClaimVerdict: ...

    def claimed(self, key: ClaimScope, /) -> WriteIntent | None: ...

    def buffer(self, item: BufferItem, /) -> None: ...


class BufferedInserts:
    """The objects one transaction has buffered an insert of.

    Shared by BOTH keyed ingresses rather than kept per representation: a
    Typed insert followed by a Wire update of the same object is one
    read-your-own-writes pair, and so is the reverse, so the exemption has to be
    one ledger or the two verbs would disagree about what this transaction
    stores.

    A member is the total reading :func:`written_object` (or
    :func:`written_object_of_row`) answers for a value, never a row and never an
    :class:`~parallax.core.unit_work.ObjectKey`: the provenance refusal that
    reads this is decided before any row is derived. ``None`` is a legitimate
    member — a value whose own class can name no object — and it matches nothing,
    which is exactly what leaves that value's provenance refusal standing.
    """

    __slots__ = ("_objects",)

    def __init__(self) -> None:
        self._objects: set[WrittenObject | None] = set()

    def record(self, written: WrittenObject | None) -> None:
        """Record the object a just-buffered insert opens."""
        self._objects.add(written)

    def holds(self, written: WrittenObject | None) -> bool:
        """Whether this transaction already buffered an insert of ``written``.

        ``None`` never matches: a value that names no object is no object this
        transaction inserted.
        """
        return written is not None and written in self._objects

    def __bool__(self) -> bool:
        """Whether this transaction has buffered any insert at all — the cheap
        answer that lets a caller skip deriving what a value names."""
        return bool(self._objects)


def validate_keyed_instruction(meta: Metamodel, instruction: KeyedWrite) -> PreparedKeyedWrite:
    """The whole judgment a keyed write instruction is measured by, in the one
    order every ingress runs it in.

    The model-aware :func:`~parallax.core.unit_work.validate_write` per row
    FIRST: its inheritance payload-shape rules
    (``subtype-write-metadata-field`` / ``-sibling-attribute`` /
    ``-set-based-unsupported``, `m-inheritance`) classify a framework-owned
    metadata key or a cross-branch field MORE SPECIFICALLY than the generic
    member-name honesty gate ever could. Then
    :func:`~parallax.core.unit_work.instructions.prepare_typed_write`, which
    catches any OTHERWISE-unknown member the row walk left unexamined and
    returns the managed immutable product this function retains.

    Stated once rather than at each ingress because the ORDER is the rule: two
    ingresses that classified one defect differently would make the ingress,
    not the model, decide what a write violated.

    A spelling naming no single declared Entity is left entirely to
    preparation, which owns that classification and refuses it one
    step later: a row judgment presupposes the target whose members it is
    measured against, so an unresolvable target has no row question to answer,
    and answering it here would report a member complaint about an Entity the
    model does not have.
    """
    entity = entity_by_name(meta, instruction.entity)
    if entity is not None:
        for row in instruction.rows:
            validate_write(entity, row, meta, mutation=instruction.mutation)
    prepared = instructions.prepare_typed_write(instruction, meta)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def keyed_instruction(
    mutation: KeyedMutation,
    entity: EntityIdentity,
    row: Mapping[str, object],
    *,
    valid_from: str | None = None,
    until: str | None = None,
) -> KeyedWrite:
    """One single-row keyed instruction, built through the durable IR's own door.

    The document route buys the IR's structural validation — no ``at`` alias, no
    reserved observation control key — before anything measures the row against
    the model, so every ingress that holds a value rather than an instruction
    reaches planning through the same canonical shape a serialized instruction
    does.

    ``valid_from`` / ``until`` are the already-rendered instant literals a
    temporal write carries; a non-temporal or Transaction-Time-Only target's
    caller passes neither. They ride the instruction's own dimension-explicit
    fields, never the row (`m-txtime-write` / `m-bitemp-write`; ADR 0010/0013).
    """
    doc: dict[str, object] = {
        "mutation": mutation,
        "entity": entity.canonical,
        "rows": [dict(row)],
    }
    if valid_from is not None:
        doc["validFrom"] = valid_from
    if until is not None:
        doc["until"] = until
    instruction = instructions.deserialize(doc)
    assert isinstance(instruction, KeyedWrite)  # `doc` carries `rows`
    return instruction


def admit_and_buffer(
    ledger: ClaimLedger,
    meta: Metamodel,
    instruction: PreparedKeyedWrite,
    evidence: SettledEvidence | None,
    *,
    restorations: frozenset[str] = frozenset(),
) -> None:
    """Take this write's claim at the scope it settles against, then buffer it.

    The buffer item is built FIRST, because the carriers' own structural
    refusals are judgments about this write alone — an insert or an instruction
    naming several rows cannot hold the evidence it was handed — while a claim
    is a mutation of state the transaction survives. Taking the claim first
    would leave a caller who catches such a refusal in an open transaction
    holding a claim for a write that was never buffered, against which a later
    legal write of that same scope would be refused, coalesced, or superseded.
    In this order the claim is the last judgment a keyed write passes before it
    is buffered, and a write refused by either of them leaves nothing behind:
    the buffer and the claims it could not join are both untouched.

    Scope and intent are read off what the write settles against and what its
    verb does, and the two are absent together: an insert opens a row rather
    than writing against one, so it has neither. A caller-HELD Write
    Observation carries an intent but no scope, for the reason it spends
    nothing at the flush — it is a value rather than a reference into this
    scope's ledger, so there is no retained evidence a second intent could be
    competing for. Finalization still combines two such writes when they
    address one object and carry equal evidence, because what it coalesces is
    the intent rather than the claim.
    """
    item = buffered_write(instruction, evidence, restorations=restorations)
    admit_write_claim(
        ledger,
        instruction_identity(meta, instruction),
        keyed_intent(instruction),
        scope=claim_scope(evidence),
    )
    ledger.buffer(item)


def instruction_identity(meta: Metamodel, instruction: KeyedWrite) -> EntityIdentity:
    """The Entity Identity ``instruction``'s own spelling names.

    Read by a claim refusal's message, which runs after validation has already
    resolved the spelling; the fallback keeps that message honest for a spelling
    this model somehow does not carry, rather than raising a second failure while
    reporting the first.
    """
    entity = entity_by_name(meta, instruction.entity)
    if entity is None:  # pragma: no cover - validation resolved the spelling already
        return EntityIdentity(namespace="", name=instruction.entity)
    return entity.identity


def cancels_a_pending_assignment(
    ledger: ClaimLedger,
    meta: Metamodel,
    record: EntityMetadata,
    hint: SourceHint | None,
    mutation: KeyedMutation,
) -> bool:
    """Whether this transaction already buffered an ASSIGNMENT at the scope the
    write about to be authored would claim.

    Read off the source value's own hint rather than off a derived row, and at
    whatever scope the target Entity's Optimistic Key names, so the question is
    asked exactly where the verb about to buffer would take its claim: a
    versioned write settling against a different generation of the same row is a
    different claim and taking it back is not something this value said, while an
    unversioned Non-Temporal row has one claim per object because that is the
    grain its shared row lock is held at.

    Asked before the write's evidence is resolved, which is what keeps the
    no-op-first ordering `m-opt-lock` fixes: a net-zero chain off a value the
    verb would refuse still buffers nothing rather than raising.

    A value carrying no hint came from no read and can cancel nothing. A hint
    that IS there always reaches a scope for an update verb: it names an Object
    Key unconditionally, and it retains an observation for exactly the
    state-keyed targets whose arm needs one
    (:class:`~parallax.core.unit_work.SourceHint`).
    """
    if hint is None:
        return False
    scope = claim_scope(
        opt_lock.settled_evidence(
            opt_lock.optimistic_key(meta, record.identity),
            mutation,
            object_key=hint.object_key,
            observation=hint.observation,
        )
    )
    if scope is None:  # pragma: no cover - a hint reaches its target's own arm
        return False
    held = ledger.claimed(scope)
    return held is not None and held.kind == "assignment"


def admit_write_claim(
    ledger: ClaimLedger,
    identity: EntityIdentity,
    intent: WriteIntent | None,
    *,
    scope: ClaimScope | None,
) -> None:
    """Take this write's claim at the scope it settles against, refusing an
    intent the buffer's existing claim cannot absorb.

    A write missing either claims nothing. An insert has neither: it makes no
    intent against existing state and reaches no scope to take one at
    (:func:`~parallax.core.unit_work.keyed_intent`,
    :func:`~parallax.core.opt_lock.settled_evidence`). A caller-held Write
    Observation and an instruction addressing several rows each carry an intent
    and reach no scope — the first because it is a value rather than a reference
    into this ledger, the second because the derivation over a write with no
    single object answers nothing, its caller having supplied nothing either;
    supplied evidence never arrives here with such an instruction, because the
    carrier holding it is built first and refuses the pairing — so neither
    leaves anything for a second intent to compete for.

    The verdict comes from the one algebra finalization also reads
    (:func:`~parallax.core.unit_work.admits`), so a refusal here is exactly the
    combination the flush would have had no meaning for. Everything it admits is
    something the flush performs: assignments merge in authored order, a
    destruction supersedes the assignments buffered before it, and a repeated
    destruction of one scope and region is one destruction.

    The message names what the held claim was rather than only that there was
    one, because the caller's remedy differs: a different temporal region needs
    the first intent flushed through a participating read, while an assignment
    after a destruction has no remedy at all — the row it would write is going
    away.
    """
    if intent is None or scope is None:
        return
    if ledger.claim(scope, intent) != "incompatible":
        return
    raise WriteEvidenceError(
        code="write-evidence-already-claimed",
        message=(
            f"{identity.canonical}: a write already buffered in this transaction claims "
            "what this one settles against, for an intent it cannot be combined "
            "with — a different Valid-Time region composes no interval, an assignment after "
            "a destructive intent resurrects nothing, and a predicate write's selected rows "
            "are one compact group; read the row through this transaction to flush the "
            "buffered intent and settle against fresh state"
        ),
        object_key=claimed_object(scope),
    )


def retain_evidence(
    meta: Metamodel,
    observations: ReadObservations,
    *,
    ledger: ObservationLedger | None,
    pin: Pin | None = None,
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

    The statement's own as-of coordinates are deliberately no part of that
    EVIDENCE. What a write settles against is the state its value came from, and
    that state is what the key names; the pin that selected it is a property of
    the read, so two pins selecting one milestone retain one indistinguishable
    piece of evidence. The pin rides each hint instead (``pin`` below), where it
    answers a different question — whether this value may be written at all —
    rather than which state a write settles against.

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

    ``pin`` is the read's own whole-graph as-of coordinate, which each hint
    carries for a TEMPORAL row and leaves absent otherwise — the same rule the
    typed materializer applies to a node's own lifecycle state, so a Typed node
    and a Wire node of one row answer the same pin to the finite-Transaction-Time
    refusal every keyed verb runs.
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
        observed_pin = pin if _is_temporal(declaring_entity) else None
        if observation is None:
            hints[observed.node] = SourceHint(
                observed.entity, object_key, participation, None, observed_pin
            )
            continue
        key = observed_state_key(object_key, observation, declaring_entity)
        held = pass_states.get(key)
        if held is None:
            held = RetainedObservation(key, observation, participation)
            if ledger is not None:
                held = ledger.retain(held)
            pass_states[key] = held
        hints[observed.node] = SourceHint(
            observed.entity, object_key, participation, held, observed_pin
        )
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


type WriteEvidenceErrorCode = Literal[
    "write-evidence-unavailable",
    "write-evidence-consumed",
    "write-evidence-already-claimed",
]
"""The write-evidence refusals a keyed verb raises.

The three partition what can be wrong with a source's evidence at the verb:
there is none the target Entity's Effective Concurrency Strategy can use, the
evidence there is has been spent by a successful flush, or a write already
buffered in this unit of work claimed the scope this one settles against, for an
intent this one cannot join. A conflict the database discovers later is a
different thing entirely and keeps its own flush-time classification.
"""

WRITE_EVIDENCE_CODES: Final[frozenset[str]] = frozenset(
    {
        "write-evidence-unavailable",
        "write-evidence-consumed",
        "write-evidence-already-claimed",
    }
)
"""The complete set of codes :class:`WriteEvidenceError` carries."""


class WriteEvidenceError(LookupError):
    """A keyed write verb was handed a source whose write evidence it cannot use.

    A ``LookupError`` because every code reports that the evidence this write
    needs is not there for it to use: never recorded for this source, recorded
    and already spent, or still live but claimed by an intent this unit of work
    already buffered at the scope this write settles against, which this one
    cannot join. ``object_key`` is the object the write addressed, always
    visible so a caller can say WHICH write was refused; the Source Hint and the
    claim scope behind it stay implementation state.

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
    hint: SourceHint | None,
    *,
    mutation: KeyedMutation,
    object_key: ObjectKey,
    preference: Concurrency,
    participation: ParticipationToken,
) -> SettledEvidence | None:
    """What a keyed write against existing state settles against, read
    off the source value's own hint.

    One resolution serves the address, the gate, the version advance, and the
    claim, which is what makes it impossible for them to disagree. It follows the
    target Entity's Effective Concurrency Strategy (`m-opt-lock`), not the
    transaction's preference:

    * **Locking** — the license is the shared row lock, so the source read must
      have run in THIS transaction. A source from another scope, or none at all,
      proves no held lock. This holds for EVERY effective-Locking target,
      unversioned Non-Temporal ones included: the lock is the whole of an
      unversioned row's evidence, so exempting it would admit a keyed write
      that proves nothing about the row it addresses and would make write
      safety depend on whether a version column was declared. Unconditional
      intent has its own spelling — ``tx.delete_where(query)`` — rather than
      being reached by constructing a throwaway instance.
    * **Optimistic** — the license is the database gate, so the retained
      observation IS the evidence and a standalone ``db.find`` source carries it
      exactly as a participating read's does.

    Evidence a successful flush already spent is refused under BOTH strategies
    (:func:`_refuse_consumed`).

    What the licensed write then settles against — and therefore claims — is
    :func:`~parallax.core.opt_lock.settled_evidence`'s derivation over this
    target's own Optimistic Key, so the participation check and the scope it
    licenses are stated together: an unversioned Non-Temporal row observes no
    state, and what the lock this check just proved is held on is the OBJECT.
    """
    key = opt_lock.optimistic_key(meta, record.identity)
    strategy = opt_lock.effective_strategy(preference, key)
    observation = None if hint is None else hint.observation
    settled = opt_lock.settled_evidence(
        key, mutation, object_key=object_key, observation=observation
    )
    if strategy == "locking":
        if hint is None or hint.participation is not participation:
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
        return settled
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
    return settled


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
# `_where` temporal verb shares (`validate_window`).                          #
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

    On the UPDATE side this overlaps :func:`resolve_write_evidence`: a value no
    managed read produced, and a value another source produced, both carry no
    hint and so no usable evidence either. Provenance is asked first because it
    is the more specific diagnosis — it names the verb that DOES accept the
    value, where the evidence refusal could only report that there was none.

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


def _stated_instant(name: str, mutation: KeyedMutation, bound: str, value: object) -> dt.datetime:
    """``value`` as the ``timestamp`` a Valid-Time bound has to be.

    Total over what a caller can actually pass, which a type annotation is not:
    a value of another type is no `m-core` instant at all, so it keeps
    `m-core`'s :class:`~parallax.core.base.InstantError` — the same class a
    naive datetime earns one step later — rather than reaching
    :func:`~parallax.core.base.normalize_instant` and leaving an
    ``AttributeError`` where a verdict belongs.
    """
    if not isinstance(value, dt.datetime):
        raise InstantError(
            f"{name}: {mutation!r} takes an aware datetime for {bound}, "
            f"and {type(value).__name__} is no `timestamp`"
        )
    return value


def validate_window(
    declaring_entity: EntityMetadata,
    mutation: KeyedMutation,
    valid_from: object,
    until: object,
) -> tuple[str | None, str | None]:
    """One write verb's rendered Valid-Time bounds, validated together — the
    single window gate every keyed AND ``_where`` temporal verb runs, in both
    representations.

    Three questions in a fixed order, because each presupposes the one before
    it. **Is the window stated?** A ``*_until`` verb's window is a PAIR, and a
    call stating one bound without the other has stated no window at all, so it
    is refused whatever else the call turns out to be — before the target's
    temporality is consulted and before either bound's type is. Which bound is
    missing is asked of the MUTATION rather than of the other bound, because a
    keyed update whose change set is wholly restoring buffers no instruction:
    the window this seam waves through is a window the instruction build never
    sees. **Does the target admit it?** (:func:`_validate_valid_from`.) **Is
    each bound an instant, and is the window ordered?**
    (:func:`_validate_until`, measuring ``until`` against the ``valid_from``
    that judgement accepted.)

    Which refusal follows from whose rule was broken. A half-stated window, a
    bound the target's temporality does not admit, and an unordered window are
    all the verb's OWN verdict on caller input
    (:class:`~parallax.core.unit_work.WriteInstructionError`); a bound that is
    no instant keeps `m-core`'s :class:`~parallax.core.base.InstantError`. All
    are ``ValueError``s, and all precede any evidence question.
    """
    _require_stated_window(declaring_entity, mutation, valid_from, until)
    valid_from_literal = _validate_valid_from(declaring_entity, mutation, valid_from)
    if until is None:
        return valid_from_literal, None
    return valid_from_literal, _validate_until(declaring_entity, mutation, valid_from, until)


def _require_stated_window(
    declaring_entity: EntityMetadata, mutation: KeyedMutation, valid_from: object, until: object
) -> None:
    if mutation not in BOUNDED_MUTATIONS:
        return
    missing = "valid_from" if valid_from is None else "until" if until is None else None
    if missing is None:
        return
    raise instructions.WriteInstructionError(
        f"{declaring_entity.identity.name}: a bounded {mutation!r} states its window as a pair, "
        f"and {missing} is absent"
    )


def _validate_valid_from(
    declaring_entity: EntityMetadata, mutation: KeyedMutation, valid_from: object
) -> str | None:
    """Validate and render a write verb's ``valid_from`` (`python.md` §5):
    a Bitemporal target requires it (the mutation's own Valid-Time instant
    ``B``, `m-bitemp-write` "Plain (unbounded) bitemporal writes"); a
    non-temporal or Transaction-Time-Only target takes none.

    Which refusal follows from whose rule the bound broke. A bound the target's
    temporality does not admit — stated where none is taken, absent where one is
    required — is the verb's OWN verdict on caller input and raises
    :class:`~parallax.core.unit_work.WriteInstructionError`; a bound the target
    does admit but that is no instant keeps `m-core`'s
    :class:`~parallax.core.base.InstantError`, whose rule that is. Admissibility
    leads because it is the more specific complaint: a target declaring no
    Valid-Time dimension takes no bound whatever type the caller spelled it as.
    Both are ``ValueError``s, and both precede any evidence question.
    """
    name = declaring_entity.identity.name
    if _is_bitemporal(declaring_entity):
        if valid_from is None:
            raise instructions.WriteInstructionError(
                f"{name}: a bitemporal {mutation!r} requires valid_from "
                "(the mutation's own Valid-Time instant)"
            )
        return cast(
            "str",
            encode_wire(
                TIMESTAMP,
                normalize_instant(_stated_instant(name, mutation, "valid_from", valid_from)),
            ),
        )
    if valid_from is not None:
        shape = "a Transaction-Time-Only" if _is_temporal(declaring_entity) else "a non-temporal"
        raise instructions.WriteInstructionError(
            f"{name}: {shape} {mutation!r} takes no valid_from "
            f"({name!r} declares no Valid-Time dimension to bound)"
        )
    return None


def _validate_until(
    declaring_entity: EntityMetadata,
    mutation: KeyedMutation,
    valid_from: object,
    until: object,
) -> str:
    """Validate + render a ``*Until`` verb's window bound (`python.md` §5:
    "both aware-UTC-microsecond datetimes, all validated at build" ... "the
    `*_until` trio additionally requires `until`, with `valid_from <
    until` ... all validated at build"): reject an equal or reversed window
    — ``until`` must be strictly later than ``valid_from`` — at the verb
    call, before any buffering (never at flush time).

    An unordered window is the verb's own verdict on caller input and raises
    :class:`~parallax.core.unit_work.WriteInstructionError`, exactly as
    :func:`_validate_valid_from`'s inadmissible bound does; a bound that is no
    ``timestamp`` keeps `m-core`'s :class:`~parallax.core.base.InstantError`,
    exactly as that function's ``valid_from`` does.

    Only a Bitemporal target carrying BOTH bounds reaches this stage: ``until``
    belongs to the bounded verbs alone, :func:`_require_stated_window` has
    already refused a window stated as one bound, and
    :func:`_validate_valid_from` has already refused a ``valid_from`` the
    target's temporality does not admit. ``valid_from`` is re-derived here all
    the same, because that function hands back the rendered literal rather than
    the instant behind it, and ordering is a question about instants.

    NORMALIZES both bounds BEFORE comparing them: comparing raw, un-normalized
    datetimes let a naive ``until`` — measured against a ``valid_from`` its own
    rendering had already normalized — leak a bare ``TypeError`` from the ``<=``
    comparison itself, rather than the
    :class:`~parallax.core.base.InstantError`
    :func:`~parallax.core.base.normalize_instant` raises for any datetime it
    cannot put in UTC."""
    name = declaring_entity.identity.name
    valid_from_normalized = normalize_instant(
        _stated_instant(name, mutation, "valid_from", valid_from)
    )
    until_normalized = normalize_instant(_stated_instant(name, mutation, "until", until))
    if until_normalized <= valid_from_normalized:
        raise instructions.WriteInstructionError(
            f"{name}: {mutation!r} requires valid_from < until "
            f"(python.md §5) — got valid_from={valid_from!r}, until={until!r}"
        )
    return cast("str", encode_wire(TIMESTAMP, until_normalized))


def normalize_assignment_values(
    assignments: Mapping[str, object],
    occurrences: Mapping[str, ValueObjectMetadata] | None = None,
) -> dict[str, object]:
    """Decode each encoded occurrence assignment once into its managed value.

    Scalar assignments already carry managed values. An occurrence decodes to the
    complete document the assignment would STORE — presence preserved, so a member
    the author omits contributes no key exactly as an unstored one does — because
    assigning an occurrence replaces its subtree whole and the comparison below is
    against a resolved row's own reduction of what it holds. A nested ``many`` is
    the one member presence preservation leaves alone, because it has no absence to
    preserve: the stored document carries ``[]`` there whichever of the three zero
    spellings was written, and so does the document this assignment would store, so
    the reduction answers ``[]`` for an omitted one rather than dropping the key
    and calling a stored zero a change. The returned mapping is reusable across
    every row resolved by one predicate write.
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
                reduce_declared_members(shape, element, preserve_presence=True)
                for element in cast("Sequence[object]", encoded)
            ]
        else:
            normalized[member] = reduce_declared_members(shape, value, preserve_presence=True)
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
    for the whole predicate write, so an occurrence arrives as the complete
    document the assignment would store and is compared against the row's whole
    decoded occurrence, without decoding either side again. Nothing is masked by
    the members the author named: assigning an occurrence replaces its subtree,
    so an omitted declared member the row does hold is a change like any other,
    and eliminating that write would leave stored state the assignment removes.
    A nested ``many`` is the one omission that removes nothing — both sides read
    it as the empty collection the store holds either way — so an occurrence
    authored short of one is a no-op rather than a change.

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
        compared = (
            list(cast("tuple[object, ...]", stored))
            if occurrence is not None
            and occurrence.multiplicity is Multiplicity.MANY
            and isinstance(stored, tuple)
            else stored
        )
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
    ``validate_write`` -> typed preparation against the connected model,
    where member-name honesty and the declared-type walk reject a foreign
    instance's row.
    """
    cls = type(instance)
    metadata = meta.entity(declaration_of(cls).identity)
    if metadata is None:
        raise TypeError(f"{cls.__name__} is not an Entity Class of this model")
    return metadata
