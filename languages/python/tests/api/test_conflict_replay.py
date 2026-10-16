"""Recoverable-conflict replay through the shipped public surface
(`spec/execution.md`), against a real Postgres: the usage guide's own story, in
which a credit another writer overtook is replayed from a fresh read, and
writers contending for one row, every one of which commits within the default
retry bound.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any

from parallax.conformance import conflict_replay_stories, engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.execution import TxnOptions
from parallax.snapshot import TxnContext, connect

_WRITERS = 8


def _seeded(profile_run: Any) -> None:
    case = load_case(default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml")
    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )


def test_the_conflict_replay_usage_guide_story_runs_against_a_real_database(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    report = (
        conflict_replay_stories.a_credit_overtaken_by_another_writer_is_replayed_from_a_fresh_read(
            profile_run.port, MODELS["account"]
        )
    )
    assert report.balances_read == (Decimal("250.00"), Decimal("999.00"))
    assert report.balance == Decimal("1024.00")


def test_writers_contending_for_one_row_all_commit_within_the_default_bound(
    profile_run: Any,
) -> None:
    # Each writer credits the row once, and every first attempt reads before
    # any writes, so all but one first attempt conflict. A writer's attempt
    # fails only when another writer committed between that attempt's read and
    # its write, and its next attempt reads after that commit, so every failure
    # is a distinct commit of another writer: no writer needs more attempts than
    # there are writers, which the default bound admits.
    _seeded(profile_run)
    query = Account.where(Account.id == 2)
    failures: list[BaseException] = []
    attempts: list[int] = []
    lock = threading.Lock()

    with connect(profile_run.port, MODELS["account"]) as database:
        db = database.using_database_login()
        read_together = threading.Barrier(_WRITERS)

        def writer() -> None:
            made = 0

            def credit(tx: TxnContext) -> None:
                nonlocal made
                made += 1
                account = tx.find(query).result()
                if made == 1:
                    read_together.wait(timeout=30.0)
                tx.amend(account.edit(balance=account.balance + Decimal("1.00")))

            try:
                db.transact(credit)
            except BaseException as failure:  # reported on the main thread below
                with lock:
                    failures.append(failure)
            with lock:
                attempts.append(made)

        threads = [threading.Thread(target=writer) for _ in range(_WRITERS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60.0)
        assert not any(thread.is_alive() for thread in threads)
        assert failures == []
        final = db.find(query).result()

    assert final.balance == Decimal("250.00") + _WRITERS
    assert final.version == 1 + _WRITERS
    assert max(attempts) <= _WRITERS <= TxnOptions().max_retries + 1
    assert sum(attempts) >= 2 * _WRITERS - 1
