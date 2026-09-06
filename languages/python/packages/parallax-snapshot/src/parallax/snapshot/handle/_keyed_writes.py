"""``parallax.snapshot.handle._keyed_writes`` — the keyed write ingress (spec §5).

A keyed write is one order, and that order is the whole of what a caller
observes as refusal precedence: re-entry is refused; the representation's own
input shape is judged and captured; the source is resolved and its provenance
and pin judged; the temporal window is judged; member names, values, and
assignment legality are judged and the instruction prepared; the effective
change set and its restorations are reduced, with the no-op return; the
buffered-insert exemption applies; write evidence resolves; the claim is taken
and the write buffered. An insert enters by its own door, with no source, null
or synthetic: it opens a row rather than revising one, so it resolves no source,
reduces no change set, settles against no evidence, and takes no claim. What it
keeps of the stages above is what a value alone can be wrong about — the pin its
own view carries and the provenance it states, in that order.

What differs between one representation's keyed verbs and another's is not that
order but where the facts it consumes come from — a Typed value carries its own
Change Record and lifecycle, a Wire source carries a frozen published row and a
Source Hint. A **Keyed Write Source** is that difference and nothing else: three phases,
run once each in the order above, answering the concrete Entity, the source Pin,
the Source Hint, the canonical identity row, the value's provenance, which
interface stated the write, and the canonical authored and original values of
every named member. A source exposes
no codec, carrier, selected model, unit of work, mutation, prepared front door,
or insert ledger, and it judges nothing: it answers facts, and the order judges
them.

The two records crossing that seam split where the order splits.
:class:`ResolvedKeyedWriteSource` carries what a source can answer before the
window is judged, and :class:`PreparedSourceWrite` what it can answer only
after — which is why the protocol needs no typestate to say which question is
askable when. The ingress owns every call, so which record it holds is which
stage it stands at.

:class:`KeyedWriteContext` is the transaction state a keyed write reads and
nothing wider. It is built once per ``Transaction`` and handed in per call,
because nothing here is retained: this module is a composition rather than a
scope. Both representations reading one ``BufferedInserts`` through that context
is what makes a Typed insert followed by a Wire update of one object one
read-your-own-writes pair rather than two ingresses each with their own idea of
what this transaction stores.

Its ``spec/python.md`` §7 scope states what a keyed write reaches. A keyed write
addresses a row the caller already holds, so it resolves nothing from the store:
row-to-graph materialization, the read result, and the read lock are forbidden
here although the parent scope is granted all three, as are the write lowerings
the sibling scopes own. The Database Port, deep fetch, and navigation are NOT
among those exclusions and the row claims no such thing — a forbidden row is the
complement of a closure, and each of the three rides in through a dependency the
ingress does need: the port through the execution lifecycle the re-entry gate
requires, the two traversals through the Entity values a Typed write is stated
over.

Names crossing a module boundary are spelled bare; a helper whose every caller
lives here keeps its underscore. Privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import InstalledLifecycle, refuse_reentry
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    KeyedMutation,
    ObjectKey,
    SettledEvidence,
    SourceHint,
    UnitOfWork,
    object_key,
)
from parallax.core.unit_work.columns import freeze_retained_value
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedTemporalBounds,
    derive_keyed_write,
)

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._family import declaring as declaring_of
from parallax.snapshot.handle._write_inputs import (
    UPDATE_MUTATIONS,
    BufferedInserts,
    Provenance,
    WriteRepresentation,
    admit_and_buffer,
    cancels_a_pending_assignment,
    reject_temporal_delete,
    resolve_write_evidence,
    validate_provenance,
    validate_source_pin,
    validate_window,
    written_object_of_row,
)

__all__ = [
    "KeyedInsertSource",
    "KeyedWriteContext",
    "KeyedWriteSource",
    "OpenedKeyedWrite",
    "PreparedSourceWrite",
    "Provenance",
    "ResolvedKeyedInsert",
    "ResolvedKeyedWriteSource",
    "WriteRepresentation",
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
    hint: SourceHint | None
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
    canonical and owned; ``originals`` carries those same members' canonical
    original values. Both sides pass through the SAME producer inside the
    adapter, so the effective change set is a comparison of like with like
    whether the originals came from a Change Record or from a published row —
    and the comparison itself belongs to the ingress rather than to any adapter,
    so no source decides its own effectiveness.

    A destructive or close verb names no member, so ``originals`` is empty and
    the instruction is the identity row alone.
    """

    instruction: PreparedKeyedWrite
    object_key: ObjectKey
    originals: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "originals", _sealed_row(self.originals))


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
    and its Source Hint names this transaction's participation with NO
    observation — which is exactly what an opening row has observed. The write
    that follows is licensed by the buffered insert instead.
    """

    identity: EntityIdentity
    row: Mapping[str, object]
    object_key: ObjectKey
    hint: SourceHint


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
    Order (`python.md` §5).

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
    so there is no prior row for a second intent to compete for.
    """
    refuse_reentry(ctx.lifecycle)
    source.capture(mutation)
    meta = ctx.model.meta
    resolved = source.resolve(meta, mutation)
    identity_row = resolved.identity_row
    written = (
        None if identity_row is None else written_object_of_row(resolved.entity, meta, identity_row)
    )
    validate_provenance(
        resolved.entity.identity,
        resolved.provenance,
        mutation,
        inserted=ctx.inserts.holds(written),
        representation=resolved.representation,
    )
    validate_source_pin(resolved.entity.identity, resolved.pin)
    declaring = declaring_of(meta, resolved.entity)
    reject_temporal_delete(resolved.entity, declaring, mutation, surface="keyed")
    valid_from_managed, until_managed = validate_window(declaring, mutation, valid_from, until)
    prepared = source.prepare(resolved, PreparedTemporalBounds(valid_from_managed, until_managed))
    row, restorations = _effective_row(ctx, resolved, prepared, mutation)
    if row is None:
        return
    evidence: SettledEvidence | None = (
        None
        if ctx.inserts.holds(written)
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
    admit_and_buffer(
        ctx.uow,
        meta,
        derive_keyed_write(prepared.instruction, (row,)),
        evidence,
        restorations=restorations,
    )


def keyed_insert(
    ctx: KeyedWriteContext,
    opening: KeyedInsertSource,
    mutation: KeyedMutation,
    *,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> OpenedKeyedWrite:
    """Open a row through the insert's own door (`python.md` §5).

    The same three phases over the facts an opening row has, and the stages it
    has no meaning for are absent rather than guarded: nothing is restored, no
    prior state was observed, and no claim is taken. What remains beside the
    window and preparation is the pin the value's own view carries and the
    provenance it states — in that order, because a pinned value is one this
    store's read published, so both refusals stand over the one value and the
    read-only view is the more specific complaint. (On the source-backed door the
    two can never both be pending: a value the provenance rule refuses came from
    no read of this store at all, so it carries no view to be pinned.)

    The row this opens is recorded in the one ledger both representations read,
    which is what licenses the keyed write that follows it, and the answer names
    that row so a caller holding no Entity Class can revise it.
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
    valid_from_managed, until_managed = validate_window(
        declaring_of(meta, resolved.entity), mutation, valid_from, until
    )
    prepared = opening.prepare(resolved, PreparedTemporalBounds(valid_from_managed, until_managed))
    row = prepared.rows[0]
    admit_and_buffer(ctx.uow, meta, prepared, None)
    ctx.inserts.record(written_object_of_row(resolved.entity, meta, row))
    opened = object_key(prepared, meta)
    # A Create Payload is a complete document, so the row it buffers always names
    # its own object by the time validation has admitted it.
    assert opened is not None
    return OpenedKeyedWrite(
        identity=resolved.entity.identity,
        row=row,
        object_key=opened,
        hint=SourceHint(
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


def _effective_row(
    ctx: KeyedWriteContext,
    resolved: ResolvedKeyedWriteSource,
    prepared: PreparedSourceWrite,
    mutation: KeyedMutation,
) -> tuple[Mapping[str, object] | None, frozenset[str]]:
    """The row this write actually buffers and the members it restored, or
    ``None`` for the write that buffers nothing.

    One comparison rule, applied here rather than in either adapter, over values
    the adapter ran through one producer on both sides: a member whose authored
    value equals the original the source states was RESTORED, and what is left is
    the effective change set. A restoration is not nothing — it is the author's
    last word on that member — so a wholly restoring chain still buffers its
    identity row when this transaction already buffered an assignment at the
    scope it would claim, and the merged write is eliminated instead of writing
    a value the caller took back.

    A destructive or close verb names no member and always buffers its identity
    row: what it says about the row's existence is not a change set to reduce.
    """
    authored = prepared.instruction.rows[0]
    originals = prepared.originals
    identity = {name: value for name, value in authored.items() if name not in originals}
    if mutation not in UPDATE_MUTATIONS:
        return identity, frozenset()
    effective: dict[str, object] = {}
    restored: set[str] = set()
    for name, original in originals.items():
        if authored[name] == original:
            restored.add(name)
        else:
            effective[name] = authored[name]
    restorations = frozenset(restored)
    if effective:
        return {**identity, **effective}, restorations
    if not restorations or not cancels_a_pending_assignment(
        ctx.uow, ctx.model.meta, resolved.entity, resolved.hint, mutation
    ):
        return None, restorations
    return identity, restorations
