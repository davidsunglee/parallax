"""``parallax.core.audit_write`` enforcement scope (m-audit-write).

The audit-only (processing-axis) milestone-chaining PLANNING scope: this module
never renders SQL and never imports ``opt_lock`` / ``dialect`` / ``sql_gen`` — it
owns the MILESTONE ARITHMETIC only (which rows close, which chain, statement
shape) as **pure functions** over ``(instruction, observed row, tx instant)``.
``parallax.snapshot.handle`` is the one seam that renders SQL: it composes this
scope's neutral :class:`MilestonePlan` with the ``opt_lock`` gate/licensing policy
(`core/spec/m-opt-lock.md` "Temporal entities derive the version from the
processing axis") and the descriptor-driven column/tag machinery it already owns
for non-temporal writes.

Three mutations, one shape each (`m-audit-write.md` "Milestone-chaining writes"):

- **insert** — a single :class:`MilestoneOpen`: the instruction's own authored row
  plus the fresh processing bounds ``[txInstant, infinity)``.
- **terminate** — a single :class:`MilestoneClose`: close the current row
  (``out_z = txInstant``) and chain nothing — the terminated state is the
  ABSENCE of any ``out_z = infinity`` row.
- **update** — a :class:`MilestoneClose` immediately followed by a
  :class:`MilestoneOpen` carrying the instruction's own authored FULL row (never
  the observed payload — audit-only chains the CALLER's new values, contrast the
  bitemporal rectangle split's observed-payload carry-forward,
  `m-bitemp-write` "Head/tail old values come from the observed prior rectangle").
  Close-before-chain, the pair adjacent (`m-audit-write.md` L96-109).

The close's gate CANDIDATES (:attr:`MilestoneClose.gate_in_z`) come straight from
the caller-supplied ``observed`` :class:`~parallax.core.unit_work.Observation` —
this scope never decides WHETHER to gate (that is the ``opt_lock`` policy
composed at the render seam) or issues an implicit read to find one (`m-audit-write`
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
processing-from; ``terminate`` (audit-preserving: closes, chains nothing) is
Reladomo's dated ``terminate()``, deliberately NOT its MAY-tier physical ``purge``
(`m-bitemp-write` "MAY-tier mutations").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from parallax.core.base import INFINITY_LITERAL
from parallax.core.descriptor import AsOfAttribute, Axis, Entity
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
    """One inactivating/closing ``UPDATE`` the write plans (`m-audit-write` /
    `m-bitemp-write`): close the CURRENT (``out_z = infinity``) row identified by
    ``identity`` (the instruction's own row — at minimum the primary key; the
    render seam's existing key-predicate derivation resolves it, tag guard
    included) by setting its processing-axis upper bound to the transaction
    instant.

    ``gate_in_z`` / ``gate_from_z`` are gate CANDIDATES, not a gating decision:
    ``gate_in_z`` is the observed processing-from (``None`` when this write
    carries no observation — an ungated audit-only locking-mode close needs
    none, `python.md` §5 "locking-mode audit closes need no observation for
    SQL"); ``gate_from_z`` is the bitemporal business discriminator (always
    ``None`` for an audit-only close — a single-axis entity has no business
    coordinate to discriminate on). The render seam decides WHETHER to actually
    bind them (`~parallax.core.opt_lock.gates`) and always expects the close to
    affect exactly one row.
    """

    identity: Mapping[str, object]
    gate_in_z: str | None
    gate_from_z: str | None = None


@dataclass(frozen=True, slots=True)
class MilestoneOpen:
    """One opened/chained ``INSERT`` the write plans: ``row`` is the FULL neutral
    row (business-attribute-keyed, including every axis bound this mutation
    opens) the render seam lowers exactly like any other keyed insert — value
    objects, inheritance tag derivation, and pk-gen markers all compose
    unchanged, since this is structurally an ordinary full-row insert."""

    row: Mapping[str, object]


MilestoneStep = MilestoneClose | MilestoneOpen


@dataclass(frozen=True, slots=True)
class MilestonePlan:
    """The neutral, execution-ordered milestone plan one temporal keyed write
    lowers to: an ordered sequence of :class:`MilestoneClose` / :class:`MilestoneOpen`
    steps, close-before-chain, the pair adjacent (`m-audit-write.md` L96-109) —
    the render seam maps each step to exactly one DML statement, in order."""

    steps: tuple[MilestoneStep, ...]


def axis_attr_names(entity: Entity, axis: Axis) -> tuple[str, str]:
    """``entity``'s declared attribute NAMES for ``axis``'s ``(fromColumn, toColumn)``.

    A temporal entity's interval columns are ordinary declared attributes
    (`m-descriptor`; mirrors `~parallax.core.temporal_read.attr_ref_for_column`'s
    own column lookup, inverted to names): the milestone plan's own rows are
    business-attribute-keyed (like any other neutral write row), so this is how
    a mutation's open/close steps name the axis bounds they set. ``entity`` MUST
    be the FAMILY-EFFECTIVE declaring entity (the root, for an inheritance
    participant) — its axes and their governing attributes are ALWAYS declared
    there (`m-inheritance` "Inherited members"), never on a descendant.
    """
    aoa = _axis(entity, axis)
    return _attr_name_for_column(entity, aoa.from_column), _attr_name_for_column(
        entity, aoa.to_column
    )


def _axis(entity: Entity, axis: Axis) -> AsOfAttribute:
    for aoa in entity.as_of_attributes:
        if aoa.axis == axis:
            return aoa
    raise TemporalPlanningError(f"{entity.name} declares no {axis!r} as-of axis")


def _attr_name_for_column(entity: Entity, column: str) -> str:
    for attr in entity.attributes:
        if attr.column == column:
            return attr.name
    raise TemporalPlanningError(  # pragma: no cover - guards a malformed descriptor
        f"{entity.name}: interval column {column!r} is not a declared attribute"
    )


def _open_row(entity: Entity, tx_instant: str, payload: Mapping[str, object]) -> dict[str, object]:
    """The fresh current-milestone row ``payload`` opens at ``tx_instant`` on the
    (sole) processing axis — audit-only has no business axis to bound."""
    in_name, out_name = axis_attr_names(entity, "processing")
    return {**payload, in_name: tx_instant, out_name: INFINITY_LITERAL}


def plan(
    instruction: KeyedWrite, entity: Entity, tx_instant: str, observed: Observation | None
) -> MilestonePlan:
    """Plan one audit-only (single-axis, processing) keyed temporal write.

    Pure: renders no SQL, takes no dialect. ``entity`` is the family-effective
    declaring entity (the root, for an inheritance participant — `m-inheritance`).
    ``observed`` is the caller-supplied observation of the CURRENT milestone this
    write's close (if any) targets — never derived here, never an implicit read
    (`m-audit-write` "The engine supplies observed rows from case state").
    """
    mutation = instruction.mutation
    row = instruction.rows[0]
    if mutation in _INSERT_MUTATIONS:
        return MilestonePlan(steps=(MilestoneOpen(row=_open_row(entity, tx_instant, row)),))
    close = MilestoneClose(
        identity=row,
        gate_in_z=observed.in_z if observed is not None else None,
    )
    if mutation in _TERMINATE_MUTATIONS:
        return MilestonePlan(steps=(close,))
    # update: chain the instruction's OWN authored full row (never the observed
    # payload — the audit-only contrast to the bitemporal rectangle split).
    return MilestonePlan(steps=(close, MilestoneOpen(row=_open_row(entity, tx_instant, row))))
