"""The declared matrix profiles (`parallax.conformance.profile`).

An unprovisioned run reports its profile's dialect and refuses SQL.
"""

from __future__ import annotations

import pytest

from parallax.conformance.profile import profile_for
from parallax.core.dialect import POSTGRES


def test_an_unprovisioned_run_answers_this_profiles_dialect_and_refuses_sql() -> None:
    # A `rejected`-shape run is provisioning-free by contract: it still has to be
    # classified and reported under the dialect it would have executed in, and
    # reading that off the port must not need the port to be usable.
    run = profile_for("pg-full").unprovisioned()
    assert run.name == "pg-full"
    assert run.port.dialect is POSTGRES
    with pytest.raises(AssertionError, match="must not execute SQL"):
        run.port.execute("select 1", [])
    with pytest.raises(AssertionError, match="must not execute SQL"):
        run.port.execute_write("update t set a = 1", [])
    with pytest.raises(AssertionError, match="must not open a transaction"):
        run.port.transaction(lambda _port: None)
