from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import InstalledLifecycle, refuse_reentry
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Bitemporal, Pin, TimeInterval
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    UPDATE_MUTATIONS,
    KeyedMutation,
    KeyedWrite,
    ReadOrigin,
    TargetMutation,
    UnitOfWork,
    buffered_write,
    object_key,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    WriteInstructionError,
)
from parallax.core.unit_work.retain import InsertionIdentity
from parallax.core.unit_work.uow import NO_INSERTION_AUTHORITY, NoInsertionAuthority
from parallax.core.write_plan import ObjectKey

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._family import temporal_shape
from parallax.snapshot.handle._options import Omitted

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "KeyedWriteContext",
    "KeyedWriteValueError",
    "PreparedSourceWrite",
    "Provenance",
    "ResolvedKeyedInsert",
    "ResolvedKeyedWriteSource",
    "TransactionTimePinReadOnlyError",
    "WriteRepresentation",
    "keyed_insert",
    "keyed_instruction",
    "keyed_write",
    "retained",
    "validate_source_pin",
    "window_mutation",
]

KEYED_WRITE_VALUE_CODES: Final[frozenset[str]] = frozenset(
    {
        "write-value-not-stored",
        "write-value-already-stored",
        "write-value-foreign-lifecycle",
    }
)
"""The complete keyed-write value refusal vocabulary (`m-unit-work` "Write value
provenance"). The three answer to the three :data:`Provenance` answers — no
managed source published this value, this verb's own source did, another managed
source did — so a refused value carries exactly one of them."""


class KeyedWriteValueError(ValueError):
    """A keyed write verb was handed a value whose PROVENANCE it does not accept.

    A ``ValueError`` for :class:`TransactionTimePinReadOnlyError`'s reason, which
    is the sibling this shares a vocabulary with: both report a neutral
    application-lifecycle refusal of an argument a caller supplied, so a caller
    catching one kind of refused write value catches the other the same way.

    ``code`` is the neutral `m-unit-work` refusal and ``identity`` the Entity
    Identity the write addressed. The value itself is never retained: what the
    refusal is about is which source published it, and the message names the verb
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
    retroactive correction that lowers to the `m-temporal-write` rectangle
    split."""

    code: Final[str] = "transaction-time-pin-read-only"


type Provenance = Literal["none", "foreign", "this"]
"""Which framework-managed source PUBLISHED a written value: none did, another
managed source did, or this store's own did — by a read, or, on the Wire door,
by the insert that opened the row.

Publication rather than read origin is the axis, which is what lets the three
answers partition the values a keyed verb can be handed, makes
:func:`validate_provenance` total over them, and lets each refusal name the verb
that does accept the value. `m-unit-work` "Write value provenance" states its
answers over the values a READ produced, so this answer alone never settles
whether a row exists for a write to address; the unit of work's admitted
insertions do, and :func:`validate_provenance` takes that answer as its own
argument. Deriving the answer
is the REPRESENTATION's job — a Typed value carries a lifecycle to read it from
and a Wire source carries a Read Origin — so this is a fact a caller states
rather than a value this module inspects."""


type WriteRepresentation = Literal["typed", "wire"]
"""Which interface stated a keyed write — the other fact a source answers that
only the representation knows.

A provenance refusal names the verb that DOES accept the value, and a caller
spells that verb in the interface they called: an already-stored value is
re-authored through ``value.edit(...)`` and ``tx.update(...)`` where a Typed
verb was handed it, and through ``tx.wire.update(value, {...})`` where a Wire
one was. The rule, its class, and its code are one; only the spelling of the way
out is the representation's."""

_ALREADY_STORED_ADVICE: Final[Mapping[WriteRepresentation, str]] = {
    "typed": "change it with `value.edit(...)` and write it with `tx.update(...)`",
    "wire": "write the change with `tx.wire.update(value, {...})`",
}
"""How each interface spells the verb that accepts a value already stored.

Only this refusal is reachable from both representations. The other two — a
value no managed source published, and one another lifecycle published — arise on the
source-backed door alone, and a Wire keyed source answers neither: a hintless
argument is refused as no source at all before provenance is asked, so every
source that reaches the question is a node this store published."""

