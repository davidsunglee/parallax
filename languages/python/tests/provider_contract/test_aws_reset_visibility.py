from __future__ import annotations

from contextlib import closing
from typing import Any

import pytest

from tests._support.aws_run import _RESET_STATE
from tests._support.routed_reads import SEEDED_MODEL, seeded_fixtures


def test_reset_visibility_distinguishes_recreated_tables_with_the_same_names(
    profile_run: Any,
) -> None:
    profile_run.reset(SEEDED_MODEL, seeded_fixtures())
    with closing(profile_run.control()) as first, closing(profile_run.control()) as second:
        previous = first.execute(_RESET_STATE, [])
        assert second.execute(_RESET_STATE, []) == previous

        profile_run.reset(SEEDED_MODEL, seeded_fixtures())

        current = first.execute(_RESET_STATE, [])
        assert current != previous
        assert second.execute(_RESET_STATE, []) == current


@pytest.mark.parametrize("grant", ["select on rv_ledger", "usage on schema public"])
def test_reset_visibility_distinguishes_incomplete_grants(profile_run: Any, grant: str) -> None:
    profile_run.reset(SEEDED_MODEL, seeded_fixtures())
    with closing(profile_run.control()) as control:
        complete = control.execute(_RESET_STATE, [])
        role = control.dialect.quote(profile_run.default_role.name)
        control.execute_write(f"revoke {grant} from {role}", [])
        assert control.execute(_RESET_STATE, []) != complete
