"""Write-observation retention unit tests (`parallax.core._execution._retention`).

Drives :class:`RecordedProjections` and :func:`defer_read_evidence` directly, off
hand-written rows admitted as judged positional Entity State rather than through
a `TxnContext.find`: which of the two mutually exclusive branches a row takes (a
versioned row's observed version, a temporal row's whole predecessor milestone),
which rows retain no evidence at all, what the retained state is keyed by, and
what a hint carries when there is no state behind it.

Everything a collector holds is asserted through the Read Evidence the retention
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
from typing import Any, cast

import pytest

from parallax.conformance import models
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import inheritance, opt_lock, temporal_read
from parallax.core._execution._page_origins import ReadEvidenceCollector
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._retention import (
    ReadEvidenceByProjection,
    RecordedProjections,
    defer_read_evidence,
)
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.instructions import prepare_typed_write
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityIdentity
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.read_delivery._page import (
    ROOT_LEVEL,
    PageBuilder,
    ViewSchema,
    page_rows,
    state_for,
)
from parallax.core.temporal_read import Edge, Pin
from parallax.core.unit_work import (
    AdmittedWrite,
    KeyedWriteInstruction,
    ReadEvidence,
    RetainedObservation,
    TransactionSettings,
    UnitOfWork,
    buffered_write,
)
from parallax.core.write_plan import (
    ObjectStateKey,
    TemporalObservation,
    VersionObservation,
    object_state_key_from_observation,
)
from parallax.core.write_plan.keys import TemporalObjectStateKey, VersionedObjectStateKey
from tests._support.planner_probes import NO_COUNTED_STEPS, NO_ROW_READS, TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_entity, corpus_object_key
from tests.unit._judged_evidence_support import judged_evidence
from tests.unit._prepared_read_support import bound_read, compiled_read, result_row

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


def _accepted(model_name: str) -> AcceptedMetamodel:
    return _MODELS[model_name]


def _account_columns(*, id_: int = 1, version: int = 4) -> Mapping[str, object]:
    return {"id": id_, "owner": "Ada", "balance": Decimal("5.00"), "version": version}


# The state every `_balance_columns` row observed: `Balance` is
# Transaction-Time-only, so its milestone is that one axis's from-instant.
_BALANCE_STATE = TemporalObjectStateKey(
    corpus_object_key("Balance", ("id", 1)), Edge(tx_time=_TX_START)
)


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


def _unit_of_work(model: AcceptedMetamodel) -> UnitOfWork:
    planner = build_write_planner(model)
    return UnitOfWork(
        lifetime=TxnAttemptLifetime(),
        settings=TransactionSettings(),
        clock=FixedClock(_FIXED),
        meta=model,
        execute_write_steps=SimulatedWriteSteps(planner.payloads, model, POSTGRES),
        execute_counted_step=NO_COUNTED_STEPS,
        acquire_rows=NO_ROW_READS,
        planner=planner,
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(model).required_key,
    )


def _in_transaction[T](model: AcceptedMetamodel, body: Callable[[UnitOfWork], T]) -> T:
    """Run ``body`` in a unit of work over ``model``."""
    return body(_unit_of_work(model))


def _retained(
    model: AcceptedMetamodel, entity: EntityIdentity, *rows: Mapping[str, object]
) -> ReadEvidenceByProjection:
    """What one participating read of ``rows`` retains, in a unit of work of its own."""
    return judged_evidence(model, entity, *rows, evidence_context=_unit_of_work(model))


def _hint(
    model: AcceptedMetamodel,
    entity: EntityIdentity,
    columns: Mapping[str, object],
    document: object | None = None,
) -> ReadEvidence:
    """The hint one participating read retains for one row."""
    return judged_evidence(
        model, entity, columns, document=document, evidence_context=_unit_of_work(model)
    )[0]


# --------------------------------------------------------------------------- #
# What the deferred sources hold before and after resolving.                  #
# --------------------------------------------------------------------------- #
def test_a_collector_that_observed_nothing_retains_no_sources() -> None:
    # A read that materialized no row — or whose every row was non-hydrating —
    # hands the retention an empty collector, and every value it publishes
    # carries no hint rather than a hint over nothing.
    assert _retained(_accepted("account"), corpus_entity("Account")) == {}


def test_deferred_sources_release_callbacks_after_resolving_every_origin() -> None:
    model = _accepted("orders")
    entity = corpus_entity("Order")
    observations = RecordedProjections()
    observations.observe_projection(0, entity, None)
    sources = defer_read_evidence(
        model,
        observations,
        lambda _node: None,
        lambda _node: entity,
        lambda _node: 1,
        evidence_context=_unit_of_work(model),
        pin=Pin(),
    )

    assert sources[0].object_key == corpus_object_key("Order", ("id", 1))
    with pytest.raises(KeyError):
        sources[1]
    with pytest.raises(RuntimeError, match="already resolved"):
        cast("Any", sources)._admitted(0)


def test_deferred_sources_report_a_reached_projection_with_no_admissible_state_as_absent() -> None:
    model = _accepted("orders")
    unknown = EntityIdentity("parallax.compatibility", "Unknown")
    observations = RecordedProjections()
    observations.observe_projection(0, unknown, None)
    sources = defer_read_evidence(
        model,
        observations,
        lambda _node: None,
        lambda _node: unknown,
        lambda _node: 1,
        evidence_context=_unit_of_work(model),
        pin=Pin(),
    )

    with pytest.raises(KeyError):
        sources[0]


def _deposit_rate_columns() -> Mapping[str, object]:
    return {
        "id": 1,
        "amount": Decimal("2.50"),
        "grade": "A",
        "from_z": _VALID_START,
        "thru_z": _INFINITY,
        "in_z": _RATE_TX_START,
        "out_z": _INFINITY,
    }


def test_resolving_evidence_again_repeats_no_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    derived: list[ObjectStateKey] = []

    def counted(*args: Any) -> ObjectStateKey:
        derived.append(object_state_key_from_observation(*args))
        return derived[-1]

    monkeypatch.setattr(
        "parallax.core._execution._retention.object_state_key_from_observation", counted
    )
    sources = _retained(_accepted("rate"), corpus_entity("DepositRate"), _deposit_rate_columns())
    origin = sources[0]
    assert sources[0] is origin
    first = origin.observation
    assert first is not None
    assert origin.observation is first
    assert origin.object_key == corpus_object_key("DepositRate", ("id", 1))
    assert derived == [first.key]


def test_deferred_sources_release_the_family_owners_once_every_origin_resolves() -> None:
    model = _accepted("rate")
    sources = cast(
        "Any",
        _retained(
            model,
            corpus_entity("DepositRate"),
            _deposit_rate_columns(),
            {**_deposit_rate_columns(), "id": 2},
        ),
    )
    assert sources._families is inheritance.view(model)
    assert sources._keys is opt_lock.view(model)
    assert sources._temporal is temporal_read.view(model)
    sources[0]
    assert sources._temporal is temporal_read.view(model)
    sources[1]
    assert (sources._families, sources._keys, sources._temporal) == (None, None, None)


# --------------------------------------------------------------------------- #
# The two mutually exclusive retention branches.                              #
# --------------------------------------------------------------------------- #
def test_a_versioned_row_retains_its_observed_version() -> None:
    hint = _hint(_accepted("account"), corpus_entity("Account"), _account_columns())
    assert hint.observation is not None
    assert hint.observation.evidence == VersionObservation(observed_version=4)
    assert hint.observation.key == VersionedObjectStateKey(
        corpus_object_key("Account", ("id", 1)), 4
    )


def test_a_row_that_is_neither_versioned_nor_temporal_retains_no_state() -> None:
    # An unversioned Non-Temporal row observes no state at all, so its hint
    # carries the object and the participation and nothing else.
    hint = _hint(_accepted("orders"), corpus_entity("Order"), {"id": 1, "customer_id": 2})
    assert hint.observation is None
    assert hint.entity == corpus_entity("Order")
    assert hint.object_key == corpus_object_key("Order", ("id", 1))


def test_a_temporal_row_retains_its_whole_predecessor_milestone() -> None:
    # The Predecessor Row is COMPLETE — every applicable member, not just the
    # bounds — because a chained successor carries forward members the authored
    # mutation never mentioned.
    hint = _hint(_accepted("balance"), corpus_entity("Balance"), _balance_columns())
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


def _voyage_members() -> dict[str, object]:
    return {
        "id": 7,
        "title": "Northbound",
        "crew": 12,
        "txStart": _TX_START,
        "txEnd": _INFINITY,
        "manifest": {"cargo": "grain"},
        "legs": ({"port": "Oslo"}, {"port": "Bergen"}),
    }


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(nested) for key, nested in cast("Mapping[str, object]", value).items()}
    if isinstance(value, tuple):
        return tuple(_plain(nested) for nested in cast("tuple[object, ...]", value))
    return value


def test_a_temporal_row_retains_its_judged_state_by_declared_name() -> None:
    # The judged positional Entity State a real find's Page owns is read by
    # declared name, and Voyage's storage names differ from its declared ones
    # (`in_z` / `txStart`). The object key, the observed state, every
    # predecessor member (value-object occurrences included), and the retained
    # document all come from that one state.
    hint = _hint(
        _accepted("document-layout"), corpus_entity("Voyage"), _voyage_columns(), _VOYAGE_DOCUMENT
    )

    assert hint.object_key == corpus_object_key("Voyage", ("id", 7))
    assert hint.observation is not None
    observation = hint.observation.evidence
    assert isinstance(observation, TemporalObservation)
    assert {"manifest", "legs"} <= observation.predecessor.members.keys()
    assert _plain(dict(observation.predecessor.members)) == _voyage_members()
    assert observation.predecessor.member("txStart") == _TX_START
    assert hint.observation.key == TemporalObjectStateKey(
        corpus_object_key("Voyage", ("id", 7)), Edge(tx_time=_TX_START)
    )
    # The Structured Column rides BESIDE the members.
    assert observation.predecessor.document == _VOYAGE_DOCUMENT
    assert "charterCode" not in observation.predecessor.members


def test_a_retained_predecessor_document_is_the_one_the_read_transferred() -> None:
    # The dialect transfers the decoded document to the read, so retention keeps
    # that document itself, host containers and all, rather than a frozen copy
    # of it (`m-write-plan` "Predecessor Row").
    document: dict[str, object] = {
        "title": "Northbound",
        "manifest": {"cargo": "grain", "sealNumber": "S-4021"},
        "legs": [{"port": "Oslo"}],
    }
    hint = _hint(_accepted("document-layout"), corpus_entity("Voyage"), _voyage_columns(), document)
    assert hint.observation is not None
    observation = hint.observation.evidence
    assert isinstance(observation, TemporalObservation)
    assert observation.predecessor.document is document


# --------------------------------------------------------------------------- #
# What the retained evidence is keyed by.                                     #
# --------------------------------------------------------------------------- #
def test_two_reads_of_one_milestone_at_different_pins_retain_one_state() -> None:
    # The property that makes an Edge usable as a key without an identity map:
    # an Edge is a VALUE, so two independent reads of one milestone — here a
    # latest read and a read pinned at a past instant that still resolves to it —
    # derive equal coordinates and therefore name the SAME observed state. Within
    # a transaction the second read answers the FIRST read's own evidence, so a
    # value still held from the first read is not superseded by the second.
    model = _accepted("balance")
    balance = corpus_entity("Balance")

    def observe(uow: UnitOfWork) -> tuple[RetainedObservation, RetainedObservation]:
        first = judged_evidence(model, balance, _balance_columns(), evidence_context=uow)[
            0
        ].observation
        second = judged_evidence(model, balance, _balance_columns(), evidence_context=uow)[
            0
        ].observation
        assert first is not None
        assert second is not None
        return first, second

    first, second = _in_transaction(model, observe)
    assert first is second
    assert first.key == _BALANCE_STATE


def test_two_observed_versions_of_one_object_are_distinct_states() -> None:
    # The evidence context admits several observed states of one Object Key: the version is
    # part of the address, so a read that saw version 4 and a later read that saw
    # version 7 hold evidence about two different states rather than overwriting
    # one slot.
    model = _accepted("account")
    account = corpus_entity("Account")

    def observe(uow: UnitOfWork) -> tuple[ObjectStateKey, ObjectStateKey]:
        first_read = judged_evidence(
            model, account, _account_columns(version=4), evidence_context=uow
        )
        second_read = judged_evidence(
            model, account, _account_columns(version=7), evidence_context=uow
        )
        earlier = first_read[0].observation
        later = second_read[0].observation
        assert earlier is not None
        assert later is not None
        reread = judged_evidence(model, account, _account_columns(version=4), evidence_context=uow)
        assert reread[0].observation is earlier
        return earlier.key, later.key

    earlier_key, later_key = _in_transaction(model, observe)
    assert earlier_key != later_key
    assert isinstance(earlier_key, VersionedObjectStateKey)
    assert isinstance(later_key, VersionedObjectStateKey)
    assert (earlier_key.object, earlier_key.version) == (
        corpus_object_key("Account", ("id", 1)),
        4,
    )
    assert later_key.version == 7


def test_every_observed_row_retains_its_own_evidence() -> None:
    # One find observes the root and every attached level, so the collector holds
    # more than one row and each retains independently, under its own projection.
    sources = _retained(
        _accepted("account"),
        corpus_entity("Account"),
        _account_columns(id_=1, version=4),
        _account_columns(id_=2, version=7),
    )
    hints = [sources[0], sources[1]]
    assert [hint.object_key for hint in hints] == [
        corpus_object_key("Account", ("id", 1)),
        corpus_object_key("Account", ("id", 2)),
    ]
    assert [hint.observation.evidence for hint in hints if hint.observation is not None] == [
        VersionObservation(observed_version=4),
        VersionObservation(observed_version=7),
    ]


def test_two_projections_of_one_state_share_one_retained_observation() -> None:
    # A graph alias reaches one row through two positions. Both hints answer the
    # identical claim, which is what makes a shared node's evidence one claim
    # rather than two that could be spent independently.
    model = _accepted("account")

    def observe(uow: UnitOfWork) -> tuple[ReadEvidence, ReadEvidence]:
        row = _account_columns()
        sources = judged_evidence(model, corpus_entity("Account"), row, row, evidence_context=uow)
        return sources[0], sources[1]

    first, second = _in_transaction(model, observe)
    assert first.observation is not None
    assert first.observation is second.observation


def test_two_judged_projections_of_one_temporal_state_share_one_retained_observation() -> None:
    # The same sharing over judged positional state: two projections of one
    # Balance milestone, each viewed by declared name, answer one retained
    # observation and one predecessor, keyed by the declared-name coordinate
    # (`txStart` over storage `in_z`).
    model = _accepted("balance")

    def observe(uow: UnitOfWork) -> tuple[ReadEvidence, ReadEvidence]:
        row = _balance_columns()
        sources = judged_evidence(model, corpus_entity("Balance"), row, row, evidence_context=uow)
        return sources[0], sources[1]

    first, second = _in_transaction(model, observe)
    assert first.observation is not None
    assert first.observation is second.observation
    assert first.observation.key == _BALANCE_STATE
    observation = first.observation.evidence
    assert isinstance(observation, TemporalObservation)
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "acctNum": "A-1",
        "value": Decimal("5.00"),
        "txStart": _TX_START,
        "txEnd": _INFINITY,
    }


def test_evidence_is_keyed_by_the_rows_own_entity_through_inherited_members() -> None:
    # `DepositRate` is a concrete subtype of the bitemporal root `Rate`, whose own
    # declaration owns the primary key and both axes. The key still names the
    # subtype, because that is the class a developer's later `tx.amend(copy)`
    # carries (`m-unit-work` `KeyedWriteInstruction.entity`), and the declared-name view
    # resolves each inherited member at its canonical position (`from_z` /
    # `validStart`, `in_z` / `txStart`).
    columns: Mapping[str, object] = {
        "id": 1,
        "amount": Decimal("2.50"),
        "grade": "A",
        "from_z": _VALID_START,
        "thru_z": _INFINITY,
        "in_z": _RATE_TX_START,
        "out_z": _INFINITY,
    }
    hint = _hint(_accepted("rate"), corpus_entity("DepositRate"), columns)
    assert hint.object_key == corpus_object_key("DepositRate", ("id", 1))
    assert hint.observation is not None
    assert hint.observation.key == TemporalObjectStateKey(
        corpus_object_key("DepositRate", ("id", 1)),
        Edge(tx_time=_RATE_TX_START, valid_time=_VALID_START),
    )
    observation = hint.observation.evidence
    assert isinstance(observation, TemporalObservation)
    assert observation.predecessor.member("grade") == "A"
    assert observation.predecessor.member("validEnd") is _INFINITY


def _instrument_root(builder: PageBuilder, tag: str, price: Decimal) -> int:
    """One row of the Instrument family read, tagged ``tag``, converted as a root
    provider row is, every concrete's own subtype member stored null."""
    stored: dict[str, object] = {
        "id": 1,
        "kind": tag,
        "price": price,
        "coupon": None,
        "ticker": None,
        "from_z": _VALID_START,
        "thru_z": _INFINITY,
        "in_z": _TX_START,
        "out_z": _INFINITY,
    }
    model = _accepted("instrument")
    row = result_row(compiled_read(model, "Instrument").result_contract, stored)
    ref, _resolved, _document, _variant = bound_read(model, "Instrument").convert_row(
        row, builder, source=ROOT_LEVEL
    )
    return ref


