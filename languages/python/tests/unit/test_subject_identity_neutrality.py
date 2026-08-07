"""Subject Identity is audit-neutral (m-unit-work "Subject Identity").

Until provenance decoration is implemented, an implementation MUST NOT inspect,
validate, retain, serialize, persist, lower, or bind the supplied Subject
Identity, and two planning calls differing only in Subject Identity MUST
produce equal Write Plans and identical emitted SQL and binds. This is
observable only from inside an implementation — no emitted statement can carry
"how many distinct Subject Identities were used" — so this suite proves it
directly: planning one flush twice under different Subject Identities and
comparing the resulting Write Plans, statements, and binds, across every
mutation shape the corpus witnesses (non-temporal insert/update/delete,
readless predicate write, batching, and a temporal close-and-chain).
"""

from __future__ import annotations

import pytest

from _support.clock_probes import inert_instant, instant_at
from _support.planner_probes import observed_buffer
from parallax.conformance import models
from parallax.core import op_algebra
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import (
    BufferItem,
    Concurrency,
    KeyedWrite,
    ObjectKey,
    PlanningRequest,
    PredecessorRow,
    PredicateSelection,
    PredicateWrite,
    SubjectIdentity,
    TemporalObservation,
    TransactionInstant,
    VersionObservation,
    WriteObservation,
    WritePlan,
    capture_subject_identity,
    object_key,
)
from parallax.snapshot.handle import build_write_planner, stream_lowered

_MODELS = models.load_models()
_ACCOUNT = models.accepted_model(_MODELS["account"])
_WALLET = models.accepted_model(_MODELS["wallet"])
_BALANCE = models.accepted_model(_MODELS["balance"])

# Two Subject Identities differing only in their opaque string — neither is
# more "real" than the other; audit-neutrality means the choice cannot matter.
_SUBJECT_A = SubjectIdentity("subject-alpha")
_SUBJECT_B = SubjectIdentity("subject-beta-differs")


def test_capturing_a_subject_identity_requires_a_nonempty_value() -> None:
    # Nonemptiness is enforced at capture (the Principal boundary), not by
    # the value type itself, which an audit-neutral plan must never inspect.
    with pytest.raises(ValueError, match="nonempty"):
        capture_subject_identity("")


def test_the_subject_identity_type_itself_performs_no_validation() -> None:
    assert SubjectIdentity("").value == ""


def _plan_under(
    subject: SubjectIdentity,
    buffer: list[BufferItem],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, WriteObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=subject,
            transaction_instant=tx_instant if tx_instant is not None else inert_instant(),
            concurrency=concurrency,
            buffered_writes=observed_buffer(buffer, model, observations),
        )
    )


def _statements(plan: WritePlan, model: Metamodel) -> list[Statement]:
    return [statement for _step, statement in stream_lowered(plan, model, POSTGRES)]


def _assert_neutral(
    buffer: list[BufferItem],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, WriteObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant_literal: str | None = None,
) -> None:
    tx_instant_a = None if tx_instant_literal is None else instant_at(tx_instant_literal)
    tx_instant_b = None if tx_instant_literal is None else instant_at(tx_instant_literal)
    plan_a = _plan_under(
        _SUBJECT_A,
        buffer,
        model,
        observations=observations,
        concurrency=concurrency,
        tx_instant=tx_instant_a,
    )
    plan_b = _plan_under(
        _SUBJECT_B,
        buffer,
        model,
        observations=observations,
        concurrency=concurrency,
        tx_instant=tx_instant_b,
    )
    assert plan_a == plan_b  # structural equality: identical Write Plans

    statements_a = _statements(plan_a, model)
    statements_b = _statements(plan_b, model)
    assert statements_a == statements_b  # identical SQL and binds

    # No literal Subject Identity value survives anywhere the plan or its
    # lowered statements can be inspected.
    rendered = repr(plan_a) + "".join(f"{s.sql}{s.binds!r}" for s in statements_a)
    assert _SUBJECT_A.value not in rendered
    assert _SUBJECT_B.value not in rendered


def test_a_non_temporal_insert_is_audit_neutral() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 1, "owner": "Ada", "balance": 5.00},))
    _assert_neutral([insert], _ACCOUNT)


def test_a_versioned_update_with_an_observation_is_audit_neutral() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00},))
    key = object_key(update, _ACCOUNT)
    assert key is not None
    _assert_neutral(
        [update],
        _ACCOUNT,
        observations={key: VersionObservation(observed_version=3)},
        concurrency="optimistic",
    )


def test_a_keyed_delete_is_audit_neutral() -> None:
    delete = KeyedWrite("delete", "Wallet", ({"id": 1}, {"id": 2}))
    _assert_neutral([delete], _WALLET)


def test_a_readless_predicate_write_is_audit_neutral() -> None:
    predicate = PredicateWrite(
        "delete",
        PredicateSelection("Wallet", op_algebra.Comparison("lessThan", "Wallet.balance", 200.00)),
    )
    _assert_neutral([predicate], _WALLET)


def test_a_batched_insert_run_is_audit_neutral() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": 2.00},)),
    ]
    _assert_neutral(buffer, _WALLET)


def test_a_temporal_close_and_chain_is_audit_neutral() -> None:
    update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "A", "value": 175.00},))
    key = object_key(update, _BALANCE)
    assert key is not None
    observation = TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": 1,
                "acctNum": "A",
                "value": 100.00,
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
