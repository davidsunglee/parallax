"""Case-local temporal shadow state (engine translation layer only).

The conformance engine's write lanes (writeSequence / scenario / conflict) drive
production ``db.transact`` per choreography unit (COR-3 Phase 8 increment 4, DQ4
re-route); a later unit's temporal write needs "the observed current milestone" its
close/chain consumes, but the framework itself never issues an implicit resolving
read for one (`core/spec/m-audit-write.md` / `m-bitemp-write.md`: "the engine
supplies observed rows from case state"). This module is the engine-side tracker
that makes that observation available WITHOUT a database round trip — fixtures (for
a case that loads them) seed it, and each temporal write's own neutral milestone
plan (:mod:`parallax.core.audit_write` / :mod:`parallax.core.bitemp_write`, the SAME
pure planning functions the production render seam calls) advances it, so COMPILE
and RUN consume the identical in-memory state.

Non-normative engine-internal bookkeeping: never serialized, never a
:class:`~parallax.core.unit_work.WriteInstruction` field, never consulted by
production code (:mod:`parallax.snapshot.handle`) — the conformance family's own
translation-layer state, mirroring how a real caller would have read the current
milestone via an earlier transaction-scoped find.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.core import audit_write, bitemp_write
from parallax.core.descriptor import Metamodel
from parallax.core.inheritance import declaring_entity, family_primary_key
from parallax.core.unit_work import KeyedWrite, Observation

__all__ = ["AmbiguousObservationError", "TemporalShadow"]

_ObjectKey = tuple[str, tuple[object, ...]]


class AmbiguousObservationError(ValueError):
    """More than one current milestone is tracked for one (entity, pk) — the
    business-discriminator disambiguation `m-bitemp-write.md` describes for a
    key whose current rows share an ``in_z`` is not witnessed by any reachable
    writeSequence/scenario case this increment, so this tracker refuses rather
    than silently guessing which candidate a later step means."""


class TemporalShadow:
    """The case-local map of (entity, primary key) -> its tracked CURRENT
    (``out_z = infinity``) milestone, advanced as each temporal write plans."""

    __slots__ = ("_current",)

    def __init__(self) -> None:
        self._current: dict[_ObjectKey, list[Observation]] = {}

    def seed_fixtures(
        self, meta: Metamodel, entity_name: str, rows: Sequence[Mapping[str, object]]
    ) -> None:
        """Seed the tracker from a case's loaded fixture rows for ``entity_name``
        (`given.fixtures: true`, or a scenario/conflict case's own default
        lifecycle load). A non-temporal entity's rows are a no-op."""
        entity = meta.entity(entity_name)
        declaring = declaring_entity(meta, entity)
        if not declaring.as_of_axes:
            return
        tx_start, tx_end = audit_write.axis_attr_names(declaring, "transactionTime")
        is_bitemporal = declaring.temporal == "bitemporal"
        valid_start, valid_end = (
            audit_write.axis_attr_names(declaring, "validTime") if is_bitemporal else (None, None)
        )
        pk_names = [attr.name for attr in family_primary_key(meta, entity)]
        for row in rows:
            if row.get(tx_end) != "infinity":
                continue  # not current on Transaction Time
            key = self._key(entity_name, pk_names, row)
            observation = Observation(
                tx_start=_as_str(row[tx_start]),
                valid_start=_as_str(row[valid_start]) if valid_start is not None else None,
                valid_end=_as_str(row[valid_end]) if valid_end is not None else None,
                payload=_payload(row, {tx_start, tx_end, valid_start, valid_end}),
            )
            self._current.setdefault(key, []).append(observation)

    def resolve(
        self, meta: Metamodel, entity_name: str, row: Mapping[str, object]
    ) -> Observation | None:
        """The tracked observation a temporal update/terminate/updateUntil/
        terminateUntil instruction's close/chain consumes, or ``None`` for a
        pk this tracker has never seen open (an insert, or a genuinely
        unobserved close the write itself will surface as a conflict/stale
        error at execution).

        Raises :class:`AmbiguousObservationError` when more than one current
        candidate is tracked for this pk — disambiguation by a write's own
        Valid-Time-start discriminator is a conflict-shape-only mechanism this
        increment reaches via the case's explicit ``observedTxStart`` /
        ``write.validFrom`` fields, never this tracker (see the module
        docstring).
        """
        entity = meta.entity(entity_name)
        pk_names = [attr.name for attr in family_primary_key(meta, entity)]
        key = self._key(entity_name, pk_names, row)
        candidates = self._current.get(key)
        if not candidates:
            return None
        if len(candidates) > 1:
            raise AmbiguousObservationError(
                f"{entity_name}: {len(candidates)} current milestones are tracked for "
                f"{dict(zip(pk_names, key[1], strict=True))!r} — disambiguation is out of "
                "scope this increment (COR-3 Phase 8 increment 4)"
            )
        return candidates[0]

    def advance(
        self,
        meta: Metamodel,
        entity_name: str,
        instruction: KeyedWrite,
        tx_instant: str,
        observed: Observation | None,
    ) -> None:
        """Replace this pk's tracked current milestone(s) with the newly OPENED
        rows the SAME planning function (:mod:`parallax.core.audit_write` /
        :mod:`parallax.core.bitemp_write`) the render seam calls computes —
        never a separately re-derived arithmetic, so the tracker and the
        rendered SQL can never disagree (m-audit-write.md / m-bitemp-write.md
        "the engine supplies observed rows from case state")."""
        entity = meta.entity(entity_name)
        declaring = declaring_entity(meta, entity)
        pk_names = [attr.name for attr in family_primary_key(meta, entity)]
        key = self._key(entity_name, pk_names, instruction.rows[0])
        plan_fn = bitemp_write.plan if declaring.temporal == "bitemporal" else audit_write.plan
        milestone_plan = plan_fn(instruction, declaring, tx_instant, observed)
        opened = [
            step for step in milestone_plan.steps if isinstance(step, audit_write.MilestoneOpen)
        ]
        if not opened:
            self._current.pop(key, None)  # a terminate/terminateUntil closes with no chain
            return
        is_bitemporal = declaring.temporal == "bitemporal"
        valid_start, valid_end = (
            audit_write.axis_attr_names(declaring, "validTime") if is_bitemporal else (None, None)
        )
        tx_start, tx_end = audit_write.axis_attr_names(declaring, "transactionTime")
        self._current[key] = [
            Observation(
                tx_start=_as_str(step.row[tx_start]),
                valid_start=(_as_str(step.row[valid_start]) if valid_start is not None else None),
                valid_end=_as_str(step.row[valid_end]) if valid_end is not None else None,
                payload=_payload(step.row, {tx_start, tx_end, valid_start, valid_end}),
            )
            for step in opened
        ]

    @staticmethod
    def _key(entity_name: str, pk_names: Sequence[str], row: Mapping[str, object]) -> _ObjectKey:
        return (entity_name, tuple(row[name] for name in pk_names))


def _as_str(value: object) -> str:
    if not isinstance(value, str):  # pragma: no cover - defends a malformed fixture/plan row
        raise TypeError(f"expected an instant string, got {type(value).__name__}")
    return value


def _payload(row: Mapping[str, object], excluded: set[str | None]) -> dict[str, object]:
    return {key: value for key, value in row.items() if key not in excluded}
