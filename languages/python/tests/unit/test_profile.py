"""The declared matrix profiles (`parallax.conformance.profile`).

A profile is resolved by name out of one declaration and reports the dialect its
adapter executes in. Everything here runs without a container and without a
connection, which is the property the profile exists to have: the claim `describe`
publishes is derived from these, so deriving it must not need a database.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _support.repo import PY_ROOT, canonical_snapshot_claim
from parallax.conformance.claim import SNAPSHOT_CLAIM
from parallax.conformance.profile import PROFILES, Profile, profile_dialects, profile_for
from parallax.conformance.provision import Provisioner
from parallax.core.dialect import POSTGRES
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
    # lane would load the driver to answer a question about SQL spelling.
    probed = _probe(
        "import json, sys\n"
        "import parallax.conformance.adapter as conformance_adapter\n"
        "at_import = 'psycopg' in sys.modules\n"
        "dialects = conformance_adapter.describe()['capabilities']['dialects']\n"
        "print(json.dumps({'at_import': at_import, 'dialects': dialects}))\n"
    )
    assert probed == {"at_import": False, "dialects": ["postgres"]}


def test_deriving_a_profiles_dialect_starts_no_container() -> None:
    probed = _probe(
        "import json, sys\n"
        "from parallax.conformance.profile import profile_dialects\n"
        "dialects = list(profile_dialects())\n"
        "print(json.dumps({'testcontainers': 'testcontainers' in sys.modules,"
        " 'dialects': dialects}))\n"
    )
    assert probed == {"testcontainers": False, "dialects": ["postgres"]}
