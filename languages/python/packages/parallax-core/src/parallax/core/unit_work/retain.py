from __future__ import annotations

from typing import Final, Protocol, cast

from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import Pin
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.planner import ObjectKey, ObservedStateKey

__all__ = ["InsertionIdentity", "ParticipationToken", "ReadOrigin", "RetainedObservation"]


class InsertionIdentity:
    """The authority one admitted insertion grants the source values that carry it.

    Issued by a unit of work when it admits an insertion, carried privately by
    the inserted source and every value derived from it afterwards, and compared
    by identity alone: an equal key, an equal address, or an equal instant never
    stands for it. ``object_key`` names the object the insertion opened.

    It holds no reference to the unit of work that issued it, so a source
    outliving its attempt keeps nothing of that attempt alive; whether the
    identity still licenses a write is the issuing unit of work's answer alone.
    """

    __slots__ = ("object_key",)

    def __init__(self, object_key: ObjectKey) -> None:
        self.object_key: Final = object_key


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


class _DeferredReadEvidence(Protocol):
    @property
    def entity(self) -> EntityIdentity: ...

    def object_key(self) -> ObjectKey: ...

    def observation(self) -> RetainedObservation: ...


_CONSUMED: Final = 1
_INVALIDATED: Final = 2


class RetainedObservation:
    """One observed state's evidence, owned by the values that observed it.

    ``key`` is the exact state the evidence is about, ``evidence`` the database
    evidence itself, and ``participation`` the unit of work whose read produced
    it — absent for a standalone read, which participates in nothing.

    :attr:`consumed` and :attr:`invalidated` are the two mutable facts, and each
    moves one way. They live on this shared object rather than in a
    transaction-side set because both must OUTLIVE the transaction that set
    them: a later transaction handed the same still-live source must be refused,
    and a set that died with the flush could not say so.
    """

    __slots__ = ("__weakref__", "_spent", "evidence", "key", "participation")

    def __init__(
        self,
        key: ObservedStateKey,
        evidence: WriteObservation,
        participation: ParticipationToken | None,
    ) -> None:
        self.key: Final = key
        self.evidence: Final = evidence
        self.participation: Final = participation
        # Both one-way facts in one slot, since every retained read pays for it:
        # `_CONSUMED` and `_INVALIDATED` bits.
        self._spent = 0

    @property
    def consumed(self) -> bool:
        """Whether a successful flush has already spent this evidence.

        A consumed source stays an ordinary readable value; what it no longer
        carries is authority, because the state it observed is not the stored
        state any more.
        """
        return bool(self._spent & _CONSUMED)

    def consume(self) -> None:
        """Spend this evidence, at the successful flush of a write that used it."""
        self._spent |= _CONSUMED

    @property
    def invalidated(self) -> bool:
        """Whether a successful change of this transaction's own has since
        revised, closed, or removed the state this evidence describes.

        Distinct from consumption, which records that a write spent this
        evidence: an observation no write ever used is still invalidated when
        another write changes its state, even when the changed row keeps the
        same address and revision token.
        """
        return bool(self._spent & _INVALIDATED)

    def invalidate(self) -> None:
        """Record that a successful own change replaced the observed state."""
        self._spent |= _INVALIDATED


class _Spent:
    """An observation-free origin's context once a write completed through it."""

    __slots__ = ("context",)

    def __init__(
        self, context: ParticipationToken | Pin | tuple[ParticipationToken, Pin] | None
    ) -> None:
        self.context: Final = context


