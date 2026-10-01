from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol

from parallax.core.document_codec import EffectiveChangeSet, classify_effective_change
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import InstalledLifecycle, refuse_reentry
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    UPDATE_MUTATIONS,
    BufferOutcome,
    KeyedMutation,
    KeyedWrite,
    ObjectKey,
    ReadOrigin,
    SettledEvidence,
    UnitOfWork,
    buffered_write,
    object_key,
)
from parallax.core.unit_work.columns import freeze_retained_value
from parallax.core.unit_work.instructions import PreparedKeyedWrite

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._family import comparison_shape, family_view

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "InsertedObjects",
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
    retroactive correction that lowers to the `m-bitemp-write` rectangle
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
whether a row exists for a write to address; the opened-object ledger does,
and :func:`validate_provenance` takes it as its own argument. Deriving the answer
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

    ``inserted`` answers whether the writing unit of work has ALREADY buffered an
    insert of this object, and its ``True`` exempts a value from the NotStored
    refusal: a row this transaction inserted is a row it stores, so the update
    that follows carries the final value the flush writes rather than addressing
    nothing (`m-unit-work` "Insert-then-update coalesces in place"). It is
    answered from what a source's own identity row names
    (:func:`~parallax.snapshot.handle._typed_writes.source_identity_row`,
    :func:`written_object_of_row`), never through a
    row derived for the purpose, so a value whose class can key no row still
    reaches THIS refusal rather than an
    :class:`~parallax.core.entity.EntityRowError` raised on its behalf. It is the
    UPDATE family's exemption only: the insert family reads the same ledger for
    the opposite verdict, and that refusal is :func:`refuse_repeated_insert`'s,
    asked once the row is prepared rather than here.
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
    """Refuse an insert of an object this transaction already buffered an insert
    of, whichever value spells the repeat and whichever representation opened
    the row.

    The insert family's half of read-your-own-writes, read off the same ledger
    whose entry lifts ``write-value-not-stored`` from an update: a row this
    unit of work opens is a row it stores, so a second opening of it names a row
    already held, exactly as a value this store published does — and it carries
    that value's code, because what is wrong is the same thing. `m-unit-work`'s
    coalescing rules name insert-then-update and insert-then-delete and are
    silent on insert-then-insert, whose only other outcome is the database
    refusing the pair at commit; the verb answers instead.

    ``opened_by`` is the ledger's answer for the object the PREPARED row names
    (:func:`written_object_of_row`), which is why this stands after preparation
    rather than beside the provenance question: a Wire payload's key members are
    canonical only once its row is prepared. A Typed instance could answer
    earlier and does not, so both representations hear pin, provenance, and
    preparation ahead of this. ``None`` is the whole "not held" answer, so
    the refusal and the spelling of the way out come from one reading: the
    advice names the update verb over the carrier the OPENING interface produced
    (:data:`_REPEATED_INSERT_ADVICE`), which is the only carrier that exists,
    and the refusing call's own interface never decides it. The answer is about
    an insert that still STANDS buffered: a destructive write that cancelled a
    pending pair retired the object (:meth:`InsertedObjects.retire`), so an
    insert after it is a first opening and is not refused.
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


type WrittenObject = tuple[EntityIdentity, tuple[tuple[str, object], ...]]
"""Which object a written row names, as :func:`written_object_of_row` reads it —
the equivalence a same-transaction insert is recognized by, never a row and never
an :class:`~parallax.core.unit_work.ObjectKey`."""


def written_object_of_row(
    record: EntityIdentity, key: AttributeMetadata, row: Mapping[str, object]
) -> WrittenObject | None:
    """Which object a written ROW names.

    The one reading, whatever produced the row: the identity row a source states
    (:func:`~parallax.snapshot.handle._typed_writes.source_identity_row`,
    an object key a read filed) and the canonical
    row an insert buffers key by the SAME family key member ``key`` and carry
    the value as the caller supplied it, so a Typed
    insert and a Wire update of one object name one member of
    :class:`InsertedObjects` — which is what makes the exemption span both
    representations rather than one each.

    ``None`` for a row that names no object: one short of the key member, or one
    whose member carries something no object can be addressed BY. A row short
    of the member is defensive rather than reachable — a keyed write's
    identity row is the key the source itself states, and an insert's is judged
    complete before this is asked. An unaddressable member is reachable, because
    a source states its key members as its caller populated them and only the
    write that follows judges them against the declared type; answering ``None``
    is what leaves that value's own refusal standing instead of failing the
    ledger's question about it.
    """
    name = key.identity.name
    if name not in row:  # pragma: no cover - every caller holds a complete key already
        return None
    member = row[name]
    if not _addresses_an_object(member):
        return None
    return (record, ((name, member),))


def _addresses_an_object(member: object) -> bool:
    """Whether an object can be addressed by ``member`` at all.

    Addressing is by equality within :class:`InsertedObjects`, so a member no
    hash is defined over addresses nothing there — and nothing there could have
    been recorded under one, since an insert is validated against the declared
    type before its row is recorded. Read as a property of the member rather
    than a list of carriers: which containers a caller can smuggle past
    validation is open-ended, and every one of them addresses no object for the
    same reason.

    Only ``TypeError`` answers ``False``, because only ``TypeError`` is Python's
    statement that the member defines no hash. A member whose own ``__hash__``
    raises anything else is the caller's code failing, and that exception
    belongs to the caller unmasked rather than being read as an answer about
    naming.
    """
    try:
        hash(member)
    except TypeError:
        return False
    return True


class InsertedObjects:
    """The objects one transaction opened by insert, and which interface opened
    each.

    Not the unit of work's pending inserts: those answer whether an
    :class:`~parallax.core.unit_work.ObjectKey` still has an unflushed insert,
    while this answers, by the identity row a source states before any
    instruction exists, whether this transaction opened the object at all —
    flushed or not — and through which interface.

    Shared by BOTH keyed doors rather than kept per representation: a Typed
    insert followed by a Wire update of the same object is one
    read-your-own-writes pair, and so is the reverse, so the ledger has to be
    one or the two verbs would disagree about what this transaction stores.

    Two rules read it, and they are the two halves of read-your-own-writes. A
    write over existing state reads it for the EXEMPTION: a row this transaction
    opened is a row it stores, so a value naming that object is not refused as
    unstored (:func:`validate_provenance`). An insert reads it for the REFUSAL:
    that same row is already opening, so a second insert of its object names a
    row already held (:func:`refuse_repeated_insert`).

    The refusal also needs the OPENER's representation, which is why an entry is
    a :data:`WriteRepresentation` and not merely presence: the way out of a
    repeat is the update verb over the carrier the first insert produced, and
    only the interface that opened the row has one. Selecting that spelling from
    the refusing call instead would name a Wire node after a Typed insert
    answered none, and a Typed ``.edit`` after a Wire insert took a mapping.

    An object leaves it by one route, :meth:`retire`, taken when a destructive
    keyed write cancels an insert of it that is still PENDING in the buffer: the
    flush annihilates that pair and emits nothing for the object (`m-unit-work`
    "Insert-then-delete cancels"), so from that verb on the transaction holds no
    insert of it, a later insert is a first opening, and a later update
    addresses nothing. A destructive write of an object whose insert already
    flushed retires nothing — that row exists, and a second insert of it would
    collide with it, since a flush emits every surviving insert ahead of every
    delete. A flush retires nothing either, and what a write of a flushed row
    then owes is the question
    :meth:`~parallax.core.unit_work.UnitOfWork.resolve_write_evidence` leaves
    open.

    A member is the total reading :func:`written_object_of_row` answers for an
    identity row, never a row and never an
    :class:`~parallax.core.unit_work.ObjectKey`: the provenance refusal that
    reads this is decided before any row is derived. ``None`` is a legitimate
    member — every way a value can name no object arrives as one — and it matches
    nothing, which is exactly what leaves that value's provenance refusal
    standing.
    """

    __slots__ = ("_objects",)

    def __init__(self) -> None:
        self._objects: dict[WrittenObject | None, WriteRepresentation] = {}

    def record(self, written: WrittenObject | None, opened_by: WriteRepresentation) -> None:
        """Record the object a just-buffered insert opens, and the interface
        that opened it."""
        self._objects[written] = opened_by

    def opened_by(self, written: WrittenObject | None) -> WriteRepresentation | None:
        """Which interface opened the insert this transaction holds of
        ``written``, or ``None`` where it holds none.

        ``None`` is the whole "not held" answer, and a value naming no object is
        never held: a value that names no object is no object this transaction
        inserted.
        """
        if written is None:
            return None
        return self._objects.get(written)

    def retire(self, written: WrittenObject | None) -> None:
        """Forget the object a just-buffered destructive write cancelled the
        pending insert of.

        Called on the unit of work's report that buffering that write cancelled
        the pending insert, and never before: a refused write leaves this ledger
        as it found it, exactly as it leaves the unit of work's own. Total over
        what :func:`written_object_of_row` answers — an object the ledger does
        not hold, and ``None``, retire nothing.
        """
        self._objects.pop(written, None)


@dataclass(frozen=True, slots=True)
class KeyedWriteContext:
    """The transaction state a keyed write reads, and nothing wider.

    Four facts, all fixed for a ``Transaction``'s whole life, which is why one
    value is built at its construction and handed to every keyed verb it answers
    — its own and ``tx.wire``'s alike. ``inserts`` is therefore the SAME ledger
    under both representations, and ``model`` the same accepted metadata, so no
    two keyed verbs of one transaction can disagree about what it stores or what
    it declares.

    It carries no connection and no attempt: a keyed write addresses a row its
    caller already holds and reads nothing from the store, so a context that
    could hand it either would be wider than the writes it serves.
    """

    model: CatalogedModel
    uow: UnitOfWork
    inserts: InsertedObjects
    lifecycle: InstalledLifecycle | None


@dataclass(frozen=True, slots=True)
class ResolvedKeyedWriteSource:
    """What a Keyed Write Source answers about the state a write revises.

    Everything here is answerable before the write is prepared, which is what
    makes it one record rather than a phase's worth of separate getters: the
    provenance refusal, the pin refusal, and the buffered-insert exemption are
    all decided from it, in that order, and the identity row is what names the
    object to the ledger before any instruction exists.

    ``pin`` and ``hint`` are the source's own, never derived: a hintless source
    is one no read of this store published, and a source pinned at a finite
    Transaction-Time instant is read-only whatever else is true of it.

    ``identity_row`` is ``None`` for a source that names no object of this store
    at all — a value whose own class keys this Entity by other members, or one
    that carries no value for a member it does key by. The ledger holds no insert
    of an object nothing named, so such a source reaches the provenance refusal
    that is the honest complaint about it; deriving a row to ask the question
    with would answer that mistake with a codec failure instead.

    ``representation`` is which interface stated the write, and is here for the
    one thing a refusal cannot state without it: the verb that DOES accept the
    value, in the spelling the caller would type.
    """

    entity: EntityMetadata
    pin: Pin | None
    hint: ReadOrigin | None
    identity_row: Mapping[str, object] | None
    provenance: Provenance
    representation: WriteRepresentation

    def __post_init__(self) -> None:
        if self.identity_row is not None:
            object.__setattr__(self, "identity_row", _sealed_row(self.identity_row))


@dataclass(frozen=True, slots=True)
class PreparedSourceWrite:
    """What a Keyed Write Source answers once its write has been prepared.

    ``instruction`` carries the identity plus every member the caller named,
    canonical and owned; ``originals`` carries those same members' original
    values in the carriers that instruction states them in. Both sides cross the
    SAME leaf conversion inside the adapter and only the authored one is judged,
    so the effective change set is a comparison of like with like whether the
    originals came from a Change Record or from a published row, and state a
    write corrects never refuses that write. The comparison itself is the
    document codec's, applied by the ingress rather than by any adapter, so no
    source decides its own effectiveness.

    A destructive or close verb names no member, so ``originals`` is empty and
    the instruction is the identity row alone.
    """

    instruction: PreparedKeyedWrite
    object_key: ObjectKey
    originals: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "originals", _sealed_row(self.originals))

    @property
    def assigned(self) -> Mapping[str, object]:
        """The authored side of the comparison: the instruction's members under
        ``originals``' names, identity excluded.

        The two sides of a comparison are the same member set, which is what
        ``originals``' own invariant says; reading the assigned side through it
        is that invariant spelled once rather than restated at the comparison.
        """
        row = self.instruction.rows[0]
        return {name: row[name] for name in self.originals}


@dataclass(frozen=True, slots=True)
class ResolvedKeyedInsert:
    """What a Keyed Insert Source answers about the row a verb opens.

    An opening row revises no state: no read published it and no prior value is
    restored by it, so there is no identity row to name to the ledger before the
    instruction exists and no hint to settle against. What remains is which
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
    """The row an insert opened, as its caller may render it.

    A Typed caller keeps the instance it passed and ignores this; a Wire caller
    has nothing else to hold, so it renders the frozen node it will revise the
    row through. What it publishes is the buffered ROW rather than the payload,
    and its Read Origin names this transaction's participation with NO
    observation — which is exactly what an opening row has observed. The write
    that follows is licensed by the buffered insert instead.
    """

    identity: EntityIdentity
    row: Mapping[str, object]
    object_key: ObjectKey
    hint: ReadOrigin


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
    Valid-Time pin is the writable retroactive correction (`m-bitemp-write`).
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


