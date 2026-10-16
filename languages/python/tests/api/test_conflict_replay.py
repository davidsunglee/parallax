"""Recoverable-conflict replay through the shipped public surface
(`spec/execution.md`), against a real Postgres: the usage guide's own story, in
which a credit another writer overtook is replayed from a fresh read.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from parallax.conformance import conflict_replay_stories, engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS


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
