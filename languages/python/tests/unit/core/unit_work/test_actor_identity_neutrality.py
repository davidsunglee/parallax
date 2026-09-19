"""Actor Identity is audit-neutral throughout write planning and lowering."""

from __future__ import annotations

from decimal import Decimal

from parallax.conformance import models
from parallax.core import predicate as predicate_algebra
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import (
    ActorIdentity,
    BufferItem,
    Concurrency,
    DatabaseLoginActor,
    KeyedWrite,
    ObjectKey,
    PlanningRequest,
    PredecessorRow,
    PredicateSelection,
    PredicateWrite,
    SubjectActor,
    TemporalObservation,
    TransactionInstant,
    VersionObservation,
    WriteObservation,
    WritePlan,
    object_key,
)
from parallax.snapshot.handle import build_write_planner, stream_lowered
from tests._support.clock_probes import inert_instant, instant_at
from tests._support.planner_probes import observed_buffer

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_WALLET = _MODELS["wallet"]
_BALANCE = _MODELS["balance"]

_SUBJECT = SubjectActor("subject-alpha")
_LOGIN = DatabaseLoginActor("runtime-login")


def _plan_under(
    actor: ActorIdentity,
    buffer: list[BufferItem | KeyedWrite | PredicateWrite],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, WriteObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                actor_identity=actor,
                transaction_instant=tx_instant if tx_instant is not None else inert_instant(),
                concurrency=concurrency,
                buffered_writes=observed_buffer(buffer, model, observations),
            )
        )
        .plan
    )


def _statements(plan: WritePlan, model: Metamodel) -> list[LoweredStatement]:
    return [statement for _step, statement in stream_lowered(plan, model, POSTGRES)]


def _assert_neutral(
    buffer: list[BufferItem | KeyedWrite | PredicateWrite],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, WriteObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant_literal: str | None = None,
) -> None:
    subject_instant = None if tx_instant_literal is None else instant_at(tx_instant_literal)
    login_instant = None if tx_instant_literal is None else instant_at(tx_instant_literal)
    subject_plan = _plan_under(
        _SUBJECT,
        buffer,
        model,
        observations=observations,
        concurrency=concurrency,
        tx_instant=subject_instant,
    )
    login_plan = _plan_under(
        _LOGIN,
        buffer,
        model,
        observations=observations,
        concurrency=concurrency,
        tx_instant=login_instant,
    )

    assert subject_plan == login_plan
    subject_statements = _statements(subject_plan, model)
    login_statements = _statements(login_plan, model)
    assert subject_statements == login_statements

    rendered = repr(subject_plan) + "".join(
        f"{statement.sql}{statement.binds!r}" for statement in subject_statements
    )
    assert _SUBJECT.value not in rendered
    assert _LOGIN.value not in rendered


def test_a_non_temporal_insert_is_actor_neutral() -> None:
    insert = KeyedWrite(
        "insert", "Account", ({"id": 1, "owner": "Ada", "balance": Decimal("5.00")},)
    )
    _assert_neutral([insert], _ACCOUNT)


def test_a_versioned_update_with_an_observation_is_actor_neutral() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("175.00")},))
    key = object_key(update, _ACCOUNT)
    assert key is not None
    _assert_neutral(
        [update],
        _ACCOUNT,
        observations={key: VersionObservation(observed_version=3)},
        concurrency="optimistic",
    )


def test_a_keyed_delete_is_actor_neutral() -> None:
    _assert_neutral([KeyedWrite("delete", "Wallet", ({"id": 1}, {"id": 2}))], _WALLET)


def test_a_readless_predicate_write_is_actor_neutral() -> None:
    predicate = PredicateWrite(
        "delete",
        PredicateSelection(
            "Wallet", predicate_algebra.Comparison("lessThan", "Wallet.balance", "200.00")
        ),
    )
    _assert_neutral([predicate], _WALLET)


def test_a_batched_insert_run_is_actor_neutral() -> None:
    buffer: list[BufferItem | KeyedWrite | PredicateWrite] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1")},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": Decimal("2")},)),
    ]
    _assert_neutral(buffer, _WALLET)


def test_a_temporal_close_and_chain_is_actor_neutral() -> None:
    update = KeyedWrite(
        "update", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("175.00")},)
    )
    key = object_key(update, _BALANCE)
    assert key is not None
    observation = TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": 1,
                "acctNum": "A",
                "value": Decimal("100.00"),
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            }
        )
    )
    _assert_neutral(
        [update],
        _BALANCE,
        observations={key: observation},
        tx_instant_literal="2024-06-01T00:00:00+00:00",
    )