class ReadOrigin:
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

    An origin with no observation still carries one mutable fact, moving one
    way: whether a successful write already completed through it
    (:attr:`consumed`). Every value derived from the source shares the origin,
    so completing through one spends them all; an origin with an observation
    defers both questions to that shared observation instead.

    The pin rides here because a representation with no lifecycle state of its
    own has nowhere else to keep it: a frozen Wire node's whole provenance is
    this record, and the Transaction-Time past is read-only through every keyed
    verb, Typed and Wire alike.
    """

    __slots__ = ("_context", "_source")

    _context: ParticipationToken | Pin | tuple[ParticipationToken, Pin] | _Spent | None
    _source: (
        ObjectKey
        | tuple[ObjectKey, RetainedObservation]
        | tuple[EntityIdentity, str, object]
        | _DeferredReadEvidence
    )

    def __init__(
        self,
        entity: EntityIdentity,
        object_key: ObjectKey,
        participation: ParticipationToken | None,
        observation: RetainedObservation | None,
        pin: Pin | None = None,
    ) -> None:
        object.__setattr__(
            self, "_source", object_key if observation is None else (object_key, observation)
        )
        object.__setattr__(
            self,
            "_context",
            (participation, pin)
            if participation is not None and pin is not None
            else participation or pin,
        )

    @classmethod
    def from_single_primary_key(
        cls,
        entity: EntityIdentity,
        name: str,
        value: object,
        participation: ParticipationToken | None,
    ) -> ReadOrigin:
        origin = object.__new__(cls)
        object.__setattr__(origin, "_source", (entity, name, value))
        object.__setattr__(origin, "_context", participation)
        return origin

    @classmethod
    def deferred(
        cls,
        entity: EntityIdentity,
        evidence: _DeferredReadEvidence,
        *,
        pin: Pin | None,
    ) -> ReadOrigin:
        if evidence.entity != entity:
            raise ValueError("deferred read evidence must name its origin's Entity")
        origin = object.__new__(cls)
        object.__setattr__(origin, "_source", evidence)
        object.__setattr__(origin, "_context", pin)
        return origin

    @property
    def entity(self) -> EntityIdentity:
        source = self._source
        if isinstance(source, ObjectKey):
            return source.entity
        if isinstance(source, tuple):
            if isinstance(source[0], ObjectKey):
                return cast("tuple[ObjectKey, RetainedObservation]", source)[0].entity
            return cast("tuple[EntityIdentity, str, object]", source)[0]
        return source.entity

    @property
    def participation(self) -> ParticipationToken | None:
        context = self._context
        if isinstance(context, _Spent):
            context = context.context
        if isinstance(context, ParticipationToken):
            return context
        return context[0] if isinstance(context, tuple) else None

    @property
    def pin(self) -> Pin | None:
        context = self._context
        if isinstance(context, _Spent):
            context = context.context
        if isinstance(context, Pin):
            return context
        return context[1] if isinstance(context, tuple) else None

    @property
    def consumed(self) -> bool:
        """Whether a successful write already completed through this source.

        Answered by the shared observation where the origin has one, and by the
        origin itself otherwise.
        """
        observation = self.observation
        if observation is not None:
            return observation.consumed
        return isinstance(self._context, _Spent)

    def consume(self) -> None:
        """Spend this source's authority, once a write through it completed."""
        observation = self.observation
        if observation is not None:
            observation.consume()
            return
        context = self._context
        if not isinstance(context, _Spent):
            object.__setattr__(self, "_context", _Spent(context))

    def __setattr__(self, name: str, value: object) -> None:
        del value
        raise AttributeError(f"a Read Origin is immutable: cannot set {name!r}")

    @property
    def object_key(self) -> ObjectKey:
        source = self._source
        if isinstance(source, ObjectKey):
            return source
        if isinstance(source, tuple):
            if isinstance(source[0], ObjectKey):
                return cast("tuple[ObjectKey, RetainedObservation]", source)[0]
            entity, name, value = cast("tuple[EntityIdentity, str, object]", source)
            held = ObjectKey(entity, ((name, value),))
            object.__setattr__(self, "_source", held)
            return held
        held = source.object_key()
        object.__setattr__(self, "_source", (held, source.observation()))
        return held

    @property
    def observation(self) -> RetainedObservation | None:
        source = self._source
        if isinstance(source, ObjectKey) or (
            isinstance(source, tuple) and not isinstance(source[0], ObjectKey)
        ):
            return None
        if isinstance(source, tuple):
            return cast("tuple[ObjectKey, RetainedObservation]", source)[1]
        key = source.object_key()
        held = source.observation()
        object.__setattr__(self, "_source", (key, held))
        return held

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ReadOrigin) and (
            self.entity,
            self.object_key,
            self.participation,
            self.observation,
            self.pin,
        ) == (
            other.entity,
            other.object_key,
            other.participation,
            other.observation,
            other.pin,
        )

    def __hash__(self) -> int:
        return hash((self.entity, self.object_key, self.participation, self.observation, self.pin))

    def __repr__(self) -> str:
        return (
            "ReadOrigin("
            f"entity={self.entity!r}, object_key={self.object_key!r}, "
            f"participation={self.participation!r}, observation={self.observation!r}, "
            f"pin={self.pin!r})"
        )
