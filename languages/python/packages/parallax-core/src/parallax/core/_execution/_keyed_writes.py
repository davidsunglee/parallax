from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.core._execution._family import temporal_shape
from parallax.core._execution._options import OMITTED, Omitted
from parallax.core._execution._unit_work.admission import (
    NO_INSERTION_AUTHORITY,
    NoInsertionAuthority,
)
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    ASSIGNMENT_MUTATIONS,
    INSERT_MUTATIONS,
    KeyedMutation,
    KeyedWriteInstruction,
    PreparedKeyedWrite,
    WriteInstructionError,
)
from parallax.core._execution._unit_work.keys import object_key
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    ReadEvidence,
)
from parallax.core._execution._unit_work.uow import UnitOfWork
from parallax.core._execution._unit_work.write_items import buffered_write
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import InstalledLifecycle, refuse_reentry
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Bitemporal, Pin, TimeInterval
from parallax.core.write_plan import ObjectKey

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "KeyedInsertSource",
    "KeyedWriteSource",
    "KeyedWriteValueError",
    "OpenedKeyedWrite",
    "PreparedSourceWrite",
    "Provenance",
    "ResolvedKeyedInsert",
    "ResolvedKeyedWriteSource",
    "TargetRevisionArguments",
    "TransactionTimePinReadOnlyError",
    "keyed_insert",
    "keyed_instruction",
    "keyed_write",
    "retained",
    "stated_valid_from",
    "target_revision_arguments",
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
    retroactive correction that lowers to the `m-temporal-write` rectangle
    split."""

    code: Final[str] = "transaction-time-pin-read-only"


type Provenance = Literal["none", "foreign", "this"]
"""Which framework-managed source PUBLISHED a written value: none did, another
managed source did, or this store's own did — by a read, or, on the Wire door,
by the insert that opened the row.

