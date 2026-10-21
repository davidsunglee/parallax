"""The target write family through the shipped public surface
(`spec/execution.md`), against a real Postgres: the usage guide's own stories,
in which versions a read-only review saw condition later deletions, and a row
with no revision is written through a read of the writing transaction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from parallax.conformance import engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS
from parallax.conformance.target_write_stories import (
    ClosingReport,
    an_unversioned_wallet_is_written_through_a_read_of_the_writing_transaction,
    reviewed_accounts_are_deleted_under_the_versions_their_review_saw,
)


def _reset(profile_run: Any, case_file: str) -> None:
    case = load_case(default_cases_dir() / case_file)
    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )


def test_the_reviewed_deletion_story_runs_against_a_real_database(profile_run: Any) -> None:
    _reset(
        profile_run, "m-opt-lock-041-a-stale-or-missing-target-deletion-fails-its-precondition.yaml"
    )
    report = reviewed_accounts_are_deleted_under_the_versions_their_review_saw(
        profile_run.port, MODELS["account"]
    )
    assert report == ClosingReport(closed=(3,), refused=(2,), remaining=(1, 2))


def test_the_unversioned_write_story_runs_against_a_real_database(profile_run: Any) -> None:
    _reset(profile_run, "m-opt-lock-023-unversioned-locking-fallback.yaml")
    balance = an_unversioned_wallet_is_written_through_a_read_of_the_writing_transaction(
        profile_run.port, MODELS["wallet"]
    )
    assert balance == Decimal("175.00")
