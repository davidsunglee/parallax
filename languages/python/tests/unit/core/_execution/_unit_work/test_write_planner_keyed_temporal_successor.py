"""A keyed temporal amendment's successor, settled through the production
planner (`m-temporal-write` *Temporal expansion*): it overlays every member its
row assigns, and a restated occurrence is assigned whole."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core._execution._write_lowering import lowered
from parallax.core.base import INFINITY
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import PreparedEffectiveChange
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    AdmittedWrite,
    Concurrency,
    KeyedWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
    admitted_write,
)
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import (
    ObjectKey,
    PlannedInsert,
    PredecessorRow,
    StateObservation,
    TemporalObservation,
    WritePlan,
)
from parallax.core.write_plan.steps import (
    ChangedFrom,
    PlannedRow,
    PlannedStep,
)
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    observed_buffer,
    plan_steps,
    retained_observation,
)
from tests.unit import _milestone_rows_support as milestone_rows
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._positional_row_support import positional_row

_BALANCE = corpus_model("balance")

# The planner threads its Transaction Instant through untouched to whichever
# stage first needs it, so every test below shares one uncaptured holder rather
# than pinning an instant it would never read.
_INSTANT = inert_instant()
_ASSIGNED_TITLE = "title-changed"
_INTERIOR_FROM = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
_INTERIOR_UNTIL = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)

type _TestAdmittedWrite = AdmittedWrite | KeyedWriteInstruction


def _plan(
    buffer: Sequence[_TestAdmittedWrite],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, StateObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=tx_instant if tx_instant is not None else _INSTANT,
            concurrency=concurrency,
            composed_writes=observed_buffer(buffer, model, observations),
        )
    )


def _row_values(row: PlannedRow) -> dict[str, object]:
    values: dict[str, object] = {ident.name: value for ident, value in row.attributes.items()}
    for ident, value in row.value_objects.items():
        values[ident.path[-1]] = value
    return values


def _insert_rows(step: PlannedStep) -> list[dict[str, object]]:
    assert isinstance(step, PlannedInsert)
    return [_row_values(entry.row) for entry in step.entries]


def _prepared_keyed(write: KeyedWriteInstruction, model: Metamodel) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(write, model)
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


_BALANCE_PREDECESSOR: dict[str, object] = {
    "id": 1,
    "acctNum": "A",
    "value": Decimal("1.00"),
    "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "txEnd": INFINITY,
}


# --------------------------------------------------------------------------- #
# A surviving row executes every assignment, a member it restores included:   #
# settlement compares no assigned member against the row it reaches.          #
# --------------------------------------------------------------------------- #
def _refuse_member_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("settlement compared an assigned member with its row")

    monkeypatch.setattr(PreparedEffectiveChange, "effective_positions", refuse)


def test_a_literal_keyed_write_overlays_every_member_it_assigns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _refuse_member_comparison(monkeypatch)
    prepared = _prepared_keyed(
        KeyedWriteInstruction(
            "amend", "Balance", ({"id": 1, "acctNum": "B", "value": Decimal("9.00")},)
        ),
        _BALANCE,
    )
    observation = TemporalObservation(predecessor=PredecessorRow(members=_BALANCE_PREDECESSOR))
    literal = admitted_write(prepared, retained_observation(prepared, _BALANCE, observation))
    (_close, successor) = plan_steps(_plan([literal], _BALANCE))
    # The successor overlays every member the row assigns, whatever it equals.
    assert _insert_rows(successor)[0]["acctNum"] == "B"
    assert _insert_rows(successor)[0]["value"] == Decimal("9.00")


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
    plan = _plan([admitted_write(prepared, observed)], model)

    (changed,) = (
        step
        for step in plan_steps(plan)
        if isinstance(step, PlannedInsert) and isinstance(step.entries[0].origin, ChangedFrom)
    )
    documents = [
        cast("Mapping[str, Any]", bind.value)
        for bind in lowered(changed, LayoutPayloadPreparer(model), model, POSTGRES).binds
        if isinstance(bind, JsonDocument)
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
