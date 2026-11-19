"""The routes a policy's acquisitions try, their shares of one budget, and which
failures move an acquisition on to the next route."""

from __future__ import annotations

from typing import Any

import pytest

from parallax.core.internal.db_port._runtime._route_plan import RoutePlan


@pytest.mark.parametrize(
    ("policy", "has_reader", "steps"),
    [
        ("writer_only", False, [("writer", 1.0)]),
        ("writer_only", True, [("writer", 1.0)]),
        ("reader_only", True, [("reader", 1.0)]),
        ("reader_preferred", True, [("reader", 0.5), ("writer", 1.0)]),
    ],
)
def test_each_policy_plans_its_routes_and_their_shares_of_the_budget(
    policy: Any, has_reader: bool, steps: list[tuple[str, float]]
) -> None:
    plan = RoutePlan.for_policy(policy, has_reader=has_reader)
    assert [(step.route, step.share) for step in plan.steps] == steps


@pytest.mark.parametrize(
    ("policy", "has_reader"),
    [("reader_only", False), ("reader_preferred", False)],
)
def test_a_policy_with_no_route_to_serve_it_is_refused_by_the_plan(
    policy: Any, has_reader: bool
) -> None:
    with pytest.raises(ValueError, match="does not serve"):
        RoutePlan.for_policy(policy, has_reader=has_reader)


@pytest.mark.parametrize(
    ("failure", "fallback"),
    [
        ("unavailable", "unavailable"),
        ("connection_lost", "connection_lost"),
        ("timeout", None),
        ("queue_rejected", None),
        ("closed", None),
        ("preparation_failed", None),
        ("authorization_failed", None),
        ("authentication_refused", None),
        ("credentials_refused", None),
    ],
)
def test_only_an_unreachable_route_or_a_lost_setup_connection_falls_back(
    failure: Any, fallback: str | None
) -> None:
    assert RoutePlan.falls_back_on(failure) == fallback
