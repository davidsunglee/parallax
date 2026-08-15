"""Retained write evidence and the source values that own it (m-unit-work).

Evidence belongs to the VALUE a read produced, not to the transaction that ran
the read. A standalone read has no transaction to file into and still produces
values a later optimistic write may settle against, so the observation is
reachable from the source and the transaction keeps only a weak index of what it
has seen plus the participation its own reads license.

Two consequences fall out of the ownership rather than being maintained:
liveness IS strong reachability — an observation stays eligible exactly while
some source value or buffered write still reaches it — and several observed
states of one object coexist as distinct :class:`RetainedObservation`\\ s reached
from distinct values, so rereading a row never upgrades the evidence an older
live value carries.

Bare (non-underscored) names here are intra-package shared infrastructure, for
the reason :mod:`~parallax.core.unit_work.planner` states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import Pin
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.planner import ObjectKey, ObservedStateKey

__all__ = ["ParticipationToken", "RetainedObservation", "SourceHint"]


class ParticipationToken:
    """One unit of work's participation identity.

    Handed out by the unit of work and compared by identity alone, which is the
    whole of what it is for: a source value carries the token of the unit of work
    whose read produced it, and an effective-Locking write asks whether that
    token is the writing transaction's own — the proof that the shared row lock
    this write relies on is still held.

    It is a token rather than the unit of work itself so that evidence outliving
    a transaction keeps no reference to the transaction's buffer, planner, or
    connection.
    """

    __slots__ = ()


class RetainedObservation:
    """One observed state's evidence, owned by the values that observed it.

    ``key`` is the exact state the evidence is about, ``evidence`` the database
    evidence itself, and ``participation`` the unit of work whose read produced
    it — absent for a standalone read, which participates in nothing.

    :attr:`consumed` is the one mutable fact, and it moves one way. It lives on
    this shared object rather than in a transaction-side set because consumption
    must OUTLIVE the flushing transaction: a later transaction handed the same
    still-live source must be refused, and a set that died with the flush could
    not say so.
    """

    __slots__ = ("__weakref__", "_consumed", "evidence", "key", "participation")

    def __init__(
        self,
        key: ObservedStateKey,
        evidence: WriteObservation,
        participation: ParticipationToken | None,
    ) -> None:
        self.key: Final = key
        self.evidence: Final = evidence
        self.participation: Final = participation
        self._consumed = False

    @property
    def consumed(self) -> bool:
        """Whether a successful flush has already spent this evidence.

        A consumed source stays an ordinary readable value; what it no longer
        carries is authority, because the state it observed is not the stored
        state any more.
        """
        return self._consumed

    def consume(self) -> None:
        """Spend this evidence, at the successful flush of a write that used it."""
        self._consumed = True


@dataclass(frozen=True, slots=True)
class SourceHint:
    """What one source value privately retains about the read that produced it.

    Never authority of its own: it names the concrete Entity the read resolved
    the row to, the object that row denotes, the participation its read
    licensed, the as-of coordinates the read stood at, and the observation
    retained for its exact state — and a keyed write then decides what those
    facts license under the target Entity's own Effective Concurrency Strategy.

    ``observation`` is absent for an unversioned Non-Temporal row, which
    observes no state at all; ``participation`` is absent for a standalone read;
    ``pin`` is absent for a row whose family declares no As-Of Axis, exactly as
    a Typed node's own lifecycle state leaves it absent there. A value that
    carries no hint carried no read behind it, which is the one answer a
    caller-built value can ever give.

    The pin rides here because a representation with no lifecycle state of its
    own has nowhere else to keep it: a frozen Wire node's whole provenance is
    this record, and the Transaction-Time past is read-only through every keyed
    verb, Typed and Wire alike.
    """

    entity: EntityIdentity
    object_key: ObjectKey
    participation: ParticipationToken | None
    observation: RetainedObservation | None
    pin: Pin | None = None
