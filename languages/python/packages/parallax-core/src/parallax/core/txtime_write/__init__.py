"""``parallax.core.txtime_write`` enforcement scope (m-txtime-write).

The Transaction-Time-Only milestone-chaining PLANNING scope: this module
never renders SQL and never imports ``opt_lock`` / ``dialect`` / ``sql_gen`` — it
owns the MILESTONE ARITHMETIC only (which rows close, which chain, statement
shape) as **pure functions** over ``(instruction, observed row, tx instant)``.
``parallax.snapshot.handle`` is the one seam that renders SQL: it composes this
scope's neutral :class:`MilestonePlan` with the ``opt_lock`` gate/licensing policy
(`core/spec/m-opt-lock.md` "Temporal entities derive the version from the
Transaction-Time dimension") and the descriptor-driven column/tag machinery it already owns
for non-temporal writes.

Three mutations, one shape each (`m-txtime-write.md` "Milestone-chaining writes"):

- **insert** — a single :class:`MilestoneOpen`: the instruction's own authored row
  plus the fresh Transaction-Time bounds ``[txInstant, infinity)``.
- **terminate** — a single :class:`MilestoneClose`: close the current row
  (``out_z = txInstant``) and chain nothing — the terminated state is the
  ABSENCE of any ``out_z = infinity`` row.
- **update** — a :class:`MilestoneClose` immediately followed by a
  :class:`MilestoneOpen` carrying the instruction's own row MERGED onto the
  observed payload (mirrors
  the bitemporal rectangle split's own observed-payload carry-forward,
  `m-bitemp-write` "Head/tail old values come from the observed prior
  rectangle") — a public ``tx.update(copy)`` authors a SPARSE row (primary key
  plus effective change set only, `python.md` §3/§5), so an unauthored field
  carries FORWARD from the observed current milestone unchanged, exactly like
  its bitemporal sibling; a caller-authored FULL row (every conformance-engine
  writeSequence witness) merges to itself (an identity, since every member the
  merge could overlay is already present in the caller's own row). Close-
  before-chain, the pair adjacent (`m-txtime-write.md` L96-109).

The close's ADDRESS is the key plus one exclusive upper bound per As-Of Axis, so
a Transaction-Time-Only close addresses ``out_z = infinity`` alone
(:attr:`MilestoneClose.target_valid_end` is ``None``) and is identical in both
concurrency modes (ADR 0046). Only the close's gate CANDIDATE
(:attr:`MilestoneClose.gate_tx_start`) comes from the caller-supplied
``observed`` :class:`~parallax.core.unit_work.TemporalObservation` —
this scope never decides WHETHER to gate (that is the ``opt_lock`` policy
composed at the render seam) or issues an implicit read to find one (`m-txtime-write`
"Affected-row conflict contract for closes": the observed ``in_z`` is the version
analogue a temporal entity carries no version column for). A zero-row close is an
error in ANY mode — this scope names the row it EXPECTS to affect (exactly one,
always, for a close) only implicitly, via its own :class:`MilestoneClose` shape;
the render seam is what turns that shape into the ``expected_affected`` check and
picks the retriable-vs-non-retriable error class (`m-opt-lock.OptimisticLockConflictError`
/ `.StaleWriteError`) from whether it actually rendered the gate.

Prior art (Reladomo; semantics, not idioms): close-then-chain mirrors
``AuditOnlyTemporalDirector.update`` / ``.inactivate`` — the close-old-insert-new
discipline research §6 documents; the observed-``in_z`` gate is Reladomo's own
``IN_Z`` optimistic rule, extended from a version column to a milestone's own
Transaction-Time start; ``terminate`` (audit-preserving: closes, chains nothing) is
Reladomo's dated ``terminate()``, deliberately NOT its MAY-tier physical ``purge``
(`m-bitemp-write` "MAY-tier mutations").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, cast

from parallax.core import temporal_read
from parallax.core.base import INFINITY_LITERAL
from parallax.core.metamodel import EntityMetadata, Metamodel, TemporalDimension
from parallax.core.unit_work import KeyedWrite, TemporalObservation

__all__ = [
    "MilestoneClose",
    "MilestoneOpen",
    "MilestonePlan",
    "MilestoneStep",
    "TemporalPlanningError",
    "axis_attr_names",
    "observed_bound",
    "observed_tx_start",
    "plan",
]

_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
_TERMINATE_MUTATIONS: Final[frozenset[str]] = frozenset({"terminate", "terminateUntil"})


class TemporalPlanningError(ValueError):
    """A temporal write instruction cannot be planned (a shape this scope's own
    caller — the render seam — is responsible for never producing, e.g. a
    mutation this axis-count does not recognize; a defensive backstop, not a
    normal-path outcome for a well-formed instruction)."""


@dataclass(frozen=True, slots=True)
class MilestoneClose:
    """One inactivating/closing ``UPDATE`` the write plans (`m-txtime-write` /
    `m-bitemp-write`): close the current milestone the ADDRESS selects by setting
    its Transaction-Time upper bound to the transaction instant.

    The address is ``identity`` (the instruction's own row — at minimum the
    primary key; the render seam's existing key-predicate derivation resolves
    it, tag guard included) plus one exclusive upper bound per As-Of Axis.
    Transaction Time is invariantly infinity, so only the Valid-Time bound
    varies and only it is carried: ``target_valid_end`` is the observed
    rectangle's own Valid-Time end for a Bitemporal close, and ``None`` for a
    Transaction-Time-Only close, which has no second axis. The address is
    identical in both concurrency modes (ADR 0046).

    ``gate_tx_start`` is a gate CANDIDATE, not a gating decision: the observed
    Transaction-Time start (``None`` when this write carries no observation — an
    ungated audit-only locking-mode close needs none, `python.md` §5
    "locking-mode audit closes need no observation for SQL"). The render seam
    decides WHETHER to actually bind it (`~parallax.core.opt_lock.gates`) and
    always expects the close to affect exactly one row.
    """

    identity: Mapping[str, object]
    target_valid_end: str | None
    gate_tx_start: str | None


@dataclass(frozen=True, slots=True)
class MilestoneOpen:
    """One opened/chained ``INSERT`` the write plans: ``row`` is the FULL neutral
    row (Attribute-keyed, including every axis bound this mutation
    opens) the render seam lowers exactly like any other keyed insert — value
    objects, inheritance tag derivation, and pk-gen markers all compose
    unchanged, since this is structurally an ordinary full-row insert."""

    row: Mapping[str, object]


MilestoneStep = MilestoneClose | MilestoneOpen


@dataclass(frozen=True, slots=True)
class MilestonePlan:
    """The neutral, execution-ordered milestone plan one temporal keyed write
    lowers to: an ordered sequence of :class:`MilestoneClose` / :class:`MilestoneOpen`
    steps, close-before-chain, the pair adjacent (`m-txtime-write.md` L96-109) —
    the render seam maps each step to exactly one DML statement, in order."""

    steps: tuple[MilestoneStep, ...]


def axis_attr_names(
    model: Metamodel, entity: EntityMetadata, dimension: TemporalDimension
) -> tuple[str, str]:
    """``entity``'s effective Attribute names for a temporal dimension.

    A temporal entity's interval columns are ordinary declared attributes, and
    the milestone plan's rows are Attribute-keyed like any other neutral write
    row, so this is how a mutation's open/close steps name the axis bounds they
    set. The axes are family-wide and root-owned, so they are read through the
    Temporal Facet: a concrete subtype answers with its family's axes without
    the caller resolving a declaring position first.
    """
    axis = temporal_read.view(model).axis(entity.identity, dimension)
    if axis is None:
        raise TemporalPlanningError(
            f"{entity.identity.name} declares no {dimension.name} temporal dimension"
        )
    return axis.start_attribute.name, axis.end_attribute.name


def observed_bound(
    model: Metamodel,
    entity: EntityMetadata,
    observed: TemporalObservation,
    dimension: TemporalDimension,
    *,
    upper: bool = False,
) -> str:
    """One axis bound of the observed predecessor milestone.

    The predecessor retains the whole row it was read as, so an axis bound is
    read off it by the same Attribute name the milestone rows this scope opens
    write it under — never re-derived from a separate field per axis. The value
    rides through exactly as the port returned it, which for a real read may be a
    driver-native instant rather than a wire string.
    """
    names = axis_attr_names(model, entity, dimension)
    return cast("str", observed.predecessor.member(names[1] if upper else names[0]))


def observed_tx_start(
    model: Metamodel, entity: EntityMetadata, observed: TemporalObservation | None
) -> str | None:
    """The observed Transaction-Time start a close may gate on, or ``None`` when
    this write carries no observation to gate from."""
    if observed is None:
        return None
    return observed_bound(model, entity, observed, TemporalDimension.TRANSACTION_TIME)


def _open_row(
    model: Metamodel, entity: EntityMetadata, tx_instant: str, payload: Mapping[str, object]
) -> dict[str, object]:
    """The fresh current-milestone row ``payload`` opens at ``tx_instant`` on the
    sole Transaction-Time dimension."""
    in_name, out_name = axis_attr_names(model, entity, TemporalDimension.TRANSACTION_TIME)
    return {**payload, in_name: tx_instant, out_name: INFINITY_LITERAL}


def _merged_row(
    observed: TemporalObservation | None, row: Mapping[str, object]
) -> Mapping[str, object]:
    """The chained current row an audit-only ``update`` opens: the
    instruction's own (possibly SPARSE) row overlaid onto the observed
    predecessor — the audit-only analogue of
    :func:`~parallax.core.bitemp_write._merged_payload`. The instruction's row
    rides through unchanged when this write carries no observation, which leaves
    nothing to merge onto."""
    if observed is None:
        return row
    return {**observed.predecessor.members, **row}


def plan(
    instruction: KeyedWrite,
    model: Metamodel,
    entity: EntityMetadata,
    tx_instant: str,
    observed: TemporalObservation | None,
) -> MilestonePlan:
    """Plan one Transaction-Time-Only keyed temporal write.

    Pure: renders no SQL, takes no dialect. ``entity`` is the write's own target
    position; its family's axes are resolved through the Temporal Facet.
    ``observed`` is the caller-supplied observation of the CURRENT milestone this
    write's close (if any) targets — never derived here, never an implicit read
    (`m-txtime-write` "The engine supplies observed rows from case state").
    """
    mutation = instruction.mutation
    row = instruction.rows[0]
    if mutation in _INSERT_MUTATIONS:
        return MilestonePlan(steps=(MilestoneOpen(row=_open_row(model, entity, tx_instant, row)),))
    close = MilestoneClose(
        identity=row,
        target_valid_end=None,
        gate_tx_start=observed_tx_start(model, entity, observed),
    )
    if mutation in _TERMINATE_MUTATIONS:
        return MilestonePlan(steps=(close,))
    # update: chain the MERGED row — the instruction's own row overlaid
    # onto the observed payload, mirroring the bitemporal rectangle split.
    new_row = _merged_row(observed, row)
    return MilestonePlan(
        steps=(close, MilestoneOpen(row=_open_row(model, entity, tx_instant, new_row)))
    )
