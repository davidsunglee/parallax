"""``parallax.core.txtime_write`` enforcement scope (m-txtime-write).

The Transaction-Time-Only milestone-chaining PLANNING scope: it renders no SQL,
takes no dialect, and imports neither ``opt_lock`` nor ``sql_gen``. It owns the
MILESTONE ARITHMETIC alone — which milestone closes, why, and which current rows
the mutation chains — and it contributes that arithmetic to write finalization as
a neutral topology description rather than as statements
(`m-txtime-write.md` "What this module contributes to planning").

Three mutations, one topology each (`m-txtime-write.md` "Milestone-chaining
writes"):

- **insert** — no closure and one successor carrying the authored row alone: a
  fresh lineage opened over ``[txInstant, infinity)``.
- **terminate** — a `Terminated` closure and no successor: the terminated state
  is the ABSENCE of any current row.
- **update** — a `Superseded` closure and one successor carrying the
  predecessor's state with the authored change set overlaid. A public
  ``tx.update(copy)`` authors a SPARSE row, so an unauthored member carries
  forward from the observed current milestone unchanged, exactly like its
  bitemporal sibling; a caller-authored FULL row overlays to itself.

The description is scoped to the authored mutation, never to a resolved row: it
names no instant, no bound value, no observation, and no payload, so one
description serves every row a predicate-selected mutation resolves. Finalization
applies it (`~parallax.core.unit_work.temporal.expand_milestone`), addresses the
close through a Milestone Target, and decides from the transaction's concurrency
mode whether the gate basis this module names becomes a Temporal Gate or the
explicit `Ungated` decision (`m-opt-lock`).

Prior art (Reladomo; semantics, not idioms): close-then-chain mirrors
``AuditOnlyTemporalDirector.update`` / ``.inactivate`` — the close-old-insert-new
discipline research §6 documents; the observed-``in_z`` gate basis is Reladomo's
own ``IN_Z`` optimistic rule, extended from a version column to a milestone's own
Transaction-Time start; ``terminate`` (audit-preserving: closes, chains nothing) is
Reladomo's dated ``terminate()``, deliberately NOT its MAY-tier physical ``purge``
(`m-bitemp-write` "MAY-tier mutations").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core import temporal_read
from parallax.core.metamodel import EntityMetadata, Metamodel, TemporalDimension
from parallax.core.unit_work import (
    AUTHORED_STATE,
    CHANGED_STATE,
    SUPERSEDED,
    TERMINATED,
    MilestoneClosure,
    MilestoneSuccessor,
    MilestoneTopology,
)

__all__ = [
    "MILESTONE_CHAIN",
    "TemporalPlanningError",
    "TransactionTimeChaining",
    "axis_attr_names",
]

_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
_TERMINATE_MUTATIONS: Final[frozenset[str]] = frozenset({"terminate", "terminateUntil"})
_UPDATE_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})

# The one axis this facet closes on, and therefore the one an optimistic close
# gates on: a Transaction-Time-Only milestone carries no other start to observe.
_GATE_BASIS: Final[TemporalDimension] = TemporalDimension.TRANSACTION_TIME


class TemporalPlanningError(ValueError):
    """A temporal mutation cannot be described (a shape this scope's own caller
    is responsible for never producing, e.g. a verb this facet does not
    recognize; a defensive backstop, not a normal-path outcome for a well-formed
    instruction)."""


@dataclass(frozen=True, slots=True)
class TransactionTimeChaining:
    """The Transaction-Time-Only facet's topology answer."""

    def topology(self, mutation: str) -> MilestoneTopology:
        """``mutation``'s neutral close-and-chain topology.

        A ``*Until`` verb reaching this facet carries a Valid-Time bound the
        target declares no axis for, so its successor has no window and the
        bound is simply unused — the verb chains exactly as its unbounded
        sibling does.
        """
        if mutation in _INSERT_MUTATIONS:
            return MilestoneTopology(
                closure=None, successors=(MilestoneSuccessor(state=AUTHORED_STATE),)
            )
        if mutation in _TERMINATE_MUTATIONS:
            return MilestoneTopology(
                closure=MilestoneClosure(cause=TERMINATED, gate_basis=_GATE_BASIS), successors=()
            )
        if mutation in _UPDATE_MUTATIONS:
            return MilestoneTopology(
                closure=MilestoneClosure(cause=SUPERSEDED, gate_basis=_GATE_BASIS),
                successors=(MilestoneSuccessor(state=CHANGED_STATE),),
            )
        raise TemporalPlanningError(
            f"{mutation!r} is not a Transaction-Time-Only milestone mutation"
        )


MILESTONE_CHAIN: Final[TransactionTimeChaining] = TransactionTimeChaining()


def axis_attr_names(
    model: Metamodel, entity: EntityMetadata, dimension: TemporalDimension
) -> tuple[str, str]:
    """``entity``'s effective Attribute names for a temporal dimension.

    A temporal entity's interval columns are ordinary declared attributes, and a
    milestone row is Attribute-named like any other neutral write row, so this is
    how a mutation's opened rows name the axis bounds they stamp. The axes are
    family-wide and root-owned, so they are read through the Temporal Facet: a
    concrete subtype answers with its family's axes without the caller resolving
    a declaring position first.
    """
    axis = temporal_read.view(model).axis(entity.identity, dimension)
    if axis is None:
        raise TemporalPlanningError(
            f"{entity.identity.name} declares no {dimension.name} temporal dimension"
        )
    return axis.start_attribute.name, axis.end_attribute.name
