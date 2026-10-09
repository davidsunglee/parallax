"""Write admission and Observed-State Coalescing (`m-unit-work`).

One claim algebra backs two seams — the synchronous refusal a keyed verb raises
and the merge finalization performs — so this module measures the algebra itself
as a pure function; the choreography a caller performs through the real handles
over a fake port is ``test_transaction_write_claims.py``'s subject.

The evidence a source carries and how long it lives is `test_source_evidence.py`'s
subject; what lives here is what a SECOND intent against the same evidence may do.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, cast

import pytest

from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.core import opt_lock
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.opt_lock._facet import UNVERSIONED
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    SELECTION_INTENT,
    KeyedWrite,
    RetainedObservation,
    WriteIntent,
    instructions,
    keyed_intent,
)
from parallax.core.unit_work.claims import (
    SPANNING_SELECTION_INTENT,
    ClaimTable,
    admits,
    admits_composed,
)
from parallax.core.unit_work.instructions import PreparedKeyedWrite
from parallax.core.unit_work.materialized import ObjectClaimedWrite
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.core.write_plan.keys import VersionedStateKey
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
)

PERSON = CLASS_MODELS["person"]

_VALID_FROM = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_OTHER_FROM = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
_UNTIL = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

_ASSIGNMENT = WriteIntent(kind="assignment")
_DESTRUCTIVE = WriteIntent(kind="destructive")
_OBJECT = ObjectKey(EntityIdentity("parallax.compatibility", "Account"), (("id", 1),))
_STATE = VersionedStateKey(ObjectKey(EntityIdentity("parallax.compatibility", "Account"), ()), 4)
_VERSION_ATTRIBUTE = AttributeIdentity(
    EntityIdentity("parallax.compatibility", "Account"), "version"
)
_START_ATTRIBUTE = AttributeIdentity(EntityIdentity("parallax.compatibility", "Balance"), "inZ")
_RETAINED = RetainedObservation(
    VersionedStateKey(_OBJECT, 4), VersionObservation(observed_version=4), None
)

_PERSON_META = model_of(PERSON)
_WHERE_POSITION_META = model_of(WHERE_POSITION_META)


def _person_delete(*ids: int) -> KeyedWrite:
    instruction = instructions.deserialize(
        {
            "mutation": "delete",
            "entity": "parallax.compatibility.Person",
            "rows": [{"id": value} for value in ids],
        }
    )
    assert isinstance(instruction, KeyedWrite)
    return instruction


def _prepared_person_delete(*ids: int) -> PreparedKeyedWrite:
    prepared = instructions.prepare_wire_write(_person_delete(*ids), _PERSON_META)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _prepared_intent(mutation: str) -> PreparedKeyedWrite:
    """``mutation`` prepared over a target that admits it: a Bitemporal one for
    every verb but ``delete``, which only a non-temporal target takes."""
    if mutation == "delete":
        return _prepared_person_delete(1)
    document: dict[str, object] = {
        "mutation": mutation,
        "entity": "WherePosition",
        "rows": [{"id": 1, "acctNum": "A", "value": "100.00"}],
        "validFrom": "2024-01-01T00:00:00.000000Z",
    }
    if mutation.endswith("Until"):
        document["until"] = "2024-06-01T00:00:00.000000Z"
    instruction = instructions.deserialize(document)
    prepared = instructions.prepare_wire_write(instruction, _WHERE_POSITION_META)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


# --------------------------------------------------------------------------- #
# The algebra itself.                                                         #
# --------------------------------------------------------------------------- #
def test_an_insert_intends_nothing_against_an_observed_state() -> None:
    # An opening row observes no prior state, so there is no claim for a second
    # intent to compete for — the absence is the missing answer, not an intent
    # kind of its own.
    assert keyed_intent(_prepared_intent("insert")) is None
    assert keyed_intent(_prepared_intent("insertUntil")) is None


@pytest.mark.parametrize(
    ("mutation", "kind"),
    [
        ("amend", "assignment"),
        ("amendUntil", "assignment"),
        ("delete", "destructive"),
        ("terminate", "destructive"),
        ("terminateUntil", "destructive"),
    ],
)
def test_every_other_keyed_mutation_intends_an_assignment_or_a_destruction(
    mutation: str, kind: str
) -> None:
    prepared = _prepared_intent(mutation)
    intent = keyed_intent(prepared)
    assert intent is not None
    assert intent.kind == kind
    assert intent.valid_time_window is prepared.valid_time_window


@pytest.mark.parametrize(
    ("held", "arriving", "verdict"),
    [
        (None, _ASSIGNMENT, "admit"),
        (None, _DESTRUCTIVE, "admit"),
        (None, SELECTION_INTENT, "admit"),
        (_ASSIGNMENT, _ASSIGNMENT, "coalesce"),
        (_ASSIGNMENT, _DESTRUCTIVE, "supersede"),
        (_DESTRUCTIVE, _DESTRUCTIVE, "deduplicate"),
        (_DESTRUCTIVE, _ASSIGNMENT, "incompatible"),
        (SELECTION_INTENT, _ASSIGNMENT, "incompatible"),
        (_ASSIGNMENT, SELECTION_INTENT, "incompatible"),
        (
            WriteIntent(kind="assignment", valid_time_window=TimeInterval(_VALID_FROM, INFINITY)),
            WriteIntent(kind="assignment", valid_time_window=TimeInterval(_OTHER_FROM, INFINITY)),
            "incompatible",
        ),
        (
            WriteIntent(kind="assignment", valid_time_window=TimeInterval(_VALID_FROM, _UNTIL)),
            WriteIntent(kind="assignment", valid_time_window=TimeInterval(_VALID_FROM, _UNTIL)),
            "coalesce",
        ),
        (
            WriteIntent(kind="destructive", valid_time_window=TimeInterval(_VALID_FROM, _UNTIL)),
            WriteIntent(kind="destructive", valid_time_window=TimeInterval(_VALID_FROM, INFINITY)),
            "incompatible",
        ),
    ],
)
def test_the_claim_algebra_answers_one_verdict_per_pair(
    held: WriteIntent | None, arriving: WriteIntent, verdict: str
) -> None:
    assert admits(held, arriving) == verdict


def test_the_claim_table_holds_what_the_buffer_will_carry() -> None:
    # An unclaimed state admits; a compatible intent replaces what is held,
    # because the merged write is what the flush will carry; a deduplicated or
    # refused one leaves the held claim exactly as it was.
    table = ClaimTable()
    assert table.claim(_STATE, _ASSIGNMENT) == "admit"
    assert table.held(_STATE) == _ASSIGNMENT
    assert table.claim(_STATE, _DESTRUCTIVE) == "supersede"
    assert table.held(_STATE) == _DESTRUCTIVE
    assert table.claim(_STATE, _DESTRUCTIVE) == "deduplicate"
    assert table.claim(_STATE, _ASSIGNMENT) == "incompatible"
    assert table.held(_STATE) == _DESTRUCTIVE
    table.clear()
    assert table.held(_STATE) is None


def test_releasing_claims_drops_exactly_the_named_scopes() -> None:
    other = VersionedStateKey(_STATE.object, _STATE.version + 1)
    table = ClaimTable()
    assert table.claim(_STATE, SELECTION_INTENT) == "admit"
    assert table.claim(other, _ASSIGNMENT) == "admit"
    table.release(iter((_STATE,)))
    assert table.held(_STATE) is None
    assert table.held(other) == _ASSIGNMENT


def test_the_claim_table_answers_which_objects_it_claims_as_its_claims_change() -> None:
    another = ObjectKey(_STATE.object.entity, (("id", 99),))
    table = ClaimTable()
    assert not table.claims_object(_STATE.object)
    assert table.claim(_STATE, SELECTION_INTENT) == "admit"
    assert table.claims_object(_STATE.object)
    assert table.claim(another, SELECTION_INTENT) == "admit"
    assert table.claims_object(another)
    table.release(iter((_STATE,)))
    assert not table.claims_object(_STATE.object)
    assert table.claims_object(another)
    table.clear()
    assert not table.claims_object(another)


def test_the_claim_table_answers_which_objects_a_claim_reaches_whole() -> None:
    another = ObjectKey(_STATE.object.entity, (("id", 99),))
    third = ObjectKey(_STATE.object.entity, (("id", 98),))
    table = ClaimTable()
    assert table.claim(_STATE, SELECTION_INTENT) == "admit"
    assert not table.spans(_STATE.object)
    assert table.claim(another, SPANNING_SELECTION_INTENT) == "admit"
    assert table.spans(another)
    assert table.claim(third, SPANNING_SELECTION_INTENT) == "admit"
    assert table.spans(third)
    assert table.claim(another, _ASSIGNMENT) == "incompatible"
    table.release(iter((another,)))
    assert not table.spans(another)
    assert table.spans(third)
    table.clear()
    assert not table.spans(third)


_S1 = "first observed state"
_S2 = "second observed state"


def _window(kind: str, start: dt.datetime, until: dt.datetime | None) -> WriteIntent:
    return WriteIntent(
        kind=cast("Any", kind),
        valid_time_window=TimeInterval(start, INFINITY if until is None else until),
    )


@pytest.mark.parametrize(
    ("held_scope", "held", "scope", "arriving", "verdict"),
    [
        (
            _S1,
            _window("assignment", _VALID_FROM, _UNTIL),
            _S2,
            _window("assignment", _OTHER_FROM, None),
            "compose",
        ),
        (
            _S1,
            _window("assignment", _VALID_FROM, _UNTIL),
            _S1,
            _window("destructive", _VALID_FROM, _UNTIL),
            "compose",
        ),
        (
            _S1,
            _window("destructive", _VALID_FROM, _UNTIL),
            _S2,
            _window("destructive", _VALID_FROM, _UNTIL),
            "compose",
        ),
        (
            _S1,
            _window("assignment", _VALID_FROM, _OTHER_FROM),
            _S2,
            _window("destructive", _UNTIL, None),
            "compose",
        ),
        (
            _S1,
            _window("destructive", _VALID_FROM, _OTHER_FROM),
            _S2,
            _window("assignment", _UNTIL, None),
            "compose",
        ),
        (
            _S1,
            _window("destructive", _VALID_FROM, _OTHER_FROM),
            _S1,
            _window("assignment", _UNTIL, None),
            "incompatible",
        ),
        (
            _S1,
            _window("destructive", _VALID_FROM, _UNTIL),
            _S2,
            _window("assignment", _OTHER_FROM, None),
            "incompatible",
        ),
        (
            _S1,
            _window("assignment", _VALID_FROM, _UNTIL),
            _S2,
            _window("destructive", _OTHER_FROM, None),
            "incompatible",
        ),
        (
            _S1,
            _window("assignment", _VALID_FROM, _OTHER_FROM),
            _S1,
            _window("destructive", _UNTIL, None),
            "incompatible",
        ),
    ],
    ids=[
        "overlapping-assignments",
        "destruction-of-the-same-window",
        "repeated-destruction",
        "destruction-disjoint-from-an-assignment",
        "assignment-disjoint-from-a-destruction",
        "assignment-at-a-destroyed-scope",
        "assignment-over-a-destroyed-window",
        "destruction-over-another-window",
        "destruction-of-another-window-at-the-same-scope",
    ],
)
def test_a_temporal_objects_observed_writes_compose_unless_they_resurrect_or_half_apply(
    held_scope: str, held: WriteIntent, scope: str, arriving: WriteIntent, verdict: str
) -> None:
    states = cast("Any", {_S1: _S1, _S2: _S2})
    assert admits_composed(((states[held_scope], held),), states[scope], arriving) == verdict


# --------------------------------------------------------------------------- #
# The claim-scope derivation and the object-claimed arm.                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("key", "mutation", "expected"),
    [
        (UNVERSIONED, "insert", None),
        (opt_lock.ExplicitVersion(_VERSION_ATTRIBUTE), "insert", None),
        (opt_lock.TransactionTimeDerived(_START_ATTRIBUTE), "insertUntil", None),
        (opt_lock.ExplicitVersion(_VERSION_ATTRIBUTE), "amend", _RETAINED),
        (opt_lock.ExplicitVersion(_VERSION_ATTRIBUTE), "delete", _RETAINED),
        (opt_lock.TransactionTimeDerived(_START_ATTRIBUTE), "terminate", _RETAINED),
        (UNVERSIONED, "amend", _OBJECT),
        (UNVERSIONED, "delete", _OBJECT),
    ],
)
def test_the_claim_scope_derivation_is_total_over_the_write_kind(
    key: opt_lock.OptimisticKey, mutation: str, expected: object
) -> None:
    # Two declared facts decide every arm — the target's Optimistic Key and the
    # mutation — and each of the three Optimistic Key variants names its own, so
    # no arm is reached because something was absent or because the tests above
    # it did not match.
    assert (
        opt_lock.settled_evidence(
            key,
            mutation,  # pyright: ignore[reportArgumentType]
            object_key=_OBJECT,
            observation=_RETAINED,
        )
        is expected
    )


def test_a_state_keyed_target_handed_no_observation_claims_nothing() -> None:
    # The state arm answers what its source retained, and a producer that retained
    # none settles against nothing here — the required-observation rule refuses it
    # where every buffered write is settled, rather than an object claim standing
    # in for evidence a gate needs.
    assert (
        opt_lock.settled_evidence(
            opt_lock.ExplicitVersion(_VERSION_ATTRIBUTE),
            "amend",
            object_key=_OBJECT,
            observation=None,
        )
        is None
    )


def test_an_instruction_naming_no_entity_of_the_model_is_refused() -> None:
    # Absence is never an input to the derivation: an unresolved target is a
    # caller that skipped resolving it, not a family without a version source.
    foreign = instructions.deserialize(
        {"mutation": "delete", "entity": "parallax.compatibility.Account", "rows": [{"id": 1}]}
    )
    assert isinstance(foreign, KeyedWrite)
    with pytest.raises(instructions.WriteInstructionError, match="declares no entity"):
        instructions.prepare_wire_write(foreign, _PERSON_META)


def test_an_object_claim_refuses_to_wrap_an_insert_or_a_multi_row_write() -> None:
    # The carrier's own structural half, which needs no model: an opening row has
    # no prior row to claim, and a claim is about the object ONE row addresses.
    with pytest.raises(ValueError, match="an insert claims no object"):
        insertion = instructions.deserialize(
            {"mutation": "insert", "entity": "Person", "rows": [{"id": 1, "name": "Ada"}]}
        )
        prepared = instructions.prepare_wire_write(insertion, _PERSON_META)
        assert isinstance(prepared, PreparedKeyedWrite)
        ObjectClaimedWrite(prepared)
    with pytest.raises(ValueError, match="an object claim addresses one object"):
        ObjectClaimedWrite(_prepared_person_delete(1, 2))
