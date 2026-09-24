"""The child-interpreter boundary the whole-interpreter readers require."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.unit.memory_instruments import OWN_INTERPRETER_VARIABLE, require_own_interpreter


def test_a_reader_refuses_a_process_no_boundary_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OWN_INTERPRETER_VARIABLE, raising=False)
    with pytest.raises(RuntimeError, match="in_a_child_interpreter"):
        require_own_interpreter("a reader")


_BOUNDARY_PROBE = (
    "import sys\n\n"
    "from tests.unit.memory_instruments import in_a_child_interpreter, serve_one_measurement\n\n\n"
    "@in_a_child_interpreter\n"
    "def boundary_probe() -> None:\n"
    "    pass\n"
)
_SERVER_ENTRY_POINT = '\n\nif __name__ == "__main__":\n    serve_one_measurement(sys.argv[1])\n'


def _boundary_probe(tmp_path: Path, source: str) -> Callable[[], None]:
    path = tmp_path / "boundary_probe.py"
    path.write_text(source, encoding="utf-8")
    return runpy.run_path(str(path))["boundary_probe"]


def test_a_child_serving_its_measurement_passes(tmp_path: Path) -> None:
    _boundary_probe(tmp_path, _BOUNDARY_PROBE + _SERVER_ENTRY_POINT)()


def test_a_child_that_serves_nothing_fails_its_test(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="exited without serving it"):
        _boundary_probe(tmp_path, _BOUNDARY_PROBE)()
