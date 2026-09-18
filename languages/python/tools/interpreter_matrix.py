"""Child interpreters over every supported CPython minor, for the report tools.

A report that measures on every supported minor starts one child per reading:
the workspace's own interpreter for the current minor, and ``uv run`` against a
throwaway environment for any other. What the range is, how a child of either
kind is started, and what environment it measures in are decided here once so
every report answers the same matrix the same way.

A reading names its minor alone, and envelope provenance records only the
interpreter that spawned the children, so which patch release read a minor is
established by a probe: this module run as a script, through the same command
and environment a reading child gets, answers the interpreter that resolution
reaches. A member probes once per runtime outside every measured window and
records the answer in a metadata sidecar beside its envelope.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

WORKSPACE: Final = Path(__file__).resolve().parents[1]
CURRENT_MINOR: Final = f"{sys.version_info.major}.{sys.version_info.minor}"
SUPPORTED_MINORS: Final = 2
HASH_SEED: Final = "0"
IDENTITY_SCRIPT: Final = Path(__file__).resolve()
METADATA_VERSION: Final = 1

_COVERAGE_VARIABLES: Final = frozenset(
    {"COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"}
)


def supported_minors() -> tuple[str, ...]:
    """Every CPython minor the workspace declares, oldest first.

    Read off the declared floor rather than the interpreter spawning the
    children, so a report run on the prior minor still names the latest one and a
    matrix short by a runtime cannot look complete.
    """
    declared = cast(
        "str",
        tomllib.loads((WORKSPACE / "pyproject.toml").read_text())["project"]["requires-python"],
    )
    floor = declared.removeprefix(">=").strip()
    parts = floor.split(".")
    if not (
        declared.startswith(">=") and len(parts) == 2 and all(part.isdigit() for part in parts)
    ):
        raise SystemExit(
            f"requires-python {declared!r} is not the bare '>=<major>.<minor>' "
            "floor the supported-minor matrix requires"
        )
    major, minor = (int(part) for part in parts)
    return tuple(f"{major}.{minor + above}" for above in range(SUPPORTED_MINORS))


def authority_minor(authority: Mapping[str, object]) -> str:
    """The CPython minor a Budget Contract's authority fingerprint names."""
    version = str(authority.get("cpython", ""))
    parts = version.split(".")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise ValueError(f"authority cpython {version!r} does not name a <major>.<minor>")
    return f"{parts[0]}.{parts[1]}"


def child_environment(runtime: str, namespace: str) -> dict[str, str]:
    """The environment a ``runtime`` child measures in.

    A child of this interpreter's own minor inherits the import path that reached
    here; a child of another minor must not, because this environment's extension
    modules were built for another ABI, so its path is dropped and uv is pointed at
    a throwaway environment named by ``namespace``. Coverage is never inherited,
    and hashing is pinned so container sizes are the same in every child.
    """
    environment = {
        name: value for name, value in os.environ.items() if name not in _COVERAGE_VARIABLES
    }
    environment["PYTHONHASHSEED"] = HASH_SEED
    if runtime == CURRENT_MINOR:
        environment["PYTHONPATH"] = os.pathsep.join(entry for entry in sys.path if entry)
        return environment
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["UV_PROJECT_ENVIRONMENT"] = str(
        Path(tempfile.gettempdir()) / f"parallax-{namespace}-{runtime}"
    )
    return environment


def child_command(runtime: str, script: Path, arguments: Sequence[str]) -> list[str]:
    """What starts ``script`` with ``arguments`` on ``runtime``."""
    if runtime == CURRENT_MINOR:
        return [sys.executable, str(script), *arguments]
    return ["uv", "run", "--frozen", "--python", runtime, "python", str(script), *arguments]


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """The interpreter one runtime's command resolution reaches."""

    implementation: str
    version: str
    executable: str

    def document(self) -> dict[str, object]:
        return {
            "status": "available",
            "implementation": self.implementation,
            "version": self.version,
            "executable": self.executable,
        }


@dataclass(frozen=True, slots=True)
class RuntimeUnavailable:
    reason: str

    def document(self) -> dict[str, object]:
        return {"status": "unavailable", "reason": self.reason}


type RuntimeStatus = RuntimeIdentity | RuntimeUnavailable
type ProbeRunner = Callable[[Sequence[str], Mapping[str, str]], tuple[int, str, str]]
"""Runs one probe command in one environment and answers its exit status,
stdout, and stderr."""


