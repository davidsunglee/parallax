"""The Usage Guide's source-admission story, over a fake port.

The story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_source_admission.py` executes it against real Postgres. This is
the database-free half — the same call over a scripted port — so a snippet that
stopped compiling, or a reviewed value that started licensing its own write,
fails on the first run of the fast suite.
"""

from __future__ import annotations

from decimal import Decimal

from parallax.conformance import source_admission_stories
from parallax.conformance.class_models import MODELS
from tests._support.db_port import BeginCall, Read, ScriptedAdapter, Transact, Write, WriteCall

_ROW = {"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}


def test_the_documented_story_refuses_the_source_write_and_gates_the_conditional_one() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_ROW])),
        Transact(Write()),
        Read(rows=[{**_ROW, "balance": Decimal("275.00"), "version": 2}]),
    )
    report = source_admission_stories.a_reviewed_value_is_written_under_the_version_its_review_saw(
        port, MODELS["account"]
    )
    assert report.source_write_refused
    assert report.balance == Decimal("275.00")
    assert [call.access_mode for call in port.calls if isinstance(call, BeginCall)] == [
        "read_only",
        "read_write",
    ]
    (update,) = (call for call in port.calls if isinstance(call, WriteCall))
    assert update.sql.endswith("and version = %s")
    assert update.binds[-1] == 1


def test_the_snippet_the_usage_guide_renders_is_the_source_that_ran() -> None:
    snippet = source_admission_stories.source_admission_snippet()
    assert "db.read_only(" in snippet
    assert "except WriteEvidenceError:" in snippet
    assert "version=reviewed.version" in snippet
