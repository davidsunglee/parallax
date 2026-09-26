from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from parallax.core.document_codec import classify_effective_change
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import InstalledLifecycle, refuse_reentry
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    DESTRUCTIVE_MUTATIONS,
    UPDATE_MUTATIONS,
    KeyedMutation,
    ObjectKey,
    ReadOrigin,
    SettledEvidence,
    UnitOfWork,
    object_key,
)
from parallax.core.unit_work.columns import freeze_retained_value
from parallax.core.unit_work.instructions import PreparedKeyedWrite, PreparedTemporalBounds

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._family import comparison_shape, family_view, temporal_shape
from parallax.snapshot.handle._write_inputs import (
    BufferedInserts,
    Provenance,
    WriteRepresentation,
    admit_and_buffer,
    cancels_a_pending_assignment,
    refuse_repeated_insert,
    reject_temporal_delete,
    resolve_write_evidence,
    validate_provenance,
    validate_source_pin,
    validate_window,
    written_object_of_row,
)

__all__ = [
    "KeyedWriteContext",
    "PreparedSourceWrite",
    "Provenance",
    "ResolvedKeyedInsert",
    "ResolvedKeyedWriteSource",
    "keyed_insert",
    "keyed_write",
    "retained",
]


@dataclass(frozen=True, slots=True)
class KeyedWriteContext:
    """The transaction state a keyed write reads, and nothing wider.

    Four facts, all fixed for a ``Transaction``'s whole life, which is why one
    value is built at its construction and handed to every keyed verb it answers
    — its own, ``tx.wire``'s, and the conformance bridge's alike. ``inserts`` is
    therefore the SAME ledger under both representations, and ``model`` the same
    accepted metadata, so no two keyed verbs of one transaction can disagree
    about what it stores or what it declares.

    It carries no connection and no attempt: a keyed write addresses a row its
    caller already holds and reads nothing from the store, so a lane that could
    hand it either would be wider than the writes it serves.
    """

    model: CatalogedModel
    uow: UnitOfWork
    inserts: BufferedInserts
    lifecycle: InstalledLifecycle | None


@dataclass(frozen=True, slots=True)
class ResolvedKeyedWriteSource:
    """What a Keyed Write Source answers about the state a write revises.

    Everything here is answerable before the temporal window is judged, which is
    what makes it one record rather than a phase's worth of separate getters: the
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
    """What a Keyed Write Source answers once the window has been judged.

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
    :meth:`prepare` builds the instruction and the originals beside it, after the
    window has been judged, because a prepared instruction carries the managed
    bounds.
    """

    def capture(self, mutation: KeyedMutation, /) -> None: ...

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource: ...

    def prepare(
        self, resolved: ResolvedKeyedWriteSource, bounds: PreparedTemporalBounds, /
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
        self, resolved: ResolvedKeyedInsert, bounds: PreparedTemporalBounds, /
    ) -> PreparedKeyedWrite: ...


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

    Two stages read the buffered-insert ledger, from one object derived once at
    stage 3: the provenance exemption, which is what lets an update follow this
    transaction's own insert, and the evidence exemption, which is why the write
    that follows settles bare — the row it revises is the one that insert opens,
    so there is no prior row for a second intent to compete for. One step past
    the buffer writes it: a destructive write that cancels an insert of the same
    object still PENDING in the unit of work retires that object, because the
    flush will annihilate that pair and emit nothing for it, so from here on an
    insert of it is a first opening and an update of it addresses nothing.

    Pending is asked of the unit of work
    (:meth:`~parallax.core.unit_work.UnitOfWork.pending_insert`) and read BEFORE
    the buffer, because buffering this very write is what ends the pair. It is
    the whole condition, and an object whose insert already flushed is not one:
    that row exists, so a second insert of it would collide with it — the flush
    emits every surviving insert ahead of every delete, so a delete and a
    re-insert of one flushed row cannot even be ordered as authored. Retiring
    follows the buffer rather than preceding it for the guarantee the claim
    ledger already gives: a refused write leaves every ledger as it found it.
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
    shape = temporal_shape(meta, resolved.entity)
    reject_temporal_delete(resolved.entity, shape, mutation, surface="keyed")
    valid_from_managed, until_managed = validate_window(
        family.root, shape, mutation, valid_from, until
    )
    prepared = source.prepare(resolved, PreparedTemporalBounds(valid_from_managed, until_managed))
    effective, restorations = _effective_change(ctx, resolved, prepared, mutation)
    if _is_no_op(ctx, resolved, mutation, effective, restorations):
        return
    evidence: SettledEvidence | None = (
        None
        if opened_by is not None
        else resolve_write_evidence(
            meta,
            resolved.entity,
            resolved.hint,
            mutation=mutation,
            object_key=prepared.object_key,
            preference=ctx.uow.settings.concurrency,
            participation=ctx.uow.participation,
        )
    )
    cancels_pending_insert = mutation in DESTRUCTIVE_MUTATIONS and ctx.uow.pending_insert(
        prepared.object_key
    )
    admit_and_buffer(
        ctx.uow,
        meta,
        prepared.instruction,
        evidence,
        restorations=restorations,
        effective=effective,
    )
    if cancels_pending_insert:
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
    prior state was observed, and no claim is taken. What remains beside the
    window and preparation is the pin the value's own view carries and the
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
    canonical only once the row is — so pin, provenance, window, and preparation
    are all heard ahead of it, on both lanes.

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
    family = family_view(meta, resolved.entity)
    valid_from_managed, until_managed = validate_window(
        family.root, temporal_shape(meta, resolved.entity), mutation, valid_from, until
    )
    prepared = opening.prepare(resolved, PreparedTemporalBounds(valid_from_managed, until_managed))
    row = prepared.rows[0]
    written = written_object_of_row(resolved.entity.identity, family.primary_key, row)
    refuse_repeated_insert(
        resolved.entity.identity,
        mutation,
        opened_by=ctx.inserts.opened_by(written),
    )
    admit_and_buffer(ctx.uow, meta, prepared, None)
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
) -> tuple[frozenset[str] | None, frozenset[str]]:
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
        return None, frozenset()
    change = classify_effective_change(
        comparison_shape(ctx.model.meta, resolved.entity),
        prepared.assigned,
        prepared.originals,
    )
    return change.effective, change.restored


def _is_no_op(
    ctx: KeyedWriteContext,
    resolved: ResolvedKeyedWriteSource,
    mutation: KeyedMutation,
    effective: frozenset[str] | None,
    restorations: frozenset[str],
) -> bool:
    """Whether an update changes nothing and cancels nothing, so buffers nothing.

    A restoration is not nothing — it is the author's last word on that member —
    so a wholly restoring chain still buffers its identity row when this
    transaction already buffered an assignment at the scope it would claim, and
    the merged write is eliminated instead of writing a value the caller took
    back.
    """
    if effective is None or effective:
        return False
    return not restorations or not cancels_a_pending_assignment(
        ctx.uow, ctx.model.meta, resolved.entity, resolved.hint, mutation
    )