_REPEATED_INSERT_ADVICE: Final[Mapping[WriteRepresentation, str]] = {
    "typed": (
        "write the change with `tx.update(inserted.edit(...))`, where `inserted` is the value "
        "the first insert took"
    ),
    "wire": (
        "write the change with `tx.wire.update(opened, {...})`, where `opened` is the node "
        "the first insert answered"
    ),
}
"""How each interface spells the verb that revises a row this transaction opened.

Keyed by the interface that OPENED the row, never by the one being refused, and
naming the carrier that first insert produced rather than the value just refused.
Two things force both halves. The two values need not be the same object at all —
two instances of one primary key open one row, and an edit of the refused
instance authors its change against a value nothing buffered, so following that
advice would commit the first insert unaltered. And only the opener has a carrier
to name: ``tx.insert`` answers nothing and leaves the caller holding the instance
it passed, while ``tx.wire.insert`` answers a frozen node and took a mapping that
is no keyed source. Selecting by the refusing call would therefore send a Wire
caller to a node no Typed insert produced, and a Typed caller to ``.edit`` on a
payload that has no such method.

The already-stored refusal keeps its own advice
(:data:`_ALREADY_STORED_ADVICE`), where the value handed in IS the stored one and
editing it is the whole repair — so it is the refusing call's spelling, because
there is no earlier insert whose carrier could be named instead."""


def validate_provenance(
    identity: EntityIdentity,
    provenance: Provenance,
    mutation: KeyedMutation,
    *,
    inserted: bool,
    representation: WriteRepresentation,
) -> None:
    """Refuse a value whose PROVENANCE ``mutation``'s verb does not accept
    (`m-unit-work` "Write value provenance"), before any row is derived from it.

    Provenance is which framework-managed source, if any, published the value
    (:data:`Provenance`) — never whether an author has since changed it, which
    decides what a write CONTAINS rather than which verb accepts it. The three answers partition
    the values a verb can be handed, so a refused value earns exactly one code and
    the message names the verb that does accept it, spelled in the
    ``representation`` the call arrived through (:data:`WriteRepresentation`).

    On the UPDATE side this overlaps
    :meth:`~parallax.core.unit_work.UnitOfWork.resolve_write_evidence`: a value no
    managed source published, and a value another source published, both carry no
    hint and so no usable evidence either. Provenance is asked first because it
    is the more specific diagnosis — it names the verb that DOES accept the
    value, where the evidence refusal could only report that there was none.

    An unedited value this source produced is NOT refused for an `update`: it
    carries no change, so it buffers nothing, issues no statement, and raises
    nothing — the same outcome as an edit whose net change is empty.
    ``delete`` / ``terminate`` / ``terminateUntil`` derive an identity row alone
    and fall through, exactly as they already do for ``valid_from``.

    ``inserted`` answers whether the value carries the authority of an
    insertion still standing in the writing unit of work, and its ``True``
    exempts the value from the NotStored refusal: the instance an insertion was
    stated through, and every value derived from it since, revise what that
    insertion opened (`m-unit-work` "Insertion authority"). It is answered from
    the authority the value itself carries, never from the key it names or a
    row derived for the purpose, so a value whose class can key no row still
    reaches THIS refusal rather than an
    :class:`~parallax.core.entity.EntityRowError` raised on its behalf. It is the
    UPDATE family's exemption only: the insert family asks whether an insertion
    of the object still stands for the opposite verdict, and that refusal is
    :func:`refuse_repeated_insert`'s, asked once the row is prepared rather
    than here.
    """
    if mutation not in UPDATE_MUTATIONS and mutation not in INSERT_MUTATIONS:
        return
    if provenance == "none":
        if mutation in INSERT_MUTATIONS or inserted:
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
    if provenance == "foreign":
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
                f"{identity.canonical}: {mutation!r} was handed a value this store published "
                "for a row it already holds — from its own read, or from an insert this "
                "transaction buffered — so there is no row to open; "
                f"{_ALREADY_STORED_ADVICE[representation]}"
            ),
            identity=identity,
        )


