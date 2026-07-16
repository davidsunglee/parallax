"""``parallax.core.bitemp_write`` enforcement scope (m-bitemp-write).

The full-bitemporal (business + processing) RECTANGLE-SPLIT planning scope: it
reuses :mod:`parallax.core.audit_write`'s close-and-chain machinery (the
``MilestoneClose`` / ``MilestoneOpen`` shapes and the processing-axis attribute
lookup), extended to the second (business) axis. Like its sibling, this module
never renders SQL and never imports ``opt_lock`` / ``dialect`` / ``sql_gen`` — the
render seam (``parallax.snapshot.handle``) composes its neutral
:class:`~parallax.core.audit_write.MilestonePlan` with the ``opt_lock`` gate policy
and the descriptor-driven column/tag machinery.

Six mutations (`m-bitemp-write.md`), all expressed as an ``inactivate`` (a close,
reusing :class:`~parallax.core.audit_write.MilestoneClose`) plus zero-to-three
opened rectangles (each an :class:`~parallax.core.audit_write.MilestoneOpen`):

- **insert** / **insertUntil** — a single open rectangle, no close: the business
  window is ``[businessFrom, infinity)`` (plain) or the bounded
  ``[businessFrom, businessTo)`` (``*Until``).
- **updateUntil** — close + **head** ``[obsFrom, businessFrom)`` (OLD payload) +
  **middle** ``[businessFrom, businessTo)`` (the caller's new values, MERGED onto
  the observed payload) + **tail** ``[businessTo, obsTo)`` (OLD payload).
- **terminateUntil** — close + head + tail, **no middle** — the window is left
  covered by no current-on-processing row.
- **update** (plain) — the two-way degenerate of ``updateUntil``: close + head
  ``[obsFrom, B)`` (OLD) + a NEW tail ``[B, obsTo)`` (the merged new payload) — no
  old tail, since the correction runs unbounded from ``B``.
- **terminate** (plain) — close + head ``[obsFrom, B)`` (OLD) only — no tail, no
  middle: the value is absent from ``B`` onward.

Every opened rectangle's business bounds and old/new payload composition come from
the caller-supplied ``observed`` :class:`~parallax.core.unit_work.Observation` (the
CURRENT rectangle this write's close targets) and the instruction's own authored
fields — this scope issues no implicit read and performs no observation lookup of
its own (`m-bitemp-write` "The engine supplies observed rows from case state").
The MERGE that produces a chained row's NEW payload (``middle`` / the new ``tail``)
overlays the instruction's own row onto the observed payload — the bitemporal
analogue of a non-temporal edited copy's effective change set, since the corpus's
own bitemporal update rows are SPARSE (pk + the touched fields only, `python.md`
§5): an unauthored field carries FORWARD from the prior rectangle unchanged.

The close's gate candidates additionally carry the bitemporal business
discriminator (:attr:`~parallax.core.audit_write.MilestoneClose.gate_from_z`) —
the observed rectangle's OWN business-from — composing with the observed ``in_z``
exactly as `m-bitemp-write.md` "The inactivation UPDATE" pins: gated ONLY under
optimistic concurrency (the render seam's decision), never data-dependent on
whether disambiguation was structurally needed.

Prior art (Reladomo; semantics, not idioms): the rectangle dispatch mirrors
``GenericBiTemporalDirector.updateUntil`` / ``.splitTailEnd`` (research §6, the
bitemporal rectangle split); the plain (unbounded) trio is the open-window,
tailless degenerate of the same director's unbounded ``insert`` / ``update`` /
``terminate``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from parallax.core.audit_write import MilestoneClose, MilestoneOpen, MilestonePlan, axis_attr_names
from parallax.core.base import INFINITY_LITERAL
from parallax.core.descriptor import Entity
from parallax.core.unit_work import KeyedWrite, Observation

__all__ = ["MilestoneClose", "MilestoneOpen", "MilestonePlan", "plan"]

_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
_UPDATE_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})
_BOUNDED_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"insertUntil", "updateUntil", "terminateUntil"}
)


def _open(
    entity: Entity,
    tx_instant: str,
    business_from: str,
    business_to: str,
    payload: Mapping[str, object],
) -> MilestoneOpen:
    proc_from, proc_to = axis_attr_names(entity, "processing")
    biz_from, biz_to = axis_attr_names(entity, "business")
    row = {
        **payload,
        biz_from: business_from,
        biz_to: business_to,
        proc_from: tx_instant,
        proc_to: INFINITY_LITERAL,
    }
    return MilestoneOpen(row=row)


def _merged_payload(observed: Observation, row: Mapping[str, object]) -> dict[str, object]:
    """The chained rectangle's NEW payload: the observed row's own values, with the
    instruction's own (sparse, pk-plus-touched-fields) row overlaid on top."""
    return {**(observed.payload or {}), **row}


def plan(
    instruction: KeyedWrite, entity: Entity, tx_instant: str, observed: Observation | None
) -> MilestonePlan:
    """Plan one full-bitemporal keyed write: the rectangle split or one of its
    unbounded/insert degenerates.

    Pure: renders no SQL, takes no dialect. ``entity`` is the family-effective
    declaring entity (the root, for an inheritance participant). ``observed`` is
    REQUIRED for every close-bearing mutation (update / updateUntil / terminate /
    terminateUntil) — the head/tail rectangles' old business bounds and payload
    come from it, unconditionally of concurrency mode (`m-bitemp-write` "Head/tail
    old values come from the observed prior rectangle").
    """
    mutation = instruction.mutation
    row = instruction.rows[0]
    business_from = instruction.business_from
    assert business_from is not None  # every bitemporal mutation carries one (schema-required)

    if mutation in _INSERT_MUTATIONS:
        business_to = (
            instruction.business_to if instruction.business_to is not None else INFINITY_LITERAL
        )
        return MilestonePlan(steps=(_open(entity, tx_instant, business_from, business_to, row),))

    assert observed is not None  # every close-bearing mutation needs the observed rectangle
    obs_from = observed.business_from
    obs_to = observed.business_to
    assert obs_from is not None and obs_to is not None
    old_payload = observed.payload or {}
    close = MilestoneClose(identity=row, gate_in_z=observed.in_z, gate_from_z=obs_from)

    if mutation == "terminate":
        head = _open(entity, tx_instant, obs_from, business_from, old_payload)
        return MilestonePlan(steps=(close, head))
    if mutation == "terminateUntil":
        business_to = instruction.business_to
        assert business_to is not None
        head = _open(entity, tx_instant, obs_from, business_from, old_payload)
        tail = _open(entity, tx_instant, business_to, obs_to, old_payload)
        return MilestonePlan(steps=(close, head, tail))
    if mutation in _UPDATE_MUTATIONS:
        new_payload = _merged_payload(observed, row)
        head = _open(entity, tx_instant, obs_from, business_from, old_payload)
        if mutation in _BOUNDED_MUTATIONS:
            business_to = instruction.business_to
            assert business_to is not None
            middle = _open(entity, tx_instant, business_from, business_to, new_payload)
            tail = _open(entity, tx_instant, business_to, obs_to, old_payload)
            return MilestonePlan(steps=(close, head, middle, tail))
        new_tail = _open(entity, tx_instant, business_from, obs_to, new_payload)
        return MilestonePlan(steps=(close, head, new_tail))
    raise ValueError(  # pragma: no cover - defends an unrecognized mutation
        f"bitemp_write.plan: unrecognized temporal mutation {mutation!r}"
    )
