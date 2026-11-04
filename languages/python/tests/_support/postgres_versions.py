"""Select and record the exact PostgreSQL server exercised by the main suite."""

from __future__ import annotations

import json
import os
import platform
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from postgres_matrix import versions


def selected_image(version: str) -> str:
    versions(version)
    return f"postgres:{version}-alpine"


@contextmanager
def selected_postgres(version: str) -> Generator[None]:
    from parallax.conformance import constants

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(constants, "POSTGRES_IMAGE", selected_image(version))
        yield


def record_version(run: Any, selected: str, output: Path) -> None:
    control = run.control()  # database-access: profile_run's provisioned main-suite server
    try:
        ((observed,),) = control.execute("show server_version", [])
    finally:
        control.close()
    exact = str(observed).split()[0]
    output.mkdir(parents=True, exist_ok=True)
    record = {
        "selected": selected,
        "observed": str(observed),
        "matched": exact == selected,
        "source_sha": os.environ.get("PARALLAX_SOURCE_SHA", "local"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "python_version": platform.python_version(),
        "shard": os.environ.get("PARALLAX_DB_SHARD", "1/1"),
    }
    (output / f"postgres-{os.getpid()}.json").write_text(
        json.dumps(record) + "\n", encoding="utf-8"
    )
    print(f"PostgreSQL main-suite server: {observed}; selected {selected}", flush=True)
    if exact != selected:
        raise RuntimeError(f"PostgreSQL {observed!r} does not match selected {selected}")
