"""``parallax.snapshot.handle._write_inputs`` — the keyed verb-input step library.

Everything a keyed write needs from the moment a verb is called to the moment
the buffer holds it, including the write evidence it resolves off the source
value it was handed, and nothing a read needs. Both keyed ingresses — the Typed
verbs and ``tx.wire``'s — reach the whole of it, which is what keeps one
judgement and one buffer behind two representations:

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
* the resolution a keyed verb runs over the write evidence its source value
  carries (:func:`source_hint_of`, :func:`resolve_write_evidence`,
  :class:`WriteEvidenceError`, :data:`WRITE_EVIDENCE_CODES`), and the claim that
  verb then takes at the scope it settles against (:func:`admit_write_claim`,
  :class:`ClaimLedger`);
* the keyed seam itself, in the order every ingress runs it: the canonical
  single-row instruction a verb holding a value builds
  (:func:`keyed_instruction`), the whole judgement it is then measured by
  (:func:`validate_keyed_instruction`), the claim-then-buffer step that ends it
  (:func:`admit_and_buffer`, :func:`instruction_identity`), the question a
  wholly restoring edit asks before it decides whether it cancels anything
  (:func:`cancels_a_pending_assignment`), and the read-your-own-writes ledger
  both ingresses record into and read (:class:`BufferedInserts`,
  :func:`written_object_of_row`).

Family facts come from the accepted Metamodel and its facets, reached through
:mod:`parallax.snapshot.handle._family` as two SEMANTIC answers and no others:
the family-effective primary key a written object is addressed by
(:func:`~parallax.snapshot.handle._family.family_primary_key`) and whether the
family declares as-of axes at all
(:func:`~parallax.snapshot.handle._family.is_temporal`). No step here composes a
physical column sequence or reads a Storage Layout view — a ``row`` crossing this
seam is a canonical identity row keyed by ATTRIBUTE name, as the Entity Row Codec
or a Wire ingress derived it. The participating unit of work reaches this module
as one structural protocol — :class:`ClaimLedger`, the three answers a keyed
write needs — rather than as the whole scope.

Names crossing a module boundary are spelled bare; a helper whose every caller
lives here keeps its underscore. Privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, never by per-name
underscores. What that ``__all__`` carries onward from here it carries for one of
two reasons: a developer catches the keyed write-value and write-evidence
refusals from ``parallax.snapshot`` itself, and the conformance engine's scenario
grading runs the exact finite-Transaction-Time-pin validator the developer verbs
run. The package's re-export list is which names those are.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from typing import Final, Literal, Protocol

from parallax.core import opt_lock
from parallax.core.base import InstantError, normalize_instant
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import lifecycle_state_of
from parallax.core.entity._declaration import declaration_of
from parallax.core.entity._entity import wire_names_of
from parallax.core.metamodel import (
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TemporalDimension,
    entity_by_name,
)
from parallax.core.object_query import Latest
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
    ParticipationToken,
    RetainedObservation,
    SettledEvidence,
    SourceHint,
    WriteIntent,
    buffered_write,
    claim_scope,
    claimed_object,
    instructions,
    keyed_intent,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
)
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle._family import family_primary_key, is_temporal

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "WRITE_EVIDENCE_CODES",
    "BufferedInserts",
    "ClaimLedger",
    "KeyedWriteValueError",
    "TransactionTimePinReadOnlyError",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
    "WrittenObject",
    "admit_and_buffer",
    "admit_write_claim",
    "cancels_a_pending_assignment",
    "instruction_identity",
    "keyed_instruction",
    "metadata_of_instance",
    "resolve_write_evidence",
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


def _is_bitemporal(declaring_entity: EntityMetadata) -> bool:
    return declaring_entity.as_of_axis(TemporalDimension.VALID_TIME) is not None


def written_object_key(
    record: EntityMetadata, meta: Metamodel, row: Mapping[str, object]
) -> ObjectKey:
    """The object a WRITTEN instance addresses — the same
    :class:`~parallax.core.unit_work.ObjectKey` a read's own Source Hints name
    their objects by (the instance's OWN Entity Identity, never
    family-normalized; pk pairs by canonical attribute name, in the
    family-effective primary key's own order) and `unit_work.object_key`
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
            for attr in family_primary_key(meta, record)
        ),
    )