def test_a_root_retains_evidence_from_its_own_judged_state_beside_an_equal_sibling() -> None:
    # Two roots of one Page claim one Logical Key under sibling concretes of a
    # table-per-hierarchy family, and their stored values are equal position by
    # position. The witness includes the resolved concrete, so they are two
    # witnesses with two judged states, and each root's evidence is read from
    # the state judged for its own row: the Stock's retained `price` is the very
    # value its own row carried, not the Bond's equal one.
    model = _accepted("instrument")
    bond_price, stock_price = Decimal("2.50"), Decimal("2.50")
    builder = PageBuilder(ViewSchema.of())
    bond = _instrument_root(builder, "bond", bond_price)
    stock = _instrument_root(builder, "stock", stock_price)
    page = builder.finish((bond, stock), Pin())
    assert page_rows(page).logical_ids[bond] == page_rows(page).logical_ids[stock]
    assert page_rows(page).witnesses[bond] == page_rows(page).witnesses[stock]
    state_for(page_rows(page), bond)
    state_for(page_rows(page), stock)
    observations = ReadEvidenceCollector(model, evidence_context=_unit_of_work(model))
    observations.observe_projection(bond, corpus_entity("Bond"), None)
    observations.observe_projection(stock, corpus_entity("Stock"), None)
    # Page judgment and Read Evidence retention meet only inside the read that
    # owns both, so the collector's origin step is called directly.
    sources = observations.origins_for(page)

    for projection, price in ((bond, bond_price), (stock, stock_price)):
        observation = sources[projection].observation
        assert observation is not None
        evidence = observation.evidence
        assert isinstance(evidence, TemporalObservation)
        assert evidence.predecessor.member("price") is price


