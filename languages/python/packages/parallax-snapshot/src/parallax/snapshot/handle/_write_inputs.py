from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Final, Literal

from parallax.core.entity import Entity as EntityBase
from parallax.core.entity._declaration import declaration_of, wire_names_of
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.core.object_query import Latest
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    UPDATE_MUTATIONS,
    KeyedMutation,
    KeyedWrite,
    ObjectKey,
    ReadOrigin,
)
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle._family import family_view

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "BufferedInserts",
    "KeyedWriteValueError",
    "Provenance",
    "TransactionTimePinReadOnlyError",
    "WriteRepresentation",
    "keyed_instruction",
    "metadata_of_instance",
    "read_origin_of",
    "refuse_repeated_insert",
    "source_identity_row",
    "source_pin",
    "validate_provenance",
    "validate_source_pin",
    "written_object_key",
    "written_object_of_row",
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


_UNPOPULATED: Final = object()
"""What :func:`source_identity_row` reads for a member the value states no value
for — the one reading that must answer rather than raise, since it runs before
the refusal such a value has coming."""


def written_object_key(
    record: EntityMetadata, meta: Metamodel, row: Mapping[str, object]
) -> ObjectKey:
    """The object a WRITTEN instance addresses — the same
    :class:`~parallax.core.unit_work.ObjectKey` a source's own Read Origins name
    their objects by (the instance's OWN Entity Identity, never
    family-normalized; its one pair keyed by the family key's canonical
    attribute name) and `unit_work.object_key` computes at flush, so a
    verb-time refusal and the flush-time settle can never name the object two
    different ways.

    ``row`` is that instance's identity row as the Entity Row Codec derived it,
    passed in rather than derived here: the Inheritance Facet owns which member
    is the family key, and the codec owns what an Entity value's canonical
    primary key IS."""
    name = family_view(meta, record).primary_key.identity.name
    return ObjectKey(record.identity, ((name, row[name]),))


type WrittenObject = tuple[EntityIdentity, tuple[tuple[str, object], ...]]
"""Which object a written row names, as :func:`written_object_of_row` reads it —
the equivalence a same-transaction insert is recognized by, never a row and never
an :class:`~parallax.core.unit_work.ObjectKey`."""


def source_identity_row(
    record: EntityMetadata, meta: Metamodel, value: EntityBase
) -> Mapping[str, object] | None:
    """``value``'s family-key member read straight off it — or ``None`` when it
    states no value for it, because its own class carries no attribute for that
    member or because nothing ever populated the one it carries.

    Total for every value of the Entity, which is what this reading exists for:
    the identity row is what names the object to the buffered-insert ledger, and
    the ledger is consulted before the provenance refusal that a value naming no
    object of this store has coming, so a value this reading could refuse would
    be answered ahead of the honest complaint about it. The Entity Row Codec's
    :meth:`~parallax.core.entity.EntityRowCodec.identity_row` selects the same
    member and is total over neither case: it refuses the class that carries no
    attribute for the member and fails on the attribute read for the one that
    carries it unpopulated. Whichever it does follows later, when the write goes
    to derive the row it would actually buffer.

    ``None`` means no object, so no insert of it was buffered, which is what
    leaves such a value's provenance refusal standing.

    A primary key is an Attribute, whose canonical form is the value itself, so
    the member is carried here exactly as a row would serialize it and a reading
    of this row compares equal to a reading of the row an insert buffers.
    """
    name = family_view(meta, record).primary_key.identity.name
    py_name = wire_names_of(type(value)).name_to_py.get(name)
    if py_name is None:
        return None
    member = getattr(value, py_name, _UNPOPULATED)
    if member is _UNPOPULATED:
        return None
    return {name: member}


def written_object_of_row(
    record: EntityIdentity, key: AttributeMetadata, row: Mapping[str, object]
) -> WrittenObject | None:
    """Which object a written ROW names.

    The one reading, whatever produced the row: the identity row a source states
    (:func:`source_identity_row`, an object key a read filed) and the canonical
    row an insert buffers key by the SAME family key member ``key`` and carry
    the value as the caller supplied it, so a Typed
    insert and a Wire update of one object name one member of
    :class:`BufferedInserts` — which is what makes the exemption span both
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

    Addressing is by equality within :class:`BufferedInserts`, so a member no
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


class BufferedInserts:
    """The objects one transaction holds a buffered insert of, and which
    interface opened each.

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


def read_origin_of(instance: object) -> ReadOrigin | None:
    """The private :class:`~parallax.core.unit_work.ReadOrigin` ``instance``
    carries, or ``None`` for a value Parallax never published.

    An edited copy answers the node's own hint, because an edit preserves every
    kind of instance state outside the declared members (``Entity.edit``) — which
    is what lets a developer read a row, change what they read, and write back
    against the state they read. A value another framework-managed source
    produced answers ``None`` here: its lifecycle state is that source's own, so
    this lifecycle recognizes no hint on it.
    """
    state = snapshot_state_of(instance)
    return None if state is None else state.source


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
    Shared by both keyed doors of the ingress and by the conformance engine's
    scenario ``mutate`` grading, so the callers can never drift. The
    predicate-selected ``_where`` family needs no counterpart: a set-based write
    target must be a bare statement, so it can never carry an as-of pin at all.

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


type Provenance = Literal["none", "foreign", "this"]
"""Which framework-managed source PUBLISHED a written value: none did, another
managed source did, or this store's own did — by a read, or, on the Wire door,
by the insert that opened the row.

Publication rather than read origin is the axis, which is what lets the three
answers partition the values a keyed verb can be handed, makes
:func:`validate_provenance` total over them, and lets each refusal name the verb
that does accept the value. `m-unit-work` "Write value provenance" states its
answers over the values a READ produced, so this answer alone never settles
whether a row exists for a write to address; the buffered-insert ledger does,
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
    (:func:`source_identity_row`, :func:`written_object_of_row`), never through a
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
    pending pair retired the object (:meth:`BufferedInserts.retire`), so an
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