def refuse_repeated_insert(
    identity: EntityIdentity,
    mutation: KeyedMutation,
    *,
    opened_by: WriteRepresentation | None,
) -> None:
    """Refuse an insert of an object whose insertion in this transaction still
    stands, whichever value spells the repeat and whichever representation
    opened the row.

    The insert family's half of read-your-own-writes: a row this unit of work
    opens is a row it stores, so a second opening of it names a row already
    held, exactly as a value this store published does — and it carries that
    value's code, because what is wrong is the same thing. The database would
    otherwise refuse the pair at commit; the verb answers instead.

    ``opened_by`` is the unit of work's answer for the object the PREPARED row
    names, which is why this stands after preparation
    rather than beside the provenance question: a Wire payload's key members are
    canonical only once its row is prepared. A Typed instance could answer
    earlier and does not, so both representations hear pin, provenance, and
    preparation ahead of this. ``None`` is the whole "not held" answer, so
    the refusal and the spelling of the way out come from one reading: the
    advice names the update verb over the carrier the OPENING interface produced
    (:data:`_REPEATED_INSERT_ADVICE`), which is the only carrier that exists,
    and the refusing call's own interface never decides it. The answer is about
    an insertion that still STANDS: once everything it opened has been removed,
    or a pending write removes all of it, an insert of the object is a first
    opening and is not refused (`m-unit-work` *Insertion authority*).
    """
    if opened_by is None:
        return
    raise KeyedWriteValueError(
        code="write-value-already-stored",
        message=(
            f"{identity.canonical}: {mutation!r} was handed a value naming an object this "
            "transaction already buffered an insert of, so there is no row to open; "
            f"{_REPEATED_INSERT_ADVICE[opened_by]}"
        ),
        identity=identity,
    )


@dataclass(frozen=True, slots=True)
class KeyedWriteContext:
    """The transaction state a keyed write reads, and nothing wider.

    Three facts, all fixed for a ``Transaction``'s whole life, which is why one
    value is built at its construction and handed to every keyed verb it answers
    — its own and ``tx.wire``'s alike. ``uow`` therefore holds the SAME admitted
    insertions under both representations, and ``model`` the same accepted
    metadata, so no two keyed verbs of one transaction can disagree about what
    it stores or what it declares.

    It carries no connection and no attempt: a keyed write addresses a row its
    caller already holds and reads nothing from the store, so a context that
    could hand it either would be wider than the writes it serves.
    """

    model: CatalogedModel
    uow: UnitOfWork
    lifecycle: InstalledLifecycle | None


@dataclass(frozen=True, slots=True)
class ResolvedKeyedWriteSource:
    """What a Keyed Write Source answers about the state a write revises.

    Everything here is answerable before the write is prepared, which is what
    makes it one record rather than a phase's worth of separate getters: the
    provenance refusal, the exemption a standing insertion grants it, and the
    pin refusal are all decided from it, in that order, before any row is
    derived — so a value whose class can key no row reaches the provenance
    refusal that is the honest complaint about it, rather than a codec failure.

    ``pin`` and ``hint`` are the source's own, never derived: a hintless source
    is one no read of this store published, and a source pinned at a finite
    Transaction-Time instant is read-only whatever else is true of it.

    ``representation`` is which interface stated the write, and is here for the
    one thing a refusal cannot state without it: the verb that DOES accept the
    value, in the spelling the caller would type.

    ``authoring`` is the insertion authority the source privately carries — the
    instance an insertion was admitted through, a value derived from it since,
    or the node a Wire insert answered — which licenses the write only while
    the unit of work still answers it as standing. A source no read published
    carries no hint beside it, and a read's source carries no authority.
    """

    entity: EntityMetadata
    pin: Pin | None
    hint: ReadOrigin | None
    provenance: Provenance
    representation: WriteRepresentation
    authoring: InsertionIdentity | None = None


@dataclass(frozen=True, slots=True)
class PreparedSourceWrite:
    """What a Keyed Write Source answers once its write has been prepared.

    ``instruction`` carries the identity plus every member the caller
    expressed, canonical and owned; ``assigned`` names those members, identity
    excluded. They are the write's literal assignment set: a member equal to
    the value the source published is still assigned, and only an update that
    expresses no member at all is empty.

    A destructive or close verb names no member, so ``assigned`` is empty and
    the instruction is the identity row alone.
    """

    instruction: PreparedKeyedWrite
    object_key: ObjectKey
    assigned: frozenset[str]


