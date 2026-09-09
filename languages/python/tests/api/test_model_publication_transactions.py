"""Two editions serving one connection, A then B, against real Postgres
(spec §3 *Transactions adopt per attempt*, m-api-conformance).

The Docker-free demarcation suite grades adoption over fake ports. What only a
real boundary shows is that the retained selection survives an actual
`BEGIN`, a real deadlock the loop retries, and a commit: a publication landing
while a callback runs changes nothing that callback holds, the retried attempt
adopts what is serving by then, and a joining call inherits rather than adopts.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _support.corpus import case_fixtures
from parallax.conformance import case_format, engine
from parallax.conformance.boundary_runner import TARGET_ID, fault_injecting_adapter
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.snapshot import ServingModel, connect, prepare_model
from parallax.snapshot.handle import Transaction

_CASE_ID = "m-execution-lifecycle-004"


def _seeded(profile_run: Any) -> Any:
    case = next(case for case in case_format.load_cases() if case.case_id == _CASE_ID)
    profile_run.reset(engine.load_case_metamodel(case), case_fixtures(case))
    return profile_run.port


def _editions() -> tuple[Any, Any, ServingModel]:
    a = prepare_model(MODELS["account"], edition="2026-09-a")
    b = prepare_model(MODELS["account"], edition="2026-09-b")
    return a, b, ServingModel(a)


def test_a_publication_during_a_transaction_leaves_that_transaction_on_a(
    profile_run: Any,
) -> None:
    a, b, serving = _editions()
    db = connect(_seeded(profile_run), serving)

    def body(tx: Transaction) -> tuple[str, str, Decimal]:
        before = tx.edition
        serving.publish(b, expected=a)
        # Still served under A: the read runs against the projections this
        # attempt adopted, and the stamp it reports does not move.
        account = tx.find(Account.where(Account.id == TARGET_ID)).result()
        return before, tx.edition, account.balance

    assert db.transact(body) == ("2026-09-a", "2026-09-a", Decimal("250.00"))
    # The next invocation adopts what is serving by then.
    assert db.transact(lambda tx: tx.edition) == "2026-09-b"


def test_a_retry_adopts_b_and_commits_under_it(profile_run: Any) -> None:
    a, b, serving = _editions()
    port = fault_injecting_adapter(_seeded(profile_run), fault="deadlock", persistent=False)
    db = connect(port, serving)
    seen: list[str] = []

    def body(tx: Transaction) -> str:
        seen.append(tx.edition)
        if len(seen) == 1:
            serving.publish(b, expected=a)
        account = tx.find(Account.where(Account.id == TARGET_ID)).result()
        tx.update(account.edit(balance=account.balance + Decimal("1.00")))
        return tx.edition

    # The first attempt's write meets the injected deadlock and rolls back; the
    # loop re-executes the callback on a fresh attempt, which adopts B.
    assert db.transact(body) == "2026-09-b"
    assert seen == ["2026-09-a", "2026-09-b"]
    verify = connect(profile_run.port, MODELS["account"])
    committed = verify.transact(lambda tx: tx.find(Account.where(Account.id == TARGET_ID)).result())
    assert committed.balance == Decimal("251.00")


def test_a_join_stays_on_the_outer_attempts_edition(profile_run: Any) -> None:
    a, b, serving = _editions()
    db = connect(_seeded(profile_run), serving)

    def outer(tx: Transaction) -> tuple[str, bool]:
        serving.publish(b, expected=a)
        return db.transact(lambda inner: (inner.edition, inner is tx))

    assert db.transact(outer) == ("2026-09-a", True)
    assert serving.current() is b