# --------------------------------------------------------------------------- #
# Participation: what a read stamps on the values it produced.                #
# --------------------------------------------------------------------------- #
def test_a_participating_read_stamps_its_own_unit_of_works_participation() -> None:
    model = _accepted("account")

    def observe(uow: UnitOfWork) -> bool:
        hint = judged_evidence(
            model, corpus_entity("Account"), _account_columns(), evidence_context=uow
        )[0]
        assert hint.observation is not None
        return (
            hint.participation is uow.participation
            and hint.observation.participation is uow.participation
        )

    assert _in_transaction(model, observe)


# --------------------------------------------------------------------------- #
# Freshness: evidence is judged against the state its rows had when read.     #
# --------------------------------------------------------------------------- #
def _balance_update(model: AcceptedMetamodel, hint: ReadEvidence) -> AdmittedWrite:
    instruction = prepare_typed_write(
        KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("6.00")},)), model
    )
    assert hint.observation is not None
    return buffered_write(
        instruction,
        hint.observation,
    )


def test_evidence_resolved_after_an_own_change_to_its_state_is_invalidated() -> None:
    model = _accepted("balance")
    entity = corpus_entity("Balance")

    def observe(uow: UnitOfWork) -> None:
        unsubmitted = judged_evidence(model, entity, _balance_columns(), evidence_context=uow)
        unaffected = judged_evidence(model, entity, _balance_columns(id_=2), evidence_context=uow)
        writer = judged_evidence(model, entity, _balance_columns(), evidence_context=uow)[0]
        uow.buffer(_balance_update(model, writer))
        uow.read(lambda: None)
        stale = unsubmitted[0].observation
        assert stale is not None
        assert stale.invalidated
        assert stale is not writer.observation
        other = unaffected[0].observation
        assert other is not None and not other.invalidated
        fresh = judged_evidence(model, entity, _balance_columns(), evidence_context=uow)[
            0
        ].observation
        assert fresh is not None and not fresh.invalidated

    _in_transaction(model, observe)


def test_an_own_change_invalidates_a_built_observation_no_write_used() -> None:
    model = _accepted("balance")
    entity = corpus_entity("Balance")

    def observe(uow: UnitOfWork) -> None:
        built = judged_evidence(model, entity, _balance_columns(), evidence_context=uow)[
            0
        ].observation
        assert built is not None
        writer = judged_evidence(model, entity, _balance_columns(), evidence_context=uow)[0]
        assert writer.observation is built  # one state, one shared observation
        uow.buffer(_balance_update(model, writer))
        assert not built.invalidated  # buffered, not yet completed
        uow.read(lambda: None)
        assert built.invalidated

    _in_transaction(model, observe)
