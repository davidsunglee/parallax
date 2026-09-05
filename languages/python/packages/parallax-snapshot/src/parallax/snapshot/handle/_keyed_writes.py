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
reduces no change set, settles against no evidence, and takes no claim.

What differs between the Typed verbs and ``tx.wire``'s is not that order but
where the facts it consumes come from — a Typed value carries its own Change
Record and lifecycle, a Wire source carries a frozen published row and a Source
Hint. A **Keyed Write Source** is that difference and nothing else: three phases,
run once each in the order above, answering the concrete Entity, the source Pin,
the Source Hint, the canonical identity row, the value's provenance, and the
canonical authored and original values of every named member. A source exposes
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

Its ``spec/python.md`` §7 scope states what a keyed write reaches. Snapshot
reads, deep fetch, navigation, the materializer, the Database Port, and the
predicate-selected lane all fall outside its closure although the parent scope is
granted every one: a keyed write addresses a row the caller already holds, so it
resolves nothing from the store and needs no connection to refuse being given
one.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import InstalledLifecycle
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import KeyedMutation, ObjectKey, SourceHint, UnitOfWork
from parallax.core.unit_work.instructions import PreparedKeyedWrite, PreparedTemporalBounds

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._write_inputs import BufferedInserts, Provenance

__all__ = [
    "KeyedInsertSource",
    "KeyedWriteContext",
    "KeyedWriteSource",
    "OpenedKeyedWrite",
    "PreparedSourceWrite",
    "Provenance",
    "ResolvedKeyedInsert",
    "ResolvedKeyedWriteSource",
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
    """

    entity: EntityMetadata
    pin: Pin | None
    hint: SourceHint | None
    identity_row: Mapping[str, object]
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class PreparedSourceWrite:
    """What a Keyed Write Source answers once the window has been judged.

    ``instruction`` carries the identity plus every member the caller named,
    canonical and owned; ``originals`` carries those same members' canonical
    original values. Both sides pass through the SAME producer inside the
    adapter, so the effective change set is a comparison of like with like
    whether the originals came from a Change Record or from a published row —
    and the comparison itself belongs to the ingress, so one rule decides
    effectiveness for both representations.

    A destructive or close verb names no member, so ``originals`` is empty and
    the instruction is the identity row alone.
    """

    instruction: PreparedKeyedWrite
    object_key: ObjectKey
    originals: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ResolvedKeyedInsert:
    """What a Keyed Insert Source answers about the row a verb opens.

    An opening row has no source: no pin stands over it, no read published it,
    and no prior value is restored by it. What remains is which Entity it is a
    row of and where the value itself came from, which is the one provenance
    answer an insert can be refused for — a value this store's own read produced
    names a row it already holds.
    """

    entity: EntityMetadata
    provenance: Provenance


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
    no pin, no hint, no identity row derived ahead of the instruction, and no
    originals to compare against. :meth:`prepare` answers the prepared write
    itself rather than a record pairing it with originals, because an insert
    reduces no effective change set.
    """

    def capture(self, mutation: KeyedMutation, /) -> None: ...

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert: ...

    def prepare(
        self, resolved: ResolvedKeyedInsert, bounds: PreparedTemporalBounds, /
    ) -> PreparedKeyedWrite: ...
