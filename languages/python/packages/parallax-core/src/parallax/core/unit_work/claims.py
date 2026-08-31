"""What a buffered write intends, where it claims it, and what a second intent
may do to it (`m-unit-work` "Observed-State Coalescing").

One claim scope may back several buffered writes before a flush, and this
module states the only question that decides whether it may: given the intent a
buffer already holds at a scope, what does an arriving intent become? The
answer is one closed verdict, and both consumers read it — the developer verb,
which refuses `write-evidence-already-claimed` synchronously for the
incompatible answers, and the Write Planner, which performs the compatible ones
while it coalesces. Stating it once is what makes it impossible for the
synchronous refusal to disagree with what the flush would have done.

Bare (non-underscored) names here are intra-package shared infrastructure, for
the reason :mod:`~parallax.core.unit_work.planner` states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.unit_work.instructions import INSERT_MUTATIONS, PreparedKeyedWrite
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.planner import ObjectKey, ObservedStateKey
from parallax.core.unit_work.retain import RetainedObservation

__all__ = [
    "SELECTION_INTENT",
    "ClaimScope",
    "ClaimTable",
    "ClaimVerdict",
    "SettledEvidence",
    "WriteIntent",
    "WriteIntentKind",
    "admits",
    "claim_scope",
    "claimed_object",
    "keyed_intent",
]

type WriteIntentKind = Literal["assignment", "destructive", "selection"]
"""What a buffered write means to do to what it claimed.

``assignment`` writes member values against a row that survives the write;
``destructive`` removes the row or closes the milestone; ``selection`` is a
Materialized Write Group's own claim over every state its predicate resolved,
which is a whole compact unit rather than a per-object intent a later write
could join.
"""

# The keyed mutations that write member values against a surviving row. The
# complement among non-insert mutations is destructive: `delete` removes the
# row outright, and `terminate` / `terminateUntil` close the milestone.
_ASSIGNMENT_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})


@dataclass(frozen=True, slots=True)
class WriteIntent:
    """One buffered write's claim at one scope: what it does, over which
    temporal region.

    The region is the authored Valid-Time window exactly as the instruction
    carries it — absent on both ends for a non-temporal or Transaction-Time-Only
    write. It is part of the claim rather than payload beside it because two
    intents over DIFFERENT regions are incompatible by construction: composing
    them would require interval semantics this framework deliberately does not
    invent, so the second is refused and the caller flushes the first through a
    participating read.
    """

    kind: WriteIntentKind
    valid_from: object | None = None
    until: object | None = None

    @property
    def region(self) -> tuple[object | None, object | None]:
        """The temporal region this intent claims — its two Valid-Time bounds."""
        return (self.valid_from, self.until)


SELECTION_INTENT: Final = WriteIntent(kind="selection")
"""The claim a Materialized Write Group takes on every state its predicate
resolved. It is one intent value rather than one per row because a group carries
no region of its own to compare: it is indivisible, and every keyed intent
against a state it selected is incompatible with it."""


type ClaimScope = ObservedStateKey | ObjectKey
"""What one buffered write's claim is taken AT — the grain two intents must
share before either can affect the other.

A versioned or temporal existing-row write claims the exact
:data:`~parallax.core.unit_work.planner.ObservedStateKey` its source observed,
because two writes of one key that observed two different states are two
independent intents. An unversioned Non-Temporal existing-row write claims its
:class:`~parallax.core.unit_work.planner.ObjectKey`, because the shared row lock
its evidence rule demands is held on the OBJECT and covers every state the row
can be in — two such writes can never have observed two different states, so the
state-keyed rule's own reason does not apply and the object is the correct grain.
An insert claims nothing at all and reaches no scope.

Both keyed arms address ONE object, so an instruction naming SEVERAL rows reaches
no scope either: it has no single object and no single observed state. Only a
caller holding a pre-formed multi-row instruction can author one — a keyed
developer verb writes the one row the value it was handed names — and where that
caller supplies no evidence of its own, the write claims nothing and buffers
bare. Evidence such a caller does supply is refused by the single-row carrier
that would have had to hold it, before the write takes any claim, rather than
dropped in favour of the bare shape.

Which arm a write takes is derived from declared facts — the target Entity's
Optimistic Key and the write's own mutation — never from an absent observation:
an insert observes no state either, so an absence-triggered object claim would
sweep it in.
"""


type SettledEvidence = WriteObservation | RetainedObservation | ObjectKey
"""What one keyed write against existing state settles against, in the three
shapes a producer can hold — which is also what decides the buffer item it
becomes and the claim it takes:

* a RETAINED observation is a read's own claim on one exact observed state: the
  write settles against that state, claims it, and a successful flush spends it;
* a caller-HELD Write Observation is that same evidence as a plain value: the
  write settles against the state it describes and claims nothing, because there
  is no reference into this scope's ledger for a second intent to compete for;
* an OBJECT KEY is what an unversioned Non-Temporal row's write settles against.
  Its evidence is the shared row lock, which is held on the object rather than on
  a state, so the object is what it claims and there is nothing for a flush to
  spend.

