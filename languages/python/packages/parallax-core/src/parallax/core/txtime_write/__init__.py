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
  observed payload (D-30, COR-3 Phase 8 increment 7 completion round; mirrors
  the bitemporal rectangle split's own observed-payload carry-forward,
  `m-bitemp-write` "Head/tail old values come from the observed prior
  rectangle") — a public ``tx.update(copy)`` authors a SPARSE row (primary key
  plus effective change set only, `python.md` §3/§5), so an unauthored field
  carries FORWARD from the observed current milestone unchanged, exactly like
  its bitemporal sibling; a caller-authored FULL row (every conformance-engine
  writeSequence witness) merges to itself (an identity, since every member the
  merge could overlay is already present in the caller's own row). Close-
  before-chain, the pair adjacent (`m-txtime-write.md` L96-109).

The close's gate CANDIDATES (:attr:`MilestoneClose.gate_tx_start`) come straight from
the caller-supplied ``observed`` :class:`~parallax.core.unit_work.Observation` —
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
from typing import Final

from parallax.core.base import INFINITY_LITERAL
from parallax.core.descriptor import AsOfAxisMetadata, Entity, TemporalDimension
from parallax.core.unit_work import KeyedWrite, Observation

__all__ = [
    "MilestoneClose",
    "MilestoneOpen",
    "MilestonePlan",
    "MilestoneStep",
    "TemporalPlanningError",
    "axis_attr_names",
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
    `m-bitemp-write`): close the CURRENT (``out_z = infinity``) row identified by
    ``identity`` (the instruction's own row — at minimum the primary key; the
    render seam's existing key-predicate derivation resolves it, tag guard
    included) by setting its Transaction-Time upper bound to the transaction
    instant.

    ``gate_tx_start`` / ``gate_valid_start`` are gate CANDIDATES, not a gating decision:
    ``gate_tx_start`` is the observed Transaction-Time start (``None`` when this write
    carries no observation — an ungated audit-only locking-mode close needs
    none, `python.md` §5 "locking-mode audit closes need no observation for
    SQL"); ``gate_valid_start`` is the bitemporal Valid-Time discriminator (always
    ``None`` for a Transaction-Time-Only close — it has no Valid-Time
    coordinate to discriminate on). The render seam decides WHETHER to actually
    bind them (`~parallax.core.opt_lock.gates`) and always expects the close to
    affect exactly one row.
    """

    identity: Mapping[str, object]
    gate_tx_start: str | None
    gate_valid_start: str | None = None


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


def axis_attr_names(entity: Entity, dimension: TemporalDimension) -> tuple[str, str]:
    """``entity``'s declared Attribute names for a temporal dimension.

    A temporal entity's interval columns are ordinary declared attributes
    (`m-descriptor`; mirrors `~parallax.core.temporal_read.attr_ref_for_column`'s
    own lookup): the milestone plan's rows are Attribute-keyed (like any other
    neutral write row), so this is how
    a mutation's open/close steps name the axis bounds they set. ``entity`` MUST
    be the FAMILY-EFFECTIVE declaring entity (the root, for an inheritance
    participant) — its axes and their governing attributes are ALWAYS declared
    there (`m-inheritance` "Inherited members"), never on a descendant.
    """
    axis = _axis(entity, dimension)
    return axis.start_attribute, axis.end_attribute


def _axis(entity: Entity, dimension: TemporalDimension) -> AsOfAxisMetadata:
    for axis in entity.as_of_axes:
        if axis.dimension == dimension:
            return axis
    raise TemporalPlanningError(f"{entity.name} declares no {dimension!r} temporal dimension")


def _open_row(entity: Entity, tx_instant: str, payload: Mapping[str, object]) -> dict[str, object]:
    """The fresh current-milestone row ``payload`` opens at ``tx_instant`` on the
    sole Transaction-Time dimension."""
    in_name, out_name = axis_attr_names(entity, "transactionTime")
    return {**payload, in_name: tx_instant, out_name: INFINITY_LITERAL}


def _merged_row(observed: Observation | None, row: Mapping[str, object]) -> Mapping[str, object]:
    """The chained current row an audit-only ``update`` opens (D-30): the
    instruction's own (possibly SPARSE) row overlaid onto the observed
    payload — the audit-only analogue of
    :func:`~parallax.core.bitemp_write._merged_payload`. ``None`` when this
    write carries no observation (nothing to merge onto — the instruction's
    row rides through unchanged, exactly as it did before this fix)."""
    if observed is None or observed.payload is None:
        return row
    return {**observed.payload, **row}


def plan(
    instruction: KeyedWrite, entity: Entity, tx_instant: str, observed: Observation | None
) -> MilestonePlan:
    """Plan one Transaction-Time-Only keyed temporal write.

    Pure: renders no SQL, takes no dialect. ``entity`` is the family-effective
    declaring entity (the root, for an inheritance participant — `m-inheritance`).
    ``observed`` is the caller-supplied observation of the CURRENT milestone this
    write's close (if any) targets — never derived here, never an implicit read
    (`m-txtime-write` "The engine supplies observed rows from case state").
    """
    mutation = instruction.mutation
    row = instruction.rows[0]
    if mutation in _INSERT_MUTATIONS:
        return MilestonePlan(steps=(MilestoneOpen(row=_open_row(entity, tx_instant, row)),))
    close = MilestoneClose(
        identity=row,
        gate_tx_start=observed.tx_start if observed is not None else None,
    )
    if mutation in _TERMINATE_MUTATIONS:
        return MilestonePlan(steps=(close,))
    # update: chain the MERGED row (D-30) — the instruction's own row overlaid
    # onto the observed payload, mirroring the bitemporal rectangle split.
    new_row = _merged_row(observed, row)
    return MilestonePlan(steps=(close, MilestoneOpen(row=_open_row(entity, tx_instant, new_row))))