@dataclass(frozen=True, slots=True)
class ResolvedKeyedInsert:
    """What a Keyed Insert Source answers about the row a verb opens.

    An opening row revises no state: no read published it and no prior value is
    restored by it, so there is no identity row to name an admitted insertion by
    before the instruction exists and no hint to settle against. What remains is which
    Entity it is a row of, where the value itself came from — the one provenance
    answer an insert can be refused for, since a value this store published names
    a row it already holds — and the ``pin`` such a value carries,
    because the Transaction-Time past is read-only whatever verb was aimed at it.

    ``representation`` is which interface stated the insert, for the same reason
    its peer carries one: the value naming a row already held is refused by
    naming the update verb the caller reaches for, and each interface spells that
    verb its own way.
    """

    entity: EntityMetadata
    pin: Pin | None
    provenance: Provenance
    representation: WriteRepresentation


@dataclass(frozen=True, slots=True)
class OpenedKeyedWrite:
    """The row an insert opened, and the authority its admission granted.

    A Typed caller has ``authority`` bound to the instance it passed; a Wire
    caller has nothing else to hold, so it renders the frozen node it will
    revise the row through, carrying that authority. What the node publishes is
    the buffered ROW rather than the payload. No read published it, so it
    carries no Read Origin: the writes that follow are licensed by the
    insertion's authority instead.
    """

    identity: EntityIdentity
    row: Mapping[str, object]
    object_key: ObjectKey
    authority: InsertionIdentity