Publication rather than read evidence is the axis, which is what lets the three
answers partition the values a keyed verb can be handed, makes
:func:`validate_provenance` total over them, and lets each refusal name the verb
that does accept the value. `m-unit-work` "Write value provenance" states its
answers over the values a READ produced, so this answer alone never settles
whether a row exists for a write to address; the unit of work's admitted
insertions do, and :func:`validate_provenance` takes that answer as its own
argument. Deriving the answer
belongs to whoever supplies the source — the lifecycle or node that published a
value is what records it — so this is a fact a caller states rather than a
value this module inspects. Read Evidence never decides it: a read can publish
a value without leaving any."""


def validate_provenance(
    identity: EntityIdentity,
    provenance: Provenance,
    mutation: KeyedMutation,
    *,
    inserted: bool,
    advice: KeyedWriteRefusalAdvice,
) -> None:
    """Refuse a value whose PROVENANCE ``mutation``'s verb does not accept
    (`m-unit-work` "Write value provenance"), before any row is derived from it.

    Provenance is which framework-managed source, if any, published the value
    (:data:`Provenance`) — never whether an author has since changed it, which
    decides what a write CONTAINS rather than which verb accepts it. The three answers partition
    the values a verb can be handed, so a refused value earns exactly one code and
    the message names the verb that does accept it, in the ``advice`` of the
    interface the call arrived through: the value handed in IS the one refused,
    so that interface's spelling is its repair.

    On the amendment and replacement side this overlaps
    :meth:`~parallax.core.unit_work.UnitOfWork.resolve_read_evidence`: a value no
    managed source published, and a value another source published, both carry no
    hint and so no usable evidence either. Provenance is asked first because it
    is the more specific diagnosis — it names the verb that DOES accept the
    value, where the evidence refusal could only report that there was none.

    An unedited value this source produced is NOT refused for an `amend`: it
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
    amendment and replacement family's exemption only: the insert family asks whether an insertion
    of the object still stands for the opposite verdict, and that refusal is
    :func:`refuse_repeated_insert`'s, asked once the row is prepared rather
    than here.
    """
    if mutation not in ASSIGNMENT_MUTATIONS and mutation not in INSERT_MUTATIONS:
        return
    if provenance == "none":
        if mutation in INSERT_MUTATIONS or inserted:
            return
        raise KeyedWriteValueError(
            code="write-value-not-stored",
            message=(
                f"{identity.canonical}: {mutation!r} was handed a value no read of this "
                f"store produced, so it addresses no stored row; {advice.not_stored}"
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
                f"{advice.already_stored}"
            ),
            identity=identity,
        )


def refuse_repeated_insert(
    identity: EntityIdentity,
    mutation: KeyedMutation,
    *,
    opener_advice: KeyedWriteRefusalAdvice | None,
) -> None:
    """Refuse an insert of an object whose insertion in this transaction still
    stands, whichever value spells the repeat and whichever representation
    opened the row.

    The insert family's half of read-your-own-writes: a row this unit of work
    opens is a row it stores, so a second opening of it names a row already
    held, exactly as a value this store published does — and it carries that
    value's code, because what is wrong is the same thing. The database would
    otherwise refuse the pair at commit; the verb answers instead.

    ``opener_advice`` is the unit of work's answer for the object the PREPARED
    row names, which is why this stands after preparation
    rather than beside the provenance question: a Wire payload's key members are
    canonical only once its row is prepared. A Typed instance could answer
    earlier and does not, so both representations hear pin, provenance, and
    preparation ahead of this. ``None`` is the whole "not held" answer, so
    the refusal and the spelling of the way out come from one reading. The
    answer is about an insertion that still STANDS: once everything it opened
    has been removed, or a pending write removes all of it, an insert of the
    object is a first opening and is not refused (`m-unit-work` *Insertion
    authority*).

    The advice is the one the OPENING insert supplied, never the refusing
    call's. The two values need not be the same object at all — two values of
    one primary key open one row, so revising the refused one would author a
    change against a value nothing buffered and commit the first insert
    unaltered — and only the opening interface produced a carrier the repair
    can name.
    """
    if opener_advice is None:
        return
    raise KeyedWriteValueError(
        code="write-value-already-stored",
        message=(
            f"{identity.canonical}: {mutation!r} was handed a value naming an object this "
            "transaction already buffered an insert of, so there is no row to open; "
            f"{opener_advice.repeated_insert}"
        ),
        identity=identity,
    )


@dataclass(frozen=True, slots=True)
class ResolvedKeyedWriteSource:
    """What a Keyed Write Source answers about the state a write revises.

    Everything here is answerable before the write is prepared, which is what
    makes it one record rather than a phase's worth of separate getters: the
    provenance refusal, the exemption a standing insertion grants it, and the
    pin refusal are all decided from it, in that order, before any row is
    derived — so a value whose class can key no row reaches the provenance
    refusal that is the honest complaint about it, rather than a codec failure.

    ``pin`` and ``read_evidence`` are the source's own, never derived. Read
    evidence is optional beside ``provenance``: a read outside a writable
    attempt and a milestone-set read both publish a source that carries none.
    A source pinned at a finite Transaction-Time instant is read-only whatever
    else is true of it.

    ``advice`` is the repair wording of the interface that stated the write,
    here for the one thing a refusal cannot state without it: the verb that
    DOES accept the value, in the spelling the caller would type.

    ``authoring`` is the insertion authority the source privately carries — the
    instance an insertion was admitted through, a value derived from it since,
    or the node a Wire insert answered — which licenses the write only while
    the unit of work still answers it as standing. A source no read published
    carries no read evidence beside it, and a read's source carries no authority.
    """

    entity: EntityMetadata
    pin: Pin | None
    read_evidence: ReadEvidence | None
    provenance: Provenance
    advice: KeyedWriteRefusalAdvice
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

    ``advice`` is the repair wording of the interface that stated the insert,
    for the same reason its peer carries one: the value naming a row already
    held is refused by naming the amend verb the caller reaches for, and each
    interface spells that verb its own way. An admitted insertion retains it,
    so a later repeat names the way out this insert's carrier offers.
    """

    entity: EntityMetadata
    pin: Pin | None
    provenance: Provenance
    advice: KeyedWriteRefusalAdvice


