"""A keyed temporal amendment's successor, settled through the production
planner (`m-temporal-write` *Temporal expansion*): a restated occurrence is
assigned whole."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pytest

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core._execution._write_lowering import lowered
from parallax.core.internal.base import INFINITY
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.db_port import StructuredDocument
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity._construction_input import ABSENT
from parallax.core.internal.entity._layout import LayoutCatalog
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.unit_work import (
    AdmittedWrite,
    KeyedWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
    admitted_write,
)
from parallax.core.internal.write_payload import LayoutPayloadPreparer
from parallax.core.internal.write_plan import (
    ObjectKey,
    PlannedInsert,
    PredecessorRow,
    StateObservation,
    TemporalObservation,
    WritePlan,
)
from parallax.core.internal.write_plan.steps import (
    ChangedFrom,
)
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    observed_buffer,
    plan_steps,
    retained_observation,
)
from tests._support.write_preparation import write_preparation_of
from tests.unit import _milestone_rows_support as milestone_rows
from tests.unit._positional_row_support import positional_row

# The planner threads its Transaction Instant through untouched to whichever
# stage first needs it, so every test below shares one uncaptured holder, later
# than every stored Transaction-Time start a test closes.
_INSTANT = instant_at("2027-01-01T00:00:00+00:00")
_ASSIGNED_TITLE = "title-changed"
_INTERIOR_FROM = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
_INTERIOR_UNTIL = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)

type _TestAdmittedWrite = AdmittedWrite | KeyedWriteInstruction


def _plan(
    buffer: Sequence[_TestAdmittedWrite],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, StateObservation] | None = None,
    concurrency: ConcurrencyPreference = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return build_write_planner(bound_model(model)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=tx_instant if tx_instant is not None else _INSTANT,
            preference=concurrency,
            composed_writes=observed_buffer(buffer, model, observations),
        )
    )


def _prepared_keyed(write: KeyedWriteInstruction, model: Metamodel) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(write, write_preparation_of(model))
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


@pytest.mark.parametrize("positional", [False, True], ids=["mapping", "positional"])
def test_a_restated_occurrence_is_assigned_whole_and_keeps_no_key_its_value_omits(
    positional: bool,
) -> None:
    # An update's row is its literal assignment set: `address`, restated as an
    # equal but distinct value, is assigned whole like any other occurrence, so
    # the changed successor writes the stated subtree — not the stored one, and
    # not the stored key no member declares — beside the patched `title`, while
    # every member the row does not name is carried.
    model = model_of(milestone_rows.MODEL)
    target = model.entity(milestone_rows.MilestoneDocument.identity)
    assert target is not None
    selection = LayoutCatalog(model).entity(target.identity).member_selection
    members: dict[str, object] = {
        "id": 1,
        "title": "title-1",
        "address": {"city": "Oslo", "geo": {"country": "NO"}},
        "tags": [{"label": "a"}],
        "validStart": milestone_rows.VALID_START,
        "validEnd": INFINITY,
        "txStart": milestone_rows.TX_START,
        "txEnd": INFINITY,
    }
    stored: dict[str, object] = {
        "title": "title-1",
        "address": {"city": "Oslo", "geo": {"country": "NO"}, "legacyDiscount": 5},
        "tags": [{"label": "a"}],
    }
    predecessor = (
        PredecessorRow.over_row(
            selection, positional_row(selection.shape, members, absent=ABSENT), stored, ABSENT
        )
        if positional
        else PredecessorRow(members, document=stored)
    )
    prepared = _prepared_keyed(
        KeyedWriteInstruction(
            "amendUntil",
            target.identity.canonical,
            (
                {
                    "id": 1,
                    "title": _ASSIGNED_TITLE,
                    "address": {"city": "Oslo", "geo": {"country": "NO"}},
                },
            ),
            _INTERIOR_FROM,
            _INTERIOR_UNTIL,
        ),
        model,
    )
    observed = retained_observation(prepared, model, TemporalObservation(predecessor))
    plan = _plan([admitted_write(prepared, observed, observed.key.object)], model)

    (changed,) = (
        step
        for step in plan_steps(plan)
        if isinstance(step, PlannedInsert) and isinstance(step.entries[0].origin, ChangedFrom)
    )
    documents = [
        cast("Mapping[str, Any]", bind.document)
        for bind in lowered(
            changed,
            LayoutPayloadPreparer(bound_model(model)),
            bound_model(model),
            POSTGRES,
        ).binds
        if isinstance(bind, StructuredDocument)
    ]
    assert documents == [
        {
            **stored,
            "title": _ASSIGNED_TITLE,
            "address": {"city": "Oslo", "geo": {"country": "NO"}},
        }
    ]
    (entry,) = changed.entries
    (address,) = (
        identity for identity in entry.row.value_objects if identity.path[-1] == "address"
    )
    assert address in entry.executed
