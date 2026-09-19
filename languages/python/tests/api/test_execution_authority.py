"""Public scoped execution under login and principal authority."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import pytest

from parallax.conformance import case_format, engine
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance.boundary_runner import TARGET_ID, fault_injecting_adapter
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.execution_lifecycle import TransactionAttemptStarted
from parallax.core.object_query import deserialize
from parallax.snapshot import connect
from parallax.snapshot.handle import ScopedDatabase, Transaction
from tests._support.corpus import case_fixtures

type _AuthorityMode = Literal["database-login", "principal"]


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def _authority_case() -> case_format.Case:
    return next(
        case for case in case_format.load_cases() if case.case_id == "m-execution-authority-001"
    )


def _target_node() -> dict[str, object]:
    target = "parallax.compatibility.Account"
    return {
        "target": target,
        "predicate": {"eq": {"attr": f"{target}.id", "value": TARGET_ID}},
    }


def _scope(root: Any, profile_run: Any, mode: _AuthorityMode) -> ScopedDatabase:
    if mode == "database-login":
        return root.using_database_login()
    return root.using_principal(_Principal("authority-api", profile_run.authorization("role-a")))


@pytest.mark.parametrize("mode", ["database-login", "principal"])
def test_every_public_execution_path_runs_under_the_selected_authority(
    profile_run: Any, mode: _AuthorityMode
) -> None:
    case = _authority_case()
    profile_run.reset(engine.load_case_metamodel(case), case_fixtures(case))
    observed = LifecycleObservation()
    adapter = fault_injecting_adapter(
        profile_run.port,
        fault="deadlock",
        persistent=False,
    )

    with connect(adapter, MODELS["account"], lifecycle_provider=observed.provider) as root:
        scoped = _scope(root, profile_run, mode)
        query = Account.where(Account.id == TARGET_ID)

        assert scoped.find(query).result().balance == Decimal("250.00")
        assert scoped.wire.find(_target_node()).result()["balance"] == "250.00"
        assert scoped.read_rows(deserialize(_target_node())).rows
        with scoped.stream(
            Account.where(Account.id >= 1).order_by(Account.id.asc()), batch_size=1
        ) as stream:
            assert [account.id for account in stream] == [1, 2, 3]

        def update(tx: Transaction) -> Decimal:
            account = tx.find(query).result()
            changed = account.edit(balance=account.balance + Decimal("1.00"))
            tx.update(changed)
            return changed.balance

        assert scoped.transact(update, max_retries=1) == Decimal("251.00")
        assert scoped.find(query).result().balance == Decimal("251.00")

    attempts = sum(
        1
        for execution in observed.roots
        for event in execution.events
        if isinstance(event, TransactionAttemptStarted)
    )
    assert attempts == 2
