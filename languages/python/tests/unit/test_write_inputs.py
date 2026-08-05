"""Observation recording unit tests (`parallax.snapshot.handle._write_inputs`).

Drives :class:`ReadObservations` and :func:`record_observations` directly, off
hand-written physical-column rows rather than through a `Transaction.find`: which
of the two mutually exclusive branches a row takes (a versioned row's observed
version, a temporal row's whole predecessor milestone), which rows record
nothing, what the recorded key is keyed by, and the Transaction-Time Basis the
observing read's own pin decides.

The whole-choreography proofs — a real find licensing or refusing a later write —
stay in `test_transaction_reads.py`; what lives here is the seam itself.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from decimal import Decimal

from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.conformance import models
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.temporal_read import LATEST, Pin
from parallax.core.unit_work import (
    HISTORICAL_PINNED,
    LATEST_PINNED,
    FixedClock,
    ObjectKey,
    TemporalObservation,
    TransactionSettings,
    UnitOfWork,
    VersionObservation,
    WriteObservation,
    run_unit_of_work,
)
from parallax.snapshot.handle import build_write_planner
from parallax.snapshot.handle._write_inputs import ReadObservations, record_observations

_MODELS = models.load_models()
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_HISTORICAL = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_INFINITY = "infinity"
_LATEST_PIN = Pin(tx_time=LATEST)


def _accepted(model_name: str) -> AcceptedMetamodel:
    return models.accepted_model(_MODELS[model_name])


def _account_columns(*, id_: int = 1, version: int | None = 4) -> Mapping[str, object]:
    columns: dict[str, object] = {"id": id_, "owner": "Ada", "balance": Decimal("5.00")}
    if version is not None:
        columns["version"] = version
    return columns


def _balance_columns(*, id_: int = 1) -> Mapping[str, object]:
    return {
        "bal_id": id_,
        "acct_num": "A-1",
        "val": Decimal("5.00"),
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": _INFINITY,
    }


def _recorded(
    model: AcceptedMetamodel,
    observations: ReadObservations,
    key: ObjectKey,
    *,
    pin: Pin = _LATEST_PIN,
) -> WriteObservation | None:
    """What ``key`` observed after ``observations`` is recorded under ``pin``."""

    def observe(uow: UnitOfWork) -> WriteObservation | None:
        record_observations(uow, model, observations, pin)
        return uow.observation_for(key)

    return run_unit_of_work(
        observe,
        settings=TransactionSettings(),
        clock=FixedClock(_FIXED),
        meta=model,
        flush_executor=lambda _plan: None,
        planner=build_write_planner(model),
        subject_identity=TEST_SUBJECT_IDENTITY,
    )


# --------------------------------------------------------------------------- #
# The collector: what it retains, and that it retains it by copy.             #
# --------------------------------------------------------------------------- #
def test_a_fresh_collector_holds_no_rows() -> None:
    assert list(ReadObservations().rows) == []


def test_the_collector_copies_the_columns_it_is_handed() -> None:
    # `find` hands over a mapping built from a row that is released immediately
    # afterwards, so the collector must own its copy: a later edit to the mapping
    # it was handed cannot reach what a write will read.
    handed: dict[str, object] = {"id": 1, "owner": "Ada"}
    observations = ReadObservations()
    observations.observe_row("Account", handed, None)
    handed["owner"] = "Grace"
    handed["version"] = 9
    assert dict(observations.rows[0].columns) == {"id": 1, "owner": "Ada"}


def test_rows_accumulate_in_the_order_they_are_observed() -> None:
    observations = ReadObservations()
    observations.observe_row("Order", {"id": 1}, None)
    observations.observe_row("OrderItem", {"id": 11}, None)
    assert [row.entity for row in observations.rows] == ["Order", "OrderItem"]


# --------------------------------------------------------------------------- #
# The two mutually exclusive recording branches.                              #
# --------------------------------------------------------------------------- #
def test_a_versioned_row_records_its_observed_version() -> None:
    observations = ReadObservations()
    observations.observe_row("Account", _account_columns(), None)
    observation = _recorded(_accepted("account"), observations, ("Account", (("id", 1),)))
    assert observation == VersionObservation(observed_version=4)


def test_a_versioned_row_whose_version_column_the_projection_omitted_records_nothing() -> None:
    # The seam takes no data on faith: a row that reached it without the version
    # column it would gate on records nothing rather than observing a guess.
    observations = ReadObservations()
    observations.observe_row("Account", _account_columns(version=None), None)
    assert _recorded(_accepted("account"), observations, ("Account", (("id", 1),))) is None


def test_a_row_that_is_neither_versioned_nor_temporal_records_nothing() -> None:
    observations = ReadObservations()
    observations.observe_row("Order", {"id": 1, "customer_id": 2}, None)
    assert _recorded(_accepted("orders"), observations, ("Order", (("id", 1),))) is None


def test_a_temporal_row_records_its_whole_predecessor_milestone() -> None:
    # The Predecessor Row is COMPLETE — every applicable member, not just the
    # bounds — because a chained successor carries forward members the authored
    # mutation never mentioned.
    observations = ReadObservations()
    observations.observe_row("Balance", _balance_columns(), None)
    observation = _recorded(_accepted("balance"), observations, ("Balance", (("id", 1),)))
    assert isinstance(observation, TemporalObservation)
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "acctNum": "A-1",
        "value": Decimal("5.00"),
        "txStart": "2024-01-01T00:00:00+00:00",
        "txEnd": _INFINITY,
    }
    assert observation.predecessor.document is None


# --------------------------------------------------------------------------- #
# What the record is keyed by, and what the observing read's pin decides.     #
# --------------------------------------------------------------------------- #
def test_an_observation_is_keyed_by_the_rows_own_entity_never_its_family_root() -> None:
    # `DepositRate` is a concrete subtype of the bitemporal root `Rate`, whose own
    # declaration owns the primary key and both axes. The key still names the
    # subtype, because that is the class a developer's later `tx.update(copy)`
    # carries (`m-unit-work` `KeyedWrite.entity`).
    model = _accepted("rate")
    columns: Mapping[str, object] = {
        "id": 1,
        "amount": Decimal("2.50"),
        "grade": "A",
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": _INFINITY,
        "in_z": "2024-02-01T00:00:00+00:00",
        "out_z": _INFINITY,
    }
    observations = ReadObservations()
    observations.observe_row("DepositRate", columns, None)
    assert isinstance(
        _recorded(model, observations, ("DepositRate", (("id", 1),))), TemporalObservation
    )
    observations_again = ReadObservations()
    observations_again.observe_row("DepositRate", columns, None)
    assert _recorded(model, observations_again, ("Rate", (("id", 1),))) is None


def test_a_latest_pin_records_a_latest_pinned_basis_and_a_finite_one_records_historical() -> None:
    # The observing read's own Transaction-Time pin decides the Basis, which is
    # what a later locking-mode write consults for its historical-observation
    # license (`m-opt-lock`). An explicit `LATEST` and a finite instant are the
    # two sides of that one decision.
    model = _accepted("balance")
    latest = ReadObservations()
    latest.observe_row("Balance", _balance_columns(), None)
    at_latest = _recorded(model, latest, ("Balance", (("id", 1),)))
    assert isinstance(at_latest, TemporalObservation)
    assert at_latest.transaction_time_basis is LATEST_PINNED

    historical = ReadObservations()
    historical.observe_row("Balance", _balance_columns(), None)
    at_instant = _recorded(
        model, historical, ("Balance", (("id", 1),)), pin=Pin(tx_time=_HISTORICAL)
    )
    assert isinstance(at_instant, TemporalObservation)
    assert at_instant.transaction_time_basis is HISTORICAL_PINNED


def test_an_omitted_transaction_time_axis_is_latest_pinned_like_an_explicit_latest() -> None:
    observations = ReadObservations()
    observations.observe_row("Balance", _balance_columns(), None)
    observation = _recorded(
        _accepted("balance"), observations, ("Balance", (("id", 1),)), pin=Pin()
    )
    assert isinstance(observation, TemporalObservation)
    assert observation.transaction_time_basis is LATEST_PINNED


def test_every_observed_row_records_under_its_own_key() -> None:
    # One find observes the root and every attached level, so the collector holds
    # more than one row and each records independently.
    model = _accepted("account")
    observations = ReadObservations()
    observations.observe_row("Account", _account_columns(id_=1, version=4), None)
    observations.observe_row("Account", _account_columns(id_=2, version=7), None)

    def observe(uow: UnitOfWork) -> tuple[WriteObservation | None, WriteObservation | None]:
        record_observations(uow, model, observations, _LATEST_PIN)
        return (
            uow.observation_for(("Account", (("id", 1),))),
            uow.observation_for(("Account", (("id", 2),))),
        )

    first, second = run_unit_of_work(
        observe,
        settings=TransactionSettings(),
        clock=FixedClock(_FIXED),
        meta=model,
        flush_executor=lambda _plan: None,
        planner=build_write_planner(model),
        subject_identity=TEST_SUBJECT_IDENTITY,
    )
    assert first == VersionObservation(observed_version=4)
    assert second == VersionObservation(observed_version=7)
