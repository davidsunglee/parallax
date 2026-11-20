"""Write admission and Observed-State Coalescing (`m-unit-work`).

Admission judges each arriving write by one claim algebra and composes it by
the verdict it reached, so this module measures the algebra itself as a pure
function, beside the admitted writes a write travels as; the choreography a caller
performs through the real handles over a fake port is
``test_transaction_write_claims.py``'s subject.

The evidence a source carries and how long it lives is `test_source_registry.py`'s
subject; what lives here is what a SECOND intent against the same evidence may do.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, cast

import pytest

from parallax.conformance import models
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.claims import (
    admits,
    admits_composed,
    settled_evidence,
)
from parallax.core._execution._unit_work.evidence import InsertionIdentity
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    derive_keyed_instruction,
)
from parallax.core._execution._unit_work.preparation import WIRE
from parallax.core._execution._unit_work.write_items import (
    InsertionAuthorized,
    LicensedWrite,
    StateObserved,
    TxStartConditioned,
    UnversionedLocked,
    VersionConditioned,
    WriteAuthority,
    admitted_write,
    is_licensed_by,
)
from parallax.core.internal import concurrency
from parallax.core.internal.base import INFINITY
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.planned_step import ObjectKey, VersionObservation
from parallax.core.internal.planned_step.keys import (
    TemporalObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.internal.temporal_read import Edge, TimeInterval
from parallax.core.internal.unit_work import (
    KeyedWriteInstruction,
    RetainedObservation,
    WriteIntent,
    keyed_intent,
)
from tests._support.planner_probes import object_source
from tests._support.write_preparation import prepare_instruction, write_preparation_of
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
_PERSON_ONE = ObjectKey(EntityIdentity("parallax.compatibility", "Person"), (("id", 1),))
_RETAINED = RetainedObservation(
    VersionedObjectStateKey(_OBJECT, 4), VersionObservation(observed_version=4), None
)

_PERSON_META = model_of(PERSON)
_WHERE_POSITION_META = model_of(WHERE_POSITION_META)


def _prepared_person_delete(*ids: int) -> PreparedKeyedInstruction:
    """The deletion of each Person ``ids`` names, as one prepared write: several
    ids are the derived plural a collapse produces."""
    first, *others = (
        prepare_instruction(
            KeyedWriteInstruction("delete", "parallax.compatibility.Person", {"id": value}),
            write_preparation_of(_PERSON_META),
            WIRE,
        )
        for value in ids
    )
    if not others:
        return first
    return derive_keyed_instruction(
        first, (*first.rows, *(row for other in others for row in other.rows))
    )


def _prepared_intent(mutation: str) -> PreparedKeyedInstruction:
    """``mutation`` prepared over a target that admits it: a Bitemporal one for
    every verb but ``delete``, which only a non-temporal target takes."""
    if mutation == "delete":
        return _prepared_person_delete(1)
    document: dict[str, object] = {
        "mutation": mutation,
        "entity": "WherePosition",
        "row": {"id": 1}
        if mutation.startswith("terminate")
        else {"id": 1, "acctNum": "A", "value": "100.00"},
        "validFrom": "2024-01-01T00:00:00.000000Z",
    }
    if mutation.endswith("Until"):
        document["until"] = "2024-06-01T00:00:00.000000Z"
    instruction = instructions.deserialize(document)
    prepared = prepare_instruction(instruction, write_preparation_of(_WHERE_POSITION_META), WIRE)
    assert isinstance(prepared, PreparedKeyedInstruction)
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
        (_ASSIGNMENT, _ASSIGNMENT, "coalesce"),
        (_ASSIGNMENT, _DESTRUCTIVE, "supersede"),
        (_DESTRUCTIVE, _DESTRUCTIVE, "deduplicate"),
        (_DESTRUCTIVE, _ASSIGNMENT, "incompatible"),
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
# The claim-scope derivation and the unversioned case.                         #
# --------------------------------------------------------------------------- #
_MODELS = models.load_models()


def _versioning(stem: str, entity: str) -> tuple[concurrency.ConcurrencyFacet, EntityIdentity]:
    return concurrency.concurrency_facet_of(_MODELS[stem]), EntityIdentity(
        "parallax.compatibility", entity
    )


@pytest.mark.parametrize(
    ("stem", "entity", "mutation", "expected"),
    [
        ("animal", "Person", "insert", None),
        ("account", "Account", "insert", None),
        ("balance", "Balance", "insertUntil", None),
        ("account", "Account", "amend", _RETAINED),
        ("account", "Account", "delete", _RETAINED),
        ("balance", "Balance", "terminate", _RETAINED),
        ("animal", "Person", "amend", _OBJECT),
        ("animal", "Person", "delete", _OBJECT),
    ],
)
def test_the_claim_scope_derivation_is_total_over_the_write_kind(
    stem: str, entity: str, mutation: str, expected: object
) -> None:
    # Two declared facts decide every case — what the target's family settles
    # against and the mutation — so no case is reached because something was
    # absent or because the tests above it did not match.
    versioning, identity = _versioning(stem, entity)
    assert (
        settled_evidence(
            versioning,
            identity,
            mutation,  # pyright: ignore[reportArgumentType]
            object_key=_OBJECT,
            observation=_RETAINED,
        )
        is expected
    )


def test_an_entity_the_model_lacks_settles_against_nothing_it_could_claim() -> None:
    # Reading a miss as an object claim would let an unrecognized write claim an
    # object on the strength of what was missing.
    versioning, identity = _versioning("account", "Undeclared")
    with pytest.raises(KeyError, match="Undeclared"):
        settled_evidence(versioning, identity, "amend", object_key=_OBJECT, observation=_RETAINED)


def test_a_state_keyed_target_handed_no_observation_claims_nothing() -> None:
    # The state case answers what its source retained, and a producer that retained
    # none settles against nothing here, rather than an object claim standing in
    # for evidence a gate needs.
    versioning, identity = _versioning("account", "Account")
    assert settled_evidence(
        versioning, identity, "amend", object_key=_OBJECT, observation=None
    ) is (None)


_AUTHORITIES: tuple[WriteAuthority, ...] = (
    StateObserved(_RETAINED),
    UnversionedLocked((object_source(_PERSON_ONE),)),
    InsertionAuthorized(InsertionIdentity(_PERSON_ONE)),
    VersionConditioned(VersionedObjectStateKey(_PERSON_ONE, 3)),
    TxStartConditioned(TemporalObjectStateKey(_PERSON_ONE, Edge(tx_time=_VALID_FROM))),
)


@pytest.mark.parametrize("authority", _AUTHORITIES, ids=lambda authority: type(authority).__name__)
def test_a_licensed_write_refuses_an_insert_and_a_write_of_several_objects(
    authority: WriteAuthority,
) -> None:
    # The record's own structural half, which needs no model: an opening row
    # needs no licence, and a licence is about the one object a write addresses.
    insert = prepare_instruction(
        KeyedWriteInstruction("insert", "Person", {"id": 1, "name": "Ada"}),
        write_preparation_of(_PERSON_META),
        WIRE,
    )
    assert isinstance(insert, PreparedKeyedInstruction)
    with pytest.raises(ValueError, match="an insert is admitted by its own verb"):
        LicensedWrite(insert, _PERSON_ONE, authority)
    with pytest.raises(ValueError, match="addresses one existing object"):
        LicensedWrite(_prepared_person_delete(1, 2), _PERSON_ONE, authority)


def test_the_factory_refuses_a_licensed_insert_and_a_licensed_write_of_several_objects() -> None:
    insert = prepare_instruction(
        KeyedWriteInstruction("insert", "Person", {"id": 1, "name": "Ada"}),
        write_preparation_of(_PERSON_META),
        WIRE,
    )
    assert isinstance(insert, PreparedKeyedInstruction)
    source = object_source(_PERSON_ONE)
    with pytest.raises(ValueError, match="an insert is admitted by its own verb"):
        admitted_write(insert, _PERSON_ONE, _PERSON_ONE, source=source)
    with pytest.raises(ValueError, match="an insert is admitted by its own verb"):
        admitted_write(insert, None, _PERSON_ONE, insertion=InsertionIdentity(_PERSON_ONE))
    with pytest.raises(ValueError, match="addresses 2 rows"):
        admitted_write(_prepared_person_delete(1, 2), _PERSON_ONE, _PERSON_ONE, source=source)


def test_an_unversioned_write_requires_the_source_it_was_admitted_through() -> None:
    # The object key is the claim; the source evidence beside it is what keeps
    # that source's demand alive, so neither the factory nor the authority
    # admits a write without one.
    prepared = _prepared_person_delete(1)
    message = (
        "A write of an unversioned object requires the source evidence it was admitted through"
    )
    with pytest.raises(ValueError, match=message):
        admitted_write(prepared, _PERSON_ONE, _PERSON_ONE)
    with pytest.raises(ValueError, match=message):
        UnversionedLocked(())
    source = object_source(_PERSON_ONE)
    claimed = admitted_write(prepared, _PERSON_ONE, _PERSON_ONE, source=source)
    assert is_licensed_by(claimed, UnversionedLocked)
    assert claimed.source_evidence == (source,) and claimed.source_evidence[0] is source


@pytest.mark.parametrize(
    "evidence", [None, VersionObservation(observed_version=4)], ids=["missing", "plain"]
)
def test_an_observed_write_requires_a_retained_observation(evidence: object) -> None:
    # Application ingress hands a write the retained observation its read
    # produced; a plain State Observation names no claim and spends nothing, so
    # it is refused where the observed authority is built, before anything is
    # buffered.
    prepared = _prepared_person_delete(1)
    with pytest.raises(ValueError, match="requires the retained observation"):
        StateObserved(evidence)  # pyright: ignore[reportArgumentType]
    if evidence is not None:
        with pytest.raises(ValueError, match="requires the retained observation"):
            admitted_write(prepared, evidence, _PERSON_ONE)  # pyright: ignore[reportArgumentType, reportCallIssue]
    observed = admitted_write(prepared, _RETAINED, _PERSON_ONE)
    assert is_licensed_by(observed, StateObserved)
    assert observed.authority.retained_observation is _RETAINED
