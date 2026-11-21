"""Licensed writes: each holds the one authority that licenses it (m-unit-work, Docker-free)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

import pytest

from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.claims import ClaimScope, SettledEvidence, WriteIntent
from parallax.core._execution._unit_work.evidence import (
    InsertionIdentity,
    ParticipationToken,
    ReadEvidence,
)
from parallax.core._execution._unit_work.preparation import (
    WIRE,
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
    derive_keyed_instruction,
)
from parallax.core._execution._unit_work.row_acquisition import RetainedStartingRow
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    CallerConditioned,
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    InsertBatch,
    InsertionAuthorized,
    KeyedInsert,
    LicensedWrite,
    OrderedWrite,
    PostRemovalInsert,
    StateObserved,
    TemporalCoverageAuthority,
    TemporalCoverageWrite,
    TemporalIntent,
    TxStartConditioned,
    UnversionedLocked,
    UnversionedWriteBatch,
    VersionConditioned,
    WriteAuthority,
    WritePhase,
    distinct_evidence,
    is_licensed_by,
    target_write,
)
from parallax.core.internal import inheritance
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import CompiledEntity
from parallax.core.internal.planned_step import ObjectKey, VersionObservation
from parallax.core.internal.planned_step.keys import (
    TemporalObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.internal.planned_step.managed_row import RowSelection, named_members
from parallax.core.internal.temporal_read import Edge, TimeInterval
from parallax.core.internal.temporal_write.coverage import CoverageTransform
from parallax.core.internal.unit_work import (
    KeyedMutation,
    KeyedWriteInstruction,
    RetainedObservation,
    TargetWriteInstruction,
    admitted_write,
    object_key,
)
from tests._support.planner_probes import (
    admit_licensed,
    admitted_writes,
    object_source,
    source_registry,
    write_admission,
)
from tests._support.write_preparation import prepare_instruction, write_preparation_of
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    JAN,
    JUN,
    MAR,
    OBJECT,
    POSITION,
    SEP,
    START,
    T0,
    T1,
    addressed_write,
    observed_write,
    rectangle,
    retained,
)

_ACCOUNT = corpus_model("account")
_PERSON = model_of(CLASS_MODELS["person"])


def _prepared(mutation: KeyedMutation, *rows: Mapping[str, object]) -> PreparedKeyedInstruction:
    """``rows`` written by ``mutation`` as one prepared write: several rows are
    the derived plural a collapse produces."""
    first, *others = (
        prepare_instruction(
            KeyedWriteInstruction(mutation, "Account", row), write_preparation_of(_ACCOUNT)
        )
        for row in rows
    )
    if not others:
        return first
    return derive_keyed_instruction(
        first, (*first.rows, *(row for other in others for row in other.rows))
    )


def _account(account_id: int) -> dict[str, object]:
    return {"id": account_id, "owner": "Ada", "balance": Decimal("1.00")}


def _account_key(account_id: int) -> ObjectKey:
    key = object_key(_prepared("delete", {"id": account_id}), _ACCOUNT)
    assert key is not None
    return key


def test_an_insert_is_admitted_as_its_own_keyed_insert() -> None:
    prepared = _prepared("insert", _account(1))
    admitted = admitted_write(prepared, None, object_key(prepared, _ACCOUNT))
    assert isinstance(admitted, KeyedInsert)
    assert admitted.instruction is prepared
    assert admitted.object_key == _account_key(1)


@pytest.mark.parametrize(
    ("mutation", "row"),
    [("amend", {"id": 1, "balance": Decimal("2.00")}), ("delete", {"id": 1})],
)
def test_a_write_of_existing_state_needs_a_licence_beyond_itself(
    mutation: KeyedMutation, row: Mapping[str, object]
) -> None:
    with pytest.raises(ValueError, match="only an insert is admitted unlicensed"):
        admitted_write(_prepared(mutation, row), None, None)


def test_an_admitted_insert_opens_one_row() -> None:
    with pytest.raises(ValueError, match="opens 2 rows"):
        admitted_write(_prepared("insert", _account(1), _account(2)), None, None)


def test_an_admitted_insert_names_the_object_it_opens() -> None:
    with pytest.raises(ValueError, match="names no object to open"):
        admitted_write(_prepared("insert", _account(1)), None, None)


@pytest.mark.parametrize(
    "licence",
    ["observed", "insertion"],
)
def test_a_licensed_write_names_the_object_it_writes(licence: str) -> None:
    prepared = _prepared("amend", {"id": 1, "balance": Decimal("2.00")})
    key = _account_key(1)
    with pytest.raises(ValueError, match="names the object it writes"):
        if licence == "observed":
            observed = RetainedObservation(
                VersionedObjectStateKey(key, 4), VersionObservation(4), None
            )
            admitted_write(prepared, observed, None)
        else:
            admitted_write(prepared, None, None, insertion=InsertionIdentity(key))


def test_a_write_is_licensed_by_read_evidence_or_an_insertion_never_both() -> None:
    prepared = _prepared("amend", {"id": 1, "balance": Decimal("2.00")})
    key = _account_key(1)
    observed = RetainedObservation(VersionedObjectStateKey(key, 4), VersionObservation(4), None)
    with pytest.raises(ValueError, match="never by both"):
        admitted_write(prepared, observed, key, insertion=InsertionIdentity(key))  # pyright: ignore[reportArgumentType,reportCallIssue] - no overload takes evidence and an insertion together


def test_a_composed_opening_names_the_object_its_insert_names() -> None:
    assert _position_opening().object_key == OBJECT


def test_a_post_removal_insert_answers_its_inserts_phase_and_target() -> None:
    insert = admitted_write(_prepared("insert", _account(1)), None, _account_key(1))
    assert isinstance(insert, KeyedInsert)
    marker = PostRemovalInsert(insert)
    assert (marker.phase, marker.target) == ("insert", insert.instruction.target)


def _position_opening() -> ComposedBitemporalOpening:
    insertion = prepare_instruction(
        KeyedWriteInstruction(
            "insertUntil", "Position", {"id": 1, "acctNum": "A", "value": "1.00"}, JAN, SEP
        ),
        write_preparation_of(POSITION),
        WIRE,
    )
    amendment = prepare_instruction(
        KeyedWriteInstruction("amendUntil", "Position", {"id": 1, "value": "2.00"}, JAN, MAR),
        write_preparation_of(POSITION),
        WIRE,
    )
    assert isinstance(insertion, PreparedKeyedInstruction)
    assert isinstance(amendment, PreparedKeyedInstruction)
    admission = write_admission(POSITION)
    identity = admission.admit_insert(
        admitted_write(insertion, None, OBJECT), insertion_advice=None
    )
    assert identity is not None
    admit_licensed(admission, admitted_write(amendment, None, OBJECT, insertion=identity))
    (opening,) = admission.composed_writes()
    assert isinstance(opening, ComposedBitemporalOpening)
    return opening


def test_a_composed_temporal_write_keeps_equal_but_distinct_evidence_once_each_in_order() -> None:
    first = retained(rectangle(JAN, JUN, "1.00"))
    second = retained(rectangle(JUN, SEP, "2.00"))
    earlier = observed_write("amendUntil", first, valid_from=MAR, until=JUN, value="3.00")
    repeated = observed_write("amendUntil", first, valid_from=MAR, until=JUN, value="4.00")
    later = observed_write("amendUntil", second, valid_from=JUN, until=SEP, value="5.00")
    participation = ParticipationToken()
    twin = ReadEvidence(OBJECT.entity, OBJECT, participation, first)
    equal = ReadEvidence(OBJECT.entity, OBJECT, participation, first)
    assert twin == equal and twin is not equal
    writes = [
        admitted_write(w.instruction, w.authority.retained_observation, w.object_key, source=e)
        for w, e in ((earlier, twin), (repeated, twin), (later, equal))
    ]
    (composed,) = admitted_writes(POSITION, writes)
    assert isinstance(composed, ComposedTemporalWrite)
    kept = composed.source_evidence
    assert len(kept) == 2 and kept[0] is twin and kept[1] is equal


# --------------------------------------------------------------------------- #
# Each authority answers the record's projections.                            #
# --------------------------------------------------------------------------- #
_PARTICIPATION = ParticipationToken()


def _account_read(version: int) -> tuple[RetainedObservation, ReadEvidence]:
    key = _account_key(1)
    observed = RetainedObservation(
        VersionedObjectStateKey(key, version), VersionObservation(version), None
    )
    return observed, ReadEvidence(key.entity, key, _PARTICIPATION, observed)


def _observed_account() -> tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]:
    observed, source = _account_read(4)
    write = admitted_write(
        _prepared("amend", {"id": 1, "balance": Decimal("2.00")}),
        observed,
        _account_key(1),
        source=source,
    )
    return write, observed.key, (source,)


def _advanced_account() -> tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]:
    _observed, source = _account_read(4)
    current = VersionedObjectStateKey(_account_key(1), 5)
    write = admitted_write(
        _prepared("amend", {"id": 1, "balance": Decimal("2.00")}),
        current,
        _account_key(1),
        source=source,
    )
    return write, current, (source,)


def _locked_person() -> tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]:
    prepared = prepare_instruction(
        KeyedWriteInstruction("delete", "Person", {"id": 1}), write_preparation_of(_PERSON)
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    key = object_key(prepared, _PERSON)
    assert key is not None
    source = object_source(key)
    return admitted_write(prepared, key, key, source=source), key, (source,)


def _unresolved_insertion() -> tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]:
    prepared = _prepared("amend", {"id": 1, "balance": Decimal("2.00")})
    key = _account_key(1)
    return admitted_write(prepared, None, key, insertion=InsertionIdentity(key)), None, ()


def _resolved_insertion() -> tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]:
    registry = source_registry(_ACCOUNT)
    admission = WriteAdmission(_ACCOUNT, registry=registry)
    insert = admitted_write(_prepared("insert", _account(1)), None, _account_key(1))
    identity = admission.admit_insert(insert, insertion_advice=None)
    admission.drain_planned()
    write = registry.resolve_insertion_authorized_write(
        admitted_write(
            _prepared("amend", {"id": 1, "balance": Decimal("2.00")}),
            None,
            _account_key(1),
            insertion=identity,
        )
    )
    return write, VersionedObjectStateKey(_account_key(1), 1), ()


def _version_target() -> tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]:
    prepared = prepare_instruction(
        TargetWriteInstruction("amend", "Account", {"id": 1, "balance": "2.00"}, if_version=3),
        write_preparation_of(_ACCOUNT),
        WIRE,
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    write = target_write(prepared, inheritance.inheritance_facet_of(_ACCOUNT))
    return write, VersionedObjectStateKey(_account_key(1), 3), ()


def _tx_start_target() -> tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]:
    return addressed_write(value="150.00"), OBJECT, ()


_AUTHORITY_CASES: dict[
    str,
    tuple[
        Callable[[], tuple[AdmittedWrite, ClaimScope | None, tuple[ReadEvidence, ...]]],
        type[WriteAuthority],
        WritePhase,
    ],
] = {
    "state-observed": (_observed_account, StateObserved, "update"),
    "state-observed-advanced": (_advanced_account, StateObserved, "update"),
    "unversioned-locked": (_locked_person, UnversionedLocked, "delete"),
    "insertion-unresolved": (_unresolved_insertion, InsertionAuthorized, "update"),
    "insertion-resolved": (_resolved_insertion, InsertionAuthorized, "update"),
    "version-conditioned": (_version_target, VersionConditioned, "update"),
    "tx-start-conditioned": (_tx_start_target, TxStartConditioned, "update"),
}
_AUTHORITY_CLASSES: tuple[type[WriteAuthority], ...] = (
    StateObserved,
    UnversionedLocked,
    InsertionAuthorized,
    VersionConditioned,
    TxStartConditioned,
)


@pytest.mark.parametrize("case", list(_AUTHORITY_CASES))
def test_each_authority_answers_the_records_claim_scope_evidence_phase_and_target(
    case: str,
) -> None:
    build, licence, phase = _AUTHORITY_CASES[case]
    write, scope, evidence = build()
    assert isinstance(write, LicensedWrite)
    assert type(write.authority) is licence
    assert write.claim_scope == scope
    assert len(write.source_evidence) == len(evidence)
    assert all(kept is held for kept, held in zip(write.source_evidence, evidence, strict=True))
    assert write.phase == phase
    assert write.target is write.instruction.target
    assert [is_licensed_by(write, other) for other in _AUTHORITY_CLASSES] == [
        other is licence for other in _AUTHORITY_CLASSES
    ]


def test_only_a_licensed_write_is_licensed_by_an_authority() -> None:
    insert = admitted_write(_prepared("insert", _account(1)), None, _account_key(1))
    (composed,) = admitted_writes(
        POSITION, [addressed_write(value="1.00"), addressed_write(value="2.00")]
    )
    assert isinstance(composed, ComposedTemporalWrite)
    for item in (insert, composed, PostRemovalInsert(insert)):
        assert not any(is_licensed_by(item, licence) for licence in _AUTHORITY_CLASSES)


def _insertion_position() -> LicensedWrite[InsertionAuthorized]:
    prepared = prepare_instruction(
        KeyedWriteInstruction("amendUntil", "Position", {"id": 1, "value": "150.00"}, MAR, SEP),
        write_preparation_of(POSITION),
        WIRE,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, None, OBJECT, insertion=InsertionIdentity(OBJECT))


_WINDOW = WriteIntent("assignment", TimeInterval(MAR, SEP))


@pytest.mark.parametrize(
    "build",
    [
        lambda: observed_write("amendUntil", START, value="150.00"),
        _insertion_position,
        lambda: addressed_write(value="150.00"),
    ],
    ids=["state-observed", "insertion-authorized", "tx-start-conditioned"],
)
def test_a_write_against_temporal_coverage_alone_answers_its_intent_transform_and_selection(
    build: Callable[[], LicensedWrite[TemporalCoverageAuthority]],
) -> None:
    write = build()
    (intent,) = write.intents
    assert intent == TemporalIntent(_WINDOW, write.authority)
    assert intent.authority is write.authority
    (segment,) = write.transform.segments
    assert segment.assigned is not None
    assert named_members(segment.assigned) == {"value": Decimal("150.00")}
    assert write.selection is write.instruction.rows[0].selection


def test_a_lone_intent_keeps_the_authoritys_evidence_and_starting_row() -> None:
    source = ReadEvidence(OBJECT.entity, OBJECT, _PARTICIPATION, START)
    observed = admitted_write(
        observed_write("amendUntil", START, value="1.00").instruction, START, OBJECT, source=source
    )
    assert is_licensed_by(observed, StateObserved)
    (intent,) = observed.intents
    assert is_licensed_by(intent, StateObserved) and intent.authority is observed.authority
    assert intent.authority.retained_observation is START
    assert intent.authority.source_evidence[0] is source
    row = _starting_row(0)
    target = addressed_write(value="1.00")
    refined = replace(target, authority=replace(target.authority, starting_row=row))
    (condition,) = refined.intents
    assert is_licensed_by(condition, TxStartConditioned)
    assert condition.authority is refined.authority and condition.authority.starting_row is row


def _starting_row(read_at: int) -> RetainedStartingRow:
    state = START.key
    assert isinstance(state, TemporalObjectStateKey)
    return RetainedStartingRow(state, read_at, (), None)


def _condition(
    kind: Literal["assignment", "destructive"] = "assignment",
    until: dt.datetime = SEP,
    tx_start: dt.datetime = T0,
    starting_row: RetainedStartingRow | None = None,
) -> TemporalIntent[TxStartConditioned]:
    return TemporalIntent(
        WriteIntent(kind, TimeInterval(MAR, until)),
        TxStartConditioned(
            TemporalObjectStateKey(OBJECT, Edge(tx_time=tx_start, valid_time=MAR)), starting_row
        ),
    )


def test_equal_conditions_are_one_condition_whatever_starting_row_each_kept() -> None:
    first, second = (
        _condition(starting_row=_starting_row(0)),
        _condition(starting_row=_starting_row(1)),
    )
    assert first == second and first.authority.starting_row is not second.authority.starting_row
    assert first in (_condition(),)


@pytest.mark.parametrize(
    "other",
    [
        _condition(kind="destructive"),
        _condition(until=JUN),
        _condition(tx_start=T1),
    ],
    ids=["kind", "window", "stated-start"],
)
def test_a_condition_differing_in_kind_window_or_stated_start_is_another(
    other: TemporalIntent[TxStartConditioned],
) -> None:
    assert _condition() != other


def test_an_intent_is_licensed_only_by_its_own_authority() -> None:
    (observed,) = observed_write("amendUntil", START, value="1.00").intents
    (authorized,) = _insertion_position().intents
    (condition,) = addressed_write(value="1.00").intents
    coverage: tuple[type[TemporalCoverageAuthority], ...] = (
        StateObserved,
        InsertionAuthorized,
        TxStartConditioned,
    )
    for intent, licence in (
        (observed, StateObserved),
        (authorized, InsertionAuthorized),
        (condition, TxStartConditioned),
    ):
        assert [is_licensed_by(intent, other) for other in coverage] == [
            other is licence for other in coverage
        ]


# --------------------------------------------------------------------------- #
# Equality ignores lifetimes; merging keeps them by identity.                 #
# --------------------------------------------------------------------------- #
def test_equal_records_ignore_distinct_evidence_that_merging_keeps_by_identity() -> None:
    observed, _source = _account_read(4)
    key = _account_key(1)
    prepared = _prepared("amend", {"id": 1, "balance": Decimal("2.00")})
    one = ReadEvidence(key.entity, key, ParticipationToken(), observed)
    other = ReadEvidence(key.entity, key, ParticipationToken(), observed)
    first = admitted_write(prepared, observed, key, source=one)
    second = admitted_write(prepared, observed, key, source=other)
    assert first == second and first.authority == second.authority
    merged = distinct_evidence((first.source_evidence, second.source_evidence))
    assert len(merged) == 2 and merged[0] is one and merged[1] is other


def test_equal_conditions_ignore_their_starting_rows() -> None:
    state = START.key
    assert isinstance(state, TemporalObjectStateKey)
    target = addressed_write(value="1.00")
    rows = [RetainedStartingRow(state, read_at, (), None) for read_at in (0, 1)]
    first, second = (
        replace(target, authority=replace(target.authority, starting_row=row)) for row in rows
    )
    assert first == second and first.authority.starting_row is not second.authority.starting_row


# --------------------------------------------------------------------------- #
# Read Evidence merges once, by identity, first occurrence first.             #
# --------------------------------------------------------------------------- #
def _evidence() -> ReadEvidence:
    return ReadEvidence(OBJECT.entity, OBJECT, _PARTICIPATION, START)


def test_distinct_evidence_of_nothing_is_empty() -> None:
    assert distinct_evidence(()) == ()
    assert distinct_evidence(((), ())) == ()


def test_distinct_evidence_answers_the_first_group_itself_where_the_others_add_nothing() -> None:
    held = (_evidence(), _evidence())
    assert distinct_evidence((held,)) is held
    assert distinct_evidence((held, (), (held[1], held[0]))) is held


def test_distinct_evidence_keeps_equal_but_distinct_evidence_once_each_in_first_order() -> None:
    first, twin, other = _evidence(), _evidence(), _evidence()
    assert first == twin and first is not twin
    merged = distinct_evidence(((first,), (other, first), (twin, other)))
    assert [id(evidence) for evidence in merged] == [id(first), id(other), id(twin)]


def test_distinct_evidence_drops_a_first_groups_repeats_once_another_group_adds() -> None:
    first, other = _evidence(), _evidence()
    merged = distinct_evidence(((first, first), (other,)))
    assert [id(evidence) for evidence in merged] == [id(first), id(other)]


if TYPE_CHECKING:

    def _static_factory_contract(  # pyright: ignore[reportUnusedFunction] - static contract probe
        prepared: PreparedKeyedInstruction,
        target: PreparedTargetInstruction,
        families: inheritance.InheritanceFacet,
        evidence: SettledEvidence,
        maybe_evidence: SettledEvidence | None,
        key: ObjectKey,
        insertion: InsertionIdentity,
        source: ReadEvidence,
    ) -> None:
        inserted: KeyedInsert = admitted_write(prepared, None, key)
        authorized: LicensedWrite[InsertionAuthorized] = admitted_write(
            prepared, None, key, insertion=insertion
        )
        read: LicensedWrite[StateObserved | UnversionedLocked] = admitted_write(
            prepared, evidence, key, source=source
        )
        ingress: KeyedInsert | LicensedWrite[StateObserved | UnversionedLocked] = admitted_write(
            prepared, maybe_evidence, key, source=source
        )
        conditioned: LicensedWrite[CallerConditioned] = target_write(target, families)
        del inserted, authorized, read, ingress, conditioned
        admitted_write(prepared, None, key, insertion=insertion, source=source)  # pyright: ignore[reportCallIssue] - an insertion is no read, so it retains no source
        admitted_write(prepared, maybe_evidence, key, insertion=insertion)  # pyright: ignore[reportArgumentType,reportCallIssue] - evidence and an insertion never license one write together
        unconditioned: LicensedWrite[TxStartConditioned] = target_write(target, families)  # pyright: ignore[reportAssignmentType] - preparation, not the producer's type, picks the condition
        del unconditioned

    def _static_variance_contract(  # pyright: ignore[reportUnusedFunction] - static contract probe
        observed: LicensedWrite[StateObserved],
        targeted: LicensedWrite[TxStartConditioned],
        locked: LicensedWrite[UnversionedLocked],
        licensed: LicensedWrite[WriteAuthority],
        condition: TemporalIntent[TxStartConditioned],
        intent: TemporalIntent[TemporalCoverageAuthority],
        row: RetainedStartingRow,
    ) -> None:
        wide: LicensedWrite[WriteAuthority] = targeted
        coverage: LicensedWrite[TemporalCoverageAuthority] = observed
        refined: LicensedWrite[TxStartConditioned] = replace(
            targeted, authority=replace(targeted.authority, starting_row=row)
        )
        wide_intent: TemporalIntent[TemporalCoverageAuthority] = condition
        refined_intent: TemporalIntent[TxStartConditioned] = replace(
            condition, authority=replace(condition.authority, starting_row=row)
        )
        built: TemporalIntent[TxStartConditioned] = TemporalIntent(
            condition.write_intent, targeted.authority
        )
        del wide, coverage, refined, wide_intent, refined_intent, built
        narrowed: LicensedWrite[StateObserved] = licensed  # pyright: ignore[reportAssignmentType] - a licence is never widened into a narrower one
        narrowed_intent: TemporalIntent[StateObserved] = intent  # pyright: ignore[reportAssignmentType] - a licence is never widened into a narrower one
        del narrowed, narrowed_intent
        TemporalIntent(intent.write_intent, locked.authority)  # pyright: ignore[reportArgumentType] - an unversioned object composes no temporal intent

    def _static_narrowing_contract(  # pyright: ignore[reportUnusedFunction] - static contract probe
        admitted: AdmittedWrite,
        ordered: OrderedWrite,
        intent: TemporalIntent[TemporalCoverageAuthority],
        composed: ComposedTemporalWrite,
    ) -> None:
        if is_licensed_by(admitted, StateObserved):
            observed: StateObserved = admitted.authority
            del observed
        if is_licensed_by(admitted, UnversionedLocked):
            locked: UnversionedLocked = admitted.authority
            del locked
        if is_licensed_by(admitted, InsertionAuthorized):
            authorized: InsertionAuthorized = admitted.authority
            del authorized
        if is_licensed_by(admitted, VersionConditioned):
            version: VersionConditioned = admitted.authority
            del version
        if is_licensed_by(admitted, TxStartConditioned):
            tx_start: TxStartConditioned = admitted.authority
            del tx_start
        if (
            isinstance(ordered, ComposedTemporalWrite)
            or is_licensed_by(ordered, StateObserved)
            or is_licensed_by(ordered, InsertionAuthorized)
            or is_licensed_by(ordered, TxStartConditioned)
        ):
            pending: TemporalCoverageWrite = ordered
            del pending
        if is_licensed_by(intent, StateObserved):
            observed_intent: StateObserved = intent.authority
            del observed_intent
        if is_licensed_by(intent, InsertionAuthorized):
            authorized_intent: InsertionAuthorized = intent.authority
            del authorized_intent
        if is_licensed_by(intent, TxStartConditioned):
            tx_start_intent: TxStartConditioned = intent.authority
            del tx_start_intent
        anchor: TemporalIntent[InsertionAuthorized] | None = next(
            (held for held in composed.intents if is_licensed_by(held, InsertionAuthorized)), None
        )
        conditions: tuple[TemporalIntent[TxStartConditioned], ...] = tuple(
            held for held in composed.intents if is_licensed_by(held, TxStartConditioned)
        )
        del anchor, conditions
        is_licensed_by(intent, UnversionedLocked)  # pyright: ignore[reportArgumentType,reportCallIssue] - no temporal intent is an unversioned object's

    def _static_projection_contract(  # pyright: ignore[reportUnusedFunction] - static contract probe
        insert: KeyedInsert,
        licensed: LicensedWrite[WriteAuthority],
        observed: LicensedWrite[StateObserved],
        locked: LicensedWrite[UnversionedLocked],
        authorized: LicensedWrite[InsertionAuthorized],
        versioned: LicensedWrite[VersionConditioned],
        targeted: LicensedWrite[TxStartConditioned],
        insert_batch: InsertBatch,
        locked_batch: UnversionedWriteBatch,
        composed: ComposedTemporalWrite,
        opening: ComposedBitemporalOpening,
        marker: PostRemovalInsert,
        admitted: AdmittedWrite,
        composed_write: ComposedWrite,
        ordered: OrderedWrite,
        observed_intent: TemporalIntent[StateObserved],
        authorized_intent: TemporalIntent[InsertionAuthorized],
        target_intent: TemporalIntent[TxStartConditioned],
        intent: TemporalIntent[TemporalCoverageAuthority],
        coverage: TemporalCoverageWrite,
    ) -> None:
        instruction: PreparedKeyedInstruction = admitted.instruction
        key: ObjectKey | None = admitted.object_key
        keys: tuple[ObjectKey | None, ...] = insert_batch.object_keys
        locked_keys: tuple[ObjectKey, ...] = locked_batch.object_keys
        composed_key: ObjectKey = composed.object_key
        opening_key: ObjectKey | None = opening.object_key
        evidence: tuple[ReadEvidence, ...] = ordered.source_evidence
        phase: WritePhase = composed_write.phase
        target: CompiledEntity = composed_write.target
        scope: ClaimScope | None = licensed.claim_scope
        authority: WriteAuthority = licensed.authority
        del instruction, key, keys, locked_keys, composed_key, opening_key, evidence
        del phase, target, scope, authority
        observation: RetainedObservation = observed.authority.retained_observation
        current: VersionedObjectStateKey | None = observed.authority.current
        observed_evidence: tuple[ReadEvidence, ...] = observed.authority.source_evidence
        locked_evidence: tuple[ReadEvidence, ...] = locked.authority.source_evidence
        identity: InsertionIdentity = authorized.authority.identity
        resolved: ClaimScope | None = authorized.authority.claim_scope
        stated_version: VersionedObjectStateKey = versioned.authority.state
        version: int = versioned.authority.revision
        absorbed: tuple[ReadEvidence, ...] = versioned.authority.source_evidence
        stated_start: TemporalObjectStateKey = targeted.authority.state
        start: dt.datetime = targeted.authority.revision
        starting_row: RetainedStartingRow | None = targeted.authority.starting_row
        del observation, current, observed_evidence, locked_evidence, identity, resolved
        del stated_version, version, absorbed, stated_start, start, starting_row
        lone_intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...] = observed.intents
        lone_transform: CoverageTransform = authorized.transform
        lone_selection: RowSelection = targeted.selection
        intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...] = composed.intents
        opening_intents: tuple[WriteIntent, ...] = opening.intents
        stated: WriteIntent = intent.write_intent
        intent_authority: TemporalCoverageAuthority = intent.authority
        observed_observation: RetainedObservation = observed_intent.authority.retained_observation
        intent_evidence: tuple[ReadEvidence, ...] = observed_intent.authority.source_evidence
        insertion: InsertionIdentity = authorized_intent.authority.identity
        intent_start: dt.datetime = target_intent.authority.revision
        intent_row: RetainedStartingRow | None = target_intent.authority.starting_row
        del lone_intents, lone_transform, lone_selection, intents, opening_intents, stated
        del intent_authority, observed_observation, intent_evidence, insertion, intent_start
        del intent_row
        pending_intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...] = coverage.intents
        pending_transform: CoverageTransform = coverage.transform
        pending_key: ObjectKey = coverage.object_key
        pending_target: CompiledEntity = coverage.target
        del pending_intents, pending_transform, pending_key, pending_target
        _ = coverage.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a composition holds no one instruction
        _ = locked.intents  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a write of an unversioned object is no temporal write
        _ = locked.transform  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a write of an unversioned object is no temporal write
        _ = locked.selection  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a write of an unversioned object is no temporal write
        _ = versioned.intents  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a versioned Non-Temporal write is no temporal write
        _ = versioned.transform  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a versioned Non-Temporal write is no temporal write
        _ = versioned.selection  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a versioned Non-Temporal write is no temporal write
        _ = licensed.intents  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only a write against temporal coverage composes intents
        _ = authorized.authority.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - insertion authority is no Read Evidence
        _ = targeted.authority.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a Transaction-Time start absorbs no evidence
        _ = locked.authority.retained_observation  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an unversioned object has no state to observe
        _ = versioned.authority.starting_row  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only a temporal condition reads a starting row
        _ = observed.authority.state  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a read states no caller's revision
        _ = admitted.authority  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insert needs no licence
        _ = observed_intent.authority.revision  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a read states no caller's start
        _ = observed_intent.authority.starting_row  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a read retains no starting row
        _ = authorized_intent.authority.retained_observation  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insertion observed nothing
        _ = authorized_intent.authority.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - insertion authority is no Read Evidence
        _ = authorized_intent.authority.revision  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insertion states no caller's start
        _ = target_intent.authority.retained_observation  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a caller's condition observed nothing
        _ = target_intent.authority.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a caller's condition is no Read Evidence
        _ = intent.authority.retained_observation  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only an observed intent observed
        _ = intent.authority.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only an observed intent holds evidence
        _ = intent.authority.state  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only a target intent states a start
        _ = intent.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an intent keeps no instruction; the transform holds its values
        _ = insert.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insert claims nothing
        _ = insert_batch.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch names several objects
        _ = insert_batch.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch claims nothing
        _ = locked_batch.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch names several objects
        _ = locked_batch.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch claims nothing
        _ = composed.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a composition holds no one instruction
        _ = composed.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a composition composes by object
        _ = opening.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an opening holds its insert instead
        _ = marker.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = marker.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = marker.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = marker.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = admitted.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an admitted insert claims nothing
        _ = composed_write.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - compositions hold none
        _ = composed_write.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - the marker names none
        _ = composed_write.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - the marker holds none
        _ = ordered.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - compositions hold none
        _ = ordered.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - batches name several objects
        unordered: OrderedWrite = marker  # pyright: ignore[reportAssignmentType] - ordering consumes markers
        unbatched: ComposedWrite = insert_batch  # pyright: ignore[reportAssignmentType] - only batching batches
        uncomposed: AdmittedWrite = composed  # pyright: ignore[reportAssignmentType] - only admission composes
        del unordered, unbatched, uncomposed
