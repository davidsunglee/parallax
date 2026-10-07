"""Clean-install production topology proofs (§8 / `clean_install` marker).

Each of the seven §8 selective topologies is installed into a fresh uv venv
from the locally built wheels, and the installed distribution list + import
space are probed to prove that unselected interchange, lifecycles, the driver,
the credential provider, and the dev-only conformance tooling are all absent.

The two AWS topologies are one either side of the `postgres` extra: what the
credential provider brings with it on its own, and what selecting the extra
adds.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests._support.distributions import Wheelhouse
from tests._support.repo import REPO_ROOT


def _make_venv(root: Path) -> Path:
    # The interpreter under test, because the adapter's wheel is built for it alone.
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    layouts = (root / "bin" / "python", root / "Scripts" / "python.exe")
    python = next((path for path in layouts if path.exists()), layouts[0])
    assert python.exists(), python
    return python


def _install(python: Path, wheelhouse: Wheelhouse, *packages: str) -> None:
    # uv caches a find-links wheel by its path, and pytest's numbered temp paths recur
    # across checkouts, so an unrefreshed install can reuse another tree's same-version wheel.
    refreshed = [arg for package in wheelhouse.wheels for arg in ("--refresh-package", package)]
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--find-links",
            str(wheelhouse.directory),
            *refreshed,
            *packages,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _import_ok(python: Path, module: str) -> bool:
    result = subprocess.run([str(python), "-c", f"import {module}"], capture_output=True, text=True)
    return result.returncode == 0


def _module_absent(python: Path, module: str) -> bool:
    # Resolved rather than imported, so the answer is "nothing is there" and not
    # "something there failed to import"; a failing probe is neither answer.
    probe = (
        "import importlib.util, sys\n"
        f"sys.exit(0 if importlib.util.find_spec({module!r}) is None else 3)"
    )
    result = subprocess.run([str(python), "-c", probe], capture_output=True, text=True)
    assert result.returncode in (0, 3), result.stderr
    return result.returncode == 0


def _dist_installed(python: Path, distribution: str) -> bool:
    result = subprocess.run(
        [str(python), "-c", f"import importlib.metadata as m; m.distribution('{distribution}')"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run(python: Path, source: str) -> str:
    result = subprocess.run([str(python), "-c", source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_core_alone(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-core")

    assert _import_ok(python, "parallax.core")
    # The split SQL-generation package cold-imports from the built wheel.
    # `test_wheels.py` proves the six files SHIP; this proves the private direction
    # actually RESOLVES outside the source tree — a missing module, a leftover
    # import of the retired `compile`, or an import cycle among the five private
    # modules fails here and nowhere else in the clean-install lane.
    assert _import_ok(python, "parallax.core.sql_gen")
    # The execution runtime and read delivery are core's own: both cold-import
    # with no lifecycle extension installed.
    assert _import_ok(python, "parallax.core.execution")
    assert _import_ok(python, "parallax.core.read_delivery")
    # Unselected interchange, lifecycle, adapter, driver, and dev tooling are all
    # absent — the Descriptor Frontend and both of the dependencies it alone
    # declares included, so `parallax-core`'s manifest really is Pydantic only.
    assert not _import_ok(python, "parallax.descriptor")
    assert not _import_ok(python, "parallax.evolution")
    assert not _import_ok(python, "parallax.snapshot")
    assert not _import_ok(python, "parallax.postgres")
    assert not _import_ok(python, "parallax.conformance")
    assert not _import_ok(python, "yaml")
    assert not _import_ok(python, "jsonschema")
    assert not _dist_installed(python, "parallax-descriptor")
    assert not _dist_installed(python, "parallax-evolution")
    assert not _dist_installed(python, "pyyaml")
    assert not _dist_installed(python, "jsonschema")
    assert not _dist_installed(python, "psycopg")
    assert not _dist_installed(python, "botocore")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")


def test_core_and_descriptor(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-descriptor")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.descriptor")
    # Both ingestion dependencies arrive with the frontend that declares them, so
    # no phase has an optional-import failure branch.
    assert _dist_installed(python, "pyyaml")
    assert _dist_installed(python, "jsonschema")
    # The packaged schema loads through `importlib.resources` out of the installed
    # wheel — no repository checkout in sight — and both text doors round-trip
    # through it. Reading the schema from the source tree would still pass a
    # bytes-comparison test; only running the doors in a venv proves the resource
    # resolves where an installed frontend actually looks.
    authoritative = (REPO_ROOT / "core" / "schemas" / "metamodel.schema.json").read_text(
        encoding="utf-8"
    )
    document = {
        "entity": {
            "name": "Author",
            "table": "author",
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        }
    }
    probe = f"""
import json
from importlib import resources

from parallax.descriptor import (
    domain_model_from_json,
    domain_model_from_yaml,
    export_json,
    export_yaml,
)