A write against existing state that addresses no single object is derived none of
the three and settles against nothing: an instruction naming several rows, or a
row naming no complete primary key, has neither a state nor an object for
evidence to be about. A caller can still hold one of the three and supply it with
such a write, and the carrier it would travel in refuses that pairing rather than
settling the write bare.
"""


def claim_scope(evidence: SettledEvidence | None) -> ClaimScope | None:
    """The scope the write settling against ``evidence`` claims, or ``None``
    where it claims nothing.

    Total over the three shapes above, so a caller reads one answer rather than
    pairing an evidence value with a separately derived address that could name
    a different state than the evidence it travels with.
    """
    if isinstance(evidence, RetainedObservation):
        return evidence.key
    if isinstance(evidence, ObjectKey):
        return evidence
    return None


def claimed_object(scope: ClaimScope) -> ObjectKey:
    """The object ``scope`` addresses — itself for an object-scoped claim, and the
    identity half of the state for a state-scoped one.

    What a refusal reports is which OBJECT was refused; the observed state behind
    a state-scoped claim stays implementation detail.
    """
    return scope if isinstance(scope, ObjectKey) else scope.object


type ClaimVerdict = Literal["admit", "coalesce", "supersede", "deduplicate", "incompatible"]
"""What an arriving intent becomes against the intent a buffer already holds.

``admit`` — nothing claimed this scope yet. ``coalesce`` — the two assignments
merge in authored order into one surviving write. ``supersede`` — a destructive
intent replaces the assignments buffered before it, so an update followed by a
delete at one scope emits one delete. ``deduplicate`` — an identical destructive
intent is already buffered and the second adds nothing. ``incompatible`` — the
two cannot be combined, and the arriving verb refuses.
"""


def keyed_intent(instruction: PreparedKeyedWrite) -> WriteIntent | None:
    """What ``instruction`` intends against existing state, or ``None`` for an
    insert, which intends nothing against any.

    An insert opens a row rather than writing against one, so it claims nothing;
    every other keyed mutation is an assignment or a destruction of the existing
    row it addresses, whichever scope that row's claim is taken at.

    An intent is not itself a claim: a write takes one only where it also reaches
    a scope, so an instruction naming several rows carries the intent its mutation
    states and still claims nothing, having no single scope to claim at.
    """
    if instruction.mutation in INSERT_MUTATIONS:
        return None
    kind: WriteIntentKind = (
        "assignment" if instruction.mutation in _ASSIGNMENT_MUTATIONS else "destructive"
    )
    return WriteIntent(
        kind=kind,
        valid_from=instruction.bounds.valid_from,
        until=instruction.bounds.until,
    )


def admits(held: WriteIntent | None, arriving: WriteIntent) -> ClaimVerdict:
    """What ``arriving`` becomes against the ``held`` claim at one scope, or
    against ``None`` where nothing claims that scope yet.

    The unclaimed row belongs here rather than in each consumer, which is what
    makes this function the whole rule: a caller answers every ``(held,
    arriving)`` pair by asking once, and the verb-time seam and the flush cannot
    disagree about the one row a second implementation would have had to repeat.

    The rule reads in the order the incompatibilities appear:

    * an unclaimed scope admits whatever arrives;
    * a Materialized Write Group's selection claim admits nothing beside it, in
      either direction — the group is compact and indivisible, so merging a keyed
      assignment into it would mean indexing and mutating it;
    * different temporal regions never compose, because interval composition is
      semantics this framework does not invent;
    * an assignment after a destruction is a resurrection, which no write means;
    * two destructions of one scope and region are one destruction; and
    * everything else combines — assignments merge, and a destruction supersedes
      the assignments buffered before it.
    """
    if held is None:
        return "admit"
    if "selection" in (held.kind, arriving.kind):
        return "incompatible"
    if held.region != arriving.region:
        return "incompatible"
    if held.kind == "destructive":
        return "deduplicate" if arriving.kind == "destructive" else "incompatible"
    return "coalesce" if arriving.kind == "assignment" else "supersede"


class ClaimTable:
    """The claims one buffer holds, by the scope each is taken at.

    Buffer-scoped and no wider: a flush spends the buffer it planned and the
    claims travel out with it, so what a later write may claim is decided
    by what is still pending rather than by everything this unit of work has
    ever written. An abort drops both together for the same reason.
    """

    __slots__ = ("_held",)

    def __init__(self) -> None:
        self._held: dict[ClaimScope, WriteIntent] = {}

    def claim(self, key: ClaimScope, intent: WriteIntent) -> ClaimVerdict:
        """Take ``intent``'s claim at ``key``, answering what it became.

        The verdict is :func:`admits`' alone, unclaimed row included, so this
        table decides nothing of its own and stays the storage the rule is
        applied to.

        What it is left holding is what the buffer will actually carry after the
        verdict: an admitted or coalescing intent replaces the held one, a
        superseding destruction replaces it too, and a deduplicated or
        incompatible intent leaves it untouched — the first because the second
        adds nothing, the second because the arriving verb is about to refuse.
        """
        verdict = admits(self._held.get(key), intent)
        if verdict in ("admit", "coalesce", "supersede"):
            self._held[key] = intent
        return verdict

    def held(self, key: ClaimScope) -> WriteIntent | None:
        """What this buffer currently claims at ``key``, if anything — the read
        side of :meth:`claim`, for a verb deciding whether it has an earlier
        intent to combine with at all."""
        return self._held.get(key)

    def clear(self) -> None:
        """Drop every claim — the buffer that held them is gone."""
        self._held.clear()
