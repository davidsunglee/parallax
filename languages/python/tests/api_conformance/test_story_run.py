"""API-suite write stories against real Postgres (m-api-conformance, spec §"API
Conformance Suite").

Every registered write story — the same executable functions the Usage Guide
renders and the fake-port write no-drift guard drives — executes here through
the **shipped** surface: `parallax.snapshot.connect` over the `parallax-postgres`
adapter against the real Testcontainers Postgres, inside the documented
API-conformance lane (python.md: pytest ``-m api_conformance`` under
``tests/api_conformance/``, "executing idiomatic public-API code through the
shipped `parallax-snapshot` extension and `parallax-postgres` adapter";
IMPLEMENTING.md "Continuous API Conformance Lane" step 2). Docker-backed: the
shared ``provisioner`` fixture skips with a recorded reason when Docker is
unavailable (never silently), and the ``python-database`` CI job fails on any
skip. Grading is the mirrored case's own oracle: a story returning rows must
observe its final find's `expectRows`; a writeSequence story must leave exactly
`then.tableState` behind; the boundary story must raise (the withheld value) and
leave the pre-transaction state standing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest

from conftest import case_document, case_fixtures, compare_rows
from parallax.conformance import case_format, engine
from parallax.conformance.stories import WRITE_STORIES, WriteStory
from parallax.conformance.story_models import Account
from parallax.core.dialect import POSTGRES
from parallax.snapshot import connect

pytestmark = pytest.mark.api_conformance

_CASES = {c.case_id: c for c in case_format.load_cases()}


def _final_find_expect_rows(case_id: str) -> list[dict[str, Any]]:
    """The last scenario find step's ``expectRows`` — the story's returned oracle."""
    steps = cast("list[dict[str, Any]]", case_document(_CASES[case_id])["when"]["scenario"])
    finds = [step for step in steps if "find" in step]
    assert finds, case_id
    return cast("list[dict[str, Any]]", finds[-1]["expectRows"])


def _reset_for(story: WriteStory, provisioner: Any) -> Any:
    case = _CASES[story.case_id]
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, case_fixtures(case))
    return meta


_STORY_IDS = [story.case_id for story in WRITE_STORIES]


@pytest.mark.parametrize("story", WRITE_STORIES, ids=_STORY_IDS)
def test_story_runs_through_the_shipped_surface(story: WriteStory, provisioner: Any) -> None:
    meta = _reset_for(story, provisioner)
    db = connect(provisioner.port, meta)

    if story.kind == "boundary":
        # The callback value is withheld: `db.transact` raises, and the abort
        # discarded even the force-flushed write — the fixture row stands.
        with pytest.raises(RuntimeError, match="abort"):
            story.run(db)
        snapshot = db.transact(lambda tx: tx.find(Account.where(Account.id == 1)))
        assert snapshot.result().balance == Decimal("100.00"), snapshot.results()
        return

    result = story.run(db)
    if result is not None:
        # Commit and abort stories both conclude with an observing find; its
        # rows must equal the mirrored case's final `expectRows`.
        compare_rows(
            [engine.wire_row(row) for row in result], _final_find_expect_rows(story.case_id)
        )
        return

    # A writeSequence story observes no rows; the committed table state must
    # equal the case's `then.tableState`, table for table.
    expected_state = cast(
        "dict[str, list[dict[str, Any]]]",
        case_document(_CASES[story.case_id])["then"]["tableState"],
    )
    observed_state = engine.read_table_state(provisioner.port, meta, POSTGRES)
    assert set(observed_state) >= set(expected_state), (story.case_id, observed_state)
    for table, expected_rows in expected_state.items():
        compare_rows(observed_state[table], expected_rows)