def identity_document() -> dict[str, str]:
    """What the probe child prints: this interpreter's own identity."""
    return {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "executable": sys.executable,
    }


def current_identity() -> RuntimeIdentity:
    """The identity of the interpreter running this process."""
    document = identity_document()
    return RuntimeIdentity(document["implementation"], document["version"], document["executable"])


def run_probe(command: Sequence[str], environment: Mapping[str, str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=WORKSPACE,
            env=dict(environment),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return 127, "", str(error)
    return completed.returncode, completed.stdout, completed.stderr


def probe_identity(
    command: Sequence[str], environment: Mapping[str, str], run: ProbeRunner = run_probe
) -> RuntimeStatus:
    """The identity ``command`` reaches in ``environment``, or why it is unknown."""
    returncode, stdout, stderr = run(command, environment)
    if returncode != 0:
        return RuntimeUnavailable(
            f"the identity probe exited {returncode}: {stderr.strip() or stdout.strip()}"
        )
    lines = stdout.strip().splitlines()
    if not lines:
        return RuntimeUnavailable("the identity probe printed nothing")
    try:
        document = json.loads(lines[-1])
        if not isinstance(document, Mapping):
            raise TypeError("the identity is not an object")
        fields = cast("Mapping[str, object]", document)
        implementation, version, executable = (
            fields["implementation"],
            fields["version"],
            fields["executable"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return RuntimeUnavailable(f"the identity probe answered no identity: {error}")
    if not all(isinstance(value, str) and value for value in (implementation, version, executable)):
        return RuntimeUnavailable("the identity probe answered an incomplete identity")
    return RuntimeIdentity(str(implementation), str(version), str(executable))


def probe_runtime(runtime: str, namespace: str, run: ProbeRunner = run_probe) -> RuntimeStatus:
    """The identity a ``runtime`` reading child of ``namespace`` would get,
    through the same command and environment resolution."""
    return probe_identity(
        child_command(runtime, IDENTITY_SCRIPT, ()), child_environment(runtime, namespace), run
    )


def metadata_document(subject: str, runtimes: Mapping[str, RuntimeStatus]) -> dict[str, object]:
    return {
        "schemaVersion": METADATA_VERSION,
        "subject": subject,
        "runtimes": {runtime: runtimes[runtime].document() for runtime in sorted(runtimes)},
    }


def write_metadata(path: Path, subject: str, runtimes: Mapping[str, RuntimeStatus]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata_document(subject, runtimes), indent=2) + "\n", encoding="utf-8"
    )


def load_metadata(path: Path) -> dict[str, RuntimeStatus]:
    """The runtime identities a metadata sidecar records; ``ValueError`` names
    the first way the document is not one."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"{path} does not hold a metadata document")
    loaded = cast("Mapping[str, object]", document)
    if loaded.get("schemaVersion") != METADATA_VERSION:
        raise ValueError(
            f"{path} has schemaVersion {loaded.get('schemaVersion')!r}, expected {METADATA_VERSION}"
        )
    runtimes = loaded.get("runtimes")
    if not isinstance(runtimes, Mapping):
        raise ValueError(f"{path} runtimes is not an object")
    return {
        str(runtime): runtime_status(status)
        for runtime, status in cast("Mapping[object, object]", runtimes).items()
    }


def runtime_status(document: object) -> RuntimeStatus:
    """One recorded runtime status; ``ValueError`` for any other shape."""
    if not isinstance(document, Mapping):
        raise ValueError(f"runtime status {document!r} is not an object")
    status = cast("Mapping[str, object]", document)
    if status.get("status") == "unavailable":
        reason = status.get("reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError(f"runtime status reason {reason!r} is not a non-empty string")
        return RuntimeUnavailable(reason)
    if status.get("status") != "available":
        raise ValueError(f"runtime status {status.get('status')!r} is not available|unavailable")
    fields = [status.get(name) for name in ("implementation", "version", "executable")]
    if not all(isinstance(value, str) and value for value in fields):
        raise ValueError(f"runtime identity {dict(status)!r} is incomplete")
    return RuntimeIdentity(*(str(value) for value in fields))


if __name__ == "__main__":
    print(json.dumps(identity_document()))
