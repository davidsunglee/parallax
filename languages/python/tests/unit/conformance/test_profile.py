"""The declared matrix profiles (`parallax.conformance.profile`).

An unprovisioned run reports its profile's dialect and refuses SQL, and the claim
`describe` publishes, a profile's dialect, and a scoped control are each reached in
a cold process without a container or the driver: deriving the claim must not need a
database.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from parallax.conformance.profile import profile_for
from parallax.core.dialect import POSTGRES
from tests._support.repo import PY_ROOT


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


def test_naming_a_scoped_control_loads_no_driver() -> None:
    # The provisioner hands out scoped controls — the session a case drives
    # directly, and the dedicated one an interleaved choreography may destroy —
    # and every psycopg fact those need lives in one native module. Naming a
    # control must cost no driver import: the protocols the engine consumes
    # carry no driver at all, and the provisioner reaches the native module
    # inside the call that opens a session, exactly as it already reaches the
    # adapter class. Both readings matter: absent after the protocols and the
    # provisioner are imported is the property, and present after the native
    # module is what proves the deferral reaches a real psycopg implementation.
    probed = _probe(
        "import json, sys\n"
        "import parallax.conformance._database_control as control\n"
        "import parallax.conformance.provision as provision\n"
        "declared = 'psycopg' in sys.modules\n"
        "import parallax.conformance._postgres_control as native\n"
        "print(json.dumps({'declared': declared, 'native': 'psycopg' in sys.modules,"
        " 'protocols': sorted(control.__all__),"
        " 'provisioner': hasattr(provision.Provisioner, 'control')}))\n"
    )
    assert probed == {
        "declared": False,
        "native": True,
        "protocols": [
            "CaseDatabase",
            "DriverControl",
            "InterleavedExecution",
            "InterleavedExecutionFactory",
            "ModeledExecution",
            "TerminationReport",
        ],
        "provisioner": True,
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