@dataclass(frozen=True, slots=True)
class OpenedKeyedWrite:
    """The row an insert opened, and the authority its admission granted.

    A Typed caller has ``authority`` bound to the instance it passed; a Wire
    caller has nothing else to hold, so it renders the frozen node it will
    revise the row through, carrying that authority. What the node publishes is
    the buffered ROW rather than the payload. No read published it, so it
    carries no Read Evidence: the writes that follow are licensed by the
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
) -> KeyedWriteInstruction:
    """One single-row authored keyed instruction.

    The bounds ride the instruction's dimension-explicit fields as the caller
    passed them, never the row: an As-Of Axis endpoint is framework-owned, and
    preparation judges the window against the target.
    """
    return KeyedWriteInstruction(mutation, entity.canonical, (row,), valid_from, until)


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


@dataclass(frozen=True, slots=True)
class TargetRevisionArguments:
    """The revision keywords a caller-conditioned write was handed, unjudged, as
    the canonical instruction carries them beside the names its caller stated,
    so preparation can judge presence apart from value in its fixed order."""

    if_version: int | None
    if_tx_start: dt.datetime | None
    stated: tuple[str, ...]


def target_revision_arguments(
    *, version: object = OMITTED, tx_start: object = OMITTED
) -> TargetRevisionArguments:
    """The revision a ``_if`` write's keywords state, unjudged.

    Omission is the one absence: a keyword stated as ``None`` or as any other
    value is a stated revision, so preparation refuses more than one stated,
    a missing one, and an invalid value — a ``None`` included — and never
    falls back on a source's authority.
    """
    stated: tuple[str, ...] = ()
    if not isinstance(version, Omitted):
        stated += ("version",)
    if not isinstance(tx_start, Omitted):
        stated += ("tx_start",)
    return TargetRevisionArguments(
        if_version=None if isinstance(version, Omitted) else cast("int", version),
        if_tx_start=None if isinstance(tx_start, Omitted) else cast("dt.datetime", tx_start),
        stated=stated,
    )


def stated_valid_from(valid_from: dt.datetime | Omitted) -> dt.datetime | None:
    """A write's ``valid_from`` keyword as the bound preparation judges: an
    omitted start is absent, and a stated ``None`` is refused rather than read
    as omission."""
    if isinstance(valid_from, Omitted):
        return None
    if cast("object", valid_from) is None:
        raise WriteInstructionError(
            "valid_from=None states no start; omit valid_from rather than stating None"
        )
    return valid_from


def keyed_write(
    model: CatalogedModel,
    uow: UnitOfWork,
    lifecycle: InstalledLifecycle | None,
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
    and ``until`` together, and the source is admitted — by that standing
    authority, or by read evidence of this attempt — before an amendment that
    expresses no member is dropped as the empty set it is, so stating nothing
    never lets an ineligible source pass. Dropping it buffers nothing and
    changes no evidence. A replacement is never empty: it states the object's complete
    writable state, completed from whatever it omits. A refused write leaves the
    admissions as it found them, because the buffer admits all or nothing.
    """
    refuse_reentry(lifecycle)
    source.capture(mutation)
    meta = model.meta
    resolved = source.resolve(meta, mutation)
    authoring = resolved.authoring
    anchor = (
        NO_INSERTION_AUTHORITY
        if authoring is None or resolved.read_evidence is not None
        else uow.insertion_authority(authoring)
    )
    authorized = anchor is not NO_INSERTION_AUTHORITY
    validate_provenance(
        resolved.entity.identity,
        resolved.provenance,
        mutation,
        inserted=authorized,
        advice=resolved.advice,
    )
    validate_source_pin(resolved.entity.identity, resolved.pin)
    valid_from = source_start(meta, resolved, mutation, anchor)
    prepared = source.prepare(resolved, valid_from=valid_from, until=until)
    if authorized:
        item = buffered_write(prepared.instruction, None, authority=authoring)
    else:
        evidence = uow.resolve_read_evidence(
            resolved.entity,
            resolved.read_evidence,
            mutation=mutation,
            object_key=prepared.object_key,
        )
        item = buffered_write(prepared.instruction, evidence, source=resolved.read_evidence)
    if mutation in AMEND_MUTATIONS and not prepared.assigned:
        return
    uow.buffer(item)


def source_start(
    meta: Metamodel,
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
    if mutation not in ASSIGNMENT_MUTATIONS and mutation not in _SOURCE_WINDOWED:
        return None
    entity = resolved.entity
    if not isinstance(temporal_shape(meta, entity), Bitemporal):
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
    model: CatalogedModel,
    uow: UnitOfWork,
    lifecycle: InstalledLifecycle | None,
    opening: KeyedInsertSource,
    mutation: KeyedMutation,
    *,
    valid_from: dt.datetime | Omitted = OMITTED,
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

    The insertion this admits retains the advice of the interface that opened
    it, which is what a later repeat's refusal names the way out in: the caller
    is sent to the amend verb over the carrier THIS call produced, which the
    opposite interface has no spelling for. The answer carries the authority the
    admission granted, which the caller's interface binds to that carrier, and
    names the row so a caller holding no Entity Class can revise it.
    """
    refuse_reentry(lifecycle)
    start = stated_valid_from(valid_from)
    opening.capture(mutation)
    meta = model.meta
    resolved = opening.resolve(meta, mutation)
    validate_source_pin(resolved.entity.identity, resolved.pin)
    validate_provenance(
        resolved.entity.identity,
        resolved.provenance,
        mutation,
        inserted=False,
        advice=resolved.advice,
    )
    prepared = opening.prepare(resolved, valid_from=start, until=until)
    opened = object_key(prepared, meta)
    # A Create Payload is a complete document, so the row it buffers always names
    # its own object by the time validation has admitted it.
    assert opened is not None
    refuse_repeated_insert(
        resolved.entity.identity,
        mutation,
        opener_advice=uow.insertion_advice(opened),
    )
    uow.buffer(prepared, insertion_advice=resolved.advice)
    authority = uow.insertion_identity(opened)
    assert authority is not None  # the admission just issued it
    return OpenedKeyedWrite(
        identity=resolved.entity.identity,
        row=prepared.rows[0],
        object_key=opened,
        authority=authority,
    )
