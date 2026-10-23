from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core._execution._unit_work.instructions import (
    INSERT_MUTATIONS,
    PreparedKeyedInstruction,
)
from parallax.core._execution._unit_work.retain import RetainedObservation
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey, VersionedObjectStateKey

__all__ = [
    "ClaimScope",
    "ClaimVerdict",
    "SettledEvidence",
    "WriteIntent",
    "admits",
    "admits_composed",
    "claim_scope",
    "claimed_object",
    "keyed_intent",
]

type WriteIntentKind = Literal["assignment", "destructive"]
"""What a buffered write means to do to what it claimed.

``assignment`` writes member values against a row that survives the write;
``destructive`` removes the row or closes the milestone.
"""

# The keyed mutations that write member values against a surviving row. The
# complement among non-insert mutations is destructive: `delete` removes the
# row outright, and `terminate` / `terminateUntil` close the milestone.
_ASSIGNMENT_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"amend", "amendUntil", "replace", "replaceUntil"}
)


@dataclass(frozen=True, slots=True)
class WriteIntent:
    """One buffered write's claim at one scope: what it does, over which
    Valid-Time window.

    The window is the one the prepared instruction carries, shared rather than
    copied — ``None`` for a non-temporal or Transaction-Time-Only write. It is
    part of the claim rather than payload beside it because two intents over
    DIFFERENT windows are incompatible by construction: composing them would
    require interval semantics this framework deliberately does not invent, so
    the second is refused and the caller flushes the first through a
    participating read.
    """

    kind: WriteIntentKind
    valid_time_window: TimeInterval | None = None


type ClaimScope = ObjectStateKey | ObjectKey
"""What one buffered write's claim is taken AT — the grain two intents must
share before either can affect the other.

A versioned or temporal existing-row write claims the exact
:data:`~parallax.core.write_plan.keys.ObjectStateKey` its source observed,
because two writes of one key that observed two different states are two
independent intents. An unversioned Non-Temporal existing-row write claims its
:class:`~parallax.core.write_plan.keys.ObjectKey`, because the shared row lock
its evidence rule demands is held on the OBJECT and covers every state the row
can be in — two such writes can never have observed two different states, so the
state-keyed rule's own reason does not apply and the object is the correct grain.
An insert claims nothing at all and reaches no scope.

Both keyed arms address ONE object, so an instruction naming SEVERAL rows reaches
no scope either: it has no single object and no single observed state. Only a
caller holding a pre-formed multi-row instruction can author one — a keyed
developer verb writes the one row the value it was handed names — and every
admitted write is single-row, so such an instruction is refused before it takes
any claim, whatever evidence its caller supplies.

Which arm a write takes is derived from declared facts — the target Entity's
Optimistic Key and the write's own mutation — never from an absent observation:
an insert observes no state either, so an absence-triggered object claim would
sweep it in.
"""


type SettledEvidence = RetainedObservation | VersionedObjectStateKey | ObjectKey
"""What one keyed write against existing state settles against, in the three
shapes a source can supply — which is also what decides the admitted write it
becomes and the claim it takes:

* a RETAINED observation is a read's own claim on one exact observed state: the
  write settles against that state and claims it;
* a VERSIONED STATE is the protected current state a versioned Non-Temporal
  source's authority reaches — the state it observed, or the one this
  attempt's own completed writes left it at — which the write settles against
  and claims, its source's observation travelling beside it unchanged;
* an OBJECT KEY is what an unversioned Non-Temporal row's write settles against.
  Its evidence is the shared row lock, which is held on the object rather than on
  a state, so the object is what it claims; the source the write is admitted
  through travels beside it.

A write against existing state that addresses no single object is derived
neither and settles against nothing: an instruction naming several rows, or a
row naming no complete primary key, has neither a state nor an object for
evidence to be about. A caller can still hold one of the two and supply it with
such a write, and the admitted write it would travel in refuses that pairing;
without either, no admitted write licenses it at all.
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
    return evidence


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
intent replaces the assignments buffered before it, so an amendment followed by a
delete at one scope emits one delete. ``deduplicate`` — an identical destructive
intent is already buffered and the second adds nothing. ``incompatible`` — the
two cannot be combined, and the arriving verb refuses.
"""


def keyed_intent(instruction: PreparedKeyedInstruction) -> WriteIntent | None:
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
    return WriteIntent(kind=kind, valid_time_window=instruction.valid_time_window)


def admits(held: WriteIntent | None, arriving: WriteIntent) -> ClaimVerdict:
    """What ``arriving`` becomes against the ``held`` claim at one scope, or
    against ``None`` where nothing claims that scope yet.

    The unclaimed row belongs here rather than in each consumer, which is what
    makes this function the whole rule: a caller answers every ``(held,
    arriving)`` pair by asking once, and the verb-time seam and the flush cannot
    disagree about the one row a second implementation would have had to repeat.

    The rule reads in the order the incompatibilities appear:

    * an unclaimed scope admits whatever arrives;
    * different Valid-Time windows never compose, because interval composition
      is semantics this framework does not invent;
    * an assignment after a destruction is a resurrection, which no write means;
    * two destructions of one scope and window are one destruction; and
    * everything else combines — assignments merge, and a destruction supersedes
      the assignments buffered before it.
    """
    if held is None:
        return "admit"
    if held.valid_time_window != arriving.valid_time_window:
        return "incompatible"
    if held.kind == "destructive":
        return "deduplicate" if arriving.kind == "destructive" else "incompatible"
    return "coalesce" if arriving.kind == "assignment" else "supersede"


def admits_composed(
    held: Iterable[tuple[ClaimScope | None, WriteIntent]],
    scope: ClaimScope | None,
    arriving: WriteIntent,
) -> Literal["compose", "incompatible"]:
    """Whether ``arriving``, a temporal object's observed write at ``scope``,
    composes with the writes of that object ``held`` already pending, each at
    its own scope.

    Assignments compose in authored order whatever their windows or scopes:
    later values win per member where windows overlap, and every earlier
    condition stays. Destruction composes only where it cannot be undone or
    half-applied: no assignment follows a destruction at the same scope or over
    an overlapping window — a resurrection — and a destruction overlapping any
    other write, or sharing its scope, must state exactly that write's window,
    superseding an assignment there or repeating a destruction.
    """
    for held_scope, intent in held:
        same_scope = scope is not None and held_scope == scope
        overlapping = _overlaps(intent, arriving)
        if arriving.kind == "assignment":
            if intent.kind == "destructive" and (same_scope or overlapping):
                return "incompatible"
        elif (same_scope or overlapping) and intent.valid_time_window != arriving.valid_time_window:
            return "incompatible"
    return "compose"


def _overlaps(first: WriteIntent, second: WriteIntent) -> bool:
    """Whether two intents' requested windows share any instant; an intent
    without Valid Time spans the whole axis."""
    first_window = first.valid_time_window
    second_window = second.valid_time_window
    return first_window is None or second_window is None or first_window.overlaps(second_window)