class KeyedWriteSource(Protocol):
    """The representation seam of a keyed write over existing state.

    Three phases, called once each and only by the ingress, in the order the
    Keyed Write Validation Order runs them. A source is inert when constructed
    and private to one call, so constructing one refuses nothing and no
    validation can run ahead of the re-entry refusal.

    :meth:`capture` judges and freezes whatever the representation alone can be
    wrong about — a Wire change document's own shape; nothing at all for a Typed
    value, whose shape its class fixes. :meth:`resolve` answers the source facts.
    :meth:`prepare` acquires the authored row, builds the instruction with the
    caller's raw bounds, and has core preparation judge it — target and window
    first, then payload — answering the originals beside it.
    """

    def capture(self, mutation: KeyedMutation, /) -> None: ...

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource: ...

    def prepare(
        self,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedSourceWrite: ...


class KeyedInsertSource(Protocol):
    """The representation seam of a keyed insert — :class:`KeyedWriteSource`'s
    narrower peer, not a synthetic instance of it.

    The same three phases in the same order, over the facts an opening row has:
    no hint, no identity row derived ahead of the instruction, and no originals
    to compare against. :meth:`prepare` answers the prepared write
    itself rather than a record pairing it with originals, because an insert
    reduces no effective change set.
    """

    def capture(self, mutation: KeyedMutation, /) -> None: ...

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert: ...

    def prepare(
        self,
        resolved: ResolvedKeyedInsert,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedWrite: ...


def keyed_instruction(
    mutation: KeyedMutation,
    entity: EntityIdentity,
    row: Mapping[str, object],
    *,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> KeyedWrite:
    """One single-row authored keyed instruction.

    The bounds ride the instruction's dimension-explicit fields as the caller
    passed them, never the row: an As-Of Axis endpoint is framework-owned, and
    preparation judges the window against the target.
    """
    return KeyedWrite(mutation, entity.canonical, (row,), valid_from, until)


def validate_source_pin(identity: EntityIdentity, pin: Pin | None) -> None:
    """Reject a mutation sourced from a view pinned at a FINITE Transaction-Time
    instant (`m-temporal-read`'s finite-pin mutation row): raise
    :class:`TransactionTimePinReadOnlyError` at the verb call, before any
    buffering, so no DML is ever emitted. An absent pin, a ``LATEST``
    Transaction-Time pin, and a finite Valid-Time pin all pass — the finite
    Valid-Time pin is the writable retroactive correction (`m-temporal-write`).
    Shared by both keyed doors of the ingress and by the conformance engine's
    scenario ``mutate`` grading, so the callers can never drift. The
    predicate-selected ``_where`` family needs no counterpart: a set-based write
    target must be a bare statement, so it can never carry an as-of pin at all.

    Takes the written Entity's structured ``identity`` rather than a spelling:
    no layer of the keyed-write path holds an Entity spelling, and the message
    reports the canonical one the identity renders."""
    tx_time = None if pin is None else pin.tx_time
    if not isinstance(tx_time, dt.datetime):
        return
    raise TransactionTimePinReadOnlyError(
        f"{identity.canonical}: the write's source view is pinned at the finite "
        f"Transaction-Time instant {tx_time.isoformat()} and is read-only — the "
        "Transaction-Time past records what the system knew and is never rewritten "
        "(transaction-time-pin-read-only); read the current milestone "
        "(Transaction Time Latest) to mutate it"
    )


def retained[T](filed: T | None) -> T:
    """What a source's :meth:`resolve` filed for its :meth:`prepare`.

    The ingress calls the three phases in order and nothing else calls any of
    them, so what ``resolve`` filed is always there by ``prepare`` — which is a
    fact about this protocol rather than about any one representation, and is why
    an adapter states its retained facts as plain optional slots and reads them
    back through here.
    """
    assert filed is not None
    return filed


def window_mutation[M: KeyedMutation | TargetMutation](
    unbounded: M, bounded: M, until: dt.datetime | Omitted
) -> tuple[M, dt.datetime | None]:
    """The portable verb a public method's ``until`` argument selects, beside
    the bound it carries.

    Omission selects the unbounded verb; any stated argument selects the bounded
    one with that argument as its bound, ``None`` included, so core preparation
    refuses a missing bound rather than this representation reading it as
    omission. Nothing else about the bound is judged here.
    """
    if isinstance(until, Omitted):
        return unbounded, None
    return bounded, until


def keyed_write(
    ctx: KeyedWriteContext,
    source: KeyedWriteSource,
    mutation: KeyedMutation,
    *,
    until: dt.datetime | None = None,
) -> None:
    """Run one keyed write over existing state, in the Keyed Write Validation
    Order.

    The body IS the order, and the order is the contract: a caller learns it
    once, and every source entering here observes the same refusal precedence
    from it.
    Re-entry is the first executable line, so a source's own capture can never
    run inside a lifecycle callback; the source answers, and every judgement
    between its answers belongs here.

    A source no read published is licensed by the insertion authority it
    carries, while the unit of work answers that authority as standing: that
    lifts the provenance refusal, supplies the write's start, and replaces the
    evidence question, because the insertion — not a read — is what authorized
    writes of the object it opened. A key equal to an inserted object's lends a
    value no authority, and a source a read published keeps its own evidence
    whatever this transaction inserted.

    A source-backed write states no start of its own: a Bitemporal one starts
    at its source's finite Valid-Time pin, or at the anchor its insertion was
    admitted with (:func:`source_start`). Preparation then judges that start
    and ``until`` together, before an update that expresses no member is
    dropped as the empty set it is. A refused write leaves the admissions as it
    found them, because the buffer admits all or nothing.
    """
    refuse_reentry(ctx.lifecycle)
    source.capture(mutation)
    meta = ctx.model.meta
    resolved = source.resolve(meta, mutation)
    authoring = resolved.authoring
    anchor = (
        NO_INSERTION_AUTHORITY
        if authoring is None or resolved.hint is not None
        else ctx.uow.insertion_authority(authoring)
    )
    authorized = anchor is not NO_INSERTION_AUTHORITY
    validate_provenance(
        resolved.entity.identity,
        resolved.provenance,
        mutation,
        inserted=authorized,
        representation=resolved.representation,
    )
    validate_source_pin(resolved.entity.identity, resolved.pin)
    valid_from = source_start(ctx, resolved, mutation, anchor)
    prepared = source.prepare(resolved, valid_from=valid_from, until=until)
    if mutation in UPDATE_MUTATIONS and not prepared.assigned:
        return
    if authorized:
        ctx.uow.buffer(buffered_write(prepared.instruction, None, authority=authoring))
        return
    evidence = ctx.uow.resolve_write_evidence(
        resolved.entity, resolved.hint, mutation=mutation, object_key=prepared.object_key
    )
    ctx.uow.buffer(buffered_write(prepared.instruction, evidence, source=resolved.hint))


def source_start(
    ctx: KeyedWriteContext,
    resolved: ResolvedKeyedWriteSource,
    mutation: KeyedMutation,
    anchor: TimeInterval | NoInsertionAuthority | None,
) -> dt.datetime | None:
    """The Valid-Time start a source-backed write of a Bitemporal target
    begins at, or ``None`` for a target with no Valid Time.

    A source an insertion's standing authority licenses starts at the start of
    the ``anchor`` window that insertion was admitted with, however its coverage has been
    edited since. A source a read published starts at that read's finite
    Valid-Time pin, whatever its stored rectangle's own start: the read's
    coordinate is where the caller looked. Valid-Time ``LATEST`` selects the
    open-ended rectangle rather than naming an instant, so a source read there
    states no start and is refused, as is a source neither a pin nor a standing
    insertion anchors.
    """
    if mutation not in UPDATE_MUTATIONS and mutation not in _SOURCE_WINDOWED:
        return None
    entity = resolved.entity
    if not isinstance(temporal_shape(ctx.model.meta, entity), Bitemporal):
        return None
    if isinstance(anchor, TimeInterval):
        return anchor.start
    pin = resolved.pin
    valid_time = None if pin is None else pin.valid_time
    if isinstance(valid_time, dt.datetime):
        return valid_time
    if valid_time is None:
        raise WriteInstructionError(
            f"{entity.identity.canonical}: {mutation!r} starts where its source was read, and "
            "this source names no Valid-Time instant — no read pinned it and no insertion "
            "this transaction admitted anchors it; read the row at a finite Valid-Time "
            "instant and write what that read returns"
        )
    raise WriteInstructionError(
        f"{entity.identity.canonical}: {mutation!r} starts where its source was read, and this "
        "source was read at Valid-Time LATEST, which selects the open-ended rectangle rather "
        "than naming an instant to start from; read the row at a finite Valid-Time instant "
        "and write what that read returns"
    )


_SOURCE_WINDOWED: Final[frozenset[str]] = frozenset({"terminate", "terminateUntil"})


def keyed_insert(
    ctx: KeyedWriteContext,
    opening: KeyedInsertSource,
    mutation: KeyedMutation,
    *,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> OpenedKeyedWrite:
    """Open a row through the insert's own door.

    The same three phases over the facts an opening row has, and the stages it
    has no meaning for are absent rather than guarded: nothing is restored, no
    prior state was observed, and no claim is taken. What remains beside
    preparation is the pin the value's own view carries and the
    provenance it states — in that order, because a pinned value is one this
    store's read published, so both refusals stand over the one value and the
    read-only view is the more specific complaint. (On the source-backed door the
    two can never both be pending: a value the provenance rule refuses came from
    no read of this store at all, so it carries no view to be pinned.)

    One stage stands after preparation, the last before the buffer: an insert
    of an object whose insertion in this transaction still stands is refused,
    whichever value spells it and whichever representation opened the row. It
    is asked over the object the PREPARED row names, because a Wire payload's
    key members are canonical only once the row is — so pin, provenance, and
    preparation are all heard ahead of it, on both lanes.

    The insertion this admits is labelled with the representation that opened
    it, which is what a later repeat's refusal names the way out in: the caller
    is sent to the update verb over the carrier THIS call produced, which the
    opposite interface has no spelling for. The answer carries the authority the
    admission granted, which the caller's interface binds to that carrier, and
    names the row so a caller holding no Entity Class can revise it.
    """
    refuse_reentry(ctx.lifecycle)
    opening.capture(mutation)
    meta = ctx.model.meta
    resolved = opening.resolve(meta, mutation)
    validate_source_pin(resolved.entity.identity, resolved.pin)
    validate_provenance(
        resolved.entity.identity,
        resolved.provenance,
        mutation,
        inserted=False,
        representation=resolved.representation,
    )
    prepared = opening.prepare(resolved, valid_from=valid_from, until=until)
    opened = object_key(prepared, meta)
    # A Create Payload is a complete document, so the row it buffers always names
    # its own object by the time validation has admitted it.
    assert opened is not None
    refuse_repeated_insert(
        resolved.entity.identity,
        mutation,
        opened_by=_opener(ctx.uow.opened_by(opened)),
    )
    ctx.uow.buffer(prepared, opener=resolved.representation)
    authority = ctx.uow.insertion_identity(opened)
    assert authority is not None  # the admission just issued it
    return OpenedKeyedWrite(
        identity=resolved.entity.identity,
        row=prepared.rows[0],
        object_key=opened,
        authority=authority,
    )


def _opener(label: object) -> WriteRepresentation | None:
    if label is None:
        return None
    assert label in _REPEATED_INSERT_ADVICE  # this module labels every insertion it admits
    return label
