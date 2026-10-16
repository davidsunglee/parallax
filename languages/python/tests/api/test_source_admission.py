"""Current-attempt source admission through the shipped public surface
(`spec/execution.md`), against a real Postgres: the usage guide's own story, in
which a value a read-only transaction published licenses no later source write
and states its version through `amend_if` instead.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from parallax.conformance import engine, provision, source_admission_stories
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS


def test_the_source_admission_usage_guide_story_runs_against_a_real_database(
    profile_run: Any,
) -> None:
    case = load_case(default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml")
    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )
    report = source_admission_stories.a_reviewed_value_is_written_under_the_version_its_review_saw(
        profile_run.port, MODELS["account"]
    )
    assert report.source_write_refused
    assert report.balance == Decimal("275.00")
