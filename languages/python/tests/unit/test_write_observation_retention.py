"""Write-observation retention unit tests (`parallax.snapshot.handle._retention`).

Drives :class:`ObservedRows` and :func:`retain_evidence` directly, off
hand-written physical-column rows rather than through a `Transaction.find`: which
of the two mutually exclusive branches a row takes (a versioned row's observed
version, a temporal row's whole predecessor milestone), which rows retain no
evidence at all, what the retained state is keyed by, and what a hint carries
when there is no state behind it.

Everything a collector holds is asserted through the Source Hints the retention
answers, never off its own storage: the accumulator is an internal seam, and a
proof that crosses it would pin an arrangement no caller can observe.

The whole-choreography proofs — a real find licensing or refusing a later write —
stay in `test_transaction_reads.py` and `test_transaction_writes.py`; what lives
here is the seam itself.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from decimal import Decimal

from _corpus_identity_support import corpus_entity, corpus_object_key

from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.conformance import models
from parallax.core.base import INFINITY
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.temporal_read import Edge
from parallax.core.unit_work import (
    FixedClock,
    ObservedStateKey,
    RetainedObservation,
    SourceHint,
    TemporalObservation,
    TemporalStateKey,
    TransactionSettings,
    UnitOfWork,
    VersionedStateKey,
    VersionObservation,
    WriteBatchTrigger,
    WritePlan,
    run_unit_of_work,
)
from parallax.snapshot.handle import build_write_planner
from parallax.snapshot.handle._family import entity_layout, members, placed_members
from parallax.snapshot.handle._predicate_writes import (
    _predecessor_payload,  # pyright: ignore[reportPrivateUsage] - the predicate lane's own contribution, proved to be one extraction with retention's
)
from parallax.snapshot.handle._retention import ObservedRows, retain_evidence

_MODELS = models.load_models()
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

# Interval values as the port returns them: an aware `datetime` for a finite
# bound, the neutral open-bound sentinel for an open one. Nothing between the
# driver and a Predecessor Row re-renders either, so a fixture that spelled them
# on the wire would be describing a row this seam never sees.
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_RATE_TX_START = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_INFINITY = INFINITY


def _no_flush(_plan: WritePlan, *, trigger: WriteBatchTrigger) -> None:
    """A flush sink for a test that never flushes."""
    return None


def _accepted(model_name: str) -> AcceptedMetamodel:
    return _MODELS[model_name]


def _account_columns(*, id_: int = 1, version: int | None = 4) -> Mapping[str, object]:
    columns: dict[str, object] = {"id": id_, "owner": "Ada", "balance": Decimal("5.00")}
    if version is not None:
        columns["version"] = version
    return columns


# The state every `_balance_columns` row observed: `Balance` is
# Transaction-Time-only, so its milestone is that one axis's from-instant.
_BALANCE_STATE = TemporalStateKey(corpus_object_key("Balance", ("id", 1)), Edge(tx_time=_TX_START))


def _balance_columns(*, id_: int = 1) -> Mapping[str, object]:
    return {
        "bal_id": id_,
        "acct_num": "A-1",
        "val": Decimal("5.00"),
        "in_z": _TX_START,
        "out_z": _INFINITY,
    }


# A Transaction-Time-Only row under Relational Document Layout, as the fan-out
# leaves it: every member under its own column name, occurrences decoded to their
# declared shape, and the raw Structured Column riding beside them.
def _voyage_columns() -> dict[str, object]:
    return {
        "id": 7,
        "title": "Northbound",
        "crew": 12,
        "manifest": {"cargo": "grain"},
        "legs": ({"port": "Oslo"}, {"port": "Bergen"}),
        "in_z": _TX_START,
        "out_z": _INFINITY,
    }


_VOYAGE_DOCUMENT: Mapping[str, object] = {
    "title": "Northbound",
    "manifest": {"cargo": "grain"},
    "charterCode": "NB-118",
}


def _standalone(model: AcceptedMetamodel, observations: ObservedRows) -> Mapping[int, SourceHint]:
    """The hints a STANDALONE read retains — no unit of work behind it."""
    return retain_evidence(model, observations, ledger=None)


def _hint(model: AcceptedMetamodel, observations: ObservedRows, node: int = 0) -> SourceHint:
    return _standalone(model, observations)[node]


def _in_transaction[T](model: AcceptedMetamodel, body: Callable[[UnitOfWork], T]) -> T:
    """Run ``body`` in a unit of work over ``model``."""
    return run_unit_of_work(
        body,
        settings=TransactionSettings(),
        clock=FixedClock(_FIXED),
        meta=model,
        flush_executor=_no_flush,
        planner=build_write_planner(model),
        subject_identity=TEST_SUBJECT_IDENTITY,
    )


# --------------------------------------------------------------------------- #
# What a collector hands the retention: nothing, or a copy.                   #
# --------------------------------------------------------------------------- #
def test_a_collector_that_observed_nothing_retains_no_sources() -> None:
    # A read that materialized no row — or whose every row was non-hydrating —
    # hands the retention an empty collector, and every value it publishes
    # carries no hint rather than a hint over nothing.
    assert _standalone(_accepted("account"), ObservedRows()) == {}


def test_an_edit_to_the_observed_columns_reaches_nothing_the_retention_answered() -> None:
    # The seam accepts any caller-owned `Mapping`, and a read observes each row
    # while that row is still live, so the collector snapshots what it was
    # handed. The copy protects the OUTPUT: an edit afterwards reaches neither
    # the object a hint names nor the state it retained.
    handed: dict[str, object] = dict(_account_columns())
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Account"), handed, None)
    handed["id"] = 2
    handed["owner"] = "Grace"
    handed["version"] = 9
    hint = _hint(_accepted("account"), observations)
    assert hint.object_key == corpus_object_key("Account", ("id", 1))
    assert hint.observation is not None
    assert hint.observation.evidence == VersionObservation(observed_version=4)


def test_an_edit_to_the_observed_columns_reaches_no_member_of_a_retained_predecessor() -> None:
    # The snapshot covers the WHOLE row, not only the columns a hint is keyed
    # by. A temporal row retains every applicable member, so an ordinary payload
    # member is exactly what an aliased mapping would corrupt: the successor a
    # later write chains would carry the edited value forward as stored state.
    handed: dict[str, object] = dict(_balance_columns())
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Balance"), handed, None)
    handed["bal_id"] = 2
    handed["acct_num"] = "A-2"
    handed["val"] = Decimal("9.00")
    handed["in_z"] = _FIXED
    hint = _hint(_accepted("balance"), observations)
    assert hint.observation is not None
    observation = hint.observation.evidence
    assert isinstance(observation, TemporalObservation)
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "acctNum": "A-1",
        "value": Decimal("5.00"),
        "txStart": _TX_START,
        "txEnd": _INFINITY,
    }
    assert hint.observation.key == _BALANCE_STATE


# --------------------------------------------------------------------------- #
# The two mutually exclusive retention branches.                              #
# --------------------------------------------------------------------------- #
def test_a_versioned_row_retains_its_observed_version() -> None:
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Account"), _account_columns(), None)
    hint = _hint(_accepted("account"), observations)
    assert hint.observation is not None
    assert hint.observation.evidence == VersionObservation(observed_version=4)
    assert hint.observation.key == VersionedStateKey(corpus_object_key("Account", ("id", 1)), 4)


def test_a_versioned_row_whose_version_column_the_projection_omitted_retains_no_state() -> None:
    # The seam takes no data on faith: a row that reached it without the version
    # column it would gate on retains no evidence rather than observing a guess.
    # It still names the object it denotes, which is all a hint claims.
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Account"), _account_columns(version=None), None)
    hint = _hint(_accepted("account"), observations)
    assert hint.observation is None
    assert hint.object_key == corpus_object_key("Account", ("id", 1))


def test_a_row_that_is_neither_versioned_nor_temporal_retains_no_state() -> None:
    # An unversioned Non-Temporal row observes no state at all, so its hint
    # carries the object and the participation and nothing else.
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Order"), {"id": 1, "customer_id": 2}, None)
    hint = _hint(_accepted("orders"), observations)
    assert hint.observation is None
    assert hint.entity == corpus_entity("Order")
    assert hint.object_key == corpus_object_key("Order", ("id", 1))


def test_a_temporal_row_retains_its_whole_predecessor_milestone() -> None:
    # The Predecessor Row is COMPLETE — every applicable member, not just the
    # bounds — because a chained successor carries forward members the authored
    # mutation never mentioned.
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Balance"), _balance_columns(), None)
    hint = _hint(_accepted("balance"), observations)
    assert hint.observation is not None
    observation = hint.observation.evidence
    assert isinstance(observation, TemporalObservation)
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "acctNum": "A-1",
        "value": Decimal("5.00"),
        "txStart": _TX_START,
        "txEnd": _INFINITY,
    }
    assert observation.predecessor.document is None
    assert hint.observation.key == _BALANCE_STATE


def test_a_retained_predecessor_is_the_extraction_a_predicate_write_also_streams() -> None:
    # A real find's Predecessor Row and the one a materializing predicate write
    # contributes per resolved row are ONE extraction over the row's applicable
    # members, not two that happen to agree: `retain_evidence` and
    # `_predecessor_payload` reach the same `row_payload` rule, value-object
    # occurrences included. Two extractions that drifted would chain successors
    # carrying different rows forward from the same stored state.
    model = _accepted("document-layout")
    entity = model.entity(corpus_entity("Voyage"))
    assert entity is not None
    layout = entity_layout(model, entity)
    assert layout is not None
    columns = _voyage_columns()

    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Voyage"), columns, _VOYAGE_DOCUMENT)
    hint = _hint(model, observations)
    assert hint.observation is not None
    observation = hint.observation.evidence
    assert isinstance(observation, TemporalObservation)

    streamed = _predecessor_payload(members(placed_members(model, entity, layout)), columns)
    assert {"manifest", "legs"} <= streamed.keys()
    assert dict(observation.predecessor.members) == streamed
    # The Structured Column rides BESIDE the members either way, so the shared
    # extraction is over the members alone.
    assert observation.predecessor.document == _VOYAGE_DOCUMENT


# --------------------------------------------------------------------------- #
# What the retained evidence is keyed by.                                     #
# --------------------------------------------------------------------------- #
def test_evidence_is_keyed_by_the_rows_own_entity_never_its_family_root() -> None:
    # `DepositRate` is a concrete subtype of the bitemporal root `Rate`, whose own
    # declaration owns the primary key and both axes. The key still names the
    # subtype, because that is the class a developer's later `tx.update(copy)`
    # carries (`m-unit-work` `KeyedWrite.entity`).
    columns: Mapping[str, object] = {
        "id": 1,
        "amount": Decimal("2.50"),
        "grade": "A",
        "from_z": _VALID_START,
        "thru_z": _INFINITY,
        "in_z": _RATE_TX_START,
        "out_z": _INFINITY,
    }
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("DepositRate"), columns, None)
    hint = _hint(_accepted("rate"), observations)
    assert hint.observation is not None
    assert hint.observation.key == TemporalStateKey(
        corpus_object_key("DepositRate", ("id", 1)),
        Edge(tx_time=_RATE_TX_START, valid_time=_VALID_START),
    )


def test_two_reads_of_one_milestone_at_different_pins_retain_one_state() -> None:
    # The property that makes an Edge usable as a key without an identity map:
    # an Edge is a VALUE, so two independent reads of one milestone — here a
    # latest read and a read pinned at a past instant that still resolves to it —
    # derive equal coordinates and therefore name the SAME observed state. Within
    # a transaction the second read answers the FIRST read's own evidence, so a
    # value still held from the first read is not superseded by the second.
    model = _accepted("balance")
    latest = ObservedRows()
    latest.observe_row(0, corpus_entity("Balance"), _balance_columns(), None)
    historical = ObservedRows()
    historical.observe_row(0, corpus_entity("Balance"), _balance_columns(), None)

    def observe(uow: UnitOfWork) -> tuple[RetainedObservation, RetainedObservation]:
        first = retain_evidence(model, latest, ledger=uow)[0].observation
        second = retain_evidence(model, historical, ledger=uow)[0].observation
        assert first is not None
        assert second is not None
        return first, second

    first, second = _in_transaction(model, observe)
    assert first is second
    assert first.key == _BALANCE_STATE


def test_two_observed_versions_of_one_object_are_distinct_states() -> None:
    # The ledger admits several observed states of one Object Key: the version is
    # part of the address, so a read that saw version 4 and a later read that saw
    # version 7 hold evidence about two different states rather than overwriting
    # one slot.
    model = _accepted("account")
    first_read = ObservedRows()
    first_read.observe_row(0, corpus_entity("Account"), _account_columns(version=4), None)
    second_read = ObservedRows()
    second_read.observe_row(0, corpus_entity("Account"), _account_columns(version=7), None)

    def observe(uow: UnitOfWork) -> tuple[ObservedStateKey, ObservedStateKey]:
        earlier = retain_evidence(model, first_read, ledger=uow)[0].observation
        later = retain_evidence(model, second_read, ledger=uow)[0].observation
        assert earlier is not None
        assert later is not None
        assert uow.retained_for(earlier.key) is earlier
        assert uow.retained_for(later.key) is later
        return earlier.key, later.key

    earlier_key, later_key = _in_transaction(model, observe)
    assert earlier_key != later_key
    assert isinstance(earlier_key, VersionedStateKey)
    assert isinstance(later_key, VersionedStateKey)
    assert (earlier_key.object, earlier_key.version) == (
        corpus_object_key("Account", ("id", 1)),
        4,
    )
    assert later_key.version == 7


def test_every_observed_row_retains_its_own_evidence() -> None:
    # One find observes the root and every attached level, so the collector holds
    # more than one row and each retains independently, under its own projection.
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Account"), _account_columns(id_=1, version=4), None)
    observations.observe_row(1, corpus_entity("Account"), _account_columns(id_=2, version=7), None)
    hints = _standalone(_accepted("account"), observations)
    assert [hint.object_key for hint in hints.values()] == [
        corpus_object_key("Account", ("id", 1)),
        corpus_object_key("Account", ("id", 2)),
    ]
    assert [
        hint.observation.evidence for hint in hints.values() if hint.observation is not None
    ] == [VersionObservation(observed_version=4), VersionObservation(observed_version=7)]


def test_two_projections_of_one_state_share_one_retained_observation() -> None:
    # A graph alias reaches one row through two positions. Both hints answer the
    # identical claim, which is what makes a shared node's evidence one claim
    # rather than two that could be spent independently.
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Account"), _account_columns(), None)
    observations.observe_row(1, corpus_entity("Account"), _account_columns(), None)
    hints = _standalone(_accepted("account"), observations)
    assert hints[0].observation is hints[1].observation


# --------------------------------------------------------------------------- #
# Participation: what a read stamps on the values it produced.                #
# --------------------------------------------------------------------------- #
def test_a_standalone_read_stamps_no_participation() -> None:
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Account"), _account_columns(), None)
    hint = _hint(_accepted("account"), observations)
    assert hint.participation is None
    assert hint.observation is not None
    assert hint.observation.participation is None


def test_a_participating_read_stamps_its_own_unit_of_works_participation() -> None:
    model = _accepted("account")
    observations = ObservedRows()
    observations.observe_row(0, corpus_entity("Account"), _account_columns(), None)

    def observe(uow: UnitOfWork) -> bool:
        hint = retain_evidence(model, observations, ledger=uow)[0]
        assert hint.observation is not None
        return (
            hint.participation is uow.participation
            and hint.observation.participation is uow.participation
        )

    assert _in_transaction(model, observe)