type WrittenObject = tuple[EntityIdentity, tuple[tuple[str, object], ...]]
"""Which object a written value names, as :func:`written_object` reads it — the
equivalence a same-transaction insert is recognized by, never a row and never an
:class:`~parallax.core.unit_work.ObjectKey`."""


def written_object(
    record: EntityMetadata, meta: Metamodel, value: EntityBase
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
    for attribute in family_primary_key(meta, record):
        py_name = names.name_to_py.get(attribute.identity.name)
        if py_name is None:
            return None
        pairs.append((attribute.identity.name, getattr(value, py_name)))
    return (record.identity, tuple(pairs))


def written_object_of_row(
    record: EntityMetadata, meta: Metamodel, row: Mapping[str, object]
) -> WrittenObject | None:
    """Which object a written ROW names — :func:`written_object`'s peer for an
    ingress holding a row rather than an Entity value.

    A Wire verb never holds an instance, so the read-your-own-writes exemption
    has to be answerable from the canonical row an insert buffers. Both readings
    key by the SAME family-effective primary-key members in the SAME order and
    carry the values as the caller supplied them, so a Typed insert and a Wire
    update of one object name one member of :class:`BufferedInserts` — which is
    what makes the exemption span both representations rather than one each.

    ``None`` for a row short of a primary-key member, which names no object at
    all. Defensive rather than reachable: an insert's row is judged complete
    before this is asked, and a keyed write's identity row comes from the object
    key its source's own read filed.
    """
    pairs: list[tuple[str, object]] = []
    for attribute in family_primary_key(meta, record):
        name = attribute.identity.name
        if name not in row:  # pragma: no cover - both callers hold a complete key already
            return None
        pairs.append((name, row[name]))
    return (record.identity, tuple(pairs))


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
    """Prepare one typed keyed instruction through Unit Work's sole judgment."""
    prepared = instructions.prepare_typed_write(instruction, meta)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def keyed_instruction(
    mutation: KeyedMutation,
    entity: EntityIdentity,
    row: Mapping[str, object],
    *,
    valid_from: str | dt.datetime | None = None,
    until: str | dt.datetime | None = None,
) -> KeyedWrite:
    """One single-row authored keyed instruction.

    Typed callers pass managed instants; the Wire ingress passes canonical
    spellings for its own decode. Both ride the instruction's dimension-explicit
    fields, never the row, and preparation applies the policy of the ingress.
    """
    return KeyedWrite(mutation, entity.canonical, (row,), valid_from, until)


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


def instruction_identity(
    meta: Metamodel, instruction: KeyedWrite | PreparedKeyedWrite
) -> EntityIdentity:
    """The Entity Identity ``instruction``'s own spelling names.

    Read by a claim refusal's message, which runs after validation has already
    resolved the spelling; the fallback keeps that message honest for a spelling
    this model somehow does not carry, rather than raising a second failure while
    reporting the first.
    """
    if isinstance(instruction, PreparedKeyedWrite):
        return instruction.target.identity
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


# --------------------------------------------------------------------------- #
# Build-time validation, run off what the caller supplied and before any row  #
# is derived from it: the source-pin and value-provenance refusals every      #
# keyed verb runs on the instance it was handed, and the Valid-Time window     #
# `validate_window` judges for every keyed AND `_where` temporal verb —       #
# the one step of this library the predicate-selected lane also runs.         #
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
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """One write verb's managed Valid-Time bounds, validated together — the
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
    valid_from_managed = _validate_valid_from(declaring_entity, mutation, valid_from)
    if until is None:
        return valid_from_managed, None
    return valid_from_managed, _validate_until(declaring_entity, mutation, valid_from, until)


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
) -> dt.datetime | None:
    """Validate and normalize a write verb's ``valid_from`` (`python.md` §5):
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
        return normalize_instant(_stated_instant(name, mutation, "valid_from", valid_from))
    if valid_from is not None:
        shape = "a Transaction-Time-Only" if is_temporal(declaring_entity) else "a non-temporal"
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
) -> dt.datetime:
    """Validate + normalize a ``*Until`` verb's window bound (`python.md` §5:
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
    target's temporality does not admit. Both bounds are normalized here so the
    ordering comparison is wholly expressed in managed instant space.

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
    return until_normalized


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
