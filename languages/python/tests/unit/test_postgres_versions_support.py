from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from parallax.conformance import constants
from tests._support.postgres_versions import record_version, selected_image, selected_postgres


class _Control:
    def __init__(self, observed: str) -> None:
        self.observed = observed
        self.closed = False

    def execute(self, sql: str, binds: list[Any]) -> list[list[str]]:
        assert sql == "show server_version" and not binds
        return [[self.observed]]

    def close(self) -> None:
        self.closed = True


class _Run:
    def __init__(self, observed: str) -> None:
        self.session = _Control(observed)

    def control(self) -> _Control:
        return self.session


def test_selection_reaches_provisioning_and_replication_then_restores_default() -> None:
    original = constants.POSTGRES_IMAGE
    with selected_postgres("18.7"):
        assert constants.POSTGRES_IMAGE == "postgres:18.7-alpine"
    assert original == constants.POSTGRES_IMAGE


@pytest.mark.parametrize("version", ["18.5", "19.0", "18.6-alpine", "latest"])
def test_invalid_server_selection_is_refused(version: str) -> None:
    with pytest.raises(ValueError):
        selected_image(version)


@pytest.mark.parametrize("observed", ["18.7", "18.6 (Debian build)"])
def test_record_retains_actual_version_and_refuses_mismatch(tmp_path: Path, observed: str) -> None:
    run = _Run(observed)
    if observed == "18.7":
        with pytest.raises(RuntimeError, match="does not match"):
            record_version(run, "18.6", tmp_path)
    else:
        record_version(run, "18.6", tmp_path)
    assert run.session.closed
    (evidence,) = tmp_path.glob("*.json")
    record = json.loads(evidence.read_text())
    assert {key: record[key] for key in ("selected", "observed", "matched")} == {
        "selected": "18.6",
        "observed": observed,
        "matched": observed.startswith("18.6"),
    }
