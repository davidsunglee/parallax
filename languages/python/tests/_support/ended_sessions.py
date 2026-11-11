"""Ending a live backend session from outside it, for proofs about broken connections.

A session under test is never asked for its own backend: on a pooled scope that
question would be the lease's first submission. Each helper works from an
independent control session the live fixture opens instead.
"""

from __future__ import annotations

import time
from typing import Any

__all__ = ["end_backend", "named_backend"]


def end_backend(profile_run: Any, pid: int) -> None:
    """End backend ``pid`` and wait until the server no longer lists it, so what
    reaches it next meets a session that is already gone rather than one still
    on its way out."""
    control = profile_run.control()
    try:
        control.execute("select pg_terminate_backend(?) as ended", [pid])
        give_up = time.monotonic() + 10.0
        while control.execute(
            "select count(*) as listed from pg_stat_activity where pid = ?", [pid]
        ) != [(0,)]:
            assert time.monotonic() < give_up, "the ended backend never left"
            time.sleep(0.01)
    finally:
        control.close()


def named_backend(profile_run: Any, application_name: str) -> int:
    """The one backend of this run's database and login whose connection
    carries ``application_name``."""
    control = profile_run.control()
    try:
        ((pid,),) = control.execute(
            "select pid from pg_stat_activity "
            "where application_name = ? and datname = current_database() and usename = ?",
            [application_name, profile_run.login_identity],
        )
    finally:
        control.close()
    return int(pid)
