from __future__ import annotations

from contextlib import closing
from typing import Any

import pytest

from tests._support.aws_run import (
    _RESET_STATE,  # pyright: ignore[reportPrivateUsage] - the cloud readiness query is graded on a local server
)
from tests._support.bindings import TEST_BINDING, TEST_SCHEMA
from tests._support.routed_reads import SEEDED_MODEL, seeded_fixtures

_SCHEMAS = ["public", TEST_SCHEMA]


def test_reset_visibility_distinguishes_recreated_tables_with_the_same_names(
    profile_run: Any,
) -> None:
    profile_run.reset(SEEDED_MODEL, seeded_fixtures(), TEST_BINDING)
    with closing(profile_run.control()) as first, closing(profile_run.control()) as second:
        previous = first.execute(_RESET_STATE, [_SCHEMAS])
        assert second.execute(_RESET_STATE, [_SCHEMAS]) == previous

        profile_run.reset(SEEDED_MODEL, seeded_fixtures(), TEST_BINDING)

        current = first.execute(_RESET_STATE, [_SCHEMAS])
        assert current != previous
        assert second.execute(_RESET_STATE, [_SCHEMAS]) == current


@pytest.mark.parametrize("grant", ["select on px.rv_ledger", "usage on schema px"])
def test_reset_visibility_distinguishes_incomplete_grants(profile_run: Any, grant: str) -> None:
    profile_run.reset(SEEDED_MODEL, seeded_fixtures(), TEST_BINDING)
    with closing(profile_run.control()) as control:
        complete = control.execute(_RESET_STATE, [_SCHEMAS])
        role = control.dialect.quote(profile_run.default_role.name)
        control.execute_write(f"revoke {grant} from {role}", [])
        assert control.execute(_RESET_STATE, [_SCHEMAS]) != complete