def keyed_write(
    ctx: KeyedWriteContext,
    source: KeyedWriteSource,
    mutation: KeyedMutation,
    *,
    valid_from: dt.datetime | None = None,
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

    Two stages read the opened-object ledger, from one object derived once at
    stage 3: the provenance exemption, which is what lets an update follow this
    transaction's own insert, and the evidence exemption, which is why the write
    that follows settles bare — the row it revises is the one that insert opens,
    so there is no prior row for a second intent to compete for. One step past
    the buffer writes it: a destructive write that cancels an insert of the same
    object still PENDING in the unit of work retires that object, because the
    flush will annihilate that pair and emit nothing for it, so from here on an
    insert of it is a first opening and an update of it addresses nothing.

    Whether it cancelled one is the unit of work's report of the buffering
    itself (:class:`~parallax.core.unit_work.BufferOutcome`). An object whose
    insert already flushed is not pending: that row exists, so a second insert
    of it would collide with it — the flush emits every surviving insert ahead
    of every delete, so a delete and a re-insert of one flushed row cannot even
    be ordered as authored. Retiring follows the buffer for the guarantee the
    buffer itself gives: a refused write leaves every ledger as it found it.
    """
    refuse_reentry(ctx.lifecycle)
    source.capture(mutation)
    meta = ctx.model.meta
    resolved = source.resolve(meta, mutation)
    family = family_view(meta, resolved.entity)
    identity_row = resolved.identity_row
    written = (
        None
        if identity_row is None
        else written_object_of_row(resolved.entity.identity, family.primary_key, identity_row)
    )
    opened_by = ctx.inserts.opened_by(written)
    validate_provenance(
        resolved.entity.identity,
        resolved.provenance,
        mutation,
        inserted=opened_by is not None,
        representation=resolved.representation,
    )
    validate_source_pin(resolved.entity.identity, resolved.pin)
    prepared = source.prepare(resolved, valid_from=valid_from, until=until)
    change = _effective_change(ctx, resolved, prepared, mutation)
    if _is_no_op(ctx, resolved, mutation, change):
        return
    evidence: SettledEvidence | None = (
        None
        if opened_by is not None
        else ctx.uow.resolve_write_evidence(
            resolved.entity, resolved.hint, mutation=mutation, object_key=prepared.object_key
        )
    )
    item = buffered_write(prepared.instruction, evidence, change=change)
    if ctx.uow.buffer(item) is BufferOutcome.CANCELLED_PENDING_INSERT:
        ctx.inserts.retire(written)


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

    One stage stands after preparation, the last before the buffer: a second
    insert of an object this transaction already buffered an insert of is
    refused, whichever value spells it and whichever representation opened the
    row. It reads the same ledger the source-backed door's exemption reads, over
    the object the PREPARED row names, because a Wire payload's key members are
    canonical only once the row is — so pin, provenance, and preparation are all
    heard ahead of it, on both lanes.

    The row this opens is recorded in that ledger under the representation that
    opened it, which is what licenses the keyed write that follows and what the
    refusal names the way out in: the caller is sent to the update verb over the
    carrier THIS call produced, which the opposite interface has no spelling for.
    The answer names the row so a caller holding no Entity Class can revise it.
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
    family = family_view(meta, resolved.entity)
    row = prepared.rows[0]
    written = written_object_of_row(resolved.entity.identity, family.primary_key, row)
    refuse_repeated_insert(
        resolved.entity.identity,
        mutation,
        opened_by=ctx.inserts.opened_by(written),
    )
    ctx.uow.buffer(prepared)
    ctx.inserts.record(written, resolved.representation)
    opened = object_key(prepared, meta)
    # A Create Payload is a complete document, so the row it buffers always names
    # its own object by the time validation has admitted it.
    assert opened is not None
    return OpenedKeyedWrite(
        identity=resolved.entity.identity,
        row=row,
        object_key=opened,
        hint=ReadOrigin(
            entity=resolved.entity.identity,
            object_key=opened,
            participation=ctx.uow.participation,
            observation=None,
        ),
    )


def _sealed_row(row: Mapping[str, object]) -> Mapping[str, object]:
    """``row`` owned by the record that answers it, to the leaves.

    Copied and then sealed, both: an adapter builds these mappings as it reads a
    value, and the ingress weighs them against the sealed rows a prepared
    instruction carries, so a record crossing the seam has to be as unable to
    change underneath its reader as those rows are. Sealing the mapping alone
    would leave a structured member's own container reachable, so the values go
    through the SAME freeze a prepared row's leaves do — which is also what makes
    the two comparable: one carrier per value, whichever side produced it.
    """
    return MappingProxyType({name: freeze_retained_value(value) for name, value in row.items()})


def _effective_change(
    ctx: KeyedWriteContext,
    resolved: ResolvedKeyedWriteSource,
    prepared: PreparedSourceWrite,
    mutation: KeyedMutation,
) -> EffectiveChangeSet | None:
    """This write's effective and restored members against the originals its
    source states; a verb that assigns nothing classifies nothing.

    Effectiveness is the document codec's one rule, asked here rather than in
    either adapter, over values the adapter ran through one producer on both
    sides: a member whose authored value is the original the source states was
    RESTORED, and what is left is the effective change set. The codec answers
    names alone, so buffering selects the prepared row's own values by them and
    the comparison never rewrites what will be stored.

    A destructive or close verb names no member, and what it says about the
    row's existence is not a change set to reduce.
    """
    if mutation not in UPDATE_MUTATIONS:
        return None
    return classify_effective_change(
        comparison_shape(ctx.model.meta, resolved.entity),
        prepared.assigned,
        prepared.originals,
    )


def _is_no_op(
    ctx: KeyedWriteContext,
    resolved: ResolvedKeyedWriteSource,
    mutation: KeyedMutation,
    change: EffectiveChangeSet | None,
) -> bool:
    """Whether an update changes nothing and cancels nothing, so buffers nothing.

    A restoration is not nothing — it is the author's last word on that member —
    so a wholly restoring chain still buffers its identity row when this
    transaction already buffered an assignment at the scope it would claim, and
    the merged write is eliminated instead of writing a value the caller took
    back.
    """
    if change is None or change.effective:
        return False
    return not change.restored or not ctx.uow.holds_assignment(
        resolved.entity, resolved.hint, mutation=mutation
    )
