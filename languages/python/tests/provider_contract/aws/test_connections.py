"""Connections on the deployed cluster: one login on both routes, IAM tokens
signed per host over verified TLS, retained connections reused, and on-demand
connections each newly authenticated."""

from __future__ import annotations

from typing import Any

import pytest

from parallax.core.db_port import RoutePolicy
from parallax.postgres import OnDemandOptions, PoolOptions

_IDENTITY = (
    "select pg_backend_pid(), session_user, s.ssl from pg_stat_ssl s where s.pid = pg_backend_pid()"
)


def _leases(runtime: Any, policy: RoutePolicy, times: int) -> list[tuple[object, ...]]:
    seen: list[tuple[object, ...]] = []
    for _ in range(times):
        with runtime.login_source().new_context(policy) as connection:
            (row,) = connection.execute(_IDENTITY, [])
            seen.append(row)
    return seen


@pytest.mark.parametrize("policy", ["writer_only", "reader_only"])
def test_each_route_authenticates_the_one_login_over_tls(aws_run: Any, policy: RoutePolicy) -> None:
    runtime = aws_run.adapter().open()
    try:
        ((_pid, login, encrypted),) = _leases(runtime, policy, 1)
    finally:
        runtime.close()

    assert login == aws_run.environment.login
    assert encrypted is True


@pytest.mark.parametrize("policy", ["writer_only", "reader_only"])
def test_a_retained_connection_is_reused_across_leases(aws_run: Any, policy: RoutePolicy) -> None:
    runtime = aws_run.adapter(pool=PoolOptions(min_size=0, max_size=1, num_workers=1)).open()
    try:
        first, second = _leases(runtime, policy, 2)
    finally:
        runtime.close()

    assert first == second


@pytest.mark.parametrize("policy", ["writer_only", "reader_only"])
def test_an_on_demand_connection_is_fresh_and_newly_authenticated_each_time(
    aws_run: Any, policy: RoutePolicy
) -> None:
    runtime = aws_run.adapter(pool=OnDemandOptions()).open()
    try:
        first, second = _leases(runtime, policy, 2)
    finally:
        runtime.close()

    assert first[0] != second[0]
    assert first[1:] == second[1:] == (aws_run.environment.login, True)
