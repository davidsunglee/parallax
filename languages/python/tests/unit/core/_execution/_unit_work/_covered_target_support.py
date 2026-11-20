"""Target writes of the shared-coverage objects, each stating the start of the
one stored rectangle that covers its window."""

from __future__ import annotations

from dataclasses import replace

from parallax.core import Bitemporal
from parallax.core._execution._unit_work.instructions import (
    PreparedTargetInstruction,
)
from parallax.core._execution._unit_work.preparation import WIRE
from parallax.core._execution._unit_work.row_acquisition import RetainedStartingRow
from parallax.core._execution._unit_work.write_items import (
    LicensedWrite,
    TxStartConditioned,
    is_licensed_by,
    target_write,
)
from parallax.core.internal.entity._construction_input import ABSENT
from parallax.core.internal.inheritance import inheritance_facet_of
from parallax.core.internal.planned_step import PredecessorRow
from parallax.core.internal.planned_step.keys import TemporalObjectStateKey
from parallax.core.internal.unit_work import TargetWriteInstruction
from tests._support.write_preparation import prepare_instruction, write_preparation_of
from tests.unit._positional_row_support import positional_row
from tests.unit.core._shared_coverage_support import MODEL, T0, day, observation, rectangle


def covered_target_instruction(entity: type[Bitemporal], key: int) -> PreparedTargetInstruction:
    """A target write of object ``key`` over ``[d_0, d_1)`` stating the
    Transaction-Time start ``T0`` of the stored rectangle ``[d_0, ∞)``."""
    prepared = prepare_instruction(
        TargetWriteInstruction(
            "amendUntil",
            entity.identity.canonical,
            {"id": key, "amount": 7},
            if_tx_start=T0,
            valid_from=day(0),
            until=day(1),
        ),
        write_preparation_of(MODEL),
        WIRE,
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    return prepared


def covered_target(
    entity: type[Bitemporal], key: int
) -> tuple[LicensedWrite[TxStartConditioned], PredecessorRow]:
    """A Locking target write of object ``key`` over ``[d_0, d_1)`` beside the
    one stored rectangle ``[d_0, ∞)`` its acquisition retained, which covers
    its whole window (:func:`covered_target_instruction`)."""
    stored = rectangle(entity, key, 0, None, 0)
    prepared = covered_target_instruction(entity, key)
    view = inheritance_facet_of(MODEL).entity(entity.identity)
    assert view is not None
    state = observation(entity, stored).key
    assert isinstance(state, TemporalObjectStateKey)
    starting_row = RetainedStartingRow(
        state,
        0,
        positional_row(view.member_selection.shape, stored.members, absent=ABSENT),
        stored.document,
    )
    item = target_write(prepared, inheritance_facet_of(MODEL))
    assert is_licensed_by(item, TxStartConditioned)
    return replace(item, authority=replace(item.authority, starting_row=starting_row)), stored
