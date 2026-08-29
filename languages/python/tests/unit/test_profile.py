"""The declared matrix profiles (`parallax.conformance.profile`).

A profile is resolved by name out of one declaration, reports the dialect its
adapter executes in, and constitutes the runs made under its name. Everything here
runs without a container and without a connection, which is the property the profile
exists to have: the claim `describe` publishes is derived from these, so deriving it
must not need a database.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence

import pytest
from _second_dialect import BACKTICKED

from _support.repo import PY_ROOT, canonical_snapshot_claim
from parallax.conformance.claim import SNAPSHOT_CLAIM
from parallax.conformance.profile import (
    PROFILES,
    Profile,
    ProfileRun,
    profile_dialects,
    profile_for,
)
from parallax.conformance.provision import Provisioner
from parallax.core.db_port import DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres import PostgresAdapter


def test_profile_for_resolves_the_declared_profile() -> None:
    assert profile_for("pg-full") is PROFILES[0]
    assert profile_for("pg-full") == Profile("pg-full", Provisioner)


def test_profile_for_refuses_a_name_no_profile_declares() -> None:
    with pytest.raises(ValueError, match="unknown profile 'mariadb-full'"):
        profile_for("mariadb-full")


def test_a_profile_reports_its_adapters_dialect_without_a_connection() -> None:
    # The whole point of siting the declaration on the adapter's CLASS: nothing
    # here constructs a provisioner, a container, or a connection, and the
    # dialect is still the one that adapter's own SQL is spelled in.
    profile = profile_for("pg-full")
    assert profile.adapter is PostgresAdapter
    assert profile.dialect is PostgresAdapter.dialect
    assert profile.dialect is POSTGRES


class _StandInPort:
    """An `m-db-port` standing in for a database: it answers a dialect of its own
    and refuses every execution."""

    dialect: Dialect = BACKTICKED

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        raise AssertionError(f"the stand-in port executes nothing: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError(f"the stand-in port executes nothing: {sql!r}")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        raise AssertionError("the stand-in port opens nothing")


def test_a_run_pairs_the_profiles_reporting_name_with_the_port_it_runs_through() -> None:
    # The pairing is what a run is reported from, and only a profile makes one, so
    # the name an envelope carries and the port that produced it cannot be a pair
    # some caller assembled. It answers no dialect of its own — what executes does.
    profile = profile_for("pg-full")
    port = _StandInPort()
    run = profile.on_stand_in(port)
    assert isinstance(run, ProfileRun)
    assert (run.name, run.port) == (profile.name, port)
    assert not hasattr(run, "dialect")


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


def test_an_unprovisioned_run_starts_no_container() -> None:
    probed = _probe(
        "import json, sys\n"
        "from parallax.conformance.profile import profile_for\n"
        "run = profile_for('pg-full').unprovisioned()\n"
        "print(json.dumps({'testcontainers': 'testcontainers' in sys.modules,"
        " 'dialect': run.port.dialect.name, 'profile': run.name}))\n"
    )
    assert probed == {"testcontainers": False, "dialect": "postgres", "profile": "pg-full"}


def test_profile_dialects_are_the_dialects_some_profile_runs() -> None:
    assert profile_dialects() == tuple(sorted({p.dialect.name for p in PROFILES}))
    assert profile_dialects() == ("postgres",)


def test_the_claim_derives_its_dialects_from_the_profiles() -> None:
    # `dialects` is the one capability the claim does not author: a claimed
    # dialect is one some declared profile actually runs the suite against.
    assert SNAPSHOT_CLAIM.dialects == profile_dialects()
    assert (
        SNAPSHOT_CLAIM.capabilities()["dialects"]
        == canonical_snapshot_claim()["capabilities"]["dialects"]
    )


def _probe(source: str) -> dict[str, object]:
    """Run *source* in a fresh interpreter and parse the JSON it prints.

    The imports a module performs are a property of a cold process: by the time
    this suite runs, collection has already imported most of the tree, so an
    in-process reading of `sys.modules` could not see them.
    """
    result = subprocess.run(
        [sys.executable, "-c", source], cwd=PY_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_driver_stays_out_of_the_conformance_adapters_import_graph() -> None:
    # `describe` is answered from the claim, whose dialects are read off an
    # adapter class that lives in the psycopg module — so the reach has to be
    # deferred to the derivation rather than taken at import, or every Docker-free
    # lane would load the driver to answer a question about SQL spelling. Both
    # readings matter: absent at import is the property, and present afterwards is
    # what proves the derivation really reached the concrete adapter rather than
    # answering from something that never needed it.
    probed = _probe(
        "import json, sys\n"
        "import parallax.conformance.adapter as conformance_adapter\n"
        "at_import = 'psycopg' in sys.modules\n"
        "dialects = conformance_adapter.describe()['capabilities']['dialects']\n"
        "after = 'psycopg' in sys.modules\n"
        "print(json.dumps({'at_import': at_import, 'after': after, 'dialects': dialects}))\n"
    )
    assert probed == {"at_import": False, "after": True, "dialects": ["postgres"]}


def test_the_driver_stays_out_of_the_cold_cli_import_graph() -> None:
    # The CLI resolves a profile at module level, so importing it reaches the
    # declaration; `describe` and `compile` must still run without the driver, and
    # a `run` loads it only when it resolves the profile's adapter.
    probed = _probe(
        "import json, sys\n"
        "import parallax.conformance.cli as cli\n"
        "at_import = 'psycopg' in sys.modules\n"
        "profile = cli.profile_for('pg-full')\n"
        "named = 'psycopg' in sys.modules\n"
        "dialect = profile.dialect.name\n"
        "after = 'psycopg' in sys.modules\n"
        "print(json.dumps({'at_import': at_import, 'named': named, 'after': after,"
        " 'dialect': dialect}))\n"
    )
    assert probed == {
        "at_import": False,
        "named": False,
        "after": True,
        "dialect": "postgres",
    }


def test_deriving_a_profiles_dialect_starts_no_container() -> None:
    probed = _probe(
        "import json, sys\n"
        "from parallax.conformance.profile import profile_dialects\n"
        "dialects = list(profile_dialects())\n"
        "print(json.dumps({'testcontainers': 'testcontainers' in sys.modules,"
        " 'dialects': dialects}))\n"
    )
    assert probed == {"testcontainers": False, "dialects": ["postgres"]}