schema = resources.files("parallax.descriptor").joinpath(
    "_schemas/metamodel.schema.json"
).read_text("utf-8")
document = json.loads({json.dumps(json.dumps(document))})
from_json = domain_model_from_json(json.dumps(document))
from_yaml = domain_model_from_yaml(export_yaml(from_json))
assert export_json(from_yaml) == export_json(from_json)
print(json.dumps({{"schema": schema, "document": export_json(from_yaml)}}))
"""
    answered = json.loads(_run(python, probe))
    assert answered["schema"] == authoritative
    assert json.loads(answered["document"]) == document

    # No sibling lifecycle, evolution, adapter, driver, or conformance harness.
    assert not _import_ok(python, "parallax.evolution")
    assert not _import_ok(python, "parallax.snapshot")
    assert not _import_ok(python, "parallax.postgres")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "parallax-evolution")
    assert not _dist_installed(python, "psycopg")
    assert not _dist_installed(python, "botocore")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")


def test_core_and_snapshot(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-snapshot")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.snapshot")
    # The retired implementation packages are gone from the installed tree, not
    # merely unexported: neither old path resolves to any module.
    assert _module_absent(python, "parallax.snapshot.handle")
    assert _module_absent(python, "parallax.snapshot.materialize")
    # No Descriptor Frontend, descriptor parser, schema validator, sibling
    # evolution/adapter/driver, or conformance harness.
    assert not _import_ok(python, "parallax.descriptor")
    assert not _import_ok(python, "parallax.evolution")
    assert not _import_ok(python, "parallax.postgres")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "parallax-descriptor")
    assert not _dist_installed(python, "parallax-evolution")
    assert not _dist_installed(python, "pyyaml")
    assert not _dist_installed(python, "jsonschema")
    assert not _dist_installed(python, "psycopg")
    assert not _dist_installed(python, "botocore")


def test_core_snapshot_and_postgres(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-snapshot", "parallax-postgres")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.snapshot")
    assert _import_ok(python, "parallax.postgres")
    assert _dist_installed(python, "psycopg")
    # Importing the adapter selects its compiled loaders for the psycopg build
    # the manifest installs, straight out of the installed platform wheel.
    selected = (
        "from parallax.postgres._connection import _TEXT_LOADERS\n"
        "print(_TEXT_LOADERS.float4.__module__)"
    )
    assert _run(python, selected).strip() == "parallax.postgres._cloaders_binary"
    # The optional Descriptor Frontend, the evolution wheel, the dev-only
    # conformance tooling, and the container tooling all stay out.
    assert not _import_ok(python, "parallax.descriptor")
    assert not _import_ok(python, "parallax.evolution")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "parallax-descriptor")
    assert not _dist_installed(python, "parallax-evolution")
    assert not _dist_installed(python, "botocore")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")


def test_core_and_evolution(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-evolution")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.evolution")
    # The scope resolves out of the installed wheel, not merely off the source
    # tree: a private module missing from the built package, or a cycle among the
    # private modules, fails here and nowhere else in the clean-install lane.
    assert _import_ok(python, "parallax.evolution.model_evolution")
    assert _import_ok(python, "parallax.evolution.schema_delta")
    # No Descriptor Frontend, descriptor parser, schema validator, sibling
    # lifecycle, adapter, driver, or conformance harness.
    assert not _import_ok(python, "parallax.descriptor")
    assert not _import_ok(python, "parallax.snapshot")
    assert not _import_ok(python, "parallax.postgres")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "parallax-descriptor")
    assert not _dist_installed(python, "pyyaml")
    assert not _dist_installed(python, "jsonschema")
    assert not _dist_installed(python, "psycopg")
    assert not _dist_installed(python, "botocore")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")


def test_core_and_aws(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-aws")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.aws")
    # The AWS credential chain arrives with the provider that declares it, so
    # resolving a token has no optional-import failure branch.
    assert _dist_installed(python, "botocore")
    # A credential provider is a leaf beside the adapters, so selecting one
    # selects no adapter: neither the Postgres wheel nor its driver is here,
    # and the engine-specific slice is unreachable without the extra that
    # brings that adapter in.
    assert not _import_ok(python, "parallax.aws.postgres")
    assert not _import_ok(python, "parallax.postgres")
    assert not _dist_installed(python, "parallax-postgres")
    assert not _dist_installed(python, "psycopg")
    # No sibling interchange, lifecycle, evolution, or dev tooling either.
    assert not _import_ok(python, "parallax.descriptor")
    assert not _import_ok(python, "parallax.evolution")
    assert not _import_ok(python, "parallax.snapshot")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "parallax-descriptor")
    assert not _dist_installed(python, "parallax-evolution")
    assert not _dist_installed(python, "parallax-snapshot")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")


def test_core_snapshot_postgres_and_aws_postgres(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-snapshot", "parallax-aws[postgres]")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.snapshot")
    # The extra is what selects the adapter, so the engine-specific slice and
    # everything it composes are here together — the whole of what the
    # `core + aws` fixture proves absent without it.
    assert _import_ok(python, "parallax.aws")
    assert _import_ok(python, "parallax.aws.postgres")
    assert _import_ok(python, "parallax.postgres")
    assert _dist_installed(python, "parallax-postgres")
    assert _dist_installed(python, "psycopg")
    assert _dist_installed(python, "botocore")
    # Selecting the extra installs only its own requirements, not a wider install.
    assert not _import_ok(python, "parallax.descriptor")
    assert not _import_ok(python, "parallax.evolution")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "parallax-descriptor")
    assert not _dist_installed(python, "parallax-evolution")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")
